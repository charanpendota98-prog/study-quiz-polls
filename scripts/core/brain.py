# -*- coding: utf-8 -*-
"""
🧠 STUDENT BRAIN 3.0 — Ability & Readiness Engine (100X layer)

Inthavaraku manam topic accuracy matrame chusam ("Polity 60%"). Kaani
oka student EASY questions pai 60% ki, HARD questions pai 60% ki chala
difference undi — nijamaina "ability" anedi question difficulty ni
batti telustundi. Ee module adhe chestundi:

  • ELO ABILITY (θ): prathi student ki okka rating (start 1000) +
    topic-wise ratings. Question difficulty rating (D) item-intel
    real correct-rate nunchi (≥10 attempts unte) lekapothe difficulty
    tag nunchi vastundi. Hard question gelisthe ekkuva gain, easy
    question odithe ekkuva loss — Chess Elo laage.
  • EXAM READINESS (0-100): ability (45%) + syllabus coverage (25%)
    + practice volume (15%) + streak consistency (15%). Student ki
    "exam ki entha ready" okka number lo, components tho.
  • ADAPTIVE COMPOSE: practice paper = due revision first, tarvatha
    weak topics, anni student level zone lone (~65% success zone —
    |D − θ| takkuva unna questions first). Chala easy/chala hard
    questions tho time waste avvadu.

Storage: data/brain.json (item_intel style cache + atomic save).
record() eppudu raise cheyyadu — scoring path break avvadu.
"""
import math
import threading
from pathlib import Path

from .store import load_json, save_json_atomic
from . import config

BRAIN_FILE = config.DATA / "brain.json"
_LOCK = threading.RLock()
_cache = {"mtime": None, "data": None}

START_THETA = 1000.0
THETA_MIN, THETA_MAX = 400.0, 2000.0
# difficulty tag -> Elo rating (item-intel data lekapothe)
LEVEL_D = {"easy": 880.0, "medium": 1010.0, "hard": 1160.0}
BANDS = [(1500, "🏆 Expert"), (1300, "💎 Advanced"), (1120, "📈 Intermediate"),
         (950, "🌱 Foundation"), (0, "🐣 Beginner")]


def _load() -> dict:
    try:
        mt = BRAIN_FILE.stat().st_mtime
    except OSError:
        mt = None
    if mt is None:
        _cache["data"] = {}
        _cache["mtime"] = None
        return _cache["data"]
    if _cache["mtime"] != mt:
        d = load_json(BRAIN_FILE, {})
        _cache["data"] = d if isinstance(d, dict) else {}
        _cache["mtime"] = mt
    return _cache["data"]


def _save(d: dict):
    save_json_atomic(BRAIN_FILE, d)
    try:
        _cache["mtime"] = BRAIN_FILE.stat().st_mtime
    except OSError:
        _cache["mtime"] = None
    _cache["data"] = d


def _rec(d: dict, uid: str) -> dict:
    return d.setdefault(str(uid), {"theta": START_THETA, "n": 0, "topics": {}})


def question_rating(qid: str = "", level: str = "") -> float:
    """Question difficulty rating D: real student data (item-intel
    correct-rate) unte ade; lekapothe difficulty tag."""
    if qid:
        try:
            from . import item_intel
            s = item_intel.stats_of(qid)
            if s["attempts"] >= 10 and s["rate"] is not None:
                r = min(0.97, max(0.03, s["rate"]))
                return max(650.0, min(1550.0,
                                      1000.0 + 400.0 * math.log10((1 - r) / r)))
        except Exception:
            pass
    return LEVEL_D.get(str(level or "").lower(), 1000.0)


def _expected(theta: float, d: float) -> float:
    return 1.0 / (1.0 + 10 ** ((d - theta) / 400.0))


def record(uid, qid: str = "", correct: bool = False, topic: str = "",
           level: str = ""):
    """Oka answer → Elo update (global + topic). Never raises."""
    if not uid:
        return
    try:
        with _LOCK:
            d = _load()
            r = _rec(d, uid)
            d_q = question_rating(qid, level)
            n = int(r.get("n", 0))
            k = 32.0 if n < 30 else 20.0          # kotta students fast ga settle
            exp = _expected(float(r.get("theta", START_THETA)), d_q)
            delta = k * ((1.0 if correct else 0.0) - exp)
            r["theta"] = max(THETA_MIN, min(THETA_MAX,
                                            float(r.get("theta", START_THETA)) + delta))
            r["n"] = n + 1
            t = str(topic or "").lower().strip()
            if t:
                tr = r.setdefault("topics", {}).setdefault(
                    t, {"theta": START_THETA, "n": 0})
                tn = int(tr.get("n", 0))
                tk = 32.0 if tn < 20 else 20.0
                texp = _expected(float(tr.get("theta", START_THETA)), d_q)
                tr["theta"] = max(THETA_MIN, min(
                    THETA_MAX, float(tr.get("theta", START_THETA))
                    + tk * ((1.0 if correct else 0.0) - texp)))
                tr["n"] = tn + 1
            _save(d)
    except Exception:
        pass


def band_of(theta: float) -> str:
    for lo, name in BANDS:
        if theta >= lo:
            return name
    return BANDS[-1][1]


def ability(uid) -> dict:
    d = _load()
    r = d.get(str(uid)) or {}
    theta = float(r.get("theta", START_THETA))
    topics = [{"topic": t, "theta": round(float(v.get("theta", START_THETA))),
               "n": int(v.get("n", 0))}
              for t, v in (r.get("topics") or {}).items()]
    topics.sort(key=lambda x: x["theta"])
    return {"theta": round(theta), "band": band_of(theta),
            "answers": int(r.get("n", 0)), "topics": topics,
            "weak_topics": [t["topic"] for t in topics if t["n"] >= 3][:3],
            "strong_topics": [t["topic"] for t in topics[::-1] if t["n"] >= 3][:3]}


def target_level(uid, topic: str = "") -> str:
    """Student zone: θ ki daggara difficulty unte learning best."""
    ab = ability(uid)
    theta = ab["theta"]
    if topic:
        for t in ab["topics"]:
            if t["topic"] == str(topic).lower():
                theta = t["theta"]
                break
    if theta < 1010:
        return "easy"
    if theta < 1200:
        return "medium"
    return "hard"


def readiness(member: dict, uid) -> dict:
    """📊 Exam Readiness 0-100 = ability 45 + coverage 25 + volume 15
    + streak 15. Components tho — student ki emi improve cheyyalo
    telustundi, owner ki honest number."""
    member = member or {}
    ab = ability(uid)
    # confidence gate: answers leni student ki ability points ivvam
    # (θ start value matrame — nijamaina data vachaka ne count)
    _conf = min(1.0, ab["answers"] / 20.0)
    ability_pts = _conf * max(0.0, min(45.0,
                                       (ab["theta"] - 650.0) / 700.0 * 45.0))
    topics = member.get("topics") or {}
    seen = [t for t, v in topics.items() if int(v.get("total", 0)) >= 3]
    coverage_pts = min(25.0, len(seen) / 8.0 * 25.0)     # 8+ topics = full
    total = int(member.get("total", 0) or 0)
    volume_pts = min(15.0, total / 300.0 * 15.0)         # 300 answers = full
    streak = int(member.get("streak", 0) or 0)
    streak_pts = min(15.0, streak / 14.0 * 15.0)         # 14-day streak = full
    score = round(ability_pts + coverage_pts + volume_pts + streak_pts)
    return {"score": max(0, min(100, score)), "theta": ab["theta"],
            "band": ab["band"],
            "components": {"ability": round(ability_pts, 1),
                           "coverage": round(coverage_pts, 1),
                           "volume": round(volume_pts, 1),
                           "streak": round(streak_pts, 1)},
            "weak_topics": ab["weak_topics"],
            "strong_topics": ab["strong_topics"]}


def profile_for(member: dict, uid) -> dict:
    """Portal/bot card: ability + readiness + revision count okkate."""
    rd = readiness(member, uid)
    due = len([r for r in (member or {}).get("review") or []])
    return {**rd, "answers": ability(uid)["answers"],
            "reviews_due": due, "target_level": target_level(uid)}


def _q_rating(q: dict) -> float:
    try:
        from . import blueprint
        lvl = blueprint.difficulty_of(q)
    except Exception:
        lvl = ""
    return question_rating(q.get("id", ""), lvl)


def compose(pool, member: dict, uid, n: int = 10, review_qs=None) -> list:
    """🎯 Adaptive paper: due revision → weak topics → level zone.
    ~65% success zone (|D-θ| chinna questions first) prathi bucket lo."""
    pool = [q for q in (pool or []) if q]
    if not pool:
        return []
    ab = ability(uid)
    theta = ab["theta"]
    weak = {w.lower() for w in ab["weak_topics"]}
    for t, v in ((member or {}).get("topics") or {}).items():
        if int(v.get("total", 0)) >= 2 and v.get("total"):
            if v.get("correct", 0) / v["total"] < 0.6:
                weak.add(str(t).lower())
    used, out = set(), []

    def take(cands, limit):
        ranked = sorted(cands, key=lambda q: abs(_q_rating(q) - theta))
        for q in ranked:
            if len(out) >= limit or len(out) >= n:
                return
            if q.get("id") not in used:
                used.add(q.get("id"))
                out.append(q)

    take([q for q in (review_qs or []) if q], min(3, n))          # 1) revision
    take([q for q in pool if (q.get("topic") or "").lower() in weak],
         min(7, n))                                              # 2) weak zones
    take(pool, n)                                                # 3) level fill
    return out[:n]


def overview() -> dict:
    """Dashboard: ability distribution (honest, tracked students only)."""
    d = _load()
    thetas = [float(r.get("theta", START_THETA)) for r in d.values()
              if isinstance(r, dict)]
    bands = {}
    for t in thetas:
        bands[band_of(t)] = bands.get(band_of(t), 0) + 1
    return {"students": len(thetas),
            "answers": sum(int(r.get("n", 0)) for r in d.values()
                           if isinstance(r, dict)),
            "avg_theta": round(sum(thetas) / len(thetas)) if thetas else 0,
            "bands": bands,
            "top": sorted(
                ({"uid": u, "theta": round(float(r.get("theta", 0))),
                  "n": int(r.get("n", 0))}
                 for u, r in d.items() if isinstance(r, dict)),
                key=lambda x: -x["theta"])[:5]}
