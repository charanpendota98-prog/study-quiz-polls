# -*- coding: utf-8 -*-
"""🚦 310X: APPROVE-TO-LIVE PUBLISH QUEUE (Bridge Phase-3).

Owner rule: everything for the day is prepared AUTOMATICALLY as a
draft — quiz paper, today's live exams, Sunday Weekly Grand, the
WordPress export — but NOTHING goes live until the owner approves.
One tap in the dashboard (Approve → Push WP / Go Live) publishes.

State machine:  draft → approved → live
                draft → rejected  (next build replaces it)

The draft is a *manifest*, not a second copy of the content: the
quiz paper itself stays in portal (date-seeded, one paper for all),
live exams stay in portal, the WP payload is rebuilt at push time.
This module only records what was prepared, who approved it, and
what already went out — so approval is auditable and idempotent.
"""
from __future__ import annotations

import threading
from datetime import datetime

from . import config
from .store import KV, now_iso

_LOCK = threading.RLock()
STATUSES = ("draft", "approved", "live", "rejected")


def _kv() -> KV:
    return KV(config.DATA / "publish_queue.json", default={"drafts": {}})


def _today_str() -> str:
    return datetime.now(config.IST).strftime("%Y-%m-%d")


def draft_id(date_str: str) -> str:
    return "PD-" + date_str


def build_draft(date_str, paper_qs, exams, is_sunday, grand=None):
    """Pure manifest builder (unit-testable, no IO)."""
    grand = grand or {}
    return {
        "id": draft_id(date_str),
        "date": date_str,
        "status": "draft",
        "created_at": now_iso(),
        "approved_by": "", "approved_at": "",
        "live_by": "", "live_at": "",
        "rejected_reason": "",
        "quiz": {
            "count": len(paper_qs),
            "pyq": sum(1 for q in paper_qs if q.get("source") == "pyq"),
            "topics": sorted({str(q.get("topic") or "general")
                              for q in paper_qs})[:12],
            "ids": [q.get("id") for q in paper_qs][:50],
        },
        "exams_today": [{
            "id": e.get("id"), "title": e.get("title"),
            "starts_at": e.get("starts_at"), "status": e.get("status"),
            "n_q": e.get("n_q"),
        } for e in exams],
        "weekly_grand": ({
            "title": "Weekly Grand Test",
            "n_q": int(grand.get("n_q") or 25),
            "time": str(grand.get("time") or "10:00"),
        } if is_sunday else None),
        "wp": {"pushed": False, "pushed_at": "", "stored": 0, "error": ""},
        "history": [{"ts": now_iso(), "event": "draft_built", "by": "system"}],
    }


def _compose_today(date_str: str):
    """Build today's manifest from the live portal state."""
    from . import portal
    d = portal._load()
    paper = portal._daily_paper(d)
    exams = [e for e in portal.admin_list()
             if str(e.get("starts_at", ""))[:10] == date_str]
    now = datetime.now(config.IST)
    grand = {"n_q": getattr(config, "GRAND_TEST_QUESTIONS", 25),
             "time": getattr(config, "GRAND_TEST_TIME", "10:00")}
    return build_draft(date_str, paper.get("qs") or [], exams,
                       now.weekday() == 6, grand)


def get_or_build_today(rebuild: bool = False):
    """Return today's draft, building it on first ask. A rejected
    draft is replaced by a fresh build; approved/live are sticky."""
    with _LOCK:
        kv = _kv()
        drafts = kv.data.setdefault("drafts", {})
        did = draft_id(_today_str())
        cur = drafts.get(did)
        if cur and not rebuild and cur.get("status") != "rejected":
            return cur
        draft = _compose_today(_today_str())
        drafts[did] = draft
        kv.save()
        return draft


def get(did: str):
    with _LOCK:
        return _kv().data.get("drafts", {}).get(did)


def _mutate(did, fn):
    with _LOCK:
        kv = _kv()
        draft = kv.data.get("drafts", {}).get(did)
        if not draft:
            return None
        fn(draft)
        kv.save()
        return draft


def approve(did: str, by: str = "owner"):
    draft = get(did)
    if not draft:
        return False, "Draft dorakaledu."
    if draft["status"] != "draft":
        return False, f"Approve avvadu — status already '{draft['status']}'."

    def _f(dr):
        dr["status"] = "approved"
        dr["approved_by"] = by
        dr["approved_at"] = now_iso()
        dr["history"].append({"ts": now_iso(), "event": "approved", "by": by})
    _mutate(did, _f)
    return True, "Approved ✅ — ippudu Push WP / Go Live cheyyachu."


def reject(did: str, by: str = "owner", reason: str = ""):
    draft = get(did)
    if not draft:
        return False, "Draft dorakaledu."
    if draft["status"] != "draft":
        return False, f"Reject avvadu — status already '{draft['status']}'."

    def _f(dr):
        dr["status"] = "rejected"
        dr["rejected_reason"] = reason
        dr["history"].append({"ts": now_iso(), "event": "rejected",
                              "by": by, "reason": reason})
    _mutate(did, _f)
    return True, "Rejected — kotta draft rebuild avthundi."


def mark_wp_pushed(did: str, ok: bool, stored: int = 0, error: str = ""):
    def _f(dr):
        dr["wp"] = {"pushed": bool(ok), "pushed_at": now_iso(),
                    "stored": int(stored or 0), "error": error or ""}
        dr["history"].append({"ts": now_iso(),
                              "event": "wp_pushed" if ok else "wp_push_failed",
                              "by": "owner", "stored": int(stored or 0)})
    return _mutate(did, _f)


def go_live(did: str, by: str = "owner"):
    draft = get(did)
    if not draft:
        return False, "Draft dorakaledu."
    if draft["status"] == "live":
        return False, "Already LIVE undi. 🚀"
    if draft["status"] != "approved":
        return False, "Mundu Approve cheyyandi — approve lekunda live avvadu."

    def _f(dr):
        dr["status"] = "live"
        dr["live_by"] = by
        dr["live_at"] = now_iso()
        dr["history"].append({"ts": now_iso(), "event": "go_live", "by": by})
    _mutate(did, _f)
    return True, "LIVE ayindi 🚀 — quiz + exams students ki open."
