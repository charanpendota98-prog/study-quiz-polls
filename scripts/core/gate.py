"""
Register Gate 2.0 — every touch-point tells un-registered players, clearly and
professionally, that points / Top-10 need a one-time registration, and chases the
ones who started but never finished.

Channel side (anonymous polls can't be gated, so we make registering irresistible):
  * T-5 / T-1 alerts, round opener and Top-10 post carry a live footer
      👥 1,240 registered · 🔒 37 players have locked points
    plus an inline button  📝 Register & earn points → t.me/<bot>?start=quiz
  * Opener spells the rule: "Register అయిన వాళ్ళకే points + Top-10 lo పేరు".
Bot side:
  * /start quiz|register deep link → straight into the registration form.
  * Locked-points chase (20:05 daily): DM to everyone with locked_points>0 or a
    half-done form — day 1, 2, 3, 7, 14 after first contact, then stop. One line,
    one button, shows exactly how many points are waiting.
  * After every round: players who answered but are not registered get ONE DM
    (per day) with their score and the unlock CTA.
All functions are dry-safe and never raise into the engine.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

STATE = config.DATA / "gate_state.json"
CHASE_DAYS = (1, 2, 3, 7, 14)


def _now():
    return datetime.now(config.IST)


def _day(dt=None):
    return (dt or _now()).strftime("%Y-%m-%d")


def bot_link(arg: str = "quiz") -> str:
    u = (getattr(config, "BOT_USERNAME", "") or "").lstrip("@")
    if not u:
        h = (getattr(config, "BRAND_HANDLE", "") or "").replace("https://", "").replace("t.me/", "")
        u = h.lstrip("@")
    return f"https://t.me/{u}?start={arg}" if u else ""


def cta_buttons(label: str = "📝 Register & earn points · రిజిస్టర్", arg: str = "quiz"):
    link = bot_link(arg)
    return [[(label, f"url:{link}")]] if link else None


# ------------------------------------------------------------------ live numbers
def counts(members) -> dict:
    ms = members.members if hasattr(members, "members") else members
    reg = sum(1 for m in ms.values() if m.get("registered"))
    locked_n = sum(1 for m in ms.values() if not m.get("registered") and m.get("locked_points", 0) > 0)
    locked_pts = sum(m.get("locked_points", 0) for m in ms.values() if not m.get("registered"))
    pend = len(getattr(members, "pending", {}) or {})
    today = _day()
    new_today = sum(1 for m in ms.values() if m.get("registered") and (m.get("registered_at") or "")[:10] == today)
    return {"registered": reg, "locked_players": locked_n, "locked_points": locked_pts, "pending": pend, "new_today": new_today}


def footer(members) -> str:
    c = counts(members)
    parts = [f"👥 {c['registered']:,} registered"]
    if c["new_today"]:
        parts.append(f"🆕 +{c['new_today']} today")
    if c["locked_players"]:
        parts.append(f"🔒 {c['locked_players']} players · {c['locked_points']:,} pts locked (register to unlock)")
    return " · ".join(parts)


def rule_line() -> str:
    return "📝 Points + Top-10 lo పేరు + జిల్లా — register అయిన వాళ్ళకే. ఒక్కసారి, 30 సెకన్లు, మళ్ళీ అడగం."


def alert_block(members) -> str:
    """Appended to T-5 / T-1 alerts and the round opener."""
    return f"{rule_line()}\n{footer(members)}"


def top10_tail(members, n_unreg: int) -> str:
    c = counts(members)
    lines = []
    if n_unreg:
        lines.append(f"🔒 {n_unreg} players ఆడారు కానీ register కాలేదు — వాళ్ళ పేరు, points ఇక్కడ రావు.")
    lines.append(f"📝 Register → points unlock + next round Top-10 lo మీ పేరు · 👥 {c['registered']:,} already in")
    return "\n".join(lines)


# ------------------------------------------------------------------ chase jobs
def _state():
    return load_json(STATE, {"first_seen": {}, "chased": {}, "round_dm": {}})


def chase_locked(members, tg, dry=False, today=None) -> int:
    """20:05 — DM un-registered users with locked points / half form on chase days."""
    st = _state()
    today = today or _now().date()
    tday = today.strftime("%Y-%m-%d")
    sent = 0
    pend = getattr(members, "pending", {}) or {}
    for uid, m in list(members.members.items()):
        if m.get("registered") or m.get("dm_blocked"):
            continue
        lp = m.get("locked_points", 0) or 0
        if lp <= 0 and uid not in pend:
            continue
        fs = st["first_seen"].setdefault(uid, tday)
        try:
            age = (today - datetime.strptime(fs, "%Y-%m-%d").date()).days
        except Exception:
            age = 0
        if age not in CHASE_DAYS or st["chased"].get(uid) == tday:
            continue
        st["chased"][uid] = tday
        step = "పేరు పంపండి" if uid in pend else "/start నొక్కండి"
        txt = (f"🔒 {lp} points మీ కోసం wait చేస్తున్నాయి\n" if lp else "📝 మీ registration సగంలో ఆగింది\n") + \
              f"Register అయితే: points unlock ⭐ · ప్రతి round Top-10 lo మీ పేరు + జిల్లా 🏆 · offers /wallet 🎁\n" \
              f"30 సెకన్లు — {step} 👇" + ("" if age < 14 else "\n(ఇది చివరి reminder — తర్వాత మేము disturb చేయం 🙏)")
        if dry:
            sent += 1; continue
        try:
            tg.send_message(uid, txt, buttons=[[("📝 Register now", "gate:reg")]])
            sent += 1; tg.polite_gap(True)
        except Exception as e:
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                m["dm_blocked"] = True
    if not dry:
        st["chased"] = dict(list(st["chased"].items())[-20000:])
        save_json_atomic(STATE, st)
        try:
            members.kv.save()
        except Exception:
            pass
    return sent


def after_round_dms(members, tg, round_id, ch, n_q, dry=False) -> int:
    """Players who answered this round but are not registered → one DM per day."""
    raw = members.data.get("rounds", {}).get(round_id, {}).get("by_channel", {}).get(ch, {})
    if not raw:
        return 0
    st = _state()
    tday = _day()
    sent = 0
    for uid, e in raw.items():
        m = members.members.get(str(uid)) or {}
        if m.get("registered") or m.get("dm_blocked") or st["round_dm"].get(str(uid)) == tday:
            continue
        st["round_dm"][str(uid)] = tday
        lp = m.get("locked_points", 0) or 0
        txt = (f"🏁 Round అయిపోయింది — మీ score {e.get('correct', 0)}/{n_q} ✅\n"
               f"కానీ మీరు register కాలేదు → Top-10 lo పేరు రాలేదు, {lp} points 🔒 lock లో ఉన్నాయి.\n"
               f"ఒక్కసారి register (30 సెకన్లు) → అన్నీ unlock, next round నుంచి పేరు + జిల్లా channel lo 🏆")
        if dry:
            sent += 1; continue
        try:
            tg.send_message(str(uid), txt, buttons=[[("📝 Register now", "gate:reg")]])
            sent += 1; tg.polite_gap(True)
        except Exception as ex:
            if "blocked" in str(ex).lower():
                m["dm_blocked"] = True
    if not dry:
        st["round_dm"] = dict(list(st["round_dm"].items())[-20000:])
        save_json_atomic(STATE, st)
    return sent


def owner_line(members) -> str:
    c = counts(members)
    return (f"📝 Gate: {c['registered']} registered · {c['pending']} half-done forms · "
            f"{c['locked_players']} with locked pts ({c['locked_points']} pts)")
