"""
District League — season-long, fair inter-district competition.

Weekly (Mon–Sun) each district earns LEAGUE POINTS from the members' round
results, designed so a big district cannot win by head-count alone:

    week_score = avg_marks_per_player × 10          (quality)
               + min(players, 10) × 2               (participation, capped)
               + grand_test_bonus (5 / 3 / 2 for 1st/2nd/3rd in Sunday test)

Districts are split into two tiers by size of registered base so Adilabad
does not race Hyderabad: 🅰 Premier (top-8 by last-season points) and 🅱
Challengers. Bottom-2 Premier / top-2 Challengers swap each month.

Season = calendar month. Standings, form (last 3 weeks ▲▼), MVP per district.
State: data/league.json  {seasons:{YYYYMM:{weeks:{isoweek:{district:score}}}}, tiers:{...}}
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "league.json"
PREMIER_SIZE = 8


def _load():
    return load_json(PATH, {"seasons": {}, "tiers": {}})


def _week_key(dt):
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def compute_week(members, now=None):
    """Aggregate last 7 days of rounds → {district: {score, players, avg, mvp}}."""
    now = now or datetime.now(config.IST)
    since = (now - timedelta(days=7)).strftime("%Y%m%d")
    agg = {}
    for rid, r in members.data.get("rounds", {}).items():
        date8 = rid.lstrip("GM")[:8]
        if date8 < since:
            continue
        is_grand = rid[:1] in ("G", "M")
        for ch, players in r.get("by_channel", {}).items():
            ranked = sorted(players.items(), key=lambda kv: -kv[1]["correct"])
            for pos, (uid, e) in enumerate(ranked):
                m = members.members.get(str(uid)) or {}
                d = m.get("district")
                if not d or not m.get("registered"):
                    continue
                a = agg.setdefault(d, {"correct": 0, "total": 0, "players": set(), "grand": 0, "best": {}})
                a["correct"] += e["correct"]; a["total"] += e["total"]; a["players"].add(str(uid))
                a["best"][str(uid)] = a["best"].get(str(uid), 0) + e["correct"]
                if is_grand and pos < 3:
                    a["grand"] += (5, 3, 2)[pos]
    out = {}
    for d, a in agg.items():
        n = len(a["players"])
        avg = a["correct"] / max(n, 1)
        score = round(avg * 10 + min(n, 10) * 2 + a["grand"], 1)
        mvp_uid = max(a["best"], key=a["best"].get) if a["best"] else None
        mvp = (members.members.get(mvp_uid) or {}).get("name", "") if mvp_uid else ""
        out[d] = {"score": score, "players": n, "avg": round(avg, 1), "grand": a["grand"], "mvp": mvp,
                  "acc": round(100 * a["correct"] / max(a["total"], 1))}
    return out


def record_week(members, now=None):
    now = now or datetime.now(config.IST)
    data = _load()
    season = data["seasons"].setdefault(now.strftime("%Y%m"), {"weeks": {}})
    wk = compute_week(members, now)
    season["weeks"][_week_key(now - timedelta(days=1))] = {d: v["score"] for d, v in wk.items()}
    if not data["tiers"]:
        data["tiers"] = _initial_tiers(members)
    save_json_atomic(PATH, data)
    return wk, data


def _initial_tiers(members):
    from collections import Counter
    c = Counter(m.get("district") for m in members.members.values()
                if m.get("registered") and m.get("district"))
    prem = [d for d, _ in c.most_common(PREMIER_SIZE)]
    return {"premier": prem, "season": datetime.now(config.IST).strftime("%Y%m")}


def season_table(data, season_key):
    weeks = data["seasons"].get(season_key, {}).get("weeks", {})
    tot, hist = {}, {}
    for wk in sorted(weeks):
        for d, s in weeks[wk].items():
            tot[d] = round(tot.get(d, 0) + s, 1)
            hist.setdefault(d, []).append(s)
    return tot, hist


def promote_relegate(data, season_key):
    """Called at month end: bottom-2 Premier ↔ top-2 Challengers."""
    tot, _ = season_table(data, season_key)
    prem = [d for d in data["tiers"].get("premier", []) if d in tot]
    chal = sorted((d for d in tot if d not in prem), key=lambda d: -tot[d])
    prem_sorted = sorted(prem, key=lambda d: -tot[d])
    down, up = prem_sorted[-2:] if len(prem_sorted) >= 4 else [], chal[:2]
    new_prem = [d for d in prem_sorted if d not in down] + up
    data["tiers"]["premier"] = new_prem[:PREMIER_SIZE]
    data["tiers"]["season"] = season_key
    save_json_atomic(PATH, data)
    return up, down


def _form(hist):
    if len(hist) < 2:
        return "🆕"
    return "▲" if hist[-1] > hist[-2] else ("▼" if hist[-1] < hist[-2] else "▬")


def render_week(members, now=None, limit=8):
    from . import districts as D
    now = now or datetime.now(config.IST)
    wk, data = record_week(members, now)
    if not wk:
        return ""
    season_key = now.strftime("%Y%m")
    tot, hist = season_table(data, season_key)
    prem = set(data["tiers"].get("premier", []))
    lines = [f"🏟 DISTRICT LEAGUE — Week {_week_key(now - timedelta(days=1))[-2:]} · {now:%B} season", ""]

    def block(title, ds):
        if not ds:
            return
        lines.append(title)
        rows = sorted(ds, key=lambda d: -tot.get(d, 0))[:limit]
        for i, d in enumerate(rows, 1):
            w = wk.get(d, {})
            lines.append(f"{i}. {d} ({D.telugu_name(d)}) — {tot.get(d, 0):g} pts {_form(hist.get(d, []))}"
                         f" · this week {w.get('score', 0):g} · {w.get('players', 0)}👥 avg {w.get('avg', 0)}✅")
        lines.append("")
    block("🅰 Premier", [d for d in tot if d in prem])
    block("🅱 Challengers", [d for d in tot if d not in prem])
    mvps = [(d, v["mvp"]) for d, v in sorted(wk.items(), key=lambda kv: -kv[1]["score"]) if v.get("mvp")][:5]
    if mvps:
        lines.append("⭐ District MVPs: " + " · ".join(f"{n} ({d})" for d, n in mvps))
    lines += ["", "Formula: avg per player ×10 + participation (max 10 players ×2) + Grand Test podium",
              "నెల చివర: Premier bottom-2 ⬇ · Challengers top-2 ⬆",
              "మీ జిల్లా పైకి రావాలంటే ఫ్రెండ్స్‌ని పిలవండి 👉 /invite"]
    return "\n".join(lines)
