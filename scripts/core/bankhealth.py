# -*- coding: utf-8 -*-
"""🏥 280X: BANK HEALTH & ANSWER-BIAS SHIELD.

Why this module exists
----------------------
Students are smart: if the correct option sits in the same position
too often (the classic "answer is usually B" disease), they stop
studying and start pattern-guessing. Portal serving already shuffles
per student (260X/270X), and scheduled rounds already balance via
``content.poll_safe`` — but until 280X several live surfaces (DM
quizzes, coach, arena, district war, WhatsApp native polls) sent
options in raw bank order, so the bank's raw position skew leaked
straight to students.

This module is the *measurement* half of the shield:

  * ``position_distribution`` — where the bank hides its answers.
  * ``bias_flags``            — deterministic skew detection (overall
                                + per exam/goal group).
  * ``bank_health_report``    — one honest report: totals, PYQ share,
                                duplicates, invalid questions, missing
                                explanations, position bias, a grade.
  * ``rebalance_bank``        — offline repair: returns a rebalanced
                                copy (correct option TEXT never moves
                                relative to itself — only its position),
                                using the same deterministic
                                ``content.balance_options`` the
                                send-paths use. Data files are never
                                rewritten automatically; serve-time
                                balancing is the live protection.

Everything is pure/deterministic — fully unit-testable offline.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

POSITIONS = 4
BIAS_MIN_N = 40          # need a real sample before accusing a group
BIAS_MAX_SHARE = 0.40    # top position holding >40% = predictable


def _norm_stem(q: dict) -> str:
    """Normalized question stem for duplicate detection (EN preferred)."""
    s = (q.get("q_en") or q.get("q_te") or "").lower()
    s = re.sub(r"[^a-z0-9\u0C00-\u0C7F]+", " ", s)
    return " ".join(s.split())


def _group_of(q: dict) -> str:
    return (q.get("exam") or q.get("goal") or q.get("channel")
            or "mixed") or "mixed"


def position_distribution(questions) -> dict:
    """{0: n0, 1: n1, 2: n2, 3: n3} over questions with a valid index."""
    c = Counter()
    for q in questions or []:
        ai = q.get("answer_index")
        if isinstance(ai, int) and 0 <= ai < POSITIONS:
            c[ai] += 1
    return {i: c.get(i, 0) for i in range(POSITIONS)}


def _flag(scope: str, dist: dict) -> dict | None:
    n = sum(dist.values())
    if n < BIAS_MIN_N:
        return None
    top_pos, top_n = max(dist.items(), key=lambda kv: kv[1])
    share = top_n / n if n else 0.0
    if share <= BIAS_MAX_SHARE:
        return None
    return {"scope": scope, "n": n, "top_position": top_pos,
            "top_share": round(share, 3), "distribution": dist}


def bias_flags(questions, min_n: int = BIAS_MIN_N,
               max_share: float = BIAS_MAX_SHARE) -> list:
    """Skewed scopes: 'ALL' first, then per exam/goal group (worst first)."""
    qs = list(questions or [])
    old_min, old_share = BIAS_MIN_N, BIAS_MAX_SHARE
    flags = []
    try:
        globals()["BIAS_MIN_N"], globals()["BIAS_MAX_SHARE"] = min_n, max_share
        f = _flag("ALL", position_distribution(qs))
        if f:
            flags.append(f)
        per = defaultdict(list)
        for q in qs:
            per[_group_of(q)].append(q)
        for scope in sorted(per):
            f = _flag(scope, position_distribution(per[scope]))
            if f:
                flags.append(f)
    finally:
        globals()["BIAS_MIN_N"], globals()["BIAS_MAX_SHARE"] = old_min, old_share
    flags.sort(key=lambda f: (f["scope"] != "ALL", -f["top_share"]))
    return flags


def question_defects(q: dict) -> list:
    """All the ways ONE question can be broken (empty list = healthy)."""
    bad = []
    ai = q.get("answer_index")
    opts = q.get("options_en") or q.get("options_te") or []
    if not _norm_stem(q):
        bad.append("empty_stem")
    if not isinstance(ai, int) or not 0 <= ai < POSITIONS:
        bad.append("bad_answer_index")
    if len(opts) < 2:
        bad.append("too_few_options")
    elif isinstance(ai, int) and ai >= len(opts):
        bad.append("answer_index_out_of_range")
    if len({str(o).strip().lower() for o in opts if str(o).strip()}) < len(
            [o for o in opts if str(o).strip()]):
        bad.append("duplicate_options")
    return bad


def bank_health_report(questions) -> dict:
    """One honest, deterministic health report for the whole bank."""
    qs = list(questions or [])
    stems = Counter(_norm_stem(q) for q in qs if _norm_stem(q))
    dup_stems = {s: n for s, n in stems.items() if n > 1}
    dup_ids = [q.get("id", "?") for q in qs
               if _norm_stem(q) and stems[_norm_stem(q)] > 1]
    invalid = {}
    missing_expl = 0
    for q in qs:
        d = question_defects(q)
        if d:
            invalid[q.get("id", "?")] = d
        if not (q.get("explanation_en") or q.get("explanation_te")
                or q.get("explanation") or q.get("note")):
            missing_expl += 1
    pyq = sum(1 for q in qs if q.get("source") == "pyq")
    flags = bias_flags(qs)
    groups = Counter(_group_of(q) for q in qs)
    n = len(qs)
    if invalid:
        grade = "D" if len(invalid) > max(5, n // 20) else "C"
    elif flags and flags[0]["top_share"] > 0.55:
        grade = "C"
    elif flags or dup_stems or missing_expl > n // 2:
        grade = "B"
    else:
        grade = "A"
    return {
        "total": n,
        "groups": dict(groups.most_common()),
        "pyq": {"count": pyq, "share": round(pyq / n, 3) if n else 0.0},
        "positions": position_distribution(qs),
        "bias_flags": flags,
        "duplicates": {"stems": len(dup_stems), "question_ids": dup_ids[:25]},
        "invalid": invalid,
        "invalid_count": len(invalid),
        "missing_explanation": missing_expl,
        "grade": grade,
        "ok": not invalid,
    }


def rebalance_bank(questions, seed: str = "studentup-280x") -> list:
    """Offline repair copy: every healthy question re-positioned via
    the same deterministic balance the live send-paths use. The correct
    option TEXT is invariant — only its position changes."""
    from .content import balance_options
    out = []
    for q in questions or []:
        if question_defects(q):
            out.append(dict(q))
            continue
        out.append(balance_options(q, seed=f"{seed}:{q.get('id', '')}"))
    return out


def summarize(report: dict) -> str:
    """One-line human summary (dashboard / CLI)."""
    pos = report.get("positions", {})
    flags = report.get("bias_flags", [])
    bias = (f"⚠️ bias: position {flags[0]['top_position']} holds "
            f"{round(100 * flags[0]['top_share'])}% ({flags[0]['scope']})"
            if flags else "positions balanced")
    return (f"{report.get('total', 0)} Q · grade {report.get('grade', '?')} · "
            f"PYQ {report.get('pyq', {}).get('count', 0)} · "
            f"invalid {report.get('invalid_count', 0)} · "
            f"dup stems {report.get('duplicates', {}).get('stems', 0)} · "
            f"pos {pos} · {bias}")
