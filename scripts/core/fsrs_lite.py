# -*- coding: utf-8 -*-
"""🧠 360X: FSRS-LITE — stability-based spaced repetition.

The old ladder (0 → 3d → 7d → mastered) advanced on ANY single
correct answer: a lucky guess "mastered" the question forever,
while a genuinely hard item came back on the same fixed schedule
as an easy one. 360X replaces the ladder with a lightweight
DSR-style model (inspired by FSRS — no native deps, tiny data):

Stability S (days), FSRS-shaped retention: R = 1 / (1 + t/(9S)).
The review interval targets R_target = 0.90, which under this
curve falls at t ≈ S — so intervals grow in step with stability.
A correct recall at low R (the memory was actually exercised)
grows S strongly; a lapse collapses S to a fraction, but a
once-large stability keeps a relearning floor.

Pure module: deterministic, unit-tested, never raises on odd
inputs. members.py calls `grade(log, correct, day) -> new_log`.
"""
from __future__ import annotations

from datetime import date, timedelta

S0 = 1.0            # fresh card stability (1 day)
S_MAX = 180.0       # 6-month ceiling
R_TARGET = 0.90     # schedule when ~10% is forgotten
GOOD_BASE = 1.7     # growth for an on-time proven recall
GOOD_SPAN = 2.2     # extra growth when recall was hard-earned
LAPSE_KEEP = 0.25   # stability retained after a wrong answer
MIN_S = 0.4


def _parse_day(day) -> date:
    return date.fromisoformat(str(day)[:10])


def retrievability(log: dict, day) -> float:
    """Current recall probability of a card (1.0 = fresh)."""
    try:
        last = _parse_day(log.get("last") or log.get("due"))
        days = max(0.0, (_parse_day(day) - last).days)
        s = max(MIN_S, float(log.get("s") or S0))
        return 1.0 / (1.0 + days / (9.0 * s))
    except Exception:
        return 0.0


def next_interval_days(log: dict) -> int:
    """Days until R falls to R_TARGET under the FSRS curve."""
    s = max(MIN_S, float((log or {}).get("s") or S0))
    return max(1, int(round(9.0 * s * (1.0 / R_TARGET - 1.0))))


def new_log(qid, day, topic="") -> dict:
    """Fresh review card after a first wrong answer.

    Reviews are collected ONCE per day, so a card created by a
    mistake is already due in today's end-of-day / tomorrow's
    review run (due today — the daily batch picks it up)."""
    today = _parse_day(day)
    return {"qid": qid, "topic": topic, "s": S0,
            "last": today.isoformat(), "reps": 0,
            "due": today.isoformat()}


def grade(log: dict, correct: bool, day) -> dict:
    """Grade one recall; returns the updated card (a copy)."""
    out = dict(log or {})
    today = _parse_day(day)
    r = retrievability(out, day)
    s = max(MIN_S, float(out.get("s") or S0))
    out["reps"] = int(out.get("reps") or 0) + 1
    if correct:
        # On-time proven recall grows well; a late, hard-earned
        # recall (low R) grows most; S never shrinks on success.
        s = min(S_MAX, s * (GOOD_BASE + GOOD_SPAN * max(0.0, (1.0 - r))))
    else:
        # Lapse: collapse, but long-built stability keeps a floor.
        s = max(MIN_S, s * LAPSE_KEEP)
    out["s"] = round(s, 3)
    out["last"] = today.isoformat()
    out["due"] = (today + timedelta(
        days=next_interval_days(out))).isoformat()
    return out


def mastered(log: dict) -> bool:
    """A card retires when stability is proven at review scale."""
    return float((log or {}).get("s") or 0) >= 45.0 and \
        int((log or {}).get("reps") or 0) >= 4
