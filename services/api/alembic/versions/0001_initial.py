"""Initial local-pilot schema and fail-closed tenant policies."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
TENANT_TABLES = [
    "companies",
    "contacts",
    "import_jobs",
    "icp_profiles",
    "audit_events",
    "deals",
    "social_posts",
    "message_drafts",
    "discovery_runs",
]


def upgrade():
    for statement in DDL:
        op.execute(statement)
    for name in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"CREATE POLICY tenant_isolation ON {name} USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), ''))"
        )


def downgrade():
    for name in TABLES_REVERSED:
        op.drop_table(name)


# Frozen schema snapshot; future changes require a new migration.
DDL = [
    "\nCREATE TABLE users (\n\tid VARCHAR(36) NOT NULL, \n\temail VARCHAR(254) NOT NULL, \n\tname VARCHAR(120) NOT NULL, \n\tpassword_hash VARCHAR(255) NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (email)\n)\n\n",
    "\nCREATE TABLE workspaces (\n\tid VARCHAR(36) NOT NULL, \n\tname VARCHAR(120) NOT NULL, \n\tslug VARCHAR(100) NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (slug)\n)\n\n",
    "\nCREATE TABLE auth_sessions (\n\ttoken_hash VARCHAR(64) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\tcsrf_token VARCHAR(64) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (token_hash), \n\tFOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE\n)\n\n",
    "\nCREATE TABLE memberships (\n\tworkspace_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\trole VARCHAR(20) NOT NULL, \n\tPRIMARY KEY (workspace_id, user_id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)\n\n",
    "\nCREATE TABLE companies (\n\tname VARCHAR(240) NOT NULL, \n\tidentity VARCHAR(500) NOT NULL, \n\tlocation VARCHAR(240) NOT NULL, \n\tindustry VARCHAR(120) NOT NULL, \n\tsource VARCHAR(100) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, id), \n\tUNIQUE (workspace_id, identity), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_companies_workspace_id ON companies (workspace_id)",
    "\nCREATE TABLE import_jobs (\n\towner_id VARCHAR(36) NOT NULL, \n\tstatus VARCHAR(30) NOT NULL, \n\tdata JSON NOT NULL, \n\tjournal JSON NOT NULL, \n\tsummary JSON NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_import_jobs_workspace_id ON import_jobs (workspace_id)",
    "\nCREATE TABLE icp_profiles (\n\tprofile JSON NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_icp_profiles_workspace_id ON icp_profiles (workspace_id)",
    "\nCREATE TABLE audit_events (\n\tactor_id VARCHAR(36) NOT NULL, \n\tkind VARCHAR(60) NOT NULL, \n\tdescription VARCHAR(300) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_audit_events_workspace_id ON audit_events (workspace_id)",
    "\nCREATE TABLE social_posts (\n\tcaption VARCHAR(3000) NOT NULL, \n\talt_text VARCHAR(1000) NOT NULL, \n\tstate VARCHAR(30) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tapproved_revision INTEGER, \n\tauthor_id VARCHAR(36) NOT NULL, \n\tscheduled_at TIMESTAMP WITH TIME ZONE, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(author_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_social_posts_workspace_id ON social_posts (workspace_id)",
    "\nCREATE TABLE discovery_runs (\n\tquery VARCHAR(300) NOT NULL, \n\tresults JSON NOT NULL, \n\tstatus VARCHAR(30) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_discovery_runs_workspace_id ON discovery_runs (workspace_id)",
    "\nCREATE TABLE contacts (\n\tcompany_id VARCHAR(36), \n\tfirst_name VARCHAR(120) NOT NULL, \n\tlast_name VARCHAR(120) NOT NULL, \n\tjob_title VARCHAR(240) NOT NULL, \n\tlocation VARCHAR(240) NOT NULL, \n\temail VARCHAR(254), \n\tphone VARCHAR(80), \n\tlinkedin_url VARCHAR(500), \n\timport_key VARCHAR(64), \n\tstatus VARCHAR(30) NOT NULL, \n\tsource VARCHAR(100) NOT NULL, \n\tversion INTEGER NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, id), \n\tUNIQUE (workspace_id, linkedin_url), \n\tUNIQUE (workspace_id, import_key), \n\tFOREIGN KEY(workspace_id, company_id) REFERENCES companies (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_contacts_workspace_id ON contacts (workspace_id)",
    "CREATE INDEX contact_workspace_name ON contacts (workspace_id, last_name, first_name)",
    "\nCREATE TABLE deals (\n\ttitle VARCHAR(200) NOT NULL, \n\tcontact_id VARCHAR(36), \n\tamount INTEGER NOT NULL, \n\tstage VARCHAR(30) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_deals_workspace_id ON deals (workspace_id)",
    "\nCREATE TABLE message_drafts (\n\tcontact_id VARCHAR(36) NOT NULL, \n\tcontent VARCHAR(3000) NOT NULL, \n\tsource VARCHAR(40) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_message_drafts_workspace_id ON message_drafts (workspace_id)",
]
TABLES_REVERSED = [
    "message_drafts",
    "deals",
    "contacts",
    "social_posts",
    "memberships",
    "import_jobs",
    "icp_profiles",
    "discovery_runs",
    "companies",
    "auth_sessions",
    "audit_events",
    "workspaces",
    "users",
]
