"""Security and connected-flow evidence for the experience extension.

Provider transports are mocked explicitly; no test sends paid requests or posts.
Run through infra/scripts/validate_database.py to isolate the running worker.
"""

import base64
import hashlib
import io

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.db import SessionLocal
from app.experience import AssetOrigin
from app.jobs import execute_one, tenant
from app.models import Membership
from app.platform_models import Asset, UsageEvent
from app.providers.ai import GenerationResult, ProviderError
from app.providers.images import OpenAIImages


def path(ws, suffix):
    return f"/v1/workspaces/{ws}/{suffix}"


def png(width=24, height=12):
    output = io.BytesIO()
    Image.new("RGB", (width, height), "#4f46e5").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def image_config(monkeypatch, tmp_path):
    monkeypatch.setenv("IMAGE_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("IMAGE_MODEL", "synthetic-image-model")
    monkeypatch.setenv("IMAGE_MAX_COST_USD_CENTS", "5")
    monkeypatch.setenv("ASSET_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def llm_config(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("LLM_MODEL", "synthetic-text-model")
    monkeypatch.setenv("LLM_INPUT_USD_PER_MILLION", "1")
    monkeypatch.setenv("LLM_OUTPUT_USD_PER_MILLION", "2")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "1500")


def test_image_provider_returns_real_base64_bytes_and_bounded_request(image_config):
    expected = png()
    requests = []

    def handle(request):
        import json

        requests.append((request.url, json.loads(request.content)))
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(expected).decode()}]}
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        actual = OpenAIImages().generate("Illustrative synthetic workplace graphic", client=client)
    assert actual == expected
    assert str(requests[0][0]).endswith("/v1/images/generations")
    assert requests[0][1]["model"] == "synthetic-image-model"
    assert requests[0][1]["n"] == 1 and requests[0][1]["output_format"] == "jpeg"


@pytest.mark.parametrize(
    "response",
    [
        {"data": [{"url": "https://example.test/not-stored.jpg"}]},
        {"data": [{"b64_json": "not-base64!"}]},
        {"data": []},
    ],
)
def test_image_provider_never_treats_placeholder_or_malformed_output_as_success(
    image_config, response
):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response))
    ) as client:
        with pytest.raises(ProviderError) as error:
            OpenAIImages().generate("Synthetic illustration", client=client)
    assert error.value.code == "invalid_image_output" and error.value.ambiguous


def test_paid_image_timeout_is_ambiguous_and_not_retryable(image_config):
    def timeout(request):
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ProviderError) as error:
            OpenAIImages().generate("Synthetic illustration", client=client)
    assert error.value.ambiguous and not error.value.retryable


def queue_image(client, ws, **changes):
    body = {
        "prompt": "Synthetic geometric office illustration",
        "alt_text": "Synthetic purple geometry",
        "rights_confirmed": True,
    } | changes
    response = client.post(path(ws, "social/images/generate"), json=body)
    assert response.status_code == 202, response.text
    return response.json()


def test_real_image_must_be_stored_privately_and_reviewed_before_library_or_post(
    context, image_config, monkeypatch
):
    client, (a, b, *_), _ = context
    monkeypatch.setattr(OpenAIImages, "generate", lambda self, prompt: png())
    job = queue_image(client, a)
    assert client.get(path(a, "usage")).json()["ai_reserved_minor"] == 5
    assert execute_one(a)
    result = client.get(path(a, f"jobs/{job['id']}")).json()
    assert result["status"] == "succeeded" and result["result"]["review_required"]
    asset = result["result"]["asset"]
    preview = client.get(asset["url"])
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(preview.content)).size == (24, 12)
    assert client.get(path(a, "assets")).json()["total"] == 0
    assert client.get(path(b, f"assets/{asset['id']}/content")).status_code == 404
    assert (
        client.post(
            path(b, f"social/images/{job['id']}/save"), json={"rights_confirmed": True}
        ).status_code
        == 404
    )
    assert (
        client.post(
            path(a, "social/posts"),
            json={"caption": "Must review first", "asset_ids": [asset["id"]]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            path(a, f"social/images/{job['id']}/save"), json={"rights_confirmed": False}
        ).status_code
        == 422
    )
    accepted = client.post(
        path(a, f"social/images/{job['id']}/save"), json={"rights_confirmed": True}
    )
    assert accepted.status_code == 200, accepted.text
    assert client.get(path(a, "assets")).json()["total"] == 1
    assert (
        client.post(
            path(a, "social/posts"), json={"caption": "Reviewed image", "asset_ids": [asset["id"]]}
        ).status_code
        == 201
    )
    with SessionLocal() as db:
        tenant(db, a)
        origin = db.scalar(select(AssetOrigin).where(AssetOrigin.job_id == job["id"]))
        stored = db.get(Asset, origin.asset_id)
        assert origin.reviewed and origin.kind == "ai_generated"
        assert origin.metadata_json["provider"] == "openai_images"
        assert stored.sha256 == hashlib.sha256(preview.content).hexdigest()
        assert (image_config / stored.storage_key).is_file()
    usage = client.get(path(a, "usage")).json()
    assert usage["ai_reserved_minor"] == 0 and usage["ai_spent_minor"] == 5


def test_failed_paid_image_never_creates_asset_or_free_retry(context, image_config, monkeypatch):
    client, (ws, *_), _ = context

    def failed(*_):
        raise ProviderError("ambiguous_result", ambiguous=True)

    monkeypatch.setattr(OpenAIImages, "generate", failed)
    job = queue_image(client, ws)
    assert execute_one(ws)
    result = client.get(path(ws, f"jobs/{job['id']}")).json()
    assert result["status"] == "ambiguous" and "asset" not in result["result"]
    assert client.get(path(ws, "assets")).json()["total"] == 0
    assert client.post(path(ws, f"jobs/{job['id']}/retry")).status_code == 409
    usage = client.get(path(ws, "usage")).json()
    assert usage["ai_reserved_minor"] == 0 and usage["ai_spent_minor"] == 5
    assert list(image_config.iterdir()) == []


def test_image_generation_checks_provider_rights_and_budget_before_enqueue(
    context, image_config, monkeypatch
):
    client, (ws, *_), _ = context
    body = {
        "prompt": "Synthetic illustration",
        "alt_text": "Synthetic workplace",
        "rights_confirmed": False,
    }
    assert client.post(path(ws, "social/images/generate"), json=body).status_code == 422
    client.put(path(ws, "usage/budget"), json={"ai_budget_minor": 4})
    assert (
        client.post(
            path(ws, "social/images/generate"), json=body | {"rights_confirmed": True}
        ).status_code
        == 402
    )
    assert client.get(path(ws, "jobs")).json()["total"] == 0
    monkeypatch.delenv("IMAGE_MODEL")
    requirements = client.get(path(ws, "social/images/requirements")).json()
    assert requirements["configured"] is False and "IMAGE_MODEL" in requirements["requirements"]
    assert (
        client.post(
            path(ws, "social/images/generate"), json=body | {"rights_confirmed": True}
        ).status_code
        == 503
    )


def test_center_crop_preserves_original_and_denies_other_workspace(context, image_config):
    client, (a, b, *_), _ = context
    original = client.post(
        path(a, "assets/upload"),
        files={"file": ("synthetic.png", png(40, 20), "image/png")},
        data={"alt_text": "Synthetic graphic", "rights_confirmed": "true"},
    ).json()
    assert (
        client.post(path(b, f"assets/{original['id']}/crop"), json={"crop": "square"}).status_code
        == 404
    )
    square = client.post(path(a, f"assets/{original['id']}/crop"), json={"crop": "square"})
    assert square.status_code == 201, square.text
    portrait = client.post(path(a, f"assets/{original['id']}/crop"), json={"crop": "portrait"})
    assert portrait.status_code == 201, portrait.text
    assert Image.open(io.BytesIO(client.get(square.json()["url"]).content)).size == (20, 20)
    assert Image.open(io.BytesIO(client.get(portrait.json()["url"]).content)).size == (16, 20)
    assert Image.open(io.BytesIO(client.get(original["url"]).content)).size == (40, 20)
    assert square.json()["id"] != original["id"]


def output(text, cost=100):
    return GenerationResult(
        text=text,
        citations=[],
        unverified_claims=["No independent source evidence"],
        model="synthetic-model",
        input_tokens=10,
        output_tokens=20,
        estimated_cost_microunits=cost,
    )


def test_three_real_social_variants_have_one_settlement_and_no_publish_side_effect(
    context, llm_config, monkeypatch
):
    client, (ws, *_), _ = context
    prompts = []

    def generate(prompt, sources):
        prompts.append(prompt)
        return output(
            f"Actual synthetic transport result {len(prompts)}\nQuestion {len(prompts)}?",
            100 * len(prompts),
        )

    monkeypatch.setattr("app.providers.ai.generate_text", generate)
    response = client.post(
        path(ws, "social/generate"),
        json={
            "topic": "Synthetic office quality",
            "audience": "Test offices",
            "tone": "Sachlich",
            "objective": "Wissen teilen",
            "post_type": "Praxistipp",
            "instructions": "Keine erfundenen Zahlen",
            "variants": 3,
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert client.get(path(ws, "usage")).json()["ai_reserved_minor"] >= 3
    assert execute_one(ws)
    result = client.get(path(ws, f"jobs/{job['id']}")).json()
    assert result["status"] == "succeeded" and len(prompts) == 3 and len(set(prompts)) == 3
    variants = result["result"]["variants"]
    assert [variant["text"] for variant in variants] == [
        f"Actual synthetic transport result {i}\nQuestion {i}?" for i in range(1, 4)
    ]
    assert result["result"]["verified"] is False and result["result"]["partial"] is False
    assert client.get(path(ws, "social/posts")).json()["total"] == 0
    usage = client.get(path(ws, "usage")).json()
    assert usage["ai_reserved_minor"] == 0 and usage["ai_spent_minor"] == 1
    with SessionLocal() as db:
        tenant(db, ws)
        events = list(db.scalars(select(UsageEvent).where(UsageEvent.job_id == job["id"])))
        assert len(events) == 1 and events[0].input_tokens == 30 and events[0].output_tokens == 60


def test_partial_paid_variants_remain_honest_and_cannot_be_retried_free(
    context, llm_config, monkeypatch
):
    client, (ws, *_), _ = context
    calls = []

    def generate(*_):
        calls.append(True)
        if len(calls) == 2:
            raise ProviderError("ambiguous_result", ambiguous=True)
        return output("Only completed provider variant\nReview it.")

    monkeypatch.setattr("app.providers.ai.generate_text", generate)
    job = client.post(path(ws, "social/generate"), json={"topic": "Synthetic topic"}).json()
    reserved = client.get(path(ws, "usage")).json()["ai_reserved_minor"]
    assert execute_one(ws)
    result = client.get(path(ws, f"jobs/{job['id']}")).json()
    assert result["status"] == "ambiguous" and len(calls) == 2
    assert result["result"]["partial"] is True and len(result["result"]["variants"]) == 1
    assert client.post(path(ws, f"jobs/{job['id']}/retry")).status_code == 409
    usage = client.get(path(ws, "usage")).json()
    assert usage["ai_reserved_minor"] == 0 and usage["ai_spent_minor"] == reserved


def test_social_cross_tenant_brand_does_not_reserve_or_generate(context, llm_config, monkeypatch):
    client, (a, b, *_), _ = context
    brand = client.post(path(b, "brands"), json={"name": "Other tenant brand"}).json()
    calls = []
    monkeypatch.setattr("app.providers.ai.generate_text", lambda *_: calls.append(True))
    result = client.post(
        path(a, "social/generate"), json={"topic": "Test topic", "brand_id": brand["id"]}
    )
    assert result.status_code == 404
    assert client.get(path(a, "usage")).json()["ai_reserved_minor"] == 0 and calls == []


def test_operational_home_uses_persisted_data_and_isolates_workspaces(context):
    client, (a, b, *_), _ = context
    lead = client.post(
        path(a, "contacts"),
        json={
            "first_name": "Synthetic",
            "last_name": "Qualified",
            "company": "Fictional office",
            "status": "qualified",
        },
    ).json()
    client.post(path(a, "tasks"), json={"title": "Actual next step", "contact_id": lead["id"]})
    client.post(
        path(a, "deals"),
        json={"title": "Actual test deal", "contact_id": lead["id"], "amount": 12345},
    )
    client.post(
        path(a, "campaigns"),
        json={"name": "Actual active campaign", "status": "active", "contact_ids": [lead["id"]]},
    )
    draft = client.post(path(a, "outreach/drafts"), json={"contact_id": lead["id"]}).json()
    client.patch(
        path(a, f"outreach/drafts/{draft['id']}"),
        json={"content": "Prepared text", "subject": "Prepared subject", "revision": 1},
    )
    result = client.get(path(a, "home"))
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["counts"]["contacts"] == 1 and data["counts"]["qualified"] == 1
    assert data["counts"]["pipeline_value"] == 12345 and data["counts"]["open_tasks"] == 1
    assert data["counts"]["pending_approvals"] == 1 and data["counts"]["active_campaigns"] == 1
    assert data["recent_leads"][0]["id"] == lead["id"]
    assert data["campaigns"][0]["audience_count"] == 1
    other = client.get(path(b, "home")).json()
    assert other["counts"]["contacts"] == 0 and other["recent_leads"] == [] and other["tasks"] == []


def test_onboarding_persistence_validation_and_read_only_role(context, admin):
    client, (a, b, *_), user = context
    body = {
        "business": "Synthetic B2B service",
        "region": "Offenburg",
        "target_customers": "Test offices",
        "completed_steps": ["business", "icp"],
    }
    result = client.put(path(a, "onboarding"), json=body)
    assert result.status_code == 200, result.text
    assert client.get(path(a, "onboarding")).json() == body
    assert client.get(path(b, "onboarding")).json()["business"] == ""
    assert (
        client.put(
            path(a, "onboarding"), json=body | {"completed_steps": ["invented_provider_success"]}
        ).status_code
        == 422
    )
    member = admin.get(Membership, (a, user))
    member.role = "analyst"
    admin.commit()
    assert client.get(path(a, "onboarding")).status_code == 200
    assert client.put(path(a, "onboarding"), json=body).status_code == 403


def test_manual_engagement_is_unverified_persistent_and_never_posts(context, monkeypatch):
    client, (a, b, *_), _ = context
    for key in ("LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    calls = []
    monkeypatch.setattr("app.providers.ai.generate_text", lambda *_: calls.append(True))
    response = client.post(
        path(a, "social/interactions"),
        json={
            "author": "Synthetic author",
            "content": "Manually supplied discussion",
            "post_url": "https://www.linkedin.com/feed/update/synthetic",
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["source"] == "manual"
    assert client.post(path(a, f"social/interactions/{item['id']}/suggest")).status_code == 503
    reviewed = client.patch(
        path(a, f"social/interactions/{item['id']}"),
        json={"status": "reviewed", "reply_draft": "Manually reviewed reply"},
    )
    assert reviewed.status_code == 200 and reviewed.json()["source"] == "manual"
    assert client.get(path(b, "social/interactions")).json()["total"] == 0
    assert (
        client.patch(
            path(b, f"social/interactions/{item['id']}"), json={"status": "reviewed"}
        ).status_code
        == 404
    )
    assert calls == [] and client.get(path(a, "jobs")).json()["total"] == 0


@pytest.mark.parametrize("kind", ["social_image", "social_text"])
def test_model_change_after_reservation_fails_before_paid_dispatch(
    context, image_config, llm_config, monkeypatch, kind
):
    client, (ws, *_), _ = context
    calls = []
    monkeypatch.setattr(OpenAIImages, "generate", lambda *_: calls.append(True))
    monkeypatch.setattr("app.providers.ai.generate_text", lambda *_: calls.append(True))
    if kind == "social_image":
        job = queue_image(client, ws)
        monkeypatch.setenv("IMAGE_MODEL", "changed-model")
    else:
        response = client.post(
            path(ws, "social/generate"), json={"topic": "Synthetic model drift proof"}
        )
        assert response.status_code == 202, response.text
        job = response.json()
        monkeypatch.setenv("LLM_MODEL", "changed-model")
    assert execute_one(ws)
    result = client.get(path(ws, f"jobs/{job['id']}")).json()
    assert result["status"] == "failed" and result["last_error"] == "provider_configuration_changed"
    assert calls == []
    usage = client.get(path(ws, "usage")).json()
    assert usage["ai_reserved_minor"] == 0 and usage["ai_spent_minor"] == 0


def test_provider_checks_report_missing_configuration_and_require_admin(
    context, admin, monkeypatch
):
    client, (ws, *_), user = context
    for key in (
        "LLM_API_KEY",
        "IMAGE_API_KEY",
        "IMAGE_MODEL",
        "STRIPE_SECRET_KEY",
        "PDL_API_KEY",
        "RESEND_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    for provider in ("llm", "images", "stripe", "discovery", "email", "linkedin"):
        response = client.post(path(ws, f"providers/{provider}/test"))
        assert response.status_code == 200, response.text
        assert response.json()["validated"] is False
    admin.get(Membership, (ws, user)).role = "analyst"
    admin.commit()
    assert client.post(path(ws, "providers/llm/test")).status_code == 403
    assert client.post(path(ws, "leads/query"), json={}).status_code == 200
