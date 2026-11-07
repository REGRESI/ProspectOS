"""Probe-Post and publish readiness: nothing is published by preparing; the official
publish path needs approval, the env flag and the w_member_social scope. A two-week plan
with 3 posts/week uses the file voice and the style rules. All data synthetic; the LLM
and LinkedIn are never called."""

from datetime import timedelta

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app import style
from app.db import now
from app.jobs import execute_one
from app.models import Workspace
from app.platform_models import Connection
from tests.conftest import admin_engine
from tests.test_content_plan import fake


def connect(admin, ws, user, scopes=("openid", "profile", "w_member_social")):
    key = Fernet.generate_key()
    admin.add(
        Connection(
            workspace_id=ws,
            provider="linkedin",
            user_id=user,
            encrypted_token=Fernet(key).encrypt(b"synthetic-token").decode(),
            author_urn="urn:li:person:synthetic",
            scopes=list(scopes),
            expires_at=now() + timedelta(days=30),
        )
    )
    admin.commit()
    return key


def test_probe_post_is_prepared_never_published(context, admin, monkeypatch):
    client, (ws, other, _), user = context
    w = f"/v1/workspaces/{ws}"
    monkeypatch.setenv("LINKEDIN_PUBLISHING_APPROVED", "false")
    monkeypatch.setenv("LINKEDIN_API_VERSION", "202610")
    r = client.get(f"{w}/social/publish-readiness").json()
    assert not r["ready"]
    by = {c["key"]: c for c in r["checks"]}
    assert not by["flag"]["ok"] and not by["connected"]["ok"] and by["role"]["ok"]
    key = connect(admin, ws, user)
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key.decode())
    created = client.post(f"{w}/social/probe-post")
    assert created.status_code == 201, created.text
    post = created.json()
    assert post["state"] == "draft" and post["studio_context"]["probe"] is True
    assert not style.violations(post["caption"])
    again = client.post(f"{w}/social/probe-post").json()
    assert again["existing"] and again["id"] == post["id"]
    # Not approved: refused.
    assert client.post(f"{w}/social/posts/{post['id']}/publish", json={}).status_code in (409, 503)
    client.post(f"{w}/social/posts/{post['id']}/submit-review")
    client.post(f"{w}/social/posts/{post['id']}/approve")
    # Approved but flag false: refused, nothing enqueued.
    refused = client.post(f"{w}/social/posts/{post['id']}/publish", json={})
    assert refused.status_code == 503
    # With the flag every check is green; publishing would now need the explicit click.
    monkeypatch.setenv("LINKEDIN_PUBLISHING_APPROVED", "true")
    assert client.get(f"{w}/social/publish-readiness").json()["ready"]


def test_probe_post_refused_in_demo_and_missing_scope(context, admin, monkeypatch):
    client, (ws, other, _), user = context
    with Session(admin_engine) as db, db.begin():
        db.get(Workspace, other).kind = "demo"
    assert client.post(f"/v1/workspaces/{other}/social/probe-post").status_code == 409
    connect(admin, ws, user, scopes=("openid", "profile"))
    r = client.get(f"/v1/workspaces/{ws}/social/publish-readiness").json()
    assert not {c["key"]: c for c in r["checks"]}["scope"]["ok"]


def test_two_week_plan_three_posts_uses_file_voice(context, monkeypatch, tmp_path):
    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    for k, v in {
        "LLM_API_KEY": "x",
        "LLM_MODEL": "gpt-test",
        "LLM_INPUT_USD_PER_MILLION": "0.4",
        "LLM_OUTPUT_USD_PER_MILLION": "1.6",
    }.items():
        monkeypatch.setenv(k, v)
    samples = tmp_path / "meine-texte.md"
    samples.write_text(
        "Hallo zusammen,\nheute haben wir ein neues Büro übernommen. Kurz und knapp: läuft.\n---\n"
        "Hallo Max,\ndanke für deine Nachricht. Ich melde mich morgen bei dir.\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("STYLE_SAMPLES_PATH", str(samples))
    voice_id = client.post(f"{w}/style/sync").json()["voice_profile_id"]
    plan_text = "\n".join(
        ["ROTER FADEN: Saubere Büros in der Ortenau – Schritt für Schritt."]
        + [
            f"W{wk}|{d}|{p}|Thema {wk}{d}|Hook {wk}{d}|Bild"
            for wk in (1, 2)
            for d, p in (("Mo", "Alltag"), ("Mi", "Region"), ("Fr", "Tipps"))
        ]
    )
    captured = {}

    def capture(text):
        inner = fake(text)

        def call(prompt, sources=None, client=None):
            captured.setdefault("prompts", []).append(prompt)
            return inner(prompt, sources, client)

        return call

    monkeypatch.setattr("app.providers.ai.generate_text", capture(plan_text))
    r = client.post(
        f"{w}/content/plans",
        json={
            "name": "CleanStar · 2 Wochen",
            "goal": "Sichtbarkeit bei Büro- und Praxisleitungen in der Ortenau",
            "audience": "Büro- und Praxisleitungen",
            "pillars": ["Alltag", "Region", "Tipps"],
            "cadence": 3,
            "weeks": 2,
        },
    )
    assert r.status_code == 202, r.text
    assert execute_one(ws)
    plan = client.get(f"{w}/content/plans/{r.json()['id']}").json()
    assert plan["voice_profile_id"] == voice_id  # default: profile from meine-texte.md
    assert len(plan["items"]) == 6 and {i["week"] for i in plan["items"]} == {1, 2}
    assert "Kein Gedankenstrich" in captured["prompts"][0]
    monkeypatch.setattr(
        "app.providers.ai.generate_text",
        capture(
            "VARIANTE A:\nWir reinigen – zuverlässig.\nVARIANTE B:\nText B — kurz.\nBILDIDEE:\nBüro"
        ),
    )
    item = plan["items"][0]
    client.post(f"{w}/content/plans/{plan['id']}/items/{item['id']}/draft")
    assert execute_one(ws)
    assert "Text 1" in captured["prompts"][-1] or "Stilbeispiele" in captured["prompts"][-1]
    drafted = client.get(f"{w}/content/plans/{plan['id']}").json()["items"][0]["post"]
    assert drafted["variants"] == ["Wir reinigen, zuverlässig.", "Text B, kurz."]
