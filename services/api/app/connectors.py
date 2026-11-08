"""M9: connections to external outreach tools, at the user's own risk.

Boundary (unchanged, see AGENTS.md): ProspectOS itself never automates LinkedIn. It does
not touch LinkedIn sessions or cookies, does not emulate, proxy or scrape. This module
only calls the official APIs of third-party tools where the user has their own account;
those tools do the automation, and the user accepts that risk explicitly.

- Product switch ``EXTERNAL_OUTREACH_TOOLS_ENABLED`` (default false) hides the feature.
- Per workspace off by default; only the owner turns it on after confirming the exact
  risk text. Name, time and text of the confirmation go to the audit log.
- Keys are stored encrypted (TOKEN_ENCRYPTION_KEY). Each tool gets its own inbound
  webhook URL ``/v1/hooks/<workspace>/<secret>``; only a hash of the secret is stored.
- Before every handoff (and again at dispatch): objection, suppression, verified LinkedIn
  URL, no other active route, tool active. Only name, company, role and LinkedIn URL are
  sent; e-mail only with a documented e-mail legal basis.
- Inbound events (accepted, replied, message sent) feed the M3 logic: a reply stops every
  step on every channel. A reaction elsewhere pauses the contact in the tool, or creates
  a task "In <Tool> stoppen" when the tool's API cannot pause.
"""

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app import credentials
from app.db import Base, SessionLocal, now
from app.models import Company, Contact, TenantMixin
from app.providers.ai import ProviderError
from app.providers.outreach_tools import ADAPTERS, Lead, normalize_linkedin

ACKNOWLEDGMENT = (
    "Diese Tools automatisieren LinkedIn über dein Konto. Das verstößt gegen die "
    "LinkedIn-Nutzervereinbarung und kann zur Einschränkung oder Sperre deines Accounts "
    "führen. Du nutzt sie auf eigene Gefahr."
)
ACTIVE_STATES = ("queued", "handed_over")
SIGNATURE_MAX_AGE = 300


def product_enabled() -> bool:
    return os.getenv("EXTERNAL_OUTREACH_TOOLS_ENABLED", "false").lower() == "true"


class ConnectorSettings(TenantMixin, Base):
    __tablename__ = "connector_settings"
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(36))
    acknowledged_name: Mapped[str] = mapped_column(String(200), default="")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledgment_text: Mapped[str] = mapped_column(String(1000), default="")
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "acknowledged_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class OutreachConnector(TenantMixin, Base):
    __tablename__ = "outreach_connectors"
    tool: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    secrets_ciphertext: Mapped[str] = mapped_column(String(6000), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    inbound_secret_hash: Mapped[str] = mapped_column(String(64), default="")
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_error: Mapped[str] = mapped_column(String(200), default="")
    __table_args__ = (
        UniqueConstraint("workspace_id", "tool"),
        UniqueConstraint("workspace_id", "id"),
    )


class Handoff(TenantMixin, Base):
    __tablename__ = "connector_handoffs"
    contact_id: Mapped[str] = mapped_column(String(36))
    tool: Mapped[str] = mapped_column(String(20))
    target: Mapped[str] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(String(20), default="queued")
    linkedin_url: Mapped[str] = mapped_column(String(500))
    external_ref: Mapped[str | None] = mapped_column(String(300))
    tool_contact_id: Mapped[str | None] = mapped_column(String(100))
    task_id: Mapped[str | None] = mapped_column(String(36))
    actor_id: Mapped[str | None] = mapped_column(String(36))
    last_event: Mapped[str] = mapped_column(String(30), default="")
    error: Mapped[str] = mapped_column(String(200), default="")
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        Index(
            "connector_one_active_handoff",
            "workspace_id",
            "contact_id",
            unique=True,
            postgresql_where=text("state IN ('queued', 'handed_over')"),
        ),
    )


class ConnectorEvent(TenantMixin, Base):
    __tablename__ = "connector_events"
    tool: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(20))
    contact_id: Mapped[str | None] = mapped_column(String(36))
    handoff_id: Mapped[str | None] = mapped_column(String(36))
    owner_id: Mapped[str | None] = mapped_column(String(36))
    event_id: Mapped[str | None] = mapped_column(String(200))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        Index(
            "connector_event_dedup",
            "workspace_id",
            "tool",
            "event_id",
            unique=True,
            postgresql_where=text("event_id IS NOT NULL"),
        ),
    )


class EnableInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    confirmation_text: str = Field(max_length=1000)


class ConnectorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secrets: dict[str, str] = Field(default_factory=dict)
    config: dict[str, str] = Field(default_factory=dict)
    active: bool = True


class HandoffInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    target: str = Field(min_length=1, max_length=500)


def settings_of(db, ws) -> ConnectorSettings | None:
    return db.scalar(select(ConnectorSettings).where(ConnectorSettings.workspace_id == ws))


def feature_on(db, ws) -> bool:
    s = settings_of(db, ws)
    return product_enabled() and bool(s and s.enabled)


def connector_of(db, ws, tool) -> OutreachConnector | None:
    return db.scalar(
        select(OutreachConnector).where(
            OutreachConnector.workspace_id == ws, OutreachConnector.tool == tool
        )
    )


def secrets_of(row: OutreachConnector) -> dict:
    if not row or not row.secrets_ciphertext:
        return {}
    try:
        return json.loads(credentials.cipher().decrypt(row.secrets_ciphertext.encode()).decode())
    except Exception:
        return {}


def cfg_of(row: OutreachConnector) -> dict:
    return {**(row.config or {}), **secrets_of(row)}


def active_handoff(db, ws, contact_id) -> Handoff | None:
    return db.scalar(
        select(Handoff).where(
            Handoff.workspace_id == ws,
            Handoff.contact_id == contact_id,
            Handoff.state.in_(ACTIVE_STATES),
        )
    )


def blockers(
    db, ws, contact: Contact, tool: str, *, allow_existing: Handoff | None = None
) -> list[str]:
    """Every reason not to hand this contact to the tool. Empty list = allowed."""
    from app.multichannel import channel_permissions, suppression_of
    from app.today import QueueItem

    reasons = []
    if not feature_on(db, ws):
        reasons.append("Externe Tools sind in diesem Workspace nicht eingeschaltet.")
    row = connector_of(db, ws, tool)
    if tool not in ADAPTERS or row is None or not row.active:
        reasons.append("Dieses Tool ist nicht verbunden oder ausgeschaltet.")
    if suppression_of(db, ws, contact.id):
        reasons.append("Widerspruch: Kontakt ist gesperrt.")
    elif not channel_permissions(db, ws, contact)["linkedin"]["allowed"]:
        reasons.append("Kein geprüftes LinkedIn-Profil.")
    existing = active_handoff(db, ws, contact.id)
    if existing and existing is not allow_existing:
        reasons.append(f"Schon an {ADAPTERS[existing.tool].spec.label} übergeben.")
    if contact.channel_route == "letter":
        reasons.append("Aktiver Weg ist der Brief; erst auf LinkedIn oder Externes Tool umstellen.")
    if db.scalar(
        select(QueueItem.id).where(
            QueueItem.workspace_id == ws,
            QueueItem.contact_id == contact.id,
            QueueItem.state == "approved",
        )
    ):
        reasons.append("In Heute ist eine manuelle LinkedIn-Aufgabe freigegeben.")
    return reasons


def lead_for(db, ws, contact: Contact) -> Lead:
    from app.email_outreach import eligibility

    company = db.get(Company, contact.company_id) if contact.company_id else None
    return Lead(
        contact_id=contact.id,
        first_name=contact.first_name,
        last_name=contact.last_name,
        company=company.name if company else "",
        job_title=contact.job_title,
        linkedin_url=normalize_linkedin(contact.linkedin_url),
        email=contact.email if contact.email and eligibility(db, ws, contact)["allowed"] else None,
    )


def start_handoff(
    db, ws, contact: Contact, tool: str, target: str, actor_id, task_id=None
) -> Handoff:
    from app.jobs import enqueue

    problems = blockers(db, ws, contact, tool)
    if problems:
        raise HTTPException(409, " ".join(problems))
    item = Handoff(
        workspace_id=ws,
        contact_id=contact.id,
        tool=tool,
        target=target,
        state="queued",
        linkedin_url=normalize_linkedin(contact.linkedin_url),
        task_id=task_id,
        actor_id=actor_id,
    )
    db.add(item)
    db.flush()
    enqueue(
        db, ws, actor_id, "connector_push", {"handoff_id": item.id}, key="connector-push:" + item.id
    )
    return item


# ---- worker (prepare in a transaction, call outside, finalize) ------------------------------


def prepare_connector(db, job) -> dict:
    ws = job.workspace_id
    handoff = db.get(Handoff, job.payload["handoff_id"])
    if handoff is None or handoff.workspace_id != ws:
        raise HTTPException(404, "handoff_missing")
    row = connector_of(db, ws, handoff.tool)
    if job.kind == "connector_push":
        contact = db.get(Contact, handoff.contact_id)
        problems = (
            blockers(db, ws, contact, handoff.tool, allow_existing=handoff)
            if contact
            else ["Kontakt gelöscht."]
        )
        if problems:
            raise HTTPException(409, ("blocked: " + " ".join(problems))[:100])
        lead = lead_for(db, ws, contact)
        return {
            "tool": handoff.tool,
            "cfg": cfg_of(row),
            "target": handoff.target,
            "leads": [lead.__dict__],
            "handoff_id": handoff.id,
        }
    if not product_enabled() or row is None:
        raise HTTPException(409, "tool_not_available")
    return {
        "tool": handoff.tool,
        "cfg": cfg_of(row),
        "handoff": {
            "target": handoff.target,
            "linkedin_url": handoff.linkedin_url,
            "external_ref": handoff.external_ref,
            "tool_contact_id": handoff.tool_contact_id,
            "contact_id": handoff.contact_id,
        },
        "handoff_id": handoff.id,
    }


def send_connector(context, kind) -> dict:
    adapter = ADAPTERS[context["tool"]]
    if kind == "connector_push":
        return {
            "pushed": adapter.push_contacts(
                context["cfg"], context["target"], [Lead(**item) for item in context["leads"]]
            )
        }
    result = adapter.pause_contact(context["cfg"], context["handoff"])
    return {"paused": bool(result), "supported": result is not None}


def finalize_connector(db, job, result) -> dict:
    from app.flows import FlowTask, complete_task

    ws = job.workspace_id
    handoff = db.get(Handoff, job.payload["handoff_id"])
    label = ADAPTERS[handoff.tool].spec.label
    if job.kind == "connector_push":
        pushed = (result.get("pushed") or [{}])[0]
        handoff.state, handoff.external_ref = "handed_over", pushed.get("external_ref")
        contact = db.get(Contact, handoff.contact_id)
        contact.channel_route, contact.route_mode = "tool", "manual"
        contact.route_reason, contact.route_set_at = f"An {label} übergeben.", now()
        from app.multichannel import _stop_today_queue

        _stop_today_queue(db, ws, contact.id, f"An {label} übergeben")
        if handoff.task_id:
            task = db.get(FlowTask, handoff.task_id)
            if task and task.state == "pending_tool":
                task.state = "open"
                complete_task(db, ws, task, job.actor_id, "done", f"An {label} übergeben")
        return result
    if result.get("supported"):
        handoff.state = "paused"
    else:
        handoff.state = "stopped"
        manual_stop_task(db, ws, handoff, label)
    return result


def fail_connector(db, job, code):
    from app.flows import FlowTask

    handoff = db.get(Handoff, job.payload.get("handoff_id"))
    if handoff is None:
        return
    label = ADAPTERS[handoff.tool].spec.label
    if job.kind == "connector_push":
        handoff.state = "ambiguous" if job.status == "ambiguous" else "failed"
        handoff.error = code[:200]
        if handoff.task_id:
            task = db.get(FlowTask, handoff.task_id)
            if task and task.state == "pending_tool":
                task.state, task.blocked_reason = (
                    "blocked",
                    f"Übergabe an {label} fehlgeschlagen: {code}"[:300],
                )
    elif job.status in ("failed", "ambiguous"):
        manual_stop_task(db, job.workspace_id, handoff, label)


def manual_stop_task(db, ws, handoff: Handoff, label: str):
    from app.flows import FlowTask

    contact = db.get(Contact, handoff.contact_id)
    db.add(
        FlowTask(
            workspace_id=ws,
            contact_id=handoff.contact_id,
            kind="tool_stop_task",
            title=f"In {label} stoppen",
            body=f"Kontakt in {label} von Hand pausieren: {handoff.linkedin_url}",
            state="open",
            assignee_id=contact.owner_id if contact else None,
            origin="connector",
        )
    )


def stop_in_tools(db, ws, contact_id, reason) -> int:
    """STOP_HOOK: a reaction elsewhere pauses the contact in the tool (or creates a task)."""
    from app.jobs import enqueue

    count = 0
    for handoff in db.scalars(
        select(Handoff).where(
            Handoff.workspace_id == ws,
            Handoff.contact_id == contact_id,
            Handoff.state.in_(ACTIVE_STATES),
        )
    ):
        handoff.state = "stopping"
        enqueue(
            db,
            ws,
            handoff.actor_id or _owner(db, ws),
            "connector_pause",
            {"handoff_id": handoff.id},
            key="connector-pause:" + handoff.id,
        )
        count += 1
    return count


def _owner(db, ws):
    from app.models import Membership

    return db.scalar(
        select(Membership.user_id)
        .where(Membership.workspace_id == ws, Membership.role == "owner")
        .limit(1)
    )


# ---- inbound events ---------------------------------------------------------------------


def apply_events(db, ws, tool: str, events: list[dict]) -> dict:
    from app.reactions import record_reaction

    counts = {"matched": 0, "ignored": 0, "duplicate": 0}
    for event in events:
        if event["kind"] == "other" or not (event.get("linkedin_url") or event.get("external_ref")):
            counts["ignored"] += 1
            continue
        if event.get("event_id") and db.scalar(
            select(ConnectorEvent.id).where(
                ConnectorEvent.workspace_id == ws,
                ConnectorEvent.tool == tool,
                ConnectorEvent.event_id == event["event_id"],
            )
        ):
            counts["duplicate"] += 1
            continue
        handoff = db.scalar(
            select(Handoff)
            .where(
                Handoff.workspace_id == ws,
                Handoff.tool == tool,
                (Handoff.linkedin_url == event.get("linkedin_url"))
                | (Handoff.external_ref == event.get("external_ref")),
            )
            .order_by(Handoff.created_at.desc())
            .limit(1)
        )
        contact = (
            db.get(Contact, handoff.contact_id)
            if handoff
            else _contact_by_url(db, ws, event.get("linkedin_url"))
        )
        if contact is None:
            counts["ignored"] += 1
            continue
        db.add(
            ConnectorEvent(
                workspace_id=ws,
                tool=tool,
                kind=event["kind"],
                contact_id=contact.id,
                handoff_id=handoff.id if handoff else None,
                owner_id=contact.owner_id,
                event_id=event.get("event_id"),
            )
        )
        if handoff:
            handoff.last_event = event["kind"]
            if event.get("tool_contact_id"):
                handoff.tool_contact_id = event["tool_contact_id"]
        label = ADAPTERS[tool].spec.label
        if event["kind"] == "accepted":
            record_reaction(
                db,
                ws,
                contact,
                "linkedin_accepted",
                f"über {label}",
                source_ref=f"{tool}:{event.get('event_id') or 'accepted'}",
            )
        elif event["kind"] == "replied":
            if handoff:
                handoff.state = "replied"  # the tool already stopped this lead; no pause needed
            record_reaction(
                db,
                ws,
                contact,
                "linkedin_replied",
                event.get("text") or f"Antwort über {label}",
                source_ref=f"{tool}:{event.get('event_id') or event.get('linkedin_url')}",
            )
        counts["matched"] += 1
    db.flush()
    return counts


def _contact_by_url(db, ws, url):
    if not url:
        return None
    for contact in db.scalars(
        select(Contact)
        .where(Contact.workspace_id == ws, Contact.linkedin_url.is_not(None))
        .limit(20000)
    ):
        if normalize_linkedin(contact.linkedin_url) == url:
            return contact
    return None


def tool_activity(db, ws, user_id, since) -> int:
    """Invitations a tool reported for this person's contacts (for the M5 pace view)."""
    return (
        db.scalar(
            select(func.count(ConnectorEvent.id)).where(
                ConnectorEvent.workspace_id == ws,
                ConnectorEvent.owner_id == user_id,
                ConnectorEvent.kind == "invite_sent",
                ConnectorEvent.created_at >= since,
            )
        )
        or 0
    )


def hook_secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def handoff_output(h: Handoff) -> dict:
    return {
        "id": h.id,
        "contact_id": h.contact_id,
        "tool": h.tool,
        "tool_label": ADAPTERS[h.tool].spec.label,
        "target": h.target,
        "state": h.state,
        "last_event": h.last_event,
        "error": h.error,
        "created_at": h.created_at,
    }


def register_connector_routes(app, db_session, scope, record, audit):
    from app.multichannel import STOP_HOOKS

    STOP_HOOKS["connectors"] = stop_in_tools

    def require_product():
        if not product_enabled():
            raise HTTPException(404, "Diese Funktion ist nicht freigeschaltet.")

    def owner(member):
        if member.role != "owner":
            raise HTTPException(403, "Nur der Owner verwaltet Anschlüsse.")

    def tool_output(db, ws, tool, adapter, public_base):
        row = connector_of(db, ws, tool)
        stored = secrets_of(row) if row else {}
        return {
            "id": tool,
            "label": adapter.spec.label,
            "docs": adapter.spec.docs,
            "price_hint": adapter.spec.price_hint,
            "can": adapter.spec.can,
            "cannot": adapter.spec.cannot,
            "secret_fields": list(adapter.spec.secret_fields),
            "config_fields": list(adapter.spec.config_fields),
            "configured": bool(row and stored),
            "secrets_masked": {k: credentials.mask(v, True) for k, v in stored.items()},
            "config": (row.config if row else {}) or {},
            "active": bool(row and row.active),
            "last_test_ok": row.last_test_ok if row else None,
            "last_test_at": row.last_test_at if row else None,
            "last_error": row.last_error if row else "",
            "webhook_ready": bool(row and row.inbound_secret_hash),
            "webhook_events": list(adapter.spec.webhook_events),
        }

    @app.get("/v1/workspaces/{ws}/connectors")
    def overview(
        ws: str, request: Request, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if not product_enabled():
            return {
                "available": False,
                "notice": "Externe Outreach-Tools sind in dieser Installation ausgeblendet.",
            }
        s = settings_of(db, ws)
        base = os.getenv("PUBLIC_WEB_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
        return {
            "available": True,
            "enabled": bool(s and s.enabled),
            "acknowledgment": ACKNOWLEDGMENT,
            "acknowledged": {
                "name": s.acknowledged_name,
                "at": s.acknowledged_at,
                "text": s.acknowledgment_text,
            }
            if s and s.acknowledged_at
            else None,
            "tools": [tool_output(db, ws, tool, a, base) for tool, a in ADAPTERS.items()],
            "handoffs": {
                state: count
                for state, count in db.execute(
                    select(Handoff.state, func.count())
                    .where(Handoff.workspace_id == ws)
                    .group_by(Handoff.state)
                )
            },
            "is_owner": member.role == "owner",
        }

    @app.post("/v1/workspaces/{ws}/connectors/enable")
    def enable(
        ws: str, body: EnableInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        from app.models import User

        require_product()
        owner(member)
        if not body.accepted or body.confirmation_text.strip() != ACKNOWLEDGMENT:
            raise HTTPException(422, "Bitte den Hinweis vollständig bestätigen.")
        s = settings_of(db, ws) or ConnectorSettings(workspace_id=ws)
        db.add(s)
        user = db.get(User, member.user_id)
        s.enabled, s.acknowledged_by, s.acknowledged_at = True, member.user_id, now()
        s.acknowledged_name, s.acknowledgment_text, s.disabled_at = (
            (user.name or user.email)[:200],
            ACKNOWLEDGMENT,
            None,
        )
        audit(
            db,
            ws,
            member.user_id,
            "external_tools_enabled",
            f"Externe Outreach-Tools eingeschaltet von {s.acknowledged_name} am {s.acknowledged_at:%d.%m.%Y %H:%M} UTC. Bestätigt: {ACKNOWLEDGMENT}"[
                :1000
            ],
        )
        db.flush()
        return {"enabled": True}

    @app.post("/v1/workspaces/{ws}/connectors/disable")
    def disable(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        require_product()
        owner(member)
        s = settings_of(db, ws)
        if s:
            s.enabled, s.disabled_at = False, now()
        audit(
            db,
            ws,
            member.user_id,
            "external_tools_disabled",
            "Externe Outreach-Tools ausgeschaltet",
        )
        return {
            "enabled": False,
            "notice": "Neue Übergaben sind gesperrt. Bereits übergebene Kontakte bitte im Tool selbst stoppen.",
        }

    @app.put("/v1/workspaces/{ws}/connectors/{tool}")
    def save(
        ws: str,
        tool: str,
        body: ConnectorInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        require_product()
        owner(member)
        if not feature_on(db, ws):
            raise HTTPException(409, "Zuerst Anschlüsse einschalten und den Hinweis bestätigen.")
        adapter = ADAPTERS.get(tool)
        if adapter is None:
            raise HTTPException(404, "Unbekanntes Tool.")
        if set(body.secrets) - set(adapter.spec.secret_fields) or set(body.config) - set(
            adapter.spec.config_fields
        ):
            raise HTTPException(422, "Unbekannte Felder für dieses Tool.")
        if not credentials.encryption_ready():
            raise HTTPException(
                503, "TOKEN_ENCRYPTION_KEY fehlt; Schlüssel können nicht sicher gespeichert werden."
            )
        row = connector_of(db, ws, tool) or OutreachConnector(workspace_id=ws, tool=tool, config={})
        db.add(row)
        merged = {**secrets_of(row), **{k: v.strip() for k, v in body.secrets.items() if v.strip()}}
        row.secrets_ciphertext = credentials.encrypt(merged) if merged else ""
        row.config = {**(row.config or {}), **{k: v.strip() for k, v in body.config.items()}}
        row.active = body.active
        new_secret = None
        if not row.inbound_secret_hash:
            new_secret = secrets.token_urlsafe(24)
            row.inbound_secret_hash = hook_secret_hash(new_secret)
        db.flush()
        audit(
            db, ws, member.user_id, "connector_saved", f"Anschluss {adapter.spec.label} gespeichert"
        )
        out = tool_output(db, ws, tool, adapter, "")
        if new_secret:
            out["webhook_path"] = f"/v1/hooks/{ws}/{new_secret}"
        return out

    @app.post("/v1/workspaces/{ws}/connectors/{tool}/rotate-webhook")
    def rotate(ws: str, tool: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        require_product()
        owner(member)
        row = connector_of(db, ws, tool)
        if row is None:
            raise HTTPException(404, "Anschluss nicht gefunden.")
        secret = secrets.token_urlsafe(24)
        row.inbound_secret_hash = hook_secret_hash(secret)
        return {
            "webhook_path": f"/v1/hooks/{ws}/{secret}",
            "notice": "Die alte Webhook-Adresse funktioniert nicht mehr.",
        }

    @app.post("/v1/workspaces/{ws}/connectors/{tool}/test")
    def test(ws: str, tool: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        require_product()
        owner(member)
        row = connector_of(db, ws, tool)
        if row is None:
            raise HTTPException(404, "Anschluss nicht gefunden.")
        try:
            result = ADAPTERS[tool].test(cfg_of(row))
            row.last_test_ok, row.last_error = True, ""
        except (ProviderError, KeyError) as exc:
            result = {"ok": False}
            row.last_test_ok, row.last_error = False, getattr(exc, "code", "missing_credentials")
        row.last_test_at = now()
        return result | {"error": row.last_error}

    @app.get("/v1/workspaces/{ws}/connectors/{tool}/campaigns")
    def campaigns(
        ws: str, tool: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        require_product()
        row = connector_of(db, ws, tool)
        if row is None or not feature_on(db, ws):
            raise HTTPException(404, "Anschluss nicht gefunden.")
        try:
            items = ADAPTERS[tool].campaigns(cfg_of(row))
        except ProviderError as exc:
            raise HTTPException(502, f"Tool antwortet nicht: {exc.code}") from None
        return {"items": items, "supported": items is not None}

    @app.post("/v1/workspaces/{ws}/contacts/{entity_id}/handoff", status_code=202)
    def handoff(
        ws: str,
        entity_id: str,
        body: HandoffInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")
        require_product()
        contact = record(db, Contact, ws, entity_id, True)
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k,0))"),
            {"k": "handoff:" + contact.id},
        )
        item = start_handoff(db, ws, contact, body.tool, body.target, member.user_id)
        audit(
            db,
            ws,
            member.user_id,
            "contact_handoff",
            f"Kontakt an {ADAPTERS[body.tool].spec.label} übergeben (eigene Gefahr)",
        )
        return handoff_output(item)

    @app.get("/v1/workspaces/{ws}/handoffs")
    def handoffs(
        ws: str,
        contact_id: str | None = None,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        stmt = select(Handoff).where(Handoff.workspace_id == ws)
        if contact_id:
            stmt = stmt.where(Handoff.contact_id == contact_id)
        return {
            "items": [
                handoff_output(h)
                for h in db.scalars(stmt.order_by(Handoff.created_at.desc()).limit(200))
            ]
        }

    @app.post("/v1/hooks/{ws}/{secret}", include_in_schema=False)
    async def inbound(ws: str, secret: str, request: Request):
        raw = await request.body()
        if len(raw) > 256 * 1024 or not product_enabled():
            raise HTTPException(404, "Nicht gefunden.")
        try:
            body = json.loads(raw or b"{}")
        except ValueError:
            raise HTTPException(400, "Ungültiges JSON.") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "Ungültiges JSON.")
        digest = hook_secret_hash(secret)
        with SessionLocal() as db, db.begin():
            db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})
            rows = db.scalars(
                select(OutreachConnector).where(OutreachConnector.workspace_id == ws)
            ).all()
            row = next(
                (
                    r
                    for r in rows
                    if r.inbound_secret_hash and hmac.compare_digest(r.inbound_secret_hash, digest)
                ),
                None,
            )
            if row is None or not feature_on(db, ws) or not row.active:
                raise HTTPException(404, "Nicht gefunden.")
            cfg = cfg_of(row)
            if row.tool == "webhook":
                # Our own generic webhook always signs: HMAC over timestamp + body, max 5 min old.
                from app.providers.outreach_tools import sign

                stamp = request.headers.get("x-prospectos-timestamp", "")
                given = request.headers.get("x-prospectos-signature", "")
                fresh = stamp.isdigit() and abs(now().timestamp() - int(stamp)) <= SIGNATURE_MAX_AGE
                expected = sign(cfg.get("signing_secret", ""), raw, stamp)
                if not (
                    cfg.get("signing_secret") and fresh and hmac.compare_digest(expected, given)
                ):
                    raise HTTPException(401, "Signatur ungültig oder abgelaufen.")
            events = ADAPTERS[row.tool].parse_webhook(body)
            return apply_events(db, ws, row.tool, events)
