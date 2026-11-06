"""Integrations page API: per-workspace encrypted credentials with live connection tests.

Secrets are write-only: responses carry masks (last four characters) and the source
(workspace / environment / missing). Every test is a read-only, non-billable or
minimal request; none sends messages, posts content or creates provider objects.
"""

import os
from urllib.parse import quote

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app import credentials
from app.db import now
from app.platform_models import Connection, IntegrationCredential
from app.providers.ai import ProviderError, request_json


class CredentialInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, str] = Field(default_factory=dict, max_length=10)
    clear: list[str] = Field(default_factory=list, max_length=10)
    test: bool = True


def _client():
    return httpx.Client(timeout=httpx.Timeout(20, connect=10), follow_redirects=False)


def check_openai(client=None) -> dict:
    key, model = credentials.get("LLM_API_KEY"), credentials.get("LLM_MODEL")
    if not key or not model:
        raise ProviderError("missing_credentials")
    base = credentials.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    checked = []
    for name in filter(None, [model, credentials.get("IMAGE_MODEL")]):
        data, _ = request_json(
            "GET",
            base + "/models/" + quote(name, safe=""),
            client=client,
            headers={"Authorization": "Bearer " + key},
        )
        if data.get("id") != name:
            raise ProviderError("model_not_verified")
        checked.append(name)
    return {"detail": "Key gültig, Modelle verfügbar: " + ", ".join(checked)}


CALLBACK_PATH = "/v1/integrations/linkedin/callback"


def check_linkedin_app(client=None) -> dict:
    """Verify the app credentials without issuing a token or touching any profile.

    Live check 2026-11-06: the authorization-code endpoint answers wrong and correct
    credentials identically (401 invalid_request "authorization code not found"), so it
    cannot validate anything. Token introspection with a dummy token does distinguish:
    valid client -> 400 invalid_access_token; wrong secret -> 401 invalid_client;
    wrong client id -> 400 invalid_client_id.
    """
    from urllib.parse import urlsplit

    client_id, secret = (
        credentials.get("LINKEDIN_CLIENT_ID"),
        credentials.get("LINKEDIN_CLIENT_SECRET"),
    )
    redirect = credentials.get("LINKEDIN_REDIRECT_URI")
    if not client_id or not secret or not redirect:
        raise ProviderError("missing_credentials")
    if urlsplit(redirect).path != CALLBACK_PATH:
        raise ProviderError("redirect_uri_path_mismatch")
    own = client is None
    client = client or _client()
    try:
        response = client.post(
            "https://www.linkedin.com/oauth/v2/introspectToken",
            data={
                "token": "prospectos-connection-test",
                "client_id": client_id,
                "client_secret": secret,
            },
        )
    except httpx.TransportError:
        raise ProviderError("provider_unavailable") from None
    finally:
        if own:
            client.close()
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error", "") if isinstance(body, dict) else ""
    if error in ("invalid_client", "invalid_client_id"):
        raise ProviderError("invalid_client_credentials")
    if error == "invalid_access_token" or (response.is_success and "active" in body):
        return {
            "detail": "Client ID und Secret von LinkedIn bestätigt. Redirect-URL: "
            + redirect
            + " (muss exakt so unter „Authorized redirect URLs“ stehen)."
        }
    if response.status_code >= 500:
        raise ProviderError("provider_unavailable")
    raise ProviderError("provider_rejected")


def check_osm(client=None) -> dict:
    from app.providers.osm import DEFAULT_NOMINATIM, _endpoint, _user_agent

    contact = credentials.get("OSM_CONTACT")
    if not contact:
        raise ProviderError("missing_credentials")
    base = _endpoint("OSM_NOMINATIM_URL", DEFAULT_NOMINATIM)
    data, _ = request_json(
        "GET",
        base.rstrip("/") + "/status",
        client=client,
        params={"format": "json"},
        headers={"User-Agent": _user_agent()},
    )
    if data.get("status") != 0:
        raise ProviderError("provider_unavailable")
    return {"detail": "Nominatim erreichbar; Kontaktangabe wird im User-Agent gesendet."}


def check_brave(client=None) -> dict:
    key = credentials.get("BRAVE_SEARCH_API_KEY")
    if not key:
        raise ProviderError("missing_credentials")
    data, headers = request_json(
        "GET",
        "https://api.search.brave.com/res/v1/web/search",
        client=client,
        params={"q": "Offenburg", "count": 1},
        headers={"Accept": "application/json", "X-Subscription-Token": key},
    )
    remaining = headers.get("x-ratelimit-remaining", "")
    return {
        "detail": "Such-API antwortet (1 Anfrage verbraucht)."
        + (f" Verbleibendes Kontingent: {remaining}." if remaining else "")
    }


def check_northdata(client=None) -> dict:
    from app.providers.northdata import test_connection

    return test_connection(client=client)


TESTS = {
    "openai": check_openai,
    "linkedin": check_linkedin_app,
    "osm": check_osm,
    "brave": check_brave,
    "northdata": check_northdata,
}

ERRORS = {
    "missing_credentials": "Pflichtangaben fehlen.",
    "provider_forbidden": "Zugang abgelehnt (Key ungültig oder ohne Berechtigung).",
    "invalid_client_credentials": "Client ID oder Secret ungültig (von LinkedIn abgelehnt).",
    "redirect_uri_path_mismatch": "LINKEDIN_REDIRECT_URI muss auf /v1/integrations/linkedin/callback enden.",
    "model_not_verified": "Modell für diesen Key nicht verfügbar.",
    "not_found": "Modell oder Endpunkt nicht gefunden.",
    "rate_limited": "Rate-Limit erreicht, später erneut testen.",
    "provider_unavailable": "Anbieter nicht erreichbar.",
    "provider_rejected": "Anbieter hat die Anfrage abgelehnt.",
    "feature_disabled": "Adapter per Feature-Flag deaktiviert.",
}


def describe(db, ws: str, provider: str, linkedin_connection=None) -> dict:
    spec = credentials.PROVIDERS[provider]
    stored, item = credentials.stored_fields(db, ws, provider)
    demo = credentials.is_demo(db, ws)
    if demo:
        stored = {}
    fields = []
    missing = []
    for field in spec["fields"]:
        value = stored.get(field.env) or ""
        # Computed from this transaction's row + environment (not the lazy request cache).
        env_value = "" if demo else os.getenv(field.env, "").strip()
        src = "workspace" if value else ("environment" if env_value else "missing")
        if src == "environment":
            value = env_value
        if field.required and src == "missing":
            missing.append(field.env)
        fields.append(
            {
                "name": field.env,
                "label": field.label,
                "secret": field.secret,
                "required": field.required,
                "hint": field.hint,
                "source": src,
                "masked": credentials.mask(value, field.secret),
            }
        )
    if missing:
        status = "missing"
    elif item and item.status == "error":
        status = "error"
    elif item and item.status == "connected":
        status = "connected"
    else:
        status = "untested"
    result = {
        "provider": provider,
        "label": spec["label"],
        "purpose": spec["purpose"],
        "fields": fields,
        "status": status,
        "missing": missing,
        "last_tested_at": item.last_tested_at if item else None,
        "last_error": item.last_error if item else "",
        "last_message": (item.masked or {}).get("_message", "") if item else "",
    }
    if provider == "linkedin":
        result["account"] = (
            {
                "connected": True,
                "author_urn": linkedin_connection.author_urn,
                "scopes": linkedin_connection.scopes,
                "expires_at": linkedin_connection.expires_at,
                "can_post": "w_member_social" in (linkedin_connection.scopes or []),
            }
            if linkedin_connection
            else {"connected": False}
        )
        result["redirect_uri"] = credentials.get("LINKEDIN_REDIRECT_URI")
    return result


def run_test(db, ws: str, provider: str, member_id: str, client=None) -> dict:
    item = db.scalar(
        select(IntegrationCredential)
        .where(IntegrationCredential.workspace_id == ws, IntegrationCredential.provider == provider)
        .with_for_update()
    )
    try:
        outcome = TESTS[provider](client=client)
        status, error, message = "connected", "", outcome["detail"]
    except ProviderError as exc:
        status, error = "error", exc.code
        message = ERRORS.get(exc.code, "Prüfung fehlgeschlagen: " + exc.code)
    if not item:
        item = IntegrationCredential(
            workspace_id=ws,
            provider=provider,
            ciphertext=credentials.encrypt({}),
            masked={},
            updated_by=member_id,
        )
        db.add(item)
    item.status = status
    item.last_error = error[:200]
    item.last_tested_at = now()
    item.masked = {**(item.masked or {}), "_message": message[:300]}
    db.flush()
    return {"status": status, "error": error, "message": message}


def register_integration_routes(app, db_session, scope, audit):
    def owner_admin(member):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Nur Owner/Admin dürfen Zugangsdaten verwalten.")

    def known(provider):
        if provider not in credentials.PROVIDERS:
            raise HTTPException(404, "Unbekannte Integration.")

    def linkedin_connection(db, ws):
        return db.scalar(
            select(Connection).where(
                Connection.workspace_id == ws, Connection.provider == "linkedin"
            )
        )

    @app.get("/v1/workspaces/{ws}/integrations/credentials")
    def list_integrations(ws: str, member=Depends(scope), db=Depends(db_session, scope="function")):
        owner_admin(member)
        connection = linkedin_connection(db, ws)
        return {
            "encryption_ready": credentials.encryption_ready(),
            "items": [describe(db, ws, p, connection) for p in credentials.PROVIDERS],
        }

    @app.put("/v1/workspaces/{ws}/integrations/credentials/{provider}")
    def save_integration(
        ws: str,
        provider: str,
        body: CredentialInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        owner_admin(member)
        known(provider)
        credentials.refuse_in_demo(db, ws)
        allowed = {f.env: f for f in credentials.PROVIDERS[provider]["fields"]}
        unknown = (set(body.values) | set(body.clear)) - set(allowed)
        if unknown:
            raise HTTPException(422, "Unbekannte Felder: " + ", ".join(sorted(unknown)))
        for name, value in body.values.items():
            if len(value) > 2000 or "\n" in value or "\r" in value:
                raise HTTPException(422, f"{name}: ungültiger Wert.")
        credentials.cipher()  # 503 without TOKEN_ENCRYPTION_KEY
        stored, item = credentials.stored_fields(db, ws, provider)
        if item:
            db.refresh(item, with_for_update=True)
        stored.update({k: v.strip() for k, v in body.values.items() if v.strip()})
        for name in body.clear:
            stored.pop(name, None)
        masked = {
            name: credentials.mask(value, allowed[name].secret) for name, value in stored.items()
        }
        if not item:
            item = IntegrationCredential(
                workspace_id=ws, provider=provider, updated_by=member.user_id
            )
            db.add(item)
        item.ciphertext = credentials.encrypt(stored)
        item.masked = masked
        item.status = "untested"
        item.last_error = ""
        item.updated_by = member.user_id
        item.updated_at = now()
        db.flush()
        audit(
            db,
            ws,
            member.user_id,
            "integration_saved",
            f"Integration {provider}: fields {', '.join(sorted(stored)) or 'none'} stored encrypted",
        )
        test = None
        if body.test:
            with credentials.override(stored):
                test = run_test(db, ws, provider, member.user_id)
        return {"item": describe(db, ws, provider, linkedin_connection(db, ws)), "test": test}

    @app.post("/v1/workspaces/{ws}/integrations/credentials/{provider}/test")
    def test_integration(
        ws: str, provider: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        owner_admin(member)
        known(provider)
        credentials.refuse_in_demo(db, ws)
        with credentials.workspace(db, ws):
            test = run_test(db, ws, provider, member.user_id)
        audit(
            db,
            ws,
            member.user_id,
            "integration_tested",
            f"Integration {provider}: {test['status']}",
        )
        return {"item": describe(db, ws, provider, linkedin_connection(db, ws)), "test": test}

    @app.delete("/v1/workspaces/{ws}/integrations/credentials/{provider}")
    def delete_integration(
        ws: str, provider: str, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        owner_admin(member)
        known(provider)
        _, item = credentials.stored_fields(db, ws, provider)
        if item:
            db.delete(item)
            db.flush()
        audit(db, ws, member.user_id, "integration_removed", f"Integration {provider} removed")
        return {"item": describe(db, ws, provider, linkedin_connection(db, ws))}
