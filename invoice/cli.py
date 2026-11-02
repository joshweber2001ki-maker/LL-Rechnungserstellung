#!/usr/bin/env python3
"""CLI: Finanzsheet-Zeile -> Vorprüfung -> Dokument-JSONs -> PDFs.

  python3 -m invoice.cli build --kampagnen data/kampagnen.csv --adressen data/finanzsheet.xlsx \
      --nummer 288 [--datum 2026-11-02] [--nr-kunde AR-2026-002 --nr-fee LL-2026-156] \
      [--expenses belege.json] [--out out/288] [--pdf]

  python3 -m invoice.cli storno --doc out/288/DR-2026-030.json --nummer DR-2026-031 --grund "..." [--ersatz DR-2026-032] --out out/storno --pdf

Ausgabe: <out>/befund.json (findings + meta), <out>/<Nr>.json je Dokument, optional PDFs.
Exit-Code 0 = Dokumente erzeugt, 3 = Stopp-Befund (keine Dokumente), 2 = Aufrufe falsch.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import sheet
from .build import build_invoices, cancellation_doc


def cmd_build(a):
    rows = sheet.load_kampagnen(Path(a.kampagnen).read_text(encoding="utf-8"))
    hits = sheet.find_row(rows, a.nummer)
    out = Path(a.out or f"out/{a.nummer}")
    out.mkdir(parents=True, exist_ok=True)
    if len(hits) != 1:
        res = {"findings": [{"level": "stop", "text": f"Nummer {a.nummer}: {len(hits)} Treffer im Finanzsheet (erwartet 1)."}], "meta": {}}
        (out / "befund.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 3
    row = hits[0]
    if a.adressen.endswith(".xlsx"):
        addr = sheet.load_creator_addresses(a.adressen)
    else:
        addr = sheet.load_creator_addresses_csv(Path(a.adressen).read_text(encoding="utf-8"))
    expenses = json.loads(Path(a.expenses).read_text(encoding="utf-8")) if a.expenses else None
    issue = date.fromisoformat(a.datum) if a.datum else date.today()
    res = build_invoices(row, addr, issue_date=issue, number_customer=a.nr_kunde or "ENTWURF",
                         number_fee=a.nr_fee or "ENTWURF", expenses=expenses, lang_override=a.lang)
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
    b.add_argument("--kampagnen", required=True)
    b.add_argument("--adressen", required=True)
    b.add_argument("--nummer", required=True)
    b.add_argument("--datum")
    b.add_argument("--nr-kunde")
    b.add_argument("--nr-fee")
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
