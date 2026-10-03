"""
📊 Broadcast History & Analytics
Every poll/message dispatch (Telegram instant or WhatsApp interleaved) is
recorded here so the admin can see exactly what went where and when.

Storage: data/broadcast_history.json  → {"events": [ ... newest last ... ]}
Each event: {ts, date, kind: telegram|whatsapp|scheduler, target, count,
             subjects, dry, note}
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta

from core import config

HISTORY_FILE = config.DATA / "broadcast_history.json"
MAX_EVENTS = 1200  # keep the file small & fast
_LOCK = threading.Lock()


def _load() -> dict:
    try:
        if HISTORY_FILE.exists():
            d = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("events"), list):
                return d
    except Exception:
        pass
    return {"events": []}


def _save(d: dict):
    try:
        HISTORY_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def log_event(kind: str, target: str, count: int = 1, subjects=None,
              dry: bool = False, note: str = "") -> dict:
    """Record one dispatch. Never raises — logging must not break sending."""
    try:
        now = datetime.now()
        ev = {
            "ts": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "kind": str(kind),
            "target": str(target)[:120],
            "count": int(count),
            "subjects": [str(s) for s in (subjects or [])],
            "dry": bool(dry),
            "note": str(note)[:160],
        }
        with _LOCK:
            d = _load()
            d["events"].append(ev)
            if len(d["events"]) > MAX_EVENTS:
                d["events"] = d["events"][-MAX_EVENTS:]
            _save(d)
        return ev
    except Exception:
        return {}


def get_history(limit: int = 60) -> list:
    evs = _load().get("events", [])
    return list(reversed(evs[-int(limit):]))  # newest first


def get_summary() -> dict:
    evs = _load().get("events", [])
    today = datetime.now().strftime("%Y-%m-%d")
    week_cut = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    def _tot(rows):
        return sum(max(int(e.get("count", 0)), 0) for e in rows)

    today_rows = [e for e in evs if e.get("date") == today]
    week_rows = [e for e in evs if e.get("date", "") >= week_cut]

    by_kind = {}
    for e in week_rows:
        k = e.get("kind", "?")
        by_kind[k] = by_kind.get(k, 0) + max(int(e.get("count", 0)), 0)

    top = {}
    for e in week_rows:
        t = e.get("target", "?")
        top[t] = top.get(t, 0) + max(int(e.get("count", 0)), 0)
    top_targets = sorted(top.items(), key=lambda kv: -kv[1])[:8]

    return {
        "today_polls": _tot(today_rows),
        "today_events": len(today_rows),
        "week_polls": _tot(week_rows),
        "week_events": len(week_rows),
        "by_kind": by_kind,
        "top_targets": [{"target": t, "count": c} for t, c in top_targets],
        "total_events": len(evs),
    }
