#!/usr/bin/env python3
"""260X — STATELESS CLIENT CORE (zero-server-storage student state).

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
(nuve old token malli use) cheyyochu; leaderboards kosam 265X lo
optional server-claim (signed receipt) undali. Ikkada: learning
features (daily quiz/mocks/reports) full stateless lu saripothayi;
ranks/prizes vache chotla server-side claim mandatory.
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
        if int(body.get("exp", 0)) < int(time.time()):
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
    try:
        from .portal import GOALS
    except Exception:
        GOALS = {}
    chans = set((GOALS.get(goal) or {}).get("channels") or [])
    qs = [q for q in _bank()
          if not chans or str(q.get("channel", "")).upper() in chans]
    return qs


def _subject(topic: str) -> str:
    try:
        from .syllabus import subject_of_topic
        return subject_of_topic(topic or "general")
    except Exception:
        return "general"


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
    acc = round(100 * pr.get("correct", 0) / max(1, pr.get("answers", 0)))
    _, dev = _secret(secret)
    return {"profile": p, "points": pr.get("points", 0),
            "answers": pr.get("answers", 0), "correct": pr.get("correct", 0),
            "accuracy": acc, "streak": pr.get("streak", 0),
            "best_streak": pr.get("best_streak", 0),
            "topics_seen": len(pr.get("topics") or {}),
            "dev_secret": dev,
            "token_exp": s.get("exp")}


def _reissue(state, secret):
    state = {k: v for k, v in state.items() if k not in ("iat", "exp")}
    return encode_token(state, secret)


def record_answer(token, qid, choice_index, secret=None, today=None):
    """Grade one answer against the bank; return (new_token, result)."""
    s = decode_token(token, secret, want_typ="u")
    if not s:
        return None, {"ok": False, "error": "invalid/expired token"}
    q = next((x for x in _bank() if str(x.get("id")) == str(qid)), None)
    if q is None:
        return None, {"ok": False, "error": "question not found"}
    pr = s.setdefault("prog", {})
    ok_ans = int(choice_index) == int(q.get("answer_index", -1))
    today = today or time.strftime("%Y-%m-%d")
    if pr.get("last_day") != today:         # new day -> streak decides
        from datetime import date, timedelta
        yday = (date.today() - timedelta(days=1)).isoformat()
        pr["streak"] = (pr.get("streak", 0) + 1) if pr.get("last_day") == yday else 1
        pr["last_day"] = today
    pr["answers"] = pr.get("answers", 0) + 1
    gained = 0
    if ok_ans:
        pr["correct"] = pr.get("correct", 0) + 1
        gained = 10 + (5 if pr.get("streak", 0) >= 3 else 0)
        pr["points"] = pr.get("points", 0) + gained
    pr["best_streak"] = max(pr.get("best_streak", 0), pr.get("streak", 0))
    t = str(q.get("topic") or "general")
    row = (pr.setdefault("topics", {})).setdefault(t, {"total": 0, "correct": 0})
    row["total"] += 1
    row["correct"] += int(ok_ans)
    seen = pr.setdefault("seen", [])
    if str(qid) not in seen:
        seen.append(str(qid))
        del seen[:-200]                     # bounded payload
    topics = pr.get("topics") or {}
    if len(topics) > 60:                    # keep token size sane
        for k in sorted(topics, key=lambda k: topics[k]["total"])[:len(topics) - 60]:
            topics.pop(k, None)
    return _reissue(s, secret), {
        "ok": True, "correct": ok_ans,
        "correct_index": int(q.get("answer_index", -1)),
        "points_gained": gained, "points": pr["points"],
        "streak": pr["streak"], "accuracy":
        round(100 * pr["correct"] / max(1, pr["answers"]))}


def daily_quiz(token, secret=None, n=10, today=None):
    """Today's deterministic set for this student (pure; no writes)."""
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
    return {"date": today, "goal": prof.get("goal", ""),
            "questions": [{"id": q.get("id"), "q_en": q.get("q_en", ""),
                           "q_te": q.get("q_te", ""),
                           "options_en": q.get("options_en") or [],
                           "options_te": q.get("options_te") or [],
                           "topic": q.get("topic", "")}
                          for q in picked]}


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
    claims = {"typ": "a", "uid": s.get("uid"),
              "goal": (s.get("profile") or {}).get("goal", ""),
              "qids": [str(q.get("id")) for q in picked]}
    return encode_token(claims, secret, ttl=_ATTEMPT_TTL), None


def submit_attempt(state_token, attempt_token, answers: dict, secret=None):
    """Grade the attempt, fold stats into the state, issue a fresh token."""
    st = decode_token(state_token, secret, want_typ="u")
    at = decode_token(attempt_token, secret, want_typ="a")
    if not st or not at:
        return None, {"ok": False, "error": "invalid/expired token"}
    by_id = {str(q.get("id")): q for q in _bank()}
    pr = st.setdefault("prog", {})
    sections, correct, wrong = {}, 0, 0
    review = []
    for qid in at.get("qids") or []:
        q = by_id.get(str(qid))
        if q is None:
            continue
        pick = (answers or {}).get(str(qid), -1)
        ok_ans = int(pick) == int(q.get("answer_index", -1))
        correct += int(ok_ans)
        wrong += int(not ok_ans)
        subj = _subject(str(q.get("topic") or "general"))
        row = sections.setdefault(subj, {"subject": subj, "total": 0, "correct": 0})
        row["total"] += 1
        row["correct"] += int(ok_ans)
        t = str(q.get("topic") or "general")
        trow = (pr.setdefault("topics", {})).setdefault(t, {"total": 0, "correct": 0})
        trow["total"] += 1
        trow["correct"] += int(ok_ans)
        review.append({"id": qid, "correct": ok_ans,
                       "correct_index": int(q.get("answer_index", -1)),
                       "explanation_en": q.get("explanation_en", "")})
    total = correct + wrong
    pr["answers"] = pr.get("answers", 0) + total
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
