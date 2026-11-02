"""Durable jobs, private media, CRM and provider infrastructure (additive)."""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_posts_ws_id", "social_posts", ["workspace_id", "id"])
    op.add_column("social_posts", sa.Column("brand_id", sa.String(36), nullable=True))
    op.add_column(
        "social_posts",
        sa.Column("publish_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("social_posts", sa.Column("provider_post_id", sa.String(300), nullable=True))
    op.alter_column("deals", "amount", type_=sa.BigInteger())
    for statement in DDL:
        op.execute(statement)
    op.create_foreign_key(
        "post_brand_tenant",
        "social_posts",
        "brands",
        ["workspace_id", "brand_id"],
        ["workspace_id", "id"],
    )
    for name in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"CREATE POLICY tenant_isolation ON {name} USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), ''))"
        )
    op.create_check_constraint(
        "usage_nonnegative",
        "usage_accounts",
        "ai_budget_minor >= 0 AND ai_spent_minor >= 0 AND ai_reserved_minor >= 0",
    )
    op.create_check_constraint(
        "job_state",
        "jobs",
        "status IN ('queued','running','retry','succeeded','failed','cancelled','ambiguous') AND attempts >= 0 AND max_attempts BETWEEN 1 AND 10",
    )


def downgrade():
    op.drop_constraint("post_brand_tenant", "social_posts", type_="foreignkey")
    for name in REVERSED_TABLES:
        op.drop_table(name)
    op.drop_column("social_posts", "provider_post_id")
    op.drop_column("social_posts", "publish_enabled")
    op.drop_column("social_posts", "brand_id")
    op.drop_constraint("uq_posts_ws_id", "social_posts", type_="unique")
    op.alter_column("deals", "amount", type_=sa.Integer())


DDL = [
    "\nCREATE TABLE webhook_events (\n\tid VARCHAR(150) NOT NULL, \n\tprovider VARCHAR(40) NOT NULL, \n\tprocessed_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n",
    "\nCREATE TABLE assets (\n\tfilename VARCHAR(200) NOT NULL, \n\tstorage_key VARCHAR(80) NOT NULL, \n\tcontent_type VARCHAR(80) NOT NULL, \n\tsize INTEGER NOT NULL, \n\tsha256 VARCHAR(64) NOT NULL, \n\talt_text VARCHAR(1000) NOT NULL, \n\trights_confirmed BOOLEAN NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, id), \n\tUNIQUE (storage_key), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_assets_workspace_id ON assets (workspace_id)",
    "\nCREATE TABLE billing_accounts (\n\tcustomer_id VARCHAR(100), \n\tsubscription_id VARCHAR(100), \n\tstatus VARCHAR(40) NOT NULL, \n\tplan VARCHAR(40) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id), \n\tUNIQUE (customer_id), \n\tUNIQUE (subscription_id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_billing_accounts_workspace_id ON billing_accounts (workspace_id)",
    "\nCREATE TABLE brands (\n\tname VARCHAR(120) NOT NULL, \n\tvoice VARCHAR(1000) NOT NULL, \n\taudience VARCHAR(1000) NOT NULL, \n\tpillars JSON NOT NULL, \n\tprimary_color VARCHAR(7) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_brands_workspace_id ON brands (workspace_id)",
    "\nCREATE TABLE campaigns (\n\tname VARCHAR(200) NOT NULL, \n\tgoal VARCHAR(1000) NOT NULL, \n\tstatus VARCHAR(20) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_campaigns_workspace_id ON campaigns (workspace_id)",
    "\nCREATE TABLE connections (\n\tprovider VARCHAR(40) NOT NULL, \n\tencrypted_token VARCHAR(6000) NOT NULL, \n\tauthor_urn VARCHAR(300) NOT NULL, \n\tscopes JSON NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, provider), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_connections_workspace_id ON connections (workspace_id)",
    "\nCREATE TABLE content_policies (\n\tmode VARCHAR(20) NOT NULL, \n\tmax_posts_daily INTEGER NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_content_policies_workspace_id ON content_policies (workspace_id)",
    "\nCREATE TABLE jobs (\n\tactor_id VARCHAR(36) NOT NULL, \n\tkind VARCHAR(40) NOT NULL, \n\tstatus VARCHAR(30) NOT NULL, \n\tpayload JSON NOT NULL, \n\tresult JSON NOT NULL, \n\tidempotency_key VARCHAR(150) NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tmax_attempts INTEGER NOT NULL, \n\tavailable_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tlast_error VARCHAR(120), \n\tside_effect_started BOOLEAN NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, id), \n\tUNIQUE (workspace_id, idempotency_key), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_jobs_workspace_id ON jobs (workspace_id)",
    "CREATE INDEX job_pending ON jobs (workspace_id, status, available_at)",
    "\nCREATE TABLE oauth_states (\n\tstate_hash VARCHAR(64) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tuser_id VARCHAR(36) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tconsumed BOOLEAN NOT NULL, \n\tPRIMARY KEY (state_hash), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)\n\n",
    "\nCREATE TABLE usage_accounts (\n\tai_budget_minor INTEGER NOT NULL, \n\tai_spent_minor INTEGER NOT NULL, \n\tai_reserved_minor INTEGER NOT NULL, \n\tperiod VARCHAR(7) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_usage_accounts_workspace_id ON usage_accounts (workspace_id)",
    "\nCREATE TABLE post_media (\n\tpost_id VARCHAR(36) NOT NULL, \n\tasset_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, post_id, asset_id), \n\tFOREIGN KEY(workspace_id, post_id) REFERENCES social_posts (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id, asset_id) REFERENCES assets (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_post_media_workspace_id ON post_media (workspace_id)",
    "\nCREATE TABLE post_revisions (\n\tpost_id VARCHAR(36) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tsnapshot JSON NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, post_id, revision), \n\tFOREIGN KEY(workspace_id, post_id) REFERENCES social_posts (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_post_revisions_workspace_id ON post_revisions (workspace_id)",
    "\nCREATE TABLE usage_events (\n\tjob_id VARCHAR(36) NOT NULL, \n\tprovider VARCHAR(40) NOT NULL, \n\tinput_tokens INTEGER NOT NULL, \n\toutput_tokens INTEGER NOT NULL, \n\tcost_minor INTEGER NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, job_id), \n\tFOREIGN KEY(workspace_id, job_id) REFERENCES jobs (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_usage_events_workspace_id ON usage_events (workspace_id)",
    "\nCREATE TABLE campaign_enrollments (\n\tcampaign_id VARCHAR(36) NOT NULL, \n\tcontact_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, campaign_id, contact_id), \n\tFOREIGN KEY(workspace_id, campaign_id) REFERENCES campaigns (workspace_id, id), \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_campaign_enrollments_workspace_id ON campaign_enrollments (workspace_id)",
    "\nCREATE TABLE consents (\n\tcontact_id VARCHAR(36) NOT NULL, \n\tchannel VARCHAR(20) NOT NULL, \n\tevidence VARCHAR(1000) NOT NULL, \n\tlegal_basis VARCHAR(60) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\trevoked BOOLEAN NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_consents_workspace_id ON consents (workspace_id)",
    "\nCREATE TABLE notes (\n\tbody VARCHAR(5000) NOT NULL, \n\tcontact_id VARCHAR(36), \n\tactor_id VARCHAR(36) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_notes_workspace_id ON notes (workspace_id)",
    "\nCREATE TABLE suppressions (\n\tcontact_id VARCHAR(36) NOT NULL, \n\treason VARCHAR(200) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, contact_id), \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_suppressions_workspace_id ON suppressions (workspace_id)",
    "\nCREATE TABLE tasks (\n\ttitle VARCHAR(240) NOT NULL, \n\tcontact_id VARCHAR(36), \n\tdue_at TIMESTAMP WITH TIME ZONE, \n\tstate VARCHAR(20) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_tasks_workspace_id ON tasks (workspace_id)",
]
TENANT_TABLES = [
    "assets",
    "billing_accounts",
    "brands",
    "campaigns",
    "connections",
    "content_policies",
    "jobs",
    "usage_accounts",
    "post_media",
    "post_revisions",
    "usage_events",
    "campaign_enrollments",
    "consents",
    "notes",
    "suppressions",
    "tasks",
]
REVERSED_TABLES = [
    "tasks",
    "suppressions",
    "notes",
    "consents",
    "campaign_enrollments",
    "usage_events",
    "post_revisions",
    "post_media",
    "usage_accounts",
    "oauth_states",
    "jobs",
    "content_policies",
    "connections",
    "campaigns",
    "brands",
    "billing_accounts",
    "assets",
    "webhook_events",
]
