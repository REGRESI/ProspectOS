# Übergabe ProspectOS V3 (Multichannel, LinkedIn-sicher)

Stand 08.11.2026 · Branch `claude/v3-multichannel` (von `claude/cleanstar-linkedin-content`, `92c12e1`) · nichts auf `main`, nichts deployt.

Gebaut und getestet in einer Cloud-Sitzung **ohne** deine Schlüssel, deine Datenbank und ohne Zugang zu OpenAI, Brave, LinkedIn oder OSM. Alles lief gegen synthetische Testdaten und eine Wegwerf-Datenbank.

## (a) Was fertig ist

| # | Was | Wo in der App | Commit |
| --- | --- | --- | --- |
| M1 | Eine Person, ein Datensatz: Kontaktwege (LinkedIn, Post, E-Mail persönlich/allgemein, Telefon) mit Quelle und Datum. Kanal-Weiche: geprüftes Profil → LinkedIn, sonst Postadresse → Brief. Rechtsgrundlage je Kanal, Widerspruch sperrt alles sofort. Duplikate zusammenführen mit Begründung. Schalter „kalte Erst-E-Mail“ (aus) | Kontakt öffnen → Reiter **Kanäle** | `67ed8e8` |
| M2 | Kampagnen-Baukasten: LinkedIn-Aufgabe, Brief, Anruf, Besuch, E-Mail, Warten, Bedingung. Änderungen gelten ab dem nächsten Schritt. Drei Rezepte. Fällige Schritte in Heute | Kontakte → **Ansprache**; **Heute** | `e3b6bc9` |
| M3 | Jede Reaktion (E-Mail-Antwort per IMAP, LinkedIn-Klick, QR-Scan, Anfrage mit Code) stoppt alle geplanten Schritte auf allen Kanälen und legt eine Anruf-/Termin-Aufgabe an. Ein Posteingang mit Status | Heute → **Posteingang** | `94949f4` |
| M4 | Brief nach DIN 5008 im CleanStar-Look, QR-Code je Firma, Sammel-PDF, Etiketten (Zweckform 3474), Druckdienst als Schalter (aus) | Kontakte → **Briefe** | `a8af0b4` |
| M5 | Team: Leads abwechselnd oder nach Gebiet verteilen, eigenes Heute je Person, Tempo je Person (Standard 15/Tag), Annahmequote, Einladungen älter als 3 Wochen | Einstellungen → **Team** | `5a07f5c` |
| M6 | Geführter Start in 5 Schritten bis zur ersten Aufgabe | Einstellungen → **Geführter Start**, Hinweis in Heute | `cddfb5e` |
| M7 | Server-Setup (Caddy/HTTPS, eigene Datenbank, verschlüsseltes Backup außer Haus, Wiederherstellung) und Anleitung | `docs/DEPLOY.md`, `infra/deploy/` | `261069e` |
| M8 | Quellen als Bausteine mit Qualitätsbericht (Treffer, Quote Ansprechpartner, Quote geprüftes LinkedIn, Fehler); Handelsregister-Optionen recherchiert, nicht aktiviert | Firmen → **Quellen** | dieser Commit |

Migrationen **0022 bis 0026**, alle additiv. Neue Python-Pakete: `reportlab`, `fonttools`, `brotli` (für PDF und Schriften).

Bewusste Entscheidung: Eine **angenommene** LinkedIn-Einladung ist eine Reaktion im Posteingang, stoppt die Kampagne aber nicht, sonst käme nie die „Nachricht nach Annahme“. Antworten, QR-Scans, Anfragen und E-Mail-Antworten stoppen alles.

## (b) Was nur gegen Mocks oder synthetische Daten geprüft ist

- **IMAP-Antworten:** Erkennung und Stopp mit einer simulierten Antwort-Mail (bestehender Mail-Test). Kein echtes Postfach.
- **QR-Scan über `/r/<code>`:** lokal geprüft. Öffentlich erreichbar erst mit eigenem Server (M7). Bis dahin zeigt der QR-Code direkt auf eure Website mit `?ref=<code>`; den Code aus einer Anfrage trägst du im Posteingang ein.
- **Briefe:** PDF, QR-Code und Etiketten erzeugt und angesehen, aber **nicht gedruckt**. Bitte einen Probedruck machen: Sitzt die Adresse im Fenster eines DL-Umschlags?
- **Server/Backup:** Backup → Verschlüsselung → Wiederherstellung lokal geprüft (`infra/scripts/test-backup-restore.sh`: 76 Tabellen identisch). Auf einem echten Server lief das noch nie; Caddy, Supabase-Login und rclone sind ungetestet.
- **Druckdienst und Handelsregister-Anbieter:** nur recherchiert, kein Aufruf.
- **Mit deinen echten Daten** lief nichts: weder die Kanal-Weiche auf den 38 CleanStar-Kontakten noch Verteilung oder Briefe.
- Testergebnisse dieser Sitzung: Backend **259 bestanden**, Frontend-Unit 22, E2E siehe `docs/TESTING.md` (Abschnitt V3).

## (c) Am Mac: Branch holen, sichern, migrieren, live testen

Im Terminal im Ordner ProspectOS:

```bash
cd ~/ProspectOS
```

```bash
git fetch origin && git switch claude/v3-multichannel
```

Datenbank-Backup vor den Migrationen:

```bash
mkdir -p data/private/backups && docker compose exec -T db pg_dump -U prospectos -d prospectos -Fc > data/private/backups/prospectos-$(date +%F)-before-v3.dump
```

Neu bauen (neue Python-Pakete), migrieren, starten:

```bash
docker compose build migrate api worker web
```

```bash
docker compose run --rm migrate
```

```bash
docker compose up -d
```

Kanal-Weiche einmal für alle Kontakte berechnen (oder in der App: Kontakte → Ansprache → „Wege neu berechnen“):

```bash
docker compose exec api python -m app.multichannel
```

Falls etwas schiefgeht, zurück auf den alten Stand: `git switch claude/cleanstar-linkedin-content`, Datenbank aus dem Dump wiederherstellen (`pg_restore --clean`), Container neu bauen.

### Live-Checkliste (mit deinen echten Daten)

1. **Status-Seite** (Einstellungen → Status): alles wie vorher grün?
2. **Ansprache → „Wege neu berechnen“:** Wie viele Kontakte bekommen LinkedIn, Brief, keinen Weg? Bei 12 von 38 geprüften Profilen sollten etwa 12 auf LinkedIn landen. Stichproben im Reiter „Kanäle“ prüfen.
3. **Briefe → Einstellungen:** Absender, Telefon, Zielseite (z. B. `https://www.cleanstar-dienstleistungen.de/reinigungs-check/`) eintragen. Einen Brief vorbereiten, als PDF ansehen, **einmal ausdrucken** und in einen Fensterumschlag stecken.
4. **QR-Code mit dem Handy scannen:** Landest du auf der Website mit `?ref=…`? (Gezählt wird der Scan erst mit eigenem Server.)
5. **Rezept „Büro Ortenau mit LinkedIn“** für 2 bis 3 echte Kontakte starten. Erscheinen die Aufgaben in Heute? Eine LinkedIn-Aufgabe ganz normal in LinkedIn erledigen und abhaken.
6. **Posteingang:** Eine echte Antwort-Mail (IMAP verbunden) oder eine LinkedIn-Antwort per Klick eintragen. Werden alle Schritte dieses Kontakts gestoppt und steht „Anrufen und Termin vereinbaren“ in Heute?
7. **Team:** Lino und Eknoor einladen, Gebiete (z. B. „Lahr, 779“) setzen, „Nach Gebiet verteilen“. Sieht jeder nur seine Kontakte in Heute?
8. **Quellen:** Stimmen Treffer und Quoten mit deinem Gefühl überein?

## (d) Was du selbst entscheiden oder klicken musst

- **Kalte Erst-E-Mails** bleiben aus. Freischalten nur nach Rechtsberatung (Kontakt → Kanäle bzw. `PUT /channel-policy`, nur Owner, mit Notiz wer wann beraten hat). Auch dann prüft der Versand weiter die Rechtsgrundlage je Kontakt.
- **Eigener Server (M7):** mieten ja/nein, Domain, Supabase-Projekt (EU) für den Login, Backup-Speicher. Kosten ca. 10 bis 15 € im Monat. Anleitung: `docs/DEPLOY.md`.
- **LinkedIn-App:** bei eigenem Server die neue Redirect-URL `https://<domain>/v1/integrations/linkedin/callback` eintragen.
- **Druck-und-Versand-Dienst:** vorerst selbst drucken; ob Pingen, LetterXpress o. a., entscheidest du nach Preisvergleich und Datenschutzvertrag.
- **Handelsregister-Daten:** North Data ist angebunden und braucht einen kostenpflichtigen Schlüssel; andere Anbieter sind nur gelistet.
- **Limits:** 15 Einladungen pro Person und Tag sind Standard; in Team → Verteilung und Tempo anpassen.
- Das CleanStar-Logo und die Schriften kommen aus `apps/web/public/brand/cleanstar` (Kopie aus `cleanstar-rebrand`). Das Repository `cleanstar-rebrand` selbst konnte in dieser Sitzung nicht angebunden werden; bei neuem Logo die Datei `services/api/app/assets/brand/cleanstar/logo-cropped.png` ersetzen.
