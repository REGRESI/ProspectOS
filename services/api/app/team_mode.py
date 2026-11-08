"""V3 M5: team mode. Leads are distributed to people; each person works their own Heute.

- A contact has exactly one owner (``contacts.owner_id``), so no contact is worked by two
  people at once. Distribution is round robin or by territory (place names or postcode
  prefixes matched against the contact's location, company location and postal address).
- Each person has their own pace: invitations they marked as sent in the last 24 h and
  7 days against personal limits (default 15 per day), acceptance rate, and invitations
  still open after 21 days (worth withdrawing in LinkedIn by hand).
- Heute and campaign tasks can be filtered to "mine" (own contacts plus unassigned ones).
"""

from datetime import datetime, timedelta
from itertools import cycle

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, now
from app.models import Company, Contact, Membership, TenantMixin, User

DEFAULT_DAILY = 15
DEFAULT_WEEKLY = 80
STALE_DAYS = 21


class MemberSettings(TenantMixin, Base):
    __tablename__ = "member_settings"
    user_id: Mapped[str] = mapped_column(String(36))
    daily_invite_limit: Mapped[int] = mapped_column(Integer, default=DEFAULT_DAILY)
    weekly_invite_limit: Mapped[int] = mapped_column(Integer, default=DEFAULT_WEEKLY)
    territory: Mapped[list] = mapped_column(JSON, default=list)
    receives_leads: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id"),
        ForeignKeyConstraint(
            ["workspace_id", "user_id"],
            ["memberships.workspace_id", "memberships.user_id"],
            ondelete="CASCADE",
        ),
    )


class MemberSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    daily_invite_limit: int = Field(default=DEFAULT_DAILY, ge=1, le=30)
    weekly_invite_limit: int = Field(default=DEFAULT_WEEKLY, ge=1, le=150)
    territory: list[str] = Field(default_factory=list, max_length=40)
    receives_leads: bool = True


class DistributeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str = Field(pattern="^(round_robin|territory)$")
    only_unassigned: bool = True
    route: str = Field(default="any", pattern="^(any|linkedin|letter)$")


def member_settings(db, ws, user_id) -> MemberSettings:
    item = db.scalar(
        select(MemberSettings).where(
            MemberSettings.workspace_id == ws, MemberSettings.user_id == user_id
        )
    )
    if item is None:
        item = MemberSettings(workspace_id=ws, user_id=user_id, territory=[])
        db.add(item)
        db.flush()
    return item


def pace(db, ws, user_id) -> dict:
    from app.linkedin_channel import LinkedInAction

    settings = member_settings(db, ws, user_id)
    base = select(LinkedInAction).where(
        LinkedInAction.workspace_id == ws,
        LinkedInAction.actor_id == user_id,
        LinkedInAction.action == "connection_request",
        LinkedInAction.channel == "manual",
        LinkedInAction.state.not_in(["not_sent", "cancelled"]),
    )
    actions = db.scalars(base).all()
    day, week, stale_at = (
        now() - timedelta(days=1),
        now() - timedelta(days=7),
        now() - timedelta(days=STALE_DAYS),
    )
    contacts = (
        {
            c.id: c
            for c in db.scalars(
                select(Contact).where(Contact.id.in_({a.contact_id for a in actions}))
            )
        }
        if actions
        else {}
    )
    accepted = [
        a
        for a in actions
        if contacts.get(a.contact_id)
        and contacts[a.contact_id].outreach_stage in ("connected", "replied", "meeting")
    ]
    stale = [
        a
        for a in actions
        if a.created_at < stale_at
        and contacts.get(a.contact_id)
        and contacts[a.contact_id].outreach_stage == "sent"
    ]
    sent_day = sum(a.created_at >= day for a in actions)
    sent_week = sum(a.created_at >= week for a in actions)
    return {
        "daily_limit": settings.daily_invite_limit,
        "weekly_limit": settings.weekly_invite_limit,
        "sent_24h": sent_day,
        "sent_7d": sent_week,
        "remaining_today": max(
            0, min(settings.daily_invite_limit - sent_day, settings.weekly_invite_limit - sent_week)
        ),
        "sent_total": len(actions),
        "accepted": len(accepted),
        "acceptance_rate": round(len(accepted) / len(actions), 2) if actions else None,
        "stale_open": [
            {
                "contact_id": a.contact_id,
                "name": f"{contacts[a.contact_id].first_name} {contacts[a.contact_id].last_name}".strip(),
                "sent_at": a.created_at,
                "linkedin_url": contacts[a.contact_id].linkedin_url,
            }
            for a in sorted(stale, key=lambda a: a.created_at)[:25]
        ],
        "territory": settings.territory,
        "receives_leads": settings.receives_leads,
    }


def check_personal_limit(db, ws, user_id):
    """Called when someone marks an invitation as sent in Heute."""
    p = pace(db, ws, user_id)
    if p["sent_24h"] >= p["daily_limit"]:
        raise HTTPException(
            429, f"Dein persönliches Tageslimit ({p['daily_limit']} Einladungen) ist erreicht."
        )
    if p["sent_7d"] >= p["weekly_limit"]:
        raise HTTPException(
            429, f"Dein Wochenlimit ({p['weekly_limit']} Einladungen) ist erreicht."
        )


def _place_text(db, ws, contact: Contact) -> str:
    from app.multichannel import ContactPoint

    company = db.get(Company, contact.company_id) if contact.company_id else None
    postal = db.scalars(
        select(ContactPoint.value).where(
            ContactPoint.workspace_id == ws,
            ContactPoint.contact_id == contact.id,
            ContactPoint.channel == "postal",
        )
    ).all()
    return " ".join(
        [contact.location or "", company.location if company else "", *postal]
    ).casefold()


def territory_match(place: str, territory: list[str]) -> bool:
    for term in territory:
        term = term.strip().casefold()
        if not term:
            continue
        if term.isdigit():
            # Postcode prefix: "779" matches 77933 Lahr.
            if any(
                token.startswith(term)
                for token in place.replace(",", " ").split()
                if token.isdigit()
            ):
                return True
        elif term in place:
            return True
    return False


def assign(db, ws, contact: Contact, user_id):
    from app.flows import FlowTask

    contact.owner_id = user_id
    contact.version += 1
    for task in db.scalars(
        select(FlowTask).where(
            FlowTask.workspace_id == ws,
            FlowTask.contact_id == contact.id,
            FlowTask.state.in_(["open", "blocked"]),
        )
    ):
        task.assignee_id = user_id


def register_team_mode_routes(app, db_session, scope, record, audit):
    def admin(member):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Nur Owner oder Admin.")

    def members_of(db, ws):
        return db.execute(
            select(Membership.user_id, Membership.role, User.name, User.email)
            .join(User, User.id == Membership.user_id)
            .where(Membership.workspace_id == ws)
            .order_by(User.name, User.email)
        ).all()

    @app.get("/v1/workspaces/{ws}/team/pace")
    def team_pace(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        from app.flows import FlowTask

        rows = []
        for user_id, role, name, email in members_of(db, ws):
            rows.append(
                {
                    "user_id": user_id,
                    "name": name or email,
                    "role": role,
                    "contacts": db.scalar(
                        select(func.count(Contact.id)).where(
                            Contact.workspace_id == ws, Contact.owner_id == user_id
                        )
                    ),
                    "open_tasks": db.scalar(
                        select(func.count(FlowTask.id)).where(
                            FlowTask.workspace_id == ws,
                            FlowTask.assignee_id == user_id,
                            FlowTask.state == "open",
                        )
                    ),
                    "is_me": user_id == member.user_id,
                }
                | pace(db, ws, user_id)
            )
        unassigned = db.scalar(
            select(func.count(Contact.id)).where(
                Contact.workspace_id == ws, Contact.owner_id.is_(None)
            )
        )
        return {
            "members": rows,
            "unassigned": unassigned,
            "notice": "Gezählt werden Einladungen, die du in Heute als gesendet markierst. "
            "LinkedIn selbst wird nie abgefragt.",
        }

    @app.put("/v1/workspaces/{ws}/team/members/{user_id}/settings")
    def save_member_settings(
        ws: str,
        user_id: str,
        body: MemberSettingsInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        if user_id != member.user_id:
            admin(member)
        if not db.get(Membership, (ws, user_id)):
            raise HTTPException(404, "Mitglied nicht gefunden.")
        if body.daily_invite_limit > body.weekly_invite_limit:
            raise HTTPException(422, "Das Tageslimit darf nicht über dem Wochenlimit liegen.")
        item = member_settings(db, ws, user_id)
        item.daily_invite_limit = body.daily_invite_limit
        item.weekly_invite_limit = body.weekly_invite_limit
        item.territory = [t.strip()[:60] for t in body.territory if t.strip()]
        item.receives_leads = body.receives_leads
        item.updated_at = now()
        audit(
            db,
            ws,
            member.user_id,
            "member_settings",
            "Tempo und Gebiet eines Mitglieds gespeichert",
        )
        return pace(db, ws, user_id)

    @app.post("/v1/workspaces/{ws}/team/distribute")
    def distribute(
        ws: str,
        body: DistributeInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        admin(member)
        receivers = []
        for user_id, role, _name, _email in members_of(db, ws):
            settings = member_settings(db, ws, user_id)
            if settings.receives_leads and role in ("owner", "admin", "editor"):
                receivers.append((user_id, settings.territory))
        if not receivers:
            raise HTTPException(409, "Niemand im Team nimmt Leads an.")
        stmt = select(Contact).where(Contact.workspace_id == ws)
        if body.only_unassigned:
            stmt = stmt.where(Contact.owner_id.is_(None))
        if body.route != "any":
            stmt = stmt.where(Contact.channel_route == body.route)
        contacts = db.scalars(stmt.order_by(Contact.created_at, Contact.id).limit(5000)).all()
        counts = {user_id: 0 for user_id, _ in receivers}
        unmatched = 0
        rotation = cycle([user_id for user_id, _ in receivers])
        for contact in contacts:
            if body.mode == "territory":
                place = _place_text(db, ws, contact)
                owner = next((u for u, terms in receivers if territory_match(place, terms)), None)
                if owner is None:
                    unmatched += 1
                    continue
            else:
                owner = next(rotation)
            assign(db, ws, contact, owner)
            counts[owner] += 1
        audit(
            db,
            ws,
            member.user_id,
            "leads_distributed",
            f"Leads verteilt ({body.mode}): {sum(counts.values())}",
        )
        return {"assigned": counts, "unmatched": unmatched, "total": len(contacts)}
