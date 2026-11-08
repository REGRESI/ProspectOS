"""M9 a-c: external outreach tools at the user's own risk. All HTTP is mocked; no request
leaves the test process. Synthetic companies, people and keys only."""

import json
import time

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app import connectors
from app.connectors import ACKNOWLEDGMENT, ConnectorEvent, Handoff, OutreachConnector
from app.flows import FlowTask
from app.jobs import tenant
from app.models import Audit, Contact, Membership
from app.platform_models import Suppression
from app.providers.outreach_tools import sign
from app.reactions import Reaction, record_reaction
from tests.test_agent import drain
from tests.test_v3_channels import firm, person, w

REAL_CLIENT = httpx.Client
LEMLIST_KEY = "synthetic-lemlist-key-not-real"


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.setenv("EXTERNAL_OUTREACH_TOOLS_ENABLED", "true")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr("app.providers.outreach_tools.time.sleep", lambda _s: None)
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        path = request.url.path
        if request.url.host == "api.lemlist.com":
            if path.endswith("/team"):
                return httpx.Response(200, json={"_id": "tea_synthetic"})
            if "/campaigns/" in path and path.endswith("/leads/"):
                return httpx.Response(200, json={"_id": "lea_synthetic1"})
            if path.startswith("/api/leads/pause/"):
                return httpx.Response(200, json={"ok": True})
        if request.url.host == "api.waalaxy.com":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404)

    def client_factory(*args, **kwargs):
        kwargs.pop("transport", None)
        return REAL_CLIENT(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client_factory)
    return calls


def enable(client, ws):
    result = client.post(
        w(ws, "/connectors/enable"),
        json={"accepted": True, "confirmation_text": ACKNOWLEDGMENT},
    )
    assert result.status_code == 200, result.text


def connect(client, ws, tool="lemlist", secrets=None, config=None):
    result = client.put(
        w(ws, f"/connectors/{tool}"),
        json={"secrets": secrets or {"api_key": LEMLIST_KEY}, "config": config or {}},
    )
    assert result.status_code == 200, result.text
    return result.json()


def verified(client, admin, ws, first="Lina", **extra):
    company = firm(admin, ws, name=f"Synthetische Praxis {first}")
    contact = person(
        admin,
        ws,
        company,
        first,
        linkedin_url=f"https://www.linkedin.com/in/synthetic-{first.lower()}/",
        linkedin_status="confirmed",
        **extra,
    )
    admin.commit()
    assert client.post(w(ws, "/channels/refresh")).status_code == 200
    return contact


def handed_over(client, admin, ws, contact, tool="lemlist", target="cam_synthetic"):
    result = client.post(
        w(ws, f"/contacts/{contact.id}/handoff"), json={"tool": tool, "target": target}
    )
    assert result.status_code == 202, result.text
    drain(admin, ws)
    admin.expire_all()
    return admin.get(Handoff, result.json()["id"])


def test_product_switch_hides_everything(context, admin, monkeypatch):
    client, (ws, *_), _ = context
    monkeypatch.delenv("EXTERNAL_OUTREACH_TOOLS_ENABLED", raising=False)
    assert client.get(w(ws, "/connectors")).json()["available"] is False
    body = {"accepted": True, "confirmation_text": ACKNOWLEDGMENT}
    assert client.post(w(ws, "/connectors/enable"), json=body).status_code == 404
    contact = verified(client, admin, ws)
    handoff = {"tool": "lemlist", "target": "cam_x"}
    assert client.post(w(ws, f"/contacts/{contact.id}/handoff"), json=handoff).status_code == 404
    assert client.post(f"/v1/hooks/{ws}/anything", json={}).status_code == 404


def test_enable_needs_owner_and_exact_text_and_is_audited(context, admin, tools):
    client, (ws, *_), user_id = context
    overview = client.get(w(ws, "/connectors")).json()
    assert overview["available"] and not overview["enabled"]
    assert overview["acknowledgment"] == ACKNOWLEDGMENT
    assert {t["id"] for t in overview["tools"]} == {
        "heyreach",
        "waalaxy",
        "lgm",
        "expandi",
        "lemlist",
        "webhook",
    }
    assert all(t["docs"].startswith("https://") and t["cannot"] for t in overview["tools"])
    # Saving keys before the risk confirmation is refused.
    assert (
        client.put(w(ws, "/connectors/lemlist"), json={"secrets": {"api_key": "x"}}).status_code
        == 409
    )
    for body in (
        {"accepted": False, "confirmation_text": ACKNOWLEDGMENT},
        {"accepted": True, "confirmation_text": "Ja"},
    ):
        assert client.post(w(ws, "/connectors/enable"), json=body).status_code == 422
    membership = admin.get(Membership, (ws, user_id))
    membership.role = "admin"
    admin.commit()
    body = {"accepted": True, "confirmation_text": ACKNOWLEDGMENT}
    assert client.post(w(ws, "/connectors/enable"), json=body).status_code == 403
    membership.role = "owner"
    admin.commit()
    enable(client, ws)
    overview = client.get(w(ws, "/connectors")).json()
    assert overview["enabled"] and overview["acknowledged"]["text"] == ACKNOWLEDGMENT
    assert overview["acknowledged"]["name"] == "Test User"
    entry = admin.scalar(
        select(Audit).where(Audit.workspace_id == ws, Audit.kind == "external_tools_enabled")
    )
    assert "Test User" in entry.description and "auf eigene Gefahr" in entry.description
    assert client.post(w(ws, "/connectors/disable")).json()["enabled"] is False
    assert client.get(w(ws, "/connectors")).json()["enabled"] is False


def test_keys_are_encrypted_masked_and_webhook_secret_shown_once(
    context, admin, tools, monkeypatch
):
    client, (ws, other, *_), _ = context
    enable(client, ws)
    bad = client.put(w(ws, "/connectors/lemlist"), json={"secrets": {"password": "x"}})
    assert bad.status_code == 422
    first = connect(client, ws)
    assert first["webhook_path"].startswith(f"/v1/hooks/{ws}/")
    assert LEMLIST_KEY not in json.dumps(first)
    row = admin.scalar(
        select(OutreachConnector).where(
            OutreachConnector.workspace_id == ws, OutreachConnector.tool == "lemlist"
        )
    )
    assert LEMLIST_KEY not in row.secrets_ciphertext and row.inbound_secret_hash
    assert first["webhook_path"].rsplit("/", 1)[1] not in row.inbound_secret_hash
    second = connect(client, ws, secrets={"api_key": ""})
    assert "webhook_path" not in second and second["configured"]
    # Test call: lemlist /team with Basic auth (empty user, key as password).
    assert client.post(w(ws, "/connectors/lemlist/test")).json()["ok"] is True
    auth = tools[-1].headers["Authorization"]
    assert auth.startswith("Basic ") and tools[-1].url.path == "/api/team"
    # Another workspace sees nothing of this connector.
    assert client.post(w(other, "/connectors/lemlist/test")).status_code == 404
    monkeypatch.delenv("TOKEN_ENCRYPTION_KEY")
    assert client.put(w(ws, "/connectors/lemlist"), json={"secrets": {}}).status_code == 503


def test_handoff_sends_only_needed_fields_and_leaves_heute(context, admin, tools):
    client, (ws, other, *_), _ = context
    enable(client, ws)
    connect(client, ws)
    contact = verified(client, admin, ws, email="lina@praxis.example.test", job_title="Inhaberin")
    handoff = handed_over(client, admin, ws, contact)
    assert handoff.state == "handed_over" and handoff.external_ref == "lea_synthetic1"
    push = next(r for r in tools if r.url.path.endswith("/leads/"))
    sent = json.loads(push.content)
    assert sent["linkedinUrl"] == "https://www.linkedin.com/in/synthetic-lina"
    assert {"firstName", "lastName", "companyName"} <= set(sent)
    # No documented e-mail legal basis -> the address is not sent.
    assert "email" not in sent
    admin.expire_all()
    stored = admin.get(Contact, contact.id)
    assert stored.channel_route == "tool" and stored.route_mode == "manual"
    # Second handoff, letter route, forged IDs and other workspace are refused.
    again = client.post(
        w(ws, f"/contacts/{contact.id}/handoff"), json={"tool": "lemlist", "target": "x"}
    )
    assert again.status_code == 409 and "Schon an lemlist" in again.json()["message"]
    forged = client.post(
        w(other, f"/contacts/{contact.id}/handoff"), json={"tool": "lemlist", "target": "x"}
    )
    assert forged.status_code in (404, 409)
    assert client.get(w(other, "/handoffs")).json()["items"] == []
    route = client.put(w(ws, f"/contacts/{contact.id}/route"), json={"route": "tool"})
    assert route.status_code == 409
    # Today's queue never proposes a manual LinkedIn step for a handed-over contact.
    queue = client.get(w(ws, "/today"))
    assert queue.status_code == 200 and contact.id not in queue.text


def test_blockers_objection_unverified_and_inactive_tool(context, admin, tools):
    client, (ws, *_), _ = context
    enable(client, ws)
    plain = person(admin, ws, firm(admin, ws), "Leo")
    blocked = verified(client, admin, ws, "Mia")
    admin.add(Suppression(workspace_id=ws, contact_id=blocked.id, reason="Widerspruch"))
    admin.commit()
    body = {"tool": "lemlist", "target": "cam_x"}
    inactive = client.post(w(ws, f"/contacts/{blocked.id}/handoff"), json=body)
    assert inactive.status_code == 409 and "nicht verbunden" in inactive.json()["message"]
    connect(client, ws)
    objection = client.post(w(ws, f"/contacts/{blocked.id}/handoff"), json=body)
    assert "Widerspruch" in objection.json()["message"]
    unverified = client.post(w(ws, f"/contacts/{plain.id}/handoff"), json=body)
    assert unverified.status_code == 409 and "LinkedIn" in unverified.json()["message"]
    # An objection after queueing but before dispatch is caught at dispatch.
    late = verified(client, admin, ws, "Ida")
    queued = client.post(w(ws, f"/contacts/{late.id}/handoff"), json=body)
    assert queued.status_code == 202
    admin.add(Suppression(workspace_id=ws, contact_id=late.id, reason="Widerspruch"))
    admin.commit()
    drain(admin, ws)
    admin.expire_all()
    assert admin.get(Handoff, queued.json()["id"]).state == "failed"
    assert not any(r.url.path.endswith("/leads/") for r in tools)


def test_inbound_reply_stops_everything_and_is_deduplicated(context, admin, tools):
    client, (ws, other, *_), _ = context
    enable(client, ws)
    path = connect(client, ws)["webhook_path"]
    contact = verified(client, admin, ws)
    handoff = handed_over(client, admin, ws, contact)
    secret = path.rsplit("/", 1)[1]
    assert client.post(f"/v1/hooks/{ws}/wrong-secret", json={}).status_code == 404
    assert client.post(f"/v1/hooks/{other}/{secret}", json={}).status_code == 404
    accepted = {
        "_id": "evt_1",
        "type": "linkedinInviteAccepted",
        "linkedinUrl": "https://linkedin.com/in/Synthetic-Lina",
        "leadId": "lea_synthetic1",
    }
    assert client.post(path, json=accepted).json()["matched"] == 1
    reply = {
        "_id": "evt_2",
        "type": "linkedinReplied",
        "leadId": "lea_synthetic1",
        "text": "Gern, rufen Sie mich an.",
    }
    assert client.post(path, json=reply).json()["matched"] == 1
    assert client.post(path, json=reply).json()["duplicate"] == 1
    admin.expire_all()
    kinds = admin.scalars(
        select(Reaction.kind).where(Reaction.workspace_id == ws, Reaction.contact_id == contact.id)
    ).all()
    assert sorted(kinds) == ["linkedin_accepted", "linkedin_replied"]
    assert admin.get(Handoff, handoff.id).state == "replied"
    assert admin.get(Contact, contact.id).outreach_stage == "replied"
    task = admin.scalar(
        select(FlowTask).where(FlowTask.contact_id == contact.id, FlowTask.origin == "reaction")
    )
    assert task is not None
    # The tool already stopped the lead on reply, so no pause call is made.
    drain(admin, ws)
    assert not any("/leads/pause/" in r.url.path for r in tools)


def test_reaction_elsewhere_pauses_in_tool_or_creates_stop_task(context, admin, tools):
    client, (ws, *_), _ = context
    enable(client, ws)
    connect(client, ws)
    connect(client, ws, "waalaxy", {"api_key": "synthetic"}, {"prospect_list_id": "pl_1"})
    lina = verified(client, admin, ws, "Lina")
    nora = verified(client, admin, ws, "Nora")
    first = handed_over(client, admin, ws, lina)
    second = handed_over(client, admin, ws, nora, tool="waalaxy", target="camp_w")
    assert second.state == "handed_over"
    tenant(admin, ws)
    for contact in (lina, nora):
        record_reaction(admin, ws, admin.get(Contact, contact.id), "email_reply", "Antwort")
    admin.commit()
    drain(admin, ws)
    admin.expire_all()
    assert admin.get(Handoff, first.id).state == "paused"
    pause = next(r for r in tools if "/leads/pause/" in r.url.path)
    assert pause.url.path.endswith("/lea_synthetic1")
    assert pause.url.params["campaignId"] == "cam_synthetic"
    assert admin.get(Handoff, second.id).state == "stopped"
    stop = admin.scalar(
        select(FlowTask).where(FlowTask.contact_id == nora.id, FlowTask.kind == "tool_stop_task")
    )
    assert stop.title == "In Waalaxy stoppen" and stop.state == "open"


def test_generic_webhook_requires_fresh_signature_and_counts_pace(context, admin, tools):
    client, (ws, *_), user_id = context
    enable(client, ws)
    path = connect(
        client,
        ws,
        "webhook",
        {"signing_secret": "synthetic-signing-secret"},
        {"outgoing_url": "https://hooks.example.test/in"},
    )["webhook_path"]
    contact = verified(client, admin, ws, owner_id=user_id)
    body = json.dumps(
        {"event": "invite_sent", "linkedin_url": contact.linkedin_url, "id": "g1"}
    ).encode()
    stamp = str(int(time.time()))
    good = sign("synthetic-signing-secret", body, stamp)
    headers = {"Content-Type": "application/json"}
    assert client.post(path, content=body, headers=headers).status_code == 401
    wrong = headers | {"X-ProspectOS-Timestamp": stamp, "X-ProspectOS-Signature": "sha256=00"}
    assert client.post(path, content=body, headers=wrong).status_code == 401
    old_stamp = str(int(time.time()) - 3600)
    old = headers | {
        "X-ProspectOS-Timestamp": old_stamp,
        "X-ProspectOS-Signature": sign("synthetic-signing-secret", body, old_stamp),
    }
    assert client.post(path, content=body, headers=old).status_code == 401
    ok = headers | {"X-ProspectOS-Timestamp": stamp, "X-ProspectOS-Signature": good}
    result = client.post(path, content=body, headers=ok)
    assert result.status_code == 200 and result.json()["matched"] == 1
    assert admin.scalar(select(ConnectorEvent).where(ConnectorEvent.workspace_id == ws))
    me = next(m for m in client.get(w(ws, "/team/pace")).json()["members"] if m["is_me"])
    assert me["tool_invites_24h"] == 1 and me["sent_24h"] == 0


def test_generic_webhook_refuses_private_targets(context, admin, tools):
    from app.providers.ai import ProviderError
    from app.providers.outreach_tools import ADAPTERS, Lead

    lead = Lead("c1", "A", "B", "Firma", "", "https://www.linkedin.com/in/a")
    for url in ("http://hooks.example.test/x", "https://127.0.0.1/x", "https://localhost/x"):
        with pytest.raises(ProviderError):
            ADAPTERS["webhook"].push_contacts(
                {"outgoing_url": url, "signing_secret": "s"}, "t", [lead]
            )


def test_campaign_step_hands_over_and_skips_manual_linkedin(context, admin, tools):
    client, (ws, *_), _ = context
    enable(client, ws)
    connect(client, ws)
    contact = verified(client, admin, ws)
    campaign = client.post(
        w(ws, "/campaigns"), json={"name": "Tool", "goal": "", "contact_ids": [contact.id]}
    ).json()
    steps = [
        {
            "position": 0,
            "kind": "tool_handoff",
            "config": {"tool": "lemlist", "target": "cam_synthetic"},
        },
        {"position": 1, "kind": "linkedin_task", "title": "Einladung"},
    ]
    saved = client.put(w(ws, f"/campaigns/{campaign['id']}/flow"), json={"steps": steps})
    assert saved.status_code == 200, saved.text
    bad = [{"position": 0, "kind": "tool_handoff", "config": {"tool": "nope", "target": "x"}}]
    assert (
        client.put(w(ws, f"/campaigns/{campaign['id']}/flow"), json={"steps": bad}).status_code
        == 422
    )
    started = client.post(w(ws, f"/campaigns/{campaign['id']}/flow/start"), json={})
    assert started.status_code == 200, started.text
    drain(admin, ws)
    admin.expire_all()
    tasks = admin.scalars(select(FlowTask).where(FlowTask.contact_id == contact.id)).all()
    assert [t.kind for t in tasks] == ["tool_handoff"] and tasks[0].state == "done"
    assert connectors.active_handoff(admin, ws, contact.id).state == "handed_over"
