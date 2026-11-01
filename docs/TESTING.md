# Prüfungen

Beobachtungen aus der Cloud-Entwicklung am 01.11.2026. Ergebnisse gelten für diese Instanz, nicht automatisch für einen veröffentlichten Snapshot oder einen späteren Task.

| Prüfung | Beobachtung |
| --- | --- |
| PostgreSQL-Container | PostgreSQL16.11, `pg_isready` und Versionsabfrage erfolgreich |
| Migration und Seed | Frische PostgreSQL-DB: Upgrade → Downgrade base → Upgrade (inkl.0002) erfolgreich; Seed zweimal erfolgreich |
| Backend `uv run pytest` | 25 Tests bestanden, ca.9,85s; eine Starlette/httpx-Deprecation-Warnung |
| Backend Ruff | Lint und Formatprüfung bestanden, 16 Backenddateien sowie Infrastruktur-Skripte |
| pnpm | Lockfile erzeugt; `pnpm install --frozen-lockfile` erfolgreich |
| API-Dockerbuild | Erfolgreich, `uv sync --frozen --no-dev` mit aktivem TLS |
| API-Container funktional | `/health/ready`: DB verbunden, Rolle `prospectos_app`; HTTP-Anmeldung, 2 Workspaces und DB-Dashboard erfolgreich |
| Web und vollständiger Compose-Stack | `infra/scripts/cloud-compose.sh up -d --build --wait`: Build erfolgreich, alle drei Container gesund; idempotenter Seed und `python infra/scripts/smoke.py` bestanden |
| Frontend Lint / Typen / Unit | `pnpm lint`, `pnpm typecheck`, `pnpm test`: bestanden; 5 Vitesttests |
| Browser | 3 Playwright-E2E-Tests gegen den gebauten Docker-Stack bestanden (17,8s): Import/Reimport/Score, Discovery/CRM/Social, responsive Oberfläche/Modal/Integrationen. Screenshots 1440/768/375px; kein horizontaler Überlauf bei geprüften Größen |
| GitHub Actions | Konfiguration vorhanden, Remote-CI nicht ausgeführt |

Die Backendtests prüfen u.a. 773 synthetische CSV-Zeilen, leere E-Mail/Telefonwerte, BOM/Delimiter/Unicode, URL-Validierung, Reimport/Parallelimport, Rollback-Konflikte, gefälschte Workspace-/Kontakt-IDs, RLS ohne/falschen Kontext, Composite-FK-Angriff, Audit-Rechte, CSRF/Logout, Analyst-/Approver-Rechte, fehlende Scoring-Fakten, Social-Revisionen, Scheduling/DST sowie ehrliche Discovery-/Outreach-Zustände. Tests verwenden eine echte isolierte PostgreSQL-Datenbank und löschen ihre eigenen Testdaten. Nicht gegen eine Produktionsdatenbank richten.

Browserdurchläufe erzeugen eigene sichtbar bezeichnete `E2E Demo`-Workspaces. Diese bleiben als synthetische lokale Daten bestehen; sie sind keine realen Geschäftsergebnisse. Screenshots/Traces liegen nur unter ignorierten Testausgabe-Verzeichnissen bzw. CI-Artefakten.

## Wiederholen

```sh
docker compose up -d db
cd services/api
UV_CACHE_DIR=/tmp/prospectos-uv uv sync --frozen
UV_CACHE_DIR=/tmp/prospectos-uv uv run python -m app.migrate
UV_CACHE_DIR=/tmp/prospectos-uv uv run ruff check .
UV_CACHE_DIR=/tmp/prospectos-uv uv run ruff format --check .
UV_CACHE_DIR=/tmp/prospectos-uv uv run pytest
cd ../..
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Echte Providerfunktionen, echte LinkedIn-Veröffentlichung, fremde Personen-/Firmendaten, Checkout/Billing, Objektspeicher, Worker, Backup-Restore und umfassende Barrierefreiheit sind nicht durch diese Tests bestätigt.

## Weitere geprüfte Befehle

```sh
# Eigene temporäre DB: Upgrade, Downgrade, Upgrade, Seed zweimal, alle Backendtests
cd services/api
uv run python ../../infra/scripts/validate_database.py
cd ../..
# Laufenden lokalen Containerstack vorausgesetzt; Cloud-Browserpfad dieser Instanz
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium pnpm test:e2e
```

Auf anderen Systemen zuerst `pnpm --filter @prospectos/web exec playwright install --with-deps chromium` ausführen und dann `pnpm test:e2e`. Die drei E2E-Tests erzeugen eigene synthetische Workspaces; sie werden zur visuellen Prüfung behalten. Backendtest-Fixtures werden dagegen entfernt. Warnungen: Starlette weist auf zukünftiges httpx2 hin, Vite auf zukünftiges natives Config-Loading; alle Tests liefen durch. Vollständiges Screenreader-/Kontrastaudit, produktive Identität und externe Anbieter sind ungetestet.
