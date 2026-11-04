# Claude Code work log

Continuation of ProspectOS after an interrupted Codex session. Entries are appended per milestone with exact commits and observed test results. Nothing here claims live provider verification unless stated.

## 2026-11-03 — Takeover audit

### Repository state found

- Task branch `claude/inspiring-meitner-vf8sut` was at `d166d55` (pilot + Pages workflow), clean tree, no stashes.
- Remote branches: `feat/prospectos-local-pilot` (`d166d55`), `feat/prospectos-production-mvp` (`489e618`), `feat/social-studio-v2` (`56f14d9`, newest; contains the production MVP, experience workflows `0d4fe20`/`8b92928` and Social Studio V2).
- The task branch was **fast-forwarded** to `56f14d9` so Social Studio V2 and all previous work are preserved. No history was rewritten; `main` untouched.
- **Missing inputs:** `CLAUDE.md`, `docs/CLAUDE_CODE_HANDOFF_2026-11-03.md`, `docs/INTERNAL_SALES_AGENT_V1_ORIGINAL_SPEC.md`, `docs/CLAUDE_SPRINT_PLAN_2026-11-03.md` and `docs/CLAUDE_WORK_LOG.md` exist on no branch in the remote repository. Any uncommitted Codex work from the interrupted session was not pushed and is not recoverable from this checkout. The retained specification is `CODEX_MASTER_PROMPT.md`; status is in `docs/STATUS.md`, `docs/EXPERIENCE_UPGRADE.md`, `docs/SOCIAL_STUDIO_V2.md`. This log was created new.

### Verified baseline (before any change, at `56f14d9`)

- Local PostgreSQL 16 cluster (no Docker daemon in this container). Dev owner role given superuser locally to match the Compose `POSTGRES_USER` semantics the seed relies on; runtime role `prospectos_app` remains NOSUPERUSER/NOBYPASSRLS.
- `uv run python ../../infra/scripts/validate_database.py`: migrate → downgrade base → migrate → seed ×2 → **130 passed**.
- `pnpm lint`, `pnpm typecheck`: pass. `pnpm test`: **19 passed** (5 files).

### Implemented before takeover (verified by reading code + tests)

Tenant RLS/composite FKs (migrations 0001–0008), identity, team, CSV import, contacts/companies, saved searches with deterministic briefing interpretation, durable job queue, synthetic + licensed PDL company discovery (credential-gated), reviewed-domain research adapter (fail-closed), configurable ICP profiles with explainable known/unknown factors, campaigns with sequence planning, offline template drafts, approval inbox, manual LinkedIn handoff events, CRM board, Social Studio V2, official LinkedIn posting adapter (credential-gated), email/billing adapters (credential-gated).

### Gaps identified for Internal Sales Agent V1

1. No free/open company discovery path that works without paid licences; no radius/geocoding (explicitly disclosed as unsupported).
2. Discovery deduplication is exact provider identity only; no domain/name+place duplicate detection against existing companies.
3. ICP scoring of *company* results uses contact-oriented factors (role always "unknown"); no distance factor.
4. Research output is never normalized into cited company evidence; drafts cannot cite evidence.
5. Campaign drafts are template-only; AI output is not attached to sequence drafts.
6. LinkedIn connection/DM workflow is only self-reported manual events; no simulator, no per-channel capability model.

### Environment blockers

- `overpass-api.de` and `nominatim.openstreetmap.org` are denied by this environment's network policy (proxy HTTP 403). OSM adapters can therefore only be verified with transport-mocked responses here. Allowing these hosts in the environment's network settings would permit a live check.
- No provider credentials (LLM, PDL, LinkedIn) are present; those paths stay gated.

## Milestone 1 — OSM discovery, dedup, company fit (`ab824fe`)

- `app/providers/osm.py`: Nominatim geocode + Overpass `around:` search; 18 curated categories → documented OSM tags; keyword name filter with strict charset + regex escaping; ODbL licence, attribution and `openstreetmap.org/{type}/{id}` per row; phone/e-mail tags dropped; ≥1.1 s per-process spacing; fail-closed unless `OSM_DISCOVERY_ENABLED=true` and `OSM_CONTACT` set.
- `app/prospecting.py`: `DuplicateIndex` (identity → domain → normalized name+place) and `company_fit_score` (radius distance, category, unknown size; role excluded and disclosed).
- Import: probable duplicates are linked (evidence attached, no new company); new companies get cited `company_facts`.
- Migration `0009` (discovery criteria/meta, RLS `geocode_cache`, fact source kind/id/actor with composite FK). `GET …/discovery/providers`.
- Tests: `tests/test_osm_discovery.py` 8 new (transport-mocked, synthetic fixtures). Full `validate_database.py`: **138 passed**. Ruff clean. Compose validation passed.
- Not verified live: OSM hosts blocked by environment network policy.
- Next: M2 evidence review endpoints and evidence-cited drafts.

## Milestone 2 — Evidence and cited drafts (`b1eaf96`)

- `app/sales_agent.py`: `GET/POST/DELETE …/companies/{id}/facts`, `POST …/companies/{id}/research`, `POST …/campaigns/{id}/personalize` (`evidence` | `ai`), `GET …/outreach/drafts/{id}/evidence`.
- Research excerpts are accepted only verbatim from a succeeded research job of that company on the company's own domain.
- Evidence drafts use at most two ranked facts (website excerpt > provider > manual; website/opening-hours/tag facts are not used as message content). AI drafts reserve budget, run via the existing durable worker, and store only citations whose IDs match supplied facts.
- Migration `0010` (`draft_evidence`, RLS). Security fix: draft edit role check.
- Tests: `tests/test_sales_agent.py` 6 new. Full suite **144 passed**; ruff clean.
- Not verified live: no LLM credentials; website research remains operator-gated.
- Next: M3 LinkedIn channel simulator/manual/official gate.

## Milestone 3 — LinkedIn channel (`3f33faa`)

- `app/linkedin_channel.py`: `GET …/linkedin/capabilities`, simulator accounts list/create/seed, `GET/POST …/linkedin/actions`, `POST …/linkedin/actions/{id}/outcome` (manual only), `GET …/campaigns/{id}/linkedin` (sequence progress, next due step, stop on reply/suppression).
- Simulator: synthetic personas only, worker job `linkedin_sim` resolves outcomes after `LINKEDIN_SIM_DELAY_SECONDS`; enabled by default only in development/test.
- Official: refused with explanation; no API call exists.
- Migration `0011`; export includes `draft_evidence`, simulator accounts, actions. AGENTS.md clarified.
- Tests: `tests/test_linkedin_channel.py` 6 new. Full suite **150 passed**; ruff clean; compose validation passed.
- Next: M4 frontend for discovery/evidence/LinkedIn, Playwright E2E, STATUS.md.

## Milestone 4 — UI, E2E, docs (`c27aeec`, `6783e85`)

- `apps/web/components/sales-agent.tsx`: `CompanyEvidence` (company profile) and `CampaignAgent` (campaign view). Discovery workbench: OSM source, capability box, category chips, distance/source/duplicate columns, ODbL attribution.
- Fixed during E2E: handoff card lost on parent reload; mobile outreach grid overflow (910 px at 375 px viewport) — pre-existing layout rule, fixed with `minmax(0, 1fr)`.
- Results: backend **150 passed**, frontend unit **22 passed**, E2E **15 passed**, build/lint/typecheck/ruff/compose clean. Details in TESTING.md; status matrix in STATUS.md.
- Session note: the container restarted once mid-milestone; uncommitted work survived on disk and was committed immediately afterwards.

### Blockers

- OSM public endpoints blocked by environment network policy → no live OSM verification.
- No LLM / LinkedIn partner credentials → AI drafts and official sending unverified/refused.

### Next tasks

1. Allow `nominatim.openstreetmap.org` and `overpass-api.de` (or a self-hosted mirror) and run one live, low-volume OSM search to validate tag coverage.
2. Scheduled reminders for due sequence steps (still manual send/approval), withdraw stale requests.
3. Evidence review queue and fuzzy merge UI for probable duplicates.
4. Map view for OSM results; cross-run OSM result cache with TTL.

## 2026-11-04 — CleanStar round, M0 baseline + M1 backend (branch `claude/cleanstar-sales-v2` from `4f0b2d7`)

### M0 baseline (before changes)
- Tools: `uv` (pip --user) and `pnpm` 11.25.0 (corepack) installed to `~/.local/bin`; Docker stack (db/api/worker/web) running.
- Network here is open: Nominatim 200, OpenAI reachable. OpenAI key lists `gpt-4.1-mini` and `gpt-image-2.5-sunburst` (free `/v1/models` call only).
- Backend `validate_database.py` with only DB URLs: **150 passed**. With the full `.env` loaded: 10 failed (tests inherited real provider env) → fixed by hermetic `pytest_configure` scrub in `tests/conftest.py`.
- Frontend lint/typecheck clean, unit **22 passed**. E2E against running containers: **12 passed, 3 failed**, all environment-dependent: studio-v2 expects "LLM key missing" text but real keys are set; sales-agent simulator outcome not resolved by container worker in time; journeys click timeout. Not yet fixed.
- Two untracked files named `.envdocker compose up -d --force-recreate api worker[.save]` (contain env values) were NOT ignored by `.env.*` → `.gitignore` now ignores `.env*` (examples excepted). Not committed.

### M1 (backend part, built, not live confirmed)
- `app/credentials.py`: provider registry (openai, linkedin, osm, brave, northdata), Fernet-encrypted per-workspace values (TOKEN_ENCRYPTION_KEY), masks only, lazy per-request binding via middleware (path workspace; values load only after `scope` authorized), `bind(ws)` in worker `execute_one`, env fallback. Provider modules read registry fields via `credentials.get`; operator switches (approvals/enable flags/base URLs) stay env-only.
- Migration `0012` `integration_credentials` (RLS, composite FK to memberships, status check).
- `app/integrations.py`: `GET/PUT/DELETE /v1/workspaces/{ws}/integrations/credentials[/{provider}]`, `POST …/{provider}/test`; owner/admin only; save runs a connection test. Tests: OpenAI model metadata (text+image), LinkedIn app probe (invalid code → invalid_client vs invalid_request, no token issued), Nominatim `/status`, Brave 1 query, North Data `suggest` (not billed).
- `app/providers/northdata.py`: power search (address+maxDistanceKm, WZ codes, paging, one concurrent search, censor, blocked dropped, store `register.uniqueKey`), behind `NORTHDATA_ENABLED` + `NORTHDATA_LICENSE_APPROVED`. Docs read: github.com/northdata/api, northdata.github.io/doc/api. No public terms/pricing page retrieved.
- LinkedIn: `LINKEDIN_API_VERSION=202610` is the latest per Microsoft Learn versioning page (checked 2026-11-04). Microsoft Learn's sample app registers `http://localhost:8080/login`, so local http://localhost redirect works without a tunnel. LINKEDIN_CLIENT_ID/SECRET are not in `.env` → OAuth not live tested.
- Tests: `tests/test_integrations.py` 7 new (masking, encryption at rest, forged workspace 404, role 403, 503 without key, workspace-over-env in request and worker binding, error without secret leak, probes). Full suite **157 passed**, ruff clean.

### Open (next session continues here)
1. M1 frontend: extend existing `/settings/integrations` page (workspace-app.tsx ~2418) with credential forms, masked values, test button, status; OAuth callback should redirect to that page instead of returning JSON.
2. M1 live acceptance: one real text + one GPT-Image job through workspace credentials, verify ledger entries; LinkedIn connect/disconnect once Client ID/Secret are entered.
3. Fix the 3 environment-dependent E2E tests; then M2 (OSM live count for Offenburg, North Data import path) onward.

## 2026-11-04 — M1 live + M2 (`e68b483`, next commit)

- `.env` `TOKEN_ENCRYPTION_KEY` contained the generator command instead of a key (invalid Fernet → nothing could ever be encrypted). Backed up to `.env.backup-2026-11-04` (ignored) and replaced with a fresh key. No encrypted data existed.
- M1 live (OpenAI): `infra/scripts/live_m1.py` stored OpenAI settings in the demo workspace (all fields source=workspace), test "Key gültig, Modelle verfügbar: gpt-4.1-mini, gpt-image-2.5-sunburst", real text job and real GPT-Image job succeeded, usage ledger 106 → 207 US cents. Image is booked at the cost cap, not the actual price.
- LinkedIn: no Client ID/Secret in `.env` → OAuth connect/disconnect not live tested. Callback now redirects back to the integrations page.
- `git push` failed: no GitHub credentials on this machine (`gh auth login` needed). Commits are local only.
- M2: North Data wired into discovery/search/job/import with register facts; OSM/North Data limit 200 per run; Overpass backoff; shared geocode cache. Tests: `test_northdata.py` (3), Overpass backoff test. Full suite 162 passed.
- M2 live blocked: overpass-api.de 502 "at capacity", maps.mail.ru 504, overpass.kumi.systems and overpass.private.coffee no response (2026-11-04 ~16:30 CET). Background retry scheduled. Acceptance (≥100 real companies) still open.
