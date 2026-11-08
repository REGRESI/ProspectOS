"""M9d/M9e: companies without a contact person, and honest ways to close the gap.

- ``gap``: counts companies without a named contact, split by legal form. Forms that must
  be in a public register (GmbH, UG, AG, KG, OHG, e.K., GmbH & Co. KG) usually have a
  registered managing person; a licensed register source (North Data) can name them. Forms
  that are usually unregistered (Praxis, Kanzlei, GbR, Einzelunternehmen) cannot be closed
  by any register.
- ``estimate``: extra named contacts North Data would add. Measured from this workspace's own
  North Data imports when there are any; otherwise an upper bound of one person per
  registered company, labelled as an assumption.
- Role fallback: a role contact ("Geschäftsführung", "Praxisleitung", "Kita-Leitung") so the
  letter channel can write "An die Geschäftsführung", plus a visit task "nach der
  zuständigen Person fragen". Never an invented person.
- Names from company names ("Praxis Dr. med. Anna Muster"): rules only; a name is kept only
  when every part appears verbatim in the company name. Source "Firmenname" with a
  confidence. An optional model check for unclear cases is validated the same way.
- Professional registers: pre-filled search links only (no automated queries), see
  docs/CONNECTORS.md.

No scrapers for Gelbe Seiten, Das Örtliche, Google Maps or North Data.

CLI: ``python -m app.register_gap [--workspace <id>]``
"""

import re
import sys
from collections import Counter

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.db import now
from app.models import Company, Contact

ROLE_SOURCE = "role_fallback"
NAME_SOURCE = "company_name"
NAME_FACT = "Person aus Firmenname"

REGISTERED = (
    ("GmbH & Co. KG", r"\bgmbh\s*(?:&|und|\+)\s*co\.?\s*kg\b"),
    ("UG", r"\bug\b"),
    ("GmbH", r"\bg?gmbh\b"),
    ("AG", r"\bag\b"),
    ("OHG", r"\bohg\b"),
    ("KG", r"\bkg\b"),
    ("e.K.", r"\be\.\s?(?:k|kfm|kfr|kffr)\.?(?=[\s,)]|$)"),
)
UNREGISTERED = (
    ("GbR", r"\bgbr\b"),
    (
        "Praxis",
        r"praxis|\bdr\.?\s*med\b|zahnarzt|zahnärzt|\barzt\b|ärztin|physiotherap|ergotherap"
        r"|logopäd|heilpraktik|tierarzt|tierärzt|psychotherap",
    ),
    ("Kanzlei", r"kanzlei|rechtsanw|steuerberat|notar\b|notariat|anwält|anwalt"),
    ("Einzelunternehmen", r"\binh\.|\binhaber|einzelunternehm"),
)
REGISTERED_FORMS = [label for label, _ in REGISTERED]
UNREGISTERED_FORMS = [label for label, _ in UNREGISTERED]


def legal_form(name: str) -> tuple[str, str]:
    """('registered'|'unregistered'|'unknown', form). Registered forms win: a
    'Kanzlei Muster GmbH' is in the register."""
    text = (name or "").casefold()
    for label, pattern in REGISTERED:
        if re.search(pattern, text):
            return "registered", label
    for label, pattern in UNREGISTERED:
        if re.search(pattern, text):
            return "unregistered", label
    return "unknown", ""


def role_for(company: Company) -> str:
    text = f"{company.name} {company.industry}".casefold()
    if re.search(r"\bkita\b|kindergarten|kindertages|krippe|hort\b", text):
        return "Kita-Leitung"
    if legal_form(company.name)[1] == "Praxis" or "praxis" in text:
        return "Praxisleitung"
    return "Geschäftsführung"


def _named_contacts():
    return select(Contact.company_id).where(
        Contact.company_id.is_not(None), Contact.source != ROLE_SOURCE
    )


def companies_without_contact(db, ws, limit=20000) -> list[Company]:
    return db.scalars(
        select(Company)
        .where(Company.workspace_id == ws, Company.id.not_in(_named_contacts()))
        .order_by(Company.name)
        .limit(limit)
    ).all()


def gap(db, ws) -> dict:
    companies = db.scalar(select(func.count(Company.id)).where(Company.workspace_id == ws)) or 0
    missing = companies_without_contact(db, ws)
    classes, forms = Counter(), Counter()
    for company in missing:
        kind, form = legal_form(company.name)
        classes[kind] += 1
        forms[form or "unbekannt"] += 1
    role_contacts = (
        db.scalar(
            select(func.count(Contact.id)).where(
                Contact.workspace_id == ws, Contact.source == ROLE_SOURCE
            )
        )
        or 0
    )
    return {
        "companies": companies,
        "without_contact": len(missing),
        "registered": classes["registered"],
        "unregistered": classes["unregistered"],
        "unknown": classes["unknown"],
        "by_form": dict(forms.most_common()),
        "registered_forms": REGISTERED_FORMS,
        "unregistered_forms": UNREGISTERED_FORMS,
        "role_contacts": role_contacts,
        "estimate": estimate(db, ws, classes["registered"]),
    }


def estimate(db, ws, registered_missing: int) -> dict:
    """Extra named contacts a licensed register source would add."""
    imported = db.scalar(
        select(func.count(Company.id)).where(
            Company.workspace_id == ws, Company.identity.like("northdata:%")
        )
    )
    if imported:
        people = db.scalar(
            select(func.count(Contact.id))
            .join(Company, Company.id == Contact.company_id)
            .where(
                Contact.workspace_id == ws,
                Company.identity.like("northdata:%"),
                Contact.source != ROLE_SOURCE,
            )
        )
        rate = people / imported
        return {
            "extra_contacts": round(registered_missing * rate),
            "per_company": round(rate, 2),
            "basis": f"gemessen an {imported} North-Data-Firmen in diesem Workspace",
            "measured": True,
        }
    return {
        "extra_contacts": registered_missing,
        "per_company": 1.0,
        "basis": "Annahme: höchstens eine eingetragene vertretungsberechtigte Person je "
        "registrierter Firma (noch keine North-Data-Daten zum Messen)",
        "measured": False,
    }


# ---- role fallback ----------------------------------------------------------------------


def ensure_role_contact(db, ws, company: Company, actor_id=None, visit_task=True) -> Contact:
    from app.flows import FlowTask
    from app.multichannel import apply_route, sync_points

    existing = db.scalar(
        select(Contact).where(
            Contact.workspace_id == ws,
            Contact.company_id == company.id,
            Contact.source == ROLE_SOURCE,
        )
    )
    if existing:
        return existing
    role = role_for(company)
    contact = Contact(
        workspace_id=ws,
        company_id=company.id,
        first_name="",
        last_name=role,
        job_title=role,
        location=company.location or "",
        source=ROLE_SOURCE,
        # A role is not a person: never search a LinkedIn profile for it.
        linkedin_status="not_found",
        linkedin_reason="Rollen-Adresse, keine Person",
    )
    db.add(contact)
    db.flush()
    apply_route(db, ws, contact, sync_points(db, ws, contact))
    if visit_task:
        db.add(
            FlowTask(
                workspace_id=ws,
                contact_id=contact.id,
                kind="visit_task",
                title="Vor Ort nach der zuständigen Person fragen",
                body=f"{company.name}: Wer entscheidet über die Reinigung? Name und Funktion "
                "notieren und als Kontakt eintragen. Keine Daten raten.",
                due_at=now(),
                state="open",
                origin="role_fallback",
            )
        )
    return contact


def recipient_role_line(contact: Contact) -> str | None:
    if contact.source == ROLE_SOURCE and not contact.first_name:
        return f"An die {contact.last_name or 'Geschäftsführung'}"
    return None


# ---- names from company names -----------------------------------------------------------

TITLES = r"(?:(?:Dr\.|Prof\.|Dipl\.-[A-ZÄÖÜa-zäöü]+\.?)\s*(?:med\.|dent\.|vet\.|rer\.\s*nat\.)?\s*)"
PROFESSIONS = (
    r"Praxis|Zahnarztpraxis|Arztpraxis|Hausarztpraxis|Kanzlei|Rechtsanwaltskanzlei|"
    r"Steuerkanzlei|Steuerberater(?:in)?|Rechtsanwalt|Rechtsanwältin|Notar(?:in)?|"
    r"Physiotherapie|Ergotherapie|Logopädie|Zahnarzt|Zahnärztin|Tierarztpraxis|"
    r"Architekt(?:in)?|Architekturbüro|Ingenieurbüro|Heilpraktiker(?:in)?|Malermeister|"
    r"Inh\.|Inhaber(?:in)?"
)
NAME = r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?"
NOT_NAMES = {
    "Praxis",
    "Kanzlei",
    "Partner",
    "Partnerschaft",
    "Zentrum",
    "Gemeinschaftspraxis",
    "Steuerberatung",
    "Rechtsanwälte",
    "Medizin",
    "Zahnmedizin",
    "Physiotherapie",
    "Allgemeinmedizin",
    "Innere",
    "Familie",
    "Gesundheit",
    "Service",
    "Gebäudereinigung",
    "Bau",
    "Holz",
}
RULES = (
    # "Praxis Dr. med. Anna Muster", "Steuerberaterin Anna Muster", "Inh. Anna Muster"
    (re.compile(rf"(?:{PROFESSIONS})\s+{TITLES}?(?P<first>{NAME})\s+(?P<last>{NAME})\b"), "hoch"),
    # "Dr. med. Anna Muster Zahnarztpraxis"
    (re.compile(rf"^{TITLES}(?P<first>{NAME})\s+(?P<last>{NAME})\b"), "hoch"),
    # "Anna Muster Steuerberatung" (name first, business word after)
    (
        re.compile(
            rf"^(?P<first>{NAME})\s+(?P<last>{NAME})\s+(?:Steuerberatung|Rechtsanwältin|"
            rf"Rechtsanwalt|Physiotherapie|Ergotherapie|Logopädie|Architektur|Malerbetrieb|"
            rf"Elektro|Sanitär|Friseur)"
        ),
        "mittel",
    ),
)


def name_from_company(company_name: str) -> dict | None:
    """Rule-based. Returns {first_name, last_name, title, confidence} or None (unclear)."""
    text = re.sub(r"\s+", " ", company_name or "").strip()
    for pattern, confidence in RULES:
        m = pattern.search(text)
        if not m:
            continue
        first, last = m.group("first"), m.group("last")
        if first in NOT_NAMES or last in NOT_NAMES:
            continue
        title = re.search(rf"{TITLES}(?={re.escape(first)})", text)
        return {
            "first_name": first,
            "last_name": last,
            "title": (title.group(0).strip() if title else ""),
            "confidence": confidence,
        }
    return None


def checked_model_name(company_name: str, answer: str) -> dict | None:
    """Validate a model's answer for an unclear case: both parts must appear verbatim in the
    company name, otherwise it is discarded. A model can never add a name."""
    parts = (answer or "").strip().split()
    if len(parts) != 2 or answer.strip().casefold() in ("keiner", "keine", "none"):
        return None
    words = re.findall(r"[\wäöüÄÖÜß-]+", company_name or "")
    if all(p in words for p in parts) and not any(p in NOT_NAMES for p in parts):
        return {"first_name": parts[0], "last_name": parts[1], "title": "", "confidence": "KI"}
    return None


def apply_company_names(db, ws, actor_id=None, limit=500) -> dict:
    """Create contacts from company names with high confidence; store medium ones as a fact
    to confirm. Only companies without a named contact."""
    from app.journeys import CompanyFact
    from app.multichannel import apply_route, sync_points

    created, suggested, unclear = [], [], 0
    for company in companies_without_contact(db, ws, limit):
        found = name_from_company(company.name)
        if found is None:
            unclear += 1
            continue
        full = " ".join(filter(None, [found["title"], found["first_name"], found["last_name"]]))
        fact = db.scalar(
            select(CompanyFact).where(
                CompanyFact.workspace_id == ws,
                CompanyFact.company_id == company.id,
                CompanyFact.field == NAME_FACT,
            )
        )
        if fact is None:
            db.add(
                CompanyFact(
                    workspace_id=ws,
                    company_id=company.id,
                    field=NAME_FACT,
                    value=full,
                    source_url="",
                    confidence=f"regel_{found['confidence']}",
                    source_kind="company_name",
                    actor_id=actor_id,
                )
            )
        if found["confidence"] != "hoch":
            suggested.append({"company": company.name, "name": full})
            continue
        contact = Contact(
            workspace_id=ws,
            company_id=company.id,
            first_name=found["first_name"],
            last_name=found["last_name"],
            location=company.location or "",
            source=NAME_SOURCE,
        )
        db.add(contact)
        db.flush()
        apply_route(db, ws, contact, sync_points(db, ws, contact))
        created.append({"company": company.name, "name": full, "contact_id": contact.id})
    db.flush()
    return {"created": created, "suggested": suggested, "unclear": unclear}


# ---- professional registers (links only) -------------------------------------------------

REGISTERS = (
    {
        "id": "arztsuche_bw",
        "label": "Arztsuche der KV Baden-Württemberg",
        "url": "https://www.arztsuche-bw.de/",
        "fits": "Praxis",
    },
    {
        "id": "anwaltsverzeichnis",
        "label": "Bundesweites Amtliches Anwaltsverzeichnis (BRAK)",
        "url": "https://www.bea-brak.de/bravsearch/index.brak",
        "fits": "Kanzlei",
    },
    {
        "id": "steuerberater",
        "label": "Steuerberaterverzeichnis (Bundessteuerberaterkammer)",
        "url": "https://www.bstbk.de/de/steuerberatersuche",
        "fits": "Kanzlei",
    },
    {
        "id": "handwerk",
        "label": "Betriebssuche der Handwerkskammer",
        "url": "https://www.hwk-freiburg.de/betriebssuche",
        "fits": "Handwerk",
    },
)


def register_links(company: Company) -> list[dict]:
    """Start pages of public professional registers plus the search term to paste. No
    automated queries: their terms of use were not confirmed (docs/CONNECTORS.md)."""
    form = legal_form(company.name)[1]
    term = re.sub(r"\s+", " ", f"{company.name} {company.location or ''}").strip()
    return [
        {
            **r,
            "search_term": term,
            "verified": False,
            "suggested": r["fits"] == form,
        }
        for r in REGISTERS
    ]


# ---- routes -----------------------------------------------------------------------------


class RoleContactsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_ids: list[str] = Field(default_factory=list, max_length=500)
    all_without_contact: bool = False
    unregistered_only: bool = False
    visit_task: bool = True


class FindWebsitesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_ids: list[str] = Field(default_factory=list, max_length=25)


def register_gap_routes(app, db_session, scope, record, audit):
    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")

    @app.get("/v1/workspaces/{ws}/sources/register-gap")
    def register_gap(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return gap(db, ws) | {
            "notice": "Ohne Ansprechpartner geht ein Brief „An die Geschäftsführung“ "
            "(oder Praxis- bzw. Kita-Leitung). Registerdaten nur über lizenzierte Schnittstellen.",
        }

    @app.post("/v1/workspaces/{ws}/companies/role-contacts", status_code=201)
    def role_contacts(
        ws: str,
        body: RoleContactsInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        if body.company_ids:
            companies = [record(db, Company, ws, cid) for cid in body.company_ids]
        elif body.all_without_contact:
            companies = companies_without_contact(db, ws, 500)
            if body.unregistered_only:
                companies = [c for c in companies if legal_form(c.name)[0] != "registered"]
        else:
            raise HTTPException(422, "Firmen auswählen oder „alle ohne Ansprechpartner“.")
        made = [ensure_role_contact(db, ws, c, member.user_id, body.visit_task) for c in companies]
        audit(
            db,
            ws,
            member.user_id,
            "role_contacts_created",
            f"{len(made)} Rollen-Adressen angelegt (keine Personen)",
        )
        return {
            "created": len(made),
            "items": [
                {"contact_id": c.id, "company_id": c.company_id, "role": c.last_name} for c in made
            ],
        }

    @app.post("/v1/workspaces/{ws}/companies/names-from-company-names")
    def names_from_company_names(
        ws: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        result = apply_company_names(db, ws, member.user_id)
        audit(
            db,
            ws,
            member.user_id,
            "names_from_company_names",
            f"{len(result['created'])} Kontakte aus Firmennamen (Regeln), "
            f"{len(result['suggested'])} zur Prüfung",
        )
        return result

    @app.post("/v1/workspaces/{ws}/companies/find-websites", status_code=202)
    def find_websites(
        ws: str,
        body: FindWebsitesInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app import credentials
        from app.jobs import enqueue
        from app.platform_models import Job
        from app.providers import site_research

        authoring(member)
        if not credentials.get("BRAVE_SEARCH_API_KEY"):
            raise HTTPException(
                409, "Für die Website-Suche fehlt der Brave-Schlüssel (Verbindungen)."
            )
        if not site_research.enabled():
            raise HTTPException(409, "Website-Recherche ist in dieser Installation ausgeschaltet.")
        running = db.scalar(
            select(Job.id).where(
                Job.workspace_id == ws,
                Job.kind == "website_find",
                Job.status.in_(["queued", "running", "retry"]),
            )
        )
        if running:
            raise HTTPException(409, "Eine Website-Suche läuft bereits.")
        ids = [record(db, Company, ws, cid).id for cid in body.company_ids]
        job = enqueue(db, ws, member.user_id, "website_find", {"company_ids": ids})
        audit(db, ws, member.user_id, "website_find_queued", "Fehlende Websites suchen (Brave)")
        return {"job_id": job.id, "max_companies": 25}

    @app.get("/v1/workspaces/{ws}/website-finder")
    def website_finder_report(
        ws: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        from app.platform_models import Job

        job = db.scalar(
            select(Job)
            .where(Job.workspace_id == ws, Job.kind == "website_find")
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        missing = db.scalar(
            select(func.count(Company.id)).where(
                Company.workspace_id == ws, (Company.website.is_(None)) | (Company.website == "")
            )
        )
        return {
            "missing_websites": missing,
            "last": {
                "status": job.status,
                "created_at": job.created_at,
                "error": job.last_error,
                "result": job.result if job.status == "succeeded" else None,
            }
            if job
            else None,
        }

    @app.get("/v1/workspaces/{ws}/companies/{entity_id}/register-links")
    def links(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        company = record(db, Company, ws, entity_id)
        return {"items": register_links(company)}


def main(argv=None) -> int:
    from app.db import SessionLocal
    from app.models import Workspace

    argv = list(sys.argv[1:] if argv is None else argv)
    only = argv[argv.index("--workspace") + 1] if "--workspace" in argv else None
    with SessionLocal() as db, db.begin():
        ids = [only] if only else db.scalars(select(Workspace.id).order_by(Workspace.name)).all()
        from sqlalchemy import text

        for ws in ids:
            db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})
            g = gap(db, ws)
            est = g["estimate"]
            print(
                f"Workspace {ws}: {g['companies']} Firmen, {g['without_contact']} ohne Ansprechpartner"
            )
            print(f"  registerpflichtige Rechtsform: {g['registered']}")
            print(f"  vermutlich ohne Registereintrag: {g['unregistered']}")
            print(f"  Rechtsform unbekannt: {g['unknown']}")
            for form, n in g["by_form"].items():
                print(f"    {form}: {n}")
            print(
                f"  North Data würde etwa {est['extra_contacts']} Ansprechpartner ergänzen "
                f"({est['basis']})."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
