"""LinkedIn channel proofs: local simulator with SYNTHETIC accounts only, manual handoff with
self-reported outcomes, and a refused official channel. No request reaches LinkedIn."""

import pytest
from sqlalchemy import select

from app.jobs import execute_one
from app.journeys import ManualActivity
from app.linkedin_channel import LinkedInAction
from app.models import Contact, Deal, Draft
from app.platform_models import Task


def url(ws, path):
    return f"/v1/workspaces/{ws}/{path}"


@pytest.fixture(autouse=True)
def immediate_simulation(monkeypatch):
    monkeypatch.setenv("LINKEDIN_SIM_DELAY_SECONDS", "0")


def seed(client, ws):
    result = client.post(url(ws, "linkedin/simulator/seed"))
    assert result.status_code == 200, result.text
    return {
        a["handle"]: a for a in client.get(url(ws, "linkedin/simulator/accounts")).json()["items"]
    }


def campaign(client, ws, contact_ids):
    item = client.post(
        url(ws, "campaigns"), json={"name": "LinkedIn Sim", "goal": "Austausch", "contact_ids": []}
    ).json()
    client.post(url(ws, "leads/bulk"), json={"contact_ids": contact_ids, "campaign_id": item["id"]})
    client.put(
        url(ws, f"campaigns/{item['id']}/sequence"),
        json={
            "channel": "linkedin_manual",
            "steps": [
                {"position": 0, "template": "Hallo {first_name}, danke für die Vernetzung."},
                {
                    "position": 1,
                    "delay_days": 3,
                    "template": "Hallo {first_name}, kurze Nachfrage.",
                },
            ],
        },
    )
    client.post(url(ws, f"campaigns/{item['id']}/generate-drafts"), json={})
    return item


def approved_draft(client, admin, ws, contact_id, position=0):
    from app.journeys import CampaignDraft

    link = admin.scalar(
        select(CampaignDraft).where(
            CampaignDraft.contact_id == contact_id, CampaignDraft.step_position == position
        )
    )
    assert client.post(url(ws, f"outreach/drafts/{link.draft_id}/approve")).status_code == 200
    return link.draft_id


def test_capabilities_refuse_official_channel(context):
    client, (ws, *_), _ = context
    caps = client.get(url(ws, "linkedin/capabilities")).json()
    assert caps["channels"]["official"]["available"] is False
    assert "keine allgemein verfügbare API" in caps["channels"]["official"]["reason"]
    assert caps["channels"]["simulator"]["available"] is True
    accounts = seed(client, ws)
    result = client.post(
        url(ws, "linkedin/actions"),
        json={
            "contact_id": accounts["sim-anna-keller"]["contact_id"],
            "channel": "official",
            "action": "connection_request",
        },
    )
    assert result.status_code == 403


def test_simulator_full_sequence_with_crm_updates(context, admin):
    client, (ws, other, *_), _ = context
    accounts = seed(client, ws)
    assert len(accounts) == 5 and all(
        a["profile_url"].startswith("sim://") for a in accounts.values()
    )
    assert client.post(url(ws, "linkedin/simulator/seed")).json()["created"] == []
    anna = accounts["sim-anna-keller"]["contact_id"]
    item = campaign(client, ws, [anna])
    base = {"contact_id": anna, "channel": "simulator", "campaign_id": item["id"]}
    draft0 = approved_draft(client, admin, ws, anna, 0)
    early = client.post(
        url(ws, "linkedin/actions"), json=base | {"action": "message", "draft_id": draft0}
    )
    assert early.status_code == 409  # not connected yet
    request = client.post(url(ws, "linkedin/actions"), json=base | {"action": "connection_request"})
    assert request.status_code == 201, request.text
    assert request.json()["state"] == "pending" and request.json()["simulated"] is True
    again = client.post(url(ws, "linkedin/actions"), json=base | {"action": "connection_request"})
    assert again.status_code == 409
    assert execute_one(ws)
    assert admin.get(LinkedInAction, request.json()["id"]).state == "accepted"
    assert admin.get(Contact, anna).status == "contacted"
    # Unapproved draft cannot be sent.
    draft1 = admin.get(Draft, draft0)
    sent = client.post(
        url(ws, "linkedin/actions"), json=base | {"action": "message", "draft_id": draft0}
    )
    assert sent.status_code == 201, sent.text
    assert sent.json()["state"] == "delivered" and draft1.id == draft0
    reuse = client.post(
        url(ws, "linkedin/actions"), json=base | {"action": "message", "draft_id": draft0}
    )
    assert reuse.status_code == 409
    progress = client.get(url(ws, f"campaigns/{item['id']}/linkedin")).json()
    row = progress["contacts"][0]
    assert row["connection"] == "accepted" and row["completed_steps"] == [0]
    assert row["next_step"] == 1 and row["next_due_at"] is not None
    assert row["next_draft"]["approved"] is False
    assert execute_one(ws)
    replied = admin.get(LinkedInAction, sent.json()["id"])
    admin.refresh(replied)
    assert replied.state == "replied" and "Simulierte Antwort" in replied.history[-1]["note"]
    assert admin.scalar(select(Task).where(Task.contact_id == anna)).title.endswith("(simuliert)")
    assert admin.scalar(select(Deal).where(Deal.contact_id == anna)).stage == "conversation"
    workspace = client.get(url(ws, f"campaigns/{item['id']}/workspace")).json()
    assert workspace["counts"]["replied"] == 1
    assert client.get(url(ws, f"campaigns/{item['id']}/linkedin")).json()["contacts"][0]["stopped"]
    # Tenant isolation.
    assert client.get(url(other, f"campaigns/{item['id']}/linkedin")).status_code == 404
    assert (
        client.post(
            url(other, "linkedin/actions"),
            json=base | {"action": "connection_request", "campaign_id": None},
        ).status_code
        == 404
    )
    assert client.get(url(other, "linkedin/actions")).json()["total"] == 0


def test_simulated_decline_blocks_repeat_requests(context):
    client, (ws, *_), _ = context
    mira = seed(client, ws)["sim-mira-sommer"]["contact_id"]
    body = {"contact_id": mira, "channel": "simulator", "action": "connection_request"}
    assert client.post(url(ws, "linkedin/actions"), json=body).status_code == 201
    assert execute_one(ws)
    actions = client.get(url(ws, f"linkedin/actions?contact_id={mira}")).json()["items"]
    assert actions[0]["state"] == "declined"
    assert client.post(url(ws, "linkedin/actions"), json=body).status_code == 409


def test_channels_cannot_be_mixed_and_suppression_blocks(context):
    client, (ws, *_), _ = context
    sim = seed(client, ws)["sim-jonas-brandt"]["contact_id"]
    real = client.post(
        url(ws, "contacts"),
        json={
            "first_name": "Real",
            "last_name": "Fixture",
            "linkedin_url": "https://www.linkedin.com/in/fixture-test",
        },
    ).json()["id"]
    simulate_real = {"contact_id": real, "channel": "simulator", "action": "connection_request"}
    assert client.post(url(ws, "linkedin/actions"), json=simulate_real).status_code == 422
    manual_sim = {"contact_id": sim, "channel": "manual", "action": "connection_request"}
    assert client.post(url(ws, "linkedin/actions"), json=manual_sim).status_code == 422
    client.post(url(ws, "suppressions"), json={"contact_id": real, "reason": "Widerspruch"})
    manual_real = {"contact_id": real, "channel": "manual", "action": "connection_request"}
    assert client.post(url(ws, "linkedin/actions"), json=manual_real).status_code == 409


def test_manual_handoff_outcomes_and_pacing_limit(context, admin, monkeypatch):
    client, (ws, *_), _ = context
    monkeypatch.setenv("LINKEDIN_DAILY_CONNECTION_LIMIT", "1")
    ids = [
        client.post(
            url(ws, "contacts"),
            json={
                "first_name": f"Manual{i}",
                "last_name": "Fixture",
                "linkedin_url": f"https://www.linkedin.com/in/fixture-{i}",
            },
        ).json()["id"]
        for i in range(2)
    ]
    item = campaign(client, ws, ids)
    handoff = client.post(
        url(ws, "linkedin/actions"),
        json={
            "contact_id": ids[0],
            "channel": "manual",
            "action": "connection_request",
            "campaign_id": item["id"],
        },
    )
    assert handoff.status_code == 201, handoff.text
    body = handoff.json()
    assert body["state"] == "handed_off" and body["simulated"] is False
    assert body["handoff"]["profile_url"] == "https://www.linkedin.com/in/fixture-0"
    limited = client.post(
        url(ws, "linkedin/actions"),
        json={"contact_id": ids[1], "channel": "manual", "action": "connection_request"},
    )
    assert limited.status_code == 429
    outcome = url(ws, f"linkedin/actions/{body['id']}/outcome")
    assert client.post(outcome, json={"outcome": "replied"}).status_code == 409
    assert client.post(outcome, json={"outcome": "sent"}).status_code == 200
    assert (
        client.post(outcome, json={"outcome": "accepted", "note": "selbst geprüft"}).status_code
        == 200
    )
    assert client.post(outcome, json={"outcome": "declined"}).status_code == 409
    kinds = set(
        admin.scalars(select(ManualActivity.kind).where(ManualActivity.contact_id == ids[0]))
    )
    assert kinds == {"connection_requested", "connected"}
    draft = approved_draft(client, admin, ws, ids[0], 0)
    message = client.post(
        url(ws, "linkedin/actions"),
        json={
            "contact_id": ids[0],
            "channel": "manual",
            "action": "message",
            "draft_id": draft,
            "campaign_id": item["id"],
        },
    )
    assert message.status_code == 201, message.text
    assert message.json()["handoff"]["text"].startswith("Hallo Manual0")
    assert admin.get(Draft, draft).state == "handed_off"
    reply = url(ws, f"linkedin/actions/{message.json()['id']}/outcome")
    assert client.post(reply, json={"outcome": "sent"}).status_code == 200
    assert client.post(reply, json={"outcome": "replied"}).status_code == 200
    deal = admin.scalar(select(Deal).where(Deal.contact_id == ids[0]))
    assert deal is not None and "simuliert" not in deal.title
    # Simulator-only endpoints refuse outcome self-reporting.
    sim = seed(client, ws)["sim-eva-roth"]["contact_id"]
    sim_action = client.post(
        url(ws, "linkedin/actions"),
        json={"contact_id": sim, "channel": "simulator", "action": "connection_request"},
    )
    assert sim_action.status_code == 429  # pacing limit applies to every channel


def test_simulator_can_be_disabled(context, monkeypatch):
    client, (ws, *_), _ = context
    monkeypatch.setenv("LINKEDIN_SIMULATOR_ENABLED", "false")
    assert client.post(url(ws, "linkedin/simulator/seed")).status_code == 403
    caps = client.get(url(ws, "linkedin/capabilities")).json()
    assert caps["channels"]["simulator"]["available"] is False
