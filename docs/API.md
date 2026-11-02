# API contracts

The complete executable contract is FastAPI `/openapi.json` (interactive `/docs`). Next proxies `/api/*` to the same-origin API. All workspace paths use `/v1/workspaces/{ws}` and require verified membership. Pagination is page/limit, maximum100. Writes require X-CSRF-Token from GET `/v1/me`; HttpOnly sessions never enter browser storage. Errors contain safe code/message/details; X-Request-Id links to structured metadata logs.

| Domain | Endpoints |
| --- | --- |
| Identity | GET `/v1/auth/config`, POST `/v1/auth/demo` (dev only), POST `/v1/auth/login` (Supabase), GET `/v1/me`, POST `/v1/auth/logout` |
| Workspaces/team | GET/POST `/v1/workspaces`; GET `…/members`, POST `…/invites`, PATCH `…/members/{user}`; POST `/v1/invites/{token}/accept` |
| Leads | Original dashboard, contacts CRUD/search, company listing and ICP GET/PUT retained |
| CSV | POST `…/imports/preview` multipart; POST `…/imports/{id}/commit` or durable `/enqueue`; POST `/rollback` |
| Discovery | POST `…/discovery/search` structured provider query →202 job; existing `/discovery/runs` demo retained (dev only); POST `/discovery/runs/{id}/import` |
| Research/AI | POST `…/research` reviewed URL →job; POST `…/ai/generate` purpose/prompt/optional contact source →job; GET `…/usage`, PUT `/usage/budget` |
| Jobs | GET `…/jobs`, GET `…/jobs/{id}`, POST `/retry`, POST `/cancel`; uncertain/settled paid work is not automatically retried |
| Media/brand | GET/POST `…/brands`, PUT `…/brands/{id}`; GET `…/assets`; POST `/assets/upload` file+alt_text+rights_confirmed; GET `/assets/{id}/content` tenant-private |
| Social | Original posts/editor/review/approve/internal schedule/cancel retained; asset_ids and brand_id supported; POST `…/social/posts/{id}/publish` separately authorizes durable real publication; GET/PUT `…/social/policy` |
| LinkedIn | POST `…/integrations/linkedin/start`, POST `/disconnect`; GET `/v1/integrations/linkedin/callback`; GET `…/integrations` reports actual connection/configuration/capabilities |
| CRM | Original deals retained; GET/POST `…/tasks`, PATCH `/tasks/{id}`; GET/POST `…/notes`; GET/POST `…/campaigns`, PATCH `/campaigns/{id}`, POST `/campaigns/{id}/drafts` |
| Email | PATCH `…/outreach/drafts/{id}` increments revision/invalidates approval; POST `/approve`; POST `/send-email` →202 job after source/consent/suppression/approval gates. Provider acceptance is not delivery. No LinkedIn send endpoint |
| Consent | POST `…/contacts/{id}/source-review`, `…/consents`, `…/suppressions`; owner/admin proof/source review and last-moment dispatch checks |
| Billing | GET `…/billing`, POST `/billing/checkout`, POST `/billing/portal`; POST `/v1/webhooks/stripe` requires raw-body signature, timestamp and test-mode event, transactionally deduplicated |
| Privacy/audit | POST `…/privacy/export` (owner/admin, excludes credentials), POST `/privacy/delete-contact/{id}` atomically removes derived records/redacts associated jobs; GET `…/audit` |
| Health | GET `/health/live`, `/health/ready`; API and worker use the same startup role/config checks |

Owner/admin permissions gate provider connections, publication, email sending, legal/source reviews, budgets, privacy and billing. Editors cannot self-escalate to approver/admin; approvers can review but not edit leads. No API response implies a missing key, expired token or unavailable provider was bypassed. All unverified provider capabilities and remaining gaps are documented in STATUS.md.

## Product journey endpoints (additive)

All paths below are workspace-relative, with the same membership/RLS/CSRF rules. `POST /leads/query` and `/discovery/interpret` are explicitly read-only; analyst/approver roles may use them with CSRF.

| Domain | Additions |
| --- | --- |
| Home/setup | GET `/home`; GET/PUT `/onboarding` (owner/admin writes) |
| Leads | POST `/leads/query` validated multi-filter/sort/pagination; POST `/leads/bulk`; GET/POST `/segments`; GET `/contacts/{id}/context` |
| Companies/imports | GET `/companies/summary`, `/companies/{id}`; GET `/imports/history`, `/imports/{id}/report` |
| ICP | GET/POST `/icp-profiles`; GET/PUT `/icp-profiles/{id}` with structured criteria and version |
| Discovery | POST `/discovery/interpret` returns unconfirmed suggestions; GET/POST `/discovery/searches`; POST `/discovery/searches/{id}/run` requires `confirmed` and licensed rights where relevant; GET `/discovery/runs/{id}/results`; POST `/discovery/runs/{id}/import-selected` with exact result keys |
| Campaigns | GET `/campaigns/{id}/workspace`; PUT `/campaigns/{id}/sequence`; POST `/campaigns/{id}/generate-drafts` creates labelled template drafts, no AI/send side effect; GET `/outreach/inbox`; POST `/outreach/handoffs` stores manual self-reported events |
| AI/media | POST `/social/generate` queues three variants; GET `/social/images/requirements`; POST `/social/images/generate`; POST `/social/images/{job_id}/save` reviews actual persisted output; POST `/assets/{id}/crop` creates a private derivative |
| Social | GET `/social/posts/{id}/revisions`; GET/POST `/social/interactions`; PATCH `/social/interactions/{id}`; POST `/social/interactions/{id}/suggest` queues an AI suggestion for manual review |
| CRM | GET `/deals` adds bounded search/stage/sort and full filtered totals; GET `/deals/{id}/context` returns real deal/contact/company plus linked contact notes/tasks |
| Provider checks | POST `/providers/{provider}/test` owner/admin; read-only token/model/test-mode checks only; licensed search/email return requirements without hidden paid calls |

Template variables accept `{first_name}`, `{last_name}`, `{company}`, `{job_title}` and double-brace equivalents. They are string substitution only. Profile scores distinguish unsupported/missing evidence from matched criteria. All generated claims require review. Paid social jobs reject model/base/pricing changes before dispatch and never blindly retry ambiguous calls. Image review is rechecked when attaching and publishing media.
