"""M5 autopilot for the Ortenaukreis: daily town rotation, budget limit with the usage
ledger, and texts prepared with the workspace sender settings. Synthetic OSM results;
no provider is called."""

from sqlalchemy import select

from app import agent
from app.models import Contact
from app.today import QueueItem
from tests.test_agent import drain, fake_places, fake_research


def test_budget_fits_paid_steps():
    import os

    plan = {
        "steps": ["discover", "import", "research", "profile", "rank"],
        "profiles": 20,
        "provider": "osm",
        "research": 5,
    }

    os.environ["LLM_INPUT_USD_PER_MILLION"] = "2"
    os.environ["LLM_OUTPUT_USD_PER_MILLION"] = "8"
    try:
        full = agent.estimate(plan)["total_minor"]
        assert full > 0
        fitted = agent.budgeted(plan, budget_minor=full // 2, remaining_minor=None)
        assert 0 < fitted["profiles"] < 20 and "begrenzt" in fitted["budget_note"]
        none = agent.budgeted(plan, budget_minor=0, remaining_minor=None)
        assert none["profiles"] == 0 and "profile" not in none["steps"]
        assert "nur kostenlose" in none["budget_note"]
        # Workspace budget is the tighter bound.
        tight = agent.budgeted(plan, budget_minor=10_000, remaining_minor=0)
        assert tight["profiles"] == 0
        assert agent.budgeted(plan, 10_000, None)["budget_note"] == ""
    finally:
        os.environ.pop("LLM_INPUT_USD_PER_MILLION")
        os.environ.pop("LLM_OUTPUT_USD_PER_MILLION")


def test_area_rotation():
    plan = {"place": "Ortenaukreis", "radius_km": 30}
    towns = [agent.todays_area(plan, i)["place"] for i in range(len(agent.ROTATION) + 1)]
    assert towns[0] == "Offenburg" and towns[1] == "Lahr" and towns[-1] == "Offenburg"
    assert agent.todays_area(plan, 0)["radius_km"] == 12
    assert agent.todays_area({"place": "Kehl", "radius_km": 20}, 5)["place"] == "Kehl"


def test_autopilot_ortenau_run_prepares_texts_for_approval(context, admin, monkeypatch):
    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    monkeypatch.setenv("OSM_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("OSM_CONTACT", "test@example.invalid")
    monkeypatch.setenv("RESEARCH_ENABLED", "true")
    # Stand-in for the Brave check: every Impressum contact counts as verified here.
    monkeypatch.setattr("app.today.has_profile", lambda contact: True)
    monkeypatch.setattr(osm_mod(), "search_places", fake_places)
    monkeypatch.setattr(
        osm_mod(),
        "geocode",
        lambda place, country="", client=None: osm_mod().GeoPoint(
            latitude=48.47, longitude=7.94, display_name=place, source_url="https://osm.org/"
        ),
    )
    from app.providers import site_research

    monkeypatch.setattr(site_research, "research_site", fake_research)
    client.post(f"{w}/icp-profiles/from-template", json={"template": "office_cleaning_ortenau"})
    client.put(
        f"{w}/today/settings",
        json={"daily_limit": 5, "address_form": "sie", "sender_name": "Nico Test"},
    )
    r = client.put(
        f"{w}/agent/autopilot",
        json={
            "enabled": True,
            "place": "Ortenaukreis",
            "new_companies": 10,
            "research": 3,
            "hour": 0,
            "budget_minor": 0,
        },
    )
    assert r.status_code == 200 and r.json()["next_area"] == "Offenburg"
    assert agent.autopilot_tick() >= 1
    info = client.get(f"{w}/agent/autopilot").json()
    assert info["next_area"] == "Lahr"  # cursor advanced
    run = info["recent"][0]
    assert run["place"] == "Offenburg" and run["ledger"]["actual_minor"] == 0
    drain(admin, ws)
    done = client.get(f"{w}/agent/runs/{run['id']}").json()
    assert done["status"] == "done", done["progress"]
    assert done["ledger"]["budget_minor"] == 0
    assert "profile" not in done["plan"]["steps"]  # no paid step without budget
    items = admin.scalars(select(QueueItem).where(QueueItem.workspace_id == ws)).all()
    assert items and all(i.state == "pending" for i in items)  # human approves
    assert all("Nico Test" in i.message for i in items)
    today_step = next(p for p in done["progress"] if p["step"] == "today")
    assert "Limit 5" in today_step["detail"] and "freigeben" in today_step["detail"]
    assert admin.scalars(select(Contact).where(Contact.workspace_id == ws)).all()


def osm_mod():
    from app.providers import osm

    return osm
