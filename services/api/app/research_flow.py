"""M3: website + Impressum research and cited AI company profiles.

- ``research`` jobs with ``mode=site`` run the domain-bound crawler outside the DB
  transaction; ``finalize_site_research`` stores every Impressum field as a cited
  CompanyFact (source_kind ``website_impressum``, confidence ``extracted``).
- ``company_profile`` jobs send the stored page texts as numbered sources to the LLM;
  only lines that cite valid source IDs are stored (source_kind ``ai_profile``).
"""

import hashlib
import re

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import data_quality
from app.db import now
from app.jobs import enqueue, reserve_ai
from app.journeys import CompanyFact
from app.models import Company
from app.platform_models import Job

IMPRESSUM_LABELS = {
    "company": "Firmenname (Impressum)",
    "legal_form": "Rechtsform",
    "managers": "Geschäftsführung / Inhaber",
    "address": "Adresse (Impressum)",
    "phone": "Telefon (Impressum)",
    "email": "E-Mail allgemein (Impressum)",
    "register_id": "Handelsregister",
    "register_court": "Registergericht",
    "vat_id": "USt-IdNr.",
}
PROFILE_LABELS = (
    "Tätigkeit",
    "Standorte",
    "Hinweise Bürofläche",
    "Hinweise Mitarbeitende",
    "Anknüpfungspunkte",
)


class BatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_ids: list[str] = Field(default_factory=list, max_length=200)
    limit: int = Field(default=50, ge=1, le=200)
    only_missing: bool = True
    profile: bool = False


def _upsert_fact(db, ws, company_id, field, value, source_url, kind, confidence, actor):
    existing = db.scalar(
        select(CompanyFact).where(
            CompanyFact.workspace_id == ws,
            CompanyFact.company_id == company_id,
            CompanyFact.field == field,
            CompanyFact.source_kind == kind,
        )
    )
    if existing:
        if existing.value == value[:1000] and existing.source_url == source_url:
            return 0
        db.delete(existing)
        db.flush()
    db.add(
        CompanyFact(
            workspace_id=ws,
            company_id=company_id,
            field=field,
            value=value[:1000],
            source_url=source_url[:2000],
            confidence=confidence,
            source_kind=kind,
            source_id=hashlib.sha256(source_url.encode()).hexdigest()[:32],
            actor_id=actor,
        )
    )
    return 1


def finalize_site_research(db, job, result: dict) -> dict:
    ws, company_id = job.workspace_id, job.payload["company_id"]
    company = db.scalar(select(Company).where(Company.workspace_id == ws, Company.id == company_id))
    if not company:
        return result | {"facts": 0}
    created = 0
    for key, label in IMPRESSUM_LABELS.items():
        item = result.get("impressum", {}).get(key)
        if item and item.get("value"):
            created += _upsert_fact(
                db,
                ws,
                company_id,
                label,
                item["value"],
                item["source_url"],
                "website_impressum",
                "extracted",
                job.actor_id,
            )
    profile = company.provenance or {}
    company.provenance = profile | {
        "website_research": {
            "retrieved_at": result.get("retrieved_at"),
            "impressum_url": result.get("impressum_url"),
            "fields": sorted(result.get("impressum", {})),
        }
    }
    db.flush()
    # Name ↔ domain ↔ Impressum plausibility; a mismatch marks the Impressum facts
    # "unbestätigt" instead of adopting them silently.
    facts = db.scalars(
        select(CompanyFact).where(
            CompanyFact.workspace_id == ws, CompanyFact.company_id == company_id
        )
    ).all()
    quality = data_quality.store_check(db, ws, company, list(facts), job.actor_id)
    # Backwards compatible shape for verbatim excerpt facts (sales_agent.add_fact).
    text = "\n".join(p["text"] for p in result.get("pages", []))[:16000]
    return result | {
        "facts": created,
        "website_check": quality["check"],
        "url": result.get("website"),
        "text": text,
        "source_id": hashlib.sha256(str(result.get("website")).encode()).hexdigest()[:32],
    }


def profile_prompt_and_sources(result: dict) -> tuple[str, list[dict], dict]:
    sources, urls = [], {}
    for i, page in enumerate(result.get("pages", [])[:4], start=1):
        text = page.get("text", "").strip()
        if not text:
            continue
        sid = f"p{i}"
        sources.append({"id": sid, "text": text[:4500]})
        urls[sid] = page["url"]
    if not sources:
        raise HTTPException(422, "Die Recherche enthält keinen auswertbaren Seitentext.")
    lines = "\n".join(f"{label}: <kurz> [pX]" for label in PROFILE_LABELS)
    prompt = (
        "Erstelle ein knappes Firmenprofil für die Vertriebsvorbereitung eines Reinigungs-"
        "dienstleisters aus den Website-Quellen. Antworte im Feld text mit genau diesen "
        f"Zeilen:\n{lines}\nJede Zeile endet mit den Quellen-IDs in eckigen Klammern, "
        "z. B. [p1][p2]. Steht etwas nicht in den Quellen, schreibe 'unbekannt' ohne Quelle. "
        "Keine Schätzungen von Fläche oder Mitarbeitenden, nur ausdrückliche Hinweise."
    )
    return prompt, sources, urls


def finalize_company_profile(db, job, result: dict) -> dict:
    ws, company_id = job.workspace_id, job.payload["company_id"]
    urls = job.payload["source_urls"]
    stored = []
    for line in str(result.get("text", "")).splitlines():
        m = re.match(r"^\s*([^:]{3,40}):\s*(.+?)\s*((?:\[p\d+\]\s*)+)\s*$", line)
        if not m or m.group(1).strip() not in PROFILE_LABELS:
            continue
        value = m.group(2).strip()
        cited = re.findall(r"\[(p\d+)\]", m.group(3))
        if not value or value.lower().startswith("unbekannt") or not all(c in urls for c in cited):
            continue
        stored.append(m.group(1).strip())
        _upsert_fact(
            db,
            ws,
            company_id,
            "KI-Profil: " + m.group(1).strip(),
            value,
            urls[cited[0]],
            "ai_profile",
            "ai_summary_cited",
            job.actor_id,
        )
    return result | {"stored_fields": stored, "verified": False}


def register_research_routes(app, db_session, scope, record, audit):
    from app.platform_routes import job_output
    from app.providers import site_research

    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Diese Rolle darf keine Recherche starten.")

    def enqueue_site(db, ws, member, company):
        if not company.website:
            return None
        return enqueue(
            db,
            ws,
            member.user_id,
            "research",
            {"mode": "site", "url": company.website, "company_id": company.id},
            key=f"site-research:{company.id}:{now().date().isoformat()}",
        )

    @app.post("/v1/workspaces/{ws}/data-quality/recheck")
    def recheck(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        """Re-run name ↔ domain ↔ Impressum checks and segments over stored facts."""
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Keine Berechtigung.")
        result = data_quality.recheck_workspace(db, ws, member.user_id)
        audit(
            db,
            ws,
            member.user_id,
            "data_quality_rechecked",
            f"Website-Abgleich für {result['companies']} Firmen neu berechnet",
        )
        return result

    @app.post("/v1/workspaces/{ws}/companies/research-batch", status_code=202)
    def research_batch(
        ws: str, body: BatchInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        if not site_research.enabled():
            raise HTTPException(503, "Website-Recherche ist deaktiviert (RESEARCH_ENABLED=true).")
        stmt = select(Company).where(Company.workspace_id == ws, Company.website.is_not(None))
        if body.company_ids:
            stmt = stmt.where(Company.id.in_(body.company_ids))
        companies = db.scalars(stmt.order_by(Company.created_at).limit(500)).all()
        if body.company_ids and len({c.id for c in companies}) != len(set(body.company_ids)):
            raise HTTPException(422, "Unbekannte oder websitelose Unternehmen ausgewählt.")
        queued, skipped = [], 0
        for company in companies:
            if len(queued) >= body.limit:
                break
            if body.only_missing and (company.provenance or {}).get("website_research"):
                skipped += 1
                continue
            job = enqueue_site(db, ws, member, company)
            if job:
                queued.append(job.id)
        audit(
            db, ws, member.user_id, "research_batch", f"{len(queued)} Website-Recherchen eingeplant"
        )
        return {"queued": len(queued), "job_ids": queued, "skipped_already_researched": skipped}

    @app.post("/v1/workspaces/{ws}/companies/{entity_id}/profile", status_code=202)
    def company_profile(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        from app import credentials

        authoring(member)
        company = record(db, Company, ws, entity_id)
        if not credentials.get("LLM_API_KEY") or not credentials.get("LLM_MODEL"):
            raise HTTPException(503, "KI-Anbieter ist nicht konfiguriert (Integrationen).")
        research = db.scalar(
            select(Job)
            .where(
                Job.workspace_id == ws,
                Job.kind == "research",
                Job.status == "succeeded",
                Job.payload["company_id"].as_string() == company.id,
            )
            .order_by(Job.created_at.desc())
        )
        if (
            not research
            or not isinstance(research.result, dict)
            or not research.result.get("pages")
        ):
            raise HTTPException(422, "Zuerst eine Website-Recherche durchführen.")
        prompt, sources, urls = profile_prompt_and_sources(research.result)
        reservation = reserve_ai(db, ws, prompt + "".join(s["text"] for s in sources))
        job = enqueue(
            db,
            ws,
            member.user_id,
            "company_profile",
            {
                "prompt": prompt,
                "sources": sources,
                "source_urls": urls,
                "company_id": company.id,
                "purpose": "company_profile",
                "reservation_minor": reservation,
            },
        )
        audit(db, ws, member.user_id, "company_profile_queued", "KI-Firmenprofil eingeplant")
        return job_output(job)
