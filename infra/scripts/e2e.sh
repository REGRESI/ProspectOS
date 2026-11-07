#!/usr/bin/env bash
# Browser tests against the isolated E2E stack (docker-compose.e2e.yml), never against
# the development database. The stack's database lives on tmpfs and the stack is torn
# down after every run, so nothing a test creates survives.
#
#   infra/scripts/e2e.sh                 # all specs
#   infra/scripts/e2e.sh cleanstar       # extra args go to `playwright test`
#   E2E_KEEP=1 infra/scripts/e2e.sh      # keep the stack running for debugging
set -euo pipefail
cd "$(dirname "$0")/../.."
compose=(docker compose -f docker-compose.e2e.yml -p prospectos-e2e)

if [[ "${E2E_SKIP_BUILD:-}" != "1" ]]; then
  docker compose build api web >/dev/null
fi
export E2E_TOKEN_ENCRYPTION_KEY="${E2E_TOKEN_ENCRYPTION_KEY:-$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')}"

cleanup() {
  if [[ "${E2E_KEEP:-}" == "1" ]]; then
    echo "E2E-Stack läuft weiter auf http://localhost:3100 (E2E_KEEP=1)."
  else
    "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

"${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${compose[@]}" up -d --wait
E2E_BASE_URL=http://localhost:3100 E2E_ISOLATED=1 \
  pnpm --filter @prospectos/web exec playwright test "$@"
