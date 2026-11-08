"""V3 M4: letters as PDF with QR code, batch print, labels, scan -> call task.
Synthetic recipients only; no print service is called."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.flows import FlowRun, FlowTask
from app.letters import Letter, render_pdf, split_address
from app.main import app
from tests.test_v3_channels import firm, person, w
from tests.test_v3_flows import open_tasks

TARGET = "https://www.cleanstar.example.test/reinigungs-check/"


def ten_letters(client, admin, ws, n=10):
    people = []
    for i in range(n):
        company = firm(admin, ws, f"Fiktive Praxis {i:02d}")
        people.append(person(admin, ws, company, f"Person{i:02d}", "Synthetisch"))
    admin.commit()
    client.post(w(ws, "/channels/refresh"))
    return people


def configure(client, ws):
    saved = client.put(
        w(ws, "/letters/settings"),
        json={
            "sender_name": "Nico Test",
            "sender_company": "CleanStar (Test)",
            "sender_street": "Musterweg 3",
            "sender_city": "77933 Lahr",
            "sender_phone": "+49 7821 000000",
            "qr_target_url": TARGET,
        },
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


def test_address_split():
    assert split_address("Testweg 1, 77652 Offenburg") == ["Testweg 1", "77652 Offenburg"]
    assert split_address("Hof 2, Anbau, 77933 Lahr") == ["Hof 2, Anbau", "77933 Lahr"]


def test_ten_letters_one_pdf_scan_creates_call_task(context, admin):
    client, (ws, other, *_), _ = context
    people = ten_letters(client, admin, ws)
    campaign = client.post(
        w(ws, "/campaigns/from-recipe"),
        json={"recipe": "letter_only", "contact_ids": [p.id for p in people]},
    ).json()["campaign"]
    assert len([t for t in open_tasks(client, ws) if t["kind"] == "letter"]) == 10
    # Without a QR target the letters cannot be prepared.
    missing = client.post(w(ws, "/letters/prepare"), json={"from_tasks": True})
    assert missing.status_code == 409
    settings = configure(client, ws)
    assert settings["fonts"].startswith("CleanStar")
    prepared = client.post(w(ws, "/letters/prepare"), json={"from_tasks": True}).json()
    assert len(prepared["created"]) == 10 and prepared["skipped"] == []
    letter = prepared["created"][0]
    assert letter["recipient"][0].startswith("Fiktive Praxis")
    assert letter["recipient"][-2:] == ["Testweg 1", "77652 Offenburg"]
    assert letter["qr_url"] == f"{TARGET}?ref={letter['code']}"
    assert "–" not in letter["body"] and letter["style_issues"] == []
    assert "CleanStar (Test)" in letter["body"]
    # Again: no duplicate drafts.
    assert (
        len(client.post(w(ws, "/letters/prepare"), json={"from_tasks": True}).json()["created"])
        == 0
    )
    # Drafts never go to print; a preview PDF carries a draft mark.
    preview = client.get(w(ws, f"/letters/{letter['id']}/pdf"))
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF")
    assert client.post(w(ws, "/letters/print-pdf"), json={"ids": [letter["id"]]}).status_code == 409
    assert client.get(w(other, f"/letters/{letter['id']}/pdf")).status_code == 404
    for item in prepared["created"]:
        assert client.post(w(ws, f"/letters/{item['id']}/approve")).status_code == 200
    batch = client.post(w(ws, "/letters/print-pdf"), json={"all_approved": True})
    assert batch.status_code == 200 and batch.headers["content-type"] == "application/pdf"
    assert batch.content.count(b"/Type /Page\n") + batch.content.count(b"/Type /Page ") >= 10
    labels = client.post(w(ws, "/letters/labels-pdf"), json={"all_approved": True})
    assert labels.status_code == 200 and labels.content.startswith(b"%PDF")
    printed = client.post(w(ws, "/letters/mark-printed"), json={"all_approved": True}).json()
    assert printed == {"printed": 10, "tasks_completed": 10}
    # Letter tasks are done, runs now wait 10 days.
    runs = admin.scalars(select(FlowRun).where(FlowRun.campaign_id == campaign["id"])).all()
    assert {r.state for r in runs} == {"waiting"}
    # A scan of the first letter's code creates a call task for that person.
    with TestClient(app) as anonymous:
        assert anonymous.get(f"/v1/r/{letter['code']}", follow_redirects=False).status_code == 302
    task = admin.scalar(
        select(FlowTask).where(
            FlowTask.contact_id == letter["contact"]["id"], FlowTask.origin == "reaction"
        )
    )
    assert task.kind == "call_task" and task.state == "open"  # Impressum phone + concrete interest
    # The print service stays off.
    assert client.post(w(ws, "/letters/send-print-service")).status_code == 403


def test_objection_blocks_letters(context, admin):
    client, (ws, *_), _ = context
    (one,) = ten_letters(client, admin, ws, 1)
    configure(client, ws)
    letter = client.post(w(ws, "/letters/prepare"), json={"contact_ids": [one.id]}).json()[
        "created"
    ][0]
    client.post(w(ws, f"/letters/{letter['id']}/approve"))
    client.post(w(ws, f"/contacts/{one.id}/objection"), json={"reason": "Keine Post bitte"})
    assert client.post(w(ws, "/letters/print-pdf"), json={"ids": [letter["id"]]}).status_code == 409
    skipped = client.post(w(ws, "/letters/prepare"), json={"contact_ids": [one.id]}).json()
    assert skipped["created"] == []


def test_edit_resets_approval_and_render_is_one_page(context, admin):
    client, (ws, *_), _ = context
    (one,) = ten_letters(client, admin, ws, 1)
    configure(client, ws)
    letter = client.post(w(ws, "/letters/prepare"), json={"contact_ids": [one.id]}).json()[
        "created"
    ][0]
    client.post(w(ws, f"/letters/{letter['id']}/approve"))
    long_body = "Sehr langer Text. " * 400
    edited = client.patch(
        w(ws, f"/letters/{letter['id']}"),
        json={"subject": "Neuer Betreff", "body": long_body[:2990], "revision": letter["revision"]},
    ).json()
    assert edited["state"] == "draft" and edited["revision"] == 2
    stored = admin.get(Letter, letter["id"])
    admin.refresh(stored)
    pdf = render_pdf(admin, ws, [stored])
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") == 1
