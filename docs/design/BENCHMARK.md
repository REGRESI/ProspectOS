# Design-Benchmark ProspectOS gegen Dripify (M9f)

Stand 2026-11-08. Ziel laut Plan: in jedem Kriterium mindestens gleichauf, höchstens 4 Runden.
**Ergebnis: Ziel nicht erreicht.** Nach 4 Runden liegt ProspectOS bei 4 Kriterien noch hinter
Dripify (Baukasten, Hierarchie, Typografie, Farbe), bei 4 vorn und bei 1 gleichauf. 2 Kriterien
sind für Dripify nicht bewertbar.

## Vorgehen

- **Dripify-Referenzen:** [benchmark/dripify/](benchmark/dripify/README.md). Fünf Ausschnitte der
  öffentlichen Produktbilder von dripify.com (Dashboard, Sequenz-Baukasten ×2, Posteingang,
  Website mobil). Die App selbst ist ohne Konto nicht sichtbar; es wurde kein Konto angelegt.
- **Unsere Screenshots:**
  - Erzeugt mit `E2E_DESIGN_FIXTURE=1 DESIGN_SHOTS_DIR=… DESIGN_SHOTS_PAGES=… infra/scripts/e2e-local.sh tests/e2e/design-shots.spec.ts -g light`.
  - Läuft auf dem isolierten Stack mit synthetischen Daten (`app/design_fixture.py`, neu mit einer laufenden Beispielkampagne).
  - Seiten: Heute, Baukasten, Posteingang, Kontakte, Firmen, Geführter Start, je 1440 px und 390 px.
  - Ablage: [Runde 1](benchmark/prospectos/round-1/) (vorher) und [Runde 4](benchmark/prospectos/round-4/) (nachher).
- **Bewertung:**
  - Je Runde ein neuer Sub-Agent ohne Vorwissen, Sets nur als „A“ und „B“ benannt.
  - Blind nur eingeschränkt: Logos und Produktnamen waren auf den Bildern sichtbar.
  - Bewertet wurde nur Sichtbares, sonst „n/a“.
  - Protokolle: [Runde 1](benchmark/rounds/round-1.md), [2](benchmark/rounds/round-2.md), [3](benchmark/rounds/round-3.md), [4](benchmark/rounds/round-4.md).

## Verlauf (ProspectOS / Dripify)

| Kriterium | R1 | R2 | R3 | R4 | Stand |
|---|---|---|---|---|---|
| Visuelle Hierarchie | 3.5 / 4.5 | 3.5 / 4 | 3.5 / 4 | 3.5 / 4 | dahinter |
| Abstände/Raster | 4 / 4.5 | 4 / 4 | 3.5 / 4 | 4 / 4 | gleich |
| Typografie | 3.5 / 4 | 3.5 / 3.5 | 3.5 / 3.5 | 3.5 / 4 | dahinter |
| Farbeinsatz | 3.5 / 4.5 | 3.5 / 4 | 3 / 4 | 3.5 / 4 | dahinter |
| Klarheit Baukasten | 2.5 / 4.5 | 3 / 4.5 | 3 / 4.5 | 3 / 4.5 | dahinter |
| Tabellen/Listen | 4 / 4 | 4 / 3.5 | 4 / 3.5 | 4 / 3.5 | vorn |
| Leerzustände/Onboarding | 4 / n/a | 4 / n/a | 4 / n/a | 4 / n/a | Dripify nicht sichtbar |
| Lade-/Fehlerzustände | n/a | n/a | n/a | n/a | auf keinem Bild sichtbar |
| Mobil (390 px) | 3.5 / n/a | 3.5 / n/a | 3.5 / n/a | 3.5 / n/a | Dripify-App mobil nicht sichtbar |
| Kontrast WCAG AA | 3.5 / 3 | 4 / 3 | 4 / 3 | 3.5 / 2.5 | vorn (gemessen ≥ 4,5:1) |
| Klicks bis zur ersten Aufgabe | 4.5 / 3.5 | 4.5 / 3 | 4.5 / 3 | 4.5 / 3.5 | vorn (Heute öffnet direkt mit Aufgaben) |

Die Werte schwanken zwischen den Bewertern um ±0,5. Die Dripify-Bilder sind Marketing-Renderings
und wirken deshalb vermutlich besser als die echte App; das haben die Bewerter selbst angemerkt.

## Umgesetzt in den Runden

- **Baukasten:**
  - Rezepte als nummerierter Ablauf mit Wartezeiten und sichtbaren Bedingungen.
  - „Starten · N Kontakte“, gesperrt bei 0; ein einziger Leerzustand.
  - Bedingungen im Editor als zwei Spuren; Schritt-Zusammenfassung im Kopf.
  - Schritte mobil eingeklappt.
- **Heute:**
  - Schritte zeigen zuerst Person und Firma; ein gefüllter Knopf je Karte.
  - Hinweise (Geführter Start, Schreibstil) unter die Liste; Notizfeld wächst mit.
  - Sammel-Freigabe sekundär.
- **Farbe/Kontrast:**
  - Sekundär- und Grautöne sowie Status-Grün, -Bernstein und -Rot auf ≥ 4,5:1 angehoben.
  - Badges farbig hinterlegt und 13 px; Status in Kontakte farbig.
  - Zahl 0 nicht mehr rot.
- **Mobil:** Kontakte als Karten ohne Überlauf; Unterreiter mit Auslauf als Hinweis auf mehr.
- **Nebenbefund behoben:** Kontakte in einer laufenden Kampagne bekamen zusätzlich Vorschläge in
  Heute (doppelte LinkedIn-Ansprache möglich). Jetzt sind sie ausgeschlossen, und offene
  Vorschläge werden beim Kampagnenstart zurückgezogen (Test in `tests/test_v3_flows.py`).

## Was noch fehlt (nächste Schritte, nicht umgesetzt)

1. **Baukasten (größte Lücke):**
   - Editor auch am Desktop eingeklappt: eine Zusammenfassungszeile je Schritt, Bearbeiten in einer Seitenleiste.
   - Bedingungen als echte Gabelung mit zwei Ästen statt Liste.
   - Leere Felder „Text (optional)“ und das wiederholte „Gilt für“ nur bei Bedarf zeigen.
2. **Typografie:** deutlichere Stufen (Seitentitel/Kartentitel/Meta). Kein Knopftext unter 13 px auf Mobil.
3. **Hierarchie in Heute mobil:**
   - Beitragszahlen und Kosten in einen einklappbaren Bereich „Mehr“.
   - Geführten Start oben anheften, solange er offen ist.
4. **Geführter Start:** Fortschrittsbalken „x von 5“; übersprungene Schritte als „übersprungen“ kennzeichnen.
5. **Posteingang:** Leerzustand mit Symbol und Aktion („Kampagne starten“); Code-Formular einklappbar.
6. **Lade- und Fehlerzustände** einmal gezielt aufnehmen; sie wurden in keiner Runde gezeigt.
