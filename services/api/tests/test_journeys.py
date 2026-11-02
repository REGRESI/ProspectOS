"""Connected workflow proofs against PostgreSQL; fixtures are exclusively synthetic."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, now
from app.jobs import execute_one, tenant
from app.journeys import LeadProfile, SequenceStepInput
from app.models import Contact, Deal, Discovery, Membership


def url(ws, path):
    return f"/v1/workspaces/{ws}/{path}"


def contact(client, ws, name="Synthetic", **fields):
    result = client.post(
        url(ws, "contacts"),
        json={
            "first_name": name,
            "last_name": "Fixture",
            "company": "Fiktive Firma",
            "job_title": "Office Management",
            "location": "Offenburg",
            **fields,
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_company_count_and_linked_context_are_real(context, admin):
    client, (ws, *_), _ = context
    first = contact(client, ws, "First")
    second = contact(client, ws, "Second")
    company_id = admin.get(Contact, first["id"]).company_id
    admin.get(Contact, second["id"]).company_id = company_id
    admin.add(
        Deal(
            workspace_id=ws,
            contact_id=first["id"],
            title="Synthetic opportunity",
            stage="qualified",
            amount=10000,
        )
    )
    admin.commit()
    summary = client.get(url(ws, "companies/summary")).json()
    company = next(row for row in summary["items"] if row["id"] == company_id)
    assert company["contact_count"] == 2 and company["deal_count"] == 1
    detail = client.get(url(ws, f"companies/{company_id}"))
    assert detail.status_code == 200, detail.text
    assert detail.json()["contacts_total"] == 2 and len(detail.json()["contacts"]) == 2
    assert detail.json()["deals"][0]["amount"] == 10000


def test_company_and_contact_context_deny_foreign_ids(context):
    client, (a, b, *_), _ = context
    lead = contact(client, b)
    ctx = client.get(url(b, f"contacts/{lead['id']}/context")).json()
    assert client.get(url(a, f"contacts/{lead['id']}/context")).status_code == 404
    assert client.get(url(a, f"companies/{ctx['company']['id']}")).status_code == 404


def test_bulk_tags_owner_status_and_segment_restore(context):
    client, (ws, *_), user = context
    lead = contact(client, ws)
    changed = client.post(
        url(ws, "leads/bulk"),
        json={
            "contact_ids": [lead["id"]],
            "status": "qualified",
            "tags_add": ["Priorität", "Region"],
            "owner_id": user,
        },
    )
    assert changed.status_code == 200, changed.text
    query = {
        "statuses": ["qualified"],
        "tags": ["Priorität"],
        "owner_id": user,
        "has_email": "missing",
        "location": "Offenburg",
    }
    matches = client.post(url(ws, "leads/query"), json=query)
    assert matches.status_code == 200, matches.text
    row = matches.json()["items"][0]
    assert row["owner_id"] == user and row["tags"] == ["Priorität", "Region"]
    assert "email" in row["completeness"]["missing"]
    segment = client.post(
        url(ws, "segments"), json={"name": "Regional qualified", "filters": query}
    )
    assert segment.status_code == 201, segment.text
    restored = client.get(url(ws, "segments")).json()["items"][0]["filters"]
    assert client.post(url(ws, "leads/query"), json=restored).json()["total"] == 1
    assert (
        client.post(
            url(ws, "segments"), json={"name": "Unsafe", "filters": {"sql": "DROP TABLE contacts"}}
        ).status_code
        == 422
    )


def test_bulk_is_atomic_and_cannot_assign_foreign_owner(context, admin):
    client, (a, b, *_), _ = context
    own = contact(client, a)
    foreign = contact(client, b)
    response = client.post(
        url(a, "leads/bulk"), json={"contact_ids": [own["id"], foreign["id"]], "status": "archived"}
    )
    assert response.status_code == 404
    assert client.get(url(a, f"contacts/{own['id']}")).json()["status"] == "new"
    assert (
        client.post(
            url(a, "leads/bulk"), json={"contact_ids": [own["id"]], "owner_id": "not-a-member"}
        ).status_code
        == 422
    )


def test_readonly_query_for_analyst_and_write_denied(context, admin):
    client, (ws, *_), user = context
    contact(client, ws)
    member = admin.get(Membership, (ws, user))
    member.role = "analyst"
    admin.commit()
    assert client.post(url(ws, "leads/query"), json={}).status_code == 200
    assert (
        client.post(url(ws, "segments"), json={"name": "Cannot write", "filters": {}}).status_code
        == 403
    )


def test_saved_search_requires_confirmation_and_keeps_unparsed_text(context):
    client, (ws, other, *_), _ = context
    parsed = client.post(
        url(ws, "discovery/interpret"),
        json={
            "briefing": "Büros in Offenburg mit 10–250 Mitarbeitenden und Facility Management im Umkreis von 25 km"
        },
    ).json()
    assert parsed["suggested_filters"]["city"] == "Offenburg"
    assert parsed["suggested_filters"]["min_employees"] == 10
    assert parsed["interpretation"]["requires_confirmation"] is True
    assert "Facility" in parsed["interpretation"]["unparsed"]
    saved = client.post(
        url(ws, "discovery/searches"),
        json={
            "name": "Regional demo",
            "briefing": "Explicit fictional test",
            "filters": parsed["suggested_filters"],
        },
    )
    assert saved.status_code == 201, saved.text
    sid = saved.json()["id"]
    assert (
        client.post(url(ws, f"discovery/searches/{sid}/run"), json={"confirmed": False}).status_code
        == 422
    )
    assert client.get(url(other, "discovery/searches")).json()["total"] == 0
    assert (
        client.post(
            url(other, f"discovery/searches/{sid}/run"), json={"confirmed": True}
        ).status_code
        == 404
    )
    queued = client.post(url(ws, f"discovery/searches/{sid}/run"), json={"confirmed": True})
    assert queued.status_code == 202, queued.text
    assert queued.json()["warnings"]
    assert execute_one(ws)
    job = client.get(url(ws, f"jobs/{queued.json()['id']}")).json()
    assert job["status"] == "succeeded"
    results = client.get(url(ws, f"discovery/runs/{job['result']['run_id']}/results")).json()
    assert all(row["source"] == "synthetic_demo" for row in results["items"])
    assert results["items"][0]["last_verified_at"] is None


def test_selected_discovery_import_deduplicates_and_preserves_kind(context, admin):
    client, (ws, other, *_), _ = context
    run = Discovery(
        workspace_id=ws,
        query="Test licensed company",
        results=[
            {
                "external_key": "licensed-fixture-1",
                "company": "Fiktiver Lizenzdatensatz",
                "location": "Offenburg",
                "industry": "office",
                "source": "licensed_fixture",
                "source_url": "https://provider.example.test/record/1",
                "license": "Synthetic test-only record",
                "confidence": "provider_reported",
                "observed_at": now().isoformat(),
                "website": "https://fictional.example.test",
            }
        ],
    )
    admin.add(run)
    admin.commit()
    rows = client.get(url(ws, f"discovery/runs/{run.id}/results")).json()["items"]
    assert rows[0]["entity_kind"] == "company" and rows[0]["imported"] is False
    assert (
        client.post(
            url(other, f"discovery/runs/{run.id}/import-selected"), json={"keys": [rows[0]["key"]]}
        ).status_code
        == 404
    )
    first = client.post(
        url(ws, f"discovery/runs/{run.id}/import-selected"), json={"keys": [rows[0]["key"]]}
    )
    assert first.status_code == 200, first.text
    assert first.json() == {"created": 1, "duplicates": 0, "companies": 1, "contacts": 0}
    assert client.get(url(ws, "contacts")).json()["total"] == 0
    second = client.post(
        url(ws, f"discovery/runs/{run.id}/import-selected"), json={"keys": [rows[0]["key"]]}
    ).json()
    assert second["created"] == 0 and second["duplicates"] == 1
    assert (
        client.post(
            url(ws, f"discovery/runs/{run.id}/import-selected"), json={"keys": ["forged"]}
        ).status_code
        == 422
    )


def test_campaign_enrollment_sequence_drafts_approval_and_manual_history(context):
    client, (ws, *_), _ = context
    lead = contact(client, ws)
    campaign = client.post(
        url(ws, "campaigns"),
        json={"name": "Synthetic sequence", "goal": "Manual exchange", "contact_ids": []},
    ).json()
    enrolled = client.post(
        url(ws, "leads/bulk"), json={"contact_ids": [lead["id"]], "campaign_id": campaign["id"]}
    )
    assert enrolled.json()["enrolled"] == 1
    assert (
        client.post(
            url(ws, "leads/bulk"), json={"contact_ids": [lead["id"]], "campaign_id": campaign["id"]}
        ).json()["enrolled"]
        == 0
    )
    seq = {
        "channel": "linkedin_manual",
        "steps": [
            {
                "position": 0,
                "delay_days": 0,
                "channel": "linkedin_manual",
                "template": "Hallo {first_name}, ich möchte mich zu {company} austauschen.",
            },
            {
                "position": 1,
                "delay_days": 3,
                "channel": "linkedin_manual",
                "template": "Hallo {first_name}, darf ich nachfragen?",
            },
        ],
    }
    assert client.put(url(ws, f"campaigns/{campaign['id']}/sequence"), json=seq).status_code == 200
    generated = client.post(url(ws, f"campaigns/{campaign['id']}/generate-drafts"), json={})
    assert generated.status_code == 200, generated.text
    assert generated.json()["created"] == 2
    assert (
        client.post(url(ws, f"campaigns/{campaign['id']}/generate-drafts"), json={}).json()[
            "duplicates"
        ]
        == 2
    )
    inbox = client.get(url(ws, "outreach/inbox")).json()["items"]
    assert all(
        row["campaign"]["id"] == campaign["id"] and row["source"] == "offline" and row["subject"]
        for row in inbox
    )
    assert client.post(url(ws, f"outreach/drafts/{inbox[0]['id']}/approve")).status_code == 200
    before = client.get(url(ws, f"campaigns/{campaign['id']}/workspace")).json()
    assert before["counts"]["approved"] == 1
    activity = client.post(
        url(ws, "outreach/handoffs"),
        json={
            "contact_id": lead["id"],
            "campaign_id": campaign["id"],
            "kind": "replied",
            "note": "Synthetic manually recorded response",
        },
    )
    assert activity.status_code == 201 and activity.json()["verification"] == "self_reported"
    after = client.get(url(ws, f"campaigns/{campaign['id']}/workspace")).json()
    assert after["counts"]["replied"] == 1 and after["sequence"][1]["delay_days"] == 3
    ctx = client.get(url(ws, f"contacts/{lead['id']}/context")).json()
    assert ctx["activities"][0]["verification"] == "self_reported" and len(ctx["drafts"]) == 2


def test_sequence_and_handoff_reject_cross_tenant_and_template_execution(context):
    client, (a, b, *_), _ = context
    lead = contact(client, a)
    foreign = client.post(url(b, "campaigns"), json={"name": "Private"}).json()
    assert (
        client.post(
            url(a, "leads/bulk"), json={"contact_ids": [lead["id"]], "campaign_id": foreign["id"]}
        ).status_code
        == 404
    )
    assert (
        client.post(
            url(a, "outreach/handoffs"),
            json={"contact_id": lead["id"], "campaign_id": foreign["id"], "kind": "connected"},
        ).status_code
        == 404
    )
    with pytest.raises(ValueError):
        SequenceStepInput(position=0, template="{__class__}")


def test_multiple_icp_profiles_and_unknown_evidence(context):
    client, (ws, other, *_), _ = context
    contact(client, ws)
    profile = {
        "name": "Evidence-aware profile",
        "locations": ["Offenburg"],
        "roles": ["Office"],
        "industries": ["office"],
        "min_employees": 10,
        "max_employees": 250,
        "needs": ["cleaning"],
        "weights": {"location": 20, "role": 20, "industry": 20, "size": 20, "needs": 20},
        "required_fields": ["email"],
    }
    created = client.post(url(ws, "icp-profiles"), json=profile)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert client.get(url(other, f"icp-profiles/{pid}")).status_code == 404
    result = client.post(url(ws, "leads/query"), json={"icp_id": pid, "sort": "score"}).json()[
        "items"
    ][0]
    assert result["score"]["value"] == 40
    assert any(
        "unbekannt" in f["reason"]
        for f in result["score"]["factors"]
        if f["name"] == "Unternehmensgröße"
    )
    assert result["score"]["value"] != 100
    profile["name"] = "Updated profile"
    assert client.put(url(ws, f"icp-profiles/{pid}"), json=profile).json()["version"] == 2


def test_journey_tables_fail_closed_and_composite_owner_fk(context, admin):
    client, (a, b, *_), user = context
    lead = contact(client, a)
    with SessionLocal() as db:
        assert db.scalars(select(LeadProfile)).all() == []
        tenant(db, b)
        with pytest.raises(IntegrityError):
            db.add(LeadProfile(workspace_id=b, contact_id=lead["id"], tags=[]))
            db.flush()
    assert client.post(url(a, "leads/query"), json={"sort": "random()"}).status_code == 422


def test_discovery_applies_known_postfilters_and_durable_paid_dispatch(context, monkeypatch, admin):
    from app.journeys import CompanyProfile
    from app.models import Company
    from app.platform_models import Job
    from app.providers.licensed import CompanyCandidate

    client, (ws, *_), _ = context
    company = Company(
        workspace_id=ws,
        name="Synthetic customer",
        identity="people_data_labs:customer",
        website="https://customer.example",
        provenance={},
    )
    admin.add(company)
    admin.flush()
    admin.add(CompanyProfile(workspace_id=ws, company_id=company.id, is_customer=True))
    admin.commit()
    monkeypatch.setenv("PDL_API_KEY", "synthetic-test-credential")
    monkeypatch.setenv("PDL_LICENSE_APPROVED", "true")
    monkeypatch.setenv("PDL_LICENSE_REFERENCE", "synthetic-test-license")

    def provider(criteria, limit):
        assert criteria.min_employees == 10 and criteria.max_employees == 250
        with SessionLocal() as db:
            tenant(db, ws)
            assert db.scalar(select(Job).where(Job.kind == "discovery")).side_effect_started
        return [
            CompanyCandidate(
                external_key=key,
                company=name,
                industry=industry,
                location="Berlin",
                license="Synthetic",
                observed_at=now().isoformat(),
            )
            for key, name, industry in [
                ("match", "Synthetic tooling", "software"),
                ("exclude", "Synthetic tooling", "finance"),
                ("customer", "Synthetic tooling", "software"),
                ("keyword", "Synthetic other", "software"),
            ]
        ]

    monkeypatch.setattr("app.providers.licensed.search_companies", provider)
    search = client.post(
        url(ws, "discovery/searches"),
        json={
            "name": "Known field filters",
            "filters": {
                "provider": "pdl",
                "industries": ["software"],
                "excluded_industries": ["finance"],
                "keywords": ["tooling"],
                "min_employees": 10,
                "max_employees": 250,
            },
        },
    ).json()
    queued = client.post(
        url(ws, f"discovery/searches/{search['id']}/run"),
        json={"confirmed": True, "license_confirmed": True},
    )
    assert queued.status_code == 202, queued.text
    assert execute_one(ws)
    job = client.get(url(ws, f"jobs/{queued.json()['id']}")).json()
    assert job["status"] == "succeeded", job
    assert [r["external_key"] for r in job["result"]["results"]] == ["match"]


def test_deal_context_and_filtered_totals(context):
    client, (a, b, *_), _ = context
    lead = contact(client, a)
    deal = client.post(
        url(a, "deals"),
        json={
            "title": "Synthetic deal",
            "amount": 12300,
            "stage": "qualified",
            "contact_id": lead["id"],
        },
    ).json()
    assert client.get(url(b, f"deals/{deal['id']}/context")).status_code == 404
    detail = client.get(url(a, f"deals/{deal['id']}/context"))
    assert detail.status_code == 200, detail.text
    assert detail.json()["contact"]["id"] == lead["id"]
    listing = client.get(url(a, "deals?stage=qualified&sort=amount"))
    assert listing.status_code == 200, listing.text
    assert listing.json()["open_value"] == 12300


def test_new_profile_and_campaign_links_export_and_subject_delete(context):
    from sqlalchemy import func

    from app.journeys import CampaignDraft, ManualActivity

    client, (ws, *_), _ = context
    lead = contact(client, ws)
    campaign = client.post(
        url(ws, "campaigns"), json={"name": "Synthetic privacy proof", "contact_ids": [lead["id"]]}
    ).json()
    assert (
        client.post(
            url(ws, "leads/bulk"), json={"contact_ids": [lead["id"]], "tags_add": ["Synthetic"]}
        ).status_code
        == 200
    )
    assert (
        client.post(url(ws, f"campaigns/{campaign['id']}/generate-drafts"), json={}).status_code
        == 200
    )
    assert (
        client.post(
            url(ws, "outreach/handoffs"),
            json={
                "contact_id": lead["id"],
                "campaign_id": campaign["id"],
                "kind": "profile_opened",
            },
        ).status_code
        == 201
    )
    exported = client.post(url(ws, "privacy/export"))
    assert exported.status_code == 200, exported.text
    assert exported.json()["data"]["lead_profiles"][0]["tags"] == ["Synthetic"]
    assert "connections" not in exported.json()["data"]
    deleted = client.post(url(ws, f"privacy/delete-contact/{lead['id']}"))
    assert deleted.status_code == 200, deleted.text
    with SessionLocal() as db:
        tenant(db, ws)
        for model in [LeadProfile, CampaignDraft, ManualActivity]:
            assert db.scalar(select(func.count()).select_from(model)) == 0
