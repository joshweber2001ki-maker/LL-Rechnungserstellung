# Dokument-JSON (Eingabe für render/render.py)

```json
{
  "doc_type": "invoice | cancellation | reimbursement",
  "category": "customer | fee",            // Kundenrechnung (grau-blau) oder Fee-Rechnung (schwarz)
  "lang": "de | en",
  "currency": "EUR | USD",
  "number": "DR-2026-030",
  "date": "30.09.2026",
  "service_period": "September 2026",
  "cancels":  {"number": "DR-2026-024", "date": "31.07.2026"},   // nur Storno
  "replaces": {"number": "LL-2026-103", "date": "31.07.2026"},   // nur Ersatzrechnung
  "recipient": {
    "lines": ["CASIO Europe GmbH", "Casio-Platz 1", "22848 Norderstedt", "Deutschland"],
    "ids":   [{"label": "VAT", "value": "DK31081610"}],
    "refs":  [{"label": "Bestellnummer", "value": "4700001050"}]
  },
  "items": [
    {"title": "Instagram-Karussellbeitrag", "lines": ["Kampagne: EDIFICE · Go Live: 30.09.2026", "@daniel.reith (Instagram)"],
     "qty": 1, "unit_price": 1200.0, "amount": 1200.0},
    {"kind": "group", "title": "Weiterberechnete Auslagen (netto, Belege im Anhang)"},
    {"kind": "sub", "title": "Taxi · Beleg 123", "qty": 1, "unit_price": 56.07, "amount": 56.07}
  ],
  "totals": [
    {"label": "NETTOSUMME:", "value": 1600.0, "style": "sub"},
    {"label": "zzgl. MwSt. (19%)", "value": 304.0},
    {"label": "BRUTTOSUMME:", "value": 1904.0, "style": "grand"}
  ],
  "payment_text": "Bitte begleichen Sie …",      // fett
  "highlights": ["Diese Stornorechnung hebt … auf."],   // fett, unter payment_text
  "notes": ["Hinweis: …", {"text": "Grund der Stornierung: …", "plain": true}],  // kursiv, plain = aufrecht
  "annexes": [{"title": "…", "intro": "…", "rows": [{"title": "…", "pages": "S. 3", "gross": 1.0, "net": 0.84}],
               "budget": {"title": "…", "rows": [{"label": "…", "value": 1.0, "style": "sum"}]}}]
}
```
Beträge als Zahlen (float), Formatierung übernimmt der Renderer (`1.234,56 €` / `€1,234.56`).
Negative Beträge für Stornos. `items[].lines` werden kursiv unter dem Titel gesetzt.
