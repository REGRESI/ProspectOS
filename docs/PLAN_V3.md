# ProspectOS V3: Bestandsaufnahme und Umsetzungsplan

Stand 08.11.2026, Branch `claude/v3-multichannel` (abgezweigt von `claude/cleanstar-linkedin-content`, `92c12e1`). Grundlage: Bauplan „ProspectOS V3“ vom 08.11.

## Arbeitsumgebung dieser Sitzung

- Cloud-Container ohne Docker-Daemon, ohne `.env`, ohne echte Daten. PostgreSQL 16 läuft lokal; Tests laufen über `infra/scripts/validate_database.py` (eigene Wegwerf-Datenbank).
- Der isolierte E2E-Stack (`docker-compose.e2e.yml`) braucht Docker. Hier wird er mit denselben Umgebungsvariablen nachgebildet: eigene Datenbank `prospectos_e2e`, API auf 8100, Web auf 3100 (Skript `infra/scripts/e2e-local.sh`, neu).
- Externe Dienste (OpenAI, Brave, LinkedIn, OSM, Druckdienste) sind nicht erreichbar. Alles Externe wird gegen Mocks geprüft und in `docs/STATUS.md` so markiert.

## Bestandsaufnahme

| Bereich | Gibt es schon | Halb fertig | Fehlt für V3 |
| --- | --- | --- | --- |
| Kontakt-Datensatz | `contacts` mit Firma, Rolle, E-Mail, Telefon, LinkedIn-URL; Profilprüfung `linkedin_status` (verified/confirmed/unsure/not_found) mit Begründung; `owner_id` | Postadresse und allgemeine E-Mail/Telefon liegen nur als Firmen-Fakten (Impressum, OSM) vor, nicht am Kontakt; keine Quelle/Datum je Feld | Kontaktpunkte je Kanal mit Quelle und Datum; Zusammenführen von Duplikaten mit Begründung |
| Kanal-Weiche | – | LinkedIn-Routine „Heute“ nimmt Kontakte mit Profil | Genau ein aktiver Weg je Kontakt (LinkedIn oder Brief), automatisch und manuell |
| Rechtsgrundlage | `consents` mit Kanal, Nachweis, Ablauf; E-Mail-Regeln je Land (`email_outreach.eligibility`), Prüfung bei Planung und Versand | Kanal-Feld wird nur für E-Mail genutzt | Regeln je Kanal: Brief (zulässig ohne Widerspruch), Telefon (konkretes Interesse mit Anlass), Besuch; Schalter „kalte Erst-E-Mail“ (aus) |
| Widerspruchsliste | `suppressions`; sperrt E-Mail und Heute | – | Sperre aller Kanäle inkl. neuer Schritte, Briefe, Aufgaben |
| Kampagnen | `campaigns`, Enrollment, `campaign_sequence_steps` (LinkedIn manuell/E-Mail, Verzögerung), E-Mail-Kampagne mit Hochlauf | Sequenz ist nur Planung | Baukasten mit Brief, Anruf, Besuch, Warten, Bedingung; Läufe je Kontakt; Rezepte; fällige Schritte in „Heute“ |
| Reaktionen | IMAP-Abruf erkennt Antwort/Bounce/Beschwerde und stoppt geplante E-Mails; LinkedIn-Stufen per Klick; Antwortanalyse | Stopp gilt nur für E-Mail | Kanalübergreifender Stopp, Anruf-/Termin-Aufgabe, ein Posteingang mit Status |
| Brief | – | – | DIN-5008-Brief, QR-Code je Firma, Sammel-PDF, Etiketten, Druckdienst-Adapter (aus) |
| Team | Einladungen, Rollen, `owner_id` am Kontakt, LinkedIn-Verbindung je Nutzer (`connections.user_id`) | „Heute“ ist pro Workspace, nicht pro Person | Verteilung (abwechselnd/Gebiet), eigenes Heute, Tempo-Anzeige je Person |
| Onboarding | Workspace-Einrichtung (Angebot, Region, Zielgruppe), Status-Seite | – | Geführter Start in 5 Schritten bis zur ersten Kampagne aus Rezept |
| Betrieb | Compose (lokal, E2E, Produktionsbeispiel), Migrator getrennt, Healthchecks | Kein HTTPS-Proxy, kein Backup | Caddy, verschlüsseltes Backup außer Haus, getestete Wiederherstellung, `docs/DEPLOY.md` |
| Lead-Quellen | OSM (Overpass + lokaler Extrakt), North Data (lizenziert), Impressum-Recherche, Brave-Profilprüfung, CSV mit Zuordnung | Quellen haben keine gemeinsame Schnittstelle | Quellen-Register und Qualitätsbericht je Quelle |
| Content/Posten, Kostenkonto, Autopilot | Vorhanden, live genutzt | – | Nicht anfassen, nur nicht kaputt machen |

## Umsetzungsplan

Jeder Meilenstein: additive Migration, Backend mit Tests, UI, E2E auf dem lokal nachgebildeten isolierten Stack, Screenshots nach `docs/design/v3/`, Commit, Push.

- **M1 Kontakt-Kern und Kanal-Weiche** (`app/multichannel.py`, Migration 0022): Tabelle `contact_points` (Kanal, Wert, Art persönlich/allgemein, Quelle, Quell-URL, Datum, geprüft). Übernahme aus Kontaktfeldern und Firmen-Fakten (Impressum, OSM). Feld `channel_route` (linkedin/letter/none) mit Grund und Herkunft (auto/manuell). Regeln: geprüftes Profil → LinkedIn, sonst Postadresse → Brief, sonst keiner. Rechtsgrundlage je Kanal über `consents.channel`; Funktion `channel_permissions()` als einzige Quelle für alle Kanäle; Widerspruch sperrt alles. Duplikatvorschläge und Zusammenführen mit gespeicherter Begründung.
- **M2 Kampagnen-Baukasten** (Migration 0023): `flow_steps` (Art, Weg-Filter, Tage, Vorlage, Bedingung mit Sprungziel), `flow_runs` je Kontakt, `flow_tasks` als fällige Aufgaben. Der Lauf liest Schritte immer frisch, Änderungen gelten ab dem nächsten Schritt. Drei Rezepte. „Heute“ zeigt fällige Aufgaben.
- **M3 Stopp bei Reaktion** (Migration 0024): `reactions` mit Status; Quellen: IMAP-Antwort, LinkedIn-Klick, QR-Scan, Code aus Anfrage. Jede Reaktion stoppt Läufe, Aufgaben, geplante E-Mails und Heute-Einträge und legt eine Anruf-Aufgabe plus Telefon-Rechtsgrundlage „konkretes Interesse“ an. Posteingang.
- **M4 Brief-Kanal** (Migration 0025): Brief nach DIN 5008 Form B als PDF (reportlab), QR-Code mit Code je Firma, Sammel-PDF, Etiketten (Zweckform 3474, 3×8). Öffentlicher Endpunkt `/r/<code>` speichert den Scan und leitet weiter. Druckdienst als Adapter hinter Schalter (aus), Optionen recherchiert und dokumentiert.
- **M5 Team-Modus** (Migration 0026): Verteilung abwechselnd oder nach Gebiet, Heute und Aufgaben je Person, Tempo je Person (Standard 15 Einladungen/Tag), Annahmequote, offene Einladungen älter als 21 Tage.
- **M6 Einfach wie Waalaxy**: geführter Start in 5 Schritten, leere Zustände mit nächstem Schritt.
- **M7 Cloud-Betrieb vorbereiten**: Produktions-Compose mit Caddy, Backup-Skript (verschlüsselt, außer Haus per rclone), Wiederherstellungstest, `docs/DEPLOY.md`. Nichts mieten, nichts deployen.
- **M8 Lead-Quellen**: Quellen-Register mit gemeinsamer Schnittstelle und Qualitätsbericht je Quelle; Handelsregister-Anbieter recherchiert, nicht aktiviert.

## Grenzen (unverändert)

Keine LinkedIn-Automatisierung, kein E-Mail-Versand ohne dokumentierte Rechtsgrundlage, kalte Erst-E-Mails standardmäßig aus, kein Google-Maps-Scraping, keine echten Daten oder Schlüssel in Git.
