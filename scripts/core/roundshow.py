"""
ROUND SHOW — the post that goes to the exam channel when a round closes.
Not just Top-10: EVERY answerer is counted and placed in a tier, so nobody
feels invisible and the post reads like a match summary, not a list.

Sections (all computed from members.data["rounds"][rid]["by_channel"][ch]):
  🏆 Top 10           — name · district · score · level badge · ⚡ fastest tag
  🌱 Rising 5         — best of the mid-table (rank 11+): "next time +1 ✅ → Top 10"
  📊 Score spread     — histogram: 💯 perfect / 🔥 8-9 / 👍 5-7 / 💪 <5 with counts
  🏅 Specials         — ⚡ Fastest finisher · 🆕 Best newcomer · 📈 Comeback (vs last round)
                        · 🎯 perfect-score count · 👑 District of the round
  🧮 How points work  — one line, so scoring is never a mystery

Scoring/ranking = same as members.round_top: most correct → fewer attempts → finished earliest.
"""
from __future__ import annotations

from datetime import datetime

from . import config
from . import districts as D
from .members import level_for

MEDALS = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]


def _players(members, round_id, ch):
    raw = members.data.get("rounds", {}).get(round_id, {}).get("by_channel", {}).get(ch, {})
    rows = []
    for uid, e in raw.items():
        m = members.members.get(str(uid)) or {}
        if not m.get("registered"):
            continue
        rows.append({"uid": str(uid), "name": (m.get("name") or m.get("username") or "Player")[:20],
                     "district": m.get("district", ""), "correct": e.get("correct", 0), "total": e.get("total", 0),
                     "first": e.get("first", ""), "last": e.get("last", ""), "points": m.get("points", 0),
                     "rounds": m.get("rounds_played", m.get("rounds", 0))})
    rows.sort(key=lambda r: (-r["correct"], r["total"], r["last"]))
    return rows, len(raw)


def _secs(r):
    try:
        return (datetime.fromisoformat(r["last"]) - datetime.fromisoformat(r["first"])).total_seconds()
    except Exception:
        return None


def _prev_round_correct(members, uid, round_id, ch):
    """Player's correct count in the previous round of this channel (for comeback)."""
    prev = [rid for rid in members.data.get("rounds", {}) if rid < round_id and rid[:1].isdigit()
            and ch in members.data["rounds"][rid].get("by_channel", {})
            and str(uid) in members.data["rounds"][rid]["by_channel"][ch]]
    if not prev:
        return None
    return members.data["rounds"][max(prev)]["by_channel"][ch][str(uid)].get("correct", 0)


def render(members, round_id, ch, n_q, label="", cfg=None):
    rows, n_all = _players(members, round_id, ch)
    if not rows:
        return ""
    head = f"{cfg['emoji']} " if cfg else ""
    lab = f"{label} " if label else ""
    perfect = [r for r in rows if r["correct"] >= n_q and n_q > 0]
    lines = [f"{head}🏁 {lab}Round FINISHED — {n_q} Q · 👥 {len(rows)} players ఆడారు",
             ""]

    # ---- Top 10
    fastest_uid = None
    timed = [(s, r["uid"]) for r in rows[:10] if r["correct"] == rows[0]["correct"] and (s := _secs(r)) is not None]
    if timed:
        fastest_uid = min(timed)[1]
    lines.append("🏆 TOP 10")
    for i, r in enumerate(rows[:10]):
        lv = level_for(r["points"])
        lv = lv.get("icon", "") if isinstance(lv, dict) else lv[1]
        dte = D.telugu_name(r["district"]) if r["district"] else ""
        place = f" · {r['district']}" if r["district"] else ""
        tag = " ⚡fastest" if r["uid"] == fastest_uid else ""
        lines.append(f"{MEDALS[i]} {r['name']}{place} — {r['correct']}/{n_q} ✅ {lv}{tag}")

    # ---- Rising 5 (mid table)
    mid = rows[10:]
    if mid:
        gap = rows[9]["correct"] - mid[0]["correct"] + 1 if len(rows) >= 10 else 1
        lines += ["", f"🌱 RISING 5 (rank 11–{len(rows)})"]
        for r in mid[:5]:
            place = f" · {r['district']}" if r["district"] else ""
            lines.append(f"• {r['name']}{place} — {r['correct']}/{n_q} ✅")
        lines.append(f"   ఇంకా +{max(gap, 1)} ✅ చేస్తే Top 10 లో! 🔥")

    # ---- Score spread
    if n_q:
        b_perf = len(perfect)
        b_hi = sum(1 for r in rows if 0.8 * n_q <= r["correct"] < n_q)
        b_mid = sum(1 for r in rows if 0.5 * n_q <= r["correct"] < 0.8 * n_q)
        b_low = len(rows) - b_perf - b_hi - b_mid
        mx = max(b_perf, b_hi, b_mid, b_low, 1)
        bar = lambda n: "█" * max(1 if n else 0, int(round(8 * n / mx))) + "░" * (8 - max(1 if n else 0, int(round(8 * n / mx))))
        lines += ["", "📊 SCORE SPREAD",
                  f"💯 {n_q}/{n_q}   {bar(b_perf)} {b_perf}",
                  f"🔥 {int(0.8 * n_q)}–{n_q - 1}   {bar(b_hi)} {b_hi}",
                  f"👍 {int(0.5 * n_q)}–{int(0.8 * n_q) - 1}   {bar(b_mid)} {b_mid}",
                  f"💪 <{int(0.5 * n_q)}     {bar(b_low)} {b_low}"]
        avg = sum(r["correct"] for r in rows) / len(rows)
        lines.append(f"📈 Average {avg:.1f}/{n_q} · {round(100 * sum(r['correct'] for r in rows) / max(sum(r['total'] for r in rows), 1))}% accuracy")

    # ---- Specials
    sp = []
    if fastest_uid:
        fr = next(r for r in rows if r["uid"] == fastest_uid)
        s = _secs(fr)
        if s is not None and s > 0:
            sp.append(f"⚡ Fastest top score: {fr['name']} — {int(s // 60)}m{int(s % 60):02d}s")
    newbies = [r for r in rows if r["rounds"] <= 3]
    if newbies:
        nb = newbies[0]
        sp.append(f"🆕 Best newcomer: {nb['name']}{' · ' + nb['district'] if nb['district'] else ''} — {nb['correct']}/{n_q}")
    best_cb = None
    for r in rows:
        pc = _prev_round_correct(members, r["uid"], round_id, ch)
        if pc is not None and r["correct"] - pc >= 2 and (best_cb is None or r["correct"] - pc > best_cb[1]):
            best_cb = (r, r["correct"] - pc)
    if best_cb:
        sp.append(f"📈 Comeback: {best_cb[0]['name']} — last round కంటే +{best_cb[1]} ✅")
    if perfect:
        sp.append(f"🎯 Perfect {n_q}/{n_q}: {len(perfect)} " + ("player" if len(perfect) == 1 else "players") + " — " + ", ".join(r["name"] for r in perfect[:5]) + (" …" if len(perfect) > 5 else ""))
    dor = members.district_of_round(round_id, ch)
    if dor:
        sp.append(f"👑 District of the round: {dor['district']} ({D.telugu_name(dor['district'])}) — {dor['avg']}% avg · {dor['players']} players")
    if sp:
        lines += ["", "🏅 SPECIALS"] + sp

    # ---- points formula
    lines += ["", "🧮 Points: ✅ +10 each · 🥇+30 🥈+20 🥉+10 · జిల్లా టాపర్ +10 · రోజు మొదటి round +5 · streak shields 🛡",
              "🫵 మీ personal card DM లో వచ్చింది · మీ పేరు ఇక్కడ రావాలంటే → bot /start లో register 📝"]
    if n_all > len(rows):
        lines.append(f"({n_all - len(rows)} unregistered players ఆడారు — register అయితే పేరు వస్తుంది)")
    return "\n".join(lines)


def my_line(members, uid, round_id, ch, n_q):
    """Appended to the personal DM card: exact rank, tier, gap to Top-10."""
    rows, _ = _players(members, round_id, ch)
    idx = next((i for i, r in enumerate(rows) if r["uid"] == str(uid)), None)
    if idx is None:
        return ""
    r = rows[idx]
    rank = idx + 1
    tier = "🏆 Top 10" if rank <= 10 else ("🌱 Rising" if rank <= 15 else ("👍 Mid" if r["correct"] >= 0.5 * n_q else "💪 Keep going"))
    gap = "" if rank <= 10 else f" · Top 10 కి ఇంకా +{max(1, rows[9]['correct'] - r['correct'] + 1)} ✅"
    beat = round(100 * (len(rows) - rank) / max(len(rows) - 1, 1)) if len(rows) > 1 else 100
    return f"\n📍 Rank #{rank}/{len(rows)} · {tier}{gap}\n🚀 మీరు {beat}% players కంటే ముందు ఉన్నారు"
