"""
Addiction & acquisition hooks — the behavioural mechanics top channels run.

1. STREAK SHIELD + MILESTONES
   Missing one day normally kills a streak. A member EARNS a shield every 7-day
   streak (max 2 banked); a missed day auto-consumes one instead of resetting.
   Milestones 7 / 30 / 100 days give points + a channel shout-out with name and
   district. Loss-aversion is the strongest retention lever we have.

2. DAILY MYSTERY MULTIPLIER
   One question per round is secretly the "mystery question" with ×2 / ×3 / ×5
   points (weights 60/30/10). Revealed only in the round Top-10 post, so
   people answer EVERY question (skipping might skip the ×5).

3. FRIEND SQUAD
   /squad → create a 3–5 member team (invite code). Squad score = sum of the
   week's correct answers; a weekly Squad Top-5 goes to the hub with all names +
   districts. Joining requires registration → every squad invite is a referral.

4. SHARE POSTER
   After each round every registered player gets a personal "నా score" PNG
   (rank, district, score, streak, channel link) — one tap to WhatsApp status.
   Every player becomes an advertisement.

5. LIVE / FOMO LINES
   Openers show "🔴 N aspirants played the last round · M from <district> " and
   Top-10 posts show how many people from the reader's district appeared —
   social proof at the exact moment of the decision to play.

All state is in members' own records + data/squads.json. Every function is
guarded; nothing raises into the engine.
"""
from __future__ import annotations

import hashlib
import random
import re
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

SQUADS_PATH = config.DATA / "squads.json"
MAX_SQUAD_MEMBERS = int(getattr(config, "MAX_SQUAD_MEMBERS", 10) or 10)
SHIELD_EVERY = 7
SHIELD_MAX = 2
MILESTONES = {7: 50, 30: 200, 100: 1000}
MYSTERY_WEIGHTS = ((2, 60), (3, 30), (5, 10))


# ============================================================ 1. STREAK SHIELD
def on_daily_activity(m: dict, today: str, yesterday: str) -> dict:
    """Call once per member per active day (after streak already updated by
    award_answer). Banks shields on 7-day marks and returns milestone info."""
    out = {"shield_earned": False, "milestone": None, "bonus": 0}
    s = int(m.get("streak", 0))
    if s and s % SHIELD_EVERY == 0 and m.get("_shield_mark") != s:
        if m.get("shields", 0) < SHIELD_MAX:
            m["shields"] = m.get("shields", 0) + 1
            out["shield_earned"] = True
        m["_shield_mark"] = s
    if s in MILESTONES and m.get("_ms_mark") != s:
        m["_ms_mark"] = s
        m["points"] = m.get("points", 0) + MILESTONES[s]
        out["milestone"] = s
        out["bonus"] = MILESTONES[s]
    return out


def protect_streaks(members, now=None) -> list:
    """Run once a day just after midnight: members who did NOT play yesterday
    but have a shield keep their streak (shield consumed). Returns [(uid, streak)]."""
    now = now or datetime.now(config.IST)
    yday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    dby = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    saved = []
    for uid, m in members.members.items():
        if not m.get("registered") or m.get("streak", 0) < 2:
            continue
        if m.get("last_correct") == dby and m.get("shields", 0) > 0:
            m["shields"] -= 1
            m["last_correct"] = yday           # streak logic sees a played day
            m["last_active"] = yday
            m["shield_used"] = m.get("shield_used", 0) + 1
            saved.append((uid, m["streak"]))
    if saved:
        members.kv.save()
    return saved


def shield_dm(m: dict, streak: int) -> str:
    return (f"🛡 Streak Shield used! నిన్న miss అయినా మీ {streak}-day streak safe.\n"
            f"Shields left: {m.get('shields', 0)}/{SHIELD_MAX} · ప్రతి 7-day streak కి ఒక shield.")


def milestone_post(m: dict, streak: int, cfg=None) -> str:
    from . import districts as D
    d = m.get("district", "")
    dd = f" · {d} ({D.telugu_name(d)})" if d else ""
    head = f"{cfg['emoji']} " if cfg else ""
    return (f"{head}🔥 {streak}-DAY STREAK — {m.get('name', 'Player')}{dd}\n"
            f"{streak} రోజులు వరుసగా quiz ఆడారు · +{MILESTONES[streak]} pts 🎉\n"
            f"మీ streak ఎంత? bot లో /me")


# ======================================================== 2. MYSTERY MULTIPLIER
def mystery_pick(round_id: str, channel: str, n_questions: int):
    """Deterministic (round, channel) → (index, multiplier). Same for everyone."""
    if n_questions <= 0:
        return None, 1
    h = hashlib.sha256(f"{round_id}|{channel}|mystery".encode()).hexdigest()
    idx = int(h[:8], 16) % n_questions
    r = int(h[8:12], 16) % 100
    acc = 0
    for mult, w in MYSTERY_WEIGHTS:
        acc += w
        if r < acc:
            return idx, mult
    return idx, 2


def apply_mystery(members, round_id: str, channel: str, qids: list) -> dict:
    """After a round: members who got the mystery question right get bonus
    (mult-1) extra points. Returns {uid: bonus}."""
    if not qids:
        return {}
    idx, mult = mystery_pick(round_id, channel, len(qids))
    if idx is None or mult <= 1:
        return {}
    mq = qids[idx]
    out = {}
    base = 10      # P_CORRECT — bonus = (mult-1) × base so ×5 really means 50 pts
    ch = members.data.get("rounds", {}).get(round_id, {}).get("by_channel", {}).get(channel, {})
    for uid, e in ch.items():
        if mq in e.get("right", []):
            m = members._get(uid)
            m["points"] = m.get("points", 0) + (mult - 1) * base
            m["mystery_hits"] = m.get("mystery_hits", 0) + 1
            out[str(uid)] = (mult - 1) * base
    if out:
        members.kv.save()
    return out


def mystery_line(round_id: str, channel: str, n: int, winners: int) -> str:
    idx, mult = mystery_pick(round_id, channel, n)
    if idx is None:
        return ""
    return (f"🎁 Mystery question was Q{idx + 1} — ×{mult} points! "
            f"{winners} మంది సాధించారు. రేపు ఏ ప్రశ్నో ఎవరికీ తెలియదు 😉")


def mystery_opener_line() -> str:
    return "🎁 ఈ round లో ఒక Mystery Question ఉంది — ×2/×3/×5 points. ఏదో చివర్లో తెలుస్తుంది!"


# ================================================================ 3. SQUADS
def _sq():
    return load_json(SQUADS_PATH, {"squads": {}, "by_uid": {}})


def _code(data):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        c = "".join(random.choice(alphabet) for _ in range(4))
        if c not in data["squads"]:
            return c


def squad_code_display(code: str) -> str:
    return code if code.startswith("SQ-") else f"SQ-{code}"


def squad_code_normalize(raw: str) -> str:
    """'sq-7k4q' / 'SQ 7K4Q' / '7k4q' → stored bare code ('7K4Q')."""
    c = (raw or "").strip().upper()
    if c.startswith("SQ"):
        c = c[2:].lstrip("-–_ ")
    return re.sub(r"[^A-Z0-9]", "", c)


def squad_create(members, uid, name: str):
    m = members.members.get(str(uid)) or {}
    if not m.get("registered"):
        return None, "ముందు register అవ్వండి — /start"
    data = _sq()
    if str(uid) in data["by_uid"]:
        return None, "మీరు already ఒక squad లో ఉన్నారు — /squad చూడండి. వదలాలంటే /squad leave"
    name = (name or f"{m.get('district', 'Team')} Squad").strip()[:24]
    code = _code(data)
    data["squads"][code] = {"code": code, "name": name, "leader": str(uid), "members": [str(uid)],
                            "created": datetime.now(config.IST).isoformat()}
    data["by_uid"][str(uid)] = code
    save_json_atomic(SQUADS_PATH, data)
    disp = squad_code_display(code)
    return code, (f"👥 Squad '{name}' created! Code: {disp}\n"
                  f"Friends ని పిలవండి: bot లో /squad join {disp}  (2–{MAX_SQUAD_MEMBERS} members)\n"
                  f"Squad score = అందరి ✅ కలిపి · ప్రతి సోమవారం Squad Top-5 channel లో పేర్లతో 🏆\n"
                  f"⚔️ Squad vs Squad race కోసం: /battle new")


def squad_join(members, uid, code: str):
    m = members.members.get(str(uid)) or {}
    if not m.get("registered"):
        return None, "ముందు register అవ్వండి — /start"
    data = _sq()
    norm = squad_code_normalize(code)
    s = data["squads"].get(norm) or data["squads"].get((code or "").upper().strip())
    if s:
        code = norm if norm in data["squads"] else (code or "").upper().strip()
    if not s:
        return None, f"Squad code దొరకలేదు ({squad_code_display(norm or (code or '').upper().strip())}). Leader అడిగి మళ్ళీ ట్రై చేయండి."
    if str(uid) in data["by_uid"]:
        return None, "మీరు already ఒక squad లో ఉన్నారు."
    if len(s["members"]) >= MAX_SQUAD_MEMBERS:
        return None, f"ఈ squad full ({MAX_SQUAD_MEMBERS}/{MAX_SQUAD_MEMBERS})."
    s["members"].append(str(uid))
    data["by_uid"][str(uid)] = code
    save_json_atomic(SQUADS_PATH, data)
    # squad invite doubles as referral for the leader
    try:
        members.add_referral(uid, s["leader"])
    except Exception:
        pass
    return s, f"✅ Joined squad '{s['name']}' ({len(s['members'])}/{MAX_SQUAD_MEMBERS}). కలిసి ఆడండి, కలిసి గెలవండి 🔥"


def squad_leave(uid):
    data = _sq()
    code = data["by_uid"].pop(str(uid), None)
    if not code:
        return "మీరు ఏ squad లోనూ లేరు."
    s = data["squads"].get(code)
    if s:
        s["members"] = [u for u in s["members"] if u != str(uid)]
        if not s["members"]:
            data["squads"].pop(code, None)
        elif s["leader"] == str(uid):
            s["leader"] = s["members"][0]
    save_json_atomic(SQUADS_PATH, data)
    return "Squad నుంచి బయటకు వచ్చారు."


def squad_week_scores(members, now=None):
    now = now or datetime.now(config.IST)
    since = (now - timedelta(days=7)).strftime("%Y%m%d")
    per_uid = {}
    for rid, r in members.data.get("rounds", {}).items():
        if rid.lstrip("GM")[:8] < since:
            continue
        for players in r.get("by_channel", {}).values():
            for uid, e in players.items():
                per_uid[str(uid)] = per_uid.get(str(uid), 0) + e["correct"]
    data = _sq()
    rows = []
    for code, s in data["squads"].items():
        if len(s["members"]) < 2:
            continue
        total = sum(per_uid.get(u, 0) for u in s["members"])
        rows.append((total, s))
    rows.sort(key=lambda x: -x[0])
    return rows, per_uid


def render_squad(members, uid):
    data = _sq()
    code = data["by_uid"].get(str(uid))
    if not code:
        return ("👥 Friend Squad — 3–5 friends కలిసి ఒక team.\n"
                "Squad score = అందరి ✅ కలిపి · వారానికి Squad Top-5 channel లో.\n\n"
                "/squad new <పేరు> — కొత్త squad\n/squad join <CODE> — friend squad లో చేరండి")
    s = data["squads"][code]
    rows, per_uid = squad_week_scores(members)
    rank = next((i for i, (_t, x) in enumerate(rows, 1) if x["code"] == code), None)
    lines = [f"👥 {s['name']} · code {squad_code_display(code)} · {len(s['members'])}/{MAX_SQUAD_MEMBERS}", ""]
    for u in sorted(s["members"], key=lambda u: -per_uid.get(u, 0)):
        mm = members.members.get(u) or {}
        lines.append(f"  {'👑' if u == s['leader'] else '•'} {mm.get('name', 'Player')[:18]} · {mm.get('district', '')} — {per_uid.get(u, 0)} ✅")
    total = sum(per_uid.get(u, 0) for u in s["members"])
    lines += ["", f"This week: {total} ✅" + (f" · squad rank #{rank}" if rank else " (need 2+ members to rank)")]
    if len(s["members"]) < MAX_SQUAD_MEMBERS:
        lines.append(f"ఇంకా {MAX_SQUAD_MEMBERS - len(s['members'])} మందిని పిలవండి: /squad join {squad_code_display(code)}")
    lines.append("⚔️ Squad vs Squad race: /battle new · /battle list")
    return "\n".join(lines)


def squad_buttons(uid=None):
    data = _sq()
    code = data["by_uid"].get(str(uid)) if uid else None
    if not code:
        return [
            [("➕ Create Squad", "sq:create"), ("📋 Top Squads", "arena:top")],
            [("⚔️ Squad Battles (/battle)", "arena:list")]
        ]
    s = data["squads"].get(code, {})
    disp = squad_code_display(code)
    rows = [
        [("⚔️ Battle Now (10 Q)", "arena:new:10"), ("📋 Open Rooms", "arena:list")],
        [("🏆 Squad Rankings", "arena:top"), ("🚪 Leave Squad", "sq:leave")]
    ]
    return rows


def render_squad_top(members, limit=5, cfg=None):
    from . import districts as D
    rows, per_uid = squad_week_scores(members)
    if not rows:
        return ""
    head = f"{cfg['emoji']} " if cfg else ""
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    lines = [f"{head}👥 SQUAD OF THE WEEK — Friend Squads Top {min(limit, len(rows))}", ""]
    for i, (total, s) in enumerate(rows[:limit]):
        names = []
        for u in s["members"]:
            mm = members.members.get(u) or {}
            d = mm.get("district", "")
            names.append(f"{mm.get('name', 'Player')[:14]}" + (f" ({d})" if d else ""))
        lines.append(f"{medals[i]} {s['name']} — {total} ✅")
        lines.append("    " + ", ".join(names))
    lines += ["", "మీ friends తో squad పెట్టండి → bot లో /squad new <పేరు> · Squad invite = referral +20 pts"]
    return "\n".join(lines)


# ============================================================ 5. FOMO LINES
def live_line(members, channel: str, district: str = "") -> str:
    """'🔴 N aspirants played the last round · M from <district>'."""
    try:
        rounds = members.data.get("rounds", {})
        if not rounds:
            return ""
        last = None
        for rid in sorted(rounds, reverse=True):
            if channel in rounds[rid].get("by_channel", {}):
                last = rounds[rid]["by_channel"][channel]
                break
        if not last:
            return ""
        n = len(last)
        total_reg = sum(1 for m in members.members.values() if m.get("registered"))
        parts = [f"🔴 {n} aspirants played the last round"]
        if district:
            k = sum(1 for u in last if (members.members.get(str(u)) or {}).get("district") == district)
            if k:
                parts.append(f"{k} from {district}")
        parts.append(f"{total_reg} registered")
        return " · ".join(parts)
    except Exception:
        return ""
