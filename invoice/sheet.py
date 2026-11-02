"""Lesen des Finanzsheets (CSV-Export von "Finance | Kampagnen" und XLSX-Export für Creator-Adressen).

Spalten werden über die Kopfzeile aufgelöst, nicht über feste Indizes. Doppelte Kopfzeilen
("MwSt 19%" kommt dreimal vor) werden nach Position eindeutig gemacht: die erste bleibt,
die weiteren erhalten den Zusatz des linken Nachbarn.
"""
import csv
import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Kanonische Feldnamen -> mögliche Kopfzeilen (normalisiert: Umbrüche/Doppelleerzeichen entfernt)
COLUMNS = {
    "nummer": ["Nummer"],
    "status": ["Status"],
    "kunde": ["Kunde"],
    "creator": ["Creator:in"],
    "art": ["Art der Kooperation"],
    "monat": ["Monat"],
    "go_live": ["Go Live"],
    "leistungen": ["Leistungen"],
    "verguetung_gesamt": ["Vergütung Gesamt"],
    "verguetung_creator": ["Vergütung Creator"],
    "zusatzkosten": ["Zusatzkosten"],
    "zusatzkosten_mwst": ["MwSt 19% #2"],          # Spalte M (nach Zusatzkosten)
    "belege": ["Belege"],
    "mwst_creator": ["MwSt 19% #3"],               # Spalte O (nach Belege) – das "Ausland"-Indiz
    "verguetung_ll": ["Vergütung L&L"],
    "brutto_sheet": ["Vergütung Gesamt (Rechnunsbetrag)", "Vergütung Gesamt (Rechnungsbetrag)"],
    "rechnung_status": ["Rechnung Status"],
    "faellig": ["Rechnung fällig am"],
    "projektnummer": ["Projektnummer"],
    "empfaenger": ["Rechnungsempfänger"],
    "ansprechpartner": ["Ansprechpartner"],
    "kontakt": ["Kontakt"],
    "sprache": ["Sprache"],
    "zahlungsfrist": ["Zahlungsfrist"],
    "rechnung_creator": ["Rechnung Creator:in"],
    "rechnung_ll": ["Rechnung L&L"],
}


def _norm(h):
    return re.sub(r"\s+", " ", str(h or "").replace("\n", " ")).strip()


def header_map(header):
    """Gibt {kanonisch: index} zurück. Doppelte Kopfzeilen werden durchnummeriert (#2, #3)."""
    seen = {}
    labeled = []
    for h in header:
        n = _norm(h)
        seen[n] = seen.get(n, 0) + 1
        labeled.append(n if seen[n] == 1 else f"{n} #{seen[n]}")
    idx = {}
    for key, candidates in COLUMNS.items():
        for c in candidates:
            if c in labeled:
                idx[key] = labeled.index(c)
                break
    missing = [k for k in COLUMNS if k not in idx]
    if missing:
        raise ValueError(f"Spalten im Finanzsheet nicht gefunden: {missing}. Kopfzeile: {labeled}")
    return idx


def parse_amount(value):
    """'1.400,00€' -> Decimal('1400.00'); '-', '', 'pending' -> None."""
    s = str(value or "").strip()
    if not s or s in {"-", "–"}:
        return None
    s = s.replace("€", "").replace("$", "").replace("EUR", "").replace("USD", "").replace(" ", "").strip()
    if not re.match(r"^-?[\d.,]+$", s):
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def currency_of(value):
    s = str(value or "")
    if "$" in s or "USD" in s:
        return "USD"
    return "EUR"


def load_kampagnen(csv_text):
    """Liest den CSV-Export (Tab "Finance | Kampagnen"). Jede Zeile bekommt zusätzlich 'jahr' und 'csv_row'."""
    return load_kampagnen_values(list(csv.reader(io.StringIO(csv_text))))


def _cell(c):
    """Zellwert → String wie im Sheet angezeigt (Brücke liefert bereits Strings; XLSX liefert Zahlen)."""
    if c is None:
        return ""
    if isinstance(c, bool):
        return str(c)
    if isinstance(c, int):
        return str(c)
    if isinstance(c, float):
        return str(int(c)) if c.is_integer() else f"{c:.2f}".replace(".", ",")
    return str(c)


def load_kampagnen_values(rows):
    """Wie load_kampagnen, aber aus einer Liste von Zeilen (z. B. Brücke: action=sheet → getDisplayValues)."""
    rows = [[_cell(c) for c in r] for r in rows]
    idx = header_map(rows[0])
    out = []
    year = None
    for i, r in enumerate(rows[1:], start=2):
        if len(r) < 3:
            continue
        # Abschnittsmarker: Jahr steht allein in Spalte A oder B, Kunde leer
        marker = [c.strip() for c in r[:3] if re.fullmatch(r"20\d\d", c.strip())]
        if marker and not r[idx["kunde"]].strip():
            year = int(marker[0])
            continue
        if not r[idx["kunde"]].strip():
            continue
        rec = {k: (r[i2].strip() if i2 < len(r) else "") for k, i2 in idx.items()}
        rec["jahr"] = year
        rec["csv_row"] = i
        out.append(rec)
    return out


def find_row(rows, nummer):
    nummer = str(nummer).strip()
    hits = [r for r in rows if r["nummer"] == nummer]
    return hits


def load_creator_addresses(xlsx_path):
    """Tab 'Finance I Creator-Adressen' -> {name: {adresse, hinweis_de, hinweis_en, handles}}."""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    ws = wb["Finance I Creator-Adressen"]
    out = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        name = str(r[0] or "").strip()
        if not name or re.fullmatch(r"20\d\d(\.0)?", name) or name.startswith("Creator"):
            continue
        out[name] = {
            "adresse": str(r[1] or "").strip(),
            "hinweis_de": re.sub(r"\s*\n\s*", " ", str(r[2] or "").strip()),
            "hinweis_en": re.sub(r"\s*\n\s*", " ", str(r[3] or "").strip()),
            "handles": [h.strip() for h in str(r[4] or "").splitlines() if h.strip()],
        }
    return out


def load_creator_addresses_csv(csv_text):
    """Alternative, falls der Adress-Tab als CSV vorliegt (gleiche Spaltenreihenfolge)."""
    return load_creator_addresses_values(list(csv.reader(io.StringIO(csv_text))))


def load_creator_addresses_values(rows):
    """Adress-Tab aus einer Liste von Zeilen (Brücke: action=sheet)."""
    rows = [[_cell(c) for c in r] for r in rows]
    out = {}
    for r in rows[1:]:
        if len(r) < 5:
            continue
        name = r[0].strip()
        if not name or re.fullmatch(r"20\d\d", name):
            continue
        out[name] = {
            "adresse": r[1].strip(),
            "hinweis_de": re.sub(r"\s*\n\s*", " ", r[2].strip()),
            "hinweis_en": re.sub(r"\s*\n\s*", " ", r[3].strip()),
            "handles": [h.strip() for h in r[4].splitlines() if h.strip()],
        }
    return out


def max_numbers(rows, year):
    """Höchste vergebene Nummer je Kreis im Finanzsheet (Spalten AH/AI) für ein Jahr."""
    mx = {}
    pat = re.compile(r"([A-Z]{1,4})-(\d{4})-(\d{3})")
    for r in rows:
        for field in ("rechnung_creator", "rechnung_ll"):
            for prefix, y, n in pat.findall(r.get(field, "")):
                if int(y) == year:
                    mx[prefix] = max(mx.get(prefix, 0), int(n))
    return mx
