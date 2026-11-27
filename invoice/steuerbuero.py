"""Monatssammlung Ausgangsrechnungen an das Steuerbüro (simbadirekt, Postfach A = Ausgangsrechnungen) – Regel 17.

Am 5. jedes Monats gehen ALLE Kundenrechnungen (Creator-Nummernkreise, inkl. Stornos) und Management-Fee-Rechnungen
(LL-) des Vormonats gesammelt in EINER Mail an simbadirekt. Es wird nur ein Gmail-Entwurf angelegt – Josh sendet.

    python3 -m invoice.steuerbuero liste 2026-11 --sheet-json data/sheet.json    # Liste + Lücken + PDFs, nichts angelegt
    python3 -m invoice.steuerbuero entwurf 2026-11 --sheet-json data/sheet.json [--neu]   # Entwurf über die Brücke

Quellen: Register (Rechnungsdatum im Monat, Status ≠ verworfen) → PDF aus `drive_kopie`; Altsystem-Rechnungen ohne
Datum im Register aus dem Finanzsheet (Datum = Fälligkeit − Zahlungsfrist, als „geschätzt“ markiert). PDF ohne
Register-Link: Drive-Suche nach `Rechnung-<Nr>.pdf` / `Stornorechnung-<Nr>.pdf` (Kampagnenordner vor
_parallelbetrieb; mehrdeutig ⇒ ohne PDF + Kandidaten). Protokoll: register/steuerbuero.csv (ein Entwurf je Monat).
"""
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from invoice import register as reg

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "register" / "steuerbuero.csv"
LOG_FIELDS = ["monat", "teil", "nummern", "anzahl", "draft_id", "erstellt_am", "status", "notiz"]
SIMBA_A = "rzmd-iyyam-a@belege.simbadirekt.de"
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember"]
MAX_FILES = 60   # je Entwurf; mehr (oder > 24 MB) ⇒ mehrere Teile


def drive_id(url):
    m = re.search(r"/d/([A-Za-z0-9_-]{20,})", url or "") or re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", url or "")
    return m.group(1) if m else None


def in_month(datum, year, month):
    try:
        d = datetime.strptime(datum.strip(), "%d.%m.%Y")
    except (ValueError, AttributeError):
        return False
    return d.year == year and d.month == month


NUM_IN_TEXT = re.compile(r"\b([A-Z]{1,4}-\d{4}-\d{3})\b")
DATE_IN_TEXT = re.compile(r"(\d{2}\.\d{2}\.\d{4})")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _kunde_tokens(kunde):
    words = [w for w in re.split(r"[^A-Za-zÄÖÜäöüß0-9]+", str(kunde or "")) if w]
    toks = {_norm(w) for w in words if len(w) >= 4}
    if len(words) >= 2:
        toks.add(_norm(words[0][:2] + words[1][:2]))          # „American Express“ → „amex“
    toks.add(_norm(kunde))
    return {t for t in toks if len(t) >= 3}


def sheet_invoices(sheet_json):
    """Nummern aus den Sheet-Spalten „Rechnung Creator:in“ / „Rechnung L&L“ mit geschätztem Rechnungsdatum
    (Fälligkeit − Zahlungsfrist) – für Rechnungen aus dem Altsystem ohne Datum im Register."""
    from datetime import timedelta
    tab = json.load(open(sheet_json, encoding="utf-8"))["Finance | Kampagnen"]
    head = [str(h).replace("\n", " ").strip().lower() for h in tab[0]]

    def col(name):
        return next(i for i, h in enumerate(head) if h.replace(" ", "") == name.replace(" ", ""))
    c_k, c_f, c_z = col("kunde"), col("rechnung fällig am"), col("zahlungsfrist")
    c_rc, c_rl = col("rechnung creator:in"), col("rechnung l&l")
    out = {}
    for r in tab[1:]:
        if len(r) <= c_rl:
            continue
        m = DATE_IN_TEXT.search(str(r[c_f]))
        if not m:
            continue
        frist = re.search(r"\d+", str(r[c_z]))
        due = datetime.strptime(m.group(1), "%d.%m.%Y")
        datum = due - timedelta(days=int(frist.group(0)) if frist else 14)
        for c, typ in ((c_rc, "kunde"), (c_rl, "fee")):
            for nr in NUM_IN_TEXT.findall(str(r[c])):
                out.setdefault(nr, []).append({"nummer": nr, "typ": typ, "sheet_nummer": str(r[0]).strip(),
                                               "kunde": str(r[c_k]).strip(), "datum": datum.strftime("%d.%m.%Y")})
    return out


def pick_file(nr, kunde, used):
    """PDF zu einer Nummer in Drive suchen. → (file|None, kandidaten)"""
    from invoice.bridge import find
    names = [f"Rechnung-{nr}.pdf", f"Stornorechnung-{nr}.pdf"]
    cands = [f for n in names for f in find(n, "application/pdf") if f["id"] not in used]
    if len(cands) <= 1:
        return (cands[0] if cands else None), cands
    real = [f for f in cands if "_parallelbetrieb" not in f.get("parents", [])] or cands
    if len(real) == 1:
        return real[0], cands
    toks = _kunde_tokens(kunde)
    hit = [f for f in real if any(t in _norm(" ".join(f.get("parents", [])[:2])) for t in toks)]
    if len(hit) == 1:
        return hit[0], cands
    return None, cands


def liste(ym, with_drive=True, sheet_json=None):
    year, month = (int(x) for x in ym.split("-"))
    rows = reg.load()
    items, ohne_pdf, verworfen, befunde = [], [], [], []
    used = set()
    # 1) Register: Rechnungsdatum im Monat
    reg_nrs = {}
    for r in rows:
        reg_nrs.setdefault(r["nummer"], []).append(r)
    for r in rows:
        if not in_month(r.get("datum", ""), year, month):
            continue
        nr = r["nummer"]
        if r.get("status") == "verworfen":
            verworfen.append(nr)
            continue
        it = {"nummer": nr, "typ": r.get("typ"), "datum": r.get("datum"), "kunde": r.get("kunde"),
              "sheet_nummer": r.get("sheet_nummer"), "status": r.get("status"), "datum_geschaetzt": False,
              "drive_id": drive_id(r.get("drive_kopie")), "quelle": "register"}
        items.append(it)
        if it["drive_id"]:
            used.add(it["drive_id"])
    # 2) Finanzsheet: Altsystem-Rechnungen ohne Datum im Register, Datum = Fälligkeit − Zahlungsfrist
    if sheet_json:
        have = {i["nummer"] for i in items}
        for nr, lst in sheet_invoices(sheet_json).items():
            if nr in have or any(r.get("datum") for r in reg_nrs.get(nr, [])):
                continue
            for s in lst:
                if in_month(s["datum"], year, month):
                    items.append(dict(s, status="altsystem", datum_geschaetzt=True, drive_id=None, quelle="finanzsheet"))
    # 3) PDF suchen, wo das Register keinen Link hat
    for it in items:
        if not it["drive_id"] and with_drive:
            f, cands = pick_file(it["nummer"], it["kunde"], used)
            if f:
                it["drive_id"], it["quelle"] = f["id"], it["quelle"] + " + Drive: " + "/".join(reversed(f.get("parents", [])[:2]))
                used.add(f["id"])
            else:
                it["kandidaten"] = [{"id": c["id"], "ordner": "/".join(reversed(c.get("parents", [])[:3]))} for c in cands]
    ohne_pdf = [i for i in items if not i["drive_id"]]
    items = [i for i in items if i["drive_id"]]
    from collections import Counter
    for nr, n in Counter(i["nummer"] for i in items + ohne_pdf).items():
        if n > 1:
            befunde.append(f"{nr} kommt im Monat {n}× vor (verschiedene Vorgänge, alle Dateien angehängt) – bitte prüfen.")
    geschaetzt = [i["nummer"] for i in items + ohne_pdf if i.get("datum_geschaetzt")]
    # Lücken je Nummernkreis zwischen kleinster und größter Nummer des Monats
    luecken, anderer_monat = [], []
    all_nrs = {i["nummer"] for i in items + ohne_pdf} | set(verworfen)
    by_kreis = {}
    for nr in all_nrs:
        k, y, n = reg.split_number(nr)
        by_kreis.setdefault(k, set()).add(n)
    sheet_all = sheet_invoices(sheet_json) if sheet_json else {}
    for k, nums in sorted(by_kreis.items()):
        for n in range(min(nums), max(nums) + 1):
            nr = f"{k}-{year}-{n:03d}"
            if n in nums:
                continue
            where = []
            other = [x for x in reg_nrs.get(nr, []) if x.get("datum") and not in_month(x["datum"], year, month)] + \
                    [x for x in sheet_all.get(nr, []) if not in_month(x["datum"], year, month)]
            if other and not any(in_month(x.get("datum", ""), year, month) for x in reg_nrs.get(nr, []) + sheet_all.get(nr, [])):
                anderer_monat.append(f"{nr} ({other[0]['datum']}{', geschätzt' if nr not in reg_nrs or not reg_nrs[nr][0].get('datum') else ''})")
                continue
            if nr in reg_nrs:
                where.append("Register: " + ", ".join(f"{r.get('datum') or 'ohne Datum'} {r.get('status')}" for r in reg_nrs[nr]))
            if nr in sheet_all:
                where.append("Sheet: Datum geschätzt " + ", ".join(s["datum"] for s in sheet_all[nr]))
            luecken.append(f"{nr} ({'; '.join(where) or 'weder Register noch Finanzsheet'})")
    return {"monat": ym, "an": SIMBA_A, "anzahl": len(items), "items": items, "ohne_pdf": ohne_pdf,
            "verworfen": verworfen, "datum_geschaetzt": geschaetzt, "luecken": luecken, "anderer_monat": anderer_monat, "befunde": befunde,
            "teile": max(1, -(-len(items) // MAX_FILES))}


def load_log():
    if not LOG.exists():
        return []
    with LOG.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_log(row):
    exists = LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in LOG_FIELDS})


def entwurf(ym, neu=False, sheet_json=None):
    from invoice.bridge import call
    done = [r for r in load_log() if r["monat"] == ym and r["status"] in ("entwurf_angelegt", "gesendet")]
    if done and not neu:
        raise SystemExit(f"Für {ym} gibt es schon einen Entwurf ({', '.join(r['draft_id'] for r in done)}) – "
                         f"nur mit --neu erneut (vorher alten Entwurf löschen).")
    data = liste(ym, sheet_json=sheet_json)
    if not data["items"]:
        raise SystemExit(f"Keine Rechnungen mit PDF für {ym}.")
    year, month = (int(x) for x in ym.split("-"))
    items = sorted(data["items"], key=lambda i: (i["typ"] != "kunde" and i["typ"] != "storno", i["nummer"]))
    teile = [items[i:i + MAX_FILES] for i in range(0, len(items), MAX_FILES)]
    # Größe vorab prüfen (Gmail-Limit 25 MB): zu große Teile halbieren
    sizes = {i["drive_id"]: int(call("info", fileId=i["drive_id"]).get("size") or 0) for i in items}
    def split(part):
        if len(part) > 1 and sum(sizes[i["drive_id"]] for i in part) > 20 * 1024 * 1024:
            h = len(part) // 2
            return split(part[:h]) + split(part[h:])
        return [part]
    teile = [p for t in teile for p in split(t)]
    res = []
    for t, part in enumerate(teile, 1):
        suffix = f" (Teil {t}/{len(teile)})" if len(teile) > 1 else ""
        subject = f"Ausgangsrechnungen {MONATE[month - 1]} {year}{suffix}"
        text = (f"Ausgangsrechnungen {MONATE[month - 1]} {year} – {len(part)} Rechnungen "
                f"(Kundenrechnungen und Management-Fee-Rechnungen):\n\n"
                + "\n".join(f"{i['nummer']} · {i['datum']} · {i['kunde'] or ''}" for i in part))
        out = call("draftDrive", to=[SIMBA_A], subject=subject, text=text, fileIds=[i["drive_id"] for i in part])
        write_log({"monat": ym, "teil": f"{t}/{len(teile)}", "nummern": " ".join(i["nummer"] for i in part),
                   "anzahl": len(part), "draft_id": out["draftId"], "erstellt_am": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "status": "entwurf_angelegt", "notiz": f"{out.get('bytes')} Bytes"})
        res.append({"teil": t, "subject": subject, "draftId": out["draftId"], "messageId": out.get("messageId"),
                    "anzahl": len(part), "bytes": out.get("bytes")})
    return {"monat": ym, "entwuerfe": res, "ohne_pdf": data["ohne_pdf"], "luecken": data["luecken"],
            "datum_geschaetzt": data["datum_geschaetzt"], "anderer_monat": data["anderer_monat"],
            "verworfen": data["verworfen"], "befunde": data["befunde"]}


if __name__ == "__main__":
    a = sys.argv[1:]
    sj = a[a.index("--sheet-json") + 1] if "--sheet-json" in a else None
    if len(a) >= 2 and a[0] == "liste":
        print(json.dumps(liste(a[1], with_drive="--ohne-drive" not in a, sheet_json=sj), ensure_ascii=False, indent=1))
    elif len(a) >= 2 and a[0] == "entwurf":
        print(json.dumps(entwurf(a[1], neu="--neu" in a, sheet_json=sj), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        sys.exit(2)
