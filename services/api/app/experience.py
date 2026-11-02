"""Operational home, reviewed image generation, social composition and manual engagement."""

import hashlib
import json
import os
from io import BytesIO
from types import SimpleNamespace

from fastapi import Depends, HTTPException
from PIL import Image
from pydantic import Field, field_validator
from sqlalchemy import JSON, ForeignKeyConstraint, String, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now
from app.jobs import enqueue, reserve_ai, usage_account
from app.media import private_path, store_image
from app.models import Audit, Company, Contact, Deal, Draft, Post, TenantMixin
from app.platform_models import (
    Asset,
    Brand,
    Campaign,
    Enrollment,
    Job,
    Note,
    PostRevision,
    Task,
)
from app.schemas import Strict
from app.studio import WritingControls, constraints_for, shape_text, voice_snapshot, writing_prompt


class AssetOrigin(TenantMixin, Base):
    __tablename__ = "asset_origins"
    asset_id: Mapped[str] = mapped_column(String(36))
    job_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(30))
    reviewed: Mapped[bool] = mapped_column(default=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("workspace_id", "asset_id"),
        ForeignKeyConstraint(["workspace_id", "asset_id"], ["assets.workspace_id", "assets.id"]),
        ForeignKeyConstraint(["workspace_id", "job_id"], ["jobs.workspace_id", "jobs.id"]),
    )


class Interaction(TenantMixin, Base):
    __tablename__ = "manual_interactions"
    author: Mapped[str] = mapped_column(String(120))
    content: Mapped[str] = mapped_column(String(5000))
    post_url: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(20), default="open")
    reply_draft: Mapped[str] = mapped_column(String(5000), default="")
    actor_id: Mapped[str] = mapped_column(String(36))
    source: Mapped[str] = mapped_column(String(20), default="manual")


class WorkspaceSetup(TenantMixin, Base):
    __tablename__ = "workspace_setups"
    business: Mapped[str] = mapped_column(String(2000), default="")
    region: Mapped[str] = mapped_column(String(200), default="")
    target_customers: Mapped[str] = mapped_column(String(2000), default="")
    completed_steps: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (UniqueConstraint("workspace_id"),)


class SocialGeneration(WritingControls):
    topic: str = Field(min_length=3, max_length=500)
    audience: str = Field(default="", max_length=500)
    brand_id: str | None = None
    tone: str = Field(default="Klar und sachlich", max_length=200)
    objective: str = Field(default="", max_length=500)
    post_type: str = Field(default="Fachbeitrag", max_length=100)
    instructions: str = Field(default="", max_length=1000)
    variants: int = Field(default=3, ge=3, le=3)


class ImageGeneration(Strict):
    prompt: str = Field(min_length=3, max_length=3000)
    alt_text: str = Field(min_length=3, max_length=1000)
    brand_id: str | None = None
    rights_confirmed: bool = False
    style: str = Field(default="", max_length=200)
    mood: str = Field(default="", max_length=200)
    post_context: str = Field(default="", max_length=1000)
    aspect_ratio: str = "square"
    allow_text: bool = False

    @field_validator("aspect_ratio")
    @classmethod
    def ratio(cls, value):
        if value not in ("square", "landscape", "portrait"):
            raise ValueError("Unsupported image format")
        return value


class ImageReview(Strict):
    rights_confirmed: bool


class CropInput(Strict):
    crop: str
    alt_text: str | None = Field(default=None, max_length=1000)

    @field_validator("crop")
    @classmethod
    def mode(cls, value):
        if value not in ("square", "portrait", "original"):
            raise ValueError("Unsupported crop mode")
        return value


class InteractionInput(Strict):
    author: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=3, max_length=5000)
    post_url: str | None = Field(default=None, max_length=2000)

    @field_validator("post_url")
    @classmethod
    def safe_url(cls, value):
        from urllib.parse import urlsplit

        if value:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("HTTPS URL required")
        return value


class InteractionUpdate(Strict):
    status: str
    reply_draft: str = Field(default="", max_length=5000)

    @field_validator("status")
    @classmethod
    def allowed(cls, value):
        if value not in ("open", "reviewed"):
            raise ValueError("Invalid status")
        return value


class SetupInput(Strict):
    business: str = Field(default="", max_length=2000)
    region: str = Field(default="", max_length=200)
    target_customers: str = Field(default="", max_length=2000)
    completed_steps: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("completed_steps")
    @classmethod
    def valid_steps(cls, value):
        if not set(value) <= {"business", "icp", "leads", "ai", "linkedin", "first_action"}:
            raise ValueError("Invalid onboarding step")
        return list(dict.fromkeys(value))


def generation_fingerprint(kind):
    image = kind == "social_image"
    values = {
        "model": os.getenv("IMAGE_MODEL") if image else os.getenv("LLM_MODEL"),
        "base": (
            (os.getenv("IMAGE_BASE_URL") if image else None)
            or os.getenv("LLM_BASE_URL")
            or "https://api.openai.com/v1"
        ),
        "cap": os.getenv("IMAGE_MAX_COST_USD_CENTS") if image else None,
        "input_price": None if image else os.getenv("LLM_INPUT_USD_PER_MILLION"),
        "output_price": None if image else os.getenv("LLM_OUTPUT_USD_PER_MILLION"),
        "tokens": None if image else os.getenv("LLM_MAX_OUTPUT_TOKENS", "1500"),
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def validate_generation_config(job):
    expected = job.payload.get("provider_configuration")
    if expected and expected != generation_fingerprint(job.kind):
        raise HTTPException(409, "provider_configuration_changed")


def image_requirements():
    missing = []
    if not (os.getenv("IMAGE_API_KEY") or os.getenv("LLM_API_KEY")):
        missing.append("IMAGE_API_KEY oder LLM_API_KEY")
    if not os.getenv("IMAGE_MODEL"):
        missing.append("IMAGE_MODEL")
    try:
        cap = int(os.environ["IMAGE_MAX_COST_USD_CENTS"])
        if not 1 <= cap <= 10000:
            raise ValueError()
    except (KeyError, ValueError):
        cap = None
        missing.append("IMAGE_MAX_COST_USD_CENTS (geprüfte Kostenobergrenze)")
    return {
        "configured": not missing,
        "requirements": missing,
        "max_cost_minor": cap,
        "currency": "USD",
    }


def write_asset(db, ws, payload, alt_text, filename):
    from app.entitlements import remaining

    remaining(db, ws, "assets")
    key, size, digest = store_image(payload)
    asset = Asset(
        workspace_id=ws,
        filename=filename,
        storage_key=key,
        content_type="image/jpeg",
        size=size,
        sha256=digest,
        alt_text=alt_text,
        rights_confirmed=True,
    )
    try:
        db.add(asset)
        db.flush()
    except Exception:
        private_path(key).unlink(missing_ok=True)
        raise
    return asset


def external_generation(job):
    """Paid calls run after the durable dispatch marker; returned suggestions are never facts."""
    from app.providers.ai import generate_text

    if job.kind == "social_image":
        from app.providers.images import OpenAIImages

        if job.payload.get("aspect_ratio", "square") == "square":
            payload = OpenAIImages().generate(job.payload["prompt"])
        else:
            payload = OpenAIImages().generate(
                job.payload["prompt"], aspect_ratio=job.payload["aspect_ratio"]
            )
        return {"image_bytes": payload}, SimpleNamespace(
            input_tokens=0,
            output_tokens=0,
            estimated_cost_microunits=job.payload["reservation_minor"] * 10000,
        )
    if job.kind == "social_reply":
        result = generate_text(job.payload["prompt"], job.payload.get("sources", []))
        return result.model_dump(mode="json") | {
            "verified": False,
            "manual_review_required": True,
        }, result
    results = []
    input_tokens = output_tokens = cost = 0
    angles = (
        ["Gezielte Überarbeitung: " + job.payload["action"]]
        if job.payload.get("purpose") == "social_refinement"
        else [
            "Persönlich: eine ehrliche Beobachtung, keine erfundene Geschichte",
            "Direkt und meinungsstark: klare These und begründeter Standpunkt",
            "Fachlich und praxisnah: konkrete Schritte, keine erfundenen Zahlen",
        ]
    )
    for index, angle in enumerate(angles):
        output = generate_text(
            job.payload["prompt"] + "\nVariante " + str(index + 1) + ": " + angle,
            job.payload.get("sources", []),
        )
        text = shape_text(output.text, job.payload.get("constraints", {}))
        if not text:
            from app.providers.ai import ProviderError

            raise ProviderError("empty_social_output")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        results.append(
            {
                "text": text,
                "angle": angle,
                "hook": lines[0] if lines else "",
                "cta": lines[-1] if len(lines) > 1 else "",
                "citations": output.citations,
                "unverified_claims": output.unverified_claims,
            }
        )
        input_tokens += output.input_tokens
        output_tokens += output.output_tokens
        cost += output.estimated_cost_microunits
        # Preserve already-paid partial suggestions if a later variant fails.
        from app.db import SessionLocal
        from app.jobs import tenant

        with SessionLocal() as db, db.begin():
            tenant(db, job.workspace_id)
            current = db.get(Job, job.id)
            current.result = {
                "variants": results,
                "provider": "openai_compatible",
                "partial": True,
                "verified": False,
            }
    return {
        "variants": results,
        "provider": "openai_compatible",
        "verified": False,
        "partial": False,
        "notice": "KI-Vorschläge aus konfiguriertem Anbieter. Fakten und Rechte vor Freigabe prüfen.",
    }, SimpleNamespace(
        input_tokens=input_tokens, output_tokens=output_tokens, estimated_cost_microunits=cost
    )


def finalize_generation(db, job, result):
    if job.kind != "social_image":
        return result
    from app.platform_routes import asset_output

    asset = write_asset(
        db,
        job.workspace_id,
        result["image_bytes"],
        job.payload["alt_text"],
        "KI-Entwurf-" + job.id[:8] + ".jpg",
    )
    asset.uploaded_by = job.actor_id
    db.add(
        AssetOrigin(
            workspace_id=job.workspace_id,
            asset_id=asset.id,
            job_id=job.id,
            kind="ai_generated",
            reviewed=False,
            metadata_json={
                "provider": "openai_images",
                "model": job.payload["model"],
                "estimated_max_cost_minor": job.payload["reservation_minor"],
                "aspect_ratio": job.payload.get("aspect_ratio", "square"),
                "actor_id": job.actor_id,
            },
        )
    )
    return {
        "asset": asset_output(asset) | {"created_at": asset.created_at.isoformat()},
        "provider": "openai_images",
        "review_required": True,
        "estimated_max_cost_minor": job.payload["reservation_minor"],
        "notice": "Echte Anbieterausgabe privat gespeichert. Vor Bibliotheksübernahme prüfen; Kosten sind die konfigurierte Obergrenze, keine Anbieterrechnung.",
    }


def text_requirements():
    if not os.getenv("LLM_API_KEY") or not os.getenv("LLM_MODEL"):
        raise HTTPException(503, "LLM_API_KEY und LLM_MODEL für echte KI-Varianten konfigurieren.")


def register_experience_routes(
    app, db_session, scope, record, paginate, audit, contact_output, profile
):
    @app.get("/v1/workspaces/{ws}/home")
    def home(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        def count(model, *filters):
            return db.scalar(
                select(func.count()).select_from(model).where(model.workspace_id == ws, *filters)
            )

        leads = list(
            db.scalars(
                select(Contact)
                .where(Contact.workspace_id == ws)
                .order_by(Contact.created_at.desc())
                .limit(6)
            )
        )
        companies = {
            c.id: c
            for c in db.scalars(
                select(Company).where(
                    Company.workspace_id == ws,
                    Company.id.in_({c.company_id for c in leads if c.company_id}),
                )
            )
        }
        qualified = list(
            db.scalars(
                select(Contact)
                .where(Contact.workspace_id == ws, Contact.status == "qualified")
                .order_by(Contact.created_at.desc())
                .limit(5)
            )
        )
        scheduled = list(
            db.scalars(
                select(Post)
                .where(Post.workspace_id == ws, Post.state == "scheduled")
                .order_by(Post.scheduled_at)
                .limit(5)
            )
        )
        tasks = list(
            db.scalars(
                select(Task)
                .where(Task.workspace_id == ws, Task.state == "open")
                .order_by(Task.due_at.asc().nullslast(), Task.created_at.desc())
                .limit(5)
            )
        )
        campaigns = list(
            db.scalars(
                select(Campaign)
                .where(Campaign.workspace_id == ws, Campaign.status == "active")
                .order_by(Campaign.created_at.desc())
                .limit(5)
            )
        )
        pending = list(
            db.scalars(
                select(Draft)
                .where(Draft.workspace_id == ws, Draft.state == "draft", Draft.subject != "")
                .order_by(Draft.created_at.desc())
                .limit(5)
            )
        )
        pipeline = list(
            db.scalars(
                select(Audit)
                .where(
                    Audit.workspace_id == ws, Audit.kind.in_(["deal_stage_changed", "deal_created"])
                )
                .order_by(Audit.created_at.desc())
                .limit(5)
            )
        )
        return {
            "counts": {
                "contacts": count(Contact),
                "companies": count(Company),
                "qualified": count(Contact, Contact.status == "qualified"),
                "deals": count(Deal, Deal.stage.not_in(["won", "lost"])),
                "pipeline_value": db.scalar(
                    select(func.coalesce(func.sum(Deal.amount), 0)).where(
                        Deal.workspace_id == ws, Deal.stage.not_in(["won", "lost"])
                    )
                ),
                "pending_approvals": count(Draft, Draft.state == "draft", Draft.subject != ""),
                "scheduled_posts": count(Post, Post.state == "scheduled"),
                "open_tasks": count(Task, Task.state == "open"),
                "active_campaigns": count(Campaign, Campaign.status == "active"),
            },
            "recent_leads": [
                contact_output(c, companies.get(c.company_id), profile(db, ws)) for c in leads
            ],
            "qualified_leads": [
                {"id": c.id, "name": c.first_name + " " + c.last_name, "job_title": c.job_title}
                for c in qualified
            ],
            "pending_outreach": [
                {
                    "id": d.id,
                    "contact_id": d.contact_id,
                    "subject": d.subject,
                    "revision": d.revision,
                }
                for d in pending
            ],
            "scheduled_posts": [
                {
                    "id": p.id,
                    "caption": p.caption,
                    "scheduled_at": p.scheduled_at,
                    "publish_enabled": p.publish_enabled,
                    "state": p.state,
                }
                for p in scheduled
            ],
            "tasks": [
                {"id": t.id, "title": t.title, "due_at": t.due_at, "contact_id": t.contact_id}
                for t in tasks
            ],
            "campaigns": [
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "audience_count": db.scalar(
                        select(func.count())
                        .select_from(Enrollment)
                        .where(Enrollment.workspace_id == ws, Enrollment.campaign_id == c.id)
                    ),
                }
                for c in campaigns
            ],
            "pipeline_changes": [
                {"id": e.id, "description": e.description, "created_at": e.created_at}
                for e in pipeline
            ],
        }

    @app.get("/v1/workspaces/{ws}/deals/{deal_id}/context")
    def deal_context(
        ws: str, deal_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        deal = record(db, Deal, ws, deal_id)
        contact = record(db, Contact, ws, deal.contact_id) if deal.contact_id else None
        company = (
            record(db, Company, ws, contact.company_id) if contact and contact.company_id else None
        )
        tasks = (
            list(
                db.scalars(
                    select(Task)
                    .where(Task.workspace_id == ws, Task.contact_id == contact.id)
                    .order_by(Task.created_at.desc())
                    .limit(20)
                )
            )
            if contact
            else []
        )
        notes = (
            list(
                db.scalars(
                    select(Note)
                    .where(Note.workspace_id == ws, Note.contact_id == contact.id)
                    .order_by(Note.created_at.desc())
                    .limit(20)
                )
            )
            if contact
            else []
        )
        return {
            "id": deal.id,
            "title": deal.title,
            "amount": deal.amount,
            "stage": deal.stage,
            "contact": {"id": contact.id, "name": contact.first_name + " " + contact.last_name}
            if contact
            else None,
            "company": {"id": company.id, "name": company.name} if company else None,
            "tasks": [
                {"id": t.id, "title": t.title, "state": t.state, "due_at": t.due_at} for t in tasks
            ],
            "notes": [{"id": n.id, "body": n.body, "created_at": n.created_at} for n in notes],
            "notice": "Aufgaben und Notizen beziehen sich auf den verknüpften Kontakt. Kein erfundener Deal-Verlauf.",
        }

    @app.get("/v1/workspaces/{ws}/onboarding")
    def setup(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        item = db.scalar(select(WorkspaceSetup).where(WorkspaceSetup.workspace_id == ws))
        return (
            {
                key: getattr(item, key)
                for key in ("business", "region", "target_customers", "completed_steps")
            }
            if item
            else {"business": "", "region": "", "target_customers": "", "completed_steps": []}
        )

    @app.put("/v1/workspaces/{ws}/onboarding")
    def save_setup(
        ws: str, body: SetupInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Owner/admin required.")
        item = db.scalar(
            select(WorkspaceSetup).where(WorkspaceSetup.workspace_id == ws).with_for_update()
        )
        if not item:
            item = WorkspaceSetup(workspace_id=ws)
            db.add(item)
        for key, value in body.model_dump().items():
            setattr(item, key, value)
        audit(db, ws, member.user_id, "onboarding_updated", "Workspace-Einrichtung gespeichert")
        return body

    @app.post("/v1/workspaces/{ws}/social/generate", status_code=202)
    def generate_social(
        ws: str,
        body: SocialGeneration,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.platform_routes import job_output

        text_requirements()
        voice = voice_snapshot(db, ws, body.voice_profile_id, record)
        sources = []
        if body.brand_id:
            brand = record(db, Brand, ws, body.brand_id)
            sources = [
                {
                    "id": brand.id,
                    "text": f"Benutzer-Markenprofil, keine Kundenbelege: {brand.name}; Stimme:{brand.voice}; Zielgruppe:{brand.audience}; Säulen:{brand.pillars}",
                }
            ]
        prompt = f"Thema: {body.topic}\nZielgruppe: {body.audience}\nTonalität: {body.tone}\nZiel: {body.objective}\nFormat: {body.post_type}\nRevisionswünsche: {body.instructions}\nSchreibe einen LinkedIn-Entwurf unter Beachtung der ausgewählten Hook- und CTA-Regeln. Keine erfundenen Kundenbelege, Statistiken oder Geschäftszahlen. Fehlende Fakten als unbekannt behandeln."
        prompt = writing_prompt(body, voice) + "\n" + prompt
        if body.factual_notes:
            sources.append({"id": "user_facts", "text": body.factual_notes})
        if len(prompt) > 11500:
            raise HTTPException(422, "Stilbeispiele oder Kontext für diesen Auftrag kürzen.")
        reservation = reserve_ai(db, ws, prompt + str(sources), multiplier=3)
        job = enqueue(
            db,
            ws,
            member.user_id,
            "social_text",
            {
                "prompt": prompt,
                "sources": sources,
                "reservation_minor": reservation,
                "purpose": "social_variants",
                "voice_snapshot": voice,
                "constraints": constraints_for(body, voice),
                "parameters": body.model_dump(),
                "provider_configuration": generation_fingerprint("social_text"),
            },
        )
        audit(
            db,
            ws,
            member.user_id,
            "social_ai_requested",
            "Drei echte KI-Varianten mit Budgetreservierung angefordert",
        )
        return job_output(job)

    @app.get("/v1/workspaces/{ws}/social/images/requirements")
    def requirements(ws: str, member=Depends(scope)):
        return image_requirements()

    @app.post("/v1/workspaces/{ws}/social/images/generate", status_code=202)
    def generate_image(
        ws: str,
        body: ImageGeneration,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.entitlements import remaining
        from app.platform_routes import job_output

        status = image_requirements()
        if not status["configured"]:
            raise HTTPException(
                503, "Bildanbieter konfigurieren: " + ", ".join(status["requirements"])
            )
        if not body.rights_confirmed:
            raise HTTPException(422, "Rechte und Anbieterbedingungen bestätigen.")
        remaining(db, ws, "assets")
        brand = record(db, Brand, ws, body.brand_id) if body.brand_id else None
        account = usage_account(db, ws)
        cost = status["max_cost_minor"]
        if account.ai_spent_minor + account.ai_reserved_minor + cost > account.ai_budget_minor:
            raise HTTPException(402, "Workspace-KI-Budget überschritten.")
        account.ai_reserved_minor += cost
        prompt = (
            "Create a professional illustrative business graphic, never a fake customer photo or fabricated testimonial. "
            + body.prompt
        )
        prompt += (
            f" Visual style: {body.style}; mood: {body.mood}; post context: {body.post_context}."
        )
        if not body.allow_text:
            prompt += " No typography, captions, text overlays or logos."
        if brand:
            prompt += f" Brand palette: {brand.primary_color}; style: {brand.voice}."
        job = enqueue(
            db,
            ws,
            member.user_id,
            "social_image",
            {
                "prompt": prompt,
                "alt_text": body.alt_text,
                "aspect_ratio": body.aspect_ratio,
                "model": os.environ["IMAGE_MODEL"],
                "provider_configuration": generation_fingerprint("social_image"),
                "reservation_minor": cost,
            },
        )
        audit(
            db,
            ws,
            member.user_id,
            "image_generation_requested",
            "Echte Bildgenerierung mit Kostenobergrenze angefordert",
        )
        return job_output(job)

    @app.post("/v1/workspaces/{ws}/social/images/{job_id}/save")
    def save_generated(
        ws: str,
        job_id: str,
        body: ImageReview,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.platform_routes import asset_output

        job = record(db, Job, ws, job_id)
        origin = db.scalar(
            select(AssetOrigin)
            .where(AssetOrigin.workspace_id == ws, AssetOrigin.job_id == job.id)
            .with_for_update()
        )
        if job.kind != "social_image" or job.status != "succeeded" or not origin:
            raise HTTPException(409, "Noch kein gespeichertes Anbieterbild vorhanden.")
        if not body.rights_confirmed:
            raise HTTPException(422, "Bild und Nutzungsrechte explizit prüfen.")
        origin.reviewed = True
        audit(
            db,
            ws,
            member.user_id,
            "generated_asset_reviewed",
            "KI-Bild geprüft und in private Bibliothek übernommen",
        )
        return asset_output(record(db, Asset, ws, origin.asset_id))

    @app.post("/v1/workspaces/{ws}/assets/{asset_id}/crop", status_code=201)
    def crop(
        ws: str,
        asset_id: str,
        body: CropInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.platform_routes import asset_output

        asset = record(db, Asset, ws, asset_id)
        origin = db.scalar(
            select(AssetOrigin).where(
                AssetOrigin.workspace_id == ws, AssetOrigin.asset_id == asset.id
            )
        )
        if origin and not origin.reviewed:
            raise HTTPException(409, "Generiertes Original zuerst prüfen.")
        image = Image.open(private_path(asset.storage_key))
        image.load()
        if body.crop != "original":
            target_ratio = 1 if body.crop == "square" else 4 / 5
            width, height = image.size
            if width / height > target_ratio:
                new_width = round(height * target_ratio)
                left = (width - new_width) // 2
                image = image.crop((left, 0, left + new_width, height))
            else:
                new_height = round(width / target_ratio)
                top = (height - new_height) // 2
                image = image.crop((0, top, width, top + new_height))
        output = BytesIO()
        image.save(output, format="JPEG", quality=90)
        derived = write_asset(
            db,
            ws,
            output.getvalue(),
            body.alt_text or asset.alt_text,
            "Zuschnitt-" + asset.filename[:180] + ".jpg",
        )
        db.add(
            AssetOrigin(
                workspace_id=ws,
                asset_id=derived.id,
                kind="crop",
                reviewed=True,
                metadata_json={"source_asset_id": asset.id, "crop": body.crop},
            )
        )
        audit(
            db,
            ws,
            member.user_id,
            "asset_cropped",
            "Privater Bildzuschnitt gespeichert; Original erhalten",
        )
        return asset_output(derived)

    @app.get("/v1/workspaces/{ws}/social/posts/{post_id}/revisions")
    def revisions(
        ws: str, post_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        record(db, Post, ws, post_id)
        rows = list(
            db.scalars(
                select(PostRevision)
                .where(PostRevision.workspace_id == ws, PostRevision.post_id == post_id)
                .order_by(PostRevision.revision.desc())
                .limit(100)
            )
        )
        return {
            "items": [
                {"revision": r.revision, "snapshot": r.snapshot, "created_at": r.created_at}
                for r in rows
            ]
        }

    @app.get("/v1/workspaces/{ws}/social/interactions")
    def interactions(
        ws: str,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        rows, total = paginate(
            db,
            select(Interaction)
            .where(Interaction.workspace_id == ws)
            .order_by(Interaction.created_at.desc()),
            page,
            limit,
        )
        return {
            "items": [
                {
                    k: getattr(r, k)
                    for k in (
                        "id",
                        "author",
                        "content",
                        "post_url",
                        "status",
                        "reply_draft",
                        "source",
                        "created_at",
                    )
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "limit": limit,
            "notice": "Manuell erfasste Interaktionen. Kein fremder Feed oder Kommentarabruf.",
        }

    @app.post("/v1/workspaces/{ws}/social/interactions", status_code=201)
    def add_interaction(
        ws: str,
        body: InteractionInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        item = Interaction(workspace_id=ws, actor_id=member.user_id, **body.model_dump())
        db.add(item)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "manual_interaction_recorded",
            "Interaktion manuell erfasst; nicht als Anbieterereignis verifiziert",
        )
        return {"id": item.id, "source": "manual", "status": item.status, **body.model_dump()}

    @app.patch("/v1/workspaces/{ws}/social/interactions/{item_id}")
    def update_interaction(
        ws: str,
        item_id: str,
        body: InteractionUpdate,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        item = record(db, Interaction, ws, item_id, True)
        item.status = body.status
        item.reply_draft = body.reply_draft
        audit(
            db,
            ws,
            member.user_id,
            "manual_reply_reviewed",
            "Manuelle Antwort gespeichert/geprüft; nichts extern veröffentlicht",
        )
        return {"id": item.id, **body.model_dump(), "source": "manual"}

    @app.post("/v1/workspaces/{ws}/social/interactions/{item_id}/suggest", status_code=202)
    def suggest_reply(
        ws: str, item_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        from app.platform_routes import job_output

        item = record(db, Interaction, ws, item_id)
        if not os.getenv("LLM_API_KEY") or not os.getenv("LLM_MODEL"):
            raise HTTPException(
                503, "KI-Anbieter fehlt. Antworten können manuell vorbereitet werden."
            )
        prompt = "Entwirf eine sachliche deutsche Antwort auf den manuell bereitgestellten Kommentar. Keine behaupteten Kundenbeziehungen, Zahlen oder externen Handlungen."
        sources = [{"id": item.id, "text": "Unverifizierter manueller Kontext: " + item.content}]
        reserve = reserve_ai(db, ws, prompt + str(sources))
        return job_output(
            enqueue(
                db,
                ws,
                member.user_id,
                "social_reply",
                {
                    "prompt": prompt,
                    "sources": sources,
                    "reservation_minor": reserve,
                    "purpose": "manual_engagement_reply",
                    "provider_configuration": generation_fingerprint("social_reply"),
                },
            )
        )


def provider_test(provider, db, ws):
    """Read-only checks. Reachability does not imply permission to generate, send or publish."""
    from urllib.parse import quote, urlsplit

    from app.platform_models import Connection
    from app.providers.ai import ProviderError, request_json
    from app.social import cipher

    missing = []
    if provider == "linkedin":
        connection = db.scalar(
            select(Connection).where(
                Connection.workspace_id == ws, Connection.provider == "linkedin"
            )
        )
        if not connection or connection.expires_at <= now():
            return {
                "status": "not_connected",
                "validated": False,
                "message": "LinkedIn zuerst über den offiziellen OAuth-Dialog verbinden.",
            }
        data, _ = request_json(
            "GET",
            "https://api.linkedin.com/v2/userinfo",
            headers={
                "Authorization": "Bearer "
                + cipher().decrypt(connection.encrypted_token.encode()).decode()
            },
        )
        if "urn:li:person:" + str(data.get("sub", "")) != connection.author_urn:
            raise ProviderError("identity_mismatch")
        return {
            "status": "validated",
            "validated": True,
            "scopes": connection.scopes,
            "message": "Kontozugriff bestätigt. Veröffentlichung erfordert zusätzlich Produktfreigabe und w_member_social.",
        }
    if provider in ("llm", "images"):
        image = provider == "images"
        key = (
            (os.getenv("IMAGE_API_KEY") or os.getenv("LLM_API_KEY"))
            if image
            else os.getenv("LLM_API_KEY")
        )
        model = os.getenv("IMAGE_MODEL") if image else os.getenv("LLM_MODEL")
        base = (
            (os.getenv("IMAGE_BASE_URL") if image else None)
            or os.getenv("LLM_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        if not key:
            missing.append("IMAGE_API_KEY oder LLM_API_KEY" if image else "LLM_API_KEY")
        if not model:
            missing.append("IMAGE_MODEL" if image else "LLM_MODEL")
        if missing:
            return {
                "status": "not_configured",
                "validated": False,
                "requirements": missing,
                "message": "Zugangsdaten/Modell fehlen. Keine Anbieteranfrage ausgeführt.",
            }
        p = urlsplit(base)
        if (
            p.scheme != "https"
            or not p.hostname
            or p.username
            or p.password
            or p.query
            or p.fragment
        ):
            raise ProviderError("invalid_provider_configuration")
        data, _ = request_json(
            "GET",
            base + "/models/" + quote(model, safe=""),
            headers={"Authorization": "Bearer " + key},
        )
        if data.get("id") != model:
            raise ProviderError("model_not_verified")
        return {
            "status": "validated",
            "validated": True,
            "message": "Modell-Metadaten erreichbar. Kein kostenpflichtiger Generierungsaufruf ausgeführt; die konkrete Generierungsberechtigung ist separat zu prüfen.",
        }
    if provider == "stripe":
        key = os.getenv("STRIPE_SECRET_KEY")
        if not key:
            return {
                "status": "not_configured",
                "validated": False,
                "requirements": ["STRIPE_SECRET_KEY", "STRIPE_PRICE_ID", "STRIPE_WEBHOOK_SECRET"],
                "message": "Stripe-Testzugang fehlt.",
            }
        data, _ = request_json(
            "GET", "https://api.stripe.com/v1/balance", headers={"Authorization": "Bearer " + key}
        )
        if data.get("livemode") is not False:
            raise ProviderError("test_mode_required")
        return {
            "status": "validated",
            "validated": True,
            "message": "Stripe-Testmodus bestätigt. Keine Zahlung oder Subscription angelegt.",
        }
    if provider == "discovery":
        missing = [name for name in ("PDL_API_KEY", "PDL_LICENSE_REFERENCE") if not os.getenv(name)]
        if os.getenv("PDL_LICENSE_APPROVED") != "true":
            missing.append("PDL_LICENSE_APPROVED")
        return {
            "status": "not_configured" if missing else "requires_search",
            "validated": False,
            "requirements": missing,
            "message": "Lizenzanbieter benötigt eine explizite Suche zur fachlichen Prüfung. Es wird kein möglicherweise kostenpflichtiger Test versteckt ausgeführt.",
        }
    if provider == "email":
        missing = [name for name in ("RESEND_API_KEY", "EMAIL_FROM") if not os.getenv(name)]
        return {
            "status": "not_configured" if missing else "requires_domain_review",
            "validated": False,
            "requirements": missing,
            "message": "Absenderdomain und Vertragszugang beim E-Mail-Anbieter prüfen. Es wird keine Testwerbung versendet.",
        }
    raise HTTPException(404, "Unknown provider.")


def register_provider_tests(app, db_session, scope, audit):
    @app.post("/v1/workspaces/{ws}/providers/{provider}/test")
    def check(
        ws: str, provider: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        from cryptography.fernet import InvalidToken

        from app.providers.ai import ProviderError

        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Owner/admin required.")
        try:
            result = provider_test(provider, db, ws)
        except ProviderError as exc:
            result = {
                "status": "unavailable",
                "validated": False,
                "code": exc.code,
                "message": "Anbieterprüfung fehlgeschlagen: " + exc.code,
            }
        except InvalidToken:
            result = {
                "status": "unavailable",
                "validated": False,
                "code": "reconnect_required",
                "message": "Gespeicherte Zugangsdaten nicht entschlüsselbar; Konto erneut verbinden.",
            }
        audit(
            db,
            ws,
            member.user_id,
            "provider_check",
            f"Provider {provider[:40]}: {result['status']}",
        )
        return result | {
            "checked_at": now(),
            "notice": "Nur der ausgewiesene Prüfumfang ist bestätigt. Keine Sende- oder Veröffentlichungsfreigabe.",
        }
