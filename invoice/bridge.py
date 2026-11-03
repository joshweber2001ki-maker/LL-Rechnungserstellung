"""Client für die Apps-Script-Brücke (bridge/Code.gs). Konfiguration in config/bridge.yaml:

    url: "https://script.google.com/macros/s/.../exec"
    secret: "..."
    register_sheet_id: "..."      # optional: Google-Sheet-Spiegel des Registers (Tab "Register")

Aufruf aus der Shell:
    python3 -m invoice.bridge ping
    python3 -m invoice.bridge sheet <spreadsheetId> "Finance | Kampagnen" "Finance I Creator-Adressen" > data/sheet.json
    python3 -m invoice.bridge upload <datei.pdf> Rechnungskopien/2026/November [--replace]
    python3 -m invoice.bridge upload <datei.pdf> --folder-id <DriveOrdnerId>
    python3 -m invoice.bridge draft --to kunde@x.de --subject "…" --html mail.html --attach a.pdf [--attach b.pdf]
    python3 -m invoice.bridge find 06_Rechnungen
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config" / "bridge.yaml"


def config():
    if not CFG.exists():
        raise SystemExit("config/bridge.yaml fehlt – Brücke nicht konfiguriert (siehe bridge/Code.gs).")
    # Die Datei kommt aus einem Google Doc: typografische Anführungszeichen und geschützte Leerzeichen entfernen
    text = CFG.read_text(encoding="utf-8")
    for ch in "\u201c\u201d\u201e\u201f\u2018\u2019\u00ab\u00bb\"'":
        text = text.replace(ch, "")
    text = text.replace("\u00a0", " ").replace("\\_", "_").replace("\\-", "-").replace("\\.", ".")
    cfg = yaml.safe_load(text) or {}
    for key in ("url", "secret"):
        if not str(cfg.get(key, "")).strip():
            raise SystemExit(f"config/bridge.yaml: '{key}' fehlt.")
        cfg[key] = str(cfg[key]).strip()
    return cfg


def call(action, **payload):
    cfg = config()
    body = json.dumps(dict(payload, action=action, secret=cfg["secret"])).encode("utf-8")
    req = urllib.request.Request(cfg["url"], data=body, headers={"Content-Type": "application/json"}, method="POST")
    # Apps Script antwortet mit 302 auf script.googleusercontent.com – urllib folgt dem Redirect (GET) nicht
    # mit POST-Body, daher die Umleitung selbst behandeln.
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        resp = opener.open(req, timeout=120)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307):
            resp = urllib.request.urlopen(e.headers["Location"], timeout=120)
        else:
            raise
    data = json.loads(resp.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Brücke {action}: {data.get('error')}")
    return data


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def upload(path, drive_path=None, folder_id=None, replace=False, mime="application/pdf"):
    p = Path(path)
    b64 = base64.b64encode(p.read_bytes()).decode()
    kw = {"filename": p.name, "base64": b64, "mimeType": mime, "replace": replace}
    if folder_id:
        kw["folderId"] = folder_id
    else:
        kw["path"] = [s for s in str(drive_path).split("/") if s]
    return call("upload", **kw)


def draft(to, subject, html=None, text=None, cc=None, attachments=()):
    atts = []
    for a in attachments:
        p = Path(a)
        atts.append({"filename": p.name, "base64": base64.b64encode(p.read_bytes()).decode(), "mimeType": "application/pdf"})
    return call("draft", to=list(to or []), cc=list(cc or []), subject=subject, html=html, text=text or "", attachments=atts)


def sheet(spreadsheet_id, *tabs):
    return call("sheet", spreadsheetId=spreadsheet_id, tabs=list(tabs))["tabs"]


def find(name, mime="application/vnd.google-apps.folder"):
    return call("find", name=name, mimeType=mime)["files"]


def append_register(rows):
    cfg = config()
    if not cfg.get("register_sheet_id"):
        return None
    return call("append", spreadsheetId=cfg["register_sheet_id"], tab="Register", rows=rows)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "ping":
        print(json.dumps(call("ping")))
    elif cmd == "sheet":
        print(json.dumps(sheet(args[0], *args[1:]), ensure_ascii=False))
    elif cmd == "upload":
        replace = "--replace" in args
        folder_id = None
        if "--folder-id" in args:
            folder_id = args[args.index("--folder-id") + 1]
            args = [a for i, a in enumerate(args) if a != "--folder-id" and (i == 0 or args[i - 1] != "--folder-id")]
        args = [a for a in args if a != "--replace"]
        print(json.dumps(upload(args[0], drive_path=args[1] if len(args) > 1 else None, folder_id=folder_id, replace=replace)))
    elif cmd == "draft":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("--to", action="append", default=[])
        ap.add_argument("--cc", action="append", default=[])
        ap.add_argument("--subject", required=True)
        ap.add_argument("--html")
        ap.add_argument("--text")
        ap.add_argument("--attach", action="append", default=[])
        a = ap.parse_args(args)
        html = Path(a.html).read_text(encoding="utf-8") if a.html else None
        print(json.dumps(draft(a.to, a.subject, html=html, text=a.text, cc=a.cc, attachments=a.attach)))
    elif cmd == "find":
        print(json.dumps(find(args[0]), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
