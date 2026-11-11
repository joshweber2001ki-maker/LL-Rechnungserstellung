# Rechnungsregeln Locker & Lauter

Diese Datei ist die fachliche Wahrheit für die Rechnungserstellung. Claude liest sie bei jedem Lauf
komplett und wendet sie an. Neue Regeln werden unten unter „Änderungsprotokoll" mit Datum ergänzt
(Befehl `rechnung regel "..."`). Bei Widerspruch gilt die jüngere Regel.

Stand: 2026-11-11 · Quelle: bisherige Rechnungen 2026, n8n-Workflow, Absprachen mit Josh/Steuerberatung.

---

## 1. Grundprinzip

- Jeder Vorgang (= eine Zeile im Finanzsheet, Tab „Finance | Kampagnen", identifiziert über die Spalte
  **Nummer**) erzeugt **zwei Dokumente**:
  1. **Kundenrechnung** im Nummernkreis der Creatorin (`DR-2026-NNN`), Empfänger = Kunde.
     Ausgestellt „im Namen von und auf Rechnung für" die Creatorin über L&L.
  2. **Management-Fee-Rechnung** `LL-2026-NNN`, Empfänger = Creatorin (bzw. deren UG).
     Geht **nie** an den Kunden. Wird mit der Kundenzahlung verrechnet, keine separate Zahlung.
- Das Finanzsheet wird **nur gelesen**, nie beschrieben.
- Nummern werden ausschließlich über das Rechnungsregister vergeben (siehe Abschnitt 8).

## 2. Datenquellen und Spalten (Tab „Finance | Kampagnen")

| Feld | Spalte | Verwendung |
|---|---|---|
| Nummer | A | Schlüssel, steht in der Kalender-Event-Beschreibung |
| Kunde | D | Kundenname, Kampagnenzeile |
| Creator:in | E | Schlüssel in `creators.yaml` und Tab „Creator-Adressen" |
| Monat | G | Leistungszeitraum (`<Monat> <Jahr>`); Jahr = Jahr des Abschnitts im Sheet |
| Go Live | H | Go-Live-Datum/-Daten in der Leistungsbeschreibung |
| Leistungen | I | Grundlage der Leistungsbeschreibung |
| Vergütung Gesamt | J | Netto-Gesamthonorar (Creator + Fee) |
| Vergütung Creator | K | Netto-Honorar Creatorin = Position 1 |
| Zusatzkosten | L | Fremdkosten/Auslagen **netto** (Sheet-Wert ist oft brutto – siehe Regel 6!) |
| MwSt 19% (Spalte O, 15. Spalte) | O | 0,00 € ⇒ keine deutsche USt auf der Rechnung. **Nur Indiz**, Steuerfall wird aus dem Land bestimmt (Regel 4) |
| Vergütung L&L | Q | Management Fee netto = Position 2 |
| Rechnungsempfänger | AB | Adressblock, zeilenweise (Regel 3) |
| Ansprechpartner / Kontakt | AC / AD | Mail-Entwurf an den Kunden |
| Sprache | AE | `Deutsch` / `Englisch` ⇒ Vorlage DE/EN |
| Zahlungsfrist | AF | „14 Tage" ⇒ Fälligkeit = Rechnungsdatum + 14 |
| Rechnung Creator:in / Rechnung L&L | AH / AI | bereits vergebene Nummern (Dublettencheck, Zählerabgleich) |

Tab „Finance I Creator-Adressen": Adresse (zeilenweise), **Beschreibung (DE)/(EN)** = fertiger
Hinweistext inkl. Steuernummer/USt-IdNr. (wird 1:1 übernommen), Creator Handle (für die Leistungsbeschreibung).

## 3. Adressblock des Kunden

- Zeilen des Sheet-Felds „Rechnungsempfänger" werden 1:1 übernommen (Name, Straße, PLZ Ort, Land).
- Zeilen mit Kennungen werden erkannt und separat gesetzt:
  - **Steuer-ID**: `USt-ID`, `USt-IdNr`, `VAT`, `VAT ID`, `VAT-ID`, `VAT Number`, `UID` ⇒ Zeile `VAT: …` / `USt-IdNr.: …`
  - **Referenzen**: `Bestellnummer`, `PO`, `PO number`, `ANID`, `WBS-Code`, `Registration number`, `KVK`, `#OP-…`
    ⇒ eigene Zeilen unter der Adresse (werden auf der Rechnung angezeigt, Kunde braucht sie zur Zuordnung).
- Land fehlt und PLZ ist 5-stellig numerisch ⇒ Deutschland annehmen. Sonst: Land aus `customers.yaml`,
  sonst **Rückfrage**.
- Steht im Feld `pending` ⇒ **keine Rechnung**, Rückfrage.

## 4. Steuerfall (entscheidet Summenblock + Hinweistexte)

Bestimmung: Land des Kunden (Adresse/`customers.yaml`) × Sitzland der Creatorin (`creators.yaml`).

| Fall | Bedingung | Summenblock | Hinweistexte |
|---|---|---|---|
| **DE** | Kunde DE, Creatorin DE | Netto · zzgl. MwSt. 19 % · Brutto | Creator-Hinweis (DE) + KSK-Hinweis „vom Verwerter … direkt abzuführen" |
| **EU** | Kunde EU (nicht DE), Creatorin DE | net amount · KSK (4,9 %) · total amount | Creator-Hinweis (EN) + „Reverse Charge Procedure applies. The customer is required to account for the VAT." · USt-ID des Kunden im Adressblock **Pflicht** |
| **DRITTLAND** | Kunde CH/GB/US/…, Creatorin DE | wie EU | wie EU, zusätzlich „Not subject to German VAT – the place of supply is <Land> (Sec. 3a (2) German VAT Act)." |
| **CREATOR-AT** | Creatorin AT (Selina) | NETTOSUMME · UMSATZSTEUER (0 %)* · RECHNUNGSBETRAG | österreichischer Text: „Die Leistung ist in Österreich nicht steuerbar; Leistungsort ist <Land> (§ 3a Abs. 6 UStG AT). Die Steuerschuld geht auf den Leistungsempfänger über …" + englische Kurzfassung. **Keine KSK.** Fee ist in Position 1 enthalten („inkl. Management Fee"), keine eigene Fee-Position |
| **UG** | Creatorin arbeitet über UG (Julie) | wie DE/EU je nach Kunde | Hinweistext nennt die UG. **Bis Sonderregel vorliegt: manuelle Freigabe** |

Konsistenzprüfung (Vorprüfung): Sheet-Spalte „MwSt 19%" = 0 muss zum Fall EU/DRITTLAND/CREATOR-AT passen,
> 0 zum Fall DE. Passt es nicht ⇒ **keine Rechnung, Rückfrage** mit beiden Befunden.

Sprache: Fall DE/CREATOR-AT ⇒ Deutsch, EU/DRITTLAND ⇒ Englisch, es sei denn Sheet-Spalte „Sprache"
sagt explizit etwas anderes (dann Sheet).

## 5. KSK-Umlage (Regel vom 26.10.2026)

- **Ausländischer Kunde** (EU + Drittland, Creatorin DE): KSK 4,9 % wird auf der Kundenrechnung als eigene
  Zeile im Summenblock berechnet. Bemessung = Creator-Honorar + Management Fee (**nicht** auf Auslagen).
- **Deutscher Kunde**: keine Umlage, nur der Hinweistext.
- Creatorin AT: keine KSK.
- Ob auf den KSK-Anteil USt anfällt, prüft die Steuerberatung (offen seit 21.10.2026). Bis zur Antwort:
  KSK ohne USt, wie bisher.

## 6. Fremdkosten / Auslagen

- Weiterberechnung **immer netto** (Creatorinnen sind umsatzsteuerpflichtig). Der Sheet-Wert
  „Zusatzkosten" ist nicht verlässlich (teils brutto, teils Belegsumme) ⇒ **jede Rechnung mit
  Zusatzkosten > 0 wird nur als Entwurf mit Rückfrage erstellt**, bis Josh die Netto-Belegliste bestätigt
  (per Chat: `rechnung sonderfall <Nr> "..."`).
- Darstellung auf der Rechnung:
  - Fall DE: Block „Weiterberechnete Auslagen (netto, Belege im Anhang)" mit **einer Unterzeile je Beleg**
    (Bezeichnung, Belegnummer, Datum), 19 % USt auf alles.
  - Fall EU/DRITTLAND (Variante DR-2026-033, bestätigt 02.11.2026): Belege als Netto-Positionen,
    Summenblock: subtotal (Honorar + Fee) · KSK (4,9 % of subtotal) · travel expenses (net) · net amount ·
    VAT (reverse charge) 0,00 · total amount. Zusatztext: „Travel expenses are charged at net cost as part
    of the consideration for the service; receipts attached. Reverse Charge Procedure applies to the full amount."
  - Belege ohne USt (Kilometerpauschale, § 19 UStG) in voller Höhe.
  - **Ab 4 Belegen**: zusätzliche Anlage-Seite „Aufstellung der weiterberechneten Auslagen" (Tabelle
    Nr · Beleg · Anhang-Seite · Brutto · Netto, Summenzeile) wie KML-2026-015.
- Belege werden als Anhang hinter die Rechnung gehängt (PDF-Merge), wenn sie im Kampagnenordner liegen.
- Kooperationsverträge mit Fremdkostenbudget (TK Mental Matters/Kira: 12.905 € netto): Anlage zusätzlich mit
  Budgetabgleich (Budget · bereits abgerechnet · verbleibend · mit dieser Rechnung berechnet). Alles über
  dem Budget zahlt die Creatorin – L&L stellt ihr den Eigenanteil mit einer LL-Rechnung in Rechnung.

## 7. Leistungsbeschreibung (neues Format, bestätigt 02.11.2026)

Ziel: lesbar statt Textklumpen. Nur aus Sheet-Daten (Leistungen, Go Live, Kunde, Handles).

```
<Leistung – fett>                                     1   <Preis>   <Summe>
  Kampagne: <Kunde> · Go Live: <Datum/Daten>
  <Handles der Creatorin>
  <ggf. weitere Zeile: Teilrechnung/Abschlag/Nachberechnung>

Management Fee                                        1   <Fee>     <Fee>
```

Regeln:
- „Leistungen" wird in einzelne Deliverables zerlegt (Trenner `;`, Zeilenumbruch, „1 x / 1 ×"). Mehrere
  Deliverables ⇒ Leistungszeile = kurze Zusammenfassung („4 × LinkedIn-Beiträge als Co-Author"), die
  einzelnen Deliverables als Unterzeilen mit `·`. Beträge stehen nur auf der Leistungszeile (ein Preis,
  wie im Sheet), **keine** erfundene Aufteilung je Deliverable.
- Teilrechnungs-Hinweise aus „Leistungen" („1. Teilrechnung", „2. Partial Invoice") werden zur Unterzeile
  „1. Teilrechnung" / „1st partial invoice" und zählen nicht als Deliverable.
- „Go Live:"-Präfix aus dem Sheet entfernen, Datumsangaben normalisieren (`30.10. & 02.11.2026` bleibt).
  Steht nur ein Monat („September") ⇒ `Go Live: September 2026`.
- Handles aus Tab Creator-Adressen, alle in einer Zeile.
- Markdown-Sternchen (`*Scalable Capital*`) entfernen.
- Englische Vorlage: `Campaign:` / `Go live:` / `Management fee`.
- Fee-Rechnung: Position „Management Fee" mit Unterzeilen `für Kunde: <Kunde>` ·
  `Leistungszeitraum: <Monat Jahr>` · `Rechnung: <Kundenrechnungsnummer>` (unverändert zum bisherigen Format).

## 7a. Abgleich mit Vertrag/Angebot (Regel vom 04.11.2026)

Jede Leistungsbeschreibung wird vor dem Rendern einmal mit dem Vertrag oder Angebot des Vorgangs abgeglichen,
in beiden Betriebsmodi.

- **Suche:** Ordner `01_Vertrag` im Kampagnenordner (Match über Creator + Kunde + Monat wie in Regel 13), danach
  der übrige Kampagnenordner, zuletzt Drive-weit nach Dateien mit Kunde und Creatorin im Titel (Angebote liegen
  teils außerhalb, z. B. in `00_KONZEPTE`). Mehrere Fassungen: unterschriebene vor der neuesten.
- **Abgleich:** Kunde/Kampagne, Art und Anzahl der Deliverables, Plattform, Go Live. Bei Teilrechnungen zählt, ob
  der berechnete Teil vom Vertrag gedeckt ist; dass nicht alles auf einmal berechnet wird, ist keine Abweichung.
- **Nur Hinweis, kein Stopp:** Der Entwurf wird trotzdem erzeugt. Die Leistungsbeschreibung kommt weiter aus den
  Sheet-Daten (Regel 7) und wird nicht automatisch an den Vertrag angepasst.
- **Kurze Info an Josh** in genau diesen Fällen, jeweils mit Sheet-Nummer und Dateilink, falls vorhanden:
  1. Unstimmigkeit: was steht im Sheet, was im Dokument
  2. Kein Vertrag und kein Angebot gefunden
  3. Mehr als ein passender Kampagnenordner, kein eindeutiger Treffer
  4. Dokument nicht lesbar (z. B. Scan) oder nur als unterschriebener Entwurf/ohne Unterschrift vorhanden
- Stimmt alles überein, genügt in der Zusammenfassung „Vertragsabgleich ok“ mit Dokumentname.

## 8. Rechnungsnummern und Register

- Register = Google Sheet „Rechnungsregister L&L" (Ordner „Locker & Lauter Finanzen"). Eine Zeile je Dokument.
- Nächste Nummer je Kreis und Jahr = max(Register, Finanzsheet-Spalten AH/AI) + 1. Weichen Register und
  Finanzsheet voneinander ab ⇒ **Stopp und Rückfrage**.
- Eine Nummer wird beim Anlegen des Entwurfs sofort reserviert (Status `entwurf`, `python3 -m invoice.register
  reserve out/<N>`), committet und gepusht – **in beiden Betriebsmodi**. Damit sieht jede spätere Session (Routine,
  manuelles `rechnung erstellen`, Folgetag) die Nummer, auch wenn sie noch nicht im Finanzsheet steht.
  Fortlaufende Nummern hängen also nicht davon ab, wann Josh die Rechnung im Finanzsheet einträgt.
- Hat das Register für eine Sheet-Nummer schon eine aktive Reservierung, bekommt ein erneuter Lauf dieselbe Nummer
  (keine Doppelvergabe). Nennt das Finanzsheet für die Zeile eine andere Nummer als das Register, oder ist die
  Sheet-Nummer im Register einem anderen Vorgang zugeordnet ⇒ **Stopp und Rückfrage**.
- Eine Nummer wird erst beim Anlegen des Entwurfs reserviert, nicht schon bei einem Stopp-Befund. Wird der Entwurf verworfen,
  bleibt die Zeile mit Status `verworfen` + Grund (Lücke erklärbar). Nächster Entwurf nimmt die nächste freie
  Nummer – eine verworfene Nummer wird **nicht** wiederverwendet.
- Ab Status `gesendet` ist die Rechnung unveränderlich: Änderung nur per Storno + Neuausstellung (Regel 9).
- Idempotenz: Kalender-Event-ID und Sheet-Nummer werden im Register gespeichert. Gibt es für die
  Sheet-Nummer bereits eine Kundenrechnung mit Status ≠ `verworfen`/`storniert` ⇒ keine neue, nur Hinweis.
- Marina Ziblis: max. eine Rechnung à 5.000 € netto pro Tag ⇒ weitere auf Folgetage verteilen (Rechnungsdatum).

## 9. Storno und Korrektur

- Stornorechnung = eigene Nummer im selben Kreis, Titel „STORNORECHNUNG", Kopfzeile „Storno zu Rechnung
  <Nr> vom <Datum>", alle Beträge negativ, gleiche Positionen und gleicher Steuerfall wie das Original,
  Text: „Diese Stornorechnung hebt die Rechnung <Nr> vom <Datum> vollständig auf. Grund der Stornierung: …".
  Wird eine Ersatzrechnung gestellt: Verweis darauf im Stornotext.
- Ersatzrechnung = neue Nummer, Kopfzeile „Ersetzt Rechnung: <alt>" / „Replaces invoice: <alt>", bei bereits
  geleisteter Zahlung Verrechnungstext: „Your payment of X has been offset against the total amount of this
  invoice (Y). No payment required – the difference of Z will be refunded to you." (bzw. Restbetrag fällig).
- Fee-Rechnung folgt immer der Kundenrechnung: wird die Kundenrechnung storniert/ersetzt, wird die LL-Rechnung
  ebenfalls storniert und neu gestellt (Beispiel DR-024 → DR-031/032, LL-103 → LL-150/151).
- Register: Original bekommt Status `storniert` + Referenz auf Storno; Storno und Ersatz referenzieren das Original.

## 10. Fee-Rechnung (LL-)

- Empfänger: Creatorin (Adresse aus Tab Creator-Adressen) bzw. ihre UG. Immer Deutsch.
- Betrag: Spalte „Vergütung L&L" netto.
- Steuer: Creatorin DE und Kunde DE/EU ⇒ 19 % USt.
  Kunde im Drittland (CH, GB, US …) ⇒ steuerfrei „gemäß § 4 Nr. 5 Buchst. c UStG" (Vermittlungsleistung zu
  einem im Drittland ausgeführten Umsatz) und KSK-Anteil der Kundenrechnung als eigene Position durchreichen
  (Beispiel LL-2026-151). Creatorin AT ⇒ ohne USt, Reverse Charge.
- Zahlungshinweis: „Der Rechnungsbetrag wird mit eingehenden Kundenzahlungen verrechnet. Eine gesonderte
  Zahlung ist nicht erforderlich."
- USD-Deals (Whalar): Fee-Rechnung ebenfalls in USD, Verrechnung in EUR zum Kurs am Zahlungseingang (Hinweistext).

## 11. Daten, Fälligkeit, Zeitraum

- Rechnungsdatum = Tag der Erstellung (Lauf). Für Marina ggf. verschoben (Regel 8).
- Fälligkeit = Rechnungsdatum + Zahlungsfrist aus Sheet (Zahl in „Zahlungsfrist"), Default 14 Tage.
- Leistungszeitraum = „<Monat> <Jahr>" aus Spalte Monat; Zeitraum über mehrere Monate nur, wenn „Leistungen"
  oder Go Live das hergeben (dann „Juli – August 2026").

## 12. Vorprüfung – wann KEINE Rechnung erzeugt wird (Rückfrage statt Best Guess)

1. Pflichtfeld leer oder `pending`: Kunde, Creator:in, Vergütung Creator, Vergütung L&L, Rechnungsempfänger.
2. Creatorin unbekannt (nicht in `creators.yaml` oder nicht im Adress-Tab).
3. Vergütung Gesamt ≠ Creator + L&L (Rundungstoleranz 0,02 €).
4. Fee-Prozent nicht in `fee_default` der Creatorin.
5. Steuerfall-Konflikt (Regel 4) oder EU-Kunde ohne USt-ID.
6. Zusatzkosten > 0 (Regel 6) – Entwurf ja, aber mit Rückfrage zur Belegliste.
7. Sheet-Nummer bereits fakturiert (Spalte AH/AI gefüllt oder Register) – Hinweis, keine Dublette.
8. Creatorin mit `entity: ug` oder markierter Sonderregel (Julie) – manuelle Freigabe.
9. Währung ≠ EUR.
10. Mehr als ein Kalender-Event am Tag mit derselben Sheet-Nummer.

## 13. Ablage und Versand

- PDFs: Drive `Locker & Lauter Finanzen/Rechnungskopien/<Jahr>/<Monat>` (Monat deutsch ausgeschrieben,
  fehlende Ordner werden angelegt) **und** im Kampagnenordner der Creatorin
  `<CREATOR> (L&L)/02_Partners/01_Bezahlte Partnerschaften/<Jahr>/<NN_Kunde_MM/JJJJ>/06_Rechnungen`
  (Match über Creator + Kunde + Monat; 0 oder >1 Treffer ⇒ nur Rechnungskopien + Hinweis).
- Dateinamen: `Rechnung-<Nr>.pdf`, `Stornorechnung-<Nr>.pdf`, `Rechnung-<Nr>_Belege.pdf` (Belegbündel).
- Gmail-Entwürfe (finance@): (a) an den Kunden mit Kundenrechnung, immer (Regel 13a); (b) an die Creatorin mit
  Fee-Rechnung nur im Modus `produktiv`. Nichts wird automatisch gesendet.
- Nach Versand (Status `gesendet`, erkannt über gesendete Mail mit der Rechnungsnummer): Beleg an
  simbadirekt (Ausgangsrechnungen) als Entwurf vorbereiten.

## 13a. Mail-Entwurf zur Kundenrechnung (Regel vom 10.11.2026)

- Zu **jeder** erzeugten Kundenrechnung wird ein Gmail-Entwurf in finance@ angelegt – in **beiden** Betriebsmodi,
  im Schattenmodus ohne Zusatz im Betreff (Josh entscheidet beim Senden). Keine Fee-Mail im Schattenmodus.
- Werkzeug: `python3 -m invoice.mail out/<N> --draft` (Anhang `Rechnung-<Nr>.pdf`; ein zweiter Aufruf legt keinen
  zweiten Entwurf an).
- **Empfänger** aus Sheet-Spalte „Kontakt“: die **erste** Adresse = An, **alle weiteren** = CC (egal ob im Sheet mit
  „CC:“ markiert). Keine Adresse ⇒ Entwurf ohne Empfänger + Befund.
- **Betreff**: `Rechnung <Nr>` (Deutsch) / `Invoice <Nr>` (Englisch).
- **Text**: Standardvorlage von Josh (DE: „Hallo <Name>, ich hoffe, es geht dir gut! Hier ist Josh aus dem
  Finance-Team von Locker & Lauter. 🪩 Anbei sende ich dir die Rechnung (<Nr>) zur gemeinsamen Aktivierung mit
  <Creator> (<Handles>). …“; EN: „Hi <Name>, … Please find attached the invoice (<Nr>) for our collaboration with
  <Creator> (<Handles>). We kindly ask for payment by <Fälligkeit> …“), danach Signatur Josh Weber, Finance Manager.
  Name = Sheet „Ansprechpartner“ (leer/`pending` ⇒ Anrede ohne Namen). Sprache wie die Rechnung.
  `customers.yaml` `contact.du_sie: sie` ⇒ Sie-Fassung.
- **Aufbau fest, Wortlaut flexibel:** immer Anrede · Einstieg (Josh, Finance-Team) · Rechnung mit Nummer und
  Creator · Bitte um Zahlung/Eingangsbestätigung · Dank und Gruß · Signatur. Die Formulierung darf sich je Mail
  leicht ändern (Varianten im Code, stabil je Rechnungsnummer).
- **Mehrere Mails am selben Tag an dieselbe Person** (gleiche An-Adresse, andere Rechnungsnummer – im selben Lauf
  oder heute schon gesendet/als Entwurf in Gmail): ab der zweiten Mail Folgetext, ohne erneute Vorstellung
  („ich melde mich heute direkt noch einmal – es gibt eine weitere Rechnung“), kürzerer Gruß.
- **Creator-Handles:** nur die Handles der Plattform, um die es in der Kampagne geht (aus Sheet „Leistungen“:
  LinkedIn-Kampagne ⇒ nur LinkedIn-Handle, Reel/Story/IG ⇒ nur Instagram). Ist das nicht eindeutig (keine Plattform
  erkennbar oder kein passender Handle), alle Handles aus Tab „Creator-Adressen“.
- Ist die Rechnung laut Gmail schon versendet (gesendete Mail mit der Nummer im Betreff), keinen Entwurf anlegen,
  nur Hinweis.

## 15. Zahlungserinnerungen (Regel vom 11.11.2026)

Läuft bei **jedem** Tageslauf, auch ohne Kalender-Event und in beiden Betriebsmodi. Es werden nur Gmail-Entwürfe
angelegt, nie gesendet. Werkzeug: `python3 -m invoice.erinnerung` (pruefen / text / log), Ablauf im Skill.

- **Wann:** Kundenrechnung im Finanzsheet mit Status `RE gestellt` oder `ZA überfällig`, deren Datum in „Rechnung
  fällig am“ **mehr als 3 Kalendertage** zurückliegt (Schwelle in `config/betrieb.yaml`). Fee-Rechnungen (LL-) werden
  nie angemahnt. Das Finanzsheet wird dabei nicht verändert – den Status `RE Erinnerung gesendet` setzt Josh selbst,
  wenn er den Entwurf abschickt.
- **Nie doppelt** – ein Entwurf entsteht nur, wenn ALLE Prüfungen leer sind:
  1. Sheet-Status ist nicht `RE Erinnerung gesendet`.
  2. Protokoll `register/zahlungserinnerungen.csv` hat für die Nummer kein `entwurf_angelegt`/`manuell_erinnert`.
  3. Gmail „Gesendet“ enthält keine Erinnerung zu der Nummer (Betreff/Text mit Nummer + Zahlungserinnerung, Payment
     reminder, Mahnung, überfällig …), auch nicht als Sammelmail mit mehreren Nummern.
  4. Unter den Gmail-Entwürfen liegt keiner zu der Nummer.
  Trifft 3 oder 4 zu: als `manuell_erinnert` protokollieren, kein neuer Entwurf. Je Rechnung gibt es automatisch
  **genau eine** Erinnerung; eine zweite Stufe/Mahnung schreibt Josh selbst (Hinweis in der Zusammenfassung, wenn eine
  erinnerte Rechnung nach 14 Tagen noch offen ist).
- **Rückmeldung des Kunden zählt vor dem Entwurf.** Gelesen werden alle Mails seit Rechnungsversand, die von der
  Kontaktadresse, den CC-Adressen oder derselben Domain kommen oder die Rechnungsnummer nennen – auch in anderen
  Threads (z. B. einer älteren Erinnerung zum selben Kunden) und auch, wenn finance@ nur in CC steht:
  - Verzögerung angekündigt, Zahlung „in Bearbeitung/im Zahllauf/freigegeben“, konkretes Zahldatum, längeres
    Zahlungsziel genannt ⇒ **kein Entwurf**, `zurueckgestellt` mit Wiedervorlage: genanntes Datum + 3 Tage, sonst
    Datum der Rückmeldung + 7 Tage. Liegt die Wiedervorlage schon in der Vergangenheit, gilt die Rückmeldung als
    verbraucht ⇒ Entwurf mit Nachfrage-Text (`text --nachfrage`), der sich für die Rückmeldung bedankt.
  - Kunde meldet Zahlung als erfolgt, Zahlung an falsches Konto, bestreitet die Rechnung, verlangt Korrektur,
    neue Rechnungsadresse/Bestellnummer, oder die Lage ist unklar ⇒ **kein Entwurf**, `rueckfrage` (bzw. `erledigt`)
    mit einem Satz Begründung; Josh entscheidet. Erst `rechnung erinnerung <Nr> freigeben` hebt das auf.
  - Zählt NICHT als Rückmeldung: automatische Eingangsbestätigungen/Abwesenheitsnotizen, reine „Rechnung
    erhalten“-Bestätigungen vor Fälligkeit, Mails zu anderen Rechnungen ohne Bezug zur Zahlung dieser Rechnung.
  Ebenso zählt eine eigene, nach Fälligkeit gesendete Mail von finance@ an den Kunden zum Zahlungsstand als
  Erinnerung (Prüfung 3).
- **Entwurf:** eine Mail je An-Adresse; mehrere überfällige Rechnungen desselben Kontakts kommen in EINE Mail.
  Empfänger wie Regel 13a (erste Adresse aus „Kontakt“ = An, weitere = CC). Der Entwurf wird als **Antwort im Thread
  der ursprünglichen Rechnungsmail** angelegt (bei mehreren: Thread der ersten Rechnung), damit der Kunde die Rechnung
  vor sich hat; findet sich keine Rechnungsmail, als neue Mail. Betreff `Zahlungserinnerung <Nr>[ / <Nr>]` bzw.
  `Payment reminder <Nr>`. Text = Joshs bisherige Erinnerung (Rechnung, Creator × Kunde, Bruttobetrag laut Sheet,
  Fälligkeit, Bitte um Prüfung, „falls schon unterwegs, gegenstandslos“), Sprache/Du-Sie wie die Rechnungsmail,
  Sammelpostfach ohne Ansprechpartner ⇒ „ihr“. Ton freundlich, keine Mahngebühren, keine Fristsetzung.
- **Keine Mailadresse** im Sheet („Sonderfall“, Portal) ⇒ kein Entwurf, Hinweis „manuell erinnern“.
- **Information an Josh:** jeder angelegte Entwurf, jede Zurückstellung und jede Rückfrage steht im Chat-Protokoll des
  Laufs und in der Zusammenfassungsmail (Abschnitt „Zahlungserinnerungen“), bei neuem Entwurf oder neuer Rückfrage
  zusätzlich Push. Das Protokoll wird committet und gepusht.

## 14. Betriebsmodus

- **Rechnungsnummern laufen in beiden Modi wie produktiv** (Regel 8): Vergabe aus Finanzsheet/Register,
  sofortige Reservierung im Register, Commit + Push + Spiegel, Widerspruch Register ↔ Finanzsheet = Stopp.
  Josh verwendet die Claude-Rechnungen; n8n läuft nur noch zum Abgleich.
- `modus: schatten` – PDFs nach `Locker & Lauter Finanzen/_parallelbetrieb/<Datum>/`, Gmail-Entwurf an den Kunden
  laut Regel 13a (keiner an die Creatorin), keine Ablage in Rechnungskopien/Kampagnenordner. Vergleichsmail an
  finance@ mit Abweichungen zur n8n-Rechnung (Betrag, Steuerfall, Texte; vergibt n8n eine andere Nummer, ist das ein
  Befund – maßgeblich ist die Register-Nummer).
- `modus: produktiv` – voller Ablauf nach Abschnitt 8 und 13.

---

## Änderungsprotokoll

- 2026-11-11 · Regel 15 Zahlungserinnerungen: Entwurf ab mehr als 3 Tagen Überfälligkeit, nie doppelt (Sheet-Status,
  Protokoll, Gmail gesendet + Entwürfe), Rückmeldungen des Kunden werden vorher gelesen, Info im Lauf-Protokoll.
  Angabe Josh.

- 2026-11-11 · Regel 8/14: Rechnungsnummern auch im Schattenmodus wie produktiv – jede Nummer wird beim Anlegen des
  Entwurfs im Register reserviert, committet und gepusht; Widerspruch Register ↔ Finanzsheet ist in beiden Modi ein
  Stopp; bestehende Reservierung einer Sheet-Nummer wird wiederverwendet. Hintergrund: Josh nutzt die
  Claude-Rechnungen, n8n nur noch zum Abgleich; Sheet-Einträge erfolgen teils erst abends/am Folgetag (Josh).
- 2026-11-10 · Neu Regel 13a: zu jeder Kundenrechnung ein Gmail-Entwurf (auch im Schattenmodus, ohne Zusatz im
  Betreff); erste Kontaktadresse = An, alle weiteren = CC; Betreff „Rechnung <Nr>“/„Invoice <Nr>“; Standardvorlage
  DE/EN. Fee-Mail an die Creatorin weiterhin nur produktiv (Josh).
- 2026-11-10 · Regel 13a ergänzt: Folgetext bei mehreren Mails am selben Tag an dieselbe Person; nur die Handles der
  Kampagnen-Plattform (unklar ⇒ alle); Wortlaut darf leicht variieren, Aufbau bleibt gleich (Josh).

- 2026-11-06 · Summenblock: Bezeichnungen (Netto/zzgl./Brutto) linksbündig untereinander, Beträge rechtsbündig – gilt
  für Kunden- und Fee-Rechnung. Schattenmodus vergibt echte Rechnungsnummern statt `ENTWURF` (ohne Reservierung im
  Register). Angabe Josh.

- 2026-11-02 · Initialfassung aus Rechnungen 2026, n8n-Workflow und Memory. Entscheidungen Josh:
  Fremdkosten-Ausland nach Variante DR-2026-033; neues Format Leistungsbeschreibung; Rechnungskopien in
  Jahr/Monat-Ordnern; Firmensitz bleibt Eschenholt 22a; Julie-Sonderregel folgt später.
- 2026-11-04 · Neu Regel 7a: Leistungsbeschreibung immer mit Vertrag/Angebot abgleichen; bei Unstimmigkeit oder
  fehlendem Dokument kurze Info an Josh, kein Stopp (Josh).
