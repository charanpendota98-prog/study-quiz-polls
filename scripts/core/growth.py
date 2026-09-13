"""
Growth & retention layer — three features that make people come back and
bring friends:

1. WEEKLY REPORT CARD (Sunday night DM to every active member)
   Subject-wise accuracy (GK / Reasoning / Quant / English), weak topics
   with a concrete "revise this" list, rounds played vs available, rank in
   district & overall, streak, points trend vs last week, and ONE goal for
   next week — like a coaching-institute progress report.

2. REFERRAL LEADERBOARD (Monday, with the District League)
   Top referrers of the week + all-time, tier badges (🥉3 · 🥈10 · 🥇25
   friends), and a district referral race. Referral counting already exists
   (members.add_referral, +20 pts); this only ranks and rewards.

3. BEAT THE TOPPER (weekday 13:00 DM challenge)
   Yesterday's evening-round topper's exact 5 questions are re-served to
   any member who taps "Challenge" — same questions, same 60–90 s pace,
   scored against the topper's time & score. Win = +15 pts and a 🥊 badge.
   The topper's questions are already posted publicly (so no leak) and are
   read from data/last_round.json / week log; never touches the no-repeat
   store (challenge questions are replays by design).

Every entry point is exception-safe and returns "" / 0 rather than raising.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

CHALLENGE_PATH = config.DATA / "challenges.json"
CHALLENGE_Q = 5
CHALLENGE_WIN_PTS = 15
REF_TIERS = ((25, "🥇 Ambassador"), (10, "🥈 Recruiter"), (3, "🥉 Connector"))


# ---------------------------------------------------------------- helpers
def _subject(topic: str, q_en: str = "") -> str:
    try:
        from .blueprint import subject_of
        return subject_of({"topic": topic, "q_en": q_en})
    except Exception:
        return "gk"


def _week_rounds(members, days=7, now=None):
    now = now or datetime.now(config.IST)
    since = (now - timedelta(days=days)).strftime("%Y%m%d")
    for rid, r in members.data.get("rounds", {}).items():
        if rid.lstrip("GM")[:8] >= since:
            yield rid, r


# ============================================================ 1. REPORT CARD
def weekly_report(members, uid, now=None) -> str:
    """Personal weekly report card text (empty if the member did not play)."""
    try:
        from . import districts as D
        now = now or datetime.now(config.IST)
        m = members.members.get(str(uid)) or {}
        if not m.get("registered"):
            return ""
        played, correct, total, ranks = 0, 0, 0, []
        available = 0
        for rid, r in _week_rounds(members, now=now):
            for ch, players in r.get("by_channel", {}).items():
                available += 1
                e = players.get(str(uid))
                if not e:
                    continue
                played += 1
                correct += e["correct"]; total += e["total"]
                order = sorted(players.values(), key=lambda x: (-x["correct"], x["total"]))
                ranks.append(1 + next(i for i, x in enumerate(order) if x is e))
        if not played:
            return ""
        acc = round(100 * correct / max(total, 1))
        # subject split from the topic stats (lifetime, but that's the study map)
        subj = {}
        for t, st in (m.get("topics") or {}).items():
            s = _subject(t)
            a = subj.setdefault(s, [0, 0])
            a[0] += st.get("correct", 0); a[1] += st.get("total", 0)
        weak = members.weak_topics(uid, limit=3) if hasattr(members, "weak_topics") else []
        weak_names = [w[0] if isinstance(w, (list, tuple)) else w for w in weak]
        # points trend
        pts = m.get("points", 0)
        last_pts = m.get("_pts_last_week", None)
        delta = f" (▲{pts - last_pts})" if last_pts is not None and pts >= last_pts else \
                (f" (▼{last_pts - pts})" if last_pts is not None else "")
        m["_pts_last_week"] = pts
        d = m.get("district", "")
        d_rank = ""
        if d and hasattr(members, "top_in_district"):
            rows = members.top_in_district(d, limit=1000)
            for i, (ruid, _mm) in enumerate(rows, 1):
                if str(ruid) == str(uid):
                    d_rank = f"#{i} in {d}"
                    break
        overall = members.rank(uid) if hasattr(members, "rank") else None
        best_rank = min(ranks) if ranks else None
        names = {"gk": "GK/Subject", "reasoning": "Reasoning", "quant": "Aptitude", "english": "English"}
        lines = [f"📋 Weekly Report Card — {m.get('name', 'Player')} · {now.strftime('%d %b')}",
                 f"📍 {d} ({D.telugu_name(d)})" if d else "", "",
                 f"🎯 Rounds: {played}/{available} · Accuracy {acc}% ({correct}/{total})",
                 f"🏅 Best round rank: #{best_rank}" + (f" · {d_rank}" if d_rank else "") +
                 (f" · overall #{overall}" if overall else ""),
                 f"⭐ Points: {pts}{delta} · 🔥 Streak {m.get('streak', 0)}d", ""]
        if subj:
            lines.append("📚 Subject-wise:")
            for s, (c, t) in sorted(subj.items(), key=lambda kv: kv[1][0] / max(kv[1][1], 1)):
                if t:
                    bar = "█" * int(10 * c / t) + "░" * (10 - int(10 * c / t))
                    lines.append(f"  {names.get(s, s):<11} {bar} {round(100 * c / t)}%")
            lines.append("")
        if weak_names:
            lines.append("⚠️ Revise this week / ఈ వారం revise: " + ", ".join(weak_names[:3]))
        # one concrete goal
        if played < available * 0.6:
            goal = f"రోజూ రెండు rounds ఆడండి — target {min(available, 14)} rounds"
        elif acc < 60:
            goal = "Accuracy 70%+ — guess తగ్గించండి, /review రోజూ చేయండి"
        elif best_rank and best_rank > 3:
            goal = "ఒక్క round లో అయినా Top-3 — Sunday Grand Test కి prepare అవ్వండి"
        else:
            goal = "Sunday Grand Test లో 🥇 — negative marking జాగ్రత్త"
        lines += [f"🎯 Next week goal: {goal}", "",
                  "/review — missed questions · /quiz — practice · /invite — +20 pts per friend"]
        try:
            members.kv.save()
        except Exception:
            pass
        return "\n".join(l for l in lines if l is not None)
    except Exception as e:
        print(f"   [report] {uid}: {e}")
        return ""


def active_members(members, now=None):
    seen = set()
    for _rid, r in _week_rounds(members, now=now):
        for players in r.get("by_channel", {}).values():
            seen.update(players.keys())
    return [u for u in seen if (members.members.get(str(u)) or {}).get("registered")
            and not (members.members.get(str(u)) or {}).get("dm_blocked")]


# ====================================================== 2. REFERRAL BOARD
def referral_board(members, limit=10, now=None) -> str:
    try:
        from . import districts as D
        now = now or datetime.now(config.IST)
        since = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        week, alltime, dist = {}, {}, {}
        for uid, m in members.members.items():
            if not m.get("registered"):
                continue
            ref = m.get("referred_by")
            if ref and (m.get("registered_at") or m.get("joined", ""))[:10] >= since:
                week[ref] = week.get(ref, 0) + 1
            n = m.get("referrals", 0)
            if n:
                alltime[uid] = n
                if m.get("district"):
                    dist[m["district"]] = dist.get(m["district"], 0) + n
        if not alltime and not week:
            return ""
        def nm(u):
            mm = members.members.get(str(u)) or {}
            d = mm.get("district", "")
            return f"{(mm.get('name') or 'Player')[:20]}" + (f" · {d}" if d else "")
        def tier(n):
            for k, t in REF_TIERS:
                if n >= k:
                    return t
            return ""
        lines = ["🤝 Referral Leaderboard — ఫ్రెండ్స్ తెచ్చినవారు", ""]
        if week:
            lines.append("📅 This week:")
            for i, (u, n) in enumerate(sorted(week.items(), key=lambda kv: -kv[1])[:5], 1):
                lines.append(f"  {i}. {nm(u)} — +{n}")
            lines.append("")
        lines.append("🏆 All-time:")
        medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, limit + 1)]
        for i, (u, n) in enumerate(sorted(alltime.items(), key=lambda kv: -kv[1])[:limit]):
            lines.append(f"  {medals[i]} {nm(u)} — {n} friends {tier(n)}")
        if dist:
            top = sorted(dist.items(), key=lambda kv: -kv[1])[:3]
            lines += ["", "📍 District race: " + " · ".join(f"{d} ({D.telugu_name(d)}) {n}" for d, n in top)]
        lines += ["", "Tiers: 🥉 3 · 🥈 10 · 🥇 25 friends · ప్రతి friend +20 pts",
                  "మీ link: bot లో /invite"]
        return "\n".join(lines)
    except Exception as e:
        print(f"   [referral] {e}")
        return ""


# ===================================================== 3. BEAT THE TOPPER
def _load_ch():
    return load_json(CHALLENGE_PATH, {"day": "", "topper": {}, "attempts": {}, "polls": {}})


def build_daily_challenge(members, bank, now=None):
    """Pick yesterday's evening-round topper (any channel with ≥3 players) and
    5 of that round's questions. Stored once per day."""
    try:
        now = now or datetime.now(config.IST)
        day = now.strftime("%Y-%m-%d")
        data = _load_ch()
        if data.get("day") == day and data.get("topper"):
            return data
        yday = (now - timedelta(days=1)).strftime("%Y%m%d")
        best = None
        for rid, r in members.data.get("rounds", {}).items():
            if not rid.startswith(yday):
                continue
            for ch, players in r.get("by_channel", {}).items():
                if len(players) < 3:
                    continue
                uid, e = max(players.items(), key=lambda kv: (kv[1]["correct"], -kv[1]["total"]))
                m = members.members.get(str(uid)) or {}
                if not m.get("registered") or e["correct"] < 5:
                    continue
                cand = (e["correct"], rid, ch, uid, e)
                if best is None or cand[0] > best[0]:
                    best = cand
        if not best:
            return None
        score, rid, ch, uid, e = best
        m = members.members[str(uid)]
        qids = [q for q in e.get("qids", []) if bank.by_id(q)][:CHALLENGE_Q]
        if len(qids) < 3:
            return None
        try:
            secs = (datetime.fromisoformat(e["last"]) - datetime.fromisoformat(e["first"])).total_seconds()
        except Exception:
            secs = 0
        data = {"day": day, "round_id": rid, "channel": ch,
                "topper": {"uid": str(uid), "name": m.get("name", "Topper"), "district": m.get("district", ""),
                           "score": e["correct"], "total": e["total"], "secs": int(secs)},
                "qids": qids, "attempts": {}, "polls": {}}
        save_json_atomic(CHALLENGE_PATH, data)
        return data
    except Exception as ex:
        print(f"   [challenge] build note: {ex}")
        return None


def challenge_invite_text(data) -> str:
    from . import districts as D
    t = data["topper"]
    d = f" ({t['district']} · {D.telugu_name(t['district'])})" if t.get("district") else ""
    mins = f"{t['secs'] // 60}m {t['secs'] % 60}s" if t.get("secs") else "—"
    return "\n".join([
        f"🥊 BEAT THE TOPPER — {config.CHANNELS.get(data['channel'], {}).get('subject', data['channel'])}",
        f"నిన్నటి topper: {t['name']}{d} — {t['score']}/{t['total']} in {mins}",
        f"అవే {len(data['qids'])} ప్రశ్నలు, same timer. వాళ్ళని beat చేయండి → +{CHALLENGE_WIN_PTS} pts + 🥊 badge",
        "Tap Challenge 👇  (one attempt per day)",
    ])


def start_attempt(uid, data) -> bool:
    """Register an attempt; False if already attempted today."""
    a = data.setdefault("attempts", {})
    if str(uid) in a:
        return False
    a[str(uid)] = {"correct": 0, "total": 0, "first": datetime.now(config.IST).isoformat(), "done": False}
    save_json_atomic(CHALLENGE_PATH, data)
    return True


def register_poll(data, poll_id, uid, qid, answer_index):
    data.setdefault("polls", {})[str(poll_id)] = [str(uid), qid, int(answer_index)]
    save_json_atomic(CHALLENGE_PATH, data)


def record_answer(members, poll_id, uid, chosen):
    """Returns (is_challenge, result_text_or_None)."""
    try:
        data = _load_ch()
        meta = data.get("polls", {}).get(str(poll_id))
        if not meta or meta[0] != str(uid):
            return False, None
        a = data["attempts"].get(str(uid))
        if not a or a.get("done"):
            return True, None
        correct = int(chosen) == int(meta[2])
        a["total"] += 1
        a["correct"] += 1 if correct else 0
        a["last"] = datetime.now(config.IST).isoformat()
        result = None
        if a["total"] >= len(data["qids"]):
            a["done"] = True
            t = data["topper"]
            secs = int((datetime.fromisoformat(a["last"]) - datetime.fromisoformat(a["first"])).total_seconds())
            t_score = t["score"] * len(data["qids"]) / max(t["total"], 1)   # scale topper to 5 Q
            won = a["correct"] > t_score or (abs(a["correct"] - t_score) < 1e-9 and t.get("secs") and secs < t["secs"])
            m = members._get(uid)
            if won:
                m["points"] = m.get("points", 0) + CHALLENGE_WIN_PTS
                m["challenge_wins"] = m.get("challenge_wins", 0) + 1
                if "beat_topper" not in m.setdefault("badges", []):
                    m["badges"].append("beat_topper")
                members.kv.save()
                result = (f"🥊 YOU BEAT THE TOPPER! {a['correct']}/{a['total']} in {secs}s vs "
                          f"{t['name']} {t_score:g} · +{CHALLENGE_WIN_PTS} pts · 🥊 badge\n"
                          f"⤷ Topper ని beat చేశారు! రేపు మీరే topper అవ్వచ్చు 🔥")
            else:
                result = (f"🥊 Close! {a['correct']}/{a['total']} in {secs}s — topper {t['name']} had {t_score:g}.\n"
                          f"⤷ ఈరోజు కాదు — రేపు మళ్ళీ. /review తో ఆ topics చూడండి.")
        save_json_atomic(CHALLENGE_PATH, data)
        return True, result
    except Exception as e:
        print(f"   [challenge] record note: {e}")
        return False, None


def challenge_stats_line(m) -> str:
    return f"🥊 Topper beats: {m.get('challenge_wins', 0)}"
