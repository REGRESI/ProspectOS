"""Domain-bound company website research with Impressum extraction.

Boundaries (all enforced in code):
- only the company's own website host (and its www/apex variant) is fetched;
- every hop goes through ``web_guard`` (public IPs only, pinned connection, no proxy);
- robots.txt is honoured for our user agent; at most MAX_PAGES pages, MAX_BYTES each,
  10 s per request, >= 1 s between requests to the same host;
- only text/html or text/plain; scripts/styles dropped; text is untrusted data.
Extracted Impressum fields are labelled "extracted" with the source URL and the exact
line they came from; nothing is inferred.
"""

import os
import re
import threading
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app import credentials
from app.providers.ai import ProviderError
from app.providers.web_guard import check_url, guarded_client

MAX_PAGES = 4
MAX_BYTES = 2 * 1024 * 1024  # bounded; modern pages carry large inline scripts
HOME_MAX_BYTES = 2 * 1024 * 1024  # footers with the Impressum link sit at the end
IMPRESSUM_PATHS = ("/impressum", "/impressum/", "/impressum.html", "/imprint", "/kontakt/impressum")
_lock = threading.Lock()
_last: dict[str, float] = {}


def enabled() -> bool:
    # Own egress guard is built in; the legacy single-page path keeps its own flags.
    return os.getenv("RESEARCH_ENABLED", "false").lower() == "true"


def user_agent() -> str:
    contact = credentials.get("OSM_CONTACT", "").strip()
    return "ProspectOSResearch/1.0" + (f" (+{contact})" if contact and len(contact) < 200 else "")


class _Page(HTMLParser):
    BLOCK = {
        "p",
        "div",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "tr",
        "td",
        "section",
        "address",
        "footer",
        "header",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.lines = [""]
        self.title = []
        self.in_title = False
        self.links: list[tuple[str, str]] = []
        self._href = None
        self._anchor = []
        self.mailto: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "iframe", "svg", "template"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag in self.BLOCK:
            self.lines.append("")
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.lower().startswith("mailto:"):
                self.mailto.append(href[7:].split("?", 1)[0])
            self._href, self._anchor = href, []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "iframe", "svg", "template"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._anchor).strip()))
            self._href = None
        if tag in self.BLOCK:
            self.lines.append("")

    def handle_data(self, data):
        if self.hidden:
            return
        if self.in_title:
            self.title.append(data)
            return
        if self._href is not None:
            self._anchor.append(data)
        self.lines[-1] += data

    def text_lines(self) -> list[str]:
        out = []
        for line in self.lines:
            clean = " ".join(line.split())
            if clean and (not out or out[-1] != clean):
                out.append(clean)
        return out


def _allowed_hosts(website: str) -> set[str]:
    host = (urlsplit(website).hostname or "").lower().rstrip(".")
    if not host:
        raise ProviderError("invalid_website")
    apex = host[4:] if host.startswith("www.") else host
    return {apex, "www." + apex}


def _throttle(host: str):
    with _lock:
        wait = 1.0 - (time.monotonic() - _last.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last[host] = time.monotonic()


def _get(
    client, url: str, allowed: set[str], *, max_bytes=MAX_BYTES
) -> tuple[str, str, str] | None:
    """Return (final_url, content_type, text) or None for 404/410. Follows <=3 redirects
    only within the company's own hosts."""
    for _ in range(4):
        parsed = check_url(url)
        if parsed.host.lower() not in allowed:
            raise ProviderError("redirect_outside_company_domain")
        _throttle(parsed.host)
        try:
            with client.stream(
                "GET", url, headers={"User-Agent": user_agent(), "Accept": "text/html,text/plain"}
            ) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    location = r.headers.get("location")
                    if not location:
                        raise ProviderError("invalid_research_response")
                    url = urljoin(url, location)
                    continue
                if r.status_code in (404, 410):
                    return None
                if r.status_code != 200:
                    raise ProviderError("research_unavailable", retryable=r.status_code >= 500)
                ctype = r.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if ctype not in ("text/html", "application/xhtml+xml", "text/plain"):
                    return None
                body = bytearray()
                for chunk in r.iter_bytes():
                    body.extend(chunk)
                    if len(body) >= max_bytes:
                        # Hard cap: stop reading, evaluate the bounded prefix only.
                        del body[max_bytes:]
                        break
                encoding = r.charset_encoding or "utf-8"
                try:
                    text = body.decode(encoding, errors="replace")
                except LookupError:
                    text = body.decode("utf-8", errors="replace")
                return url, ctype, text
        except httpx.TimeoutException:
            raise ProviderError("research_timeout", retryable=True) from None
        except httpx.HTTPError:
            raise ProviderError("research_unavailable", retryable=True) from None
    raise ProviderError("research_redirect_limit")


def _parse(url: str, ctype: str, text: str) -> dict:
    if ctype == "text/plain":
        return {
            "url": url,
            "title": "",
            "lines": [ln.strip() for ln in text.splitlines() if ln.strip()],
            "links": [],
            "mailto": [],
        }
    page = _Page()
    page.feed(text)
    return {
        "url": url,
        "title": " ".join(" ".join(page.title).split())[:300],
        "lines": page.text_lines(),
        "links": page.links,
        "mailto": page.mailto,
    }


def _find_impressum_link(page: dict, allowed: set[str]) -> str | None:
    scored = []
    for href, label in page["links"]:
        target = urljoin(page["url"], href)
        host = (urlsplit(target).hostname or "").lower()
        if host not in allowed:
            continue
        hay = (href + " " + label).lower()
        if "impressum" in hay or "imprint" in hay or "legal-notice" in hay or "legal notice" in hay:
            scored.append((0 if "impressum" in label.lower() else 1, target.split("#", 1)[0]))
    return sorted(scored)[0][1] if scored else None


# ---- Impressum extraction -------------------------------------------------------

LEGAL_FORM = re.compile(
    r"\b(Gesellschaft mit beschränkter Haftung|Aktiengesellschaft|Kommanditgesellschaft|Partnerschaftsgesellschaft|GmbH\s*&\s*Co\.?\s*KG|gGmbH|GmbH|AG|UG(?:\s*\(haftungsbeschränkt\))?|KGaA|KG|OHG|GbR|PartG(?:\s*mbB)?|mbB|e\.\s?K\.|e\.\s?Kfr\.|e\.\s?V\.|eG|SE|Ltd\.?|Inc\.?)(?=$|[\s,.;)])"
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
OBFUSCATED = re.compile(
    r"([A-Za-z0-9._%+-]+)\s*(?:\(at\)|\[at\]|\{at\}| at )\s*([A-Za-z0-9-]+(?:\s*(?:\.|\(dot\)|\[dot\]|\(punkt\))\s*[A-Za-z0-9-]+)+)",
    re.I,
)
PHONE_LABEL = re.compile(
    r"^(?:Tel(?:efon)?\.?|Fon|Phone|T\.?)\s*[:.]?\s*(\+?[\d][\d\s/()\-–.]{5,24}\d)", re.I
)
PHONE_INLINE = re.compile(
    r"(?:Tel(?:efon)?\.?|Fon|Phone)\s*[:.]?\s*(\+?[\d][\d\s/()\-–.]{5,24}\d)", re.I
)
REGISTER = re.compile(r"\b(HRB|HRA|PR|VR|GnR|GsR)\s*[:.]?\s*(\d{2,7}(?:\s?[A-Z]{1,2}\b)?)")
COURT = re.compile(
    r"(?:Amtsgericht|Registergericht)\s*[:]?\s*([A-ZÄÖÜ][\wÄÖÜäöüß.\- ]{2,40}?)(?=$|[,;:]|\s+HR[AB]|\s+unter|\s+Register)"
)
VAT = re.compile(r"\bDE\s?\d{3}\s?\d{3}\s?\d{3}\b")
PLZ_CITY = re.compile(r"\b(\d{5})\s+([A-ZÄÖÜ][\wÄÖÜäöüß.\- ]{1,40})")
STREET = re.compile(
    r"([A-ZÄÖÜ][\wÄÖÜäöüß.\- ]{1,50}(?:straße|strasse|str\.|weg|platz|allee|gasse|ring|damm|ufer|markt|steig|hof|park|chaussee)\s*\d+\s?[a-zA-Z]?(?:\s?[-–]\s?\d+)?)",
    re.I,
)
PEOPLE_LABEL = re.compile(
    r"(?:^|[•|;]\s*|\s)(?:Geschäftsführ(?:er(?:in|innen)?|ung|ende\s+Gesellschafter(?:in)?)|Vertreten\s+durch(?:\s+(?:den|die)\s+(?:Geschäftsführer(?:in)?|Vorstand))?|Vertretungsberechtigte?r?(?:\s+(?:Geschäftsführer(?:in)?|Gesellschafter(?:in)?|Vorstand))?|Inhaber(?:in)?|Vorstand|Vorstände|Persönlich\s+haftende[rn]?\s+Gesellschafter(?:in)?|Geschäftsinhaber(?:in)?)\s*[:.]?\s*([^•|]*)",
    re.I,
)
CREDIT = re.compile(
    r"Produktion|Konzept|Design|Umsetzung|Realisierung|Hosting|Agentur|Programmierung|Bildnachweis|Fotonachweis|Fotos|Haftung|Urheber|Datenschutz|Amtsgericht|Register|Aufsichtsrat|Eigentum",
    re.I,
)
TITLES = re.compile(
    r"\b(?:Prof(?:essor)?|Dr|Dipl|Ing|med|jur|rer|nat|oec|habil|E\.\s?h|h\.\s?c|Wi|Kfm|Kffr|FH|MBA|LL\.M|M\.A|B\.A|M\.Sc|B\.Sc)\b\.?(?:-|\s)*",
    re.I,
)
NAME = re.compile(
    r"^(?:(?:Dr|Prof|Dipl|Ing|med|jur|rer|nat)\.?[-\s]*)*[A-ZÄÖÜ][a-zäöüß]+(?:[-\s][A-ZÄÖÜ][a-zäöüß]+){1,3}$"
)


def _names(raw: str) -> list[str]:
    raw = re.sub(r"\([^)]*\)", "", raw)
    parts = re.split(r",|;| und | & |/|\bsowie\b", raw)
    names = []
    for part in parts:
        candidate = " ".join(TITLES.sub(" ", part).split()).strip(" .:-")
        if NAME.match(candidate) and len(candidate) <= 60:
            names.append(candidate)
    return names[:5]


def _company(window, put, found):
    def ends_with_form(line):
        matches = list(LEGAL_FORM.finditer(line))
        return bool(matches) and matches[-1].end() >= len(line.rstrip(" .")) - 1

    exact = next(
        (ln for ln in window if len(ln) <= 90 and not CREDIT.search(ln) and ends_with_form(ln)),
        None,
    )
    if exact:
        put("company", exact.rstrip(" ."), exact)
    else:
        for ln in window:
            if CREDIT.search(ln) and not re.search(r"Eigentum", ln):
                continue
            m = LEGAL_FORM.search(ln)
            if not m:
                continue
            words = re.findall(r"[A-ZÄÖÜ0-9][\wÄÖÜäöüß&.\-]*", ln[: m.start()])
            prefix = []
            for w in reversed(ln[: m.start()].split()):
                if w in words:
                    prefix.insert(0, w)
                else:
                    break
            if prefix:
                put("company", " ".join(prefix[-6:]) + " " + m.group(1), ln)
                break
    if "company" in found:
        forms = list(LEGAL_FORM.finditer(found["company"]["value"]))
        lf = forms[-1] if forms else None
        if lf:
            put("legal_form", re.sub(r"\s+", " ", lf.group(1)), found["company"]["line"])


def extract_impressum(page: dict) -> dict:
    """Deterministic field extraction. Each value carries the line it was read from."""
    lines = page["lines"]
    url = page["url"]
    start = next(
        (
            i
            for i, ln in enumerate(lines)
            if ln.lower().strip(" :")
            in ("impressum", "imprint", "angaben gemäß § 5 tmg", "angaben gemäß § 5 ddg")
        ),
        0,
    )
    window = []
    for line in lines[start : start + 160]:
        # Join table-style "Label:" cells with their value cell.
        if window and window[-1].endswith(":") and len(window[-1]) <= 40:
            window[-1] = window[-1] + " " + line
        else:
            window.append(line)
    found: dict[str, dict] = {}

    def put(field, value, line):
        if value and field not in found:
            found[field] = {"value": value.strip()[:300], "source_url": url, "line": line[:300]}

    for i, line in enumerate(window):
        people = PEOPLE_LABEL.search(line)
        if people and "managers" not in found:
            rest = people.group(1).strip() or (window[i + 1] if i + 1 < len(window) else "")
            names = _names(rest)
            if names:
                put("managers", ", ".join(names), line if people.group(1) else line + " " + rest)
        if "address" not in found:
            plz = PLZ_CITY.search(line)
            if plz:
                street_line = line if STREET.search(line) else (window[i - 1] if i > 0 else "")
                street = STREET.search(street_line)
                if street:
                    put(
                        "address",
                        f"{street.group(1).strip()}, {plz.group(1)} {plz.group(2).strip()}",
                        (street_line + " | " + line) if street_line != line else line,
                    )
        if "phone" not in found:
            m = PHONE_LABEL.search(line) or PHONE_INLINE.search(line)
            if m:
                put("phone", " ".join(m.group(1).split()), line)
        if "register_id" not in found:
            m = REGISTER.search(line)
            if m:
                put("register_id", f"{m.group(1)} {m.group(2).strip()}", line)
        if "register_court" not in found:
            m = COURT.search(line)
            if m:
                put(
                    "register_court",
                    "Amtsgericht " + re.sub(r"^Amtsgericht\s+", "", m.group(1).strip()),
                    line,
                )
        if "vat_id" not in found:
            m = VAT.search(line)
            if m:
                put("vat_id", m.group(0).replace(" ", ""), line)
        if "email" not in found:
            m = EMAIL.search(line)
            if m:
                put("email", m.group(0), line)
            else:
                ob = OBFUSCATED.search(line)
                if ob:
                    domain = re.sub(
                        r"\s*(?:\(dot\)|\[dot\]|\(punkt\))\s*", ".", ob.group(2)
                    ).replace(" ", "")
                    put("email", f"{ob.group(1)}@{domain}", line)
    _company(window, put, found)
    if "email" not in found and page.get("mailto"):
        address = page["mailto"][0]
        if EMAIL.fullmatch(address):
            put("email", address, "mailto:" + address)
    return found


def research_site(website: str, *, client=None) -> dict:
    if not enabled():
        raise ProviderError("research_disabled")
    allowed = _allowed_hosts(website)
    root = website if website.startswith(("http://", "https://")) else "https://" + website
    own = client is None
    client = client or guarded_client()
    retrieved_at = datetime.now(UTC).isoformat()
    try:
        rules: dict[str, RobotFileParser] = {}

        def permitted(url):
            host = (urlsplit(url).hostname or "").lower()
            if host not in rules:
                parser = RobotFileParser()
                try:
                    got = _get(client, f"https://{host}/robots.txt", {host}, max_bytes=128 * 1024)
                except ProviderError as exc:
                    if exc.code == "unsafe_url":
                        raise
                    # Missing/unreadable robots.txt (incl. redirect elsewhere) = no rules.
                    got = None
                parser.parse(got[2].splitlines() if got else [])
                rules[host] = parser
            return rules[host].can_fetch(user_agent().split(" ", 1)[0], url)

        pages = []
        home_url = root if root.endswith("/") or urlsplit(root).path else root + "/"
        if not permitted(home_url):
            raise ProviderError("robots_disallowed")
        try:
            got = _get(client, home_url, allowed, max_bytes=HOME_MAX_BYTES)
        except ProviderError as exc:
            if exc.code != "redirect_outside_company_domain":
                raise
            # The company's own homepage moved to another domain (e.g. .de -> .com):
            # follow that single hop and re-bind research to the new domain.
            location = ""
            url = home_url
            for _ in range(3):
                with client.stream("GET", url, headers={"User-Agent": user_agent()}) as r:
                    location = r.headers.get("location", "")
                if not location:
                    break
                url = urljoin(url, location)
                if (urlsplit(url).hostname or "").lower() not in allowed:
                    break
            allowed = _allowed_hosts(url)
            if not permitted(url):
                raise ProviderError("robots_disallowed") from None
            got = _get(client, url, allowed, max_bytes=HOME_MAX_BYTES)
        if not got:
            raise ProviderError("website_not_found")
        home = _parse(*got)
        pages.append(home)
        candidates = [link for link in [_find_impressum_link(home, allowed)] if link]
        base = f"{urlsplit(home['url']).scheme}://{urlsplit(home['url']).hostname}"
        prefix = "/".join(urlsplit(home["url"]).path.split("/")[:2]).rstrip("/")
        if prefix and len(prefix) <= 8:  # language prefix like /de or /de-de
            candidates += [base + prefix + p for p in IMPRESSUM_PATHS[:2]]
        candidates += [base + p for p in IMPRESSUM_PATHS]
        impressum_page = None
        for target in dict.fromkeys(candidates):
            if len(pages) >= MAX_PAGES:
                break
            if not permitted(target):
                continue
            got = _get(client, target, allowed)
            if not got:
                continue
            page = _parse(*got)
            pages.append(page)
            path = urlsplit(page["url"]).path.lower()
            if any(k in path for k in ("impressum", "imprint", "legal")) or any(
                "impressum" in ln.lower() or "imprint" in ln.lower() or "§ 5" in ln
                for ln in page["lines"][:400]
            ):
                impressum_page = page
                break
        fields = extract_impressum(impressum_page) if impressum_page else {}
        # A homepage footer often carries the Impressum itself (single-page sites).
        if not fields:
            fields = extract_impressum(home)
        return {
            "website": home["url"],
            "retrieved_at": retrieved_at,
            "impressum_url": impressum_page["url"] if impressum_page else None,
            "impressum": fields,
            "pages": [
                {"url": p["url"], "title": p["title"], "text": "\n".join(p["lines"])[:8000]}
                for p in pages
            ],
            "robots": "honoured",
        }
    finally:
        if own:
            client.close()
