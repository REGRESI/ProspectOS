#!/bin/sh
# Runs once when the database volume is created: the non-owner runtime role that
# API and worker use. Row-level security applies to it; migrations run as the owner.
set -eu
psql -v ON_ERROR_STOP=1 -v pw="$DB_APP_PASSWORD" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE prospectos_app LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS', :'pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prospectos_app') \gexec
SQL
