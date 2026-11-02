# Persistent schema

Original tables and rows are preserved. Migrations0001/0002 establish the local core;0003 adds platform tables and tenant policies;0004 adds provider-bound identity/invitations;0005 adds source review, email approval metadata and actual dispatch timestamps. Migrations are frozen additive instructions, not live create_all calls. `python -m app.migrate` runs Alembic; production requires an explicit owner DSN and pre-provisioned prospectos_app role, with no development password provisioning.

Domains: users/auth_sessions/auth_rate_buckets/workspaces/memberships/workspace_invites; contacts/companies/import_jobs/icp_profiles; brands/assets/post_media/post_revisions/social_posts/content_policies/connections/oauth_states; jobs/usage_accounts/usage_events; tasks/notes/campaigns/campaign_enrollments/message_drafts/consents/suppressions; billing_accounts/webhook_events; audit_events.

Tenant business tables have indexed workspace_id and FORCE RLS. Composite tenant FKs cover contacts→companies, media→post/asset, post→brand, revisions→post, tasks/notes/consents/suppressions/enrollments/drafts→contact, enrollments→campaign and usage→job. Exact identity and idempotency uniqueness is workspace-scoped. Audit and revision history cannot be modified by the runtime role. Global auth/catalog, transient user-bound OAuth and signed webhook lookup tables are server-only exceptions, never direct browser DB access.

Jobs persist claim attempts, due time, lease, dispatch marker/timestamp, safe error and result. User/capability checks run again at dispatch. Usage reservations and event uniqueness prevent repeated charging/settlement. Private asset metadata stores random storage keys, canonical byte type, SHA256, size, rights and alt text; contents live in an isolated persistent volume. Tokens use Fernet ciphertext, not browser storage or job payloads.

The complete target schema remains larger than this MVP: full segments, per-field provenance, richer CRM attribution, job outbox, billing ordering/history, legal retention and object-storage lifecycle remain gaps. See STATUS.md and the executable models/migrations.
