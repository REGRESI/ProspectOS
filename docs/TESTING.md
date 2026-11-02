# Verification — 2026-11-02

These are observed results in the current restored environment, not inferred publication or live-provider readiness. The baseline d103f23 workflows are retained.

| Check | Observed result |
| --- | --- |
| Full backend suite | **92 passed** on real PostgreSQL, last fresh-database run13.15s; original25 retained plus identity, provider and platform security/workflow tests |
| Migration lifecycle | Disposable DB upgrade0001–0005 → downgradebase → upgradehead; synthetic seed twice; complete backend suite; disposable DB removed |
| Python lint/format | Ruff checks and formatting pass |
| Frontend | ESLint and strict TypeScript pass; **8 Vitest tests passed** (original5 plus production/demo login behavior) |
| Production build | Next16.4.3 standalone build, TypeScript and static generation pass inside the non-root web image; frozen uv/pnpm installs and TLS verification preserved |
| Docker functional smoke | PostgreSQL, API, worker and standalone web healthy; privileged migrator exits successfully; real cookie login, restricted runtime role and consistent contact totals verified |
| Compose security configuration | Development and production examples resolve; only migrator receives owner DSN; runtime API/worker share private media; web has no private asset mount; production identity settings required |
| Browser E2E | **6 passed**, final run19.5s against the running container stack, including an actual durable worker job |
| Python runtime vulnerability audit | No known vulnerabilities after upgrading cryptography50.0.2 and Pillow13.0.0; tested pinned runtime requirement set via pip-audit |
| JavaScript audit | `pnpm audit --audit-level=high` passes with one **moderate development-tooling** minimatch advisory (GHSA-g3hv-75wg-m249), no high/critical findings. Standalone runtime excludes ESLint tooling |
| GitHub | Existing branch pushed normally. API request to api.github.com/graphql returns Forbidden; final review branch has the preserved pilot as its base. No PR or force-push |
| Remote CI/deployment/publication | CI configured, not remotely observed passing. No production deployment or Cloud Environment publication performed |

## Browser flows actually executed

1. Workspace creation → brand → private PNG upload with rights/alt text → authenticated image retrieval → post with persisted brand/media → review → approval → internal schedule → visual calendar.
2. Contact → task completion and note → campaign audience → saved offline drafts, with no sending side effect.
3. Durable synthetic discovery query → actual worker result → attributed import; absent real AI credentials produce an explicit error rather than generated success.
4. Original773-row synthetic CSV mapping/preview → commit → idempotent reimport → search → score detail/status update.
5. Original fixture discovery → import → CRM phase → offline caption → review/approval/schedule → edit invalidation.
6. Dashboard at1440/768/375px, no horizontal overflow at checked widths, modal keyboard Escape and honest integration states. Screenshots are ignored artifacts, not committed customer data.

The first browser passes exposed an asset display-name mismatch and native-select test locator problems. The asset now retains a sanitized original basename while bytes/storage remain canonical/private; selectors use the accessible combobox role. All six final assertions completed. No assertions or flows were disabled to obtain a pass.

## Backend proof highlights

Cross-tenant read/write/delete and FK attacks; missing tenant context; append-only audit; JWT tampering/issuer/audience/expiry/algorithm/email and old-demo-session rejection; hashed email-bound expiring/replay-safe invitations and role escalation;773-row CSV/reimport/concurrency/rollback conflicts; SVG/file/body/chunk/pixel limits; private media and post associations; approval invalidation; actor/policy revocation before dispatch; concurrent publishing claim produces one mocked receipt; daily quota uses actual dispatch date; email consent/source/suppression checks again at dispatch; AI reservations/settlement and no free paid retry; lease recovery/ambiguous outcome; signed Stripe webhook idempotency; privacy deletion/redaction and enforced resource limits.

Provider tests use mocked transports and signed local JWTs. They do **not** verify paid-provider authorization, real OAuth, live posts/images/email delivery, real charges, website-network guard effectiveness or model quality. Supabase/PDL/LLM/LinkedIn/Resend/Stripe credentials were not supplied. Existing package/Git network policy was not broadened.

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
