#!/usr/bin/env python3
"""
STUDENTUP — FORM WEBHOOK SERVER (zero dependency, stdlib)
Run on any public host (the same Oracle box is fine). Google Apps Script POSTs
each new form submission here; the signup is normalised, imported into the bot's
points system, and the admin is notified on Telegram. No manual CSV needed.

Run:
  python3 webhook_server.py                 # bind 0.0.0.0:8080
  WEBHOOK_PORT=9000 WEBHOOK_SECRET=abc python3 webhook_server.py

Point your form's Apps Script at:
  POST  http(s)://<your-host>:<port>/form?secret=<WEBHOOK_SECRET>
  body: JSON of the form fields (any keys — matched flexibly).
See forms/google_apps_script.gs (POST_WEBHOOK_URL).
"""
import sys
import json
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).parent))
from core import config
from core.members import Members
from core.formingest import normalize_signup

SECRET = config.env("WEBHOOK_SECRET", "")
PORT = int(config.env("WEBHOOK_PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print(f"[webhook] {self.address_string()} {fmt % args}")

    def do_GET(self):
        p = urlparse(self.path)
        if p.path == "/health":
            self._send(200, {"ok": True, "service": "studentup-webhook",
                             "members": Members().count_form()})
        else:
            self._send(200, {"ok": True, "hint": "POST /form?secret=... with JSON"})

    def do_POST(self):
        p = urlparse(self.path)
        if p.path != "/form":
            return self._send(404, {"ok": False, "error": "unknown path"})
        qs = parse_qs(p.query)
        provided = (qs.get("secret", [""])[0] if qs else "")
        if SECRET and provided != SECRET:
            return self._send(403, {"ok": False, "error": "bad secret"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            fields = json.loads(raw)
            # Accept either a flat object or a {"namedValues":{...}} Apps Script form
            if isinstance(fields, dict) and "namedValues" in fields:
                fields = {k: (v[0] if isinstance(v, list) else v)
                          for k, v in fields["namedValues"].items()}
            info = normalize_signup(fields)
            mb = Members()
            status, key = mb.import_form_signup(info)
            # notify admin on Telegram
            try:
                from core.telegram import Telegram
                Telegram().admin_notify(
                    f"🆕 {info.get('name','?')} registered ({status})\n"
                    f"🎯 {info.get('exam','?')} | 📍 {info.get('district') or info.get('state','?')}\n"
                    f"📱 {info.get('phone','?')} | ✈️ {info.get('username') or info.get('tg_id') or '?'}\n"
                    f"Total members: {mb.count_form()}")
            except Exception as e:
                print("[webhook] admin notify note:", e)
            return self._send(200, {"ok": True, "status": status,
                                    "key": key, "members": mb.count_form()})
        except Exception as e:
            return self._send(500, {"ok": False, "error": str(e)[:200]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"STUDENTUP webhook server on http://{args.host}:{args.port}/form"
          f"{' (secret-protected)' if SECRET else '  — ⚠ set WEBHOOK_SECRET!'}")
    print("Health: GET /health")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
