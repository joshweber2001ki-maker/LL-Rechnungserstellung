# Lohnsteuer-Erinnerung (Stand 27.11.2026, Josh)

Ab dem 5. jedes Monats wird Josh daran erinnert, die Lohnsteuer des Vormonats zu überweisen – danach täglich,
bis er die Zahlung bestätigt hat. Ausführung: geplante Aufgabe „L&L Lohnsteuer-Erinnerung“ (täglich).
Kontonummern stehen bewusst nicht im Repo.

## Zahlungsdaten

- Empfänger: **Finanzamt für Steuererhebung in Hamburg** (so in den bisherigen Online-Überweisungen; in Joshs
  Banking als Empfänger hinterlegt). IBAN bei Bedarf aus der Umsatzliste des Hauptkontos in Drive lesen
  (`_daten/umsaetze_hauptkonto_<Jahr>.csv`, Zeilen mit Partner „Finanzamt für Steuererhebung in Hamburg“) –
  nur in die Erinnerungsmail an finance@, nie ins Repo.
- Steuernummer: 45/740/01965 (Finanzamt Hamburg-Eimsbüttel, Finanzamts-Nr. 2245)
- Verwendungszweck (bisherige Form): **`Steuer-Nr. 45/740/01965 LSt MM/JJJJ`**
- Fällig: 10. des Folgemonats (steht in der Lohnauswertung unter „Übersicht Zahlungen“ → „FA Hamburg für Steuererh.“).

## Betrag

Quelle: `MM-Lohnauswertungen MM-JJJJ.pdf` (teils „Lohn-Auswertungen“ / „Lohnauswertung“) im Drive-Ordner der
Lohnunterlagen (2026: Ordner-ID `11GC_ZCjEEJc1fDfp0Dqr2Ob4d22k6uIG`, Uploads von laura@). Darin:
- „DÜ-Protokoll Lohnsteuer-Anmeldung <Monat>“: **Gesamtbetrag Kz. 83** = zu zahlender Betrag
  (Lohnsteuer Kz. 48 + Solidaritätszuschlag Kz. 49 + Kirchensteuer Kz. 61/62).
- Gegenprobe: „Übersicht Zahlungen“ → Zeile „FA Hamburg für Steuererh. … LSt MM/JJJJ 45/740/01965 <Betrag>
  Fälligkeit bis: <Datum>“. Beide Beträge müssen gleich sein, sonst Hinweis an Josh.
- Nicht enthalten: die einheitliche Pauschsteuer 2 % der Minijobber (geht per Lastschrift an die Knappschaft).
- DATEV nennt als Zahlart „Lastschrift“; tatsächlich wird bisher per Online-Überweisung gezahlt.

Beispiele: Oktober 2026 → 1.472,21 €, fällig 10.11.2026; November 2026 → 2.284,54 € (LSt 2.205,90 + KiSt 78,64),
fällig 10.12.2026.

## Protokoll und Bestätigung

`register/lohnsteuer.csv` – eine Zeile je Monat: monat, betrag, faellig, quelle, erinnert_erstmals, erinnert_zuletzt,
thread_id, status (`offen` / `bezahlt`), bestaetigt_am, notiz.

Josh bestätigt, indem er auf die Erinnerungsmail antwortet (z. B. „bezahlt“, „überwiesen“, „erledigt“). Die Aufgabe
liest den Thread und setzt dann `status=bezahlt`; danach keine Erinnerung mehr für diesen Monat.
