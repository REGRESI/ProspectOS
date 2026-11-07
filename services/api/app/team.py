"""Team: invite more users into a workspace (Inhaber or Mitglied).

There is no system mailing yet (no SMTP sender for system mails is configured), so an
invitation returns a one-time link to copy; nothing is emailed. The link opens
/einladung#<token>; the token never reaches server logs as a query parameter.

Accepting:
- An existing user signs in and accepts (``/v1/invites/{token}/accept``, email must match).
- In local demo authentication a new user sets name and password on the invite page
  (``/v1/invites/{token}/register``). This is development-only local auth, like the
  demo login itself; production identity stays with the configured provider.

Each user keeps an own LinkedIn connection and an own writing profile. Contacts belong
to the member who sends the first request, posts to their author.
"""

import hashlib
import os
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text

from app.db import now
from app.identity import Invite, auth_settings
from app.models import AuthSession, Membership, User, Workspace

ROLE_LABELS = {
    "owner": "Inhaber",
    "admin": "Mitglied",
    "editor": "Mitglied",
    "approver": "Mitglied",
    "analyst": "Mitglied",
}
INVITE_DAYS = 7


class TeamInvite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=254)
    role: str = Field(pattern="^(owner|member)$")

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if "@" not in value or " " in value or "." not in value.split("@")[-1]:
            raise ValueError("Bitte eine gültige E-Mail-Adresse eingeben.")
        return value.lower()


class Register(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=256)


def _lookup(db, token: str) -> Invite:
    if len(token) > 200:
        raise HTTPException(404, "Einladung ungültig oder abgelaufen.")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    # SECURITY DEFINER: returns only the workspace of this exact, open, unexpired capability.
    workspace_id = db.scalar(
        text("SELECT invitation_workspace(:token_hash)"), {"token_hash": token_hash}
    )
    if not workspace_id:
        raise HTTPException(404, "Einladung ungültig oder abgelaufen.")
    db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": workspace_id})
    item = db.scalar(select(Invite).where(Invite.token_hash == token_hash).with_for_update())
    if not item or item.accepted_at or item.expires_at <= now():
        raise HTTPException(404, "Einladung ungültig oder abgelaufen.")
    return item


def invite_link(request: Request, token: str) -> str:
    base = os.getenv("APP_BASE_URL", "").rstrip("/")
    if not base:
        origin = request.headers.get("origin") or ""
        base = origin.rstrip("/") or "http://localhost:3000"
    return f"{base}/einladung#{token}"


def system_mail_ready() -> bool:
    # No system mailer exists yet; invitations are always handed over as a link.
    return False


def register_team_routes(app, db_session, scope, audit):
    from app.main import auth_payload

    def admin(member):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Nur Inhaber dürfen Nutzer einladen.")

    @app.get("/v1/workspaces/{ws}/team")
    def team(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        rows = db.execute(
            select(User, Membership.role)
            .join(Membership, User.id == Membership.user_id)
            .where(Membership.workspace_id == ws)
            .order_by(User.name)
        ).all()
        invites = db.scalars(
            select(Invite)
            .where(Invite.workspace_id == ws, Invite.accepted_at.is_(None))
            .order_by(Invite.created_at.desc())
        ).all()
        return {
            "members": [
                {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "role": role,
                    "role_label": ROLE_LABELS.get(role, "Mitglied"),
                    "me": user.id == member.user_id,
                }
                for user, role in rows
            ],
            "invites": [
                {
                    "id": i.id,
                    "email": i.email,
                    "role": i.role,
                    "role_label": ROLE_LABELS.get(i.role, "Mitglied"),
                    "expires_at": i.expires_at,
                    "expired": i.expires_at <= now(),
                }
                for i in invites
            ],
            "mail": "link" if not system_mail_ready() else "email",
            "can_invite": member.role in ("owner", "admin"),
        }

    @app.post("/v1/workspaces/{ws}/team/invites", status_code=201)
    def invite(
        ws: str,
        body: TeamInvite,
        request: Request,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        admin(member)
        if body.role == "owner" and member.role != "owner":
            raise HTTPException(403, "Nur Inhaber dürfen weitere Inhaber einladen.")
        existing = db.scalar(
            select(User.id)
            .join(Membership, User.id == Membership.user_id)
            .where(Membership.workspace_id == ws, User.email == body.email)
        )
        if existing:
            raise HTTPException(409, "Diese Person ist schon im Workspace.")
        for old in db.scalars(
            select(Invite).where(
                Invite.workspace_id == ws, Invite.email == body.email, Invite.accepted_at.is_(None)
            )
        ):
            db.delete(old)
        raw = secrets.token_urlsafe(40)
        item = Invite(
            workspace_id=ws,
            email=body.email,
            role="owner" if body.role == "owner" else "editor",
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            created_by=member.user_id,
            expires_at=now() + timedelta(days=INVITE_DAYS),
        )
        db.add(item)
        db.flush()
        audit(
            db, ws, member.user_id, "member_invited", "Einladung als Link erstellt (keine E-Mail)"
        )
        return {
            "id": item.id,
            "email": item.email,
            "role_label": ROLE_LABELS[item.role],
            "link": invite_link(request, raw),
            "expires_at": item.expires_at,
            "delivery": "link",
            "notice": "Es gibt noch kein System-Mailing. Schick den Link selbst, er gilt 7 Tage und nur einmal.",
        }

    @app.delete("/v1/workspaces/{ws}/team/invites/{entity_id}")
    def revoke(
        ws: str, entity_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        admin(member)
        item = db.scalar(select(Invite).where(Invite.workspace_id == ws, Invite.id == entity_id))
        if not item or item.accepted_at:
            raise HTTPException(404, "Einladung nicht gefunden.")
        db.delete(item)
        audit(db, ws, member.user_id, "invite_revoked", "Einladung zurückgezogen")
        return {"deleted": True}

    @app.delete("/v1/workspaces/{ws}/team/members/{user_id}")
    def remove_member(
        ws: str, user_id: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if member.role != "owner":
            raise HTTPException(403, "Nur Inhaber dürfen Nutzer entfernen.")
        if user_id == member.user_id:
            raise HTTPException(409, "Du kannst dich nicht selbst entfernen.")
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:ws, 2))"), {"ws": ws})
        target = db.get(Membership, (ws, user_id))
        if not target:
            raise HTTPException(404, "Mitglied nicht gefunden.")
        if target.role == "owner":
            owners = db.scalars(
                select(Membership.user_id).where(
                    Membership.workspace_id == ws, Membership.role == "owner"
                )
            ).all()
            if len(owners) <= 1:
                raise HTTPException(409, "Der letzte Inhaber kann nicht entfernt werden.")
        from app.models import Contact

        # Contacts stay in the workspace; their owner is cleared.
        for contact in db.scalars(
            select(Contact).where(Contact.workspace_id == ws, Contact.owner_id == user_id)
        ):
            contact.owner_id = None
        db.flush()
        db.delete(target)
        audit(db, ws, member.user_id, "member_removed", "Mitglied entfernt")
        return {"deleted": True}

    @app.get("/v1/invites/{token}")
    def preview(token: str, db=Depends(db_session, scope="function")):
        item = _lookup(db, token)
        workspace = db.get(Workspace, item.workspace_id)
        has_account = bool(db.scalar(select(User.id).where(User.email == item.email)))
        return {
            "email": item.email,
            "workspace": workspace.name if workspace else "",
            "role_label": ROLE_LABELS.get(item.role, "Mitglied"),
            "expires_at": item.expires_at,
            "has_account": has_account,
            "can_register": auth_settings().mode == "demo" and not has_account,
        }

    @app.post("/v1/invites/{token}/register")
    def register(
        token: str,
        body: Register,
        response: Response,
        db=Depends(db_session, scope="function"),
    ):
        if auth_settings().mode != "demo":
            raise HTTPException(403, "Konten werden über die Anmeldung des Anbieters angelegt.")
        item = _lookup(db, token)
        if db.scalar(select(User.id).where(User.email == item.email)):
            raise HTTPException(409, "Für diese E-Mail gibt es schon ein Konto. Bitte anmelden.")
        user = User(
            email=item.email, name=body.name, password_hash=PasswordHasher().hash(body.password)
        )
        db.add(user)
        db.flush()
        db.add(Membership(workspace_id=item.workspace_id, user_id=user.id, role=item.role))
        item.accepted_at = now()
        raw = secrets.token_urlsafe(40)
        session = AuthSession(
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            user_id=user.id,
            csrf_token=secrets.token_urlsafe(32),
            expires_at=now() + timedelta(hours=8),
        )
        db.add(session)
        db.flush()
        response.set_cookie(
            "prospectos_session",
            raw,
            max_age=8 * 3600,
            httponly=True,
            samesite="lax",
            secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            path="/",
        )
        audit(
            db,
            item.workspace_id,
            user.id,
            "invite_accepted",
            "Einladung angenommen, Konto angelegt",
        )
        return auth_payload(db, session) | {"workspace_id": item.workspace_id}
