"""Resend transport: only callable after an independent policy/approval gate.

The official resend-python emails resource verifies POST /emails and an
Idempotency-Key header. No automatic LinkedIn messaging is implemented here.
"""

import os
import re

from app.providers.ai import ProviderError, configured, request_json


def send_email(
    recipient: str,
    subject: str,
    text: str,
    idempotency_key: str,
    *,
    policy_authorized: bool = False,
    client=None,
) -> dict:
    if not policy_authorized:
        raise ProviderError("policy_denied")
    if os.getenv("EMAIL_SEND_ENABLED", "false").lower() != "true":
        raise ProviderError("email_disabled")
    key, sender = configured("RESEND_API_KEY"), configured("EMAIL_FROM")
    if (
        not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", recipient)
        or len(recipient) > 254
        or not 1 <= len(subject) <= 200
        or "\r" in subject
        or "\n" in subject
        or not 1 <= len(text) <= 12000
        or not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", idempotency_key)
        or "\r" in sender
        or "\n" in sender
    ):
        raise ProviderError("invalid_email")
    response, _ = request_json(
        "POST",
        "https://api.resend.com/emails",
        client=client,
        side_effect=True,
        headers={"Authorization": "Bearer " + key, "Idempotency-Key": idempotency_key},
        json={"from": sender, "to": [recipient], "subject": subject, "text": text},
    )
    receipt = response.get("id")
    if not isinstance(receipt, str) or not receipt or len(receipt) > 200:
        raise ProviderError("invalid_provider_response", ambiguous=True)
    return {
        "provider": "resend",
        "external_id": receipt,
        "status": "accepted",
        "delivery_confirmed": False,
    }
