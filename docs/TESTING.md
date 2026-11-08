# Verification — 2026-11-02

These are observed results in the current restored environment, not inferred publication or live-provider readiness. The baseline d103f23 workflows are retained.

| Check | Observed result |
| --- | --- |
| Full backend suite | **124 passed** on real PostgreSQL; all 92 production-MVP backend tests retained, plus connected journey/media/budget/provider tests |
| Migration lifecycle | Disposable DB upgrade0001–0007 → downgradebase → upgradehead; synthetic seed twice; complete backend suite; disposable DB removed |
| Python lint/format | Ruff checks and formatting pass |
| Frontend | ESLint and strict TypeScript pass; **15 Vitest tests passed** (all 8 previous tests plus Social and workflow contract tests) |
| Production build | Next16.4.3 standalone build, TypeScript and static generation pass inside the non-root web image; frozen uv/pnpm installs and TLS verification preserved |
| Docker functional smoke | PostgreSQL, API, worker and standalone web healthy; privileged migrator exits successfully; real cookie login, restricted runtime role and consistent contact totals verified |
| Compose security configuration | Development and production examples resolve; only migrator receives owner DSN; runtime API/worker share private media; web has no private asset mount; production identity settings required |
| Browser E2E | **11 passed**, final run43.5s against the running container stack, including an actual durable worker job |
| Python runtime vulnerability audit | No known vulnerabilities after upgrading cryptography50.0.2 and Pillow13.0.0; tested pinned runtime requirement set via pip-audit |
| JavaScript audit | `pnpm audit --audit-level=high` passes with one **moderate development-tooling** minimatch advisory (GHSA-g3hv-75wg-m249), no high/critical findings. Standalone runtime excludes ESLint tooling |
| GitHub | `feat/prospectos-experience-workflows` pushed normally (implementation commit `0d4fe20`), intended PR base `feat/prospectos-production-mvp`. Draft-PR creation returned `Post https://api.github.com/graphql: Forbidden`. No PR, force-push or deployment |
| Remote CI/deployment/publication | CI configured, not remotely observed passing. No production deployment or Cloud Environment publication performed |

## Browser flows actually executed

1. Workspace creation → brand → private PNG upload with rights/alt text → authenticated image retrieval → post with persisted brand/media → review → approval → internal schedule → visual calendar.
2. Contact → task completion and note → campaign audience → saved offline drafts, with no sending side effect.
3. Durable synthetic discovery query → actual worker result → attributed import; absent real AI credentials produce an explicit error rather than generated success.
4. Original773-row synthetic CSV mapping/preview → commit → idempotent reimport → search → score detail/status update.
5. Original fixture discovery → import → CRM phase → offline caption → review/approval/schedule → edit invalidation.
6. Six core product views at1440/1280/768/375px, no horizontal overflow at checked widths, modal keyboard Escape and honest integration states. Screenshots are ignored artifacts, not committed customer data.

The expanded browser coverage additionally executes persisted business onboarding, explicitly confirmed saved discovery → actual worker → selective import, real company counts, contextual contact → campaign enrollment, sequence variables → attributed draft → approval, foreign-workspace denial, structured ICP create/update and profile application to a lead list. Calendar month/week/list editing invalidates approval and reschedules the actual stored revision; real AI/image configuration failure states and desktop/mobile previews are checked.

Early passes found malformed JSON in the new lead query, missing legacy demo shortcuts, a generated-image job datetime serialization error and a route-announcer test locator ambiguity. These were fixed; original tests were not removed or disabled. The larger suite also reached the existing 10-logins/minute guard. New journey tests reuse one in-memory session, preserving the production guard and avoiding persisted session-cookie artifacts.

Screenshots are ignored artifacts in `apps/web/test-results/experience-*.png`; this task also copies 30 images to `/tmp/prospectos-preview/index.html` for local review. They contain only explicitly synthetic E2E workspaces. No horizontal document overflow was observed across the six core views at the four required widths. Full-page and mobile screenshots were visually inspected.

## Backend proof highlights

Cross-tenant read/write/delete and FK attacks; missing tenant context; append-only audit; JWT tampering/issuer/audience/expiry/algorithm/email and old-demo-session rejection; hashed email-bound expiring/replay-safe invitations and role escalation;773-row CSV/reimport/concurrency/rollback conflicts; SVG/file/body/chunk/pixel limits; private media and post associations; approval invalidation; actor/policy revocation before dispatch; concurrent publishing claim produces one mocked receipt; daily quota uses actual dispatch date; email consent/source/suppression checks again at dispatch; AI reservations/settlement and no free paid retry; lease recovery/ambiguous outcome; signed Stripe webhook idempotency; privacy deletion/redaction and enforced resource limits.

New checks also cover company contact aggregates, validated filters/segments/bulk enrollment, company/contact/deal context isolation, sequence variable allowlists/idempotent draft attribution, selective discovery import/deduplication, paid licensed-discovery dispatch markers, generated-image review/crop gates, model configuration changes before dispatch, partial paid variants, safe provider checks and deletion/export of new derived data.

Provider tests use mocked transports and signed local JWTs. They do **not** verify paid-provider authorization, real OAuth, live posts/images/email delivery, real charges, website-network guard effectiveness or model quality. Supabase/PDL/LLM/LinkedIn/Resend/Stripe credentials were not supplied. Existing package/Git network policy was not broadened.

The package vulnerability audits above were performed for the unchanged dependency lockfiles in the production-MVP baseline; this product upgrade adds no dependencies. Remote CI is configured but has not been observed in this task.

## Repeat

```sh
# DB-dependent tests use their own disposable DB; do not run destructive fixtures against production.
cd services/api
UV_CACHE_DIR=/tmp/prospectos-uv uv sync --frozen
UV_CACHE_DIR=/tmp/prospectos-uv uv run python ../../infra/scripts/validate_database.py
uv run ruff check .
uv run ruff format --check .
cd ../..
pnpm lint
pnpm typecheck
pnpm test
# Running API/worker/web needed; system Chromium was available in this instance.
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium pnpm test:e2e
python infra/scripts/validate_compose.py
python infra/scripts/smoke.py
```

On machines without system Chromium, install the Playwright-supported browser first (`pnpm --filter @prospectos/web exec playwright install --with-deps chromium`) and omit the executable override. Browser tests retain isolated synthetic E2E workspaces; backend fixtures and disposable test DBs are removed. Do not enable real paid providers merely to run development browser tests.

Known non-failing warnings: Starlette's future httpx2 migration and terminal color settings. Comprehensive screenreader/contrast/security/load/DR audits and live-provider release gates remain open.

## Social Studio V2 verification — 2026-11-02

Observed for `feat/social-studio-v2`, based on `8b92928`:

- **130 backend tests passed** on PostgreSQL: all 124 previous tests retained plus six workflow tests covering voice CRUD/examples/version conflicts/export/RLS, variant snapshot/grounding/hard style rules, refinement chains/inherited facts/tenant-bound parent jobs, draft revision comparison/duplicate/archive, metadata/manual/auto/random image selection, explicit absent credentials, and mocked landscape image generation/storage/review gating.
- Migration lifecycle: disposable database upgrade through **0008 → downgrade base → upgrade head**, seed twice, full suite, disposable database removed. The running local dev database was upgraded separately.
- **19 frontend tests passed**, including all previous 15. Added failure-safe voice/example persistence, tag search/manual override, empty/random gallery failure and refinement context/credential failure coverage.
- ESLint, strict TypeScript, Ruff checks/format, `git diff --check` and Next production build pass. No new runtime dependencies or lockfile changes.
- **12 browser E2E tests passed** against local PostgreSQL + source API/worker + the production standalone web build; all 11 prior tests retained. New browser flow creates a voice/example, uses manual/automatic/random/no-image modes, previews a real private fixture image, saves/reloads/edits revisions, duplicates/archives, and checks missing text/image configuration. Narrow-screen overflow and media control availability are checked. Final run details are recorded in the delivery report.
- Compose security validation and local functional smoke pass (web, restricted PostgreSQL role, real cookie login, consistent contact totals). Docker PostgreSQL was used; the API/web container images were not rebuilt in this task. This does not re-claim the previous branch's full container-image verification.

Screenshots: `apps/web/test-results/studio-v2-{voice,workspace,image-configuration,mobile}.png`, copied to the delivery outputs. Screenshots contain only synthetic E2E workspaces and a clearly labeled locally created fixture. They are not evidence of real provider output. Existing cross-product screenshots were also exercised. Failed early browser runs exposed test selector assumptions and a responsive visibility issue; the product and test fixes are included and no existing tests were deleted or skipped.

Live LLM prose quality, paid image authorization/costs, real LinkedIn publishing and remote CI are **not** verified. No provider keys were supplied, no real paid calls were made, no production/public deployment occurred. One existing Starlette/httpx deprecation warning and terminal color warnings are non-failing.

Repeat the commands in the existing Repeat section above, including the disposable-database script, `pnpm build`, and the running API/worker/web for E2E. Local start commands with migrator credentials removed are in [SOCIAL_STUDIO_V2.md](SOCIAL_STUDIO_V2.md).

## Internal Sales Agent V1 verification — 2026-11-04

Observed on `claude/inspiring-meitner-vf8sut` at `6783e85`, local PostgreSQL 16 (no Docker daemon in this container), source API + worker (`LINKEDIN_SIM_DELAY_SECONDS=2`) and the production Next.js build:

- `validate_database.py` (migrate → downgrade base → migrate → seed ×2 → pytest): **150 passed** (130 baseline + 8 OSM + 6 evidence/drafts + 6 LinkedIn channel).
- `ruff check` / `ruff format --check`: clean. `pnpm lint`, `pnpm typecheck`: clean. `pnpm test`: **22 passed** (19 baseline + 3). `pnpm build`: success. `validate_compose.py`: passed.
- Playwright `pnpm test:e2e` with `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/opt/pw-browsers/chromium`: **15 passed** (12 baseline + 3 new: OSM source disclosure, evidence → draft → approval → simulated connect/message/reply → CRM, manual handoff with outcomes and 375 px overflow check).

OSM and LLM HTTP calls are transport-mocked or injected; no live OpenStreetMap, LLM or LinkedIn request was made. The OSM hosts were denied by the environment network policy.

## V3 Multichannel — 2026-11-08

Branch `claude/v3-multichannel`. Cloud session without Docker: the isolated E2E stack was reproduced by `infra/scripts/e2e-local.sh` (throw-away database, same environment as `docker-compose.e2e.yml`, web built against the E2E API).

- Backend `validate_database.py` (migrate → downgrade base → migrate → seed ×2 → pytest): **259 passed** (232 before V3 + 27 new in `tests/test_v3_*.py` and the extended mail test).
- `ruff check`, `ruff format --check`, `pnpm lint`, `pnpm typecheck`: clean. `pnpm test`: 22 passed.
- Full E2E: **34 passed, 3 skipped** (27 existing + 7 V3 specs; the skipped ones are the opt-in design screenshot specs). V3 spec rerun after the last UI change: 7/7.
- Backup/restore: `infra/scripts/test-backup-restore.sh` → 76 tables identical, migration 0026, RLS and `resolve_ref_code` present after restore.
- Letter PDF rendered and inspected (`docs/design/v3/v3-m4-brief-beispiel.png`); not printed on paper.

Not tested here: real IMAP mailbox, public QR scans over the internet, printing, Caddy/HTTPS, Supabase login, rclone upload, real CleanStar data.
