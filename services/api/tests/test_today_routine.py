"""LinkedIn day routine: daily limit 5–10, outreach stages, follow-ups on day 3 and 7,
style rules in every text. Synthetic companies/people only; nothing contacts LinkedIn."""

from datetime import timedelta

from sqlalchemy import select

from app import style
from app.db import now
from app.linkedin_channel import LinkedInAction
from app.models import Contact
from app.today import QueueItem
from tests.test_today import seed


def setup(client, admin, ws, n=6):
    seed(admin, ws, n)
    w = f"/v1/workspaces/{ws}"
    client.post(f"{w}/icp-profiles/from-template", json={"template": "office_cleaning_ortenau"})
    client.post(f"{w}/contacts/from-impressum", json={})
    return w


def test_daily_limit_is_configurable_visible_and_enforced(context, admin):
    client, (ws, *_), _ = context
    w = setup(client, admin, ws)
    assert client.get(f"{w}/today/settings").json()["daily_limit"] == 7
    assert (
        client.put(
            f"{w}/today/settings", json={"daily_limit": 11, "address_form": "sie"}
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"{w}/today/settings", json={"daily_limit": 4, "address_form": "sie"}
        ).status_code
        == 422
    )
    saved = client.put(
        f"{w}/today/settings",
        json={"daily_limit": 5, "address_form": "sie", "sender_name": "Nico Test"},
    )
    assert saved.status_code == 200 and saved.json()["daily_limit"] == 5
    built = client.post(f"{w}/today/build", json={}).json()
    assert built["created"]["connect"] == 5 and built["daily_limit"] == 5
    day = client.get(f"{w}/today").json()
    assert day["daily"] == {"limit": 5, "sent_last_24h": 0, "queued": 5, "remaining": 5}
    assert all(i["contact"]["stage"] == "new" for i in day["items"])
    client.post(f"{w}/today/approve", json={"all_pending": True})
    for item in day["items"]:
        assert client.post(f"{w}/today/items/{item['id']}/sent", json={}).status_code == 200
    # Stage moved to "gesendet" for every sent request.
    stages = {
        c.outreach_stage
        for c in admin.scalars(
            select(Contact).where(Contact.id.in_([i["contact"]["id"] for i in day["items"]]))
        )
    }
    assert stages == {"sent"}
    assert client.get(f"{w}/today").json()["daily"]["remaining"] == 0
    # Limit reached: no new requests today, and a forged extra item cannot be marked sent.
    assert client.post(f"{w}/today/build", json={}).json()["created"]["connect"] == 0
    extra_contact = admin.scalar(
        select(Contact).where(Contact.workspace_id == ws, Contact.outreach_stage == "new")
    )
    extra = QueueItem(
        workspace_id=ws,
        day=day["day"],
        contact_id=extra_contact.id,
        company_id=extra_contact.company_id,
        kind="connect",
        state="approved",
        note="Hallo",
    )
    admin.add(extra)
    admin.commit()
    r = client.post(f"{w}/today/items/{extra.id}/sent", json={})
    assert r.status_code == 429 and "Tageslimit erreicht: 5" in r.text


def test_stages_follow_outcomes_and_manual_changes(context, admin):
    client, (ws, other, _), _ = context
    w = setup(client, admin, ws, 2)
    client.post(f"{w}/today/build", json={})
    client.post(f"{w}/today/approve", json={"all_pending": True})
    item = client.get(f"{w}/today").json()["items"][0]
    sent = client.post(f"{w}/today/items/{item['id']}/sent", json={}).json()
    cid = item["contact"]["id"]
    assert sent["contact"]["stage"] == "sent" and sent["contact"]["stage_label"] == "gesendet"
    r = client.post(
        f"{w}/linkedin/actions/{sent['action_id']}/outcome", json={"outcome": "accepted"}
    )
    assert r.status_code == 200
    assert admin.get(Contact, cid).outreach_stage == "connected"
    admin.expire_all()
    # Manual: Termin, then kein Interesse; open items for the contact are skipped.
    r = client.put(f"{w}/contacts/{cid}/outreach-stage", json={"stage": "meeting"})
    assert r.json()["stage_label"] == "Termin"
    r = client.put(f"{w}/contacts/{cid}/outreach-stage", json={"stage": "not_interested"})
    assert r.json()["stage"] == "not_interested"
    assert (
        client.put(f"{w}/contacts/{cid}/outreach-stage", json={"stage": "bogus"}).status_code == 422
    )
    pipeline = client.get(f"{w}/today/pipeline").json()
    assert pipeline["counts"]["not_interested"] == 1
    assert pipeline["items"][0]["stage_label"] == "kein Interesse"
    # Tenant isolation: the contact is not reachable through another workspace.
    assert (
        client.put(
            f"/v1/workspaces/{other}/contacts/{cid}/outreach-stage", json={"stage": "meeting"}
        ).status_code
        == 404
    )


def _manual(admin, ws, contact, action, state, days_ago, actor):
    a = LinkedInAction(
        workspace_id=ws,
        contact_id=contact.id,
        actor_id=actor,
        channel="manual",
        action=action,
        state=state,
        content="x",
        simulated=False,
        history=[],
    )
    a.created_at = now() - timedelta(days=days_ago)
    admin.add(a)
    admin.flush()
    return a


def test_followups_on_day_three_and_seven(context, admin):
    client, (ws, *_), user = context
    w = setup(client, admin, ws, 1)
    contact = admin.scalars(select(Contact).where(Contact.workspace_id == ws)).first()
    _manual(admin, ws, contact, "connection_request", "accepted", 10, user)
    first = _manual(admin, ws, contact, "message", "sent", 2, user)
    admin.commit()
    r = client.post(f"{w}/today/build", json={"max_new": 0})
    assert r.status_code == 200, r.text
    built = r.json()
    assert built["created"]["followup"] == 0  # only two days
    first.created_at = now() - timedelta(days=3, minutes=1)
    admin.commit()
    built = client.post(f"{w}/today/build", json={"max_new": 0}).json()
    assert built["created"]["followup"] == 1
    item = next(i for i in client.get(f"{w}/today").json()["items"] if i["kind"] == "followup")
    assert item["followup_days"] == 3 and "kurze Nachfrage" in item["followup"]
    # Day-3 follow-up sent; day 7 suggests the last one.
    client.post(f"{w}/today/approve", json={"item_ids": [item["id"]]})
    assert client.post(f"{w}/today/items/{item['id']}/sent", json={}).status_code == 200
    first.created_at = now() - timedelta(days=7, minutes=1)
    admin.commit()
    r = client.post(f"{w}/today/build", json={"max_new": 0})
    assert r.status_code == 200, r.text
    built = r.json()
    assert built["created"]["followup2"] == 1
    last = next(i for i in client.get(f"{w}/today").json()["items"] if i["kind"] == "followup2")
    assert last["followup_days"] == 7 and "letztes Mal" in last["followup"]
    # An answer stops further follow-ups.
    client.post(f"{w}/today/items/{last['id']}/skip")
    contact = admin.get(Contact, contact.id)
    admin.refresh(contact)
    client.put(f"{w}/contacts/{contact.id}/outreach-stage", json={"stage": "replied"})
    assert client.post(f"{w}/today/build", json={"max_new": 0}).json()["created"] == {
        "connect": 0,
        "message": 0,
        "followup": 0,
        "followup2": 0,
    }


def test_texts_follow_style_and_address_form(context, admin):
    client, (ws, *_), _ = context
    w = setup(client, admin, ws, 1)
    client.put(
        f"{w}/today/settings",
        json={"daily_limit": 5, "address_form": "du", "sender_name": "Nico"},
    )
    client.post(f"{w}/today/build", json={})
    item = client.get(f"{w}/today").json()["items"][0]
    for text in (item["note"], item["message"], item["followup"]):
        assert not style.violations(text), text
    assert item["note"].startswith("Hallo ") and len(item["note"]) <= 200
    assert " Sie " not in item["message"] and "eure Räume" in item["message"]


def test_style_samples_parse_derive_clean_and_sync(context, admin, tmp_path, monkeypatch):
    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    path = tmp_path / "meine-texte.md"
    monkeypatch.setenv("STYLE_SAMPLES_PATH", str(path))
    missing = client.get(f"{w}/style").json()
    assert missing["state"] == "missing" and "meine-texte.md" in missing["hint"]
    path.write_text("<!-- Anleitung: hier eigene Texte einfügen -->\n", encoding="utf-8")
    assert client.get(f"{w}/style").json()["state"] == "empty"
    path.write_text(
        "<!-- Anleitung -->\n"
        "Hallo zusammen,\nheute war ein guter Tag im Büro. Wir haben viel geschafft. Danke an das Team.\n"
        "---\n"
        "Hallo Max,\ndanke für deine Nachricht. Ich melde mich morgen bei dir.\nViele Grüße\nNico\n"
        "---\nzu kurz\n",
        encoding="utf-8",
    )
    state, samples = style.read_samples()
    assert state == "ok" and len(samples) == 2
    stats = style.derive(samples)
    assert stats["formality"] == "Du" and stats["greeting"] == "Hallo"
    assert stats["signoff"] == "Viele Grüße" or stats["signoff"] == ""
    synced = client.post(f"{w}/style/sync").json()
    assert synced["state"] == "ok" and synced["voice_profile_id"] and synced["in_sync"]
    voices = client.get(f"{w}/social/voices").json()["items"]
    assert any(v["name"] == style.PROFILE_NAME for v in voices)
    # Idempotent: no new version without a file change.
    again = client.post(f"{w}/style/sync").json()
    assert again["voice_version"] == synced["voice_version"]
    assert style.clean("Wir reinigen Büros – zuverlässig und schnell — ohne Stress.") == (
        "Wir reinigen Büros, zuverlässig und schnell, ohne Stress."
    )
    assert style.clean("Mo–Fr 7–9 Uhr") == "Mo-Fr 7 bis 9 Uhr"
    assert "erreicht" not in style.clean(
        "Ich hoffe, diese Nachricht erreicht Sie gut. Wir reinigen Büros."
    )


def test_rebuild_refreshes_stale_items_and_drops_hidden_companies(context, admin):
    from app.models import Company

    client, (ws, *_), _ = context
    w = setup(client, admin, ws, 2)
    client.post(f"{w}/today/build", json={})
    items = client.get(f"{w}/today").json()["items"]
    keep, hide = items[0], items[-1]
    # Simulate an item prepared under old rules: dashes in the text ...
    stale = admin.get(QueueItem, keep["id"])
    stale.note = "Guten Tag – alter Text"
    # ... and a company that is now hidden (Autohaus).
    car = admin.get(Company, hide["company"]["id"])
    car.provenance = {"osm_category": "shop=car"}
    car.industry = "Kfz"
    admin.commit()
    built = client.post(f"{w}/today/build", json={}).json()
    assert built["refreshed"]["skipped"] >= 1 and built["refreshed"]["updated"] >= 1
    after = {i["id"]: i for i in client.get(f"{w}/today").json()["items"]}
    assert after[hide["id"]]["state"] == "skipped"
    assert not style.violations(after[keep["id"]]["note"])
