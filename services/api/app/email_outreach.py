"""M6: email outreach from the customer's own mailboxes (never via Resend).

Legal: under §7 Abs. 2 Nr. 2 UWG advertising e-mails need prior express consent, also
B2B; §7 Abs. 3 UWG allows existing-customer e-mail under strict conditions. Each contact
therefore needs a documented legal basis (consents table: type, evidence, country,
expiry). Allowed basis types per country are configuration (EMAIL_COUNTRY_RULES JSON).
Contacts without an allowed basis may sit in campaigns, but sending to them is blocked
and the UI says why. This check runs at scheduling AND again at dispatch; it can't be
switched off.

Deliverability: per-mailbox ramp-up (start limit + daily step up to a max), rotation over
active mailboxes, sending window with random spacing, bounce/complaint detection via IMAP
with automatic pause, RFC 8058 one-click List-Unsubscribe, workspace-wide suppression.
"""

import hashlib
import json
import os
import random
import re
import secrets
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app import credentials
from app.db import Base, SessionLocal, now
from app.journeys import CampaignDraft, CampaignStep, CompanyFact
from app.models import Company, Contact, Draft, TenantMixin
from app.platform_models import Campaign, Consent, Enrollment, Job, Suppression
from app.providers.ai import ProviderError

TZ = ZoneInfo("Europe/Berlin")
DEFAULT_RULES = {
    "DE": {
        "allowed": ["consent", "explicit_consent", "existing_customer_7_3", "recipient_request"],
        "note": "§7 Abs. 2 Nr. 2 UWG: Werbe-E-Mails nur mit vorheriger ausdrücklicher Einwilligung "
        "(auch B2B). Ausnahme Bestandskunde nach §7 Abs. 3 UWG nur bei eigener Kundenbeziehung, "
        "ähnlichen Waren/Dienstleistungen, Hinweis bei Erhebung und jeder Verwendung.",
    },
    "AT": {
        "allowed": ["consent", "explicit_consent", "existing_customer_7_3", "recipient_request"],
        "note": "§174 TKG 2021",
    },
    "*": {
        "allowed": ["consent", "explicit_consent", "recipient_request"],
        "note": "Standard: nur Einwilligung/Anfrage",
    },
}
BASIS_LABELS = {
    "consent": "Einwilligung",
    "explicit_consent": "Einwilligung",
    "existing_customer_7_3": "Bestandskunde (§7 Abs. 3 UWG)",
    "recipient_request": "Anfrage des Empfängers",
    "verified_statutory_exception": "Gesetzliche Ausnahme (Altbestand)",
    "other": "Sonstige",
}
BOUNCE_PAUSE_RATE = 0.05
COMPLAINT_PAUSE_RATE = 0.003


def country_rules() -> dict:
    try:
        custom = json.loads(os.getenv("EMAIL_COUNTRY_RULES", "") or "{}")
        if isinstance(custom, dict):
            return DEFAULT_RULES | custom
    except ValueError:
        pass
    return DEFAULT_RULES


class Mailbox(TenantMixin, Base):
    __tablename__ = "mailboxes"
    email: Mapped[str] = mapped_column(String(254))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    username: Mapped[str] = mapped_column(String(254))
    ciphertext: Mapped[str] = mapped_column(String(4000))
    smtp_host: Mapped[str] = mapped_column(String(253))
    smtp_port: Mapped[int] = mapped_column(Integer)
    smtp_security: Mapped[str] = mapped_column(String(10))
    imap_host: Mapped[str] = mapped_column(String(253))
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    signature: Mapped[str] = mapped_column(String(1000), default="")
    sender_footer: Mapped[str] = mapped_column(String(1000))
    ramp_start: Mapped[date] = mapped_column(Date)
    ramp_start_limit: Mapped[int] = mapped_column(Integer, default=5)
    ramp_step: Mapped[int] = mapped_column(Integer, default=3)
    daily_max: Mapped[int] = mapped_column(Integer, default=40)
    window_start: Mapped[int] = mapped_column(Integer, default=8)
    window_end: Mapped[int] = mapped_column(Integer, default=17)
    status: Mapped[str] = mapped_column(String(20), default="active")
    paused_reason: Mapped[str] = mapped_column(String(300), default="")
    last_error: Mapped[str] = mapped_column(String(100), default="")
    last_tested_at = mapped_column(DateTime(timezone=True), nullable=True)
    imap_last_uid: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        UniqueConstraint("workspace_id", "id"),
        UniqueConstraint("workspace_id", "email"),
        ForeignKeyConstraint(
            ["workspace_id", "created_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class EmailMessage(TenantMixin, Base):
    __tablename__ = "email_messages"
    mailbox_id: Mapped[str] = mapped_column(String(36))
    contact_id: Mapped[str] = mapped_column(String(36))
    campaign_id: Mapped[str | None] = mapped_column(String(36))
    draft_id: Mapped[str] = mapped_column(String(36))
    draft_revision: Mapped[int] = mapped_column(Integer)
    step_position: Mapped[int] = mapped_column(Integer, default=0)
    to_email: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    message_id: Mapped[str | None] = mapped_column(String(300))
    state: Mapped[str] = mapped_column(String(20), default="scheduled")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at = mapped_column(DateTime(timezone=True), nullable=True)
    unsubscribe_hash: Mapped[str] = mapped_column(String(64))
    events: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str] = mapped_column(String(100), default="")
    __table_args__ = (
        UniqueConstraint("workspace_id", "draft_id", "draft_revision"),
        ForeignKeyConstraint(
            ["workspace_id", "mailbox_id"], ["mailboxes.workspace_id", "mailboxes.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"], ["campaigns.workspace_id", "campaigns.id"]
        ),
        ForeignKeyConstraint(
            ["workspace_id", "draft_id"], ["message_drafts.workspace_id", "message_drafts.id"]
        ),
    )


# ---- schemas ---------------------------------------------------------------------------


class MailboxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(pattern=r"^[^@\s]{1,64}@[A-Za-z0-9.-]{3,190}$")
    display_name: str = Field(default="", max_length=120)
    username: str | None = Field(default=None, max_length=254)
    password: str = Field(min_length=4, max_length=500)
    smtp_host: str = Field(max_length=253)
    smtp_port: int = 465
    smtp_security: str = Field(default="ssl", pattern="^(ssl|starttls)$")
    imap_host: str = Field(max_length=253)
    imap_port: int = 993
    signature: str = Field(default="", max_length=1000)
    sender_footer: str = Field(min_length=10, max_length=1000)
    ramp_start_limit: int = Field(default=5, ge=1, le=50)
    ramp_step: int = Field(default=3, ge=0, le=20)
    daily_max: int = Field(default=40, ge=1, le=200)
    window_start: int = Field(default=8, ge=0, le=23)
    window_end: int = Field(default=17, ge=1, le=24)
    test: bool = True


class MailboxPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str | None = Field(default=None, pattern="^(active|paused)$")
    daily_max: int | None = Field(default=None, ge=1, le=200)
    signature: str | None = Field(default=None, max_length=1000)
    sender_footer: str | None = Field(default=None, min_length=10, max_length=1000)


class LegalBasisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contact_id: str
    basis: str = Field(pattern="^(consent|existing_customer_7_3|recipient_request|other)$")
    evidence: str = Field(min_length=10, max_length=1000)
    evidence_url: str | None = Field(default=None, max_length=2000)
    country: str = Field(default="DE", pattern="^[A-Z]{2}$")
    expires_at: datetime | None = None


class EmailDraftsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_position: int = Field(ge=0, le=20)
    subject: str = Field(min_length=3, max_length=200)
    mailbox_id: str | None = None


class BulkApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_ids: list[str] = Field(default_factory=list, max_length=500)
    all_for_step: int | None = Field(default=None, ge=0, le=20)


class ScheduleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_position: int = Field(ge=0, le=20)
    min_gap_minutes: int = Field(default=4, ge=1, le=120)
    max_gap_minutes: int = Field(default=11, ge=1, le=240)


# ---- policy ----------------------------------------------------------------------------


def eligibility(db, ws, contact: Contact) -> dict:
    """Single source of truth for 'may we e-mail this contact?'. Never bypassed."""
    reasons = []
    if not contact.email:
        reasons.append("Keine E-Mail-Adresse hinterlegt.")
    elif (contact.source or "").startswith("guessed"):
        reasons.append("Adresse ist nur vermutet (nicht geprüft).")
    if db.scalar(
        select(Suppression.id).where(
            Suppression.workspace_id == ws, Suppression.contact_id == contact.id
        )
    ):
        reasons.append("Kontakt steht auf der Sperrliste (abgemeldet/gebounct).")
    rules = country_rules()
    bases = db.scalars(
        select(Consent).where(
            Consent.workspace_id == ws,
            Consent.contact_id == contact.id,
            Consent.channel == "email",
            Consent.revoked.is_(False),
        )
    ).all()
    valid = None
    for basis in bases:
        rule = rules.get(basis.country or "DE", rules["*"])
        expired = basis.expires_at is not None and basis.expires_at <= now()
        if basis.legal_basis in rule["allowed"] and not expired:
            valid = basis
            break
    if not valid:
        if bases:
            reasons.append(
                "Vorhandene Rechtsgrundlage ist für das Land nicht zulässig oder abgelaufen ("
                + ", ".join(BASIS_LABELS.get(b.legal_basis, b.legal_basis) for b in bases)
                + ")."
            )
        else:
            reasons.append(
                "Keine dokumentierte Rechtsgrundlage (§7 UWG: Einwilligung erforderlich)."
            )
    return {
        "allowed": not reasons,
        "reasons": reasons,
        "basis": (
            {
                "type": valid.legal_basis,
                "label": BASIS_LABELS.get(valid.legal_basis, valid.legal_basis),
                "country": valid.country,
                "evidence": valid.evidence,
                "evidence_url": valid.evidence_url,
                "expires_at": valid.expires_at,
            }
            if valid
            else None
        ),
    }


def capacity_today(db, ws, box: Mailbox) -> int:
    days = max(0, (datetime.now(TZ).date() - box.ramp_start).days)
    limit = min(box.daily_max, box.ramp_start_limit + box.ramp_step * days)
    start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.scalar(
        select(func.count(EmailMessage.id)).where(
            EmailMessage.workspace_id == ws,
            EmailMessage.mailbox_id == box.id,
            EmailMessage.scheduled_at >= start,
            EmailMessage.state.not_in(["cancelled", "blocked"]),
        )
    )
    return max(0, limit - used)


def _cfg(box: Mailbox):
    from app.providers.mailbox import MailboxConfig

    secret = json.loads(credentials.cipher().decrypt(box.ciphertext.encode()).decode())
    return MailboxConfig(
        email=box.email,
        username=box.username,
        password=secret["password"],
        smtp_host=box.smtp_host,
        smtp_port=box.smtp_port,
        smtp_security=box.smtp_security,
        imap_host=box.imap_host,
        imap_port=box.imap_port,
        display_name=box.display_name,
    )


def mailbox_output(db, ws, box: Mailbox) -> dict:
    sent = db.scalar(
        select(func.count(EmailMessage.id)).where(
            EmailMessage.mailbox_id == box.id, EmailMessage.sent_at.is_not(None)
        )
    )
    bounced = db.scalar(
        select(func.count(EmailMessage.id)).where(
            EmailMessage.mailbox_id == box.id, EmailMessage.state == "bounced"
        )
    )
    return {
        "id": box.id,
        "email": box.email,
        "display_name": box.display_name,
        "domain": box.email.split("@", 1)[1],
        "smtp": f"{box.smtp_host}:{box.smtp_port} ({box.smtp_security})",
        "imap": f"{box.imap_host}:{box.imap_port}",
        "password": "••••••••",
        "status": box.status,
        "paused_reason": box.paused_reason,
        "last_error": box.last_error,
        "last_tested_at": box.last_tested_at,
        "ramp": {
            "start": box.ramp_start,
            "start_limit": box.ramp_start_limit,
            "step": box.ramp_step,
            "max": box.daily_max,
        },
        "capacity_today": capacity_today(db, ws, box),
        "window": f"{box.window_start:02d}:00–{box.window_end:02d}:00 Europe/Berlin",
        "signature": box.signature,
        "sender_footer": box.sender_footer,
        "stats": {"sent": sent, "bounced": bounced},
    }


# ---- DNS assistant -------------------------------------------------------------------


def dns_report(domain: str, resolver=None) -> dict:
    import dns.exception
    import dns.resolver

    resolver = resolver or dns.resolver.Resolver()
    resolver.lifetime = 5

    def txt(name):
        try:
            return [
                b"".join(r.strings).decode(errors="replace") for r in resolver.resolve(name, "TXT")
            ]
        except (dns.exception.DNSException, OSError):
            return []

    try:
        mx = sorted(str(r.exchange).rstrip(".") for r in resolver.resolve(domain, "MX"))
    except (dns.exception.DNSException, OSError):
        mx = []
    spf = [t for t in txt(domain) if t.lower().startswith("v=spf1")]
    dmarc = [t for t in txt("_dmarc." + domain) if t.lower().startswith("v=dmarc1")]
    selectors = [
        "google",
        "selector1",
        "selector2",
        "default",
        "dkim",
        "mail",
        "k1",
        "s1",
        "s2",
        "ionos",
        "strato",
    ]
    dkim = {s: t for s in selectors for t in txt(f"{s}._domainkey.{domain}") if "p=" in t}
    checks = [
        {
            "name": "MX",
            "ok": bool(mx),
            "value": ", ".join(mx),
            "fix": "MX-Einträge des Mailanbieters setzen (nötig für Antworten und Bounces).",
        },
        {
            "name": "SPF",
            "ok": len(spf) == 1,
            "value": "; ".join(spf),
            "fix": "Genau einen TXT-Eintrag 'v=spf1 include:<anbieter> ~all' setzen."
            if len(spf) != 1
            else "",
        },
        {
            "name": "DKIM",
            "ok": bool(dkim),
            "value": ", ".join(dkim),
            "fix": "DKIM beim Mailanbieter aktivieren und den TXT-Eintrag <selector>._domainkey veröffentlichen (Selector nicht automatisch erkannt? Bitte prüfen)."
            if not dkim
            else "",
        },
        {
            "name": "DMARC",
            "ok": bool(dmarc),
            "value": "; ".join(dmarc),
            "fix": "TXT-Eintrag _dmarc mit 'v=DMARC1; p=none; rua=mailto:dmarc@"
            + domain
            + "' setzen, später p=quarantine."
            if not dmarc
            else "",
        },
    ]
    return {
        "domain": domain,
        "checks": checks,
        "ready": all(c["ok"] for c in checks),
        "advice": "Kaltakquise nur von separaten Zweitdomains (nicht Subdomains der Hauptdomain) und erst nach Aufwärmphase.",
    }


# ---- content ---------------------------------------------------------------------------


def personalize(
    template: str, contact: Contact, company: Company | None, facts: dict, signature: str
) -> str:
    hook = ""
    for field in ("KI-Profil: Anknüpfungspunkte", "KI-Profil: Tätigkeit"):
        if facts.get(field):
            hook = facts[field].value
            break
    values = {
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "name": " ".join(filter(None, [contact.first_name, contact.last_name])),
        "company": company.name if company else "",
        "city": company.location if company else "",
        "evidence": hook,
    }
    body = re.sub(
        r"\{(first_name|last_name|name|company|city|evidence)\}",
        lambda m: values.get(m.group(1), ""),
        template,
    )
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return (body + ("\n\n" + signature.strip() if signature.strip() else ""))[:3000]


# ---- job phases ------------------------------------------------------------------------


def prepare_send(db, job) -> dict:
    msg = db.scalar(
        select(EmailMessage)
        .where(
            EmailMessage.workspace_id == job.workspace_id,
            EmailMessage.id == job.payload["message_id"],
        )
        .with_for_update()
    )
    if not msg or msg.state != "scheduled":
        raise HTTPException(409, "message_not_scheduled")
    ws = job.workspace_id
    contact = db.scalar(
        select(Contact).where(Contact.workspace_id == ws, Contact.id == msg.contact_id)
    )
    draft = db.scalar(select(Draft).where(Draft.workspace_id == ws, Draft.id == msg.draft_id))
    box = db.scalar(select(Mailbox).where(Mailbox.workspace_id == ws, Mailbox.id == msg.mailbox_id))

    # Returned (not raised) so the state change is committed; no SMTP call follows.
    def block(reason):
        msg.state, msg.error = "blocked", reason[:100]
        msg.events = list(msg.events or []) + [
            {"at": now().isoformat(), "event": "blocked", "reason": reason[:200]}
        ]
        return {"skip": "blocked", "reason": reason[:200]}

    check = eligibility(db, ws, contact)
    if not check["allowed"]:
        return block("legal_basis: " + "; ".join(check["reasons"]))
    if contact.email != msg.to_email:
        return block("recipient_changed")
    if (
        not draft
        or draft.approved_revision != msg.draft_revision
        or draft.revision != msg.draft_revision
    ):
        return block("draft_changed_after_approval")
    if not box or box.status != "active":
        from app.jobs import enqueue

        msg.scheduled_at = now() + timedelta(hours=1)
        msg.events = list(msg.events or []) + [
            {"at": now().isoformat(), "event": "deferred", "reason": "mailbox_paused"}
        ]
        enqueue(
            db,
            ws,
            job.actor_id,
            "email_send",
            job.payload,
            key=f"email:{msg.id}:{msg.scheduled_at.isoformat()}",
            available_at=msg.scheduled_at,
        )
        return {"skip": "deferred", "reason": "mailbox_paused"}
    if db.scalar(
        select(EmailMessage.id).where(
            EmailMessage.workspace_id == ws,
            EmailMessage.contact_id == contact.id,
            EmailMessage.state.in_(["replied", "unsubscribed", "bounced", "complained"]),
        )
    ):
        msg.state = "cancelled"
        msg.events = list(msg.events or []) + [
            {"at": now().isoformat(), "event": "cancelled", "reason": "sequence_stopped"}
        ]
        return {"skip": "cancelled", "reason": "sequence_stopped"}
    msg.state = "sending"
    base = os.getenv("PUBLIC_WEB_URL") or os.getenv("APP_BASE_URL") or "http://localhost:3000"
    token = job.payload["unsubscribe_token"]
    domain = box.email.split("@", 1)[1]
    return {
        "cfg": _cfg(box),
        "to": msg.to_email,
        "subject": msg.subject,
        "text": draft.content,
        "unsubscribe_url": f"{base.rstrip('/')}/v1/u/{token}",
        "unsubscribe_mailto": f"mailto:{box.email}?subject=Abmelden",
        "sender_footer": box.sender_footer,
        "domain": domain,
    }


def send(context) -> dict:
    from app.providers import mailbox as provider

    if context.get("skip"):
        return context
    cfg = context.pop("cfg")
    msg = provider.build_message(cfg, **context)
    message_id = provider.send_message(cfg, msg)
    return {"message_id": message_id, "provider": "smtp", "to": context["to"]}


def finalize_send(db, job, result) -> dict:
    if result.get("skip"):
        return result
    msg = db.scalar(
        select(EmailMessage)
        .where(
            EmailMessage.workspace_id == job.workspace_id,
            EmailMessage.id == job.payload["message_id"],
        )
        .with_for_update()
    )
    msg.state, msg.sent_at, msg.message_id = "sent", now(), result["message_id"]
    msg.events = list(msg.events or []) + [
        {
            "at": now().isoformat(),
            "event": "sent",
            "detail": "SMTP accepted (not proof of delivery)",
        }
    ]
    contact = db.scalar(
        select(Contact).where(
            Contact.workspace_id == job.workspace_id, Contact.id == msg.contact_id
        )
    )
    if contact and contact.status in ("new", "qualified"):
        contact.status = "contacted"
        contact.version += 1
    return result | {"verified_delivery": False}


def _apply_event(db, ws, kind, ids, detail=None):
    if not ids:
        return 0
    rows = db.scalars(
        select(EmailMessage).where(
            EmailMessage.workspace_id == ws, EmailMessage.message_id.in_(ids)
        )
    ).all()
    for m in rows:
        if kind == "reply":
            m.state = "replied"
            from app.reactions import record_reaction

            contact = db.get(Contact, m.contact_id)
            if contact is not None:
                # Stops every planned step on every channel and creates a call task.
                record_reaction(
                    db,
                    ws,
                    contact,
                    "email_reply",
                    (detail or {}).get("text", ""),
                    source_ref=m.message_id,
                )
        elif kind == "bounce":
            m.state = "bounced"
        elif kind == "complaint":
            m.state = "complained"
        m.events = list(m.events or []) + [
            {"at": now().isoformat(), "event": kind, **(detail or {})}
        ]
        if kind in ("bounce", "complaint") and (kind == "complaint" or (detail or {}).get("hard")):
            if not db.scalar(
                select(Suppression.id).where(
                    Suppression.workspace_id == ws, Suppression.contact_id == m.contact_id
                )
            ):
                db.add(
                    Suppression(workspace_id=ws, contact_id=m.contact_id, reason=f"E-Mail {kind}")
                )
        # Any reply/bounce/complaint stops the rest of the sequence for that contact.
        for later in db.scalars(
            select(EmailMessage).where(
                EmailMessage.workspace_id == ws,
                EmailMessage.contact_id == m.contact_id,
                EmailMessage.state == "scheduled",
            )
        ):
            later.state = "cancelled"
            later.events = list(later.events or []) + [
                {"at": now().isoformat(), "event": "cancelled", "reason": f"{kind}_received"}
            ]
    return len(rows)


def health_check(db, ws, box: Mailbox):
    recent = db.scalars(
        select(EmailMessage)
        .where(
            EmailMessage.workspace_id == ws,
            EmailMessage.mailbox_id == box.id,
            EmailMessage.sent_at.is_not(None),
        )
        .order_by(EmailMessage.sent_at.desc())
        .limit(100)
    ).all()
    if len(recent) < 10:
        return None
    bounces = sum(m.state == "bounced" for m in recent) / len(recent)
    complaints = sum(m.state == "complained" for m in recent) / len(recent)
    if bounces > BOUNCE_PAUSE_RATE or complaints > COMPLAINT_PAUSE_RATE:
        box.status = "paused"
        box.paused_reason = f"Automatisch pausiert: Bounce-Quote {bounces:.0%}, Beschwerden {complaints:.1%} (letzte {len(recent)} Mails)"
        return box.paused_reason
    return None


def sync_mailbox(job) -> dict:
    """Phase 2 (no DB): fetch new inbox messages."""
    from app.providers import mailbox as provider

    cfg, last_uid = job.payload["_cfg"], job.payload["last_uid"]
    items, new_uid = provider.fetch_new(cfg, last_uid)
    return {
        "events": [provider.classify(raw) | {"uid": uid} for uid, raw in items],
        "last_uid": new_uid,
    }


def finalize_sync(db, job, result) -> dict:
    ws = job.workspace_id
    box = db.scalar(
        select(Mailbox)
        .where(Mailbox.workspace_id == ws, Mailbox.id == job.payload["mailbox_id"])
        .with_for_update()
    )
    counts = {"reply": 0, "bounce": 0, "complaint": 0}
    for ev in result["events"]:
        if ev["kind"] in counts:
            counts[ev["kind"]] += _apply_event(
                db,
                ws,
                ev["kind"],
                ev["ids"],
                {"hard": ev.get("hard", False)}
                if ev["kind"] == "bounce"
                else ({"text": ev.get("text", "")} if ev["kind"] == "reply" else None),
            )
    box.imap_last_uid = max(box.imap_last_uid, result["last_uid"])
    paused = health_check(db, ws, box)
    return {"matched": counts, "paused": paused, "last_uid": box.imap_last_uid}


# ---- routes ----------------------------------------------------------------------------


def register_email_routes(app, db_session, scope, record, audit):
    from app.jobs import enqueue
    from app.platform_routes import job_output
    from app.providers import mailbox as provider
    from app.providers.mailbox import MailboxConfig

    def owner_admin(member):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Nur Owner/Admin verwalten Postfächer.")

    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Keine Berechtigung.")

    @app.get("/v1/workspaces/{ws}/mailboxes")
    def mailboxes(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        owner_admin(member)
        return {
            "items": [
                mailbox_output(db, ws, b)
                for b in db.scalars(
                    select(Mailbox).where(Mailbox.workspace_id == ws).order_by(Mailbox.created_at)
                )
            ]
        }

    @app.post("/v1/workspaces/{ws}/mailboxes", status_code=201)
    def add_mailbox(
        ws: str, body: MailboxInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        owner_admin(member)
        cipher = credentials.cipher()
        if body.window_end <= body.window_start:
            raise HTTPException(422, "Versandfenster ungültig.")
        if db.scalar(
            select(Mailbox.id).where(
                Mailbox.workspace_id == ws, Mailbox.email == body.email.lower()
            )
        ):
            raise HTTPException(409, "Postfach existiert bereits.")
        cfg = MailboxConfig(
            email=body.email.lower(),
            username=body.username or body.email,
            password=body.password,
            smtp_host=body.smtp_host,
            smtp_port=body.smtp_port,
            smtp_security=body.smtp_security,
            imap_host=body.imap_host,
            imap_port=body.imap_port,
            display_name=body.display_name,
        )
        test = None
        if body.test:
            try:
                test = {"ok": True, **provider.test_mailbox(cfg)}
            except ProviderError as exc:
                raise HTTPException(
                    422, f"Verbindungstest fehlgeschlagen: {exc.code}. Nichts gespeichert."
                ) from None
        box = Mailbox(
            workspace_id=ws,
            email=cfg.email,
            display_name=body.display_name,
            username=cfg.username,
            ciphertext=cipher.encrypt(json.dumps({"password": body.password}).encode()).decode(),
            smtp_host=body.smtp_host,
            smtp_port=body.smtp_port,
            smtp_security=body.smtp_security,
            imap_host=body.imap_host,
            imap_port=body.imap_port,
            signature=body.signature,
            sender_footer=body.sender_footer,
            ramp_start=datetime.now(TZ).date(),
            ramp_start_limit=body.ramp_start_limit,
            ramp_step=body.ramp_step,
            daily_max=body.daily_max,
            window_start=body.window_start,
            window_end=body.window_end,
            status="active",
            last_tested_at=now() if test else None,
            created_by=member.user_id,
        )
        db.add(box)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "mailbox_added",
            f"Postfach {box.email} verschlüsselt gespeichert",
        )
        return {"item": mailbox_output(db, ws, box), "test": test}

    @app.patch("/v1/workspaces/{ws}/mailboxes/{entity_id}")
    def patch_mailbox(
        ws: str,
        entity_id: str,
        body: MailboxPatch,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        owner_admin(member)
        box = record(db, Mailbox, ws, entity_id, True)
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(box, k, v)
        if body.status == "active":
            box.paused_reason = ""
        return mailbox_output(db, ws, box)

    @app.delete("/v1/workspaces/{ws}/mailboxes/{entity_id}")
    def delete_mailbox(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        owner_admin(member)
        box = record(db, Mailbox, ws, entity_id, True)
        if db.scalar(select(EmailMessage.id).where(EmailMessage.mailbox_id == box.id)):
            box.status, box.paused_reason = (
                "paused",
                "Deaktiviert (Versandhistorie bleibt erhalten)",
            )
            return {"deleted": False, "paused": True}
        db.delete(box)
        return {"deleted": True}

    @app.post("/v1/workspaces/{ws}/mailboxes/{entity_id}/test")
    def retest(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        owner_admin(member)
        box = record(db, Mailbox, ws, entity_id, True)
        try:
            result = provider.test_mailbox(_cfg(box))
            box.last_error, box.last_tested_at = "", now()
            if box.status == "error":
                box.status = "active"
            return {"ok": True, **result}
        except ProviderError as exc:
            box.last_error, box.status = exc.code, "error"
            return {"ok": False, "error": exc.code}

    @app.get("/v1/workspaces/{ws}/mailboxes/{entity_id}/dns")
    def dns_check(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        owner_admin(member)
        box = record(db, Mailbox, ws, entity_id)
        return dns_report(box.email.split("@", 1)[1])

    @app.post("/v1/workspaces/{ws}/mailboxes/{entity_id}/sync", status_code=202)
    def sync(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        box = record(db, Mailbox, ws, entity_id)
        job = enqueue(
            db,
            ws,
            member.user_id,
            "mailbox_sync",
            {"mailbox_id": box.id},
            key=f"sync:{box.id}:{now().strftime('%Y%m%d%H%M')}",
        )
        return job_output(job)

    @app.post("/v1/workspaces/{ws}/legal-bases", status_code=201)
    def add_basis(
        ws: str,
        body: LegalBasisInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        contact = record(db, Contact, ws, body.contact_id)
        if body.evidence_url and not re.match(r"^https://\S+$", body.evidence_url):
            raise HTTPException(422, "Nachweis-URL muss mit https:// beginnen.")
        item = Consent(
            workspace_id=ws,
            contact_id=contact.id,
            channel="email",
            evidence=body.evidence,
            legal_basis=body.basis,
            country=body.country,
            evidence_url=body.evidence_url,
            expires_at=body.expires_at or (now() + timedelta(days=730)),
        )
        db.add(item)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "legal_basis_recorded",
            f"Rechtsgrundlage {body.basis} ({body.country}) dokumentiert",
        )
        return {"id": item.id, "eligibility": eligibility(db, ws, contact)}

    @app.get("/v1/workspaces/{ws}/contacts/{entity_id}/email-eligibility")
    def contact_eligibility(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        contact = record(db, Contact, ws, entity_id)
        return eligibility(db, ws, contact) | {"rules": country_rules()}

    @app.post("/v1/workspaces/{ws}/campaigns/{entity_id}/email/drafts", status_code=201)
    def email_drafts(
        ws: str,
        entity_id: str,
        body: EmailDraftsInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        campaign = record(db, Campaign, ws, entity_id)
        step = db.scalar(
            select(CampaignStep).where(
                CampaignStep.workspace_id == ws,
                CampaignStep.campaign_id == campaign.id,
                CampaignStep.position == body.step_position,
            )
        )
        if not step:
            raise HTTPException(404, "Sequenzschritt nicht gefunden.")
        box = (
            record(db, Mailbox, ws, body.mailbox_id)
            if body.mailbox_id
            else db.scalar(
                select(Mailbox).where(Mailbox.workspace_id == ws).order_by(Mailbox.created_at)
            )
        )
        signature = box.signature if box else ""
        created = skipped = 0
        for enr in db.scalars(
            select(Enrollment).where(
                Enrollment.workspace_id == ws, Enrollment.campaign_id == campaign.id
            )
        ):
            if db.scalar(
                select(CampaignDraft.id).where(
                    CampaignDraft.workspace_id == ws,
                    CampaignDraft.campaign_id == campaign.id,
                    CampaignDraft.contact_id == enr.contact_id,
                    CampaignDraft.step_position == body.step_position,
                )
            ):
                skipped += 1
                continue
            contact = db.scalar(
                select(Contact).where(Contact.workspace_id == ws, Contact.id == enr.contact_id)
            )
            company = (
                db.scalar(
                    select(Company).where(
                        Company.workspace_id == ws, Company.id == contact.company_id
                    )
                )
                if contact.company_id
                else None
            )
            facts = {}
            if company:
                for f in db.scalars(
                    select(CompanyFact).where(
                        CompanyFact.workspace_id == ws, CompanyFact.company_id == company.id
                    )
                ):
                    facts.setdefault(f.field, f)
            draft = Draft(
                workspace_id=ws,
                contact_id=contact.id,
                subject=personalize(body.subject, contact, company, facts, "")[:200],
                content=personalize(step.template, contact, company, facts, signature),
                source="email_template",
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
                    step_position=body.step_position,
                )
            )
            created += 1
        audit(
            db,
            ws,
            member.user_id,
            "email_drafts_created",
            f"{created} E-Mail-Entwürfe für Schritt {body.step_position}",
        )
        return {"created": created, "existing": skipped}

    @app.post("/v1/workspaces/{ws}/campaigns/{entity_id}/email/approve")
    def bulk_approve(
        ws: str,
        entity_id: str,
        body: BulkApprove,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if member.role not in ("owner", "admin", "approver"):
            raise HTTPException(403, "Freigaberolle erforderlich.")
        campaign = record(db, Campaign, ws, entity_id)
        links = select(CampaignDraft.draft_id).where(
            CampaignDraft.workspace_id == ws, CampaignDraft.campaign_id == campaign.id
        )
        if body.all_for_step is not None:
            links = links.where(CampaignDraft.step_position == body.all_for_step)
        stmt = select(Draft).where(
            Draft.workspace_id == ws, Draft.id.in_(links), Draft.state == "draft"
        )
        if body.draft_ids:
            stmt = stmt.where(Draft.id.in_(body.draft_ids))
        elif body.all_for_step is None:
            raise HTTPException(422, "Entwürfe auswählen oder einen Schritt komplett freigeben.")
        count = 0
        for draft in db.scalars(stmt.with_for_update()):
            if draft.subject:
                draft.approved_revision, draft.state = draft.revision, "approved"
                count += 1
        audit(
            db,
            ws,
            member.user_id,
            "email_drafts_approved",
            f"{count} E-Mails freigegeben; nichts gesendet",
        )
        return {"approved": count}

    @app.get("/v1/workspaces/{ws}/campaigns/{entity_id}/email")
    def campaign_email(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        campaign = record(db, Campaign, ws, entity_id)
        rows = []
        for enr in db.scalars(
            select(Enrollment).where(
                Enrollment.workspace_id == ws, Enrollment.campaign_id == campaign.id
            )
        ):
            contact = db.scalar(
                select(Contact).where(Contact.workspace_id == ws, Contact.id == enr.contact_id)
            )
            drafts = db.execute(
                select(CampaignDraft.step_position, Draft)
                .join(
                    Draft,
                    (Draft.workspace_id == CampaignDraft.workspace_id)
                    & (Draft.id == CampaignDraft.draft_id),
                )
                .where(
                    CampaignDraft.workspace_id == ws,
                    CampaignDraft.campaign_id == campaign.id,
                    CampaignDraft.contact_id == contact.id,
                    Draft.source == "email_template",
                )
            ).all()
            msgs = db.scalars(
                select(EmailMessage).where(
                    EmailMessage.workspace_id == ws,
                    EmailMessage.campaign_id == campaign.id,
                    EmailMessage.contact_id == contact.id,
                )
            ).all()
            rows.append(
                {
                    "contact_id": contact.id,
                    "name": " ".join(filter(None, [contact.first_name, contact.last_name])),
                    "email": contact.email,
                    "eligibility": eligibility(db, ws, contact),
                    "drafts": [
                        {
                            "step": p,
                            "id": d.id,
                            "subject": d.subject,
                            "content": d.content,
                            "state": d.state,
                            "revision": d.revision,
                        }
                        for p, d in drafts
                    ],
                    "messages": [
                        {
                            "step": m.step_position,
                            "state": m.state,
                            "scheduled_at": m.scheduled_at,
                            "sent_at": m.sent_at,
                            "error": m.error,
                        }
                        for m in msgs
                    ],
                }
            )
        all_msgs = db.scalars(
            select(EmailMessage).where(
                EmailMessage.workspace_id == ws, EmailMessage.campaign_id == campaign.id
            )
        ).all()
        sent = [m for m in all_msgs if m.sent_at]
        metrics = {
            k: sum(m.state == k for m in all_msgs)
            for k in ("scheduled", "bounced", "replied", "unsubscribed", "complained", "blocked")
        }
        metrics["sent"] = len(sent)
        return {
            "contacts": rows,
            "metrics": metrics,
            "notice": "Kennzahlen nur aus echten Ereignissen (SMTP-Annahme, IMAP-Antworten/Bounces, Abmeldungen).",
        }

    @app.post("/v1/workspaces/{ws}/campaigns/{entity_id}/email/schedule")
    def schedule(
        ws: str,
        entity_id: str,
        body: ScheduleInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        owner_admin(member)
        if body.max_gap_minutes < body.min_gap_minutes:
            raise HTTPException(422, "Abstände ungültig.")
        campaign = record(db, Campaign, ws, entity_id)
        boxes = db.scalars(
            select(Mailbox)
            .where(Mailbox.workspace_id == ws, Mailbox.status == "active")
            .order_by(Mailbox.created_at)
        ).all()
        if not boxes:
            raise HTTPException(409, "Kein aktives Postfach (Integrationen → Postfach hinzufügen).")
        capacity = {b.id: capacity_today(db, ws, b) for b in boxes}
        cursor = {b.id: _next_window_start(b) for b in boxes}
        scheduled, blocked, waiting = 0, [], 0
        pairs = db.execute(
            select(CampaignDraft.contact_id, Draft)
            .join(
                Draft,
                (Draft.workspace_id == CampaignDraft.workspace_id)
                & (Draft.id == CampaignDraft.draft_id),
            )
            .where(
                CampaignDraft.workspace_id == ws,
                CampaignDraft.campaign_id == campaign.id,
                CampaignDraft.step_position == body.step_position,
                Draft.source == "email_template",
            )
        ).all()
        rng = random.SystemRandom()
        for contact_id, draft in pairs:
            if draft.state != "approved" or draft.approved_revision != draft.revision:
                continue
            if db.scalar(
                select(EmailMessage.id).where(
                    EmailMessage.workspace_id == ws,
                    EmailMessage.draft_id == draft.id,
                    EmailMessage.draft_revision == draft.revision,
                )
            ):
                continue
            contact = db.scalar(
                select(Contact).where(Contact.workspace_id == ws, Contact.id == contact_id)
            )
            stopped = db.scalar(
                select(EmailMessage.state).where(
                    EmailMessage.workspace_id == ws,
                    EmailMessage.contact_id == contact.id,
                    EmailMessage.state.in_(["replied", "unsubscribed", "bounced", "complained"]),
                )
            )
            if stopped:
                blocked.append(
                    {
                        "contact_id": contact.id,
                        "name": f"{contact.first_name} {contact.last_name}",
                        "reasons": [f"Sequenz gestoppt ({stopped})."],
                    }
                )
                continue
            check = eligibility(db, ws, contact)
            if not check["allowed"]:
                blocked.append(
                    {
                        "contact_id": contact.id,
                        "name": f"{contact.first_name} {contact.last_name}",
                        "reasons": check["reasons"],
                    }
                )
                continue
            box = next(
                (b for b in sorted(boxes, key=lambda b: cursor[b.id]) if capacity[b.id] > 0), None
            )
            if not box:
                waiting += 1
                continue
            when = cursor[box.id]
            cursor[box.id] = _clamp_to_window(
                box,
                when + timedelta(minutes=rng.uniform(body.min_gap_minutes, body.max_gap_minutes)),
            )
            capacity[box.id] -= 1
            token = f"{ws}.{secrets.token_urlsafe(24)}"
            msg = EmailMessage(
                workspace_id=ws,
                mailbox_id=box.id,
                contact_id=contact.id,
                campaign_id=campaign.id,
                draft_id=draft.id,
                draft_revision=draft.revision,
                step_position=body.step_position,
                to_email=contact.email,
                subject=draft.subject,
                state="scheduled",
                scheduled_at=when,
                unsubscribe_hash=hashlib.sha256(token.encode()).hexdigest(),
                events=[{"at": now().isoformat(), "event": "scheduled", "mailbox": box.email}],
            )
            db.add(msg)
            db.flush()
            enqueue(
                db,
                ws,
                member.user_id,
                "email_send",
                {"message_id": msg.id, "unsubscribe_token": token},
                key=f"email:{msg.id}",
                available_at=when,
            )
            draft.state = "queued"
            scheduled += 1
        audit(
            db,
            ws,
            member.user_id,
            "email_scheduled",
            f"{scheduled} E-Mails eingeplant, {len(blocked)} blockiert",
        )
        return {"scheduled": scheduled, "blocked": blocked, "waiting_for_capacity": waiting}

    @app.get("/v1/u/{token}", response_class=HTMLResponse)
    def unsubscribe_page(token: str):
        found = _unsubscribe(token, apply=False)
        if not found:
            return HTMLResponse("<p>Link ungültig oder abgelaufen.</p>", status_code=404)
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            "<title>Abmelden</title><body style='font-family:system-ui;max-width:32rem;margin:3rem auto;padding:0 1rem'>"
            "<h1>Keine weiteren E-Mails</h1><form method=post><button style='font-size:1.1rem;padding:.6rem 1rem'>Jetzt abmelden</button></form>"
            "</body>"
        )

    @app.post("/v1/u/{token}", response_class=HTMLResponse)
    async def unsubscribe(token: str, request: Request):
        # RFC 8058 one-click: POST with body "List-Unsubscribe=One-Click" (or the form above).
        if not _unsubscribe(token, apply=True):
            return HTMLResponse("<p>Link ungültig.</p>", status_code=404)
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><p style='font-family:system-ui'>Sie wurden abgemeldet und erhalten keine weiteren E-Mails.</p>"
        )


def _next_window_start(box: Mailbox) -> datetime:
    local = datetime.now(TZ)
    return _clamp_to_window(box, local + timedelta(minutes=2))


def _clamp_to_window(box: Mailbox, when: datetime) -> datetime:
    local = when.astimezone(TZ)
    start = local.replace(hour=box.window_start, minute=0, second=0, microsecond=0)
    end = (
        local.replace(hour=box.window_end % 24, minute=0, second=0, microsecond=0)
        if box.window_end < 24
        else local.replace(hour=23, minute=59)
    )
    if local < start:
        local = start + timedelta(minutes=random.SystemRandom().uniform(0, 20))
    elif local >= end:
        local = start + timedelta(days=1, minutes=random.SystemRandom().uniform(0, 20))
    while local.weekday() >= 5:  # no weekend sends
        local = (local + timedelta(days=1)).replace(
            hour=box.window_start, minute=int(random.SystemRandom().uniform(0, 20))
        )
    return local


def _unsubscribe(token: str, apply: bool) -> bool:
    ws = token.split(".", 1)[0]
    if len(token) > 200 or not re.fullmatch(r"[0-9a-f-]{36}", ws):
        return False
    digest = hashlib.sha256(token.encode()).hexdigest()
    with SessionLocal() as db, db.begin():
        db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})
        msg = db.scalar(
            select(EmailMessage).where(
                EmailMessage.workspace_id == ws, EmailMessage.unsubscribe_hash == digest
            )
        )
        if not msg:
            return False
        if apply and msg.state != "unsubscribed":
            msg.state = "unsubscribed"
            msg.events = list(msg.events or []) + [
                {"at": now().isoformat(), "event": "unsubscribed"}
            ]
            if not db.scalar(
                select(Suppression.id).where(
                    Suppression.workspace_id == ws, Suppression.contact_id == msg.contact_id
                )
            ):
                db.add(
                    Suppression(
                        workspace_id=ws, contact_id=msg.contact_id, reason="E-Mail-Abmeldung"
                    )
                )
            for later in db.scalars(
                select(EmailMessage).where(
                    EmailMessage.workspace_id == ws,
                    EmailMessage.contact_id == msg.contact_id,
                    EmailMessage.state == "scheduled",
                )
            ):
                later.state = "cancelled"
        return True


def mailbox_sync_payload(db, job):
    box = db.scalar(
        select(Mailbox).where(
            Mailbox.workspace_id == job.workspace_id, Mailbox.id == job.payload["mailbox_id"]
        )
    )
    if not box:
        raise HTTPException(404, "mailbox_missing")
    return {"_cfg": _cfg(box), "last_uid": box.imap_last_uid}


__all__ = ["Mailbox", "EmailMessage", "Job"]
