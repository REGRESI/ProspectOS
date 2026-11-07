#!/usr/bin/env bash
# Screenshots of the main pages for docs/design/<phase>/ (vorher | nachher).
# Isolated E2E stack + synthetic design fixture only; nothing real ends up in Git.
#   infra/scripts/design-shots.sh vorher "today=/today,companies=/companies,..."
set -euo pipefail
cd "$(dirname "$0")/../.."
phase="${1:?vorher oder nachher}"
pages="${2:?name=/pfad,...}"
compose=(docker compose -f docker-compose.e2e.yml -p prospectos-e2e)
docker compose build api web >/dev/null
export E2E_TOKEN_ENCRYPTION_KEY="${E2E_TOKEN_ENCRYPTION_KEY:-$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')}"
if [[ "${DESIGN_KEEP:-}" == "1" ]]; then
  # Iterating: keep the stack, only swap in the freshly built web/api images.
  "${compose[@]}" up -d --wait
else
  trap '"${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true' EXIT
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  "${compose[@]}" up -d --wait
fi
"${compose[@]}" exec -T api python -m app.design_fixture
mkdir -p "docs/design/$phase"
DESIGN_SHOTS_DIR="$PWD/docs/design/$phase" DESIGN_SHOTS_PAGES="$pages" \
  E2E_BASE_URL=http://localhost:3100 E2E_ISOLATED=1 \
  pnpm --filter @prospectos/web exec playwright test design-shots
