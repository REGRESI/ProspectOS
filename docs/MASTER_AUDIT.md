# Abgleich mit dem Master-Prompt

Ausgangspunkt dieser Fortsetzung: Commit `d103f23` (`feat/prospectos-local-pilot`). Grundlage: **ProspectOS_Codex_Master_Prompt_v1.md**, Version1.0 vom 01.11.2026, vom Nutzer als Produktspezifikation angenommen. Der Upload ist eine Anforderungsquelle, kein Nachweis implementierter Funktionen.

## Baseline vor Erweiterung

| Anforderung / Epic | In d103f23 beobachtet | Fehlender Teil |
| --- | --- | --- |
| S0 / PRO-001–004 | Lockfiles, Next/FastAPI/Postgres, Docker, CI, lokaler Build | Produktionskonfiguration und getrennte Migrationsrechte |
| Identität / PRO-010–013 | Argon2-Demoauth, Workspaces, Rollen, RLS, Audit | Supabase/JWKS, Einladungen, Produktionslogin |
| Leads / PRO-020–024 | CSV-Vorschau/Mapping, 773-Zeilen-Test, Reimport, Rollback, ICP, einfache Deals | XLSX, sichere Exporte, vollständige Feldherkunft, Aufgaben/Kampagnen |
| Discovery / PRO-030–034 | Gekennzeichnete synthetische Suche und Übernahme | Lizenzierter realer Anbieter, geprüfte Website-Recherche, dauerhafte Jobs |
| KI/Outreach / PRO-040–044 | Deterministische Offline-Vorschläge und Entwürfe ohne Versand | Echter Gateway, Budgets/Ledger, Kampagnen, manuelle Aktivitäten, Consent-Verwaltung |
| Social / PRO-050–054 | Entwürfe, Revisionsfreigaben, interne Terminplanung | Markenprofile, private geprüfte Medien, Templates, Medienanbindung und Worker |
| LinkedIn / PRO-060–063 | Ehrlich nicht verbunden, kein externer Versand | OAuth, verschlüsselte Tokens, geprüfte Scopes, offizieller Publisher mit Reconciliation |
| SaaS / PRO-070–073 | Lokale Audit-Ereignisse | Echte Usage, Privacy-Prozesse, sichere Billing-Grundlage und Betrieb |
| Qualität / PRO-080–082 | 25 Backend-, 5 Frontend-, 3 E2E-Tests laut Übergabe | Zusätzliche Sicherheits-/Provider-/Workerprüfungen und erneute Integration nach Erweiterungen |

## Ausführung dieser Fortsetzung

Die Erweiterungen werden erneut als zusammenhängende Workflows geprüft. Als umgesetzt gelten nur Code plus tatsächliche Test-/Laufzeitbeobachtung. Neue Anbindungen ohne Betreiberzugang oder Providerfreigabe sind **implementiert, unverbunden und extern unbestätigt**, niemals live verifiziert. Ergebnisse: [TESTING.md](TESTING.md), Funktionsinventar: [STATUS.md](STATUS.md).

Architekturabweichungen werden in DECISIONS dokumentiert. Insbesondere PostgreSQL als dauerhafte Jobqueue und privater lokaler Dateispeicher ersetzen im ersten Ausbau Redis/MinIO; daraus folgt keine zugesicherte Mehrhost-/S3-Skalierung.

## Repository und Veröffentlichung

Der ursprüngliche Remote war leer. Der lokale Pilot und die ersten Erweiterungen wurden regulär ohne Force-Push auf `feat/prospectos-local-pilot` übertragen. Während der Arbeit kam Remote-Commit `d166d55` mit einem GitHub-Pages-Workflow hinzu; er wurde per Fast-forward übernommen und unverändert erhalten.

Dieser Workflow veröffentlicht bei Push auf den Pilot-Branch. Da keine Veröffentlichung autorisiert ist, werden die finalen Erweiterungen auf dem davon abgeleiteten Review-Branch `feat/prospectos-production-mvp` gesichert und gepusht. Der Pilot-Branch bleibt unverändert; er kann als PR-Basis dienen. GitHub-API-Zugriff auf `api.github.com/graphql` liefert in der aktuellen Umgebung jedoch `Forbidden`; ein PR wird daher nicht als erstellt behauptet.

Keine Force-Pushes, kein neuer `main`, keine Cloud-Konfigurationsänderung und keine Anwendung-/Cloud-Snapshot-Veröffentlichung. Frühere gespeicherte Startanweisungen sind historische Konfiguration; die versionierte Anleitung im README beschreibt die neue Migrator-/Worker-Struktur.
