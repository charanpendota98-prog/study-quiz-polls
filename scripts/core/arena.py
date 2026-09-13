"""
SQUAD BATTLE ARENA — PUBG-style rooms for quiz squads.

A ROOM is a live match between 2–4 squads (each 2–5 players).
  * host squad leader:  /battle new  [questions=10]   → room code  e.g. RM-7K4Q
  * other leaders:      /battle join RM-7K4Q          (their whole squad enters)
  * host:               /battle start  (or auto-start when the room is full /
                        or 3 min after the 2nd squad joins)
  * public lobby:       /battle list   → open rooms ("looking for opponents")
  * everyone else:      /battle watch RM-7K4Q → live scoreboard DMs

MATCH FLOW (state machine advanced by the bot loop's tick(); no sleeps)
  lobby → countdown(30 s) → Q1 … Qn (each 45–75 s by difficulty) → result
  Every player of every squad gets the SAME question at the SAME moment as a
  non-anonymous quiz poll in DM. Scoring per player per question:
      correct: 100 + speed bonus (0–50, linear over the window)
      wrong:   −25   (so guessing hurts, like negative marking)
      skip:    0
  Squad score = sum of players' points (normalised per player when squads are
  unequal: score × 5 / squad_size so a 3-member squad can beat a 5-member one).
  After every question a LIVE SCOREBOARD is DM'd to all players + watchers:
  squad ranking, who answered, streak-of-kills ("🔥 Ravi 3 in a row").

RESULT
  🏆 Winner squad gets +30 arena pts per member, +15 for 2nd; MVP (top scorer
  of the match) +20 and a channel shout-out with names + districts.
  Season ELO per squad (starts 1000, K=32) → tiers: Bronze <1100 · Silver
  <1250 · Gold <1400 · Diamond <1550 · Conqueror ≥1550. Weekly Arena
  Leaderboard in the hub; season resets monthly (top-3 into the Hall of Fame).

TOURNAMENT (weekend)
  /battle tournament  (admin) creates a single-elimination bracket from the
  top-8 squads by ELO; rounds are ordinary rooms auto-created by the bot.

Questions: pulled through Bank.pick() so the permanent no-repeat store still
applies (arena questions never return in channel rounds), balanced difficulty,
chosen from the channels the squads follow (mode = the host's exam channel).
All state: data/arena.json  ({rooms:{}, elo:{}, season:"YYYYMM", history:[]}).
Every public function is guarded — a broken room can never crash the bot.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "arena.json"
ROOM_MIN_SQUADS, ROOM_MAX_SQUADS = 2, 4
DEFAULT_Q = 10
COUNTDOWN_SEC = 30
LOBBY_AUTOSTART_SEC = 180
LOBBY_TTL_SEC = 1800
Q_WINDOW = {"easy": 45, "medium": 60, "hard": 75}
GAP_SEC = 6
PTS_CORRECT, PTS_SPEED_MAX, PTS_WRONG = 100, 50, -25
REWARD_WIN, REWARD_SECOND, REWARD_MVP = 30, 15, 20
ELO_K, ELO_START = 32, 1000
TIERS = ((1550, "💎 Conqueror"), (1400, "💠 Diamond"), (1250, "🥇 Gold"), (1100, "🥈 Silver"), (0, "🥉 Bronze"))


# ------------------------------------------------------------------ storage
def _load():
    d = load_json(PATH, {"rooms": {}, "elo": {}, "season": "", "history": [], "polls": {}})
    season = datetime.now(config.IST).strftime("%Y%m")
    if d.get("season") != season:
        d["last_season"] = {"season": d.get("season"), "elo": d.get("elo", {})}
        d["season"], d["elo"] = season, {}
    return d


def _save(d):
    save_json_atomic(PATH, d)


def _now():
    return datetime.now(config.IST)


def _code(d):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        c = "RM-" + "".join(random.choice(alphabet) for _ in range(4))
        if c not in d["rooms"]:
            return c


def tier(elo: float) -> str:
    for th, name in TIERS:
        if elo >= th:
            return name
    return TIERS[-1][1]


def squad_elo(d, code):
    return float(d["elo"].get(code, ELO_START))


# --------------------------------------------------------------- squads glue
def _squad_of(uid):
    from . import hooks
    data = hooks._sq()
    code = data["by_uid"].get(str(uid))
    return (data["squads"].get(code) if code else None)


def _room_of(d, uid):
    for r in d["rooms"].values():
        if r["state"] in ("lobby", "countdown", "question", "gap") and str(uid) in r["players"]:
            return r
    return None


# ------------------------------------------------------------------- lobby
def room_new(members, uid, n_q: int = DEFAULT_Q, channel: str = ""):
    s = _squad_of(uid)
    if not s:
        return None, "ముందు squad కావాలి — /squad new <పేరు> (2–5 friends)."
    if s["leader"] != str(uid):
        return None, "Squad leader మాత్రమే room open చేయగలరు."
    if len(s["members"]) < 2:
        return None, "Room కి squad లో కనీసం 2 members ఉండాలి — /squad join code friends కి పంపండి."
    d = _load()
    if _room_of(d, uid):
        return None, "మీరు already ఒక room లో ఉన్నారు — /battle leave."
    n_q = max(5, min(20, int(n_q or DEFAULT_Q)))
    m = members.members.get(str(uid)) or {}
    if not channel:
        from .members import exam_channel
        channel = exam_channel(m.get("exam", "")) or "CURRENT"
    code = _code(d)
    r = {"code": code, "host": str(uid), "channel": channel, "n_q": n_q, "state": "lobby",
         "created": _now().isoformat(), "squads": {s["code"]: {"name": s["name"], "members": list(s["members"]),
                                                              "score": 0.0, "raw": 0}},
         "players": {str(u): {"squad": s["code"], "pts": 0, "correct": 0, "wrong": 0, "streak": 0, "best": 0}
                     for u in s["members"]},
         "watchers": [], "questions": [], "qi": -1, "q_open": None, "q_close": None, "answers": {},
         "second_joined": None, "log": []}
    d["rooms"][code] = r
    _save(d)
    return r, (f"🎮 ROOM {code} open! Mode: {config.CHANNELS.get(channel, {}).get('subject', channel)} · {n_q} Q\n"
               f"మీ squad '{s['name']}' ({len(s['members'])}) ready.\n"
               f"Opponent squads leaders కి పంపండి: /battle join {code}\n"
               f"Public lobby లో కూడా కనిపిస్తుంది (/battle list). 2 squads రాగానే 3 నిమిషాల్లో auto-start, "
               f"లేదా host /battle start.")


def room_join(members, uid, code: str):
    s = _squad_of(uid)
    if not s:
        return None, "ముందు squad కావాలి — /squad new <పేరు>."
    if s["leader"] != str(uid):
        return None, "మీ squad leader join చేయాలి (అందరూ automatic గా వస్తారు)."
    if len(s["members"]) < 2:
        return None, "Squad లో కనీసం 2 members కావాలి."
    d = _load()
    r = d["rooms"].get((code or "").upper().strip())
    if not r or r["state"] != "lobby":
        return None, "Room లేదు / already start అయ్యింది. /battle list చూడండి."
    if s["code"] in r["squads"]:
        return None, "మీ squad already ఈ room లో ఉంది."
    if len(r["squads"]) >= ROOM_MAX_SQUADS:
        return None, "Room full (4 squads)."
    for u in s["members"]:
        if _room_of(d, u):
            return None, f"మీ squad member ఇంకో room లో ఉన్నారు."
    r["squads"][s["code"]] = {"name": s["name"], "members": list(s["members"]), "score": 0.0, "raw": 0}
    for u in s["members"]:
        r["players"][str(u)] = {"squad": s["code"], "pts": 0, "correct": 0, "wrong": 0, "streak": 0, "best": 0}
    if len(r["squads"]) == 2:
        r["second_joined"] = _now().isoformat()
    _save(d)
    names = " vs ".join(x["name"] for x in r["squads"].values())
    return r, f"⚔️ Joined {r['code']}: {names}\nStart: host /battle start లేదా auto in 3 min."


def room_leave(uid):
    d = _load()
    r = _room_of(d, uid)
    if not r:
        return "మీరు ఏ room లోనూ లేరు."
    if r["state"] != "lobby":
        return "Match నడుస్తోంది — ఇప్పుడు leave చేయలేరు."
    sq = r["players"][str(uid)]["squad"]
    for u in r["squads"][sq]["members"]:
        r["players"].pop(str(u), None)
    r["squads"].pop(sq, None)
    if not r["squads"] or r["host"] == str(uid):
        r["state"] = "cancelled"
    _save(d)
    return "Room నుంచి బయటకు వచ్చారు." + (" Room closed." if r["state"] == "cancelled" else "")


def room_watch(uid, code):
    d = _load()
    r = d["rooms"].get((code or "").upper().strip())
    if not r or r["state"] in ("done", "cancelled"):
        return "Room లేదు."
    if str(uid) in r["players"]:
        return "మీరు player — scoreboard automatic గా వస్తుంది."
    if str(uid) not in r["watchers"]:
        r["watchers"].append(str(uid)); _save(d)
    return f"👀 Watching {r['code']} — ప్రతి ప్రశ్న తర్వాత live scoreboard వస్తుంది."


def list_rooms():
    d = _load()
    rows = [r for r in d["rooms"].values() if r["state"] == "lobby"]
    if not rows:
        return "🎮 ఇప్పుడు open rooms లేవు — /battle new తో మీరే open చేయండి!"
    lines = ["🎮 OPEN ROOMS — looking for opponents", ""]
    for r in rows[:10]:
        sq = ", ".join(f"{x['name']} ({len(x['members'])})" for x in r["squads"].values())
        lines.append(f"{r['code']} · {config.CHANNELS.get(r['channel'], {}).get('subject', r['channel'])} · "
                     f"{r['n_q']} Q · {len(r['squads'])}/{ROOM_MAX_SQUADS} squads — {sq}")
    lines += ["", "Join: /battle join RM-XXXX (squad leader)"]
    return "\n".join(lines)


# ----------------------------------------------------------------- matching
def _pick_questions(bank, channel, n):
    try:
        qs = bank.pick(channel, n)
    except Exception:
        qs = []
    if len(qs) < n:
        for ch in config.PUBLIC_CHANNELS:
            if ch == channel or len(qs) >= n:
                continue
            try:
                qs += bank.pick(ch, n - len(qs))
            except Exception:
                pass
    return qs[:n]


def _window(q):
    try:
        from .blueprint import difficulty_of
        return Q_WINDOW.get(difficulty_of(q), 60)
    except Exception:
        return 60


def room_start(bank, uid=None, code=None, force=False):
    """Host or auto-start: freeze squads, load questions, enter countdown."""
    d = _load()
    r = d["rooms"].get(code) if code else _room_of(d, uid)
    if not r or r["state"] != "lobby":
        return None, "Room lobby లో లేదు."
    if uid and r["host"] != str(uid) and not force:
        return None, "Host మాత్రమే start చేయగలరు."
    if len(r["squads"]) < ROOM_MIN_SQUADS:
        return None, "కనీసం 2 squads కావాలి — /battle list లో share చేయండి."
    qs = _pick_questions(bank, r["channel"], r["n_q"])
    if len(qs) < 5:
        return None, "ఈ mode లో ఇప్పుడు ప్రశ్నలు సరిపోలేదు — వేరే mode try చేయండి."
    r["questions"] = [{"id": q["id"], "q_en": q.get("q_en", ""), "q_te": q.get("q_te", ""),
                       "options_en": q.get("options_en", []), "options_te": q.get("options_te", []),
                       "answer_index": int(q["answer_index"]), "window": _window(q),
                       "explanation_te": q.get("explanation_te", ""), "explanation_en": q.get("explanation_en", "")}
                      for q in qs]
    r["n_q"] = len(r["questions"])
    r["state"] = "countdown"
    r["q_open"] = (_now() + timedelta(seconds=COUNTDOWN_SEC)).isoformat()
    _save(d)
    return r, None


def countdown_text(r):
    names = " ⚔️ ".join(f"{x['name']} ({len(x['members'])})" for x in r["squads"].values())
    return "\n".join([
        f"🎮 MATCH {r['code']} — {names}",
        f"📝 {r['n_q']} Q · ✅ +100 (+speed bonus up to 50) · ❌ −25 · skip 0",
        "Squad score = members' points (fair-scaled per player)",
        f"⏱ Q1 in {COUNTDOWN_SEC} seconds — అందరూ ready! 🔥",
    ])


# --------------------------------------------------------------------- tick
def tick(bank, tg, members, now=None):
    """Advance every live room. Called by the bot loop every few seconds.
    Returns number of actions taken. Never raises."""
    now = now or _now()
    try:
        d = _load()
    except Exception:
        return 0
    acted = 0
    for r in list(d["rooms"].values()):
        try:
            st = r["state"]
            if st == "lobby":
                if r.get("second_joined") and (now - datetime.fromisoformat(r["second_joined"])).total_seconds() >= LOBBY_AUTOSTART_SEC:
                    _save(d)
                    rr, err = room_start(bank, code=r["code"], force=True)
                    d = _load(); acted += 1
                    if rr:
                        _broadcast(tg, rr, countdown_text(rr))
                elif (now - datetime.fromisoformat(r["created"])).total_seconds() > LOBBY_TTL_SEC:
                    r["state"] = "cancelled"; acted += 1
                    _broadcast(tg, r, f"⌛ Room {r['code']} closed — opponents రాలేదు. మళ్ళీ try చేయండి /battle new")
            elif st == "countdown":
                if now >= datetime.fromisoformat(r["q_open"]):
                    _open_question(tg, r, d, 0, now); acted += 1
            elif st == "question":
                if now >= datetime.fromisoformat(r["q_close"]) or _all_answered(r):
                    _close_question(tg, members, r, d, now); acted += 1
            elif st == "gap":
                if now >= datetime.fromisoformat(r["q_open"]):
                    nxt = r["qi"] + 1
                    if nxt >= r["n_q"]:
                        _finish(tg, members, r, d, now)
                    else:
                        _open_question(tg, r, d, nxt, now)
                    acted += 1
        except Exception as e:
            print(f"   [arena] room {r.get('code')} tick note: {e}")
            r["state"] = "cancelled"
    # prune old rooms
    keep = {}
    for c, r in d["rooms"].items():
        if r["state"] in ("done", "cancelled"):
            try:
                if (now - datetime.fromisoformat(r.get("closed") or r["created"])).total_seconds() < 86400:
                    keep[c] = r
            except Exception:
                pass
        else:
            keep[c] = r
    d["rooms"] = keep
    if acted or len(keep) != len(d["rooms"]):
        _save(d)
    else:
        _save(d)
    return acted


def _all_answered(r):
    ans = r["answers"].get(str(r["qi"]), {})
    return len(ans) >= len(r["players"])


def _broadcast(tg, r, text, watchers=True):
    targets = list(r["players"].keys()) + (r.get("watchers", []) if watchers else [])
    for u in targets:
        try:
            tg.send_message(u, text)
        except Exception:
            pass


def _open_question(tg, r, d, qi, now):
    from .content import build_question_text, build_options
    q = r["questions"][qi]
    r["qi"] = qi
    r["state"] = "question"
    r["q_open"] = now.isoformat()
    r["q_close"] = (now + timedelta(seconds=q["window"])).isoformat()
    r["answers"][str(qi)] = {}
    cfg = config.CHANNELS.get(r["channel"], {"emoji": "🎮", "subject": r["channel"]})
    text = build_question_text(q, cfg, telugu_first=True, position=f"⚔️ {qi + 1}/{r['n_q']} · {q['window']}s")
    opts = build_options(q, telugu_first=True)
    for u in r["players"]:
        try:
            res = tg._call("sendPoll", {"chat_id": u, "question": text[:300],
                                        "options": [{"text": o} for o in opts], "type": "quiz",
                                        "is_anonymous": False, "correct_option_id": q["answer_index"],
                                        "open_period": max(5, min(600, q["window"]))})
            pid = (res.get("result", {}).get("poll") or {}).get("id")
            if pid:
                d["polls"][str(pid)] = [r["code"], qi, str(u)]
        except Exception:
            pass
    _save(d)


def record_answer(members, tg, poll_id, uid, chosen, bank=None):
    """Bot hook. Returns True if this poll belonged to an arena room."""
    try:
        d = _load()
        meta = d["polls"].get(str(poll_id))
        if not meta:
            return False
        code, qi, owner = meta
        if owner != str(uid):
            return True
        r = d["rooms"].get(code)
        if not r or r["state"] != "question" or r["qi"] != qi:
            return True
        ans = r["answers"].setdefault(str(qi), {})
        if str(uid) in ans:
            return True
        q = r["questions"][qi]
        elapsed = (_now() - datetime.fromisoformat(r["q_open"])).total_seconds()
        p = r["players"][str(uid)]
        if int(chosen) == q["answer_index"]:
            speed = max(0, PTS_SPEED_MAX * (1 - elapsed / max(q["window"], 1)))
            pts = PTS_CORRECT + int(round(speed))
            p["correct"] += 1; p["streak"] += 1; p["best"] = max(p["best"], p["streak"])
        else:
            pts = PTS_WRONG
            p["wrong"] += 1; p["streak"] = 0
        p["pts"] += pts
        ans[str(uid)] = {"pts": pts, "t": round(elapsed, 1), "ok": pts > 0}
        _save(d)
        return True
    except Exception as e:
        print(f"   [arena] answer note: {e}")
        return False


def _squad_scores(r):
    out = []
    for code, s in r["squads"].items():
        raw = sum(r["players"][str(u)]["pts"] for u in s["members"] if str(u) in r["players"])
        scaled = raw * 5.0 / max(len(s["members"]), 1)
        s["raw"], s["score"] = raw, round(scaled, 1)
        out.append((scaled, raw, code, s))
    out.sort(key=lambda x: -x[0])
    return out


def scoreboard(r, members, final=False):
    from . import districts as D
    rows = _squad_scores(r)
    head = "🏁 FINAL" if final else f"📊 After Q{r['qi'] + 1}/{r['n_q']}"
    lines = [f"{head} — Room {r['code']}", ""]
    medals = ["🥇", "🥈", "🥉", "4."]
    for i, (scaled, raw, code, s) in enumerate(rows):
        lines.append(f"{medals[i]} {s['name']} — {scaled:g} pts")
        ps = sorted(((str(u), r["players"][str(u)]) for u in s["members"] if str(u) in r["players"]),
                    key=lambda kv: -kv[1]["pts"])
        for u, p in ps[:5]:
            m = members.members.get(u) or {}
            fire = f" 🔥{p['streak']}" if p["streak"] >= 3 else ""
            lines.append(f"    {m.get('name', 'Player')[:14]} ({m.get('district', '')[:10]}) {p['pts']}{fire}")
    if not final:
        q = r["questions"][r["qi"]]
        ans = r["answers"].get(str(r["qi"]), {})
        n_ok = sum(1 for a in ans.values() if a["ok"])
        lines += ["", f"Q{r['qi'] + 1}: {n_ok}/{len(r['players'])} ✅ · key {'ABCD'[q['answer_index']]}"]
        if len(rows) >= 2 and abs(rows[0][0] - rows[1][0]) <= 120:
            lines.append("⚡ Neck and neck! ఇంకా ఏమీ decide అవ్వలేదు")
        lines.append(f"⏭ Next in {GAP_SEC}s")
    return "\n".join(lines)


def _close_question(tg, members, r, d, now):
    r["state"] = "gap"
    r["q_open"] = (now + timedelta(seconds=GAP_SEC)).isoformat()
    for u, p in r["players"].items():        # skipped → streak breaks
        if u not in r["answers"].get(str(r["qi"]), {}):
            p["streak"] = 0
    _save(d)
    _broadcast(tg, r, scoreboard(r, members))


def _finish(tg, members, r, d, now):
    r["state"] = "done"
    r["closed"] = now.isoformat()
    rows = _squad_scores(r)
    # rewards
    mvp_uid = max(r["players"], key=lambda u: r["players"][u]["pts"]) if r["players"] else None
    for i, (scaled, raw, code, s) in enumerate(rows):
        bonus = REWARD_WIN if i == 0 else (REWARD_SECOND if i == 1 else 0)
        for u in s["members"]:
            m = members._get(u)
            m["points"] = m.get("points", 0) + bonus
            m["arena_matches"] = m.get("arena_matches", 0) + 1
            if i == 0:
                m["arena_wins"] = m.get("arena_wins", 0) + 1
    if mvp_uid:
        m = members._get(mvp_uid)
        m["points"] = m.get("points", 0) + REWARD_MVP
        m["arena_mvp"] = m.get("arena_mvp", 0) + 1
    members.kv.save()
    # ELO (multi-squad: pairwise)
    codes = [c for _, _, c, _ in rows]
    old = {c: squad_elo(d, c) for c in codes}
    new = dict(old)
    for i, a in enumerate(codes):
        for j, b in enumerate(codes):
            if i == j:
                continue
            exp = 1 / (1 + 10 ** ((old[b] - old[a]) / 400))
            sc = 1.0 if i < j else 0.0
            new[a] += ELO_K * (sc - exp) / max(len(codes) - 1, 1)
    for c in codes:
        d["elo"][c] = round(new[c], 1)
    d["history"].append({"code": r["code"], "ts": now.isoformat(), "channel": r["channel"],
                         "result": [(c, s["name"], s["score"]) for _, _, c, s in rows],
                         "mvp": mvp_uid})
    d["history"] = d["history"][-500:]
    _save(d)
    from . import districts as D
    text = scoreboard(r, members, final=True)
    w = rows[0][3]
    mv = members.members.get(mvp_uid) or {}
    text += (f"\n\n🏆 WINNER: {w['name']} — +{REWARD_WIN} pts each · 2nd +{REWARD_SECOND}\n"
             f"⭐ MVP: {mv.get('name', '')} ({mv.get('district', '')}) +{REWARD_MVP}\n"
             + "\n".join(f"{s['name']}: ELO {old[c]:.0f} → {new[c]:.0f} {tier(new[c])}" for _, _, c, s in rows)
             + "\n\nRematch? /battle new · Rankings: /battle top")
    _broadcast(tg, r, text)
    r["_shout"] = {"winner": w["name"], "names": [
        f"{(members.members.get(u) or {}).get('name', 'Player')} ({(members.members.get(u) or {}).get('district', '')})"
        for u in w["members"]], "loser": rows[1][3]["name"] if len(rows) > 1 else "", "channel": r["channel"],
        "score": f"{rows[0][0]:g}–{rows[1][0]:g}" if len(rows) > 1 else ""}
    _save(d)


# ---------------------------------------------------------------- shout-outs
def pop_shoutouts():
    d = _load()
    out = []
    for r in d["rooms"].values():
        if r.get("_shout") and not r.get("_shouted"):
            out.append(r["_shout"]); r["_shouted"] = True
    if out:
        _save(d)
    return out


def shout_text(s, cfg=None):
    head = f"{cfg['emoji']} " if cfg else ""
    return (f"{head}⚔️ SQUAD BATTLE — {s['winner']} defeated {s['loser']} {s['score']}\n"
            f"🏆 {', '.join(s['names'])}\n"
            f"మీ friends తో squad పెట్టి challenge చేయండి → bot లో /squad new · /battle new")


# --------------------------------------------------------------- rankings
def render_top(members, limit=10):
    from . import hooks
    d = _load()
    sq = hooks._sq()["squads"]
    rows = sorted(((elo, c) for c, elo in d["elo"].items() if c in sq), reverse=True)
    if not rows:
        return "🏟 Arena season ఇంకా మొదలవలేదు — మొదటి match మీదే! /battle new"
    lines = [f"🏟 ARENA SEASON {d['season'][4:]}/{d['season'][:4]} — Squad Rankings", ""]
    for i, (elo, c) in enumerate(rows[:limit], 1):
        s = sq[c]
        w = sum(1 for h in d["history"] if h["result"] and h["result"][0][0] == c)
        n = sum(1 for h in d["history"] if any(x[0] == c for x in h["result"]))
        lines.append(f"{i}. {s['name']} — {elo:.0f} {tier(elo)} · {w}W/{n - w}L")
    lines += ["", "Tiers: 🥉<1100 🥈<1250 🥇<1400 💠<1550 💎 Conqueror", "నెల చివర top-3 → Hall of Fame 🏛"]
    return "\n".join(lines)


def my_status(members, uid):
    d = _load()
    r = _room_of(d, uid)
    s = _squad_of(uid)
    lines = ["🎮 SQUAD BATTLE ARENA", ""]
    if s:
        elo = squad_elo(d, s["code"])
        lines.append(f"Squad: {s['name']} · ELO {elo:.0f} {tier(elo)}")
    else:
        lines.append("Squad లేదు → /squad new <పేరు>")
    if r:
        lines.append(f"Room: {r['code']} · {r['state']} · {len(r['squads'])} squads")
    lines += ["", "/battle new [10] — room open (leader)", "/battle join RM-XXXX — opponent గా చేరండి (leader)",
              "/battle list — open rooms", "/battle start — host start", "/battle watch RM-XXXX — live చూడండి",
              "/battle top — season rankings", "/battle leave"]
    return "\n".join(lines)


# ------------------------------------------------------------- tournament
def tournament_create(bank, members, size=8):
    """Admin: single-elimination bracket from top squads by ELO (≥2 members)."""
    from . import hooks
    d = _load()
    sq = hooks._sq()["squads"]
    ranked = sorted(((squad_elo(d, c), c) for c, s in sq.items() if len(s["members"]) >= 2), reverse=True)
    codes = [c for _, c in ranked[:size]]
    if len(codes) < 4:
        return None, "Tournament కి కనీసం 4 squads (2+ members) కావాలి."
    # seed pairing 1v8, 2v7 ...
    pairs = [(codes[i], codes[-1 - i]) for i in range(len(codes) // 2)]
    created = []
    for a, b in pairs:
        host = sq[a]["leader"]
        r, err = room_new(members, host, DEFAULT_Q)
        if not r:
            continue
        rr, err2 = room_join(members, sq[b]["leader"], r["code"])
        if rr:
            created.append((r["code"], sq[a]["name"], sq[b]["name"]))
    if not created:
        return None, "Rooms create అవ్వలేదు (leaders already rooms లో ఉన్నారా?)."
    d = _load()
    d["tournament"] = {"ts": _now().isoformat(), "round": 1, "rooms": [c for c, _, _ in created]}
    _save(d)
    txt = "🏆 SQUAD TOURNAMENT — Round 1 bracket\n" + "\n".join(f"{c}: {a} ⚔️ {b}" for c, a, b in created) + \
          "\n\nRooms auto-start in 3 min. Winners advance!"
    return created, txt
