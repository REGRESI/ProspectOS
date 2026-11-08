#!/usr/bin/env bash
# One command for a fresh Ubuntu 24.04 / Debian 12+ server in the EU (as root):
#
#   curl -fsSL <raw URL of this file> -o setup-server.sh && sudo bash setup-server.sh
#   (or after cloning: sudo bash infra/deploy/setup-server.sh)
#
# Idempotent. First run: installs Docker, firewall, age and rclone, clones the repository
# to /opt/prospectos/app and writes /opt/prospectos/server.env with fresh secrets, then
# stops so you can fill in domain, Supabase and backup settings. Second run: builds and
# starts everything behind Caddy (HTTPS), runs migrations and installs the daily backup.
# Nothing here rents a server or touches DNS.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo "Bitte als root ausführen (sudo)."; exit 1; }
base=/opt/prospectos
repo=${REPO_URL:-https://github.com/REGRESI/ProspectOS.git}
branch=${BRANCH:-claude/v3-multichannel}

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git age rclone ufw python3 docker.io docker-compose-v2 >/dev/null
systemctl enable --now docker >/dev/null

ufw allow OpenSSH >/dev/null && ufw allow 80/tcp >/dev/null && ufw allow 443 >/dev/null
ufw --force enable >/dev/null

mkdir -p "$base"
if [[ ! -d "$base/app/.git" ]]; then
  git clone --branch "$branch" "$repo" "$base/app"
else
  git -C "$base/app" fetch origin "$branch" && git -C "$base/app" checkout -q "$branch" && git -C "$base/app" pull -q --ff-only
fi

env_file="$base/server.env"
if [[ ! -f "$env_file" ]]; then
  secret() { python3 -c 'import secrets;print(secrets.token_urlsafe(32))'; }
  fernet=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')
  sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(secret)|" \
      -e "s|^DB_APP_PASSWORD=.*|DB_APP_PASSWORD=$(secret)|" \
      -e "s|^TOKEN_ENCRYPTION_KEY=.*|TOKEN_ENCRYPTION_KEY=$fernet|" \
      "$base/app/infra/deploy/server.env.example" > "$env_file"
  chmod 600 "$env_file"
  echo "Angelegt: $env_file (mit neuen Geheimnissen)."
  echo "Bitte DOMAIN, ACME_EMAIL, APP_BASE_URL, SUPABASE_* und BACKUP_* ausfüllen, dann dieses Skript erneut starten."
  exit 0
fi

set -a; . "$env_file"; set +a
for key in DOMAIN ACME_EMAIL APP_BASE_URL SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_JWT_ISSUER; do
  [[ -n "${!key:-}" ]] || { echo "$key fehlt in $env_file."; exit 1; }
done

cd "$base/app"
compose=(docker compose --env-file "$env_file" -f infra/docker/production.compose.yml -f infra/deploy/server.compose.yml)
"${compose[@]}" build
"${compose[@]}" up -d --wait
echo "Läuft: https://$DOMAIN"

cat > /etc/systemd/system/prospectos-backup.service <<UNIT
[Unit]
Description=ProspectOS encrypted off-site backup
After=docker.service
[Service]
Type=oneshot
ExecStart=$base/app/infra/deploy/backup.sh
UNIT
cat > /etc/systemd/system/prospectos-backup.timer <<UNIT
[Unit]
Description=Daily ProspectOS backup
[Timer]
OnCalendar=*-*-* 03:15:00
RandomizedDelaySec=15m
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
if [[ -n "${BACKUP_AGE_RECIPIENT:-}" ]]; then
  systemctl enable --now prospectos-backup.timer >/dev/null
  echo "Tägliches Backup aktiv (03:15 UTC). Jetzt einmal testen: systemctl start prospectos-backup.service"
else
  echo "Backup noch nicht aktiv: BACKUP_AGE_RECIPIENT und BACKUP_REMOTE setzen, Skript erneut starten."
fi
