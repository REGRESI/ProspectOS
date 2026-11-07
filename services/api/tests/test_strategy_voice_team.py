"""Content strategy (A/B/C, campaigns, metrics), learning writing profile, team invites.

Mocked LLM only, synthetic people. Nothing is posted or emailed.
"""

from datetime import timedelta

from sqlalchemy import select

from app.db import now
from app.jobs import execute_one
from app.models import Membership, Post, User
from app.voice_learning import derive_rules, merge_rules
from tests.test_content_plan import fake

LLM = {
    "LLM_API_KEY": "x",
    "LLM_MODEL": "gpt-test",
    "LLM_INPUT_USD_PER_MILLION": "0.4",
    "LLM_OUTPUT_USD_PER_MILLION": "1.6",
}


def test_three_versions_differ_in_approach_and_say_why(context, monkeypatch):
    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    for k, v in LLM.items():
        monkeypatch.setenv(k, v)
    prompts = []

    def gen(prompt, sources=None, client=None):
        prompts.append(prompt)
        return fake("Ein Entwurf.\nWARUM: Passt, weil er Vertrauen schafft.")(prompt)

    monkeypatch.setattr("app.providers.ai.generate_text", gen)
    r = client.post(
        f"{w}/social/generate",
        json={
            "topic": "Wie wir Reinigungspreise offenlegen",
            "goal": "trust",
            "audience_key": "ortenau_ceo",
            "pillar": "Transparenz in der Reinigungsbranche",
        },
    )
    assert r.status_code == 202, r.text
    assert execute_one(ws)
    job = client.get(f"{w}/jobs/{r.json()['id']}").json()
    variants = job["result"]["variants"]
    assert [v["approach"] for v in variants] == ["A", "B", "C"]
    assert [v["angle"] for v in variants] == [
        "Provokante These",
        "Persönliche Geschichte",
        "Nützlicher Tipp mit Zahlen",
    ]
    assert all(v["why"] == "Passt, weil er Vertrauen schafft." for v in variants)
    assert all("WARUM" not in v["text"] for v in variants)
    assert "Vertrauen aufbauen" in prompts[0] and "Geschäftsführer Ortenau" in prompts[0]
    assert "Provokante These" in prompts[0] and "Persönliche Geschichte" in prompts[1]
    # The chosen version keeps its strategy on the post.
    post = client.post(
        f"{w}/social/posts",
        json={
            "caption": variants[2]["text"],
            "goal": "trust",
            "audience": "ortenau_ceo",
            "approach": "C",
            "pillar": "Transparenz in der Reinigungsbranche",
        },
    ).json()
    assert (
        post["approach_label"] == "Nützlicher Tipp mit Zahlen"
        and post["goal_label"] == "Vertrauen aufbauen"
    )
    bad = client.post(f"{w}/social/posts", json={"caption": "x", "goal": "viral"})
    assert bad.status_code == 422


def test_campaign_slots_metrics_and_insights(context, admin):
    client, (ws, other, *_), user = context
    w = f"/v1/workspaces/{ws}"
    camp = client.post(
        f"{w}/content/campaigns",
        json={
            "name": "Die neue CleanStar-Website",
            "goal": "leads",
            "audience": "ortenau_ceo",
            "start_date": "2026-11-10",
            "end_date": "2026-11-24",
        },
    )
    assert camp.status_code == 201, camp.text
    cid = camp.json()["id"]
    assert client.get(f"/v1/workspaces/{other}/content/campaigns/{cid}").status_code == 404
    slots = client.post(f"{w}/content/campaigns/{cid}/slots", json={"count": 7}).json()
    days = [p["planned_for"] for p in slots["posts"]]
    # Start Tuesday 10.11., then every second weekday: Tuesday and Thursday.
    assert days == [
        "2026-11-10",
        "2026-11-12",
        "2026-11-17",
        "2026-11-19",
        "2026-11-24",
        "2026-11-26",
        "2026-12-01",
    ]
    assert all(p["placeholder"] and p["goal"] == "leads" for p in slots["posts"])
    assert slots["end_date"] == "2026-12-01"  # extended to the last slot
    # Numbers only for published posts; due 48 h after publication.
    first = slots["posts"][0]["id"]
    assert (
        client.put(
            f"{w}/social/posts/{first}/metrics",
            json={"impressions": 1, "comments": 0, "profile_visits": 0, "inquiries": 0},
        ).status_code
        == 409
    )
    for i, (pillar, approach) in enumerate(
        [("Bauen mit KI", "B"), ("Bauen mit KI", "B"), ("Unternehmeralltag", "A")]
    ):
        post = Post(
            workspace_id=ws,
            author_id=user,
            caption=f"Synthetischer Beitrag {i}",
            state="published_manually",
            pillar=pillar,
            approach=approach,
            studio_context={
                "manual_publication": {"at": (now() - timedelta(hours=50)).isoformat()}
            },
        )
        admin.add(post)
    admin.commit()
    due = client.get(f"{w}/content/insights").json()["due"]
    assert len(due) == 3
    numbers = [(900, 6, 10, 1), (1100, 4, 8, 1), (3000, 1, 2, 0)]
    for item, (imp, com, vis, inq) in zip(
        sorted(due, key=lambda d: d["caption"]), numbers, strict=True
    ):
        r = client.put(
            f"{w}/social/posts/{item['id']}/metrics",
            json={"impressions": imp, "comments": com, "profile_visits": vis, "inquiries": inq},
        )
        assert r.status_code == 200, r.text
    insights = client.get(f"{w}/content/insights").json()
    assert insights["due"] == [] and insights["measured_posts"] == 3
    assert insights["pillars"][0]["name"] == "Bauen mit KI"
    assert insights["approaches"][0]["name"] == "B Persönliche Geschichte"
    assert "Bauen mit KI" in insights["hint"] and "Persönliche Geschichte" in insights["hint"]


def test_edits_and_feedback_become_editable_rules():
    edits = [
        (
            "Hallo zusammen! 🚀 Wir revolutionieren heute die Reinigung. Ganz ehrlich, das ist spannend!",
            "Wir machen Reinigung planbar. Was ist dir wichtig?",
        ),
        (
            "Hallo zusammen! ✨ Ganz ehrlich, wir revolutionieren das Büro. Innovativ und nachhaltig!",
            "Saubere Büros, feste Ansprechpartner. Was fehlt dir?",
        ),
    ]
    rules = derive_rules(edits, [("no", "zu werblich")])
    keys = {r["key"] for r in rules}
    assert {"shorter", "no_emoji", "no_exclamation", "avoid_words", "end_question"} <= keys
    avoid = next(r for r in rules if r["key"] == "avoid_words")
    assert "revolutionieren" in avoid["text"] and "ehrlich" in avoid["text"]
    assert any(r["text"] == "Nicht: zu werblich" for r in rules)
    merged = merge_rules([], rules, dismissed=["no_emoji"])
    assert "no_emoji" not in {r["key"] for r in merged}
    edited = [dict(merged[0], text="Maximal 800 Zeichen.", source="edited")]
    again = merge_rules(edited, rules, dismissed=[])
    assert (
        again[0]["text"] == "Maximal 800 Zeichen."
        and len([r for r in again if r["key"] == merged[0]["key"]]) == 1
    )


def test_writing_profile_learns_from_post_edits(context, monkeypatch):
    client, (ws, other, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    for _i, (old, new) in enumerate(
        [
            (
                "Ganz ehrlich, wir revolutionieren die Reinigung! 🚀 Mega spannend!",
                "Wir machen Reinigung planbar.",
            ),
            (
                "Ganz ehrlich, wir revolutionieren das Büro! ✨ Absolut innovativ!",
                "Saubere Büros. Feste Teams.",
            ),
        ]
    ):
        post = client.post(f"{w}/social/posts", json={"caption": old}).json()
        r = client.patch(
            f"{w}/social/posts/{post['id']}",
            json={"caption": new, "version": post["version"]},
        )
        assert r.status_code == 200, r.text
    profile = client.post(
        f"{w}/writing-profile/feedback",
        json={"verdict": "no", "reason": "zu werblich", "post_id": post["id"]},
    ).json()
    assert profile["counts"]["edits"] == 2 and profile["counts"]["no"] == 1
    assert profile["recent_edits"][0]["edited"] == "Saubere Büros. Feste Teams."
    texts = [r["text"] for r in profile["rules"]]
    assert "Keine Emojis." in texts and "Nicht: zu werblich" in texts
    rule = next(r for r in profile["rules"] if r["key"] == "no_emoji")
    edited = client.patch(
        f"{w}/writing-profile/rules/{rule['id']}",
        json={"text": "Gar keine Emojis, auch keine Häkchen."},
    ).json()
    assert any(r["source"] == "edited" for r in edited["rules"])
    relearned = client.post(f"{w}/writing-profile/relearn").json()
    assert "Gar keine Emojis, auch keine Häkchen." in [r["text"] for r in relearned["rules"]]
    assert "Keine Emojis." not in [r["text"] for r in relearned["rules"]]
    own = client.post(
        f"{w}/writing-profile/rules", json={"text": "Immer mit einem Beispiel aus Offenburg."}
    ).json()
    assert own["rules"][-1]["source"] == "manual"
    insp = client.post(
        f"{w}/writing-profile/inspirations",
        json={
            "author": "Beispiel Autorin",
            "text": "Ein fremder Post, der mir gefällt, weil er kurz und klar ist.",
        },
    ).json()
    assert insp["inspirations"][0]["author"] == "Beispiel Autorin"
    # Rules and style references reach the next suggestion.
    for k, v in LLM.items():
        monkeypatch.setenv(k, v)
    prompts = []
    monkeypatch.setattr(
        "app.providers.ai.generate_text",
        lambda prompt, sources=None, client=None: prompts.append(prompt) or fake("Text")(prompt),
    )
    client.post(f"{w}/social/generate", json={"topic": "Ein Thema für den Test"})
    assert execute_one(ws)
    assert (
        "Gar keine Emojis" in prompts[0] and "Immer mit einem Beispiel aus Offenburg." in prompts[0]
    )
    assert "Ein fremder Post, der mir gefällt" in prompts[0] and "niemals Inhalte" in prompts[0]
    # Per workspace and per user: nothing leaks into another workspace.
    assert client.get(f"/v1/workspaces/{other}/writing-profile").json()["counts"]["edits"] == 0


def test_team_invite_link_register_and_roles(context, admin):
    client, (ws, other, *_), user = context
    w = f"/v1/workspaces/{ws}"
    team = client.get(f"{w}/team").json()
    assert team["mail"] == "link" and team["members"][0]["role_label"] == "Inhaber"
    bad = client.post(f"{w}/team/invites", json={"email": "kein-mail", "role": "member"})
    assert bad.status_code == 422
    inv = client.post(
        f"{w}/team/invites", json={"email": "Lino.Test@Example.test", "role": "member"}
    )
    assert inv.status_code == 201, inv.text
    body = inv.json()
    assert body["delivery"] == "link" and "/einladung#" in body["link"]
    token = body["link"].split("#", 1)[1]
    owner_inv = client.post(
        f"{w}/team/invites", json={"email": "eknoor.test@example.test", "role": "owner"}
    ).json()
    assert owner_inv["role_label"] == "Inhaber"
    assert len(client.get(f"{w}/team").json()["invites"]) == 2

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as guest:
        preview = guest.get(f"/v1/invites/{token}").json()
        assert preview["email"] == "lino.test@example.test" and preview["role_label"] == "Mitglied"
        assert preview["can_register"]
        short = guest.post(
            f"/v1/invites/{token}/register", json={"name": "Lino", "password": "kurz"}
        )
        assert short.status_code == 422
        joined = guest.post(
            f"/v1/invites/{token}/register",
            json={"name": "Lino Test", "password": "LangesPasswort2026"},
        )
        assert joined.status_code == 200, joined.text
        assert joined.json()["workspace_id"] == ws
        assert [x["id"] for x in joined.json()["workspaces"]] == [ws]
        guest.headers["X-CSRF-Token"] = joined.json()["csrf_token"]
        # Single use.
        assert (
            guest.post(
                f"/v1/invites/{token}/register",
                json={"name": "Noch Einmal", "password": "LangesPasswort2026"},
            ).status_code
            == 404
        )
        # Own writing profile, not the owner's; members cannot invite owners.
        assert guest.get(f"{w}/writing-profile").json()["counts"]["edits"] == 0
        assert (
            guest.post(
                f"{w}/team/invites", json={"email": "x@example.test", "role": "owner"}
            ).status_code
            == 403
        )
        assert guest.get(f"/v1/workspaces/{other}/team").status_code in (403, 404)
    lino = admin.scalar(select(User).where(User.email == "lino.test@example.test"))
    assert admin.get(Membership, (ws, lino.id)).role == "editor"
    members = client.get(f"{w}/team").json()["members"]
    assert {m["role_label"] for m in members} == {"Inhaber", "Mitglied"}
    assert client.delete(f"{w}/team/members/{user}").status_code == 409  # not yourself
    assert client.delete(f"{w}/team/members/{lino.id}").status_code == 200
    admin.expire_all()
    assert admin.get(Membership, (ws, lino.id)) is None
