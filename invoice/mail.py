#!/usr/bin/env python3
"""Gmail-Entwurf zur Kundenrechnung (Regel 13a).

    python3 -m invoice.mail out/<N>            # baut out/<N>/mail.json + mail.html (Vorschau, kein Entwurf)
    python3 -m invoice.mail out/<N> --draft    # zusätzlich Gmail-Entwurf über die Brücke (PDF im Anhang)

- Empfänger aus Sheet-Spalte „Kontakt": erste Adresse = An, alle weiteren = CC (Reihenfolge wie im Sheet,
  „CC:"-Präfixe, Namen in Klammern, Trenner ; , & / Zeilenumbruch werden ignoriert).
- Betreff: „Rechnung <Nr>" (DE) / „Invoice <Nr>" (EN) – wie bisher von Josh verschickt.
- Text: Standardvorlage DE/EN; Du ist Standard, „Sie" wenn customers.yaml contact.du_sie = sie. Aufbau fest
  (Anrede · Einstieg · Rechnung · Bitte · Dank/Gruß), Formulierung variiert leicht (stabil je Rechnungsnummer).
- Mehrere Rechnungsmails am selben Tag an dieselbe Person ⇒ ab der zweiten Folgetext („noch eine weitere Rechnung“).
  Zählt im Lauf über out/_mails.json; frühere Mails des Tages aus Gmail übergibt der Lauf mit --bereits <n>.
- Handles: nur die der Plattform aus „Leistungen“ (z. B. LinkedIn-Kampagne ⇒ nur LinkedIn-Handle); unklar ⇒ alle.
- Idempotent: steht in mail.json schon eine draftId, wird kein zweiter Entwurf angelegt (--force erzwingt).
"""
import argparse
import hashlib
import html as htmlmod
import json
import re
import sys
from pathlib import Path

import yaml

from .build import customer_override

ROOT = Path(__file__).resolve().parent.parent
EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def parse_recipients(raw):
    """'a@x.de\\nCC: b@x.de & c@x.de' -> ('a@x.de', ['b@x.de', 'c@x.de'])."""
    seen, out = set(), []
    for m in EMAIL.findall(raw or ""):
        addr = m.strip(".'")
        if addr.lower() not in seen:
            seen.add(addr.lower())
            out.append(addr)
    if not out:
        return None, []
    return out[0], out[1:]


def first_name(ansprechpartner):
    s = (ansprechpartner or "").strip()
    if not s or s.lower() in ("pending", "-", "n/a", "tbd"):
        return ""
    s = re.split(r"[\n;,/&]| und | and ", s)[0].strip()
    return s


PLATFORMS = {
    "Instagram": r"instagram|\binsta\b|\big\b|\breels?\b|\bstor(y|ies)\b",
    "LinkedIn": r"linked\s?in|\bli\b",
    "TikTok": r"tik\s?tok",
    "YouTube": r"youtube|\byt\b",
    "Pinterest": r"pinterest",
}


def split_handle(h):
    m = re.match(r"^\s*(.+?)\s*\(([^)]+)\)\s*$", h or "")
    return (m.group(1), m.group(2).strip()) if m else ((h or "").strip(), None)


def campaign_platforms(leistungen):
    t = (leistungen or "").lower()
    return {p for p, rx in PLATFORMS.items() if re.search(rx, t)}


def pick_handles(handles, leistungen):
    """Nur die Handles der Plattform(en) aus „Leistungen“; ist das unklar (keine Plattform erkennbar oder kein
    passender Handle), alle Handles aus Tab Creator-Adressen."""
    handles = [h for h in (handles or []) if h and h.strip()]
    plats = campaign_platforms(leistungen)
    hits = [h for h in handles if (split_handle(h)[1] or "").lower() in {p.lower() for p in plats}]
    return (hits, True) if hits else (handles, False)


def handles_text(handles, lang):
    parts = []
    for h in handles or []:
        handle, plat = split_handle(h)
        if plat:
            parts.append(f"{handle} {'auf' if lang == 'de' else 'on'} {plat}")
        elif handle:
            parts.append(handle)
    return ", ".join(parts)


SIGNATURE_TEXT = """Josh Weber
Finance Manager

Mail: finance@lockerundlauter.com
Social: Website https://lockerundlauter.com/ | Instagram https://www.instagram.com/lockerundlauter/ | LinkedIn https://www.linkedin.com/company/locker-und-lauter/

Locker & Lauter UG (haftungsbeschränkt)
Eschenholt 22a | 22525 Hamburg | +4917663033047
Geschäftsführung: Laura Schimming
Amtsgericht Hamburg HRB 187235 | VAT-ID: DE369478827 | Sitz: Hamburg"""

SIGNATURE_HTML = """<p style="margin:16px 0 0 0"><b>Josh Weber</b><br>Finance Manager</p>
<p style="margin:8px 0 0 0"><b>Mail:</b> <a href="mailto:finance@lockerundlauter.com">finance@lockerundlauter.com</a><br>
<b>Social:</b> <a href="https://lockerundlauter.com/">Website</a> | <a href="https://www.instagram.com/lockerundlauter/">Instagram</a> | <a href="https://www.linkedin.com/company/locker-und-lauter/">LinkedIn</a></p>
<p style="margin:8px 0 0 0;font-size:12px;color:#555"><b>Locker &amp; Lauter UG (haftungsbeschränkt)</b><br>
Eschenholt 22a | 22525 Hamburg | +4917663033047<br>Geschäftsführung: Laura Schimming<br>
Amtsgericht Hamburg HRB 187235 | VAT-ID: DE369478827 | Sitz: Hamburg</p>"""


# Bausteine je Absatz: Aufbau bleibt immer gleich (Anrede · Einstieg · Rechnung · Bitte · Dank/Gruß), die
# Formulierung variiert leicht. Auswahl stabil je Rechnungsnummer (gleicher Aufruf ⇒ gleicher Text).
# „folge“ = es ging heute schon eine andere Rechnungsmail an dieselbe Person.
TEXTS = {
    "du": {
        "anrede": ("Hallo {name},", "Hallo,"),
        "einstieg": ["ich hoffe, es geht dir gut!\nHier ist Josh aus dem Finance-Team von Locker & Lauter. 🪩",
                     "ich hoffe, dir geht es gut!\nHier ist Josh aus dem Finance-Team von Locker & Lauter. 🪩",
                     "ich hoffe, bei dir ist alles gut!\nHier ist Josh aus dem Finance-Team von Locker & Lauter. 🪩"],
        "einstieg_folge": ["ich melde mich heute direkt noch einmal – es gibt eine weitere Rechnung.",
                           "heute kommt von mir gleich noch eine weitere Rechnung.",
                           "da bin ich heute gleich noch einmal, mit einer weiteren Rechnung."],
        "rechnung": ["Anbei sende ich dir die Rechnung ({nr}) zur gemeinsamen Aktivierung mit {mit}.",
                     "Anbei findest du die Rechnung ({nr}) zur gemeinsamen Aktivierung mit {mit}.",
                     "Im Anhang schicke ich dir die Rechnung ({nr}) zur gemeinsamen Aktivierung mit {mit}."],
        "bitte": ["Ich bitte um fristgerechte Begleichung und freue mich über eine kurze Bestätigung des Rechnungseingangs.",
                  "Ich bitte um fristgerechte Begleichung und freue mich über eine kurze Rückmeldung, sobald die "
                  "Rechnung bei dir angekommen ist."],
        "dank": ["Vielen Dank für die angenehme Zusammenarbeit und\nliebe Grüße",
                 "Danke für die schöne Zusammenarbeit und\nliebe Grüße",
                 "Vielen Dank für die tolle Zusammenarbeit und\nliebe Grüße"],
        "dank_folge": ["Danke dir und\nliebe Grüße", "Nochmals danke und\nliebe Grüße"],
    },
    "sie": {
        "anrede": ("Guten Tag {name},", "Sehr geehrte Damen und Herren,"),
        "einstieg": ["ich hoffe, es geht Ihnen gut! Hier ist Josh aus dem Finance-Team von Locker & Lauter.",
                     "ich hoffe, bei Ihnen ist alles gut! Hier ist Josh aus dem Finance-Team von Locker & Lauter."],
        "einstieg_folge": ["ich melde mich heute noch einmal mit einer weiteren Rechnung.",
                           "heute erhalten Sie von mir noch eine weitere Rechnung."],
        "rechnung": ["Anbei sende ich Ihnen die Rechnung ({nr}) zur gemeinsamen Aktivierung mit {mit}.",
                     "Im Anhang finden Sie die Rechnung ({nr}) zur gemeinsamen Aktivierung mit {mit}."],
        "bitte": ["Ich bitte um Begleichung bis zum {due} und freue mich über eine kurze Bestätigung des Rechnungseingangs.",
                  "Ich bitte um Begleichung bis zum {due} und freue mich über eine kurze Rückmeldung, sobald die "
                  "Rechnung bei Ihnen eingegangen ist."],
        "dank": ["Vielen Dank für die angenehme Zusammenarbeit und\nbeste Grüße",
                 "Herzlichen Dank für die gute Zusammenarbeit und\nbeste Grüße"],
        "dank_folge": ["Vielen Dank und\nbeste Grüße"],
    },
    "en": {
        "anrede": ("Hi {name},", "Hi,"),
        "einstieg": ["I hope you're doing well! This is Josh from the Finance Team at Locker & Lauter. 🪩",
                     "I hope all is well on your end! This is Josh from the Finance Team at Locker & Lauter. 🪩"],
        "einstieg_folge": ["It's me again – there's one more invoice coming your way today.",
                           "Following up today with one more invoice."],
        "rechnung": ["Please find attached the invoice ({nr}) for our collaboration with {mit}.",
                     "Attached you'll find the invoice ({nr}) for our collaboration with {mit}."],
        "bitte": ["We kindly ask for payment by {due_en}, and would appreciate a short confirmation once you've received it.",
                  "We kindly ask for payment by {due_en}, and would appreciate a quick note once it has arrived."],
        "dank": ["Thank you for the great collaboration!\n\nBest regards,",
                 "Thanks a lot for the great collaboration!\n\nBest regards,"],
        "dank_folge": ["Thanks again!\n\nBest regards,"],
    },
}


def _pick(options, seed, slot):
    if isinstance(options, str):
        return options
    h = int(hashlib.sha256(f"{seed}|{slot}".encode()).hexdigest(), 16)
    return options[h % len(options)]


def compose(meta, number, du_sie="du", folge=0, leistungen=""):
    """-> (subject, [Absätze], handles_passend). folge = Anzahl anderer Rechnungsmails heute an dieselbe Person."""
    lang = meta.get("lang", "de")
    key = "en" if lang == "en" else ("sie" if du_sie == "sie" else "du")
    t = TEXTS[key]
    name = first_name(meta.get("ansprechpartner"))
    handles, passend = pick_handles(meta.get("handles"), leistungen)
    h = handles_text(handles, "en" if key == "en" else "de")
    mit = f"{meta.get('creator', '')} ({h})" if h else meta.get("creator", "")
    v = {"nr": number, "mit": mit, "due": meta.get("due", ""), "due_en": en_date(meta.get("due"))}
    sfx = "_folge" if folge else ""
    anrede = t["anrede"][0].format(name=name) if name else t["anrede"][1]
    paras = [anrede,
             _pick(t["einstieg" + sfx], number, "einstieg"),
             _pick(t["rechnung"], number, "rechnung").format(**v),
             _pick(t["bitte"], number, "bitte").format(**v),
             _pick(t["dank" + sfx], number, "dank")]
    if key == "en":  # Englische Vorlage: Rechnung + Bitte in einem Absatz (wie bisher)
        paras[2:4] = [paras[2] + " " + paras[3]]
    subject = ("Invoice " if key == "en" else "Rechnung ") + number
    return subject, paras, passend


MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
             "October", "November", "December"]


def en_date(dmy):
    m = re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", dmy or "")
    return f"{MONTHS_EN[int(m.group(2)) - 1]} {int(m.group(1))}, {m.group(3)}" if m else (dmy or "")


DISCO = "\U0001FAA9"  # 🪩 – GmailApp zerlegt Zeichen außerhalb der BMP, daher im HTML als Entity, im Text weglassen


def to_html(paras):
    body = "".join(f'<p style="margin:0 0 12px 0">{htmlmod.escape(p).replace(chr(10), "<br>").replace(DISCO, "&#x1FAA9;")}</p>'
                   for p in paras)
    return f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222">{body}{SIGNATURE_HTML}</div>'


def same_day_position(out_dir, to, number, day):
    """Wie viele andere Rechnungsmails gehen in diesem Lauf (out/_mails.json) heute schon an dieselbe Adresse?
    Die Reihenfolge der ersten Vorbereitung zählt; ein erneuter Aufruf für dieselbe Nummer behält seinen Platz."""
    log_path = Path(out_dir).parent / "_mails.json"
    try:
        log = json.loads(log_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        log = {}
    if not to:
        return 0
    entries = log.setdefault(day, {}).setdefault(to.lower(), [])
    if number not in entries:
        entries.append(number)
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    return entries.index(number)


def prepare(out_dir, bereits=0):
    """bereits = Rechnungsmails mit ANDERER Nummer, die heute laut Gmail schon an dieselbe An-Adresse gingen
    (gesendet oder als Entwurf) – ermittelt der Lauf per Connector, siehe Regel 13a."""
    out_dir = Path(out_dir)
    befund = json.loads((out_dir / "befund.json").read_text(encoding="utf-8"))
    meta = befund["meta"]
    number = (meta.get("nummern") or {}).get("kunde")
    if not number:
        raise SystemExit("befund.json: keine Kundenrechnungsnummer (meta.nummern.kunde) – kein Mail-Entwurf.")
    pdf = out_dir / f"Rechnung-{number}.pdf"
    customers = yaml.safe_load((ROOT / "config" / "customers.yaml").read_text(encoding="utf-8")) or {}
    cust = customer_override(customers, meta.get("kunde", ""))
    contact = cust.get("contact") or {}
    if contact.get("lang") and not meta.get("lang"):
        meta["lang"] = contact["lang"]
    to, cc = parse_recipients(meta.get("kontakt", ""))
    day = meta.get("issue_date", "")
    folge = same_day_position(out_dir, to, number, day) + max(0, int(bereits or 0))
    leistungen = (befund.get("row") or {}).get("leistungen", "")
    subject, paras, passend = compose(meta, number, contact.get("du_sie", "du"), folge=folge, leistungen=leistungen)
    findings = []
    if not to:
        findings.append("Kein Empfänger in Sheet-Spalte „Kontakt“ – Entwurf ohne Empfänger angelegt.")
    if not first_name(meta.get("ansprechpartner")):
        findings.append("Kein Ansprechpartner im Sheet – Anrede ohne Namen.")
    if not pdf.exists():
        findings.append(f"{pdf.name} fehlt – erst rendern.")
    if folge:
        findings.append(f"Heute schon {folge} andere Rechnungsmail(s) an {to} – Folgetext verwendet.")
    if not passend and len(meta.get("handles") or []) > 1:
        findings.append("Plattform der Kampagne nicht eindeutig – alle Creator-Handles in der Mail.")
    mail = {"to": [to] if to else [], "cc": cc, "subject": subject, "folge": folge,
            "text": "\n\n".join(paras).replace(" " + DISCO, "") + "\n\n" + SIGNATURE_TEXT, "attach": [str(pdf)],
            "findings": findings}
    old = out_dir / "mail.json"
    if old.exists():
        prev = json.loads(old.read_text(encoding="utf-8"))
        for k in ("draftId", "messageId"):
            if prev.get(k):
                mail[k] = prev[k]
    (out_dir / "mail.html").write_text(to_html(paras), encoding="utf-8")
    old.write_text(json.dumps(mail, ensure_ascii=False, indent=1), encoding="utf-8")
    return mail


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--bereits", type=int, default=0,
                    help="Anzahl Rechnungsmails (andere Nummer) heute laut Gmail schon an dieselbe An-Adresse")
    a = ap.parse_args(argv)
    mail = prepare(a.out_dir, bereits=a.bereits)
    if a.draft:
        if mail.get("draftId") and not a.force:
            mail["findings"].append(f"Entwurf existiert bereits ({mail['draftId']}) – kein zweiter angelegt.")
        elif not Path(mail["attach"][0]).exists():
            raise SystemExit(f"{mail['attach'][0]} fehlt – kein Entwurf.")
        else:
            from . import bridge
            html = (Path(a.out_dir) / "mail.html").read_text(encoding="utf-8")
            res = bridge.draft(mail["to"], mail["subject"], html=html, text=mail["text"], cc=mail["cc"],
                               attachments=mail["attach"])
            mail["draftId"], mail["messageId"] = res.get("draftId"), res.get("messageId")
            (Path(a.out_dir) / "mail.json").write_text(json.dumps(mail, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: mail.get(k) for k in ("to", "cc", "subject", "folge", "draftId", "findings")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
