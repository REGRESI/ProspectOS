"""Find and verify LinkedIn profiles of contacts through the official Brave Search API.

ProspectOS never calls linkedin.com. It asks Brave for public search results
(``linkedin "Vorname Nachname" Firma Ort``) and judges each hit:

- verified: every name token appears in the hit AND the company or the place appears
  in the hit. Only then the profile URL is used.
- unsure: the name matches but neither company nor place does, or several different
  profiles match. Unsure profiles are never used.
- not_found: no LinkedIn profile in the results.

Brave's terms forbid storing search results beyond the transient operation, so titles
and snippets are never written. Stored are only the profile URL and a reason in
ProspectOS' own words ("Name und Firma stimmen überein"). The user decided this on
2026-11-07; the report asks them to check their Brave plan.

When no contact of a company has a verified profile, a role search looks for the
facility, office or practice manager or the head of administration. A hit becomes a new
contact only if the company AND the role appear in the hit (and the hit reads like a
person's name).
"""

import hashlib
import os
import re
import time
import unicodedata
from typing import Callable

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import credentials
from app.db import now
from app.models import Company, Contact

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"
STOP = {
    "gmbh",
    "und",
    "der",
    "die",
    "das",
    "co",
    "kg",
    "mbh",
    "ohg",
    "gbr",
    "ag",
    "ug",
    "ev",
    "e",
    "v",
    "partg",
    "mbb",
    "praxis",
    "fur",
    "für",
    "von",
    "im",
    "in",
    "am",
    "the",
}
ROLES = (
    ("Facility Manager", ("facility",)),
    ("Office Manager", ("office manag", "office-manag", "officemanag")),
    ("Praxismanager", ("praxismanag", "praxis manag", "praxisleitung")),
    (
        "Leitung Verwaltung",
        (
            "leitung verwaltung",
            "verwaltungsleit",
            "leiter verwaltung",
            "leiterin verwaltung",
            "kaufmannische leitung",
        ),
    ),
    ("Büroleitung", ("buroleit", "buro leitung", "leitung buro")),
)
ROLE_QUERY = '("Facility Manager" OR "Office Manager" OR Praxismanagerin OR Praxismanager OR "Leitung Verwaltung" OR Büroleitung)'
Search = Callable[[str], list[dict]]


def fold(text: str) -> str:
    text = (text or "").casefold().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def name_tokens(first: str, last: str) -> list[str]:
    from app.today import PROFESSION

    name = PROFESSION.sub("", f"{first or ''} {last or ''}").strip()
    return [t for t in words(name) if len(t) > 1]


def firm_tokens(company_name: str) -> list[str]:
    return [t for t in words(company_name) if len(t) >= 3 and t not in STOP]


def city_of(location: str) -> str:
    first = (location or "").split("/")[0].split(",")[0].strip()
    return re.sub(r"^\d{5}\s*", "", first)[:60]


def profile_url(url: str) -> str | None:
    from app.today import normalize_profile_url

    try:
        return normalize_profile_url(str(url or ""))
    except HTTPException:
        return None


def _hit_text(hit: dict) -> str:
    return " ".join(words(f"{hit.get('title', '')} {hit.get('description', '')}"))


def _slug_words(url: str) -> list[str]:
    return words(url.rsplit("/in/", 1)[-1].replace("-", " "))


def judge(names: list[str], firm: list[str], city: str, hit: dict) -> dict | None:
    """One search hit against a known person. Returns status, url and own-words reason."""
    url = profile_url(hit.get("url", ""))
    if not url or not names:
        return None
    text = f" {_hit_text(hit)} "
    slug = set(_slug_words(url))
    name_ok = all(f" {t} " in text or t in slug for t in names)
    if not name_ok:
        return None
    # "Autohaus Wild" and Mr Wild: the surname alone is no company match.
    firm = [t for t in firm if t not in names]
    firm_ok = bool(firm) and any(f" {t} " in text for t in firm)
    place = " ".join(words(city))
    place_ok = bool(place) and f" {place} " in text
    if firm_ok and place_ok:
        reason = "Name, Firma und Ort stimmen im Suchtreffer überein"
    elif firm_ok:
        reason = "Name und Firma stimmen im Suchtreffer überein"
    elif place_ok:
        reason = "Name und Ort stimmen im Suchtreffer überein"
    else:
        return {"status": "unsure", "url": url, "reason": "Nur der Name stimmt überein", "rank": 0}
    return {"status": "verified", "url": url, "reason": reason, "rank": firm_ok * 2 + place_ok}


def check_person(person: dict, search: Search) -> dict:
    names = name_tokens(person["first_name"], person["last_name"])
    firm = firm_tokens(person.get("company", ""))
    city = city_of(person.get("location", ""))
    display = " ".join(filter(None, [person["first_name"], person["last_name"]]))
    if len(names) < 2:
        return {"status": "unsure", "url": None, "reason": "Name zu kurz für eine sichere Suche"}
    keyword = firm[0] if firm else ""
    queries = [
        f'linkedin "{display}" {keyword} {city}'.strip(),
        f'linkedin "{display}" {city}'.strip(),
    ]
    verified: dict[str, dict] = {}
    unsure: dict | None = None
    for query in dict.fromkeys(queries):
        for hit in search(query):
            verdict = judge(names, firm, city, hit)
            if not verdict:
                continue
            if verdict["status"] == "verified":
                old = verified.get(verdict["url"])
                if not old or verdict["rank"] > old["rank"]:
                    verified[verdict["url"]] = verdict
            elif not unsure:
                unsure = verdict
        if verified:
            break
    # A company match outweighs place-only matches (many people share a town). Several
    # company matches, or several place-only matches, stay unsure.
    with_firm = [v for v in verified.values() if v["rank"] >= 2]
    candidates = with_firm or list(verified.values())
    if len(candidates) > 1:
        return {"status": "unsure", "url": None, "reason": "Mehrere passende Profile gefunden"}
    if candidates:
        return {k: candidates[0][k] for k in ("status", "url", "reason")}
    if unsure:
        return {"status": "unsure", "url": None, "reason": unsure["reason"]}
    return {"status": "not_found", "url": None, "reason": "Kein LinkedIn-Profil gefunden"}


def _person_name(title: str) -> tuple[str, str] | None:
    head = re.split(r"\s+[–—|-]\s+|\s*\|\s*", title or "")[0].strip()
    head = re.sub(r"\s*\(.*?\)\s*", " ", head).strip()
    parts = head.split()
    if not 2 <= len(parts) <= 4:
        return None
    if not all(re.fullmatch(r"[A-ZÄÖÜ][a-zäöüßéèáàç'\-]+\.?", p) for p in parts):
        return None
    if any(fold(p).strip(".") in STOP or fold(p) in {"linkedin", "gmbh"} for p in parts):
        return None
    return " ".join(parts[:-1]), parts[-1]


def role_search(company: dict, search: Search, known_urls: set[str]) -> list[dict]:
    firm = firm_tokens(company["name"])
    if not firm:
        return []
    city = city_of(company.get("location", ""))
    query = f'linkedin "{" ".join(firm[:2])}" {ROLE_QUERY} {city}'.strip()
    found, urls = [], set()
    for hit in search(query):
        url = profile_url(hit.get("url", ""))
        if not url or url in known_urls or url in urls:
            continue
        text = f" {_hit_text(hit)} "
        if not any(f" {t} " in text for t in firm):
            continue
        role = next((label for label, keys in ROLES if any(k in text for k in keys)), None)
        name = _person_name(str(hit.get("title", "")))
        if not role or not name:
            continue
        urls.add(url)
        found.append(
            {
                "first_name": name[0],
                "last_name": name[1],
                "role": role,
                "url": url,
                "reason": f"Firma und Rolle „{role}“ stimmen im Suchtreffer überein",
            }
        )
    return found[:2]


def brave_search(key: str, client=None, interval: float | None = None) -> Search:
    from app.providers.ai import request_json

    gap = float(os.getenv("BRAVE_MIN_INTERVAL_SECONDS", "1.1")) if interval is None else interval
    last = [0.0]

    def run(query: str) -> list[dict]:
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
        return [
            {
                "url": str(r.get("url") or ""),
                "title": str(r.get("title") or ""),
                "description": str(r.get("description") or ""),
            }
            for r in (data.get("web") or {}).get("results", [])
            if "linkedin.com/in/" in str(r.get("url"))
        ]

    return run


# ---- job phases ------------------------------------------------------------------------


def prepare(db, job) -> dict:
    ws = job.workspace_id
    ids = job.payload.get("contact_ids") or []
    # Confirmed by a user, or a URL the user imported: never overwritten by the search.
    stmt = select(Contact).where(
        Contact.workspace_id == ws,
        Contact.linkedin_status != "confirmed",
        (Contact.linkedin_url.is_(None)) | (Contact.linkedin_status == "verified"),
    )
    stmt = (
        stmt.where(Contact.id.in_(ids))
        if ids
        else stmt.where(Contact.linkedin_status == "unchecked")
    )
    contacts = db.scalars(stmt.order_by(Contact.created_at).limit(job.payload["limit"])).all()
    companies = {
        c.id: c
        for c in db.scalars(
            select(Company).where(
                Company.workspace_id == ws,
                Company.id.in_({c.company_id for c in contacts if c.company_id}),
            )
        )
    }
    people = [
        {
            "id": c.id,
            "first_name": c.first_name,
            "last_name": c.last_name,
            "company_id": c.company_id,
            "company": companies[c.company_id].name if c.company_id in companies else "",
            "location": (companies[c.company_id].location if c.company_id in companies else "")
            or c.location,
        }
        for c in contacts
    ]
    roles: list[dict] = []
    if job.payload.get("roles", True):
        profiled = set(
            db.scalars(
                select(Contact.company_id).where(
                    Contact.workspace_id == ws,
                    Contact.linkedin_url.is_not(None),
                    Contact.linkedin_status.in_(["verified", "confirmed", "unchecked"]),
                )
            )
        )
        with_contacts = set(
            db.scalars(select(Contact.company_id).where(Contact.workspace_id == ws))
        )
        open_companies = db.scalars(
            select(Company)
            .where(Company.workspace_id == ws, Company.role_search_at.is_(None))
            .order_by(Company.name)
        ).all()
        # Companies of this batch first (decided after their contacts were checked), then
        # companies without any contact.
        batch = [
            companies[i] for i in dict.fromkeys(p["company_id"] for p in people) if i in companies
        ]
        rest = [c for c in open_companies if c.id not in with_contacts]
        for company in [*batch, *rest][: job.payload.get("roles_limit", 20)]:
            if company.id in profiled or company.role_search_at:
                continue
            roles.append({"id": company.id, "name": company.name, "location": company.location})
    known = set(
        db.scalars(
            select(Contact.linkedin_url).where(
                Contact.workspace_id == ws, Contact.linkedin_url.is_not(None)
            )
        )
    )
    return {"people": people, "companies": roles, "known_urls": sorted(known)}


def run(context: dict, search: Search | None = None) -> dict:
    if search is None:
        key = credentials.get("BRAVE_SEARCH_API_KEY")
        if not key:
            raise HTTPException(
                503, "Brave Search ist nicht verbunden (Einstellungen → Verbindungen)."
            )
        search = brave_search(key)
    people = {p["id"]: check_person(p, search) for p in context["people"]}
    verified_companies = {
        p["company_id"] for p in context["people"] if people[p["id"]]["status"] == "verified"
    }
    known = set(context["known_urls"]) | {r["url"] for r in people.values() if r["url"]}
    roles = {}
    for company in context["companies"]:
        if company["id"] in verified_companies:
            continue
        hits = role_search(company, search, known)
        known |= {h["url"] for h in hits}
        roles[company["id"]] = hits
    return {"people": people, "roles": roles}


def finalize(db, job, result: dict) -> dict:
    ws = job.workspace_id
    counts = {"verified": 0, "unsure": 0, "not_found": 0, "role_contacts": 0}
    for contact_id, verdict in result["people"].items():
        contact = db.scalar(
            select(Contact).where(Contact.workspace_id == ws, Contact.id == contact_id)
        )
        if not contact or contact.linkedin_status == "confirmed":
            continue
        status, url, reason = verdict["status"], verdict.get("url"), verdict["reason"]
        if url:
            owner = db.scalar(
                select(Contact).where(
                    Contact.workspace_id == ws,
                    Contact.linkedin_url == url,
                    Contact.id != contact.id,
                )
            )
            if owner:
                status, url = "unsure", None
                reason = "Profil gehört schon zu einem anderen Kontakt"
        previous = contact.linkedin_status
        contact.linkedin_status = status
        contact.linkedin_reason = reason[:300]
        contact.linkedin_checked_at = now()
        if status == "verified":
            contact.linkedin_url = url
        elif previous == "verified":
            # An earlier automatic match no longer holds; never keep an unsure URL.
            contact.linkedin_url = None
        counts[status] = counts.get(status, 0) + 1
    for company_id, hits in result["roles"].items():
        company = db.scalar(
            select(Company).where(Company.workspace_id == ws, Company.id == company_id)
        )
        if not company:
            continue
        company.role_search_at = now()
        for hit in hits:
            if db.scalar(
                select(Contact.id).where(
                    Contact.workspace_id == ws, Contact.linkedin_url == hit["url"]
                )
            ):
                continue
            key = hashlib.sha256(f"{company.id}:{hit['url']}".encode()).hexdigest()
            db.add(
                Contact(
                    workspace_id=ws,
                    company_id=company.id,
                    first_name=hit["first_name"][:120],
                    last_name=hit["last_name"][:120],
                    job_title=f"{hit['role']} (laut Suchtreffer)"[:240],
                    location=company.location or "",
                    linkedin_url=hit["url"],
                    linkedin_status="verified",
                    linkedin_reason=hit["reason"][:300],
                    linkedin_checked_at=now(),
                    import_key=key,
                    source="LinkedIn-Suche (Brave)",
                )
            )
            counts["role_contacts"] += 1
    db.flush()
    return counts


# ---- overview: data quality, email campaign --------------------------------------------

GENERIC = {
    "info",
    "kontakt",
    "contact",
    "office",
    "mail",
    "post",
    "hallo",
    "hello",
    "service",
    "team",
    "buero",
    "buro",
    "empfang",
    "praxis",
    "verwaltung",
    "anfrage",
    "anfragen",
    "zentrale",
    "sekretariat",
    "rezeption",
    "kanzlei",
    "termin",
    "termine",
    "vertrieb",
    "sales",
    "support",
    "hilfe",
    "webmaster",
    "admin",
    "bewerbung",
    "jobs",
    "karriere",
    "buchhaltung",
    "rechnung",
    "noreply",
    "no-reply",
    "datenschutz",
    "presse",
    "marketing",
}


def email_kind(address: str, names: list[str]) -> str:
    """persönlich (vorname@, v.nachname@ …) or allgemein (info@ …)."""
    local = fold(address.split("@", 1)[0])
    parts = [p for p in re.split(r"[._\-+]", local) if p]
    if not parts or local in GENERIC or parts[0] in GENERIC:
        return "allgemein"
    tokens = {t for n in names for t in words(n) if len(t) > 1}
    if any(p in tokens or (len(p) > 2 and any(t.startswith(p) for t in tokens)) for p in parts):
        return "persönlich"
    if len(parts) >= 2 and all(p.isalpha() for p in parts):
        return "persönlich"
    return "allgemein"


def email_campaign(db, ws) -> dict:
    """Everyone without a verified LinkedIn profile but with an email address. Nothing is sent."""
    from app.journeys import CompanyFact

    companies = {c.id: c for c in db.scalars(select(Company).where(Company.workspace_id == ws))}
    contacts = db.scalars(select(Contact).where(Contact.workspace_id == ws)).all()
    by_company: dict[str, list[Contact]] = {}
    for c in contacts:
        by_company.setdefault(c.company_id or "", []).append(c)
    facts: dict[str, list] = {}
    for f in db.scalars(
        select(CompanyFact).where(
            CompanyFact.workspace_id == ws, CompanyFact.field.ilike("E-Mail%")
        )
    ):
        facts.setdefault(f.company_id, []).append(f)
    items = []
    for company_id, company in companies.items():
        people = by_company.get(company_id, [])
        if any(has_profile(p) for p in people):
            continue
        names = [f"{p.first_name} {p.last_name}" for p in people]
        seen = set()
        rows = []
        for p in people:
            if p.email and p.email.lower() not in seen:
                seen.add(p.email.lower())
                rows.append(
                    {
                        "email": p.email,
                        "contact": " ".join(filter(None, [p.first_name, p.last_name])),
                        "source": "Kontakt" if p.source == "user_entry" else p.source,
                        "source_url": None,
                    }
                )
        for f in facts.get(company_id, []):
            for address in re.findall(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+", f.value or ""):
                if address.lower() in seen:
                    continue
                seen.add(address.lower())
                rows.append(
                    {
                        "email": address,
                        "contact": "",
                        "source": "Impressum" if "Impressum" in f.field else f.field,
                        "source_url": f.source_url,
                    }
                )
        for row in rows:
            items.append(
                row
                | {
                    "company_id": company_id,
                    "company": company.name,
                    "location": company.location,
                    "kind": email_kind(row["email"], names),
                    "linkedin": "kein geprüftes Profil",
                }
            )
    items.sort(key=lambda r: (r["kind"] != "persönlich", r["company"].casefold()))
    return {
        "items": items,
        "total": len(items),
        "personal": sum(r["kind"] == "persönlich" for r in items),
        "general": sum(r["kind"] == "allgemein" for r in items),
        "sending": "gesperrt",
        "notice": "Hier wird nichts versendet. Der Versand bleibt gesperrt, bis du ihn ausdrücklich freigibst.",
    }


def quality(db, ws, sample: int = 20, seed: str | None = None) -> dict:
    import random

    companies = db.scalars(select(Company).where(Company.workspace_id == ws)).all()
    contacts = db.scalars(select(Contact).where(Contact.workspace_id == ws)).all()
    campaign = email_campaign(db, ws)
    with_mail = {r["company_id"] for r in campaign["items"]}
    by_company: dict[str, list[Contact]] = {}
    for c in contacts:
        by_company.setdefault(c.company_id or "", []).append(c)
    rows = []
    for company in companies:
        people = by_company.get(company.id, [])
        profile = next((p for p in people if has_profile(p)), None)
        if profile:
            level = "linkedin"
        elif company.id in with_mail:
            level = "email"
        else:
            level = "nothing"
        rows.append((company, people, profile, level))
    counts = {
        "companies": len(companies),
        "with_contact": sum(1 for _, people, _, _ in rows if people),
        "with_linkedin": sum(1 for *_, level in rows if level == "linkedin"),
        "only_email": sum(1 for *_, level in rows if level == "email"),
        "nothing": sum(1 for *_, level in rows if level == "nothing"),
        "contacts": len(contacts),
        "contacts_unchecked": sum(c.linkedin_status == "unchecked" for c in contacts),
        "contacts_unsure": sum(c.linkedin_status == "unsure" for c in contacts),
        "contacts_not_found": sum(c.linkedin_status == "not_found" for c in contacts),
    }
    rng = random.Random(seed)
    picked = rng.sample(rows, min(sample, len(rows)))
    mails: dict[str, list[dict]] = {}
    for r in campaign["items"]:
        mails.setdefault(r["company_id"], []).append(r)
    return {
        "counts": counts,
        "sample": [
            {
                "company_id": company.id,
                "company": company.name,
                "location": company.location,
                "website": company.website,
                "contacts": [
                    {
                        "id": p.id,
                        "name": " ".join(filter(None, [p.first_name, p.last_name])),
                        "job_title": p.job_title,
                        "linkedin_status": p.linkedin_status,
                        "linkedin_url": p.linkedin_url,
                        "linkedin_reason": p.linkedin_reason,
                    }
                    for p in people[:4]
                ],
                "emails": [
                    {"email": m["email"], "kind": m["kind"]} for m in mails.get(company.id, [])
                ][:3],
                "level": level,
            }
            for company, people, profile, level in sorted(
                picked, key=lambda r: r[0].name.casefold()
            )
        ],
    }


# ---- routes ----------------------------------------------------------------------------


class CheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_ids: list[str] = Field(default_factory=list, max_length=200)
    limit: int = Field(default=50, ge=1, le=200)
    roles: bool = True
    roles_limit: int = Field(default=20, ge=0, le=100)


def has_profile(contact: Contact) -> bool:
    """Usable in "Heute": a verified or user-confirmed profile, or one the user imported."""
    return bool(contact.linkedin_url) and contact.linkedin_status in (
        "verified",
        "confirmed",
        "unchecked",
    )


def register_profile_routes(app, db_session, scope, audit):
    from app.jobs import enqueue
    from app.platform_routes import job_output

    @app.post("/v1/workspaces/{ws}/linkedin-check", status_code=202)
    def start_check(
        ws: str, body: CheckInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Keine Berechtigung.")
        if not credentials.get("BRAVE_SEARCH_API_KEY"):
            raise HTTPException(
                503, "Brave Search ist nicht verbunden (Einstellungen → Verbindungen)."
            )
        job = enqueue(db, ws, member.user_id, "profile_check", body.model_dump())
        audit(
            db,
            ws,
            member.user_id,
            "linkedin_check_requested",
            "LinkedIn-Profile über die Brave Search API prüfen (kein Aufruf von LinkedIn)",
        )
        return job_output(job)

    @app.get("/v1/workspaces/{ws}/data-quality")
    def data_quality(
        ws: str,
        sample: int = 20,
        seed: str | None = None,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        return quality(db, ws, max(1, min(sample, 50)), seed)

    @app.get("/v1/workspaces/{ws}/email-campaign")
    def campaign(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return email_campaign(db, ws)
