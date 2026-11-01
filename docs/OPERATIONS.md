# Betrieb

## Start und Wiederanlauf

Installation und Liveprozesse sind getrennt. `docker compose up -d db`, Migration, API und Frontend müssen nach Wiederherstellung gegebenenfalls neu gestartet werden. Daten bleiben im benannten PostgreSQL-Volume `postgres_data`. Keine Worktree-Erstellung; bestehender Checkout unter `/workspace/ProspectOS`.

`GET /health/live` prüft den Prozess. `GET /health/ready` muss die Datenbankabhängigkeit prüfen. Eine offene Portnummer ersetzt keine fachliche Funktionsprobe. Tests siehe TESTING.md.

## Migration und Rollen

Aus `services/api`: `uv run python -m app.migrate`. Nur für development/test. Der Anwendungsbenutzer besitzt keine Migrationstabellen oder BYPASSRLS-Rechte. Bei DB-Passwortänderungen lokale Rolle und Konfiguration gemeinsam aktualisieren; ein existierender Benutzer wird vom Provisionierungsbefehl nicht still überschrieben.

## Sicherung

PostgreSQL vor Migrationen sichern. Lokaler Export beispielsweise mit `docker compose exec -T db pg_dump -U prospectos -d prospectos -Fc > /sicherer/pfad/prospectos.dump`. Das Ziel liegt außerhalb Git, mit restriktiven Rechten. Backups enthalten personenbezogene Daten. Wiederherstellung zuerst in isolierter Datenbank testen; dieser Task beinhaltet keinen verifizierten Restore.

## Nicht vorhanden

Kein dauerhafter Scheduler, Providerworker, Tokenrefresh oder Monitoringdienst. Social-Planungen werden gespeichert, aber nicht extern veröffentlicht. Externe Anbieter brauchen eigene Timeouts, Retry-/Reconcile-Runbooks, Secretrotation und sichere Protokollierung vor Aktivierung.
