"""M7 content planner with a mocked LLM (no provider call)."""

from app.jobs import execute_one
from app.providers.ai import GenerationResult

PLAN_TEXT = "\n".join(
    ["ROTER FADEN: Vom Problem sauberer Büros zur verlässlichen Partnerschaft."]
    + [
        f"W{w}|{d}|{p}|Thema {w}{d}|Hook {w}{d}|Text"
        for w in range(1, 7)
        for d, p in (
            ("Di", "Sauberkeit & Gesundheit"),
            ("Do", "Einblicke ins Team"),
            ("Fr", "Regionales"),
        )
    ]
    + ["W7|Mo|Sauberkeit & Gesundheit|zu spät|x|Text", "W1|Sa|Unbekannt|x|y|Text", "kaputt"]
)


def fake(text):
    return lambda prompt, sources=None, client=None: GenerationResult(
        text=text,
        citations=[],
        unverified_claims=[],
        model="gpt-test",
        input_tokens=10,
        output_tokens=10,
        estimated_cost_microunits=10,
    )


def test_plan_variants_and_manual_publication(context, monkeypatch):
    client, (ws, other, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    for k, v in {
        "LLM_API_KEY": "x",
        "LLM_MODEL": "gpt-test",
        "LLM_INPUT_USD_PER_MILLION": "0.4",
        "LLM_OUTPUT_USD_PER_MILLION": "1.6",
    }.items():
        monkeypatch.setenv(k, v)
    voice = client.post(
        f"{w}/social/voices",
        json={
            "name": "Nico",
            "examples": [
                {"label": f"Bsp {i}", "text": f"Beispieltext {i} kurz und direkt."}
                for i in range(5)
            ],
        },
    )
    assert voice.status_code in (200, 201), voice.text
    monkeypatch.setattr("app.providers.ai.generate_text", fake(PLAN_TEXT))
    body = {
        "name": "CleanStar Q4",
        "goal": "Sichtbarkeit bei Büroleitungen in der Ortenau",
        "audience": "Büro- und Praxisleitungen",
        "pillars": ["Sauberkeit & Gesundheit", "Einblicke ins Team", "Regionales"],
        "cadence": 2,
        "weeks": 6,
        "voice_profile_id": voice.json()["id"],
    }
    assert (
        client.post(f"/v1/workspaces/{other}/content/plans", json=body).status_code == 404
    )  # foreign voice id
    r = client.post(f"{w}/content/plans", json=body)
    assert r.status_code == 202, r.text
    assert execute_one(ws)
    plan = client.get(f"{w}/content/plans/{r.json()['id']}").json()
    assert plan["status"] == "ready" and plan["storyline"].startswith("Vom Problem")
    assert len(plan["items"]) == 12  # 2 per week × 6 weeks, invalid lines dropped
    assert {i["week"] for i in plan["items"]} == set(range(1, 7))

    item = plan["items"][0]
    monkeypatch.setattr(
        "app.providers.ai.generate_text",
        fake("VARIANTE A:\nText A\nVARIANTE B:\nText B\nBILDIDEE:\nHelles Büro"),
    )
    assert (
        client.post(f"{w}/content/plans/{plan['id']}/items/{item['id']}/draft").status_code == 202
    )
    assert execute_one(ws)
    plan = client.get(f"{w}/content/plans/{plan['id']}").json()
    drafted = plan["items"][0]
    assert drafted["status"] == "drafted" and drafted["post"]["variants"] == ["Text A", "Text B"]
    assert drafted["post"]["image_idea"] == "Helles Büro"
    assert (
        client.post(f"{w}/content/plans/{plan['id']}/items/{item['id']}/draft").status_code == 409
    )
    post_id = drafted["post_id"]
    assert (
        client.post(f"{w}/social/posts/{post_id}/mark-published", json={}).status_code == 409
    )  # not approved
    client.post(f"{w}/social/posts/{post_id}/submit-review")
    assert client.post(f"{w}/social/posts/{post_id}/approve").status_code == 200
    bad = client.post(
        f"{w}/social/posts/{post_id}/mark-published", json={"url": "https://evil.example/x"}
    )
    assert bad.status_code == 422
    ok = client.post(
        f"{w}/social/posts/{post_id}/mark-published",
        json={"url": "https://www.linkedin.com/feed/update/urn:li:activity:1/"},
    ).json()
    assert ok["state"] == "published_manually" and ok["provider_post_id"] is None


def test_worker_process_can_map_models_without_main():
    """Regression: the worker never imports app.main; every FK target must be registered."""
    import subprocess
    import sys

    code = (
        "import app.jobs, app.content_plan, app.today, app.email_outreach, app.research_flow;"
        "from app.db import Base;"
        "[fk.column for t in Base.metadata.tables.values() for fk in t.foreign_keys]"
    )
    assert subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0
