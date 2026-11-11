#!/usr/bin/env python3
"""Zahlungserinnerungen (Regel 15): überfällige Kundenrechnungen finden, Entwurfstext bauen, Protokoll führen.

    python3 -m invoice.erinnerung pruefen --sheet-json data/sheet.json [--datum JJJJ-MM-TT]
        -> out/erinnerungen/pruefung.json: Gruppen (je An-Adresse eine Mail), Übersprungene, Wiedervorlagen
    python3 -m invoice.erinnerung text <gruppe> [--nachfrage]
        -> out/erinnerungen/<gruppe>.json mit to/cc/subject/text/html (legt KEINEN Entwurf an)
    python3 -m invoice.erinnerung log <Nr>[,<Nr>] --aktion <aktion> [--grund "…"] [--draft-id X]
                                      [--wiedervorlage JJJJ-MM-TT] [--datum JJJJ-MM-TT]
        -> hängt an register/zahlungserinnerungen.csv an (danach committen + pushen)

Aktionen im Protokoll (die jeweils LETZTE Zeile je Rechnungsnummer zählt):
    entwurf_angelegt   Erinnerungsentwurf liegt in Gmail            -> nie wieder automatisch erinnern
    manuell_erinnert   in Gmail lag schon eine Erinnerung/Entwurf   -> nie wieder automatisch erinnern
    zurueckgestellt    Kunde hat Verzögerung/Zahlung angekündigt    -> erst ab --wiedervorlage wieder prüfen
    rueckfrage         Kunde bestreitet/will Korrektur, unklar      -> kein Entwurf, Josh entscheidet
    erledigt           Kunde meldet Zahlung als erfolgt             -> kein Entwurf; bleibt in der Liste, bis das
                                                                       Sheet „RE bezahlt“ zeigt
    freigegeben        Josh hat rueckfrage/erledigt aufgelöst       -> ab dem nächsten Lauf wieder normal prüfen

Die Gmail-Prüfungen (schon erinnert? Rückmeldung des Kunden?) macht der Lauf per Connector – siehe Skill.
"""
import argparse
import csv
import html as htmlmod
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from . import sheet
from .build import customer_override
from .mail import en_date, first_name, parse_recipients

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "register" / "zahlungserinnerungen.csv"
OUT = ROOT / "out" / "erinnerungen"
FIELDS = ["datum", "nummer", "sheet_nummer", "kunde", "creator", "kontakt", "faellig", "betrag", "aktion", "grund",
          "wiedervorlage", "draft_id"]
OFFEN = {"re gestellt", "za überfällig"}          # Sheet-Status, bei denen erinnert werden darf
ERINNERT = {"re erinnerung gesendet"}             # Sheet sagt: Erinnerung ist schon raus
NIE_WIEDER = {"entwurf_angelegt", "manuell_erinnert"}
NUM = re.compile(r"\b([A-Z]{1,4}-\d{4}-\d{3})\b")


def settings():
    cfg = yaml.safe_load((ROOT / "config" / "betrieb.yaml").read_text(encoding="utf-8")) or {}
    z = cfg.get("zahlungserinnerung") or {}
    return {"tage": int(z.get("tage_ueberfaellig", 3)), "wiedervorlage": int(z.get("wiedervorlage_tage", 7)),
            "nachfassen": int(z.get("hinweis_nach_tagen", 14)), "aktiv": z.get("aktiv", True)}


def load_log():
    if not LOG.exists():
        return []
    with LOG.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def last_entries(log):
    last = {}
    for r in log:
        last[r["nummer"]] = r
    return last


def parse_due(text):
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text or "")
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def money(amount, cur, lang):
    if amount is None:
        return ""
    if lang == "en":
        return f"{amount:,.2f} {cur}"
    s = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {'€' if cur == 'EUR' else cur}"


def pruefen(rows, today, cfg=None):
    cfg = cfg or settings()
    customers = yaml.safe_load((ROOT / "config" / "customers.yaml").read_text(encoding="utf-8")) or {}
    last = last_entries(load_log())
    kandidaten, skipped, erinnert_offen = [], [], []
    for r in rows:
        status = (r.get("rechnung_status") or "").strip().lower()
        nums = NUM.findall(r.get("rechnung_creator") or "")
        if not nums or status not in OFFEN | ERINNERT:
            continue
        nr = nums[-1]
        due = parse_due(r.get("faellig"))
        base = {"nummer": nr, "sheet_nummer": r["nummer"], "kunde": r["kunde"].split("\n")[0].strip(),
                "creator": r["creator"].strip(), "faellig": due.strftime("%d.%m.%Y") if due else "",
                "status_sheet": r.get("rechnung_status", "").strip()}
        if not due:
            skipped.append(dict(base, grund="Fälligkeit im Sheet nicht lesbar"))
            continue
        tage = (today - due).days
        base["tage_ueberfaellig"] = tage
        entry = last.get(nr)
        if entry and entry["aktion"] == "freigegeben":  # Josh hat eine Rückfrage aufgelöst: wieder normal prüfen
            entry = None
        if status in ERINNERT or (entry and entry["aktion"] in NIE_WIEDER):
            seit = entry["datum"] if entry else ""
            d = dict(base, erinnert_am=seit, quelle="Protokoll" if entry and entry["aktion"] in NIE_WIEDER else "Sheet-Status")
            if seit and (today - date.fromisoformat(seit)).days >= cfg["nachfassen"]:
                d["hinweis"] = f"seit {(today - date.fromisoformat(seit)).days} Tagen erinnert und weiter offen – manuell nachfassen?"
            erinnert_offen.append(d)
            continue
        if tage <= cfg["tage"]:
            continue
        if entry and entry["aktion"] == "zurueckgestellt" and entry.get("wiedervorlage"):
            wv = date.fromisoformat(entry["wiedervorlage"])
            if today < wv:
                skipped.append(dict(base, grund=f"zurückgestellt bis {wv.strftime('%d.%m.%Y')}: {entry.get('grund', '')}"))
                continue
            base["nach_zurueckstellung"] = {"seit": entry["datum"], "grund": entry.get("grund", ""),
                                            "wiedervorlage": entry["wiedervorlage"]}
        if entry and entry["aktion"] in ("rueckfrage", "erledigt"):
            skipped.append(dict(base, grund=f"{entry['aktion']} seit {entry['datum']}: {entry.get('grund', '')} – Josh entscheidet"))
            continue
        to, cc = parse_recipients(r.get("kontakt", ""))
        cur = sheet.currency_of(r.get("verguetung_gesamt"))
        amount = sheet.parse_amount(r.get("brutto_sheet"))
        cust = customer_override(customers, r["kunde"])
        contact = cust.get("contact") or {}
        sprache = (r.get("sprache") or "").strip().lower()
        lang = "en" if sprache.startswith("eng") else ("de" if sprache.startswith("deu") else (cust.get("lang") or "de"))
        k = dict(base, to=to, cc=cc, ansprechpartner=first_name(r.get("ansprechpartner")), lang=lang,
                 du_sie=contact.get("du_sie", "du"), betrag=float(amount) if amount is not None else None, waehrung=cur)
        if not to:
            skipped.append(dict(base, grund=f"keine Mailadresse in Sheet-Spalte „Kontakt“ ({(r.get('kontakt') or '').strip()[:40] or 'leer'}) – manuell erinnern"))
            continue
        kandidaten.append(k)
    groups = {}
    for k in kandidaten:
        groups.setdefault(k["to"].lower(), []).append(k)
    gruppen = []
    for i, (to, items) in enumerate(sorted(groups.items()), start=1):
        nums = [x["nummer"] for x in items]
        dom = to.split("@")[1]
        nq = " OR ".join(f'"{n}"' for n in nums)
        since = min(parse_due(x["faellig"]) for x in items) - timedelta(days=45)
        gruppen.append({
            "gruppe": f"g{i}", "to": items[0]["to"], "cc": sorted({c for x in items for c in x["cc"]}),
            "rechnungen": items,
            "gmail": {
                "schon_erinnert": f'({nq}) (Zahlungserinnerung OR "payment reminder" OR Mahnung OR reminder OR überfällig OR overdue) in:sent',
                "entwuerfe": f"list_drafts mit query ({nq})",
                "rechnungsmail": f'in:sent ({nq}) (subject:Rechnung OR subject:Invoice)',
                "rueckmeldung": f'from:{dom} after:{since.strftime("%Y/%m/%d")}',
                "rueckmeldung_nummer": f'({nq}) -from:finance@lockerundlauter.com',
            }})
    return {"datum": today.isoformat(), "schwelle_tage": cfg["tage"], "gruppen": gruppen,
            "uebersprungen": skipped, "bereits_erinnert_offen": erinnert_offen}


TEXT = {
    "du": {"anrede": ("Hallo {name},", "Hallo,"), "einstieg": "ich hoffe, es geht dir gut!",
           "eine": "Für die Rechnung {nr} ({wer}){betrag}, fällig am {due}, haben wir bisher noch keine Zahlung erhalten.",
           "mehrere": "Für die folgenden Rechnungen haben wir bisher noch keine Zahlung erhalten:",
           "zeile": "– {nr} ({wer}){betrag}, fällig am {due}",
           "bitte": "Könntest du das bitte einmal auf eurer Seite prüfen? Falls die Zahlung schon unterwegs ist, "
                    "betrachte diese Mail gerne als gegenstandslos.",
           "nachfrage": "du hattest uns zuletzt eine kurze Rückmeldung zum Stand gegeben – vielen Dank dafür! "
                        "Bisher konnten wir allerdings noch keinen Zahlungseingang feststellen.",
           "gruss": "Vielen Dank und liebe Grüße\nJosh Weber", "ueber": " über {b}",
           "betreff": "Zahlungserinnerung {nrs}"},
    "sie": {"anrede": ("Guten Tag {name},", "Sehr geehrte Damen und Herren,"), "einstieg": "ich hoffe, es geht Ihnen gut!",
            "eine": "Für die Rechnung {nr} ({wer}){betrag}, fällig am {due}, haben wir bisher noch keine Zahlung erhalten.",
            "mehrere": "Für die folgenden Rechnungen haben wir bisher noch keine Zahlung erhalten:",
            "zeile": "– {nr} ({wer}){betrag}, fällig am {due}",
            "bitte": "Könnten Sie das bitte einmal auf Ihrer Seite prüfen? Falls die Zahlung bereits unterwegs ist, "
                     "betrachten Sie diese Mail gerne als gegenstandslos.",
            "nachfrage": "Sie hatten uns zuletzt eine kurze Rückmeldung zum Stand gegeben – vielen Dank dafür! "
                         "Bisher konnten wir allerdings noch keinen Zahlungseingang feststellen.",
            "gruss": "Vielen Dank und beste Grüße\nJosh Weber", "ueber": " über {b}",
            "betreff": "Zahlungserinnerung {nrs}"},
    "en": {"anrede": ("Hi {name},", "Hi,"), "einstieg": "I hope you are doing well!",
           "eine": "For invoice {nr} ({wer}){betrag}, due on {due}, we have not yet received payment.",
           "mehrere": "We have not yet received payment for the following invoices:",
           "zeile": "– {nr} ({wer}){betrag}, due on {due}",
           "bitte": "Could you please check on your side whether it is already in your payment run? If the payment has "
                    "already been made in the meantime, please disregard this message.",
           "nachfrage": "Thank you for your last update on the status! So far, however, we have not been able to "
                        "identify an incoming payment.",
           "gruss": "Many thanks and best regards,\nJosh Weber", "ueber": " over {b}",
           "betreff": "Payment reminder {nrs}"},
}


def compose(gruppe, nachfrage=False):
    items = gruppe["rechnungen"]
    lang = "en" if any(x["lang"] == "en" for x in items) else "de"
    key = "en" if lang == "en" else ("sie" if items[0]["du_sie"] == "sie" else "du")
    t = TEXT[key]
    name = next((x["ansprechpartner"] for x in items if x["ansprechpartner"]), "")
    if key == "du" and not name:  # Sammelpostfach ohne Ansprechpartner: „ihr“ statt „du“
        t = dict(t, einstieg="ich hoffe, es geht euch gut!",
                 bitte="Könntet ihr das bitte einmal auf eurer Seite prüfen? Falls die Zahlung schon unterwegs ist, "
                       "betrachtet diese Mail gerne als gegenstandslos.",
                 nachfrage="ihr hattet uns zuletzt eine kurze Rückmeldung zum Stand gegeben – vielen Dank dafür! "
                           "Bisher konnten wir allerdings noch keinen Zahlungseingang feststellen.")

    def line(tpl, x):
        b = money(x["betrag"], x["waehrung"], lang)
        return tpl.format(nr=x["nummer"], wer=f"{x['creator']} × {x['kunde']}",
                          betrag=t["ueber"].format(b=b) if b else "",
                          due=en_date(x["faellig"]) if lang == "en" else x["faellig"])

    paras = [t["anrede"][0].format(name=name) if name else t["anrede"][1], t["einstieg"]]
    if nachfrage:
        paras.append(t["nachfrage"])
    if len(items) == 1:
        paras.append(line(t["eine"], items[0]))
    else:
        paras.append(t["mehrere"] + "\n" + "\n".join(line(t["zeile"], x) for x in items))
    paras += [t["bitte"], t["gruss"]]
    subject = t["betreff"].format(nrs=" / ".join(x["nummer"] for x in items))
    text = "\n\n".join(paras)
    html = '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222">' + "".join(
        f'<p style="margin:0 0 12px 0">{htmlmod.escape(p).replace(chr(10), "<br>")}</p>' for p in paras) + "</div>"
    return {"to": [gruppe["to"]], "cc": gruppe["cc"], "subject": subject, "text": text, "html": html,
            "nummern": [x["nummer"] for x in items]}


def log_append(nummern, aktion, grund="", draft_id="", wiedervorlage="", datum=None, pruefung=None):
    known = {}
    for g in (pruefung or {}).get("gruppen", []):
        for x in g["rechnungen"]:
            known[x["nummer"]] = dict(x, kontakt=g["to"])
    for x in (pruefung or {}).get("uebersprungen", []) + (pruefung or {}).get("bereits_erinnert_offen", []):
        known.setdefault(x["nummer"], x)
    new = not LOG.exists()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for nr in nummern:
            k = known.get(nr, {})
            w.writerow({"datum": datum or date.today().isoformat(), "nummer": nr, "sheet_nummer": k.get("sheet_nummer", ""),
                        "kunde": k.get("kunde", ""), "creator": k.get("creator", ""), "kontakt": k.get("kontakt", ""),
                        "faellig": k.get("faellig", ""), "betrag": k.get("betrag", "") if k.get("betrag") is not None else "",
                        "aktion": aktion, "grund": grund, "wiedervorlage": wiedervorlage, "draft_id": draft_id})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pruefen")
    p.add_argument("--sheet-json", required=True)
    p.add_argument("--datum")
    t = sub.add_parser("text")
    t.add_argument("gruppe")
    t.add_argument("--nachfrage", action="store_true", help="Kunde hatte Verzögerung gemeldet, Wiedervorlage abgelaufen")
    lg = sub.add_parser("log")
    lg.add_argument("nummern")
    lg.add_argument("--aktion", required=True,
                    choices=["entwurf_angelegt", "manuell_erinnert", "zurueckgestellt", "rueckfrage", "erledigt",
                             "freigegeben"])
    lg.add_argument("--grund", default="")
    lg.add_argument("--draft-id", default="")
    lg.add_argument("--wiedervorlage", default="")
    lg.add_argument("--datum")
    a = ap.parse_args(argv)
    pfile = OUT / "pruefung.json"
    if a.cmd == "pruefen":
        tabs = json.loads(Path(a.sheet_json).read_text(encoding="utf-8"))
        rows = sheet.load_kampagnen_values(tabs["Finance | Kampagnen"])
        today = date.fromisoformat(a.datum) if a.datum else date.today()
        res = pruefen(rows, today)
        OUT.mkdir(parents=True, exist_ok=True)
        pfile.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif a.cmd == "text":
        res = json.loads(pfile.read_text(encoding="utf-8"))
        g = next((g for g in res["gruppen"] if g["gruppe"] == a.gruppe), None)
        if not g:
            raise SystemExit(f"Gruppe {a.gruppe} nicht in {pfile}")
        mail = compose(g, nachfrage=a.nachfrage)
        (OUT / f"{a.gruppe}.json").write_text(json.dumps(mail, ensure_ascii=False, indent=1), encoding="utf-8")
        print(json.dumps({k: v for k, v in mail.items() if k != "html"}, ensure_ascii=False, indent=1))
    elif a.cmd == "log":
        pr = json.loads(pfile.read_text(encoding="utf-8")) if pfile.exists() else None
        s = settings()
        wv = a.wiedervorlage
        if a.aktion == "zurueckgestellt" and not wv:
            base = date.fromisoformat(a.datum) if a.datum else date.today()
            wv = (base + timedelta(days=s["wiedervorlage"])).isoformat()
        nums = [n.strip() for n in a.nummern.split(",") if n.strip()]
        log_append(nums, a.aktion, a.grund, a.draft_id, wv, a.datum, pr)
        print(f"{len(nums)} Zeile(n) -> {LOG.relative_to(ROOT)} ({a.aktion}{', Wiedervorlage ' + wv if wv else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
