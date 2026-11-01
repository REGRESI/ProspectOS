# Sicherheit und Bedrohungsmodell

Geschützte Werte: Kontaktdaten, Workspace-Zuordnung, Sitzungen und Audit-Historie. Hauptbedrohungen: fremde Objekt-IDs, Rolleneskalation, CSRF, gestohlene Sitzungen, übergroße/missgebildete Dateien und Täuschung durch unbekannte Daten.

Der lokale Kern verwendet Argon2-Passworthashes, zufällige serverseitige Sitzungen mit Hashspeicherung, HttpOnly/SameSite-Cookies und CSRF-Prüfung bei zustandsändernden Anfragen. Mitgliedschaften und Rollen werden serverseitig geprüft. PostgreSQL nutzt eine eigene Laufzeitrolle ohne BYPASSRLS; Tenant-Kontext gilt nur transaktionslokal. Der Browser erhält weder Administrator-DB-Zugang noch Provider-Token.

Audit-Ereignisse sind für die Laufzeitrolle append-only. Migrationen laufen separat als Eigentümer und sind keine Endnutzerfunktion. CSV-Größe und Zeilen werden begrenzt; Importdaten sind weiterhin vertraulich zu behandeln.

Im lokalen Compose startet der API-Container vor dem Server die Migration. Deshalb enthält seine Prozessumgebung auch die Administrator-DSN. Die normalen SQLAlchemy-Anfragen nutzen nachweislich die eingeschränkte Anwendungsrolle, aber diese lokale Anordnung schützt nicht vor einer vollständigen Kompromittierung des API-Prozesses. Für Produktion muss ein eigener privilegierter Migrationsjob eingerichtet und jede Administrator-DSN aus der Anwendungsumgebung entfernt werden. Der aktuelle Server verweigert Produktionsstart.

Grenzen: Lokale Authentifizierung ist keine freigegebene Produktionsidentität. Es fehlen vollständiges Security-Audit, verteilte Rate-Limits, Produktionsschlüsselverwaltung, Penetrationstest, umfassendes Privacy-/Retention-System und externe Integrationsprüfungen. Kein Produktionsbereitschaftsversprechen.

Vor Produktivbetrieb: externe verifizierte Identität, HTTPS und Secure-Cookies, restriktive Origins/CSP, Passwort-/Session-/Rate-Limit-Policy, minimale DB-Rechte kontrollieren, verschlüsselte Backups mit Restore-Test, Abhängigkeitsprüfung und Incident-Runbook. Nie Standard-Entwicklungspasswörter wiederverwenden.
