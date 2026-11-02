"""Official LinkedIn OAuth and Posts adapters; no scraping or automated DMs.

OAuth and text Posts payload verified against linkedin-developers' official Python
client sources on 2026-11-01. Configure a currently supported API version and
explicitly attest product access; there is deliberately no guessed version default.
"""

import os
import re
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import BaseModel, Field

from app.providers.ai import ProviderError, configured, request_json


class OAuthConnection(BaseModel):
    access_token: str = Field(repr=False)
    expires_in: int = Field(gt=0)
    scopes: list[str]
    author_urn: str
    display_name: str


def _operator_approved():
    if os.getenv("LINKEDIN_PUBLISHING_APPROVED", "false").lower() != "true":
        raise ProviderError("provider_approval_required")


def authorization_url(state: str) -> str:
    if not 20 <= len(state) <= 200:
        raise ProviderError("invalid_oauth_state")
    client_id, redirect = configured("LINKEDIN_CLIENT_ID"), configured("LINKEDIN_REDIRECT_URI")
    parsed = urlsplit(redirect)
    if parsed.scheme != "https" and not (
        os.getenv("APP_ENV", "development") in ("development", "test")
        and parsed.scheme == "http"
        and parsed.hostname in ("localhost", "127.0.0.1")
    ):
        raise ProviderError("invalid_provider_configuration")
    if parsed.username or parsed.password or parsed.fragment:
        raise ProviderError("invalid_provider_configuration")
    return "https://www.linkedin.com/oauth/v2/authorization?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect,
            "scope": "openid profile w_member_social",
            "state": state,
        }
    )


def exchange_code(code: str, *, client=None) -> OAuthConnection:
    if not code or len(code) > 4000:
        raise ProviderError("invalid_oauth_code")
    data, _ = request_json(
        "POST",
        "https://www.linkedin.com/oauth/v2/accessToken",
        client=client,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": configured("LINKEDIN_REDIRECT_URI"),
            "client_id": configured("LINKEDIN_CLIENT_ID"),
            "client_secret": configured("LINKEDIN_CLIENT_SECRET"),
        },
    )
    token = data.get("access_token")
    expiry = data.get("expires_in")
    if (
        not isinstance(token, str)
        or not token
        or not isinstance(expiry, int)
        or isinstance(expiry, bool)
        or expiry <= 0
    ):
        raise ProviderError("invalid_provider_response")
    # Absent scope is not evidence of a grant. Introspection is official but not
    # necessarily available to every app; if absent do not invent capabilities.
    raw_scopes = data.get("scope", "")
    scopes = (
        raw_scopes.replace(",", " ").split()
        if isinstance(raw_scopes, str)
        else (
            raw_scopes
            if isinstance(raw_scopes, list) and all(isinstance(s, str) for s in raw_scopes)
            else []
        )
    )
    profile, _ = request_json(
        "GET",
        "https://api.linkedin.com/v2/userinfo",
        client=client,
        headers={"Authorization": "Bearer " + token},
    )
    subject = profile.get("sub")
    if not isinstance(subject, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", subject):
        raise ProviderError("invalid_provider_response")
    return OAuthConnection(
        access_token=token,
        expires_in=expiry,
        scopes=scopes,
        author_urn="urn:li:person:" + subject,
        display_name=str(profile.get("name") or "LinkedIn member")[:200],
    )


def capabilities(scopes: list[str]) -> dict:
    approved = os.getenv("LINKEDIN_PUBLISHING_APPROVED", "false").lower() == "true"
    return {
        "text_publish": approved and "w_member_social" in scopes,
        "image_publish": approved and "w_member_social" in scopes,
        "company_pages": False,
        "engagement_read": False,
        "automated_dm": False,
    }


def _headers(token, scopes):
    _operator_approved()
    if "w_member_social" not in scopes:
        raise ProviderError("missing_scope")
    version = configured("LINKEDIN_API_VERSION")
    if not re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])", version):
        raise ProviderError("invalid_provider_configuration")
    if not token:
        raise ProviderError("missing_credentials")
    return {
        "Authorization": "Bearer " + token,
        "LinkedIn-Version": version,
        "X-Restli-Protocol-Version": "2.0.0",
    }


def publish_post(
    token: str,
    author_urn: str,
    text: str,
    scopes: list[str],
    *,
    image_urn: str | None = None,
    alt_text: str = "",
    client=None,
) -> dict:
    headers = _headers(token, scopes)
    if (
        not re.fullmatch(r"urn:li:person:[A-Za-z0-9_-]{1,200}", author_urn)
        or not 1 <= len(text) <= 3000
    ):
        raise ProviderError("invalid_publication")
    body = {
        "author": author_urn,
        "commentary": text,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if image_urn:
        if not re.fullmatch(r"urn:li:image:[A-Za-z0-9_-]+", image_urn) or not alt_text.strip():
            raise ProviderError("invalid_image")
        body["content"] = {"media": {"id": image_urn, "altText": alt_text[:1000]}}
    _, response_headers = request_json(
        "POST",
        "https://api.linkedin.com/rest/posts",
        client=client,
        side_effect=True,
        headers=headers,
        json=body,
    )
    receipt = response_headers.get("x-restli-id")
    if not receipt or not receipt.startswith(("urn:li:share:", "urn:li:ugcPost:")):
        raise ProviderError("ambiguous_result", ambiguous=True)
    return {"provider": "linkedin", "external_id": receipt, "id": receipt, "confirmed": True}


def upload_image(
    token: str,
    author_urn: str,
    payload: bytes,
    content_type: str,
    scopes: list[str],
    *,
    client=None,
) -> str:
    headers = _headers(token, scopes)
    if (
        not re.fullmatch(r"urn:li:person:[A-Za-z0-9_-]{1,200}", author_urn)
        or content_type not in ("image/png", "image/jpeg")
        or not 1 <= len(payload) <= 8 * 1024 * 1024
    ):
        raise ProviderError("invalid_image")
    result, _ = request_json(
        "POST",
        "https://api.linkedin.com/rest/images?action=initializeUpload",
        client=client,
        side_effect=True,
        headers=headers,
        json={"initializeUploadRequest": {"owner": author_urn}},
    )
    try:
        upload_url, image = result["value"]["uploadUrl"], result["value"]["image"]
        parsed = urlsplit(upload_url)
        host = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port
            or not (host == "www.linkedin.com" or host.endswith(".licdn.com"))
            or not re.fullmatch(r"urn:li:image:[A-Za-z0-9_-]+", image)
        ):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ProviderError("invalid_provider_response") from None
    upload_headers = {"Content-Type": content_type}
    if host == "www.linkedin.com":
        upload_headers["Authorization"] = "Bearer " + token
    own_client = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False)
    try:
        try:
            response = client.put(upload_url, headers=upload_headers, content=payload)
        except httpx.TransportError:
            raise ProviderError("ambiguous_result", ambiguous=True) from None
        if not response.is_success:
            raise ProviderError("image_upload_failed")
        return image
    finally:
        if own_client:
            client.close()
