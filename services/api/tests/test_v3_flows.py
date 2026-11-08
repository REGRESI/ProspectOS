"""V3 M2: campaign builder runs. Synthetic data; time is moved by calling the engine with a
later timestamp instead of sleeping."""

from datetime import timedelta

from sqlalchemy import select

from app.db import now
from app.flows import FlowRun, FlowTask, tick
from app.jobs import tenant
from tests.test_v3_channels import firm, person, w


def two_contacts(client, admin, ws):
    company = firm(admin, ws)
    linked = person(
        admin,
        ws,
        company,
        "Lina",
        linkedin_url="https://www.linkedin.com/in/synthetic-lina",
        linkedin_status="confirmed",
        phone="+49 781 222222",
    )
    letter = person(admin, ws, company, "Leo")
    admin.commit()
    client.post(w(ws, "/channels/refresh"))
    return linked, letter


def open_tasks(client, ws):
    return client.get(w(ws, "/flow-tasks?due=all")).json()["items"]


def later(admin, ws, days):
    admin.expire_all()
    tenant(admin, ws)
    tick(admin, ws, at=now() + timedelta(days=days))
    admin.commit()


def test_recipe_creates_campaign_and_each_contact_walks_one_path(context, admin):
    client, (ws, other, *_), _ = context
    linked, letter = two_contacts(client, admin, ws)
    recipes = client.get(w(ws, "/flow-recipes")).json()["items"]
    assert {r["id"] for r in recipes} == {"office_linkedin", "letter_only", "after_reply"}
    created = client.post(
        w(ws, "/campaigns/from-recipe"),
        json={"recipe": "office_linkedin", "contact_ids": [linked.id, letter.id]},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["campaign"]["status"] == "active" and body["started"]["started"] == 2
    tasks = {t["contact"]["name"].split()[0]: t for t in open_tasks(client, ws)}
    assert tasks["Lina"]["kind"] == "linkedin_task" and tasks["Lina"]["state"] == "open"
    assert tasks["Leo"]["kind"] == "letter" and tasks["Leo"]["state"] == "open"
    assert client.get(w(other, f"/campaigns/{body['campaign']['id']}/flow")).status_code == 404
    assert (
        client.post(w(other, f"/flow-tasks/{tasks['Lina']['id']}/done"), json={}).status_code == 404
    )


def test_done_wait_condition_and_live_edit_apply_from_next_step(context, admin):
    client, (ws, *_), _ = context
    linked, _ = two_contacts(client, admin, ws)
    campaign = client.post(
        w(ws, "/campaigns/from-recipe"),
        json={"recipe": "office_linkedin", "contact_ids": [linked.id]},
    ).json()["campaign"]
    task = open_tasks(client, ws)[0]
    assert (
        client.post(
            w(ws, f"/flow-tasks/{task['id']}/done"), json={"note": "Selbst gesendet"}
        ).status_code
        == 200
    )
    run = admin.scalar(select(FlowRun).where(FlowRun.contact_id == linked.id))
    admin.refresh(run)
    assert run.state == "waiting" and run.next_due_at > now() + timedelta(days=3)
    assert open_tasks(client, ws) == []
    # Edit the running campaign: the next LinkedIn step gets a new title.
    flow = client.get(w(ws, f"/campaigns/{campaign['id']}/flow")).json()
    steps = [
        {k: s[k] for k in ("position", "kind", "route", "wait_days", "title", "template", "config")}
        for s in flow["steps"]
    ]
    for s in steps:
        if s["position"] == 30:
            s["title"] = "Neue Nachricht (geändert)"
    saved = client.put(w(ws, f"/campaigns/{campaign['id']}/flow"), json={"steps": steps})
    assert saved.status_code == 200, saved.text
    later(admin, ws, 5)
    nxt = open_tasks(client, ws)
    assert len(nxt) == 1 and nxt[0]["title"] == "Neue Nachricht (geändert)"


def test_condition_stops_on_reaction(context, admin):
    client, (ws, *_), _ = context
    linked, _ = two_contacts(client, admin, ws)
    client.post(
        w(ws, "/campaigns/from-recipe"),
        json={"recipe": "office_linkedin", "contact_ids": [linked.id]},
    )
    client.post(w(ws, f"/flow-tasks/{open_tasks(client, ws)[0]['id']}/done"), json={})
    client.put(w(ws, f"/contacts/{linked.id}/outreach-stage"), json={"stage": "replied"})
    later(admin, ws, 5)
    run = admin.scalar(select(FlowRun).where(FlowRun.contact_id == linked.id))
    admin.refresh(run)
    assert run.state == "stopped"


def test_blocked_call_step_shows_reason_and_can_only_be_skipped(context, admin):
    client, (ws, *_), _ = context
    linked, _ = two_contacts(client, admin, ws)
    client.post(
        w(ws, "/campaigns/from-recipe"), json={"recipe": "after_reply", "contact_ids": [linked.id]}
    )
    task = open_tasks(client, ws)[0]
    assert task["kind"] == "call_task" and task["state"] == "blocked"
    assert "konkretem Interesse" in task["blocked_reason"]
    assert client.post(w(ws, f"/flow-tasks/{task['id']}/done"), json={}).status_code == 409
    assert (
        client.post(
            w(ws, f"/flow-tasks/{task['id']}/skip"), json={"note": "Kein Anlass"}
        ).status_code
        == 200
    )


def test_objection_and_missing_route_stop_runs(context, admin):
    client, (ws, *_), _ = context
    linked, letter = two_contacts(client, admin, ws)
    nobody = person(admin, ws, None, "Niemand")
    admin.commit()
    client.post(w(ws, "/channels/refresh"))
    client.post(
        w(ws, "/campaigns/from-recipe"),
        json={"recipe": "letter_only", "contact_ids": [linked.id, letter.id, nobody.id]},
    )
    stopped = admin.scalar(select(FlowRun).where(FlowRun.contact_id == nobody.id))
    assert stopped.state == "stopped" and stopped.stop_reason.startswith("Kein Weg")
    client.post(w(ws, f"/contacts/{letter.id}/objection"), json={"reason": "Keine Werbung"})
    run = admin.scalar(select(FlowRun).where(FlowRun.contact_id == letter.id))
    admin.refresh(run)
    assert run.state == "stopped" and run.stop_reason.startswith("Widerspruch")
    cancelled = admin.scalars(select(FlowTask).where(FlowTask.contact_id == letter.id)).all()
    assert cancelled and all(t.state == "cancelled" for t in cancelled)


def test_flow_validation(context, admin):
    client, (ws, *_), _ = context
    campaign = client.post(
        w(ws, "/campaigns"), json={"name": "Leer", "goal": "", "contact_ids": []}
    ).json()
    assert client.post(w(ws, f"/campaigns/{campaign['id']}/flow/start"), json={}).status_code == 409
    bad_jump = {
        "steps": [
            {"position": 0, "kind": "condition", "config": {"if_reaction": 7, "if_none": "next"}}
        ]
    }
    assert client.put(w(ws, f"/campaigns/{campaign['id']}/flow"), json=bad_jump).status_code == 422
    assert (
        client.put(
            w(ws, f"/campaigns/{campaign['id']}/flow"),
            json={"steps": [{"position": 0, "kind": "wait"}]},
        ).status_code
        == 422
    )
    ok = client.put(
        w(ws, f"/campaigns/{campaign['id']}/flow"),
        json={
            "steps": [
                {"position": 0, "kind": "letter", "title": "Brief"},
                {"position": 1, "kind": "wait", "wait_days": 3},
            ]
        },
    )
    assert ok.status_code == 200 and len(ok.json()["steps"]) == 2


def test_recipe_with_audience_picks_routed_contacts_once(context, admin):
    client, (ws, *_), _ = context
    linked, letter = two_contacts(client, admin, ws)
    first = client.post(
        w(ws, "/campaigns/from-recipe"), json={"recipe": "letter_only", "audience": "letter"}
    ).json()
    assert first["started"]["started"] == 1
    second = client.post(
        w(ws, "/campaigns/from-recipe"), json={"recipe": "office_linkedin", "audience": "routed"}
    ).json()
    # The letter contact is already in an active run, so only the LinkedIn contact starts.
    assert second["started"]["started"] == 1
    listing = client.get(w(ws, "/flow-campaigns")).json()["items"]
    assert len(listing) == 2 and all(sum(c["runs"].values()) == 1 for c in listing)


def test_daily_queue_skips_contacts_in_a_running_campaign(context, admin):
    from app.today import QueueItem, build_queue, sender_for

    client, (ws, *_), user_id = context
    linked, _ = two_contacts(client, admin, ws)
    tenant(admin, ws)
    build_queue(admin, ws, user_id, sender_for(admin, ws))
    admin.commit()
    proposed = admin.scalars(
        select(QueueItem).where(QueueItem.workspace_id == ws, QueueItem.contact_id == linked.id)
    ).all()
    assert proposed and all(i.state == "pending" for i in proposed)
    client.post(
        w(ws, "/campaigns/from-recipe"),
        json={"recipe": "office_linkedin", "contact_ids": [linked.id]},
    )
    admin.expire_all()
    # Joining the campaign withdrew the proposal; a new build does not propose it again.
    assert {
        i.state
        for i in admin.scalars(
            select(QueueItem).where(QueueItem.workspace_id == ws, QueueItem.contact_id == linked.id)
        )
    } == {"skipped"}
    tenant(admin, ws)
    build_queue(admin, ws, user_id, sender_for(admin, ws))
    admin.flush()
    assert not admin.scalars(
        select(QueueItem).where(
            QueueItem.workspace_id == ws,
            QueueItem.contact_id == linked.id,
            QueueItem.state != "skipped",
        )
    ).all()
    admin.rollback()
