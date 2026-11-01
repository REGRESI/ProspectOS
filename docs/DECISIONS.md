# Entscheidungen

## 2026-11-01: Ein funktionsfähiger lokaler Kern

Das ursprüngliche Repository war leer. Es wird als modularer Monolith aufgebaut: Next.js App Router im Frontend, FastAPI im Backend und PostgreSQL16 als dauerhafte Datenbank. pnpm verwaltet JavaScript, uv Python. Lockfiles fixieren die tatsächlich aufgelösten Versionen.

Die erste Ausbaustufe konzentriert sich auf Import, Kontakte und Scoring. Zusatzfunktionen werden nur als implementiert geführt, wenn Speicherung und serverseitige Prüfungen existieren. Weitere Integrationen bleiben gesperrt oder klar als lokale Demo gekennzeichnet.

## Keine ungenutzten Infrastrukturkomponenten

Redis, MinIO und Hintergrundworker sind nicht allein zur Erfüllung einer Architekturliste enthalten. Sie folgen erst mit implementierten Queue-/Asset-Workflows. Kleine lokale Importvorgänge sind zunächst synchron und begrenzt. Keine Zusicherung großer Produktionsimporte.

## Lokale Identität und Produktion

Die lokale Anmeldung dient Entwicklung und Tests. Eine Produktionseinführung benötigt verifizierte externe Identität, sichere Schlüsselverwaltung, TLS, Betriebs- und Rechtsprüfung. Der lokale Authentifizierungsmodus muss in Produktion geschlossen bleiben.

## Mandantentrennung

Serverseitige Mitgliedschaftsprüfung plus PostgreSQL RLS mit transaktionslokalem Workspace-Kontext und eigenem eingeschränkten Anwendungsbenutzer. Migrationen laufen separat mit Eigentümerrechten. Für Datenverknüpfungen werden zusammengesetzte Tenant-Fremdschlüssel verwendet.

## Versionen

Node24, Python3.12, pnpm11.25.0 und uv0.12.23 sind in dieser Umgebung verfügbar. PostgreSQL16.11 wurde als lokales Container-Image gestartet und abgefragt. Weitere Versionen sind den Lockfiles zu entnehmen; dies ist kein Versprechen über zukünftige Anbieter-APIs.
