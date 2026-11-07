"""Workspace lifecycle: rename, archive, delete with all data. Deleting needs the owner,
the exact name, and is refused for the open and the last workspace; the purge only acts
on the bound tenant. All data synthetic."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Audit, Company, Membership, Workspace
from tests.conftest import admin_engine


def test_rename_and_archive(context):
    client, (ws, other, foreign), _ = context
    r = client.patch(f"/v1/workspaces/{ws}", json={"name": "Umbenannt GmbH"})
    assert r.status_code == 200 and r.json()["name"] == "Umbenannt GmbH"
    assert client.patch(f"/v1/workspaces/{foreign}", json={"name": "x" * 5}).status_code == 404
    # The open workspace cannot be archived.
    refused = client.post(
        f"/v1/workspaces/{other}/archive", json={"archived": True, "active_workspace_id": other}
    )
    assert refused.status_code == 409
    ok = client.post(
        f"/v1/workspaces/{other}/archive", json={"archived": True, "active_workspace_id": ws}
    )
    assert ok.status_code == 200 and ok.json()["archived"]
    listed = client.get("/v1/workspaces").json()["items"]
    assert listed[-1]["id"] == other and listed[-1]["archived"]
    # Last active workspace cannot be archived.
    assert (
        client.post(
            f"/v1/workspaces/{ws}/archive", json={"archived": True, "active_workspace_id": other}
        ).status_code
        == 409
    )
    back = client.post(f"/v1/workspaces/{other}/archive", json={"archived": False})
    assert back.status_code == 200 and not back.json()["archived"]


def test_delete_requires_name_not_active_not_last(context):
    client, (ws, other, foreign), user = context
    with Session(admin_engine) as db, db.begin():
        db.add(Company(workspace_id=other, name="Synthetische Firma", identity="synthetic:1"))
        db.add(Audit(workspace_id=other, actor_id=user, kind="x", description="synthetic"))
    name = client.get("/v1/workspaces").json()["items"]
    target = next(w for w in name if w["id"] == other)["name"]
    wrong = client.request(
        "DELETE",
        f"/v1/workspaces/{other}",
        json={"confirm_name": "falsch", "active_workspace_id": ws},
    )
    assert wrong.status_code == 422
    active = client.request(
        "DELETE",
        f"/v1/workspaces/{other}",
        json={"confirm_name": target, "active_workspace_id": other},
    )
    assert active.status_code == 409
    assert (
        client.request(
            "DELETE",
            f"/v1/workspaces/{foreign}",
            json={"confirm_name": "Test 2", "active_workspace_id": ws},
        ).status_code
        == 404
    )
    done = client.request(
        "DELETE",
        f"/v1/workspaces/{other}",
        json={"confirm_name": target, "active_workspace_id": ws},
    )
    assert done.status_code == 200, done.text
    assert done.json()["rows"] >= 3  # company, audit, membership
    with Session(admin_engine) as db:
        assert db.get(Workspace, other) is None
        assert not db.scalar(select(Company).where(Company.workspace_id == other))
        assert not db.scalar(select(Audit).where(Audit.workspace_id == other))
        assert db.get(Workspace, foreign) is not None
        assert db.get(Membership, (ws, user)) is not None
    # Now ws is the last one: refused.
    last = client.request(
        "DELETE",
        f"/v1/workspaces/{ws}",
        json={"confirm_name": "Test 0", "active_workspace_id": "none"},
    )
    assert last.status_code == 409


def test_purge_refuses_unbound_or_foreign_tenant(context):
    _, (ws, other, _), _ = context
    with SessionLocal() as db:
        db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})
        try:
            db.execute(text("SELECT prospectos_purge_workspace(:ws)"), {"ws": other})
            raise AssertionError("purge of a foreign tenant must fail")
        except Exception as exc:  # noqa: BLE001
            assert "purge_scope_mismatch" in str(exc)
        db.rollback()
    with Session(admin_engine) as db:
        assert db.get(Workspace, other) is not None
