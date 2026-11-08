#!/usr/bin/env bash
# Proves the backup format end to end on the local PostgreSQL: a migrated and seeded
# throw-away database is dumped, encrypted with a fresh age key, decrypted, restored into
# a second database and compared table by table (row counts + migration version).
#
#   infra/scripts/test-backup-restore.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
admin="${E2E_ADMIN_URL:-postgresql://prospectos:prospectos_dev@127.0.0.1:5432}"
suffix=$(python3 -c 'import secrets;print(secrets.token_hex(4))')
src="prospectos_backup_src_$suffix" dst="prospectos_backup_dst_$suffix"
work=$(mktemp -d)
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/prospectos-uv}"
cleanup() {
  psql "$admin/postgres" -qc "DROP DATABASE IF EXISTS $src WITH (FORCE)" -c "DROP DATABASE IF EXISTS $dst WITH (FORCE)" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT
psql "$admin/postgres" -qc "CREATE DATABASE $src" -c "CREATE DATABASE $dst"
(cd services/api && APP_ENV=development DATABASE_ADMIN_URL="postgresql+psycopg://${admin#postgresql://}/$src" \
  DB_APP_PASSWORD=prospectos_app_dev uv run sh -c 'python -m app.migrate && python -m app.seed') >"$work/migrate.log" 2>&1

age-keygen -o "$work/key.txt" 2>/dev/null
recipient=$(grep -o 'age1[0-9a-z]*' "$work/key.txt")
pg_dump "$admin/$src" -Fc --no-owner | age -r "$recipient" -o "$work/db.dump.age"
if age -d -i /dev/null "$work/db.dump.age" >/dev/null 2>&1; then echo "Fehler: ohne Schlüssel lesbar"; exit 1; fi
age -d -i "$work/key.txt" "$work/db.dump.age" | pg_restore -d "$admin/$dst" --no-owner --exit-on-error

counts() {
  psql "$admin/$1" -tA -c "SELECT string_agg(t, ',' ORDER BY t) FROM (SELECT table_name || '=' || (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %I', table_name), false, true, '')))[1]::text AS t FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE') s" 
}
a=$(counts "$src"); b=$(counts "$dst")
[[ "$a" == "$b" ]] || { echo "Abweichung nach Wiederherstellung"; diff <(tr , '\n' <<<"$a") <(tr , '\n' <<<"$b"); exit 1; }
v=$(psql "$admin/$dst" -tAc "SELECT version_num FROM alembic_version")
rls=$(psql "$admin/$dst" -tAc "SELECT count(*) FROM pg_class WHERE relrowsecurity")
fn=$(psql "$admin/$dst" -tAc "SELECT count(*) FROM pg_proc WHERE proname='resolve_ref_code'")
tables=$(tr , '\n' <<<"$a" | wc -l)
echo "Wiederherstellung OK: $tables Tabellen identisch, Migration $v, $rls Tabellen mit RLS, Code-Funktion: $fn."
