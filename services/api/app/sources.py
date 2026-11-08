"""V3 M8: lead sources as building blocks with one interface and a quality report.

Every source describes itself the same way: what it delivers (companies, contacts,
enrichment), licence and terms note, whether it is ready in this workspace (and why not),
where to start it in the app, and how to recognise its records. Execution stays in the
existing adapters (discovery jobs, CSV import, Impressum research, Brave profile check).

Quality report per source, computed from stored data only:
- hits: companies (or contacts) that came from the source,
- contact rate: share of those companies with at least one contact person,
- verified LinkedIn rate: share of their contacts with a verified/confirmed profile,
- errors: failed jobs of the source in the last 30 days, grouped by error code.

Nothing here scrapes LinkedIn or Google Maps. Register data only through a licensed
provider; ``REGISTER_OPTIONS`` lists researched options, none is activated.
"""

import os
from dataclasses import dataclass, field
from datetime import timedelta

from fastapi import Depends
from sqlalchemy import func, or_, select

from app import credentials
from app.db import now
from app.models import Company, Contact
from app.platform_models import Job

REGISTER_OPTIONS = [
    {
        "name": "North Data (bereits angebunden)",
        "status": "Adapter vorhanden, braucht API-Schlüssel",
        "note": "Kostenpflichtige Data API mit Handelsregister-, Bundesanzeiger- und Insolvenzdaten; "
        "AGB unter northdata.de/_agb vor Nutzung prüfen.",
    },
    {
        "name": "OpenRegister",
        "status": "nicht angebunden",
        "note": "Handelsregister-API mit Abruf aus der Quelle; Preise, Lizenz und Weiterverwendung "
        "laut Anbieter prüfen (docs.openregister.de).",
    },
    {
        "name": "handelsregister.ai",
        "status": "nicht angebunden",
        "note": "API für deutsche Registerdaten; Bedingungen und Datenschutzvertrag vor Nutzung prüfen.",
    },
    {
        "name": "handelsregister.de direkt",
        "status": "nicht vorgesehen",
        "note": "Kein automatisierter Massenabruf: Die Nutzungsbedingungen des Registerportals "
        "schränken das ein. Nur über einen lizenzierten Anbieter.",
    },
]


@dataclass
class LeadSource:
    id: str
    label: str
    delivers: str
    license: str
    start_path: str
    company_sources: tuple = ()
    contact_source_prefixes: tuple = ()
    job_providers: tuple = ()
    job_kinds: tuple = ()
    ready: object = None
    notes: list = field(default_factory=list)


def _osm_ready():
    contact = credentials.get("OSM_CONTACT", "").strip()
    extract = os.getenv("OSM_EXTRACT_PATH", "").strip()
    if extract:
        return True, "Lokaler OSM-Extrakt"
    if os.getenv("OSM_DISCOVERY_ENABLED", "false").lower() == "true" and contact:
        return True, "Öffentliche OSM-Schnittstelle"
    return (
        False,
        "OSM_DISCOVERY_ENABLED und OSM_CONTACT setzen oder einen lokalen Extrakt einbinden.",
    )


SOURCES = [
    LeadSource(
        id="osm",
        label="OpenStreetMap",
        delivers="Firmen mit Adresse, Branche, oft Website",
        license="ODbL 1.0, Namensnennung",
        start_path="/discover",
        company_sources=("openstreetmap", "osm", "osm_extract"),
        job_providers=("osm",),
        ready=_osm_ready,
    ),
    LeadSource(
        id="northdata",
        label="North Data (Registerdaten)",
        delivers="Firmen aus Handelsregister und Bundesanzeiger, Geschäftsführung",
        license="Lizenziert, kostenpflichtig",
        start_path="/discover",
        company_sources=("northdata",),
        job_providers=("northdata",),
        ready=lambda: (bool(credentials.get("NORTHDATA_API_KEY")), "NORTHDATA_API_KEY fehlt."),
    ),
    LeadSource(
        id="pdl",
        label="People Data Labs",
        delivers="Firmen aus einer lizenzierten Datenbank",
        license="Vertragsabhängig",
        start_path="/discover",
        company_sources=("people_data_labs",),
        job_providers=("pdl",),
        ready=lambda: (
            bool(os.getenv("PDL_API_KEY")) and os.getenv("PDL_LICENSE_APPROVED") == "true",
            "Lizenz und API-Schlüssel fehlen.",
        ),
    ),
    LeadSource(
        id="impressum",
        label="Impressum der Firmenwebsite",
        delivers="Geschäftsführung, Adresse, Telefon, allgemeine E-Mail",
        license="Öffentliche Pflichtangaben (§5 DDG); nur für die Ansprache der Firma",
        start_path="/leads/top",
        contact_source_prefixes=("impressum",),
        job_kinds=("research",),
        ready=lambda: (
            os.getenv("RESEARCH_ENABLED", "false").lower() == "true",
            "RESEARCH_ENABLED ist aus.",
        ),
    ),
    LeadSource(
        id="csv",
        label="CSV-Import mit Spaltenzuordnung",
        delivers="Kontakte und Firmen aus eigenen Listen",
        license="Eigene Daten; Herkunft beim Import bestätigen",
        start_path="/imports",
        contact_source_prefixes=("csv_upload",),
        job_kinds=("import",),
        ready=lambda: (True, ""),
    ),
    LeadSource(
        id="brave",
        label="Brave-Suche (LinkedIn-Profile prüfen)",
        delivers="Geprüfte LinkedIn-Profil-URLs zu vorhandenen Kontakten",
        license="Brave Search API; Treffer werden nicht gespeichert, nur die bestätigte URL",
        start_path="/contacts/quality",
        contact_source_prefixes=("LinkedIn-Suche (Brave)",),
        ready=lambda: (
            bool(credentials.get("BRAVE_SEARCH_API_KEY")),
            "BRAVE_SEARCH_API_KEY fehlt.",
        ),
    ),
    LeadSource(
        id="manual",
        label="Von Hand angelegt",
        delivers="Firmen und Kontakte, die du selbst einträgst",
        license="Eigene Daten",
        start_path="/contacts",
        company_sources=("user_entry",),
        contact_source_prefixes=("user_entry",),
        ready=lambda: (True, ""),
    ),
]


def _rate(part, whole):
    return round(part / whole, 2) if whole else None


def quality(db, ws, source: LeadSource) -> dict:
    verified = ("verified", "confirmed")
    company_filter = Company.source.in_(source.company_sources) if source.company_sources else None
    contact_filter = (
        or_(*[Contact.source.like(prefix + "%") for prefix in source.contact_source_prefixes])
        if source.contact_source_prefixes
        else None
    )
    if company_filter is not None:
        companies = db.scalar(
            select(func.count(Company.id)).where(Company.workspace_id == ws, company_filter)
        )
        with_contact = db.scalar(
            select(func.count(func.distinct(Contact.company_id)))
            .join(Company, Company.id == Contact.company_id)
            .where(Contact.workspace_id == ws, company_filter)
        )
        contacts_q = (
            select(Contact)
            .join(Company, Company.id == Contact.company_id)
            .where(Contact.workspace_id == ws, company_filter)
        )
    else:
        companies = with_contact = None
        contacts_q = select(Contact).where(Contact.workspace_id == ws, contact_filter)
    contacts = db.scalar(select(func.count()).select_from(contacts_q.subquery()))
    verified_count = db.scalar(
        select(func.count()).select_from(
            contacts_q.where(Contact.linkedin_status.in_(verified)).subquery()
        )
    )
    if source.id == "brave":
        checked = db.scalar(
            select(func.count(Contact.id)).where(
                Contact.workspace_id == ws, Contact.linkedin_status != "unchecked"
            )
        )
        contacts, verified_count = (
            checked,
            db.scalar(
                select(func.count(Contact.id)).where(
                    Contact.workspace_id == ws, Contact.linkedin_status.in_(verified)
                )
            ),
        )
    errors = {}
    if source.job_providers or source.job_kinds:
        stmt = select(Job.last_error, func.count()).where(
            Job.workspace_id == ws,
            Job.status.in_(["failed", "ambiguous"]),
            Job.created_at >= now() - timedelta(days=30),
        )
        if source.job_providers:
            stmt = stmt.where(
                Job.kind == "discovery",
                Job.payload["provider"].as_string().in_(source.job_providers),
            )
        else:
            stmt = stmt.where(Job.kind.in_(source.job_kinds))
        errors = {
            code or "unbekannt": count for code, count in db.execute(stmt.group_by(Job.last_error))
        }
    return {
        "hits": companies if companies is not None else contacts,
        "hits_unit": "Firmen" if companies is not None else "Kontakte",
        "companies_with_contact": with_contact,
        "contact_rate": _rate(with_contact, companies) if companies is not None else None,
        "contacts": contacts,
        "verified_linkedin": verified_count,
        "verified_linkedin_rate": _rate(verified_count, contacts),
        "errors": errors,
        "error_count": sum(errors.values()),
    }


def register_source_routes(app, db_session, scope):
    @app.get("/v1/workspaces/{ws}/sources")
    def sources(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        items = []
        for source in SOURCES:
            ready, reason = source.ready()
            items.append(
                {
                    "id": source.id,
                    "label": source.label,
                    "delivers": source.delivers,
                    "license": source.license,
                    "start_path": source.start_path,
                    "ready": ready,
                    "reason": None if ready else reason,
                    "quality": quality(db, ws, source),
                }
            )
        return {
            "items": items,
            "register_options": REGISTER_OPTIONS,
            "notice": "Kein Scraping von LinkedIn oder Google Maps. Registerdaten nur über lizenzierte Anbieter.",
        }
