# -*- coding: utf-8 -*-
"""🌐 Student Portal (quiz.studentup.in) — daily quiz, mock tests, leaders.

Students register ONCE (name + mobile + district + exam goal); data lands
in the same members CRM the bot uses (uid = "w" + phone, same identity as
web college exams). Daily quiz is the SAME paper for everyone each day
(fair leaderboard); mock tests are per-goal (Groups/SSC/Banking/Railway/
Police) with instant scores. Personal report = accuracy + weak topics.
College exams are NEVER listed here — they stay private via code/link.
"""
import random
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from . import config

PATH = Path(config.DATA) / "portal.json"

GOALS = {
    "groups": {"label": "🏛️ Groups (APPSC / TSPSC)", "channels": ["APPSC", "TSPSC", "CURRENT"]},
    "ssc": {"label": "📄 SSC", "channels": ["SSC", "BANKING"]},
    "banking": {"label": "🏦 Banking", "channels": ["BANKING"]},
    "railway": {"label": "🚆 Railway (RRB)", "channels": ["RAILWAY"]},
    "police": {"label": "👮 Police & Defence", "channels": ["POLICE", "DEFENCE"]},
    "mixed": {"label": "🌟 Mixed (All Exams)", "channels": []},
}
DAILY_N = 10
MOCK_N = 15
PTS_DAILY = 10
PTS_MOCK = 10


def _now():
    tz = getattr(config, "IST", None)
    return datetime.now(tz) if tz else datetime.now()


def _today():
    return _now().strftime("%Y-%m-%d")


def _load():
    try:
        import json
        d = json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("sessions", {})
    d.setdefault("days", {})
    d.setdefault("mocks", {})
    d.setdefault("mock_board", [])
    return d


def _save(d):
    import json
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PATH)


def _bank_pool(channels=None):
    """Postable questions (optionally channel-filtered). Lazy bank load."""
    from .question_bank import Bank
    try:
        from .verifier import postable
    except Exception:
        def postable(q):
            return q.get("source") in ("pyq", "curated")
    pool = []
    for q in Bank().questions:
        if channels and q.get("channel") not in channels:
            continue
        opts = q.get("options_en") or []
        if len(opts) < 2 or not q.get("q_en"):
            continue
        if not postable(q):
            continue
        pool.append(q)
    return pool


def _snap(q):
    return {"id": q.get("id"), "topic": (q.get("topic") or "general"),
            "channel": q.get("channel") or "",
            "q_en": q.get("q_en", ""), "q_te": q.get("q_te", ""),
            "options_en": list(q.get("options_en") or []),
            "options_te": list(q.get("options_te") or []),
            "answer_index": int(q.get("answer_index") or 0),
            "explanation": q.get("explanation") or q.get("exp") or ""}


def _daily_paper(d):
    """Today's quiz — one paper for ALL students (seeded by date)."""
    day = _today()
    if day not in d["days"] or not d["days"][day].get("qs"):
        pool = _bank_pool()
        rng = random.Random("studentup-daily-" + day)
        picked = rng.sample(pool, min(DAILY_N, len(pool))) if pool else []
        d["days"][day] = {"qs": [_snap(q) for q in picked], "runs": {}}
        # keep only the last 3 days of papers/runs
        for old in sorted(d["days"])[:-3]:
            d["days"].pop(old, None)
        _save(d)
    return d["days"][day]


def _display(q, seed):
    """Per-student shuffled options; returns (display_texts, perm)."""
    from .content import build_options
    raw = build_options(q, telugu_first=True)
    perm = list(range(len(raw)))
    random.Random(seed).shuffle(perm)
    return [raw[i] for i in perm if i < len(raw)], perm


def _serve(qs, seed_prefix, answers):
    out = []
    for i, q in enumerate(qs):
        opts, _perm = _display(q, f"{seed_prefix}:{i}")
        out.append({"i": i, "topic": q["topic"], "channel": q["channel"],
                    "te": q.get("q_te", ""), "en": q.get("q_en", ""),
                    "options": opts, "answered": str(i) in (answers or {})})
    return out


# ---------------------------------------------------------------- register
def register_student(members, name, phone, district, goal):
    """One-time smart registration: name + mobile + district + exam goal.
    Data lands in the members CRM sheet (same as bot registrations)."""
    from . import districts as D
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())[-10:]
    if len(digits) != 10:
        return False, "Sariyina 10-digit mobile number ivvandi."
    name = str(name or "").strip()[:40]
    if not name:
        return False, "Mee peru ivvandi."
    all_d = [x[0] for x in D.AP_DISTRICTS + D.TS_DISTRICTS]
    if district not in all_d:
        return False, "Mee district select cheyyandi."
    if goal not in GOALS:
        goal = "mixed"
    uid = "w" + digits
    m = members._get(uid)
    m.update({"name": name, "mobile": digits, "phone": digits,
              "district": district, "state_code": D.state_of(district) or "",
              "exam_goal": goal, "goal": goal, "registered": True,
              "via": "portal"})
    members.kv.save()
    token = secrets.token_urlsafe(18)
    d = _load()
    d["sessions"][token] = uid
    _save(d)
    return True, {"token": token, "uid": uid, "name": name,
                  "district": district, "goal": goal}


def _sess(d, token):
    return (d.get("sessions") or {}).get(str(token or ""))


def _member(members, uid):
    return members._get(uid) if hasattr(members, "_get") else {}


def _award(members, uid, name, correct, q):
    try:
        members.award_answer(uid, name, bool(correct),
                             topic=q.get("topic", ""), qid=q.get("id", ""))
    except Exception:
        m = _member(members, uid)
        m["points"] = m.get("points", 0) + (PTS_DAILY if correct else 0)
    try:
        members.kv.save()
    except Exception:
        pass


def _profile(members, uid):
    m = _member(members, uid)
    topics = m.get("topics") or {}
    tot = sum(v.get("total", 0) for v in topics.values())
    cor = sum(v.get("correct", 0) for v in topics.values())
    weak = sorted(
        ({"topic": t, "accuracy": round(v.get("correct", 0) / v["total"] * 100)
          if v.get("total") else 0, "total": v.get("total", 0)}
         for t, v in topics.items() if v.get("total", 0) >= 2),
        key=lambda r: (r["accuracy"], -r["total"]))[:3]
    return {"name": m.get("name", ""), "district": m.get("district", ""),
            "goal": m.get("exam_goal") or m.get("goal") or "mixed",
            "points": m.get("points", 0),
            "answered": tot, "correct": cor,
            "accuracy": round(cor / tot * 100) if tot else 0,
            "weak_topics": weak}


def _board(rows, members, limit=10):
    out = []
    for r in rows[:limit]:
        m = _member(members, r["uid"])
        out.append({"name": r.get("name") or m.get("name", "Student"),
                    "district": r.get("district") or m.get("district", ""),
                    "correct": r.get("correct", 0), "total": r.get("total", 0),
                    "pts": r.get("pts", 0), "goal": r.get("goal", "")})
    return out


def state(members, token):
    """Portal home state: profile + today's status + leaderboards."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    day = _daily_paper(d)
    run = (day.get("runs") or {}).get(uid)
    yday = (_now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yd = (d["days"].get(yday) or {}).get("runs") or {}
    y_rows = sorted(yd.values(), key=lambda r: (-r.get("correct", 0), -r.get("pts", 0)))
    t_rows = sorted((day.get("runs") or {}).values(),
                    key=lambda r: (-r.get("correct", 0), -r.get("pts", 0)))
    mock_rows = sorted(d.get("mock_board") or [],
                       key=lambda r: (-r.get("correct", 0), -r.get("pts", 0)))
    prof = _profile(members, uid)
    return {"student": prof,
            "goals": {k: v["label"] for k, v in GOALS.items()},
            "daily": {"n": len(day["qs"]), "done": bool(run and run.get("done")),
                      "correct": (run or {}).get("correct", 0),
                      "answered": len((run or {}).get("answers") or {})},
            "daily_board": _board(t_rows, members),
            "yesterday_winners": _board(y_rows, members, limit=3),
            "mock_board": _board(mock_rows, members),
            "my_rank_today": next((i + 1 for i, r in enumerate(t_rows)
                                    if r.get("uid") == uid), None)}


# ---------------------------------------------------------------- daily quiz
def daily_questions(members, token):
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    day = _daily_paper(d)
    run = (day.setdefault("runs", {})).get(uid)
    answers = (run or {}).get("answers") or {}
    return {"questions": _serve(day["qs"], f"{uid}:{_today()}", answers),
            "done": bool(run and run.get("done"))}


def daily_answer(members, token, idx, choice):
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    day = _daily_paper(d)
    qs = day["qs"]
    if not (0 <= int(idx) < len(qs)):
        return False, "Invalid question."
    run = day.setdefault("runs", {}).setdefault(
        uid, {"uid": uid, "answers": {}, "done": False, "correct": 0, "pts": 0})
    if str(idx) in run["answers"]:
        return True, {"already": True}
    q = qs[int(idx)]
    _opts, perm = _display(q, f"{uid}:{_today()}:{int(idx)}")
    ch = int(choice)
    orig = perm[ch] if 0 <= ch < len(perm) else ch
    correct = orig == q["answer_index"]
    prof = _profile(members, uid)
    run["answers"][str(idx)] = orig
    run["name"], run["district"] = prof["name"], prof["district"]
    if correct:
        run["correct"] += 1
        run["pts"] += PTS_DAILY
    if len(run["answers"]) >= len(qs):
        run["done"] = True
        run["finished"] = _now().isoformat()
    _save(d)
    _award(members, uid, prof["name"], correct, q)
    opts = q.get("options_en") or []
    return True, {"correct": correct,
                  "answer_text": opts[q["answer_index"]] if 0 <= q["answer_index"] < len(opts) else "",
                  "explanation": q.get("explanation", ""),
                  "answered": len(run["answers"]), "total_q": len(qs),
                  "done": run["done"], "score": run["correct"]}


# ---------------------------------------------------------------- mock tests
def mock_start(members, token, goal):
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    if goal not in GOALS:
        goal = "mixed"
    chans = GOALS[goal]["channels"]
    pool = _bank_pool(chans or None)
    if len(pool) < 5:
        pool = _bank_pool()
    picked = random.Random(secrets.token_hex(4)).sample(
        pool, min(MOCK_N, len(pool))) if pool else []
    if not picked:
        return False, "Question bank ready ga ledu."
    run_id = secrets.token_urlsafe(9)
    d["mocks"][run_id] = {"uid": uid, "goal": goal,
                          "qs": [_snap(q) for q in picked],
                          "answers": {}, "done": False,
                          "started": _now().isoformat()}
    # prune old unfinished mocks
    for k in list(d["mocks"])[:-50]:
        d["mocks"].pop(k, None)
    _save(d)
    return True, {"run_id": run_id, "goal": goal,
                  "label": GOALS[goal]["label"],
                  "minutes": max(5, len(picked) * 1),
                  "questions": _serve(d["mocks"][run_id]["qs"], run_id, {})}


def mock_submit(members, token, run_id, answers):
    d = _load()
    uid = _sess(d, token)
    run = (d.get("mocks") or {}).get(str(run_id or ""))
    if not uid or not run or run.get("uid") != uid:
        return False, "Mock session dorakaledu."
    if run.get("done"):
        return True, {"already": True, "correct": run["correct"],
                      "total": len(run["qs"])}
    prof = _profile(members, uid)
    correct = 0
    review = []
    for i, q in enumerate(run["qs"]):
        given = (answers or {}).get(str(i), (answers or {}).get(i))
        if given is None:
            review.append({"i": i, "right": False, "given": -1, "answer": q["answer_index"]})
            continue
        _opts, perm = _display(q, f"{run_id}:{i}")
        g = int(given)
        orig = perm[g] if 0 <= g < len(perm) else g
        right = orig == q["answer_index"]
        correct += int(right)
        run["answers"][str(i)] = orig
        review.append({"i": i, "right": right, "given": orig, "answer": q["answer_index"]})
        _award(members, uid, prof["name"], right, q)
    run["done"] = True
    run["correct"] = correct
    run["finished"] = _now().isoformat()
    d.setdefault("mock_board", []).append(
        {"uid": uid, "name": prof["name"], "district": prof["district"],
         "goal": run["goal"], "correct": correct, "total": len(run["qs"]),
         "pts": correct * PTS_MOCK, "date": _today()})
    d["mock_board"] = d["mock_board"][-300:]
    _save(d)
    return True, {"correct": correct, "total": len(run["qs"]),
                  "accuracy": round(correct / max(1, len(run["qs"])) * 100),
                  "review": review,
                  "questions": [({"te": q.get("q_te", ""), "en": q.get("q_en", ""),
                                  "options": q.get("options_en") or [],
                                  "explanation": q.get("explanation", "")})
                                for q in run["qs"]]}
