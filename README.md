# ProspectOS

Ein deutschsprachiger, LinkedIn-orientierter B2B-Arbeitsplatz für Kontakte, nachvollziehbares Scoring und vertriebsnahe Workflows. Dieser erste Aufbau ist eine lokale Entwicklungsanwendung; der Funktionsstand steht in [docs/STATUS.md](docs/STATUS.md).

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
uv run --env-file ../../.env uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In einem zweiten Terminal im Repository:

```sh
pnpm dev
```

Frontend: `http://localhost:3000`. API-Dokumentation: `http://localhost:8000/docs`. Die Oberfläche leitet API-Aufrufe über denselben Ursprung an FastAPI weiter. `.env.example` enthält ausschließlich lokale Entwicklungseinstellungen. Bereits vorhandene `.env`-Dateien nicht überschreiben.

Lokales Demo-Konto nach dem Seed: `demo@prospectos.local`, Passwort `ProspectDemo!2026`. Es enthält nur synthetische Daten. `DEMO_PASSWORD` kann vor dem ersten Seed einen eigenen lokalen Wert setzen; bestehende Konten werden nicht still überschrieben. Die API verweigert den Produktionsmodus ausdrücklich.

## Container

```sh
docker compose up --build -d
docker compose exec api python -m app.seed
```

Für die verwaltete Cloud mit Proxy-CA:

```sh
docker compose -f docker-compose.yml -f infra/docker/cloud.compose.yml up --build -d
```

Die getestete Cloud-Abkürzung mit derselben CA-Konfiguration ist `infra/scripts/cloud-compose.sh`. Nach Installation und Build:

```sh
infra/scripts/cloud-compose.sh build api web
infra/scripts/cloud-compose.sh up -d --wait
infra/scripts/cloud-compose.sh exec -T api python -m app.seed
python infra/scripts/smoke.py
```

Der Smoke-Check prüft Web-HTML, eingeschränkte DB-Rolle, Anmeldung und übereinstimmende Kontaktsummen. Bei geändertem Demo-Passwort dieses nur als Umgebungsvariable `DEMO_PASSWORD` bereitstellen; niemals in Logs ausgeben.

Die öffentliche CA wird über BuildKit eingebunden, nicht im Image gespeichert. Die vollständige Containerprüfung wird getrennt von lokal gestarteten Komponenten ausgewiesen.

## Prüfungen

```sh
pnpm lint
pnpm typecheck
pnpm test
pnpm build
cd services/api
uv run ruff check .
uv run pytest
```

Migration und Backendtests benötigen PostgreSQL. Tests nur gegen eine isolierte Entwicklungsdatenbank ausführen. Details und ausgeführte Ergebnisse: [docs/TESTING.md](docs/TESTING.md).

## Grenzen

- Keine LinkedIn-Scraper, Browser-Bots, automatischen Kontaktanfragen oder DMs.
- Kein tatsächlicher Versand oder externes Publishing ohne vollständig implementierte, autorisierte Anbieteranbindung.
- Synthetische Beispieldaten sind ausdrücklich Demo-Daten. Eine öffentliche Profiladresse ist kein Werbeeinverständnis.
- Echte Kontaktdateien gehören nicht in Git. Lokale Dateien unter `data/private/` sind ignoriert.
- Produktionsbetrieb, externe Authentifizierung, Zahlungsverkehr und rechtliche Freigabe sind eigene Folgeschritte.

## Struktur

`apps/web` – Next.js/TypeScript; `services/api` – FastAPI/SQLAlchemy; `infra/docker` – Container; `docs` – Architektur, Sicherheit und ehrlicher Umsetzungsstand.
