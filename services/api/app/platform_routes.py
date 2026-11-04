"""Additive vertical workflows; original endpoints and contracts remain compatible."""

import os
from pathlib import Path

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from app import credentials
from app.db import now
from app.jobs import enqueue, reserve_ai, settle_ai, usage_account
from app.media import MAX_BYTES, private_path, store_image
from app.models import Contact, Draft, ImportJob
from app.platform_models import (
    Asset,
    Brand,
    Campaign,
    Consent,
    Enrollment,
    Job,
    Note,
    Suppression,
    Task,
)
from app.platform_schemas import (
    BrandInput,
    Budget,
    CampaignInput,
    CampaignPatch,
    ConsentInput,
    Generation,
    NoteInput,
    ResearchInput,
    SearchInput,
    SuppressInput,
    TaskInput,
    TaskPatch,
)


def job_output(job):
    return {
        k: getattr(job, k)
        for k in (
            "id",
            "kind",
            "status",
            "attempts",
            "max_attempts",
            "last_error",
            "created_at",
            "result",
        )
    }


def asset_output(asset):
    return {
        k: getattr(asset, k)
        for k in (
            "id",
            "filename",
            "content_type",
            "size",
            "alt_text",
            "created_at",
            "title",
            "description",
            "tags",
            "rights_note",
            "uploaded_by",
        )
    } | {"url": f"/v1/workspaces/{asset.workspace_id}/assets/{asset.id}/content"}


def register_platform_routes(app, db_session, scope, record, paginate, audit):
    def admin(member):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Owner or admin required.")

    def listing(db, model, ws, page, limit, output):
        rows, total = paginate(
            db,
            select(model).where(model.workspace_id == ws).order_by(model.created_at.desc()),
            page,
            limit,
        )
        return {
            "items": [output(row) for row in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @app.get("/v1/workspaces/{ws}/brands")
    def brands(
        ws: str,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        return listing(
            db,
            Brand,
            ws,
            page,
            limit,
            lambda r: {
                k: getattr(r, k)
                for k in ("id", "name", "voice", "audience", "pillars", "primary_color")
            },
        )

    @app.post("/v1/workspaces/{ws}/brands", status_code=201)
    def create_brand(
        ws: str, body: BrandInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        item = Brand(workspace_id=ws, **body.model_dump())
        db.add(item)
        db.flush()
        audit(db, ws, member.user_id, "brand_created", "Markenprofil erstellt")
        return {"id": item.id, **body.model_dump()}

    @app.put("/v1/workspaces/{ws}/brands/{entity_id}")
    def update_brand(
        ws: str,
        entity_id: str,
        body: BrandInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        item = record(db, Brand, ws, entity_id, True)
        for key, value in body.model_dump().items():
            setattr(item, key, value)
        audit(db, ws, member.user_id, "brand_updated", "Markenprofil aktualisiert")
        return {"id": item.id, **body.model_dump()}

    @app.get("/v1/workspaces/{ws}/assets")
    def assets(
        ws: str,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from sqlalchemy import exists

        from app.experience import AssetOrigin

        statement = (
            select(Asset)
            .where(
                Asset.workspace_id == ws,
                ~exists().where(
                    AssetOrigin.workspace_id == ws,
                    AssetOrigin.asset_id == Asset.id,
                    AssetOrigin.reviewed.is_(False),
                ),
            )
            .order_by(Asset.created_at.desc())
        )
        rows, total = paginate(db, statement, page, limit)
        return {
            "items": [asset_output(a) for a in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @app.post("/v1/workspaces/{ws}/assets/upload", status_code=201)
    def upload(
        ws: str,
        file: UploadFile = File(...),
        alt_text: str = Form(...),
        rights_confirmed: bool = Form(False),
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if not rights_confirmed or not alt_text.strip() or len(alt_text) > 1000:
            raise HTTPException(
                422, "Bildrechte bestätigen und Alternativtext angeben (max. 1000 Zeichen)."
            )
        from app.entitlements import remaining

        remaining(db, ws, "assets")
        key, size, digest = store_image(file.file.read(MAX_BYTES + 1))
        try:
            item = Asset(
                workspace_id=ws,
                uploaded_by=member.user_id,
                filename=Path((file.filename or "image.jpg").replace("\\", "/")).name[:200]
                or "image.jpg",
                storage_key=key,
                content_type="image/jpeg",
                size=size,
                sha256=digest,
                alt_text=alt_text.strip(),
                rights_confirmed=True,
            )
            db.add(item)
            db.flush()
        except Exception:
            private_path(key).unlink(missing_ok=True)
            raise
        audit(
            db,
            ws,
            member.user_id,
            "asset_uploaded",
            "Privates Bild geprüft und gespeichert; Metadaten entfernt",
        )
        return asset_output(item)

    @app.get("/v1/workspaces/{ws}/assets/{entity_id}/content")
    def asset_content(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        item = record(db, Asset, ws, entity_id)
        return FileResponse(
            private_path(item.storage_key),
            media_type=item.content_type,
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/v1/workspaces/{ws}/tasks")
    def tasks(
        ws: str,
        page: int = 1,
        limit: int = 100,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        return listing(
            db,
            Task,
            ws,
            page,
            limit,
            lambda r: {k: getattr(r, k) for k in ("id", "title", "due_at", "state", "contact_id")},
        )

    @app.post("/v1/workspaces/{ws}/tasks", status_code=201)
    def create_task(
        ws: str, body: TaskInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if body.contact_id:
            record(db, Contact, ws, body.contact_id)
        item = Task(workspace_id=ws, **body.model_dump())
        db.add(item)
        db.flush()
        audit(db, ws, member.user_id, "task_created", "Aufgabe angelegt")
        return {"id": item.id, "state": item.state, **body.model_dump()}

    @app.patch("/v1/workspaces/{ws}/tasks/{entity_id}")
    def change_task(
        ws: str,
        entity_id: str,
        body: TaskPatch,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        item = record(db, Task, ws, entity_id, True)
        item.state = body.state
        audit(db, ws, member.user_id, "task_updated", "Aufgabenstatus aktualisiert")
        return {
            "id": item.id,
            "title": item.title,
            "contact_id": item.contact_id,
            "due_at": item.due_at,
            "state": item.state,
        }

    @app.get("/v1/workspaces/{ws}/notes")
    def notes(
        ws: str,
        page: int = 1,
        limit: int = 100,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        return listing(
            db,
            Note,
            ws,
            page,
            limit,
            lambda r: {k: getattr(r, k) for k in ("id", "body", "contact_id", "created_at")},
        )

    @app.post("/v1/workspaces/{ws}/notes", status_code=201)
    def create_note(
        ws: str, body: NoteInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if body.contact_id:
            record(db, Contact, ws, body.contact_id)
        item = Note(workspace_id=ws, actor_id=member.user_id, **body.model_dump())
        db.add(item)
        db.flush()
        audit(db, ws, member.user_id, "note_created", "Notiz angelegt")
        return {"id": item.id, "created_at": item.created_at, **body.model_dump()}

    def campaign_output(db, item):
        return {
            "id": item.id,
            "name": item.name,
            "goal": item.goal,
            "status": item.status,
            "contacts": db.scalar(
                select(func.count())
                .select_from(Enrollment)
                .where(Enrollment.campaign_id == item.id)
            ),
        }

    @app.get("/v1/workspaces/{ws}/campaigns")
    def campaigns(
        ws: str,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        return listing(db, Campaign, ws, page, limit, lambda r: campaign_output(db, r))

    @app.post("/v1/workspaces/{ws}/campaigns", status_code=201)
    def create_campaign(
        ws: str,
        body: CampaignInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        for contact_id in set(body.contact_ids):
            record(db, Contact, ws, contact_id)
        item = Campaign(workspace_id=ws, **body.model_dump(exclude={"contact_ids"}))
        db.add(item)
        db.flush()
        for contact_id in set(body.contact_ids):
            db.add(Enrollment(workspace_id=ws, campaign_id=item.id, contact_id=contact_id))
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "campaign_created",
            "Kampagne mit manuell ausgewählten Kontakten angelegt",
        )
        return campaign_output(db, item)

    @app.patch("/v1/workspaces/{ws}/campaigns/{entity_id}")
    def change_campaign(
        ws: str,
        entity_id: str,
        body: CampaignPatch,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        item = record(db, Campaign, ws, entity_id, True)
        item.status = body.status
        audit(
            db,
            ws,
            member.user_id,
            "campaign_updated",
            "Kampagnenstatus geändert; kein Versand ausgelöst",
        )
        return campaign_output(db, item)

    @app.post("/v1/workspaces/{ws}/campaigns/{entity_id}/drafts")
    def campaign_drafts(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        campaign = record(db, Campaign, ws, entity_id, True)
        if campaign.status in ("paused", "completed"):
            raise HTTPException(409, "Kampagne ist pausiert oder abgeschlossen.")
        contacts = db.scalars(
            select(Contact)
            .join(Enrollment, Enrollment.contact_id == Contact.id)
            .where(Enrollment.campaign_id == campaign.id)
        ).all()
        for contact in contacts:
            db.add(
                Draft(
                    workspace_id=ws,
                    contact_id=contact.id,
                    source="offline",
                    content=f"Hallo {contact.first_name},\n\n{campaign.goal}\n\n[Offline-Entwurf. Rechtliche Grundlage und Inhalt vor manuellem Kontakt prüfen.]",
                )
            )
        audit(
            db,
            ws,
            member.user_id,
            "campaign_drafts_generated",
            f"{len(contacts)} Offline-Entwürfe erstellt; nichts versendet",
        )
        return {"created": len(contacts), "notice": "Offline-Entwürfe; kein Versand."}

    @app.get("/v1/workspaces/{ws}/jobs")
    def jobs(
        ws: str,
        page: int = 1,
        limit: int = 25,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        return listing(db, Job, ws, page, limit, job_output)

    @app.get("/v1/workspaces/{ws}/jobs/{entity_id}")
    def job(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        return job_output(record(db, Job, ws, entity_id))

    @app.post("/v1/workspaces/{ws}/jobs/{entity_id}/retry")
    def retry(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        item = record(db, Job, ws, entity_id, True)
        if (
            item.kind in ("ai", "social_text", "social_image", "social_reply")
            or item.status != "failed"
            or item.side_effect_started
            or item.attempts >= item.max_attempts
        ):
            raise HTTPException(
                409,
                "Kein sicherer automatischer Retry möglich. Unklare externe Ergebnisse manuell abgleichen.",
            )
        item.status = "queued"
        item.available_at = now()
        item.last_error = None
        audit(db, ws, member.user_id, "job_retry", "Job bewusst erneut eingeplant")
        return job_output(item)

    @app.post("/v1/workspaces/{ws}/jobs/{entity_id}/cancel")
    def cancel(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        item = record(db, Job, ws, entity_id, True)
        if item.status not in ("queued", "retry"):
            raise HTTPException(
                409, "Laufende/externe Vorgänge können nicht sicher abgebrochen werden."
            )
        item.status = "cancelled"
        settle_ai(db, item)
        audit(db, ws, member.user_id, "job_cancelled", "Job abgebrochen")
        return job_output(item)

    @app.post("/v1/workspaces/{ws}/imports/{entity_id}/enqueue", status_code=202)
    def enqueue_import(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        item = record(db, ImportJob, ws, entity_id)
        if item.owner_id != member.user_id and member.role not in ("owner", "admin"):
            raise HTTPException(403, "Import gehört einem anderen Nutzer.")
        if item.status != "validated":
            raise HTTPException(409, "Import ist nicht zur Übernahme bereit.")
        return job_output(
            enqueue(db, ws, member.user_id, "import", {"import_id": item.id}, "import:" + item.id)
        )

    @app.post("/v1/workspaces/{ws}/discovery/search", status_code=202)
    def discovery_search(
        ws: str, body: SearchInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if (
            body.min_employees is not None
            and body.max_employees is not None
            and body.min_employees > body.max_employees
        ):
            raise HTTPException(422, "Invalid employee range.")
        if body.provider == "pdl" and (
            not body.license_confirmed
            or not os.getenv("PDL_API_KEY")
            or os.getenv("PDL_LICENSE_APPROVED") != "true"
        ):
            raise HTTPException(503, "Lizenzfreigabe und Anbieterzugang fehlen.")
        if body.provider == "synthetic" and os.getenv("APP_ENV", "development") not in (
            "development",
            "test",
        ):
            raise HTTPException(403, "Fixtures sind nur für Entwicklung verfügbar.")
        audit(db, ws, member.user_id, "discovery_queued", "Discovery zur Verarbeitung eingeplant")
        return job_output(enqueue(db, ws, member.user_id, "discovery", body.model_dump()))

    @app.post("/v1/workspaces/{ws}/ai/generate", status_code=202)
    def generate(
        ws: str, body: Generation, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if not credentials.get("LLM_API_KEY") or not credentials.get("LLM_MODEL"):
            raise HTTPException(
                503, "Kein LLM-Anbieter konfiguriert. Offline-Vorschläge bleiben separat verfügbar."
            )
        sources = []
        if body.contact_id:
            contact = record(db, Contact, ws, body.contact_id)
            sources = [
                {
                    "id": contact.id,
                    "text": f"Nutzereintrag (nicht extern verifiziert): {contact.first_name} {contact.last_name}; Rolle: {contact.job_title}; Ort: {contact.location}",
                }
            ]
        reservation = reserve_ai(db, ws, body.prompt + str(sources))
        payload = body.model_dump() | {"sources": sources, "reservation_minor": reservation}
        audit(
            db,
            ws,
            member.user_id,
            "ai_queued",
            "Quellengebundene Textgenerierung angefragt; keine Aktionen erlaubt",
        )
        return job_output(enqueue(db, ws, member.user_id, "ai", payload))

    @app.get("/v1/workspaces/{ws}/usage")
    def usage(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        from app.platform_models import UsageAccount

        item = db.scalar(select(UsageAccount).where(UsageAccount.workspace_id == ws))
        if not item:
            return {
                "ai_budget_minor": 500,
                "ai_spent_minor": 0,
                "ai_reserved_minor": 0,
                "period": now().strftime("%Y-%m"),
                "currency": "USD",
            }
        return {
            k: getattr(item, k)
            for k in ("ai_budget_minor", "ai_spent_minor", "ai_reserved_minor", "period")
        } | {
            "currency": "USD",
            "notice": "Konfigurierte Tokenpreise; geschätzte Kosten, keine Anbieterrechnung.",
        }

    @app.put("/v1/workspaces/{ws}/usage/budget")
    def set_budget(
        ws: str, body: Budget, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        admin(member)
        item = usage_account(db, ws)
        if body.ai_budget_minor < item.ai_spent_minor + item.ai_reserved_minor:
            raise HTTPException(409, "Budget unterschreitet laufende Nutzung.")
        item.ai_budget_minor = body.ai_budget_minor
        audit(db, ws, member.user_id, "budget_updated", "Workspace-KI-Budget geändert")
        return body

    @app.post("/v1/workspaces/{ws}/research", status_code=202)
    def research(
        ws: str,
        body: ResearchInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if not body.rights_confirmed:
            raise HTTPException(422, "Berechtigung zur Recherche und Quelle bestätigen.")
        return job_output(enqueue(db, ws, member.user_id, "research", body.model_dump()))

    @app.post("/v1/workspaces/{ws}/consents", status_code=201)
    def consent(
        ws: str, body: ConsentInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        admin(member)
        record(db, Contact, ws, body.contact_id)
        if body.expires_at <= now():
            raise HTTPException(422, "Nachweis ist bereits abgelaufen.")
        item = Consent(workspace_id=ws, **body.model_dump())
        db.add(item)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "consent_recorded",
            "Werbekontakt-Nachweis manuell dokumentiert; keine automatische Rechtsprüfung",
        )
        return {"id": item.id}

    @app.post("/v1/workspaces/{ws}/suppressions", status_code=201)
    def suppress(
        ws: str,
        body: SuppressInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        record(db, Contact, ws, body.contact_id)
        item = Suppression(workspace_id=ws, **body.model_dump())
        db.add(item)
        db.flush()
        audit(db, ws, member.user_id, "contact_suppressed", "Kontakt für Werbeversand gesperrt")
        return {"id": item.id}

    @app.post("/v1/workspaces/{ws}/privacy/delete-contact/{entity_id}")
    def privacy_delete(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        admin(member)
        result = delete_contact_data(db, ws, entity_id, member.user_id)
        audit(
            db,
            ws,
            member.user_id,
            "privacy_contact_deleted",
            "Contact and derived personal payloads removed; minimal audit retained",
        )
        return result

    @app.post("/v1/workspaces/{ws}/privacy/export")
    def export(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        admin(member)
        from app.experience import Interaction, WorkspaceSetup
        from app.journeys import (
            CampaignConfig,
            CampaignDraft,
            CampaignStep,
            CompanyFact,
            CompanyProfile,
            ICPProfile,
            LeadProfile,
            ManualActivity,
            SavedSearch,
            Segment,
        )
        from app.linkedin_channel import LinkedInAction, SimAccount
        from app.models import Company, Deal
        from app.sales_agent import DraftEvidence
        from app.studio import VoiceProfile

        tables = [
            Contact,
            Company,
            Deal,
            Brand,
            VoiceProfile,
            Asset,
            Campaign,
            Task,
            Note,
            Draft,
            Consent,
            Suppression,
            LeadProfile,
            Segment,
            SavedSearch,
            ICPProfile,
            CompanyProfile,
            CompanyFact,
            CampaignConfig,
            CampaignStep,
            CampaignDraft,
            ManualActivity,
            Interaction,
            WorkspaceSetup,
            DraftEvidence,
            SimAccount,
            LinkedInAction,
        ]
        result = {
            model.__tablename__: [
                {
                    column.name: getattr(row, column.name)
                    for column in model.__table__.columns
                    if column.name not in ("storage_key",)
                }
                for row in db.scalars(select(model).where(model.workspace_id == ws))
            ]
            for model in tables
        }
        audit(
            db,
            ws,
            member.user_id,
            "privacy_export",
            "Workspace-Export ohne Zugangsdaten angefordert",
        )
        return jsonable_encoder({"workspace_id": ws, "exported_at": now(), "data": result})


def delete_contact_data(db, ws, contact_id, actor):
    """Delete a subject and derived payloads atomically; retain minimal audit/job metadata."""
    from sqlalchemy import delete

    from app.models import Deal
    from app.platform_models import Consent, Suppression

    contact = db.scalar(
        select(Contact)
        .where(Contact.workspace_id == ws, Contact.id == contact_id)
        .with_for_update()
    )
    if not contact:
        raise HTTPException(404, "Contact not found.")
    drafts = list(db.scalars(select(Draft.id).where(Draft.contact_id == contact_id)))
    affected = []
    for job in db.scalars(select(Job).where(Job.workspace_id == ws).with_for_update()):
        if job.payload.get("contact_id") == contact_id or job.payload.get("draft_id") in drafts:
            if job.status == "running":
                raise HTTPException(409, "Wait for in-flight processing before deletion.")
            affected.append(job)
    for job in affected:
        if job.status in ("queued", "retry"):
            settle_ai(db, job)
            job.status = "cancelled"
        job.payload = {"redacted_for_privacy": True}
        job.result = {}
    for model in (Task, Note, Enrollment, Consent, Suppression, Draft):
        db.execute(delete(model).where(model.workspace_id == ws, model.contact_id == contact_id))
    for deal in db.scalars(select(Deal).where(Deal.contact_id == contact_id)):
        deal.contact_id = None
    for imported in db.scalars(select(ImportJob).where(ImportJob.workspace_id == ws)):
        rows = imported.data.get("rows", [])
        filtered = [
            r
            for r in rows
            if not (
                (contact.linkedin_url and r.get("linkedin_url") == contact.linkedin_url)
                or (contact.email and r.get("email") == contact.email)
            )
        ]
        if len(filtered) != len(rows):
            imported.data = {**imported.data, "rows": filtered, "total": len(filtered)}
            if imported.status == "validated":
                imported.status = "privacy_redacted"
    db.flush()
    db.delete(contact)
    return {
        "deleted": True,
        "notice": "Kontakt und abgeleitete Entwürfe/Notizen/Aufgaben gelöscht; verknüpfte Unternehmen und anonymisierte Audit-Metadaten bleiben erhalten.",
    }
