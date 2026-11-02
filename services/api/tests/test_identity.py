import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
from argon2 import PasswordHasher
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app import identity
from app.db import SessionLocal, now
from app.identity import Invite, auth_settings, authenticate_supabase, verify_supabase_token
from app.main import app
from app.models import Audit, AuthSession, Membership, User


def provider_settings(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_PROVIDER", "supabase")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("APP_BASE_URL", "https://prospectos.example.test")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-test-key")
    return auth_settings()


@pytest.fixture
def signing():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update(kid="test-signing-key", alg="RS256", use="sig")
    claims = {
        "iss": "https://project.supabase.co/auth/v1",
        "aud": "authenticated",
        "sub": str(uuid4()),
        "email": "member@example.test",
        "role": "authenticated",
        "iat": int(now().timestamp()),
        "exp": int((now() + timedelta(minutes=30)).timestamp()),
    }
    return private, jwk, claims


def response(status, body):
    return httpx.Response(
        status, json=body, request=httpx.Request("GET", "https://project.supabase.co/auth/v1")
    )


def token(signing, changes=None, key=None):
    private, _, claims = signing
    return jwt.encode(
        claims | (changes or {}),
        key or private,
        algorithm="RS256",
        headers={"kid": "test-signing-key"},
    )


def mock_jwks(monkeypatch, signing):
    identity._jwks_cache.clear()
    monkeypatch.setattr(
        identity.httpx, "get", lambda *args, **kwargs: response(200, {"keys": [signing[1]]})
    )


def test_verified_supabase_identity_has_no_token_persistence(monkeypatch, signing):
    provider_settings(monkeypatch)
    mock_jwks(monkeypatch, signing)
    captured = {}

    def exchange(url, **kwargs):
        captured.update(url=url, **kwargs)
        return response(
            200,
            {
                "access_token": token(signing),
                "refresh_token": "must-not-be-stored",
                "user": {
                    "id": signing[2]["sub"],
                    "email": signing[2]["email"],
                    "email_confirmed_at": now().isoformat(),
                },
            },
        )

    monkeypatch.setattr(identity.httpx, "post", exchange)
    result = authenticate_supabase("member@example.test", "private-input")
    assert result == signing[2]
    assert captured["params"] == {"grant_type": "password"}
    assert captured["headers"] == {"apikey": "public-test-key"}
    assert captured["timeout"] == 10 and captured["follow_redirects"] is False
    assert "refresh_token" not in result and "access_token" not in result


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "another-app"},
        {"iss": "https://evil.example/auth/v1"},
        {"exp": 1},
        {"role": "service_role"},
        {"sub": "not-a-uuid"},
    ],
)
def test_signature_claims_fail_closed(monkeypatch, signing, changes):
    settings = provider_settings(monkeypatch)
    mock_jwks(monkeypatch, signing)
    with pytest.raises(HTTPException) as failure:
        verify_supabase_token(token(signing, changes), settings)
    assert failure.value.status_code == 401


def test_tampered_signature_and_legacy_hs256_rejected(monkeypatch, signing):
    settings = provider_settings(monkeypatch)
    mock_jwks(monkeypatch, signing)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for bad in (
        token(signing, key=other_key),
        jwt.encode(
            signing[2],
            "unsupported-test-secret-that-is-long-enough",
            algorithm="HS256",
            headers={"kid": "test-signing-key"},
        ),
    ):
        with pytest.raises(HTTPException) as failure:
            verify_supabase_token(bad, settings)
        assert failure.value.status_code == 401


def test_unconfirmed_email_or_provider_failure_is_not_login(monkeypatch, signing):
    provider_settings(monkeypatch)
    mock_jwks(monkeypatch, signing)
    monkeypatch.setattr(
        identity.httpx,
        "post",
        lambda *args, **kwargs: response(
            200,
            {
                "access_token": token(signing),
                "user": {"id": signing[2]["sub"], "email": signing[2]["email"]},
            },
        ),
    )
    with pytest.raises(HTTPException) as failure:
        authenticate_supabase("member@example.test", "anything")
    assert failure.value.status_code == 401
    monkeypatch.setattr(
        identity.httpx,
        "post",
        lambda *args, **kwargs: response(503, {"message": "sensitive provider response"}),
    )
    with pytest.raises(HTTPException) as failure:
        authenticate_supabase("member@example.test", "anything")
    assert failure.value.status_code == 503
    assert "sensitive" not in str(failure.value.detail)


def test_production_requires_secure_config(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_PROVIDER", "demo")
    with pytest.raises(RuntimeError, match="Production auth"):
        auth_settings()
    monkeypatch.setenv("AUTH_PROVIDER", "supabase")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    with pytest.raises(RuntimeError, match="COOKIE_SECURE"):
        auth_settings()
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("SUPABASE_URL", "http://localhost")
    with pytest.raises(RuntimeError, match="HTTPS"):
        auth_settings()


def test_establish_user_refuses_email_based_linking(context, admin, signing):
    _, _, actor = context
    existing = admin.get(User, actor)
    with pytest.raises(HTTPException) as failure:
        identity.establish_supabase_user(admin, signing[2] | {"email": existing.email})
    assert failure.value.status_code == 409
    assert existing.auth_subject is None


def test_external_subject_and_session_lifetime(context, admin, signing, monkeypatch):
    _, _, actor = context
    user = admin.get(User, actor)
    user.auth_subject = signing[2]["iss"] + ":" + signing[2]["sub"]
    admin.flush()
    claims = signing[2] | {
        "email": user.email,
        "exp": int((now() + timedelta(minutes=5)).timestamp()),
    }
    assert identity.establish_supabase_user(admin, claims).id == actor
    monkeypatch.setenv("COOKIE_SECURE", "true")
    result = Response()
    session = identity.create_session(admin, user, result, claims)
    assert session.expires_at <= now() + timedelta(minutes=5)
    cookie = result.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=lax" in cookie
    assert session.token_hash not in cookie


def test_invitation_source_role_and_last_owner_guards(context, admin):
    client, (ws, _, private), actor = context
    base = f"/v1/workspaces/{ws}"
    assert (
        client.post(
            base + "/invites", json={"email": "person@example.test", "role": "owner"}
        ).status_code
        == 422
    )
    assert client.patch(base + f"/members/{actor}", json={"role": "editor"}).status_code == 409
    result = client.post(base + "/invites", json={"email": "person@example.test", "role": "editor"})
    assert result.status_code == 201, result.text
    data = result.json()
    stored = admin.get(Invite, data["id"])
    assert stored.token_hash == hashlib.sha256(data["token"].encode()).hexdigest()
    assert data["token"] != stored.token_hash and data["delivery"] == "manual"
    with SessionLocal() as db:
        assert db.scalar(select(Invite).where(Invite.id == stored.id)) is None
    assert (
        client.post(
            f"/v1/workspaces/{private}/invites", json={"email": "person@example.test"}
        ).status_code
        == 404
    )
    membership = admin.get(Membership, (ws, actor))
    membership.role = "editor"
    admin.commit()
    assert client.post(base + "/invites", json={"email": "another@example.test"}).status_code == 403
    assert client.patch(base + f"/members/{actor}", json={"role": "owner"}).status_code == 403


def test_invitation_accept_is_email_bound_single_use_and_tenant_scoped(context, admin):
    client, (ws, *_), _ = context
    marker = str(uuid4())
    other = User(
        email=f"{marker}@example.test",
        name="Invitation recipient",
        password_hash=PasswordHasher().hash("RecipientPassword!"),
    )
    admin.add(other)
    admin.commit()
    other_id = other.id
    try:
        invitation = client.post(
            f"/v1/workspaces/{ws}/invites", json={"email": other.email, "role": "analyst"}
        ).json()
        # Signed-in owner is not the recipient and cannot steal the invitation.
        assert client.post(f"/v1/invites/{invitation['token']}/accept").status_code == 403
        with TestClient(app) as recipient:
            login = recipient.post(
                "/v1/auth/demo", json={"email": other.email, "password": "RecipientPassword!"}
            )
            assert login.status_code == 200, login.text
            recipient.headers["X-CSRF-Token"] = login.json()["csrf_token"]
            accepted = recipient.post(f"/v1/invites/{invitation['token']}/accept")
            assert accepted.status_code == 200, accepted.text
            assert accepted.json() == {"workspace_id": ws, "role": "analyst"}
            assert recipient.post(f"/v1/invites/{invitation['token']}/accept").status_code == 404
            assert recipient.get(f"/v1/workspaces/{ws}/contacts").status_code == 200
            assert (
                recipient.post(
                    f"/v1/workspaces/{ws}/contacts", json={"first_name": "Forbidden"}
                ).status_code
                == 403
            )
    finally:
        admin.rollback()
        admin.execute(delete(Audit).where(Audit.actor_id == other_id))
        admin.execute(delete(AuthSession).where(AuthSession.user_id == other_id))
        admin.execute(delete(Membership).where(Membership.user_id == other_id))
        admin.execute(delete(User).where(User.id == other_id))
        admin.commit()


def test_invitation_expiry_and_admin_cannot_grant_owner(context, admin):
    client, (ws, *_), actor = context
    invitation = client.post(
        f"/v1/workspaces/{ws}/invites", json={"email": admin.get(User, actor).email}
    ).json()
    row = admin.get(Invite, invitation["id"])
    row.expires_at = now() - timedelta(seconds=1)
    admin.commit()
    assert client.post(f"/v1/invites/{invitation['token']}/accept").status_code == 404
    membership = admin.get(Membership, (ws, actor))
    membership.role = "admin"
    admin.commit()
    assert (
        client.post(
            f"/v1/workspaces/{ws}/invites", json={"email": "new@example.test", "role": "admin"}
        ).status_code
        == 403
    )
    assert (
        client.patch(f"/v1/workspaces/{ws}/members/{actor}", json={"role": "owner"}).status_code
        == 403
    )


def test_es256_keys_are_supported(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import ec

    settings = provider_settings(monkeypatch)
    private = ec.generate_private_key(ec.SECP256R1())
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    jwk.update(kid="ec-signing-key", alg="ES256", use="sig")
    identity._jwks_cache.clear()
    monkeypatch.setattr(
        identity.httpx, "get", lambda *args, **kwargs: response(200, {"keys": [jwk]})
    )
    claims = {
        "iss": settings.issuer,
        "aud": settings.audience,
        "sub": str(uuid4()),
        "email": "ec@example.test",
        "role": "authenticated",
        "iat": int(now().timestamp()),
        "exp": int((now() + timedelta(minutes=5)).timestamp()),
    }
    access = jwt.encode(claims, private, algorithm="ES256", headers={"kid": "ec-signing-key"})
    assert verify_supabase_token(access, settings) == claims


def test_production_login_session_and_demo_gate(context, admin, signing, monkeypatch):
    existing_client, (ws, *_), actor = context
    user = admin.get(User, actor)
    user.auth_subject = signing[2]["iss"] + ":" + signing[2]["sub"]
    admin.commit()
    provider_settings(monkeypatch)
    monkeypatch.delenv("DATABASE_ADMIN_URL", raising=False)
    mock_jwks(monkeypatch, signing)
    assert existing_client.get("/v1/me").status_code == 401
    claims = signing[2] | {"email": user.email}
    access = jwt.encode(claims, signing[0], algorithm="RS256", headers={"kid": "test-signing-key"})
    monkeypatch.setattr(
        identity.httpx,
        "post",
        lambda *args, **kwargs: response(
            200,
            {
                "access_token": access,
                "user": {
                    "id": claims["sub"],
                    "email": claims["email"],
                    "email_confirmed_at": now().isoformat(),
                },
            },
        ),
    )
    with TestClient(app, base_url="https://testserver") as client:
        config = client.get("/v1/auth/config")
        assert config.json() == {"mode": "supabase", "demo_enabled": False}
        assert (
            client.post(
                "/v1/auth/demo", json={"email": user.email, "password": "TestPassword!2026"}
            ).status_code
            == 403
        )
        result = client.post(
            "/v1/auth/login", json={"email": user.email, "password": "external-provider-password"}
        )
        assert result.status_code == 200, result.text
        assert result.json()["user"]["id"] == actor
        assert "access_token" not in result.json()
        assert client.get("/v1/me").status_code == 200
        assert client.get(f"/v1/workspaces/{ws}/contacts").status_code == 200


def test_login_rate_limit_persists_failed_attempts_across_transactions(admin):
    host = "identity-test-" + str(uuid4())
    bucket = hashlib.sha256(("auth-login:" + host).encode()).hexdigest()
    try:
        with SessionLocal() as db:
            for _ in range(10):
                identity._rate_limit(db, host)
                db.rollback()  # A rejected authentication cannot undo the stored counter.
            with pytest.raises(HTTPException) as failure:
                identity._rate_limit(db, host)
            assert failure.value.status_code == 429
    finally:
        admin.execute(
            delete(identity.AuthRateBucket).where(identity.AuthRateBucket.bucket == bucket)
        )
        admin.commit()
