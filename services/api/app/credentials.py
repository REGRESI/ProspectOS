"""Per-workspace provider credentials, encrypted with TOKEN_ENCRYPTION_KEY.

Resolution order for every provider setting: the active workspace's stored value
(set via ``workspace(db, ws)``), then the process environment. Secrets are never
returned to clients; only a mask (last four characters) leaves the server.
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import select


@dataclass(frozen=True)
class Field:
    env: str
    label: str
    secret: bool = False
    required: bool = True
    hint: str = ""


PROVIDERS: dict[str, dict] = {
    "openai": {
        "label": "OpenAI (Text und Bilder)",
        "purpose": "KI-Texte, Antwortauswertung, Website-Profile und GPT-Image-Bilder",
        "fields": [
            Field("LLM_API_KEY", "API-Key", secret=True),
            Field("LLM_MODEL", "Textmodell", hint="z. B. gpt-4.1-mini"),
            Field("IMAGE_MODEL", "Bildmodell", required=False, hint="z. B. gpt-image-1"),
            Field("LLM_INPUT_USD_PER_MILLION", "USD pro 1 Mio. Input-Tokens"),
            Field("LLM_OUTPUT_USD_PER_MILLION", "USD pro 1 Mio. Output-Tokens"),
        ],
    },
    "linkedin": {
        "label": "LinkedIn-App",
        "purpose": "Offizielles OAuth und Posten als persönliches Profil (w_member_social)",
        "fields": [
            Field("LINKEDIN_CLIENT_ID", "Client ID"),
            Field("LINKEDIN_CLIENT_SECRET", "Client Secret", secret=True),
        ],
    },
    "osm": {
        "label": "OpenStreetMap (Nominatim/Overpass)",
        "purpose": "Firmensuche nach Ort und Kategorie; Kontaktangabe ist Pflicht der Nutzungsrichtlinie",
        "fields": [
            Field("OSM_CONTACT", "Kontakt (E-Mail oder URL)", hint="wird im User-Agent gesendet"),
        ],
    },
    "brave": {
        "label": "Brave Search API",
        "purpose": "Kandidaten für LinkedIn-Profil-URLs über die offizielle Such-API (kein Scraping)",
        "fields": [Field("BRAVE_SEARCH_API_KEY", "API-Key", secret=True)],
    },
    "northdata": {
        "label": "North Data",
        "purpose": "Registerdaten, Geschäftsführung, Rechtsform, Sitz (lizenzpflichtig)",
        "fields": [Field("NORTHDATA_API_KEY", "API-Key", secret=True)],
    },
}

ALL_FIELDS = {f.env: (provider, f) for provider, spec in PROVIDERS.items() for f in spec["fields"]}

# Holder: {"ws": str | None, "values": dict | None}. Mutable so a lazy load inside a
# threadpool copy of the request context is visible for the rest of that request.
_active: ContextVar[dict | None] = ContextVar("workspace_credentials", default=None)


def bind(ws: str | None):
    """Bind a request to a workspace; values load lazily on first use.

    Only call sites behind the membership-checking ``scope`` dependency can reach a
    provider, so lazy loading never exposes another tenant's credentials.
    """
    return _active.set({"ws": ws, "values": None})


def unbind(token):
    _active.reset(token)


def _values() -> dict:
    holder = _active.get()
    if not holder:
        return {}
    if holder["values"] is None:
        holder["values"] = {}
        if holder.get("ws"):
            from sqlalchemy import text

            from app.db import SessionLocal

            with SessionLocal() as db:
                db.execute(
                    text("SELECT set_config('app.workspace_id', :ws, true)"),
                    {"ws": holder["ws"]},
                )
                holder["values"] = load(db, holder["ws"])
    return holder["values"]


def get(name: str, default: str = "") -> str:
    """Workspace value if a workspace is bound and has it, else environment."""
    values = _values()
    if values.get(name):
        return values[name]
    return os.getenv(name, default)


def source(name: str) -> str:
    if _values().get(name):
        return "workspace"
    return "environment" if os.getenv(name, "").strip() else "missing"


def cipher() -> Fernet:
    try:
        return Fernet(os.environ["TOKEN_ENCRYPTION_KEY"].encode())
    except (KeyError, ValueError):
        raise HTTPException(
            503, "Configure a valid TOKEN_ENCRYPTION_KEY before storing provider credentials."
        ) from None


def encryption_ready() -> bool:
    try:
        Fernet(os.environ["TOKEN_ENCRYPTION_KEY"].encode())
        return True
    except (KeyError, ValueError):
        return False


def mask(value: str, secret: bool) -> str:
    if not value:
        return ""
    if not secret:
        return value
    return "••••" + value[-4:] if len(value) > 8 else "••••"


def _decrypt(item) -> dict:
    try:
        import json

        return json.loads(cipher().decrypt(item.ciphertext.encode()).decode())
    except (InvalidToken, ValueError):
        # Wrong/rotated key: treat as missing rather than leaking or crashing.
        return {}


def load(db, ws: str) -> dict:
    from app.platform_models import IntegrationCredential

    if not os.getenv("TOKEN_ENCRYPTION_KEY"):
        return {}
    values: dict = {}
    for item in db.scalars(
        select(IntegrationCredential).where(IntegrationCredential.workspace_id == ws)
    ):
        values.update(_decrypt(item))
    return {k: v for k, v in values.items() if k in ALL_FIELDS and isinstance(v, str)}


def stored_fields(db, ws: str, provider: str) -> dict:
    from app.platform_models import IntegrationCredential

    item = db.scalar(
        select(IntegrationCredential).where(
            IntegrationCredential.workspace_id == ws, IntegrationCredential.provider == provider
        )
    )
    return (_decrypt(item) if item else {}), item


def encrypt(values: dict) -> str:
    import json

    return cipher().encrypt(json.dumps(values).encode()).decode()


@contextmanager
def workspace(db, ws: str):
    """Eager scope for workers and routes without a workspace path (OAuth callback)."""
    token = _active.set({"ws": ws, "values": load(db, ws)})
    try:
        yield
    finally:
        _active.reset(token)


@contextmanager
def override(values: dict):
    """Use explicit values on top of the current scope (connection test before saving)."""
    holder = _active.get()
    merged = dict(_values())
    merged.update({k: v for k, v in values.items() if v})
    token = _active.set({"ws": holder.get("ws") if holder else None, "values": merged})
    try:
        yield
    finally:
        _active.reset(token)


def require(name: str) -> str:
    """Like os.environ[name]: raises KeyError when the value is missing everywhere."""
    value = get(name)
    if not value:
        raise KeyError(name)
    return value
