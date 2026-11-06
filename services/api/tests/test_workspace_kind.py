"""Production vs. demo workspaces: default order, demo isolation from real providers,
and in-place promotion of a demo workspace that already holds real work.
All data is synthetic."""

from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import credentials
from app.models import Company, Contact, Membership, User, Workspace
from tests.conftest import admin_engine


@pytest.fixture
def kinds(context):
    c, (ws, other, _), _ = context
    with Session(admin_engine) as db, db.begin():
        db.get(Workspace, ws).kind = "demo"
        db.get(Workspace, other).kind = "production"
    return c, ws, other


def test_production_listed_first_with_kind(kinds):
    c, demo, prod = kinds
    items = c.get("/v1/me").json()["workspaces"]
    assert [w["id"] for w in items] == [prod, demo]
    assert [w["kind"] for w in items] == ["production", "demo"]


def test_demo_workspace_never_uses_real_credentials(kinds, monkeypatch):
    c, demo, prod = kinds
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "synthetic-env-brave-key-0000")
    with Session(admin_engine) as db:
        with credentials.workspace(db, demo):
            assert credentials.get("BRAVE_SEARCH_API_KEY") == ""
            assert credentials.source("BRAVE_SEARCH_API_KEY") == "missing"
        with credentials.workspace(db, prod):
            assert credentials.get("BRAVE_SEARCH_API_KEY") == "synthetic-env-brave-key-0000"
    r = c.put(
        f"/v1/workspaces/{demo}/integrations/credentials/brave",
        json={"values": {"BRAVE_SEARCH_API_KEY": "x" * 24}},
    )
    assert r.status_code == 409 and "Demo-Workspace" in r.text
    assert c.post(f"/v1/workspaces/{demo}/integrations/credentials/brave/test").status_code == 409
    assert c.post(f"/v1/workspaces/{demo}/integrations/linkedin/start").status_code == 409
    listing = c.get(f"/v1/workspaces/{demo}/integrations/credentials").json()["items"]
    assert next(i for i in listing if i["provider"] == "brave")["status"] == "missing"


def test_promotes_demo_with_real_work_and_removes_synthetic_rows():
    from app.seed import ensure_production

    marker = uuid4().hex[:8]
    with Session(admin_engine) as db, db.begin():
        # Park existing seed workspaces under other slugs; everything is rolled back.
        moved = []
        for slug in ("cleanstar", "cleanstar-demo"):
            existing = db.scalar(select(Workspace).where(Workspace.slug == slug))
            if existing:
                existing.slug = f"{slug}-parked-{marker}"
                moved.append((existing, slug))
        db.flush()
        user = User(email=f"{marker}@example.test", name="T", password_hash="x")
        db.add(user)
        db.flush()
        ws = Workspace(name="CleanStar · Demo", slug="cleanstar-demo", kind="demo")
        db.add(ws)
        db.flush()
        db.add(Membership(workspace_id=ws.id, user_id=user.id, role="owner"))
        real = Company(
            workspace_id=ws.id,
            name="Synthetische Kanzlei OSM",
            identity=f"osm-{marker}",
            location="Offenburg",
            industry="Rechtsberatung",
            source="openstreetmap",
        )
        fake = Company(
            workspace_id=ws.id,
            name="Demo Werkraum",
            identity=f"seed-{marker}",
            location="Lahr",
            industry="",
            source="synthetic_demo",
        )
        db.add_all([real, fake])
        db.flush()
        db.add(
            Contact(
                workspace_id=ws.id,
                company_id=fake.id,
                first_name="Emil",
                last_name="Test",
                source="synthetic_demo",
            )
        )
        db.flush()
        assert ensure_production(db, user) == "promoted"
        assert (ws.name, ws.slug, ws.kind) == ("CleanStar", "cleanstar", "production")
        names = set(db.scalars(select(Company.name).where(Company.workspace_id == ws.id)))
        assert names == {"Synthetische Kanzlei OSM"}
        assert not db.scalars(select(Contact).where(Contact.workspace_id == ws.id)).all()
        assert ensure_production(db, user) == "kept"
        db.rollback()


def test_creates_empty_production_workspace_when_no_real_work():
    from app.seed import ensure_production

    marker = uuid4().hex[:8]
    with Session(admin_engine) as db:
        for slug in ("cleanstar", "cleanstar-demo"):
            existing = db.scalar(select(Workspace).where(Workspace.slug == slug))
            if existing:
                existing.slug = f"{slug}-parked-{marker}"
        db.flush()
        user = User(email=f"{marker}@example.test", name="T", password_hash="x")
        db.add(user)
        db.flush()
        assert ensure_production(db, user) == "created"
        prod = db.scalar(select(Workspace).where(Workspace.slug == "cleanstar"))
        assert prod.kind == "production"
        assert db.get(Membership, (prod.id, user.id)).role == "owner"
        db.rollback()
