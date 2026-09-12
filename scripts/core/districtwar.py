"""
DISTRICT WARS — every day, every district, everyone can play.

Unlike exam rounds (TSPSC-only, SSC-only…) the War uses the COMMON SYLLABUS
that every state & central exam shares, so a Group-2 aspirant, a bank aspirant
and a constable aspirant from Warangal all fight for Warangal:

    mix per war (10 Q):  3 GK/Polity/History/Geo/Science  ·  3 Reasoning
                         2 Aptitude/Quant  ·  1 English  ·  1 Current Affairs
    (falls back gracefully if a bucket is short; never fewer than 8 Q)

Format (daily, 21:00 IST default — after both exam rounds)
  * 20:55  "⚔️ District War in 5 min" DM to every registered member (+ hub post)
  * 21:00  all registered members get the SAME 10 questions at the SAME time
           in DM (quiz polls, 45/60/75 s each, auto-close) — like a war room
  * 21:15  RESULT in the hub channel + DM:
        - District ranking by WAR SCORE = avg points per fighter × 10
                                          + participation bonus (≤10 fighters × 3)
          (so a small district with 6 sharp players beats a big lazy one)
        - Top fighter of each district (name), MVP of the war
        - Rivalry line: closest two districts
        - Season table (month): war wins, points; 🏆 District Champion at month end
  * Personal: +1/correct as usual, +speed bonus; district winners' fighters +10,
    war MVP +25; "🛡 Defender" badge for 5 wars in a row.

Questions come from Bank.pick() per subject bucket → the permanent no-repeat
store holds (war questions never return in exam rounds).
State: data/district_war.json  {season:{YYYYMM:{wars:{date:{...}}}}, polls:{}, live:{...}}
Advanced by bot loop tick() like the arena (no sleeps); engine only schedules.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "district_war.json"
WAR_Q = int(getattr(config, "WAR_QUESTIONS", 10) or 10)
MIX = (("gk", 3), ("reasoning", 3), ("quant", 2), ("english", 1), ("ca", 1))
Q_WINDOW = {"easy": 45, "medium": 60, "hard": 75}
GAP_SEC = 5
PTS_CORRECT, PTS_SPEED_MAX, PTS_WRONG = 10, 5, 0        # no negative in wars — everyone should play
WIN_BONUS, MVP_BONUS = 10, 25
DEFENDER_STREAK = 5


def _now():
    return datetime.now(config.IST)


def _load():
    return load_json(PATH, {"season": {}, "polls": {}, "live": None, "streaks": {}})


def _save(d):
    save_json_atomic(PATH, d)


# ------------------------------------------------------------ composition
def _subject(q):
    try:
        from .blueprint import subject_of
        return subject_of(q)
    except Exception:
        return "gk"


def _window(q):
    try:
        from .blueprint import difficulty_of
        return Q_WINDOW.get(difficulty_of(q), 60)
    except Exception:
        return 60


def compose(bank, n=WAR_Q):
    """Common-syllabus mix drawn across ALL channels via bank.pick (no-repeat)."""
    want = {}
    for s, k in MIX:
        want[s] = k
    chosen, seen = [], set()

    def take(subject, k, channels):
        got = 0
        for ch in channels:
            if got >= k:
                break
            try:
                pool = bank.unused(ch)
            except Exception:
                pool = []
            cands = [q for q in pool if q["id"] not in seen and
                     ((subject == "ca" and ch == "CURRENT") or (subject != "ca" and _subject(q) == subject))]
            if not cands:
                continue
            import random
            random.shuffle(cands)
            for q in cands[:k - got]:
                chosen.append(q); seen.add(q["id"]); got += 1
        return got

    order = ["SSC", "RAILWAY", "BANKING", "POLICE", "DEFENCE", "TSPSC", "APPSC", "CURRENT"]
    take("ca", want["ca"], ["CURRENT"])
    take("gk", want["gk"], ["TSPSC", "APPSC", "SSC", "RAILWAY", "POLICE", "CURRENT"])
    take("reasoning", want["reasoning"], order)
    take("quant", want["quant"], order)
    take("english", want["english"], ["SSC", "BANKING", "RAILWAY", "DEFENCE"])
    # top-up from anywhere
    if len(chosen) < n:
        for ch in order:
            if len(chosen) >= n:
                break
            try:
                for q in bank.unused(ch):
                    if q["id"] not in seen:
                        chosen.append(q); seen.add(q["id"])
                        if len(chosen) >= n:
                            break
            except Exception:
                pass
    chosen = chosen[:n]
    # mark as posted → permanent no-repeat
    by_ch = {}
    for q in chosen:
        by_ch.setdefault(q.get("channel", "CURRENT"), []).append(q)
    for ch, qs in by_ch.items():
        try:
            bank.mark_posted(ch, qs)
        except Exception:
            pass
    # order: easy → hard like a paper, but interleave subjects
    rank = {"easy": 0, "medium": 1, "hard": 2}
    try:
        from .blueprint import difficulty_of
        chosen.sort(key=lambda q: rank.get(difficulty_of(q), 1))
    except Exception:
        pass
    return chosen


# --------------------------------------------------------------- lifecycle
def start_war(bank, members, tg, now=None):
    """Create today's live war and send Q1 immediately. Returns (ok, info)."""
    now = now or _now()
    d = _load()
    day = now.strftime("%Y-%m-%d")
    if d.get("live") and d["live"].get("state") not in ("done",):
        return False, "war already live"
    if day in d["season"].get(now.strftime("%Y%m"), {}).get("wars", {}):
        return False, "war already fought today"
    qs = compose(bank)
    if len(qs) < 8:
        return False, f"not enough questions ({len(qs)})"
    fighters = {}
    for uid, m in members.members.items():
        if m.get("registered") and m.get("district") and not m.get("dm_blocked"):
            fighters[str(uid)] = {"district": m["district"], "pts": 0, "correct": 0, "answered": 0}
    if not fighters:
        return False, "no registered fighters"
    live = {"day": day, "state": "question", "qi": 0, "questions": [
        {"id": q["id"], "q_en": q.get("q_en", ""), "q_te": q.get("q_te", ""), "options_en": q.get("options_en", []),
         "options_te": q.get("options_te", []), "answer_index": int(q["answer_index"]), "window": _window(q),
         "subject": _subject(q), "channel": q.get("channel", "")} for q in qs],
        "fighters": fighters, "answers": {}, "q_open": None, "q_close": None}
    d["live"] = live
    d["polls"] = {}
    _save(d)
    _open_question(tg, d, 0, now)
    return True, {"fighters": len(fighters), "questions": len(qs)}


def _open_question(tg, d, qi, now):
    from .content import build_question_text, build_options
    live = d["live"]
    q = live["questions"][qi]
    live["qi"], live["state"] = qi, "question"
    live["q_open"] = now.isoformat()
    live["q_close"] = (now + timedelta(seconds=q["window"])).isoformat()
    live["answers"][str(qi)] = {}
    cfg = {"emoji": "⚔️", "subject": "District War"}
    subj = {"gk": "GK", "reasoning": "Reasoning", "quant": "Aptitude", "english": "English", "ca": "Current Affairs"}
    text = build_question_text(q, cfg, telugu_first=True,
                               position=f"⚔️ War {qi + 1}/{len(live['questions'])} · {subj.get(q['subject'], '')} · {q['window']}s")
    opts = build_options(q, telugu_first=True)
    sent = 0
    for u in list(live["fighters"].keys()):
        try:
            res = tg._call("sendPoll", {"chat_id": u, "question": text[:300],
                                        "options": [{"text": o} for o in opts], "type": "quiz",
                                        "is_anonymous": False, "correct_option_id": q["answer_index"],
                                        "open_period": max(5, min(600, q["window"]))})
            pid = (res.get("result", {}).get("poll") or {}).get("id")
            if pid:
                d["polls"][str(pid)] = [qi, u]
                sent += 1
        except Exception:
            live["fighters"][u]["blocked"] = True
        if sent % 25 == 0:
            import time
            time.sleep(0 if getattr(tg, "dry", False) else 1.0)
    _save(d)


def record_answer(poll_id, uid, chosen):
    """Bot hook → True if this poll was a war poll."""
    try:
        d = _load()
        meta = d["polls"].get(str(poll_id))
        if not meta:
            return False
        qi, owner = meta
        live = d.get("live")
        if not live or owner != str(uid) or live["state"] != "question" or live["qi"] != qi:
            return True
        ans = live["answers"].setdefault(str(qi), {})
        if str(uid) in ans:
            return True
        q = live["questions"][qi]
        f = live["fighters"].get(str(uid))
        if not f:
            return True
        elapsed = (_now() - datetime.fromisoformat(live["q_open"])).total_seconds()
        if int(chosen) == q["answer_index"]:
            pts = PTS_CORRECT + int(round(PTS_SPEED_MAX * max(0, 1 - elapsed / max(q["window"], 1))))
            f["correct"] += 1
        else:
            pts = PTS_WRONG
        f["pts"] += pts; f["answered"] += 1
        ans[str(uid)] = pts
        _save(d)
        return True
    except Exception as e:
        print(f"   [war] answer note: {e}")
        return False


def tick(tg, members, now=None):
    """Advance the live war (bot loop). Returns True while a war is live."""
    now = now or _now()
    try:
        d = _load()
        live = d.get("live")
        if not live or live["state"] == "done":
            return False
        if live["state"] == "question":
            all_in = len(live["answers"].get(str(live["qi"]), {})) >= sum(
                1 for f in live["fighters"].values() if not f.get("blocked"))
            if now >= datetime.fromisoformat(live["q_close"]) or all_in:
                live["state"] = "gap"
                live["q_open"] = (now + timedelta(seconds=GAP_SEC)).isoformat()
                _save(d)
        elif live["state"] == "gap":
            if now >= datetime.fromisoformat(live["q_open"]):
                nxt = live["qi"] + 1
                if nxt >= len(live["questions"]):
                    _finish(tg, members, d, now)
                    return False
                _open_question(tg, d, nxt, now)
        return True
    except Exception as e:
        print(f"   [war] tick note: {e}")
        return False


# ------------------------------------------------------------------ result
def district_table(live, members):
    agg = {}
    for uid, f in live["fighters"].items():
        if f["answered"] == 0:
            continue
        a = agg.setdefault(f["district"], {"pts": 0, "n": 0, "correct": 0, "top": (None, -1)})
        a["pts"] += f["pts"]; a["n"] += 1; a["correct"] += f["correct"]
        if f["pts"] > a["top"][1]:
            a["top"] = (uid, f["pts"])
    rows = []
    for dname, a in agg.items():
        avg = a["pts"] / a["n"]
        score = round(avg * 10 + min(a["n"], 10) * 3, 1)
        rows.append({"district": dname, "score": score, "avg": round(avg, 1), "n": a["n"],
                     "acc": round(100 * a["correct"] / max(a["n"] * len(live["questions"]), 1)),
                     "top_uid": a["top"][0], "top_pts": a["top"][1]})
    rows.sort(key=lambda r: (-r["score"], -r["n"]))
    return rows


def _finish(tg, members, d, now):
    live = d["live"]
    live["state"] = "done"
    rows = district_table(live, members)
    season = d["season"].setdefault(now.strftime("%Y%m"), {"wars": {}, "wins": {}, "points": {}})
    mvp = max(live["fighters"].items(), key=lambda kv: kv[1]["pts"])[0] if live["fighters"] else None
    if rows:
        winner = rows[0]["district"]
        season["wins"][winner] = season["wins"].get(winner, 0) + 1
        for i, r in enumerate(rows):
            season["points"][r["district"]] = season["points"].get(r["district"], 0) + max(0, 10 - i)
        # rewards
        for uid, f in live["fighters"].items():
            if f["answered"] == 0:
                d["streaks"][uid] = 0
                continue
            m = members._get(uid)
            bonus = WIN_BONUS if f["district"] == winner else 0
            if uid == mvp:
                bonus += MVP_BONUS
                m["war_mvp"] = m.get("war_mvp", 0) + 1
            m["points"] = m.get("points", 0) + bonus
            m["wars"] = m.get("wars", 0) + 1
            d["streaks"][uid] = d["streaks"].get(uid, 0) + 1
            if d["streaks"][uid] >= DEFENDER_STREAK and "defender" not in m.setdefault("badges", []):
                m["badges"].append("defender")
        members.kv.save()
    season["wars"][live["day"]] = {"rows": rows[:15], "mvp": mvp, "fighters": sum(1 for f in live["fighters"].values() if f["answered"])}
    d["live"] = live
    d["polls"] = {}
    _save(d)
    text = render_result(live, rows, members, mvp, season, now)
    # DM everyone who fought + personal line
    for uid, f in live["fighters"].items():
        if f["answered"] == 0 or f.get("blocked"):
            continue
        my = next((i for i, r in enumerate(rows, 1) if r["district"] == f["district"]), None)
        me = f"\n\n🫵 మీరు: {f['pts']} pts · {f['correct']}/{len(live['questions'])} ✅ · మీ జిల్లా #{my}"
        try:
            tg.send_message(uid, text + me)
        except Exception:
            pass
    d["_channel_post"] = text
    _save(d)


def render_result(live, rows, members, mvp, season, now):
    from . import districts as D
    n_q = len(live["questions"])
    fighters = sum(1 for f in live["fighters"].values() if f["answered"])
    lines = [f"⚔️ DISTRICT WAR — {now.strftime('%d %b')} · RESULT", f"👥 {fighters} fighters · {n_q} Q · అన్ని exams common syllabus", ""]
    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 16)]
    for i, r in enumerate(rows[:10]):
        top = members.members.get(r["top_uid"]) or {}
        lines.append(f"{medals[i]} {r['district']} ({D.telugu_name(r['district'])}) — {r['score']:g} · "
                     f"{r['n']}👥 avg {r['avg']} · ⭐ {top.get('name', '')[:14]} {r['top_pts']}")
    if len(rows) >= 2 and rows[0]["score"] - rows[1]["score"] <= 15:
        lines.append(f"⚡ Rivalry: {rows[0]['district']} vs {rows[1]['district']} — {rows[0]['score'] - rows[1]['score']:g} pts తేడా!")
    if mvp:
        m = members.members.get(mvp) or {}
        lines += ["", f"🏅 War MVP: {m.get('name', '')} · {m.get('district', '')} — {live['fighters'][mvp]['pts']} pts (+{MVP_BONUS})"]
    if rows:
        lines.append(f"🎁 {rows[0]['district']} fighters +{WIN_BONUS} pts each")
    wins = sorted(season["wins"].items(), key=lambda kv: -kv[1])[:5]
    if wins:
        lines += ["", "🏆 Season (this month): " + " · ".join(f"{d} {n}W" for d, n in wins)]
    lines += ["", "Formula: avg pts per fighter ×10 + fighters (max 10) ×3 — చిన్న జిల్లా కూడా గెలవగలదు",
              "రేపు మళ్ళీ 9 PM ⚔️ మీ జిల్లా కోసం friends ని పిలవండి → /invite"]
    return "\n".join(lines)


def pop_channel_post():
    d = _load()
    t = d.pop("_channel_post", None)
    if t:
        _save(d)
    return t


def alert_text(minutes: int) -> str:
    t = getattr(config, "WAR_TIME", "21:00")
    return ("⚔️ DISTRICT WAR — " + (f"{minutes} నిమిషాల్లో ({t})" if minutes > 1 else "1 నిమిషంలో!") + "\n"
            f"{WAR_Q} Q · GK · Reasoning · Aptitude · English · CA — అన్ని exams వాళ్ళకీ\n"
            "మీ జిల్లా కోసం పోరాడండి — ప్రశ్నలు ఇక్కడే వస్తాయి. Ready 🔥")


def season_table(now=None):
    from . import districts as D
    now = now or _now()
    d = _load()
    s = d["season"].get(now.strftime("%Y%m"))
    if not s or not s.get("points"):
        return ""
    rows = sorted(s["points"].items(), key=lambda kv: -kv[1])[:10]
    lines = [f"⚔️ DISTRICT WAR — {now.strftime('%B')} season table", ""]
    for i, (dn, p) in enumerate(rows, 1):
        lines.append(f"{i}. {dn} ({D.telugu_name(dn)}) — {p} pts · {s['wins'].get(dn, 0)} wins")
    lines += ["", f"{len(s['wars'])} wars fought · నెల చివర 🏆 District Champion"]
    return "\n".join(lines)


def my_war(members, uid):
    d = _load()
    m = members.members.get(str(uid)) or {}
    t = getattr(config, "WAR_TIME", "21:00")
    lines = ["⚔️ DISTRICT WARS — రోజూ " + t, "అన్ని exams common syllabus: GK · Reasoning · Aptitude · English · CA", ""]
    if not m.get("registered"):
        lines.append("Register అయితే automatic గా మీ జిల్లా fighter — /start")
    else:
        lines.append(f"మీ జిల్లా: {m.get('district', '—')} · wars fought {m.get('wars', 0)} · MVP {m.get('war_mvp', 0)} · streak {d['streaks'].get(str(uid), 0)}")
        lines.append("ప్రశ్నలు ఈ chat లోనే వస్తాయి — ఏమీ చేయనవసరం లేదు, 9 PM కి ready ఉండండి.")
    st = season_table()
    if st:
        lines += ["", st]
    return "\n".join(lines)
