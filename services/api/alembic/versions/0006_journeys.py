"""Connected discovery, lead context, segments and campaign journey state."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_message_drafts_tenant_id", "message_drafts", ["workspace_id", "id"]
    )
    for statement in DDL:
        op.execute(statement)
    for name in TABLES:
        op.execute(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"CREATE POLICY tenant_isolation ON {name} USING (workspace_id = nullif(current_setting('app.workspace_id', true), '')) WITH CHECK (workspace_id = nullif(current_setting('app.workspace_id', true), ''))"
        )
    op.create_check_constraint(
        "campaign_sequence_position",
        "campaign_sequence_steps",
        "position BETWEEN 0 AND 9 AND delay_days BETWEEN 0 AND 90 AND channel IN ('linkedin_manual','email')",
    )


def downgrade():
    for name in reversed(TABLES):
        op.drop_table(name)
    op.drop_constraint("uq_message_drafts_tenant_id", "message_drafts", type_="unique")


DDL = [
    "\nCREATE TABLE intelligence_profiles (\n\tname VARCHAR(120) NOT NULL, \n\tprofile JSON NOT NULL, \n\tversion INTEGER NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_intelligence_profiles_workspace_id ON intelligence_profiles (workspace_id)",
    "\nCREATE TABLE saved_searches (\n\tname VARCHAR(120) NOT NULL, \n\tbriefing VARCHAR(2000) NOT NULL, \n\tfilters JSON NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_saved_searches_workspace_id ON saved_searches (workspace_id)",
    "\nCREATE TABLE saved_segments (\n\tname VARCHAR(120) NOT NULL, \n\tfilters JSON NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_saved_segments_workspace_id ON saved_segments (workspace_id)",
    "\nCREATE TABLE campaign_configs (\n\tcampaign_id VARCHAR(36) NOT NULL, \n\tchannel VARCHAR(30) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, campaign_id), \n\tFOREIGN KEY(workspace_id, campaign_id) REFERENCES campaigns (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_campaign_configs_workspace_id ON campaign_configs (workspace_id)",
    "\nCREATE TABLE campaign_sequence_steps (\n\tcampaign_id VARCHAR(36) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tdelay_days INTEGER NOT NULL, \n\tchannel VARCHAR(30) NOT NULL, \n\ttemplate VARCHAR(3000) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, campaign_id, position), \n\tFOREIGN KEY(workspace_id, campaign_id) REFERENCES campaigns (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_campaign_sequence_steps_workspace_id ON campaign_sequence_steps (workspace_id)",
    "\nCREATE TABLE company_facts (\n\tcompany_id VARCHAR(36) NOT NULL, \n\tfield VARCHAR(80) NOT NULL, \n\tvalue VARCHAR(1000) NOT NULL, \n\tsource_url VARCHAR(2000) NOT NULL, \n\tconfidence VARCHAR(30) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id, company_id) REFERENCES companies (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_company_facts_workspace_id ON company_facts (workspace_id)",
    "\nCREATE TABLE company_profiles (\n\tcompany_id VARCHAR(36) NOT NULL, \n\tis_customer BOOLEAN NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, company_id), \n\tFOREIGN KEY(workspace_id, company_id) REFERENCES companies (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_company_profiles_workspace_id ON company_profiles (workspace_id)",
    "\nCREATE TABLE lead_profiles (\n\tcontact_id VARCHAR(36) NOT NULL, \n\towner_id VARCHAR(36), \n\ttags JSON NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, contact_id), \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id, owner_id) REFERENCES memberships (workspace_id, user_id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_lead_profiles_workspace_id ON lead_profiles (workspace_id)",
    "\nCREATE TABLE manual_outreach_activities (\n\tcontact_id VARCHAR(36) NOT NULL, \n\tcampaign_id VARCHAR(36), \n\tactor_id VARCHAR(36) NOT NULL, \n\tkind VARCHAR(40) NOT NULL, \n\tnote VARCHAR(1000) NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id, campaign_id) REFERENCES campaigns (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id, actor_id) REFERENCES memberships (workspace_id, user_id), \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_manual_outreach_activities_workspace_id ON manual_outreach_activities (workspace_id)",
    "\nCREATE TABLE campaign_draft_links (\n\tcampaign_id VARCHAR(36) NOT NULL, \n\tcontact_id VARCHAR(36) NOT NULL, \n\tdraft_id VARCHAR(36) NOT NULL, \n\tstep_position INTEGER NOT NULL, \n\tid VARCHAR(36) NOT NULL, \n\tworkspace_id VARCHAR(36) NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tUNIQUE (workspace_id, campaign_id, contact_id, step_position), \n\tFOREIGN KEY(workspace_id, campaign_id) REFERENCES campaigns (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id, contact_id) REFERENCES contacts (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id, draft_id) REFERENCES message_drafts (workspace_id, id) ON DELETE CASCADE, \n\tFOREIGN KEY(workspace_id) REFERENCES workspaces (id)\n)\n\n",
    "CREATE INDEX ix_campaign_draft_links_workspace_id ON campaign_draft_links (workspace_id)",
]
TABLES = [
    "intelligence_profiles",
    "saved_searches",
    "saved_segments",
    "campaign_configs",
    "campaign_sequence_steps",
    "company_facts",
    "company_profiles",
    "lead_profiles",
    "manual_outreach_activities",
    "campaign_draft_links",
]
