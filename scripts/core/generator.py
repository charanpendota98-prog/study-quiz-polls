#!/usr/bin/env python3
"""
STUDENTUP — QUESTION GENERATOR
Two engines:

1) OFFLINE PROCEDURAL (always works, zero API, mathematically verified):
   Generates infinite aptitude/reasoning questions with CORRECT answers
   computed in code (percentages, SI/CI, ratio, time-work, averages,
   series, ages, letter-coding, symbol math, clock angles, calendar,
   direction, ranking ...). English + Telugu question lines.

2) LLM GENERATOR (when keys are present): Groq -> DeepSeek -> OpenAI ->
   Gemini produces worded/reasoning/GK questions; strict validation gate
   before acceptance. Never accepts an unverifiable question.

Generated questions append to data/question_bank_extra.json and are merged
into the canonical bank by core.question_bank.rebuild_json().
"""
from __future__ import annotations

import random
import string
import json
from datetime import date

from . import config
from .store import load_json, save_json_atomic
from .content import validate_question

TE_DIGITS = {str(d): w for d, w in zip("0123456789",
             "౦౧౨౩౪౫౬౭౮౯")}


def te_num(n) -> str:
    """Render a number with Telugu digits (kept compact)."""
    return "".join(TE_DIGITS.get(c, c) for c in str(n))


def _options(correct, distractors, suffix=""):
    """Build 4 unique options; return (options_list, answer_index)."""
    opts = [correct]
    for d in distractors:
        if d != correct and d not in opts:
            opts.append(d)
    # pad if a distractor collided
    k = correct + 1
    while len(opts) < 4:
        if k not in opts:
            opts.append(k)
        k += 1
    opts = opts[:4]
    random.shuffle(opts)
    idx = opts.index(correct)
    return [f"{o}{suffix}" for o in opts], idx


def _q(qid, channel, topic, en, te, correct, distractors, suffix="", expl=""):
    opts_en, idx = _options(correct, distractors, suffix)
    return {
        "id": qid, "channel": channel, "topic": topic,
        "q_en": en, "q_te": te,
        "options_en": opts_en,
        # numeric/code options are language-neutral; TE mirrors them
        "options_te": opts_en,
        "answer_index": idx,
        "explanation_en": expl,
        "note": "", "source": "offline-gen", "bank": "extra",
    }


# ---------------------------------------------------------------------------
# Individual generators — each returns a question dict
# ---------------------------------------------------------------------------
def g_percentage(rng):
    p = rng.choice([5, 10, 12, 15, 20, 25, 40])
    base = rng.choice([200, 400, 600, 800, 1000, 1500, 2000, 5000])
    val = base * p // 100
    en = f"What is {p}% of {base}?"
    te = f"{base} లో {p}% ఎంత?"
    return _q("", "BANKING", "percentage", en, te, val,
              [val + base // 20, val - p, val + p, round(base * (p + 5) / 100)],
              expl=f"{p}% of {base} = {base}×{p}/100 = {val}.")


def g_ratio(rng):
    a, b = rng.choice([(2, 3), (3, 2), (3, 4), (4, 5), (2, 5), (5, 3), (1, 2)])
    unit = rng.choice([90, 120, 150, 200, 250, 300, 450])
    total = (a + b) * unit
    share_b = b * unit
    en = f"An amount of ₹{total} is divided between A and B in the ratio {a}:{b}. What is B's share?"
    te = f"₹{total} ను A, B ల మధ్య {a}:{b} నిష్పత్తిలో పంచితే B వాటా ఎంత?"
    return _q("", "BANKING", "ratio", en, te, share_b,
              [a * unit, total - share_b + unit, share_b + unit, (a + b) * unit // 2],
              suffix="", expl=f"{a}+{b}={a+b} parts; 1 part = {unit}; B = {b}×{unit} = ₹{share_b}.")


def g_simple_interest(rng):
    p = rng.choice([1000, 2000, 5000, 10000, 20000])
    r = rng.choice([4, 5, 6, 8, 10, 12])
    t = rng.choice([2, 3, 4, 5])
    si = p * r * t // 100
    en = f"Find the simple interest on ₹{p} at {r}% per annum for {t} years."
    te = f"₹{p} పై సంవత్సరానికి {r}% చొప్పున {t} సంవత్సరాల సాధారణ వడ్డీ ఎంత?"
    return _q("", "BANKING", "simple interest", en, te, si,
              [si + p // 10, si - r * t, si + r * t, p * r * (t + 1) // 100],
              expl=f"SI = P×R×T/100 = {p}×{r}×{t}/100 = ₹{si}.")


def g_compound_interest(rng):
    p = rng.choice([1000, 2000, 5000, 10000])
    r = rng.choice([10, 20])
    t = 2
    amt = round(p * (1 + r / 100) ** t)
    ci = amt - p
    en = f"₹{p} at {r}% p.a. compound interest for {t} years. Find the compound interest."
    te = f"₹{p} పై {r}% వార్షిక చక్రవడ్డీ {t} సంవత్సరాలకు. చక్రవడ్డీ ఎంత?"
    return _q("", "BANKING", "compound interest", en, te, ci,
              [si_equiv := p * r * t // 100, ci + p // 20, ci - r, ci + r * 2],
              expl=f"Amount = {p}×(1+{r}/100)^{t} = {amt}; CI = {amt}−{p} = ₹{ci}.")


def g_average(rng):
    n = rng.choice([5, 6, 8, 10])
    avg = rng.choice([20, 25, 30, 40, 50])
    total = n * avg
    rem_avg = rng.choice([a for a in (18, 22, 24, 27, 35, 45) if a != avg])
    rem_total = (n - 1) * rem_avg
    removed = total - rem_total
    en = (f"The average of {n} numbers is {avg}. If one number is removed, the average "
          f"of the remaining {n-1} becomes {rem_avg}. Find the removed number.")
    te = (f"{n} సంఖ్యల సగటు {avg}. ఒక సంఖ్యను తీసివేస్తే మిగిలిన {n-1} సగటు {rem_avg}. "
          f"తీసివేసిన సంఖ్య ఎంత?")
    return _q("", "BANKING", "average", en, te, removed,
              [total - rem_total + 2, avg + rem_avg, total // n, removed + n],
              expl=f"Total {n} = {total}; total {n-1} = {rem_total}; removed = {removed}.")


def g_squares(rng):
    base = rng.randint(4, 12)
    seq = [base ** 2, (base + 1) ** 2, (base + 2) ** 2, (base + 4) ** 2]
    missing = (base + 3) ** 2
    shown = f"{seq[0]}, {seq[1]}, {seq[2]}, ?, {seq[3]}"
    en = f"Find the missing number: {shown}"
    te = f"తప్పిపోయిన సంఖ్యను కనుగొనండి: {shown}"
    return _q("", "RAILWAY", "number series", en, te, missing,
              [missing - 1, missing + base, missing + 2, (base + 3) ** 2 + base],
              expl=f"Squares of consecutive numbers: {base+3}² = {missing}.")


def g_geometric(rng):
    r = rng.choice([2, 3, 4, 5])
        # powers a^1..a^5, ask a^4
    vals = [r ** i for i in range(1, 6)]
    shown = f"{vals[0]}, {vals[1]}, {vals[2]}, ?, {vals[4]}"
    en = f"Find the missing number: {shown}"
    te = f"తప్పిపోయిన సంఖ్య: {shown}"
    return _q("", "RAILWAY", "number series", en, te, vals[3],
              [vals[3] + r, vals[2] * r + r, vals[3] - r, vals[4] // r + 1],
              expl=f"Each term ×{r}; missing = {r}^4 = {vals[3]}.")


def g_linear_2n1(rng):
    start = rng.choice([3, 4, 5, 6, 7])
    seq = [start]
    for _ in range(4):
        seq.append(seq[-1] * 2 + 1)
    shown = f"{seq[0]}, {seq[1]}, {seq[2]}, {seq[3]}, ?"
    en = f"Find the missing number (pattern ×2+1): {shown}"
    te = f"తప్పిపోయిన సంఖ్య (×2+1): {shown}"
    return _q("", "DEFENCE", "number series", en, te, seq[4],
              [seq[4] - 2, seq[4] + 2, seq[3] * 2, seq[4] + 1],
              expl=f"Rule ×2+1: {seq[3]}×2+1 = {seq[4]}.")


def g_cubes(rng):
    base = rng.randint(2, 7)
    seq = [base ** 3, (base + 1) ** 3, (base + 2) ** 3, (base + 4) ** 3]
    missing = (base + 3) ** 3
    shown = f"{seq[0]}, {seq[1]}, {seq[2]}, ?, {seq[3]}"
    en = f"Find the missing number: {shown}"
    te = f"తప్పిపోయిన సంఖ్య: {shown}"
    return _q("", "POLICE", "number series", en, te, missing,
              [missing - 7, missing + 9, (base + 3) ** 2, missing + (base + 3)],
              expl=f"Consecutive cubes: {base+3}³ = {missing}.")


def g_letter_shift(rng):
    word = "".join(rng.choice(string.ascii_uppercase) for _ in range(4))
    shift = rng.choice([1, 2, 3])
    coded = "".join(chr((ord(c) - 65 + shift) % 26 + 65) for c in word)
    target = "".join(rng.choice(string.ascii_uppercase) for _ in range(4))
    answer = "".join(chr((ord(c) - 65 + shift) % 26 + 65) for c in target)
    en = f"In a code, {word} is written as {coded} (each letter shifted +{shift}). How is {target} written?"
    te = f"ఒక కోడ్‌లో {word} = {coded} (ప్రతి అక్షరం +{shift}). {target} ఎలా వ్రాయబడుతుంది?"
    # distractors: wrong shifts
    d = []
    for s in (shift + 1, shift - 1, shift + 2):
        d.append("".join(chr((ord(c) - 65 + s) % 26 + 65) for c in target))
    opts_en = [answer] + d
    rng.shuffle(opts_en)
    idx = opts_en.index(answer)
    return {"id": "", "channel": "TSPSC", "topic": "coding-decoding",
            "q_en": en, "q_te": te, "options_en": opts_en, "options_te": opts_en,
            "answer_index": idx,
            "explanation_en": f"Each letter shifts +{shift}: {target} → {answer}.",
            "note": "", "source": "offline-gen", "bank": "extra"}


def g_symbol_math(rng):
    # A means +, B means −, C means ×, D means ÷ ; build a guaranteed-integer expr
    a = rng.randint(2, 9)
    b = rng.randint(2, 9)
    c = rng.randint(2, 6)
    # expr: a C b B c A d  -> a*b - c + d
    d = rng.randint(1, 9)
    val = a * b - c + d
    en = (f"If A means +, B means −, C means × and D means ÷, then "
          f"{a} C {b} B {c} A {d} = ?")
    te = (f"A = +, B = −, C = ×, D = ÷ అయితే, {a} C {b} B {c} A {d} = ?")
    return _q("", "RAILWAY", "symbol logic", en, te, val,
              [a * b + c - d, a * b - c - d, a * (b - c) + d, val + 2],
              expl=f"{a}×{b}={a*b}; −{c}={a*b-c}; +{d} = {val}.")


def g_clock_angle(rng):
    # pick a clean time: minute hand at a multiple; compute hour-hand angle
    hh = rng.choice([2, 3, 4, 5, 7, 8])
    mm = rng.choice([0, 30])
    minute_angle = mm * 6
    hour_angle = (hh % 12) * 30 + mm * 0.5
    ang = abs(hour_angle - minute_angle)
    ang = min(ang, 360 - ang)
    ang = int(ang) if ang == int(ang) else ang
    t = f"{hh}:{mm:02d}"
    en = f"What is the angle between the hour and minute hands at {t}?"
    te = f"{t} సమయంలో గంట, నిమిషపు ముళ్ల మధ్య కోణం ఎంత?"
    correct = f"{ang}°"
    dist = [f"{(ang+15) if ang+15<180 else 180-ang}°", f"{max(0,ang-15)}°",
            f"{int(ang*2) if ang*2<180 else 30}°", f"{(ang+30) if ang+30<180 else 60}°"]
    opts = [correct] + [x for x in dist if x != correct][:3]
    rng.shuffle(opts)
    idx = opts.index(correct)
    return {"id": "", "channel": "RAILWAY", "topic": "clock",
            "q_en": en, "q_te": te, "options_en": opts, "options_te": opts,
            "answer_index": idx,
            "explanation_en": f"Hour hand {hour_angle}°, minute {minute_angle}° → {ang}°.",
            "note": "", "source": "offline-gen", "bank": "extra"}


def g_time_work(rng):
    a = rng.choice([10, 12, 15, 20])
    b = rng.choice([10, 15, 20, 30])
    if a == b:
        b += 5
    together = a * b // (a + b) if (a * b) % (a + b) == 0 else round(a * b / (a + b), 1)
    en = f"A can finish a work in {a} days and B in {b} days. Working together, how many days?"
    te = f"A ఒక పనిని {a} రోజుల్లో, B {b} రోజుల్లో పూర్తి చేస్తారు. కలిసి చేస్తే ఎన్ని రోజులు?"
    correct = str(together)
    dist = [str(round((a + b) / 2, 1)), str(a + b), str(abs(a - b)), str(round(a * b / (a + b) + 1, 1))]
    opts = [correct] + [x for x in dist if x != correct][:3]
    rng.shuffle(opts)
    idx = opts.index(correct)
    return {"id": "", "channel": "BANKING", "topic": "time-work",
            "q_en": en, "q_te": te, "options_en": [f"{o} days" for o in opts],
            "options_te": [f"{o} రోజులు" for o in opts],
            "answer_index": idx,
            "explanation_en": f"Together = {a}×{b}/({a}+{b}) = {together} days.",
            "note": "", "source": "offline-gen", "bank": "extra"}


def g_direction(rng):
    n = rng.choice([3, 4, 5, 6, 8])
    side = rng.choice([("north", "south", "east", "తూర్పు"),
                       ("east", "west", "south", "దక్షిణం"),
                       ("south", "north", "west", "పడమర")])
    go1, back, perp, te_perp = side
    en = (f"A person walks {n} km {go1}, turns right and walks {n} km {perp}, "
          f"then turns right and walks {n} km {back}. How far is he from the start?")
    te = (f"ఒక వ్యక్తి {n} కి.మీ. {go1} వైపు నడిచి, కుడి తిరిగి {n} కి.మీ. {te_perp} వైపు, "
          f"మళ్లీ కుడి తిరిగి {n} కి.మీ. {back} వైపు నడిచాడు. ప్రారంభం నుండి దూరం ఎంత?")
    return _q("", "DEFENCE", "direction", en, te, n,
              [n + 2, n - 1 if n > 1 else n + 1, 2 * n, n + 3], suffix=" km",
              expl=f"The two opposite {go1}/{back} walks cancel; net = {n} km {perp}.")


def g_ranking(rng):
    rank_from_left = rng.randint(5, 15)
    rank_from_right = rng.randint(5, 15)
    total = rank_from_left + rank_from_right - 1
    en = (f"In a row, Ravi's position is {rank_from_left}th from the left and "
          f"{rank_from_right}th from the right. How many students are in the row?")
    te = (f"ఒక వరుసలో రవికి ఎడమ నుండి {rank_from_left}వ స్థానం, కుడి నుండి {rank_from_right}వ స్థానం. "
          f"వరుసలో మొత్తం ఎంతమంది విద్యార్థులు?")
    return _q("", "POLICE", "ranking", en, te, total,
              [total - 1, total + 1, rank_from_left + rank_from_right, total + 2],
              expl=f"Total = left rank + right rank − 1 = {rank_from_left}+{rank_from_right}−1 = {total}.")


def g_calendar(rng):
    # weekday of a fixed, computed date (verified with Python's datetime)
    y = rng.choice([2024, 2025, 2026])
    m = rng.randint(1, 12)
    d = rng.randint(1, 28)
    dt = date(y, m, d)
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    te_names = ["సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం"]
    wi = dt.weekday()
    correct_en, correct_te = names[wi], te_names[wi]
    order = list(range(7))
    rng.shuffle(order)
    opts_en, opts_te, idx = [], [], None
    for j, wi2 in enumerate(order[:4]):
        opts_en.append(names[wi2]); opts_te.append(te_names[wi2])
        if wi2 == wi:
            idx = j
    if idx is None:
        opts_en[0], opts_te[0] = correct_en, correct_te
        idx = 0
    en = f"What day of the week was {dt.strftime('%d %B %Y')}?"
    te = f"{dt.strftime('%d %B %Y')} వారంలో ఏ రోజు?"
    return {"id": "", "channel": "POLICE", "topic": "calendar",
            "q_en": en, "q_te": te, "options_en": opts_en, "options_te": opts_te,
            "answer_index": idx,
            "explanation_en": f"{dt.strftime('%d %b %Y')} was a {correct_en}.",
            "note": "", "source": "offline-gen", "bank": "extra"}


_GENERATORS = [g_percentage, g_ratio, g_simple_interest, g_compound_interest,
               g_average, g_squares, g_geometric, g_linear_2n1, g_cubes,
               g_letter_shift, g_symbol_math, g_clock_angle, g_time_work,
               g_direction, g_ranking, g_calendar]


def generate_offline(n=10, seed=None):
    """Generate n validated offline questions (mix of channels)."""
    rng = random.Random(seed)
    out, seen_fp = [], set()
    attempts = 0
    while len(out) < n and attempts < n * 20:
        attempts += 1
        fn = rng.choice(_GENERATORS)
        try:
            q = fn(rng)
        except Exception:
            continue
        errs = validate_question(q)
        fp = (q["q_en"])[:60]
        if not errs and fp not in seen_fp:
            seen_fp.add(fp)
            out.append(q)
    return out


# ---------------------------------------------------------------------------
# LLM generation
# ---------------------------------------------------------------------------
_LLM_SYS = (
    "You are an exam-question author for Indian government-job aspirants in "
    "Telangana and Andhra Pradesh (TSPSC, APPSC, RRB, SSC, IBPS, SBI, Police, "
    "NDA/CDS). Write PREVIOUS-PAPER-STYLE questions. Output STRICT JSON only: "
    '{"q_en":..., "q_te":..., "options_en":[4], "options_te":[4 Telugu], '
    '"answer_index":0-3, "explanation_en":...}. q_te and options_te MUST be in '
    "Telugu script (U+0C00-0C7F). Exactly 4 options. The correct answer must be "
    "verifiable. HARD BLOCK any topic: cricket, sports, films, actors, singers, "
    "weather, celebrity, foreign politics, crime. Favour TS/AP + central gov content."
)


def generate_llm(channel, topic, llm=None):
    from .llm import LLM
    llm = llm or LLM()
    if not llm.available():
        return None
    user = f"Write one {topic} question for the {channel} channel. JSON only."
    raw = llm.chat(_LLM_SYS, user)
    if not raw:
        return None
    import re as _re
    m = _re.search(r"\{.*\}", raw, _re.S)
    if not m:
        return None
    try:
        q = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    q.setdefault("channel", channel)
    q.setdefault("topic", topic)
    q["id"] = ""
    q["source"] = "llm-gen"
    q["bank"] = "extra"
    if validate_question(q):
        return None
    return q


# ---------------------------------------------------------------------------
# Persist generated extras
# ---------------------------------------------------------------------------
# Offline-generated quantitative/reasoning questions are valid for every
# aptitude channel — we route a copy to whichever channel is under-stocked.
_APTITUDE_CHANNELS = {"BANKING", "RAILWAY", "POLICE", "DEFENCE", "TSPSC", "APPSC"}

# Per-topic generators are natively owned by these channels, but a numeric
# question can serve any aptitude channel. Worded GK (CURRENT) stays curated/LLM.


def _generate_for_channel(ch, rng):
    """Generate one question, re-tagged to target channel ch when aptitude."""
    qs = generate_offline(1, seed=rng.randint(0, 10 ** 6))
    if not qs:
        return None
    q = qs[0]
    if ch in _APTITUDE_CHANNELS and q["channel"] in _APTITUDE_CHANNELS:
        q["channel"] = ch
    return q


def top_up(per_channel_min=20, max_add=120, use_llm=True):
    """Ensure every channel has >= per_channel_min questions; add offline (+LLM)."""
    from .question_bank import load_bank
    bank = load_bank()
    extra = load_json(config.BANK_EXTRA_JSON, {"questions": []})
    have = {}
    for q in bank:
        have[q["channel"]] = have.get(q["channel"], 0) + 1
    for q in extra.get("questions", []):
        have[q["channel"]] = have.get(q["channel"], 0) + 1

    added = []
    counter = len({q["id"] for q in extra.get("questions", [])})
    rng = random.Random()
    # Fill the most-starved channels first (CURRENT relies on curated/LLM GK).
    order = sorted(config.PUBLIC_CHANNELS,
                   key=lambda c: have.get(c, 0))
    for ch in order:
        need = max(0, per_channel_min - have.get(ch, 0))
        if ch == "CURRENT":
            continue  # current-affairs GK is curated/LLM-only (no fabricated facts)
        made = tries = 0
        recent_topics = set()
        while made < need and len(added) < max_add and tries < need * 6:
            tries += 1
            q = _generate_for_channel(ch, rng)
            if not q:
                continue
            if validate_question(q):
                continue
            # light topic diversity — avoid 6 identical-topic questions
            tkey = (ch, q["topic"])
            if tkey in recent_topics and rng.random() < 0.6:
                continue
            recent_topics.add(tkey)
            if len(recent_topics) > 6:
                recent_topics.pop()
            counter += 1
            q["id"] = f"G{counter:03d}"
            added.append(q)
            have[ch] = have.get(ch, 0) + 1
            made += 1
    extra.setdefault("questions", []).extend(added)
    save_json_atomic(config.BANK_EXTRA_JSON, extra)
    from .question_bank import rebuild_json
    qs, errs = rebuild_json()
    return added, errs


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", type=int, default=5)
    ap.add_argument("--topup", action="store_true")
    a = ap.parse_args()
    if a.topup:
        added, errs = top_up()
        print(f"Top-up: {len(added)} new questions added; {len(errs)} validation errors")
    else:
        qs = generate_offline(a.demo, seed=42)
        for q in qs:
            print(f"[{q['channel']}/{q['topic']}] {q['q_en']}")
            print("   ", q["options_en"], "->", q["answer_index"], "|", q["explanation_en"])
