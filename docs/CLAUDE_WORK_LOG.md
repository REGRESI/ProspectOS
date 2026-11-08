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

## 2026-11-04 — M2–M6 (`2ac1515` … this commit)

- M2 live: public Overpass refused automated use ("at capacity … run a local instance", HTTP 502 in 0.1 s; alternative public instances 504/no answer). Implemented `OSM_EXTRACT_PATH` (pyosmium over a Geofabrik `.osm.pbf`, same tag selection, no API load). Coverage Offenburg 30 km (named objects): Büro 296, IT 24, Steuerberatung 24, Rechtsberatung 35, Immobilien 27, Versicherung 72, Architektur 25, Handwerk 429, Praxis 257, Gastronomie 922, Hotellerie 327, Einzelhandel 2442, Kfz 234, Fitness 293, Bildung 220, Industrie 403, Logistik 20, Agentur 17, Verwaltung 211, Reinigung 302. `infra/scripts/live_pipeline.py`: 200 results → 197 imported, 3 linked duplicates.
- M3 live: 65 sites, 51 succeeded; 50 companies with Impressum facts. Sample 10: 58/60 literal, ≈7/60 semantic issues (see STATUS). Fixes: label prefix stripping, technical mailbox de-prioritisation, homepage cross-domain re-bind, per-host robots, 2 MB cap with prefix evaluation, language-prefixed Impressum paths, Impressum detection by URL path.
- M4 live: ranking over 208 companies with reasons.
- M5/M6 built with transport-faked tests (`test_today.py`, `test_email_outreach.py`).
- Container fix: `libexpat1` for pyosmium. Compose now passes RESEARCH/North Data/Brave/extract settings.
- Tests: backend 178 passed, ruff clean; frontend lint/typecheck clean.
- Open: M5 live (user sends 5 real requests), M6 live (needs a real mailbox + 3 own test addresses), M7–M9.

## 2026-11-04 — M7–M9, live agent, final checks (`a83570d` … this commit)

- M7 live: `infra/scripts/live_content.py` → 6-week plan (12 items, storyline) and 4 posts with two variants each and a real GPT-Image image attached; ledger 208 → 615 cents. Bug found live: the worker never imports `app.main`, so `content_plans` → `voice_profiles` FK could not resolve (internal_job_failure); fixed with an explicit model import + regression test checking all FK targets in a worker-like process.
- M8 live: agent run "Finde 40 Firmen im Umkreis von 15 km um Lahr, recherchiere sie, priorisiere sie, bereite eine Kampagne vor und fülle die Tagesliste" with confirmation only → 40 hits, 37 new, 3 duplicates, 112 facts, 40 sites researched (19 with result), contacts, campaign, 3:16 min. Bugs found live and fixed: import hooks missing in worker; "Lahr" geocoded to Lahr/Eifel (now city + ICP region); ranking now focuses on the run's companies; step errors fail the run visibly.
- M5 live: Brave matching on 10 real contacts → 6 with candidates (4 at 0.85–1.0, 2 name-only 0.55), 4 fall back to the search link. `site:linkedin.com/in` with full company name returned nothing live → query cascade `linkedin "Name" Stichwort Ort`; profession prefixes stripped from names.
- M9: flow navigation, tokens, system dark mode, file splits (see STATUS). Padded panel class for new pages after reviewing screenshots.
- Tests: backend 184 passed (`validate_database.py`, migrations 0001–0016 up/down/up), ruff clean; frontend lint/typecheck/build clean, unit 22 passed. E2E full suite: 18 passed, 1 failed under load (`journeys.spec.ts` ICP test — passes alone 2/2, also failed in the M0 baseline; nav click timing under concurrent worker load). New `cleanstar.spec.ts` 4/4.
- Screenshots (desktop 1440 + mobile 390) of Heute, Auftrags-Agent, Top-Kandidaten, Lead Discovery, Kampagnen, LinkedIn-Strategie, CRM, Integrationen: `apps/web/test-results/cleanstar-*-{desktop,mobile}.png` (regenerated by `pnpm --filter @prospectos/web exec playwright test tests/e2e/cleanstar.spec.ts`; ignored by Git).
- Handover: docs/HANDOVER_2026-11-04.md.

## 2026-11-06 — LinkedIn pilot round (`fea01a3` … `69590fc`)

- M0 workspace: migration 0017; seed promotes the demo workspace that held real work to production "CleanStar" (DB dump taken first), new synthetic demo; demo isolation from real credentials.
- M1 data quality: dry run over 234 real companies before storing; seat-outside-region rule downgraded (not hidden) after it flagged an architect via a web agency's Impressum address; generic OSM categories decided by name keywords; Landrat/Bürgermeister in Impressum → public administration.
- M2/M3 Heute + style: settings, stages, day-3/7 follow-ups, style rules. Live: old queue items carried dashes and Autohäuser → rebuild now re-checks unapproved items. Robotic hook "Branche in Ort" removed.
- M4 content: live plan + 6 drafts + 6 images (ledger 615 → 1222 cents, images booked at the 100-cent cap), submitted to review. Bug fixed: local variable shadowed the style module in `post_prompt`.
- M5 autopilot: first live run failed — `.env` lacked `OSM_EXTRACT_PATH_CONTAINER` and `RESEARCH_ENABLED` (public Overpass 502); fixed via bootstrap script (backup of .env kept privately). Lahr run: 30 hits, 8 new. Manual research run returned 0 because no website was open (109 without website, 107 researched, 26 failed recently); transient failures now retried after 3 days.
- M6 setup check page. E2E `cleanstar.spec.ts` extended (setup check, demo banner, daily limit, stage) → 6/6.

## 2026-11-07 — Costs, test workspaces, design (`bda09ce` … this commit)

- **Costs:**
  - The ledger booked reservations as spend: 6×2 images at the 100-cent cap, and every text call was rounded up to ≥1 cent. The new ledger stores micro-USD from the provider usage field.
  - Live check: text 169/32 tokens → 0.000119 USD, image `quality=low`, 31/196 tokens → 0.006035 USD. Both are identical to the usage in the response.
  - Text and image calls use the same project key (`IMAGE_API_KEY` is empty).
  - Old images were re-estimated at 196 tokens and flagged as estimated.
- **Test isolation:**
  - Isolated E2E stack; login rate limit is configurable for it.
  - 86 workspaces purged after a DB dump (`data/private/backups/prospectos-2026-11-07-before-cleanup.dump`).
- **Design:** before/after screenshots with a synthetic fixture (`app/design_fixture.py`, E2E stack only).
- **Fixes found in screenshots:**
  - "ich bin ich" intro when no sender name was set.
  - Settings PUT carried an extra field.
  - Template button overflowed on mobile.
- **Tests:** backend 220 passed; frontend lint/typecheck, unit 22 passed; E2E 22/22 on the isolated stack.

## 2026-11-07 — Profiles, content strategy, writing profile, team (`824d709` … this commit)

- **Before building:** inventory, then one question to the user.
  - Inventory: Brave candidates existed (transient, manual confirm), as did invites (backend only, link), voice profiles and content plans (two variants, free-text goals).
  - Question on Brave storage. The user chose: store only the URL and an own-words reason.
- **Live:**
  - DB dump `data/private/backups/prospectos-2026-11-07-before-profiles-content.dump`, then migration 0021.
  - Campaign "Die neue CleanStar-Website" created.
  - Brave profile check on 38 CleanStar contacts: 12 verified, 16 unsure, 10 not found. The role search on 30 companies found no new contact. Two rule fixes came out of a transient diagnosis (slugs masked, nothing stored):
    - A company match beats a place-only match.
    - The surname inside a company name ("Autohaus Wild") no longer counts as a company match.
  - httpx URL logging is switched off: search queries with contact names had appeared in the container logs.
- **Tests:**
  - Backend: 232 (12 new).
  - E2E: 27 on the isolated stack (5 new).
  - Screenshots: `docs/design/neue-seiten/`.

## 2026-11-08 — V3 multichannel, M1 + M2 (branch `claude/v3-multichannel` from `92c12e1`)

- Plan and inventory: `docs/PLAN_V3.md` (`297edc3`).
- **M1** (`67ed8e8`): contact points with source/date, channel switch (verified profile → LinkedIn, else postal address → letter), per-channel permissions (objection blocks all; phone only with concrete interest; e-mail keeps per-country legal basis), cold-email switch off by default (owner + legal note), objection stops all planned steps, duplicate merge with reason. Migration 0022.
- **M2** (`e3b6bc9`): flow steps/runs/tasks, route-filtered recipes, live edits from the next step, conditions, blocked tasks with reason, worker tick, builder page "Ansprache", due steps in Heute. Migration 0023.
- Environment: no Docker here → `infra/scripts/e2e-local.sh` reproduces the isolated E2E stack with a throw-away DB on ports 8100/3100. Found while building it: Next.js bakes `API_URL` into the build, so the script builds the web app against the E2E API.
- Baseline E2E on the first (broken-proxy) attempt is not meaningful; a full E2E run follows after M3.
- Tests: backend **245 passed** (232 + 13); V3 E2E 2/2; lint/typecheck/format clean. Screenshots `docs/design/v3/`.

## 2026-11-08 — V3 M3 + M4

- **M3** (`94949f4`): reactions (IMAP reply, LinkedIn click, QR scan, inquiry code, call, other); every reaction except an accepted invitation stops runs, tasks, scheduled e-mails and Heute items, documents concrete interest for phone and creates one follow-up task; inbox with statuses; public `/r/<code>` resolved by a SECURITY DEFINER function returning ids only. Migration 0024.
- **M4** (this commit): DIN 5008 form B letter PDF (reportlab) in CleanStar look (logo, Instrument Sans/Serif from the repo's OFL fonts, brand blue), QR code per company, batch print PDF of approved letters only, Zweckform 3474 labels, mark printed completes the campaign's letter tasks; print-and-mail service off (options listed, nothing called). Migration 0025. New deps: reportlab, fonttools, brotli.
- Attaching `REGRESI/cleanstar-rebrand` was denied in this session; the brand assets already copied into this repo (`apps/web/public/brand/cleanstar`) were used instead.
- Full E2E on the local isolated stack after M3: **30 passed, 3 skipped** (design-screenshot specs). V3 E2E after M4: 4/4. Backend **253 passed**.

## 2026-11-08 — V3 M5–M8 and handover

- **M5** (`5a07f5c`): distribution round robin/territory, one owner per contact enforced when marking sent, Heute/tasks "mine", personal limits (default 15/day), acceptance rate, invitations open > 21 days; member removal clears nullable references. Migration 0026.
- **M6** (`cddfb5e`): guided start in five steps derived from real data; Heute banner; E2E to first task timed < 5 min.
- **M7** (`261069e`): `infra/deploy/` (server compose with own PostgreSQL and Caddy, setup script, age-encrypted rclone backup, restore with switch), `docs/DEPLOY.md`; restore proven locally.
- **M8** (this commit): source registry and per-source quality report, register-data options researched (vendor pages; to be checked before activation), CLI `python -m app.multichannel` to recompute routes, "Wege neu berechnen" button.
- Docs: `docs/HANDOVER_V3.md`, STATUS V3 section, TESTING V3 section.
- Final: backend 259 passed; E2E 34 passed / 3 skipped; V3 E2E 7/7 after the last change.
- Blockers: no Docker daemon here (worked around); attaching `REGRESI/cleanstar-rebrand` denied (repo copy of brand assets used); no external network for OSM/Brave/LinkedIn/OpenAI; nothing tested with real data.
- Next: live checklist in HANDOVER_V3.md on the Mac; decisions on server, Supabase, print service, cold e-mail.

## 2026-11-08 — M9 (branch `claude/v3-m9-connectors`)

- **M9a–c** (`6f2590f`, `ff1a358`):
  - External outreach tools at the user's own risk, behind a product switch and an owner-confirmed risk text (audited).
  - Adapters for HeyReach, Waalaxy, La Growth Machine, Expandi, lemlist and a generic signed webhook.
  - Handoffs via the job queue with blockers rechecked at dispatch; inbound hooks feed the reaction logic; pause or a manual stop task; "Externes Tool" route and builder step.
  - Vendor endpoints read from their public docs (verified vs. unverified in `docs/CONNECTORS.md`). Migration 0027.
- **M9d/e** (`45e071f`):
  - `python -m app.register_gap` and a Quellen card; role-address letters "An die Geschäftsführung" with a visit task.
  - Art. 14 notice on the first letter per company (migration 0028); rule-based names from company names.
  - Website finder (Brave plus Impressum, name and address must match); professional registers as links only.
- **M9f** (`ad39e66`):
  - Dripify references from dripify.com (environment host added with approval); 4 blind scoring rounds by fresh sub-agents.
  - UI fixes. Goal "equal everywhere" not reached; documented in `docs/design/BENCHMARK.md`.
- Found and fixed: contacts in a running campaign also got daily-queue proposals (double contact risk).
- Final E2E run: a 375 px overflow from wider small buttons. Fixed by letting long button labels wrap on phones.
- Final: backend 299 passed; web lint/typecheck/22 unit tests; E2E 36 passed / 3 skipped.
- Not verified: every vendor adapter (mock-only), tool prices, register URLs, the Brave website finder against the live web.
