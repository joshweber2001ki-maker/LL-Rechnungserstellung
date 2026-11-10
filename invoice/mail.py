#!/usr/bin/env python3
"""Gmail-Entwurf zur Kundenrechnung (Regel 13a).

    python3 -m invoice.mail out/<N>            # baut out/<N>/mail.json + mail.html (Vorschau, kein Entwurf)
    python3 -m invoice.mail out/<N> --draft    # zusätzlich Gmail-Entwurf über die Brücke (PDF im Anhang)

- Empfänger aus Sheet-Spalte „Kontakt": erste Adresse = An, alle weiteren = CC (Reihenfolge wie im Sheet,
  „CC:"-Präfixe, Namen in Klammern, Trenner ; , & / Zeilenumbruch werden ignoriert).
- Betreff: „Rechnung <Nr>" (DE) / „Invoice <Nr>" (EN) – wie bisher von Josh verschickt.
- Text: Standardvorlage DE/EN; Du ist Standard, „Sie" wenn customers.yaml contact.du_sie = sie.
- Idempotent: steht in mail.json schon eine draftId, wird kein zweiter Entwurf angelegt (--force erzwingt).
"""
import argparse
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


def handles_text(handles, lang):
    parts = []
    for h in handles or []:
        m = re.match(r"^\s*(.+?)\s*\(([^)]+)\)\s*$", h)
        if m:
            parts.append(f"{m.group(1)} {'auf' if lang == 'de' else 'on'} {m.group(2)}")
        elif h.strip():
            parts.append(h.strip())
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


def compose(meta, number, du_sie="du"):
    """-> (subject, [Absätze])"""
    lang = meta.get("lang", "de")
    name = first_name(meta.get("ansprechpartner"))
    creator = meta.get("creator", "")
    h = handles_text(meta.get("handles"), lang)
    mit = f"{creator} ({h})" if h else creator
    if lang == "en":
        subject = f"Invoice {number}"
        paras = [f"Hi {name}," if name else "Hi,",
                 "I hope you're doing well! This is Josh from the Finance Team at Locker & Lauter. 🪩",
                 f"Please find attached the invoice ({number}) for our collaboration with {mit}. "
                 f"We kindly ask for payment by {en_date(meta.get('due'))}, and would appreciate a short "
                 "confirmation once you've received it.",
                 "Thank you for the great collaboration!",
                 "Best regards,"]
    elif du_sie == "sie":
        subject = f"Rechnung {number}"
        paras = [f"Guten Tag {name}," if name else "Sehr geehrte Damen und Herren,",
                 "ich hoffe, es geht Ihnen gut! Hier ist Josh aus dem Finance-Team von Locker & Lauter.",
                 f"Anbei sende ich Ihnen die Rechnung ({number}) zur gemeinsamen Aktivierung mit {mit}.",
                 f"Ich bitte um Begleichung bis zum {meta.get('due')} und freue mich über eine kurze Bestätigung "
                 "des Rechnungseingangs.",
                 "Vielen Dank für die angenehme Zusammenarbeit und\nbeste Grüße"]
    else:
        subject = f"Rechnung {number}"
        paras = [f"Hallo {name}," if name else "Hallo,",
                 "ich hoffe, es geht dir gut!\nHier ist Josh aus dem Finance-Team von Locker & Lauter. 🪩",
                 f"Anbei sende ich dir die Rechnung ({number}) zur gemeinsamen Aktivierung mit {mit}.",
                 "Ich bitte um fristgerechte Begleichung und freue mich über eine kurze Bestätigung des "
                 "Rechnungseingangs.",
                 "Vielen Dank für die angenehme Zusammenarbeit und\nliebe Grüße"]
    return subject, paras


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


def prepare(out_dir):
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
    subject, paras = compose(meta, number, contact.get("du_sie", "du"))
    findings = []
    if not to:
        findings.append("Kein Empfänger in Sheet-Spalte „Kontakt“ – Entwurf ohne Empfänger angelegt.")
    if not first_name(meta.get("ansprechpartner")):
        findings.append("Kein Ansprechpartner im Sheet – Anrede ohne Namen.")
    if not pdf.exists():
        findings.append(f"{pdf.name} fehlt – erst rendern.")
    mail = {"to": [to] if to else [], "cc": cc, "subject": subject,
            "text": "\n\n".join(paras).replace(" " + DISCO, "") + "\n\n" + SIGNATURE_TEXT, "attach": [str(pdf)], "findings": findings}
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
    a = ap.parse_args(argv)
    mail = prepare(a.out_dir)
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
    print(json.dumps({k: mail.get(k) for k in ("to", "cc", "subject", "draftId", "findings")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
