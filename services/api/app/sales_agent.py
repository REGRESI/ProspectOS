"""Internal Sales Agent V1: source-backed company evidence and evidence-cited outreach drafts.

Facts are only stored when they carry a source. A fact taken from website research must be
a verbatim excerpt of the stored research text for that company's own domain. Drafts cite
the exact facts they use (immutable snapshot), and AI suggestions may only cite supplied
source IDs (validated by the provider gateway). Nothing here sends a message.
"""

import hashlib
import os
import re

from fastapi import Depends, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import ForeignKeyConstraint, String, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.jobs import enqueue, reserve_ai
from app.journeys import (
    CampaignDraft,
    CampaignStep,
    CompanyFact,
    SequenceStepInput,
)
from app.models import Company, Contact, Draft, TenantMixin
from app.platform_models import Campaign, Enrollment, Job, Suppression
from app.prospecting import domain_of
from app.schemas import Strict

FACT_PRIORITY = {"website_research": 0, "openstreetmap": 1, "people_data_labs": 1, "manual": 2}
UNUSED_FIELDS = {"Website", "OSM-Tag", "Öffnungszeiten"}
DRAFT_FOOTER = {
    "evidence_template": "[Evidenzbasierter Vorlagenentwurf – Quellen am Entwurf hinterlegt. "
    "Kein KI-Anbieter aufgerufen; nichts versendet.]",
    "ai_suggestion": "[KI-Vorschlag – nur zitierte Quellen sind belegt; vor Freigabe prüfen. "
    "Nichts versendet.]",
}


class DraftEvidence(TenantMixin, Base):
    """Immutable citation snapshot: what a draft relied on at generation time."""

    __tablename__ = "draft_evidence"
    draft_id: Mapped[str] = mapped_column(String(36))
    fact_id: Mapped[str | None] = mapped_column(String(36))
    field: Mapped[str] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(String(1000))
    source_url: Mapped[str] = mapped_column(String(2000))
    source_kind: Mapped[str] = mapped_column(String(40))
    citation_id: Mapped[str] = mapped_column(String(64))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["message_drafts.workspace_id", "message_drafts.id"],
            ondelete="CASCADE",
        ),
    )


class FactInput(Strict):
    field: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=3, max_length=1000)
    source_url: str | None = Field(default=None, max_length=2000)
    research_job_id: str | None = None

    @field_validator("field", "value")
    @classmethod
    def printable(cls, value):
        if any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("Control characters are not allowed")
        return value.strip()


class PersonalizeInput(Strict):
    mode: str = "evidence"
    step_position: int = Field(default=0, ge=0, le=9)
    contact_ids: list[str] = Field(default_factory=list, max_length=200)
    instructions: str = Field(default="", max_length=1000)

    @field_validator("mode")
    @classmethod
    def supported(cls, value):
        if value not in ("evidence", "ai"):
            raise ValueError("Unsupported personalization mode")
        return value


def _norm(text: str) -> str:
    return " ".join(text.replace(" ", " ").split()).casefold()


def fact_output(fact):
    return {
        "id": fact.id,
        "company_id": fact.company_id,
        "field": fact.field,
        "value": fact.value,
        "source_url": fact.source_url,
        "source_kind": fact.source_kind,
        "source_id": fact.source_id,
        "confidence": fact.confidence,
        "created_at": fact.created_at,
    }


def ranked_facts(db, ws, company_id):
    rows = db.scalars(
        select(CompanyFact)
        .where(CompanyFact.workspace_id == ws, CompanyFact.company_id == company_id)
        .order_by(CompanyFact.created_at, CompanyFact.id)
    ).all()
    usable = [f for f in rows if f.field not in UNUSED_FIELDS]
    return sorted(usable, key=lambda f: (FACT_PRIORITY.get(f.source_kind, 3), f.created_at))


def evidence_sentence(fact, company: Company) -> str:
    if fact.source_kind == "website_research":
        return f"Auf Ihrer Website heißt es: „{fact.value}“"
    if fact.field == "Kategorie":
        place = f" in {company.location}" if company.location else ""
        return f"Ich bin auf {company.name} als Anbieter im Bereich {fact.value}{place} gestoßen."
    if fact.field == "Adresse":
        return f"Ihr Standort ({fact.value}) liegt in unserer Region."
    if fact.field.startswith("Mitarbeitende"):
        return f"{company.name} wird mit {fact.value} Mitarbeitenden angegeben."
    return f"{fact.field}: {fact.value}"


def citation_id(fact) -> str:
    return "F-" + hashlib.sha256((fact.id + fact.source_url).encode()).hexdigest()[:10]


def render_template(template: str, values: dict) -> str:
    return re.sub(
        r"\{(first_name|last_name|company|job_title|evidence)\}",
        lambda m: values.get(m.group(1), ""),
        template.replace("{{", "{").replace("}}", "}"),
    )


def _attach(db, ws, campaign, contact, position, content, source, facts):
    draft = Draft(
        workspace_id=ws,
        contact_id=contact.id,
        content=content[:3000],
        subject=campaign.name[:200],
        source=source,
        state="draft",
    )
    db.add(draft)
    db.flush()
    db.add(
        CampaignDraft(
            workspace_id=ws,
            campaign_id=campaign.id,
            contact_id=contact.id,
            draft_id=draft.id,
            step_position=position,
        )
    )
    for fact in facts:
        db.add(
            DraftEvidence(
                workspace_id=ws,
                draft_id=draft.id,
                fact_id=fact.id,
                field=fact.field,
                value=fact.value,
                source_url=fact.source_url,
                source_kind=fact.source_kind,
                citation_id=citation_id(fact),
            )
        )
    db.flush()
    return draft


def finalize_outreach(db, job, result):
    """Worker hook: persist an AI suggestion as a reviewable draft with validated citations."""
    payload = job.payload
    ws = job.workspace_id
    campaign = db.get(Campaign, payload["campaign_id"])
    contact = db.get(Contact, payload["contact_id"])
    if (
        campaign is None
        or contact is None
        or campaign.workspace_id != ws
        or contact.workspace_id != ws
        or campaign.status in ("paused", "completed")
        or not db.scalar(
            select(Enrollment.id).where(
                Enrollment.campaign_id == campaign.id, Enrollment.contact_id == contact.id
            )
        )
    ):
        return result | {"draft_id": None, "skipped": "campaign_or_enrollment_changed"}
    if db.scalar(select(Suppression.id).where(Suppression.contact_id == contact.id)):
        return result | {"draft_id": None, "skipped": "suppressed"}
    if db.scalar(
        select(CampaignDraft.id).where(
            CampaignDraft.campaign_id == campaign.id,
            CampaignDraft.contact_id == contact.id,
            CampaignDraft.step_position == payload["step_position"],
        )
    ):
        return result | {"draft_id": None, "skipped": "draft_exists"}
    by_citation = {}
    for fact_id in payload["fact_ids"]:
        fact = db.get(CompanyFact, fact_id)
        if fact and fact.workspace_id == ws:
            by_citation[citation_id(fact)] = fact
    cited = [by_citation[c] for c in result.get("citations", []) if c in by_citation]
    text = result["text"].strip()
    if result.get("unverified_claims"):
        text += (
            "\n\n[Unbelegte Aussagen laut Modell: "
            + "; ".join(str(x)[:200] for x in result["unverified_claims"][:5])
            + "]"
        )
    text += "\n\n" + DRAFT_FOOTER["ai_suggestion"]
    draft = _attach(
        db, ws, campaign, contact, payload["step_position"], text, "ai_suggestion", cited
    )
    return result | {"draft_id": draft.id}


def register_sales_agent_routes(app, db_session, scope, record, paginate, audit):
    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")

    @app.get("/v1/workspaces/{ws}/companies/{entity_id}/facts")
    def list_facts(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        company = record(db, Company, ws, entity_id)
        facts = db.scalars(
            select(CompanyFact)
            .where(CompanyFact.workspace_id == ws, CompanyFact.company_id == company.id)
            .order_by(CompanyFact.created_at.desc(), CompanyFact.id)
            .limit(200)
        ).all()
        research = db.scalars(
            select(Job)
            .where(
                Job.workspace_id == ws,
                Job.kind == "research",
                Job.payload["company_id"].as_string() == company.id,
            )
            .order_by(Job.created_at.desc())
            .limit(5)
        ).all()
        return {
            "items": [fact_output(f) for f in facts],
            "research_jobs": [
                {
                    "id": j.id,
                    "status": j.status,
                    "last_error": j.last_error,
                    "created_at": j.created_at,
                    "result": j.result if j.status == "succeeded" else None,
                }
                for j in research
            ],
            "notice": "Nur belegte Angaben. Website-Auszüge sind wörtlich, aber nicht unabhängig verifiziert.",
        }

    @app.post("/v1/workspaces/{ws}/companies/{entity_id}/facts", status_code=201)
    def add_fact(
        ws: str,
        entity_id: str,
        body: FactInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        company = record(db, Company, ws, entity_id)
        if body.research_job_id:
            job = record(db, Job, ws, body.research_job_id)
            if (
                job.kind != "research"
                or job.status != "succeeded"
                or not isinstance(job.result, dict)
                or job.payload.get("company_id") != company.id
            ):
                raise HTTPException(422, "Recherche gehört nicht zu diesem Unternehmen.")
            source_url = str(job.result.get("url") or "")
            if not company.website or domain_of(source_url) != domain_of(company.website):
                raise HTTPException(422, "Quelle ist nicht die Website dieses Unternehmens.")
            if _norm(body.value) not in _norm(str(job.result.get("text") or "")):
                raise HTTPException(
                    422, "Der Auszug muss wörtlich im gespeicherten Recherchetext vorkommen."
                )
            kind, confidence = "website_research", "website_excerpt"
            source_id = str(job.result.get("source_id") or "")[:64]
        else:
            source_url = body.source_url or ""
            if not re.match(r"^https://[^\s/@]+(/\S*)?$", source_url):
                raise HTTPException(422, "Eine HTTPS-Quelle ist für manuelle Angaben erforderlich.")
            kind, confidence = "manual", "user_reported"
            source_id = hashlib.sha256(source_url.encode()).hexdigest()[:32]
        fact = CompanyFact(
            workspace_id=ws,
            company_id=company.id,
            field=body.field,
            value=body.value,
            source_url=source_url,
            confidence=confidence,
            source_kind=kind,
            source_id=source_id,
            actor_id=member.user_id,
        )
        db.add(fact)
        db.flush()
        audit(db, ws, member.user_id, "company_fact_added", f"Belegte Angabe ({kind}) gespeichert")
        return fact_output(fact)

    @app.delete("/v1/workspaces/{ws}/companies/{entity_id}/facts/{fact_id}", status_code=204)
    def delete_fact(
        ws: str,
        entity_id: str,
        fact_id: str,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        company = record(db, Company, ws, entity_id)
        fact = record(db, CompanyFact, ws, fact_id)
        if fact.company_id != company.id:
            raise HTTPException(404, "Datensatz nicht gefunden.")
        db.delete(fact)
        audit(db, ws, member.user_id, "company_fact_removed", "Belegte Angabe entfernt")

    @app.post("/v1/workspaces/{ws}/companies/{entity_id}/research", status_code=202)
    def research_company(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        from app.platform_routes import job_output

        authoring(member)
        company = record(db, Company, ws, entity_id)
        if not company.website or not company.website.startswith("https://"):
            raise HTTPException(422, "Für die Recherche ist eine HTTPS-Website erforderlich.")
        if (
            os.getenv("RESEARCH_TERMS_APPROVED", "false").lower() != "true"
            or os.getenv("RESEARCH_NETWORK_GUARD_APPROVED", "false").lower() != "true"
        ):
            raise HTTPException(
                503,
                "Website-Recherche ist deaktiviert: Quellenprüfung und Egress-Schutz müssen vom Betreiber freigegeben sein.",
            )
        job = enqueue(
            db, ws, member.user_id, "research", {"url": company.website, "company_id": company.id}
        )
        audit(db, ws, member.user_id, "company_research_queued", "Website-Recherche eingeplant")
        return job_output(job)

    @app.get("/v1/workspaces/{ws}/outreach/drafts/{entity_id}/evidence")
    def draft_evidence(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        draft = record(db, Draft, ws, entity_id)
        rows = db.scalars(
            select(DraftEvidence)
            .where(DraftEvidence.workspace_id == ws, DraftEvidence.draft_id == draft.id)
            .order_by(DraftEvidence.citation_id)
        ).all()
        return {
            "draft_id": draft.id,
            "source": draft.source,
            "items": [
                {
                    k: getattr(r, k)
                    for k in (
                        "citation_id",
                        "fact_id",
                        "field",
                        "value",
                        "source_url",
                        "source_kind",
                    )
                }
                for r in rows
            ],
        }

    @app.post("/v1/workspaces/{ws}/campaigns/{entity_id}/personalize")
    def personalize(
        ws: str,
        entity_id: str,
        body: PersonalizeInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.platform_routes import job_output

        authoring(member)
        campaign = record(db, Campaign, ws, entity_id, True)
        if campaign.status in ("paused", "completed"):
            raise HTTPException(409, "Kampagne ist pausiert oder abgeschlossen.")
        step = db.scalar(
            select(CampaignStep).where(
                CampaignStep.campaign_id == campaign.id,
                CampaignStep.position == body.step_position,
            )
        )
        template = (
            step.template
            if step
            else "Hallo {first_name},\n\n{evidence}\n\n"
            + (campaign.goal or "Hätten Sie Interesse an einem kurzen Austausch?")
        )
        SequenceStepInput(position=body.step_position, template=template)
        stmt = (
            select(Contact)
            .join(Enrollment, Enrollment.contact_id == Contact.id)
            .where(Enrollment.campaign_id == campaign.id)
            .order_by(Contact.last_name, Contact.id)
        )
        if body.contact_ids:
            stmt = stmt.where(Contact.id.in_(body.contact_ids))
        contacts = db.scalars(stmt.limit(200)).all()
        if body.contact_ids and len(contacts) != len(set(body.contact_ids)):
            raise HTTPException(422, "Kontakte sind dieser Kampagne nicht zugeordnet.")
        if body.mode == "ai":
            for name in ("LLM_API_KEY", "LLM_MODEL"):
                if not os.getenv(name):
                    raise HTTPException(
                        503,
                        "KI-Anbieter ist nicht konfiguriert. Evidenzbasierte Vorlage verwenden.",
                    )
        summary = {"created": 0, "queued": 0, "duplicates": 0, "no_evidence": 0, "suppressed": 0}
        jobs = []
        for contact in contacts:
            if db.scalar(select(Suppression.id).where(Suppression.contact_id == contact.id)):
                summary["suppressed"] += 1
                continue
            if db.scalar(
                select(CampaignDraft.id).where(
                    CampaignDraft.campaign_id == campaign.id,
                    CampaignDraft.contact_id == contact.id,
                    CampaignDraft.step_position == body.step_position,
                )
            ):
                summary["duplicates"] += 1
                continue
            company = db.get(Company, contact.company_id) if contact.company_id else None
            facts = ranked_facts(db, ws, company.id)[:4] if company else []
            if not facts:
                summary["no_evidence"] += 1
                continue
            values = {
                "first_name": contact.first_name,
                "last_name": contact.last_name,
                "job_title": contact.job_title,
                "company": company.name,
            }
            if body.mode == "evidence":
                used = facts[:2]
                values["evidence"] = " ".join(evidence_sentence(f, company) for f in used)
                content = render_template(template, values)
                if "{evidence}" not in template:
                    content = values["evidence"] + "\n\n" + content
                content += "\n\n" + DRAFT_FOOTER["evidence_template"]
                if len(content) > 3000:
                    raise HTTPException(422, "Entwurf ist länger als 3.000 Zeichen.")
                _attach(
                    db,
                    ws,
                    campaign,
                    contact,
                    body.step_position,
                    content,
                    "evidence_template",
                    used,
                )
                summary["created"] += 1
                continue
            sources = [{"id": citation_id(f), "text": f"{f.field}: {f.value}"} for f in facts]
            prompt = (
                "Formuliere eine kurze, höfliche LinkedIn-Nachricht (max. 600 Zeichen, Deutsch, Sie-Form) "
                "an die Person. Nutze ausschließlich die Quellen; zitiere deren IDs. "
                "Keine erfundenen Fakten, keine Annahmen zu Bedarf oder Größe.\n"
                f"Empfänger: {contact.first_name} {contact.last_name}, Rolle: {contact.job_title or 'unbekannt'}\n"
                f"Unternehmen: {company.name}\nKampagnenziel: {campaign.goal or campaign.name}\n"
                f"Vorlage (Struktur): {render_template(template, values | {'evidence': '[Beleg]'})}\n"
                f"Zusatzhinweise des Nutzers: {body.instructions or '-'}"
            )
            reservation = reserve_ai(db, ws, prompt)
            job = enqueue(
                db,
                ws,
                member.user_id,
                "outreach_ai",
                {
                    "prompt": prompt,
                    "sources": sources,
                    "purpose": "outreach_personalization",
                    "reservation_minor": reservation,
                    "campaign_id": campaign.id,
                    "contact_id": contact.id,
                    "step_position": body.step_position,
                    "fact_ids": [f.id for f in facts],
                },
            )
            jobs.append(job_output(job))
            summary["queued"] += 1
        audit(
            db,
            ws,
            member.user_id,
            "campaign_personalized",
            f"Personalisierung ({body.mode}): {summary['created']} Entwürfe, "
            f"{summary['queued']} KI-Jobs, {summary['no_evidence']} ohne Belege",
        )
        return summary | {
            "mode": body.mode,
            "jobs": jobs,
            "notice": "Entwürfe benötigen Freigabe. Kontakte ohne belegte Unternehmensangaben "
            "werden nicht personalisiert. Nichts wurde versendet.",
        }
