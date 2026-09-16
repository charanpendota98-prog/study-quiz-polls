"""
COLLEGE CUP — cricket/IPL-style knockout tournament between colleges.

Any number of colleges (3–16) enter ONE cup. The bot builds a seeded bracket:
    10 colleges → Round of 16 with 6 byes → QUARTER-FINALS → SEMI-FINALS → 🏆 FINAL
Every match is an ordinary campus event (college mode) between exactly two
colleges, and ALL matches of a round run in PARALLEL — each organiser starts
their own match with the usual 🚀 START button. When a match event finishes,
the winner (college table score) advances automatically; the next round's
matches are created instantly. No typing, no manual brackets.

Seeding: standard bracket order (1 vs N, 2 vs N-1 …) in the order the
colleges were added; extra slots are byes for the top seeds.

Rewards (paid on final): champion college members +50 pts, runner-up +25,
MVP of the final +25; trophy post queued to the hub channels + Google Sheet
('rounds' tab, channel=CUP) + hall-of-fame line on the cup record.

State: data/cup.json   {"cups": {code: {...}}, "by_event": {event_code: [cup, round_idx, pair_idx]}}
All functions are guarded — a broken cup can never crash the bot.
"""
from __future__ import annotations

import random
from datetime import datetime

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "cup.json"
MIN_COLLEGES, MAX_COLLEGES = 3, 16
CHAMPION_PTS, RUNNER_PTS, FINAL_MVP_PTS = 50, 25, 25
MATCH_Q, MATCH_LEVEL = 15, "easy"


def _now():
    return datetime.now(config.IST)


def _load():
    d = load_json(PATH, {}) or {}
    d.setdefault("cups", {}); d.setdefault("by_event", {})
    return d


def _save(d):
    save_json_atomic(PATH, d)


def _code(existing):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        c = "CUP-" + "".join(random.choice(alphabet) for _ in range(4))
        if c not in existing:
            return c


# ------------------------------------------------------------------ bracket
def seed_order(size: int) -> list:
    """Classic seeded bracket order for a power-of-2 draw: [1,8,4,5,2,7,3,6]…"""
    order = [1]
    while len(order) < size:
        m = len(order) * 2 + 1
        order = [s for x in order for s in (x, m - x)]
    return order


def label_for(n_pairs: int) -> str:
    return {1: "🏆 FINAL", 2: "⚡ SEMI-FINALS", 4: "🔥 QUARTER-FINALS"}.get(
        n_pairs, f"ROUND OF {n_pairs * 2}")


def _make_match(cup, d, rnd_idx, a, b):
    """Create the campus event for one cup match (b may be None = bye)."""
    from . import campus
    pair = {"a": a, "b": b, "event": None, "winner": None, "bye": b is None,
            "score": ""}
    if b is None:
        pair["winner"] = a                     # bye advances instantly
        pair["score"] = "bye"
        return pair
    label = cup["rounds"][rnd_idx]["label"]
    clean = label.replace("🏆 ", "").replace("⚡ ", "").replace("🔥 ", "")
    name = f"{cup['name']} · {clean}: {a} vs {b}"
    code = campus.new_event(name[:70], cup["district"], [a, b], MATCH_Q,
                            MATCH_LEVEL, created_by=cup.get("by", ""), mode="college")
    cd = campus._load()
    e = cd["events"].get(code)
    if e is not None:
        e["cup"] = cup["code"]
        campus._save(cd)
    pair["event"] = code
    d["by_event"][code] = [cup["code"], rnd_idx, len(cup["rounds"][rnd_idx]["pairs"])]
    return pair


def cup_new(district, colleges, name="", created_by="", n_q=MATCH_Q):
    """Create a knockout cup. Returns (code, summary) or (None, error)."""
    cols = []
    for c in colleges:
        c = str(c).strip()[:40]
        if c and c not in cols:
            cols.append(c)
    if len(cols) < MIN_COLLEGES:
        return None, f"Cup కి కనీసం {MIN_COLLEGES} colleges కావాలి (2 అయితే /campus new వాడండి)."
    if len(cols) > MAX_COLLEGES:
        return None, f"గరిష్ఠం {MAX_COLLEGES} colleges — ముందుగా {MAX_COLLEGES} పెట్టండి."
    d = _load()
    code = _code(d["cups"])
    size = 1
    while size < len(cols):
        size *= 2
    slots = [cols[s - 1] if s <= len(cols) else None for s in seed_order(size)]
    cup = {"code": code, "name": (name or f"{district} College Cup").strip()[:50],
           "district": district, "colleges": cols, "created": _now().isoformat(),
           "by": str(created_by), "state": "live", "champion": None, "runner": None,
           "n_q": int(n_q), "rounds": [], "announce": []}
    d["cups"][code] = cup
    pairs = [{"a": slots[i], "b": slots[i + 1]} for i in range(0, len(slots), 2)]
    rnd = {"label": label_for(len(pairs)), "pairs": []}
    cup["rounds"].append(rnd)
    byes = 0
    for p in pairs:
        mp = _make_match(cup, d, 0, p["a"], p["b"])
        rnd["pairs"].append(mp)
        byes += 1 if mp["bye"] else 0
    _save(d)
    live = sum(1 for p in rnd["pairs"] if not p["bye"])
    return code, (f"🏆 CUP {code} ready — {cup['name']}\n"
                  f"👥 {len(cols)} colleges · {label_for(len(pairs))}: {live} matches live + {byes} byes\n"
                  f"📲 అన్ని matches ఒకేసారి (parallel) — ప్రతి match 🚀 START నొక్కితే మొదలవుతుంది.\n"
                  f"Bracket: /cup {code}")


# ------------------------------------------------------------------ progress
def on_event_done(members, e) -> None:
    """campus._finish hook — advance the bracket when a cup match ends."""
    try:
        d = _load()
        ref = d["by_event"].get(e["code"])
        if not ref:
            return
        code, ri, pi = ref
        cup = d["cups"].get(code)
        if not cup or cup["state"] != "live":
            return
        pair = cup["rounds"][ri]["pairs"][pi]
        if pair["winner"]:
            return
        from . import campus
        cols = campus.college_table(e)           # sorted best-first
        by_col = {r["college"]: r for r in cols}
        winner = None
        for r in cols:
            if r["college"] in (pair["a"], pair["b"]):
                winner = r["college"]            # higher-ranked of the two colleges
                break
        if not winner:                           # nobody answered → walkover to seed A
            winner = pair["a"]
            pair["score"] = "walkover (no scores)"
        else:
            w = by_col.get(winner, {})
            l = by_col.get(pair["a"] if winner == pair["b"] else pair["b"], {})
            pair["score"] = f"{w.get('score', 0):g} vs {l.get('score', 0):g}"
        pair["winner"] = winner
        _round_complete(cup, d, members, e)
        _save(d)
    except Exception as ex:
        print(f"   [cup] note: {ex}")


def _round_complete(cup, d, members, e):
    """If the current round is decided, build the next one (or crown champion)."""
    ri = len(cup["rounds"]) - 1
    rnd = cup["rounds"][ri]
    winners = [p["winner"] for p in rnd["pairs"]]
    if not all(winners):
        return
    if len(winners) == 1:
        _crown(cup, d, members, winners[0], rnd, e)
        return
    nxt = {"label": label_for(len(winners) // 2), "pairs": []}
    cup["rounds"].append(nxt)
    ri2 = len(cup["rounds"]) - 1
    for i in range(0, len(winners), 2):
        a, b = winners[i], (winners[i + 1] if i + 1 < len(winners) else None)
        nxt["pairs"].append(_make_match(cup, d, ri2, a, b))
    cup["announce"].append({"to": "staff", "text":
        f"🏆 {cup['name']} ({cup['code']}) — {nxt['label']} READY\n" +
        "\n".join(f"  ⚔️ {p['a']} vs {p['b']} · event {p['event']} · /campus start {p['event']}"
                  for p in nxt["pairs"] if not p["bye"]) +
        "\nPoster: /campus poster <code> · అన్నీ ఒకేసారి పెట్టొచ్చు (parallel)"})


def _crown(cup, d, members, champion, final_round, final_event):
    from . import campus
    runner = None
    for p in final_round["pairs"]:
        runner = p["a"] if p["winner"] == p["b"] else p["b"]
    cup["state"] = "done"
    cup["champion"] = champion
    cup["runner"] = runner
    # MVP of the final = best individual player of the final event
    mvp_uid, mvp_pts = None, 0
    try:
        for u, p in campus.ranking(final_event)[:1]:
            mvp_uid, mvp_pts = u, p.get("pts", 0)
    except Exception:
        pass
    # rewards: champion/runner college members + final MVP
    paid = {"champion": 0, "runner": 0}
    for uid, m in members.members.items():
        if not m.get("registered"):
            continue
        if m.get("college") == champion:
            m["points"] = m.get("points", 0) + CHAMPION_PTS
            paid["champion"] += 1
        elif m.get("college") == runner:
            m["points"] = m.get("points", 0) + RUNNER_PTS
            paid["runner"] += 1
    if mvp_uid:
        mv = members._get(mvp_uid)
        mv["points"] = mv.get("points", 0) + FINAL_MVP_PTS
    members.kv.save()
    cup["paid"] = paid
    cup["mvp"] = mvp_uid
    fs = final_round["pairs"][0].get("score", "") if final_round["pairs"] else ""
    mvp_line = ""
    if mvp_uid:
        mn = (members.members.get(str(mvp_uid)) or {}).get("name", "Player")
        mvp_line = f"\n🏅 Final MVP: {mn} ({mvp_pts} pts, +{FINAL_MVP_PTS})"
    cup["announce"].append({"to": "hub", "text":
        f"🏆🏆 {cup['name']} — CHAMPION: {champion.upper()} 🏆🏆\n"
        f"⚔️ Final: {champion} def. {runner or '—'} ({fs}){mvp_line}\n"
        f"🎁 Champion college members +{CHAMPION_PTS} pts ({paid['champion']}) · runner-up +{RUNNER_PTS} ({paid['runner']})\n"
        f"మీ college కి ఇదే కావాలంటే → /campuswar లేదా /cup new"})
    try:
        from . import crm
        if crm.sheet_enabled():
            rows = []
            for i, col in enumerate([champion, runner] + [c for c in cup["colleges"]
                                                           if c not in (champion, runner)]):
                rows.append({"uid": "", "name": col, "district": cup["district"],
                             "correct": 0, "total": 0,
                             "points": CHAMPION_PTS if i == 0 else (RUNNER_PTS if i == 1 else 0)})
            crm.push_round_top(cup["code"], "CUP", rows[:MAX_COLLEGES])
    except Exception:
        pass


def pop_announces() -> list:
    """[{'to': 'hub'|'staff', 'text': ...}] — drained by the bot loop."""
    d = _load()
    out = []
    for cup in d["cups"].values():
        while cup.get("announce"):
            out.append(cup["announce"].pop(0))
    if out:
        _save(d)
    return out


# ------------------------------------------------------------------ display
def cup_progress(cup) -> tuple:
    """(round_label, done, total) of the current (latest) round."""
    rnd = cup["rounds"][-1]
    done = sum(1 for p in rnd["pairs"] if p["winner"])
    return rnd["label"], done, len(rnd["pairs"])


def cup_ping_targets(code) -> list:
    """Event codes of this cup's matches that are still waiting for students."""
    from . import campus
    d = _load()
    cup = d["cups"].get(code)
    ev = campus._load()["events"]
    out = []
    if not cup:
        return out
    for rnd in cup["rounds"]:
        for p in rnd["pairs"]:
            e = ev.get(p.get("event") or "")
            if e and e["state"] == "open":
                out.append(e["code"])
    return out


def render_cup(code) -> str:
    d = _load()
    cup = d["cups"].get(code)
    if not cup:
        return "❓ Cup దొరకలేదు — /cup లిస్ట్ చూడండి."
    label, done, total = cup_progress(cup)
    head = [f"🏆 {cup['name']} · {cup['code']} · {cup['district']}",
            f"👥 {len(cup['colleges'])} colleges · {'LIVE' if cup['state'] == 'live' else 'DONE'}"]
    if cup["state"] == "live":
        head.append(f"📊 Now: {label} — {done}/{total} matches done" +
                    (" · 🚀 START పెట్టాల్సినవి ఉన్నాయి!" if done < total else " · next round వస్తోంది…"))
    lines = head + [""]
    for rnd in cup["rounds"]:
        lines.append(f"── {rnd['label']} ──")
        for p in rnd["pairs"]:
            if p["bye"]:
                lines.append(f"  🎟 {p['a']} — bye")
            elif p["winner"]:
                loser = p["a"] if p["winner"] == p["b"] else p["b"]
                lines.append(f"  ✅ {p['winner']} def. {loser} ({p['score']})")
            else:
                lines.append(f"  ⏳ {p['a']} vs {p['b']} · {p['event']} → /campus start {p['event']}")
    if cup["champion"]:
        lines += ["", f"👑 CHAMPION: {cup['champion']} 🏆" + (f" · runner-up {cup['runner']}" if cup["runner"] else "")]
    else:
        lines += ["", "ప్రతి match అయ్యాకే వచ్చే రౌండ్ — అన్నీ ఒకేసారి నడపొచ్చు ⚡"]
    return "\n".join(lines)


def list_cups(limit=5) -> str:
    d = _load()
    cups = sorted(d["cups"].values(), key=lambda c: c.get("created", ""), reverse=True)[:limit]
    if not cups:
        return ("🏆 COLLEGE CUP — cricket-style knockout between colleges.\n"
                "Create: /cup new <District> | College A ; College B ; College C …\n"
                "(3–16 colleges · seeded bracket · parallel matches · auto rounds)")
    lines = ["🏆 COLLEGE CUPS", ""]
    for c in cups:
        st = "LIVE" if c["state"] == "live" else f"👑 {c.get('champion', '')}"
        lines.append(f"• {c['code']} {c['name'][:30]} · {len(c['colleges'])}🏫 · {st}")
    lines += ["", "కొత్తది: /cup new <District> | A ; B ; C ; D …  ·  bracket: /cup <CODE>"]
    return "\n".join(lines)


def cup_buttons(code=None):
    rows = []
    if code:
        rows.append([("🔄 Refresh bracket", f"cupc:bracket:{code}"),
                     ("🔔 Ping all waiting rooms", f"cupc:ping:{code}")])
        rows.append([("🏫 All matches panel", f"cupc:panel:{code}")])
    return rows or None
