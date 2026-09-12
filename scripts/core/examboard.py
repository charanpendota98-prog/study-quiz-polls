"""
EXAM-WISE BOARDS — every exam channel (TSPSC, APPSC, Banking, …) gets its own
competition, on top of the all-exam District War:

  • round close   → Top-10 (already) + "🏙 <EXAM> district clash" mini-table for
                    that round: district avg %, players, best fighter.
  • daily 21:30   → per-channel "Today in <EXAM>": Top-10 aggregated across the
                    day's rounds + district table.
  • Sunday 20:15  → per-channel WEEKLY exam champions (Top-10 + district podium),
                    +40/+25/+15 bonus, "District of the week in <EXAM>" +10 per member.
  • /top <exam> [districts|week]  → same tables on demand, in the bot.

Aggregation source = members.data["rounds"][round_id]["by_channel"][channel].
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from . import districts as D

WEEK_BONUS = {0: 40, 1: 25, 2: 15}
WEEK_DISTRICT_BONUS = 10
MEDALS = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
EXAM_LABEL = {"TSPSC": "TSPSC Groups", "APPSC": "APPSC Groups", "BANKING": "Banking", "RAILWAY": "Railway",
              "POLICE": "Police", "DEFENCE": "Defence", "SSC": "SSC/UPSC", "CURRENT": "Current Affairs"}


def _now():
    return datetime.now(config.IST)


def aggregate(members, channel, since_prefix="", round_ids=None):
    """→ (player_rows, district_rows, n_rounds) for one channel over a period."""
    agg, n_rounds = {}, 0
    for rid, r in members.data.get("rounds", {}).items():
        if round_ids is not None and rid not in round_ids:
            continue
        if since_prefix and rid[:8] < since_prefix and not rid.startswith(("G", "M")):
            continue
        players = r.get("by_channel", {}).get(channel)
        if not players:
            continue
        n_rounds += 1
        for uid, e in players.items():
            a = agg.setdefault(uid, [0, 0, 0, e.get("last", "")])
            a[0] += e["correct"]; a[1] += e["total"]; a[2] += 1
            a[3] = max(a[3], e.get("last", ""))
    rows, dist = [], {}
    for uid, (c, t, rn, last) in agg.items():
        m = members.members.get(str(uid)) or {}
        if not m.get("registered"):
            continue
        d = m.get("district", "")
        rows.append({"uid": uid, "name": m.get("name") or m.get("username") or "Player", "district": d,
                     "correct": c, "total": t, "rounds": rn, "last": last, "points": m.get("points", 0)})
        if d:
            x = dist.setdefault(d, {"correct": 0, "total": 0, "players": 0, "best": None})
            x["correct"] += c; x["total"] += t; x["players"] += 1
            if not x["best"] or c > x["best"][1]:
                x["best"] = (rows[-1]["name"], c)
    rows.sort(key=lambda r: (-r["correct"], r["total"], r["last"]))
    drows = []
    for d, x in dist.items():
        acc = 100 * x["correct"] / max(x["total"], 1)
        # score = avg accuracy + participation weight (so 2 lucky players can't beat 30 solid ones)
        score = round(acc + min(x["players"], 15) * 2, 1)
        drows.append({"district": d, "score": score, "acc": round(acc), "players": x["players"],
                      "correct": x["correct"], "best": x["best"]})
    drows.sort(key=lambda r: (-r["score"], -r["correct"]))
    return rows, drows, n_rounds


def _bar(v, top):
    n = int(round(8 * v / max(top, 1)))
    return "█" * n + "░" * (8 - n)


def district_clash_lines(drows, exam, limit=5):
    if len(drows) < 2:
        return []
    top = drows[0]["score"]
    lines = ["", f"🏙 {EXAM_LABEL.get(exam, exam)} — జిల్లాల clash"]
    for i, r in enumerate(drows[:limit]):
        best = f" · ⭐{r['best'][0][:12]}" if r.get("best") else ""
        lines.append(f"{MEDALS[i]} {r['district']} ({D.telugu_name(r['district'])}) {_bar(r['score'], top)} {r['acc']}% · {r['players']}👤{best}")
    if len(drows) > limit:
        lines.append(f"   … {len(drows) - limit} more districts")
    return lines


def round_clash(members, round_id, channel):
    """Appended to the round Top-10 post: district clash for THIS exam round."""
    _, drows, _ = aggregate(members, channel, round_ids={round_id})
    return "\n".join(district_clash_lines(drows, channel))


def render_board(members, channel, period="today", limit=10):
    """period: today | week | round:<id>"""
    now = _now()
    exam = EXAM_LABEL.get(channel, channel)
    if period == "week":
        since = (now - timedelta(days=7)).strftime("%Y%m%d"); title = f"📆 {exam} — ఈ వారం Top {limit}"
    else:
        since = now.strftime("%Y%m%d"); title = f"📅 {exam} — ఈరోజు Top {limit}"
    rows, drows, n_rounds = aggregate(members, channel, since)
    if not rows:
        return ""
    lines = [f"{config.CHANNELS.get(channel, {}).get('emoji', '🏆')} {title}", f"🎯 {n_rounds} rounds · 👥 {len(rows)} players", ""]
    for i, r in enumerate(rows[:limit]):
        d = f" · {r['district']}" if r["district"] else ""
        lines.append(f"{MEDALS[i]} {r['name'][:22]}{d} — {r['correct']}/{r['total']} ✅ · {r['rounds']}R")
    lines += district_clash_lines(drows, channel, limit=5)
    lines += ["", f"మీ exam board: bot లో /top {channel.lower()} · జిల్లా: /top {channel.lower()} districts"]
    return "\n".join(lines)


def render_districts(members, channel, period="week", limit=10):
    now = _now()
    since = (now - timedelta(days=7 if period == "week" else 0)).strftime("%Y%m%d")
    _, drows, n_rounds = aggregate(members, channel, since)
    if not drows:
        return f"{EXAM_LABEL.get(channel, channel)}: ఇంకా data లేదు — rounds ఆడండి."
    top = drows[0]["score"]
    lines = [f"🏙 {EXAM_LABEL.get(channel, channel)} — జిల్లాల {'వారపు' if period == 'week' else 'ఈరోజు'} table · {n_rounds} rounds", ""]
    for i, r in enumerate(drows[:limit]):
        best = f" · ⭐{r['best'][0][:14]} {r['best'][1]}✅" if r.get("best") else ""
        lines.append(f"{MEDALS[i] if i < 10 else str(i + 1)} {r['district']} ({D.telugu_name(r['district'])}) {_bar(r['score'], top)} {r['score']} · {r['acc']}% · {r['players']}👤{best}")
    lines += ["", "Score = accuracy + participation (max 15 players count) → చిన్న జిల్లా కూడా గెలవచ్చు", "మీ జిల్లా పైకి రావాలంటే → friends ని పిలవండి /invite"]
    return "\n".join(lines)


def weekly_close(members, channel):
    """Sunday: pay bonuses, return the champions post (or '')."""
    since = (_now() - timedelta(days=7)).strftime("%Y%m%d")
    rows, drows, n_rounds = aggregate(members, channel, since)
    if not rows:
        return ""
    exam = EXAM_LABEL.get(channel, channel)
    for i, b in WEEK_BONUS.items():
        if i < len(rows):
            m = members._get(rows[i]["uid"]); m["points"] = m.get("points", 0) + b
            m.setdefault("exam_week_wins", {})[channel] = m.get("exam_week_wins", {}).get(channel, 0) + (1 if i == 0 else 0)
    if drows:
        win = drows[0]["district"]
        for uid, m in members.members.items():
            if m.get("district") == win and m.get("registered"):
                m["points"] = m.get("points", 0) + WEEK_DISTRICT_BONUS
    members.kv.save()
    lines = [f"🏆 {exam} — WEEKLY CHAMPIONS · వారపు విజేతలు", f"🎯 {n_rounds} rounds · 👥 {len(rows)} players", ""]
    for i, r in enumerate(rows[:10]):
        d = f" · {r['district']} ({D.telugu_name(r['district'])})" if r["district"] else ""
        b = f" 🎁+{WEEK_BONUS[i]}" if i in WEEK_BONUS else ""
        lines.append(f"{MEDALS[i]} {r['name'][:22]}{d} — {r['correct']}/{r['total']} ✅ · {r['rounds']}R{b}")
    lines += district_clash_lines(drows, channel, limit=5)
    if drows:
        lines += ["", f"👑 District of the week in {exam}: {drows[0]['district']} ({D.telugu_name(drows[0]['district'])}) — ఆ జిల్లా members అందరికీ +{WEEK_DISTRICT_BONUS} pts!"]
    lines += ["", "కొత్త వారం సోమవారం మొదలు — ప్రతి round ఆడండి 🔥 · register: bot /start"]
    return "\n".join(lines)
