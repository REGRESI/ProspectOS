"""Workspace lifecycle: rename, archive and delete (with all data).

Deleting requires the owner role, the workspace name typed exactly, and is refused for
the workspace that is currently open and for the user's last remaining workspace. The
actual purge runs in the database function `prospectos_purge_workspace`, which only
acts on the workspace bound as tenant context. Stored image files are removed too.

CLI (cleanup of test workspaces in the real database, after a backup):
  python -m app.workspace_admin               # preview
  python -m app.workspace_admin --apply       # delete
"""

import re
import sys

from fastapi import Depends, HTTPException
from pydantic import Field
from sqlalchemy import func, select, text

from app.db import now
from app.models import Membership, Workspace
from app.schemas import Strict


class RenameInput(Strict):
    name: str = Field(min_length=2, max_length=120)


class ArchiveInput(Strict):
    archived: bool
    active_workspace_id: str = Field(default="", max_length=36)


class DeleteInput(Strict):
    confirm_name: str = Field(max_length=120)
    active_workspace_id: str = Field(max_length=36)


def _active_memberships(db, user_id: str, *, exclude: str = "") -> int:
    return db.scalar(
        select(func.count())
        .select_from(Membership)
        .join(Workspace, Workspace.id == Membership.workspace_id)
        .where(
            Membership.user_id == user_id,
            Workspace.archived_at.is_(None),
            Workspace.id != exclude,
        )
    )


def asset_keys(db, ws: str) -> list[str]:
    from app.platform_models import Asset

    return list(db.scalars(select(Asset.storage_key).where(Asset.workspace_id == ws)))


def remove_files(keys: list[str]) -> None:
    from app.media import asset_root

    root = asset_root()
    for key in keys:
        path = (root / key).resolve()
        if path.parent == root:
            path.unlink(missing_ok=True)


def purge(db, ws: str) -> int:
    """Delete one workspace with all rows. Caller has authorized; binds tenant context."""
    db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})
    return db.scalar(text("SELECT prospectos_purge_workspace(:ws)"), {"ws": ws})


def register_workspace_admin_routes(app, db_session, scope, audit):
    from app.main import current_auth

    def owner(member):
        if member.role != "owner":
            raise HTTPException(403, "Nur die Inhaberin oder der Inhaber darf das.")

    @app.patch("/v1/workspaces/{ws}")
    def rename(
        ws: str, body: RenameInput, member=Depends(scope), db=Depends(db_session, scope="function")
    ):
        if member.role not in ("owner", "admin"):
            raise HTTPException(403, "Nur Inhaber oder Admins dürfen umbenennen.")
        item = db.get(Workspace, ws)
        old = item.name
        item.name = body.name.strip()
        audit(db, ws, member.user_id, "workspace_renamed", f"Workspace „{old}“ → „{item.name}“")
        return {"id": item.id, "name": item.name}

    @app.post("/v1/workspaces/{ws}/archive")
    def archive(
        ws: str,
        body: ArchiveInput,
        member=Depends(scope),
        db=Depends(db_session, scope="function"),
    ):
        owner(member)
        item = db.get(Workspace, ws)
        if body.archived:
            if ws == body.active_workspace_id:
                raise HTTPException(409, "Der geöffnete Workspace kann nicht archiviert werden.")
            if not _active_memberships(db, member.user_id, exclude=ws):
                raise HTTPException(409, "Der letzte Workspace kann nicht archiviert werden.")
            item.archived_at = item.archived_at or now()
        else:
            item.archived_at = None
        audit(
            db,
            ws,
            member.user_id,
            "workspace_archived" if body.archived else "workspace_restored",
            "Workspace archiviert" if body.archived else "Workspace wiederhergestellt",
        )
        return {"id": ws, "archived": bool(item.archived_at)}

    @app.delete("/v1/workspaces/{ws}")
    def delete_workspace(
        ws: str,
        body: DeleteInput,
        member=Depends(scope),
        auth=Depends(current_auth),
        db=Depends(db_session, scope="function"),
    ):
        owner(member)
        item = db.get(Workspace, ws)
        if body.confirm_name.strip() != item.name:
            raise HTTPException(422, "Der eingetippte Name stimmt nicht mit dem Workspace überein.")
        if ws == body.active_workspace_id:
            raise HTTPException(409, "Der geöffnete Workspace kann nicht gelöscht werden.")
        total = db.scalar(
            select(func.count()).select_from(Membership).where(Membership.user_id == auth.user_id)
        )
        if total <= 1:
            raise HTTPException(409, "Der letzte Workspace kann nicht gelöscht werden.")
        keys = asset_keys(db, ws)
        rows = purge(db, ws)
        db.flush()
        remove_files(keys)
        return {"deleted": ws, "rows": rows}


# --- cleanup of test workspaces ----------------------------------------------------

TEST_NAME = re.compile(r"^(E2E |Synthetisch Studio V2 )")


def test_workspaces(db) -> list[Workspace]:
    return [
        w
        for w in db.scalars(select(Workspace).order_by(Workspace.name))
        if w.kind != "production" and (TEST_NAME.match(w.name) or w.slug == "studio-demo")
    ]


def main(argv: list[str]) -> int:
    from app.db import SessionLocal

    apply = "--apply" in argv
    with SessionLocal() as db:
        targets = [(w.id, w.name, w.kind) for w in test_workspaces(db)]
        keep = [
            (w.name, w.kind)
            for w in db.scalars(select(Workspace))
            if w.id not in {t[0] for t in targets}
        ]
    print(f"{len(targets)} Workspaces zum Löschen, bleiben: {keep}")
    if not apply:
        for _, name, kind in targets:
            print(f"  {name} ({kind})")
        print("Nur Vorschau. Mit --apply löschen.")
        return 0
    removed = 0
    for ws, name, _ in targets:
        with SessionLocal() as db, db.begin():
            db.execute(text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": ws})
            keys = asset_keys(db, ws)
            rows = purge(db, ws)
        remove_files(keys)
        removed += 1
        print(f"  gelöscht: {name} ({rows} Zeilen, {len(keys)} Dateien)")
    print(f"{removed} Workspaces gelöscht.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
