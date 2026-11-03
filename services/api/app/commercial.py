"""Explicit email policy gates and Stripe test-mode event handling."""

import os

from fastapi import Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db import now
from app.entitlements import limits
from app.jobs import enqueue, tenant
from app.models import Contact, Draft, Membership, Workspace
from app.platform_models import BillingAccount, Consent, Suppression, WebhookEvent
from app.schemas import Strict


class DraftEdit(Strict):
    content: str = Field(min_length=1, max_length=3000)
    subject: str = Field(min_length=1, max_length=200)
    revision: int = Field(ge=1)


class SourceReview(Strict):
    approved: bool


def email_context(db, ws, draft, actor):
    membership = db.get(Membership, (ws, actor))
    if not membership or membership.role not in ("owner", "admin"):
        raise HTTPException(403, "Owner/admin authorization required.")
    if (
        os.getenv("EMAIL_SEND_ENABLED") != "true"
        or not os.getenv("RESEND_API_KEY")
        or not os.getenv("EMAIL_FROM")
    ):
        raise HTTPException(503, "Email provider is disabled or not configured.")
    contact = db.scalar(
        select(Contact)
        .where(Contact.workspace_id == ws, Contact.id == draft.contact_id)
        .with_for_update()
    )
    if not contact or not contact.email or not contact.source_reviewed:
        raise HTTPException(
            409, "Recipient/source provenance must be reviewed before marketing outreach."
        )
    if db.scalar(
        select(Suppression.id).where(
            Suppression.workspace_id == ws, Suppression.contact_id == contact.id
        )
    ):
        raise HTTPException(409, "Recipient is suppressed.")
    consent = db.scalar(
        select(Consent)
        .where(
            Consent.workspace_id == ws,
            Consent.contact_id == contact.id,
            Consent.channel == "email",
            Consent.revoked.is_(False),
            Consent.expires_at > now(),
        )
        .limit(1)
    )
    if not consent:
        raise HTTPException(409, "Documented valid marketing basis is missing.")
    if (
        draft.approved_revision != draft.revision
        or not draft.subject
        or draft.state not in ("approved", "queued")
    ):
        raise HTTPException(409, "Current email revision requires explicit approval.")
    return {"recipient": contact.email, "subject": draft.subject, "text": draft.content}


def prepare_email(db, job):
    draft = db.scalar(
        select(Draft)
        .where(Draft.workspace_id == job.workspace_id, Draft.id == job.payload["draft_id"])
        .with_for_update()
    )
    if not draft or draft.revision != job.payload["revision"]:
        raise HTTPException(409, "Draft changed after authorization.")
    result = email_context(db, job.workspace_id, draft, job.actor_id)
    draft.state = "sending"
    return result


def send_authorized_email(context, job_id):
    from app.providers.email import send_email

    return send_email(**context, idempotency_key=job_id, policy_authorized=True)


def register_commercial_routes(app, db_session, scope, record, audit):
    def admin(member):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Owner/admin required.")

    @app.patch("/v1/workspaces/{ws}/outreach/drafts/{entity_id}")
    def edit(
        ws: str,
        entity_id: str,
        body: DraftEdit,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")
        draft = record(db, Draft, ws, entity_id, True)
        if draft.state == "sending" or draft.revision != body.revision:
            raise HTTPException(409, "Draft is stale or in-flight.")
        draft.content = body.content
        draft.subject = body.subject
        draft.revision += 1
        draft.approved_revision = None
        draft.state = "draft"
        audit(db, ws, member.user_id, "outreach_edited", "Message changed; approval invalidated")
        return {"id": draft.id, "revision": draft.revision, "state": draft.state}

    @app.post("/v1/workspaces/{ws}/outreach/drafts/{entity_id}/approve")
    def approve(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if member.role not in ("owner", "admin", "approver"):
            raise HTTPException(403, "Approval role required.")
        draft = record(db, Draft, ws, entity_id, True)
        if draft.state != "draft" or not draft.subject:
            raise HTTPException(409, "Email needs a subject and draft state.")
        draft.approved_revision = draft.revision
        draft.state = "approved"
        audit(
            db,
            ws,
            member.user_id,
            "outreach_approved",
            f"Message revision {draft.revision} approved; nothing sent",
        )
        return {"id": draft.id, "revision": draft.revision, "state": draft.state}

    @app.post("/v1/workspaces/{ws}/contacts/{entity_id}/source-review")
    def source_review(
        ws: str,
        entity_id: str,
        body: SourceReview,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        admin(member)
        contact = record(db, Contact, ws, entity_id, True)
        contact.source_reviewed = body.approved
        contact.version += 1
        audit(
            db,
            ws,
            member.user_id,
            "source_reviewed",
            "Source rights manually reviewed; this is not marketing consent",
        )
        return {"id": contact.id, "source_reviewed": contact.source_reviewed}

    @app.post("/v1/workspaces/{ws}/outreach/drafts/{entity_id}/send-email", status_code=202)
    def send(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        from app.platform_routes import job_output

        draft = record(db, Draft, ws, entity_id, True)
        email_context(db, ws, draft, member.user_id)
        job = enqueue(
            db,
            ws,
            member.user_id,
            "email",
            {"draft_id": draft.id, "revision": draft.revision},
            f"email:{draft.id}:{draft.revision}",
        )
        draft.state = "queued"
        audit(
            db,
            ws,
            member.user_id,
            "email_authorized",
            "Consent/source/suppression/approval checked; delivery not confirmed",
        )
        return job_output(job)

    @app.get("/v1/workspaces/{ws}/billing")
    def billing(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        item = db.scalar(select(BillingAccount).where(BillingAccount.workspace_id == ws))
        configured = bool(os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_PRICE_ID"))
        return {
            "status": item.status if item else "trial",
            "plan": item.plan if item else "trial",
            "test_mode": True,
            "configured": configured,
            "entitlements": limits(db, ws),
            "notice": "Test billing only. No production charges.",
        }

    @app.post("/v1/workspaces/{ws}/billing/checkout")
    def checkout(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        from app.providers.billing import create_checkout

        admin(member)
        item = db.scalar(select(BillingAccount).where(BillingAccount.workspace_id == ws))
        return create_checkout(ws, customer_id=item.customer_id if item else None)

    @app.post("/v1/workspaces/{ws}/billing/portal")
    def portal(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        from app.providers.billing import create_portal_session

        admin(member)
        item = db.scalar(select(BillingAccount).where(BillingAccount.workspace_id == ws))
        if not item or not item.customer_id:
            raise HTTPException(409, "No test subscription customer exists.")
        return create_portal_session(item.customer_id)

    @app.post("/v1/webhooks/stripe")
    async def webhook(request: Request, db=Depends(db_session, scope="function")):
        from app.providers.billing import verify_webhook

        event = verify_webhook(await request.body(), request.headers.get("Stripe-Signature", ""))
        claimed = db.scalar(
            insert(WebhookEvent)
            .values(id=event["id"], provider="stripe", processed_at=now())
            .on_conflict_do_nothing()
            .returning(WebhookEvent.id)
        )
        if not claimed:
            return {"received": True, "duplicate": True}
        obj = event["data"]["object"]
        kind = event["type"]
        if kind not in (
            "checkout.session.completed",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ):
            return {"received": True, "ignored": True}
        ws = obj.get("metadata", {}).get("workspace_id")
        if not isinstance(ws, str) or not db.get(Workspace, ws):
            raise HTTPException(400, "Unknown billing workspace.")
        tenant(db, ws)
        item = db.scalar(
            select(BillingAccount).where(BillingAccount.workspace_id == ws).with_for_update()
        )
        customer = obj.get("customer")
        if not isinstance(customer, str) or not customer.startswith("cus_"):
            raise HTTPException(400, "Invalid customer.")
        if not item:
            item = BillingAccount(workspace_id=ws, customer_id=customer)
            db.add(item)
        elif item.customer_id and item.customer_id != customer:
            raise HTTPException(400, "Billing customer mismatch.")
        if kind == "checkout.session.completed":
            # Checkout alone is not subscription entitlement proof.
            item.customer_id = customer
            item.subscription_id = obj.get("subscription")
            item.status = "pending"
        else:
            if item.subscription_id and item.subscription_id != obj.get("id"):
                raise HTTPException(400, "Subscription mismatch.")
            item.subscription_id = obj.get("id")
            item.status = "cancelled" if kind.endswith(".deleted") else obj.get("status", "unknown")
            item.plan = "test_subscription" if item.status in ("active", "trialing") else "trial"
        return {"received": True, "duplicate": False}
