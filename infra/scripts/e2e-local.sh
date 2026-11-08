#!/usr/bin/env bash
# Browser tests without Docker: the same isolation as docker-compose.e2e.yml, built from
# local processes. A throw-away database (prospectos_e2e_<random>) is created on the local
# PostgreSQL, migrated and seeded, API/worker/web run on ports 8100/3100, and everything
# is dropped again afterwards. Use it where no Docker daemon exists (e.g. cloud sessions).
#
#   infra/scripts/e2e-local.sh               # all specs
#   infra/scripts/e2e-local.sh v3            # extra args go to `playwright test`
#   E2E_KEEP=1 infra/scripts/e2e-local.sh    # keep the stack for debugging
#
# Requires: local PostgreSQL with the dev owner role from .env.example, uv, pnpm and
# Chromium for Playwright. The web app is rebuilt against the E2E API port first.
set -euo pipefail
cd "$(dirname "$0")/../.."
root=$(pwd)
admin_base="${E2E_ADMIN_URL:-postgresql+psycopg://prospectos:prospectos_dev@127.0.0.1:5432}"
db="prospectos_e2e_$(python3 -c 'import secrets;print(secrets.token_hex(4))')"
logs="${E2E_LOG_DIR:-$(mktemp -d)}"
mkdir -p "$logs"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/prospectos-uv}"
pids=()

cleanup() {
  # Each service runs in its own process group (setsid); kill the whole group so child
  # processes such as next-server do not keep the ports.
  for pid in "${pids[@]:-}"; do kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true; done
  if [[ "${E2E_KEEP:-}" == "1" ]]; then
    echo "E2E-Stack läuft weiter auf http://localhost:3100 (Datenbank $db, Logs $logs)."
    return
  fi
  wait 2>/dev/null || true
  (cd services/api && uv run python - "$admin_base" "$db" <<'PY'
import sys
from sqlalchemy import create_engine, text
engine = create_engine(sys.argv[1] + "/postgres", isolation_level="AUTOCOMMIT")
with engine.connect() as c:
    c.execute(text(f'DROP DATABASE IF EXISTS "{sys.argv[2]}" WITH (FORCE)'))
PY
  ) >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Next.js bakes the API rewrite target into the build, so the web app is built against
# the E2E API port. Run `pnpm build` again afterwards for normal development.
if [[ "${E2E_SKIP_BUILD:-}" != "1" ]]; then
  API_URL=http://127.0.0.1:8100 pnpm --filter @prospectos/web build >"$logs/build.log" 2>&1
fi

(cd services/api && uv run python - "$admin_base" "$db" <<'PY'
import sys
from sqlalchemy import create_engine, text
engine = create_engine(sys.argv[1] + "/postgres", isolation_level="AUTOCOMMIT")
with engine.connect() as c:
    c.execute(text(f'CREATE DATABASE "{sys.argv[2]}"'))
PY
)

common=(
  APP_ENV=development AUTH_PROVIDER=demo COOKIE_SECURE=false
  APP_BASE_URL=http://localhost:3100 PUBLIC_WEB_URL=http://localhost:3100
  TOKEN_ENCRYPTION_KEY="$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
  LINKEDIN_PUBLISHING_APPROVED=false LINKEDIN_CLIENT_ID=e2e-synthetic-client
  LINKEDIN_CLIENT_SECRET=e2e-synthetic-secret
  LINKEDIN_REDIRECT_URI=http://localhost:3100/v1/integrations/linkedin/callback
  LINKEDIN_SIMULATOR_ENABLED=true LINKEDIN_SIM_DELAY_SECONDS=2
  OSM_DISCOVERY_ENABLED=false RESEARCH_ENABLED=false EMAIL_SEND_ENABLED=false
  STYLE_SAMPLES_PATH=/nonexistent/meine-texte.md E2E_STACK=true LOGIN_ATTEMPTS_PER_MINUTE=500
  ASSET_ROOT="$logs/assets"
)
runtime_url="postgresql+psycopg://prospectos_app:prospectos_app_dev@127.0.0.1:5432/$db"
mkdir -p "$logs/assets"
if curl -s -o /dev/null --max-time 2 http://127.0.0.1:3100/ || curl -s -o /dev/null --max-time 2 http://127.0.0.1:8100/; then
  echo "Port 3100 oder 8100 ist belegt (alter E2E-Lauf?). Bitte zuerst beenden." >&2
  exit 1
fi

(cd services/api && env APP_ENV=development DATABASE_ADMIN_URL="$admin_base/$db" \
  DB_APP_PASSWORD=prospectos_app_dev DEMO_PASSWORD='ProspectDemo!2026' \
  uv run sh -c 'python -m app.migrate && python -m app.seed') >"$logs/migrate.log" 2>&1

(cd services/api && exec setsid env -u DATABASE_ADMIN_URL "${common[@]}" DATABASE_URL="$runtime_url" \
  uv run uvicorn app.main:app --host 127.0.0.1 --port 8100 --no-access-log) >"$logs/api.log" 2>&1 &
pids+=($!)
(cd services/api && exec setsid env -u DATABASE_ADMIN_URL "${common[@]}" DATABASE_URL="$runtime_url" \
  uv run python -m app.worker) >"$logs/worker.log" 2>&1 &
pids+=($!)
(cd apps/web && exec setsid env API_URL=http://127.0.0.1:8100 npx next start --hostname 127.0.0.1 --port 3100) \
  >"$logs/web.log" 2>&1 &
pids+=($!)

for _ in $(seq 1 60); do
  if curl -fs http://127.0.0.1:8100/health/ready >/dev/null && curl -fs -o /dev/null http://127.0.0.1:3100/; then
    break
  fi
  sleep 1
done

cd "$root"
E2E_BASE_URL=http://localhost:3100 E2E_ISOLATED=1 \
  PLAYWRIGHT_CHROMIUM_EXECUTABLE="${PLAYWRIGHT_CHROMIUM_EXECUTABLE:-/opt/pw-browsers/chromium}" \
  pnpm --filter @prospectos/web exec playwright test "$@"
