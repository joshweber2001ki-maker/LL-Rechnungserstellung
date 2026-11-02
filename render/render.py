#!/usr/bin/env python3
"""Rendert ein Rechnungsdokument (JSON) als PDF im L&L-Design.

Aufruf:  python3 render/render.py <dokument.json> <ausgabe.pdf> [--html]
Das JSON-Format ist in docs/dokument-schema.md beschrieben (siehe auch tests/fixtures/*.json).
"""
import base64
import json
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"
ASSETS = ROOT / "assets"
CONFIG = ROOT / "config"

TEXTS = {
    "de": {
        "title": {"invoice": "RECHNUNG", "cancellation": "STORNORECHNUNG", "reimbursement": "REISEKOSTENERSTATTUNG"},
        "number": "Rechnungsnummer", "date": "Rechnungsdatum", "period": "Leistungszeitraum",
        "cancels": "Storno zu Rechnung", "replaces": "Ersetzt Rechnung", "dated": "vom",
        "page": "Seite", "of": "von",
        "issuer": "Rechnungsaussteller", "recipient": "Rechnungsempfänger",
        "col_desc": "Beschreibung", "col_qty": "Anzahl", "col_price": "Preis", "col_sum": "Summe",
        "company_info": "Unternehmensinformationen", "bank_info": "Kontoverbindung",
        "annex": "Anlage", "col_no": "Nr", "col_receipt": "Beleg", "col_pages": "Anhang", "col_gross": "Brutto",
        "col_net": "Netto", "sum_receipts": "Summe der Belege",
    },
    "en": {
        "title": {"invoice": "INVOICE", "cancellation": "CANCELLATION INVOICE", "reimbursement": "TRAVEL EXPENSE REIMBURSEMENT"},
        "number": "Invoice number", "date": "Invoice date", "period": "Performance period",
        "cancels": "Cancellation of invoice", "replaces": "Replaces invoice", "dated": "dated",
        "page": "Page", "of": "of",
        "issuer": "Invoice issuer", "recipient": "Invoice recipient",
        "col_desc": "Description", "col_qty": "Quantity", "col_price": "Price", "col_sum": "Total",
        "company_info": "Company Information", "bank_info": "Bank account details",
        "annex": "Annex", "col_no": "No", "col_receipt": "Receipt", "col_pages": "Attachment", "col_gross": "Gross",
        "col_net": "Net", "sum_receipts": "Total of receipts",
    },
}


def money(value, currency="EUR", lang="de"):
    """1234.5 -> '1.234,50 €' (de) bzw. '€1,234.50' (en); USD analog."""
    if value is None or value == "":
        return ""
    v = float(value)
    neg = v < 0
    v = abs(v)
    sym = {"EUR": "€", "USD": "$", "CHF": "CHF"}.get(currency, currency)
    if lang == "de":
        s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        out = f"{s} {sym}"
    else:
        s = f"{v:,.2f}"
        out = f"{sym}{s}"
    return ("-" if neg else "") + out


def load_company():
    return yaml.safe_load((CONFIG / "company.yaml").read_text(encoding="utf-8"))


def build_env():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["money"] = money
    return env


def logo_data_uri():
    data = (ASSETS / "logo.png").read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode()


def prepare(doc):
    """Defaults ergänzen, damit Templates nicht auf fehlende Keys laufen."""
    doc.setdefault("doc_type", "invoice")
    doc.setdefault("category", "customer")
    doc.setdefault("lang", "de")
    doc.setdefault("currency", "EUR")
    doc.setdefault("recipient", {})
    doc["recipient"].setdefault("lines", [])
    doc["recipient"].setdefault("ids", [])
    doc["recipient"].setdefault("refs", [])
    doc.setdefault("items", [])
    doc.setdefault("totals", [])
    doc.setdefault("highlights", [])
    doc.setdefault("notes", [])
    doc.setdefault("annexes", [])
    doc.setdefault("cancels", None)
    doc.setdefault("replaces", None)
    for it in doc["items"]:
        it.setdefault("kind", "item")
        it.setdefault("lines", [])
        it.setdefault("qty", 1)
    # letzte Unterzeile eines Blocks markieren (für den Trennstrich)
    items = doc["items"]
    for i, it in enumerate(items):
        if it["kind"] == "sub":
            it["last"] = (i + 1 == len(items)) or items[i + 1]["kind"] != "sub"
    return doc


def render_html(doc, company=None):
    company = company or load_company()
    doc = prepare(doc)
    env = build_env()
    lang = doc["lang"]
    t = dict(TEXTS[lang])
    t["title"] = t["title"][doc["doc_type"]]
    band = company["design"]["color_fee_band"] if doc["category"] == "fee" else company["design"]["color_customer_band"]
    ctx = dict(d=doc, t=t, company=company, band_color=band, logo_src=logo_data_uri(),
               multipage=bool(doc["annexes"]))
    body = env.get_template("invoice.html").render(**ctx)
    header = env.get_template("header.html").render(**ctx)
    footer = env.get_template("footer.html").render(**ctx)
    return body, header, footer


def render_pdf(doc, out_path, company=None, keep_html=False):
    from playwright.sync_api import sync_playwright

    body, header, footer = render_html(doc, company)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if keep_html:
        out_path.with_suffix(".html").write_text(body, encoding="utf-8")
    expected_pages = 1 + len(doc.get("annexes", []))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(body, wait_until="load")
        # Passt der Inhalt nicht auf die erwartete Seitenzahl, wird leicht verkleinert (max. 3 Stufen),
        # damit Rechnung und Hinweistexte nicht auf eine Folgeseite rutschen.
        for scale in (1.0, 0.96, 0.92, 0.88):
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template=header,
                footer_template=footer,
                margin={"top": "47mm", "bottom": "37mm", "left": "0", "right": "0"},
                prefer_css_page_size=True,
                scale=scale,
            )
            if count_pages(pdf_bytes) <= expected_pages:
                break
        browser.close()
    out_path.write_bytes(pdf_bytes)
    return out_path


def count_pages(pdf_bytes):
    from pypdf import PdfReader
    import io
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    doc = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out = render_pdf(doc, argv[2], keep_html="--html" in argv)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
