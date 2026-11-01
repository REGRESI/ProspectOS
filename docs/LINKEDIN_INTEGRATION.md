# LinkedIn: aktueller Status und Voraussetzungen

**Nicht verbunden, nicht implementiert.** Die erste Version kann Entwürfe speichern und manuelle Arbeit vorbereiten; sie authentifiziert kein LinkedIn-Profil und sendet keine Kontaktanfragen, DMs oder Beiträge. Kein Cookie-Import, Scraping oder Browser-Bot.

Für produktives Publishing sind eine echte LinkedIn-Developer-App, freigegebene Produkte und tatsächlich gewährte Scopes erforderlich. `w_member_social` allein ersetzt weder eine Produktfreigabe noch zusätzliche Rechte für Organisationsseiten. Profil-API-Daten dürfen nicht ohne entsprechende vertragliche Erlaubnis zu einer Lead-Datenbank werden.

Noch umzusetzen: geprüfte aktuelle OAuth-/API-Dokumentation, Callback-Allowlist, state/nonce mit Ablauf, gegebenenfalls unterstütztes PKCE, verschlüsselte Tokens, Revoke/Refresh, Capability-Prüfung, unveränderliche Freigaberevision, durable Queue/Outbox, idempotente Versuche und Behandlung unklarer Providerantworten. Keine automatische Wiederholung eines möglicherweise erfolgreichen Posts.

Offizielle Ausgangspunkte aus dem Brief; in dieser Implementierung wurden daraus keine funktionierenden API-Verträge behauptet:

- https://learn.microsoft.com/linkedin/consumer/integrations/self-serve/share-on-linkedin
- https://learn.microsoft.com/linkedin/marketing/community-management/shares/posts-api
- https://developer.linkedin.com/legal
- https://www.linkedin.com/help/linkedin/answer/a1341387

Stand dieser Implementierungsnotiz: 01.11.2026. Exakte API-Versionen und Produkte vor Implementierung anhand offizieller aktueller Dokumentation verifizieren.
