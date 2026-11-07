"""M8 job agent + autopilot with synthetic OSM results and a faked website research."""

from datetime import timedelta

from sqlalchemy import select

from app import agent
from app.db import now
from app.jobs import execute_one
from app.models import Company, Contact
from app.platform_models import Campaign, Job
from app.providers import osm, site_research
from app.today import QueueItem


def fake_places(center, radius, categories, keywords, limit, client=None):
    return [
        osm.OsmCandidate(
            external_key=f"node/{i}",
            company=f"Synthetische Kanzlei {i}",
            location="Offenburg",
            address=f"Testweg {i}, 77652 Offenburg",
            industry="Rechtsberatung",
            osm_category="office=lawyer",
            website=f"https://k{i}.example",
            latitude=48.47,
            longitude=7.94,
            distance_km=1.0 + i,
            source_url=f"https://www.openstreetmap.org/node/{i}",
            observed_at=now().isoformat(),
        )
        for i in range(3)
    ]


def fake_research(url, client=None):
    page = {
        "url": url + "/impressum",
        "title": "",
        "lines": ["Impressum", "Geschäftsführer: Erika Fiktiv"],
        "links": [],
        "mailto": [],
    }
    return {
        "website": url,
        "retrieved_at": now().isoformat(),
        "impressum_url": page["url"],
        "impressum": site_research.extract_impressum(page),
        "pages": [{"url": page["url"], "title": "", "text": "Geschäftsführer: Erika Fiktiv"}],
        "robots": "honoured",
    }


def drain(admin, ws, rounds=40):
    for _ in range(rounds):
        for job in admin.scalars(select(Job).where(Job.workspace_id == ws, Job.status == "queued")):
            job.available_at = now() - timedelta(seconds=1)
        admin.commit()
        if not execute_one(ws):
            break


def test_parse_and_estimate():
    plan = agent.parse_instruction(
        "Finde 200 Firmen in meiner Region, recherchiere sie, priorisiere sie und bereite eine Kampagne vor",
        "Offenburg",
    )
    assert plan["place"] == "Offenburg" and plan["companies"] == 200 and plan["radius_km"] == 30
    assert plan["steps"] == ["discover", "import", "research", "rank", "contacts", "campaign"]
    plan = agent.parse_instruction(
        "Suche 50 Unternehmen im Umkreis von 20 km um Lahr und fülle die Tagesliste", ""
    )
    assert plan["place"] == "Lahr" and plan["radius_km"] == 20 and "today" in plan["steps"]
    assert agent.estimate(plan)["total_minor"] == 0


def test_agent_run_end_to_end_and_autopilot(context, admin, monkeypatch):
    client, (ws, other, *_), _ = context
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("OSM_CONTACT", "ops@prospectos.example.test")
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    monkeypatch.setattr(osm, "search_places", fake_places)
    monkeypatch.setattr(
        osm,
        "geocode",
        lambda place, country="", client=None: osm.GeoPoint(
            latitude=48.47,
            longitude=7.94,
            display_name="Offenburg",
            source_url="https://www.openstreetmap.org",
        ),
    )
    monkeypatch.setattr(site_research, "research_site", fake_research)
    w = f"/v1/workspaces/{ws}"
    client.post(f"{w}/icp-profiles/from-template", json={"template": "office_cleaning_ortenau"})
    planned = client.post(
        f"{w}/agent/plan",
        json={
            "instruction": "Finde 20 Firmen in meiner Region, recherchiere sie, priorisiere sie, bereite eine Kampagne vor und fülle die Tagesliste für LinkedIn"
        },
    )
    assert planned.status_code == 201, planned.text
    run = planned.json()
    assert run["status"] == "planned" and run["estimate"]["lines"][0]["label"] == "Firmen suchen"
    assert not admin.scalars(
        select(Job).where(Job.workspace_id == ws)
    ).all()  # nothing runs before confirmation
    assert client.post(f"/v1/workspaces/{other}/agent/runs/{run['id']}/confirm").status_code == 404
    assert client.post(f"{w}/agent/runs/{run['id']}/confirm").json()["status"] == "running"
    drain(admin, ws)
    done = client.get(f"{w}/agent/runs/{run['id']}").json()
    assert done["status"] == "done", done["progress"]
    assert all(p["status"] == "done" for p in done["progress"])
    assert done["results"]["imported"]["companies"] == 3
    assert done["results"]["top"][0]["name"].startswith("Synthetische Kanzlei")
    assert done["results"]["contacts_created"] == 3
    campaign = admin.get(Campaign, done["results"]["campaign_id"])
    assert campaign is not None
    # Impressum contacts have no verified LinkedIn profile yet: they do not reach "Heute".
    assert len(admin.scalars(select(QueueItem).where(QueueItem.workspace_id == ws)).all()) == 0
    assert len(admin.scalars(select(Company).where(Company.workspace_id == ws)).all()) == 3
    assert len(admin.scalars(select(Contact).where(Contact.workspace_id == ws)).all()) == 3

    # Autopilot: enabled once per day after the configured hour.
    r = client.put(
        f"{w}/agent/autopilot",
        json={"enabled": True, "place": "Offenburg", "new_companies": 10, "research": 2, "hour": 0},
    )
    assert r.status_code == 200 and r.json()["plan"]["steps"][0] == "discover"
    assert agent.autopilot_tick() >= 1
    assert agent.autopilot_tick() == 0  # same day
    runs = client.get(f"{w}/agent/runs").json()["items"]
    assert runs[0]["kind"] == "autopilot" and runs[0]["status"] == "running"


def test_worker_process_has_import_hooks():
    """Regression: the worker process must reach the shared import logic without app.main."""
    import subprocess
    import sys

    code = (
        "import app.jobs, app.agent; from app.journeys import HOOKS;"
        "app.agent.ensure_hooks(); assert 'import_discovery_results' in HOOKS"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-500:]


def test_region_disambiguates_homonym_places(context, monkeypatch):
    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    client.post(f"{w}/icp-profiles/from-template", json={"template": "office_cleaning_ortenau"})
    run = client.post(f"{w}/agent/plan", json={"instruction": "Finde 20 Firmen um Lahr"}).json()
    assert run["plan"]["place"] == "Lahr" and run["plan"]["region"] == "Ortenaukreis"
    payload = agent._discovery_payload(run["plan"])
    assert payload["osm"]["place"] == "Lahr, Ortenaukreis"
