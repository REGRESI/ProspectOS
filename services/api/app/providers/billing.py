"""Stripe test-mode checkout and raw-body webhook verification.

Signature algorithm verified against stripe-python/_webhook.py (2026-11-01).
Replay protection belongs in the transactionally unique event ledger at the caller.
"""

import hashlib
import hmac
import json
import os
import re
import time
from urllib.parse import urlsplit

from app.providers.ai import ProviderError, configured, request_json


def verify_webhook(
    payload: bytes,
    signature: str,
    *,
    secret: str | None = None,
    timestamp: int | None = None,
    tolerance: int = 300,
) -> dict:
    secret = secret or configured("STRIPE_WEBHOOK_SECRET")
    if not secret.startswith("whsec_") or len(payload) > 1024 * 1024 or not 1 <= tolerance <= 300:
        raise ProviderError("invalid_webhook")
    try:
        parts = [part.split("=", 1) for part in signature.split(",")]
        times = [value for key, value in parts if key == "t"]
        signatures = [value for key, value in parts if key == "v1"]
        if len(times) != 1 or not signatures:
            raise ValueError()
        created = int(times[0])
        if abs((timestamp if timestamp is not None else int(time.time())) - created) > tolerance:
            raise ValueError()
        signed = str(created).encode() + b"." + payload
        digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(digest, value) for value in signatures):
            raise ValueError()
        event = json.loads(payload)
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("id"), str)
            or not re.fullmatch(r"evt_[A-Za-z0-9_]{1,200}", event["id"])
            or not isinstance(event.get("type"), str)
            or not isinstance(event.get("data", {}).get("object"), dict)
            or event.get("livemode") is not False
        ):
            raise ValueError()
        return event
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ProviderError("invalid_webhook") from None


def _settings():
    key = configured("STRIPE_SECRET_KEY")
    if key.startswith("sk_live_"):
        raise ProviderError("test_mode_required")
    origin = configured("PUBLIC_WEB_URL").rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or not parsed.hostname
    ):
        raise ProviderError("invalid_provider_configuration")
    if parsed.scheme != "https" and not (
        os.getenv("APP_ENV", "development") in ("development", "test")
        and parsed.scheme == "http"
        and parsed.hostname in ("localhost", "127.0.0.1")
    ):
        raise ProviderError("invalid_provider_configuration")
    return key, origin


def _verify_test_mode(key, client):
    # Proxy-injected credentials may be opaque placeholders; a missing visible
    # sk_test prefix does not establish missing access. Confirm mode read-only.
    balance, _ = request_json(
        "GET",
        "https://api.stripe.com/v1/balance",
        client=client,
        headers={"Authorization": "Bearer " + key},
    )
    if balance.get("livemode") is not False:
        raise ProviderError("test_mode_required")


def create_checkout(workspace_id: str, *, customer_id: str | None = None, client=None) -> dict:
    key, origin = _settings()
    _verify_test_mode(key, client)
    price = configured("STRIPE_PRICE_ID")
    if not re.fullmatch(r"price_[A-Za-z0-9_]{1,200}", price) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,100}", workspace_id
    ):
        raise ProviderError("invalid_checkout")
    data = {
        "mode": "subscription",
        "line_items[0][price]": price,
        "line_items[0][quantity]": "1",
        "client_reference_id": workspace_id,
        "metadata[workspace_id]": workspace_id,
        "subscription_data[metadata][workspace_id]": workspace_id,
        "success_url": origin
        + "/settings/billing?checkout=success&session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": origin + "/settings/billing?checkout=cancelled",
    }
    if customer_id:
        if not re.fullmatch(r"cus_[A-Za-z0-9_]{1,200}", customer_id):
            raise ProviderError("invalid_checkout")
        data["customer"] = customer_id
    response, _ = request_json(
        "POST",
        "https://api.stripe.com/v1/checkout/sessions",
        client=client,
        side_effect=True,
        headers={"Authorization": "Bearer " + key},
        data=data,
    )
    session_id, url = response.get("id"), response.get("url")
    if (
        not isinstance(session_id, str)
        or not session_id.startswith("cs_test_")
        or not isinstance(url, str)
        or urlsplit(url).scheme != "https"
        or urlsplit(url).hostname != "checkout.stripe.com"
    ):
        raise ProviderError("invalid_provider_response", ambiguous=True)
    return {"id": session_id, "url": url, "test_mode": True}


def create_portal_session(customer_id: str, *, client=None) -> dict:
    key, origin = _settings()
    _verify_test_mode(key, client)
    if not re.fullmatch(r"cus_[A-Za-z0-9_]{1,200}", customer_id):
        raise ProviderError("invalid_checkout")
    response, _ = request_json(
        "POST",
        "https://api.stripe.com/v1/billing_portal/sessions",
        client=client,
        side_effect=True,
        headers={"Authorization": "Bearer " + key},
        data={"customer": customer_id, "return_url": origin + "/settings/billing"},
    )
    url = response.get("url")
    if (
        not isinstance(url, str)
        or urlsplit(url).scheme != "https"
        or urlsplit(url).hostname != "billing.stripe.com"
    ):
        raise ProviderError("invalid_provider_response", ambiguous=True)
    return {"url": url, "test_mode": True}
