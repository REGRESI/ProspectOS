# Runbook

Use the existing checkout; no worktree is required. `.env.example` is development-only, `.env.production.example` documents external prerequisites. Preserve existing local configuration and never commit secret values. Local database state lives in postgres_data; private media in asset_data. Redis is not needed: PostgreSQL is the durable broker.

Cloud startup from repository root:

```sh
infra/scripts/cloud-compose.sh build api web
infra/scripts/cloud-compose.sh up -d --wait
infra/scripts/cloud-compose.sh run --rm migrate python -m app.seed
python infra/scripts/smoke.py
```

The migrate service is a bounded one-shot with owner privileges; API and worker do not receive DATABASE_ADMIN_URL or development provisioning passwords. They use the restricted app role. Containers run non-root, the web image contains standalone runtime files and cannot mount private assets. The cloud overlay provides the session CA as build secret and read-only runtime mount with SSL_CERT_FILE; TLS verification remains enabled. Production example additionally uses read-only filesystems/capability restrictions, a managed external database and explicit Supabase/HTTPS values. It is not an executed deployment.

The worker polls durable jobs, claims with SKIP LOCKED and a lease, checks actor membership again and records results/errors/attempts. Read-only retryable work uses bounded backoff; expired local leases recover. Dispatch markers commit before email/publishing/paid AI. Unknown outcomes become ambiguous and require operator reconciliation; never reset side_effect_started or blindly requeue an uncertain post. Jobs with previous paid reservation settlement require a fresh authorized AI request. Queue fairness across very large tenant catalogs and a dedicated metrics/alerting stack remain future work.

`/health/ready` verifies database access; it does not prove provider authorization or worker throughput. The smoke additionally checks real login and consistent data. The E2E durable-discovery test exercises the running worker. Request logs use safe route templates and request IDs, not raw OAuth/invitation URLs. Audit and post revisions are append-only for runtime roles.

Before migrations/production: create encrypted PostgreSQL and asset backups outside Git and verify restoration in a separate environment. No full customer-data backup/restore, failover or retention proof was performed here. Rotate Fernet/provider credentials with a tested migration strategy; missing old keys require reconnecting accounts, not disabling encryption. OAuth expiry and missing scopes block publishing. Real provider outcomes, charges, tokens and source licensing need operator review.

Required outbound destinations are listed in .env.example/provider docs and include the specific Supabase project host, api.openai.com (or approved configured LLM host), api.peopledatalabs.com, www.linkedin.com, api.linkedin.com and validated official media-upload hosts, api.stripe.com and api.resend.com. Existing cloud policy only permits selected package/Git hosts; no new egress or secret bindings were silently applied. Review exact provider destinations/approvals before enabling them. No cloud snapshot or production application was published by this task.
