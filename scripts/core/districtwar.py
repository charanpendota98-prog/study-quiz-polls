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
import urllib.parse

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "district_war.json"
WAR_Q = int(getattr(config, "WAR_QUESTIONS", 10) or 10)
MIX = (("gk", 3), ("reasoning", 3), ("quant", 2), ("english", 1), ("ca", 1))
Q_WINDOW = {"easy": 45, "medium": 60, "hard": 75}
GAP_SEC = 5
PTS_CORRECT, PTS_SPEED_MAX, PTS_WRONG = 10, 5, 0        # no negative in wars — everyone should play
WIN_BONUS, MVP_BONUS, SQUAD_WIN_BONUS, STATE_WIN_BONUS = 10, 25, 15, 10
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
# ------------------------------------------------------------- squads & ranks
WAR_TIERS = [(0, "🪖 Recruit"), (150, "⚔️ Fighter"), (400, "🛡 Warrior"), (800, "🔥 Veteran"),
             (1500, "👑 Warlord"), (3000, "🐉 Legend")]
KILL_STREAK = {3: (5, "🔥 3-streak"), 5: (10, "💥 5-streak"), 8: (20, "☄️ 8-streak"), 10: (40, "🐉 FLAWLESS")}


def _squad_of(uid):
    try:
        from .hooks import _sq
        data = _sq()
        code = data["by_uid"].get(str(uid))
        if code and code in data["squads"]:
            return {"code": code, "name": data["squads"][code]["name"][:16]}
    except Exception:
        pass
    return None


def war_tier(d, uid):
    """Lifetime war points → PUBG-like rank title."""
    wp = d.setdefault("war_points", {}).get(str(uid), 0)
    title = WAR_TIERS[0][1]
    for th, t in WAR_TIERS:
        if wp >= th:
            title = t
    return title


def tier_progress(d, uid):
    wp = d.get("war_points", {}).get(str(uid), 0)
    nxt = next(((th, t) for th, t in WAR_TIERS if th > wp), None)
    return wp, nxt


def state_table(live, members):
    """TS vs AP — avg pts per fighter ×10 + participation (max 50) ×1."""
    agg = {}
    from . import districts as D
    for uid, f in live["fighters"].items():
        if f["answered"] == 0:
            continue
        st = (members.members.get(uid) or {}).get("state_code") or (D.state_of(f["district"]) or "AP")
        a = agg.setdefault(st, {"pts": 0, "n": 0, "correct": 0, "top": ("", -1)})
        a["pts"] += f["pts"]; a["n"] += 1; a["correct"] += f["correct"]
        if f["pts"] > a["top"][1]:
            a["top"] = (uid, f["pts"])
    rows = []
    for st, a in agg.items():
        rows.append({"state": st, "name": D.STATES[st][0], "score": round(a["pts"] / a["n"] * 10 + min(a["n"], 50), 1),
                     "avg": round(a["pts"] / a["n"], 1), "n": a["n"],
                     "acc": round(100 * a["correct"] / max(a["n"] * len(live["questions"]), 1)), "top": a["top"]})
    rows.sort(key=lambda r: -r["score"])
    return rows


def squad_table(live):
    """Squads with ≥2 fighters who answered; score = sum of pts (squads are same-size-capped at 5)."""
    agg = {}
    for uid, f in live["fighters"].items():
        sq = f.get("squad")
        if not sq or f["answered"] == 0:
            continue
        a = agg.setdefault(sq["code"], {"name": sq["name"], "district": f["district"], "pts": 0, "n": 0, "correct": 0, "top": ("", -1)})
        a["pts"] += f["pts"]; a["n"] += 1; a["correct"] += f["correct"]
        if f["pts"] > a["top"][1]:
            a["top"] = (uid, f["pts"])
    rows = [{"code": c, **a} for c, a in agg.items() if a["n"] >= 2]
    rows.sort(key=lambda r: (-r["pts"], -r["correct"]))
    return rows


def start_war(bank, members, tg, now=None):
    """Create today's live war and send Q1 immediately. Returns (ok, info)."""
    now = now or _now()
    d = _load()
    day = now.strftime("%Y-%m-%d")
    if d.get("live") and d["live"].get("state") not in ("done",):
        return False, "war already live"
    # Allow admin on-demand and recurring wars seamlessly
    qs = compose(bank)
    if len(qs) < 8:
        return False, f"not enough questions ({len(qs)})"
    lb = d.get("lobby") or {}
    fighters = {}
    if lb.get("day") == day:
        for uid, v in lb.get("joined", {}).items():
            m = members.members.get(str(uid)) or {}
            if m.get("registered") and m.get("district") and not m.get("dm_blocked"):
                fighters[str(uid)] = {"district": m["district"], "pts": 0, "correct": 0, "answered": 0,
                                      "squad": _squad_of(uid), "streak": 0, "best_streak": 0, "tier": war_tier(d, uid)}
    if len(fighters) < 2:
        d["lobby"] = {**lb, "open": False}
        _save(d)
        return False, f"only {len(fighters)} fighters opted in"
    d["lobby"] = {**lb, "open": False, "locked": now.isoformat()}     # 🔒 no entry after start
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
            f["streak"] = f.get("streak", 0) + 1
            f["best_streak"] = max(f.get("best_streak", 0), f["streak"])
            ks = KILL_STREAK.get(f["streak"])
            if ks:
                pts += ks[0]
                f.setdefault("streak_bonus", []).append(ks[1])
        else:
            pts = PTS_WRONG
            f["streak"] = 0
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
                # live board at Q3, Q6 and before the last Q (not every Q → no spam)
                qi = live["qi"]; n_q = len(live["questions"])
                if qi + 1 in (3, 6) or qi + 1 == n_q - 1:
                    _broadcast_board(tg, members, live, qi)
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


def _broadcast_board(tg, members, live, qi):
    rows = district_table(live, members)
    if not rows:
        return
    n_q = len(live["questions"])
    top = rows[:5]
    lead = top[0]
    lines = [f"📊 LIVE after Q{qi + 1}/{n_q}", ""]
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    for i, r in enumerate(top):
        bar = "█" * max(1, int(10 * r["score"] / max(lead["score"], 1)))
        lines.append(f"{medals[i]} {r['district'][:12]:<12} {bar} {r['score']:g}")
    if len(rows) >= 2 and rows[0]["score"] - rows[1]["score"] <= 15:
        lines.append(f"⚡ {rows[0]['district']} vs {rows[1]['district']} — neck and neck!")
    sq = squad_table(live)[:3]
    if sq:
        lines.append("👥 Squads: " + " · ".join(f"{r['name']} {r['pts']}" for r in sq))
    # personal line per fighter
    for uid, f in live["fighters"].items():
        if f.get("blocked") or f["answered"] == 0:
            continue
        my = next((i for i, r in enumerate(rows, 1) if r["district"] == f["district"]), None)
        dist_rank = sorted((x["pts"] for x in live["fighters"].values() if x["district"] == f["district"]), reverse=True)
        my_in_d = dist_rank.index(f["pts"]) + 1 if f["pts"] in dist_rank else None
        me = f"\n🫵 మీరు {f['pts']} pts · {f['district']} #{my} · జిల్లాలో మీరు #{my_in_d}" + (f" · 🔥{f['streak']} streak" if f.get("streak", 0) >= 2 else "")
        try:
            tg.send_message(uid, "\n".join(lines) + me + f"\n⏭ Q{qi + 2} వస్తోంది…")
        except Exception:
            pass


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


def district_heroes(live, members, per=2):
    """Top fighters of EVERY district (not just the winner's) — the 'top-2
    list from each district' that makes every district see its own people.
    Returns [(district, [(uid, fighter), ...]), ...] ordered like district_table."""
    by_d = {}
    for uid, f in live.get("fighters", {}).items():
        if f.get("answered", 0) == 0 or not f.get("district"):
            continue
        by_d.setdefault(f["district"], []).append((str(uid), f))
    order = {r["district"]: i for i, r in enumerate(district_table(live, members))}
    out = []
    for dname, fs in sorted(by_d.items(), key=lambda kv: order.get(kv[0], 999)):
        fs.sort(key=lambda x: (-x[1].get("pts", 0), -x[1].get("correct", 0)))
        out.append((dname, fs[:per]))
    return out


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
    # lifetime war points → rank tiers (PUBG-style), squads table
    wp = d.setdefault("war_points", {})
    tier_ups = []
    for uid, f in live["fighters"].items():
        if f["answered"] == 0:
            continue
        before = war_tier(d, uid)
        wp[uid] = wp.get(uid, 0) + f["pts"] + (WIN_BONUS if rows and f["district"] == rows[0]["district"] else 0)
        after = war_tier(d, uid)
        f["tier"] = after
        if after != before:
            tier_ups.append((uid, after))
    live["tier_ups"] = tier_ups
    sq_rows = squad_table(live)
    live["squad_rows"] = sq_rows[:10]
    st_rows = state_table(live, members)
    live["state_rows"] = st_rows
    if now.weekday() == 5 and len(st_rows) == 2:                   # Saturday = STATE WAR night: TS vs AP bonus
        sw = season.setdefault("state_wins", {})
        sw[st_rows[0]["state"]] = sw.get(st_rows[0]["state"], 0) + 1
        for uid, f in live["fighters"].items():
            if f["answered"] and ((members.members.get(uid) or {}).get("state_code") == st_rows[0]["state"]):
                m = members._get(uid); m["points"] = m.get("points", 0) + STATE_WIN_BONUS
        members.kv.save()
    if sq_rows:
        ws = season.setdefault("squad_wins", {})
        ws[sq_rows[0]["code"]] = ws.get(sq_rows[0]["code"], 0) + 1
        for uid, f in live["fighters"].items():
            if f.get("squad") and f["squad"]["code"] == sq_rows[0]["code"] and f["answered"]:
                m = members._get(uid); m["points"] = m.get("points", 0) + SQUAD_WIN_BONUS
        members.kv.save()
    war_key = live["day"] if live["day"] not in season["wars"] else f"{live['day']}#{len(season['wars']) + 1}"
    season["wars"][war_key] = {"rows": rows[:15], "mvp": mvp, "fighters": sum(1 for f in live["fighters"].values() if f["answered"]),
                                   "squads": sq_rows[:5]}
    d["live"] = live
    d["polls"] = {}
    _save(d)
    try:
        from . import tournament
        for i, r in enumerate(rows):
            is_winner = (i == 0)
            tournament.record_district_war_stats(r["district"], r.get("score", 0.0), win=is_winner, now=now)
    except Exception as e:
        print(f"   [districtwar] stats record note: {e}")
    try:  # 📊 record the war in the Google Sheet ('rounds' tab, channel=WAR)
        from . import crm
        if crm.sheet_enabled():
            hrows = []
            for dname, hs in district_heroes(live, members, per=2):
                for uid, f in hs:
                    mm = members.members.get(uid) or {}
                    hrows.append({"uid": uid, "name": mm.get("name") or "", "district": dname,
                                  "correct": f.get("correct", 0), "total": len(live["questions"]),
                                  "points": f.get("pts", 0)})
            if hrows:
                crm.push_round_top(live["day"], "WAR", hrows)
    except Exception as e:
        print(f"   [war] sheet note: {e}")
    text = render_result(live, rows, members, mvp, season, now)
    # DM everyone who fought + personal line
    for uid, f in live["fighters"].items():
        if f["answered"] == 0 or f.get("blocked"):
            continue
        my = next((i for i, r in enumerate(rows, 1) if r["district"] == f["district"]), None)
        allf = sorted((x["pts"] for x in live["fighters"].values() if x["answered"]), reverse=True)
        my_rank = allf.index(f["pts"]) + 1
        wpts, nxt = tier_progress(d, uid)
        me = (f"\n\n🫵 మీరు: {f['pts']} pts · {f['correct']}/{len(live['questions'])} ✅ · overall #{my_rank}/{len(allf)} · మీ జిల్లా #{my}"
              f"\n🎖 Rank: {f.get('tier', '')} · war points {wpts}" + (f" · next {nxt[1]} at {nxt[0]}" if nxt else " · MAX")
              + (f"\n🔥 Best streak {f.get('best_streak', 0)} " + " ".join(f.get("streak_bonus", [])) if f.get("best_streak", 0) >= 3 else ""))
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
    lead = rows[0]["score"] if rows else 1
    for i, r in enumerate(rows[:10]):
        top = members.members.get(r["top_uid"]) or {}
        bar = "█" * max(1, int(8 * r["score"] / max(lead, 1)))
        lines.append(f"{medals[i]} {r['district']} ({D.telugu_name(r['district'])}) {bar} {r['score']:g}")
        lines.append(f"      {r['n']}👥 · avg {r['avg']} · 🎯{r['acc']}% · ⭐ {top.get('name', '')[:14]} {r['top_pts']}")
    # top-5 fighters overall (names + districts — the attraction)
    best = sorted(((uid, f) for uid, f in live["fighters"].items() if f["answered"]), key=lambda kv: -kv[1]["pts"])[:5]
    if best:
        lines += ["", "🔥 Top fighters:"]
        for j, (uid, f) in enumerate(best, 1):
            mm = members.members.get(uid) or {}
            lines.append(f"  {j}. {mm.get('name', '')[:16]} · {f['district']} — {f['pts']} pts ({f['correct']}/{n_q})")
    # 🏅 every district sees its own TOP-2 (names from that district only)
    heroes = district_heroes(live, members, per=2)
    if heroes:
        lines += ["", "🏅 జిల్లా హీరోలు — ప్రతి జిల్లా టాప్-2 / each district's TOP-2:"]
        for dname, hs in heroes[:10]:
            parts = []
            for i, (uid, f) in enumerate(hs, 1):
                mm = members.members.get(uid) or {}
                parts.append(f"{i}. {(mm.get('name') or 'Player')[:14]} {f['pts']}pts {f['correct']}✅")
            lines.append(f"  {dname}: " + " · ".join(parts))
        if len(heroes) > 10:
            lines.append(f"  … +{len(heroes) - 10} more districts")
    st = live.get("state_rows") or []
    if len(st) == 2:
        a, b = st
        tot = a["score"] + b["score"]
        la = max(1, int(round(12 * a["score"] / tot)))
        sat = now.weekday() == 5
        lines += ["", ("🏛 STATE WAR NIGHT — " if sat else "🏛 ") + f"{a['name']} vs {b['name']}",
                  f"   {a['state']} {'█' * la}{'░' * (12 - la)} {b['state']}   {a['score']:g} : {b['score']:g}",
                  f"   {a['state']}: {a['n']}👥 · avg {a['avg']} · 🎯{a['acc']}%   |   {b['state']}: {b['n']}👥 · avg {b['avg']} · 🎯{b['acc']}%"]
        if sat:
            lines.append(f"   🎁 {a['name']} fighters +{STATE_WIN_BONUS} each · season: " + " · ".join(f"{k} {v}W" for k, v in season.get("state_wins", {}).items()))
    sq = live.get("squad_rows") or []
    if sq:
        lines += ["", "👥 SQUAD BATTLE (same war, squads scored together):"]
        for j, r in enumerate(sq[:5], 1):
            lines.append(f"  {'🥇🥈🥉'[j-1] if j <= 3 else str(j)+'.'} {r['name']} · {r['district']} — {r['pts']} pts · {r['n']}👤 · {r['correct']}✅")
        lines.append(f"  🎁 {sq[0]['name']} members +{SQUAD_WIN_BONUS} each · squad లేదా? bot లో /squad create")
    ups = live.get("tier_ups") or []
    if ups:
        names = []
        for uid, t in ups[:6]:
            mm = members.members.get(uid) or {}
            names.append(f"{mm.get('name', '')[:12]} → {t}")
        lines += ["", "🎖 RANK UP: " + " · ".join(names)]
    streaks = sorted(((f.get("best_streak", 0), uid) for uid, f in live["fighters"].items() if f.get("best_streak", 0) >= 5), reverse=True)[:3]
    if streaks:
        lines.append("🔥 Streaks: " + " · ".join(f"{(members.members.get(u) or {}).get('name', '')[:12]} {n}🔥" for n, u in streaks))
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
              "Fighter: ✅ +10 + speed ≤5 · streak 3/5/8/10 → +5/+10/+20/+40 · ranks 🪖→⚔️→🛡→🔥→👑→🐉",
              "రేపు మళ్ళీ 9 PM ⚔️ మీ జిల్లా కోసం friends ని పిలవండి → /invite"]
    return "\n".join(lines)


def pop_channel_post():
    d = _load()
    t = d.pop("_channel_post", None)
    if t:
        _save(d)
    return t


# ------------------------------------------------------------ opt-in lobby
def open_lobby(now=None):
    """Called at T-5: today's lobby opens; only people who tap ⚔️ get in."""
    now = now or _now()
    d = _load()
    d["lobby"] = {"day": now.strftime("%Y-%m-%d"), "open": True, "joined": {}, "opened": now.isoformat()}
    _save(d)


def lobby_join(members, uid, via_squad=False):
    """Button/command → (ok, text). Squad leaders bring the whole squad."""
    d = _load()
    lb = d.get("lobby")
    if not lb or not lb.get("open"):
        return False, "⌛ War lobby ఇప్పుడు open లో లేదు — రోజూ 8:55 PM కి 'I want to play' button వస్తుంది."
    m = members.members.get(str(uid)) or {}
    if not m.get("registered") or not m.get("district"):
        return False, "ముందు register అవ్వండి (జిల్లా కావాలి) — /start"
    added = []
    if str(uid) not in lb["joined"]:
        lb["joined"][str(uid)] = {"district": m["district"], "t": _now().isoformat()}
        added.append(str(uid))
    if via_squad:
        try:
            from . import hooks
            sq = hooks._sq()
            code = sq["by_uid"].get(str(uid))
            if code and sq["squads"][code]["leader"] == str(uid):
                for u in sq["squads"][code]["members"]:
                    mm = members.members.get(u) or {}
                    if u not in lb["joined"] and mm.get("registered") and mm.get("district"):
                        lb["joined"][u] = {"district": mm["district"], "t": _now().isoformat(), "by": str(uid)}
                        added.append(u)
        except Exception:
            pass
    _save(d)
    n = len(lb["joined"])
    by_d = {}
    for v in lb["joined"].values():
        by_d[v["district"]] = by_d.get(v["district"], 0) + 1
    mine = by_d.get(m["district"], 0)
    top = sorted(by_d.items(), key=lambda kv: -kv[1])[:3]
    return True, (f"✅ మీరు ఈరోజు War లో ఉన్నారు — {m['district']} fighter #{mine}\n"
                  f"👥 Lobby: {n} fighters · " + " · ".join(f"{k} {v}" for k, v in top) + "\n"
                  + (f"👥 Squad తో {len(added)} మంది join అయ్యారు\n" if via_squad and len(added) > 1 else "")
                  + (f"ప్రశ్నలు {lb.get('start_at', '')[11:16]} కి ఇక్కడే వస్తాయి! Start అయ్యాక entry లేదు 🔒" if lb.get('start_at') else "9:00 PM కి ప్రశ్నలు ఇక్కడే. Start అయ్యాక entry లేదు 🔒"))


def channel_buttons():
    """Channel post button → bot deep link (channels can't use callback buttons for DMs)."""
    try:
        from . import gate
        link = gate.bot_link("war")
    except Exception:
        link = ""
    return [[("⚔️ I want to play — join War", f"url:{link}")]] if link else None


def channel_alert_text(minutes: int) -> str:
    return alert_text(minutes) + "\n\n📣 Button నొక్కి bot లో join అవ్వండి (register ఒక్కసారి). ప్రశ్నలు bot DM లో వస్తాయి, result ఇక్కడ 🏆"


def manual_launch(members, tg, bank=None, minutes=5, now=None, force=False):
    """Owner: /war now [minutes] [force] → lobby opens NOW, alerts everywhere, war auto-starts in `minutes`
    (bot loop tick() fires start_war when lobby.start_at passes). Supports any time / random hours!"""
    now = now or _now()
    d = _load()
    day = now.strftime("%Y-%m-%d")
    if d.get("live") and d["live"].get("state") != "done":
        return False, "⚔️ War already LIVE."
    if not force and day in d["season"].get(now.strftime("%Y%m"), {}).get("wars", {}):
        # Admin can launch any time on-demand, or re-launch anytime with force!
        pass
    if bank is not None and len(compose(bank)) < 8:
        return False, "❌ war ki questions చాలవు (bank check /pyq)."
    open_lobby(now)
    d = _load()
    d["lobby"]["start_at"] = (now + timedelta(minutes=minutes)).isoformat()
    d["lobby"]["manual"] = True
    _save(d)
    txt = alert_text(minutes)
    btn = lobby_buttons(minutes)
    n = 0
    for uid, m in members.members.items():
        if m.get("registered") and m.get("district") and not m.get("dm_blocked"):
            try:
                tg.send_message(uid, txt, buttons=btn); n += 1
            except Exception:
                m["dm_blocked"] = True
            if n % 25 == 0:
                tg.polite_gap(True)
    posted = 0
    for ch in getattr(config, "WAR_CHANNELS", None) or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
        try:
            tg.send_message(config.channel_chat_id(ch), channel_alert_text(minutes), buttons=channel_buttons()); posted += 1
        except Exception:
            pass
    try:
        members.kv.save()
    except Exception:
        pass
    return True, (f"⚔️ WAR LAUNCHED — start at {(now + timedelta(minutes=minutes)).strftime('%H:%M')}\n"
                  f"📨 {n} fighters alerted · 📣 {posted} channels posted\n"
                  f"Lobby open → auto-start in {minutes} min (≥2 fighters కావాలి). Status: /war status")


def maybe_auto_start(bank, members, tg, now=None):
    """Called from bot tick: manual launch whose start_at has passed → start_war."""
    now = now or _now()
    try:
        d = _load()
        lb = d.get("lobby") or {}
        sa = lb.get("start_at")
        if not sa or not lb.get("open") or (d.get("live") and d["live"].get("state") != "done"):
            return False
        if now < datetime.fromisoformat(sa):
            return False
        ok, info = start_war(bank, members, tg, now)
        d = _load(); d["lobby"].pop("start_at", None); d["lobby"]["open"] = False; _save(d)
        if not ok:
            try:
                tg.admin_notify(f"District War (manual) not started: {info}")
            except Exception:
                pass
        return ok
    except Exception as e:
        print(f"   [war] auto-start note: {e}")
        return False


def owner_status(members) -> str:
    d = _load()
    st = lobby_status()
    live = d.get("live") or {}
    t = getattr(config, "WAR_TIME", "21:00")
    lines = ["⚔️ DISTRICT WAR — owner status",
             f"🕘 Daily auto: {t} (alerts {t[:-2]}55 / T-1 · start · result ~+18 min) — .env WAR_TIME",
             f"📣 Channels: {', '.join(getattr(config, 'WAR_CHANNELS', []) or ['CURRENT'])}"]
    if live and live.get("state") != "done":
        lines.append(f"🔴 LIVE now: Q{live.get('qi', 0) + 1}/{len(live.get('questions', []))} · {len(live.get('fighters', {}))} fighters")
    elif st["open"]:
        lb = d.get("lobby") or {}
        when = lb.get("start_at", "")[11:16] if lb.get("start_at") else t
        lines.append(f"🟢 Lobby OPEN → start {when} · {st['n']} in · " + " · ".join(f"{k} {v}" for k, v in sorted(st['by_district'].items(), key=lambda kv: -kv[1])[:5]))
    else:
        lines.append("⚪ No lobby open now")
    wars = d["season"].get(_now().strftime("%Y%m"), {}).get("wars", {})
    lines.append(f"📅 This month: {len(wars)} wars fought")
    lines.append("\nManual: /war now (5 min) · /war now 10 · /war status")
    return "\n".join(lines)


def lobby_status():
    d = _load()
    lb = d.get("lobby") or {}
    by_d = {}
    for v in lb.get("joined", {}).values():
        by_d[v["district"]] = by_d.get(v["district"], 0) + 1
    return {"open": bool(lb.get("open")), "n": len(lb.get("joined", {})), "by_district": by_d}


def lobby_buttons(minutes):
    bot = getattr(config, "BOT_USERNAME", "") or "StudentUpBot"
    join_link = f"https://t.me/{bot}?start=war"
    wa_msg = (
        f"⚔️ *TELANGANA & AP DISTRICT WAR CALL!* ⚔️\n"
        f"మన జిల్లా పరువు కోసం యుద్ధం మొదలవుతోంది! ({minutes} నిమిషాల్లో start)\n"
        f"👉 Join War Now: {join_link}\n"
        f"మీ జిల్లాని టాప్ లో నిలబెట్టండి! 🔥"
    )
    wa_url = f"https://api.whatsapp.com/send?text={urllib.parse.quote(wa_msg)}"
    return [
        [("⚔️ I want to play — నేను ఆడతాను", "war:join")],
        [("📲 WhatsApp లో ఫ్రెండ్స్‌ని పిలవండి", f"url:{wa_url}")],
        [("👥 Squad మొత్తం join", "war:squad"), ("📊 Top Districts (వారపు/నెల)", "war:ranks")]
    ]


def alert_text(minutes: int) -> str:
    t = getattr(config, "WAR_TIME", "21:00")
    st = lobby_status()
    top = sorted(st["by_district"].items(), key=lambda kv: -kv[1])[:4]
    live = (f"👥 {st['n']} fighters already in · " + " · ".join(f"{k} {v}" for k, v in top)) if st["n"] else "మొదటి fighter మీరే అవ్వండి!"
    return ("⚔️ DISTRICT WAR — " + (f"{minutes} నిమిషాల్లో ({t})" if minutes > 1 else "1 నిమిషంలో — చివరి అవకాశం!") + "\n"
            f"{WAR_Q} Q · GK · Reasoning · Aptitude · English · CA — అన్ని exams వాళ్ళకీ\n"
            f"{live}\n"
            "👇 Button నొక్కితేనే మీకు ప్రశ్నలు వస్తాయి. Start అయ్యాక entry లేదు 🔒")


def season_table(now=None):
    from . import districts as D
    now = now or _now()
    d = _load()
    s = d["season"].get(now.strftime("%Y%m"))
    sections = []
    if s and s.get("points"):
        rows = sorted(s["points"].items(), key=lambda kv: -kv[1])[:10]
        lines = [f"⚔️ DISTRICT WAR — {now.strftime('%B')} season table", ""]
        for i, (dn, p) in enumerate(rows, 1):
            lines.append(f"{i}. {dn} ({D.telugu_name(dn)}) — {p} pts · {s['wins'].get(dn, 0)} wins")
        lines += ["", f"{len(s['wars'])} wars fought · నెల చివర 🏆 District Champion"]
        sections.append("\n".join(lines))
    
    # Also attach Weekly & Monthly Leaderboards from tournament engine
    try:
        from . import tournament
        t_board = tournament.render_district_war_leaderboards(period="both", now=now)
        if t_board.strip():
            sections.append(t_board.strip())
    except Exception:
        pass

    return "\n\n".join(sections) if sections else "⚔️ District War సీజన్ ప్రారంభమైంది! రోజూ 9 PM కి పాల్గొనండి." 


def war_rank_text(uid):
    d = _load()
    wp, nxt = tier_progress(d, uid)
    t = war_tier(d, uid)
    board = sorted(d.get("war_points", {}).items(), key=lambda kv: -kv[1])
    pos = next((i for i, (u, _) in enumerate(board, 1) if u == str(uid)), None)
    return (f"🎖 మీ War Rank: {t} · {wp} war points" + (f" · next {nxt[1]} at {nxt[0]} (ఇంకా {nxt[0] - wp})" if nxt else " · MAX 🐉")
            + (f"\n🌍 All-time war board: #{pos}/{len(board)}" if pos else "\nఇంకా war ఆడలేదు — 9 PM ⚔️"))


def war_leaderboard(members, limit=10):
    d = _load()
    board = sorted(d.get("war_points", {}).items(), key=lambda kv: -kv[1])[:limit]
    if not board:
        return "ఇంకా wars జరగలేదు."
    lines = ["🎖 WAR RANKS — all-time top fighters", ""]
    for i, (u, wp) in enumerate(board, 1):
        m = members.members.get(u) or {}
        lines.append(f"{'🥇🥈🥉'[i-1] if i <= 3 else str(i)+'.'} {m.get('name', '')[:16]} · {m.get('district', '')} — {wp} · {war_tier(d, u)}")
    return "\n".join(lines)


def my_war(members, uid):
    d = _load()
    m = members.members.get(str(uid)) or {}
    t = getattr(config, "WAR_TIME", "21:00")
    lines = ["⚔️ DISTRICT WARS — రోజూ " + t, "అన్ని exams common syllabus: GK · Reasoning · Aptitude · English · CA",
             "శనివారం 🏛 STATE WAR NIGHT: Telangana vs Andhra Pradesh (+10 winners)", ""]
    if not m.get("registered"):
        lines.append("Register అయితే automatic గా మీ జిల్లా fighter — /start")
    else:
        lines.append(f"మీ జిల్లా: {m.get('district', '—')} · wars fought {m.get('wars', 0)} · MVP {m.get('war_mvp', 0)} · streak {d['streaks'].get(str(uid), 0)}")
        lines.append("ప్రశ్నలు ఈ chat లోనే వస్తాయి — ఏమీ చేయనవసరం లేదు, 9 PM కి ready ఉండండి.")
    st = season_table()
    if st:
        lines += ["", st]
    return "\n".join(lines)
