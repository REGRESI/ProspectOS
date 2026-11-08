# Übergabe M9 – Externe Outreach-Tools, Datenlücken, Design-Benchmark

Stand 2026-11-08 · Branch `claude/v3-m9-connectors` (baut auf `claude/v3-multichannel` auf, nicht
auf `main`). Migrationen 0027 und 0028, beide additiv. Details: [STATUS.md](STATUS.md) (Abschnitt
M9), [CONNECTORS.md](CONNECTORS.md), [design/BENCHMARK.md](design/BENCHMARK.md).

Commits: `6f2590f` (M9a–c Backend), `ff1a358` (M9a–c UI/Doku/E2E), `45e071f` (M9d/e),
`ad39e66` (M9f) und der Abschluss-Commit mit dieser Datei.

## (a) Was fertig ist (getestet mit synthetischen Daten)

**M9a Anschluss-Rahmen**
- **Wo:** Einstellungen → Anschlüsse.
- **Schalter:** Produktschalter `EXTERNAL_OUTREACH_TOOLS_ENABLED` ist standardmäßig aus.
- **Einschalten:**
  - je Workspace nur durch den Owner;
  - nur nach Bestätigung des genauen Risikotexts im Dialog;
  - Name, Zeit und Text gehen in den Verlauf.
- **Ausschalten** geht jederzeit.
- **Schlüssel** liegen verschlüsselt (`TOKEN_ENCRYPTION_KEY`) und werden nur maskiert angezeigt.
- **Prüfen:** Verbindungstest je Tool, Ampel auf der Status-Seite.

**M9b Adapter**
- **Tools:** HeyReach, Waalaxy, La Growth Machine, Expandi, lemlist und ein allgemeiner Webhook.
- **Gemeinsame Schnittstelle:** `push_contacts`, `pause_contact`, `fetch_status`, `parse_webhook`.
- **Eingehende Webhooks:** `/v1/hooks/<workspace>/<geheimnis>`.
  - Das Geheimnis wird nur als Hash gespeichert und einmal angezeigt.
  - Beim allgemeinen Webhook ist eine HMAC-Signatur Pflicht, höchstens 5 Minuten alt.
- **Ausgehend:** Aufrufe an selbst eingetragene URLs laufen durch den Egress-Schutz (nur öffentliche Adressen).
- **In der Oberfläche je Tool:** Preis-Hinweis (ungeprüft), Doku-Link, was es kann und was nicht.

**M9c Einbindung**
- **Weg „Externes Tool“** gibt es nur für Kontakte mit geprüftem LinkedIn-Profil.
- **Übergeben:** im Reiter „Kanäle“ oder als Baukasten-Schritt „An Tool übergeben“ (Tool + Ziel-Kampagne).
- **Prüfungen** vor jeder Übergabe und erneut beim Versand: Widerspruch, Sperrliste, kein anderer aktiver Weg, Tool aktiv.
- **Gesendet werden** nur Name, Firma, Position und LinkedIn-URL. E-Mail nur mit E-Mail-Rechtsgrundlage.
- **Danach** gibt es keine manuellen LinkedIn-Aufgaben mehr für diesen Kontakt.
- **Rückmeldungen des Tools** gehen in die Reaktionslogik:
  - eine Antwort stoppt alles und legt die Anruf-Aufgabe an;
  - eine angenommene Einladung wird vermerkt.
- **Reaktion woanders oder Weg von Hand geändert:** Pause im Tool, oder die Aufgabe „In <Tool> stoppen“.
- **Tempo-Ansicht** zählt Tool-Einladungen.

**M9d Registerlücke**
- **Wo:** `python -m app.register_gap` und eine Karte auf der Seite Quellen.
- **Zählung:** Firmen ohne Ansprechpartner, getrennt nach
  - registerpflichtiger Rechtsform (GmbH, UG, AG, KG, OHG, e.K., GmbH & Co. KG);
  - vermutlich ohne Register (Praxis, Kanzlei, GbR, Einzelunternehmen).
- **North-Data-Schätzung:** gemessen, sobald eigene North-Data-Firmen vorhanden sind; sonst als „Annahme“ gekennzeichnet.
- **Briefe an Firmen ohne Ansprechpartner:**
  - gehen „An die Geschäftsführung“ (bzw. Praxis- oder Kita-Leitung);
  - neutrale Anrede, dazu eine Besuchsaufgabe „nach der zuständigen Person fragen“.

**M9e Lücken schließen**
- **Website-Finder:**
  - Brave „Firmenname Ort“; Verzeichnisse werden nie abgerufen.
  - Impressum mit robots.txt; übernommen wird nur, wenn Name und Adresse passen.
  - Bericht je Firma.
- **Namen aus Firmennamen:**
  - nur per Regeln, Quelle „Firmenname“ mit Sicherheit;
  - nur „hoch“ wird ein Kontakt, „mittel“ ist ein Vorschlag.
- **Berufsregister:** als Links mit kopierbarem Suchbegriff, keine automatische Abfrage.
- **Erster Brief je Firma:** enthält den Art.-14-DSGVO-Hinweis mit Quelle und Datum der Adresse. Widerspruch geht wie bisher auf die Sperrliste.

**M9f Design-Benchmark gegen Dripify**
- **Ablauf:** 4 blinde Runden mit jeweils neuem Sub-Agenten. Viele Verbesserungen im Baukasten, in Heute, an Farben/Kontrast und auf Mobil.
- **Ziel „überall mindestens gleichauf“ nicht erreicht:**
  - **dahinter:** Baukasten, Hierarchie, Typografie, Farbe;
  - **vorn:** Tabellen, Kontrast, Klicks bis zur ersten Aufgabe;
  - **gleich:** Abstände.
- Nächste Schritte stehen in `docs/design/BENCHMARK.md`.

**Nebenbei behoben**
- Kontakte in einer laufenden Kampagne bekamen zusätzlich Vorschläge in Heute, also eine mögliche doppelte Ansprache.
- Jetzt sind sie ausgeschlossen, und offene Vorschläge werden beim Kampagnenstart zurückgezogen (mit Test).

**Tests zum Schluss**
- **Backend:** 299 passed.
- **Web:** Lint, Typecheck und 22 Unit-Tests grün; ruff sauber.
- **E2E** auf dem isolierten lokalen Stack: 36 passed, 3 skipped (Design-Screenshot-Läufe nur auf Anforderung).

## (b) Was unverifiziert ist oder nur gegen Mocks läuft

- **Alle fünf Anbieter-Adapter.** Kein echtes Konto, keine echte API wurde erreicht; im Container waren nur die Doku-Seiten erreichbar. Unverifiziert laut CONNECTORS.md:
  - HeyReach: Basis-Host und Webhook-Inhalt;
  - Expandi: Feldnamen im Webhook;
  - Waalaxy: Pause und Webhooks;
  - La Growth Machine: Test, Pause und Webhooks.
- **Preisangaben** der Tools sind nicht geprüft.
- **Website-Finder:** Brave und die Websites liefen in den Tests nur als Fakes.
- **Berufsregister:** die vier Register-URLs sind nicht geprüft, ihre Nutzungsbedingungen nicht gelesen.
- **Dripify** wurde nur über öffentliche Produktbilder (Marketing-Renderings) verglichen, nicht über die echte App.
- **KI-Rückfall für unklare Firmennamen:** die Prüffunktion gibt es, sie ist aber nicht an Budget und Jobs angeschlossen. Unklare Namen bleiben unklar.

## (c) Am Mac: Branch holen, sichern, migrieren, testen

Im Terminal im Ordner ProspectOS:

```bash
cd ~/ProspectOS
```

```bash
git fetch origin && git switch claude/v3-m9-connectors
```

Datenbank-Backup vor den Migrationen:

```bash
mkdir -p data/private/backups && docker compose exec -T db pg_dump -U prospectos -d prospectos -Fc > data/private/backups/prospectos-$(date +%F)-before-m9.dump
```

Neu bauen, migrieren (0027, 0028), starten:

```bash
docker compose build migrate api worker web
```

```bash
docker compose run --rm migrate
```

```bash
docker compose up -d
```

Registerlücke für deine echten Firmen anzeigen (oder in der App: Firmen → Quellen):

```bash
docker compose exec api python -m app.register_gap
```

Externe Tools bleiben unsichtbar, solange in `.env` nichts geändert wird. Nur wenn du sie wirklich
nutzen willst, in `.env` die Zeile `EXTERNAL_OUTREACH_TOOLS_ENABLED=true` setzen und dann:

```bash
docker compose up -d api worker web
```

**Live-Checkliste**
1. **Quellen:** Stimmen „ohne Ansprechpartner“ und die Aufteilung nach Rechtsform mit deinem Eindruck?
2. **„Brief an die Geschäftsführung vorbereiten“:**
   - Danach unter Briefe einen Brief ansehen: steht „An die Geschäftsführung“ in der Anschrift?
   - Ist unten der Datenschutz-Hinweis mit Quelle und Datum zu sehen?
   - Einmal ausdrucken.
3. **„Namen aus Firmennamen“:** Stichprobe der angelegten Kontakte; Vorschläge mit „mittel“ von Hand prüfen.
4. **Ein Firmenprofil öffnen:** führen die Links zu Arztsuche, Anwaltsverzeichnis, Steuerberater- und Handwerkskammer-Suche auf die richtigen Seiten? Falsche URLs bitte melden.
5. **Mit Brave-Schlüssel und `RESEARCH_ENABLED=true`:** „Fehlende Websites suchen“ für bis zu 25 Firmen; Bericht prüfen.
6. **Nur wenn du ein Tool nutzt:**
   - Einstellungen → Anschlüsse → Risiko bestätigen → Tool verbinden → „Testen“.
   - Einen eigenen Testkontakt übergeben und im Tool nachsehen.
   - Webhook-Adresse im Tool eintragen und ein Ereignis auslösen (z. B. eine Antwort).

**Falls etwas schiefgeht**
- Zurück mit `git switch claude/v3-multichannel`.
- Datenbank aus dem Dump wiederherstellen (`pg_restore --clean`).
- Container neu bauen.

## (d) Was du entscheiden musst

- **Externe Tools überhaupt nutzen?** Sie verstoßen gegen die LinkedIn-Nutzervereinbarung und können dein Konto sperren lassen. Standard bleibt aus. ProspectOS selbst automatisiert LinkedIn weiterhin nie.
- **Welches Tool, welcher Tarif.** Preise sind nicht geprüft; API-Zugang gibt es teils nur in höheren Tarifen (La Growth Machine: Pro).
- **North Data** (kostenpflichtig) für die registerpflichtigen Firmen ohne Ansprechpartner. Die Karte auf Quellen zeigt, wie viele Kontakte etwa dazukämen.
- **Berufsregister automatisch abfragen?** Nur wenn deren Nutzungsbedingungen das ausdrücklich erlauben; bis dahin von Hand.
- **Art.-14-Text** im Brief einmal rechtlich prüfen lassen (Speicherdauer „höchstens 24 Monate ohne Antwort“ ist ein Vorschlag).
- **Design:** ob die Baukasten-Ansicht als nächstes zur Verzweigungs-Grafik ausgebaut wird (größte verbleibende Lücke zu Dripify).
- **Netzwerk:** Die Cloud-Umgebung „ProspectOS“ hat für diese Arbeit zusätzliche erlaubte Hosts bekommen (Doku-Seiten der Tools, dripify.io/.com). Bei Bedarf in den Umgebungseinstellungen wieder entfernen.
