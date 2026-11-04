"""M4: ICP templates and an explained "Top-Kandidaten" ranking for companies.

Priority = 0.8 × ICP fit (existing deterministic company_fit_score: region, industry,
size/needs when weighted; unknown = 0 points) + 0.2 × data completeness (cited facts
needed to approach the company). Every factor and every missing fact is returned.
No purchase probability is implied.
"""

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.journeys import CompanyFact, CompanyProfile, ICPProfile
from app.models import Company
from app.prospecting import company_fit_score

ORTENAU = [
    "Offenburg", "Lahr", "Kehl", "Achern", "Oberkirch", "Gengenbach", "Haslach", "Hausach",
    "Wolfach", "Ettenheim", "Zell am Harmersbach", "Oppenau", "Renchen", "Rheinau",
    "Willstätt", "Appenweier", "Durbach", "Ortenberg", "Schutterwald", "Neuried", "Hohberg",
    "Friesenheim", "Schwanau", "Meißenheim", "Kappel-Grafenhausen", "Rust", "Mahlberg",
    "Kippenheim", "Seelbach", "Biberach", "Nordrach", "Oberharmersbach", "Steinach",
    "Fischerbach", "Hornberg", "Gutach", "Schiltach", "Kappelrodeck", "Sasbach",
    "Sasbachwalden", "Lauf", "Ottenhöfen", "Seebach", "Lautenbach", "Bad Peterstal-Griesbach",
    "Berghaupten", "Hofstetten", "Mühlenbach", "Oberwolfach", "Ohlsbach", "Ringsheim",
    "Schuttertal", "Ortenaukreis", "Ortenau",
]  # fmt: skip

TEMPLATES = {
    "office_cleaning_ortenau": {
        "name": "Büro-Unterhaltsreinigung Ortenaukreis",
        "description": "Büros, Kanzleien, Steuerberater, Praxen, Agenturen, Autohäuser, Verwaltungen im Ortenaukreis",
        "profile": {
            "locations": ORTENAU,
            "roles": [
                "Geschäftsführer",
                "Inhaber",
                "Office Management",
                "Praxisinhaber",
                "Kanzleileitung",
            ],
            "industries": [
                "Büro / Dienstleistung",
                "Rechtsberatung",
                "Steuerberatung",
                "Gesundheit / Praxis",
                "Agentur / Marketing",
                "Kfz",
                "Öffentliche Verwaltung",
                "Immobilien",
                "Versicherung & Finanzen",
                "Architektur & Ingenieurwesen",
                "IT & Software",
            ],
            # Competitors are never prospects.
            "excluded_industries": ["Reinigung / Facility"],
            "min_employees": None,
            "max_employees": None,
            "needs": ["Regelmäßige Büroreinigung"],
            "required_fields": ["company", "location"],
            "optional_fields": ["phone", "email"],
            "weights": {"location": 50, "role": 0, "industry": 50, "size": 0, "needs": 0},
        },
    }
}

COMPLETENESS = [
    ("Geschäftsführung / Inhaber", ("Geschäftsführung / Inhaber", "Vertretung (Registerangabe)")),
    ("Telefon", ("Telefon (Impressum)",)),
    ("E-Mail allgemein", ("E-Mail allgemein (Impressum)",)),
    ("Adresse", ("Adresse (Impressum)", "Adresse")),
    ("Website", ("Website",)),
    ("KI-Profil", ("KI-Profil: Tätigkeit",)),
]


class TemplateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: str


def rank_company(company: Company, facts: list, profile: dict) -> dict:
    by_field: dict[str, list] = {}
    for fact in facts:
        by_field.setdefault(fact.field, []).append(fact)
    prov = company.provenance or {}
    location = company.location or ""
    address = prov.get("address") or (by_field.get("Adresse (Impressum)") or [None])[0]
    if not location and address is not None:
        location = address if isinstance(address, str) else address.value
    row = {
        "location": location,
        "industry": company.industry or "",
        "osm_category": prov.get("osm_category") or "",
        "website": company.website,
        "source_url": prov.get("source_url"),
        "employee_count": prov.get("employee_count"),
    }
    fit = company_fit_score(row, profile)
    have, missing = [], []
    for label, fields in COMPLETENESS:
        present = any(by_field.get(f) for f in fields) or (label == "Website" and company.website)
        (have if present else missing).append(label)
    completeness = round(100 * len(have) / len(COMPLETENESS))
    excluded = any(f["name"] == "Branchenausschluss" for f in fit["factors"])
    priority = 0 if excluded else round(0.8 * fit["value"] + 0.2 * completeness)
    reasons = [f["reason"] for f in fit["factors"] if f["points"] > 0]
    gaps = [f["reason"] for f in fit["factors"] if f["points"] == 0 and f["max_points"] > 0]
    summary = (
        (
            "Ausgeschlossen: "
            + "; ".join(f["reason"] for f in fit["factors"] if f["name"] == "Branchenausschluss")
        )
        if excluded
        else "; ".join(reasons) or "Keine ICP-Übereinstimmung belegt"
    )
    sources = sorted({f.source_url for f in facts if f.source_url})[:6]
    return {
        "company_id": company.id,
        "name": company.name,
        "location": location,
        "industry": company.industry,
        "website": company.website,
        "priority": priority,
        "fit": fit["value"],
        "completeness": completeness,
        "excluded": excluded,
        "reason": summary,
        "gaps": gaps,
        "factors": fit["factors"],
        "known": have,
        "missing_facts": missing
        + [m for m in fit["missing_data"] if m not in missing and m != "Website"],
        "sources": sources,
        "formula": "Priorität = 0,8 × ICP-Fit + 0,2 × Datenlage",
    }


def register_ranking_routes(app, db_session, scope, record, audit):
    @app.get("/v1/workspaces/{ws}/icp-templates")
    def icp_templates(ws: str, member=Depends(scope)):
        return {
            "items": [
                {"id": k, "name": v["name"], "description": v["description"]}
                for k, v in TEMPLATES.items()
            ]
        }

    @app.post("/v1/workspaces/{ws}/icp-profiles/from-template", status_code=201)
    def from_template(
        ws: str,
        body: TemplateInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Diese Rolle darf keine ICP-Profile anlegen.")
        template = TEMPLATES.get(body.template)
        if not template:
            raise HTTPException(404, "Unbekannte Vorlage.")
        from app.journeys import IntelligenceProfileInput

        data = IntelligenceProfileInput.model_validate(
            {"name": template["name"], **template["profile"]}
        )
        existing = db.scalar(
            select(ICPProfile).where(ICPProfile.workspace_id == ws, ICPProfile.name == data.name)
        )
        if existing:
            return {
                "id": existing.id,
                **existing.profile,
                "version": existing.version,
                "created_at": existing.created_at,
            }
        item = ICPProfile(workspace_id=ws, name=data.name, profile=data.model_dump())
        db.add(item)
        db.flush()
        audit(
            db, ws, member.user_id, "icp_profile_created", f"ICP-Profil aus Vorlage {body.template}"
        )
        return {
            "id": item.id,
            **item.profile,
            "version": item.version,
            "created_at": item.created_at,
        }

    @app.get("/v1/workspaces/{ws}/ranking/companies")
    def ranking(
        ws: str,
        profile_id: str | None = None,
        limit: int = 50,
        include_excluded: bool = False,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        limit = max(1, min(limit, 500))
        if profile_id:
            icp = record(db, ICPProfile, ws, profile_id)
        else:
            icp = db.scalar(
                select(ICPProfile)
                .where(ICPProfile.workspace_id == ws)
                .order_by(ICPProfile.created_at.desc())
            )
        if not icp:
            raise HTTPException(422, "Zuerst ein ICP-Profil anlegen (z. B. aus einer Vorlage).")
        customers = set(
            db.scalars(
                select(CompanyProfile.company_id).where(
                    CompanyProfile.workspace_id == ws, CompanyProfile.is_customer.is_(True)
                )
            )
        )
        companies = db.scalars(
            select(Company)
            .where(Company.workspace_id == ws)
            .order_by(Company.created_at)
            .limit(3000)
        ).all()
        facts: dict[str, list] = {}
        for fact in db.scalars(select(CompanyFact).where(CompanyFact.workspace_id == ws)):
            facts.setdefault(fact.company_id, []).append(fact)
        rows = [
            rank_company(c, facts.get(c.id, []), icp.profile)
            for c in companies
            if c.id not in customers
        ]
        if not include_excluded:
            rows = [r for r in rows if not r["excluded"]]
        rows.sort(key=lambda r: (-r["priority"], -r["fit"], r["name"].casefold()))
        return {
            "profile": {"id": icp.id, "name": icp.name, "version": icp.version},
            "total": len(rows),
            "items": [r | {"rank": i + 1} for i, r in enumerate(rows[:limit])],
            "notice": "Erklärte Priorisierung aus belegten Fakten; keine Kaufwahrscheinlichkeit. "
            "Bestandskunden sind ausgenommen.",
        }
