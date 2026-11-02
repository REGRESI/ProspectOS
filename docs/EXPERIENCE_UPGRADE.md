# Product workflow upgrade — 2026-11-02

Incremental work on `feat/prospectos-experience-workflows` from `489e618` (`feat/prospectos-production-mvp`). The architecture, original master specification, migrations, API/route contracts and existing tests were reviewed before implementation. No public deployment or cloud configuration publication is part of this change. The original master audit remains in MASTER_AUDIT.md.

| Journey | Implemented and locally verified | Explicit remaining scope |
| --- | --- | --- |
| Navigation/home | Five product journeys plus settings; collapsible persistent sidebar, independent navigation scroll; operational counts, recent/qualified leads, pending outreach, tasks, campaigns, scheduled posts and pipeline audit from PostgreSQL | Workspace choice remains session-persistent. Full analytics and accessibility certification remain open |
| Discovery | Editable deterministic briefing interpretation requiring confirmation; saved searches; durable jobs; country/city/industry/employee ranges for licensed company search; region/keyword/exclusion filtering over bounded provider response; customer exclusions by known company identity/domain or won deal; attributed sortable/paginated results, completeness, score factors, detail, selective idempotent import | No licensed person adapter. Radius, role and seniority unsupported by company search and explicitly disclosed. Multiple industries are constrained by first-industry upstream search. No exhaustive-market or geocoding claim. Demo mode delivers fixed synthetic samples, not matches |
| Leads/companies | Validated read-only filter query; saved segments; bulk tags/status/owner/campaign enrollment; provenance/completeness; contextual profiles with notes/tasks/manual activities/drafts; company navigation, linked contacts/deals and corrected aggregate contact counts; import history and staged validation reports | Filters/segments bounded to interactive pages; large-scale indexing/streaming pending. Completed imports discard staging error details. Research jobs are visible but do not automatically assert website text as verified company facts |
| ICP | Multiple persisted profiles, chip-based region/role/industry/exclusion/need criteria; employee ranges, required/optional fields, weights totalling 100, versioned edits; explainable known/unknown scoring; apply profile to lead query and save as campaign audience segment | Required fields are completeness indicators, not a guarantee of qualification. Discovery profile prefill and a dedicated campaign profile selector remain open. Need evidence must already exist in company provenance |
| Outreach | Audience from selection/segment; persistent sequence steps, channel, delay planning and allowlisted variables; contact-specific attributed offline drafts; central review inbox, revision approval/edit invalidation, manual LinkedIn handoff events; real campaign status and observed progress | Delays are planning data, not an automatic scheduler. Campaign AI personalization remains available through existing AI jobs, without automatically attaching output to sequence drafts. No inferred delivery/reply rates. Email consent/source/suppression and send APIs remain separately gated; full sending/revocation UI is pending |
| Social | Real configurable three-variant AI jobs; topic/audience/brand/tone/objective/type/instructions; review-only outputs, usage/budget reservations, partial paid results retained; real image provider interface + OpenAI implementation; private persisted output, separate review/save, crop; desktop/mobile preview; stored revisions; month/week/list calendar with edit/reapproval/reschedule; workspace automation policy UI; manual engagement log and real AI reply jobs | Real provider approval/key/model/prices/egress required. Only one concrete image provider; no provider invoice reconciliation. Image cost is an operator-verified maximum, not a billing receipt. No live provider generation/publication verified. No external engagement feed or automatic commenting |
| CRM | Persistent native drag/drop stage changes and accessible select alternative, list/board, search/sort/stage filters, server-side total values, deal context with linked contact/company and that contact's tasks/notes | Deal owner, expected-close dates, deal-specific notes and touch/mobile drag/drop library remain open. Contact tasks are explicitly linked contact context, not invented deal activity |
| Onboarding/settings | Persisted business/region/target customers; guided next actions; team/role management and manually delivered one-time invitations; actual billing entitlements and test checkout/portal controls; read-only provider checks with precise scope/requirements | Invitation acceptance UI, signup/recovery/MFA and complete onboarding completion inference remain open. Provider checks confirm only the stated metadata/token/test-mode access, never blanket send rights |
| Persistence/security | Additive 0006/0007, thirteen tenant RLS tables, composite tenant FKs/cascades; validated authoring roles; paid dispatch markers before PDL requests; no blind paid retries; config fingerprint rejects model/pricing drift before social dispatch; generated image review rechecked at publication; extended safe export and subject deletion cascades | Production load, DR/backups, full retention/free-text PII erasure, S3/malware scanning, distributed observability and operational review remain release gates |

## Provider setup

All credentials stay on the server. `.env.example` and `.env.production.example` document names; local and production Compose pass the same optional image settings to API/worker.

- Text: `LLM_API_KEY`, explicit `LLM_MODEL`, HTTPS `LLM_BASE_URL`, current input/output USD-per-million prices and capped output tokens. Workspace budget uses USD cents.
- Images: `IMAGE_MODEL`, `IMAGE_MAX_COST_USD_CENTS` (verified conservative per-image maximum, 1–10000), optional `IMAGE_API_KEY`/`IMAGE_BASE_URL` (fall back to text provider key/base). Adapter calls `/images/generations`, requests one 1024px JPEG, accepts bounded base64 bytes, strips metadata and re-encodes private raster storage. Returned URLs/placeholders are rejected. Provider maximums and compatibility must be checked before enabling.
- Discovery: PDL key, approved license and license reference; permitted company research additionally requires reviewed domains/terms and an independent private-IP egress guard.
- LinkedIn: app client/secret/redirect, token encryption key, granted OAuth products/scopes and supported API version. Internal calendar scheduling is separate from actual publishing authorization. Connection requests and DMs remain manual.
- Resend and Stripe retain their existing explicit send/test-mode requirements. Production identity requires Supabase/HTTPS. No provider credentials were supplied in this task; restricted network destinations were not broadened.

## Preview and update

Do not overwrite an existing `.env`. From the repository root after fetching the feature branch:

```sh
git switch feat/prospectos-experience-workflows
pnpm install --frozen-lockfile
infra/scripts/cloud-compose.sh build api web
infra/scripts/cloud-compose.sh up -d --wait
infra/scripts/cloud-compose.sh run --rm migrate python -m app.seed
python infra/scripts/smoke.py
```

The cloud helper uses the managed proxy CA. Outside this environment use `docker compose up --build -d` and `docker compose run --rm migrate python -m app.seed`. The one-shot migrator applies additive migrations before the API/worker start. Preview: http://localhost:3000, API: http://localhost:8000/docs. The seed is development-only and idempotent. Original routes/APIs remain available; richer workspaces are primary, with old discovery/contact/company/outreach/ICP views under `/…/legacy` for compatibility.

Screenshots are generated from isolated synthetic browser workspaces in `apps/web/test-results/experience-*.png`; tests cover desktop and mobile at 375, 768, 1280 and 1440px. They are ignored artifacts, not committed customer data. See TESTING.md for final observed results.
