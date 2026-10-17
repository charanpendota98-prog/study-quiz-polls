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
PTS_GRAND = 10

# 🗓️ Official exam countdown targets (dashboard notice ga marchukovachu;
# date daggara padithe plan intensity automatic ga peruguthundi).
EXAM_DATES = {
    "groups": "2027-02-14", "ssc": "2026-12-20", "banking": "2026-12-06",
    "railway": "2027-01-18", "police": "2026-12-27", "mixed": "2026-12-31",
}

# 🎓 EXAM-SEPARATION (80X): prathi goal ki aa exam YE previous-paper
# questions — exam name keywords (bank 'exam' field mida match).
GOAL_EXAM_KEYS = {
    "groups": ("appsc", "tspsc", "group"),
    "ssc": ("ssc",),
    "banking": ("bank", "ibps", "sbi", "rbi"),
    "railway": ("rrb", "railway", "ntpc", "alp", "group d"),
    "police": ("police", "defence", "defense", "army", "constable"),
    "mixed": (),
}


def _goal_pyq_pool(goal):
    """📜 STRICT exam-wise PYQ pool: goal channels loni PYQs, exam name
    keyword match unte adhe (vere exam PYQs mix avvakunda). Keyword pool
    empty ayithe channel PYQs fallback (honest counts ekkade vastayi)."""
    chans = (GOALS.get(goal) or {}).get("channels") or []
    pyqs = [q for q in _bank_pool()
            if q.get("source") == "pyq"
            and (not chans or q.get("channel") in chans)]
    keys = GOAL_EXAM_KEYS.get(goal) or ()
    if keys:
        ex = [q for q in pyqs
              if any(k in str(q.get("exam") or "").lower() for k in keys)]
        if ex:
            return ex
    return pyqs


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
                    else:
                        ent["wrong"] = ent.get("wrong", 0) + 1
                        _neg = float((e or {}).get("neg") or 0)
                        if _neg:
                            ent["pts"] = round(ent.get("pts", 0) - PTS_MOCK * _neg, 1)
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
            # 📜 PYQ provenance (80X): exam/year/paper badges + hub ki
            "exam": q.get("exam") or "", "year": q.get("year") or "",
            "paper": q.get("paper") or "",
            "q_en": q.get("q_en", ""), "q_te": q.get("q_te", ""),
            "options_en": list(q.get("options_en") or []),
            "options_te": list(q.get("options_te") or []),
            "answer_index": int(q.get("answer_index") or 0),
            # 🛠️ FIX (bug hunt R2): bank field 'explanation_en' —
            # 'explanation' matrame chudatam valla portal lo
            # explanations EPPUDU empty ga vachevi (feedback/key/worksheet).
            "explanation": (q.get("explanation") or q.get("explanation_en")
                            or q.get("exp") or q.get("note") or ""),
            "explanation_te": q.get("explanation_te") or ""}


@_locked
def _daily_paper(d):
    """Today's quiz — one paper for ALL students (seeded by date)."""
    day = _today()
    if day not in d["days"] or not d["days"][day].get("qs"):
        pool = _bank_pool()
        rng = random.Random("studentup-daily-" + day)
        # 📜 PYQ guarantee (60X): daily paper lo kammi 40% real PYQ
        # (stock allow chesthe) — students ki daily previous-year feel.
        pyqs = [q for q in pool if q.get("source") == "pyq"]
        rest = [q for q in pool if q.get("source") != "pyq"]
        rng.shuffle(pyqs)
        rng.shuffle(rest)
        n_pyq = min(len(pyqs), max(1, round(DAILY_N * 0.4))) if pyqs else 0
        picked = pyqs[:n_pyq] + rest[:max(0, DAILY_N - n_pyq)]
        if len(picked) < min(DAILY_N, len(pool)):
            picked += (pyqs[n_pyq:] + rest[DAILY_N - n_pyq:])[
                :min(DAILY_N, len(pool)) - len(picked)]
        rng.shuffle(picked)
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
    try:
        from . import blueprint as _bp
        _lvl = lambda q: _bp.difficulty_of(q)  # noqa: E731
    except Exception:
        _lvl = lambda q: ""  # noqa: E731
    for i, q in enumerate(qs):
        opts, _perm = _display(q, f"{seed_prefix}:{i}")
        out.append({"i": i, "qid": q.get("id"), "topic": q["topic"], "channel": q["channel"],
                    "te": q.get("q_te", ""), "en": q.get("q_en", ""),
                    "level": _lvl(q),
                    "source": q.get("source") or "",
                    "exam": q.get("exam") or "", "year": q.get("year") or "",
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


def _kv_save_flush(members):
    """💾 User-initiated rare writes (goal2/focus) — debounced save valla
    immediate next read stale (≤2s window) kanipisthundi; anduke ee
    writes matrame ventane flush (per-answer hot path ki kadu)."""
    try:
        members.kv.save()
    except Exception:
        _kv_save(members)


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
    # 🛠️ Session TTL: value ippudu {uid, ts} — 30 rojula tarvatha expire
    d["sessions"][token] = {"uid": uid, "ts": _now().isoformat()}
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


SESSION_TTL_DAYS = 30


def _sess(d, token):
    """Session token -> uid. 🛠️ FIX: sessions eppudu expire ayyevi kaavu
    — ippudu 30-day TTL ({uid, ts} format; legacy string tokens
    grandfathered, next login nunchi new format vastundi)."""
    raw = (d.get("sessions") or {}).get(str(token or ""))
    if raw is None:
        return None
    if isinstance(raw, dict):
        try:
            age = (_now() - datetime.fromisoformat(raw.get("ts") or "")).days
        except Exception:
            age = 0
        if age > SESSION_TTL_DAYS:
            (d.get("sessions") or {}).pop(str(token or ""), None)
            return None
        return raw.get("uid")
    return raw


def _member(members, uid):
    return members._get(uid) if hasattr(members, "_get") else {}


def _award(members, uid, name, correct, q):
    try:
        members.award_answer(uid, name, bool(correct),
                             topic=q.get("topic", ""), qid=q.get("id", ""))
    except Exception:
        m = _member(members, uid)
        m["points"] = m.get("points", 0) + (PTS_DAILY if correct else 0)
    try:      # 🧠 Brain 3.0: difficulty-aware ability update
        from . import brain as _brain
        _brain.record(uid, q.get("id", ""), bool(correct),
                      topic=q.get("topic", ""),
                      level=str(q.get("difficulty") or q.get("level") or ""))
    except Exception:
        pass
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


_BADGE_FALLBACK = {"first_steps": "🌱 First Steps", "streak_3": "🔥 3-Day Streak",
                   "streak_7": "🔥🔥 Week Warrior", "quiz_10": "📝 Quiz x10",
                   "quiz_50": "🎯 Quiz x50", "quiz_100": "💯 Century",
                   "sharp": "🎯 Sharpshooter", "topper": "🏆 Topper"}


def _badge_labels(ids):
    """🏅 Badge ids -> display labels. 🛠️ FIX (R4): portal chips lo
    raw ids ('correct10') kanipinchhevi — ippudu icon+English name
    (members._earned_badges single source nunchi)."""
    defs = {}
    try:
        from .members import Members as _M
        for b in _M._all_badge_defs():
            defs[b["id"]] = b["icon"]
    except Exception:
        pass
    _names = {"first": "First Answer", "correct10": "10 Correct",
              "correct100": "Century — 100 Correct",
              "streak3": "3-Day Streak", "streak7": "7-Day Streak",
              "streak30": "30-Day Streak", "sharp": "Sharp Shooter",
              "champion": "Champion", "beat_topper": "Beat the Topper",
              "defender": "Defender", "round_top1": "Round Winner",
              "round_top5": "5× Round Winner",
              "district_king": "District Topper ×3",
              "perfect": "Perfect Round", "referrer3": "Brought 3 Friends",
              "focus": "Focus Star", "ambassador": "Ambassador"}
    out = []
    for bid in ids or []:
        if bid in _BADGE_FALLBACK:
            out.append(_BADGE_FALLBACK[bid])
        elif bid in defs:
            out.append(f"{defs[bid]} {_names.get(bid, bid)}")
        else:
            out.append(f"🏅 {_names.get(bid, bid)}")
    return out


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
            "badges": _badge_labels(m.get("badges") or []),
            "lang": m.get("lang") or "both",
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
    try:
        from . import brain as _brain
        _brain_card = _brain.profile_for(_member(members, uid), uid)
    except Exception:
        _brain_card = None
    _plan = None
    try:
        _plan = today_plan(members, token)
    except Exception:
        _plan = None
    _cd = None
    try:
        _cd = exam_countdowns(members, token)
    except Exception:
        _cd = None
    _nts = [n for n in list_notices(10)
            if not n.get("goal") or n.get("goal") == prof.get("goal")]
    return {"student": prof, "brain": _brain_card, "today_plan": _plan,
            "countdown": _cd,
            "sprint": (sprint_plan(members, token)
                       if _cd and (_cd.get("mine") or {}).get("days") is not None
                       and 0 <= (_cd["mine"]["days"]) <= 14 else None),
            "goal2": {"goal": _member(members, uid).get("goal2", ""),
                      "label": (GOALS.get(_member(members, uid).get("goal2") or "")
                                or {}).get("label", "")},
            "focus": _focus_stats(_member(members, uid)),
            "papers": [{"label": r["label"], "exam": r["exam"],
                        "year": r["year"], "paper": r["paper"],
                        "topics": r.get("topics") or [],
                        "size": r.get("size", "full"),
                        "count": r["count"]} for r in paper_catalog()],
            "paper_progress": paper_progress(members, token),
            "goals": {k: v["label"] for k, v in GOALS.items()},
            "notices": _nts[:3],
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
        # 🗄️ Permanent archive — 3-day window tarvatha kuda key paper!
        _archive_attempt(d, uid, "daily", _today(), "📅 Daily Quiz",
                         qs, run.get("answers") or {}, run.get("correct", 0))
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


# ------------------------------------------------------- attempt archive
def _archive_attempt(d, uid, kind, ref, title, qs, answers, correct=None):
    """🗄️ PERMANENT ATTEMPT ARCHIVE — key paper eppudaina malli download.

    🛠️ FIX: mocks/days store prune (120 runs / 3 days) tarvatha student
    thana Answer Key Paper malli teesukolekapoyevadu ('permanently
    re-downloadable' promise break). Ippudu prathi finished attempt
    snapshot archive loki velthundi (bounded, per-student latest first).
    """
    try:
        total = len(qs or [])
        if correct is None:
            correct = sum(1 for i, q in enumerate(qs or [])
                          if (answers or {}).get(str(i), -1) == q.get("answer_index"))
        arc = d.setdefault("archive", [])
        arc.insert(0, {"uid": uid, "kind": kind, "ref": str(ref),
                       "title": str(title or "")[:80], "date": _today(),
                       "qs": qs, "answers": dict(answers or {}),
                       "correct": int(correct), "total": int(total)})
        mine = [a for a in arc if a.get("uid") == uid][:60]
        others = [a for a in arc if a.get("uid") != uid]
        d["archive"] = (mine + others)[:1500]
    except Exception:
        pass


def _archive_lookup(d, uid, kind, ref):
    for a in (d.get("archive") or []):
        if (a.get("uid") == uid and a.get("kind") == kind
                and str(a.get("ref")) == str(ref)):
            return a
    return None


def my_archive(members, token, limit=30):
    """🗄️ Student thana permanent attempt archive (history + keys)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return []
    return [{"kind": a.get("kind"), "ref": a.get("ref"),
             "title": a.get("title"), "date": a.get("date"),
             "correct": a.get("correct"), "total": a.get("total")}
            for a in (d.get("archive") or []) if a.get("uid") == uid][:limit]


# ---------------------------------------------------------------- mock tests
@_locked
def mock_start(members, token, goal, neg=0.0, kind="mock"):
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    if goal not in GOALS:
        goal = "mixed"
    chans = GOALS[goal]["channels"]
    if kind == "grand":
        # 🏛️ GRAND MOCK: full-length simulation (50Q, PYQ-first)
        try:
            from . import flags as _fl
            if not _fl.enabled("grand_mock"):
                kind = "mock"
        except Exception:
            pass
    if kind == "grand":
        picked = _paper(chans or None, 50, "grand-" + secrets.token_hex(4),
                        strict=bool(chans))
    elif kind == "adaptive":
        # 🧠 ADAPTIVE MOCK: Brain compose (due review + weak + level zone)
        try:
            from . import flags as _fl
            _ad_on = _fl.enabled("adaptive_mock")
        except Exception:
            _ad_on = True
        if _ad_on:
            try:
                from . import brain as _brain
                pool = _bank_pool(chans or None)
                if len(pool) < 5:
                    pool = _bank_pool()
                _m = _member(members, uid)
                _rev = []
                try:
                    from .question_bank import Bank as _Bk
                    _bk = _Bk()
                    for r in (_m.get("review") or []):
                        if str(r.get("due", "")) <= _today():
                            _q = _bk.by_id(r.get("qid"))
                            if _q:
                                _rev.append(_q)
                except Exception:
                    _rev = []
                picked = _brain.compose(pool, _m, uid, n=MOCK_N,
                                        review_qs=_rev)
            except Exception:
                picked = []
            if not picked:
                pool = _bank_pool(chans or None)
                picked = random.Random(secrets.token_hex(4)).sample(
                    pool, min(MOCK_N, len(pool))) if pool else []
        else:
            kind = "mock"
            pool = _bank_pool(chans or None)
            picked = random.Random(secrets.token_hex(4)).sample(
                pool, min(MOCK_N, len(pool))) if pool else []
    elif kind == "exam":
        # 📜 EXAM PYQ MOCK (80X): aa exam previous papers nunchi matrame
        # (exam-name strict pool) + same-channel curated fill.
        try:
            from . import flags as _fl
            _ex_on = _fl.enabled("exam_pyq_mocks")
        except Exception:
            _ex_on = True
        if not _ex_on or goal == "mixed":
            kind = "mock"
            pool = _bank_pool(chans or None)
            picked = random.Random(secrets.token_hex(4)).sample(
                pool, min(MOCK_N, len(pool))) if pool else []
        else:
            rng = random.Random(secrets.token_hex(4))
            pyqs = _goal_pyq_pool(goal)
            rng.shuffle(pyqs)
            fill = [q for q in _bank_pool(chans or None)
                    if q.get("source") != "pyq"]
            rng.shuffle(fill)
            picked = [_snap(q) for q in (pyqs + fill)[:MOCK_N]]
            if not picked:
                return False, ("Ee exam ki inka previous-paper questions "
                               "levu — harvest thondaralo vasthundi.")
            _exam_pyq_n = sum(1 for q in picked
                              if q.get("source") == "pyq")
    else:
        pool = _bank_pool(chans or None)
        if len(pool) < 5:
            pool = _bank_pool()
        picked = random.Random(secrets.token_hex(4)).sample(
            pool, min(MOCK_N, len(pool))) if pool else []
    if not picked:
        return False, "Question bank ready ga ledu."
    try:
        neg = max(0.0, min(1.0, float(neg or 0)))
    except Exception:
        neg = 0.0
    # 🏁 Negative-marking simulator kill-switch (admin flag)
    try:
        from . import flags as _fl
        if not _fl.enabled("negative_mocks"):
            neg = 0.0
    except Exception:
        pass
    run_id = secrets.token_urlsafe(9)
    d["mocks"][run_id] = {"uid": uid, "goal": goal, "neg": neg,
                          "kind": kind,
                          "qs": [_snap(q) for q in picked],
                          "answers": {}, "done": False,
                          "started": _now().isoformat()}
    # prune old mocks (finished vi key-paper kosam kontha kaalam unchutham)
    for k in list(d["mocks"])[:-120]:
        d["mocks"].pop(k, None)
    _save(d)
    return True, {"run_id": run_id, "goal": goal, "neg": neg, "kind": kind,
                  "label": ("🏛️ Grand Mock — " if kind == "grand" else
                            "🧠 Adaptive Mock — " if kind == "adaptive" else
                            f"📜 PYQ Mock ({locals().get('_exam_pyq_n', 0)} real PYQ) — "
                            if kind == "exam" else "")
                           + GOALS[goal]["label"],
                  "minutes": (60 if kind == "grand"
                              else max(5, len(picked) * 1)),
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
    wrong = 0
    review = []
    for i, q in enumerate(run["qs"]):
        given = (answers or {}).get(str(i), (answers or {}).get(i))
        if given is None:
            wrong += 1
            review.append({"i": i, "right": False, "given": -1, "answer": q["answer_index"]})
            continue
        _opts, perm = _display(q, f"{run_id}:{i}")
        g = int(given)
        orig = perm[g] if 0 <= g < len(perm) else g
        right = orig == q["answer_index"]
        correct += int(right)
        wrong += int(not right)
        run["answers"][str(i)] = orig
        review.append({"i": i, "right": right, "given": orig, "answer": q["answer_index"]})
        _award(members, uid, prof["name"], right, q)
    # 🏁 Negative marking (real-exam simulation): pts matrame tagguthayi,
    # correct count nijamgane untundi (honest score).
    neg = float(run.get("neg") or 0)
    kind = run.get("kind") or "mock"
    pts = correct * (PTS_GRAND if kind == "grand" else PTS_MOCK)
    if neg:
        pts = max(0, round(pts - wrong * (PTS_GRAND if kind == "grand" else PTS_MOCK) * neg, 1))
    run["done"] = True
    run["correct"] = correct
    run["wrong"] = wrong
    try:
        from datetime import datetime as _dt2
        _st = _dt2.fromisoformat(run.get("started") or "")
        run["mins_taken"] = round((_now() - _st).total_seconds() / 60.0, 1) \
            if _st.tzinfo else None
    except Exception:
        run["mins_taken"] = None
    run["pts"] = pts
    run["finished"] = _now().isoformat()
    d.setdefault("mock_board", []).append(
        {"uid": uid, "name": prof["name"], "district": prof["district"],
         "goal": run.get("paper_label") or run["goal"], "run_id": run_id,
         "correct": correct, "total": len(run["qs"]),
         "pts": pts, "date": _today()})
    d["mock_board"] = d["mock_board"][-300:]
    _archive_attempt(d, uid, run.get("kind") or "mock", run_id,
                     run.get("paper_label") or
                     (GOALS.get(run.get("goal") or "") or {}).get("label", "Mock Test"),
                     run["qs"], run.get("answers") or {}, correct)
    _save(d, flush=True)
    return True, {"correct": correct, "total": len(run["qs"]), "wrong": wrong,
                  "neg": neg, "pts": pts,
                  "accuracy": round(correct / max(1, len(run["qs"])) * 100),
                  "review": review,
                  "questions": [({"te": q.get("q_te", ""), "en": q.get("q_en", ""),
                                  "options": q.get("options_en") or [],
                                  "explanation": q.get("explanation", "")})
                                for q in run["qs"]]}


# ------------------------------------------------------------- live exams
def _paper(channels, n, seed, pyq_first=True, strict=False):
    """Real-exam paper: PYQ questions FIRST (real previous-year questions),
    filled with curated ones. Same paper for every student in the exam.

    🛠️ FIX (R3): count kana pool chinna ayithe paper short ga
    vachedi (channels pool matrame) — ippudu full bank nunchi
    fill chestham (PYQ-first order maintain chesthu).
    🎓 80X strict=True: EXAM-SEPARATION — paper order: (1) aa exam
    PYQs, (2) aa exam curated, (3) vere exams PYQs (last resort,
    previous-paper promise kosam), (4) migilina bank. Production
    bank lo (1)-(2) lone full paper vasthundi."""
    pool = _bank_pool(channels or None)
    if not pool and not strict:
        return []
    rng = random.Random(seed)
    if strict and channels:
        seen = {q.get("id") for q in pool}
        fb = [q for q in _bank_pool() if q.get("id") not in seen]
        groups = [[q for q in pool if q.get("source") == "pyq"],
                  [q for q in pool if q.get("source") != "pyq"],
                  [q for q in fb if q.get("source") == "pyq"],
                  [q for q in fb if q.get("source") != "pyq"]]
        picked = []
        for g in groups:
            rng.shuffle(g)
            picked += g
        return [_snap(q) for q in picked[:n]]
    seen = {q.get("id") for q in pool}
    if len(pool) < n:
        pool = pool + [q for q in _bank_pool()
                       if q.get("id") not in seen]
    if not pool:
        return []
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


def create_exam(title, goal, starts_at, duration_min=30, n_q=20, kind="live",
                neg=0.0):
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
         "neg": max(0.0, min(1.0, float(neg or 0))),
         "duration_min": max(5, min(180, int(duration_min or 30))),
         "qs": _paper(GOALS[goal]["channels"] or None,
                      max(5, min(100, int(n_q or 20))), "portal-exam-" + exam_id,
                      strict=bool(GOALS[goal]["channels"])),
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
    # 🛠️ FIX (R3): bank ready kakapothe 0-question weekly exam
    # create avvakudadhu (students ki empty exam kanipinchakudadhu).
    if not e["qs"]:
        return None
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
            # 🗄️ Permanent archive — exam prune ayina key paper undali
            for _uid, _ent in (e.get("entries") or {}).items():
                if _ent.get("answers"):
                    _archive_attempt(
                        d, _uid, "exam", e["id"], e.get("title", ""),
                        e.get("qs") or [], _ent.get("answers") or {},
                        _ent.get("correct", 0))
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
    # 🛠️ FIX (R3): winners/board tie-break ikkada kuda joined_at —
    # lekunte tie lo 'my_winner'/rank announced winners tho mismatch.
    rows = sorted(entries.values(),
                  key=lambda r: (-r.get("correct", 0), -r.get("pts", 0),
                                 r.get("joined_at", "")))
    ent = entries.get(uid or "")
    view = {"id": e["id"], "title": e["title"], "goal": e["goal"],
            "goal_label": (GOALS.get(e["goal"]) or {}).get("label", e["goal"]),
            "kind": e["kind"], "starts_at": e["starts_at"],
            "ends_at": en.isoformat(), "duration_min": e["duration_min"],
            "starts_in_min": (max(0, int((_st - now).total_seconds() // 60))
                              if status == "scheduled" else None),
            "ends_in_min": (max(0, int((en - now).total_seconds() // 60))
                            if status == "live" else None),
            "n_q": len(e["qs"]), "status": status, "joined": len(entries),
            "remind": uid in ((_load().get("exam_reminds") or {}).get(e["id"]) or []),
            "neg": float(e.get("neg") or 0),
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
    ent["last_answer_at"] = _now().isoformat()
    ent.setdefault("wrong", 0)
    if orig == q["answer_index"]:
        ent["correct"] += 1
        ent["pts"] += PTS_MOCK
    else:
        ent["wrong"] += 1
        if e.get("neg"):
            ent["pts"] = round(ent.get("pts", 0) - PTS_MOCK * float(e["neg"]), 1)
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
        # 👥 prati question entha mandi correct pettaru (tough/easy telusthundi)
        _all = list((e.get("entries") or {}).values())
        qstats = []
        for i, q in enumerate(e["qs"]):
            _ans = [x for x in _all if str(i) in (x.get("answers") or {})]
            _ok = sum(1 for x in _ans if x["answers"][str(i)] == q["answer_index"])
            qstats.append(round(100 * _ok / len(_ans)) if _ans else None)
        view["qstats"] = qstats
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
                        # 🛠️ FIX: paper attempts goal field lo paper
                        # label untundi — 'Mock Test' ani tappudu label
                        # padakudadhu; GOALS key ayithe daani label.
                        "title": (GOALS.get(r.get("goal") or "") or {}).get(
                            "label", r.get("goal") or "Mock Test"),
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
            # 🗄️ Exam prune ayipoyina permanent archive nunchi
            arc = _archive_lookup(d, uid, "exam", ref)
            if arc:
                text, c, t = _key_text(arc.get("title") or "Live Exam",
                                       arc.get("date") or "", prof,
                                       arc.get("qs") or [],
                                       arc.get("answers") or {})
                return True, {"filename": "StudentUp-Key-Exam.txt",
                              "text": text, "correct": c, "total": t}
            return False, "Ee exam meeru rayaledu."
        if exam_status(e, _now()) != "done":
            return False, "Exam ayyaka key paper vasthundi (result time ki)."
        text, c, t = _key_text(e["title"], (e.get("starts_at") or "")[:10],
                               prof, e["qs"], ent.get("answers") or {})
        if e.get("neg"):
            _ln = text.split("\n")
            _ln.insert(6, f"Negative marking: -{float(e['neg']):g} × per wrong · "
                          f"Wrong: {ent.get('wrong', 0)} · Final points: {ent.get('pts', 0)}")
            text = "\n".join(_ln)
        slug = "".join(ch if ch.isalnum() else "-" for ch in e["title"])[:32]
        return True, {"filename": f"StudentUp-Key-{slug}.txt", "text": text,
                      "correct": c, "total": t}
    if kind == "mock":
        run = (d.get("mocks") or {}).get(str(ref or ""))
        if run and run.get("uid") == uid and run.get("done"):
            label = (GOALS.get(run.get("goal") or "") or {}).get(
                "label", run.get("paper_label") or run.get("goal") or "Mock Test")
            text, c, t = _key_text(label, (run.get("finished") or "")[:10],
                                   prof, run["qs"], run.get("answers") or {})
            return True, {"filename": "StudentUp-Key-Mock.txt", "text": text,
                          "correct": c, "total": t}
        # 🗄️ Store nunchi prune ayina permanent archive nunchi
        arc = _archive_lookup(d, uid, "mock", ref) or \
            _archive_lookup(d, uid, "paper", ref)
        if arc:
            text, c, t = _key_text(arc.get("title") or "Mock Test",
                                   arc.get("date") or "", prof,
                                   arc.get("qs") or [], arc.get("answers") or {})
            return True, {"filename": "StudentUp-Key-Mock.txt", "text": text,
                          "correct": c, "total": t}
        return False, "Mock key dorakaledu."
    if kind == "daily":
        day = (d.get("days") or {}).get(str(ref or ""))
        run = ((day or {}).get("runs") or {}).get(uid) if day else None
        if day and run and run.get("done"):
            text, c, t = _key_text("📅 Daily Quiz", str(ref), prof,
                                   day["qs"], run.get("answers") or {})
            return True, {"filename": f"StudentUp-Key-Daily-{ref}.txt", "text": text,
                          "correct": c, "total": t}
        # 🗄️ 3-day window tarvatha kuda archive nunchi key paper!
        arc = _archive_lookup(d, uid, "daily", ref)
        if arc:
            text, c, t = _key_text("📅 Daily Quiz", str(ref), prof,
                                   arc.get("qs") or [], arc.get("answers") or {})
            return True, {"filename": f"StudentUp-Key-Daily-{ref}.txt", "text": text,
                          "correct": c, "total": t}
        return False, "Daily quiz key dorakaledu."
    return False, "Unknown key type."


def exam_scorecard(members, token, exam_id):
    """📸 Personal Score Card PNG — exam finish chesina prati student ki
    (share cheyyadaniki). Winners certificate vere; idi andariki."""
    d = _load()
    uid = _sess(d, token)
    e = (d.get("exams") or {}).get(str(exam_id or ""))
    if not uid or not e:
        return None
    _refresh(d, _now())
    e = d["exams"][e["id"]]
    if exam_status(e, _now()) != "done":
        return None
    ent = (e.get("entries") or {}).get(uid)
    if not ent:
        return None
    view = _exam_view(e, members, uid, _now())
    prof = _profile(members, uid)
    total = len(e["qs"])
    pct = round(100 * ent.get("correct", 0) / max(1, total))
    try:
        from . import certcard
        return certcard.render_certificate(
            "🎓 " + e["title"],
            f"{prof.get('name', '')} · {prof.get('district', '')} · StudentUp",
            [{"rank": int(view["my"]["rank"] or 0),
              "name": prof.get("name", ""),
              "score": f"{ent.get('correct', 0)}/{total}",
              "pct": pct}],
            "StudentUp Score Card · Points: " + str(ent.get("pts", 0))
            + (f" · Top {view['my']['top_pct']}%" if view["my"].get("top_pct") else ""))
    except Exception:
        return None


# ------------------------------------------------------------- notices
@_locked
def add_notice(title, body, link="", goal=""):
    """📢 Exam updates/notifications (admin dashboard nunchi) — portal home
    lo + public /updates page lo kanipisthayi."""
    d = _load()
    n = {"id": secrets.token_hex(4),
         "title": str(title or "")[:120], "body": str(body or "")[:600],
         "link": str(link or "")[:300], "date": _today(),
         "goal": (goal if goal in GOALS else "")}
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
def practice_start(members, token, mode="smart", topic="", goal=""):
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
    # 🎯 20X practice modes (weak / speed / marathon / revenge / bookmarks)
    if not picked and mode == "weak":
        wk = [w["topic"].lower() for w in _profile(members, uid)["weak_topics"]]
        pool = _bank_pool()
        wp = [q for q in pool if (q.get("topic") or "").lower() in wk]
        if len(wp) >= 3:
            picked = random.Random(secrets.token_hex(4)).sample(
                wp, min(10, len(wp)))
    if not picked and mode == "revenge":
        try:
            from . import flags as _fl
            _ok_rev = _fl.enabled("revenge_mode")
        except Exception:
            _ok_rev = True
        if _ok_rev:
            arc = next((a for a in (d.get("archive") or [])
                        if a.get("uid") == uid), None)
            if arc:
                wrong = [q for i, q in enumerate(arc.get("qs") or [])
                         if (arc.get("answers") or {}).get(str(i), -1)
                         != q.get("answer_index")]
                if wrong:
                    picked = wrong[:10]
    if not picked and mode == "pyq":
        # 📜 PYQ-only drill (80X: goal unte aa exam strict PYQ pool)
        if goal in GOALS and GOALS[goal]["channels"]:
            pool = _goal_pyq_pool(goal)
            if len(pool) < 3:
                chans = GOALS[goal]["channels"]
                pool = [q for q in _bank_pool()
                        if q.get("source") == "pyq"
                        and q.get("channel") in chans]
        else:
            pool = [q for q in _bank_pool() if q.get("source") == "pyq"]
        if topic:
            tp = [q for q in pool
                  if (q.get("topic") or "").lower() == topic.lower()]
            pool = tp or pool
        if pool:
            picked = random.Random(secrets.token_hex(4)).sample(
                pool, min(10, len(pool)))
    if not picked and mode == "section":
        # 🧩 Sectional test: subject (gk/quant/reasoning/english) wise
        try:
            from . import flags as _fl
            _sec_on = _fl.enabled("sectional_tests")
        except Exception:
            _sec_on = True
        if _sec_on and topic:
            try:
                from . import blueprint as _bp
                pool = [q for q in _bank_pool()
                        if _bp.subject_of(q) == topic.lower()]
            except Exception:
                pool = []
            if len(pool) >= 3:
                picked = random.Random(secrets.token_hex(4)).sample(
                    pool, min(10, len(pool)))
    if not picked and mode == "bookmarks":
        picked = my_bookmarks(members, token)[:10]
    if not picked and mode == "ladder":
        # 🪜 Difficulty ladder: brain target level nunchi start chesi
        # paiki — easy->medium->hard step by step (confidence build).
        try:
            from . import brain as _brain
            from . import blueprint as _bp
            start = _brain.target_level(uid)
            rank = {"easy": 0, "medium": 1, "hard": 2}
            pool = _bank_pool()
            pool = sorted(pool, key=lambda q: (
                abs(rank.get(_bp.difficulty_of(q), 1) - rank.get(start, 1)),
                rank.get(_bp.difficulty_of(q), 1)))
            picked = pool[:10]
        except Exception:
            picked = []
    if not picked:
        pool = _bank_pool()
        if mode == "topic" and topic:
            tp = [q for q in pool if (q.get("topic") or "").lower() == topic.lower()]
            pool = tp or pool
        elif mode == "smart":
            # 🧠 Brain 3.0 adaptive: due revision + weak topics + level zone
            try:
                from . import brain as _brain
                from .question_bank import Bank as _Bank
                _rev = []
                try:
                    _bk = _Bank()
                    for r in (m.get("review") or []):
                        if str(r.get("due", "")) <= _today():
                            _q = _bk.by_id(r.get("qid"))
                            if _q:
                                _rev.append(_q)
                except Exception:
                    _rev = []
                picked = _brain.compose(pool, m, uid, n=10, review_qs=_rev)
            except Exception:
                picked = []
            if not picked:
                weak = [w["topic"] for w in
                        _profile(members, uid)["weak_topics"]]
                wp = [q for q in pool if (q.get("topic") or "").lower() in
                      [w.lower() for w in weak]]
                if len(wp) >= 5:
                    pool = wp
        if not picked:
            _n = 25 if mode == "marathon" else 10
            picked = random.Random(secrets.token_hex(4)).sample(
                pool, min(_n, len(pool))) if pool else []
    if not picked:
        return False, "Practice questions ready ga levu."
    run_id = "PR-" + secrets.token_hex(4)
    d.setdefault("practice", {})[run_id] = {
        "uid": uid, "mode": mode, "qs": [_snap(q) for q in picked],
        "answers": {}, "correct": 0, "created": _now().isoformat(),
        "per_q": 45 if mode == "speed" else 0}
    for k in list(d["practice"])[:-60]:
        d["practice"].pop(k, None)
    _save(d)
    _brain_info = None
    if mode == "smart":
        try:
            from . import brain as _brain
            _brain_info = _brain.profile_for(m, uid)
        except Exception:
            _brain_info = None
    return True, {"run_id": run_id, "mode": mode, "brain": _brain_info,
                  "per_q": 45 if mode == "speed" else 0,
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
    # 🔗 Similar follow-up: tappu ayithe same-topic vere question
    # try cheyyaniki (concept strong avuthundi).
    similar = None
    try:
        from . import flags as _fl
        _sim_on = _fl.enabled("similar_followup")
    except Exception:
        _sim_on = True
    if _sim_on and not correct:
        try:
            pool = [x for x in _bank_pool()
                    if (x.get("topic") or "").lower()
                    == (q.get("topic") or "").lower()
                    and x.get("id") != q.get("id")]
            if pool:
                sq = pool[0]
                similar = {"qid": sq.get("id"), "topic": sq.get("topic", ""),
                           "te": sq.get("q_te", ""), "en": sq.get("q_en", "")}
        except Exception:
            similar = None
    return True, {"correct": correct,
                  "answer_text": opts[q["answer_index"]] if 0 <= q["answer_index"] < len(opts) else "",
                  "explanation": q.get("explanation", ""),
                  "explanation_te": q.get("explanation_te", ""),
                  "similar": similar,
                  "answered": len(run["answers"]), "total_q": len(run["qs"]),
                  "score": run["correct"],
                  "done": len(run["answers"]) >= len(run["qs"])}


# ------------------------------------------------- previous papers (PYQ)
def paper_catalog() -> list:
    """📜 Attempt cheyyadaniki ready ga unna real PYQ paper sets.
    🛠️ FIX: min_q=5 valla 3-4 questions unna sets hide ayyevi — ippudu
    anni sets (≥3) kanipisthayi, size label tho (Full/Mini)."""
    try:
        from . import pyq as _pyq
        rows = _pyq.papers_index(min_q=3)
    except Exception:
        return []
    for r in rows:
        r["size"] = "full" if r["count"] >= 5 else "mini"
    return rows


def paper_progress(members, token):
    """📜 Student ge paper attempts: label -> {attempts, best, total}.

    🛠️ FIX: paper/board rows 'goal' field lona paper_label vastundi
    (GOALS key kaadu) — aa rows ni matrame paper progress ga count
    chestham (subject/mock veru, clear). Sight note: topic (very
    relevant)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return {}
    out = {}

    def _add(label, correct, total, date):
        e = out.setdefault(label, {"attempts": 0, "best": 0, "total": 0,
                                   "last": ""})
        if e["attempts"] == 0:
            e["last"] = date or ""
        e["attempts"] += 1
        e["best"] = max(e["best"], int(correct or 0))
        e["total"] = int(total or 0) or e["total"]

    # 🗄️ Archive-first (permanent): board 300-cap tarvatha kuda counts
    seen_refs = set()
    for a in (d.get("archive") or []):
        if a.get("uid") != uid or a.get("kind") != "paper":
            continue
        seen_refs.add(a.get("ref"))
        if a.get("title"):
            _add(a["title"], a.get("correct"), a.get("total"), a.get("date"))
    for r in reversed(d.get("mock_board") or []):
        if r.get("uid") != uid or r.get("run_id") in seen_refs:
            continue
        goal = (r.get("goal") or "").strip()
        if goal in GOALS or not goal:
            continue  # goal mocks kaavu — paper label goal ga velthundi
        _add(goal, r.get("correct"), r.get("total"), r.get("date"))
    return out


# ------------------------------------------- 20X advanced student tools
def exam_countdowns(members, token):
    """🗓️ EXAM COUNTDOWN COMMAND: goal exam ki enni rojulu unnayi +
    aa gap ki kavalsina daily pace (syllabus topics/day)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    prof = _profile(members, uid)
    goal = prof.get("goal") or "mixed"
    out = []
    for g, date_s in EXAM_DATES.items():
        try:
            days = (datetime.fromisoformat(date_s).date()
                    - _now().date()).days
        except Exception:
            continue
        out.append({"goal": g, "label": (GOALS.get(g) or {}).get("label", g),
                    "date": date_s, "days": days,
                    "mine": g == goal,
                    # 🛠️ FIX: negative days kuda 'Revision Phase'
                    # andi (order bug) — ippudu exam ayipothe done.
                    "phase": ("✅ Exam done — next cycle" if days < 0 else
                              "🔴 Final Sprint" if days <= 30 else
                              "🟠 Revision Phase" if days <= 90 else
                              "🟢 Foundation Phase")})
    out.sort(key=lambda r: (not r["mine"], r["days"]))
    return {"goal": goal, "list": out,
            "mine": next((r for r in out if r["mine"]), None)}


def my_syllabus(members, token):
    """🗺️ SYLLABUS TRACKER: goal syllabus graph lo student ekkada
    unnadu — subject-wise mastery + coverage % (real answers nunchi)."""
    try:
        from . import flags as _fl
        if not _fl.enabled("syllabus_tracker"):
            return None
    except Exception:
        pass
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    m = _member(members, uid)
    prof = _profile(members, uid)
    goal = prof.get("goal") or "mixed"
    chans = (GOALS.get(goal) or {}).get("channels") or []
    try:
        from .question_bank import Bank
        from . import syllabus as _sy
        bank = Bank()
        if chans:
            channel = chans[0]
        else:
            import collections as _c
            _cnt = _c.Counter(q.get("channel") for q in _bank_pool())
            channel = (_cnt.most_common(1) or [("CURRENT", 0)])[0][0]
        plan = _sy.plan(m, bank, channel)
        g = _sy.exam_graph(bank, channel)
        mastery = _sy.member_mastery(m)
        seen_topics = {t.lower() for t in (mastery.get("topics") or {})}
        total_topics = sum(len(v) for v in (g.get("subjects") or {}).values())
        cov_topics = 0
        subjects = []
        for subj, topics in (g.get("subjects") or {}).items():
            hit = sum(1 for t in topics if t.lower() in seen_topics)
            cov_topics += hit
            prow = next((r for r in plan["subjects"]
                         if r["subject"] == subj), {})
            subjects.append({
                "subject": subj, "topics": len(topics), "done_topics": hit,
                "weight": prow.get("exam_weight"),
                "mastery": prow.get("mastery"),
                "status": prow.get("status", "not started")})
        subjects.sort(key=lambda r: (-(r["weight"] or 0), r["subject"]))
        return {"goal": goal, "channel": channel, "exam": plan.get("exam"),
                "subjects": subjects,
                "coverage": round(100 * cov_topics / max(1, total_topics)),
                "topics_done": cov_topics, "topics_total": total_topics,
                "overall_mastery": plan.get("overall_mastery"),
                "weak_topics": plan.get("weak_topics"),
                "reviews_due": plan.get("reviews_due")}
    except Exception:
        return None


def coach_today(members, token):
    """🧑‍🏫 PERSONAL COACH: brain + syllabus + review kalipi ee roju
    student cheyyalsina ONE clear action plan (3 steps)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    prof = _profile(members, uid)
    steps = []
    if prof.get("review_due"):
        steps.append({"icon": "🔁", "action": "revision",
                      "text": f"Revision due {prof['review_due']} questions"
                              " — mundhu ive cheyyandi (marachipokunda)."})
    weak = (prof.get("weak_topics") or [])
    if weak:
        w = weak[0]
        steps.append({"icon": "🎯", "action": "weak",
                      "text": f"Weak topic: {w['topic']} ({w['accuracy']}%)"
                              " — Weak Drill start cheyyandi."})
    try:
        sy = my_syllabus(members, token)
    except Exception:
        sy = None
    if sy and sy.get("coverage", 0) < 100:
        nxt = next((s for s in sy["subjects"]
                    if s["done_topics"] < s["topics"]), None)
        if nxt:
            steps.append({"icon": "🗺️", "action": "syllabus",
                          "text": f"Syllabus coverage {sy['coverage']}% — "
                                  f"next: {nxt['subject']} topics cover "
                                  "cheyyandi."})
    cd = exam_countdowns(members, token) or {}
    mine = cd.get("mine")
    if mine and 0 <= mine["days"] <= 45:
        steps.append({"icon": "⏳", "action": "mock",
                      "text": f"{mine['label']} ki {mine['days']} rojule!"
                              " Daily oka full mock rayandi."})
    if not steps:
        steps.append({"icon": "🚀", "action": "smart",
                      "text": "Smart Practice oka round — mee level ki "
                              "saripoyina questions vastayi."})
    plan = today_plan(members, token) or {}
    return {"date": _today(), "readiness": plan.get("readiness"),
            "band": plan.get("band"), "steps": steps[:3],
            "weak_topics": weak, "exam_in": mine}


def goal_percentile(members, token):
    """📈 GOAL PERCENTILE (honest estimate): ee goal board lo student
    score migatha students tho poliste ekkada unnado."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    prof = _profile(members, uid)
    goal = prof.get("goal") or "mixed"
    label = (GOALS.get(goal) or {}).get("label", goal)
    rows = [r for r in (d.get("mock_board") or [])
            if r.get("goal") in (goal, label)]
    if not rows:
        return {"goal": goal, "percentile": None, "students": 0,
                "note": "Ee goal lo inka mock attempts levu — first meeru!"}
    best = {}
    for r in rows:
        u = r.get("uid")
        sc = int(r.get("correct") or 0)
        if u and sc > best.get(u, {}).get("correct", -1):
            best[u] = {"uid": u, "correct": sc}
    scores = sorted((v["correct"] for v in best.values()), reverse=True)
    mine = best.get(uid, {}).get("correct")
    if mine is None:
        return {"goal": goal, "percentile": None, "students": len(scores),
                "note": "Meeru ee goal mock inka rayaledu — okati rayandi!"}
    below = sum(1 for s in scores if s < mine)
    rank = 1 + sum(1 for s in scores if s > mine)
    return {"goal": goal, "percentile": round(100 * below / max(1, len(scores))),
            "rank": rank, "students": len(scores), "my_best": mine,
            "top": scores[0] if scores else 0}


def bookmark_toggle(members, token, qid):
    """🔖 Bookmark: question ni personal notebook lo save/remove."""
    d = _load()
    uid = _sess(d, token)
    if not uid or not qid:
        return False, "Session/question dorakaledu."
    # 🛠️ FIX: bank lo leni qid kuda save ayyedi (ghost bookmarks) —
    # remove toggle ki validation ledu, save ki matrame bank check.
    m0 = _member(members, uid)
    if str(qid) not in list(m0.get("bookmarks") or []):
        try:
            from .question_bank import Bank
            if Bank().by_id(str(qid)) is None:
                return False, "Aa question bank lo ledu."
        except Exception:
            pass
    m = _member(members, uid)
    marks = list(m.get("bookmarks") or [])
    if str(qid) in marks:
        marks = [x for x in marks if x != str(qid)]
        on = False
    else:
        marks = [str(qid)] + marks
        on = True
    m["bookmarks"] = marks[:100]
    _kv_save(members)
    return True, {"bookmarked": on, "count": len(marks)}


def my_bookmarks(members, token):
    """🔖 Saved questions list (bank nunchi fresh ga resolve)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return []
    m = _member(members, uid)
    try:
        from .question_bank import Bank
        bank = Bank()
    except Exception:
        return []
    out = []
    for qid in (m.get("bookmarks") or []):
        q = bank.by_id(qid)
        if q:
            s = _snap(q)
            s["bookmarked"] = True
            out.append(s)
    return out


def daily_mix():
    """🌈 DAILY MIX: ee roju daily paper lo subjects ela kalisayi
    (paper composition — student ki minh minh telustundi)."""
    d = _load()
    day = _daily_paper(d)
    import collections
    tc = collections.Counter((q.get("topic") or "general")
                             for q in day.get("qs") or [])
    return {"date": _today(), "total": len(day.get("qs") or []),
            "pyq": sum(1 for q in day.get("qs") or []
                       if q.get("source") == "pyq"),
            "topics": [{"topic": t, "n": n} for t, n in tc.most_common(8)]}


def worksheet_text(members, token):
    """🖨️ PRINTABLE WORKSHEET: ee roju daily paper print-friendly
    text ga (answers LAST lo — mundu rayandi, tarvatha check)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    prof = _profile(members, uid)
    day = _daily_paper(d)
    qs = day.get("qs") or []
    lines = ["🎓 StudentUp — Daily Worksheet", "=" * 44,
             f"Date: {_today()} · Student: {prof.get('name', '')}",
             f"Goal: {(GOALS.get(prof.get('goal') or '') or {}).get('label', prof.get('goal', ''))}",
             "Mundhu anni rayandi — answers chivarlo unnayi.", ""]
    letters = "ABCD"
    for i, q in enumerate(qs):
        opts, _perm = _display(q, f"{uid}:{_today()}:{i}")
        lines.append(f"Q{i + 1}. [{q.get('topic', 'general')}] {q.get('q_en', '')}")
        if q.get("q_te"):
            lines.append(f"    {q['q_te']}")
        for j, o in enumerate(opts[:4]):
            lines.append(f"    {letters[j]}) {o}")
        lines.append("")
    lines += ["-" * 44, "✅ ANSWER KEY (rayadam ayyaka chudandi)", ""]
    for i, q in enumerate(qs):
        opts, perm = _display(q, f"{uid}:{_today()}:{i}")
        # display position of the original correct option
        try:
            pos = perm.index(q["answer_index"])
        except Exception:
            pos = -1
        ans_txt = opts[pos] if 0 <= pos < len(opts) else ""
        lines.append(f"Q{i + 1}. {letters[pos] if 0 <= pos < 4 else '?'}"
                     f") {ans_txt}")
        if q.get("explanation"):
            lines.append(f"    💡 {q['explanation']}")
    lines += ["", "StudentUp · Roju worksheet = consistency = rank 🔥"]
    return True, {"filename": f"StudentUp-Worksheet-{_today()}.txt",
                  "text": "\n".join(lines), "total": len(qs)}


@_locked
def paper_start(members, token, exam, year="", paper=""):
    """📜 FULL previous-paper attempt: aa paper questions anni okka
    timer run la — score + review mock-submit tho ne (kind='paper')."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    cat = None
    for row in paper_catalog():
        if (row["exam"] == exam and str(row.get("year") or "") == str(year or "")
                and str(row.get("paper") or "") == str(paper or "")):
            cat = row
            break
    if not cat:
        return False, "Aa paper bank lo dorakaledu — vere paper try cheyyandi."
    try:
        from .question_bank import Bank
        bank = Bank()
        picked = [bank.by_id(qid) for qid in cat["ids"]]
        picked = [q for q in picked if q]
    except Exception:
        picked = []
    if len(picked) < 3:
        return False, "Paper questions ready ga levu."
    run_id = "PP-" + secrets.token_hex(4)
    d.setdefault("mocks", {})[run_id] = {
        "uid": uid, "goal": "paper", "kind": "paper",
        "paper_label": cat["label"],
        "qs": [_snap(q) for q in picked], "answers": {}, "done": False,
        "started": _now().isoformat()}
    for k in list(d["mocks"])[:-120]:
        d["mocks"].pop(k, None)
    _save(d)
    mins = max(5, round(len(picked) * 1.2))
    return True, {"run_id": run_id, "goal": "paper",
                  "label": f"📜 {cat['label']} — Full Paper",
                  "minutes": mins, "paper_label": cat["label"],
                  "questions": _serve(d["mocks"][run_id]["qs"], run_id, {})}


def today_plan(members, token):
    """🧭 TODAY'S SMART PLAN: student ki ee roju emi cheyyalo okka
    checklist (daily quiz, revision due, weak-topic practice, mock,
    brain readiness) — advanced lopala, easy bayata."""
    # 🛠️ FIX: mundhu rendu sarlu _load() (waste + race); okkate.
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    day = _daily_paper(d)
    prof = _profile(members, uid)
    m = _member(members, uid)
    run = (day.get("runs") or {}).get(uid)
    try:
        from . import brain as _brain
        bp = _brain.profile_for(m, uid)
    except Exception:
        bp = None
    tasks = [
        {"key": "daily", "icon": "📝", "label": "Daily Quiz",
         "done": bool(run and run.get("done")),
         "hint": "10 questions · points + streak"},
        {"key": "review", "icon": "🔁", "label": "Revision Due",
         "done": (bp or {}).get("reviews_due", 0) == 0,
         "count": (bp or {}).get("reviews_due", 0),
         "hint": "tappu chesina questions malli practice"},
        {"key": "smart", "icon": "🧠", "label": "Smart Practice",
         # 🛠️ FIX: mundhu eppudu False ('done' avvale) — ippudu ee roju
         # practice run start chesina done ga count avuthundi.
         "done": any(r.get("uid") == uid
                     and str(r.get("created", "")).startswith(_today())
                     for r in (d.get("practice") or {}).values()),
         "hint": "mee level + weak topics adaptive round"},
        {"key": "mock", "icon": "📄", "label": f"{prof['goal'].upper()} Mock Test",
         "done": any(r.get("uid") == uid and r.get("date") == _today()
                     for r in (d.get("mock_board") or [])),
         "hint": "15 Qs · timer · leaderboard"},
    ]
    return {"date": _today(), "readiness": (bp or {}).get("score"),
            "band": (bp or {}).get("band", ""),
            "tasks": tasks,
            "done_count": sum(1 for t in tasks if t["done"]),
            "total": len(tasks)}


# ------------------------------------------- 30X next-level intelligence
def study_plan(members, token, days=7):
    """📅 7-DAY STUDY PLAN: countdown + syllabus gaps + weak topics
    nunchi roju ki oka clear plan (topic focus + tasks)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    prof = _profile(members, uid)
    try:
        sy = my_syllabus(members, token) or {}
    except Exception:
        sy = {}
    weak = [w["topic"] for w in (prof.get("weak_topics") or [])]
    gaps = [s2["subject"] for s2 in (sy.get("subjects") or [])
            if s2.get("done_topics", 0) < s2.get("topics", 0)]
    focus_pool = weak + [g for g in gaps if g not in weak]
    if not focus_pool:
        focus_pool = ["Smart Practice"]
    cd = exam_countdowns(members, token) or {}
    mine = cd.get("mine") or {}
    out = []
    for i in range(int(days)):
        dt = (_now() + timedelta(days=i)).strftime("%Y-%m-%d")
        focus = focus_pool[i % len(focus_pool)]
        tasks = ["📝 Daily Quiz (10Q)"]
        if prof.get("review_due"):
            tasks.append("🔁 Revision due clear")
        tasks.append(f"🎯 Topic Practice: {focus}")
        if i in (2, 6):
            tasks.append("📄 Full Mock Test (timer)")
        if i == 6:
            tasks.append("📜 Previous Paper attempt")
        out.append({"date": dt, "day": i + 1, "focus": focus,
                    "tasks": tasks})
    return {"goal": prof.get("goal"), "exam_in": mine,
            "coverage": sy.get("coverage"), "days": out}


def next_topic(members, token):
    """🎯 NEXT BEST TOPIC: exam weight ekkuva + mastery takkuva unna
    topic — studentu 'next emi chadavaali?' ki okka answer."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    prof = _profile(members, uid)
    wk = prof.get("weak_topics") or []
    if wk:
        w = wk[0]
        return {"topic": w["topic"], "reason": "weak",
                "accuracy": w.get("accuracy"),
                "text": f"{w['topic']} lo accuracy {w.get('accuracy')}% — "
                        "idi strong chesthe marks periguthayi."}
    try:
        sy = my_syllabus(members, token) or {}
    except Exception:
        sy = {}
    for s2 in (sy.get("subjects") or []):
        if s2.get("done_topics", 0) < s2.get("topics", 0):
            return {"topic": s2["subject"], "reason": "syllabus-gap",
                    "text": f"{s2['subject']} syllabus inka "
                            f"{s2['topics'] - s2['done_topics']} topics "
                            "migilayi — okko topic practice cheyyandi."}
    return {"topic": "", "reason": "smart",
            "text": "Smart Practice — mee level ki saripadda questions."}


def attempt_analysis(members, token, run_id):
    """🔬 ATTEMPT ANALYSIS: archive attempt nunchi topic-wise
    breakdown + previous attempt tho improvement delta."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    mine = [a for a in (d.get("archive") or []) if a.get("uid") == uid]
    cur = next((a for a in mine if str(a.get("ref")) == str(run_id)), None)
    if not cur:
        return None
    topics = {}
    wrong_topics = {}
    for i, q in enumerate(cur.get("qs") or []):
        t = q.get("topic") or "general"
        topics.setdefault(t, {"topic": t, "total": 0, "correct": 0})
        topics[t]["total"] += 1
        ok = (cur.get("answers") or {}).get(str(i), -1) == q.get("answer_index")
        topics[t]["correct"] += int(ok)
        if not ok:
            wrong_topics[t] = wrong_topics.get(t, 0) + 1
    rows = sorted(topics.values(), key=lambda r: (r["correct"] / max(1, r["total"]), -r["total"]))
    for r in rows:
        r["accuracy"] = round(100 * r["correct"] / max(1, r["total"]))
    # previous same-kind attempt tho delta
    idx = mine.index(cur)
    prev = mine[idx + 1] if idx + 1 < len(mine) and mine[idx + 1].get("kind") == cur.get("kind") else None
    delta = None
    if prev:
        delta = int(cur.get("correct") or 0) - int(prev.get("correct") or 0)
    return {"title": cur.get("title"), "kind": cur.get("kind"),
            "date": cur.get("date"), "correct": cur.get("correct"),
            "total": cur.get("total"), "topics": rows,
            "weakest": rows[0]["topic"] if rows else "",
            "delta_vs_prev": delta,
            "wrong_topics": [t for t, _n in sorted(
                wrong_topics.items(), key=lambda kv: -kv[1])[:3]]}


def score_trend(members, token, limit=10):
    """📊 SCORE TREND: last attempts score graph (archive nunchi)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return []
    rows = [a for a in (d.get("archive") or []) if a.get("uid") == uid]
    out = []
    for a in reversed(rows[:limit]):
        tot = int(a.get("total") or 0)
        out.append({"date": a.get("date"), "title": a.get("title"),
                    "kind": a.get("kind"), "correct": a.get("correct"),
                    "total": tot,
                    "pct": round(100 * int(a.get("correct") or 0) / max(1, tot))})
    return out


def activity_calendar(members, token, days=14):
    """🗓️ ACTIVITY CALENDAR: last 14 rojula attempts + points."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return []
    led = {}
    for r in (d.get("ledger") or []):
        if r.get("uid") == uid:
            led[r["date"]] = led.get(r["date"], 0) + int(r.get("pts") or 0)
    att = {}
    for a in (d.get("archive") or []):
        if a.get("uid") == uid:
            att[a.get("date")] = att.get(a.get("date"), 0) + 1
    out = []
    for i in range(int(days) - 1, -1, -1):
        ds = (_now() - timedelta(days=i)).strftime("%Y-%m-%d")
        out.append({"date": ds, "pts": led.get(ds, 0),
                    "attempts": att.get(ds, 0),
                    "active": bool(led.get(ds) or att.get(ds))})
    return out


def score_forecast(members, token):
    """🔮 SCORE FORECAST (honest estimate): Brain ability + syllabus
    coverage nunchi next mock lo expected score range."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    try:
        from . import brain as _brain
        ab = _brain.ability(uid)
        theta = ab.get("theta", 1000)
        # logistic expectation vs median-difficulty paper (D=1000)
        p = 1.0 / (1.0 + 10 ** (-(theta - 1000) / 400.0))
    except Exception:
        p = 0.5
        ab = {}
    try:
        sy = my_syllabus(members, token) or {}
        cov = (sy.get("coverage") or 0) / 100.0
    except Exception:
        cov = 0.0
    expected = round(100 * (0.75 * p + 0.25 * cov))
    return {"expected_pct": expected,
            "low": max(0, expected - 8), "high": min(100, expected + 8),
            "theta": ab.get("theta"), "band": ab.get("band", ""),
            "answers": ab.get("answers", 0),
            "note": "Estimate matrame — Brain ability + syllabus "
                    "coverage nunchi. Ekkuva mocks rayyandi, forecast "
                    "accurate avuthundi."}


def pyq_trends(goal=""):
    """📈 PYQ TRENDS: previous papers lo ekkuva repeat ayye topics —
    edi padithe marks vastayo data chepthundi."""
    import collections
    pool = _bank_pool()
    chans = (GOALS.get(goal or "") or {}).get("channels") if goal in GOALS else None
    pyqs = [q for q in pool if q.get("source") == "pyq"
            and (not chans or q.get("channel") in chans)]
    tc = collections.Counter((q.get("topic") or "general") for q in pyqs)
    cc = collections.Counter((q.get("channel") or "") for q in pyqs)
    total = max(1, len(pyqs))
    return {"goal": goal or "all", "pyq_total": len(pyqs),
            "topics": [{"topic": t, "pyq": n,
                        "share": round(100 * n / total)}
                       for t, n in tc.most_common(8)],
            "channels": [{"channel": c, "pyq": n}
                         for c, n in cc.most_common(6)]}


def challenge_today(members, token):
    """🏆 CHALLENGE OF THE DAY: okka tough PYQ question, sariga
    answer chesthe bonus points. Roju okka chance."""
    try:
        from . import flags as _fl
        if not _fl.enabled("daily_challenge"):
            return None
    except Exception:
        pass
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    day = _today()
    ch = d.setdefault("challenge", {})
    entry = ch.get(day)
    if not entry:
        pool = [q for q in _bank_pool() if q.get("source") == "pyq"]
        if not pool:
            pool = _bank_pool()
        if not pool:
            return None
        q = __import__("random").Random("challenge-" + day).choice(pool)
        entry = {"q": _snap(q), "done": {}}
        ch[day] = entry
        for old in list(ch)[:-3]:
            ch.pop(old, None)
        _save(d)
    mine = (entry.get("done") or {}).get(uid)
    return {"date": day, "done": bool(mine),
            "correct": (mine or {}).get("correct"),
            "bonus": (mine or {}).get("bonus", 0),
            "question": None if mine else
            _serve([entry["q"]], f"CH:{uid}:{day}", {})[0]}


@_locked
def challenge_answer(members, token, choice):
    """Challenge answer — correct ayithe +20 bonus (ledger tho)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    day = _today()
    entry = (d.get("challenge") or {}).get(day)
    if not entry:
        return False, "Ee roju challenge ready avuthondi."
    if uid in (entry.get("done") or {}):
        return True, {"already": True}
    q = entry["q"]
    _opts, perm = _display(q, f"CH:{uid}:{day}:0")
    ch = int(choice)
    orig = perm[ch] if 0 <= ch < len(perm) else ch
    correct = orig == q["answer_index"]
    bonus = 0
    entry.setdefault("done", {})[uid] = {
        "correct": correct, "at": _now().isoformat()}
    if correct:
        bonus = 20
        m = _member(members, uid)
        m["points"] = int(m.get("points") or 0) + bonus
        _kv_save(members)
        try:
            led = d.setdefault("ledger", [])
            led.append({"uid": str(uid), "pts": bonus, "date": day})
        except Exception:
            pass
        entry["done"][uid]["bonus"] = bonus
    _save(d, flush=True)
    prof = _profile(members, uid)
    _award(members, uid, prof["name"], correct, q)
    return True, {"correct": correct, "bonus": bonus,
                  "answer_text": (q.get("options_en") or [""])[q["answer_index"]]
                  if 0 <= q["answer_index"] < len(q.get("options_en") or []) else "",
                  "explanation": q.get("explanation", "")}


def goal_board(members, goal, limit=10):
    """🏆 GOAL LEADERBOARD: aa goal mocks lo best scores."""
    d = _load()
    label = (GOALS.get(goal or "") or {}).get("label", goal)
    best = {}
    for r in (d.get("mock_board") or []):
        if r.get("goal") not in (goal, label):
            continue
        u = r.get("uid")
        if u and int(r.get("correct") or 0) > int(best.get(u, {}).get("correct", -1)):
            best[u] = r
    rows = sorted(best.values(),
                  key=lambda r: (-int(r.get("correct") or 0),
                                 -int(r.get("pts") or 0)))[:limit]
    return [{"name": r.get("name", ""), "district": r.get("district", ""),
             "correct": r.get("correct", 0), "total": r.get("total", 0),
             "pts": r.get("pts", 0)} for r in rows]


def revision_pack_text(members, token):
    """🎁 REVISION PACK: review queue + last wrongs nunchi printable
    revision pack (questions mundhu, key chivarlo)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    prof = _profile(members, uid)
    qs = my_bookmarks(members, token)[:10]
    try:
        from .question_bank import Bank
        bank = Bank()
        m = _member(members, uid)
        for r in (m.get("review") or []):
            q = bank.by_id(r.get("qid"))
            if q:
                qs.append(_snap(q))
    except Exception:
        pass
    # last attempt wrongs
    arc = next((a for a in (d.get("archive") or []) if a.get("uid") == uid), None)
    if arc:
        for i, q in enumerate(arc.get("qs") or []):
            if (arc.get("answers") or {}).get(str(i), -1) != q.get("answer_index"):
                qs.append(q)
    seen, uniq = set(), []
    for q in qs:
        if q.get("id") not in seen:
            seen.add(q.get("id"))
            uniq.append(q)
    qs = uniq[:20]
    if not qs:
        return False, "Revision pack ki questions levu — mundhu mock/practice cheyyandi."
    letters = "ABCD"
    lines = ["🎓 StudentUp — Revision Pack", "=" * 44,
             f"Student: {prof.get('name', '')} · Date: {_today()}",
             "Tappu chesina + save chesina questions — answers chivarlo.", ""]
    for i, q in enumerate(qs):
        opts, _perm = _display(q, f"RP:{uid}:{i}")
        lines.append(f"Q{i + 1}. [{q.get('topic', 'general')}] {q.get('q_en', '')}")
        if q.get("q_te"):
            lines.append(f"    {q['q_te']}")
        for j, o in enumerate(opts[:4]):
            lines.append(f"    {letters[j]}) {o}")
        lines.append("")
    lines += ["-" * 44, "✅ ANSWER KEY", ""]
    for i, q in enumerate(qs):
        opts, perm = _display(q, f"RP:{uid}:{i}")
        try:
            pos = perm.index(q["answer_index"])
        except Exception:
            pos = -1
        ans_txt = opts[pos] if 0 <= pos < len(opts) else ""
        lines.append(f"Q{i + 1}. {letters[pos] if 0 <= pos < 4 else '?'}"
                     f") {ans_txt}")
        if q.get("explanation"):
            lines.append(f"    💡 {q['explanation']}")
    return True, {"filename": f"StudentUp-RevisionPack-{_today()}.txt",
                  "text": "\n".join(lines), "total": len(qs)}


def portal_analytics(members):
    """📊 ADMIN: portal growth analytics (students, attempts, goals)."""
    import collections
    d = _load()
    mems = getattr(members, "members", None) or {}
    reg = [m for m in mems.values() if (m or {}).get("registered")]
    goals = collections.Counter((m or {}).get("exam_goal") or
                                (m or {}).get("goal") or "?"
                                for m in reg)
    arc = d.get("archive") or []
    today = _today()
    led_today = {r.get("uid") for r in (d.get("ledger") or [])
                 if r.get("date") == today}
    return {"students": len(reg),
            "attempts_total": len(arc),
            "attempts_today": sum(1 for a in arc if a.get("date") == today),
            "papers_attempts": sum(1 for a in arc if a.get("kind") == "paper"),
            "active_today": len(led_today),
            "goals": dict(goals.most_common(8)),
            "challenge_today": len(((d.get("challenge") or {}).get(today)
                                     or {}).get("done") or {}),
            "funnel": {
                "registered": len(reg),
                "attempted": len({a.get("uid") for a in arc}),
                "active_today": len(led_today),
                "attempt_rate": round(100 * len({a.get("uid") for a in arc})
                                      / max(1, len(reg)))},
            "archive_size": len(arc),
            "sessions_live": len(d.get("sessions") or {}),
            "pyq_gaps": _pyq_gaps_safe(),
            "attempt_kinds": dict(collections.Counter(
                a.get("kind") or "?" for a in arc).most_common(8)),
            "backup": _backup_safe()}


def _pyq_gaps_safe():
    try:
        from . import pyq as _pyq
        return _pyq.coverage_gaps()[:6]
    except Exception:
        return []


def _backup_safe():
    try:
        from . import backup as _bk
        return _bk.last_backup_info()
    except Exception:
        return {}


# ------------------------------------------- 40X expert intelligence
def section_stock(members, token):
    """🧩 SECTIONAL TESTS: goal pool lo subject-wise stock (real)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    prof = _profile(members, uid)
    chans = (GOALS.get(prof.get("goal") or "") or {}).get("channels") or []
    pool = _bank_pool(chans or None)
    try:
        from . import blueprint as _bp
        import collections
        cnt = collections.Counter(_bp.subject_of(q) for q in pool)
        pyq = collections.Counter(_bp.subject_of(q) for q in pool
                                  if q.get("source") == "pyq")
    except Exception:
        return None
    labels = {"gk": "📚 GK & Current Affairs", "quant": "🔢 Quant",
              "reasoning": "🧠 Reasoning", "english": "🔤 English"}
    return {"goal": prof.get("goal"),
            "sections": [{"subject": k, "label": labels.get(k, k),
                          "total": cnt.get(k, 0), "pyq": pyq.get(k, 0)}
                         for k in ("gk", "quant", "reasoning", "english")]}


def mistake_patterns(members, token):
    """📉 MISTAKE PATTERN ANALYZER: last attempts lo tappula pattern —
    concept gaps (repeat topic wrongs) vs slips (okkasari) vs skipped."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    import collections
    wrong = collections.Counter()
    skipped = 0
    total_wrong = 0
    for a in [x for x in (d.get("archive") or [])
              if x.get("uid") == uid][:3]:
        for i, q in enumerate(a.get("qs") or []):
            g = (a.get("answers") or {}).get(str(i))
            if g is None:
                skipped += 1
            elif g != q.get("answer_index"):
                wrong[q.get("topic") or "general"] += 1
                total_wrong += 1
    gaps = [{"topic": t, "wrongs": n} for t, n in wrong.most_common()
            if n >= 2]
    slips = [{"topic": t, "wrongs": n} for t, n in wrong.most_common()
             if n == 1]
    advice = []
    if gaps:
        advice.append(f"📚 Concept gap: {gaps[0]['topic']} — topic "
                      "practice tho concept clear cheyyandi.")
    if skipped >= 5:
        advice.append("⏭️ Skips ekkuva — time management meeda "
                      "Grand Mock practice cheyyandi.")
    if slips and not gaps:
        advice.append("⚡ Concepts okay, slips ekkuva — Speed mode lo "
                      "careful ga practice cheyyandi.")
    if not advice:
        advice.append("🚀 Pattern clean ga undi — Grand Mock ki vellandi!")
    return {"concept_gaps": gaps[:4], "slips": slips[:4],
            "skipped": skipped, "total_wrong": total_wrong,
            "advice": advice}


def retention_report(members, token):
    """🧠 RETENTION + REVISION FORECAST: review cards interval-wise +
    raboye 7 rojullo due ayye cards (forgetting-curve plan)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    m = _member(members, uid)
    cards = m.get("review") or []
    import collections
    by_int = collections.Counter(int(c.get("interval") or 0) for c in cards)
    forecast = []
    for i in range(7):
        ds = (_now() + timedelta(days=i)).strftime("%Y-%m-%d")
        forecast.append({"date": ds,
                         "due": sum(1 for c in cards
                                    if str(c.get("due", "")) == ds)})
    total = max(1, len(cards))
    score = round(100 * (by_int.get(7, 0) * 1.0 + by_int.get(3, 0) * 0.6
                         + by_int.get(0, 0) * 0.2) / total) if cards else 100
    return {"cards": len(cards), "due_today": forecast[0]["due"],
            "intervals": {"fresh_0d": by_int.get(0, 0),
                          "spaced_3d": by_int.get(3, 0),
                          "strong_7d": by_int.get(7, 0)},
            "retention_score": score,
            "forecast": forecast,
            "note": "7d interval cards = strong memory. Due cards daily "
                    "clear chesthe retention periguthundi."}


def weekly_goal(members, token):
    """🎯 WEEKLY GOAL: ee week 5 active days target progress."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    cal = activity_calendar(members, token, days=7) or []
    prof = _profile(members, uid)
    active = sum(1 for a in cal if a["active"])
    return {"active_days": active, "target": 5,
            "done": active >= 5, "days": cal,
            "streak": prof.get("streak", 0),
            "best_streak": prof.get("best_streak", 0),
            "text": (f"{active}/5 active days ee week — "
                     + ("🏆 Goal complete!" if active >= 5 else
                        f"inka {5 - active} rojulu active unte goal complete!"))}


def my_records(members, token):
    """🏆 PERSONAL RECORDS: best scores + totals (archive nunchi)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    mine = [a for a in (d.get("archive") or []) if a.get("uid") == uid]
    prof = _profile(members, uid)

    def pct(a):
        return round(100 * int(a.get("correct") or 0)
                     / max(1, int(a.get("total") or 0)))
    best = max(mine, key=pct, default=None)
    papers = [a for a in mine if a.get("kind") == "paper"]
    best_paper = max(papers, key=lambda a: int(a.get("correct") or 0),
                     default=None)
    return {"attempts": len(mine),
            "best_pct": pct(best) if best else None,
            "best_title": (best or {}).get("title"),
            "best_paper": ({"title": best_paper.get("title"),
                            "correct": best_paper.get("correct"),
                            "total": best_paper.get("total")}
                           if best_paper else None),
            "points": prof.get("points", 0),
            "accuracy": prof.get("accuracy", 0),
            "answered": prof.get("answered", 0),
            "streak": prof.get("streak", 0),
            "best_streak": prof.get("best_streak", 0)}


def test_series(members, token):
    """📚 TEST SERIES: goal mocks series progress (next test number)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    prof = _profile(members, uid)
    label = (GOALS.get(prof.get("goal") or "") or {}).get("label", "")
    mine = [a for a in (d.get("archive") or [])
            if a.get("uid") == uid and a.get("kind") in ("mock", "grand")
            and a.get("title") == label]
    pcts = [round(100 * int(a.get("correct") or 0)
                  / max(1, int(a.get("total") or 0))) for a in mine]
    return {"goal": prof.get("goal"), "label": label,
            "attempted": len(mine), "next_no": len(mine) + 1,
            "target": 10,
            "progress_pct": min(100, round(100 * len(mine) / 10)),
            "avg_pct": round(sum(pcts) / len(pcts)) if pcts else None,
            "best_pct": max(pcts) if pcts else None}


def district_goal_rank(members, token):
    """🏙️ DISTRICT x GOAL RANK: naa district lo naa goal rank."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    prof = _profile(members, uid)
    gb = goal_board(members, prof.get("goal") or "mixed", limit=100)
    mine = (prof.get("district") or "").lower()
    rows = []
    my_rank = None
    for i, r in enumerate(gb):
        if (r.get("district") or "").lower() == mine:
            rows.append(r)
            nm = _member(members, uid).get("name", "")
            if r.get("name") == nm and my_rank is None:
                my_rank = len(rows)
    return {"district": prof.get("district"), "goal": prof.get("goal"),
            "rows": rows[:10], "my_rank": my_rank,
            "students": len(rows)}


def set_lang(members, token, lang):
    """🌐 Display language preference: te | en | both."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    lang = str(lang or "both").lower()
    if lang not in ("te", "en", "both"):
        lang = "both"
    m = _member(members, uid)
    m["lang"] = lang
    _kv_save(members)
    return True, {"lang": lang}


def set_rival(members, token, ref_code):
    """🥊 RIVAL: ref-code tho oka student ni rival ga set — weekly
    points race."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    code = str(ref_code or "").strip().upper()
    rival = (d.get("refcodes") or {}).get(code)
    if not rival:
        for cand in (getattr(members, "members", None) or {}):
            if _ref_code(cand) == code:
                rival = cand
                break
    if not rival or str(rival) == str(uid):
        return False, "Rival dorakaledu — correct SU code ivvandi."
    m = _member(members, uid)
    m["rival"] = str(rival)
    _kv_save(members)
    rm = _member(members, rival)
    return True, {"rival": rm.get("name", "Rival"),
                  "district": rm.get("district", "")}


def rival_status(members, token):
    """🥊 RIVAL RACE: ee week points nenu vs rival."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    m = _member(members, uid)
    rival = m.get("rival")
    if not rival:
        return {"rival": None}
    start = _period_start("week", _now())
    pts = {}
    for r in (d.get("ledger") or []):
        if r.get("date", "") >= start and r.get("uid") in (str(uid), str(rival)):
            pts[r["uid"]] = pts.get(r["uid"], 0) + int(r.get("pts") or 0)
    rm = _member(members, rival)
    my_pts = pts.get(str(uid), 0)
    rv_pts = pts.get(str(rival), 0)
    return {"rival": rm.get("name", "Rival"),
            "rival_district": rm.get("district", ""),
            "my_pts": my_pts, "rival_pts": rv_pts,
            "leading": "you" if my_pts >= rv_pts else "rival",
            "diff": abs(my_pts - rv_pts)}


# ------------------------------------------- 50X perfection features
def search_practice(members, token, query):
    """🔍 QUESTION SEARCH: keyword tho bank lo vethiki ave questions
    practice run ga (student thanaku kavalsindi direct ga)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired — malli login avandi."
    qtext = str(query or "").strip().lower()
    if len(qtext) < 3:
        return False, "Kammi 3 letters tho search cheyyandi."
    pool = [q for q in _bank_pool()
            if qtext in (q.get("q_en") or "").lower()
            or qtext in (q.get("topic") or "").lower()
            or any(qtext in str(o).lower()
                   for o in (q.get("options_en") or []))]
    if not pool:
        return False, "Aa keyword tho questions dorakaledu — vere word try cheyyandi."
    picked = pool[:10]
    run_id = "PR-" + secrets.token_hex(4)
    d.setdefault("practice", {})[run_id] = {
        "uid": uid, "mode": "search", "qs": [_snap(q) for q in picked],
        "answers": {}, "correct": 0, "created": _now().isoformat(),
        "per_q": 0}
    for k in list(d["practice"])[:-60]:
        d["practice"].pop(k, None)
    _save(d)
    return True, {"run_id": run_id, "mode": "search", "per_q": 0,
                  "brain": None, "found": len(pool),
                  "questions": _serve(d["practice"][run_id]["qs"], run_id, {})}


def daily_review(members, token):
    """📅 DAILY REVIEW: ee roju daily quiz lo mee answers vs correct
    (done ayithe full, lekapothe answered matrame)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    day = _daily_paper(d)
    run = (day.get("runs") or {}).get(uid) or {}
    answers = run.get("answers") or {}
    rows = []
    for i, q in enumerate(day.get("qs") or []):
        if not run.get("done") and str(i) not in answers:
            continue
        given = answers.get(str(i), -1)
        opts = q.get("options_en") or []
        rows.append({"i": i, "topic": q.get("topic", ""),
                     "en": q.get("q_en", ""), "te": q.get("q_te", ""),
                     "given": given, "answer": q["answer_index"],
                     "right": given == q["answer_index"],
                     "given_text": opts[given] if 0 <= given < len(opts) else "—",
                     "answer_text": opts[q["answer_index"]]
                     if 0 <= q["answer_index"] < len(opts) else "",
                     "explanation": q.get("explanation", "")})
    return {"date": _today(), "done": bool(run.get("done")),
            "correct": run.get("correct", 0), "rows": rows}


def resume_latest(members, token):
    """▶️ RESUME: madhyalo aapina mock/practice akkadi nunchi malli —
    answers display positions tho saha (student ki zero rework)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    out = {"mock": None, "practice": None}
    for run_id, run in reversed(list((d.get("mocks") or {}).items())):
        if run.get("uid") == uid and not run.get("done"):
            disp = {}
            for i, q in enumerate(run["qs"]):
                if str(i) in (run.get("answers") or {}):
                    _o, perm = _display(q, f"{run_id}:{i}")
                    try:
                        disp[str(i)] = perm.index(run["answers"][str(i)])
                    except Exception:
                        pass
            out["mock"] = {"run_id": run_id, "kind": run.get("kind", "mock"),
                           "label": run.get("paper_label") or
                           (GOALS.get(run.get("goal") or "") or {}).get(
                               "label", "Mock Test"),
                           "questions": _serve(run["qs"], run_id,
                                               run.get("answers") or {}),
                           "answers": disp,
                           "answered": len(run.get("answers") or {})}
            break
    for run_id, run in reversed(list((d.get("practice") or {}).items())):
        if (run.get("uid") == uid
                and len(run.get("answers") or {}) < len(run.get("qs") or [])):
            out["practice"] = {"run_id": run_id, "mode": run.get("mode"),
                               "answered": len(run.get("answers") or {}),
                               "total": len(run.get("qs") or [])}
            break
    return out


def flag_question(members, token, qid, reason=""):
    """🚩 FLAG QUESTION: student tappu question ni report chesthe
    admin review queue loki (quality loop)."""
    d = _load()
    uid = _sess(d, token)
    if not uid or not qid:
        return False, "Session/question dorakaledu."
    flags = d.setdefault("qflags", [])
    if any(f.get("uid") == uid and f.get("qid") == str(qid)
           and f.get("date") == _today() for f in flags):
        return True, {"already": True}
    flags.insert(0, {"qid": str(qid), "uid": uid,
                     "reason": str(reason or "")[:120], "date": _today()})
    d["qflags"] = flags[:300]
    _save(d)
    return True, {"flagged": True}


def question_flags(limit=30):
    """🚩 Admin: flagged questions review list."""
    d = _load()
    try:
        from .question_bank import Bank
        bank = Bank()
    except Exception:
        bank = None
    out = []
    for f in (d.get("qflags") or [])[:limit]:
        q = bank.by_id(f.get("qid")) if bank else None
        out.append({**f, "question": (q or {}).get("q_en", "")[:120],
                    "topic": (q or {}).get("topic", "")})
    return out


def my_data_export(members, token):
    """📦 MY DATA: student thana full data (profile, attempts,
    bookmarks) JSON ga download — data meede thana hakku."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    prof = _profile(members, uid)
    m = _member(members, uid)
    data = {"exported": _now().isoformat(), "profile": prof,
            "bookmarks": m.get("bookmarks") or [],
            "review_cards": len(m.get("review") or []),
            "attempts": my_archive(members, token, limit=60),
            "papers": paper_progress(members, token)}
    return True, {"filename": f"StudentUp-MyData-{_today()}.json",
                  "text": __import__("json").dumps(
                      data, ensure_ascii=False, indent=2)}


def admin_students(members, query=""):
    """👩‍🎓 ADMIN: student search (name/phone/district) + top list."""
    mems = getattr(members, "members", None) or {}
    q = str(query or "").strip().lower()
    rows = []
    for uid, m in mems.items():
        if not (m or {}).get("registered"):
            continue
        if q and not (q in str(m.get("name", "")).lower()
                      or q in str(m.get("mobile", ""))
                      or q in str(m.get("district", "")).lower()):
            continue
        rows.append({"uid": str(uid), "name": m.get("name", ""),
                     "district": m.get("district", ""),
                     "mobile": m.get("mobile", ""),
                     "points": int(m.get("points") or 0),
                     "goal": m.get("exam_goal") or m.get("goal") or ""})
    rows.sort(key=lambda r: -r["points"])
    return rows[:20]


# ------------------------------------------- 60X sprint + series cert
def sprint_plan(members, token):
    """🔥 SPRINT MODE: exam daggara (<=14 rojulu) unte intensive plan —
    daily grand mock + revision + paper rotation."""
    try:
        from . import flags as _fl
        if not _fl.enabled("sprint_mode"):
            return None
    except Exception:
        pass
    cd = exam_countdowns(members, token) or {}
    mine = cd.get("mine") or {}
    days = mine.get("days")
    if days is None or days < 0 or days > 14:
        return {"active": False, "days": days, "label": mine.get("label", "")}
    tasks = ["🏛️ Grand Mock (50Q) — daily okati",
             "🔁 Revision due anni clear",
             "📜 Previous Paper — daily okka set",
             "📉 Mistake patterns chusi weak topic drill"]
    if days <= 3:
        tasks = ["📜 Previous Papers matrame (kotthavi vaddu)",
                 "🔁 Revision + formula/notes quick rounds",
                 "😴 Exam mundhu roju light ga — nidra mukhyam"]
    return {"active": True, "days": days, "label": mine.get("label", ""),
            "date": mine.get("date", ""), "tasks": tasks,
            "text": f"{mine.get('label', 'Exam')} ki {days} rojule — "
                    "sprint mode ON 🔥"}


def set_goal2(members, token, goal):
    """🎯 SECOND GOAL: rendu exams ki prepare ayye students kosam
    (primary goal maaradu, quick-access kosam goal2)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    if goal and goal not in GOALS:
        return False, "Invalid exam selection."
    m = _member(members, uid)
    if goal:
        m["goal2"] = goal
    else:
        m.pop("goal2", None)
    _kv_save_flush(members)
    return True, {"goal2": m.get("goal2", ""),
                  "label": (GOALS.get(goal) or {}).get("label", "")}


def weekly_report_text(members, token):
    """📲 WEEKLY REPORT (parents ki share cheyyadaniki): ee week
    progress neat text — WhatsApp share ready."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    prof = _profile(members, uid)
    cal = activity_calendar(members, token, days=7) or []
    pts_week = sum(a["pts"] for a in cal)
    active = sum(1 for a in cal if a["active"])
    tr = score_trend(members, token, limit=7)
    sr = test_series(members, token) or {}
    lines = [f"🎓 {prof.get('name', 'Student')} — Weekly Report (StudentUp)",
             f"🎯 Goal: {(GOALS.get(prof.get('goal') or '') or {}).get('label', prof.get('goal', ''))}",
             f"📅 Ee week: {active} active days · {pts_week} points earn chesaru",
             f"⭐ Total points: {prof.get('points', 0)} · 🔥 Streak: {prof.get('streak', 0)} days",
             f"🎯 Overall accuracy: {prof.get('accuracy', 0)}%"]
    if tr:
        last = tr[-1]
        lines.append(f"📊 Last test: {last.get('title', '')} — {last.get('pct', 0)}%")
    if sr.get("attempted"):
        lines.append(f"📚 Test Series: {sr['attempted']} tests ayyayi "
                     f"(avg {sr.get('avg_pct')}%)")
    weak = (prof.get("weak_topics") or [])
    if weak:
        lines.append(f"⚠️ Focus: {weak[0]['topic']} inka practice kavali")
    lines.append("💪 Consistency undi — ilaage continue chesthe rank pakka!")
    lines.append("— StudentUp (studentup.in)")
    return True, {"filename": f"StudentUp-Weekly-{_today()}.txt",
                  "text": "\n".join(lines)}


def series_certificate(members, token):
    """🏅 TEST SERIES CERTIFICATE: series lo 10 tests complete
    chesthe certificate PNG (certcard engine)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return None
    sr = test_series(members, token) or {}
    if int(sr.get("attempted") or 0) < 10:
        return None
    try:
        from . import certcard
        prof = _profile(members, uid)
        rows = [{"name": prof.get("name", "Student"), "rank": 1,
                 "score": f"{sr.get('attempted')} tests",
                 "pct": int(sr.get("avg_pct") or 0)}]
        return certcard.render_certificate(
            "TEST SERIES COMPLETE",
            f"StudentUp {sr.get('label', '')} — 10-Test Series",
            rows,
            footer=f"{prof.get('name', '')} · Avg {sr.get('avg_pct')}% "
                   f"· Best {sr.get('best_pct')}% · studentup.in")
    except Exception:
        return None


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
    # 🛠️ FIX (R3): 'correct'/'total' rendu student-count ga undedi
    # (API misleading) — ippudu honest fields matrame.
    rows = [{"name": dnm, "district": dnm, "students": cnt[dnm],
             "pts": pts[dnm]}
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
    # 🛠️ FIX: winners announce tie-break (joined_at) ikkada kuda —
    # lekunte tie lo certificate rank != announced winners rank.
    rows_all = sorted((r for r in e.get("entries", {}).values()
                       if r.get("correct", 0) > 0),
                      key=lambda r: (-r.get("correct", 0), -r.get("pts", 0),
                                     r.get("joined_at", "")))
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


# ------------------------------------------- 70X advanced student tools
def _flag_on(name):
    try:
        from . import flags as _fl
        return _fl.enabled(name)
    except Exception:
        return True


def _focus_stats(m):
    """⏱️ Focus minutes (member['focus_log'] = {date: minutes} — daylog
    [answered, correct] list shape ni disturb cheyyakunda separate)."""
    fl = (m or {}).get("focus_log") or {}
    week = 0
    for i in range(7):
        day = (_now() - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            week += int(fl.get(day) or 0)
        except Exception:
            pass
    return {"today_min": int(fl.get(_today()) or 0), "week_min": week}


def log_study(members, token, minutes):
    """⏱️ FOCUS TIMER: oka study session complete ayyaka minutes log
    chesthundi (1–240 clamp). Daily/weekly focus stats return."""
    if not _flag_on("focus_timer"):
        return False, "Focus timer off chesaru."
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    try:
        minutes = int(float(minutes))
    except Exception:
        minutes = 0
    minutes = max(1, min(240, minutes))
    m = _member(members, uid)
    fl = m.setdefault("focus_log", {})
    fl[_today()] = int(fl.get(_today()) or 0) + minutes
    for old in sorted(fl)[:-14]:
        fl.pop(old, None)
    _kv_save_flush(members)
    return True, {"logged": minutes, **_focus_stats(m)}


def mistake_notebook(members, token):
    """📕 MISTAKE NOTEBOOK: student tappu chesina questions anni (archive
    attempts + practice runs nunchi, dedupe) correct answer + bilingual
    explanation tho downloadable text."""
    if not _flag_on("mistake_notebook"):
        return False, "Mistake notebook off chesaru."
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    wrong = {}

    def _scan(qs, answers):
        for si, a in (answers or {}).items():
            try:
                i = int(si)
            except Exception:
                continue
            if not (0 <= i < len(qs or [])):
                continue
            q = qs[i]
            if a != q.get("answer_index"):
                key = (q.get("q_en") or "")[:120]
                if key and key not in wrong:
                    wrong[key] = q

    for a in (d.get("archive") or []):
        if a.get("uid") == uid:
            _scan(a.get("qs"), a.get("answers"))
    for run in (d.get("practice") or {}).values():
        if run.get("uid") == uid:
            _scan(run.get("qs"), run.get("answers"))
    rows = list(wrong.values())[:100]
    prof = _profile(members, uid)
    lines = [f"📕 {prof.get('name', 'Student')} — Mistake Notebook (StudentUp)",
             f"📅 {_today()} · Total mistakes: {len(rows)}",
             "Ee questions malli revise cheyyandi — correct answer + "
             "explanation tho unnaayi.", ""]
    if not rows:
        lines.append("🎉 Inka mistakes levu — attempts ayyaka tappu aina "
                     "questions ikkada automatic ga add avthayi!")
    by_topic = {}
    for q in rows:
        by_topic.setdefault(q.get("topic") or "general", []).append(q)
    n = 0
    for topic in sorted(by_topic):
        lines.append(f"—— {topic} ——")
        for q in by_topic[topic]:
            n += 1
            opts = q.get("options_en") or []
            ai = int(q.get("answer_index") or 0)
            lines.append(f"{n}. {q.get('q_en', '')}")
            if 0 <= ai < len(opts):
                lines.append(f"   ✅ Correct: {opts[ai]}")
            if q.get("explanation"):
                lines.append(f"   💡 {q['explanation']}")
            if q.get("explanation_te"):
                lines.append(f"   💡 {q['explanation_te']}")
            lines.append("")
    return True, {"filename": f"StudentUp-Mistakes-{_today()}.txt",
                  "text": "\n".join(lines), "count": len(rows)}


def notices_for(members, token, limit=20):
    """📢 NOTICE CENTER: student goal ki sambandinchina notices anni
    (home lo 3 matrame kanipisthayi — ikkada full list)."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    goal = _profile(members, uid).get("goal")
    out = [n for n in list_notices(limit)
           if not n.get("goal") or n.get("goal") == goal]
    return True, {"notices": out}


def goal_hub(members, token, goal):
    """🎓 EXAM-WISE HUB: okka goal ki PYQ stock, repeat topics, paper
    sets, mee attempts/best mariyu next best action — exam-wise quiz
    entry point."""
    if not _flag_on("goal_hub"):
        return False, "Goal hub off chesaru."
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    if goal not in GOALS:
        return False, "Invalid exam selection."
    stock = exam_stock().get(goal, {"pyq": 0, "total": 0})
    chans = set(GOALS[goal].get("channels") or [])
    papers = [r for r in paper_catalog()
              if not chans or chans & set(r.get("channels") or [])]
    mine = [r for r in (d.get("mock_board") or [])
            if r.get("uid") == uid and r.get("goal") == goal]
    best = max((round(100 * (r.get("correct", 0) / max(1, r.get("total", 0))))
                for r in mine), default=0)
    if not mine:
        nxt = "Meeru inka ee exam mock rayaledu — first mock start cheyyandi!"
    elif best < 50:
        nxt = "Weak topics drill + PYQ practice tho score penchandi."
    elif best < 75:
        nxt = "Sectional tests + maroka mock — 75%+ target!"
    else:
        nxt = "🏛️ Grand Mock (50Q) tho full-exam simulation ki ready!"
    trends = pyq_trends(goal)
    _ch_stock = []
    for _ch in sorted(chans):
        _cp = _bank_pool([_ch])
        _ch_stock.append({"channel": _ch, "total": len(_cp),
                          "pyq": sum(1 for q in _cp
                                     if q.get("source") == "pyq")})
    return True, {"goal": goal, "label": GOALS[goal].get("label", goal),
                  "pyq": stock.get("pyq", 0), "total": stock.get("total", 0),
                  "pyq_exam": len(_goal_pyq_pool(goal)),
                  "channels_stock": _ch_stock,
                  "papers": len(papers), "attempts": len(mine), "best": best,
                  "paper_labels": [r["label"] for r in papers[:5]],
                  "topics": (trends or {}).get("topics", [])[:5],
                  "next": nxt}


def set_exam_reminder(members, token, exam_id, on=True):
    """🔔 LIVE EXAM REMINDER: exam start ki mundhu interest mark —
    state live rows lo 'remind' flag ga reflect avthundi."""
    d = _load()
    uid = _sess(d, token)
    if not uid:
        return False, "Session expired."
    rem = d.setdefault("exam_reminds", {})
    uids = rem.setdefault(str(exam_id or ""), [])
    if on and uid not in uids:
        uids.append(uid)
    if not on and uid in uids:
        uids.remove(uid)
    _save(d)
    return True, {"exam_id": str(exam_id or ""), "remind": uid in uids}
