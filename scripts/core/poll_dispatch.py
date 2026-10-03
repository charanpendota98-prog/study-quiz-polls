"""
📢 Shared Telegram poll dispatcher — used by BOTH the dashboard button
("Post Poll") and the 24x7 Auto-Pilot scheduler, so behaviour is identical.

Perfection upgrades vs the old inline dashboard code:
  1. ✅ Sends to the ACTUAL registered channel/group chat (old code always
     posted to the base-exam channel, ignoring custom chat_ids).
  2. ✅ No-repeat rotation: fresh (never-posted) questions are preferred and,
     on a real live send, picked questions are permanently marked as posted.
  3. ✅ Every dispatch is recorded in broadcast history for analytics.
Telegram sends stay INSTANT — official Bot API, no anti-ban gaps needed.
"""
from __future__ import annotations

from core import config, channel_router, broadcast_log
from core.question_bank import Bank
from core.engine import Engine
from core.telegram import Telegram


def prefer_fresh(bank: Bank, questions: list, n: int) -> list:
    """Order candidate questions so NEVER-POSTED ones come first.
    Falls back to already-posted questions only when fresh ones run out,
    so a thin bank never blocks a broadcast."""
    fresh, used = [], []
    for q in questions:
        ch = q.get("channel", "CURRENT")
        if q.get("id") in set(bank.used.get(ch, [])):
            used.append(q)
        else:
            fresh.append(q)
    return (fresh + used)[: max(n, 0)]


def post_channel_polls(channel_key: str, count: int = 1, subjects=None,
                       source: str = "dashboard") -> dict:
    """Pick subject-correct questions and post them instantly to the given
    Telegram channel OR group. Returns {ok, sent, dry, target, message}."""
    from core import whatsapp_pipeline  # late import (avoid cycles)

    bank = Bank()
    tg = Telegram()
    dry = not bool(tg.token)
    eng = Engine(dry=dry)

    all_ch = channel_router.get_all_channels()
    ch_cfg = all_ch.get(channel_key, {})
    base = ch_cfg.get("base_exam", channel_key)

    # question pool follows the BASE exam syllabus + chosen subjects
    picked = whatsapp_pipeline.pick_subject_questions(bank, base, count * 2, subjects) or []
    if len(picked) < count:
        picked.extend(bank.pick("CURRENT", count - len(picked)) or [])
    picked = prefer_fresh(bank, picked, count)

    # 🎯 send to the channel's OWN chat when it is registered in config
    # (custom channels & groups get merged into config.CHANNELS at register
    #  time) — otherwise fall back to the base-exam channel.
    send_key = channel_key if channel_key in config.CHANNELS else base

    sent, sent_qs = 0, []
    for q in picked[:count]:
        if eng.send_quiz(send_key, q):
            sent += 1
            sent_qs.append(q)

    # permanent no-repeat: only burn questions on REAL live sends
    if sent_qs and not dry:
        by_ch = {}
        for q in sent_qs:
            by_ch.setdefault(q.get("channel", "CURRENT"), []).append(q)
        for chn, qs in by_ch.items():
            try:
                bank.mark_posted(chn, qs)
            except Exception:
                pass

    label = ch_cfg.get("name", channel_key)
    is_group = ch_cfg.get("chat_type") == "group"
    broadcast_log.log_event(
        "telegram", ("💬 " if is_group else "📢 ") + label, sent,
        subjects=subjects, dry=dry,
        note=("auto-pilot" if source == "scheduler" else source),
    )

    mode = "Live" if not dry else "Dry-Run (BOT_TOKEN not set)"
    return {
        "ok": True,
        "sent": sent,
        "dry": dry,
        "target": label,
        "message": f"✅ {sent} poll(s) → {label} [{mode}] — instant, no gaps (official Bot API)",
    }
