"""V3 M5: lead distribution, per-person Heute and pace. Two synthetic users."""

from datetime import timedelta
from uuid import uuid4

from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import now
from app.flows import FlowTask
from app.linkedin_channel import LinkedInAction
from app.main import app
from app.models import AuthSession, Contact, Membership, User
from app.today import QueueItem
from tests.test_v3_channels import firm, person, w


def second_member(admin, ws, role="editor"):
    email = f"{uuid4()}@example.test"
    user = User(
        email=email, name="Zweite Person", password_hash=PasswordHasher().hash("TestPassword!2026")
    )
    admin.add(user)
    admin.flush()
    admin.add(Membership(workspace_id=ws, user_id=user.id, role=role))
    admin.commit()
    return user, email


def login(email):
    client = TestClient(app)
    client.__enter__()
    result = client.post("/v1/auth/demo", json={"email": email, "password": "TestPassword!2026"})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return client


def cleanup(admin, user):
    admin.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    admin.commit()


def test_distribution_round_robin_and_territory(context, admin):
    client, (ws, _member_of, foreign), owner_id = context
    second, _ = second_member(admin, ws)
    lahr = firm(admin, ws, "Fiktive Firma Lahr")
    from app.journeys import CompanyFact

    for fact in admin.scalars(select(CompanyFact).where(CompanyFact.company_id == lahr.id)):
        if fact.field.startswith("Adresse"):
            fact.value = "Markt 1, 77933 Lahr"
    offenburg = firm(admin, ws, "Fiktive Firma Offenburg")
    a = person(admin, ws, lahr, "Lahr")
    b = person(admin, ws, offenburg, "Offenburg")
    c = person(admin, ws, None, "Ohne", location="Freiburg")
    admin.commit()
    client.post(w(ws, "/channels/refresh"))
    assert (
        client.post(w(foreign, "/team/distribute"), json={"mode": "round_robin"}).status_code == 404
    )
    client.put(w(ws, f"/team/members/{second.id}/settings"), json={"territory": ["779"]})
    client.put(w(ws, f"/team/members/{owner_id}/settings"), json={"territory": ["Offenburg"]})
    result = client.post(w(ws, "/team/distribute"), json={"mode": "territory"}).json()
    assert result["unmatched"] == 1 and result["assigned"] == {owner_id: 1, second.id: 1}
    admin.expire_all()
    assert admin.get(Contact, a.id).owner_id == second.id
    assert admin.get(Contact, b.id).owner_id == owner_id
    assert admin.get(Contact, c.id).owner_id is None
    rr = client.post(w(ws, "/team/distribute"), json={"mode": "round_robin"}).json()
    assert rr["total"] == 1 and sum(rr["assigned"].values()) == 1
    # Only owner/admin distribute.
    member = admin.get(Membership, (ws, owner_id))
    member.role = "editor"
    admin.commit()
    assert client.post(w(ws, "/team/distribute"), json={"mode": "round_robin"}).status_code == 403


def test_each_person_sees_own_heute_and_no_contact_is_shared(context, admin):
    client, (ws, *_), owner_id = context
    second, email = second_member(admin, ws)
    company = firm(admin, ws)
    mine = person(
        admin,
        ws,
        company,
        "Meins",
        owner_id=owner_id,
        linkedin_url="https://www.linkedin.com/in/synthetic-meins",
        linkedin_status="confirmed",
    )
    theirs = person(
        admin,
        ws,
        company,
        "Fremd",
        owner_id=second.id,
        linkedin_url="https://www.linkedin.com/in/synthetic-fremd",
        linkedin_status="confirmed",
    )
    free = person(admin, ws, company, "Frei")
    day = __import__("app.today", fromlist=["today_key"]).today_key()
    for c in (mine, theirs, free):
        admin.add(
            QueueItem(
                workspace_id=ws,
                day=day,
                contact_id=c.id,
                kind="connect",
                state="approved",
                note="Hallo",
            )
        )
    admin.commit()
    names = {
        i["contact"]["name"].split()[0]
        for i in client.get(w(ws, "/today?mine=true")).json()["items"]
    }
    assert names == {"Meins", "Frei"}
    assert len(client.get(w(ws, "/today")).json()["items"]) == 3
    other_client = login(email)
    try:
        theirs_view = {
            i["contact"]["name"].split()[0]
            for i in other_client.get(w(ws, "/today?mine=true")).json()["items"]
        }
        assert theirs_view == {"Fremd", "Frei"}
        item = admin.scalar(select(QueueItem).where(QueueItem.contact_id == mine.id))
        blocked = other_client.post(w(ws, f"/today/items/{item.id}/sent"), json={})
        assert blocked.status_code == 409
    finally:
        other_client.__exit__(None, None, None)
        cleanup(admin, second)


def test_personal_limit_acceptance_rate_and_stale_invitations(context, admin):
    client, (ws, *_), owner_id = context
    client.put(
        w(ws, f"/team/members/{owner_id}/settings"),
        json={"daily_invite_limit": 1, "weekly_invite_limit": 5},
    )
    assert (
        client.put(
            w(ws, f"/team/members/{owner_id}/settings"),
            json={"daily_invite_limit": 9, "weekly_invite_limit": 5},
        ).status_code
        == 422
    )
    company = firm(admin, ws)
    day = __import__("app.today", fromlist=["today_key"]).today_key()
    items = []
    for i in range(2):
        c = person(
            admin,
            ws,
            company,
            f"Limit{i}",
            linkedin_url=f"https://www.linkedin.com/in/synthetic-limit{i}",
            linkedin_status="confirmed",
        )
        q = QueueItem(
            workspace_id=ws,
            day=day,
            contact_id=c.id,
            kind="connect",
            state="approved",
            note="Hallo",
        )
        admin.add(q)
        items.append(q)
    old = person(admin, ws, company, "Alt", outreach_stage="sent")
    accepted = person(admin, ws, company, "Angenommen", outreach_stage="connected")
    for c, days in ((old, 30), (accepted, 30)):
        admin.add(
            LinkedInAction(
                workspace_id=ws,
                contact_id=c.id,
                actor_id=owner_id,
                channel="manual",
                action="connection_request",
                state="handed_off",
                content="",
                simulated=False,
                history=[],
                created_at=now() - timedelta(days=days),
            )
        )
    admin.commit()
    assert client.post(w(ws, f"/today/items/{items[0].id}/sent"), json={}).status_code == 200
    limited = client.post(w(ws, f"/today/items/{items[1].id}/sent"), json={})
    assert limited.status_code == 429
    pace = next(m for m in client.get(w(ws, "/team/pace")).json()["members"] if m["is_me"])
    assert pace["sent_24h"] == 1 and pace["daily_limit"] == 1 and pace["remaining_today"] == 0
    assert pace["acceptance_rate"] == round(1 / 3, 2)
    assert [s["name"] for s in pace["stale_open"]] == ["Alt Synthetisch"]


def test_member_removal_keeps_history(context, admin):
    client, (ws, *_), owner_id = context
    second, _ = second_member(admin, ws)
    contact = person(admin, ws, firm(admin, ws), "Aufgabe", owner_id=second.id)
    admin.add(
        FlowTask(
            workspace_id=ws,
            contact_id=contact.id,
            kind="call_task",
            title="Anruf",
            assignee_id=second.id,
            done_by=second.id,
            state="done",
            origin="reaction",
        )
    )
    admin.commit()
    removed = client.delete(w(ws, f"/team/members/{second.id}"))
    assert removed.status_code == 200, removed.text
    admin.expire_all()
    task = admin.scalar(select(FlowTask).where(FlowTask.contact_id == contact.id))
    assert task.assignee_id is None and task.done_by is None
