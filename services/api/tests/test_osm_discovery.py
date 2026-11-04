"""OSM discovery proofs. All HTTP is transport-mocked; payloads mirror the documented
Overpass/Nominatim JSON formats but contain only SYNTHETIC, fictional businesses.
No live OpenStreetMap service was contacted by these tests."""

import json

import httpx
import pytest
from sqlalchemy import select

from app.jobs import execute_one
from app.journeys import CompanyFact, GeocodeCache
from app.models import Company
from app.providers import osm
from app.providers.ai import ProviderError

REAL_CLIENT = httpx.Client

NOMINATIM = [
    {
        "osm_type": "relation",
        "osm_id": 999001,
        "lat": "48.4735",
        "lon": "7.9498",
        "display_name": "Synthetic Town, Fixture County",
    }
]

OVERPASS = {
    "version": 0.6,
    "generator": "synthetic test fixture",
    "elements": [
        {
            "type": "node",
            "id": 101,
            "lat": 48.4740,
            "lon": 7.9510,
            "tags": {
                "name": "Fiktive Steuerkanzlei Muster GmbH",
                "office": "tax_advisor",
                "addr:street": "Testweg",
                "addr:housenumber": "1",
                "addr:postcode": "77600",
                "addr:city": "Synthetic Town",
                "website": "www.fiktiv-steuer.example.test",
                "phone": "+49 000 000000",
                "email": "person@fiktiv-steuer.example.test",
                "opening_hours": "Mo-Fr 08:00-17:00",
            },
        },
        {
            # Same business mapped again as a building way: must be merged in-run.
            "type": "way",
            "id": 202,
            "center": {"lat": 48.4741, "lon": 7.9511},
            "tags": {
                "name": "Fiktive Steuerkanzlei Muster",
                "office": "tax_advisor",
                "addr:postcode": "77600",
            },
        },
        {
            "type": "node",
            "id": 303,
            "lat": 48.5600,
            "lon": 7.9000,
            "tags": {
                "name": "Synthetische Rechtsanwälte Beispiel",
                "office": "lawyer",
                "addr:city": "Fixture Village",
                "website": "https://www.bestand.example.test/kontakt",
            },
        },
        {"type": "node", "id": 404, "lat": 48.47, "lon": 7.95, "tags": {"office": "lawyer"}},
        {"type": "node", "id": 505, "tags": {"name": "No coordinates", "office": "lawyer"}},
    ],
}


def url(ws, path):
    return f"/v1/workspaces/{ws}/{path}"


@pytest.fixture
def osm_env(monkeypatch):
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("OSM_CONTACT", "ops@prospectos.example.test")
    monkeypatch.setattr(osm, "_throttle", lambda: None)
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        assert request.headers["User-Agent"].startswith("ProspectOS/1.0 (+ops@")
        if request.url.host == "nominatim.openstreetmap.org":
            return httpx.Response(200, json=NOMINATIM)
        if request.url.host == "overpass-api.de":
            return httpx.Response(200, json=OVERPASS)
        return httpx.Response(404)

    def client_factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return REAL_CLIENT(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    return calls


def test_query_builder_is_injection_safe_and_bounded():
    query = osm.build_query(48.47, 7.95, 15, ["Steuerberatung"], ["Muster (GmbH)"], 10)
    assert "(around:15000,48.470000,7.950000)" in query
    assert 'nwr["office"="tax_advisor"]["name"]["name"~"Muster \\\\(GmbH\\\\)",i]' in query
    assert "out center tags 30;" in query
    for bad in ['x"];out;', "a\nb", "{{bbox}}"]:
        with pytest.raises(ProviderError):
            osm.build_query(48.47, 7.95, 15, [], [bad], 10)
    with pytest.raises(ProviderError):
        osm.build_query(48.47, 7.95, 51, ["Steuerberatung"], [], 10)
    with pytest.raises(ProviderError):
        osm.build_query(48.47, 7.95, 5, [], [], 10)


def test_category_resolution_reports_unmapped_terms():
    resolved, unmapped = osm.resolve_categories(["Steuerberater", "IT", "Quantenkryptografie"])
    assert resolved == ["Steuerberatung", "IT & Software"]
    assert unmapped == ["Quantenkryptografie"]


def test_parser_merges_duplicates_drops_personal_tags_and_sorts_by_distance():
    rows = osm.parse_elements(OVERPASS, (48.4735, 7.9498), ["Steuerberatung", "Rechtsberatung"], 10)
    assert [r.external_key for r in rows] == ["node/101", "node/303"]
    first = rows[0]
    assert first.website == "https://www.fiktiv-steuer.example.test"
    assert first.address == "Testweg 1, 77600 Synthetic Town"
    assert first.industry == "Steuerberatung" and first.osm_category == "office=tax_advisor"
    assert "phone" not in first.tags and "email" not in first.tags
    assert first.source_url == "https://www.openstreetmap.org/node/101"
    assert "ODbL" in first.license and first.distance_km < 1
    assert rows[1].distance_km > 9


def test_adapter_fails_closed_without_operator_configuration(monkeypatch):
    monkeypatch.delenv("OSM_DISCOVERY_ENABLED", raising=False)
    with pytest.raises(ProviderError) as exc:
        osm.geocode("Synthetic Town")
    assert exc.value.code == "osm_not_enabled"
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    monkeypatch.delenv("OSM_CONTACT", raising=False)
    assert not osm.enabled()


def test_provider_errors_are_classified(osm_env, monkeypatch):
    def limited(request):
        return httpx.Response(429)

    client = REAL_CLIENT(transport=httpx.MockTransport(limited))
    with pytest.raises(ProviderError) as exc:
        osm.geocode("Synthetic Town", client=client)
    assert exc.value.code == "rate_limited" and exc.value.retryable
    empty = REAL_CLIENT(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[])))
    with pytest.raises(ProviderError) as exc:
        osm.geocode("Nowhere", client=empty)
    assert exc.value.code == "place_not_found"


def test_disabled_osm_search_is_refused(context, monkeypatch):
    client, (ws, *_), _ = context
    monkeypatch.delenv("OSM_DISCOVERY_ENABLED", raising=False)
    providers = client.get(url(ws, "discovery/providers")).json()
    assert next(p for p in providers["items"] if p["id"] == "osm")["available"] is False
    search = client.post(
        url(ws, "discovery/searches"),
        json={
            "name": "OSM",
            "filters": {
                "provider": "osm",
                "city": "Synthetic Town",
                "industries": ["Steuerberater"],
            },
        },
    ).json()
    assert (
        client.post(
            url(ws, f"discovery/searches/{search['id']}/run"), json={"confirmed": True}
        ).status_code
        == 503
    )


def test_osm_discovery_end_to_end_with_dedup_scoring_and_cited_import(context, admin, osm_env):
    client, (ws, other, *_), _ = context
    # Existing company with the same domain as result node/303 -> probable duplicate.
    from tests.conftest import scoped

    scoped(admin, ws)
    seeded = Company(
        workspace_id=ws,
        name="Bestandskunde Kanzlei",
        identity="manual:bestand",
        website="https://bestand.example.test",
        provenance={},
    )
    admin.add(seeded)
    admin.commit()
    existing_id = seeded.id
    interpreted = client.post(
        url(ws, "discovery/interpret"),
        json={"briefing": "Steuerberater und Kanzlei in Offenburg im Umkreis von 15 km"},
    ).json()
    assert interpreted["suggested_filters"]["provider"] == "osm"
    assert "Steuerberatung" in interpreted["suggested_filters"]["industries"]
    filters = interpreted["suggested_filters"] | {
        "industries": ["Steuerberater", "Rechtsanwalt", "Raumfahrt"],
        "min_employees": 5,
    }
    search = client.post(
        url(ws, "discovery/searches"), json={"name": "Kanzleien", "filters": filters}
    ).json()
    queued = client.post(
        url(ws, f"discovery/searches/{search['id']}/run"), json={"confirmed": True}
    )
    assert queued.status_code == 202, queued.text
    warnings = " ".join(queued.json()["warnings"])
    assert "Raumfahrt" in warnings and "Mitarbeiterzahlen" in warnings
    assert execute_one(ws)
    job = client.get(url(ws, f"jobs/{queued.json()['id']}")).json()
    assert job["status"] == "succeeded", job
    overpass = [c for c in osm_env if c.url.host == "overpass-api.de"]
    sent = overpass[0].content.decode()
    assert "office%22%3D%22tax_advisor" in sent or 'office"="tax_advisor' in sent
    run_id = job["result"]["run_id"]
    result = client.get(
        url(ws, f"discovery/runs/{run_id}/results?sort=score&direction=desc")
    ).json()
    assert result["meta"]["attribution"] == "© OpenStreetMap contributors"
    assert result["meta"]["center"]["display_name"] == "Synthetic Town, Fixture County"
    assert result["total"] == 2 and result["duplicates"] == 1
    by_name = {r["company"]: r for r in result["items"]}
    kanzlei = by_name["Fiktive Steuerkanzlei Muster GmbH"]
    assert kanzlei["duplicate_of"] is None and kanzlei["distance_km"] < 1
    region = next(f for f in kanzlei["score"]["factors"] if f["name"] == "Region")
    assert region["points"] == region["max_points"] and "Radius 15 km" in region["reason"]
    assert kanzlei["score"]["not_applicable"][0]["name"] == "Entscheiderrolle"
    assert "Ansprechpartner" in kanzlei["score"]["missing_data"]
    dup = by_name["Synthetische Rechtsanwälte Beispiel"]
    assert dup["duplicate_of"]["reason"] == "domain"
    assert dup["duplicate_of"]["company_id"] == existing_id
    # Geocode was cached for the workspace (Nominatim policy).
    assert admin.scalar(select(GeocodeCache).where(GeocodeCache.workspace_id == ws)) is not None
    # Cross-tenant access to the run is denied.
    assert client.get(url(other, f"discovery/runs/{run_id}/results")).status_code == 404
    imported = client.post(
        url(ws, f"discovery/runs/{run_id}/import-selected"),
        json={"keys": [kanzlei["key"], dup["key"]]},
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["companies"] == 1 and body["linked_duplicates"] == 1 and body["facts"] >= 5
    companies = admin.scalars(select(Company).where(Company.workspace_id == ws)).all()
    assert len(companies) == 2  # no second record created for the probable duplicate
    facts = admin.scalars(select(CompanyFact).where(CompanyFact.workspace_id == ws)).all()
    assert all(f.source_url.startswith("https://www.openstreetmap.org/") for f in facts)
    assert {f.source_kind for f in facts} == {"openstreetmap"}
    assert not any("person@" in f.value or "+49" in f.value for f in facts)
    linked_facts = [f for f in facts if f.company_id == existing_id]
    assert linked_facts and all(f.source_url.endswith("node/303") for f in linked_facts)
    # Re-running import is idempotent.
    again = client.post(
        url(ws, f"discovery/runs/{run_id}/import-selected"), json={"keys": [kanzlei["key"]]}
    ).json()
    assert again["duplicates"] == 1 and again["created"] == 0
    detail = client.get(url(ws, f"companies/{kanzlei['company_id'] or companies[0].id}"))
    assert detail.status_code == 200


def test_osm_transient_failure_is_retried_not_failed(context, monkeypatch):
    client, (ws, *_), _ = context
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("OSM_CONTACT", "ops@prospectos.example.test")
    monkeypatch.setattr(osm, "_throttle", lambda: None)

    def down(request):
        return httpx.Response(504, content=json.dumps({"error": "timeout"}).encode())

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda *a, **k: REAL_CLIENT(
            *a,
            transport=httpx.MockTransport(down),
            **{x: y for x, y in k.items() if x != "transport"},
        ),
    )
    search = client.post(
        url(ws, "discovery/searches"),
        json={
            "name": "Down",
            "filters": {"provider": "osm", "city": "Synthetic Town", "industries": ["Handwerk"]},
        },
    ).json()
    queued = client.post(
        url(ws, f"discovery/searches/{search['id']}/run"), json={"confirmed": True}
    ).json()
    assert execute_one(ws)
    job = client.get(url(ws, f"jobs/{queued['id']}")).json()
    assert job["status"] == "retry" and job["last_error"] == "provider_unavailable"


def test_overpass_backs_off_when_public_instance_is_at_capacity(monkeypatch):
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("OSM_CONTACT", "ops@prospectos.example.test")
    monkeypatch.setattr(osm, "_throttle", lambda: None)
    sleeps = []
    monkeypatch.setattr(osm, "_sleep", sleeps.append)
    responses = iter(
        [httpx.Response(502), httpx.Response(429), httpx.Response(200, json={"elements": []})]
    )
    client = httpx.Client(transport=httpx.MockTransport(lambda r: next(responses)))
    assert osm.overpass("[out:json];out count;", client=client) == {"elements": []}
    assert sleeps == [2.0, 4.0]
    # Non-retryable errors surface immediately.
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400)))
    from app.providers.ai import ProviderError

    with pytest.raises(ProviderError, match="provider_rejected"):
        osm.overpass("bad", client=client)
