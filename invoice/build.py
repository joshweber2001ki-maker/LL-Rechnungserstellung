"""Baut aus einer Finanzsheet-Zeile die beiden Rechnungsdokumente (Kunde + Management Fee).

Ergebnis von build_invoices():
{
  "findings": [ {"level": "stop"|"warn", "text": "..."} ],   # stop ⇒ keine Rechnung erzeugen
  "tax_case": "DE"|"EU"|"DRITTLAND"|"CREATOR_AT",
  "meta": {...},
  "customer": <Dokument-JSON für render.py> | None,
  "fee": <Dokument-JSON> | None,
}
Die Regeln stehen in rules/rechnungsregeln.md – dieser Code setzt sie um; bei Zweifel gilt die Regeldatei.
"""
import re
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import yaml

from .sheet import parse_amount, currency_of

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"

EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "GR", "HU", "IE", "IT", "LV", "LT", "LU",
      "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}

COUNTRY_NAMES = {
    "deutschland": "DE", "germany": "DE", "österreich": "AT", "austria": "AT", "schweiz": "CH", "switzerland": "CH",
    "the netherlands": "NL", "netherlands": "NL", "niederlande": "NL", "denmark": "DK", "dänemark": "DK",
    "uk": "GB", "united kingdom": "GB", "great britain": "GB", "england": "GB", "usa": "US", "united states": "US",
    "france": "FR", "frankreich": "FR", "spain": "ES", "spanien": "ES", "ireland": "IE", "irland": "IE",
    "poland": "PL", "polen": "PL", "italy": "IT", "italien": "IT", "sweden": "SE", "schweden": "SE",
    "belgium": "BE", "belgien": "BE", "luxembourg": "LU", "luxemburg": "LU", "portugal": "PT",
}
COUNTRY_LABEL = {"CH": ("Schweiz", "Switzerland"), "GB": ("Vereinigtes Königreich", "the United Kingdom"),
                 "US": ("USA", "the United States"), "NL": ("Niederlande", "the Netherlands"),
                 "DK": ("Dänemark", "Denmark"), "AT": ("Österreich", "Austria"), "DE": ("Deutschland", "Germany")}

ID_PATTERN = re.compile(r"^[\s•·\-–*]*(USt\.?-?Id(?:Nr)?\.?|USt-ID|UID(?:-Nr\.?)?|VAT(?:[- ]?(?:ID|Number|No\.?))?|Tax ID)\s*[:\s]\s*(.+)$", re.I)
REF_PATTERN = re.compile(r"^[\s•·\-–*]*(Bestellnummer|Bestell-Nr\.?|PO(?: number| no\.?)?|ANID|WBS-Code|Registration number|KVK|Kostenstelle|Projektnummer|Projekt-Nr\.?|Order(?: number)?|Vorgangsnummer|Vorgangs-Nr\.?|Auftragsnummer|Auftrags-Nr\.?|Referenz(?:nummer)?|Reference(?: number| no\.?)?|Ref\.|Kundennummer|Kunden-Nr\.?|Lieferantennummer|Lieferanten-Nr\.?|(?:Supplier|Vendor|Customer) (?:number|no\.?|ID)|Company (?:number|no\.?|registration(?: number)?)|Companies House(?: number)?)\s*[:#]?\s*(.+)$", re.I)
# Regel 3 (16.11.2026): jede nachvollziehbare Nummer im Empfängerfeld kommt mit auf die Rechnung.
# Allgemein: "<Bezeichnung>: <Wert mit Ziffer>" (Bezeichnung ohne Ziffern, max. 40 Zeichen) oder "#<Kennung>".
GENERIC_REF_PATTERN = re.compile(r"^[\s•·\-–*]*([^\d:#•·]{2,40}?)\s*[:#]\s*(\S*\d.*)$")
HASH_REF_PATTERN = re.compile(r"^\s*(#\S*\d\S*)\s*$")
MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def load_yaml(name):
    return yaml.safe_load((CONFIG / name).read_text(encoding="utf-8"))


def q(x):
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def f(x):
    return float(q(x))


def norm_key(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


# ---------------------------------------------------------------- Adresse

def parse_recipient(raw, customers_cfg, customer_name):
    """Adressblock aus dem Sheet -> {lines, ids, refs, country, findings}."""
    lines = [l.strip() for l in str(raw or "").replace("\r", "").split("\n") if l.strip()]
    out_lines, ids, refs, findings = [], [], [], []
    country = None
    if not lines or any(l.lower() == "pending" for l in lines):
        return {"lines": lines, "ids": [], "refs": [], "country": None,
                "findings": [{"level": "stop", "text": "Rechnungsempfänger fehlt oder steht auf 'pending'."}]}
    for l in lines:
        m = ID_PATTERN.match(l)
        if m:
            ids.append({"label": m.group(1).strip(), "value": m.group(2).strip().rstrip(".")})
            continue
        m = REF_PATTERN.match(l) or GENERIC_REF_PATTERN.match(l)
        if m:
            refs.append({"label": m.group(1).strip(), "value": m.group(2).strip()})
            continue
        m = HASH_REF_PATTERN.match(l)
        if m:
            refs.append({"label": "", "value": m.group(1).strip()})
            continue
        out_lines.append(l)
    # Land: letzte Zeile oder "…, Land"
    if out_lines:
        last = out_lines[-1]
        key = last.lower().strip()
        if key in COUNTRY_NAMES:
            country = COUNTRY_NAMES[key]
        elif "," in last and last.split(",")[-1].strip().lower() in COUNTRY_NAMES:
            country = COUNTRY_NAMES[last.split(",")[-1].strip().lower()]
    cust = customer_override(customers_cfg, customer_name)
    if cust.get("country"):
        country = cust["country"]
    if country is None:
        # 5-stellige PLZ in einer der Zeilen ⇒ Deutschland (Landzeile ergänzen, damit alle Rechnungen gleich aussehen)
        if any(re.match(r"^\d{5}\s+\S", l) for l in out_lines):
            country = "DE"
            out_lines.append("Deutschland")
        else:
            findings.append({"level": "stop", "text": f"Land des Kunden nicht erkennbar (Adresse: {' / '.join(out_lines)}). In customers.yaml hinterlegen."})
    if cust.get("vat_id") and not ids:
        ids.append({"label": None, "value": cust["vat_id"]})
    return {"lines": out_lines, "ids": ids, "refs": refs, "country": country, "findings": findings}


def customer_override(customers_cfg, name):
    nk = norm_key(name)
    for k, v in customers_cfg.items():
        if k.startswith("_"):
            continue
        if norm_key(k) and (norm_key(k) in nk or nk in norm_key(k)):
            return dict(v)
    return {}


# ---------------------------------------------------------------- Leistungsbeschreibung

PARTIAL_DE = re.compile(r"^\s*(\d+)\.\s*(Teil|Abschlags)?rechnung\s*:?\s*", re.I)
PARTIAL_EN = re.compile(r"^\s*(\d+)(?:st|nd|rd|th)?\.?\s*partial invoice\s*:?\s*", re.I)
ORDINALS_EN = {1: "1st", 2: "2nd", 3: "3rd"}


LABEL_PREFIX = re.compile(r"^\s*([^:;\n]{3,60}?):\s+(?=\S)")


def split_deliverables(text):
    """Zerlegt 'Leistungen' in Einzel-Deliverables. Trenner: ';' und Zeilenumbruch; Kommas nur dann,
    wenn dadurch mindestens zwei Segmente mit Zählung ('1x', '2 ×') entstehen."""
    text = str(text or "").replace("*", "").replace("\r", "")
    parts = re.split(r";|\n", text)
    out = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" .,")
        if not p:
            continue
        sub = [x.strip(" .,") for x in re.split(r",\s+(?=\d+\s*[x×]|\w)", p)]
        counted = sum(1 for x in sub if re.match(r"^\d+\s*[x×]\s", x))
        if counted >= 2 and len(sub) >= 2:
            out.extend(x for x in sub if x)
        else:
            out.append(p)
    return out


def normalize_count(s):
    """'1x LinkedIn Post' / '1 x ' / '4 ×' -> '1 × LinkedIn Post'."""
    return re.sub(r"^(\d+)\s*[x×]\s*", lambda m: f"{m.group(1)} × ", s)


def short_name(deliverable):
    """Für die Überschrift: Zählung und Klammern weg."""
    s = re.sub(r"^\d+\s*[x×]\s*", "", deliverable)
    s = re.sub(r"\s*\(.*?\)", "", s)
    s = re.sub(r"\s+(inkl\.|incl\.|mit|with|als|as)\s.*$", "", s, flags=re.I)
    return s.strip(" .,:")


def build_description(row, creator_info, lang, year):
    """Liefert (title, sublines, partial_note). Handles kommen bereits gefiltert (Regel 7, select_handles)."""
    raw = str(row["leistungen"] or "")
    partial = None
    m = PARTIAL_DE.match(raw) or PARTIAL_EN.match(raw)
    if m:
        n = int(m.group(1))
        partial = f"{n}. Teilrechnung" if lang == "de" else f"{ORDINALS_EN.get(n, str(n) + 'th')} partial invoice"
        raw = raw[m.end():]
    label = None
    lm = LABEL_PREFIX.match(raw)
    if lm and not re.match(r"^\s*go\s*live", lm.group(1), re.I):
        label = lm.group(1).strip()
        raw = raw[lm.end():]
    deliverables = [normalize_count(d) for d in split_deliverables(raw)]
    kunde = row["kunde"].strip()
    if label and deliverables:
        title = label
        sub_deliv = deliverables
    elif not deliverables:
        title = ("Leistung" if lang == "de" else "Service")
    elif len(deliverables) == 1:
        title = deliverables[0]
    else:
        names = [short_name(d) for d in deliverables]
        joined = ", ".join(names[:-1]) + (" & " if lang == "de" else " & ") + names[-1]
        if len(joined) > 70:
            joined = (f"Content-Paket ({len(deliverables)} Leistungen)" if lang == "de"
                      else f"Content package ({len(deliverables)} deliverables)")
        title = joined
    sub_deliv = deliverables if (label or len(deliverables) > 1) else []
    go_live = normalize_go_live(row["go_live"], year, lang)
    sub = []
    camp = ("Kampagne" if lang == "de" else "Campaign") + f": {kunde}"
    if go_live:
        camp += " · " + ("Go Live" if lang == "de" else "Go live") + f": {go_live}"
    sub.append(camp)
    handles = creator_info.get("handles") or []
    if handles:
        sub.append(" · ".join(handles))
    if sub_deliv:
        sub.append(" · ".join(sub_deliv))
    if partial:
        sub.append(partial)
    return title, sub, partial


def normalize_go_live(value, year, lang):
    s = str(value or "").strip()
    s = re.sub(r"^\s*go\s*live\s*:?\s*", "", s, flags=re.I).strip()
    if not s or s in {"-", "–"}:
        return ""
    months = MONTHS_DE if lang == "de" else MONTHS_EN
    for i, mde in enumerate(MONTHS_DE):
        if s.lower() == mde.lower() or s.lower() == MONTHS_EN[i].lower():
            return f"{months[i]} {year}"
    return s


# ---------------------------------------------------------------- Steuerfall & Texte

def tax_case_for(customer_country, creator_country):
    if creator_country == "AT":
        return "CREATOR_AT"
    if customer_country == "DE":
        return "DE"
    if customer_country in EU:
        return "EU"
    return "DRITTLAND"


def month_label(monat, year, lang):
    m = str(monat or "").strip()
    if lang == "en" and m in MONTHS_DE:
        m = MONTHS_EN[MONTHS_DE.index(m)]
    return f"{m} {year}".strip()


def due_date(issue, zahlungsfrist, default_days):
    m = re.search(r"(\d+)", str(zahlungsfrist or ""))
    days = int(m.group(1)) if m else default_days
    return issue + timedelta(days=days)


def dmy(d):
    return d.strftime("%d.%m.%Y")


# ---------------------------------------------------------------- Leistendes Unternehmen (Regel 16)

COMPANY_FORM = re.compile(r"\b(UG|GmbH|AG|KG|OHG|GbR|Ltd\.?|SE)\b")
TAXNO_PATTERN = re.compile(r"(?:Steuer(?:nummer|-Nr\.?)|tax number)\s*:?\s+([0-9][0-9 /]*[0-9])", re.I)
VATID_PATTERN = re.compile(r"(?:USt\.?-?\s?Id(?:Nr)?\.?|UID(?:-Nr\.?)?|VAT ID)\s*:?\s+([A-Z]{2}[A-Z0-9]{6,})", re.I)
COUNTRY_DE_EN = {"deutschland": "Germany", "österreich": "Austria", "schweiz": "Switzerland"}


def money_txt(v, lang):
    s = f"{float(q(v)):,.2f}"
    if lang == "de":
        return s.replace(",", "X").replace(".", ",").replace("X", ".") + " €"
    return "€" + s


def build_supplier(cinfo, ccfg, lang):
    """Kopfblock „Leistendes Unternehmen“: Name, Anschrift, Steuernummer/USt-IdNr. der Creatorin bzw. ihrer Gesellschaft.
    Steuernummern stehen im Sheet nur im Hinweistext (Tab Creator-Adressen) und werden dort herausgelesen."""
    findings = []
    lines = [l.strip() for l in str(cinfo["adresse"]).split("\n") if l.strip()]
    country_cfg = ccfg.get("country", "DE")
    land = lines.pop() if (len(lines) > 1 and lines[-1].lower() in COUNTRY_NAMES) else {"DE": "Deutschland", "AT": "Österreich"}.get(country_cfg, country_cfg)
    if lang == "en":
        land = COUNTRY_DE_EN.get(land.lower(), land)
    if len(lines) > 1:
        lines[-1] = f"{lines[-1]}, {land}"
    name = lines[0] if lines else ""
    de, en = str(cinfo.get("hinweis_de") or ""), str(cinfo.get("hinweis_en") or "")
    tax = TAXNO_PATTERN.search(de) or TAXNO_PATTERN.search(en)
    vat_de, vat_en = VATID_PATTERN.search(de), VATID_PATTERN.search(en)
    vat = (vat_de or vat_en)
    vat = vat.group(1).upper() if vat else None
    if vat_de and vat_en and vat_de.group(1).upper() != vat_en.group(1).upper():
        findings.append({"level": "stop", "text": f"USt-IdNr. von {name} im Tab Creator-Adressen widersprüchlich: deutscher Text {vat_de.group(1)}, englischer Text {vat_en.group(1)}."})
    if vat and not re.match(r"^(DE\d{9}|ATU\d{8})$", vat) and vat[:2] in ("DE", "AT"):
        findings.append({"level": "warn", "text": f"USt-IdNr. von {name} hat ein ungültiges Format ({vat}) – bitte im Tab Creator-Adressen prüfen."})
    ids = []
    if tax:
        ids.append({"label": "Steuernummer" if lang == "de" else "Tax number", "value": tax.group(1).strip()})
    if vat:
        ids.append({"label": ("UID-Nr." if vat.startswith("ATU") else "USt-IdNr.") if lang == "de" else "VAT ID", "value": vat})
    entity = ccfg.get("entity", "person")
    is_company = entity in ("ug", "gmbh")
    if COMPANY_FORM.search(name) and not is_company:
        findings.append({"level": "warn", "text": f"Adresse im Tab Creator-Adressen lautet auf eine Gesellschaft ({name}), in creators.yaml steht aber entity: {entity} – KSK-Kostenumlage (Regel 16) wird NICHT berechnet. Bitte bestätigen."})
    if is_company and not COMPANY_FORM.search(name):
        findings.append({"level": "stop", "text": f"creators.yaml nennt entity: {entity}, die Adresse im Tab Creator-Adressen lautet aber auf '{name}' statt auf die Gesellschaft."})
    return {"name": name, "lines": lines, "ids": ids, "is_company": is_company}, findings


# ---------------------------------------------------------------- Hauptfunktion

def build_invoices(row, creator_addr, *, issue_date=None, number_customer="ENTWURF", number_fee="ENTWURF",
                   company=None, creators=None, customers=None, expenses=None, lang_override=None):
    """row: Dict aus sheet.load_kampagnen; creator_addr: Dict aus load_creator_addresses (für diese Creatorin).
    expenses: optionale Belegliste [{title, net, gross?, pages?}] – ersetzt den Sheet-Wert 'Zusatzkosten'."""
    company = company or load_yaml("company.yaml")
    creators = creators or load_yaml("creators.yaml")
    customers = customers or load_yaml("customers.yaml")
    issue_date = issue_date or date.today()
    findings = []
    year = row.get("jahr") or issue_date.year

    # --- Creatorin
    creator_name = row["creator"].strip()
    ccfg = creators.get(creator_name)
    if not ccfg:
        findings.append({"level": "stop", "text": f"Creatorin '{creator_name}' nicht in config/creators.yaml."})
        return {"findings": findings, "tax_case": None, "meta": {}, "customer": None, "fee": None}
    addr_key = ccfg.get("address_key", creator_name)
    cinfo = creator_addr.get(addr_key) if isinstance(creator_addr, dict) and addr_key in creator_addr else creator_addr
    if not cinfo or not cinfo.get("adresse"):
        findings.append({"level": "stop", "text": f"Creatorin '{creator_name}' fehlt im Tab 'Finance I Creator-Adressen'."})
        return {"findings": findings, "tax_case": None, "meta": {}, "customer": None, "fee": None}
    if "SONDERREGEL" in str(ccfg.get("notes", "")):
        findings.append({"level": "stop", "text": f"{creator_name}: Sonderregel – manuelle Freigabe nötig ({ccfg.get('notes', '')[:120]})."})

    # --- Beträge
    cur = currency_of(row["verguetung_gesamt"])
    gesamt = parse_amount(row["verguetung_gesamt"])
    creator_net = parse_amount(row["verguetung_creator"])
    fee_net = parse_amount(row["verguetung_ll"])
    zusatz = parse_amount(row["zusatzkosten"])
    mwst_flag = parse_amount(row["mwst_creator"])
    for label, v in (("Vergütung Creator", creator_net), ("Vergütung L&L", fee_net)):
        if v is None:
            findings.append({"level": "stop", "text": f"'{label}' fehlt oder ist nicht numerisch ('{row['verguetung_creator'] if label.endswith('Creator') else row['verguetung_ll']}')."})
    if cur != "EUR":
        findings.append({"level": "stop", "text": f"Währung {cur} – manuell erstellen (Regel 10, USD-Deals)."})
    if any(x["level"] == "stop" for x in findings):
        return {"findings": findings, "tax_case": None, "meta": {}, "customer": None, "fee": None}
    if gesamt is not None and abs(gesamt - (creator_net + fee_net)) > Decimal("0.02"):
        findings.append({"level": "stop", "text": f"Vergütung Gesamt ({gesamt}) ≠ Creator ({creator_net}) + L&L ({fee_net})."})
    if gesamt:
        pct = int((fee_net / gesamt * 100).quantize(Decimal("1")))
        if pct not in (ccfg.get("fee_default") or []):
            findings.append({"level": "warn", "text": f"Management Fee {pct} % weicht von üblich {ccfg.get('fee_default')} ab."})
    if str(row.get("zusatzkosten", "")).strip().lower() == "pending":
        findings.append({"level": "stop", "text": "Zusatzkosten stehen auf 'pending'."})

    # --- Empfänger & Steuerfall
    rec = parse_recipient(row["empfaenger"], customers, row["kunde"])
    findings += rec["findings"]
    cust = customer_override(customers, row["kunde"])
    customer_country = rec["country"]
    creator_country = ccfg.get("country", "DE")
    tax_case = tax_case_for(customer_country, creator_country) if customer_country else None
    if tax_case in ("EU", "DRITTLAND") and mwst_flag not in (None, Decimal("0")):
        findings.append({"level": "stop", "text": f"Steuerfall {tax_case} (Kunde {customer_country}), aber im Sheet ist MwSt {mwst_flag} € eingetragen."})
    if tax_case == "DE" and mwst_flag is not None and mwst_flag == 0:
        findings.append({"level": "stop", "text": "Kunde in Deutschland, aber im Sheet MwSt = 0,00 € – Steuerfall klären."})
    # Sonderfall (Regel 4a, 16.11.2026): MwSt- UND KSK-Spalten im Sheet leer/0 ⇒ weder MwSt noch KSK berechnen, Josh informieren.
    def _leer_oder_null(v):
        v = str(v or "").strip()
        return v in ("", "-", "–") or parse_amount(v) == 0
    ohne_mwst_ksk = (all(_leer_oder_null(row.get(k)) for k in ("mwst_creator", "mwst_gesamt"))
                     and all(_leer_oder_null(row.get(k)) for k in ("ksk_einnahme", "ksk_abgabe")))
    if ohne_mwst_ksk:
        if tax_case in ("EU", "DRITTLAND"):
            findings.append({"level": "warn", "text": "Sonderfall: MwSt und KSK im Sheet leer/0 – Rechnung ohne MwSt und ohne KSK-Umlage erstellt (Regel 4a). Bitte kurz bestätigen."})
        elif tax_case == "DE":
            findings.append({"level": "stop", "text": "Sonderfall: MwSt und KSK im Sheet leer/0, Kunde aber in Deutschland – Rechnung ohne MwSt nur nach Rücksprache (Regel 4a)."})
    # Regel 12.5 (25.11.2026): jede Auslandsrechnung (EU und Drittland) braucht die USt-ID/VAT ID/UID des Kunden.
    if tax_case in ("EU", "DRITTLAND") and not rec["ids"]:
        findings.append({"level": "stop", "text": f"Auslandskunde ({customer_country}) ohne USt-ID/VAT ID im Adressblock bzw. customers.yaml – ohne VAT ID keine Auslandsrechnung (Regel 12.5). Rechnung verschieben, bis die ID vorliegt."})
    if any(x["level"] == "stop" for x in findings):
        return {"findings": findings, "tax_case": tax_case, "meta": {}, "customer": None, "fee": None}

    # --- Sprache
    sprache = str(row.get("sprache", "")).strip().lower()
    if lang_override:
        lang = lang_override
    elif sprache.startswith("eng"):
        lang = "en"
    elif sprache.startswith("deu"):
        lang = "de"
    elif cust.get("lang"):
        lang = cust["lang"]
    else:
        lang = "de" if tax_case in ("DE", "CREATOR_AT") else "en"
    for i in rec["ids"]:
        if not i["label"]:
            i["label"] = "VAT" if lang == "en" else "USt-IdNr."

    # --- Leistendes Unternehmen im Kopf (Regel 16)
    supplier, sup_findings = build_supplier(cinfo, ccfg, lang)
    findings += sup_findings
    if any(x["level"] == "stop" for x in findings):
        return {"findings": findings, "tax_case": tax_case, "meta": {}, "customer": None, "fee": None}
    is_company = supplier["is_company"]

    # --- Auslagen
    expense_items = []
    expenses_net = Decimal("0")
    if expenses:
        for e in expenses:
            expense_items.append({"title": e["title"], "net": q(e["net"]), "gross": q(e.get("gross", e["net"])), "pages": e.get("pages")})
        expenses_net = sum(e["net"] for e in expense_items)
    elif zusatz and zusatz > 0:
        expenses_net = zusatz
        expense_items.append({"title": ("Auslagen lt. Belegliste" if lang == "de" else "Expenses as per receipts"), "net": zusatz, "gross": zusatz, "pages": None})
        findings.append({"level": "warn", "text": f"Zusatzkosten {zusatz} € aus dem Sheet übernommen (Netto-Belegliste bestätigen – Sheet-Wert ist oft brutto)."})

    # --- Positionen Kundenrechnung
    # Handles (Regel 7, 26.11.2026): Plattform eindeutig ⇒ nur deren Handles, sonst alle; customers.yaml `handles: alle`
    # schaltet die Auswahl ab, `handles_hinweis: true` meldet das verwendete Handle im Befund.
    from .mail import pick_handles
    all_handles = cinfo.get("handles") or []
    if str(cust.get("handles", "plattform")).lower() == "alle":
        inv_handles, eindeutig = all_handles, False
    else:
        inv_handles, eindeutig = pick_handles(all_handles, row["leistungen"])
    if cust.get("handles_hinweis") and all_handles:
        findings.append({"level": "info", "text": f"Handle auf der Rechnung ({row['kunde'].strip()}): "
                         + (" · ".join(inv_handles) or "–")
                         + (" (Plattform eindeutig)" if eindeutig else " (Plattform nicht eindeutig – alle Handles)")})
    title, sublines, partial = build_description(row, dict(cinfo, handles=inv_handles), lang, year)
    items, totals, notes, highlights = [], [], [], []
    ksk_rate = Decimal(str(company["ksk_rate"]))
    vat_rate = Decimal(str(company["vat_rate"]))
    fee_label = "Management Fee" if lang == "de" else "Management fee"
    # Hinweis „im Namen und für Rechnung“ (Regel 16): Anschrift und Steuernummern stehen jetzt im Kopf.
    ll_de, ll_en = company["name"], company["name_en"]
    sname = supplier["name"]
    if lang == "de":
        hinweis_txt = (f"Diese Rechnung wird im Namen und für Rechnung {'der' if is_company else 'von'} {sname} durch die {ll_de} "
                       f"als Abrechnungsstelle ausgestellt. " +
                       (f"Leistende Unternehmerin im Sinne des § 14 UStG ist die {sname}." if is_company
                        else f"Leistendes Unternehmen im Sinne des § 14 UStG ist {sname}."))
    else:
        hinweis_txt = (f"This invoice is issued in the name and for the account of {sname} by {ll_en} acting as billing agent. "
                       f"The supplier within the meaning of Sec. 14 of the German VAT Act (UStG) is {sname}.")
    hinweis = {"text": hinweis_txt, "plain": True, "role": "issuer"}
    if not supplier["ids"]:
        # Steuernummer/USt-IdNr. nicht erkennbar ⇒ alten Sheet-Hinweis zusätzlich behalten (enthält die Angaben ggf. in anderer Form)
        findings.append({"level": "warn", "text": f"Steuernummer/USt-IdNr. von {sname} im Tab Creator-Adressen nicht erkennbar – Kopfblock ohne Steuernummer, alter Hinweistext zusätzlich übernommen."})
        hinweis_alt = cinfo["hinweis_de"] if lang == "de" else cinfo["hinweis_en"]
    else:
        hinweis_alt = None
    # Gesamthonorar in einer Zeile ab Schwelle (Regel 16, Punkt 2)
    schwelle = ccfg.get("gesamthonorar_ab_netto", company.get("gesamthonorar_ab_netto"))
    one_line = schwelle is not None and (creator_net + fee_net) >= Decimal(str(schwelle))
    # KSK-Kostenumlage als eigene Position, wenn die Rechnung im Namen einer UG/GmbH gestellt wird (Regel 16, Punkt 1)
    ksk_umlage = None
    ksk_note = ("Bitte beachten Sie, die Künstlersozialabgaben sind in der jeweils festgelegten Höhe (derzeit 4,9%), vom Verwerter bzw. Veranstalter zusätzlich zum oben genannten Nettohonorar an die KSK direkt abzuführen."
                if lang == "de" else
                "Please note that the artists' social security contributions must be paid directly to the Künstlersozialkasse (KSK) by the exploiter or event organizer in the applicable amount, currently 4.9%, in addition to the net fee stated above.")

    if tax_case == "CREATOR_AT":
        items.append({"title": title, "lines": sublines + ["inkl. Management Fee" if lang == "de" else "incl. management fee"],
                      "qty": 1, "unit_price": f(creator_net + fee_net), "amount": f(creator_net + fee_net)})
        net = creator_net + fee_net + expenses_net
        totals = [{"label": "NETTOSUMME:" if lang == "de" else "net amount:", "value": f(net), "style": "sub"},
                  {"label": "UMSATZSTEUER (0 %)*:" if lang == "de" else "VAT (0 %)*:", "value": 0.0},
                  {"label": "RECHNUNGSBETRAG:" if lang == "de" else "total amount:", "value": f(net), "style": "grand"}]
        land_de, land_en = COUNTRY_LABEL.get(customer_country, (customer_country, customer_country))
        notes = [hinweis,
                 f"* Die Leistung ist in Österreich nicht steuerbar; Leistungsort ist {('die ' if customer_country == 'CH' else '')}{land_de} (§ 3a Abs. 6 UStG AT). Die Steuerschuld geht auf den Leistungsempfänger über" + (" (Bezugsteuer, Art. 45 MWSTG)." if customer_country == "CH" else " (Reverse Charge)."),
                 f"Service not subject to Austrian VAT (place of supply: {land_en}). The recipient is liable to account for VAT (reverse charge)."]
        notes = notes[1:] + [hinweis]
        gross = net
    else:
        if one_line:
            items.append({"title": title, "lines": sublines + ["Gesamthonorar inkl. Kampagnenmanagement" if lang == "de" else "Total fee incl. campaign management"],
                          "qty": 1, "unit_price": f(creator_net + fee_net), "amount": f(creator_net + fee_net)})
        else:
            items.append({"title": title, "lines": sublines, "qty": 1, "unit_price": f(creator_net), "amount": f(creator_net)})
            items.append({"title": fee_label, "qty": 1, "unit_price": f(fee_net), "amount": f(fee_net)})
        if is_company and not ohne_mwst_ksk:
            ksk_umlage = q((creator_net + fee_net) * ksk_rate)
            satz = f"{(ksk_rate * 100).normalize()}".replace(".", "," if lang == "de" else ".")
            items.append({"title": (f"Kostenumlage Künstlersozialabgabe ({satz} % auf {money_txt(creator_net + fee_net, lang)})" if lang == "de"
                                    else f"Cost allocation for artists' social security contribution (KSK, {satz} % of {money_txt(creator_net + fee_net, lang)})"),
                          "qty": 1, "unit_price": f(ksk_umlage), "amount": f(ksk_umlage)})
        if len(expense_items) >= 4:
            # Ab 4 Belegen stehen die Einzelbelege nur in der Anlage-Aufstellung; auf der Rechnung eine Sammelposition
            # (Regel 6, Josh 16.11.2026).
            n = len(expense_items)
            items.append({"title": ("Weiterberechnete Auslagen (netto)" if lang == "de" else "Reimbursed expenses (net)"),
                          "lines": [(f"{n} Belege · Aufstellung siehe Anlage, Belege im Anhang" if lang == "de"
                                     else f"{n} receipts · see schedule in the annex, receipts attached")],
                          "qty": 1, "unit_price": f(expenses_net), "amount": f(expenses_net)})
        elif expense_items:
            items.append({"kind": "group", "title": ("Weiterberechnete Auslagen (netto, Belege im Anhang)" if lang == "de" else "Reimbursed expenses (net, receipts attached)"), "lines": []})
            for e in expense_items:
                items.append({"kind": "sub", "title": e["title"], "qty": 1, "unit_price": f(e["net"]), "amount": f(e["net"])})
        subtotal = creator_net + fee_net
        ksk_hinweis = ("Hinweis zur Künstlersozialabgabe: Die Kostenumlage ist Teil des Entgelts und unterliegt der Umsatzsteuer." if lang == "de"
                       else "Note on the artists' social security contribution (KSK): the cost allocation is part of the consideration for the service and is treated for VAT purposes in the same way as the fee.")
        if tax_case == "DE":
            net = subtotal + (ksk_umlage or 0) + expenses_net
            vat = q(net * vat_rate)
            gross = net + vat
            totals = [{"label": "NETTOSUMME:", "value": f(net), "style": "sub"},
                      {"label": "zzgl. MwSt. (19%)", "value": f(vat)},
                      {"label": "BRUTTOSUMME:", "value": f(gross), "style": "grand"}]
            # UG/GmbH: Zahlungen an eine Gesellschaft sind beim Kunden nicht KSK-pflichtig ⇒ kein „vom Verwerter abzuführen“-Hinweis
            notes = ([ksk_hinweis] if ksk_umlage else []) + ([] if is_company else [ksk_note]) + [hinweis]
        else:  # EU / DRITTLAND
            ksk = Decimal("0") if ohne_mwst_ksk else q(subtotal * ksk_rate)
            if is_company:
                # KSK steht als Position in der Tabelle und ist Teil des Nettobetrags
                net = subtotal + (ksk_umlage or 0) + expenses_net
                totals = [{"label": "net amount:", "value": f(net), "style": "sub"},
                          {"label": "VAT (reverse charge):", "value": 0.0},
                          {"label": "total amount:", "value": f(net), "style": "grand"}]
            elif expense_items:
                net = subtotal + ksk + expenses_net
                totals = [{"label": "subtotal:", "value": f(subtotal)}] + ([] if ohne_mwst_ksk else [
                          {"label": "KSK (4,9 % of subtotal):", "value": f(ksk)}]) + [
                          {"label": "expenses (net):", "value": f(expenses_net)},
                          {"label": "net amount:", "value": f(net), "style": "sub"},
                          {"label": "VAT (reverse charge):", "value": 0.0},
                          {"label": "total amount:", "value": f(net), "style": "grand"}]
            else:
                net = subtotal + ksk
                totals = ([{"label": "net amount:", "value": f(subtotal), "style": "sub"},
                           {"label": "VAT (reverse charge):", "value": 0.0},
                           {"label": "total amount:", "value": f(net), "style": "grand"}] if ohne_mwst_ksk else
                          [{"label": "net amount:", "value": f(subtotal), "style": "sub"},
                           {"label": "KSK (4,9 %):", "value": f(ksk)},
                           {"label": "total amount:", "value": f(net), "style": "grand"}])
            gross = net
            notes = []
            if tax_case == "DRITTLAND":
                land_en = COUNTRY_LABEL.get(customer_country, (None, customer_country))[1]
                notes.append(f"Not subject to German VAT – the place of supply is {land_en} (Sec. 3a (2) German VAT Act). Reverse Charge Procedure applies. The customer is required to account for the VAT.")
            else:
                notes.append("Reverse Charge Procedure applies. The customer is required to account for the VAT.")
            if expense_items:
                notes[-1] = "Expenses are charged at net cost as part of the consideration for the service; receipts attached. " + notes[-1].replace("Reverse Charge Procedure applies.", "Reverse Charge Procedure applies to the full amount.")
            if ksk_umlage:
                notes.append(ksk_hinweis)
            notes.append(hinweis)
    if hinweis_alt:
        notes.append(hinweis_alt)

    due = due_date(issue_date, row.get("zahlungsfrist"), company["default_payment_days"])
    payment = (f"Bitte begleichen Sie den Rechnungsbetrag bis spätestens {dmy(due)}." if lang == "de"
               else f"We kindly ask you to settle the invoice by {dmy(due)}.")
    period = month_label(row["monat"], year, lang)
    # Zahlstellen-Klausel (Regel 16, Punkt 4) – Wortlaut in company.yaml, damit er nach anwaltlicher Prüfung an einer Stelle geändert wird
    zs = company.get("zahlstelle") or {}
    payment_note = ""
    if zs.get("aktiv"):
        payment_note = (zs["text_de"] if lang == "de" else zs["text_en"]).format(
            ll=ll_de, ll_en=ll_en, name=sname, von=(f"der {sname}" if is_company else f"von {sname}"))

    customer_doc = {
        "doc_type": "invoice", "category": "customer", "lang": lang, "currency": cur,
        "number": number_customer, "date": dmy(issue_date), "service_period": period,
        "recipient": {"lines": rec["lines"], "ids": rec["ids"], "refs": rec["refs"]},
        "supplier": {"lines": supplier["lines"], "ids": supplier["ids"]},
        "items": items, "totals": totals, "payment_text": payment, "payment_note": payment_note,
        "highlights": highlights, "notes": notes,
    }
    if len(expense_items) >= 4:
        customer_doc["annexes"] = [{
            "title": (f"Aufstellung der weiterberechneten Auslagen zu Rechnung {number_customer}" if lang == "de"
                      else f"Schedule of reimbursed expenses for invoice {number_customer}"),
            "intro": ("Weiterberechnet wird der Nettobetrag der Belege (ohne enthaltene Umsatzsteuer); Belege ohne Umsatzsteuer in voller Höhe. Belege vollständig im Anhang."
                      if lang == "de" else "Receipts are charged at their net amount (excluding VAT contained); receipts without VAT in full. All receipts attached."),
            "rows": [{"title": e["title"], "pages": e["pages"], "gross": f(e["gross"]), "net": f(e["net"])} for e in expense_items],
        }]

    # --- Fee-Rechnung (immer Deutsch)
    fee_doc = build_fee_doc(row, cinfo, ccfg, tax_case, fee_net, (q((creator_net + fee_net) * ksk_rate) if not ohne_mwst_ksk else None) if (tax_case in ("EU", "DRITTLAND") and not is_company) else None,
                            number_fee, number_customer, issue_date, year, company)

    meta = {
        "nummer": row["nummer"], "kunde": row["kunde"].strip(), "creator": creator_name, "prefix": ccfg["prefix"],
        "monat": row["monat"].strip(), "jahr": year, "tax_case": tax_case, "lang": lang, "currency": cur,
        "customer_country": customer_country, "net": f(net), "gross": f(gross), "fee_net": f(fee_net),
        "kontakt": row.get("kontakt", "").strip(), "ansprechpartner": row.get("ansprechpartner", "").strip(),
        "handles": cinfo.get("handles", []), "due": dmy(due), "issue_date": dmy(issue_date),
        "entity": ccfg.get("entity", "person"), "gesamthonorar_zeile": bool(one_line or tax_case == "CREATOR_AT"),
        "ksk_umlage": f(ksk_umlage) if ksk_umlage else None,
        "already_invoiced": {"creator": row.get("rechnung_creator", ""), "ll": row.get("rechnung_ll", "")},
    }
    sheet_gross = parse_amount(row.get("brutto_sheet"))
    meta["sheet_gross"] = f(sheet_gross) if sheet_gross is not None else None
    if sheet_gross is not None and abs(sheet_gross - q(gross)) > Decimal("0.02"):
        findings.append({"level": "warn", "text": f"Rechnungsbetrag laut Sheet {sheet_gross} €, berechnet {q(gross)} € – Abweichung {q(gross) - sheet_gross:+} € (Steuerfall {tax_case}, Auslagen {expenses_net} €)."})
    if re.search(r"[A-Z]{1,4}-\d{4}-\d{3}", row.get("rechnung_creator", "")):
        findings.append({"level": "warn", "text": f"Im Sheet steht bereits eine Kundenrechnung: {row['rechnung_creator']} – Dublette prüfen."})
    return {"findings": findings, "tax_case": tax_case, "meta": meta, "customer": customer_doc, "fee": fee_doc}


def build_fee_doc(row, cinfo, ccfg, tax_case, fee_net, ksk_passthrough, number_fee, number_customer, issue_date, year, company):
    vat_rate = Decimal(str(company["vat_rate"]))
    lines = [l.strip() for l in cinfo["adresse"].split("\n") if l.strip()]
    if lines and not any(l.lower() in COUNTRY_NAMES for l in lines):
        lines.append("Deutschland" if ccfg.get("country", "DE") == "DE" else COUNTRY_LABEL.get(ccfg.get("country"), (ccfg.get("country"),))[0])
    items = [{"title": "Management Fee", "lines": [f"für Kunde: {row['kunde'].strip()}", f"Leistungszeitraum: {month_label(row['monat'], year, 'de')}", f"Rechnung: {number_customer}"],
              "qty": 1, "unit_price": f(fee_net), "amount": f(fee_net)}]
    notes = []
    if tax_case == "DRITTLAND":
        if ksk_passthrough:
            items.append({"title": "KSK (4,9%)", "qty": 1, "unit_price": f(ksk_passthrough), "amount": f(ksk_passthrough)})
        net = fee_net + (ksk_passthrough or 0)
        totals = [{"label": "GESAMTNETTOSUMME:", "value": f(net), "style": "sub"}, {"label": "GESAMTBETRAG:", "value": f(net), "style": "grand"}]
        notes = [{"text": f"Steuerfreie Vermittlungsleistung gemäß § 4 Nr. 5 Buchst. c UStG. Der vermittelte Umsatz (Rechnung {number_customer}) wird im Drittlandsgebiet ausgeführt." + (f" Die Position KSK (4,9%) entspricht der in Rechnung {number_customer} ausgewiesenen Künstlersozialabgabe." if ksk_passthrough else ""), "plain": True}]
        payment = f"Hinweis zur Zahlung: Der Rechnungsbetrag wird mit der Kundenzahlung zu {number_customer} verrechnet. Eine gesonderte Zahlung ist nicht erforderlich."
    elif tax_case == "CREATOR_AT":
        totals = [{"label": "NETTOSUMME:", "value": f(fee_net), "style": "sub"}, {"label": "UMSATZSTEUER (0 %)*:", "value": 0.0}, {"label": "RECHNUNGSBETRAG:", "value": f(fee_net), "style": "grand"}]
        notes = [{"text": "* Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge, § 13b UStG / Art. 196 MwStSystRL). Leistungsempfängerin: " + lines[0] + ".", "plain": True}]
        payment = "Hinweis zur Zahlung: Der Rechnungsbetrag wird mit eingehenden Kundenzahlungen verrechnet. Eine gesonderte Zahlung ist nicht erforderlich."
    else:
        if tax_case == "EU" and ksk_passthrough:
            items.append({"title": "KSK (4,9%)", "qty": 1, "unit_price": f(ksk_passthrough), "amount": f(ksk_passthrough)})
            base = fee_net + ksk_passthrough
        else:
            base = fee_net
        vat = q(base * vat_rate)
        totals = [{"label": "NETTOSUMME:", "value": f(base), "style": "sub"}, {"label": "zzgl. Umsatzsteuer (19%)", "value": f(vat)}, {"label": "BRUTTOSUMME:", "value": f(base + vat), "style": "grand"}]
        payment = "Hinweis zur Zahlung: Der Rechnungsbetrag wird mit eingehenden Kundenzahlungen verrechnet. Eine gesonderte Zahlung ist nicht erforderlich."
    return {
        "doc_type": "invoice", "category": "fee", "lang": "de", "currency": "EUR",
        "number": number_fee, "date": dmy(issue_date), "service_period": month_label(row["monat"], year, "de"),
        "recipient": {"lines": lines}, "items": items, "totals": totals, "payment_text": payment, "notes": notes,
    }


def cancellation_doc(original, number, issue_date, reason, replacement=None, lang=None):
    """Erzeugt aus einem Rechnungsdokument die Stornorechnung (alle Beträge negativ)."""
    import copy
    d = copy.deepcopy(original)
    lang = lang or d["lang"]
    d["doc_type"] = "cancellation"
    d["cancels"] = {"number": original["number"], "date": original["date"]}
    d["number"] = number
    d["date"] = dmy(issue_date)
    d["replaces"] = None
    for it in d["items"]:
        if it.get("kind") == "group":
            continue
        it["unit_price"] = -abs(it["unit_price"])
        it["amount"] = -abs(it["amount"])
    for t in d["totals"]:
        t["value"] = -abs(t["value"])
    d["payment_text"] = ""
    if lang == "de":
        d["highlights"] = [f"Diese Stornorechnung hebt die Rechnung {original['number']} vom {original['date']} vollständig auf."]
        txt = f"Grund der Stornierung: {reason}"
        if replacement:
            txt += f" Die Leistung wird mit der Rechnung {replacement} neu berechnet."
    else:
        d["highlights"] = [f"This cancellation invoice fully cancels invoice {original['number']} dated {original['date']}."]
        txt = f"Reason for cancellation: {reason}"
        if replacement:
            txt += f" The service is re-invoiced with invoice {replacement}."
    d["notes"] = [{"text": txt, "plain": True}] + [n for n in original.get("notes", []) if (isinstance(n, dict) and n.get("role") == "issuer")
                                                         or (n["text"] if isinstance(n, dict) else n).startswith(("Hinweis:", "Note:"))]
    d["payment_note"] = ""
    d["annexes"] = []
    return d
