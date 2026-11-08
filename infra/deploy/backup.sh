#!/usr/bin/env bash
# Daily encrypted off-site backup: database dump + private assets, encrypted with `age`
# to a public key (the private key stays OFF the server), uploaded with rclone, old
# backups pruned. Run by the systemd timer from setup-server.sh.
#
#   /opt/prospectos/app/infra/deploy/backup.sh
#
# Needs in server.env: BACKUP_AGE_RECIPIENT (age public key), BACKUP_REMOTE (rclone
# remote:path, e.g. storagebox:prospectos), optional BACKUP_KEEP_DAYS (default 30).
set -euo pipefail
base=/opt/prospectos
set -a; . "$base/server.env"; set +a
: "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT fehlt in server.env}"
: "${BACKUP_REMOTE:?BACKUP_REMOTE fehlt in server.env}"
cd "$base/app"
compose=(docker compose --env-file "$base/server.env" -f infra/docker/production.compose.yml -f infra/deploy/server.compose.yml)
stamp=$(date -u +%Y-%m-%dT%H%MZ)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

"${compose[@]}" exec -T db pg_dump -U prospectos -d prospectos -Fc --no-owner \
  | age -r "$BACKUP_AGE_RECIPIENT" -o "$work/db-$stamp.dump.age"
"${compose[@]}" run --rm --no-deps -T --entrypoint tar api -C /var/lib/prospectos -cz assets \
  | age -r "$BACKUP_AGE_RECIPIENT" -o "$work/assets-$stamp.tar.gz.age"

rclone copy "$work" "$BACKUP_REMOTE/$stamp" --no-traverse
rclone delete "$BACKUP_REMOTE" --min-age "${BACKUP_KEEP_DAYS:-30}d"
rclone rmdirs "$BACKUP_REMOTE" --leave-root
date -u +%FT%TZ > "$base/last-backup-ok"
echo "Backup $stamp hochgeladen nach $BACKUP_REMOTE."
