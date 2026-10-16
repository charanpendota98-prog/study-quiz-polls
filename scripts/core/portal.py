# -*- coding: utf-8 -*-
"""🌐 Student Portal (quiz.studentup.in) — daily quiz, mock tests, leaders.

Students register ONCE (name + mobile + district + exam goal); data lands
in the same members CRM the bot uses (uid = "w" + phone, same identity as
web college exams). Daily quiz is the SAME paper for everyone each day
(fair leaderboard); mock tests are per-goal (Groups/SSC/Banking/Railway/
Police) with instant scores. Personal report = accuracy + weak topics.
College exams are NEVER listed here — they stay private via code/link.
"""
import atexit
import json
import random
import secrets
import threading
import time
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


# 🚀 10K SCALE ENGINE -------------------------------------------------------
# Mundu: prati request ki motham portal.json load + save (10k students
# exam lo idi seconds teeskuntundi). Ippudu:
#   • Store memory lone untundi (load okkasari) — prati answer O(1).
#   • Prati exam/daily answer oka chinna JOURNAL line ga append avthundi
#     (crash ayina kuda answers povu — restart lo replay avthayi).
#   • Disk snapshot background flusher prati ~2s ki (atomic write).
_STORE = {"path": None, "d": None, "dirty": False, "last": 0.0, "jfh": None}
_FLUSHER_ON = False


def _journal_file(path_str):
    pp = Path(path_str)
    return pp.with_name(pp.stem + "_events.jsonl")


def _close_journal():
    fh = _STORE.get("jfh")
    if fh is not None:
        try:
            fh.close()
        except Exception:
            pass
        _STORE["jfh"] = None


def _flush_store():
    with _LOCK:
        d = _STORE.get("d")
        if d is None or not _STORE.get("dirty"):
            return
        target = Path(_STORE["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        try:  # 🛡️ roju ki okka backup, last 3 matrame (corrupt ayina recovery)
            bak = target.with_name(target.name + ".bak-" + _today())
            if target.exists() and not bak.exists():
                bak.write_bytes(target.read_bytes())
            baks = sorted(target.parent.glob(target.name + ".bak-*"))
            for old_bak in baks[:-3]:
                old_bak.unlink(missing_ok=True)
        except Exception:
            pass
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)
        _STORE["dirty"] = False
        _STORE["last"] = time.time()
        _close_journal()
        try:
            _journal_file(_STORE["path"]).unlink(missing_ok=True)
        except Exception:
            pass


def _ensure_flusher():
    global _FLUSHER_ON
    if _FLUSHER_ON:
        return
    _FLUSHER_ON = True

    def _loop():
        while True:
            time.sleep(1)
            try:
                if _STORE.get("dirty") and time.time() - _STORE.get("last", 0) >= 2:
                    _flush_store()
            except Exception:
                pass

    threading.Thread(target=_loop, daemon=True).start()
    try:
        atexit.register(_flush_store)
    except Exception:
        pass


def _journal(ev):
    """Answer event ni append-only journal loki — O(1), crash-safe."""
    try:
        with _LOCK:
            fh = _STORE.get("jfh")
            if fh is None:
                fh = open(_journal_file(_STORE["path"]), "a", encoding="utf-8")
                _STORE["jfh"] = fh
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            fh.flush()
    except Exception:
        pass


def _replay_journal(d):
    try:
        jp = _journal_file(_STORE["path"])
        if not jp.exists():
            return
        applied = False
        for line in jp.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            t = ev.get("t")
            if t == "xj":
                e = (d.get("exams") or {}).get(ev.get("e") or "")
                if e:
                    e.setdefault("entries", {}).setdefault(ev["u"], {
                        "uid": ev["u"], "answers": {}, "correct": 0, "pts": 0,
                        "joined_at": ev.get("j", ""), "name": ev.get("n", ""),
                        "district": ev.get("d", "")})
                    applied = True
            elif t == "xa":
                e = (d.get("exams") or {}).get(ev.get("e") or "")
                ent = ((e or {}).get("entries") or {}).get(ev.get("u") or "")
                if ent is not None and str(ev["i"]) not in ent.setdefault("answers", {}):
                    ent["answers"][str(ev["i"])] = ev["o"]
                    if ev.get("c"):
                        ent["correct"] = ent.get("correct", 0) + 1
                        ent["pts"] = ent.get("pts", 0) + PTS_MOCK
                    applied = True
            elif t == "da":
                day = (d.get("days") or {}).get(ev.get("day") or "")
                if day:
                    run = day.setdefault("runs", {}).setdefault(ev["u"], {
                        "uid": ev["u"], "answers": {}, "done": False,
                        "correct": 0, "pts": 0})
                    if str(ev["i"]) not in run.setdefault("answers", {}):
                        run["answers"][str(ev["i"])] = ev["o"]
                        run["name"], run["district"] = ev.get("n", ""), ev.get("d", "")
                        if ev.get("c"):
                            run["correct"] = run.get("correct", 0) + 1
                            run["pts"] = run.get("pts", 0) + PTS_DAILY
                        if len(run["answers"]) >= len(day.get("qs") or []):
                            run["done"] = True
                        applied = True
        if applied:
            _STORE["dirty"] = True
    except Exception:
        pass


def _load():
    p = str(PATH)
    if _STORE["path"] == p and _STORE["d"] is not None:
        return _STORE["d"]
    if _STORE["d"] is not None and _STORE.get("dirty"):
        try:
            _flush_store()
        except Exception:
            pass
    _close_journal()
    try:
        d = json.loads(PATH.read_text(encoding="utf-8"))
    except Exception:
        d = {}
        # 🛡️ corrupt main file → latest daily backup nunchi recover
        try:
            for bak in sorted(PATH.parent.glob(PATH.name + ".bak-*"), reverse=True):
                try:
                    d = json.loads(bak.read_text(encoding="utf-8"))
                    break
                except Exception:
                    continue
        except Exception:
            d = {}
    d.setdefault("sessions", {})
    d.setdefault("days", {})
    d.setdefault("mocks", {})
    d.setdefault("mock_board", [])
    _STORE.update({"path": p, "d": d, "dirty": False, "last": time.time()})
    _replay_journal(d)
    _ensure_flusher()
    return d


def _save(d, flush=False):
    _STORE["d"] = d
    _STORE["dirty"] = True
    if flush:
        _flush_store()


# 🔒 ThreadingHTTPServer — chala mandi students okesari answer chesthe
# load→modify→save races raakunda prati mutation ni lock chestham.
_LOCK = threading.RLock()


def _locked(fn):
    def _w(*a, **k):
        with _LOCK:
            return fn(*a, **k)
    _w.__name__ = fn.__name__
    return _w


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
    return {"id": q.get("id"), "source": q.get("source") or "",
            "topic": (q.get("topic") or "general"),
            "channel": q.get("channel") or "",
            "q_en": q.get("q_en", ""), "q_te": q.get("q_te", ""),
            "options_en": list(q.get("options_en") or []),
            "options_te": list(q.get("options_te") or []),
            "answer_index": int(q.get("answer_index") or 0),
            "explanation": q.get("explanation") or q.get("exp") or ""}


@_locked
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
REF_BONUS = 50


def _kv_save(members):
    """Members file save — 10k bursts lo debounced (ledante prati answer/
    register ki full-file write avthundi)."""
    try:
        sv = getattr(members.kv, "save_debounced", None)
        (sv or members.kv.save)()
    except Exception:
        pass


def _ref_code(uid):
    return "SU" + str(uid)[-6:]


@_locked
def register_student(members, name, phone, district, goal, ref=""):
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
    _was_new = not m.get("via") and not m.get("registered")
    m.update({"name": name, "mobile": digits, "phone": digits,
              "district": district, "state_code": D.state_of(district) or "",
              "exam_goal": goal, "goal": goal, "registered": True,
              "via": "portal"})
    _kv_save(members)
    token = secrets.token_urlsafe(18)
    d = _load()
    d["sessions"][token] = uid
    d.setdefault("refcodes", {})[_ref_code(uid)] = uid
    # 🤝 Referral: kottha student vere student link tho vaste, aa student ki
    # bonus points (okko sari maatrame, thana code thane vadithe invalid).
    is_new = _was_new
    ref_by = ""
    ref_code = str(ref or "").strip().upper()
    if is_new and ref_code and ref_code != _ref_code(uid):
        ref_uid = (d.get("refcodes") or {}).get(ref_code)
        if not ref_uid:
            for _cand in (getattr(members, "members", None) or {}):
                if _ref_code(_cand) == ref_code:
                    ref_uid = _cand
                    d.setdefault("refcodes", {})[ref_code] = _cand
                    break
        if ref_uid and ref_uid != uid:
            rm = members._get(ref_uid)
            rm["points"] = rm.get("points", 0) + REF_BONUS
            rm["referrals"] = rm.get("referrals", 0) + 1
            _kv_save(members)
            ref_by = rm.get("name", "")
            d.setdefault("referral_log", []).append(
                {"from": ref_uid, "to": uid, "date": _today()})
            d["referral_log"] = d["referral_log"][-300:]
    _save(d)
    return True, {"token": token, "uid": uid, "name": name,
                  "district": district, "goal": goal,
                  "ref_code": _ref_code(uid), "referred_by": ref_by}


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
        _sv = getattr(members.kv, "save_debounced", None)
        (_sv or members.kv.save)()
    except Exception:
        pass
    if correct:
        # 🏆 Toppers (week/month/year) kosam dated points ledger
        try:
            d = _load()
            led = d.setdefault("ledger", [])
            led.append({"uid": str(uid), "pts": PTS_DAILY, "date": _today()})
            cutoff = (_now() - timedelta(days=400)).strftime("%Y-%m-%d")
            d["ledger"] = [r for r in led if r.get("date", "") >= cutoff][-8000:]
            _save(d)
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
    due = sum(1 for r in (m.get("review") or [])
              if str(r.get("due", "")) <= _today())
    return {"name": m.get("name", ""), "district": m.get("district", ""),
            "goal": m.get("exam_goal") or m.get("goal") or "mixed",
            "points": m.get("points", 0),
            "streak": m.get("streak", 0), "best_streak": m.get("best_streak", 0),
            "ref_code": _ref_code(uid), "referrals": m.get("referrals", 0),
            "badges": m.get("badges") or [],
            "review_due": due,
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
    _refresh(d, _now())
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
            "notices": list_notices(3),
            "toppers": toppers_all(members),
            "daily": {"n": len(day["qs"]),
                      "pyq_count": sum(1 for q in day["qs"] if q.get("source") == "pyq"),
                      "done": bool(run and run.get("done")),
                      "correct": (run or {}).get("correct", 0),
                      "answered": len((run or {}).get("answers") or {})},
            "daily_board": _board(t_rows, members),
            "yesterday_winners": _board(y_rows, members, limit=3),
            "mock_board": _board(mock_rows, members),
            "my_rank_today": next((i + 1 for i, r in enumerate(t_rows)
                                    if r.get("uid") == uid), None),
            "stock": exam_stock(),
            "history": _attempts(d, members, uid),
            "live_exams": [_exam_view(e, members, uid, _now())
                           for e in sorted(
                               sorted((d.get("exams") or {}).values(),
                                      key=lambda x: x["starts_at"], reverse=True),
                               key=lambda x: 0 if x.get("goal") == prof["goal"] else 1)[:6]],
            "top_referrers": top_referrers(members),
            "district_league": district_league(members, prof["district"]),
            "winners_wall": [{"title": e["title"], "kind": e["kind"],
                              "winners": e.get("winners") or []}
                             for e in sorted((d.get("exams") or {}).values(),
                                             key=lambda x: x["starts_at"],
                                             reverse=True)
                             if e.get("final")][:4]}


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


@_locked
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
    _journal({"t": "da", "day": _today(), "u": uid, "i": int(idx), "o": orig,
              "c": correct, "n": prof["name"], "d": prof["district"]})
    _save(d, flush=bool(run.get("done")))
    _award(members, uid, prof["name"], correct, q)
    opts = q.get("options_en") or []
    return True, {"correct": correct,
                  "answer_text": opts[q["answer_index"]] if 0 <= q["answer_index"] < len(opts) else "",
                  "explanation": q.get("explanation", ""),
                  "answered": len(run["answers"]), "total_q": len(qs),
                  "done": run["done"], "score": run["correct"]}


# ---------------------------------------------------------------- mock tests
@_locked
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
    # prune old mocks (finished vi key-paper kosam kontha kaalam unchutham)
    for k in list(d["mocks"])[:-120]:
        d["mocks"].pop(k, None)
    _save(d)
    return True, {"run_id": run_id, "goal": goal,
                  "label": GOALS[goal]["label"],
                  "minutes": max(5, len(picked) * 1),
                  "questions": _serve(d["mocks"][run_id]["qs"], run_id, {})}


@_locked
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
         "goal": run["goal"], "run_id": run_id, "correct": correct, "total": len(run["qs"]),
         "pts": correct * PTS_MOCK, "date": _today()})
    d["mock_board"] = d["mock_board"][-300:]
    _save(d, flush=True)
    return True, {"correct": correct, "total": len(run["qs"]),
                  "accuracy": round(correct / max(1, len(run["qs"])) * 100),
                  "review": review,
                  "questions": [({"te": q.get("q_te", ""), "en": q.get("q_en", ""),
                                  "options": q.get("options_en") or [],
                                  "explanation": q.get("explanation", "")})
                                for q in run["qs"]]}


# ------------------------------------------------------------- live exams
def _paper(channels, n, seed, pyq_first=True):
    """Real-exam paper: PYQ questions FIRST (real previous-year questions),
    filled with curated ones. Same paper for every student in the exam."""
    pool = _bank_pool(channels or None)
    if not pool:
        return []
    rng = random.Random(seed)
    if pyq_first:
        pyq = [q for q in pool if q.get("source") == "pyq"]
        rest = [q for q in pool if q.get("source") != "pyq"]
        rng.shuffle(pyq)
        rng.shuffle(rest)
        picked = (pyq + rest)[:n]
    else:
        picked = rng.sample(pool, min(n, len(pool)))
    return [_snap(q) for q in picked]


def _ist():
    return getattr(config, "IST", None)


def _aware(dt):
    if dt.tzinfo is None and _ist() is not None:
        return dt.replace(tzinfo=_ist())
    return dt


_TIMES_CACHE = {}


def _exam_times(e):
    # 🚀 10k hot path: prati answer ki ISO parse cheyyakunda cache
    key = (e.get("id"), e.get("starts_at"), e.get("duration_min"))
    hit = _TIMES_CACHE.get(key)
    if hit:
        return hit
    st = _aware(datetime.fromisoformat(e["starts_at"]))
    en = st + timedelta(minutes=int(e.get("duration_min", 30)))
    if len(_TIMES_CACHE) > 64:
        _TIMES_CACHE.clear()
    _TIMES_CACHE[key] = (st, en)
    return st, en


def exam_status(e, now):
    if e.get("final"):
        return "done"
    st, en = _exam_times(e)
    if now < st:
        return "scheduled"
    return "live" if now < en else "done"


def create_exam(title, goal, starts_at, duration_min=30, n_q=20, kind="live"):
    """Admin (dashboard) nunchi scheduled live exam. Paper ready ga untundi
    kaani start time varaku students ki kanipinchadu."""
    d = _load()
    if goal not in GOALS:
        goal = "mixed"
    try:
        st = _aware(datetime.fromisoformat(str(starts_at)))
        starts_at = st.isoformat()
    except Exception:
        return None
    exam_id = "EX-" + secrets.token_hex(3).upper()
    e = {"id": exam_id, "title": str(title or "Live Exam")[:60], "goal": goal,
         "kind": kind, "starts_at": starts_at,
         "duration_min": max(5, min(180, int(duration_min or 30))),
         "qs": _paper(GOALS[goal]["channels"] or None,
                      max(5, min(100, int(n_q or 20))), "portal-exam-" + exam_id),
         "entries": {}, "final": False, "winners": [],
         "created": _now().isoformat()}
    if not e["qs"]:
        return None
    d.setdefault("exams", {})[exam_id] = e
    _save(d)
    return e


def _weekly_exam(d, now):
    """🏆 Weekly Grand Test — prati Sunday 10:00 AM, automatic ga create."""
    days_ahead = (6 - now.weekday()) % 7
    start = (now + timedelta(days=days_ahead)).replace(
        hour=10, minute=0, second=0, microsecond=0)
    if start <= now:
        start += timedelta(days=7)
    key = start.strftime("%Y-%m-%d")
    for e in (d.get("exams") or {}).values():
        if e.get("kind") == "weekly" and e["starts_at"].startswith(key):
            return e
    e = {"id": "WK-" + start.strftime("%Y%m%d"),
         "title": "🏆 Weekly Grand Test — " + start.strftime("%d %b %Y"),
         "goal": "mixed", "kind": "weekly", "starts_at": start.isoformat(),
         "duration_min": 60,
         "qs": _paper(None, 40, "weekly-" + key),
         "entries": {}, "final": False, "winners": [],
         "created": now.isoformat()}
    d.setdefault("exams", {})[e["id"]] = e
    return e


@_locked
def _refresh(d, now):
    """Weekly exam ensure + aipoina exams ki winners finalize."""
    before = len(d.get("exams") or {})
    _weekly_exam(d, now)
    changed = len(d.get("exams") or {}) != before
    for e in (d.get("exams") or {}).values():
        if not e.get("final") and exam_status(e, now) == "done":
            rows = sorted((r for r in e.get("entries", {}).values()
                           if r.get("correct", 0) > 0),
                          key=lambda r: (-r.get("correct", 0), -r.get("pts", 0),
                                         r.get("joined_at", "")))
            e["winners"] = [{"name": r.get("name", ""),
                             "district": r.get("district", ""),
                             "correct": r.get("correct", 0),
                             "total": len(e["qs"]), "pts": r.get("pts", 0)}
                            for r in rows[:3]]
            e["final"] = True
            changed = True
            if e["winners"]:
                _med = ["🥇", "🥈", "🥉"]
                _txt = " · ".join(
                    f"{_med[i]} {w['name']} ({w['district']}) {w['correct']}/{w['total']}"
                    for i, w in enumerate(e["winners"]))
                d.setdefault("notices", []).insert(0, {
                    "id": "win-" + e["id"], "title": f"🏆 {e['title']} — Winners!",
                    "body": _txt + " · Winners portal lo certificate download cheyyandi!",
                    "link": "", "date": _today()})
                d["notices"] = d["notices"][:30]
    finals = sorted([e for e in (d.get("exams") or {}).values() if e.get("final")],
                    key=lambda e: e["starts_at"])
    for e in finals[:-12]:
        d["exams"].pop(e["id"], None)
        changed = True
    if changed:
        _save(d, flush=True)


def _exam_view(e, members, uid, now):
    status = exam_status(e, now)
    _st, en = _exam_times(e)
    entries = e.get("entries") or {}
    rows = sorted(entries.values(),
                  key=lambda r: (-r.get("correct", 0), -r.get("pts", 0)))
    ent = entries.get(uid or "")
    view = {"id": e["id"], "title": e["title"], "goal": e["goal"],
            "goal_label": (GOALS.get(e["goal"]) or {}).get("label", e["goal"]),
            "kind": e["kind"], "starts_at": e["starts_at"],
            "ends_at": en.isoformat(), "duration_min": e["duration_min"],
            "n_q": len(e["qs"]), "status": status, "joined": len(entries),
            "pyq_count": sum(1 for q in e["qs"] if q.get("source") == "pyq"),
            "my": {"joined": bool(ent),
                   "answered": len((ent or {}).get("answers") or {}),
                   "correct": (ent or {}).get("correct", 0),
                   "rank": next((i + 1 for i, r in enumerate(rows)
                                 if r.get("uid") == uid), None),
                   "top_pct": None}}
    _rk = view["my"]["rank"]
    if _rk and rows:
        view["my"]["top_pct"] = max(1, (100 * _rk + len(rows) - 1) // len(rows))
    if status in ("live", "done"):
        view["board"] = _board(
            [{"uid": r.get("uid", ""), "name": r.get("name", ""),
              "district": r.get("district", ""), "correct": r.get("correct", 0),
              "total": len(e["qs"]), "pts": r.get("pts", 0)} for r in rows],
            members)
    if status == "done":
        view["winners"] = e.get("winners") or []
        ent = entries.get(uid or "")
        view["my_winner"] = bool(ent) and (view["my"]["rank"] or 99) <= 3
    return view


def admin_list():
    d = _load()
    now = _now()
    _refresh(d, now)
    out = []
    for e in sorted((d.get("exams") or {}).values(),
                    key=lambda x: x["starts_at"], reverse=True):
        _st, en = _exam_times(e)
        out.append({"id": e["id"], "title": e["title"], "goal": e["goal"],
                    "kind": e["kind"], "starts_at": e["starts_at"],
                    "ends_at": en.isoformat(), "n_q": len(e["qs"]),
                    "status": exam_status(e, now),
                    "joined": len(e.get("entries") or {}),
                    "winners": e.get("winners") or []})
    return out


@_locked
def exam_join(members, token, exam_id):
    d = _load()
    uid = _sess(d, token)
    e = (d.get("exams") or {}).get(str(exam_id or ""))
    if not uid or not e:
        return False, "Session/exam dorakaledu — malli try cheyyandi."
    _refresh(d, _now())
    e = d["exams"][e["id"]]
    if exam_status(e, _now()) == "done":
        return False, "Ee exam ayipoyindi — winners chudandi!"
    prof = _profile(members, uid)
    e.setdefault("entries", {}).setdefault(
        uid, {"uid": uid, "answers": {}, "correct": 0, "pts": 0,
              "joined_at": _now().isoformat(),
              "name": prof["name"], "district": prof["district"]})
    _journal({"t": "xj", "e": e["id"], "u": uid, "n": prof["name"],
              "d": prof["district"], "j": _now().isoformat()})
    _save(d)
    return True, {"joined": True, "status": exam_status(e, _now()),
                  "title": e["title"]}


def exam_questions(members, token, exam_id):
    d = _load()
    uid = _sess(d, token)
    e = (d.get("exams") or {}).get(str(exam_id or ""))
    if not uid or not e:
        return None
    _refresh(d, _now())
    e = d["exams"][e["id"]]
    if exam_status(e, _now()) != "live":
        return {"status": exam_status(e, _now())}
    ent = (e.get("entries") or {}).get(uid)
    if not ent:
        return {"status": "not_joined"}
    _st, en = _exam_times(e)
    return {"status": "live", "title": e["title"], "ends_at": en.isoformat(),
            "questions": _serve(e["qs"], f"{e['id']}:{uid}",
                                ent.get("answers") or {})}


@_locked
def exam_answer(members, token, exam_id, idx, choice):
    """Live exam answer — result ayye varaku correct/wrong cheppamu
    (real exam feel). Live board kosam points matrame update avthayi."""
    d = _load()
    uid = _sess(d, token)
    e = (d.get("exams") or {}).get(str(exam_id or ""))
    if not uid or not e:
        return False, "Session/exam dorakaledu."
    _refresh(d, _now())
    e = d["exams"][e["id"]]
    if exam_status(e, _now()) != "live":
        return False, "Exam live lo ledu (start/ayipoindi chudandi)."
    ent = (e.get("entries") or {}).get(uid)
    if not ent:
        return False, "Mundhu exam join avvandi."
    if not (0 <= int(idx) < len(e["qs"])):
        return False, "Invalid question."
    if str(idx) in ent.get("answers", {}):
        return True, {"already": True, "answered": len(ent["answers"])}
    q = e["qs"][int(idx)]
    _opts, perm = _display(q, f"{e['id']}:{uid}:{int(idx)}")
    ch = int(choice)
    orig = perm[ch] if 0 <= ch < len(perm) else ch
    ent.setdefault("answers", {})[str(idx)] = orig
    if orig == q["answer_index"]:
        ent["correct"] += 1
        ent["pts"] += PTS_MOCK
    _journal({"t": "xa", "e": e["id"], "u": uid, "i": int(idx), "o": orig,
              "c": orig == q["answer_index"]})
    _save(d)
    prof = _profile(members, uid)
    _award(members, uid, prof["name"], orig == q["answer_index"], q)
    return True, {"answered": len(ent["answers"]), "total_q": len(e["qs"])}


def exam_result(members, token, exam_id):
    d = _load()
    uid = _sess(d, token)
    e = (d.get("exams") or {}).get(str(exam_id or ""))
    if not uid or not e:
        return None
    _refresh(d, _now())
    e = d["exams"][e["id"]]
    view = _exam_view(e, members, uid, _now())
    if view["status"] != "done":
        return view
    ent = (e.get("entries") or {}).get(uid)
    if ent:
        review = []
        for i, q in enumerate(e["qs"]):
            g = (ent.get("answers") or {}).get(str(i), -1)
            review.append({"i": i, "right": g == q["answer_index"],
                           "given": g, "answer": q["answer_index"]})
        view["review"] = review
        view["questions"] = [{"te": q.get("q_te", ""), "en": q.get("q_en", ""),
                              "options": q.get("options_en") or [],
                              "explanation": q.get("explanation", "")}
                             for q in e["qs"]]
    return view


# ------------------------------------------------- goal, stock, key paper
@_locked
def set_goal(members, token, goal):
    """Registration tarvatha kuda eppudaina exam marchukovachu (chips nunchi)."""
    d = _load()
    uid = _sess(d, token)
    if not uid or goal not in GOALS:
        return False, "Invalid exam selection."
    m = members._get(uid)
    m["exam_goal"] = goal
    m["goal"] = goal
    try:
        _kv_save(members)
    except Exception:
        pass
    return True, _profile(members, uid)


def exam_stock():
    """Exam-wise bank stock — prati goal ki enni real PYQ / total questions."""
    pool = _bank_pool()
    out = {}
    for key, g in GOALS.items():
        chans = g["channels"]
        sel = [q for q in pool if not chans or q.get("channel") in chans]
        out[key] = {"pyq": sum(1 for q in sel if q.get("source") == "pyq"),
                    "total": len(sel)}
    return out


def _attempts(d, members, uid):
    """Student rasina exams list — key paper download status tho."""
    out = []
    now = _now()
    for e in sorted((d.get("exams") or {}).values(),
                    key=lambda x: x["starts_at"], reverse=True):
        ent = (e.get("entries") or {}).get(uid)
        if not ent:
            continue
        st = exam_status(e, now)
        out.append({"kind": "exam", "ref": e["id"], "title": e["title"],
                    "date": (e.get("starts_at") or "")[:10],
                    "correct": ent.get("correct", 0), "total": len(e["qs"]),
                    "key": st == "done", "status": st})
    for r in reversed(d.get("mock_board") or []):
        if r.get("uid") == uid:
            out.append({"kind": "mock", "ref": r.get("run_id", ""),
                        "title": (GOALS.get(r.get("goal") or "") or {}).get("label", "Mock Test"),
                        "date": r.get("date", ""), "correct": r.get("correct", 0),
                        "total": r.get("total", 0), "key": bool(r.get("run_id")),
                        "status": "done"})
    for day_key in sorted((d.get("days") or {}), reverse=True):
        run = ((d["days"][day_key].get("runs") or {}).get(uid) or {})
        if run.get("done"):
            out.append({"kind": "daily", "ref": day_key,
                        "title": "📅 Daily Quiz", "date": day_key,
                        "correct": run.get("correct", 0),
                        "total": len(d["days"][day_key].get("qs") or []),
                        "key": True, "status": "done"})
    return out[:15]


def _key_text(title, date_s, prof, qs, answers):
    letters = "ABCD"
    correct = sum(1 for i, q in enumerate(qs)
                  if (answers or {}).get(str(i), -1) == q["answer_index"])
    total = len(qs)
    pct = round(correct / max(1, total) * 100)
    lines = ["🎓 StudentUp — Answer Key Paper", "=" * 44,
             f"Exam: {title}",
             f"Date: {date_s}",
             f"Student: {prof.get('name', '')} ({prof.get('district', '')})",
             f"Score: {correct}/{total} · {pct}%", "=" * 44, ""]
    for i, q in enumerate(qs):
        given = (answers or {}).get(str(i), -1)
        ans = q["answer_index"]
        opts = q.get("options_en") or []
        ok = given == ans
        lines.append(f"Q{i + 1}. [{q.get('topic', 'general')}] {q.get('q_en', '')}")
        if q.get("q_te"):
            lines.append(f"    {q['q_te']}")
        for j, o in enumerate(opts[:4]):
            mark = "✅" if j == ans else ("❌" if j == given else "▫️")
            lines.append(f"    {letters[j]}) {o} {mark if j in (ans, given) else ''}".rstrip())
        g_txt = (f"{letters[given]}) {opts[given]}" if 0 <= given < len(opts)
                 else "— (answer cheyyaledu)")
        a_txt = (f"{letters[ans]}) {opts[ans]}" if 0 <= ans < len(opts) else "")
        lines.append(("✅ Meeru: " if ok else "❌ Meeru: ") + g_txt
                     + ("" if ok else f"  → Correct: {a_txt}"))
        if q.get("explanation"):
            lines.append(f"💡 {q['explanation']}")
        lines.append("")
    lines += ["-" * 44,
              "Weak topics meeda Practice cheyyandi — next exam ki rank periguthundi! 🔥",
              "StudentUp · Ee key paper mee personal record kosam."]
    return "\n".join(lines), correct, total


def key_paper(members, token, kind, ref):
    """📄 Rasina exam ki full Answer Key — questions + mee right/wrong +
    correct answer + explanation. Stored attempt nunchi regenerate
    avthundi kabatti eppudaina download chesukovachu (one-time kaadu)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    prof = _profile(members, uid)
    if kind == "exam":
        _refresh(d, _now())
        e = (d.get("exams") or {}).get(str(ref or ""))
        ent = (e or {}).get("entries", {}).get(uid) if e else None
        if not e or not ent:
            return False, "Ee exam meeru rayaledu."
        if exam_status(e, _now()) != "done":
            return False, "Exam ayyaka key paper vasthundi (result time ki)."
        text, c, t = _key_text(e["title"], (e.get("starts_at") or "")[:10],
                               prof, e["qs"], ent.get("answers") or {})
        slug = "".join(ch if ch.isalnum() else "-" for ch in e["title"])[:32]
        return True, {"filename": f"StudentUp-Key-{slug}.txt", "text": text,
                      "correct": c, "total": t}
    if kind == "mock":
        run = (d.get("mocks") or {}).get(str(ref or ""))
        if not run or run.get("uid") != uid or not run.get("done"):
            return False, "Mock key dorakaledu."
        label = (GOALS.get(run.get("goal") or "") or {}).get("label", "Mock Test")
        text, c, t = _key_text(label, (run.get("finished") or "")[:10],
                               prof, run["qs"], run.get("answers") or {})
        return True, {"filename": "StudentUp-Key-Mock.txt", "text": text,
                      "correct": c, "total": t}
    if kind == "daily":
        day = (d.get("days") or {}).get(str(ref or ""))
        run = ((day or {}).get("runs") or {}).get(uid) if day else None
        if not day or not run or not run.get("done"):
            return False, "Daily quiz key dorakaledu."
        text, c, t = _key_text("📅 Daily Quiz", str(ref), prof,
                               day["qs"], run.get("answers") or {})
        return True, {"filename": f"StudentUp-Key-Daily-{ref}.txt", "text": text,
                      "correct": c, "total": t}
    return False, "Unknown key type."


# ------------------------------------------------------------- notices
@_locked
def add_notice(title, body, link=""):
    """📢 Exam updates/notifications (admin dashboard nunchi) — portal home
    lo + public /updates page lo kanipisthayi."""
    d = _load()
    n = {"id": secrets.token_hex(4),
         "title": str(title or "")[:120], "body": str(body or "")[:600],
         "link": str(link or "")[:300], "date": _today()}
    if not n["title"]:
        return None
    d.setdefault("notices", []).insert(0, n)
    d["notices"] = d["notices"][:30]
    _save(d)
    return n


def list_notices(limit=10):
    return (_load().get("notices") or [])[:limit]


# ------------------------------------------------------------- practice 2.0
def topics_list(limit=16):
    """Practice kosam bank lo unna top topics."""
    import collections
    try:
        pool = _bank_pool()
    except Exception:
        return []
    c = collections.Counter((q.get("topic") or "general") for q in pool)
    return [t for t, _n in c.most_common(limit)]


@_locked
def practice_start(members, token, mode="smart", topic=""):
    """🎯 Practice: 'smart' = mee weak topics + revision nunchi; 'topic' =
    select chesina topic; 'review' = ee roju due revision questions.
    Instant feedback tho — leaderboard pressure ledu."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    m = _member(members, uid)
    pool, picked = [], []
    if mode == "review":
        try:
            from .question_bank import Bank
            bank = Bank()
            for r in (m.get("review") or []):
                if str(r.get("due", "")) <= _today():
                    q = bank.by_id(r.get("qid"))
                    if q:
                        picked.append(q)
        except Exception:
            picked = []
        picked = picked[:10]
    if not picked:
        pool = _bank_pool()
        if mode == "topic" and topic:
            tp = [q for q in pool if (q.get("topic") or "").lower() == topic.lower()]
            pool = tp or pool
        elif mode == "smart":
            weak = [w["topic"] for w in _profile(members, uid)["weak_topics"]]
            wp = [q for q in pool if (q.get("topic") or "").lower() in
                  [w.lower() for w in weak]]
            if len(wp) >= 5:
                pool = wp
        picked = random.Random(secrets.token_hex(4)).sample(
            pool, min(10, len(pool))) if pool else []
    if not picked:
        return False, "Practice questions ready ga levu."
    run_id = "PR-" + secrets.token_hex(4)
    d.setdefault("practice", {})[run_id] = {
        "uid": uid, "mode": mode, "qs": [_snap(q) for q in picked],
        "answers": {}, "correct": 0, "created": _now().isoformat()}
    for k in list(d["practice"])[:-60]:
        d["practice"].pop(k, None)
    _save(d)
    return True, {"run_id": run_id, "mode": mode,
                  "questions": _serve(d["practice"][run_id]["qs"], run_id, {})}


@_locked
def practice_answer(members, token, run_id, idx, choice):
    d = _load()
    uid = _sess(d, token)
    run = (d.get("practice") or {}).get(str(run_id or ""))
    if not uid or not run or run.get("uid") != uid:
        return False, "Practice session dorakaledu."
    if not (0 <= int(idx) < len(run["qs"])):
        return False, "Invalid question."
    if str(idx) in run.get("answers", {}):
        return True, {"already": True}
    q = run["qs"][int(idx)]
    _opts, perm = _display(q, f"{run_id}:{int(idx)}")
    ch = int(choice)
    orig = perm[ch] if 0 <= ch < len(perm) else ch
    correct = orig == q["answer_index"]
    run.setdefault("answers", {})[str(idx)] = orig
    run["correct"] = run.get("correct", 0) + int(correct)
    _save(d)
    prof = _profile(members, uid)
    _award(members, uid, prof["name"], correct, q)
    opts = q.get("options_en") or []
    return True, {"correct": correct,
                  "answer_text": opts[q["answer_index"]] if 0 <= q["answer_index"] < len(opts) else "",
                  "explanation": q.get("explanation", ""),
                  "answered": len(run["answers"]), "total_q": len(run["qs"]),
                  "score": run["correct"],
                  "done": len(run["answers"]) >= len(run["qs"])}


# ------------------------------------------------- referrals + my report
def top_referrers(members, limit=5):
    import collections
    d = _load()
    c = collections.Counter(r.get("from") for r in (d.get("referral_log") or []))
    out = []
    for uid, n in c.most_common(limit):
        m = _member(members, uid)
        out.append({"name": m.get("name", "Student"),
                    "district": m.get("district", ""),
                    "correct": n, "total": n, "pts": n * REF_BONUS, "invites": n})
    return out


def my_report(members, token):
    """📊 Detailed personal report: topic bars, mock/exam history, referral."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    prof = _profile(members, uid)
    m = _member(members, uid)
    topics = []
    for t, v in (m.get("topics") or {}).items():
        tot = v.get("total", 0)
        if tot:
            topics.append({"topic": t, "total": tot, "correct": v.get("correct", 0),
                           "accuracy": round(v.get("correct", 0) / tot * 100)})
    topics.sort(key=lambda r: (r["accuracy"], -r["total"]))
    mocks = [r for r in (d.get("mock_board") or []) if r.get("uid") == uid][-5:]
    exams = []
    for e in (d.get("exams") or {}).values():
        ent = (e.get("entries") or {}).get(uid)
        if ent:
            exams.append({"title": e["title"], "status": exam_status(e, _now()),
                          "correct": ent.get("correct", 0), "total": len(e["qs"]),
                          "answered": len(ent.get("answers") or {})})
    _led = {}
    for r in (d.get("ledger") or []):
        if r.get("uid") == uid:
            _led[r["date"]] = _led.get(r["date"], 0) + int(r.get("pts") or 0)
    _act = []
    for _i in range(27, -1, -1):
        _dt = (_now() - timedelta(days=_i)).strftime("%Y-%m-%d")
        _act.append({"date": _dt, "pts": _led.get(_dt, 0)})
    return {"student": prof, "topics": topics[:10], "activity": _act,
            "strong": [t for t in topics if t["accuracy"] >= 75][-3:],
            "mocks": [{"goal": r.get("goal", ""), "correct": r.get("correct", 0),
                       "total": r.get("total", 0), "date": r.get("date", "")}
                      for r in reversed(mocks)],
            "exams": exams[-5:],
            "top_referrers": top_referrers(members)}


def report_text(members, uid, portal_url=""):
    """Telegram DM kosam personal report text (organiser dashboard nunchi
    one-click ga anni bot students ki personal ga pamputham)."""
    prof = _profile(members, uid)
    weak = ", ".join(f"{w['topic']} ({w['accuracy']}%)"
                     for w in prof["weak_topics"]) or "— (data inka ledu, quiz raayandi!)"
    lines = [f"🎓 {prof['name']} — mee Personal Report",
             f"⭐ Points: {prof['points']} · 🔥 Streak: {prof['streak']} days",
             f"🎯 Accuracy: {prof['accuracy']}% ({prof['correct']}/{prof['answered']} correct)"]
    lines.append(f"⚠️ Weak topics: {weak}")
    if prof["review_due"]:
        lines.append(f"🔁 Revision due: {prof['review_due']} questions — ivvala revise cheyyandi!")
    if portal_url:
        lines.append(f"📝 Daily Quiz + Mocks ikkade raayandi: {portal_url}")
    lines.append("💪 Roju konchem practice = pedha rank. All the best!")
    return "\n".join(lines)


# ------------------------------------------- district league + certificates
BADGE_LABELS = {"first_steps": "🌱 First Steps", "streak_3": "🔥 3-Day Streak",
                "streak_7": "🔥🔥 Week Warrior", "quiz_10": "📝 Quiz x10",
                "quiz_50": "🎯 Quiz x50", "quiz_100": "💯 Century",
                "sharp": "🎯 Sharpshooter", "topper": "🏆 Topper"}


def district_league(members, my_district="", limit=10):
    """🏙️ District League — district-wise total points + students count.
    Mana districts madhya healthy competition = daily habit ki pedha push."""
    import collections
    pts = collections.Counter()
    cnt = collections.Counter()
    for uid, m in (getattr(members, "members", None) or {}).items():
        dist = (m or {}).get("district")
        if not dist or not (m.get("registered") or m.get("points")):
            continue
        pts[dist] += int(m.get("points") or 0)
        cnt[dist] += 1
    rows = [{"name": dnm, "district": dnm, "correct": cnt[dnm], "total": cnt[dnm],
             "pts": pts[dnm], "students": cnt[dnm]}
            for dnm in pts]
    rows.sort(key=lambda r: (-r["pts"], r["name"]))
    my_rank = next((i + 1 for i, r in enumerate(rows)
                    if r["name"] == my_district), None)
    return {"rows": rows[:limit], "my_district": my_district, "my_rank": my_rank,
            "districts": len(rows)}


def winners_public(limit=8):
    """Public Hall of Fame kosam finished exams winners (names+district —
    bot lo already public ga announce chese data ne)."""
    d = _load()
    out = []
    for e in sorted((d.get("exams") or {}).values(),
                    key=lambda x: x["starts_at"], reverse=True):
        if e.get("final") and e.get("winners"):
            out.append({"title": e["title"], "kind": e["kind"],
                        "winners": e["winners"]})
        if len(out) >= limit:
            break
    return out


def exam_certificate(members, token, exam_id):
    """🏆 Top-3 winners ki certificate PNG (certcard engine). Winner
    kakapothe None — andariki raadu, gelichinavallake value untundi."""
    d = _load()
    uid = _sess(d, token)
    e = (d.get("exams") or {}).get(str(exam_id or ""))
    if not uid or not e:
        return None
    _refresh(d, _now())
    e = d["exams"][e["id"]]
    if exam_status(e, _now()) != "done":
        return None
    rows_all = sorted((r for r in e.get("entries", {}).values()
                       if r.get("correct", 0) > 0),
                      key=lambda r: (-r.get("correct", 0), -r.get("pts", 0)))
    rank = next((i + 1 for i, r in enumerate(rows_all)
                 if r.get("uid") == uid), None)
    if not rank or rank > 3:
        return None
    try:
        from . import certcard
        rows = [{"name": r.get("name", ""), "rank": i + 1,
                 "score": f"{r.get('correct', 0)}/{len(e['qs'])}",
                 "pct": round(r.get("correct", 0) / max(1, len(e["qs"])) * 100)}
                for i, r in enumerate(rows_all[:3])]
        prof = _profile(members, uid)
        title = str(e["title"]).replace("🏆", "").strip().upper()[:28] or "WINNERS"
        return certcard.render_certificate(
            title, "StudentUp Live Exam · Top Scorers",
            rows, footer=f"{prof['name']} — Rank #{rank} · studentup.in")
    except Exception:
        return None


# ------------------------------------------------------------- toppers
def _period_start(period, now):
    if period == "week":
        return (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    if period == "month":
        return now.strftime("%Y-%m-01")
    return now.strftime("%Y-01-01")


def toppers(members, period="week", limit=10):
    """🏆 Toppers of the Week/Month/Year — portal lo earn chesina points
    (daily quiz, mocks, live exams, practice) dated ledger nunchi.
    Names + district tho public ga chupistham (bot winners laage)."""
    d = _load()
    start = _period_start(period, _now())
    import collections
    agg = {}
    for r in (d.get("ledger") or []):
        if r.get("date", "") >= start:
            a = agg.setdefault(r["uid"], {"uid": r["uid"], "pts": 0, "answers": 0})
            a["pts"] += int(r.get("pts") or 0)
            a["answers"] += 1
    rows = sorted(agg.values(), key=lambda a: (-a["pts"], a["uid"]))[:limit]
    out = []
    for r in rows:
        m = _member(members, r["uid"])
        out.append({"name": m.get("name", "Student"),
                    "district": m.get("district", ""), "pts": r["pts"],
                    "answers": r["answers"]})
    return out


def toppers_all(members):
    return {"week": toppers(members, "week"),
            "month": toppers(members, "month"),
            "year": toppers(members, "year")}


def winners_text(exam_id):
    """📣 Winners announcement text (Telegram/WhatsApp share kosam)."""
    d = _load()
    e = (d.get("exams") or {}).get(str(exam_id or ""))
    if not e or not e.get("winners"):
        return ""
    med = ["🥇", "🥈", "🥉"]
    lines = [f"🏆 {e['title']} — WINNERS! 🏆", ""]
    for i, w in enumerate(e["winners"]):
        lines.append(f"{med[i] if i < 3 else ''} {w['name']} ({w['district']}) — "
                     f"✅ {w['correct']}/{w['total']} · ⭐ {w['pts']} pts")
    lines += ["", "🎉 Congratulations winners! Certificate portal lo ready undi.",
              "📝 Meeru kuda Daily Quiz + Weekly Grand Test lo participate cheyyandi!"]
    return "\n".join(lines)
