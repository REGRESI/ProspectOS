"""V3 M1: contact points, channel switch, per-channel legal basis, objection, merge.
Synthetic companies and people only."""

from datetime import timedelta

from sqlalchemy import select

from app.db import now
from app.email_outreach import EmailMessage
from app.journeys import CompanyFact
from app.models import Company, Contact, Membership
from app.multichannel import ContactMerge, ContactPoint
from app.platform_models import Consent, Suppression
from app.today import QueueItem


def w(ws, path=""):
    return f"/v1/workspaces/{ws}{path}"


def firm(admin, ws, name="Synthetische Kanzlei Muster", address=True, phone=True, email=True):
    company = Company(workspace_id=ws, name=name, identity="test:" + name, provenance={})
    admin.add(company)
    admin.flush()
    facts = []
    if address:
        facts.append(("Adresse (Impressum)", "Testweg 1, 77652 Offenburg"))
    if phone:
        facts.append(("Telefon (Impressum)", "+49 781 000000"))
    if email:
        facts.append(("E-Mail allgemein (Impressum)", "Info@kanzlei-muster.example.test"))
    for field, value in facts:
        admin.add(
            CompanyFact(
                workspace_id=ws,
                company_id=company.id,
                field=field,
                value=value,
                source_url="https://kanzlei-muster.example.test/impressum",
                source_kind="website_impressum",
                confidence="extracted",
            )
        )
    admin.flush()
    return company


def person(admin, ws, company, first="Anna", last="Synthetisch", **extra):
    contact = Contact(
        workspace_id=ws,
        company_id=company.id if company else None,
        first_name=first,
        last_name=last,
        **extra,
    )
    admin.add(contact)
    admin.flush()
    return contact


def test_points_and_route_follow_verified_profile_else_letter(context, admin):
    client, (ws, other, *_), _ = context
    company = firm(admin, ws)
    with_profile = person(
        admin,
        ws,
        company,
        "Lena",
        linkedin_url="https://www.linkedin.com/in/synthetic-lena",
        linkedin_status="verified",
        linkedin_reason="Name und Firma passen",
    )
    unsure = person(
        admin,
        ws,
        company,
        "Max",
        linkedin_url="https://www.linkedin.com/in/synthetic-max",
        linkedin_status="unsure",
    )
    nothing = person(admin, ws, None, "Ohne", email="ohne@example.test")
    admin.commit()
    result = client.post(w(ws, "/channels/refresh")).json()
    assert result["routes"] == {"linkedin": 1, "letter": 1, "none": 1}
    lena = client.get(w(ws, f"/contacts/{with_profile.id}/channels")).json()
    assert lena["route"] == "linkedin" and "Geprüftes LinkedIn-Profil" in lena["route_reason"]
    kinds = {(p["channel"], p["kind"]) for p in lena["points"]}
    assert ("postal", "general") in kinds and ("email", "general") in kinds
    assert all(p["source"] and p["observed_at"] for p in lena["points"])
    postal = next(p for p in lena["points"] if p["channel"] == "postal")
    assert postal["source_url"] == "https://kanzlei-muster.example.test/impressum"
    # E-mail values are normalised; generic mailboxes are marked as general.
    assert any(p["value"] == "info@kanzlei-muster.example.test" for p in lena["points"])
    maxi = client.get(w(ws, f"/contacts/{unsure.id}/channels")).json()
    assert maxi["route"] == "letter" and maxi["route_reason"].startswith("Profil nicht geprüft")
    assert maxi["permissions"]["linkedin"]["allowed"] is False
    assert maxi["permissions"]["letter"]["allowed"] is True
    assert client.get(w(ws, f"/contacts/{nothing.id}/channels")).json()["route"] == "none"
    # Tenant isolation.
    assert client.get(w(other, f"/contacts/{with_profile.id}/channels")).status_code == 404
    assert client.post(w(other, f"/contacts/{with_profile.id}/channels/refresh")).status_code == 404


def test_manual_route_sticks_and_impossible_route_is_refused(context, admin):
    client, (ws, *_), _ = context
    company = firm(admin, ws)
    contact = person(admin, ws, company)
    admin.commit()
    client.post(w(ws, "/channels/refresh"))
    refused = client.put(w(ws, f"/contacts/{contact.id}/route"), json={"route": "linkedin"})
    err = refused.json()
    assert refused.status_code == 409
    assert "Kein geprüftes LinkedIn-Profil" in (err.get("message") or err.get("detail"))
    manual = client.put(
        w(ws, f"/contacts/{contact.id}/route"), json={"route": "none", "reason": "Erst nach Messe"}
    ).json()
    assert manual["route"] == "none" and manual["route_mode"] == "manual"
    # The automatic rule leaves a manual choice alone.
    client.post(w(ws, "/channels/refresh"))
    assert client.get(w(ws, f"/contacts/{contact.id}/channels")).json()["route"] == "none"
    back = client.put(w(ws, f"/contacts/{contact.id}/route"), json={"route": "auto"}).json()
    assert back["route"] == "letter" and back["route_mode"] == "auto"


def test_phone_needs_concrete_interest_and_email_keeps_its_rules(context, admin):
    client, (ws, *_), _ = context
    company = firm(admin, ws)
    contact = person(admin, ws, company, email="anna@kanzlei-muster.example.test")
    admin.commit()
    data = client.post(w(ws, f"/contacts/{contact.id}/channels/refresh")).json()
    assert data["permissions"]["phone"]["allowed"] is False
    assert "konkretem Interesse" in data["permissions"]["phone"]["reason"]
    assert data["permissions"]["email"]["allowed"] is False
    bad = client.post(
        w(ws, f"/contacts/{contact.id}/legal-basis"),
        json={"channel": "phone", "basis": "concrete_interest", "evidence": "Rückruf erbeten"},
    )
    assert bad.status_code == 422  # occasion missing
    assert (
        client.post(
            w(ws, f"/contacts/{contact.id}/legal-basis"),
            json={
                "channel": "phone",
                "basis": "general_interest",
                "evidence": "x",
                "occasion": "x",
            },
        ).status_code
        == 422
    )
    ok = client.post(
        w(ws, f"/contacts/{contact.id}/legal-basis"),
        json={
            "channel": "phone",
            "basis": "concrete_interest",
            "evidence": "Bittet um Rückruf",
            "occasion": "Anfrage vom 3.11.",
        },
    ).json()
    assert ok["permissions"]["phone"]["allowed"] is True
    assert "Anfrage vom 3.11." in ok["permissions"]["phone"]["basis"]
    mail = client.post(
        w(ws, f"/contacts/{contact.id}/legal-basis"),
        json={
            "channel": "email",
            "basis": "explicit_consent",
            "evidence": "Formular mit Häkchen, 2.11.",
        },
    ).json()
    assert mail["permissions"]["email"]["allowed"] is True


def test_objection_blocks_all_channels_and_stops_planned_steps(context, admin):
    client, (ws, *_), user_id = context
    company = firm(admin, ws)
    contact = person(
        admin,
        ws,
        company,
        linkedin_url="https://www.linkedin.com/in/synthetic-objection",
        linkedin_status="confirmed",
    )
    admin.add(
        QueueItem(
            workspace_id=ws,
            day="2026-11-08",
            contact_id=contact.id,
            kind="connect",
            state="pending",
        )
    )
    admin.commit()
    client.post(w(ws, "/channels/refresh"))
    result = client.post(
        w(ws, f"/contacts/{contact.id}/objection"), json={"reason": "Bitte keine Werbung"}
    )
    assert result.status_code == 201, result.text
    body = result.json()
    assert all(not p["allowed"] for p in body["permissions"].values())
    assert all("Widerspruch" in p["reason"] for p in body["permissions"].values())
    assert body["stopped"]["today"] == 1
    item = admin.scalar(select(QueueItem).where(QueueItem.contact_id == contact.id))
    admin.refresh(item)
    assert item.state == "skipped"
    assert admin.scalar(select(Suppression).where(Suppression.contact_id == contact.id))
    # The existing suppression endpoint stops planned steps too.
    second = person(admin, ws, company, "Zweite")
    admin.add(
        QueueItem(
            workspace_id=ws,
            day="2026-11-08",
            contact_id=second.id,
            kind="connect",
            state="approved",
        )
    )
    admin.commit()
    client.post(w(ws, "/suppressions"), json={"contact_id": second.id, "reason": "Abgemeldet"})
    queued = admin.scalar(select(QueueItem).where(QueueItem.contact_id == second.id))
    admin.refresh(queued)
    assert queued.state == "skipped"
    assert EmailMessage  # scheduled e-mails are covered by the e-mail suite's own stop


def test_cold_email_switch_is_owner_only_and_needs_review_note(context, admin):
    client, (ws, *_), user_id = context
    assert client.get(w(ws, "/channel-policy")).json()["cold_email_enabled"] is False
    assert (
        client.put(w(ws, "/channel-policy"), json={"cold_email_enabled": True}).status_code == 422
    )
    on = client.put(
        w(ws, "/channel-policy"),
        json={
            "cold_email_enabled": True,
            "legal_review_note": "Kanzlei Beispiel, Beratung am 7.11.2026",
        },
    )
    assert on.status_code == 200 and on.json()["cold_email_enabled"] is True
    admin.get(Membership, (ws, user_id)).role = "admin"
    admin.commit()
    assert (
        client.put(w(ws, "/channel-policy"), json={"cold_email_enabled": False}).status_code == 403
    )


def test_duplicates_are_suggested_and_merged_with_reason(context, admin):
    client, (ws, other, *_), _ = context
    company = firm(admin, ws)
    keep = person(admin, ws, company, "Eva", "Doppelt", job_title="Inhaberin")
    drop = person(
        admin,
        ws,
        company,
        "Eva",
        "Doppelt",
        phone="+49 781 111111",
        linkedin_url="https://www.linkedin.com/in/synthetic-eva",
        linkedin_status="confirmed",
    )
    admin.add(
        Consent(
            workspace_id=ws,
            contact_id=drop.id,
            channel="email",
            legal_basis="explicit_consent",
            evidence="Formular",
            expires_at=now() + timedelta(days=30),
        )
    )
    admin.commit()
    drop_id = drop.id
    pairs = client.get(w(ws, "/contacts-duplicates")).json()["items"]
    assert pairs and pairs[0]["reason"] == "Gleicher Name in derselben Firma."
    assert (
        client.post(
            w(other, f"/contacts/{keep.id}/merge"),
            json={"duplicate_id": drop.id, "reason": "Doppelt importiert"},
        ).status_code
        == 404
    )
    merged = client.post(
        w(ws, f"/contacts/{keep.id}/merge"),
        json={"duplicate_id": drop.id, "reason": "Doppelt importiert"},
    )
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert set(body["filled"]) >= {"phone", "linkedin_url"}
    assert body["moved"].get("consents") == 1
    assert body["channels"]["route"] == "linkedin"
    admin.expire_all()
    assert admin.scalar(select(Contact.id).where(Contact.id == drop_id)) is None
    kept = admin.get(Contact, keep.id)
    admin.refresh(kept)
    assert kept.linkedin_status == "confirmed" and kept.phone == "+49 781 111111"
    record = admin.scalar(select(ContactMerge).where(ContactMerge.kept_contact_id == keep.id))
    assert record.reason == "Doppelt importiert" and record.details["merged_name"] == "Eva Doppelt"
    assert admin.scalar(
        select(ContactPoint).where(
            ContactPoint.contact_id == keep.id, ContactPoint.channel == "linkedin"
        )
    )
