#!/usr/bin/env python3
"""260X/270X — STATELESS CLIENT CORE (zero-server-storage student state).
270X adds: server-signed claims (typ="c"), single-use attempt nonces,
per-question anti-farm awards and the No-VPS shared-host routes.
/api/portal/st270* = register/view/answer/attempt/claims-verify.

Meeru cheppinattu: student state mottam client daggara (signed token
lo) untundi; server VERIFY + COMPUTE matrame chesthundi — portal
store loki emi rayadu. Token = `su1.<b64url(json)>.<hmac-sha256>`;
server secret tho sign chestham, kadile signature/phrasing
reject (tamper-proof by construction).

State token (typ="u", rolling 30d):
    profile {name, phone, district, goal, uid:"w"+phone}
    prog    {answers, correct, points, streak, best_streak,
             topics:{t:{total,correct}}, seen:[qid...], last_day}

Attempt token (typ="a", 2h): qids + goal + started — server keeps
nothing; submit decode+grade+re-issue state token slender result.

Security notes (honest limits): points are self-asserted inside a
SIGNED payload — a student cannot forge points without the server
secret (HMAC) — kani "server-verify-only" valla duplicate-replay
(nuve old token malli use) cheyyochu; anduke 270X nunchi
leaderboards/prizes kosam server-signed claims ("c" tokens) unnaayi —
server maatrame issue chesthundi, verify kuda server ee chesthundi.
Learning features (daily quiz/mocks/reports) full stateless lu
saripothayi; ranks/prizes ki claims mandatory.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

_PREFIX = "su1"
_STATE_TTL = 30 * 24 * 3600
_ATTEMPT_TTL = 2 * 3600
_DEV_SECRET = "studentup-dev-secret-change-me"
_CLAIM_TTL270 = 7 * 24 * 3600  # 🧾 270X: server claims live 7 days


def _secret(secret=None) -> tuple[str, bool]:
    s = secret or os.environ.get("PORTAL_STATELESS_SECRET", "")
    if s:
        return s, False
    return _DEV_SECRET, True


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256)
    return _b64e(mac.digest())


def encode_token(claims: dict, secret=None, ttl: int = _STATE_TTL) -> str:
    sec, _ = _secret(secret)
    now = int(time.time())
    body = dict(claims)
    body.setdefault("iat", now)
    body["exp"] = now + ttl
    pb = _b64e(json.dumps(body, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8"))
    return f"{_PREFIX}.{pb}.{_sign(pb, sec)}"


def decode_token(token, secret=None, want_typ: str | None = None):
    """Verify signature + expiry (and optional typ). None on any failure."""
    try:
        sec, _ = _secret(secret)
        pre, pb, sig = str(token or "").split(".")
        if pre != _PREFIX:
            return None
        if not hmac.compare_digest(_sign(pb, sec), sig):
            return None
        body = json.loads(_b64d(pb).decode("utf-8"))
        if float(body.get("exp", 0) or 0) < time.time():  # float/int exp both ok
            return None
        if want_typ and body.get("typ") != want_typ:
            return None
        return body
    except Exception:
        return None


# --------------------------------------------------------------- bank access
def _bank():
    from . import question_bank  # lazy: keeps import graph simple
    return question_bank.load_bank()


def _goal_qs(goal: str):
    chans = set((_goals().get(goal) or {}).get("channels") or [])
    return [q for q in _bank()
            if not chans or q.get("channel") in chans]


def _subject(topic: str) -> str:
    try:
        from .syllabus import subject_of_topic
        return subject_of_topic(topic or "general")
    except Exception:
        return "general"


def _norm_topic(topic) -> str:
    """One topic key everywhere: trimmed + lowercase (bank 'Algebra'
    and member 'algebra' must be the SAME topic for mastery math)."""
    return " ".join(str(topic or "general").split()).lower()


def _district_ok(district: str) -> bool:
    try:
        from . import districts as _D
        names = [x[0] for x in _D.AP_DISTRICTS + _D.TS_DISTRICTS]
        return district in names
    except Exception:
        return bool(district)


def _goals():
    try:
        from .portal import GOALS
        return GOALS
    except Exception:
        return {}


def _display(q, seed, lang="both"):
    """Per-student shuffled options (portal._display tho same rule):
    returns (display_texts, perm); grading maps display idx -> orig."""
    try:
        from .portal import _display as _pd
        return _pd(q, seed, lang=lang)
    except Exception:
        opts = list(q.get("options_en") or [])
        return opts, list(range(len(opts)))


# ------------------------------------------------------------ server claims
# 🧪 270X regression suite: tests/test_advanced270.py (17+ pins).
def issue_claim(state_token, kind, detail, secret=None):
    """🧾 270X: server-signed claim (prize/rank/leaderboard receipt).

    The Stateless State token is student-carried, so anything whose
    value must be trustworthy (rank, prize, certificate) comes back
    as one of these short-lived claims signed by THIS server.  The
    claim binds uid + kind + an issuer timestamp; callers keep/verify
    them server-side later without trusting the state token."""
    st = decode_token(state_token, secret, want_typ="u")
    if not st:
        return None
    claims = {"typ": "c", "uid": st.get("uid"),
              "profile": st.get("profile") or {},
              "claim": str(kind or "")[:40],
              "detail": str(detail or "")[:200]}
    return encode_token(claims, secret, ttl=_CLAIM_TTL270)


def verify_claim(claim_token, secret=None, want_kind=None):
    """Verify a 270X server claim; returns claims dict or None."""
    c = decode_token(claim_token, secret, want_typ="c")
    if not c:
        return None
    if want_kind and c.get("claim") != want_kind:
        return None
    return c


def progress_summary(token, secret=None):
    """📊 270X: client-carried progress summary ("verified": False).

    Points here are student-carried (a stale token can be replayed),
    so leaderboards/prizes MUST only trust server-signed claims
    (typ="c"), never this summary."""
    s = decode_token(token, secret, want_typ="u")
    if not s:
        return None
    p, pr = s.get("profile") or {}, s.get("prog") or {}
    _raw_topics = pr.get("topics")
    topics = {}
    if isinstance(_raw_topics, dict):
        for _t270, _v270 in _raw_topics.items():
            topics[_norm_topic(_t270)] = _v270
    # legacy rows with non-dict values are filtered below.


    weak = sorted(
        ({"topic": t, "total": int((v or {}).get("total", 0) or 0),
          "correct": int((v or {}).get("correct", 0) or 0),
          "accuracy": round(100 * int((v or {}).get("correct", 0) or 0)
                            / max(1, int((v or {}).get("total", 0)
                                         or 0)))}
         for t, v in topics.items()
         if isinstance(v, dict) and (v.get("total") or 0)),
        key=lambda r: (r["accuracy"], -r["total"]))[:3]
    return {"uid": s.get("uid"), "name": p.get("name", ""),
            "district": p.get("district", ""), "goal": p.get("goal", ""),
            "points": pr.get("points", 0),
            "answers": pr.get("answers", 0),
            "correct": pr.get("correct", 0),
            "accuracy": round(100 * pr.get("correct", 0)
                              / max(1, pr.get("answers", 0))),
            "streak": pr.get("streak", 0),
            "best_streak": pr.get("best_streak", 0),
            "weak_topics": weak, "topics_seen": len(topics),
            "verified": False}


def _bump_topic(pr, topic, ok_ans):
    """Fold one graded answer into pr["topics"] under the normalized
    key; legacy mixed-case rows (260X tokens) merge into it."""

    t = _norm_topic(topic)
    raw_topics = pr.get("topics")
    topics = raw_topics if isinstance(raw_topics, dict) else {}
    pr["topics"] = topics
    for k in [k for k in topics if _norm_topic(k) == t and k != t]:
        old = topics.pop(k)
        row = topics.setdefault(t, {"total": 0, "correct": 0})
        row["total"] += old.get("total", 0)
        row["correct"] += old.get("correct", 0)
    row = topics.setdefault(t, {"total": 0, "correct": 0})
    row["total"] += 1
    row["correct"] += int(ok_ans)
    return row


# --------------------------------------------------------------- public API
def register_student(name, phone, district, goal, secret=None):
    """Validate + issue the zero-storage registration token."""
    name = " ".join(str(name or "").split())[:40]
    phone = "".join(c for c in str(phone or "") if c.isdigit())[-10:]
    district = str(district or "").strip()[:30]
    goal = str(goal or "").strip().lower()
    if len(name) < 2:
        return None, "Student name kavali (min 2 letters)."
    if len(phone) != 10:
        return None, "10-digit mobile number kavali."
    if not district:
        return None, "District select cheyyandi."
    if not _district_ok(district):
        return None, "Mee district select cheyyandi."
    if goal not in _goals():
        goal = "mixed"
    claims = {
        "typ": "u", "uid": "w" + phone,
        "profile": {"name": name, "phone": phone, "uid": "w" + phone,
                    "district": district, "goal": goal},
        "prog": {"answers": 0, "correct": 0, "points": 0, "streak": 0,
                 "best_streak": 0, "topics": {}, "seen": [], "last_day": ""},
    }
    return encode_token(claims, secret), None


def public_view(token, secret=None):
    s = decode_token(token, secret, want_typ="u")
    if not s:
        return None
    p, pr = s.get("profile") or {}, s.get("prog") or {}
    _ans = pr.get("answers") or pr.get("answered") or 0
    acc = round(100 * pr.get("correct", 0) / max(1, _ans))
    _, dev = _secret(secret)
    return {"profile": p, "points": pr.get("points", 0),
            "answers": _ans, "correct": pr.get("correct", 0),
            "accuracy": acc, "streak": pr.get("streak", 0),
            "best_streak": pr.get("best_streak", 0),
            "topics_seen": len(pr.get("topics") or {}),
            "dev_secret": dev,
            "token_exp": s.get("exp")}


def _reissue(state, secret):
    state = {k: v for k, v in state.items() if k not in ("iat", "exp")}
    return encode_token(state, secret)


def record_answer(token, qid, choice_index, secret=None, today=None,
                  idx=0):
    """Grade one DISPLAY-index answer; return (new_token, result).

    Serves shuffle options per student (portal._display rule). The
    pick we receive is the DISPLAY index, so recompute the same
    shuffle and map display -> original before grading."""
    s = decode_token(token, secret, want_typ="u")
    if not s:
        return None, {"ok": False, "error": "invalid/expired token"}
    q = next((x for x in _bank() if str(x.get("id")) == str(qid)), None)
    if q is None:
        return None, {"ok": False, "error": "question not found"}
    pr = s.setdefault("prog", {})
    today = today or time.strftime("%Y-%m-%d")
    try:
        _pick = int(choice_index)
    except (TypeError, ValueError):
        return None, {"ok": False, "error": "invalid choice"}
    _opts, _perm = _display(q, f"{s.get('uid', '')}:{today}:{int(idx)}")
    _orig = _perm[_pick] if 0 <= _pick < len(_perm) else _pick
    ok_ans = _orig == int(q.get("answer_index", -1))
    if pr.get("last_day") != today:         # new day -> streak decides
        from datetime import date, timedelta
        yday = (date.today() - timedelta(days=1)).isoformat()
        pr["streak"] = (pr.get("streak", 0) + 1) \
            if pr.get("last_day") == yday else 1
        pr["last_day"] = today
    raw_seen = pr.get("seen")
    _seen270 = [str(x) for x in raw_seen] if isinstance(
        raw_seen, list) else []
    pr["seen"] = _seen270
    _first270 = str(qid) not in _seen270
    if _first270:   # 🛡️ 270X: stats count once per question (anti-farm parity)
        pr["answers"] = pr.get("answers", 0) + 1
    gained = 0
    if ok_ans and _first270:   # 🛡️ 270X: one award per question (portal anti-farm parity)
        pr["correct"] = pr.get("correct", 0) + 1
        gained = 10 + (5 if pr.get("streak", 0) >= 3 else 0)  # portal parity
        pr["points"] = pr.get("points", 0) + gained
    pr["best_streak"] = max(pr.get("best_streak", 0), pr.get("streak", 0))
    if _first270:
        _bump_topic(pr, q.get("topic"), ok_ans)
    seen = _seen270
    if str(qid) not in seen:
        seen.append(str(qid))
        del seen[:-200]                     # bounded payload
    pr["seen"] = seen
    topics = (pr.get("topics") or {}) if isinstance(
        pr.get("topics"), dict) else {}
    pr["topics"] = topics
    if len(topics) > 60:                    # keep token size sane
        for k in sorted(topics,
                        key=lambda k: ((topics[k] or {}).get(
                            "total", 0)
                            if isinstance(topics.get(k), dict)
                            else 0))[:len(topics) - 60]:
            topics.pop(k, None)
    return _reissue(s, secret), {
        "ok": True, "already": not _first270, "correct": ok_ans,
        "correct_index": int(q.get("answer_index", -1)),
        "correct_display": (_perm.index(int(q.get("answer_index", -1)))
                            if int(q.get("answer_index", -1)) in _perm else -1),
        "points_gained": gained, "points": pr["points"],
        "streak": pr["streak"], "accuracy":
        round(100 * pr["correct"] / max(1, pr["answers"]))}


def daily_quiz(token, secret=None, n=10, today=None):
    """Today's deterministic set for this student (pure; no writes).

    Returns {"date", "goal", "questions": [...]} — options shuffled
    per student (seed uid:today:i); never carries the answer index."""
    s = decode_token(token, secret, want_typ="u")
    if not s:
        return None
    today = today or time.strftime("%Y-%m-%d")
    prof = s.get("profile") or {}
    prog = s.get("prog") or {}
    pool = _goal_qs(prof.get("goal", ""))
    seen = set(prog.get("seen") or [])
    fresh = [q for q in pool if str(q.get("id")) not in seen] or pool
    seed = hashlib.sha256(f"{today}|{s.get('uid','')}".encode()).digest()
    order = sorted(range(len(fresh)),
                   key=lambda i: hashlib.sha256(seed + str(i).encode()).digest())
    picked = [fresh[i] for i in order[:max(1, min(n, len(fresh)))]]
    out = []
    for i, q in enumerate(picked):
        opts, _perm = _display(q, f"{s.get('uid', '')}:{today}:{i}")
        out.append({"i": i, "id": q.get("id"), "qid": q.get("id"),
                    "q_en": q.get("q_en", ""), "q_te": q.get("q_te", ""),
                    "en": q.get("q_en", ""), "te": q.get("q_te", ""),
                    "topic": q.get("topic", ""),
                    "channel": q.get("channel", ""),
                    "subject": _subject(q.get("topic", "")),
                    "source": q.get("source") or "",
                    "exam": q.get("exam") or "",
                    "year": q.get("year") or "",
                    "options": opts, "answered": False})
    return {"date": today, "goal": prof.get("goal", ""),
            "questions": out}


def start_attempt(token, secret=None, n=15):
    s = decode_token(token, secret, want_typ="u")
    if not s:
        return None, "invalid/expired token"
    pool = _goal_qs((s.get("profile") or {}).get("goal", ""))
    if not pool:
        return None, "question pool empty"
    seed = hashlib.sha256(f"att|{s.get('uid','')}|{int(time.time())}".encode()).digest()
    order = sorted(range(len(pool)),
                   key=lambda i: hashlib.sha256(seed + str(i).encode()).digest())
    picked = [pool[i] for i in order[:max(1, min(n, len(pool)))]]
    import secrets as _sec270
    claims = {"typ": "a", "uid": s.get("uid"),
              "goal": (s.get("profile") or {}).get("goal", ""),
              "nonce": _sec270.token_hex(6),
              "qids": [str(q.get("id")) for q in picked]}
    served = []
    for i, q in enumerate(picked):
        opts, _perm = _display(q, f"sl-att:{s.get('uid', '')}:{i}")
        served.append({"i": i, "id": q.get("id"), "qid": q.get("id"),
                       "q_en": q.get("q_en", ""), "q_te": q.get("q_te", ""),
                       "en": q.get("q_en", ""), "te": q.get("q_te", ""),
                       "topic": q.get("topic", ""),
                       "channel": q.get("channel", ""),
                       "subject": _subject(q.get("topic", "")),
                       "source": q.get("source") or "",
                       "exam": q.get("exam") or "",
                       "year": q.get("year") or "",
                       "options": opts, "answered": False})
    return encode_token(claims, secret, ttl=_ATTEMPT_TTL), {
        "questions": served, "minutes": max(5, len(picked))}


def submit_attempt(state_token, attempt_token, answers: dict, secret=None):
    """Grade the attempt (DISPLAY indices, mapped via _display).

    Folds stats into the state and issues a fresh token. Single-use."""
    st = decode_token(state_token, secret, want_typ="u")
    at = decode_token(attempt_token, secret, want_typ="a")
    if not st or not at:
        return None, {"ok": False, "error": "invalid/expired token"}
    _nonce270 = at.get("nonce") or ""
    _used270 = (st.get("prog") or {}).get("used_attempts") or []
    if _nonce270 and _nonce270 in _used270:
        return None, {"ok": False,
                      "error": "attempt already submitted"}
    by_id = {str(q.get("id")): q for q in _bank()}
    pr = st.setdefault("prog", {})
    sections, correct, wrong = {}, 0, 0
    review = []
    for _pos, qid in enumerate(at.get("qids") or []):
        q = by_id.get(str(qid))
        if q is None:
            continue
        pick = (answers or {}).get(str(qid), (answers or {}).get(qid, -1))
        try:
            _p = int(pick)
        except (TypeError, ValueError):
            _p = -1
        _opts, _perm = _display(q, f"sl-att:{at.get('uid', '')}:{_pos}")
        _orig = _perm[_p] if 0 <= _p < len(_perm) else _p
        ok_ans = _orig == int(q.get("answer_index", -1))
        correct += int(ok_ans)
        wrong += int(not ok_ans)
        subj = _subject(str(q.get("topic") or "general"))
        row = sections.setdefault(subj, {"subject": subj, "total": 0, "correct": 0})
        row["total"] += 1
        row["correct"] += int(ok_ans)
        _bump_topic(pr, q.get("topic"), ok_ans)
        review.append({"i": _pos, "id": qid, "correct": ok_ans,
                       "right": ok_ans, "given": _orig,
                       "correct_index": int(q.get("answer_index", -1)),
                       "answer": int(q.get("answer_index", -1)),
                       "explanation": (q.get("explanation")
                                       or q.get("explanation_en") or ""),
                       "explanation_en": q.get("explanation_en", "")})
    topics = (pr.get("topics") or {}) if isinstance(
        pr.get("topics"), dict) else {}
    pr["topics"] = topics
    if len(topics) > 60:                    # keep token size sane
        for k in sorted(topics,
                        key=lambda k: ((topics[k] or {}).get(
                            "total", 0)
                            if isinstance(topics.get(k), dict)
                            else 0))[:len(topics) - 60]:
            topics.pop(k, None)
    if _nonce270:
        pr["used_attempts"] = (list(_used270) + [_nonce270])[-20:]
    total = correct + wrong
    pr["answers"] = pr.get("answers", 0) + total   # attempts: per-run stats
    pr["correct"] = pr.get("correct", 0) + correct
    pr["points"] = pr.get("points", 0) + correct * 10
    for row in sections.values():
        row["accuracy"] = round(100 * row["correct"] / max(1, row["total"]))
    return _reissue(st, secret), {
        "ok": True, "correct": correct, "wrong": wrong, "total": total,
        "accuracy": round(100 * correct / max(1, total)),
        "points": pr["points"],
        "sections": sorted(sections.values(), key=lambda r: r["accuracy"]),
        "review": review}
