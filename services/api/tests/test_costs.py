"""Actual cost vs. reservation: the ledger books what the provider's usage field says,
priced with the configured table; the cap is only held while the call runs. Old
bookings are corrected from stored tokens or flagged as estimated. Provider transports
are mocked; nothing paid is called. All data synthetic."""

import base64
import io
import json

import pytest
from PIL import Image
from sqlalchemy import select

from app import costs
from app.db import SessionLocal
from app.jobs import execute_one, tenant
from app.platform_models import UsageAccount, UsageEvent


def path(ws, suffix):
    return f"/v1/workspaces/{ws}/{suffix}"


def jpeg():
    out = io.BytesIO()
    Image.new("RGB", (16, 16), "#335").save(out, format="JPEG")
    return out.getvalue()


@pytest.fixture
def priced(monkeypatch, tmp_path):
    for k, v in {
        "LLM_API_KEY": "synthetic-test-key",
        "LLM_MODEL": "synthetic-text-model",
        "LLM_INPUT_USD_PER_MILLION": "0.40",
        "LLM_OUTPUT_USD_PER_MILLION": "1.60",
        "LLM_MAX_OUTPUT_TOKENS": "1500",
        "IMAGE_MODEL": "synthetic-image-model",
        "IMAGE_MAX_COST_USD_CENTS": "100",
        "IMAGE_TEXT_INPUT_USD_PER_MILLION": "5",
        "IMAGE_IMAGE_INPUT_USD_PER_MILLION": "8",
        "IMAGE_OUTPUT_USD_PER_MILLION": "30",
        "ASSET_ROOT": str(tmp_path),
    }.items():
        monkeypatch.setenv(k, v)


def fake_transport(monkeypatch, sent):
    def text_response(method, url, **kwargs):
        sent.append(url)
        if url.endswith("/images/generations"):
            return {
                "data": [{"b64_json": base64.b64encode(jpeg()).decode()}],
                "size": "1024x1024",
                "quality": "medium",
                "usage": {
                    "input_tokens": 50,
                    "input_tokens_details": {"text_tokens": 50, "image_tokens": 0},
                    "output_tokens": 439,
                    "total_tokens": 489,
                },
            }, None
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"text": "Kurzer Entwurf.", "citations": [], "unverified_claims": []}
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 812, "completion_tokens": 143},
        }, None

    monkeypatch.setattr("app.providers.ai.request_json", text_response)
    monkeypatch.setattr("app.providers.images.request_json", text_response)


def events(ws):
    with SessionLocal() as db:
        tenant(db, ws)
        return {e.job_id: e for e in db.scalars(select(UsageEvent))}


def test_text_and_image_book_actual_cost_not_reservation(context, priced, monkeypatch):
    client, (ws, *_), _ = context
    sent = []
    fake_transport(monkeypatch, sent)

    text_job = client.post(
        path(ws, "ai/generate"), json={"prompt": "Entwurf", "purpose": "caption"}
    )
    assert text_job.status_code == 202, text_job.text
    reserved = client.get(path(ws, "usage")).json()
    assert reserved["ai_reserved_minor"] > 0 and reserved["spent_usd"] == 0
    assert execute_one(ws)

    image_job = client.post(
        path(ws, "social/images/generate"),
        json={"prompt": "Synthetic office", "alt_text": "Synthetic", "rights_confirmed": True},
    )
    assert image_job.status_code == 202, image_job.text
    assert client.get(path(ws, "usage")).json()["reserved_usd"] == 1.0
    assert execute_one(ws)
    assert len(sent) == 2

    booked = events(ws)
    text = booked[text_job.json()["id"]]
    # 812 * 0.40 + 143 * 1.60 = 324.8 + 228.8 = 553.6 -> 554 micro-USD
    assert (text.input_tokens, text.output_tokens) == (812, 143)
    assert text.cost_micro == 554 and not text.estimated and text.model == "synthetic-text-model"
    image = booked[image_job.json()["id"]]
    # 50 * 5 + 439 * 30 = 250 + 13170 = 13420 micro-USD, not the 1 USD cap
    assert image.cost_micro == 13420 and not image.estimated and image.reserved_minor == 100
    assert image.details["usage"]["quality"] == "medium"

    usage = client.get(path(ws, "usage")).json()
    assert usage["ai_reserved_minor"] == 0 and usage["reserved_usd"] == 0
    assert usage["spent_usd"] == pytest.approx((554 + 13420) / 1e6)
    assert usage["spent_estimated_usd"] == 0
    assert usage["ai_spent_minor"] == 2  # rounded-up mirror only
    listed = client.get(path(ws, "usage/events")).json()["items"]
    assert {i["cost_usd"] for i in listed} == {554 / 1e6, 13420 / 1e6}


def test_image_without_usage_books_reservation_as_estimated(context, priced, monkeypatch):
    client, (ws, *_), _ = context
    monkeypatch.setattr(
        "app.providers.images.request_json",
        lambda *a, **k: ({"data": [{"b64_json": base64.b64encode(jpeg()).decode()}]}, None),
    )
    job = client.post(
        path(ws, "social/images/generate"),
        json={"prompt": "Synthetic office", "alt_text": "Synthetic", "rights_confirmed": True},
    ).json()
    assert execute_one(ws)
    event = events(ws)[job["id"]]
    assert event.estimated and event.cost_micro == 100 * 10_000
    assert client.get(path(ws, "usage")).json()["spent_estimated_usd"] == 1.0


def test_old_bookings_are_corrected_or_flagged(context, priced, monkeypatch):
    client, (ws, *_), _ = context
    sent = []
    fake_transport(monkeypatch, sent)
    text_job = client.post(
        path(ws, "ai/generate"), json={"prompt": "Entwurf", "purpose": "caption"}
    )
    assert execute_one(ws)
    image_job = client.post(
        path(ws, "social/images/generate"),
        json={"prompt": "Synthetic office", "alt_text": "Synthetic", "rights_confirmed": True},
    ).json()
    assert execute_one(ws)
    # Simulate the old ledger: whole cents and the image cap, no usage stored.
    with SessionLocal() as db, db.begin():
        tenant(db, ws)
        for e in db.scalars(select(UsageEvent)):
            old = 1 if e.provider == "openai_compatible" else 100
            e.cost_minor, e.cost_micro, e.estimated, e.details = old, old * 10_000, True, {}
        account = db.scalar(select(UsageAccount).where(UsageAccount.workspace_id == ws))
        account.ai_spent_micro, account.ai_spent_minor = 101 * 10_000, 101
    with SessionLocal() as db, db.begin():
        tenant(db, ws)
        preview = costs.recalc_workspace(db, ws)
        assert preview["old_micro"] == 101 * 10_000
        result = costs.recalc_workspace(db, ws, apply=True)
    booked = events(ws)
    text = booked[text_job.json()["id"]]
    assert text.cost_micro == 554 and not text.estimated  # tokens were stored: exact
    image = booked[image_job["id"]]
    assert image.estimated and image.cost_micro == 5880  # no usage: table estimate
    assert result["new_micro"] == 554 + 5880
    usage = client.get(path(ws, "usage")).json()
    assert usage["spent_usd"] == pytest.approx((554 + 5880) / 1e6)
    assert usage["spent_estimated_usd"] == pytest.approx(5880 / 1e6)


def test_budget_counts_actual_spend_only(context, priced, monkeypatch):
    client, (ws, *_), _ = context
    fake_transport(monkeypatch, [])
    client.put(path(ws, "usage/budget"), json={"ai_budget_minor": 150})
    for _ in range(3):
        job = client.post(
            path(ws, "social/images/generate"),
            json={"prompt": "Synthetic office", "alt_text": "Synthetic", "rights_confirmed": True},
        )
        # Each reservation is 1 USD but only ~1.3 ct is booked, so the budget is not used up.
        assert job.status_code == 202, job.text
        assert execute_one(ws)
    usage = client.get(path(ws, "usage")).json()
    assert usage["spent_usd"] < 0.05 and usage["available_usd"] > 1.4
