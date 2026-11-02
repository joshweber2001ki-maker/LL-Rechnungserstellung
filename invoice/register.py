"""Rechnungsregister: eine Zeile je Dokument, als CSV im Repo (register/rechnungsregister.csv).

Status-Lebenszyklus: entwurf -> gesendet -> bezahlt | storniert ; entwurf -> verworfen.
Zeilen aus dem Altsystem (n8n) werden beim Import mit status=altsystem übernommen.

Nummernvergabe: nächste Nummer je (kreis, jahr) = max(Register, Finanzsheet) + 1.
Weichen Register und Finanzsheet voneinander ab (Register kennt eine Nummer nicht, die im Sheet steht,
oder umgekehrt), liefert next_number() einen Konflikt – dann Rückfrage statt Vergabe.
"""
import csv
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "register" / "rechnungsregister.csv"

FIELDS = ["nummer", "typ", "kreis", "jahr", "lfd", "sheet_nummer", "kunde", "creator", "datum", "netto", "steuer",
          "brutto", "waehrung", "steuerfall", "status", "referenz", "drive_kopie", "drive_kampagne", "gmail_draft",
          "event_id", "erstellt_am", "gesendet_am", "modus", "notiz"]

NUM = re.compile(r"^([A-Z]{1,4})-(\d{4})-(\d{3})$")


def load(path=REGISTER):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def save(rows, path=REGISTER):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r.get("kreis", ""), int(r.get("jahr") or 0), int(r.get("lfd") or 0)))
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def split_number(number):
    m = NUM.match(number.strip())
    if not m:
        raise ValueError(f"Ungültige Rechnungsnummer: {number}")
    return m.group(1), int(m.group(2)), int(m.group(3))


def max_in_register(rows, prefix, year):
    nums = [int(r["lfd"]) for r in rows if r.get("kreis") == prefix and str(r.get("jahr")) == str(year)]
    return max(nums) if nums else 0


def next_number(rows, prefix, year, sheet_max=None, digits=3):
    """Gibt (nummer, konflikt). konflikt=None wenn Register und Sheet übereinstimmen."""
    reg_max = max_in_register(rows, prefix, year)
    conflict = None
    if sheet_max is not None and sheet_max > reg_max:
        conflict = f"Finanzsheet kennt {prefix}-{year}-{sheet_max:0{digits}d}, Register nur bis {reg_max:0{digits}d} – Register nachziehen (import) oder prüfen."
    n = max(reg_max, sheet_max or 0) + 1
    return f"{prefix}-{year}-{n:0{digits}d}", conflict


def exists(rows, number):
    return any(r["nummer"] == number for r in rows)


def find_by_sheet(rows, sheet_nummer, typ="kunde"):
    return [r for r in rows if r.get("sheet_nummer") == str(sheet_nummer) and r.get("typ") == typ
            and r.get("status") not in ("verworfen", "storniert")]


def reserve(rows, number, typ, meta, doc, status="entwurf", modus="produktiv", event_id="", notiz=""):
    """Legt eine Registerzeile an (idempotent über die Nummer)."""
    if exists(rows, number):
        raise ValueError(f"{number} ist bereits im Register.")
    prefix, year, lfd = split_number(number)
    tax = next((t["value"] for t in doc["totals"] if t["label"].lower().startswith(("zzgl", "vat", "umsatzsteuer", "ksk"))), 0)
    rows.append({
        "nummer": number, "typ": typ, "kreis": prefix, "jahr": year, "lfd": lfd,
        "sheet_nummer": meta.get("nummer", ""), "kunde": meta.get("kunde", ""), "creator": meta.get("creator", ""),
        "datum": doc["date"], "netto": doc["totals"][0]["value"] if doc["totals"] else "",
        "steuer": tax, "brutto": doc["totals"][-1]["value"] if doc["totals"] else "",
        "waehrung": doc.get("currency", "EUR"), "steuerfall": meta.get("tax_case", ""), "status": status,
        "referenz": doc.get("cancels", {}).get("number") if doc.get("cancels") else (doc.get("replaces", {}) or {}).get("number", ""),
        "drive_kopie": "", "drive_kampagne": "", "gmail_draft": "", "event_id": event_id,
        "erstellt_am": datetime.now().strftime("%Y-%m-%d %H:%M"), "gesendet_am": "", "modus": modus, "notiz": notiz,
    })
    return rows


def set_status(rows, number, status, **fields):
    for r in rows:
        if r["nummer"] == number:
            r["status"] = status
            if status == "gesendet" and not r.get("gesendet_am"):
                r["gesendet_am"] = datetime.now().strftime("%Y-%m-%d")
            for k, v in fields.items():
                if k in FIELDS:
                    r[k] = v
            return r
    raise ValueError(f"{number} nicht im Register.")


def import_from_sheet(rows, sheet_rows, year):
    """Übernimmt alle im Finanzsheet eingetragenen Nummern eines Jahres als Altsystem-Zeilen."""
    pat = re.compile(r"([A-Z]{1,4})-(\d{4})-(\d{3})")
    added = 0
    for r in sheet_rows:
        for field, typ in (("rechnung_creator", "kunde"), ("rechnung_ll", "fee")):
            for prefix, y, n in pat.findall(r.get(field, "")):
                if int(y) != year:
                    continue
                number = f"{prefix}-{y}-{n}"
                if exists(rows, number):
                    continue
                storniert = "storno" in r.get(field, "").lower()
                rows.append({
                    "nummer": number, "typ": typ, "kreis": prefix, "jahr": int(y), "lfd": int(n),
                    "sheet_nummer": r.get("nummer", ""), "kunde": r.get("kunde", ""), "creator": r.get("creator", ""),
                    "datum": "", "netto": "", "steuer": "", "brutto": "", "waehrung": "EUR", "steuerfall": "",
                    "status": "storniert" if storniert else "altsystem", "referenz": "", "drive_kopie": "", "drive_kampagne": "", "gmail_draft": "",
                    "event_id": "", "erstellt_am": datetime.now().strftime("%Y-%m-%d"), "gesendet_am": "",
                    "modus": "n8n", "notiz": f"Import aus Finanzsheet ({field})",
                })
                added += 1
    return added


if __name__ == "__main__":
    import sys
    from . import sheet as sh
    if len(sys.argv) >= 3 and sys.argv[1] == "import":
        rows = load()
        srows = sh.load_kampagnen(Path(sys.argv[2]).read_text(encoding="utf-8"))
        year = int(sys.argv[3]) if len(sys.argv) > 3 else datetime.now().year
        n = import_from_sheet(rows, srows, year)
        save(rows)
        print(f"{n} Nummern importiert, Register hat {len(rows)} Zeilen -> {REGISTER}")
    elif len(sys.argv) >= 2 and sys.argv[1] == "next":
        rows = load()
        print(next_number(rows, sys.argv[2], int(sys.argv[3])))
    else:
        print("python3 -m invoice.register import <kampagnen.csv> [jahr] | next <KREIS> <jahr>")
