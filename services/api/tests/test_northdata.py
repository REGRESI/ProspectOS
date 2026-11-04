"""North Data adapter: transport-mocked responses with clearly synthetic companies/people."""

import httpx
import pytest
from sqlalchemy import select

from app.jobs import execute_one
from app.journeys import CompanyFact
from app.models import Company
from app.providers import northdata
from app.providers.ai import ProviderError

REAL_CLIENT = httpx.Client


def company(i, blocked=False, person_blocked=False):
    return {
        "company": {
            "id": f"internal-{i}",
            "name": {"name": f"Synthetische Kanzlei {i} GmbH", "legalForm": "GmbH"},
            "address": {
                "street": f"Testweg {i}",
                "postalCode": "77600",
                "city": "Synthetic Town",
                "country": "DE",
                "lat": 48.47 + i / 1000,
                "lng": 7.94,
            },
            "register": {
                "city": "Fixture-Amtsgericht",
                "id": f"HRB 9{i:04d}",
                "uniqueKey": f"UK{i}",
            },
            "status": "active",
            "blocked": blocked,
            "northDataUrl": f"https://www.northdata.com/synthetic-{i}",
            "segmentCodes": {"wz": ["69.20"]},
            "relatedPersons": {
                "items": [
                    {
                        "person": {
                            "name": {"firstName": "Erika", "lastName": f"Fiktiv{i}"},
                            "blocked": person_blocked,
                        },
                        "roles": [
                            {"group": "Personal", "name": "Geschäftsführer", "date": "2020-01-01"}
                        ],
                    }
                ]
            },
        }
    }


@pytest.fixture
def nd_env(monkeypatch):
    monkeypatch.setenv("NORTHDATA_ENABLED", "true")
    monkeypatch.setenv("NORTHDATA_LICENSE_APPROVED", "true")
    monkeypatch.setenv("NORTHDATA_API_KEY", "synthetic-nd-key")
    monkeypatch.setattr(northdata.time, "sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["X-Api-Key"] == "synthetic-nd-key"
        if request.url.path.endswith("/search/v1/power"):
            if request.url.params.get("pos"):
                return httpx.Response(200, json={"results": [company(3), company(4, blocked=True)]})
            return httpx.Response(
                200,
                json={"results": [company(1), company(2, person_blocked=True)], "nextPos": "p2"},
            )
        if request.url.path.endswith("/search/v1/suggest"):
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404)

    def factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return REAL_CLIENT(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    return calls


def test_disabled_without_flags(monkeypatch):
    monkeypatch.setenv("NORTHDATA_API_KEY", "x")
    with pytest.raises(ProviderError, match="feature_disabled"):
        northdata.power_search("Offenburg", 30)


def test_power_search_pages_drops_blocked_and_stores_unique_key(nd_env):
    rows = northdata.power_search("Offenburg", 30, segment_codes=["69.20"], limit=10)
    assert [r["identity"] for r in rows] == ["northdata:UK1", "northdata:UK2", "northdata:UK3"]
    assert all("internal-" not in str(r) for r in rows)  # internal id is never stored
    assert rows[0]["representatives"][0]["name"] == "Erika Fiktiv1"
    assert rows[1]["representatives"] == []  # blocked person dropped
    first = nd_env[0].url.params
    assert first["maxDistanceKm"] == "30" and first["segmentCodes"] == "69.20"
    assert first["censor"] == "true" and nd_env[1].url.params["pos"] == "p2"


def test_discovery_run_and_import_records_cited_register_facts(context, admin, nd_env):
    client, (ws, *_), _ = context
    search = client.post(
        f"/v1/workspaces/{ws}/discovery/searches",
        json={
            "name": "Steuerberater ND",
            "filters": {
                "provider": "northdata",
                "country": "germany",
                "city": "Offenburg",
                "radius_km": 30,
                "industries": ["Steuerberater"],
                "max_results": 100,
            },
        },
    )
    assert search.status_code in (200, 201), search.text
    queued = client.post(
        f"/v1/workspaces/{ws}/discovery/searches/{search.json()['id']}/run",
        json={"confirmed": True},
    )
    assert queued.status_code == 202, queued.text
    assert execute_one(ws)
    job = client.get(f"/v1/workspaces/{ws}/jobs/{queued.json()['id']}").json()
    assert job["status"] == "succeeded", job
    run_id = job["result"]["run_id"]
    result = client.get(f"/v1/workspaces/{ws}/discovery/runs/{run_id}/results").json()
    assert result["total"] == 3
    keys = [r["key"] for r in result["items"]]
    body = client.post(
        f"/v1/workspaces/{ws}/discovery/runs/{run_id}/import-selected", json={"keys": keys}
    ).json()
    assert body["companies"] == 3
    facts = admin.scalars(select(CompanyFact).where(CompanyFact.workspace_id == ws)).all()
    by_field = {}
    for f in facts:
        by_field.setdefault(f.field, []).append(f)
    assert {"Rechtsform", "Handelsregister", "Adresse"} <= set(by_field)
    assert all(f.source_url.startswith("https://www.northdata.com/") for f in facts)
    assert {f.source_kind for f in facts} == {"northdata"}
    vertretung = sorted(f.value for f in by_field["Vertretung (Registerangabe)"])
    assert vertretung == ["Erika Fiktiv1 (Geschäftsführer)", "Erika Fiktiv3 (Geschäftsführer)"]
    companies = admin.scalars(select(Company).where(Company.workspace_id == ws)).all()
    assert sorted(c.identity for c in companies) == [
        "northdata:UK1",
        "northdata:UK2",
        "northdata:UK3",
    ]
