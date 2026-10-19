# -*- coding: utf-8 -*-
"""🌐 310X: WordPress quiz push (Bridge Phase-3 automation).

Pushes today's daily-quiz payload to the private WP REST route
(`POST /wp-json/studentup/v1/quiz`, see
integrations/wordpress/studentup-quiz-sync.php).

🔐 Credentials come ONLY from the server env/.env:
  WP_SITE_URL       (default https://studentup.in)
  WP_USERNAME       (WP admin/editor user)
  WP_APP_PASSWORD   (a revocable WordPress *Application Password*)

They are never accepted from chat, API bodies or the dashboard —
the dashboard only ever sees "creds set / not set" booleans.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

from . import config


def wp_base() -> str:
    return config.env("WP_SITE_URL", "https://studentup.in").strip().rstrip("/")


def creds():
    return (config.env("WP_USERNAME", "").strip(),
            config.env("WP_APP_PASSWORD", "").strip())


def creds_ready() -> bool:
    user, pw = creds()
    return bool(user and pw)


def push_url() -> str:
    return wp_base() + "/wp-json/studentup/v1/quiz"


def push_quiz(payload, dry_run: bool = False, timeout: int = 12,
              urlopen=None):
    """POST {date, questions[]} to the WP quiz-sync route.

    Returns a result dict; never raises. `urlopen` is injectable
    for tests (defaults to urllib.request.urlopen).
    """
    payload = payload or {}
    questions = payload.get("questions") or []
    if not questions:
        return {"ok": False, "error": "questions payload empty undi"}
    if dry_run:
        return {"ok": True, "dry_run": True, "count": len(questions),
                "url": push_url()}
    user, pw = creds()
    if not (user and pw):
        return {"ok": False, "creds_missing": True,
                "error": "WP_USERNAME / WP_APP_PASSWORD .env lo set "
                         "cheyyandi (Application Password use cheyyandi)"}
    body = json.dumps({"date": payload.get("date", ""),
                       "questions": questions},
                      ensure_ascii=False).encode("utf-8")
    auth = base64.b64encode(
        f"{user}:{pw.replace(' ', '')}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        push_url(), data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Basic " + auth,
                 "User-Agent": "StudentUp-Bridge/1.0"})
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        return {"ok": bool(data.get("ok")),
                "stored": int(data.get("stored") or 0), "url": push_url()}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"WP HTTP {e.code}", "url": push_url()}
    except Exception as e:  # network down, DNS, timeout — never crash
        return {"ok": False, "error": f"WP push fail ayindi: {e}",
                "url": push_url()}
