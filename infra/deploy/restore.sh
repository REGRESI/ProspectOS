#!/usr/bin/env bash
# Restore a backup into a NEW database next to the running one, check it, and only then
# switch over. Never overwrites the live database without the explicit --switch flag.
#
#   restore.sh <backup-folder> <age-identity-file>            # restore into prospectos_restore + check
#   restore.sh <backup-folder> <age-identity-file> --switch   # additionally make it live
#
# <backup-folder> is a remote folder name (e.g. 2026-11-08T0300Z) or a local directory.
set -euo pipefail
base=/opt/prospectos
set -a; . "$base/server.env"; set +a
folder=${1:?Backup-Ordner angeben}
identity=${2:?Datei mit dem privaten age-Schlüssel angeben}
cd "$base/app"
compose=(docker compose --env-file "$base/server.env" -f infra/docker/production.compose.yml -f infra/deploy/server.compose.yml)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
if [[ -d "$folder" ]]; then cp "$folder"/* "$work/"; else rclone copy "$BACKUP_REMOTE/$folder" "$work"; fi
dump=$(ls "$work"/db-*.dump.age)
age -d -i "$identity" "$dump" > "$work/db.dump"
"${compose[@]}" exec -T db dropdb -U prospectos --if-exists prospectos_restore
"${compose[@]}" exec -T db createdb -U prospectos prospectos_restore
"${compose[@]}" exec -T db pg_restore -U prospectos -d prospectos_restore --no-owner --exit-on-error < "$work/db.dump"
"${compose[@]}" exec -T db psql -U prospectos -d prospectos_restore -tAc \
  "SELECT 'Firmen: '||count(*) FROM companies UNION ALL SELECT 'Kontakte: '||count(*) FROM contacts UNION ALL SELECT 'Migration: '||version_num FROM alembic_version"
if [[ "${3:-}" == "--switch" ]]; then
  "${compose[@]}" stop api worker web
  "${compose[@]}" exec -T db psql -U prospectos -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='prospectos'" \
    -c "ALTER DATABASE prospectos RENAME TO prospectos_before_restore_$(date +%Y%m%d%H%M)" \
    -c "ALTER DATABASE prospectos_restore RENAME TO prospectos"
  "${compose[@]}" exec -T db psql -U prospectos -d prospectos -c \
    "GRANT USAGE ON SCHEMA public TO prospectos_app; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO prospectos_app; REVOKE UPDATE, DELETE ON audit_events, post_revisions FROM prospectos_app"
  "${compose[@]}" up -d
  echo "Wiederhergestellt. Die alte Datenbank bleibt als prospectos_before_restore_* erhalten."
else
  echo "Wiederherstellung geprüft in prospectos_restore. Live schalten mit --switch."
fi
