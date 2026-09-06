#!/usr/bin/env python3
"""
STUDENTUP — EXAM-PAPER BLUEPRINT COMPOSER
==========================================
Makes every quiz round look like the REAL exam paper of that channel:

  * subject mix follows the official section weightage
    (data/exam_blueprints.json — SSC Tier-I = 25/25/25/25, IBPS prelims =
    quant-heavy, RRB NTPC = GK-heavy, TSPSC/APPSC = GS + mental ability ...);
  * subjects appear at RANDOM positions inside the round (like a real paper,
    not neat blocks), while the difficulty ramps easy -> medium -> hard;
  * difficulty is estimated from the question itself (statement-based /
    match-the-following / multi-step numeric = hard; one-liner recall = easy),
    so "advanced" questions are guaranteed a share of every round;
  * PYQ-first priority, topic diversity and answer-key balance are preserved.

Pure functions — no I/O except reading the blueprint once.
"""
from __future__ import annotations

import random
import re

from . import config
from .store import load_json

BLUEPRINT_PATH = config.DATA / "exam_blueprints.json"
_BP = None


def blueprint() -> dict:
    global _BP
    if _BP is None:
        _BP = load_json(BLUEPRINT_PATH, {})
        if not isinstance(_BP, dict):
            _BP = {}
    return _BP


# ---------------------------------------------------------------------------
# Subject classification
# ---------------------------------------------------------------------------
def subject_of(q: dict) -> str:
    """Map a question to reasoning / quant / english / gk (never fails)."""
    bp = blueprint()
    subjects = bp.get("subjects", {})
    topic = (q.get("topic") or "").lower()
    stem = (q.get("q_en") or "").lower()
    # explicit prefix like "Quantitative Aptitude - Percentage" wins
    head = topic.split("-")[0].split("/")[0].strip()
    for subj in ("english", "quant", "reasoning", "gk"):
        for kw in subjects.get(subj, []):
            if kw in head:
                return subj
    for subj in ("english", "quant", "reasoning", "gk"):
        for kw in subjects.get(subj, []):
            if kw in topic:
                return subj
    # fall back to stem heuristics
    if re.search(r"\d+\s*%|\bratio\b|\binterest\b|\bkm/?h|\bprofit\b|\baverage\b", stem):
        return "quant"
    if re.search(r"\bcoded?\b|\bseries\b|\bfacing\b|\bsyllog|\bstatements?\b.*\bconclusion", stem):
        return "reasoning"
    if re.search(r"synonym|antonym|correct spelling|fill in the blank|idiom|one word", stem):
        return "english"
    return "gk"


# ---------------------------------------------------------------------------
# Difficulty estimation
# ---------------------------------------------------------------------------
_HARD_RE = re.compile(
    r"consider the following|which of the (?:above|following) (?:statements|pairs)|"
    r"match (?:the )?(?:list|following|column)|arrange .* chronolog|"
    r"statements?:.*conclusions?|assertion|reason \(r\)|not correctly matched|"
    r"how many of the (?:above|following)|select the (?:in)?correct statement", re.I)
_MED_RE = re.compile(
    r"\bif\b.*\bthen\b|per annum|compound|successive|respectively|"
    r"in how many|at what|find the value|what will be|how far|"
    r"coded as|written as|facing|sitting", re.I)


def difficulty_of(q: dict) -> str:
    """easy | medium | hard — from explicit tag if present, else heuristics."""
    tag = (q.get("difficulty") or q.get("level") or "").lower()
    if tag in ("easy", "medium", "hard"):
        return tag
    stem = q.get("q_en") or ""
    nums = len(re.findall(r"\d+(?:\.\d+)?", stem))
    opts = q.get("options_en") or []
    optlen = sum(len(str(o)) for o in opts) / max(1, len(opts))
    if _HARD_RE.search(stem) or len(stem) > 190 or nums >= 5 or optlen > 45:
        return "hard"
    if _MED_RE.search(stem) or len(stem) > 95 or nums >= 2 or optlen > 22:
        return "medium"
    return "easy"


# ---------------------------------------------------------------------------
# Round composition
# ---------------------------------------------------------------------------
def _quota(weights: dict, n: int) -> dict:
    """Largest-remainder rounding of subject weights into n slots."""
    if not weights:
        return {}
    total = sum(weights.values()) or 1.0
    raw = {k: v / total * n for k, v in weights.items()}
    base = {k: int(v) for k, v in raw.items()}
    left = n - sum(base.values())
    for k, _ in sorted(raw.items(), key=lambda kv: kv[1] - int(kv[1]), reverse=True):
        if left <= 0:
            break
        base[k] += 1
        left -= 1
    return base


def compose_round(channel: str, pool: list, n: int = 10, rng=None) -> list:
    """Pick n questions from `pool` that match the channel's exam blueprint.

    Guarantees (when the pool allows): subject quota per blueprint, at least
    `min_hard_share` hard/medium-hard questions, PYQ-first inside each
    subject, topic diversity, answer-key balance, random subject positions
    with an easy->hard ramp. Always returns min(n, len(pool)) questions.
    """
    rng = rng or random.Random()
    bp = blueprint()
    ch = (bp.get("channels") or {}).get(channel) or {}
    weights = ch.get("weights") or {"gk": 1.0}
    min_hard = float(ch.get("min_hard_share", 0.3))
    ramp = (bp.get("difficulty_ramp") or {}).get("positions") or []

    tagged = []
    for q in pool:
        tagged.append((q, subject_of(q), difficulty_of(q)))
    quota = _quota(weights, n)
    src_rank = {"pyq": 0, "curated": 1, "scraped": 1, "llm-gen": 2, "offline-gen": 3}
    diff_rank = {"hard": 0, "medium": 1, "easy": 2}

    chosen, topics_used, keys_used = [], {}, [0, 0, 0, 0]
    used_ids = set()
    hard_needed = int(round(min_hard * n))

    def score(item, want_hard):
        q, subj, diff = item
        s = src_rank.get(q.get("source", "offline-gen"), 3) * 1.5
        s += topics_used.get(q.get("topic", ""), 0) * 2.5
        s += keys_used[q["answer_index"]] * 0.8
        if want_hard:
            s += diff_rank[diff] * 2
        return s + rng.random()

    # 1) fill subject quotas (hard questions first until min share is met)
    for subj, k in sorted(quota.items(), key=lambda kv: -kv[1]):
        cands = [t for t in tagged if t[1] == subj and t[0]["id"] not in used_ids]
        for _ in range(k):
            if not cands:
                break
            want_hard = sum(1 for c in chosen if c[2] != "easy") < hard_needed
            cands.sort(key=lambda t: score(t, want_hard))
            item = cands.pop(0)
            chosen.append(item)
            used_ids.add(item[0]["id"])
            topics_used[item[0].get("topic", "")] = topics_used.get(item[0].get("topic", ""), 0) + 1
            keys_used[item[0]["answer_index"]] += 1

    # 2) top up from any subject if a quota could not be met
    rest = [t for t in tagged if t[0]["id"] not in used_ids]
    while len(chosen) < n and rest:
        want_hard = sum(1 for c in chosen if c[2] != "easy") < hard_needed
        rest.sort(key=lambda t: score(t, want_hard))
        item = rest.pop(0)
        chosen.append(item)
        used_ids.add(item[0]["id"])
        topics_used[item[0].get("topic", "")] = topics_used.get(item[0].get("topic", ""), 0) + 1
        keys_used[item[0]["answer_index"]] += 1

    # 3) order: random subject positions + easy->hard ramp
    rng.shuffle(chosen)
    if ramp:
        ordered = []
        remaining = chosen[:]
        for pos in range(len(chosen)):
            want = ramp[pos] if pos < len(ramp) else "medium"
            idx = next((i for i, t in enumerate(remaining) if t[2] == want), None)
            if idx is None:
                # nearest difficulty
                order = {"easy": ["medium", "hard"], "medium": ["easy", "hard"],
                         "hard": ["medium", "easy"]}[want]
                for alt in order:
                    idx = next((i for i, t in enumerate(remaining) if t[2] == alt), None)
                    if idx is not None:
                        break
            if idx is None:
                idx = 0
            ordered.append(remaining.pop(idx))
        chosen = ordered
    return [t[0] for t in chosen]


def round_profile(questions: list) -> dict:
    """Subject / difficulty / source counts for a composed round (for logs)."""
    prof = {"subjects": {}, "difficulty": {}, "sources": {}}
    for q in questions:
        s = subject_of(q)
        d = difficulty_of(q)
        prof["subjects"][s] = prof["subjects"].get(s, 0) + 1
        prof["difficulty"][d] = prof["difficulty"].get(d, 0) + 1
        src = q.get("source", "")
        prof["sources"][src] = prof["sources"].get(src, 0) + 1
    return prof
