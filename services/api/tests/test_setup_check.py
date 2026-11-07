"""Setup check traffic lights (synthetic env values; nothing is called)."""

from sqlalchemy.orm import Session

from app.models import Workspace
from tests.conftest import admin_engine

KEYS = (
    "LINKEDIN_CLIENT_ID",
    "LINKEDIN_CLIENT_SECRET",
    "LINKEDIN_REDIRECT_URI",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_INPUT_USD_PER_MILLION",
    "LLM_OUTPUT_USD_PER_MILLION",
    "IMAGE_MODEL",
    "IMAGE_API_KEY",
    "IMAGE_MAX_COST_USD_CENTS",
    "IMAGE_TEXT_INPUT_USD_PER_MILLION",
    "IMAGE_OUTPUT_USD_PER_MILLION",
    "OSM_DISCOVERY_ENABLED",
    "OSM_CONTACT",
    "OSM_EXTRACT_PATH",
    "BRAVE_SEARCH_API_KEY",
)


def test_lights_and_next_steps(context, monkeypatch, tmp_path):
    client, (ws, other, _), _ = context
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("STYLE_SAMPLES_PATH", str(tmp_path / "none.md"))
    r = client.get(f"/v1/workspaces/{ws}/setup-check").json()
    lights = {i["key"]: i for i in r["items"]}
    assert list(lights) == ["linkedin", "llm", "image", "osm", "brave", "mailbox", "style"]
    assert lights["linkedin"]["light"] == "red" and "Client ID" in lights["linkedin"]["next"]
    assert lights["mailbox"]["light"] == "off"
    assert lights["mailbox"]["status"] == "noch nicht verbunden"
    assert lights["style"]["light"] == "yellow"
    # Configure synthetic values: lights move without any value being returned.
    extract = tmp_path / "x.osm.pbf"
    extract.write_bytes(b"0" * 10)
    for k, v in {
        "LINKEDIN_CLIENT_ID": "synthetic-id",
        "LINKEDIN_CLIENT_SECRET": "synthetic-secret-1234",
        "LINKEDIN_REDIRECT_URI": "http://localhost:3000/v1/integrations/linkedin/callback",
        "OSM_DISCOVERY_ENABLED": "true",
        "OSM_CONTACT": "ops@example.test",
        "OSM_EXTRACT_PATH": str(extract),
        "BRAVE_SEARCH_API_KEY": "synthetic-brave-0000",
    }.items():
        monkeypatch.setenv(k, v)
    r = client.get(f"/v1/workspaces/{ws}/setup-check")
    assert "synthetic-secret" not in r.text and "synthetic-brave" not in r.text
    lights = {i["key"]: i for i in r.json()["items"]}
    assert lights["linkedin"]["light"] == "yellow" and "verbinden" in lights["linkedin"]["next"]
    assert lights["osm"]["light"] == "green"
    assert lights["brave"]["light"] == "yellow"  # configured, not tested
    monkeypatch.setenv("IMAGE_MODEL", "synthetic-image")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-key")
    monkeypatch.setenv("IMAGE_MAX_COST_USD_CENTS", "100")
    image = {i["key"]: i for i in client.get(f"/v1/workspaces/{ws}/setup-check").json()["items"]}
    assert "Bildpreise fehlen" in image["image"]["status"]
    with Session(admin_engine) as db, db.begin():
        db.get(Workspace, other).kind = "demo"
    demo = client.get(f"/v1/workspaces/{other}/setup-check").json()
    assert demo["items"][0]["status"] == "Demo-Workspace"
