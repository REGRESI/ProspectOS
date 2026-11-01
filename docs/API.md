# API

FastAPI erzeugt OpenAPI unter `/openapi.json` und interaktive Dokumentation unter `/docs`. Diese Laufzeitbeschreibung ist der genaue Vertrag für Felder und Validierungsgrenzen. Frontend-Anfragen laufen über `/api` der Web-Origin; das Prefix wird dort entfernt.

## Authentifizierung und Mandant

`POST /v1/auth/demo` mit `email` und `password` erzeugt ausschließlich im lokalen Modus eine Sitzung. `GET /v1/me` liefert Benutzer, Mitgliedschaften und das CSRF-Token. Das HttpOnly-Sessioncookie wird vom Browser mitgeführt; für Mutationen das CSRF-Token im Header `X-CSRF-Token` senden. `POST /v1/auth/logout` beendet die Sitzung. Ein Workspace-Parameter ist erst nach Mitgliedschaftsprüfung gültig.

| Endpunkt | Verhalten |
| --- | --- |
| GET/POST `/v1/workspaces` | Eigene Workspaces auflisten/neuen anlegen |
| GET `/v1/workspaces/{ws}/dashboard` | Zähler aus gespeicherten Daten |
| GET/POST `/v1/workspaces/{ws}/contacts` | Paginierte Suche/manueller Kontakt |
| GET/PATCH/DELETE `/v1/workspaces/{ws}/contacts/{id}` | Tenant-geprüfter Einzelkontakt |
| GET `/v1/workspaces/{ws}/companies` | Gespeicherte Unternehmen |
| GET/PUT `/v1/workspaces/{ws}/icp` | Regelprofil lesen/speichern |
| POST `/v1/workspaces/{ws}/imports/preview` | CSV, Mapping und Validierung |
| POST `/v1/workspaces/{ws}/imports/{id}/commit` | Import mit Dublettenprüfung |
| POST `/v1/workspaces/{ws}/imports/{id}/rollback` | Eigene unveränderte Import-Kontakte zurücknehmen |
| GET/POST `/v1/workspaces/{ws}/deals` | Pipeline lesen/Deal anlegen |
| PATCH `/v1/workspaces/{ws}/deals/{id}` | Persistierte Statusänderung |
| GET/POST `/v1/workspaces/{ws}/social/posts` | Social-Entwürfe |
| PATCH `/v1/workspaces/{ws}/social/posts/{id}` | Bearbeitung mit Freigabeinvalidierung |
| POST `…/social/posts/{id}/submit-review` | Zur Prüfung geben |
| POST `…/social/posts/{id}/approve` | Aktuelle Revision freigeben |
| POST `…/social/posts/{id}/schedule` | Interne Planung; kein externes Publishing |
| POST `…/social/posts/{id}/cancel` | Interne Planung abbrechen |
| POST `…/social/captions/generate` | Deterministische Offline-Demo-Vorschläge |
| GET/POST `…/outreach/drafts` | Gespeicherte Entwürfe, kein Versand |
| POST `…/discovery/runs` | Klar gekennzeichnete synthetische lokale Suche |
| POST `…/discovery/runs/{id}/import` | Demo-Ergebnisse übernehmen |
| GET `…/integrations` | Ehrliche nicht verbundene Providerzustände |
| GET `…/audit` | Workspace-Aktivitäten |
| GET `/health/live`, `/health/ready` | Prozess/DB-Bereitschaft |

Listen verwenden `page` und `limit`; konkrete Obergrenzen und Filter stehen in OpenAPI. Fehler verwenden eine einheitliche Problemstruktur statt Stacktraces. Detaillierte Rollenprüfungen sind Backendlogik, keine reine UI-Sperre.

Nicht implementiert: produktive OAuth-Callbacks, Versandschnittstellen, automatisierte LinkedIn-Operationen, Billing-Webhooks und hochgeladene Medien. Diese Endpunkte sind nicht aus dem Zielbrief als vorhanden zu verstehen.
