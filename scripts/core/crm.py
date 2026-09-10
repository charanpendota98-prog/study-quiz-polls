#!/usr/bin/env python3
"""
STUDENTUP CRM — the member base as a reusable asset.

Every registered player (name, district, state, mobile, exam, Telegram id,
points, activity) is:
  1. mirrored to a Google Sheet in real time (Apps Script web-app endpoint,
     no Google API keys/libraries needed) — this is your permanent database
     for future channels, courses, alerts, prizes, anything;
  2. exportable as CSV / Excel-friendly file from the bot (/export, admin);
  3. reachable by segment (/broadcast district=Warangal exam=TSPSC …) so you
     can DM a targeted group about a new channel, job alert, event, etc.

Google Sheet setup (one time, 2 minutes):
  • Create a Sheet → Extensions → Apps Script → paste docs/sheet_webapp.gs
  • Deploy → Web app → Execute as: Me, Access: Anyone → copy URL
  • .env:  SHEET_WEBAPP_URL=https://script.google.com/macros/s/…/exec
           SHEET_SECRET=any-long-random-string  (same value inside the script)
Pure standard library.
"""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from datetime import datetime

from . import config

SHEET_URL = getattr(config, "SHEET_WEBAPP_URL", "") or ""
SHEET_SECRET = getattr(config, "SHEET_SECRET", "") or ""

COLUMNS = ["tg_id", "name", "username", "mobile", "state", "district", "exam", "lang",
           "registered_at", "source", "points", "correct", "total", "accuracy",
           "streak", "best_streak", "level", "last_active", "follow"]


def member_row(uid, m: dict) -> dict:
    from .members import level_for
    total = m.get("total", 0) or 0
    acc = round(100 * (m.get("correct", 0) or 0) / total, 1) if total else 0.0
    return {
        "tg_id": str(uid), "name": m.get("name", ""), "username": m.get("username", ""),
        "mobile": m.get("mobile", ""), "state": m.get("state", ""),
        "district": m.get("district", ""), "exam": m.get("exam", ""), "lang": m.get("lang", ""),
        "registered_at": m.get("registered_at", ""), "source": m.get("source", ""),
        "points": m.get("points", 0), "correct": m.get("correct", 0), "total": total,
        "accuracy": acc, "streak": m.get("streak", 0), "best_streak": m.get("best_streak", 0),
        "level": level_for(m.get("points", 0)).get("title_en", ""),
        "last_active": m.get("last_active", ""),
        "follow": ",".join(m.get("follow") or []),
    }


# --------------------------------------------------------------------- Sheet
def sheet_enabled() -> bool:
    return bool(SHEET_URL and SHEET_URL.startswith("http"))


def push_member(uid, m: dict, post=None) -> bool:
    """Upsert one member row into the Google Sheet (row keyed by tg_id)."""
    if not sheet_enabled():
        return False
    return _post({"action": "upsert", "row": member_row(uid, m)}, post)


def push_all(members: dict, post=None) -> int:
    if not sheet_enabled():
        return 0
    rows = [member_row(uid, m) for uid, m in members.items() if m.get("registered")]
    ok = 0
    for i in range(0, len(rows), 200):
        if _post({"action": "bulk", "rows": rows[i:i + 200]}, post):
            ok += len(rows[i:i + 200])
    return ok


def push_round_top(round_id, channel, rows, post=None) -> bool:
    """Append round toppers to a 'rounds' tab — history of who wins where."""
    if not sheet_enabled() or not rows:
        return False
    return _post({"action": "round", "rows": [
        {"round_id": round_id, "channel": channel, "rank": i + 1, "tg_id": r["uid"],
         "name": r["name"], "district": r["district"], "correct": r["correct"],
         "total": r["total"], "points": r["points"]} for i, r in enumerate(rows)]}, post)


def ping(post=None) -> dict:
    """Health check → {'ok': bool, 'members': n} (n from the Sheet)."""
    if not sheet_enabled():
        return {"ok": False, "error": "SHEET_WEBAPP_URL not set"}
    try:
        data = json.dumps({"action": "ping", "secret": SHEET_SECRET}).encode("utf-8")
        req = urllib.request.Request(SHEET_URL, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode("utf-8", "ignore") or "{}")
        if not body.get("ok"):
            return {"ok": False, "error": body.get("error", "unknown")}
        # GET returns member count
        with urllib.request.urlopen(SHEET_URL, timeout=15) as r:
            info = json.loads(r.read().decode("utf-8", "ignore") or "{}")
        return {"ok": True, "members": info.get("members", 0)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _post(payload: dict, post=None) -> bool:
    payload["secret"] = SHEET_SECRET
    payload["ts"] = datetime.now(config.IST).isoformat(timespec="seconds")
    try:
        if post:
            return bool(post(SHEET_URL, payload))
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(SHEET_URL, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read(400).decode("utf-8", "ignore")
            return '"ok"' in body or body.strip().startswith("{")
    except Exception as e:
        print(f"   [crm] sheet push failed: {e}")
        return False


# ----------------------------------------------------------------------- CSV
def export_csv(members: dict, only_registered=True) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    for uid, m in sorted(members.items(), key=lambda kv: -(kv[1].get("points", 0) or 0)):
        if only_registered and not m.get("registered"):
            continue
        w.writerow(member_row(uid, m))
    # UTF-8 BOM so Excel opens Telugu names correctly
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


# ------------------------------------------------------------------ segments
_FILTER_RE = re.compile(r"(\w+)\s*=\s*([^\s]+)")


def parse_segment(text: str) -> dict:
    """'district=Warangal exam=TSPSC state=TS active=7' -> dict."""
    return {k.lower(): v for k, v in _FILTER_RE.findall(text or "")}


def select(members: dict, seg: dict) -> list:
    from . import districts as D
    from datetime import timedelta
    out = []
    want_d = seg.get("district")
    if want_d:
        _, canon = D.match_any_district(want_d)
        want_d = canon or want_d
    want_state = seg.get("state", "").upper()
    want_state = {"TS": "Telangana", "AP": "Andhra Pradesh"}.get(want_state, seg.get("state", ""))
    active_days = int(seg["active"]) if seg.get("active", "").isdigit() else None
    cutoff = ((datetime.now(config.IST) - timedelta(days=active_days)).strftime("%Y-%m-%d")
              if active_days else None)
    for uid, m in members.items():
        if not m.get("registered") or m.get("dm_blocked"):
            continue
        if want_d and (m.get("district") or "").lower() != want_d.lower():
            continue
        if want_state and (m.get("state") or "").lower() != want_state.lower():
            continue
        if seg.get("exam") and seg["exam"].lower() not in (m.get("exam") or "").lower():
            continue
        if seg.get("minpoints", "").isdigit() and (m.get("points", 0) or 0) < int(seg["minpoints"]):
            continue
        if cutoff and (m.get("last_active") or "") < cutoff:
            continue
        if seg.get("mobile") == "yes" and not m.get("mobile"):
            continue
        out.append(uid)
    return out


def segment_summary(members: dict) -> str:
    regs = {u: m for u, m in members.items() if m.get("registered")}
    by = lambda k: sorted(
        {}.items() if not regs else
        _count(regs, k).items(), key=lambda kv: -kv[1])
    lines = [f"🗂 *StudentUp CRM* — {len(regs)} registered",
             f"📱 with mobile: {sum(1 for m in regs.values() if m.get('mobile'))}",
             "", "*State*"]
    lines += [f"  {k or '—'}: {v}" for k, v in by("state")[:4]]
    lines += ["", "*Top districts*"]
    lines += [f"  {k or '—'}: {v}" for k, v in by("district")[:10]]
    lines += ["", "*Exam target*"]
    lines += [f"  {k or '—'}: {v}" for k, v in by("exam")[:9]]
    lines += ["", "Sheet sync: " + ("✅ on" if sheet_enabled() else "⚠️ off (set SHEET_WEBAPP_URL)"),
              "Export: /export · Segment DM: /broadcast district=Warangal exam=TSPSC <message>"]
    return "\n".join(lines)


def _count(d: dict, key: str) -> dict:
    c = {}
    for m in d.values():
        k = m.get(key) or ""
        c[k] = c.get(k, 0) + 1
    return c
