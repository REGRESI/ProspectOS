# Externe Outreach-Tools und Register (M9)

Stand: 2026-11-08. Code: `services/api/app/connectors.py` (Rahmen, Übergaben, Webhooks) und
`services/api/app/providers/outreach_tools.py` (Adapter). Tests: `tests/test_m9_connectors.py`
(alle HTTP-Aufrufe gemockt) und `apps/web/tests/e2e/m9-connectors.spec.ts`.

## Grenze

ProspectOS selbst automatisiert LinkedIn nie: keine eigenen Einladungen oder Nachrichten, kein
Zugriff auf LinkedIn-Sitzungen oder Cookies, keine Emulation, keine Proxys, kein Scraping von
linkedin.com. M9 spricht ausschließlich mit den offiziellen Schnittstellen von Drittanbietern, bei
denen der Nutzer selbst ein Konto hat. Diese Tools automatisieren LinkedIn über das Konto des
Nutzers. Das verstößt gegen die LinkedIn-Nutzervereinbarung. Deshalb gilt:

- Produktschalter `EXTERNAL_OUTREACH_TOOLS_ENABLED` (Standard `false`). Ist er aus, gibt es keine
  Seite, keine Übergabe und keinen Webhook (404).
- Pro Workspace aus. Nur der Owner schaltet ein, und nur nach Bestätigung des genauen Hinweistexts.
  Name, Zeit und Text landen im Verlauf (`external_tools_enabled`). Ausschalten geht jederzeit;
  danach sind neue Übergaben gesperrt.
- Schlüssel liegen mit `TOKEN_ENCRYPTION_KEY` verschlüsselt in `outreach_connectors` und werden nie
  wieder angezeigt (nur maskiert).

## Ablauf einer Übergabe

1. Prüfung (beim Anlegen und erneut beim Versand im Worker): Funktion an, Tool verbunden und aktiv,
   kein Widerspruch/Sperrliste, geprüftes LinkedIn-Profil, keine andere aktive Übergabe, Weg nicht
   „Brief“, keine freigegebene manuelle LinkedIn-Aufgabe in Heute.
2. Gesendet werden nur Vorname, Nachname, Firma, Position und LinkedIn-URL. E-Mail nur, wenn die
   E-Mail-Rechtsgrundlage dokumentiert ist (`email_outreach.eligibility`).
3. Versand über die dauerhafte Job-Warteschlange (`connector_push`). Unklare Ergebnisse
   (Verbindungsabbruch nach dem Senden) werden als „unklar, im Tool prüfen“ markiert, nie blind
   wiederholt.
4. Danach: Weg „Externes Tool“, keine manuellen LinkedIn-Aufgaben (Heute und Baukasten überspringen
   sie), keine doppelte Ansprache.
5. Rückmeldungen (Webhook): Annahme → Reaktion „Einladung angenommen“; Antwort → Stopp auf allen
   Kanälen und Anruf-/Termin-Aufgabe (M3-Logik). Gesendete Einladungen zählen in der Tempo-Ansicht
   (M5) als `tool_invites_24h/7d`.
6. Reaktion woanders (Brief-QR, E-Mail, Anruf) oder Weg von Hand geändert → Pause im Tool
   (`connector_pause`), oder, wenn die API das nicht kann, Aufgabe „In <Tool> stoppen“.

Eingehende Webhooks: `POST /v1/hooks/<workspace>/<geheimnis>`. Das Geheimnis wird einmal angezeigt
und nur als SHA-256 gespeichert; „Neue Webhook-Adresse“ macht die alte ungültig. Max. 256 KB.
Ereignisse werden pro Tool über die Ereignis-ID entdoppelt. Der allgemeine Webhook verlangt
zusätzlich eine HMAC-SHA256-Signatur (`X-ProspectOS-Signature: sha256=…` über
`<timestamp>.<body>`, `X-ProspectOS-Timestamp` höchstens 5 Minuten alt). Ausgehende Aufrufe an
Nutzer-URLs (allgemeiner Webhook, Expandi-Kampagnen-URL) laufen über den Egress-Schutz
(`web_guard`): nur https, nur öffentliche Adressen, IP festgenagelt, keine Umleitungen.

## Anbieter: was geprüft ist und was nicht

„Geprüft“ heißt: in der öffentlichen Doku des Anbieters am 2026-11-08 gelesen und so umgesetzt.
Kein Adapter wurde gegen ein echtes Konto getestet. „Unverifiziert“ heißt: Annahme, vor dem ersten
Echteinsatz mit dem Testknopf und einem Testkontakt prüfen. Preise sind nicht geprüft.

### HeyReach

Quelle: Postman-Sammlung „HeyReach API“ (documenter.getpostman.com, Sammlung 23808049), help.heyreach.io.

| Funktion | Endpunkt | Status |
| --- | --- | --- |
| Auth | Header `X-API-KEY`, 300 Anfragen/Minute | geprüft |
| Test | `GET /api/public/auth/CheckApiKey` | geprüft |
| Kampagnen | `POST /api/public/campaign/GetAll` (offset, limit ≤ 100) | geprüft |
| Kontakte hinzufügen | `POST /api/public/campaign/AddLeadsToCampaignV2` mit `accountLeadPairs` (LinkedIn-Konto-ID + Lead), max. 100; Kampagne muss einmal gestartet worden sein | geprüft |
| Stoppen | `POST /api/public/campaign/StopLeadInCampaign` (campaignId, leadUrl) | geprüft |
| Status | `POST /api/public/lead/GetLead` (profileUrl) | geprüft |
| Webhooks anlegen | `POST /api/public/webhooks/CreateWebhook`, Ereignisse u. a. CONNECTION_REQUEST_SENT/ACCEPTED, MESSAGE_SENT, MESSAGE_REPLY_RECEIVED | geprüft (Anlegen von Hand im Tool) |
| Basis-Host `https://api.heyreach.io` | Sammlung nutzt `baseUrl` „/“ | **unverifiziert** |
| Webhook-Inhalt (Feldnamen) | nicht dokumentiert; Parser liest tolerant `eventType`, `lead.profileUrl`, `message` | **unverifiziert** |
| Webhook-Signatur | nicht dokumentiert; Schutz nur über geheime URL | — |

### lemlist

Quelle: developer.lemlist.com (Seiten mit `.md`-Endung).

| Funktion | Endpunkt | Status |
| --- | --- | --- |
| Auth | Basic, leerer Benutzer, API-Key als Passwort; 20 Anfragen / 2 s | geprüft |
| Test | `GET /api/team` | geprüft |
| Kampagnen | `GET /api/campaigns` | geprüft |
| Kontakt anlegen | `POST /api/campaigns/{id}/leads/?deduplicate=true` (linkedinUrl, firstName, lastName, companyName, jobTitle, email); Antwort `_id` (lea_…); nur Neuanlage | geprüft |
| Pausieren | `POST /api/leads/pause/{leadId}?campaignId=` | geprüft |
| Status | `GET /api/leads?id=` | geprüft |
| Webhooks | `POST /api/hooks` (targetUrl, type, campaignId, secret); Ereignisse linkedinInviteDone, linkedinInviteAccepted, linkedinSent, linkedinReplied | geprüft |
| Webhook-Anlage durch ProspectOS | nicht gebaut; Adresse wird im Tool eingetragen | — |

### Waalaxy

Quelle: docs.waalaxy.com/introduction (die API-Referenz ist eine reine JavaScript-Seite und war nicht lesbar).

| Funktion | Endpunkt | Status |
| --- | --- | --- |
| Auth | `Authorization: Bearer`, Basis `https://api.waalaxy.com` | geprüft |
| Test | `GET /integrations/test` | geprüft |
| Listen / Kampagnen | `GET /prospectLists/getProspectLists`, `GET /campaigns/getAll` | geprüft |
| Kontakte hinzufügen | `POST /prospects/addProspectFromIntegration` ({prospects:[{url}], prospectListId, campaignId?, origin}) | geprüft |
| Pausieren | nicht dokumentiert → Aufgabe „In Waalaxy stoppen“ | **unverifiziert / nicht gebaut** |
| Webhooks | nicht dokumentiert → Rückmeldung nur über Zapier/Make an den allgemeinen Webhook | **unverifiziert** |

### La Growth Machine

Quelle: help.lagrowthmachine.com (Artikel zur API).

| Funktion | Endpunkt | Status |
| --- | --- | --- |
| Kontakt anlegen | `POST https://apiv2.lagrowthmachine.com/flow/leads`, Key als `x-api-key` | geprüft |
| Pflichtfelder | linkedinUrl genügt (alternativ E-Mail oder Name + Firma); ProspectOS erfindet nie Platzhalter-E-Mails | geprüft |
| API-Verfügbarkeit | ab Pro-Tarif | geprüft (laut Hilfe-Seite) |
| Test-Endpunkt | keiner dokumentiert; Test prüft nur das Schlüsselformat | **unverifiziert** |
| Pausieren | nicht dokumentiert → Aufgabe „In La Growth Machine stoppen“ | **unverifiziert** |
| Webhooks | im Pro-Tarif erwähnt, Inhalt nicht dokumentiert | **unverifiziert** |

### Expandi

Quelle: help.expandi.io Artikel 5405654 (Reversed Webhooks) und 5405651 (Webhook-Ereignisse).

| Funktion | Endpunkt | Status |
| --- | --- | --- |
| Kontakt hinzufügen | `POST` an die Webhook-URL der Kampagne (aus dem Reiter „Webhooks“), Body `profile_link`, `company_name` | geprüft |
| Pausieren | `GET https://api.liaufa.com/api/v1/open-api/campaign-contact/{id}/pause/?key=&secret=`; die Kontakt-ID kommt nur aus einem Webhook-Ereignis | geprüft; ohne Ereignis → Aufgabe „In Expandi stoppen“ |
| Ereignisse | Contact replied, Connection request accepted, Connection request sent, Message sent u. a. | geprüft (Namen) |
| Feldnamen im Webhook-Inhalt | Parser liest tolerant `hook.event`, `contact.profile_link`, `campaign_instance_contact.id`, `messenger.last_message` | **unverifiziert** |

### Allgemeiner Webhook (Zapier, Make, n8n)

Eigenes Format, vollständig getestet. Ausgehend: `contacts.handoff` und `contact.pause` als JSON,
signiert wie oben. Eingehend: `{event, linkedin_url, external_id, text, id}` oder
`{events: [...]}` mit `event` ∈ invite_sent, accepted, message_sent, replied.

## Was nur gegen Mocks läuft

Alle fünf Anbieter-Adapter. Kein echter API-Aufruf ist erfolgt; im Cloud-Container waren nur die
Doku-Seiten erreichbar, nicht die APIs. Vor dem ersten Einsatz pro Tool: verbinden, „Testen“, einen
synthetischen oder eigenen Kontakt übergeben, im Tool nachsehen, Webhook-Adresse eintragen und ein
Ereignis auslösen.

## Berufsregister (M9e): nur Links, keine automatische Abfrage

Im Firmenprofil stehen Links auf die Suchseiten und der Suchbegriff (Firmenname + Ort) zum
Kopieren. ProspectOS fragt diese Register nicht automatisch ab: Ihre Nutzungsbedingungen für
automatisierte Abfragen wurden nicht geprüft (die Seiten waren aus dem Cloud-Container nicht
erreichbar). Solange das so ist, bleibt es bei der Suche von Hand. Gefundene Namen mit Quelle und
Datum als Kontakt eintragen.

| Register | Link (Startseite) | Passt zu | Status |
| --- | --- | --- | --- |
| Arztsuche der KV Baden-Württemberg | https://www.arztsuche-bw.de/ | Praxis | URL **unverifiziert**, keine Abfrage |
| Bundesweites Amtliches Anwaltsverzeichnis (BRAK) | https://www.bea-brak.de/bravsearch/index.brak | Kanzlei | URL **unverifiziert**, keine Abfrage |
| Steuerberaterverzeichnis (Bundessteuerberaterkammer) | https://www.bstbk.de/de/steuerberatersuche | Kanzlei | URL **unverifiziert**, keine Abfrage |
| Betriebssuche der Handwerkskammer (Freiburg) | https://www.hwk-freiburg.de/betriebssuche | Handwerk | URL **unverifiziert**, keine Abfrage |

Vorbelegte Such-Parameter (Name/Ort direkt in der URL) sind nicht gebaut, weil die
Parameternamen nicht geprüft werden konnten. Vor dem Einsatz: Links einmal im Browser öffnen,
falsche URLs in `services/api/app/register_gap.py` (`REGISTERS`) korrigieren, Nutzungsbedingungen
lesen. Eine automatische Abfrage kommt nur in Frage, wenn die Bedingungen sie ausdrücklich
erlauben.

Nicht gebaut und nicht vorgesehen: Scraper für Gelbe Seiten, Das Örtliche, Google Maps, North
Data oder andere Datenanbieter (auch keine Apify-Actors). North Data nur über die lizenzierte Data
API (`app/providers/northdata.py`).

## Website-Finder (M9e)

Brave-Websuche „"Firmenname" Ort“ mit dem Brave-Schlüssel des Nutzers. Verzeichnisse, Social
Media und Registerportale werden übersprungen, nie abgerufen. Für höchstens drei Kandidaten läuft
die normale Impressum-Recherche (robots.txt, Egress-Schutz). Übernommen wird eine Website nur, wenn
das Impressum den Firmennamen (mind. 60 % der unterscheidbaren Wörter) und die bekannte Adresse
(PLZ und Straße) zeigt. Jede Firma bekommt im Bericht einen Grund. Bis zu 25 Firmen je Lauf; jede
Suche kostet eine Brave-Anfrage.
