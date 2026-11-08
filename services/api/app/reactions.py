"""V3 M3: every reaction stops every planned step, and all answers land in one inbox.

Sources of reactions:
- e-mail reply recognised by the IMAP sync (In-Reply-To/References of one of our mails),
- LinkedIn by click in Heute or in the contact (accepted, replied, reply text pasted),
- QR scan: public ``/r/<code>`` records the scan and redirects to the target page,
- website inquiry: the user enters the code that appears in the inquiry.

A reaction (except an accepted LinkedIn invitation, which is the expected next step of the
LinkedIn path) stops all runs, open tasks, scheduled e-mails and Heute items of the contact,
documents concrete interest for the phone channel and creates one follow-up task
("Anrufen und Termin vereinbaren" if a phone number is known, otherwise "Termin
vereinbaren").

Reference codes map a code to a company. The table has RLS for the application role; a
SECURITY DEFINER function owned by the migrator resolves a code for the public scan
endpoint without exposing other rows.
"""

import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit, urlunsplit

from fastapi import Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKeyConstraint, String, UniqueConstraint, func, select, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, SessionLocal, now
from app.models import Company, Contact, TenantMixin

KINDS = {
    "email_reply": ("email", "E-Mail-Antwort", True),
    "linkedin_accepted": ("linkedin", "LinkedIn: Einladung angenommen", False),
    "linkedin_replied": ("linkedin", "LinkedIn: Antwort", True),
    "qr_scan": ("letter", "QR-Code gescannt", True),
    "web_inquiry": ("web", "Anfrage über die Website", True),
    "phone_call": ("phone", "Anruf erhalten", True),
    "other": ("manual", "Sonstige Reaktion", True),
}
STATUSES = {
    "new": "neu",
    "answered": "beantwortet",
    "meeting": "Termin",
    "not_interested": "kein Interesse",
}
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_RE = re.compile(r"^[A-Z2-9]{6,12}$")
SCAN_DEDUP_HOURS = 24


class Reaction(TenantMixin, Base):
    __tablename__ = "reactions"
    contact_id: Mapped[str] = mapped_column(String(36))
    channel: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(String(4000), default="")
    code: Mapped[str | None] = mapped_column(String(20))
    source_ref: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default="new")
    status_by: Mapped[str | None] = mapped_column(String(36))
    status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "status_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class RefCode(TenantMixin, Base):
    __tablename__ = "ref_codes"
    code: Mapped[str] = mapped_column(String(20), unique=True)
    company_id: Mapped[str] = mapped_column(String(36))
    target_url: Mapped[str] = mapped_column(String(500), default="")
    __table_args__ = (
        UniqueConstraint("workspace_id", "company_id"),
        ForeignKeyConstraint(
            ["workspace_id", "company_id"],
            ["companies.workspace_id", "companies.id"],
            ondelete="CASCADE",
        ),
    )


class ReactionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    text: str = Field(default="", max_length=4000)


class CodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=20)
    text: str = Field(default="", max_length=4000)


class StatusInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class RefCodeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_url: str = Field(default="", max_length=500)


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def safe_target(url: str) -> str:
    """Only absolute https URLs without credentials; empty means 'no redirect target'."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise HTTPException(422, "Ziel muss eine https-Adresse sein.")
    return urlunsplit(parts)[:500]


def with_ref(url: str, code: str) -> str:
    parts = urlsplit(url)
    query = (parts.query + "&" if parts.query else "") + urlencode({"ref": code})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def code_for(db, ws, company_id, target_url="") -> RefCode:
    item = db.scalar(
        select(RefCode).where(RefCode.workspace_id == ws, RefCode.company_id == company_id)
    )
    if item is None:
        for _ in range(5):
            candidate = new_code()
            if not db.scalar(select(func.resolve_ref_code(candidate))):
                break
        item = RefCode(
            workspace_id=ws, company_id=company_id, code=candidate, target_url=target_url
        )
        db.add(item)
        db.flush()
    elif target_url and item.target_url != target_url:
        item.target_url = target_url
    return item


def contact_for_company(db, ws, company_id) -> Contact | None:
    """The person a company-level signal belongs to: one in an active run, else the first."""
    from app.flows import FlowRun

    running = db.scalar(
        select(Contact)
        .join(FlowRun, FlowRun.contact_id == Contact.id)
        .where(
            Contact.workspace_id == ws,
            Contact.company_id == company_id,
            FlowRun.state.in_(["active", "waiting"]),
        )
        .order_by(FlowRun.created_at)
        .limit(1)
    )
    return running or db.scalar(
        select(Contact)
        .where(Contact.workspace_id == ws, Contact.company_id == company_id)
        .order_by(Contact.created_at, Contact.id)
        .limit(1)
    )


def record_reaction(
    db, ws, contact: Contact, kind: str, text="", *, code=None, source_ref=None, actor_id=None
):
    """Store a reaction and apply its consequences. Idempotent per ``source_ref``."""
    from app.flows import FlowTask
    from app.multichannel import points_of, record_phone_interest, stop_everything
    from app.today import set_stage

    if kind not in KINDS:
        raise HTTPException(422, "Unbekannte Reaktion.")
    if source_ref:
        existing = db.scalar(
            select(Reaction).where(
                Reaction.workspace_id == ws,
                Reaction.contact_id == contact.id,
                Reaction.source_ref == source_ref,
            )
        )
        if existing:
            return existing, None
    channel, label, stops = KINDS[kind]
    reaction = Reaction(
        workspace_id=ws,
        contact_id=contact.id,
        channel=channel,
        kind=kind,
        text=(text or "")[:4000],
        code=code,
        source_ref=source_ref,
        actor_id=actor_id,
    )
    db.add(reaction)
    db.flush()
    if not stops:
        set_stage(contact, "connected")
        return reaction, None
    stopped = stop_everything(db, ws, contact.id, f"Reaktion: {label}", actor_id)
    set_stage(contact, "replied")
    record_phone_interest(db, ws, contact.id, label, (text or "ohne Text")[:300])
    has_phone = any(p.channel == "phone" for p in points_of(db, ws, contact.id)) or bool(
        contact.phone
    )
    db.add(
        FlowTask(
            workspace_id=ws,
            contact_id=contact.id,
            kind="call_task" if has_phone else "meeting_task",
            title="Anrufen und Termin vereinbaren"
            if has_phone
            else "Auf die Reaktion antworten und Termin vereinbaren",
            body=f"{label}: {text[:500]}" if text else label,
            due_at=now(),
            state="open",
            assignee_id=contact.owner_id,
            origin="reaction",
        )
    )
    db.flush()
    return reaction, stopped


def reaction_output(db, r: Reaction, contact=None) -> dict:
    contact = contact or db.get(Contact, r.contact_id)
    company = db.get(Company, contact.company_id) if contact and contact.company_id else None
    return {
        "id": r.id,
        "kind": r.kind,
        "kind_label": KINDS.get(r.kind, ("", r.kind, True))[1],
        "channel": r.channel,
        "text": r.text,
        "code": r.code,
        "status": r.status,
        "status_label": STATUSES.get(r.status, r.status),
        "created_at": r.created_at,
        "status_at": r.status_at,
        "contact": {
            "id": contact.id,
            "name": f"{contact.first_name} {contact.last_name}".strip(),
            "phone": contact.phone,
            "owner_id": contact.owner_id,
        }
        if contact
        else None,
        "company": {"id": company.id, "name": company.name} if company else None,
    }


def resolve_scan(code: str):
    """Public scan: resolve the code through the definer function, then record under RLS."""
    if not CODE_RE.match(code or ""):
        return None
    with SessionLocal() as db, db.begin():
        row = db.execute(text("SELECT * FROM resolve_ref_code(:c)"), {"c": code}).first()
        if not row:
            return None
        ws, company_id, target = row
        db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})
        contact = contact_for_company(db, ws, company_id)
        if contact is not None:
            recent = db.scalar(
                select(Reaction.id).where(
                    Reaction.workspace_id == ws,
                    Reaction.contact_id == contact.id,
                    Reaction.kind == "qr_scan",
                    Reaction.created_at > now() - timedelta(hours=SCAN_DEDUP_HOURS),
                )
            )
            if not recent:
                record_reaction(
                    db, ws, contact, "qr_scan", "QR-Code auf dem Brief gescannt", code=code
                )
        return target or ""


def register_reaction_routes(app, db_session, scope, record, audit):
    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")

    @app.get("/v1/r/{code}", include_in_schema=False)
    def scan(code: str):
        target = resolve_scan(code.upper())
        if target is None:
            raise HTTPException(404, "Code unbekannt.")
        if target:
            return RedirectResponse(with_ref(target, code.upper()), status_code=302)
        return {"ok": True, "message": "Danke! Wir melden uns bei Ihnen."}

    @app.post("/v1/workspaces/{ws}/contacts/{entity_id}/reactions", status_code=201)
    def add_reaction(
        ws: str,
        entity_id: str,
        body: ReactionInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        contact = record(db, Contact, ws, entity_id, True)
        reaction, stopped = record_reaction(
            db, ws, contact, body.kind, body.text, actor_id=member.user_id
        )
        audit(db, ws, member.user_id, "reaction_recorded", f"Reaktion: {KINDS[body.kind][1]}")
        return reaction_output(db, reaction, contact) | {"stopped": stopped}

    @app.post("/v1/workspaces/{ws}/reactions/by-code", status_code=201)
    def by_code(
        ws: str, body: CodeInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        code = body.code.strip().upper()
        item = db.scalar(select(RefCode).where(RefCode.workspace_id == ws, RefCode.code == code))
        if item is None:
            raise HTTPException(404, "Code gehört zu keiner Firma in diesem Workspace.")
        contact = contact_for_company(db, ws, item.company_id)
        if contact is None:
            raise HTTPException(409, "Zu dieser Firma gibt es noch keinen Kontakt.")
        reaction, stopped = record_reaction(
            db, ws, contact, "web_inquiry", body.text, code=code, actor_id=member.user_id
        )
        audit(db, ws, member.user_id, "reaction_recorded", "Anfrage mit Code zugeordnet")
        return reaction_output(db, reaction, contact) | {"stopped": stopped}

    @app.post("/v1/workspaces/{ws}/companies/{entity_id}/ref-code")
    def ref_code(
        ws: str,
        entity_id: str,
        body: RefCodeInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        company = record(db, Company, ws, entity_id)
        item = code_for(db, ws, company.id, safe_target(body.target_url))
        return {
            "code": item.code,
            "company_id": company.id,
            "target_url": item.target_url,
            "path": f"/r/{item.code}",
        }

    @app.get("/v1/workspaces/{ws}/inbox")
    def inbox(
        ws: str,
        status: str = "",
        page: int = 1,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if status and status not in STATUSES:
            raise HTTPException(422, "Unbekannter Status.")
        stmt = select(Reaction).where(Reaction.workspace_id == ws)
        if status:
            stmt = stmt.where(Reaction.status == status)
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.scalars(
            stmt.order_by(Reaction.created_at.desc(), Reaction.id)
            .offset((max(page, 1) - 1) * 50)
            .limit(50)
        ).all()
        counts = dict(
            db.execute(
                select(Reaction.status, func.count())
                .where(Reaction.workspace_id == ws)
                .group_by(Reaction.status)
            ).all()
        )
        return {
            "items": [reaction_output(db, r) for r in rows],
            "total": total,
            "counts": {k: counts.get(k, 0) for k in STATUSES},
            "statuses": STATUSES,
        }

    @app.patch("/v1/workspaces/{ws}/reactions/{entity_id}")
    def set_status(
        ws: str,
        entity_id: str,
        body: StatusInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        from app.today import set_stage

        authoring(member)
        if body.status not in STATUSES:
            raise HTTPException(422, "Unbekannter Status.")
        reaction = record(db, Reaction, ws, entity_id, True)
        reaction.status, reaction.status_by, reaction.status_at = body.status, member.user_id, now()
        contact = db.get(Contact, reaction.contact_id)
        if contact and body.status in ("meeting", "not_interested"):
            set_stage(contact, body.status, forward_only=False)
        audit(db, ws, member.user_id, "reaction_status", f"Posteingang: {STATUSES[body.status]}")
        return reaction_output(db, reaction, contact)
