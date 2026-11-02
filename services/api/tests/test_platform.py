import hashlib
import hmac
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from cryptography.fernet import Fernet
from PIL import Image

from app.db import SessionLocal, now
from app.jobs import claim, enqueue, execute_one, tenant
from app.models import Membership
from app.platform_models import Connection, Job, WebhookEvent
from app.providers.ai import GenerationResult


def endpoint(ws, path):
    return f"/v1/workspaces/{ws}/{path}"


def image_bytes():
    image = Image.new("RGB", (16, 16), "#4f46e5")
    data = io.BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


def upload(c, ws):
    result = c.post(
        endpoint(ws, "assets/upload"),
        files={"file": ("image.png", image_bytes(), "image/png")},
        data={"alt_text": "Synthetic test image", "rights_confirmed": "true"},
    )
    assert result.status_code == 201, result.text
    return result.json()


def contact(c, ws):
    r = c.post(
        endpoint(ws, "contacts"),
        json={"first_name": "Synthetic", "email": "synthetic@example.test"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_private_media_validation_cross_tenant_and_reencoding(context, monkeypatch, tmp_path):
    monkeypatch.setenv("ASSET_ROOT", str(tmp_path))
    c, (a, b, *_), _ = context
    item = upload(c, a)
    content = c.get(item["url"])
    assert content.status_code == 200 and content.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(content.content)).format == "JPEG"
    assert c.get(endpoint(b, f"assets/{item['id']}/content")).status_code == 404
    malicious = c.post(
        endpoint(a, "assets/upload"),
        files={"file": ("x.svg", b'<svg onload="alert(1)"/>', "image/svg+xml")},
        data={"alt_text": "malicious", "rights_confirmed": "true"},
    )
    assert malicious.status_code == 422
    assert (
        c.post(
            endpoint(a, "assets/upload"),
            files={"file": ("image.png", image_bytes())},
            data={"alt_text": "No rights"},
        ).status_code
        == 422
    )
    assert (
        c.post(
            endpoint(a, "assets/upload"),
            content=b"x" * (6 * 1024 * 1024 + 1),
            headers={"Content-Type": "application/octet-stream"},
        ).status_code
        == 413
    )


def test_brands_and_asset_changes_invalidate_approval(context, monkeypatch, tmp_path):
    monkeypatch.setenv("ASSET_ROOT", str(tmp_path))
    c, (a, b, *_), _ = context
    brand = c.post(
        endpoint(a, "brands"),
        json={"name": "Synthetic brand", "voice": "Helpful", "pillars": ["Workplace"]},
    ).json()
    asset = upload(c, a)
    post = c.post(
        endpoint(a, "social/posts"),
        json={"caption": "First", "brand_id": brand["id"], "asset_ids": [asset["id"]]},
    ).json()
    assert post["asset_ids"] == [asset["id"]]
    assert (
        c.post(
            endpoint(b, "social/posts"), json={"caption": "Forgery", "asset_ids": [asset["id"]]}
        ).status_code
        == 404
    )
    base = endpoint(a, f"social/posts/{post['id']}")
    c.post(base + "/submit-review")
    c.post(base + "/approve")
    r = c.patch(
        base, json={"caption": "Changed", "version": 1, "asset_ids": [], "brand_id": brand["id"]}
    )
    assert r.status_code == 200, r.text
    assert (
        r.json()["approved_revision"] is None
        and r.json()["state"] == "needs_review"
        and r.json()["asset_ids"] == []
    )


def test_crm_campaign_tenant_fk_notes_tasks(context):
    c, (a, b, *_), _ = context
    lead = contact(c, a)
    task = c.post(
        endpoint(a, "tasks"),
        json={
            "title": "Call manually",
            "contact_id": lead["id"],
            "due_at": (now() + timedelta(days=1)).isoformat(),
        },
    ).json()
    assert (
        c.patch(endpoint(a, f"tasks/{task['id']}"), json={"state": "done"}).json()["state"]
        == "done"
    )
    assert (
        c.post(
            endpoint(a, "notes"), json={"body": "User observed fact", "contact_id": lead["id"]}
        ).status_code
        == 201
    )
    assert (
        c.post(
            endpoint(b, "notes"), json={"body": "Forbidden", "contact_id": lead["id"]}
        ).status_code
        == 404
    )
    campaign = c.post(
        endpoint(a, "campaigns"),
        json={"name": "Test", "goal": "Manual draft", "contact_ids": [lead["id"]]},
    ).json()
    assert campaign["contacts"] == 1
    assert c.post(endpoint(a, f"campaigns/{campaign['id']}/drafts")).json()["created"] == 1
    assert c.get(endpoint(a, "outreach/drafts")).json()["items"][0]["send_allowed"] is False
    export = c.post(endpoint(a, "privacy/export"))
    assert export.status_code == 200, export.text
    assert (
        "connections" not in export.json()["data"] and "auth_sessions" not in export.json()["data"]
    )


def test_queue_actor_revocation_and_private_job(context, admin):
    c, (a, b, *_), user = context
    job = c.post(
        endpoint(a, "discovery/search"),
        json={"query": "Synthetic offices", "provider": "synthetic"},
    ).json()
    assert c.get(endpoint(b, f"jobs/{job['id']}")).status_code == 404
    member = admin.get(Membership, (a, user))
    member.role = "analyst"
    admin.commit()
    assert execute_one(a)
    result = c.get(endpoint(a, f"jobs/{job['id']}")).json()
    assert result["status"] == "failed" and result["last_error"] == "job_actor_permission_revoked"


def test_async_discovery_and_import(context):
    c, (ws, *_), _ = context
    job = c.post(
        endpoint(ws, "discovery/search"),
        json={"query": "Demo only", "provider": "synthetic", "limit": 3},
    ).json()
    assert job["status"] == "queued"
    assert execute_one(ws)
    result = c.get(endpoint(ws, f"jobs/{job['id']}")).json()
    assert result["status"] == "succeeded" and len(result["result"]["results"]) == 3
    assert (
        c.post(endpoint(ws, f"discovery/runs/{result['result']['run_id']}/import")).json()[
            "created"
        ]
        == 3
    )


def test_paid_ai_budget_and_usage_ledger(context, monkeypatch):
    c, (ws, *_), _ = context
    for name, value in {
        "LLM_API_KEY": "test-only",
        "LLM_MODEL": "test-model",
        "LLM_INPUT_USD_PER_MILLION": "1",
        "LLM_OUTPUT_USD_PER_MILLION": "2",
    }.items():
        monkeypatch.setenv(name, value)
    assert c.put(endpoint(ws, "usage/budget"), json={"ai_budget_minor": 0}).status_code == 200
    assert (
        c.post(
            endpoint(ws, "ai/generate"), json={"purpose": "caption", "prompt": "Test caption"}
        ).status_code
        == 402
    )
    c.put(endpoint(ws, "usage/budget"), json={"ai_budget_minor": 100})
    monkeypatch.setattr(
        "app.providers.ai.generate_text",
        lambda *_: GenerationResult(
            text="Suggestion only",
            citations=[],
            unverified_claims=["No evidence"],
            model="test-model",
            input_tokens=10,
            output_tokens=20,
            estimated_cost_microunits=100,
        ),
    )
    result = c.post(
        endpoint(ws, "ai/generate"), json={"purpose": "caption", "prompt": "Test caption"}
    )
    assert result.status_code == 202, result.text
    job = result.json()
    assert c.get(endpoint(ws, "usage")).json()["ai_reserved_minor"] > 0
    assert execute_one(ws)
    final = c.get(endpoint(ws, f"jobs/{job['id']}")).json()
    assert final["status"] == "succeeded" and final["result"]["verified"] is False
    usage = c.get(endpoint(ws, "usage")).json()
    assert usage["ai_reserved_minor"] == 0 and usage["ai_spent_minor"] == 1


def test_lease_recovery_and_ambiguous_paid_result(context):
    c, (ws, *_), user = context
    with SessionLocal() as db, db.begin():
        tenant(db, ws)
        local = enqueue(db, ws, user, "discovery", {"query": "Demo", "provider": "synthetic"})
        local.status = "running"
        local.attempts = 1
        local.lease_until = now() - timedelta(seconds=1)
        paid = enqueue(db, ws, user, "publish", {"post_id": "missing"})
        paid.status = "running"
        paid.attempts = 1
        paid.lease_until = now() - timedelta(seconds=1)
        paid.side_effect_started = True
        paid_id = paid.id
    selected = claim(ws)
    assert selected is not None
    result = c.get(endpoint(ws, f"jobs/{paid_id}")).json()
    assert result["status"] == "ambiguous"
    assert c.post(endpoint(ws, f"jobs/{paid_id}/retry")).status_code == 409


def connected_post(c, ws, user, monkeypatch):
    key = Fernet.generate_key()
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", key.decode())
    monkeypatch.setenv("LINKEDIN_PUBLISHING_APPROVED", "true")
    monkeypatch.setenv("LINKEDIN_API_VERSION", "209901")
    with SessionLocal() as db, db.begin():
        tenant(db, ws)
        db.add(
            Connection(
                workspace_id=ws,
                provider="linkedin",
                encrypted_token=Fernet(key).encrypt(b"fake-test-token").decode(),
                author_urn="urn:li:person:test",
                scopes=["w_member_social"],
                expires_at=now() + timedelta(hours=1),
            )
        )
    c.put(endpoint(ws, "social/policy"), json={"mode": "authorized_auto", "max_posts_daily": 1})
    post = c.post(endpoint(ws, "social/posts"), json={"caption": "Explicitly approved test"}).json()
    base = endpoint(ws, f"social/posts/{post['id']}")
    c.post(base + "/submit-review")
    c.post(base + "/approve")
    return post, base


def test_no_duplicate_publication_concurrent_workers(context, monkeypatch):
    c, (ws, *_), user = context
    post, base = connected_post(c, ws, user, monkeypatch)
    receipts = []

    def publish(_):
        receipts.append("one")
        return {"id": "urn:li:share:test-receipt", "confirmed": True}

    monkeypatch.setattr("app.social.send_publication", publish)
    queued = c.post(base + "/publish", json={})
    assert queued.status_code == 202, queued.text
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(execute_one, [ws, ws]))
    assert receipts == ["one"]
    result = c.get(endpoint(ws, f"jobs/{queued.json()['id']}")).json()
    assert result["status"] == "succeeded"
    stored = c.get(endpoint(ws, "social/posts")).json()["items"][0]
    assert (
        stored["state"] == "published" and stored["provider_post_id"] == "urn:li:share:test-receipt"
    )


def test_publication_approval_revocation_before_worker(context, monkeypatch):
    c, (ws, *_), user = context
    post, base = connected_post(c, ws, user, monkeypatch)
    queued = c.post(base + "/publish", json={"automation_authorized": True}).json()
    c.put(endpoint(ws, "social/policy"), json={"mode": "manual", "max_posts_daily": 1})
    receipts = []
    monkeypatch.setattr("app.social.send_publication", lambda *_: receipts.append("bad"))
    assert execute_one(ws)
    assert receipts == []
    assert c.get(endpoint(ws, f"jobs/{queued['id']}")).json()["status"] == "failed"


def test_email_requires_approval_source_consent_and_suppression(context, monkeypatch):
    c, (ws, *_), _ = context
    lead = contact(c, ws)
    draft = c.post(endpoint(ws, "outreach/drafts"), json={"contact_id": lead["id"]}).json()
    base = endpoint(ws, f"outreach/drafts/{draft['id']}")
    for name, value in {
        "RESEND_API_KEY": "test-only",
        "EMAIL_FROM": "operator@example.test",
        "EMAIL_SEND_ENABLED": "true",
    }.items():
        monkeypatch.setenv(name, value)
    assert c.post(base + "/send-email").status_code == 409
    assert (
        c.patch(
            base, json={"content": "Reviewed message", "subject": "Explicit test", "revision": 1}
        ).status_code
        == 200
    )
    c.post(base + "/approve")
    c.post(endpoint(ws, f"contacts/{lead['id']}/source-review"), json={"approved": True})
    assert c.post(base + "/send-email").status_code == 409
    c.post(
        endpoint(ws, "consents"),
        json={
            "contact_id": lead["id"],
            "evidence": "Synthetic signed test consent",
            "legal_basis": "explicit_consent",
            "expires_at": (now() + timedelta(days=1)).isoformat(),
        },
    )
    job = c.post(base + "/send-email")
    assert job.status_code == 202, job.text
    c.post(endpoint(ws, "suppressions"), json={"contact_id": lead["id"], "reason": "Test opt out"})
    deliveries = []
    monkeypatch.setattr("app.commercial.send_authorized_email", lambda *_: deliveries.append("bad"))
    assert execute_one(ws) and deliveries == []
    assert c.get(endpoint(ws, f"jobs/{job.json()['id']}")).json()["status"] == "failed"


def test_signed_billing_webhook_is_idempotent(context, monkeypatch, admin):
    c, (ws, *_), _ = context
    secret = "whsec_test-only"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    event_id = "evt_" + uuid4().hex
    event = {
        "id": event_id,
        "type": "checkout.session.completed",
        "livemode": False,
        "data": {
            "object": {
                "customer": "cus_test",
                "subscription": "sub_test",
                "metadata": {"workspace_id": ws},
            }
        },
    }
    payload = json.dumps(event).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode(), timestamp.encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    headers = {
        "Stripe-Signature": f"t={timestamp},v1={signature}",
        "Content-Type": "application/json",
    }
    first = c.post("/v1/webhooks/stripe", content=payload, headers=headers)
    assert first.status_code == 200, first.text
    second = c.post("/v1/webhooks/stripe", content=payload, headers=headers)
    assert second.json()["duplicate"] is True
    assert c.get(endpoint(ws, "billing")).json()["status"] == "pending"
    admin.query(WebhookEvent).filter(WebhookEvent.id == event_id).delete()
    admin.commit()


def test_oauth_invalid_state_rejected_before_provider_call(context):
    c, *_ = context
    assert c.get("/v1/integrations/linkedin/callback?state=invalid&code=invalid").status_code == 400


def test_privacy_deletion_removes_derived_records_and_queued_payloads(context):
    c, (ws, *_), user = context
    lead = contact(c, ws)
    c.post(endpoint(ws, "notes"), json={"body": "Private derived note", "contact_id": lead["id"]})
    c.post(endpoint(ws, "tasks"), json={"title": "Private task", "contact_id": lead["id"]})
    c.post(endpoint(ws, "outreach/drafts"), json={"contact_id": lead["id"]})
    with SessionLocal() as db, db.begin():
        tenant(db, ws)
        job = enqueue(
            db, ws, user, "ai", {"contact_id": lead["id"], "prompt": "Private derived fact"}
        )
        job_id = job.id
    response = c.post(endpoint(ws, f"privacy/delete-contact/{lead['id']}"))
    assert response.status_code == 200, response.text
    assert c.get(endpoint(ws, f"contacts/{lead['id']}")).status_code == 404
    assert c.get(endpoint(ws, "notes")).json()["total"] == 0
    assert c.get(endpoint(ws, "outreach/drafts")).json()["total"] == 0
    with SessionLocal() as db:
        tenant(db, ws)
        item = db.get(Job, job_id)
        assert item.status == "cancelled" and item.payload == {"redacted_for_privacy": True}


def test_paid_ai_retry_cannot_reuse_settled_reservation(context):
    c, (ws, *_), user = context
    with SessionLocal() as db, db.begin():
        tenant(db, ws)
        job = enqueue(db, ws, user, "ai", {"reservation_minor": 1, "prompt": "No free retries"})
        job.status = "failed"
        job_id = job.id
    assert c.post(endpoint(ws, f"jobs/{job_id}/retry")).status_code == 409


def test_chunked_body_limit(context):
    c, (ws, *_), _ = context

    def chunks():
        for _ in range(5):
            yield b" " * 100000

    response = c.post(
        endpoint(ws, "notes"), content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413, response.text


def test_entitlement_limits_are_enforced_and_import_is_atomic(context, monkeypatch):
    c, (ws, *_), _ = context
    monkeypatch.setenv("TRIAL_MAX_CONTACTS", "1")
    payload = b"First Name,Last Name,Linkedin Profile Url\nDemo1,Synthetic,https://www.linkedin.com/in/limit-1\nDemo2,Synthetic,https://www.linkedin.com/in/limit-2\n"
    preview = c.post(
        endpoint(ws, "imports/preview"), files={"file": ("synthetic.csv", payload)}
    ).json()
    result = c.post(endpoint(ws, f"imports/{preview['id']}/commit"))
    assert result.status_code == 402, result.text
    assert c.get(endpoint(ws, "contacts")).json()["total"] == 0
    assert c.post(endpoint(ws, "contacts"), json={"first_name": "Only allowed"}).status_code == 201
    assert c.post(endpoint(ws, "contacts"), json={"first_name": "Over limit"}).status_code == 402
    assert c.get(endpoint(ws, "billing")).json()["entitlements"]["max_contacts"] == 1


def test_daily_publication_quota_counts_actual_dispatch_not_creation(context, monkeypatch):
    c, (ws, *_), user = context
    post, base = connected_post(c, ws, user, monkeypatch)
    with SessionLocal() as db, db.begin():
        tenant(db, ws)
        previous = enqueue(db, ws, user, "publish", {"post_id": "prior"}, "prior-published")
        previous.created_at = now() - timedelta(days=2)
        previous.dispatched_at = now()
        previous.side_effect_started = True
        previous.status = "succeeded"
    result = c.post(base + "/publish", json={})
    assert result.status_code == 202, result.text
    deliveries = []
    monkeypatch.setattr("app.social.send_publication", lambda *_: deliveries.append("bad"))
    assert execute_one(ws)
    assert deliveries == []
    assert c.get(endpoint(ws, f"jobs/{result.json()['id']}")).json()["status"] == "failed"


def test_outreach_approver_can_review_but_cannot_dispatch(context, admin):
    c, (ws, *_), user = context
    lead = contact(c, ws)
    draft = c.post(endpoint(ws, "outreach/drafts"), json={"contact_id": lead["id"]}).json()
    base = endpoint(ws, f"outreach/drafts/{draft['id']}")
    c.patch(base, json={"content": "Reviewed message", "subject": "Approval only", "revision": 1})
    member = admin.get(Membership, (ws, user))
    member.role = "approver"
    admin.commit()
    assert c.post(base + "/approve").status_code == 200
    assert c.post(base + "/send-email").status_code == 403
