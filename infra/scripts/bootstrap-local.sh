#!/bin/sh
# Local development bootstrap (idempotent). Never overwrites existing values in .env.
# - creates .env from .env.example if missing
# - sets a valid Fernet TOKEN_ENCRYPTION_KEY if empty/invalid (needed for the Integrations page)
# - enables OSM discovery via a local Geofabrik extract and website research
# - downloads the extract (Regierungsbezirk Freiburg, contains the Ortenaukreis) once
set -eu
cd "$(dirname "$0")/../.."
fresh=0
if [ ! -f .env ]; then cp .env.example .env; fresh=1; fi

set_default() { # key value: only if missing/empty, or always for a freshly created .env
  if [ "$fresh" = 1 ] || ! grep -qE "^$1=.+" .env; then
    grep -v "^$1=" .env > .env.tmp || true
    mv .env.tmp .env
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}

key=$(grep -E '^TOKEN_ENCRYPTION_KEY=' .env | cut -d= -f2- || true)
valid=$(python3 -c "import base64,sys
k=sys.argv[1].encode()
try:
    print('ok' if len(base64.urlsafe_b64decode(k))==32 else '')
except Exception:
    print('')" "${key:-x}")
if [ "$valid" != "ok" ]; then
  grep -v '^TOKEN_ENCRYPTION_KEY=' .env > .env.tmp || true
  mv .env.tmp .env
  printf 'TOKEN_ENCRYPTION_KEY=%s\n' "$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" >> .env
  echo "TOKEN_ENCRYPTION_KEY generated"
fi
set_default OSM_DISCOVERY_ENABLED true
set_default OSM_CONTACT "${OSM_CONTACT:-please-set-contact@example.invalid}"
set_default RESEARCH_ENABLED true
set_default OSM_EXTRACT_PATH_CONTAINER /data/osm/freiburg-regbez-latest.osm.pbf
mkdir -p data/private/osm
if [ ! -s data/private/osm/freiburg-regbez-latest.osm.pbf ]; then
  curl -fL -A "ProspectOS/1.0 (local setup)" -o data/private/osm/freiburg-regbez-latest.osm.pbf \
    https://download.geofabrik.de/europe/germany/baden-wuerttemberg/freiburg-regbez-latest.osm.pbf
fi
chmod 600 .env
echo "Bootstrap done. Set OSM_CONTACT and provider keys in .env or later on Einstellungen → Integrationen."
