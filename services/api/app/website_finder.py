"""M9e: find a missing company website, honestly.

1. Brave web search for "<Firmenname>" <Ort> (the user's own Brave key, read-only).
2. Directory and social sites are skipped (Gelbe Seiten, Das Örtliche, Google, North Data,
   LinkedIn, …): we never scrape them, we only look at the company's own site.
3. For at most three candidate sites the existing Impressum research runs (robots.txt is
   honoured, egress guard, size and page limits).
4. A site is accepted only when the Impressum names the company (most of its distinctive
   name words) AND shows the known address (postcode plus street). Without a known address
   nothing is accepted.
5. Accepted: website set, Impressum fields stored as cited facts (same path as the normal
   website research). Every company gets a line in the report, including why not.

Runs as job kind ``website_find``: prepare in a transaction, search and fetch outside it,
store in a new transaction.
"""

import math
import os
import re
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select

from app import credentials
from app.db import now
from app.models import Company

MAX_COMPANIES = 25
MAX_CANDIDATES = 3
SKIP_HOSTS = (
    "gelbeseiten.de",
    "dasoertliche.de",
    "dastelefonbuch.de",
    "11880.com",
    "google.",
    "goo.gl",
    "northdata.",
    "linkedin.com",
    "xing.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "wikipedia.org",
    "kununu.com",
    "yelp.",
    "cylex",
    "golocal.de",
    "meinestadt.de",
    "branchenbuch",
    "jameda.de",
    "doctolib.de",
    "anwalt.de",
    "firmenwissen.de",
    "unternehmensregister.de",
    "handelsregister.de",
    "werkenntdenbesten.de",
    "provenexpert.com",
    "trustpilot.",
    "apify.com",
)
ADDRESS_FIELDS = ("Adresse (Impressum)", "Adresse")


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def skipped(url: str) -> bool:
    host = _host(url)
    return not host or any(host == s or host.endswith("." + s) or s in host for s in SKIP_HOSTS)


def known_address(db, ws, company: Company) -> dict:
    from app.journeys import CompanyFact

    value = db.scalar(
        select(CompanyFact.value)
        .where(
            CompanyFact.workspace_id == ws,
            CompanyFact.company_id == company.id,
            CompanyFact.field.in_(ADDRESS_FIELDS),
        )
        .limit(1)
    ) or (company.location or "")
    postcode = re.search(r"\b\d{5}\b", value)
    street = re.match(r"\s*([A-Za-zÄÖÜäöüß.\- ]+?)\s*\d", value)
    city = re.sub(r"^\d{5}\s*", "", value.split(",")[-1].strip()) if "," in value else ""
    return {
        "text": value,
        "postcode": postcode.group(0) if postcode else "",
        "street": street.group(1).strip() if street else "",
        "city": city or (company.location or "").split(",")[0].strip(),
    }


def matches(company_name: str, address: dict, research: dict) -> tuple[bool, str]:
    from app.profile_check import firm_tokens, words

    impressum = research.get("impressum") or {}
    text = " ".join(
        [str((impressum.get(k) or {}).get("value", "")) for k in ("company", "address")]
        + [p.get("text", "")[:4000] for p in research.get("pages", [])[:3]]
    )
    seen = set(words(text))
    tokens = firm_tokens(company_name)
    if not tokens:
        return False, "Firmenname ohne unterscheidbare Wörter"
    hits = sum(t in seen for t in tokens)
    if hits < max(1, math.ceil(0.6 * len(tokens))):
        return False, "Name im Impressum nicht gefunden"
    if not address["postcode"] or not address["street"]:
        return False, "Keine bekannte Adresse zum Abgleich"
    street = words(address["street"].replace("str.", "strasse").replace("Str.", "Strasse"))
    folded = " ".join(words(text.replace("str.", "strasse").replace("Str.", "Strasse")))
    if address["postcode"] not in text or not street or street[0] not in folded:
        return False, "Adresse im Impressum passt nicht"
    return True, "Name und Adresse stimmen mit dem Impressum überein"


def web_search(key: str, client=None):
    from app.profile_check import BRAVE_URL
    from app.providers.ai import request_json

    gap = float(os.getenv("BRAVE_MIN_INTERVAL_SECONDS", "1.1"))
    last = [0.0]

    def run(query: str) -> list[str]:
        wait = gap - (time.monotonic() - last[0])
        if wait > 0:
            time.sleep(wait)
        last[0] = time.monotonic()
        data, _ = request_json(
            "GET",
            BRAVE_URL,
            client=client,
            params={"q": query[:380], "count": 10, "country": "DE", "search_lang": "de"},
            headers={"Accept": "application/json", "X-Subscription-Token": key},
        )
        return [str(r.get("url") or "") for r in (data.get("web") or {}).get("results", [])]

    return run


# ---- job phases ---------------------------------------------------------------------------


def prepare(db, job) -> dict:
    from app.providers import site_research

    key = credentials.get("BRAVE_SEARCH_API_KEY")
    if not key:
        raise HTTPException(409, "brave_key_missing")
    if not site_research.enabled():
        raise HTTPException(409, "research_disabled")
    ws = job.workspace_id
    ids = job.payload.get("company_ids") or []
    stmt = select(Company).where(
        Company.workspace_id == ws, (Company.website.is_(None)) | (Company.website == "")
    )
    if ids:
        stmt = stmt.where(Company.id.in_(ids))
    items = []
    for company in db.scalars(stmt.order_by(Company.name).limit(MAX_COMPANIES)):
        items.append(
            {"company_id": company.id, "name": company.name}
            | {"address": known_address(db, ws, company)}
        )
    return {"key": key, "items": items}


def run(context, search=None, research=None) -> dict:
    from app.providers.ai import ProviderError
    from app.providers.site_research import research_site

    search = search or web_search(context["key"])
    research = research or research_site
    report = []
    for item in context["items"]:
        address = item["address"]
        query = f'"{item["name"]}" {address["city"]}'.strip()
        entry = {"company_id": item["company_id"], "query": query, "checked": []}
        try:
            urls = search(query)
        except ProviderError as exc:
            entry |= {"result": "error", "reason": f"Suche fehlgeschlagen: {exc.code}"}
            report.append(entry)
            continue
        roots, seen = [], set()
        for url in urls:
            if skipped(url) or not url.startswith("https://"):
                continue
            host = _host(url)
            if host not in seen:
                seen.add(host)
                roots.append(f"https://{urlsplit(url).hostname}/")
        for root in roots[:MAX_CANDIDATES]:
            try:
                found = research(root)
            except ProviderError as exc:
                entry["checked"].append({"url": root, "reason": exc.code})
                continue
            ok, why = matches(item["name"], address, found)
            entry["checked"].append({"url": root, "reason": why})
            if ok:
                entry |= {"result": "found", "website": found.get("website") or root}
                entry["research"] = found
                break
        else:
            entry |= {
                "result": "not_found",
                "reason": "Kein Treffer, bei dem Name und Adresse passen"
                if roots
                else "Nur Verzeichnis- oder Social-Media-Treffer",
            }
        report.append(entry)
    return {"items": report}


def finalize(db, job, result: dict) -> dict:
    from app.research_flow import finalize_site_research

    ws = job.workspace_id
    summary = {"found": 0, "not_found": 0, "error": 0, "items": []}
    for entry in result.get("items", []):
        company = db.scalar(
            select(Company).where(Company.workspace_id == ws, Company.id == entry["company_id"])
        )
        if company is None:
            continue
        outcome = entry.get("result", "error")
        summary[outcome] = summary.get(outcome, 0) + 1
        facts = 0
        if outcome == "found" and not company.website:
            company.website = entry["website"]
            stored = finalize_site_research(
                db,
                SimpleNamespace(
                    workspace_id=ws, payload={"company_id": company.id}, actor_id=job.actor_id
                ),
                entry["research"],
            )
            facts = stored.get("facts", 0)
        company.provenance = (company.provenance or {}) | {
            "website_finder": {
                "checked_at": now().isoformat(),
                "query": entry["query"],
                "result": outcome,
                "website": entry.get("website"),
                "reason": entry.get("reason", ""),
                "candidates": entry.get("checked", []),
            }
        }
        summary["items"].append(
            {
                "company_id": company.id,
                "company": company.name,
                "result": outcome,
                "website": entry.get("website"),
                "reason": entry.get("reason")
                or next((c["reason"] for c in entry.get("checked", [])[-1:]), ""),
                "facts": facts,
            }
        )
    db.flush()
    return summary
