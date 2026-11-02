"""Provider boundary for real image output; no URL placeholders or demo receipts."""

import base64
import binascii
import os
from typing import Protocol
from urllib.parse import urlsplit

from app.providers.ai import ProviderError, request_json


class ImageProvider(Protocol):
    def generate(self, prompt: str) -> bytes: ...


class OpenAIImages:
    def generate(self, prompt: str, *, client=None) -> bytes:
        key = os.getenv("IMAGE_API_KEY") or os.getenv("LLM_API_KEY")
        model = os.getenv("IMAGE_MODEL")
        base = (
            os.getenv("IMAGE_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1"
        ).rstrip("/")
        parsed = urlsplit(base)
        if not key or not model:
            raise ProviderError("missing_image_credentials")
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ProviderError("invalid_provider_configuration")
        if not 3 <= len(prompt) <= 6000:
            raise ProviderError("input_limit_exceeded")
        data, _ = request_json(
            "POST",
            base + "/images/generations",
            client=client,
            side_effect=True,
            max_response_bytes=12 * 1024 * 1024,
            headers={"Authorization": "Bearer " + key},
            json={
                "model": model,
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "output_format": "jpeg",
            },
        )
        try:
            outputs = data["data"]
            if not isinstance(outputs, list) or len(outputs) != 1:
                raise ValueError()
            encoded = outputs[0]["b64_json"]
            if not isinstance(encoded, str) or len(encoded) > 10 * 1024 * 1024:
                raise ValueError()
            payload = base64.b64decode(encoded, validate=True)
            if not payload or len(payload) > 5 * 1024 * 1024:
                raise ValueError()
            return payload
        except (KeyError, IndexError, TypeError, ValueError, binascii.Error):
            raise ProviderError("invalid_image_output", ambiguous=True) from None
