---
name: rechnung
description: Rechnungserstellung Locker & Lauter – täglicher Lauf (Kalender → Finanzsheet → Kunden- und Fee-Rechnung → Drive/Gmail) sowie Chat-Befehle erstellen, storno, korrigieren, regel, sonderfall, status. Immer laden, wenn es um L&L-Rechnungen, Rechnungsnummern, Stornos oder die Rechnungsregeln geht.
---

# Rechnungserstellung Locker & Lauter

Du arbeitest im Repo `ll-rechnungserstellung`. Fachliche Wahrheit ist **`rules/rechnungsregeln.md`** –
vor jeder Rechnung komplett lesen und anwenden. Bei Zweifel: keine Rechnung, sondern Rückfrage/Befund.
Das Finanzsheet wird **nie** beschrieben. Nichts wird automatisch per Mail versendet – nur Entwürfe.

## Betriebsmodus

`config/betrieb.yaml` → `modus: schatten | produktiv` (siehe Regel 14). **Rechnungsnummern laufen in beiden
Modi wie produktiv** (Schritt 5 + 9: Vergabe, sofortige Reservierung im Register, Commit + Push). Im Schattenmodus
unterscheiden sich nur Ablage und Mails: PDFs nur in
`Locker & Lauter Finanzen/_parallelbetrieb/<JJJJ-MM-TT>/`, Gmail-Entwurf an den Kunden (Regel 13a), keiner an die
Creatorin, Vergleichsmail an finance@.

## Werkzeuge im Repo

| Schritt | Befehl |
|---|---|
| Sheet-Zeile → Befund + Dokument-JSONs (+PDF) | `python3 -m invoice.cli build --kampagnen data/kampagnen.csv --adressen data/finanzsheet.xlsx --nummer <N> --datum JJJJ-MM-TT [--nr-kunde X --nr-fee Y] [--expenses belege.json] [--lang de|en] --out out/<N> --pdf` |
| Dokument-JSON → PDF | `python3 render/render.py <doc.json> <out.pdf>` |
| Storno aus bestehendem Dokument-JSON | `python3 -m invoice.cli storno --doc <orig.json> --nummer <Nr> --grund "…" [--ersatz <Nr>] --out out/storno --pdf` |
| Mail-Entwurf zur Kundenrechnung (Regel 13a) | `python3 -m invoice.mail out/<N> --draft` (ohne `--draft`: nur Vorschau `mail.json`/`mail.html`) |
| Nächste Nummer | `python3 -m invoice.register next <KREIS> <Jahr>` |
| Nummern eines Laufs reservieren (beide Modi) | `python3 -m invoice.register reserve out/<N> [<Event-ID>]` |
| Registerfelder nachtragen | `python3 -m invoice.register set <Nr> drive_kopie=<URL> gmail_draft=<ID> [status=gesendet]` |
| Register ↔ Finanzsheet nachziehen | `python3 -m invoice.register import data/kampagnen.csv <Jahr>` |

Exit-Code 3 von `build` = Stopp-Befund, es wurden keine Dokumente erzeugt. `out/<N>/befund.json` enthält
findings, meta, die Sheet-Zeile und `sheet_max_numbers` (höchste Nummern je Kreis im Finanzsheet).

## Zwei Wege für Drive/Gmail/Sheet – Brücke bevorzugt

**Brücke** (`config/bridge.yaml` vorhanden, `python3 -m invoice.bridge ping` antwortet `ok`): alle Datei- und
Sheet-Operationen laufen über die Shell (`invoice.bridge`), ohne Base64 im Kontext. Das ist der Normalweg.
`config/bridge.yaml` (URL + Secret) liegt **nicht** im Repo, sondern in Drive unter
`Locker & Lauter Finanzen/_daten/bridge.yaml` (Ordner-ID `1TA1pnaak4JTcMtNLNCTRWuoA3QeksJw4`). Zu Beginn jedes Laufs:
`search_files` `title = 'bridge.yaml' and parentId = '1TA1pnaak4JTcMtNLNCTRWuoA3QeksJw4'` → `read_file_content`
→ Inhalt nach `config/bridge.yaml` schreiben. Das Secret nie in Zusammenfassungen, Commits oder Mails wiedergeben.
**Connector-Fallback** (keine Brücke oder `ping` schlägt fehl): Google-Drive-/Gmail-Tools mit base64-Inhalt
(`create_file` mit `base64Content`, `create_draft` mit `attachments[].content`). Funktioniert, kostet aber
~40k Tokens je PDF – im Fallback nur die nötigsten Dateien hochladen und das in der Zusammenfassung vermerken.

## Daten holen (jeder Lauf, immer frisch)

1. **Finanzsheet** (ID in `config/betrieb.yaml` → `drive.finanzsheet`):
   - Brücke: `python3 -m invoice.bridge sheet <ID> "Finance | Kampagnen" "Finance I Creator-Adressen" > data/sheet.json`
     → `build --sheet-json data/sheet.json`.
   - Fallback: `download_file_content` mit `exportMimeType: text/csv` → base64 dekodieren → `data/kampagnen.csv`
     (CSV-Export liefert nur den ersten Tab „Finance | Kampagnen"); `download_file_content` mit
     `exportMimeType: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` → `data/finanzsheet.xlsx`
     (Tab „Finance I Creator-Adressen"). Große Tool-Ergebnisse landen als Datei; mit Python `json.load` →
     `base64.b64decode` schreiben. Dann `build --kampagnen … --adressen …`.
2. **Kalender** (Connector): `list_events` mit `fullText: "Rechnungserstellung"` für den Tag (startTime 00:00,
   endTime 23:59:59, lokale Zeit Europe/Berlin). Titel enthält `🧾 Rechnungserstellung | <KUNDE>` (ggf. führende
   Leerzeichen), `description` = Sheet-Nummer. Ohne Nummer in der Beschreibung ⇒ Befund, kein Lauf für dieses Event.
3. **Register**: `register/rechnungsregister.csv` im Repo (vorher `git pull`).

## Täglicher Lauf (geplante Aufgabe, werktags morgens)

Für jedes Event des Tages:

1. `git pull`, Daten holen (oben), `modus` lesen.
2. Idempotenz: Event-ID schon im Register oder `find_by_sheet(<N>)` liefert eine aktive Kundenrechnung ⇒
   nur Hinweis in der Zusammenfassung, nichts erzeugen.
3. `build --datum <heute>` laufen lassen (vergibt die Nummern automatisch, siehe Schritt 5) → Befund lesen.
   - Stopp-Befund ⇒ in die Zusammenfassung, weiter mit dem nächsten Event.
   - Warnungen ⇒ Entwurf trotzdem erzeugen, Warnungen in die Zusammenfassung.
4. **Leistungsbeschreibung prüfen** (`out/<N>/<Kundenrechnungs-Nr>.json`, `items[0]`): Titel muss eine
   kurze, lesbare Leistung sein (z. B. „4 × LinkedIn-Beiträge als Co-Author"), Unterzeilen Kampagne/Go Live,
   Handles, Deliverables. Ist der automatische Titel unglücklich (zu lang, Füllwörter, „Content-Paket"),
   formuliere ihn aus den Sheet-Daten besser – **keine** Inhalte erfinden, keine Beträge ändern. JSON anpassen.
   **Danach Abgleich mit Vertrag/Angebot (Regel 7a):** Kampagnenordner per Connector suchen: `search_files`
   `title contains '<Kunde>' and mimeType = 'application/vnd.google-apps.folder'`, auch ohne Leerzeichen im Kundennamen
   (Sheet „AT World“, Ordner `13_ATWorld_10/2026`). Treffer über `get_file_metadata` (`parentId`) bis zum Ordner
   `<CREATOR> (L&L)` prüfen; Monat steht im Ordnernamen. Darin `search_files` `parentId = '<Kampagnenordner>'` ⇒
   `01_Vertrag` ⇒ `parentId = '<01_Vertrag>'`, dann `read_file_content`. `bridge find 01_Vertrag` nicht verwenden: liefert
   höchstens 50 Treffer und übersieht Ordner. Leer oder kein Treffer ⇒ übriger Kampagnenordner, dann `search_files` mit
   `title contains` auf Kunde und Creatorin plus `Vertrag`/`Angebot`/`Contract`/`Offer`/`Kooperation`.
   Ergebnis je Event notieren: ok / Unstimmigkeit / kein Dokument / unklar. Kein Stopp, JSON nicht aus dem Vertrag ändern.
5. Nummern (vergibt `build` selbst, Standard `--nummern auto`; Ergebnis in `befund.json` → `meta.nummern`):
   - Steht für die Zeile schon eine Nummer im Finanzsheet (`Rechnung Creator:in` / `Rechnung L&L`), wird sie übernommen
     (`quelle: finanzsheet`). Widerspricht sie dem Register ⇒ Stopp.
   - Sonst: aktive Reservierung im Register für diese Sheet-Nummer ⇒ wiederverwenden (`quelle: register`).
   - Sonst nächste freie Nummer je Kreis = max(Register, Finanzsheet, in diesem Lauf bereits vergeben) + 1
     (`quelle: neu`). `out/_vergeben.json` hält die Vergaben des Laufs fest – mehrere Events am selben Tag bekommen
     fortlaufende Nummern, ein erneuter Aufruf für dieselbe Sheet-Nummer dieselbe. `out/` daher während des Laufs
     nicht löschen.
   - **Beide Modi:** Widerspruch Register ↔ Finanzsheet ⇒ Stopp-Befund. Ohne Stopp **sofort** reservieren:
     `python3 -m invoice.register reserve out/<N> <Event-ID>` (beide Dokumente, Status `entwurf`, Modus), dann
     `git add register && git commit -m "register: <Nummern> (<Modus>)" && git push` – damit jede spätere Session die
     Nummern kennt, auch bevor sie im Finanzsheet stehen.
   - `schatten`: Vergibt n8n eine andere Nummer, ist das ein Befund (maßgeblich bleibt die Register-Nummer).
   - `ENTWURF` erscheint nur noch, wenn die Creatorin unbekannt ist (dann gibt es ohnehin einen Stopp) oder
     ausdrücklich `--nummern keine` gesetzt wurde.
   - Marina Ziblis: Regel 8 (Tageslimit) – Rechnungsdatum ggf. auf den nächsten freien Tag legen.
6. PDFs rendern: `build … --pdf` erneut (gleiche Nummern dank `_vergeben.json`) oder die angepassten JSONs direkt
   mit `render/render.py` rendern.
   PDFs: `Rechnung-<Nr>.pdf`. Immer die fertigen PDFs einmal als Bild prüfen (`pdftoppm -r 60`) – Seitenzahl,
   nichts abgeschnitten, Summen plausibel.
7. Ablage in Drive:
   - `produktiv`: `Rechnungskopien/<Jahr>/<Monat>` (Monat des Rechnungsdatums, deutsch: Januar … Dezember).
     Brücke: `python3 -m invoice.bridge upload out/<N>/Rechnung-<Nr>.pdf Rechnungskopien/<Jahr>/<Monat>` – fehlende
     Jahr-/Monatsordner legt die Brücke an. Fallback: `search_files` `title = '<Monat>' and parentId = '<Jahr-Ordner>'`,
     fehlende Ordner mit `create_file` (`contentMimeType: application/vnd.google-apps.folder`), PDF mit `create_file`
     (`contentMimeType: application/pdf`, `disableConversionToGoogleType: true`, base64).
     Zusätzlich Kampagnenordner (Regel 13): `python3 -m invoice.bridge find 06_Rechnungen` (liefert je Treffer die
     Elternkette `<NN_Kunde_MM/JJJJ>` → `<Jahr>` → `01_Bezahlte Partnerschaften` → `02_Partners` → `<CREATOR> (L&L)`);
     genau ein Treffer mit passendem Creator + Kunde + Monat ⇒ dort ablegen (`upload … --folder-id` bzw. `folderId`),
     sonst nur Rechnungskopien + Hinweis. Drive-IDs ins Register (`drive_kopie`, `drive_kampagne`).
   - `schatten`: `_parallelbetrieb/<JJJJ-MM-TT>/` (Brücke legt Ordner an; Fallback: Ordner-ID `1Qih0oENrp5d1Mn4HQzFaj8YnKOx3wAqY`).
     Ordner-ID „Locker & Lauter Finanzen": `188XnxRQFqdpcLZ-Vy3yKXegvaujrVujV`; „Rechnungskopien": `1Rri9WmPNTVKwKNHX9nbE9lt4gY6iCrnf`.
8. Gmail-Entwürfe:
   - **an Kunde – immer, auch im Schattenmodus** (Regel 13a): vorher Gmail `search_threads`
     `in:sent subject:"<Nr>"` – schon versendet ⇒ kein Entwurf, nur Hinweis. Dann zählen, wie viele Rechnungsmails
     mit **anderer** Nummer heute schon an dieselbe An-Adresse gingen: `search_threads`
     `in:sent to:<adresse> after:<JJJJ/MM/TT> subject:(Rechnung OR Invoice)` plus `list_drafts` mit `to:<adresse>`
     (nur heute angelegte, andere Nummer) ⇒ `<n>`. Im selben Lauf zählt `invoice.mail` selbst (`out/_mails.json`).
     Sonst/danach `python3 -m invoice.mail out/<N> --draft [--bereits <n>]` nach dem Rendern (bei angepasster Leistungsbeschreibung erst neu
     rendern). Empfänger: erste Adresse aus „Kontakt“ = An, alle weiteren = CC; Betreff `Rechnung <Nr>` /
     `Invoice <Nr>`; Text = Standardvorlage DE/EN mit Signatur; Anhang Kundenrechnung. Befunde aus der Ausgabe
     (kein Empfänger, kein Ansprechpartner) in die Zusammenfassung, Draft-ID mit in die Zeile.
     Fallback ohne Brücke: `mail.json`/`mail.html` bauen und `create_draft` (to/cc/subject/htmlBody, Anhang base64).
   - an Creatorin (nur `produktiv`) (Adresse: Josh fragen bzw. `creators.yaml` `email`, falls gepflegt; sonst ohne Empfänger),
     Betreff `Management-Fee-Rechnung <LL-Nr> zu <Kundenrechnungs-Nr>`, Anhang Fee-Rechnung.
   - Draft-IDs ins Register (`gmail_draft`).
9. Register (beide Modi): Drive-Link und Draft-ID nachtragen (`python3 -m invoice.register set <Nr> drive_kopie=… gmail_draft=…`),
   `git add register && git commit -m "register: <Nummern> (<Modus>)" && git push`.
   Push-Konflikt ⇒ `git pull --rebase`, Nummern erneut prüfen (keine Doppelvergabe), nochmal pushen.
   Danach `python3 -m invoice.register mirror` – spiegelt die CSV ins Google Sheet „Rechnungsregister L&L"
   (nur Anzeige für Josh/Laura; die CSV im Repo bleibt die Wahrheit, das Sheet wird bei jedem Lauf überschrieben).
10. Zusammenfassung per `send_message` an `finance@lockerundlauter.com`, Betreff
    `Rechnungslauf <Datum>: <n> Entwürfe, <m> Rückfragen` – je Event eine Zeile (Nummer, Kunde, Creator,
    Steuerfall, Netto/Brutto, Status, Drive-Link), danach alle Befunde im Klartext. Im Schattenmodus zusätzlich
    der Vergleich: `meta.sheet_gross` (Rechnungsbetrag laut Finanzsheet = das, was n8n gestellt hat) gegen
    `meta.gross`; weicht es ab, steht der Befund bereits in `findings`. Die n8n-PDF selbst ist per Connector nicht
    lesbar (kein Anhang-Download) – Josh vergleicht das Layout anhand der Freigabe-Mail von n8n.
    Ergebnis des Vertragsabgleichs je Event mit in die Zeile; jede Unstimmigkeit und jedes fehlende Dokument als
    eigener kurzer Befund und im Betreff als Rückfrage gezählt. Liegt so ein Fall vor, zusätzlich `PushNotification`
    mit einem Satz je Fall. Beim manuellen `rechnung erstellen` steht das Ergebnis im Chat vor der Freigabe.

Niemals: Finanzsheet schreiben, Mails senden, Nummern raten, bei Stopp-Befund trotzdem rendern.

## Chat-Befehle

- **`rechnung erstellen <N>`** – manueller Lauf für Sheet-Nummer N ohne Kalender-Event (Nachberechnung,
  Teil-/Schlussrechnung). Ablauf wie oben ab Schritt 3; vor Schritt 5 dem Nutzer Befund + Leistungsbeschreibung
  zeigen und Freigabe abwarten, außer er hat „direkt" gesagt.
- **`rechnung storno <Nr> "<Grund>" [neu]`** – Original-JSON aus `out/`-Historie bzw. aus dem Register-Drive-Link
  rekonstruieren (PDF lesen, falls kein JSON vorliegt), `cli storno` mit nächster Nummer im selben Kreis, Register:
  Original → `storniert` + `referenz`, Storno-Zeile `typ=storno`. Bei `neu`: Ersatzrechnung (Regel 9) mit
  `replaces`, Verrechnungstext, neue Nummer; **Fee-Rechnung immer mitziehen** (Storno + Neu). PDFs ablegen,
  Entwürfe anlegen, zusammenfassen.
- **`rechnung korrigieren <Nr> "<was>"`** – Status `entwurf`: JSON ändern, neu rendern, PDF in Drive ersetzen
  (alte Datei `trash_file`), Register aktualisieren. Status `gesendet`: ⇒ Storno + Neu.
- **`rechnung regel "<Text>"`** – an `rules/rechnungsregeln.md` unter „Änderungsprotokoll" mit Datum anhängen
  und, wenn es eine bestehende Regel ändert, den betreffenden Abschnitt anpassen. Commit `regel: <Kurzfassung>`.
  Betrifft die Regel eine Creatorin/einen Kunden ⇒ zusätzlich `creators.yaml` / `customers.yaml`.
- **`rechnung sonderfall <N> "<Text>"`** – Einzelfall-Anweisung für genau diese Sheet-Nummer (z. B. Netto-Belegliste,
  abweichende Sprache, Bestellnummer). In `cases/<N>.md` ablegen (Datum, Text) und beim Lauf für N berücksichtigen
  (`--expenses` aus der Belegliste bauen: `[{"title": "...", "net": 56.07, "gross": 66.72, "pages": "S. 3"}]`).
- **`rechnung status [<Nr>|offen|heute]`** – Registerauszug; `offen` = Status `entwurf`/`gesendet`.
- **`rechnung gesendet <Nr>`** – Status auf `gesendet` (Datum), simbadirekt-Entwurf vorbereiten
  (`create_draft` an `rzmd-iyyam-a@belege.simbadirekt.de`, Anhang PDF, Betreff = Nummer).

## Vergleichsmodus (Schatten) – worauf achten

n8n läuft nur noch zum Abgleich (Josh nutzt die Claude-Rechnungen). Der Wert des Schattenlaufs ist die Abweichungsliste: andere Summe, anderer Steuerfall,
fehlende/zusätzliche Hinweistexte, andere Sprache, unlesbare Leistungsbeschreibung. Jede Abweichung, die eine
fehlende Regel zeigt, als Vorschlag formulieren („Regel ergänzen: …"), nicht still beheben.
