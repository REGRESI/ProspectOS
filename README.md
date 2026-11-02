# ProspectOS

Ein deutschsprachiger, LinkedIn-orientierter B2B-Arbeitsplatz für Kontakte, nachvollziehbares Scoring und vertriebsnahe Workflows. Die bestehende Anwendung wurde um produktionsorientierte MVP-Workflows erweitert; der Funktionsstand steht in [docs/STATUS.md](docs/STATUS.md).

## Lokal entwickeln

Voraussetzungen: Node24, pnpm11.25.0, Python3.12, uv und Docker mit Compose.

In der verwalteten Cloud ist das Home-Cacheverzeichnis gegebenenfalls schreibgeschützt. Vor den uv-Befehlen `export UV_CACHE_DIR=/tmp/prospectos-uv` setzen; das Makefile verwendet diesen beschreibbaren Standard bereits. Compose liest die Root-`.env` selbst. Die Host-Befehle unten laden sie ausdrücklich über `--env-file`; ohne diesen Parameter müssen eigene Werte exportiert werden.

```sh
cp .env.example .env
docker compose up -d db
pnpm install --frozen-lockfile
cd services/api
uv sync --frozen
uv run --env-file ../../.env python -m app.migrate
uv run --env-file ../../.env python -m app.seed
uv run --env-file ../../.env env -u DATABASE_ADMIN_URL -u DB_APP_PASSWORD -u POSTGRES_PASSWORD -u DEMO_PASSWORD uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

In einem zweiten Terminal im Repository:

```sh
pnpm dev
```

Frontend: `http://localhost:3000`. API-Dokumentation: `http://localhost:8000/docs`. Die Oberfläche leitet API-Aufrufe über denselben Ursprung an FastAPI weiter. `.env.example` enthält ausschließlich lokale Entwicklungseinstellungen. Bereits vorhandene `.env`-Dateien nicht überschreiben.

Lokales Demo-Konto nach dem Seed: `demo@prospectos.local`, Passwort `ProspectDemo!2026`. Es enthält nur synthetische Daten. `DEMO_PASSWORD` kann vor dem ersten Seed einen eigenen lokalen Wert setzen; bestehende Konten werden nicht still überschrieben. Produktionsmodus erfordert verifizierte Supabase-Konfiguration und HTTPS; Demo-Anmeldung ist dort gesperrt.

## Container

```sh
docker compose up --build -d
docker compose run --rm migrate python -m app.seed
```

Für die verwaltete Cloud mit Proxy-CA:

```sh
docker compose -f docker-compose.yml -f infra/docker/cloud.compose.yml up --build -d
```

Die Cloud-Abkürzung mit derselben CA-Konfiguration ist `infra/scripts/cloud-compose.sh`. Nach Installation und Build:

```sh
infra/scripts/cloud-compose.sh build migrate api worker web
infra/scripts/cloud-compose.sh up -d --wait
infra/scripts/cloud-compose.sh run --rm migrate python -m app.seed
python infra/scripts/smoke.py
```

Der Smoke-Check prüft Web-HTML, eingeschränkte DB-Rolle, Anmeldung und übereinstimmende Kontaktsummen. Bei geändertem Demo-Passwort dieses nur als Umgebungsvariable `DEMO_PASSWORD` bereitstellen; niemals in Logs ausgeben.

Die öffentliche CA wird über BuildKit eingebunden, nicht im Image gespeichert. Die vollständige Containerprüfung wird getrennt von lokal gestarteten Komponenten ausgewiesen.

Migration und Demo-Seed laufen im einmaligen `migrate`-Container mit Eigentümerrechten. API und dauerhafter Worker erhalten ausschließlich die Anwendungs-DSN. Beide teilen den privaten Asset-Datenträger; der Webcontainer hat darauf keinen Zugriff. Für Hostentwicklung einen weiteren Prozess aus `services/api` starten: `uv run --env-file ../../.env env -u DATABASE_ADMIN_URL -u DB_APP_PASSWORD -u POSTGRES_PASSWORD -u DEMO_PASSWORD python -m app.worker`.

`infra/docker/production.compose.yml` ist ein **nicht ausgerolltes Deploymentbeispiel** mit externem PostgreSQL, vorab angelegter Laufzeitrolle, echter Supabase-Konfiguration, Secure-Cookies und getrenntem Migrator. Es erfordert HTTPS-Ingress und sichere Wertebereitstellung. Ohne eigene Anbieterzugänge sind externe Authentifizierung und APIs nicht live bestätigt. Details und offene Abnahmen stehen in [docs/MASTER_AUDIT.md](docs/MASTER_AUDIT.md).

## Prüfungen

```sh
pnpm lint
pnpm typecheck
pnpm test
pnpm build
cd services/api
uv run ruff check .
uv run python ../../infra/scripts/validate_database.py
```

Migration und Backendtests benötigen PostgreSQL. Tests nur gegen eine isolierte Entwicklungsdatenbank ausführen. Details und ausgeführte Ergebnisse: [docs/TESTING.md](docs/TESTING.md).

## Produkt-Workflows

Discovery bietet bestätigte strukturierte Suchprofile, gespeicherte Suchen, Quellenprüfung und ausgewählte Übernahme. Kontakte und Unternehmen haben Filter, Segmente, Bulk-Aktionen und verknüpfte Detailansichten. Der Outreach-Workspace verbindet Zielgruppen, Sequenzvorlagen, Entwürfe, Freigaben und dokumentierte manuelle LinkedIn-Schritte. Wiederverwendbare ICP-Profile und ein operativer Startbildschirm verwenden gespeicherte Daten.

Social Studio ergänzt echte konfigurationsgebundene KI-Varianten und Bildjobs mit Budgetprüfung, privater Speicherung und separater Bildfreigabe; Kalender, Revisionen, Vorschau und Engagement-Assistenz sind verbunden. Fehlende Anbieterzugänge bleiben ausdrücklich sichtbar. Onboarding, Teamrollen, Test-Billing und gezielte Anbieterprüfungen liegen unter Einstellungen.

Umfang, genaue Grenzen und Update-Befehle: [Produkt-Upgrade](docs/EXPERIENCE_UPGRADE.md). Vollständiger [Status](docs/STATUS.md), [API](docs/API.md), [Prüfergebnisse](docs/TESTING.md). Keine externe Anbieterfunktion wurde mit echten Credentials live verifiziert.

## Grenzen

- Keine LinkedIn-Scraper, Browser-Bots, automatischen Kontaktanfragen oder DMs.
- Kein tatsächlicher Versand oder externes Publishing ohne vollständig implementierte, autorisierte Anbieteranbindung.
- Synthetische Beispieldaten sind ausdrücklich Demo-Daten. Eine öffentliche Profiladresse ist kein Werbeeinverständnis.
- Echte Kontaktdateien gehören nicht in Git. Lokale Dateien unter `data/private/` sind ignoriert.
- Live-Anbieterprüfung, Produktionsfreigabe, komplette Retention/Backups, Account-Recovery/MFA und rechtliche Freigabe bleiben gesonderte Release-Gates.

## Struktur

`apps/web` – Next.js/TypeScript; `services/api` – FastAPI/SQLAlchemy; `infra/docker` – Container; `docs` – Architektur, Sicherheit und ehrlicher Umsetzungsstand.
