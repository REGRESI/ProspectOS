"""Reviewed image provenance, manual engagement and persisted onboarding."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    for statement in DDL:
        op.execute(statement)
    for name in TABLES:
        op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"CREATE POLICY tenant_isolation ON {name} USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), ''))"
        )


def downgrade():
    for name in reversed(TABLES):
        op.drop_table(name)


DDL = [
    "\nCREATE TABLE asset_origins (\n\tasset_id VARCHAR(36) NOT NULL, \n\tjob_id VARCHAR(36), \n\tkind VARCHAR(30) NOT NULL, \n\treviewed BOOLEAN NOT NULL, \n\tmetadata_json JSON NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, asset_id), \n\tFOREIGN KEY(workspace_id, asset_id) REFERENCES assets (workspace_id, id), \n\tFOREIGN KEY(workspace_id, job_id) REFERENCES jobs (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_asset_origins_workspace_id ON asset_origins (workspace_id)",
    "\nCREATE TABLE manual_interactions (\n\tauthor VARCHAR(120) NOT NULL, \n\tcontent VARCHAR(5000) NOT NULL, \n\tpost_url VARCHAR(2000), \n\tstatus VARCHAR(20) NOT NULL, \n\treply_draft VARCHAR(5000) NOT NULL, \n\tactor_id VARCHAR(36) NOT NULL, \n\tsource VARCHAR(20) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_manual_interactions_workspace_id ON manual_interactions (workspace_id)",
    "\nCREATE TABLE workspace_setups (\n\tbusiness VARCHAR(2000) NOT NULL, \n\tregion VARCHAR(200) NOT NULL, \n\ttarget_customers VARCHAR(2000) NOT NULL, \n\tcompleted_steps JSON NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_workspace_setups_workspace_id ON workspace_setups (workspace_id)",
]
TABLES = ["asset_origins", "manual_interactions", "workspace_setups"]
