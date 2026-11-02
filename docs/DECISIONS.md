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

## 2026-11-02: Incremental production-oriented extension

Keep d103f23 workflows and database records. Add isolated migration credentials, verified Supabase identity, private raster assets, durable PostgreSQL jobs, source-grounded provider adapters, CRM/campaigns, commercial policy and privacy primitives. PostgreSQL queues avoid introducing an unused Redis service; a private filesystem volume is an explicit local-storage tradeoff rather than a false S3 claim.

External paid/delivery requests require configuration and explicit authorization. Ambiguous requests never report success or retry blindly. AI reservations use USD cents and explicit operator pricing, not fictional prices. Official SDK source contracts were checked via provider-owned GitHub repositories because several documentation domains were policy-blocked. Live approval/credential tests remain outstanding.

Security audit identified vulnerable initial cryptography/Pillow constraints; upgraded to authoritative current fixed PyPI releases cryptography50.0.2 and Pillow13.0.0, with lockfile verification and runtime audit repeated. A moderate ESLint development dependency advisory remains documented; the standalone web runtime excludes development tooling.
