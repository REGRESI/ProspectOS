"""North Data Data API adapter (register data, legal form, seat, managing directors).

Contract read 2026-11-04 from https://github.com/northdata/api (README, data API user
guide) and https://northdata.github.io/doc/api/:
- Base https://www.northdata.com/_api, auth header ``X-Api-Key``.
- ``/search/v1/suggest`` is not billed -> used for the connection test.
- ``/search/v1/power`` supports ``address`` + ``maxDistanceKm``, ``segmentCodes``,
  ``status``, ``countries``; one concurrent power search; paging via ``nextPos``/``pos``.
- ``/company/v1/company`` with ``name`` + ``address`` (DE) and ``representatives``.
- Billing: per unique company per calendar month; search results count per company.
- Storage: do not persist the internal ``id`` (may change) -> store ``register.uniqueKey``.
- Personal data of representatives is subject to take-down: honour ``blocked`` and use
  ``censor=true``. Records with ``blocked`` are dropped.
Paid licence required; no public terms/pricing page was retrievable, so the operator
must attest the contract (``NORTHDATA_LICENSE_APPROVED``) besides ``NORTHDATA_ENABLED``.
"""

import os
import threading
import time

from app import credentials
from app.providers.ai import ProviderError, request_json

BASE = "https://www.northdata.com/_api"
SOURCE = "North Data (northdata.com), lizenzierte Registerdaten"
_lock = threading.Lock()  # North Data allows one concurrent power search.
_last = [0.0]


def enabled() -> bool:
    return (
        os.getenv("NORTHDATA_ENABLED", "false").lower() == "true"
        and os.getenv("NORTHDATA_LICENSE_APPROVED", "false").lower() == "true"
        and bool(credentials.get("NORTHDATA_API_KEY"))
    )


def _headers():
    key = credentials.get("NORTHDATA_API_KEY")
    if not key:
        raise ProviderError("missing_credentials")
    return {"X-Api-Key": key, "Accept": "application/json"}


def test_connection(client=None) -> dict:
    data, _ = request_json(
        "GET",
        BASE + "/search/v1/suggest",
        client=client,
        params={"query": "Offenburg", "countries": "DE", "limit": 1},
        headers=_headers(),
    )
    if not isinstance(data.get("results", []), list):
        raise ProviderError("invalid_provider_response")
    flags = (
        "aktiv"
        if enabled()
        else "Key gültig, Adapter per NORTHDATA_ENABLED/NORTHDATA_LICENSE_APPROVED deaktiviert"
    )
    return {"detail": f"North Data antwortet (Suggest, nicht abgerechnet). Status: {flags}."}


def _representatives(company: dict) -> list[dict]:
    people = []
    related = company.get("relatedPersons") or company.get("representatives") or {}
    for item in related.get("items", []) if isinstance(related, dict) else []:
        person = item.get("person") or {}
        if person.get("blocked") or item.get("blocked"):
            continue
        name = person.get("name") or {}
        full = " ".join(
            filter(None, [name.get("title"), name.get("firstName"), name.get("lastName")])
        )
        for role in item.get("roles") or []:
            if role.get("group") == "Personal" and not role.get("demotion") and full:
                people.append(
                    {
                        "name": full,
                        "role": role.get("name") or "Vertretung",
                        "since": role.get("date"),
                    }
                )
    return people[:10]


def normalize(company: dict, retrieved_at: str) -> dict | None:
    if not isinstance(company, dict) or company.get("blocked"):
        return None
    name = company.get("name") or {}
    address = company.get("address") or {}
    register = company.get("register") or {}
    key = register.get("uniqueKey")
    if not name.get("name") or not key:
        return None
    url = company.get("northDataUrl") or ""
    return {
        "name": name["name"][:240],
        "legal_form": name.get("legalForm") or "",
        "street": address.get("street") or "",
        "postal_code": address.get("postalCode") or "",
        "city": address.get("city") or "",
        "country": address.get("country") or "",
        "lat": address.get("lat"),
        "lng": address.get("lng"),
        "register_id": register.get("id") or "",
        "register_city": register.get("city") or "",
        "identity": "northdata:" + key,
        "status": company.get("status") or "",
        "segment_codes": (company.get("segmentCodes") or {}).get("wz", []),
        "representatives": _representatives(company),
        "source": SOURCE,
        "source_url": url,
        "retrieved_at": retrieved_at,
    }


def power_search(
    address: str, radius_km: float, *, segment_codes=(), keywords="", limit=50, client=None
) -> list[dict]:
    if not enabled():
        raise ProviderError("feature_disabled")
    if not 1 <= radius_km <= 100 or not 2 <= len(address) <= 200 or not 1 <= limit <= 500:
        raise ProviderError("input_limit_exceeded")
    from app.db import now

    retrieved = now().isoformat()
    results, pos = [], None
    with _lock:
        while len(results) < limit:
            wait = 1.0 - (time.monotonic() - _last[0])
            if wait > 0:
                time.sleep(wait)
            params = {
                "address": address,
                "maxDistanceKm": radius_km,
                "countries": "DE",
                "status": "active",
                "representatives": "true",
                "censor": "true",
                "limit": min(50, limit - len(results)),
            }
            if segment_codes:
                params |= {"segmentCodeStandard": "WZ", "segmentCodes": "|".join(segment_codes)}
            if keywords:
                params["keywords"] = keywords[:200]
            if pos:
                params["pos"] = pos
            data, _ = request_json(
                "GET", BASE + "/search/v1/power", client=client, params=params, headers=_headers()
            )
            _last[0] = time.monotonic()
            for item in data.get("results", []):
                row = normalize(item.get("company", item), retrieved)
                if row:
                    results.append(row)
            pos = data.get("nextPos")
            if not pos:
                break
    return results[:limit]
