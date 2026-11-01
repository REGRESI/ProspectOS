# Datenmodell

SQLAlchemy-Modelle: `services/api/app/models.py`. Versionierte Migrationen: `services/api/alembic/versions`. Vor App-Start `python -m app.migrate` aus `services/api` ausführen. Der Befehl provisioniert ausschließlich in development/test die lokale Laufzeitrolle und führt Alembic aus.

| Bereich | Tabellen und Zweck |
| --- | --- |
| Identität | users, auth_sessions, workspaces, memberships |
| Leads | companies, contacts, import_jobs, icp_profiles |
| Vertrieb | deals, message_drafts, discovery_runs |
| Social | social_posts mit Revision und freigegebener Revision |
| Nachweis | audit_events, append-only für Anwendungsrolle |

Tenant-Tabellen tragen `workspace_id`. Zusammengesetzte Fremdschlüssel verbinden Kontakte mit Unternehmen, Deals und Entwürfe mit Kontakten innerhalb desselben Workspace. Kontakt-URL und Importidentität besitzen Workspace-bezogene Eindeutigkeitsbedingungen. Leere E-Mail/Telefonwerte sind erlaubt. Namen allein sind keine eindeutige Personenidentität.

RLS ist für Tenant-Tabellen erzwungen. Fehlender Workspace-Kontext darf keine Tenant-Zeilen sichtbar machen. Authentifizierungstabellen benötigen andere Zugriffsmuster und sind nicht für direkten Browserzugriff freigegeben. Die Migration ist keine automatische Datenbereinigung und kein Backup.

Grenzen: Das vollständige Zielmodell aus dem Master-Prompt ist nicht implementiert. Unter anderem fehlen Einladungen, private Assets, Consent-Verwaltung, Provider-Verbindungen, Outbox, Rechnungen und vollständige Versionierung aller Objekte. Die echte Quelle bleibt Code plus Migration.
