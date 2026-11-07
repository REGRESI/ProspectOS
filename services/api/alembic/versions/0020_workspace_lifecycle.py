"""Workspace lifecycle: archive flag and a guarded purge function.

Additive. `workspaces.archived_at` hides a workspace from the picker without touching
its data. `prospectos_purge_workspace(ws)` deletes one workspace with all tenant rows,
including the append-only audit history and post revisions the application role may
not delete itself. It is SECURITY DEFINER but only acts on the workspace the caller has
bound as tenant context (app.workspace_id), the same scope RLS enforces; authorization
(owner, typed name, not active, not last) is checked by the API before the call.
"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

PURGE = """
CREATE OR REPLACE FUNCTION prospectos_purge_workspace(target text) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  tbl text;
  pending text[];
  remaining text[];
  passes integer := 0;
  deleted integer := 0;
  n integer;
BEGIN
  IF target IS NULL OR current_setting('app.workspace_id', true) IS DISTINCT FROM target THEN
    RAISE EXCEPTION 'purge_scope_mismatch' USING ERRCODE = '42501';
  END IF;
  SELECT array_agg(c.table_name::text) INTO pending
    FROM information_schema.columns c
    JOIN information_schema.tables tb
      ON tb.table_name = c.table_name AND tb.table_schema = c.table_schema
   WHERE c.table_schema = 'public' AND c.column_name = 'workspace_id'
     AND tb.table_type = 'BASE TABLE';
  -- Delete in passes: a table whose rows are still referenced is retried next pass.
  WHILE array_length(pending, 1) > 0 AND passes < 20 LOOP
    passes := passes + 1;
    remaining := ARRAY[]::text[];
    FOREACH tbl IN ARRAY pending LOOP
      BEGIN
        EXECUTE format('DELETE FROM %I WHERE workspace_id = $1', tbl) USING target;
        GET DIAGNOSTICS n = ROW_COUNT;
        deleted := deleted + n;
      EXCEPTION WHEN foreign_key_violation THEN
        remaining := remaining || tbl;
      END;
    END LOOP;
    pending := remaining;
  END LOOP;
  IF array_length(pending, 1) > 0 THEN
    RAISE EXCEPTION 'purge_incomplete: %', pending;
  END IF;
  DELETE FROM workspaces WHERE id = target;
  RETURN deleted;
END $$;
"""


def upgrade():
    op.add_column("workspaces", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.execute(PURGE)
    op.execute("REVOKE ALL ON FUNCTION prospectos_purge_workspace(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION prospectos_purge_workspace(text) TO prospectos_app")


def downgrade():
    op.execute("DROP FUNCTION IF EXISTS prospectos_purge_workspace(text)")
    op.drop_column("workspaces", "archived_at")
