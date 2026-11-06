"""LinkedIn connection/DM workflow with three explicitly separated channels.

- ``simulator``: a local sandbox. Only synthetic accounts created here can be targeted;
  nothing leaves the server and every record is flagged ``simulated``. Outcomes come from
  each synthetic persona's configured behaviour, processed by the durable job queue.
- ``manual``: a handoff package (profile link + approved text) for a human to act on in
  LinkedIn themselves, followed by a self-reported, audited outcome.
- ``official``: LinkedIn offers no generally available API to send member connection
  requests or direct messages. Without an approved partner integration this channel is
  reported unavailable and every attempt is refused. No scraping, browser automation or
  unofficial endpoints exist in this codebase.

All channels enforce: approved current draft revision, suppression, campaign enrollment,
one action per draft, and conservative daily/weekly pacing limits.
"""

import os
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from pydantic import Field, field_validator, model_validator
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now
from app.jobs import enqueue
from app.journeys import CampaignDraft, CampaignStep, ManualActivity
from app.models import Company, Contact, Deal, Draft, TenantMixin
from app.platform_models import Campaign, Enrollment, Suppression, Task
from app.schemas import Strict

BEHAVIOURS = ("accepts_and_replies", "accepts_silent", "declines", "ignores")
CONNECTION_NOTE_LIMIT = 300
SIM_REPLY = (
    "[Simulierte Antwort eines synthetischen Kontos] Danke für die Nachricht – "
    "gerne können wir nächste Woche kurz sprechen."
)
OFFICIAL_REASON = (
    "LinkedIn stellt keine allgemein verfügbare API für Kontaktanfragen oder Direktnachrichten "
    "an Mitglieder bereit. Ohne genehmigte Partnerintegration ist dieser Kanal deaktiviert; "
    "verwende die manuelle Übergabe."
)
SIM_PERSONAS = [
    (
        "sim-anna-keller",
        "Anna Keller",
        "Geschäftsführerin",
        "Simulator Steuerbüro Keller",
        "accepts_and_replies",
    ),
    (
        "sim-jonas-brandt",
        "Jonas Brandt",
        "Office Manager",
        "Simulator Brandt Immobilien",
        "accepts_silent",
    ),
    ("sim-mira-sommer", "Mira Sommer", "Inhaberin", "Simulator Sommer Architektur", "declines"),
    (
        "sim-lukas-wolf",
        "Lukas Wolf",
        "Leiter Facility Management",
        "Simulator Wolf Logistik",
        "ignores",
    ),
    (
        "sim-eva-roth",
        "Eva Roth",
        "Head of Operations",
        "Simulator Roth IT-Service",
        "accepts_and_replies",
    ),
]


class SimAccount(TenantMixin, Base):
    __tablename__ = "linkedin_sim_accounts"
    handle: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(160))
    headline: Mapped[str] = mapped_column(String(240), default="")
    behaviour: Mapped[str] = mapped_column(String(40))
    contact_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("workspace_id", "handle"),
        UniqueConstraint("workspace_id", "contact_id"),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
    )


class LinkedInAction(TenantMixin, Base):
    __tablename__ = "linkedin_actions"
    contact_id: Mapped[str] = mapped_column(String(36))
    campaign_id: Mapped[str | None] = mapped_column(String(36))
    draft_id: Mapped[str | None] = mapped_column(String(36))
    draft_revision: Mapped[int | None]
    actor_id: Mapped[str] = mapped_column(String(36))
    channel: Mapped[str] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(String(3000), default="")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    history: Mapped[list] = mapped_column(JSON, default=list)
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "draft_id"],
            ["message_drafts.workspace_id", "message_drafts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        CheckConstraint("channel IN ('simulator', 'manual')", name="linkedin_action_channel"),
        CheckConstraint(
            "simulated = (channel = 'simulator')", name="linkedin_action_simulated_flag"
        ),
    )


class SimAccountInput(Strict):
    display_name: str = Field(min_length=2, max_length=120)
    headline: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    behaviour: str = "accepts_and_replies"

    @field_validator("behaviour")
    @classmethod
    def known(cls, value):
        if value not in BEHAVIOURS:
            raise ValueError("Unknown behaviour")
        return value


class ActionInput(Strict):
    contact_id: str
    channel: str
    action: str
    campaign_id: str | None = None
    draft_id: str | None = None

    @model_validator(mode="after")
    def valid(self):
        if self.channel not in ("simulator", "manual", "official"):
            raise ValueError("Unknown channel")
        if self.action not in ("connection_request", "message"):
            raise ValueError("Unknown action")
        if self.action == "message" and not self.draft_id:
            raise ValueError("A message requires an approved draft")
        return self


class OutcomeInput(Strict):
    outcome: str
    note: str = Field(default="", max_length=1000)

    @field_validator("outcome")
    @classmethod
    def known(cls, value):
        if value not in ("sent", "accepted", "declined", "replied", "not_sent"):
            raise ValueError("Unknown outcome")
        return value


def simulator_enabled() -> bool:
    default = "true" if os.getenv("APP_ENV", "development") in ("development", "test") else "false"
    return os.getenv("LINKEDIN_SIMULATOR_ENABLED", default).lower() == "true"


def _int_env(name, default, low, high):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(max(value, low), high)


def limits():
    return {
        "connection_requests_per_day": _int_env("LINKEDIN_DAILY_CONNECTION_LIMIT", 20, 1, 100),
        "connection_requests_per_week": _int_env("LINKEDIN_WEEKLY_CONNECTION_LIMIT", 80, 1, 200),
        "messages_per_day": _int_env("LINKEDIN_DAILY_MESSAGE_LIMIT", 40, 1, 150),
        "simulated_delay_seconds": _int_env("LINKEDIN_SIM_DELAY_SECONDS", 30, 0, 86400),
    }


def _log(item, state, by, note=""):
    item.state = state
    item.history = list(item.history or []) + [
        {"at": now().isoformat(), "state": state, "by": by, "note": note[:300]}
    ]


def action_output(item):
    return {
        k: getattr(item, k)
        for k in (
            "id",
            "contact_id",
            "campaign_id",
            "draft_id",
            "draft_revision",
            "channel",
            "action",
            "state",
            "content",
            "simulated",
            "resolved_at",
            "history",
            "created_at",
        )
    }


def usage(db, ws):
    day = now() - timedelta(days=1)
    week = now() - timedelta(days=7)
    counted = LinkedInAction.state.not_in(["not_sent", "cancelled"])

    def count(action, since):
        return db.scalar(
            select(func.count(LinkedInAction.id)).where(
                LinkedInAction.workspace_id == ws,
                LinkedInAction.action == action,
                LinkedInAction.created_at >= since,
                counted,
            )
        )

    return {
        "connection_requests_last_24h": count("connection_request", day),
        "connection_requests_last_7d": count("connection_request", week),
        "messages_last_24h": count("message", day),
    }


def connection_state(db, ws, contact_id):
    """Latest known connection state from simulator/manual actions or manual history."""
    latest = db.scalar(
        select(LinkedInAction)
        .where(
            LinkedInAction.workspace_id == ws,
            LinkedInAction.contact_id == contact_id,
            LinkedInAction.action == "connection_request",
            LinkedInAction.state.not_in(["not_sent", "cancelled"]),
        )
        .order_by(LinkedInAction.created_at.desc(), LinkedInAction.id.desc())
        .limit(1)
    )
    if latest is not None:
        return latest.state
    manual = db.scalar(
        select(ManualActivity.id).where(
            ManualActivity.workspace_id == ws,
            ManualActivity.contact_id == contact_id,
            ManualActivity.kind == "connected",
        )
    )
    return "accepted" if manual else "none"


def _crm_on_accept(db, contact):
    if contact.status in ("new", "qualified"):
        contact.status = "contacted"
        contact.version += 1


def _crm_on_reply(db, ws, contact, simulated):
    _crm_on_accept(db, contact)
    label = " (simuliert)" if simulated else ""
    db.add(
        Task(
            workspace_id=ws,
            contact_id=contact.id,
            title=f"Auf LinkedIn-Antwort reagieren: {contact.first_name} {contact.last_name}{label}"[
                :240
            ],
            due_at=now() + timedelta(days=1),
        )
    )
    open_deal = db.scalar(
        select(Deal.id).where(Deal.contact_id == contact.id, Deal.stage.not_in(["won", "lost"]))
    )
    if not open_deal:
        company = db.get(Company, contact.company_id) if contact.company_id else None
        db.add(
            Deal(
                workspace_id=ws,
                contact_id=contact.id,
                title=f"{company.name if company else contact.last_name} – LinkedIn-Gespräch{label}"[
                    :200
                ],
                stage="conversation",
            )
        )


def resolve_simulation(db, job):
    """Worker handler for simulated outcomes. Purely local; no network access."""
    item = db.get(LinkedInAction, job.payload["action_id"])
    if item is None or item.workspace_id != job.workspace_id or not item.simulated:
        return {"skipped": "missing"}
    if item.state not in ("pending", "delivered"):
        return {"skipped": "already_resolved", "state": item.state}
    account = db.scalar(select(SimAccount).where(SimAccount.contact_id == item.contact_id))
    contact = db.get(Contact, item.contact_id)
    if account is None or contact is None:
        _log(item, "cancelled", "simulator", "Synthetisches Konto entfernt")
        return {"state": item.state}
    if item.action == "connection_request":
        outcome = {
            "accepts_and_replies": "accepted",
            "accepts_silent": "accepted",
            "declines": "declined",
            "ignores": "no_response",
        }[account.behaviour]
        _log(item, outcome, "simulator", f"Verhalten: {account.behaviour}")
        item.resolved_at = now()
        if outcome == "accepted":
            _crm_on_accept(db, contact)
    elif account.behaviour == "accepts_and_replies":
        _log(item, "replied", "simulator", SIM_REPLY)
        item.resolved_at = now()
        _crm_on_reply(db, job.workspace_id, contact, True)
    else:
        item.resolved_at = now()
        _log(item, "delivered", "simulator", "Keine Antwort (simuliertes Verhalten)")
    return {"action_id": item.id, "state": item.state, "simulated": True}


def register_linkedin_channel_routes(app, db_session, scope, record, paginate, audit):
    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")

    def require_simulator():
        if not simulator_enabled():
            raise HTTPException(403, "LinkedIn-Simulator ist in dieser Umgebung deaktiviert.")

    def create_sim_account(db, ws, display_name, headline, company_name, behaviour, handle=None):
        first, _, last = display_name.partition(" ")
        company = None
        if company_name:
            identity = "linkedin_simulator:" + company_name.casefold()
            company = db.scalar(
                select(Company).where(Company.workspace_id == ws, Company.identity == identity)
            )
            if company is None:
                company = Company(
                    workspace_id=ws,
                    name=company_name + " (synthetisch)",
                    identity=identity,
                    source="linkedin_simulator",
                    provenance={
                        "license": "Synthetisches Simulator-Konto",
                        "confidence": "synthetic",
                    },
                )
                db.add(company)
                db.flush()
        contact = Contact(
            workspace_id=ws,
            company_id=company.id if company else None,
            first_name=first,
            last_name=(last or "Simulator") + " (synthetisch)",
            job_title=headline,
            location="Simulator",
            source="linkedin_simulator",
            linkedin_url=None,
            email=None,
            phone=None,
        )
        db.add(contact)
        db.flush()
        account = SimAccount(
            workspace_id=ws,
            handle=handle or ("sim-" + contact.id[:8]),
            display_name=display_name,
            headline=headline,
            behaviour=behaviour,
            contact_id=contact.id,
        )
        db.add(account)
        db.flush()
        return account

    def account_output(account):
        return {
            "id": account.id,
            "handle": account.handle,
            "display_name": account.display_name,
            "headline": account.headline,
            "behaviour": account.behaviour,
            "contact_id": account.contact_id,
            "profile_url": f"sim://linkedin/{account.handle}",
            "synthetic": True,
        }

    @app.get("/v1/workspaces/{ws}/linkedin/capabilities")
    def capabilities(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return {
            "channels": {
                "simulator": {
                    "available": simulator_enabled(),
                    "reason": None
                    if simulator_enabled()
                    else "Nur in Entwicklung/Test oder mit LINKEDIN_SIMULATOR_ENABLED=true.",
                    "scope": "Nur synthetische Simulator-Konten; keine Verbindung zu LinkedIn.",
                },
                "manual": {
                    "available": True,
                    "reason": None,
                    "scope": "Übergabe an eine Person, die in LinkedIn selbst handelt; Ergebnis wird selbst gemeldet.",
                },
                "official": {"available": False, "reason": OFFICIAL_REASON, "scope": None},
            },
            "limits": limits(),
            "usage": usage(db, ws),
            "rules": [
                "Jede Nachricht benötigt eine freigegebene aktuelle Entwurfsrevision.",
                f"Kontaktanfrage-Notizen höchstens {CONNECTION_NOTE_LIMIT} Zeichen.",
                "Nachrichten erst nach angenommener Verbindung.",
                "Gesperrte Kontakte sind ausgeschlossen. Eine Verbindung ist kein Werbeeinverständnis.",
            ],
        }

    @app.get("/v1/workspaces/{ws}/linkedin/simulator/accounts")
    def sim_accounts(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        rows = db.scalars(
            select(SimAccount)
            .where(SimAccount.workspace_id == ws)
            .order_by(SimAccount.display_name)
        ).all()
        return {"items": [account_output(a) for a in rows], "enabled": simulator_enabled()}

    @app.post("/v1/workspaces/{ws}/linkedin/simulator/accounts", status_code=201)
    def add_sim_account(
        ws: str,
        body: SimAccountInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        require_simulator()
        account = create_sim_account(
            db, ws, body.display_name, body.headline, body.company, body.behaviour
        )
        audit(
            db,
            ws,
            member.user_id,
            "linkedin_sim_account_created",
            "Synthetisches Simulator-Konto angelegt",
        )
        return account_output(account)

    @app.post("/v1/workspaces/{ws}/linkedin/simulator/seed")
    def seed_sim(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        authoring(member)
        require_simulator()
        existing = set(db.scalars(select(SimAccount.handle).where(SimAccount.workspace_id == ws)))
        created = []
        for handle, name, headline, company, behaviour in SIM_PERSONAS:
            if handle in existing:
                continue
            created.append(
                account_output(
                    create_sim_account(db, ws, name, headline, company, behaviour, handle)
                )
            )
        audit(
            db,
            ws,
            member.user_id,
            "linkedin_sim_seeded",
            f"{len(created)} synthetische Simulator-Konten angelegt",
        )
        return {"created": created, "existing": len(existing)}

    @app.get("/v1/workspaces/{ws}/linkedin/actions")
    def list_actions(
        ws: str,
        contact_id: str | None = None,
        campaign_id: str | None = None,
        page: int = 1,
        limit: int = 50,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        stmt = select(LinkedInAction).where(LinkedInAction.workspace_id == ws)
        if contact_id:
            stmt = stmt.where(LinkedInAction.contact_id == contact_id)
        if campaign_id:
            stmt = stmt.where(LinkedInAction.campaign_id == campaign_id)
        rows, total = paginate(
            db, stmt.order_by(LinkedInAction.created_at.desc(), LinkedInAction.id), page, limit
        )
        return {
            "items": [action_output(r) for r in rows],
            "total": total,
            "page": page,
            "limit": limit,
        }

    @app.post("/v1/workspaces/{ws}/linkedin/actions", status_code=201)
    def create_action(
        ws: str, body: ActionInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        if body.channel == "official":
            raise HTTPException(403, OFFICIAL_REASON)
        contact = record(db, Contact, ws, body.contact_id, True)
        # Serialize per workspace so pacing limits cannot be raced.
        from sqlalchemy import text

        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "linkedin-actions:" + ws},
        )
        account = db.scalar(select(SimAccount).where(SimAccount.contact_id == contact.id))
        if body.channel == "simulator":
            require_simulator()
            if account is None:
                raise HTTPException(
                    422, "Der Simulator kann nur synthetische Simulator-Konten ansprechen."
                )
        elif account is not None:
            raise HTTPException(422, "Synthetische Konten nur im Simulator verwenden.")
        if db.scalar(select(Suppression.id).where(Suppression.contact_id == contact.id)):
            raise HTTPException(409, "Kontakt ist gesperrt.")
        if body.campaign_id:
            campaign = record(db, Campaign, ws, body.campaign_id)
            if campaign.status in ("paused", "completed"):
                raise HTTPException(409, "Kampagne ist pausiert oder abgeschlossen.")
            if not db.scalar(
                select(Enrollment.id).where(
                    Enrollment.campaign_id == campaign.id, Enrollment.contact_id == contact.id
                )
            ):
                raise HTTPException(422, "Kontakt ist dieser Kampagne nicht zugeordnet.")
        content = ""
        draft = None
        if body.draft_id:
            draft = record(db, Draft, ws, body.draft_id, True)
            if draft.contact_id != contact.id:
                raise HTTPException(422, "Entwurf gehört zu einem anderen Kontakt.")
            if draft.approved_revision != draft.revision or draft.state != "approved":
                raise HTTPException(409, "Aktuelle Entwurfsrevision ist nicht freigegeben.")
            if db.scalar(
                select(LinkedInAction.id).where(
                    LinkedInAction.draft_id == draft.id,
                    LinkedInAction.state.not_in(["not_sent", "cancelled"]),
                )
            ):
                raise HTTPException(409, "Dieser Entwurf wurde bereits verwendet.")
            content = draft.content
            if body.action == "connection_request" and len(content) > CONNECTION_NOTE_LIMIT:
                raise HTTPException(
                    422, f"Kontaktanfrage-Notiz ist länger als {CONNECTION_NOTE_LIMIT} Zeichen."
                )
        state = connection_state(db, ws, contact.id)
        if body.action == "connection_request" and state != "none":
            # No repeated requests after a decline/no response: respect the recipient.
            raise HTTPException(409, f"Verbindungsstatus ist bereits '{state}'.")
        if body.action == "message" and state != "accepted":
            raise HTTPException(409, "Nachrichten erst nach angenommener Verbindung.")
        current, configured = usage(db, ws), limits()
        if body.action == "connection_request" and (
            current["connection_requests_last_24h"] >= configured["connection_requests_per_day"]
            or current["connection_requests_last_7d"] >= configured["connection_requests_per_week"]
        ):
            raise HTTPException(429, "Tages- oder Wochenlimit für Kontaktanfragen erreicht.")
        if (
            body.action == "message"
            and current["messages_last_24h"] >= configured["messages_per_day"]
        ):
            raise HTTPException(429, "Tageslimit für Nachrichten erreicht.")
        item = LinkedInAction(
            workspace_id=ws,
            contact_id=contact.id,
            campaign_id=body.campaign_id,
            draft_id=draft.id if draft else None,
            draft_revision=draft.revision if draft else None,
            actor_id=member.user_id,
            channel=body.channel,
            action=body.action,
            content=content,
            simulated=body.channel == "simulator",
            history=[],
        )
        handoff = None
        if body.channel == "simulator":
            _log(
                item,
                "pending" if body.action == "connection_request" else "delivered",
                member.user_id,
            )
            db.add(item)
            db.flush()
            enqueue(
                db,
                ws,
                member.user_id,
                "linkedin_sim",
                {"action_id": item.id},
                key="linkedin-sim:" + item.id,
                available_at=now() + timedelta(seconds=configured["simulated_delay_seconds"]),
            )
            if draft:
                draft.state = "simulated"
        else:
            _log(item, "handed_off", member.user_id)
            db.add(item)
            db.flush()
            if draft:
                draft.state = "handed_off"
            handoff = {
                "profile_url": contact.linkedin_url,
                "text": content,
                "steps": [
                    "LinkedIn selbst im Browser öffnen und das Profil prüfen.",
                    "Kontaktanfrage bzw. Nachricht selbst senden (Text kopieren, nicht automatisiert)."
                    if content
                    else "Kontaktanfrage ohne Notiz selbst senden.",
                    "Ergebnis hier bestätigen: gesendet, angenommen, abgelehnt, beantwortet oder nicht gesendet.",
                ],
                "missing_profile_url": not contact.linkedin_url,
            }
        audit(
            db,
            ws,
            member.user_id,
            "linkedin_action_created",
            f"LinkedIn {body.action} über Kanal {body.channel}"
            + (
                " (simuliert, nichts an LinkedIn gesendet)"
                if item.simulated
                else " (manuelle Übergabe)"
            ),
        )
        return action_output(item) | {"handoff": handoff}

    @app.post("/v1/workspaces/{ws}/linkedin/actions/{entity_id}/outcome")
    def record_outcome(
        ws: str,
        entity_id: str,
        body: OutcomeInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        item = record(db, LinkedInAction, ws, entity_id, True)
        if item.channel != "manual":
            raise HTTPException(
                409, "Ergebnisse werden nur für manuelle Übergaben selbst gemeldet."
            )
        allowed = {
            "handed_off": {"sent", "not_sent", "accepted", "declined", "replied"},
            "sent": {"accepted", "declined", "replied"},
            "accepted": {"replied"} if item.action == "message" else set(),
        }.get(item.state, set())
        if item.action == "connection_request":
            allowed -= {"replied"}
        else:
            allowed -= {"accepted", "declined"}
        if body.outcome not in allowed:
            raise HTTPException(
                409, f"Übergang von '{item.state}' nach '{body.outcome}' ist nicht zulässig."
            )
        contact = record(db, Contact, ws, item.contact_id, True)
        _log(item, body.outcome, member.user_id, body.note)
        if body.outcome in ("accepted", "declined", "replied", "not_sent"):
            item.resolved_at = now()
        kind = {
            ("connection_request", "sent"): "connection_requested",
            ("connection_request", "accepted"): "connected",
            ("message", "sent"): "message_sent_manually",
            ("message", "replied"): "replied",
        }.get((item.action, body.outcome))
        if kind:
            db.add(
                ManualActivity(
                    workspace_id=ws,
                    contact_id=contact.id,
                    campaign_id=item.campaign_id,
                    actor_id=member.user_id,
                    kind=kind,
                    note=body.note,
                )
            )
        if body.outcome == "accepted":
            _crm_on_accept(db, contact)
        if body.outcome == "replied":
            _crm_on_reply(db, ws, contact, False)
        from app.today import set_stage

        stage = {
            ("connection_request", "sent"): "sent",
            ("connection_request", "accepted"): "connected",
            ("message", "replied"): "replied",
        }.get((item.action, body.outcome))
        if stage:
            set_stage(contact, stage)
        if body.outcome == "not_sent" and item.draft_id:
            draft = db.get(Draft, item.draft_id)
            if draft and draft.state == "handed_off":
                draft.state = "approved"
        audit(
            db,
            ws,
            member.user_id,
            "linkedin_outcome_reported",
            f"Manuelles Ergebnis gemeldet: {body.outcome}; nicht vom Anbieter bestätigt",
        )
        return action_output(item)

    @app.get("/v1/workspaces/{ws}/campaigns/{entity_id}/linkedin")
    def campaign_linkedin(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        """Per-contact sequence progress: connection state, completed steps, next due step."""
        campaign = record(db, Campaign, ws, entity_id)
        steps = db.scalars(
            select(CampaignStep)
            .where(CampaignStep.campaign_id == campaign.id)
            .order_by(CampaignStep.position)
        ).all()
        contacts = db.scalars(
            select(Contact)
            .join(Enrollment, Enrollment.contact_id == Contact.id)
            .where(Enrollment.campaign_id == campaign.id)
            .order_by(Contact.last_name, Contact.id)
        ).all()
        sim_contacts = set(
            db.scalars(
                select(SimAccount.contact_id).where(
                    SimAccount.contact_id.in_([c.id for c in contacts])
                )
            )
        )
        suppressed = set(
            db.scalars(
                select(Suppression.contact_id).where(
                    Suppression.contact_id.in_([c.id for c in contacts])
                )
            )
        )
        rows = []
        for contact in contacts:
            actions = db.scalars(
                select(LinkedInAction)
                .where(
                    LinkedInAction.contact_id == contact.id,
                    LinkedInAction.campaign_id == campaign.id,
                )
                .order_by(LinkedInAction.created_at, LinkedInAction.id)
            ).all()
            links = {
                link.draft_id: link.step_position
                for link in db.scalars(
                    select(CampaignDraft).where(
                        CampaignDraft.campaign_id == campaign.id,
                        CampaignDraft.contact_id == contact.id,
                    )
                )
            }
            done = [
                a
                for a in actions
                if a.action == "message" and a.state in ("delivered", "sent", "replied")
            ]
            completed_positions = sorted(
                {links.get(a.draft_id) for a in done if a.draft_id in links}
            )
            replied = any(a.state == "replied" for a in actions)
            next_step = next((s for s in steps if s.position not in completed_positions), None)
            due_at = None
            if next_step is not None and done:
                last = max(a.resolved_at or a.created_at for a in done)
                due_at = last + timedelta(days=next_step.delay_days)
            approved = None
            if next_step is not None:
                draft_id = next((d for d, p in links.items() if p == next_step.position), None)
                draft = db.get(Draft, draft_id) if draft_id else None
                approved = (
                    {
                        "draft_id": draft.id,
                        "state": draft.state,
                        "approved": draft.approved_revision == draft.revision
                        and draft.state == "approved",
                    }
                    if draft
                    else None
                )
            rows.append(
                {
                    "contact_id": contact.id,
                    "name": f"{contact.first_name} {contact.last_name}".strip(),
                    "simulator_account": contact.id in sim_contacts,
                    "linkedin_url": contact.linkedin_url,
                    "suppressed": contact.id in suppressed,
                    "connection": connection_state(db, ws, contact.id),
                    "replied": replied,
                    "completed_steps": completed_positions,
                    "next_step": next_step.position if next_step is not None else None,
                    "next_due_at": due_at,
                    "next_draft": approved,
                    "stopped": replied or contact.id in suppressed,
                    "actions": [action_output(a) for a in actions],
                }
            )
        return {
            "campaign_id": campaign.id,
            "steps": [{"position": s.position, "delay_days": s.delay_days} for s in steps],
            "contacts": rows,
            "notice": "Fälligkeiten sind Planung; nichts wird automatisch gesendet. "
            "Sequenzen stoppen nach Antwort oder Sperre.",
        }
