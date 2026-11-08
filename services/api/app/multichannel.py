"""V3 M1: one person, one record, and exactly one active outreach route per contact.

Contact points: every way to reach a person (verified LinkedIn profile, postal address,
personal or general e-mail, phone) is stored once with its source and date. Points come
from the contact's own fields and from cited company facts (Impressum, OSM).

Route ("Kanal-Weiche"): a verified/confirmed LinkedIn profile -> ``linkedin``; otherwise a
postal address -> ``letter``; otherwise ``none``. A user may set the route manually; the
automatic rule then leaves it alone.

Permissions per channel are computed in one place (``channel_permissions``):
- an objection (suppression) blocks every channel immediately,
- LinkedIn: only a person clicks; ProspectOS never sends anything to LinkedIn,
- letter: advertising letters to businesses are generally allowed unless the recipient
  objected,
- phone: only with documented concrete interest (presumed consent) and its occasion,
- e-mail: the existing e-mail eligibility (documented consent per country) decides; cold
  first e-mails stay off until the workspace owner switches them on after legal advice,
  and even then dispatch keeps its own legal-basis check,
- visit: usual cold canvassing, allowed unless the recipient objected.

This is product logic, not legal advice.
"""

import re
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now
from app.models import Contact, TenantMixin
from app.platform_models import Consent, Suppression

CHANNELS = ("linkedin", "postal", "email", "phone")
ROUTES = {"linkedin": "LinkedIn", "letter": "Brief", "none": "Kein Weg"}
VERIFIED_PROFILE = ("verified", "confirmed")
GENERIC_LOCAL = re.compile(
    r"^(info|kontakt|contact|office|mail|post|hallo|hello|service|team|empfang|zentrale|"
    r"buero|büro|verwaltung|anfrage|anfragen|praxis|kanzlei)([.\-_]|$)",
    re.I,
)
# Company facts that become contact points (label -> channel, kind).
FACT_POINTS = {
    "Adresse (Impressum)": ("postal", "general"),
    "Adresse": ("postal", "general"),
    "Telefon (Impressum)": ("phone", "general"),
    "E-Mail allgemein (Impressum)": ("email", "general"),
}
PHONE_BASES = {"concrete_interest": "Konkretes Interesse (mutmaßliche Einwilligung)"}
LETTER_NOTE = (
    "Werbebriefe an Firmen sind grundsätzlich zulässig, solange kein Widerspruch vorliegt."
)


class ContactPoint(TenantMixin, Base):
    __tablename__ = "contact_points"
    contact_id: Mapped[str] = mapped_column(String(36))
    channel: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20), default="personal")
    source: Mapped[str] = mapped_column(String(100), default="")
    source_url: Mapped[str | None] = mapped_column(String(2000))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("workspace_id", "contact_id", "channel", "value"),
        ForeignKeyConstraint(
            ["workspace_id", "contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
    )


class ChannelPolicy(TenantMixin, Base):
    __tablename__ = "channel_policies"
    cold_email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    legal_review_note: Mapped[str] = mapped_column(String(1000), default="")
    changed_by: Mapped[str | None] = mapped_column(String(36))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("workspace_id"),
        ForeignKeyConstraint(
            ["workspace_id", "changed_by"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class ContactMerge(TenantMixin, Base):
    """Audit record of a merge. The removed contact's data lives on in the kept one."""

    __tablename__ = "contact_merges"
    kept_contact_id: Mapped[str] = mapped_column(String(36))
    merged_contact_id: Mapped[str] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(String(500))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    actor_id: Mapped[str] = mapped_column(String(36))
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "kept_contact_id"],
            ["contacts.workspace_id", "contacts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "actor_id"], ["memberships.workspace_id", "memberships.user_id"]
        ),
    )


class RouteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: str
    reason: str = Field(default="", max_length=300)


class BasisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: str
    basis: str
    evidence: str = Field(min_length=3, max_length=1000)
    occasion: str = Field(default="", max_length=300)
    valid_days: int = Field(default=180, ge=1, le=730)


class ObjectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=200)


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cold_email_enabled: bool
    legal_review_note: str = Field(default="", max_length=1000)


class MergeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duplicate_id: str
    reason: str = Field(min_length=3, max_length=500)


def email_kind(address: str) -> str:
    local = address.split("@", 1)[0]
    return "general" if GENERIC_LOCAL.match(local) else "personal"


def _upsert(
    db,
    ws,
    contact_id,
    channel,
    value,
    *,
    kind,
    source,
    source_url=None,
    verified=False,
    observed=None,
):
    value = (value or "").strip()[:500]
    if not value:
        return None
    point = db.scalar(
        select(ContactPoint).where(
            ContactPoint.workspace_id == ws,
            ContactPoint.contact_id == contact_id,
            ContactPoint.channel == channel,
            ContactPoint.value == value,
        )
    )
    if point is None:
        point = ContactPoint(
            workspace_id=ws,
            contact_id=contact_id,
            channel=channel,
            value=value,
            kind=kind,
            source=source[:100],
            source_url=(source_url or None),
            observed_at=observed or now(),
            verified=verified,
        )
        db.add(point)
    else:
        point.verified = verified
        point.kind = kind
    return point


def sync_points(db, ws, contact: Contact) -> list[ContactPoint]:
    """Collect contact points from the contact and its company's cited facts. Idempotent."""
    from app.journeys import CompanyFact

    keep = set()
    if contact.linkedin_url:
        verified = contact.linkedin_status in VERIFIED_PROFILE
        label = {
            "confirmed": "LinkedIn-Profil (von dir bestätigt)",
            "verified": "LinkedIn-Profil (automatisch geprüft)",
        }.get(contact.linkedin_status, "LinkedIn-Profil (ungeprüft)")
        p = _upsert(
            db,
            ws,
            contact.id,
            "linkedin",
            contact.linkedin_url,
            kind="personal",
            source=label,
            verified=verified,
            observed=contact.linkedin_checked_at or contact.created_at,
        )
        keep.add(("linkedin", p.value))
    if contact.email:
        p = _upsert(
            db,
            ws,
            contact.id,
            "email",
            contact.email.lower(),
            kind=email_kind(contact.email),
            source=contact.source or "Kontakt",
            verified=not (contact.source or "").startswith("guessed"),
            observed=contact.created_at,
        )
        keep.add(("email", p.value))
    if contact.phone:
        p = _upsert(
            db,
            ws,
            contact.id,
            "phone",
            contact.phone,
            kind="personal",
            source=contact.source or "Kontakt",
            observed=contact.created_at,
        )
        keep.add(("phone", p.value))
    if contact.company_id:
        facts = db.scalars(
            select(CompanyFact).where(
                CompanyFact.workspace_id == ws,
                CompanyFact.company_id == contact.company_id,
                CompanyFact.field.in_(list(FACT_POINTS)),
            )
        ).all()
        for fact in facts:
            channel, kind = FACT_POINTS[fact.field]
            value = fact.value.lower() if channel == "email" else fact.value
            p = _upsert(
                db,
                ws,
                contact.id,
                channel,
                value,
                kind=kind,
                source=f"{fact.field} · {fact.source_kind}",
                source_url=fact.source_url,
                verified=True,
                observed=fact.created_at,
            )
            if p is not None:
                keep.add((channel, p.value))
    db.flush()
    # Points whose origin disappeared (e.g. a changed LinkedIn URL) are removed.
    for point in db.scalars(
        select(ContactPoint).where(
            ContactPoint.workspace_id == ws, ContactPoint.contact_id == contact.id
        )
    ):
        if (point.channel, point.value) not in keep:
            db.delete(point)
    db.flush()
    return points_of(db, ws, contact.id)


def points_of(db, ws, contact_id) -> list[ContactPoint]:
    return list(
        db.scalars(
            select(ContactPoint)
            .where(ContactPoint.workspace_id == ws, ContactPoint.contact_id == contact_id)
            .order_by(ContactPoint.channel, ContactPoint.observed_at)
        )
    )


def decide_route(contact: Contact, points: list[ContactPoint]) -> tuple[str, str]:
    profile = next((p for p in points if p.channel == "linkedin" and p.verified), None)
    if profile:
        return "linkedin", f"Geprüftes LinkedIn-Profil ({profile.source})."
    postal = next((p for p in points if p.channel == "postal"), None)
    if postal:
        unverified = any(p.channel == "linkedin" for p in points)
        return "letter", (
            ("Profil nicht geprüft. " if unverified else "Kein LinkedIn-Profil. ")
            + f"Postadresse aus {postal.source.split(' · ')[0]}."
        )
    return "none", "Weder geprüftes LinkedIn-Profil noch Postadresse bekannt."


def apply_route(db, ws, contact: Contact, points=None) -> bool:
    """Set the automatic route unless a user chose one. Returns True if it changed."""
    if contact.route_mode == "manual":
        return False
    route, reason = decide_route(
        contact, points if points is not None else points_of(db, ws, contact.id)
    )
    if (route, reason) == (contact.channel_route, contact.route_reason):
        return False
    contact.channel_route, contact.route_reason, contact.route_set_at = route, reason, now()
    return True


def suppression_of(db, ws, contact_id):
    return db.scalar(
        select(Suppression).where(
            Suppression.workspace_id == ws, Suppression.contact_id == contact_id
        )
    )


def get_policy(db, ws) -> ChannelPolicy:
    policy = db.scalar(select(ChannelPolicy).where(ChannelPolicy.workspace_id == ws))
    if policy is None:
        policy = ChannelPolicy(workspace_id=ws)
        db.add(policy)
        db.flush()
    return policy


def _valid_basis(db, ws, contact_id, channel, allowed):
    return db.scalar(
        select(Consent)
        .where(
            Consent.workspace_id == ws,
            Consent.contact_id == contact_id,
            Consent.channel == channel,
            Consent.revoked.is_(False),
            Consent.legal_basis.in_(allowed),
            or_(Consent.expires_at.is_(None), Consent.expires_at > now()),
        )
        .order_by(Consent.created_at.desc())
        .limit(1)
    )


def channel_permissions(db, ws, contact: Contact, points=None) -> dict:
    """Single place deciding which channel may be used for a contact right now."""
    from app.email_outreach import eligibility

    points = points if points is not None else points_of(db, ws, contact.id)
    objection = suppression_of(db, ws, contact.id)
    if objection:
        blocked = {"allowed": False, "basis": None, "reason": f"Widerspruch: {objection.reason}"}
        return {c: dict(blocked) for c in ("linkedin", "letter", "email", "phone", "visit")}
    has = {c: [p for p in points if p.channel == c] for c in CHANNELS}
    out = {}
    verified = [p for p in has["linkedin"] if p.verified]
    out["linkedin"] = {
        "allowed": bool(verified),
        "basis": "Du klickst selbst in LinkedIn" if verified else None,
        "reason": None if verified else "Kein geprüftes LinkedIn-Profil.",
    }
    out["letter"] = {
        "allowed": bool(has["postal"]),
        "basis": LETTER_NOTE if has["postal"] else None,
        "reason": None if has["postal"] else "Keine Postadresse bekannt.",
    }
    mail = eligibility(db, ws, contact)
    policy = db.scalar(select(ChannelPolicy).where(ChannelPolicy.workspace_id == ws))
    out["email"] = {
        "allowed": mail["allowed"],
        "basis": mail["basis"]["label"] if mail["basis"] else None,
        "reason": None if mail["allowed"] else " ".join(mail["reasons"]),
        "cold_email_enabled": bool(policy and policy.cold_email_enabled),
    }
    phone_basis = _valid_basis(db, ws, contact.id, "phone", list(PHONE_BASES))
    out["phone"] = {
        "allowed": bool(has["phone"]) and phone_basis is not None,
        "basis": f"{PHONE_BASES[phone_basis.legal_basis]}: {phone_basis.evidence}"
        if phone_basis
        else None,
        "reason": None
        if has["phone"] and phone_basis
        else (
            "Keine Telefonnummer bekannt."
            if not has["phone"]
            else "Anruf erst nach konkretem Interesse (z. B. QR-Scan, Antwort, Anfrage)."
        ),
    }
    out["visit"] = {
        "allowed": bool(has["postal"]),
        "basis": "Persönlicher Besuch (übliche Kaltakquise)" if has["postal"] else None,
        "reason": None if has["postal"] else "Keine Adresse bekannt.",
    }
    return out


def record_phone_interest(db, ws, contact_id, occasion: str, evidence: str):
    """Document concrete interest after a reaction; enables the phone channel."""
    if _valid_basis(db, ws, contact_id, "phone", list(PHONE_BASES)):
        return None
    item = Consent(
        workspace_id=ws,
        contact_id=contact_id,
        channel="phone",
        legal_basis="concrete_interest",
        evidence=f"{occasion}: {evidence}"[:1000],
        expires_at=now() + timedelta(days=180),
        country="DE",
    )
    db.add(item)
    return item


def point_output(p: ContactPoint) -> dict:
    return {
        "id": p.id,
        "channel": p.channel,
        "value": p.value,
        "kind": p.kind,
        "source": p.source,
        "source_url": p.source_url,
        "observed_at": p.observed_at,
        "verified": p.verified,
    }


def channels_output(db, ws, contact: Contact) -> dict:
    points = points_of(db, ws, contact.id)
    return {
        "contact_id": contact.id,
        "route": contact.channel_route,
        "route_label": ROUTES.get(contact.channel_route, contact.channel_route),
        "route_reason": contact.route_reason,
        "route_mode": contact.route_mode,
        "route_set_at": contact.route_set_at,
        "points": [point_output(p) for p in points],
        "permissions": channel_permissions(db, ws, contact, points),
        "objection": (lambda s: {"reason": s.reason, "at": s.created_at} if s else None)(
            suppression_of(db, ws, contact.id)
        ),
    }


def _name_key(contact: Contact) -> str:
    return " ".join(f"{contact.first_name} {contact.last_name}".casefold().split())


def duplicate_pairs(db, ws, limit=100) -> list[dict]:
    contacts = db.scalars(
        select(Contact)
        .where(Contact.workspace_id == ws)
        .order_by(Contact.created_at, Contact.id)
        .limit(5000)
    ).all()
    by_email, by_name, pairs, seen = {}, {}, [], set()

    def add(a, b, reason):
        key = tuple(sorted((a.id, b.id)))
        if key in seen:
            return
        seen.add(key)
        pairs.append(
            {
                "keep": {"id": a.id, "name": f"{a.first_name} {a.last_name}".strip()},
                "duplicate": {"id": b.id, "name": f"{b.first_name} {b.last_name}".strip()},
                "reason": reason,
            }
        )

    for c in contacts:
        if c.email:
            other = by_email.setdefault(c.email.casefold(), c)
            if other is not c:
                add(other, c, f"Gleiche E-Mail-Adresse ({c.email.casefold()}).")
        if c.company_id and _name_key(c):
            other = by_name.setdefault((_name_key(c), c.company_id), c)
            if other is not c:
                add(other, c, "Gleicher Name in derselben Firma.")
    return pairs[:limit]


def merge_contacts(db, ws, keep: Contact, drop: Contact, reason: str, actor_id: str) -> dict:
    """Move everything that belongs to ``drop`` onto ``keep``, then delete ``drop``.

    Every tenant table with a ``contact_id`` column is re-pointed. Rows that would violate
    a uniqueness rule (e.g. the same campaign enrollment twice) stay with ``drop`` and are
    removed with it; their table names are recorded in the merge record."""
    if keep.id == drop.id:
        raise HTTPException(422, "Ein Kontakt kann nicht mit sich selbst zusammengeführt werden.")
    filled = []
    for field in ("email", "phone", "job_title", "location", "linkedin_url", "company_id"):
        if not getattr(keep, field) and getattr(drop, field):
            filled.append(field)
    drop_values = {f: getattr(drop, f) for f in filled}
    if drop.linkedin_url and "linkedin_url" in filled:
        drop.linkedin_url = None
        db.flush()
    moved, dropped = {}, []
    for table in Base.metadata.sorted_tables:
        if table.name in ("contacts", "contact_merges") or "contact_id" not in table.c:
            continue
        if "workspace_id" not in table.c:
            continue
        stmt = (
            update(table)
            .where(table.c.workspace_id == ws, table.c.contact_id == drop.id)
            .values(contact_id=keep.id)
        )
        savepoint = db.begin_nested()
        try:
            count = db.execute(stmt).rowcount
            savepoint.commit()
            if count:
                moved[table.name] = count
        except IntegrityError:
            savepoint.rollback()
            dropped.append(table.name)
    for field, value in drop_values.items():
        setattr(keep, field, value)
    if "linkedin_url" in filled:
        keep.linkedin_status = drop.linkedin_status
        keep.linkedin_reason = drop.linkedin_reason
    keep.version += 1
    merged_name = f"{drop.first_name} {drop.last_name}".strip()
    db.flush()
    db.delete(drop)
    db.flush()
    record = ContactMerge(
        workspace_id=ws,
        kept_contact_id=keep.id,
        merged_contact_id=drop.id,
        reason=reason,
        details={
            "moved": moved,
            "conflicting_tables": dropped,
            "filled": filled,
            "merged_name": merged_name,
        },
        actor_id=actor_id,
    )
    db.add(record)
    sync_points(db, ws, keep)
    apply_route(db, ws, keep)
    return {"kept_id": keep.id, "moved": moved, "conflicting_tables": dropped, "filled": filled}


def register_multichannel_routes(app, db_session, scope, record, audit):
    def authoring(member):
        if member.role not in ("owner", "admin", "editor"):
            raise HTTPException(403, "Bearbeitungsrecht erforderlich.")

    @app.get("/v1/workspaces/{ws}/contacts/{entity_id}/channels")
    def contact_channels(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        contact = record(db, Contact, ws, entity_id)
        return channels_output(db, ws, contact)

    @app.post("/v1/workspaces/{ws}/contacts/{entity_id}/channels/refresh")
    def refresh_contact(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        authoring(member)
        contact = record(db, Contact, ws, entity_id, True)
        apply_route(db, ws, contact, sync_points(db, ws, contact))
        return channels_output(db, ws, contact)

    @app.post("/v1/workspaces/{ws}/channels/refresh")
    def refresh_all(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        authoring(member)
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "channel-refresh:" + ws},
        )
        changed = 0
        contacts = db.scalars(select(Contact).where(Contact.workspace_id == ws).limit(5000)).all()
        for contact in contacts:
            changed += apply_route(db, ws, contact, sync_points(db, ws, contact))
        counts = dict(
            db.execute(
                select(Contact.channel_route, func.count())
                .where(Contact.workspace_id == ws)
                .group_by(Contact.channel_route)
            ).all()
        )
        audit(
            db, ws, member.user_id, "channels_refreshed", f"Kanal-Weiche: {changed} Wege geändert"
        )
        return {"contacts": len(contacts), "changed": changed, "routes": counts}

    @app.get("/v1/workspaces/{ws}/channels/summary")
    def summary(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        counts = dict(
            db.execute(
                select(Contact.channel_route, func.count())
                .where(Contact.workspace_id == ws)
                .group_by(Contact.channel_route)
            ).all()
        )
        objections = db.scalar(
            select(func.count(Suppression.id)).where(Suppression.workspace_id == ws)
        )
        policy = db.scalar(select(ChannelPolicy).where(ChannelPolicy.workspace_id == ws))
        return {
            "routes": {k: counts.get(k, 0) for k in ROUTES},
            "objections": objections,
            "cold_email_enabled": bool(policy and policy.cold_email_enabled),
        }

    @app.put("/v1/workspaces/{ws}/contacts/{entity_id}/route")
    def set_route(
        ws: str,
        entity_id: str,
        body: RouteInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        contact = record(db, Contact, ws, entity_id, True)
        if body.route == "auto":
            contact.route_mode = "auto"
            apply_route(db, ws, contact, sync_points(db, ws, contact))
            return channels_output(db, ws, contact)
        if body.route not in ROUTES:
            raise HTTPException(422, "Unbekannter Weg.")
        points = sync_points(db, ws, contact)
        perms = channel_permissions(db, ws, contact, points)
        needed = {"linkedin": "linkedin", "letter": "letter"}.get(body.route)
        if needed and not perms[needed]["allowed"]:
            raise HTTPException(409, f"Weg nicht möglich: {perms[needed]['reason']}")
        contact.channel_route = body.route
        contact.route_mode = "manual"
        contact.route_reason = body.reason or "Von Hand gewählt."
        contact.route_set_at = now()
        audit(
            db, ws, member.user_id, "route_changed", f"Weg manuell auf {ROUTES[body.route]} gesetzt"
        )
        return channels_output(db, ws, contact)

    @app.post("/v1/workspaces/{ws}/contacts/{entity_id}/legal-basis", status_code=201)
    def add_basis(
        ws: str,
        entity_id: str,
        body: BasisInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        contact = record(db, Contact, ws, entity_id)
        if body.channel == "phone":
            if body.basis not in PHONE_BASES:
                raise HTTPException(422, "Telefon nur mit konkretem Interesse.")
            if len(body.occasion.strip()) < 3:
                raise HTTPException(
                    422, "Anlass des konkreten Interesses angeben (z. B. Anfrage vom 3.11.)."
                )
        elif body.channel == "email":
            from app.email_outreach import BASIS_LABELS

            if body.basis not in BASIS_LABELS:
                raise HTTPException(422, "Unbekannte Rechtsgrundlage für E-Mail.")
        else:
            raise HTTPException(422, "Für Brief und Besuch genügt: kein Widerspruch.")
        item = Consent(
            workspace_id=ws,
            contact_id=contact.id,
            channel=body.channel,
            legal_basis=body.basis,
            evidence=(f"{body.occasion}: " if body.occasion else "") + body.evidence,
            expires_at=now() + timedelta(days=body.valid_days),
            country="DE",
        )
        db.add(item)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "legal_basis_recorded",
            f"Rechtsgrundlage {body.channel}: {body.basis}",
        )
        return channels_output(db, ws, contact)

    @app.post("/v1/workspaces/{ws}/contacts/{entity_id}/objection", status_code=201)
    def objection(
        ws: str,
        entity_id: str,
        body: ObjectionInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        contact = record(db, Contact, ws, entity_id, True)
        if not suppression_of(db, ws, contact.id):
            db.add(Suppression(workspace_id=ws, contact_id=contact.id, reason=body.reason))
            db.flush()
        stopped = stop_everything(
            db, ws, contact.id, f"Widerspruch: {body.reason}", actor_id=member.user_id
        )
        audit(
            db,
            ws,
            member.user_id,
            "objection_recorded",
            "Widerspruch eingetragen; alle Kanäle gesperrt",
        )
        return channels_output(db, ws, contact) | {"stopped": stopped}

    @app.get("/v1/workspaces/{ws}/channel-policy")
    def read_policy(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        policy = db.scalar(select(ChannelPolicy).where(ChannelPolicy.workspace_id == ws))
        return {
            "cold_email_enabled": bool(policy and policy.cold_email_enabled),
            "legal_review_note": policy.legal_review_note if policy else "",
            "changed_at": policy.changed_at if policy else None,
            "notice": "Kalte Erst-E-Mails nur nach Rechtsberatung freischalten. Der Versand prüft "
            "die dokumentierte Rechtsgrundlage je Kontakt trotzdem weiter.",
        }

    @app.put("/v1/workspaces/{ws}/channel-policy")
    def write_policy(
        ws: str, body: PolicyInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if member.role != "owner":
            raise HTTPException(403, "Nur der Owner darf kalte E-Mails freischalten.")
        if body.cold_email_enabled and len(body.legal_review_note.strip()) < 20:
            raise HTTPException(
                422, "Bitte festhalten, wer wann rechtlich beraten hat (mind. 20 Zeichen)."
            )
        policy = get_policy(db, ws)
        policy.cold_email_enabled = body.cold_email_enabled
        policy.legal_review_note = body.legal_review_note
        policy.changed_by, policy.changed_at = member.user_id, now()
        audit(
            db,
            ws,
            member.user_id,
            "cold_email_policy",
            "Kalte Erst-E-Mails "
            + ("freigeschaltet" if body.cold_email_enabled else "abgeschaltet"),
        )
        return read_policy(ws, member, db)

    @app.get("/v1/workspaces/{ws}/contacts-duplicates")
    def duplicates(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        return {"items": duplicate_pairs(db, ws)}

    @app.post("/v1/workspaces/{ws}/contacts/{entity_id}/merge")
    def merge(
        ws: str,
        entity_id: str,
        body: MergeInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        authoring(member)
        keep = record(db, Contact, ws, entity_id, True)
        drop = record(db, Contact, ws, body.duplicate_id, True)
        result = merge_contacts(db, ws, keep, drop, body.reason, member.user_id)
        audit(db, ws, member.user_id, "contacts_merged", f"Kontakte zusammengeführt: {body.reason}")
        return result | {"channels": channels_output(db, ws, keep)}


def stop_everything(db, ws, contact_id, reason, actor_id=None) -> dict:
    """Stop every planned step for a contact on every channel. Extended by later milestones
    through ``STOP_HOOKS``; each hook returns a count."""
    return {name: hook(db, ws, contact_id, reason) for name, hook in STOP_HOOKS.items()}


def _stop_scheduled_email(db, ws, contact_id, reason):
    from app.email_outreach import EmailMessage

    count = 0
    for message in db.scalars(
        select(EmailMessage).where(
            EmailMessage.workspace_id == ws,
            EmailMessage.contact_id == contact_id,
            EmailMessage.state == "scheduled",
        )
    ):
        message.state = "cancelled"
        message.events = list(message.events or []) + [
            {"at": now().isoformat(), "event": "cancelled", "reason": reason[:200]}
        ]
        count += 1
    return count


def _stop_today_queue(db, ws, contact_id, reason):
    from app.today import QueueItem

    count = 0
    for item in db.scalars(
        select(QueueItem).where(
            QueueItem.workspace_id == ws,
            QueueItem.contact_id == contact_id,
            QueueItem.state.in_(["pending", "approved"]),
        )
    ):
        item.state = "skipped"
        count += 1
    return count


STOP_HOOKS = {"email": _stop_scheduled_email, "today": _stop_today_queue}
