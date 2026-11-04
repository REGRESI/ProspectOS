"""Integrations page: encrypted per-workspace credentials, masking, tenant isolation, tests.
All provider responses are transport-mocked; values below are synthetic test strings."""

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app import credentials
from app.integrations import check_linkedin_app, check_openai
from app.platform_models import IntegrationCredential

SYNTHETIC_KEY = "sk-synthetic-test-key-000000001234"


@pytest.fixture
def fernet(monkeypatch):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())


def test_save_masks_encrypts_and_isolates(context, admin, fernet, monkeypatch):
    c, (ws, other, foreign), _ = context
    import app.integrations as integrations

    monkeypatch.setitem(integrations.TESTS, "brave", lambda client=None: {"detail": "ok"})
    r = c.put(
        f"/v1/workspaces/{ws}/integrations/credentials/brave",
        json={"values": {"BRAVE_SEARCH_API_KEY": SYNTHETIC_KEY}},
    )
    assert r.status_code == 200, r.text
    assert SYNTHETIC_KEY not in r.text
    item = r.json()["item"]
    assert item["status"] == "connected"
    assert item["fields"][0]["masked"] == "••••1234"
    assert item["fields"][0]["source"] == "workspace"
    listing = c.get(f"/v1/workspaces/{ws}/integrations/credentials")
    assert SYNTHETIC_KEY not in listing.text
    row = admin.scalar(
        select(IntegrationCredential).where(IntegrationCredential.workspace_id == ws)
    )
    assert SYNTHETIC_KEY not in row.ciphertext
    # Second workspace of the same user does not see the value.
    brave = next(
        i
        for i in c.get(f"/v1/workspaces/{other}/integrations/credentials").json()["items"]
        if i["provider"] == "brave"
    )
    assert brave["status"] == "missing"
    # Forged workspace the user is not a member of.
    assert c.get(f"/v1/workspaces/{foreign}/integrations/credentials").status_code == 404
    assert (
        c.put(
            f"/v1/workspaces/{foreign}/integrations/credentials/brave",
            json={"values": {"BRAVE_SEARCH_API_KEY": "x" * 20}},
        ).status_code
        == 404
    )
    # Unknown provider/field is rejected.
    assert c.put(f"/v1/workspaces/{ws}/integrations/credentials/nope", json={}).status_code == 404
    assert (
        c.put(
            f"/v1/workspaces/{ws}/integrations/credentials/brave",
            json={"values": {"LLM_API_KEY": "x"}},
        ).status_code
        == 422
    )
    # Delete restores env fallback / missing.
    assert (
        c.delete(f"/v1/workspaces/{ws}/integrations/credentials/brave").json()["item"]["status"]
        == "missing"
    )


def test_requires_encryption_key_and_owner(context, admin):
    c, (ws, *_), user_id = context
    r = c.put(
        f"/v1/workspaces/{ws}/integrations/credentials/brave",
        json={"values": {"BRAVE_SEARCH_API_KEY": SYNTHETIC_KEY}},
    )
    assert r.status_code == 503
    from app.models import Membership

    member = admin.get(Membership, (ws, user_id))
    member.role = "editor"
    admin.commit()
    assert c.get(f"/v1/workspaces/{ws}/integrations/credentials").status_code == 403


def test_workspace_value_overrides_environment_in_request_and_worker(
    context, admin, fernet, monkeypatch
):
    c, (ws, *_), _ = context
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "env-value-should-lose-9999")
    seen = []

    def fake(client=None):
        seen.append(credentials.get("BRAVE_SEARCH_API_KEY"))
        return {"detail": "ok"}

    import app.integrations as integrations

    monkeypatch.setitem(integrations.TESTS, "brave", fake)
    listing = c.get(f"/v1/workspaces/{ws}/integrations/credentials").json()["items"]
    assert (
        next(i for i in listing if i["provider"] == "brave")["fields"][0]["source"] == "environment"
    )
    c.put(
        f"/v1/workspaces/{ws}/integrations/credentials/brave",
        json={"values": {"BRAVE_SEARCH_API_KEY": SYNTHETIC_KEY}},
    )
    c.post(f"/v1/workspaces/{ws}/integrations/credentials/brave/test")
    assert seen == [SYNTHETIC_KEY, SYNTHETIC_KEY]
    # Worker-style binding resolves the same value lazily, environment without binding.
    token = credentials.bind(ws)
    try:
        assert credentials.get("BRAVE_SEARCH_API_KEY") == SYNTHETIC_KEY
    finally:
        credentials.unbind(token)
    assert credentials.get("BRAVE_SEARCH_API_KEY") == "env-value-should-lose-9999"


def test_failed_test_reports_error_without_secret(context, fernet):
    c, (ws, *_), _ = context

    def handler(request):
        assert request.headers["authorization"] == "Bearer " + SYNTHETIC_KEY
        return httpx.Response(401, json={"error": {"message": "bad key " + SYNTHETIC_KEY}})

    import app.integrations as integrations

    original = integrations.TESTS["openai"]
    integrations.TESTS["openai"] = lambda client=None: original(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    try:
        r = c.put(
            f"/v1/workspaces/{ws}/integrations/credentials/openai",
            json={
                "values": {
                    "LLM_API_KEY": SYNTHETIC_KEY,
                    "LLM_MODEL": "gpt-test",
                    "LLM_INPUT_USD_PER_MILLION": "0.4",
                    "LLM_OUTPUT_USD_PER_MILLION": "1.6",
                }
            },
        )
    finally:
        integrations.TESTS["openai"] = original
    assert r.status_code == 200
    assert r.json()["item"]["status"] == "error"
    assert r.json()["test"]["error"] == "provider_forbidden"
    assert SYNTHETIC_KEY not in r.text


def test_openai_checks_text_and_image_models(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("LLM_MODEL", "gpt-text")
    monkeypatch.setenv("IMAGE_MODEL", "gpt-image")
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"id": request.url.path.rsplit("/", 1)[1]})

    result = check_openai(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert paths == ["/v1/models/gpt-text", "/v1/models/gpt-image"]
    assert "gpt-image" in result["detail"]


@pytest.mark.parametrize(
    ("status", "body", "ok"),
    [(400, {"error": "invalid_request"}, True), (401, {"error": "invalid_client"}, False)],
)
def test_linkedin_app_credentials_probe(monkeypatch, status, body, ok):
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setenv(
        "LINKEDIN_REDIRECT_URI", "http://localhost:3000/v1/integrations/linkedin/callback"
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body))
    )
    if ok:
        assert "akzeptiert" in check_linkedin_app(client=client)["detail"]
    else:
        from app.providers.ai import ProviderError

        with pytest.raises(ProviderError):
            check_linkedin_app(client=client)
