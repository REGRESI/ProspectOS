"""V3 M8: lead sources with one interface and a per-source quality report."""

from app.models import Company, Contact
from app.platform_models import Job
from tests.test_v3_channels import w


def test_quality_report_per_source(context, admin, monkeypatch):
    client, (ws, other, foreign), user_id = context
    monkeypatch.delenv("OSM_DISCOVERY_ENABLED", raising=False)
    monkeypatch.delenv("OSM_EXTRACT_PATH", raising=False)
    osm = [
        Company(
            workspace_id=ws,
            name=f"OSM Fiktiv {i}",
            identity=f"openstreetmap:node/{i}",
            source="openstreetmap",
            provenance={},
        )
        for i in range(4)
    ]
    admin.add_all(osm)
    admin.flush()
    admin.add_all(
        [
            Contact(
                workspace_id=ws,
                company_id=osm[0].id,
                first_name="A",
                source="impressum https://a.example.test",
                linkedin_url="https://www.linkedin.com/in/synthetic-a",
                linkedin_status="verified",
            ),
            Contact(
                workspace_id=ws,
                company_id=osm[1].id,
                first_name="B",
                source="impressum https://b.example.test",
                linkedin_status="not_found",
            ),
            Contact(workspace_id=ws, first_name="C", source="csv_upload"),
            Job(
                workspace_id=ws,
                actor_id=user_id,
                kind="discovery",
                payload={"provider": "osm"},
                status="failed",
                last_error="provider_unavailable",
                idempotency_key="v3-src-1",
            ),
        ]
    )
    admin.commit()
    data = client.get(w(ws, "/sources")).json()
    by_id = {s["id"]: s for s in data["items"]}
    assert set(by_id) == {"osm", "northdata", "pdl", "impressum", "csv", "brave", "manual"}
    o = by_id["osm"]
    assert o["ready"] is False and "OSM_CONTACT" in o["reason"]
    assert o["quality"]["hits"] == 4 and o["quality"]["hits_unit"] == "Firmen"
    assert o["quality"]["contact_rate"] == 0.5
    assert o["quality"]["verified_linkedin_rate"] == 0.5
    assert o["quality"]["errors"] == {"provider_unavailable": 1}
    assert (
        by_id["impressum"]["quality"]["hits"] == 2
        and by_id["impressum"]["quality"]["hits_unit"] == "Kontakte"
    )
    assert by_id["csv"]["quality"]["hits"] == 1 and by_id["csv"]["ready"] is True
    brave = by_id["brave"]["quality"]
    assert brave["contacts"] == 2 and brave["verified_linkedin"] == 1
    assert any("handelsregister.de" in o["name"] for o in data["register_options"])
    # Other workspaces see none of this.
    assert client.get(w(other, "/sources")).json()["items"][0]["quality"]["hits"] == 0
    assert client.get(w(foreign, "/sources")).status_code == 404
