# Incremental implementation plan

Start: existing d103f23 on feat/prospectos-local-pilot. Preserve working vertical workflows and original tests. Specification retained in CODEX_MASTER_PROMPT.md; detailed remaining gaps in STATUS.md.

| Phase | Delivered in this continuation | Remaining gate |
| --- | --- | --- |
| Audit | Code/schema/routes/frontend/spec audit; baseline preserved; normal branch push | GitHub API/base branch blocks PR |
| Core platform | Additive migrations, isolated migrator, verified external identity/session/RBAC, private media, durable queue and safe audit/logs | Real auth setup, recovery/MFA/team UI, DR/security/load review |
| Discovery/intelligence | Structured query UI, concrete licensed company adapter, provenance/import, restricted research adapter, explainable scores | Credentials/license/egress; richer evidence/enrichment/people APIs |
| AI | Configurable structured source-grounded gateway, durable jobs, usage and budget reservations | Live model access/quality evaluation; image generation |
| Social | Brand/media composer, visual calendar, OAuth and official adapters, encrypted tokens, approval/policy/quota-bound publication jobs, connect/publish controls | Live scopes/product approval/API version, image-processing confirmation, reconciliation/refresh and engagement ingestion |
| Sales/CRM | Campaign audiences/status/drafts, tasks/notes, email transport and consent/source/suppression/approval gates | Rich sequences/reminders/segments, email UI/delivery webhooks |
| SaaS | Stripe test checkout/portal/signature/idempotency, subscription-derived resource limits, export/deletion primitives | Live test integration, billing UI/event ordering, complete privacy/retention/legal rollout |
| Verification | 92 PostgreSQL backend tests,8frontend tests,6browser flows, lint/types/build, compose/smoke and security audits | Remote CI and production/live-provider validation are unverified |

No production or Cloud Environment publication is part of this task. See README for exact preview commands and TESTING for observed outcomes.
