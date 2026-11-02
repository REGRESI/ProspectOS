"""Real PostgreSQL/RLS workflows; only the paid provider boundary is mocked."""

import io
import json

import httpx
import pytest
from PIL import Image
from sqlalchemy import select

from app.db import SessionLocal
from app.jobs import execute_one, tenant
from app.platform_models import Job
from app.providers.ai import GenerationResult
from app.providers.images import OpenAIImages
from app.studio import VoiceProfile


def path(ws, suffix):
    return f"/v1/workspaces/{ws}/{suffix}"


def voice(client, ws):
    response = client.post(
        path(ws, "social/voices"),
        json={
            "name": "Meine Stimme",
            "no_em_dash": True,
            "emoji": "keine",
            "examples": [
                {"label": "persönlich", "text": "Ich schaue zuerst auf die kleinen Dinge."}
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def image(client, ws, color="purple"):
    out = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(out, format="PNG")
    response = client.post(
        path(ws, "assets/upload"),
        files={"file": ("synthetic.png", out.getvalue(), "image/png")},
        data={"alt_text": "Synthetisches Testmotiv", "rights_confirmed": "true"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def text_provider(monkeypatch):
    for key, value in {
        "LLM_API_KEY": "synthetic",
        "LLM_MODEL": "synthetic",
        "LLM_INPUT_USD_PER_MILLION": "1",
        "LLM_OUTPUT_USD_PER_MILLION": "2",
    }.items():
        monkeypatch.setenv(key, value)
    calls = []

    def generate(prompt, sources):
        calls.append((prompt, sources))
        return GenerationResult(
            text=f"Idee {len(calls)} — mit Standpunkt 🚀\n\nEin konkreter Schritt.",
            citations=[s["id"] for s in sources],
            unverified_claims=[],
            model="synthetic",
            input_tokens=40,
            output_tokens=30,
            estimated_cost_microunits=100,
        )

    monkeypatch.setattr("app.providers.ai.generate_text", generate)
    return calls


def test_voice_crud_examples_concurrency_export_and_rls(context):
    client, (a, b, outside), _ = context
    profile = voice(client, a)
    assert (
        client.get(path(a, "social/voices")).json()["items"][0]["examples"][0]["label"]
        == "persönlich"
    )
    assert client.get(path(b, "social/voices")).json()["items"] == []
    assert client.get(path(outside, "social/voices")).status_code == 404
    data = {k: v for k, v in profile.items() if k not in ("id", "created_at")}
    data["name"] = "Überarbeitete Stimme"
    assert client.put(path(b, f"social/voices/{profile['id']}"), json=data).status_code == 404
    changed = client.put(path(a, f"social/voices/{profile['id']}"), json=data)
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert client.put(path(a, f"social/voices/{profile['id']}"), json=data).status_code == 409
    assert (
        client.post(path(a, "privacy/export")).json()["data"]["voice_profiles"][0]["name"]
        == data["name"]
    )
    assert client.delete(path(b, f"social/voices/{profile['id']}")).status_code == 404
    with SessionLocal() as db:
        assert db.scalars(select(VoiceProfile)).all() == []
        tenant(db, b)
        assert db.get(VoiceProfile, profile["id"]) is None
    assert client.delete(path(a, f"social/voices/{profile['id']}")).status_code == 200
    assert client.get(path(a, "social/voices")).json()["items"] == []


def test_variants_snapshot_grounding_constraints_and_persistent_history(context, text_provider):
    client, (a, b, *_), _ = context
    profile = voice(client, a)
    body = {
        "topic": "Kleine Schritte im Team",
        "voice_profile_id": profile["id"],
        "business_context": "Unser Team",
        "length": "kurz",
        "factual_notes": "Wir sind drei Autoren.",
        "emoji": "keine",
        "end_question": False,
    }
    assert client.post(path(b, "social/generate"), json=body).status_code == 404
    queued = client.post(path(a, "social/generate"), json=body)
    assert queued.status_code == 202, queued.text
    job_id = queued.json()["id"]
    client.delete(path(a, f"social/voices/{profile['id']}"))
    assert execute_one(a)
    result = client.get(path(a, f"jobs/{job_id}")).json()
    assert result["status"] == "succeeded", result
    variants = result["result"]["variants"]
    assert len(variants) == 3 and len({v["text"] for v in variants}) == 3
    assert all("—" not in v["text"] and "🚀" not in v["text"] for v in variants)
    assert len({v["angle"] for v in variants}) == 3
    assert all(
        "nicht kopieren" in prompt and "Meine Stimme" in prompt for prompt, _ in text_provider
    )
    assert all(
        sources == [{"id": "user_facts", "text": "Wir sind drei Autoren."}]
        for _, sources in text_provider
    )
    with SessionLocal() as db:
        tenant(db, a)
        job = db.get(Job, job_id)
        assert job.payload["voice_snapshot"]["version"] == 1
        assert job.payload["parameters"]["end_question"] is False
        assert "synthetic" not in json.dumps(job.payload)
    assert (
        client.get(path(a, "social/generations")).json()["items"][0]["voice_name"] == "Meine Stimme"
    )
    assert client.get(path(b, "social/generations")).json()["items"] == []


def test_refine_compare_save_revisions_duplicate_archive(context, text_provider):
    client, (a, b, *_), _ = context
    profile = voice(client, a)
    original = "Ein kleiner Schritt kann ein guter Anfang sein."
    post = client.post(path(a, "social/posts"), json={"caption": original}).json()
    body = {
        "text": original,
        "action": "menschlicher",
        "voice_profile_id": profile["id"],
        "factual_notes": "Wir planen wöchentlich.",
        "banned_elements": "kein Gedankenstrich",
    }
    assert client.post(path(b, "social/refine"), json=body).status_code == 404
    assert (
        client.post(path(a, "social/refine"), json=body | {"action": "publish"}).status_code == 422
    )
    queued = client.post(path(a, "social/refine"), json=body).json()
    assert execute_one(a)
    result = client.get(path(a, f"jobs/{queued['id']}")).json()
    assert result["status"] == "succeeded" and len(text_provider) == 1
    revised = result["result"]["variants"][0]["text"]
    history = client.get(path(a, "social/generations")).json()["items"][0]
    assert history["original"] == original and history["action"] == "menschlicher"
    followup = {"text": revised, "action": "direkter", "parent_job_id": queued["id"]}
    assert client.post(path(b, "social/refine"), json=followup).status_code == 404
    followup_job = client.post(path(a, "social/refine"), json=followup)
    assert followup_job.status_code == 202, followup_job.text
    assert execute_one(a)
    assert text_provider[1][1] == [{"id": "user_facts", "text": "Wir planen wöchentlich."}]
    with SessionLocal() as db:
        tenant(db, a)
        inherited = db.get(Job, followup_job.json()["id"])
        assert inherited.payload["parameters"]["banned_elements"] == "kein Gedankenstrich"
        assert inherited.payload["voice_snapshot"]["id"] == profile["id"]

    assert client.get(path(a, "social/posts")).json()["items"][0]["caption"] == original
    patch = {
        "caption": revised,
        "version": 1,
        "studio_context": {"voice_profile_id": profile["id"], "generation_job_id": queued["id"]},
    }
    assert client.patch(path(a, f"social/posts/{post['id']}"), json=patch).status_code == 200
    assert client.patch(path(a, f"social/posts/{post['id']}"), json=patch).status_code == 409
    revisions = client.get(path(a, f"social/posts/{post['id']}/revisions")).json()["items"]
    assert [r["snapshot"]["caption"] for r in revisions] == [revised, original]
    assert revisions[0]["snapshot"]["studio_context"]["generation_job_id"] == queued["id"]
    assert client.post(path(b, f"social/posts/{post['id']}/duplicate")).status_code == 404
    copied = client.post(path(a, f"social/posts/{post['id']}/duplicate"))
    assert copied.status_code == 201 and copied.json()["state"] == "draft"
    assert copied.json()["version"] == 1 and copied.json()["publish_enabled"] is False
    assert (
        client.post(
            path(b, "social/posts"),
            json={
                "caption": "Foreign job rejected",
                "studio_context": {"generation_job_id": queued["id"]},
            },
        ).status_code
        == 404
    )
    client.delete(path(a, f"social/voices/{profile['id']}"))
    # Deleting a reusable profile must not make an existing draft uneditable.
    assert (
        client.patch(path(a, f"social/posts/{post['id']}"), json=patch | {"version": 2}).status_code
        == 200
    )
    archived = client.post(path(a, f"social/posts/{post['id']}/archive"))
    assert archived.status_code == 200 and archived.json()["state"] == "archived"
    assert not archived.json()["publish_enabled"] and archived.json()["scheduled_at"] is None


def test_gallery_metadata_manual_auto_random_and_isolation(context):
    client, (a, b, *_), user = context
    first, second = image(client, a), image(client, a, "green")
    foreign = image(client, b, "blue")
    metadata = {
        "title": "Team Werkstatt",
        "description": "Planung im Team",
        "alt_text": "Synthetische Teamillustration",
        "tags": ["Team", "Planung"],
        "rights_note": "Synthetischer Test",
    }
    assert client.patch(path(b, f"assets/{first['id']}/metadata"), json=metadata).status_code == 404
    updated = client.patch(path(a, f"assets/{first['id']}/metadata"), json=metadata)
    assert updated.status_code == 200 and updated.json()["uploaded_by"] == user
    selected = client.post(
        path(a, "social/media/select"), json={"mode": "auto", "topic": "Planung im Team"}
    )
    assert selected.status_code == 200 and selected.json()["asset"]["id"] == first["id"]
    assert "gemeinsame Begriffe" in selected.json()["reason"]
    fallback = client.post(
        path(a, "social/media/select"), json={"mode": "auto", "topic": "xyzabcdef"}
    ).json()
    assert "Keine passenden Metadaten" in fallback["reason"]
    for _ in range(5):
        choice = client.post(path(a, "social/media/select"), json={"mode": "random"}).json()
        assert choice["asset"]["id"] in {first["id"], second["id"]}
        assert choice["asset"]["id"] != foreign["id"]
    body = {
        "caption": "Mein Beitrag",
        "asset_ids": [first["id"]],
        "studio_context": {"image_mode": "auto"},
    }
    created = client.post(path(a, "social/posts"), json=body)
    assert created.status_code == 201 and created.json()["studio_context"]["image_mode"] == "auto"
    assert client.post(path(b, "social/posts"), json=body).status_code == 404
    assert client.get(path(b, f"assets/{first['id']}/content")).status_code == 404


def test_empty_gallery_and_missing_credentials_never_create_success(context, monkeypatch):
    client, (a, *_), _ = context
    assert client.post(path(a, "social/media/select"), json={"mode": "random"}).status_code == 404
    for key in ("LLM_API_KEY", "LLM_MODEL", "IMAGE_API_KEY", "IMAGE_MODEL"):
        monkeypatch.delenv(key, raising=False)
    for route, body in (
        ("social/generate", {"topic": "Ein echtes Thema"}),
        ("social/refine", {"text": "Original bleibt erhalten", "action": "kürzer"}),
        (
            "social/images/generate",
            {
                "prompt": "Synthetische Illustration",
                "alt_text": "Beispiel",
                "rights_confirmed": True,
            },
        ),
    ):
        response = client.post(path(a, route), json=body)
        assert response.status_code == 503 and "konfigurieren" in response.text
    assert client.get(path(a, "social/generations")).json()["items"] == []
    assert client.get(path(a, "assets")).json()["items"] == []


def test_landscape_generation_stored_and_reviewed_before_gallery(context, monkeypatch, tmp_path):
    import base64

    client, (a, *_), user = context
    for key, value in {
        "IMAGE_API_KEY": "synthetic-key",
        "IMAGE_MODEL": "synthetic-image",
        "IMAGE_MAX_COST_USD_CENTS": "5",
        "ASSET_ROOT": str(tmp_path),
    }.items():
        monkeypatch.setenv(key, value)
    original_generate, requests = OpenAIImages.generate, []
    out = io.BytesIO()
    Image.new("RGB", (48, 32), "purple").save(out, format="PNG")

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json={"data": [{"b64_json": base64.b64encode(out.getvalue()).decode()}]}
        )

    def generate(self, prompt, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
            return original_generate(self, prompt, client=transport, **kwargs)

    monkeypatch.setattr(OpenAIImages, "generate", generate)
    queued = client.post(
        path(a, "social/images/generate"),
        json={
            "prompt": "Editorial Team Illustration",
            "alt_text": "Synthetisches Team",
            "rights_confirmed": True,
            "style": "Editorial",
            "mood": "ruhig",
            "aspect_ratio": "landscape",
            "post_context": "Zusammenarbeit",
        },
    )
    assert queued.status_code == 202, queued.text
    assert execute_one(a)
    result = client.get(path(a, f"jobs/{queued.json()['id']}")).json()
    assert result["status"] == "succeeded", result
    assert requests[0]["size"] == "1536x1024" and "No typography" in requests[0]["prompt"]
    assert result["result"]["asset"]["uploaded_by"] == user
    assert result["result"]["review_required"] is True
    assert client.post(path(a, "social/media/select"), json={"mode": "auto"}).status_code == 404
    assert (
        client.post(
            path(a, f"social/images/{queued.json()['id']}/save"), json={"rights_confirmed": True}
        ).status_code
        == 200
    )
    assert (
        client.post(path(a, "social/media/select"), json={"mode": "random"}).json()["asset"]["id"]
        == result["result"]["asset"]["id"]
    )
