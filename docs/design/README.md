# Design-Überarbeitung: Vorher / Nachher (07.11.2026)

Alle Bilder stammen aus dem isolierten Teststack (`infra/scripts/design-shots.sh`) mit
erfundenen Firmen und Personen („Fiktiv“, „Beispiel“, `example.test`). Echte Kontakte
kommen nicht ins Git. Desktop 1440 px, Handy 390 px, dazu jeweils Dunkelmodus
(`*-desktop-dark.png`).

Neu erzeugen: `infra/scripts/design-shots.sh nachher "heute=/today,firmen=/companies,…"`

## Was sich geändert hat

**Designsystem** (`apps/web/app/styles/system.css`, liegt über den alten Stilen):
- **Schrift:** eine Schrift (Inter).
- **Abstände:** im 4/8-px-Raster.
- **Farben:** eine Akzentfarbe (Blau), sonst Graustufen. Keine Verläufe, kein Glühen, keine Deko-Schatten, keine Deko-Icons.
- **Status:** kleine graue Badges mit farbigem Punkt.
- **Laden:** Skeleton-Zeilen statt Spinner.
- **Dunkelmodus:** gleich aufgebaut wie der helle.

**Navigation:**
- Nur noch fünf Bereiche: Heute, Firmen, Kontakte, Content, Einstellungen. Unterseiten erscheinen als Tabs.
- Entwicklungsansichten (Beispielsuche, Rohdaten, alte Module) gibt es nur im Demo-Workspace, unter „Mehr (Demo)“.
- Nach dem Login öffnet sich immer „Heute“ in CleanStar. Das Demo erreichst du nur über den Schalter „Demo ansehen“.

**Seiten:**

| Bereich | Vorher | Nachher |
|---|---|---|
| Heute | Einstellungsformular oben, lange Karten, Tageslimit als Textzeile | Fortschritt „0 von 7“ mit Balken, eine Hauptaktion („Alle 7 freigeben“), kompakte Zeilen zum Aufklappen, eigener Block „Follow-ups fällig“, eine Zeile mit den KI-Kosten. Absender und Limit liegen unter Einstellungen → Anschreiben |
| Firmen → Beste Treffer | Karten mit Pokal-Icons und langen Begründungen | Tabelle mit Sortierung, Suche und Filtern (Passung, Ort, Website). Eine Zeile pro Firma mit Kurzgrund |
| Firmen → Alle Firmen | Deko-Icons, „osm“, „Deals“, Fortschrittsbalken | Tabelle mit Sortierung auf dem Server: Firma, Ort, Kontakte, Quelle, Angaben, Datum |
| Firmen → Firmen finden | „Lead Discovery“, „ICP-Briefing“, synthetischer Demo-Ablauf, 15 Felder | Ort, Umkreis und Branchen oben. Alles andere unter „Weitere Filter“. Beispieldaten nur im Demo |
| Kontakte | Checkboxen, Avatare, „ICP-Fit“, Segment-Leiste | Tabelle: Name, Firma, Ort, Status (direkt änderbar), LinkedIn, Datum, mit Filter nach Status. Mehrfachauswahl und Listen unter „Auswahl und Listen“ |
| Content → Plan | Langes Formular immer offen, Hinweisbox | Plan mit Wochen als Zeilen und Status (Entwurf, zur Prüfung, freigegeben). „Neuer Plan“ als Hauptaktion |
| Einstellungen → Status | Box in Box, `.env`-Namen im Fließtext | Liste mit Ampelpunkt. Der nächste Schritt steht in Alltagssprache, technische Hinweise klein darunter |
| Einstellungen → Workspaces | (neu) | Umbenennen, Archivieren, Löschen mit Eintippen des Namens |

**Texte:**
- Durchgehend Du-Form.
- Fachbegriffe ersetzt: „Lead Discovery“ → „Firmen finden“, „ICP“ → „Zielgruppe“/„Passung“, „Social Studio“ → „Beitrag schreiben“, „Auftrags-Agent“ → „Autopilot“, „lizenzierte Suche“ und „OAuth“ entfernt.
- Leere Zustände sagen in einem Satz, was als Nächstes zu tun ist. Fehlermeldungen sind in normaler Sprache.

**Fehler, die dabei aufgefallen und behoben sind:**
- Ohne Absendernamen stand in der Anfrage „ich bin ich“. Jetzt entfällt die Vorstellung, oder es steht „hier schreibt CleanStar“.
- Das Speichern der Anschreiben-Einstellungen scheiterte an einem Zusatzfeld.
- Die Vorlage für die Zielgruppe ragte auf dem Handy über den Rand.

## Vorher / Nachher

| | Vorher | Nachher |
|---|---|---|
| Heute | ![](vorher/heute-desktop.png) | ![](nachher/heute-desktop.png) |
| Heute (Handy) | ![](vorher/heute-mobile.png) | ![](nachher/heute-mobile.png) |
| Heute (dunkel) | ![](vorher/heute-desktop-dark.png) | ![](nachher/heute-desktop-dark.png) |
| Beste Treffer | ![](vorher/top-kandidaten-desktop.png) | ![](nachher/top-kandidaten-desktop.png) |
| Alle Firmen | ![](vorher/firmen-desktop.png) | ![](nachher/firmen-desktop.png) |
| Firmen finden | ![](vorher/firmen-finden-desktop.png) | ![](nachher/firmen-finden-desktop.png) |
| Kontakte | ![](vorher/kontakte-desktop.png) | ![](nachher/kontakte-desktop.png) |
| Kontakte (Handy) | ![](vorher/kontakte-mobile.png) | ![](nachher/kontakte-mobile.png) |
| Content-Plan | ![](vorher/content-plan-desktop.png) | ![](nachher/content-plan-desktop.png) |
| Beitrag schreiben | ![](vorher/social-studio-desktop.png) | ![](nachher/social-studio-desktop.png) |
| Status | ![](vorher/setup-check-desktop.png) | ![](nachher/setup-check-desktop.png) |
| Verbindungen | ![](vorher/integrationen-desktop.png) | ![](nachher/integrationen-desktop.png) |
| Kosten | ![](vorher/budget-desktop.png) | ![](nachher/budget-desktop.png) |
| Übersicht → jetzt Heute | ![](vorher/uebersicht-desktop.png) | ![](nachher/heute-desktop.png) |

Neu (ohne Vorher): [Anschreiben](nachher/anschreiben-desktop.png),
[Autopilot](nachher/autopilot-desktop.png), [Workspaces](nachher/workspaces-desktop.png).

## Selbstkritik: was noch nicht auf Linear-Niveau ist

- **Ältere Unterseiten:** Beitrag schreiben (Editor), Zielgruppe, Mein Angebot, Kampagnen und die Firmenprofil-Detailseite erben zwar Schrift, Farben, Abstände und Badges. Ihr Aufbau (viele Karten, lange Formulare) ist aber noch der alte.
- **„Auswahl und Listen“** ist die alte Kontaktliste, nur neu gefärbt.
- **Tabs auf dem Handy:** Die Einstellungen haben zehn Tabs, die auf dem Handy horizontal scrollen. Funktioniert, ist aber nicht elegant.
