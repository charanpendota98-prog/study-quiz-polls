#!/usr/bin/env python3
"""
STUDENTUP — 🧠 ITEM INTELLIGENCE

Real student answers nunchi question quality ni auto-ga nerchukuntundi:
  • prathi answer (bot scoring chokepoint) ikkada record avuthundi;
  • andaru fail ayye question (suspect wrong key / broken) → QUARANTINE
    (verifier.postable dhanini post cheyanivvadu — bank ninchi bayatiki);
  • andaru easy ga kotte question (too easy) → retire list (slot waste);
  • correct-rate tho difficulty auto-calibration (blueprint heuristics
    kanna real data strong).

Thresholds (attempts tagginchalenivi):
  suspect key : attempts >= 15 AND correct-rate <= 18%
  too easy    : attempts >= 25 AND correct-rate >= 95%

CLI: python3 -m core.item_intel
"""
from __future__ import annotations

import threading
from datetime import datetime

from . import config
from .store import load_json, save_json_atomic

STATS_FILE = config.DATA / "item_stats.json"
_LOCK = threading.Lock()
_cache = {"mtime": None, "data": {}}

MIN_ATTEMPTS_SUSPECT = 15
SUSPECT_MAX_RATE = 0.18
MIN_ATTEMPTS_EASY = 25
EASY_MIN_RATE = 0.95
MIN_ATTEMPTS_CALIBRATE = 10


def _load() -> dict:
    try:
        mt = STATS_FILE.stat().st_mtime
    except OSError:
        mt = None
    if mt is None:            # file ledu → stale cache vaddu (test isolation)
        _cache["data"] = {}
        _cache["mtime"] = None
        return _cache["data"]
    if _cache["mtime"] != mt:
        d = load_json(STATS_FILE, {})
        _cache["data"] = d if isinstance(d, dict) else {}
        _cache["mtime"] = mt
    return _cache["data"]


def _save(d: dict):
    save_json_atomic(STATS_FILE, d)
    try:
        _cache["mtime"] = STATS_FILE.stat().st_mtime
    except OSError:
        _cache["mtime"] = None
    _cache["data"] = d


def record(qid: str, correct: bool, topic: str = "", channel: str = ""):
    """One real student answer. Never raises (scoring must not break)."""
    if not qid:
        return
    try:
        with _LOCK:
            d = _load()
            rec = d.setdefault(str(qid), {"a": 0, "c": 0, "topic": topic or "",
                                          "channel": channel or ""})
            rec["a"] = int(rec.get("a", 0)) + 1
            if correct:
                rec["c"] = int(rec.get("c", 0)) + 1
            if topic:
                rec["topic"] = topic
            if channel:
                rec["channel"] = channel
            rec["last"] = datetime.now().strftime("%Y-%m-%d")
            _save(d)
    except Exception:
        pass


def stats_of(qid: str) -> dict:
    rec = _load().get(str(qid), {})
    a = int(rec.get("a", 0)) if isinstance(rec, dict) else 0
    return {"attempts": a,
            "correct": int(rec.get("c", 0)) if isinstance(rec, dict) else 0,
            "rate": (int(rec.get("c", 0)) / a) if a else None}


def classify(qid: str) -> str:
    """ok | suspect_key | too_easy | learning (inka data chaaladu)"""
    s = stats_of(qid)
    a, rate = s["attempts"], s["rate"]
    if rate is None:
        return "learning"
    if a >= MIN_ATTEMPTS_SUSPECT and rate <= SUSPECT_MAX_RATE:
        return "suspect_key"
    if a >= MIN_ATTEMPTS_EASY and rate >= EASY_MIN_RATE:
        return "too_easy"
    return "ok" if a >= MIN_ATTEMPTS_CALIBRATE else "learning"


def channel_topic_rates(channel: str, min_attempts: int = 10) -> dict:
    """Channel topic performance map: {topic_lower: {attempts, correct,
    rate}} — Smart Rounds weak-topic focus ki (data unna topics matrame)."""
    agg = {}
    for rec in _load().values():
        if str(rec.get("channel", "")) != str(channel):
            continue
        t = str(rec.get("topic", "") or "").strip().lower()
        if not t:
            continue
        a = agg.setdefault(t, {"attempts": 0, "correct": 0})
        a["attempts"] += int(rec.get("a", 0))
        a["correct"] += int(rec.get("c", 0))
    return {t: {**v, "rate": (v["correct"] / v["attempts"] if v["attempts"] else 0.0)}
            for t, v in agg.items() if v["attempts"] >= min_attempts}


def is_quarantined(qid: str) -> bool:
    return classify(qid) == "suspect_key"


def calibrated_difficulty(qid: str, fallback: str) -> str:
    """Real correct-rate → easy/medium/hard (data unte matrame)."""
    s = stats_of(qid)
    if s["attempts"] < MIN_ATTEMPTS_CALIBRATE or s["rate"] is None:
        return fallback
    r = s["rate"]
    return "easy" if r >= 0.8 else ("medium" if r >= 0.45 else "hard")


def record_many(qid: str, n_correct: int, n_wrong: int, topic: str = "",
                channel: str = ""):
    """Aggregate answers (channel reaction polls are anonymous — reveal
    time lo bulk counts vastayi). Item-intel learning stays honest."""
    if not qid or (n_correct + n_wrong) <= 0:
        return
    try:
        with _LOCK:
            d = _load()
            rec = d.setdefault(str(qid), {"a": 0, "c": 0, "topic": topic or "",
                                          "channel": channel or ""})
            rec["a"] = int(rec.get("a", 0)) + int(n_correct) + int(n_wrong)
            rec["c"] = int(rec.get("c", 0)) + int(n_correct)
            if topic:
                rec["topic"] = topic
            if channel:
                rec["channel"] = channel
            rec["last"] = datetime.now().strftime("%Y-%m-%d")
            _save(d)
    except Exception:
        pass


def retired_ids() -> set:
    """Too-easy (≥95% correct, saripadina data tho) question ids —
    fresh rounds nunchi retire cheyyadaniki (Bank.unused vaduthundi)."""
    try:
        return {qid for qid in _load() if classify(qid) == "too_easy"}
    except Exception:
        return set()


def is_retired(qid: str) -> bool:
    try:
        return classify(str(qid)) == "too_easy"
    except Exception:
        return False


def reset(qid: str) -> bool:
    """Key fix chesina tarvata stats clear — question malli nerchukuntundi
    (quarantine nunchi bayatiki vasthundi). Returns removed or not."""
    try:
        with _LOCK:
            d = _load()
            if str(qid) in d:
                d.pop(str(qid))
                _save(d)
                return True
    except Exception:
        pass
    return False


def report(limit: int = 20) -> dict:
    d = _load()
    suspects, easy, tracked = [], [], 0
    for qid, rec in d.items():
        if not isinstance(rec, dict):
            continue
        tracked += 1
        cls = classify(qid)
        row = {"qid": qid, **stats_of(qid), "topic": rec.get("topic", ""),
               "channel": rec.get("channel", "")}
        if cls == "suspect_key":
            suspects.append(row)
        elif cls == "too_easy":
            easy.append(row)
    suspects.sort(key=lambda r: (r["rate"], -r["attempts"]))
    easy.sort(key=lambda r: (-r["rate"], -r["attempts"]))
    return {"tracked_questions": tracked,
            "suspect_key": suspects[:limit], "suspect_count": len(suspects),
            "too_easy": easy[:limit], "too_easy_count": len(easy)}


def format_text(rep: dict) -> str:
    L = [f"🧠 ITEM INTELLIGENCE — {rep['tracked_questions']} questions tracked",
         f"   🚫 suspect wrong-key (quarantined): {rep['suspect_count']}",
         f"   😴 too easy (retire candidates)  : {rep['too_easy_count']}"]
    for r in rep["suspect_key"][:10]:
        L.append(f"   🚫 {r['qid']} [{r['channel']}/{r['topic']}] "
                 f"{r['correct']}/{r['attempts']} correct ({(r['rate'] or 0) * 100:.0f}%)")
    for r in rep["too_easy"][:5]:
        L.append(f"   😴 {r['qid']} [{r['channel']}/{r['topic']}] "
                 f"{(r['rate'] or 0) * 100:.0f}% correct ×{r['attempts']}")
    return "\n".join(L)


if __name__ == "__main__":
    print(format_text(report()))
