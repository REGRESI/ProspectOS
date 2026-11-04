"""M6 e-mail outreach. SMTP/IMAP/DNS are faked; addresses are synthetic (.example)."""

from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.db import now
from app.email_outreach import EmailMessage, Mailbox, capacity_today, dns_report
from app.jobs import execute_one
from app.journeys import CampaignStep
from app.models import Company, Contact
from app.platform_models import Campaign, Enrollment, Job, Suppression
from app.providers import mailbox as provider

BOX = {
    "email": "nico@cleanstar-mail.example",
    "display_name": "Nico Test",
    "password": "synthetic-app-password",
    "smtp_host": "smtp.cleanstar-mail.example",
    "smtp_port": 465,
    "smtp_security": "ssl",
    "imap_host": "imap.cleanstar-mail.example",
    "signature": "Viele Grüße\nNico Test",
    "sender_footer": "Synthetische Reinigung GmbH · Testweg 1 · 77652 Offenburg · HRB 000",
}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://app.example")
    sent = []
    monkeypatch.setattr(provider, "test_mailbox", lambda cfg: {"detail": "fake ok"})
    monkeypatch.setattr(
        provider, "send_message", lambda cfg, msg: sent.append(msg) or msg["Message-ID"]
    )
    return sent


def setup_campaign(admin, ws, n=2):
    company = Company(
        workspace_id=ws,
        name="Synthetische Kanzlei GmbH",
        identity="test:k",
        location="Offenburg",
        provenance={},
    )
    admin.add(company)
    admin.flush()
    campaign = Campaign(workspace_id=ws, name="Büroreinigung Herbst")
    admin.add(campaign)
    admin.flush()
    contacts = []
    for i in range(n):
        c = Contact(
            workspace_id=ws,
            company_id=company.id,
            first_name="Erika",
            last_name=f"Fiktiv{i}",
            email=f"erika{i}@kanzlei.example",
            source="impressum https://kanzlei.example/impressum",
        )
        admin.add(c)
        admin.flush()
        admin.add(Enrollment(workspace_id=ws, campaign_id=campaign.id, contact_id=c.id))
        contacts.append(c)
    for pos, tpl in [
        (0, "Guten Tag {name},\n\nwir reinigen Büros wie bei {company} in {city}."),
        (1, "Kurz nachgehakt, {first_name}."),
    ]:
        admin.add(
            CampaignStep(
                workspace_id=ws,
                campaign_id=campaign.id,
                position=pos,
                delay_days=pos * 4,
                channel="email",
                template=tpl,
            )
        )
    admin.commit()
    return campaign, contacts


def run_due(admin, ws):
    # Make scheduled jobs due now and run them.
    for job in admin.scalars(select(Job).where(Job.workspace_id == ws, Job.status == "queued")):
        job.available_at = now() - timedelta(seconds=1)
    admin.commit()
    while execute_one(ws):
        pass


def test_full_email_flow(context, admin, env, monkeypatch):
    client, (ws, other, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    r = client.post(f"{w}/mailboxes", json=BOX)
    assert r.status_code == 201, r.text
    assert "synthetic-app-password" not in r.text
    box_id = r.json()["item"]["id"]
    assert (
        admin.scalar(select(Mailbox).where(Mailbox.id == box_id)).ciphertext.find("synthetic") == -1
    )
    # Forged/foreign workspace access.
    assert client.get(f"/v1/workspaces/{other}/mailboxes/{box_id}/dns").status_code == 404

    campaign, contacts = setup_campaign(admin, ws)
    c = f"{w}/campaigns/{campaign.id}/email"
    assert (
        client.post(
            f"{c}/drafts", json={"step_position": 0, "subject": "Büroreinigung für {company}"}
        ).json()["created"]
        == 2
    )
    view = client.get(c).json()
    draft = view["contacts"][0]["drafts"][0]
    assert draft["subject"] == "Büroreinigung für Synthetische Kanzlei GmbH"
    assert "Offenburg" in draft["content"] and "Nico Test" in draft["content"]
    assert client.post(f"{c}/approve", json={"all_for_step": 0}).json()["approved"] == 2

    # No legal basis -> blocked with reason; "other" is not allowed in DE either.
    blocked = client.post(f"{c}/schedule", json={"step_position": 0}).json()
    assert blocked["scheduled"] == 0 and "Rechtsgrundlage" in blocked["blocked"][0]["reasons"][0]
    client.post(
        f"{w}/legal-bases",
        json={
            "contact_id": contacts[0].id,
            "basis": "other",
            "evidence": "Messegespräch ohne Einwilligung",
        },
    )
    assert not client.get(f"{w}/contacts/{contacts[0].id}/email-eligibility").json()["allowed"]
    for contact in contacts:
        ok = client.post(
            f"{w}/legal-bases",
            json={
                "contact_id": contact.id,
                "basis": "consent",
                "evidence": "Einwilligung per Formular am 01.11.2026",
                "evidence_url": "https://kanzlei.example/nachweis",
            },
        )
        assert ok.json()["eligibility"]["allowed"]
    scheduled = client.post(f"{c}/schedule", json={"step_position": 0}).json()
    assert scheduled["scheduled"] == 2
    assert (
        client.post(f"{c}/schedule", json={"step_position": 0}).json()["scheduled"] == 0
    )  # idempotent
    run_due(admin, ws)
    assert len(env) == 2
    mail = env[0]
    assert mail["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "https://app.example/v1/u/" in mail["List-Unsubscribe"]
    body = mail.get_content()
    assert "Testweg 1" in body and "Keine weiteren Nachrichten erhalten" in body
    msgs = admin.scalars(select(EmailMessage).where(EmailMessage.workspace_id == ws)).all()
    assert {m.state for m in msgs} == {"sent"} and all(m.message_id for m in msgs)

    # One-click unsubscribe for contact 1 -> suppression, eligibility false.
    m1 = next(m for m in msgs if m.contact_id == contacts[1].id)
    token = admin.scalar(
        select(Job).where(
            Job.workspace_id == ws,
            Job.kind == "email_send",
            Job.payload["message_id"].as_string() == m1.id,
        )
    ).payload["unsubscribe_token"]
    assert client.get(f"/v1/u/{token}").status_code == 200
    assert client.post(f"/v1/u/{token}", data={"List-Unsubscribe": "One-Click"}).status_code == 200
    assert admin.scalar(
        select(Suppression).where(
            Suppression.workspace_id == ws, Suppression.contact_id == contacts[1].id
        )
    )
    assert client.post("/v1/u/" + ws + ".forged", data={}).status_code == 404

    # IMAP: contact 0 replies -> replied, step 1 for them is not scheduled; bounce DSN parsed.
    m0 = next(m for m in msgs if m.contact_id == contacts[0].id)
    reply = f"From: erika0@kanzlei.example\r\nSubject: Re: X\r\nIn-Reply-To: {m0.message_id}\r\n\r\nGerne!".encode()
    monkeypatch.setattr(provider, "fetch_new", lambda cfg, last: ([(7, reply)], 7))
    client.post(f"{w}/mailboxes/{box_id}/sync")
    run_due(admin, ws)
    admin.expire_all()
    assert admin.get(EmailMessage, m0.id).state == "replied"
    assert admin.get(Mailbox, box_id).imap_last_uid == 7
    client.post(f"{c}/drafts", json={"step_position": 1, "subject": "Nachgehakt"})
    client.post(f"{c}/approve", json={"all_for_step": 1})
    again = client.post(f"{c}/schedule", json={"step_position": 1}).json()
    assert (
        again["scheduled"] == 0
    )  # contact 0 has no... legal basis ok but sequence stopped at dispatch; contact 1 suppressed
    metrics = client.get(c).json()["metrics"]
    assert metrics["replied"] == 1 and metrics["unsubscribed"] == 1


def test_dispatch_recheck_blocks_after_revocation(context, admin, env):
    client, (ws, *_), _ = context
    w = f"/v1/workspaces/{ws}"
    client.post(f"{w}/mailboxes", json=BOX)
    campaign, contacts = setup_campaign(admin, ws, 1)
    c = f"{w}/campaigns/{campaign.id}/email"
    client.post(f"{c}/drafts", json={"step_position": 0, "subject": "Hallo"})
    client.post(f"{c}/approve", json={"all_for_step": 0})
    client.post(
        f"{w}/legal-bases",
        json={
            "contact_id": contacts[0].id,
            "basis": "consent",
            "evidence": "Einwilligung per Formular am 01.11.2026",
        },
    )
    assert client.post(f"{c}/schedule", json={"step_position": 0}).json()["scheduled"] == 1
    # Contact gets suppressed after scheduling: dispatch must refuse and persist "blocked".
    admin.add(Suppression(workspace_id=ws, contact_id=contacts[0].id, reason="manuell"))
    admin.commit()
    run_due(admin, ws)
    assert env == []
    msg = admin.scalar(select(EmailMessage).where(EmailMessage.workspace_id == ws))
    admin.refresh(msg)
    assert msg.state == "blocked" and "Sperrliste" in msg.error + str(msg.events)


def test_ramp_up_and_dns_report(context, admin, env):
    client, (ws, *_), _ = context
    box_id = client.post(
        f"/v1/workspaces/{ws}/mailboxes",
        json=BOX | {"ramp_start_limit": 5, "ramp_step": 3, "daily_max": 40},
    ).json()["item"]["id"]
    box = admin.get(Mailbox, box_id)
    assert capacity_today(admin, ws, box) == 5
    box.ramp_start = box.ramp_start - timedelta(days=10)
    assert capacity_today(admin, ws, box) == 35
    box.ramp_start = box.ramp_start - timedelta(days=100)
    assert capacity_today(admin, ws, box) == 40

    class FakeAnswer:
        def __init__(self, value):
            self.strings = [value.encode()]
            self.exchange = value

    class FakeResolver:
        lifetime = 5

        def resolve(self, name, kind):
            import dns.resolver

            table = {
                ("cleanstar-mail.example", "MX"): ["mx.provider.example."],
                ("cleanstar-mail.example", "TXT"): ["v=spf1 include:provider.example ~all"],
                ("_dmarc.cleanstar-mail.example", "TXT"): [],
            }
            values = table.get((name, kind))
            if not values:
                raise dns.resolver.NXDOMAIN()
            return [FakeAnswer(v) for v in values]

    report = dns_report("cleanstar-mail.example", resolver=FakeResolver())
    status = {c["name"]: c["ok"] for c in report["checks"]}
    assert status == {"MX": True, "SPF": True, "DKIM": False, "DMARC": False}
    assert (
        not report["ready"]
        and "_dmarc" in next(c for c in report["checks"] if c["name"] == "DMARC")["fix"]
    )


def test_classify_reply_bounce_complaint():
    reply = provider.classify(b"From: a@b.example\r\nIn-Reply-To: <abc@x>\r\n\r\nDanke")
    assert reply["kind"] == "reply" and reply["ids"] == ["<abc@x>"]
    dsn = (
        b"From: MAILER-DAEMON@mx.example\r\nContent-Type: multipart/report; report-type=delivery-status; boundary=B\r\n\r\n"
        b"--B\r\nContent-Type: text/plain\r\n\r\nfailed\r\n--B\r\nContent-Type: message/delivery-status\r\n\r\nAction: failed\r\nStatus: 5.1.1\r\n"
        b"--B\r\nContent-Type: text/rfc822-headers\r\n\r\nMessage-ID: <orig@x>\r\n--B--\r\n"
    )
    bounce = provider.classify(dsn)
    assert bounce["kind"] == "bounce" and bounce["hard"] and "<orig@x>" in bounce["ids"]
