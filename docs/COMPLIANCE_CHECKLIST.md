# Datenschutz und zulässige Nutzung

Dies ist eine technische Entwicklungscheckliste und keine Rechtsfreigabe.

| Kontrolle | Lokaler Stand |
| --- | --- |
| Keine Bots/Scraper/automatischen LinkedIn-DMs | kein solcher Versandpfad vorhanden |
| Unbekannte E-Mails, Größe, Bedarf bleiben unbekannt | Datenmodell/Scoring berücksichtigen fehlende Fakten |
| Entwurf ist keine Sendeerlaubnis | Entwürfe besitzen keinen Versand-Nebeneffekt |
| Synthetische Daten kennzeichnen | Demo-/Offline-Quellen sichtbar halten |
| Mandantentrennung | API-Mitgliedschaft, Rollen, RLS, Tenant-FKs; Tests siehe TESTING |
| Realdateien nicht committen | `data/private/` ignoriert; keine echten CSV-Daten enthalten |
| Marketingnachweis vor Versand | Versand nicht implementiert; Consent-/Suppression-Gate noch zu bauen |
| DSGVO-Auskunft, Export, Löschung, Retention | vollständiger operativer Prozess noch offen |
| Auftragsverarbeitung, Hostingregion, TOMs, Rechtsgrundlage | vor Pilot-/Produktionsbetrieb organisatorisch prüfen |

Öffentliche Profile, LinkedIn-Verbindungen, Open-/Premium-Flags oder ein verfügbarer E-Mail-Wert sind kein dokumentiertes Einverständnis für Werbung. Deutschland/EU-Regeln erfordern eine konkrete rechtliche Bewertung. Vor externem Versand müssen dokumentierte zulässige Grundlage, Kanalscope, Widerruf/Sperrlisten und letzte Autorisierung technisch erzwungen werden.
