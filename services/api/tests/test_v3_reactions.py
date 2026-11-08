"""V3 M3: reactions stop every planned step and land in one inbox. Synthetic data only."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.flows import FlowRun, FlowTask
from app.main import app
from app.platform_models import Consent
from app.reactions import Reaction
from tests.test_v3_channels import w
from tests.test_v3_flows import open_tasks, two_contacts


def start(client, ws, recipe, ids):
    created = client.post(
        w(ws, "/campaigns/from-recipe"), json={"recipe": recipe, "contact_ids": ids}
    )
    assert created.status_code == 201, created.text
    return created.json()["campaign"]


def test_linkedin_reply_stops_all_steps_and_creates_call_task(context, admin):
    client, (ws, other, *_), _ = context
    linked, _ = two_contacts(client, admin, ws)
    start(client, ws, "office_linkedin", [linked.id])
    # Accepting the invitation is the expected next step: no stop.
    client.put(w(ws, f"/contacts/{linked.id}/outreach-stage"), json={"stage": "connected"})
    run = admin.scalar(select(FlowRun).where(FlowRun.contact_id == linked.id))
    admin.refresh(run)
    assert run.state == "active"
    reply = client.post(
        w(ws, f"/contacts/{linked.id}/reactions"),
        json={"kind": "linkedin_replied", "text": "Klingt interessant, rufen Sie mich an."},
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["stopped"]["flows"] == 1
    admin.refresh(run)
    assert run.state == "stopped" and run.stop_reason.startswith("Reaktion")
    tasks = open_tasks(client, ws)
    assert len(tasks) == 1 and tasks[0]["origin"] == "reaction"
    assert tasks[0]["title"] == "Anrufen und Termin vereinbaren"
    assert tasks[0]["state"] == "open"  # phone allowed now: concrete interest documented
    assert admin.scalar(
        select(Consent).where(Consent.contact_id == linked.id, Consent.channel == "phone")
    )
    inbox = client.get(w(ws, "/inbox")).json()
    kinds = [i["kind"] for i in inbox["items"]]
    assert kinds.count("linkedin_replied") == 1 and kinds.count("linkedin_accepted") == 1
    assert client.get(w(other, "/inbox")).json()["total"] == 0
    rid = next(i["id"] for i in inbox["items"] if i["kind"] == "linkedin_replied")
    assert (
        client.patch(w(other, f"/reactions/{rid}"), json={"status": "meeting"}).status_code == 404
    )
    done = client.patch(w(ws, f"/reactions/{rid}"), json={"status": "meeting"}).json()
    assert done["status"] == "meeting"
    assert client.get(w(ws, "/inbox?status=meeting")).json()["total"] == 1


def test_qr_scan_is_public_redirects_and_stops_the_letter_path(context, admin):
    client, (ws, other, *_), _ = context
    _, letter = two_contacts(client, admin, ws)
    start(client, ws, "letter_only", [letter.id])
    assert (
        client.post(
            w(ws, f"/companies/{letter.company_id}/ref-code"),
            json={"target_url": "http://unsafe.example.test"},
        ).status_code
        == 422
    )
    code = client.post(
        w(ws, f"/companies/{letter.company_id}/ref-code"),
        json={"target_url": "https://www.cleanstar.example.test/reinigungs-check/"},
    ).json()["code"]
    with TestClient(app) as anonymous:
        scan = anonymous.get(f"/v1/r/{code}", follow_redirects=False)
        assert scan.status_code == 302
        assert (
            scan.headers["location"]
            == f"https://www.cleanstar.example.test/reinigungs-check/?ref={code}"
        )
        assert anonymous.get(f"/v1/r/{code}", follow_redirects=False).status_code == 302
        assert anonymous.get("/v1/r/NOTACODE", follow_redirects=False).status_code == 404
        assert anonymous.get("/v1/r/x'--", follow_redirects=False).status_code == 404
    scans = admin.scalars(select(Reaction).where(Reaction.contact_id == letter.id)).all()
    assert len(scans) == 1 and scans[0].kind == "qr_scan"  # second scan within 24 h is not counted
    run = admin.scalar(select(FlowRun).where(FlowRun.contact_id == letter.id))
    admin.refresh(run)
    assert run.state == "stopped"
    letter_task = admin.scalar(
        select(FlowTask).where(FlowTask.contact_id == letter.id, FlowTask.origin == "flow")
    )
    admin.refresh(letter_task)
    assert letter_task.state == "cancelled"


def test_inquiry_code_is_workspace_bound(context, admin):
    from tests.test_v3_channels import firm, person

    client, (ws, other, *_), _ = context
    letter = person(admin, ws, firm(admin, ws, "Eigene Firma ohne Telefon", phone=False), "Ida")
    admin.commit()
    code = client.post(w(ws, f"/companies/{letter.company_id}/ref-code"), json={}).json()["code"]
    assert client.post(w(other, "/reactions/by-code"), json={"code": code}).status_code == 404
    hit = client.post(
        w(ws, "/reactions/by-code"), json={"code": code.lower(), "text": "Bitte Angebot"}
    )
    assert hit.status_code == 201, hit.text
    assert hit.json()["kind"] == "web_inquiry" and hit.json()["contact"]["id"] == letter.id
    # Without a phone number the follow-up is a meeting task, not a call.
    task = admin.scalar(
        select(FlowTask).where(FlowTask.contact_id == letter.id, FlowTask.origin == "reaction")
    )
    assert task.kind == "meeting_task"


def test_reaction_code_lookup_does_not_leak_other_workspaces(context, admin):
    client, (ws, other, *_), _ = context
    _, letter = two_contacts(client, admin, ws)
    code = client.post(w(ws, f"/companies/{letter.company_id}/ref-code"), json={}).json()["code"]
    from sqlalchemy import text

    from app.db import SessionLocal

    with SessionLocal() as db:
        db.execute(text("SELECT set_config('app.workspace_id', :ws, false)"), {"ws": other})
        # The runtime role cannot read another workspace's codes directly ...
        assert (
            db.execute(text("SELECT count(*) FROM ref_codes WHERE code = :c"), {"c": code}).scalar()
            == 0
        )
        # ... only the definer function resolves exactly one code to ids.
        row = db.execute(text("SELECT * FROM resolve_ref_code(:c)"), {"c": code}).first()
        assert row[0] == ws and row[1] == letter.company_id
