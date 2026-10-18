"""
Metrics — top-company-style observability, zero dependencies.

Tiny in-house event counter: totals + hourly buckets (IST), persisted to
data/metrics.json with debounced saves (every 25 events or 10 s), 14-day
hourly retention. Wired into the real paths only:

  wa_sent / wa_failed   WhatsApp worker outcomes (real mode matrame —
                        dry runs fake numbers cheyyavu)
  wa_retry_enqueued     retry-queue additions
  answers / answers_correct   Telegram poll answers (bot)

Everything never raises — metrics must never break the product.
CLI:  python3 -m core.metrics
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

METRICS_FILE = config.DATA / "metrics.json"
RETENTION_DAYS = 14
_LOCK = threading.Lock()
_state = None          # {"counters": {}, "hourly": {}, "started_at": str}
_dirty = 0
_last_save = 0.0


def _hour_key(dt=None) -> str:
    return (dt or datetime.now(config.IST)).strftime("%Y-%m-%dT%H")


def _load() -> dict:
    global _state
    if _state is None:
        d = load_json(METRICS_FILE, {})
        _state = {
            "counters": dict(d.get("counters", {})) if isinstance(d, dict) else {},
            "hourly": dict(d.get("hourly", {})) if isinstance(d, dict) else {},
            "started_at": (d.get("started_at") if isinstance(d, dict) else None)
                          or datetime.now(config.IST).isoformat(timespec="seconds"),
        }
    return _state


def _save_locked():
    global _dirty, _last_save
    try:
        cutoff = (datetime.now(config.IST)
                  - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%dT%H")
        _state["hourly"] = {k: v for k, v in _state["hourly"].items()
                            if k >= cutoff}
        save_json_atomic(METRICS_FILE, _state)
    except Exception:
        pass
    _dirty = 0
    _last_save = time.time()


def incr(name: str, n: int = 1):
    """Count one event. Debounced persistence; never raises."""
    global _dirty
    try:
        with _LOCK:
            st = _load()
            st["counters"][name] = int(st["counters"].get(name, 0)) + int(n)
            hk = _hour_key()
            bucket = st["hourly"].setdefault(hk, {})
            bucket[name] = int(bucket.get(name, 0)) + int(n)
            _dirty += 1
            if _dirty >= 25 or (time.time() - _last_save) > 10:
                _save_locked()
    except Exception:
        pass


def flush():
    try:
        with _LOCK:
            _load()
            _save_locked()
    except Exception:
        pass


def _hour_profile(st: dict) -> dict:
    """Hour-of-day (IST) answer totals across retained buckets —
    Smart Slot Advisor ki (students eppudu active ga untaro)."""
    prof = {}
    for hk, bucket in (st.get("hourly") or {}).items():
        key = str(hk)
        if len(key) != 13 or key[10] != "T" or not key[11:13].isdigit():
            continue                    # malformed bucket key — skip
        h = int(key[11:13])
        if not 0 <= h <= 23:
            continue
        prof[h] = prof.get(h, 0) + int((bucket or {}).get("answers", 0))
    return prof


def hour_profile() -> dict:
    try:
        with _LOCK:
            return _hour_profile(_load())
    except Exception:
        return {}


def _sum_since(st: dict, since_key: str) -> dict:
    out = {}
    for hk, bucket in st["hourly"].items():
        if hk >= since_key:
            for k, v in bucket.items():
                out[k] = out.get(k, 0) + int(v)
    return out


def snapshot() -> dict:
    """Point-in-time view for dashboard/API. Never raises."""
    try:
        with _LOCK:
            st = _load()
            now = datetime.now(config.IST)
            today = _sum_since(st, now.strftime("%Y-%m-%dT00"))
            last24 = _sum_since(st, (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H"))
            series = {}
            for name in ("answers", "wa_sent", "wa_failed"):
                vals, labels = [], []
                for h in range(23, -1, -1):
                    dt = now - timedelta(hours=h)
                    hk = dt.strftime("%Y-%m-%dT%H")
                    vals.append(int(st["hourly"].get(hk, {}).get(name, 0)))
                    labels.append(dt.strftime("%H:00"))
                series[name] = {"labels": labels, "values": vals}
            sent = int(st["counters"].get("wa_sent", 0))
            failed = int(st["counters"].get("wa_failed", 0))
            total = sent + failed
            return {
                "ok": True,
                "started_at": st["started_at"],
                "counters": dict(st["counters"]),
                "today": today,
                "last_24h": last24,
                "hourly_series": series,
                "hour_profile": _hour_profile(st),
                "delivery": {
                    "sent": sent, "failed": failed,
                    "success_pct": (round(100.0 * sent / total, 1)
                                    if total else None),
                },
            }
    except Exception:
        return {"ok": False, "counters": {}, "today": {}, "last_24h": {},
                "hourly_series": {}, "delivery": {"sent": 0, "failed": 0,
                                                  "success_pct": None}}


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(snapshot(), indent=2, ensure_ascii=False))
