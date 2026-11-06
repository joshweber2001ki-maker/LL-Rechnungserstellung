#!/usr/bin/env python3
"""CLI: Finanzsheet-Zeile -> Vorprüfung -> Dokument-JSONs -> PDFs.

  python3 -m invoice.cli build --sheet-json data/sheet.json --nummer 288      # Daten über die Brücke, Nummern automatisch
  python3 -m invoice.cli build --kampagnen data/kampagnen.csv --adressen data/finanzsheet.xlsx \
      --nummer 288 [--datum 2026-11-02] [--nr-kunde AR-2026-002 --nr-fee LL-2026-156] \
      [--expenses belege.json] [--out out/288] [--pdf]

  python3 -m invoice.cli storno --doc out/288/DR-2026-030.json --nummer DR-2026-031 --grund "..." [--ersatz DR-2026-032] --out out/storno --pdf

Ausgabe: <out>/befund.json (findings + meta), <out>/<Nr>.json je Dokument, optional PDFs.
Exit-Code 0 = Dokumente erzeugt, 3 = Stopp-Befund (keine Dokumente), 2 = Aufrufe falsch.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

from . import register, sheet
from .build import build_invoices, cancellation_doc

ROOT = Path(__file__).resolve().parent.parent


def betriebsmodus():
    try:
        return (yaml.safe_load((ROOT / "config" / "betrieb.yaml").read_text(encoding="utf-8")) or {}).get("modus", "schatten")
    except FileNotFoundError:
        return "schatten"


def numbers_from_sheet(row, prefix, year):
    """Bereits im Finanzsheet eingetragene Nummern (z. B. von n8n) für diese Zeile – die zuletzt genannte zählt."""
    found = {}
    for field, key, pref in (("rechnung_creator", "kunde", prefix), ("rechnung_ll", "fee", "LL")):
        hits = re.findall(rf"\b({re.escape(pref)}-{year}-\d{{3}})\b", row.get(field, "") or "")
        if hits:
            found[key] = hits[-1]
    return found


def assign_numbers(row, rows, out_root, issue, modus):
    """Vergibt Kunden- und Fee-Nummer (Regel 8 / 14).

    1. Steht für die Zeile schon eine Nummer im Finanzsheet, wird sie übernommen.
    2. Sonst nächste freie Nummer = max(Register, Finanzsheet, in diesem Lauf schon vergeben) + 1.
       Innerhalb eines Laufs merkt sich out/_vergeben.json die Vergaben, damit zwei Events nicht dieselbe
       Nummer bekommen; derselbe Vorgang bekommt beim erneuten Aufruf dieselbe Nummer.
    Im Modus produktiv ist ein Widerspruch Register ↔ Finanzsheet ein Stopp, im Schattenmodus nur ein Hinweis.
    """
    creators = yaml.safe_load((ROOT / "config" / "creators.yaml").read_text(encoding="utf-8")) or {}
    ccfg = creators.get(row["creator"].strip())
    findings = []
    if not ccfg:
        return {}, findings
    prefix, year = ccfg["prefix"], issue.year
    from_sheet = numbers_from_sheet(row, prefix, year)
    state_file = Path(out_root) / "_vergeben.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}
    if str(row["nummer"]) in state:
        return state[str(row["nummer"])], findings
    reg_rows = register.load()
    sheet_max = sheet.max_numbers(rows, year)
    given = [n for v in state.values() for n in (v.get("kunde"), v.get("fee")) if n]
    result = {"quelle": {}}
    for key, pref in (("kunde", prefix), ("fee", "LL")):
        if key in from_sheet:
            result[key] = from_sheet[key]
            result["quelle"][key] = "finanzsheet"
            continue
        run_max = max([int(n.rsplit("-", 1)[1]) for n in given if n.startswith(f"{pref}-{year}-")] or [0])
        number, conflict = register.next_number(reg_rows, pref, year, max(sheet_max.get(pref, 0), run_max))
        if conflict and run_max < sheet_max.get(pref, 0):
            findings.append({"level": "stop" if modus == "produktiv" else "warn", "text": f"Nummernkreis {pref}: {conflict}"})
        result[key] = number
        result["quelle"][key] = "neu"
        given.append(number)
    state[str(row["nummer"])] = result
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return result, findings


def cmd_build(a):
    if a.sheet_json:
        tabs = json.loads(Path(a.sheet_json).read_text(encoding="utf-8"))
        rows = sheet.load_kampagnen_values(tabs["Finance | Kampagnen"])
        addr = sheet.load_creator_addresses_values(tabs["Finance I Creator-Adressen"])
    else:
        rows = sheet.load_kampagnen(Path(a.kampagnen).read_text(encoding="utf-8"))
        if a.adressen.endswith(".xlsx"):
            addr = sheet.load_creator_addresses(a.adressen)
        else:
            addr = sheet.load_creator_addresses_csv(Path(a.adressen).read_text(encoding="utf-8"))
    hits = sheet.find_row(rows, a.nummer)
    out = Path(a.out or f"out/{a.nummer}")
    out.mkdir(parents=True, exist_ok=True)
    if len(hits) != 1:
        res = {"findings": [{"level": "stop", "text": f"Nummer {a.nummer}: {len(hits)} Treffer im Finanzsheet (erwartet 1)."}], "meta": {}}
        (out / "befund.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 3
    row = hits[0]
    expenses = json.loads(Path(a.expenses).read_text(encoding="utf-8")) if a.expenses else None
    issue = date.fromisoformat(a.datum) if a.datum else date.today()
    nr_kunde, nr_fee, num_findings, num_info = a.nr_kunde, a.nr_fee, [], None
    if a.nummern == "auto" and not (nr_kunde and nr_fee):
        num_info, num_findings = assign_numbers(row, rows, out.parent, issue, betriebsmodus())
        nr_kunde = nr_kunde or num_info.get("kunde")
        nr_fee = nr_fee or num_info.get("fee")
    res = build_invoices(row, addr, issue_date=issue, number_customer=nr_kunde or "ENTWURF",
                         number_fee=nr_fee or "ENTWURF", expenses=expenses, lang_override=a.lang)
    res["findings"] = num_findings + res["findings"]
    if num_info:
        res["meta"]["nummern"] = num_info
    res["sheet_max_numbers"] = sheet.max_numbers(rows, row.get("jahr") or issue.year)
    res["row"] = row
    befund = {k: res[k] for k in ("findings", "tax_case", "meta", "sheet_max_numbers", "row")}
    (out / "befund.json").write_text(json.dumps(befund, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    stop = any(x["level"] == "stop" for x in res["findings"])
    print(json.dumps({"findings": res["findings"], "tax_case": res["tax_case"], "meta": res["meta"]}, ensure_ascii=False, indent=2, default=str))
    if stop or not res["customer"]:
        return 3
    for key in ("customer", "fee"):
        doc = res[key]
        name = doc["number"] if doc["number"] != "ENTWURF" else f"ENTWURF-{key}-{a.nummer}"
        p = out / f"{name}.json"
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print("->", p)
        if a.pdf:
            from render.render import render_pdf
            print("->", render_pdf(doc, out / f"Rechnung-{name}.pdf"))
    return 0


def cmd_storno(a):
    original = json.loads(Path(a.doc).read_text(encoding="utf-8"))
    issue = date.fromisoformat(a.datum) if a.datum else date.today()
    doc = cancellation_doc(original, a.nummer, issue, a.grund, replacement=a.ersatz)
    out = Path(a.out or "out/storno")
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{a.nummer}.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("->", p)
    if a.pdf:
        from render.render import render_pdf
        print("->", render_pdf(doc, out / f"Stornorechnung-{a.nummer}.pdf"))
    return 0


def main(argv=None):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--kampagnen", help="CSV-Export Tab 'Finance | Kampagnen'")
    b.add_argument("--adressen", help="XLSX/CSV mit Tab 'Finance I Creator-Adressen'")
    b.add_argument("--sheet-json", help="JSON der Brücke (action=sheet) mit beiden Tabs – ersetzt --kampagnen/--adressen")
    b.add_argument("--nummer", required=True)
    b.add_argument("--datum")
    b.add_argument("--nr-kunde")
    b.add_argument("--nr-fee")
    b.add_argument("--nummern", choices=["auto", "keine"], default="auto",
                   help="auto (Standard): Nummer aus dem Finanzsheet übernehmen oder nächste freie vergeben; keine: ENTWURF")
    b.add_argument("--expenses")
    b.add_argument("--lang", choices=["de", "en"])
    b.add_argument("--out")
    b.add_argument("--pdf", action="store_true")
    b.set_defaults(fn=cmd_build)
    s = sub.add_parser("storno")
    s.add_argument("--doc", required=True)
    s.add_argument("--nummer", required=True)
    s.add_argument("--grund", required=True)
    s.add_argument("--ersatz")
    s.add_argument("--datum")
    s.add_argument("--out")
    s.add_argument("--pdf", action="store_true")
    s.set_defaults(fn=cmd_storno)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
