#!/bin/sh
# Managed cloud wrapper: preserve inherited Docker proxy configuration and TLS.
set -eu
repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repo_dir"
if [ ! -r /etc/ssl/certs/ca-certificates.crt ]; then
  echo 'The system CA bundle is required for verified cloud builds.' >&2
  exit 1
fi
exec docker compose -f docker-compose.yml -f infra/docker/cloud.compose.yml "$@"
