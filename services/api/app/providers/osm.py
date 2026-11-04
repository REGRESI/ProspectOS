"""OpenStreetMap company/place discovery via Nominatim (geocoding) and Overpass (POI search).

Data is © OpenStreetMap contributors, licensed under ODbL 1.0. Every candidate carries
the OSM object URL, licence and attribution. OSM describes places and businesses, not
people: this adapter never returns contact persons, personal e-mail or phone numbers.

Operator prerequisites (fail closed otherwise):
- OSM_DISCOVERY_ENABLED=true
- OSM_CONTACT: operator contact (URL or mailbox) sent in the User-Agent, as the
  Nominatim usage policy requires an identifying application.
- Optional OSM_NOMINATIM_URL / OSM_OVERPASS_URL for self-hosted or commercial mirrors.

Public instances are shared, donated infrastructure: Nominatim allows max. 1 request/s and
requires caching; Overpass enforces per-IP slots. Requests are serialized per process,
geocodes are cached per workspace by the caller, and runs are user-confirmed, never
scheduled in bulk.
"""

import math
import os
import re
import threading
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field

from app import credentials
from app.providers.ai import ProviderError, request_json

ATTRIBUTION = "© OpenStreetMap contributors"
LICENSE = "ODbL 1.0 (Open Database License) – " + ATTRIBUTION
ALLOWED_USES = (
    "Öffentliche Orts-/Firmenangaben unter ODbL; Namensnennung erforderlich. "
    "Keine Personendaten, kein Werbeeinverständnis abgeleitet."
)
DEFAULT_NOMINATIM = "https://nominatim.openstreetmap.org"
DEFAULT_OVERPASS = "https://overpass-api.de/api/interpreter"
MAX_RADIUS_KM = 50
MAX_RESULTS = 50

# Curated mapping of sales-relevant categories to documented OSM tags
# (https://wiki.openstreetmap.org/wiki/Map_features). Keys are canonical labels;
# aliases let German/English user terms resolve. Values are (key, value) pairs; a
# value of "*" means any value for that key.
CATEGORIES: dict[str, dict] = {
    "Büro / Dienstleistung": {
        "aliases": ["büro", "office", "dienstleistung", "dienstleister", "service"],
        "tags": [("office", "company"), ("office", "consulting")],
    },
    "IT & Software": {
        "aliases": ["it", "software", "edv", "informatik", "it-dienstleister", "agentur"],
        "tags": [
            ("office", "it"),
            ("office", "telecommunication"),
            ("craft", "electronics_repair"),
        ],
    },
    "Steuerberatung": {
        "aliases": ["steuerberater", "steuerberatung", "tax", "tax advisor", "buchhaltung"],
        "tags": [("office", "tax_advisor"), ("office", "accountant")],
    },
    "Rechtsberatung": {
        "aliases": ["rechtsanwalt", "kanzlei", "anwalt", "lawyer", "notar", "notary"],
        "tags": [("office", "lawyer"), ("office", "notary")],
    },
    "Immobilien": {
        "aliases": ["immobilien", "makler", "real estate", "estate agent", "hausverwaltung"],
        "tags": [("office", "estate_agent"), ("office", "property_management")],
    },
    "Versicherung & Finanzen": {
        "aliases": ["versicherung", "insurance", "finanz", "finance", "finanzberatung"],
        "tags": [("office", "insurance"), ("office", "financial_advisor"), ("office", "financial")],
    },
    "Architektur & Ingenieurwesen": {
        "aliases": ["architekt", "architect", "ingenieur", "engineer", "planungsbüro"],
        "tags": [("office", "architect"), ("office", "engineer"), ("office", "surveyor")],
    },
    "Handwerk": {
        "aliases": ["handwerk", "craft", "handwerker", "elektriker", "schreiner", "maler"],
        "tags": [("craft", "*")],
    },
    "Gesundheit / Praxis": {
        "aliases": [
            "arzt",
            "praxis",
            "arztpraxis",
            "zahnarzt",
            "physiotherapie",
            "doctor",
            "dentist",
            "gesundheit",
        ],
        "tags": [
            ("amenity", "doctors"),
            ("amenity", "dentist"),
            ("healthcare", "physiotherapist"),
            ("amenity", "clinic"),
        ],
    },
    "Gastronomie": {
        "aliases": ["gastronomie", "restaurant", "café", "cafe", "hospitality"],
        "tags": [("amenity", "restaurant"), ("amenity", "cafe")],
    },
    "Hotellerie": {
        "aliases": ["hotel", "hotellerie", "pension", "unterkunft"],
        "tags": [("tourism", "hotel"), ("tourism", "guest_house")],
    },
    "Einzelhandel": {
        "aliases": ["einzelhandel", "handel", "retail", "shop", "laden", "geschäft"],
        "tags": [("shop", "*")],
    },
    "Kfz": {
        "aliases": ["kfz", "autohaus", "werkstatt", "car", "automotive"],
        "tags": [("shop", "car"), ("shop", "car_repair")],
    },
    "Fitness & Freizeit": {
        "aliases": ["fitness", "fitnessstudio", "gym", "sport"],
        "tags": [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    },
    "Bildung": {
        "aliases": ["bildung", "schule", "school", "weiterbildung", "education", "sprachschule"],
        "tags": [("amenity", "school"), ("amenity", "language_school"), ("amenity", "training")],
    },
    "Industrie & Produktion": {
        "aliases": ["industrie", "produktion", "fertigung", "manufacturing", "industrial"],
        "tags": [("man_made", "works"), ("industrial", "*"), ("office", "company")],
    },
    "Logistik": {
        "aliases": ["logistik", "spedition", "transport", "logistics"],
        "tags": [("office", "logistics"), ("industrial", "warehouse"), ("shop", "storage_rental")],
    },
    "Reinigung / Facility": {
        "aliases": ["reinigung", "gebäudereinigung", "facility", "cleaning", "hausmeister"],
        "tags": [("shop", "dry_cleaning"), ("craft", "cleaning"), ("office", "company")],
    },
}

_TAG_KEYS = {key for spec in CATEGORIES.values() for key, _ in spec["tags"]}
_SAFE_TERM = re.compile(r"^[\w .&'+()\-äöüÄÖÜß]{1,60}$")
_lock = threading.Lock()
_last_request = 0.0


class OsmCandidate(BaseModel):
    external_key: str
    company: str
    location: str = ""
    address: str = ""
    postcode: str = ""
    industry: str = ""
    osm_category: str = ""
    website: str | None = None
    latitude: float
    longitude: float
    distance_km: float | None = None
    opening_hours: str = ""
    source: str = "openstreetmap"
    source_url: str
    license: str = LICENSE
    attribution: str = ATTRIBUTION
    allowed_uses: str = ALLOWED_USES
    confidence: str = "community_reported"
    observed_at: str
    tags: dict[str, str] = Field(default_factory=dict)


class GeoPoint(BaseModel):
    latitude: float
    longitude: float
    display_name: str
    source_url: str


def enabled() -> bool:
    return os.getenv("OSM_DISCOVERY_ENABLED", "false").lower() == "true" and bool(
        credentials.get("OSM_CONTACT", "").strip()
    )


def _user_agent() -> str:
    contact = credentials.get("OSM_CONTACT", "").strip()
    if not contact or any(ord(c) < 32 for c in contact) or len(contact) > 200:
        raise ProviderError("missing_credentials")
    return f"ProspectOS/1.0 (+{contact})"


def _endpoint(name: str, default: str) -> str:
    value = os.getenv(name, "").strip() or default
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ProviderError("invalid_provider_configuration")
    return value.rstrip("/")


def _throttle():
    """Serialize requests per process with >=1.1 s spacing (Nominatim policy)."""
    global _last_request
    wait = _last_request + 1.1 - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def resolve_categories(terms: list[str]) -> tuple[list[str], list[str]]:
    """Map user industry terms to canonical categories. Returns (resolved, unmapped)."""
    resolved, unmapped = [], []
    for term in terms:
        needle = term.strip().casefold()
        match = next(
            (
                label
                for label, spec in CATEGORIES.items()
                if needle == label.casefold() or needle in spec["aliases"]
            ),
            None,
        )
        if match is None:
            match = next(
                (
                    label
                    for label, spec in CATEGORIES.items()
                    if any(
                        alias in needle or needle in alias
                        for alias in spec["aliases"]
                        if len(needle) >= 4
                    )
                ),
                None,
            )
        if match:
            if match not in resolved:
                resolved.append(match)
        else:
            unmapped.append(term)
    return resolved, unmapped


def _escape_regex(term: str) -> str:
    if not _SAFE_TERM.match(term):
        raise ProviderError("invalid_search_term")
    return re.sub(r"([.\\+*?\[^\]$(){}|])", r"\\\\\1", term)


def build_query(
    lat: float, lon: float, radius_km: float, categories: list[str], keywords: list[str], limit: int
) -> str:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or not 0 < radius_km <= MAX_RADIUS_KM:
        raise ProviderError("invalid_search_area")
    if not 1 <= limit <= MAX_RESULTS:
        raise ProviderError("input_limit_exceeded")
    around = f"(around:{int(radius_km * 1000)},{lat:.6f},{lon:.6f})"
    name_filter = ""
    if keywords:
        name_filter = '["name"~"' + "|".join(_escape_regex(k) for k in keywords) + '",i]'
    selectors = []
    pairs = [pair for label in categories for pair in CATEGORIES[label]["tags"]]
    if not pairs and keywords:
        # Keyword-only search is still restricted to business-like objects.
        pairs = [(key, "*") for key in sorted(_TAG_KEYS)]
    if not pairs:
        raise ProviderError("search_criteria_required")
    for key, value in dict.fromkeys(pairs):
        tag = f'["{key}"]' if value == "*" else f'["{key}"="{value}"]'
        selectors.append(f'  nwr{tag}["name"]{name_filter}{around};')
    # Overscan so in-run deduplication and distance sort still fill the requested page.
    return (
        "[out:json][timeout:25];\n(\n"
        + "\n".join(selectors)
        + f"\n);\nout center tags {min(limit * 3, 200)};"
    )


def _normalize_website(tags: dict) -> str | None:
    value = tags.get("website") or tags.get("contact:website") or ""
    value = value.strip().split(";")[0].strip()
    if not value:
        return None
    if "://" not in value:
        value = "https://" + value
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    host = parsed.hostname.lower()
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return None
    return value[:2000]


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _category_for(tags: dict, categories: list[str]) -> tuple[str, str]:
    for label in categories or list(CATEGORIES):
        for key, value in CATEGORIES[label]["tags"]:
            if key in tags and (value == "*" or tags[key] == value):
                return label, f"{key}={tags[key]}"
    for key in sorted(_TAG_KEYS):
        if key in tags:
            return "", f"{key}={tags[key]}"
    return "", ""


def normalize_name(name: str) -> str:
    value = name.casefold()
    value = re.sub(
        r"\b(gmbh|mbh|ag|kg|ohg|ug|e\.?\s?k\.?|e\.?\s?v\.?|gbr|co|inc|ltd|llc|haftungsbeschränkt|und|&)\b",
        " ",
        value,
    )
    return " ".join(re.sub(r"[^\w]+", " ", value).split())


def parse_elements(payload: dict, center: tuple[float, float], categories: list[str], limit: int):
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise ProviderError("invalid_provider_response")
    observed = datetime.now(UTC).isoformat()
    by_identity: dict[tuple, OsmCandidate] = {}
    for element in elements[:1000]:
        if not isinstance(element, dict):
            continue
        kind, oid, tags = element.get("type"), element.get("id"), element.get("tags")
        if (
            kind not in ("node", "way", "relation")
            or type(oid) is not int
            or not isinstance(tags, dict)
        ):
            continue
        tags = {
            str(k)[:100]: str(v)[:500] for k, v in tags.items() if isinstance(v, (str, int, float))
        }
        name = tags.get("name", "").strip()
        if not name:
            continue
        point = element if kind == "node" else element.get("center") or {}
        lat, lon = point.get("lat"), point.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        city = tags.get("addr:city") or tags.get("addr:place") or ""
        street = " ".join(
            x for x in (tags.get("addr:street", ""), tags.get("addr:housenumber", "")) if x
        )
        postcode = tags.get("addr:postcode", "")
        label, raw_category = _category_for(tags, categories)
        candidate = OsmCandidate(
            external_key=f"{kind}/{oid}",
            company=name[:240],
            location=city[:240],
            address=", ".join(x for x in (street, " ".join(x for x in (postcode, city) if x)) if x)[
                :500
            ],
            postcode=postcode[:20],
            industry=(label or raw_category)[:120],
            osm_category=raw_category[:120],
            website=_normalize_website(tags),
            latitude=float(lat),
            longitude=float(lon),
            distance_km=round(haversine_km(center[0], center[1], float(lat), float(lon)), 2),
            opening_hours=tags.get("opening_hours", "")[:300],
            source_url=f"https://www.openstreetmap.org/{kind}/{oid}",
            observed_at=observed,
            # Only business descriptors are retained; phone/e-mail tags are deliberately dropped.
            tags={
                k: v
                for k, v in tags.items()
                if k in _TAG_KEYS
                or k in ("brand", "operator", "description", "opening_hours", "wheelchair")
                or k.startswith("addr:")
            },
        )
        # OSM frequently maps one business as node + building way; keep the richer object.
        identity = (normalize_name(name), postcode or city.casefold() or f"{lat:.3f},{lon:.3f}")
        current = by_identity.get(identity)
        if current is None or len(candidate.tags) > len(current.tags):
            by_identity[identity] = candidate
    ordered = sorted(by_identity.values(), key=lambda c: (c.distance_km or 0, c.company.casefold()))
    return ordered[:limit]


def geocode(place: str, country: str = "", *, client=None) -> GeoPoint:
    if not enabled():
        raise ProviderError("osm_not_enabled")
    query = ", ".join(x.strip() for x in (place, country) if x and x.strip())
    if not query or len(query) > 200:
        raise ProviderError("invalid_search_area")
    base = _endpoint("OSM_NOMINATIM_URL", DEFAULT_NOMINATIM)
    with _lock:
        _throttle()
        # Nominatim answers with a JSON list; request_json requires an object, so call directly.
        own = client is None
        client = client or httpx.Client(
            timeout=httpx.Timeout(20, connect=10), follow_redirects=False
        )
        try:
            try:
                response = client.get(
                    base + "/search",
                    params={"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 0},
                    headers={"User-Agent": _user_agent(), "Accept-Language": "de,en"},
                )
            except httpx.TransportError:
                raise ProviderError("provider_unavailable", retryable=True) from None
        finally:
            if own:
                client.close()
    if response.status_code == 429:
        raise ProviderError("rate_limited", retryable=True)
    if response.status_code in (401, 403):
        raise ProviderError("provider_forbidden")
    if not response.is_success:
        raise ProviderError("provider_unavailable", retryable=response.status_code >= 500)
    try:
        data = response.json()
    except ValueError:
        raise ProviderError("invalid_provider_response") from None
    if not isinstance(data, list):
        raise ProviderError("invalid_provider_response")
    if not data:
        raise ProviderError("place_not_found")
    first = data[0]
    try:
        lat, lon = float(first["lat"]), float(first["lon"])
    except (KeyError, TypeError, ValueError):
        raise ProviderError("invalid_provider_response") from None
    osm_type, osm_id = first.get("osm_type"), first.get("osm_id")
    source = (
        f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
        if osm_type in ("node", "way", "relation") and isinstance(osm_id, int)
        else "https://www.openstreetmap.org/"
    )
    return GeoPoint(
        latitude=lat,
        longitude=lon,
        display_name=str(first.get("display_name") or query)[:300],
        source_url=source,
    )


def overpass(query: str, *, client=None, attempts: int = 4) -> dict:
    """Read-only Overpass call with the exponential backoff the public instance asks for
    when it is at capacity (HTTP 429/502/503/504)."""
    delay = 2.0
    for attempt in range(attempts):
        with _lock:
            _throttle()
            try:
                payload, _ = request_json(
                    "POST",
                    _endpoint("OSM_OVERPASS_URL", DEFAULT_OVERPASS),
                    client=client,
                    side_effect=False,
                    max_response_bytes=8 * 1024 * 1024,
                    headers={"User-Agent": _user_agent()},
                    data={"data": query},
                )
                return payload
            except ProviderError as exc:
                if (
                    exc.code not in ("rate_limited", "provider_unavailable")
                    or attempt == attempts - 1
                ):
                    raise
        _sleep(delay)
        delay *= 2
    raise ProviderError("provider_unavailable")


def _sleep(seconds: float):
    time.sleep(seconds)


def search_places(
    center: GeoPoint,
    radius_km: float,
    categories: list[str],
    keywords: list[str],
    limit: int,
    *,
    client=None,
) -> list[OsmCandidate]:
    if not enabled():
        raise ProviderError("osm_not_enabled")
    query = build_query(center.latitude, center.longitude, radius_km, categories, keywords, limit)
    payload = overpass(query, client=client)
    return parse_elements(payload, (center.latitude, center.longitude), categories, limit)
