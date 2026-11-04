import os
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from app.main import app, login_attempts
from app.models import Base, Membership, User, Workspace

ADMIN_URL = os.getenv(
    "DATABASE_ADMIN_URL", "postgresql+psycopg://prospectos:prospectos_dev@127.0.0.1:5432/prospectos"
)
admin_engine = create_engine(ADMIN_URL)


@pytest.fixture
def context():
    marker = str(uuid4())
    with Session(admin_engine) as db, db.begin():
        user = User(
            email=f"{marker}@example.test",
            name="Test User",
            password_hash=PasswordHasher().hash("TestPassword!2026"),
        )
        db.add(user)
        db.flush()
        workspaces = [Workspace(name=f"Test {i}", slug=f"test-{marker}-{i}") for i in range(3)]
        db.add_all(workspaces)
        db.flush()
        user_id = user.id
        ids = [w.id for w in workspaces]
        for ws in ids[:2]:
            db.add(Membership(user_id=user.id, workspace_id=ws, role="owner"))
        email = user.email
    login_attempts.clear()
    with TestClient(app) as client:
        result = client.post(
            "/v1/auth/demo", json={"email": email, "password": "TestPassword!2026"}
        )
        assert result.status_code == 200, result.text
        client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
        yield client, ids, user_id
    with Session(admin_engine) as db, db.begin():
        for table in reversed(Base.metadata.sorted_tables):
            if "workspace_id" in table.c:
                db.execute(delete(table).where(table.c.workspace_id.in_(ids)))
        db.execute(delete(Workspace).where(Workspace.id.in_(ids)))
        from app.models import AuthSession

        db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
        db.execute(delete(User).where(User.id == user_id))


@pytest.fixture
def admin():
    with Session(admin_engine) as db:
        yield db
        db.rollback()


def scoped(db, ws):
    from sqlalchemy import text

    db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})


PROVIDER_ENV = [
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_BASE_URL",
    "LLM_INPUT_USD_PER_MILLION",
    "LLM_OUTPUT_USD_PER_MILLION",
    "LLM_MAX_OUTPUT_TOKENS",
    "IMAGE_API_KEY",
    "IMAGE_MODEL",
    "IMAGE_BASE_URL",
    "IMAGE_MAX_COST_USD_CENTS",
    "LINKEDIN_CLIENT_ID",
    "LINKEDIN_CLIENT_SECRET",
    "LINKEDIN_REDIRECT_URI",
    "LINKEDIN_API_VERSION",
    "LINKEDIN_PUBLISHING_APPROVED",
    "BRAVE_SEARCH_API_KEY",
    "OSM_DISCOVERY_ENABLED",
    "OSM_CONTACT",
    "NORTHDATA_API_KEY",
    "NORTHDATA_ENABLED",
    "NORTHDATA_LICENSE_APPROVED",
    "PDL_API_KEY",
    "PDL_LICENSE_APPROVED",
    "RESEARCH_TERMS_APPROVED",
    "RESEARCH_NETWORK_GUARD_APPROVED",
    "EMAIL_SEND_ENABLED",
    "RESEND_API_KEY",
    "STRIPE_SECRET_KEY",
    "TOKEN_ENCRYPTION_KEY",
    "AUTH_PROVIDER",
]


def pytest_configure(config):
    # Hermetic tests: never inherit real provider credentials or operator switches from a
    # developer .env. Runs once (tests import this module again as tests.conftest).
    for name in PROVIDER_ENV:
        os.environ.pop(name, None)
