# Umsetzung

Die Grundlage ist der Master-Prompt v1 vom 01.11.2026. Die Entwicklung erfolgt in zusammenhängenden, prüfbaren Funktionsbereichen. Der gesamte SaaS-Umfang ist kein abgeschlossener Produktionsstand.

| Phase | Ziel | Status |
| --- | --- | --- |
| S0 | Next.js, FastAPI, PostgreSQL, lokale Anmeldung, Workspaces, Rollen, RLS | lokaler Kern implementiert; produktive Auth/Teamverwaltung offen |
| S1 | CSV-Vorschau/Import, Kontakte, Unternehmen, nachvollziehbares ICP-Scoring | implementierter begrenzter CSV-/Kontaktkern; Details STATUS.md |
| S2 | Social-Entwürfe, Freigaben, interne Planung | teilweise: Entwürfe/Freigaben/interne Planung, ohne Assets/Worker |
| S3 | Synthetische Discovery, Outreach-Entwürfe, CRM | teilweise: synthetische Discovery, Entwürfe, einfache Deals |
| S4 | Produktive Identität, lizenzierte Anbieter, echtes OAuth/Publishing, Abrechnung | außerhalb dieses ersten Kerns |

Pflichtprüfungen: Migration einer neuen PostgreSQL-Datenbank; API-Tests mit echtem PostgreSQL; Mandantentrennung, Import und Reimport; Frontend-Typprüfung, Lint, Tests, Build; Browser-Durchlauf der Kernfunktionen. Docker-Gesamtstack separat prüfen. Externe API-Operationen sind ohne geprüfte Zugangsdaten nicht Bestandteil der lokalen Demo.

Die beobachteten Ergebnisse und die tatsächlich erreichten Abnahmebedingungen stehen am Ende in [STATUS.md](STATUS.md) und [TESTING.md](TESTING.md).
