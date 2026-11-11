# L&L Rechnungserstellung

Ablösung des n8n-/Hostinger-Workflows: Google-Kalender-Event → Finanzsheet-Zeile → Kundenrechnung
(Creator-Nummernkreis) + Management-Fee-Rechnung (LL-) → PDF im L&L-Design → Drive-Ablage → Gmail-Entwurf.
Läuft als geplante Claude-Aufgabe in der Cloud (kein Rechner nötig). Die fachlichen Regeln stehen in
Klartext in `rules/rechnungsregeln.md` und werden per Chat ergänzt (`rechnung regel "…"`).

## Aufbau

```
rules/rechnungsregeln.md     Fachregeln (Steuerfälle, KSK, Fremdkosten, Nummern, Storno, Ablage) – die Wahrheit
config/company.yaml          Firmendaten, Bank, Design-Farben
config/creators.yaml         Nummernkreis, Sitzland, Fee-Plausibilität, Sonderfälle je Creatorin
config/customers.yaml        Overrides für Auslandskunden/Sonderfälle (Land, USt-ID, Sprache, Ansprechpartner)
config/betrieb.yaml          Modus schatten|produktiv, Drive-Ordner-IDs
config/bridge.yaml           URL + Secret der Apps-Script-Brücke – NICHT im Repo; liegt in Drive unter _daten/bridge.yaml
bridge/Code.gs               Apps-Script-Web-App (läuft als finance@): Sheet lesen, Upload, Gmail-Entwurf, Ordnersuche, Register-Spiegel
invoice/bridge.py            Client für die Brücke (python3 -m invoice.bridge ping|sheet|upload|draft|find)
invoice/sheet.py             Finanzsheet lesen (Spalten nach Kopfzeile, Jahresabschnitte, Beträge)
invoice/build.py             Zeile → Vorprüfung (Befunde) → Dokument-JSON Kunde + Fee, Storno-Ableitung
invoice/register.py          Rechnungsregister (CSV, versioniert), Nummernvergabe, Import aus dem Sheet
invoice/cli.py               Kommandozeile: build / storno
render/render.py             Dokument-JSON → PDF (Jinja2 + Playwright/Chromium), Auto-Fit auf eine Seite
templates/                   invoice.html (Body), header.html / footer.html (Farbbänder, Seitenzahlen)
register/rechnungsregister.csv  eine Zeile je Dokument (Status entwurf/gesendet/bezahlt/storniert/verworfen)
cases/<N>.md                 Einzelfall-Anweisungen je Sheet-Nummer
tests/fixtures/              Original-PDFs 2026 + nachgebaute Dokument-JSONs (Referenz für das Design)
.claude/skills/rechnung/     Ablauf für die geplante Aufgabe und die Chat-Befehle
```

## Schnellstart (lokal / im Task)

```bash
pip install -r requirements.txt          # Playwright-Chromium ist in der Claude-Cloud vorinstalliert
# Finanzsheet-Exporte nach data/ legen (kampagnen.csv = Tab "Finance | Kampagnen", finanzsheet.xlsx = alle Tabs)
python3 -m invoice.cli build --kampagnen data/kampagnen.csv --adressen data/finanzsheet.xlsx \
    --nummer 292 --datum 2026-11-02 --out out/292 --pdf
python3 render/render.py tests/fixtures/DR-2026-030.json out/DR-2026-030.pdf   # Design-Referenz
python3 -m invoice.register next DR 2026
```

## Betrieb

- **Schattenmodus** (`config/betrieb.yaml: modus: schatten`): n8n bleibt führend, Claude erzeugt täglich
  Vergleichs-PDFs nach `Locker & Lauter Finanzen/_parallelbetrieb/<Datum>/` und schickt eine Abweichungsliste an
  finance@. Nummernvergabe und Register wie produktiv, Gmail-Entwurf an den Kunden, keiner an die Creatorin.
- **Produktiv**: Nummern aus dem Register, PDFs nach `Rechnungskopien/<Jahr>/<Monat>` und in den Kampagnenordner,
  Gmail-Entwürfe an Kunde und Creatorin, Zusammenfassung an finance@.
- Das Finanzsheet wird ausschließlich gelesen. Es wird nie automatisch eine Mail gesendet.

## Register

`register/rechnungsregister.csv` ist die einzige Stelle, an der Nummern vergeben werden. Das Google Sheet
„Rechnungsregister L&L" (Ordner Locker & Lauter Finanzen) ist ein reiner Spiegel davon (`python3 -m invoice.register mirror`). Jede Vergabe ist ein
Git-Commit (Historie = Nachweis), in beiden Betriebsmodi sofort beim Anlegen des Entwurfs (`invoice.register reserve`).
Nächste Nummer = max(Register, Finanzsheet) + 1; weichen beide ab, stoppt der
Lauf mit Rückfrage. Verworfene Entwürfe bleiben mit Status `verworfen` stehen (Lücke erklärbar).

## Sicherheitsnetz

Vorprüfung (Regel 12) stoppt bei: fehlenden Pflichtfeldern/`pending`, unbekannter Creatorin, Summenfehler,
Steuerfall-Konflikt (Land ↔ MwSt-Flag), EU-Kunde ohne USt-ID, UG-/Sonderregel-Creatorin, Fremdwährung,
Doppel-Events. Warnungen (abweichende Fee, Zusatzkosten, bereits fakturiert) erzeugen einen Entwurf mit Hinweis.
