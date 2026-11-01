# Architektur

Browser → Next.js (`apps/web`, Port3000) → gleiche Origin `/api` → FastAPI (`services/api`, Port8000) → PostgreSQL16. Die API ist die Autorisierungsgrenze. Das Frontend erhält keine DB-Zugangsdaten.

Sitzungen verwenden zufällige Tokens; die Datenbank speichert nur deren Hash. Zustandsänderungen benötigen ein CSRF-Token. Vor Zugriff auf einen Workspace prüft die API die Mitgliedschaft und Rolle. Erst dann wird der transaktionslokale PostgreSQL-Kontext gesetzt. RLS begrenzt auch unbeabsichtigt ungescopte ORM-Abfragen. Eine separate Migrationsrolle besitzt Tabellen; die Laufzeitrolle hat kein BYPASSRLS und darf Audit-Einträge nicht ändern/löschen.

Import, Scoring, Outreach-Entwürfe und Social-Statusübergänge sind lokale Domainlogik. Externe Nebenwirkungen sind nicht Teil der ersten Version. Es gibt keinen laufenden Scheduler und keinen Publisher. Eine intern gespeicherte Planung ist daher kein Versandversprechen.

Begrenzte Imports laufen synchron. Ein dauerhafter Job-Lebenszyklus mit Queue, Outbox und Worker ist Voraussetzung für große Imports und zukünftige Anbieteroperationen. Redis und Objektspeicher werden erst mit diesen Funktionen ergänzt.
