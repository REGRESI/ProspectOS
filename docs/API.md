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
