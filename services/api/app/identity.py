"""Verified external identity and workspace invitations.

Supabase access/refresh tokens are never persisted or returned to the browser.
The API exchanges a validated identity into an existing opaque, short-lived session.
"""

import hashlib
import ipaddress
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import jwt
from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base, now
from app.models import AuthSession, Membership, TenantMixin, User


class Invite(TenantMixin, Base):
    __tablename__ = "workspace_invites"
    email: Mapped[str] = mapped_column(String(254))
    role: Mapped[str] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("workspace_id", "id"),)


class AuthRateBucket(Base):
    __tablename__ = "auth_rate_buckets"
    bucket: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int]
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class AuthSettings:
    mode: str
    supabase_url: str = ""
    anon_key: str = ""
    issuer: str = ""
    audience: str = "authenticated"


def _https_url(value: str, name: str, origin_only: bool = False) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or (parts.port is not None and parts.port != 443)
        or (origin_only and parts.path not in ("", "/"))
    ):
        raise RuntimeError(f"Production auth requires a valid HTTPS {name}")
    try:
        address = ipaddress.ip_address(parts.hostname)
        if not address.is_global:
            raise RuntimeError(f"Production auth cannot use a private IP for {name}")
    except ValueError:
        if parts.hostname in ("localhost", "metadata.google.internal"):
            raise RuntimeError(f"Production auth cannot use localhost for {name}") from None
    return value.rstrip("/")


def auth_settings() -> AuthSettings:
    environment = os.getenv("APP_ENV", "development")
    mode = os.getenv("AUTH_PROVIDER", "supabase" if environment == "production" else "demo")
    if mode not in ("demo", "supabase"):
        raise RuntimeError("Unsupported AUTH_PROVIDER")
    if environment == "production":
        if mode != "supabase":
            raise RuntimeError("Production auth requires AUTH_PROVIDER=supabase")
        if os.getenv("COOKIE_SECURE", "false").lower() != "true":
            raise RuntimeError("Production auth requires COOKIE_SECURE=true and HTTPS")
    if mode == "demo":
        return AuthSettings(mode="demo")
    url = _https_url(os.getenv("SUPABASE_URL", ""), "SUPABASE_URL", origin_only=True)
    key = os.getenv("SUPABASE_ANON_KEY", "")
    if not key:
        raise RuntimeError("Production auth requires SUPABASE_ANON_KEY")
    issuer = _https_url(os.getenv("SUPABASE_JWT_ISSUER", url + "/auth/v1"), "SUPABASE_JWT_ISSUER")
    audience = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    if not audience:
        raise RuntimeError("Production auth requires SUPABASE_JWT_AUDIENCE")
    return AuthSettings(
        mode="supabase", supabase_url=url, anon_key=key, issuer=issuer, audience=audience
    )


_jwks_cache: dict[str, tuple[float, list[dict]]] = {}
_jwks_lock = threading.Lock()


def _get_jwk(settings: AuthSettings, kid: str) -> dict:
    url = settings.supabase_url + "/auth/v1/.well-known/jwks.json"
    with _jwks_lock:
        cached = _jwks_cache.get(url)
        cached_at, keys = cached or (0.0, [])
        matching = [key for key in keys if key.get("kid") == kid]
        age = time.monotonic() - cached_at
        if cached is None or age > 300 or (not matching and age > 30):
            try:
                response = httpx.get(url, timeout=5, follow_redirects=False)
                response.raise_for_status()
                if len(response.content) > 128 * 1024:
                    raise ValueError("JWKS response too large")
                keys = response.json()["keys"]
                if (
                    not isinstance(keys, list)
                    or len(keys) > 30
                    or not all(isinstance(k, dict) for k in keys)
                ):
                    raise ValueError("Invalid JWKS")
                _jwks_cache[url] = (time.monotonic(), keys)
                matching = [key for key in keys if key.get("kid") == kid]
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise HTTPException(
                    503, "Identitätsanbieter ist derzeit nicht erreichbar."
                ) from None
        if len(matching) != 1:
            raise HTTPException(401, "Identitätsnachweis konnte nicht bestätigt werden.")
        return matching[0]


def verify_supabase_token(token: str, settings: AuthSettings) -> dict:
    try:
        if len(token) > 16384:
            raise ValueError("Token too large")
        header = jwt.get_unverified_header(token)
        algorithm, kid = header.get("alg"), header.get("kid")
        if (
            algorithm not in ("RS256", "ES256")
            or not isinstance(kid, str)
            or not 1 <= len(kid) <= 200
        ):
            raise ValueError("Unsupported signing algorithm")
        jwk = _get_jwk(settings, kid)
        if jwk.get("alg", algorithm) != algorithm or jwk.get("use", "sig") != "sig":
            raise ValueError("Signing key mismatch")
        key = jwt.PyJWK.from_dict(jwk, algorithm=algorithm)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=[algorithm],
            audience=settings.audience,
            issuer=settings.issuer,
            leeway=5,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
        UUID(claims["sub"])
        if claims.get("role") != "authenticated" or not isinstance(claims.get("email"), str):
            raise ValueError("A verified user identity is required")
        return claims
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "Identitätsnachweis konnte nicht bestätigt werden.") from None


def authenticate_supabase(email: str, password: str) -> dict:
    settings = auth_settings()
    if settings.mode != "supabase":
        raise HTTPException(503, "Produktive Anmeldung ist noch nicht konfiguriert.")
    try:
        response = httpx.post(
            settings.supabase_url + "/auth/v1/token",
            params={"grant_type": "password"},
            headers={"apikey": settings.anon_key},
            json={"email": email, "password": password},
            timeout=10,
            follow_redirects=False,
        )
        if response.status_code in (400, 401, 403, 422):
            raise HTTPException(401, "E-Mail oder Passwort falsch oder nicht bestätigt.")
        if response.status_code == 429:
            raise HTTPException(429, "Zu viele Anmeldeversuche. Bitte später versuchen.")
        response.raise_for_status()
        if len(response.content) > 128 * 1024:
            raise ValueError("Identity response too large")
        payload = response.json()
        claims = verify_supabase_token(payload["access_token"], settings)
        user = payload["user"]
        if (
            not user.get("email_confirmed_at")
            or user.get("id") != claims["sub"]
            or user.get("email", "").casefold() != claims["email"].casefold()
            or claims["email"].casefold() != email.casefold()
        ):
            raise HTTPException(401, "Bestätigte E-Mail-Adresse erforderlich.")
        return claims
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Identitätsanbieter ist derzeit nicht erreichbar.") from None


def establish_supabase_user(db: Session, claims: dict) -> User:
    subject = claims["iss"] + ":" + claims["sub"]
    user = db.scalar(select(User).where(User.auth_subject == subject).with_for_update())
    if user is None:
        # Linking by matching email alone could grant external users local demo memberships.
        existing = db.scalar(select(User.id).where(User.email == claims["email"].lower()))
        if existing:
            raise HTTPException(
                409, "Eine Kontoverknüpfung muss durch den Betreiber geprüft werden."
            )
        user = User(
            auth_subject=subject,
            email=claims["email"].lower(),
            name=claims["email"].split("@")[0][:120],
            password_hash=PasswordHasher().hash(secrets.token_urlsafe(40)),
        )
        db.add(user)
        db.flush()
    elif user.email != claims["email"].lower():
        if db.scalar(
            select(User.id).where(User.email == claims["email"].lower(), User.id != user.id)
        ):
            raise HTTPException(409, "Die aktualisierte Identität benötigt eine Betreiberprüfung.")
        user.email = claims["email"].lower()
    return user


def create_session(db: Session, user: User, response: Response, claims: dict) -> AuthSession:
    expires_at = min(
        now() + timedelta(hours=1), datetime.fromtimestamp(claims["exp"], tz=now().tzinfo)
    )
    raw = secrets.token_urlsafe(40)
    session = AuthSession(
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        user_id=user.id,
        auth_provider="supabase",
        csrf_token=secrets.token_urlsafe(32),
        expires_at=expires_at,
    )
    db.add(session)
    response.set_cookie(
        "prospectos_session",
        raw,
        max_age=max(1, int((expires_at - now()).total_seconds())),
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )
    return session


def _rate_limit(db: Session, client_host: str):
    bucket = hashlib.sha256(("auth-login:" + client_host).encode()).hexdigest()
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:bucket, 1))"), {"bucket": bucket}
    )
    entry = db.get(AuthRateBucket, bucket)
    if entry is None:
        db.add(AuthRateBucket(bucket=bucket, attempts=1, started_at=now()))
    elif entry.started_at < now() - timedelta(minutes=1):
        entry.started_at, entry.attempts = now(), 1
    elif entry.attempts >= 10:
        raise HTTPException(429, "Zu viele Anmeldeversuche. Bitte eine Minute warten.")
    else:
        entry.attempts += 1
    # The caller's request transaction rolls back on rejected authentication. Persist this
    # security counter independently so failed passwords cannot reset the limit.
    db.commit()


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


ROLES = ("admin", "editor", "approver", "analyst")


class InviteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=254)
    role: str = "editor"

    @field_validator("role")
    @classmethod
    def valid_role(cls, value):
        if value not in ROLES:
            raise ValueError("Owner-Rechte werden nicht per Einladung vergeben.")
        return value

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if "@" not in value or " " in value:
            raise ValueError("Ungültige E-Mail-Adresse")
        return value.lower()


class RoleInput(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def valid_role(cls, value):
        if value not in ("owner", *ROLES):
            raise ValueError("Unbekannte Rolle")
        return value


def register_identity_routes(app, db_session, current_auth, scope, auth_payload, audit):
    @app.get("/v1/auth/config")
    def config():
        settings = auth_settings()
        return {"mode": settings.mode, "demo_enabled": settings.mode == "demo"}

    @app.post("/v1/auth/login")
    def production_login(
        body: Credentials,
        request: Request,
        response: Response,
        db: Session = Depends(db_session, scope="function"),
    ):
        _rate_limit(db, request.client.host if request.client else "local")
        claims = authenticate_supabase(body.email, body.password)
        user = establish_supabase_user(db, claims)
        session = create_session(db, user, response, claims)
        return auth_payload(db, session)

    @app.get("/v1/workspaces/{ws}/members")
    def members(
        ws: str, member=Depends(scope), db: Session = Depends(db_session, scope="function")
    ):
        rows = db.execute(
            select(User, Membership.role)
            .join(Membership, User.id == Membership.user_id)
            .where(Membership.workspace_id == ws)
            .order_by(User.name)
            .limit(100)
        ).all()
        return {
            "items": [
                {"id": user.id, "name": user.name, "email": user.email, "role": role}
                for user, role in rows
            ]
        }

    @app.post("/v1/workspaces/{ws}/invites", status_code=201)
    def invite(
        ws: str,
        body: InviteInput,
        member=Depends(scope),
        db: Session = Depends(db_session, scope="function"),
    ):
        if member.role not in ("owner", "admin") or (
            member.role == "admin" and body.role == "admin"
        ):
            raise HTTPException(403, "Diese Rolle darf diese Einladung nicht ausstellen.")
        raw = secrets.token_urlsafe(40)
        value = Invite(
            workspace_id=ws,
            email=body.email,
            role=body.role,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            created_by=member.user_id,
            expires_at=now() + timedelta(days=3),
        )
        db.add(value)
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "member_invited",
            "Team-Einladung erstellt; Zustellung erfolgt manuell",
        )
        return {
            "id": value.id,
            "token": raw,
            "expires_at": value.expires_at,
            "delivery": "manual",
            "notice": "Einmaliger Einladungslink. Keine E-Mail wurde versendet.",
        }

    @app.post("/v1/invites/{token}/accept")
    def accept_invite(
        token: str,
        request: Request,
        auth=Depends(current_auth),
        db: Session = Depends(db_session, scope="function"),
    ):
        # An opaque invitation is a scoped capability. Client cannot supply a target workspace.
        if len(token) > 200:
            raise HTTPException(404, "Einladung ungültig oder abgelaufen.")
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        # RLS remains fail-closed. A SECURITY DEFINER function returns only the destination
        # for this exact, unexpired, unused capability hash, never arbitrary tenant rows.
        workspace_id = db.scalar(
            text("SELECT invitation_workspace(:token_hash)"), {"token_hash": token_hash}
        )
        if not workspace_id:
            raise HTTPException(404, "Einladung ungültig oder abgelaufen.")
        db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": workspace_id})
        value = db.scalar(select(Invite).where(Invite.token_hash == token_hash).with_for_update())
        user = db.get(User, auth.user_id)
        if not value or value.accepted_at or value.expires_at <= now():
            raise HTTPException(404, "Einladung ungültig oder abgelaufen.")
        if user.email.lower() != value.email:
            raise HTTPException(403, "Einladung gehört einer anderen E-Mail-Adresse.")
        if db.get(Membership, (workspace_id, auth.user_id)):
            raise HTTPException(409, "Bereits Mitglied dieses Workspace.")
        db.add(Membership(workspace_id=workspace_id, user_id=auth.user_id, role=value.role))
        value.accepted_at = now()
        audit(db, workspace_id, auth.user_id, "invite_accepted", "Team-Einladung angenommen")
        return {"workspace_id": workspace_id, "role": value.role}

    @app.patch("/v1/workspaces/{ws}/members/{user_id}")
    def role_change(
        ws: str,
        user_id: str,
        body: RoleInput,
        member=Depends(scope),
        db: Session = Depends(db_session, scope="function"),
    ):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Keine Berechtigung zur Rollenverwaltung.")
        # Serialize ownership transitions and ensure each tenant keeps an owner.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:ws, 2))"), {"ws": ws})
        target = db.get(Membership, (ws, user_id))
        if target is None:
            raise HTTPException(404, "Mitglied nicht gefunden.")
        if member.role != "owner" and (
            target.role in ("owner", "admin") or body.role in ("owner", "admin")
        ):
            raise HTTPException(403, "Nur Owner dürfen administrative Rollen verwalten.")
        if target.role == "owner" and body.role != "owner":
            owners = db.scalars(
                select(Membership.user_id).where(
                    Membership.workspace_id == ws, Membership.role == "owner"
                )
            ).all()
            if len(owners) <= 1:
                raise HTTPException(409, "Der letzte Owner kann nicht herabgestuft werden.")
        target.role = body.role
        audit(db, ws, member.user_id, "member_role_changed", "Mitgliedsrolle aktualisiert")
        return {"id": user_id, "role": target.role}
