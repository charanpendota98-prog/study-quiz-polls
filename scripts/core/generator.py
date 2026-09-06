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


# ---------------------------------------------------------------------------
# Static GK for the CURRENT channel (SSC/UPSC/RRB static facts — exam-aligned,
# NOT news). Each item is a fixed, verifiable fact with bilingual options.
# ---------------------------------------------------------------------------
_STATIC_GK = [
    ("What is the national currency of Japan?", "జపాన్ జాతీయ కరెన్సీ ఏది?",
     ["Yen", "Won", "Yuan", "Rupee"], ["యెన్", "వోన్", "యువాన్", "రూపాయ్"], 0,
     "Japan's currency is the Yen (¥).", "జపాన్ కరెన్సీ యెన్ (¥)."),
    ("The Tropic of Cancer passes through how many Indian states?", "కర్కట రేఖ భారతదేశంలో ఎన్ని రాష్ట్రాల గుండా వెళుతుంది?",
     ["8", "6", "7", "9"], ["8", "6", "7", "9"], 0,
     "The Tropic of Cancer passes through 8 Indian states.", "కర్కట రేఖ 8 భారత రాష్ట్రాల గుండా వెళుతుంది."),
    ("Which is the longest river in India?", "భారతదేశంలో పొడవైన నది ఏది?",
     ["Ganga", "Godavari", "Yamuna", "Krishna"], ["గంగా", "గోదావరి", "యమునా", "కృష్ణా"], 0,
     "The Ganga is the longest river in India (~2,525 km).", "గంగా భారత్‌లో పొడవైన నది (~2,525 కి.మీ.)."),
    ("Who was the first President of independent India?", "స్వతంత్ర భారతదేశ మొదటి రాష్ట్రపతి ఎవరు?",
     ["Dr. Rajendra Prasad", "Jawaharlal Nehru", "S. Radhakrishnan", "B. R. Ambedkar"],
     ["డాక్టర్ రాజేంద్ర ప్రసాద్", "జవహర్‌లాల్ నెహ్రూ", "ఎస్. రాధాకృష్ణన్", "బి.ఆర్. అంబేద్కర్"], 0,
     "Dr. Rajendra Prasad was the first President (1950–62).", "డాక్టర్ రాజేంద్ర ప్రసాద్ మొదటి రాష్ట్రపతి (1950–62)."),
    ("Which gas do plants absorb from the atmosphere during photosynthesis?", "కిరణజన్య సంయోగక్రియలో మొక్కలు వాతావరణం నుండి ఏ వాయువును గ్రహిస్తాయి?",
     ["Carbon dioxide", "Oxygen", "Nitrogen", "Hydrogen"], ["కార్బన్ డై ఆక్సైడ్", "ఆక్సిజన్", "నైట్రోజన్", "హైడ్రోజన్"], 0,
     "Plants absorb CO₂ and release oxygen.", "మొక్కలు CO₂ గ్రహించి ఆక్సిజన్ విడుదల చేస్తాయి."),
    ("The headquarters of the International Monetary Fund (IMF) is in?", "అంతర్జాతీయ ద్రవ్య నిధి (IMF) ప్రధాన కార్యాలయం ఎక్కడ?",
     ["Washington D.C.", "New York", "Geneva", "Paris"], ["వాషింగ్టన్ D.C.", "న్యూయార్క్", "జెనీవా", "పారిస్"], 0,
     "The IMF is headquartered in Washington D.C., USA.", "IMF ప్రధాన కార్యాలయం వాషింగ్టన్ D.C.లో ఉంది."),
    ("Which Indian state is known as the 'Spice Garden of India'?", "భారతదేశ 'స్పైస్ గార్డెన్' గా ఏ రాష్ట్రం పిలువబడుతుంది?",
     ["Kerala", "Tamil Nadu", "Karnataka", "Andhra Pradesh"], ["కేరళ", "తమిళనాడు", "కర్ణాటక", "ఆంధ్రప్రదేశ్"], 0,
     "Kerala is called the Spice Garden of India.", "కేరళను భారత స్పైస్ గార్డెన్ అంటారు."),
    ("The Reserve Bank of India was nationalised in which year?", "రిజర్వ్ బ్యాంక్ ఆఫ్ ఇండియా ఏ సంవత్సరంలో జాతీయం చేయబడింది?",
     ["1949", "1935", "1955", "1969"], ["1949", "1935", "1955", "1969"], 0,
     "RBI was nationalised on 1 January 1949 (established 1935).", "RBI 1 జనవరి 1949న జాతీయం చేయబడింది (1935లో స్థాపన)."),
    ("Which is the smallest state of India by area?", "విస్తీర్ణం ప్రకారం భారతదేశంలో అతి చిన్న రాష్ట్రం ఏది?",
     ["Goa", "Sikkim", "Tripura", "Nagaland"], ["గోవా", "సిక్కిం", "త్రిపుర", "నాగాలాండ్"], 0,
     "Goa is the smallest state by area.", "విస్తీర్ణంలో గోవా అతి చిన్న రాష్ట్రం."),
    ("The Battle of Plassey was fought in which year?", "ప్లాసీ యుద్ధం ఏ సంవత్సరంలో జరిగింది?",
     ["1757", "1764", "1857", "1761"], ["1757", "1764", "1857", "1761"], 0,
     "The Battle of Plassey was fought in 1757.", "ప్లాసీ యుద్ధం 1757లో జరిగింది."),
    ("Which vitamin is produced when the skin is exposed to sunlight?", "చర్మం సూర్యరశ్మికి గురైనప్పుడు ఏ విటమిన్ ఉత్పత్తి అవుతుంది?",
     ["Vitamin D", "Vitamin C", "Vitamin A", "Vitamin B"], ["విటమిన్ D", "విటమిన్ C", "విటమిన్ A", "విటమిన్ B"], 0,
     "Sunlight helps the skin synthesise Vitamin D.", "సూర్యరశ్మి వల్ల చర్మం విటమిన్ D తయారుచేస్తుంది."),
    ("The Sardar Sarovar Dam is built on which river?", "సర్దార్ సరోవర్ డ్యామ్ ఏ నదిపై నిర్మించబడింది?",
     ["Narmada", "Tapi", "Godavari", "Mahanadi"], ["నర్మద", "తాపీ", "గోదావరి", "మహానది"], 0,
     "Sardar Sarovar Dam is on the Narmada river, Gujarat.", "సర్దార్ సరోవర్ డ్యామ్ గుజరాత్‌లో నర్మద నదిపై ఉంది."),
    ("Who wrote the national anthem of India?", "భారత జాతీయ గీతాన్ని ఎవరు రచించారు?",
     ["Rabindranath Tagore", "Bankim Chandra Chatterjee", "Sarojini Naidu", "Subhash Chandra Bose"],
     ["రవీంద్రనాథ్ ఠాగూర్", "బంకించంద్ర ఛటర్జీ", "సరోజినీ నాయుడు", "సుభాష్ చంద్రబోస్"], 0,
     "'Jana Gana Mana' was written by Rabindranath Tagore.", "'జన గణ మన్' రచయిత రవీంద్రనాథ్ ఠాగూర్."),
    ("Which is the largest desert in the world?", "ప్రపంచంలో అతిపెద్ద ఎడారి ఏది?",
     ["Sahara", "Gobi", "Thar", "Kalahari"], ["సహారా", "గోబీ", "థార్", "కలహరి"], 0,
     "The Sahara (Africa) is the world's largest hot desert.", "ఆఫ్రికాలోని సహారా ప్రపంచ అతిపెద్ద వేడి ఎడారి."),
    ("The Indian Parliament consists of how many houses?", "భారత పార్లమెంట్‌లో ఎన్ని సభలు ఉన్నాయి?",
     ["Two", "Three", "One", "Four"], ["రెండు", "మూడు", "ఒకటి", "నాలుగు"], 0,
     "Parliament has two houses: Lok Sabha and Rajya Sabha.", "పార్లమెంట్‌లో లోక్‌సభ, రాజ్యసభ అనే రెండు సభలు."),
    ("Which metal is liquid at room temperature?", "గది ఉష్ణోగ్రత వద్ద ద్రవ రూపంలో ఉండే లోహం ఏది?",
     ["Mercury", "Iron", "Copper", "Aluminium"], ["పాదరసం", "ఇనుము", "రాగి", "అల్యూమినియం"], 0,
     "Mercury (Hg) is liquid at room temperature.", "పాదరసం (Hg) గది ఉష్ణోగ్రత వద్ద ద్రవంగా ఉంటుంది."),
    ("The headquarters of ISRO is located in which city?", "ఇస్రో (ISRO) ప్రధాన కార్యాలయం ఏ నగరంలో ఉంది?",
     ["Bengaluru", "Hyderabad", "New Delhi", "Chennai"], ["బెంగళూరు", "హైదరాబాద్", "న్యూఢిల్లీ", "చెన్నై"], 0,
     "ISRO is headquartered in Bengaluru.", "ఇస్రో ప్రధాన కార్యాలయం బెంగళూరులో ఉంది."),
    ("Which is the highest mountain peak in India?", "భారతదేశంలో ఎత్తైన పర్వత శిఖరం ఏది?",
     ["Kanchenjunga", "Mount Everest", "Nanda Devi", "K2"], ["కాంచనజంగా", "ఎవరెస్ట్", "నందాదేవి", "K2"], 0,
     "Kanchenjunga (8,586 m) is the highest peak within India.", "కాంచనజంగా (8,586 మీ.) భారతదేశంలో ఎత్తైన శిఖరం."),
    ("The Pongal festival is primarily celebrated in which state?", "పొంగల్ పండుగ ప్రధానంగా ఏ రాష్ట్రంలో జరుపుకుంటారు?",
     ["Tamil Nadu", "Kerala", "Karnataka", "Telangana"], ["తమిళనాడు", "కేరళ", "కర్ణాటక", "తెలంగాణ"], 0,
     "Pongal is the major harvest festival of Tamil Nadu.", "పొంగల్ తమిళనాడు ప్రధాన పంట పండుగ."),
    ("How many fundamental rights are currently guaranteed by the Indian Constitution?", "ప్రస్తుతం భారత రాజ్యాంగం ఎన్ని ప్రాథమిక హక్కులను కల్పిస్తోంది?",
     ["Six", "Seven", "Five", "Eight"], ["ఆరు", "ఏడు", "ఐదు", "ఎనిమిది"], 0,
     "Originally seven; after the 44th Amendment removed the Right to Property, six remain.", "మొదట ఏడు; 44వ సవరణతో ఆస్తి హక్కు తొలగి ఆరు మిగిలాయి."),
    ("Which planet is known as the Red Planet?", "ఎర్ర గ్రహం గా పిలువబడే గ్రహం ఏది?",
     ["Mars", "Venus", "Jupiter", "Saturn"], ["అంగారకుడు", "శుక్రుడు", "బృహస్పతి", "శని"], 0,
     "Mars appears red due to iron oxide on its surface.", "ఉపరితలంపై ఐరన్ ఆక్సైడ్ వల్ల అంగారకుడు ఎర్రగా కనిపిస్తాడు."),
    ("The Charminar is located in which city?", "చార్మినార్ ఏ నగరంలో ఉంది?",
     ["Hyderabad", "Vijayawada", "Warangal", "Bidar"], ["హైదరాబాద్", "విజయవాడ", "వరంగల్", "బీదర్"], 0,
     "The Charminar (1591) is a landmark of Hyderabad.", "చార్మినార్ (1591) హైదరాబాద్ చారిత్రక కట్టడం."),
    ("Which is the largest gland in the human body?", "మానవ శరీరంలో అతిపెద్ద గ్రంథి ఏది?",
     ["Liver", "Pancreas", "Thyroid", "Kidney"], ["కాలేయం", "క్లోమం", "థైరాయిడ్", "మూత్రపిండం"], 0,
     "The liver is the largest gland in the human body.", "కాలేయం మానవ శరీరంలో అతిపెద్ద గ్రంథి."),
    ("The World Health Organization (WHO) has its headquarters in?", "ప్రపంచ ఆరోగ్య సంస్థ (WHO) ప్రధాన కార్యాలయం ఎక్కడ?",
     ["Geneva", "New York", "Paris", "Rome"], ["జెనీవా", "న్యూయార్క్", "పారిస్", "రోమ్"], 0,
     "WHO is headquartered in Geneva, Switzerland.", "WHO ప్రధాన కార్యాలయం స్విట్జర్లాండ్‌లోని జెనీవాలో ఉంది."),
    ("Which Indian won the Nobel Prize for the discovery of the scattering of light (Raman Effect)?", "కాంతి వికీర్ణం (రామన్ ఎఫెక్ట్) కనుగొన్నందుకు నోబెల్ బహుమతి పొందిన భారతీయుడు ఎవరు?",
     ["C. V. Raman", "Homi Bhabha", "S. Ramanujan", "Vikram Sarabhai"],
     ["సి.వి. రామన్", "హోమీ భాభా", "ఎస్. రామానుజన్", "విక్రమ్ సారాభాయ్"], 0,
     "Sir C. V. Raman won the 1930 Nobel Prize in Physics.", "సర్ సి.వి. రామన్ 1930 భౌతిక శాస్త్ర నోబెల్ అందుకున్నారు."),
    ("The Konark Sun Temple is in which state?", "కోణార్క్ సూర్య దేవాలయం ఏ రాష్ట్రంలో ఉంది?",
     ["Odisha", "West Bengal", "Gujarat", "Madhya Pradesh"], ["ఒడిశా", "పశ్చిమ బెంగాల్", "గుజరాత్", "మధ్యప్రదేశ్"], 0,
     "The Konark Sun Temple is in Odisha.", "కోణార్క్ సూర్య దేవాలయం ఒడిశాలో ఉంది."),
    ("What is the chemical symbol for Gold?", "బంగారం రసాయన చిహ్నం ఏది?",
     ["Au", "Ag", "Gd", "Go"], ["Au", "Ag", "Gd", "Go"], 0,
     "Gold's symbol Au comes from Latin 'aurum'.", "బంగారం చిహ్నం Au — లాటిన్ 'aurum' నుండి."),
    ("The first woman Prime Minister of India was?", "భారతదేశ మొదటి మహిళా ప్రధానమంత్రి ఎవరు?",
     ["Indira Gandhi", "Pratibha Patil", "Sonia Gandhi", "Sarojini Naidu"],
     ["ఇందిరా గాంధీ", "ప్రతిభా పాటిల్", "సోనియా గాంధీ", "సరోజినీ నాయుడు"], 0,
     "Indira Gandhi was PM from 1966–77 and 1980–84.", "ఇందిరా గాంధీ 1966–77, 1980–84లో ప్రధానమంత్రి."),
    ("Which is the national aquatic animal of India?", "భారత జాతీయ జల జంతువు ఏది?",
     ["Ganges River Dolphin", "Blue Whale", "Olive Ridley Turtle", "Gharial"],
     ["గంగా నది డాల్ఫిన్", "బ్లూ వేల్", "ఆలివ్ రిడ్లీ తాబేలు", "ఘడియల్"], 0,
     "The Ganges River Dolphin is India's national aquatic animal.", "గంగా నది డాల్ఫిన్ భారత జాతీయ జల జంతువు."),
    ("The Jallianwala Bagh massacre took place in which year?", "జలియన్‌వాలా బాగ్ మారణకాండ ఏ సంవత్సరంలో జరిగింది?",
     ["1919", "1920", "1918", "1921"], ["1919", "1920", "1918", "1921"], 0,
     "The Jallianwala Bagh massacre occurred on 13 April 1919.", "జలియన్‌వాలా బాగ్ మారణకాండ 13 ఏప్రిల్ 1919న జరిగింది."),
    ("Which blood group is called the universal donor?", "సార్వత్రిక దాతగా ఏ రక్త సమూహాన్ని పిలుస్తారు?",
     ["O negative", "AB positive", "A positive", "B negative"], ["O నెగటివ్", "AB పాజిటివ్", "A పాజిటివ్", "B నెగటివ్"], 0,
     "O-negative blood can be given to all recipients.", "O-నెగటివ్ రక్తం అందరికీ ఇవ్వవచ్చు."),
    ("The Tehri Dam, the tallest in India, is on which river?", "భారతదేశంలో ఎత్తైన టెహ్రీ డ్యామ్ ఏ నదిపై ఉంది?",
     ["Bhagirathi", "Alaknanda", "Yamuna", "Sutlej"], ["భాగీరథి", "అలకనంద", "యమునా", "సట్లెజ్"], 0,
     "Tehri Dam is built on the Bhagirathi river in Uttarakhand.", "టెహ్రీ డ్యామ్ ఉత్తరాఖండ్‌లో భాగీరథి నదిపై ఉంది."),
    ("Who is known as the 'Father of the Indian Constitution'?", "భారత రాజ్యాంగ పితామహుడిగా ఎవరు పిలువబడతారు?",
     ["B. R. Ambedkar", "Jawaharlal Nehru", "Rajendra Prasad", "Sardar Patel"],
     ["బి.ఆర్. అంబేద్కర్", "జవహర్‌లాల్ నెహ్రూ", "రాజేంద్ర ప్రసాద్", "సర్దార్ పటేల్"], 0,
     "Dr. B. R. Ambedkar chaired the Drafting Committee.", "డాక్టర్ బి.ఆర్. అంబేద్కర్ ముసాయిదా కమిటీ అధ్యక్షులు."),
    ("Which is the hardest naturally occurring substance?", "ప్రకృతిలో లభించే అత్యంత కఠినమైన పదార్థం ఏది?",
     ["Diamond", "Quartz", "Iron", "Granite"], ["వజ్రం", "క్వార్ట్జ్", "ఇనుము", "గ్రానైట్"], 0,
     "Diamond is the hardest natural substance (10 on Mohs scale).", "వజ్రం అత్యంత కఠినమైన సహజ పదార్థం (మోహ్స్ 10)."),
    ("The Kumbh Mela is held on the banks of which river in Allahabad (Prayagraj)?", "అలహాబాద్ (ప్రయాగ్‌రాజ్)లో కుంభమేళా ఏ నది ఒడ్డున జరుగుతుంది?",
     ["Ganga (Triveni Sangam)", "Yamuna alone", "Godavari", "Narmada"],
     ["గంగా (త్రివేణి సంగమం)", "యమునా మాత్రమే", "గోదావరి", "నర్మద"], 0,
     "Prayagraj hosts Kumbh at the Triveni Sangam (Ganga-Yamuna-Saraswati).", "ప్రయాగ్‌రాజ్‌లో త్రివేణి సంగమం (గంగా-యమున-సరస్వతి) వద్ద కుంభం."),
    ("Which Indian state has the highest forest cover by area?", "విస్తీర్ణం ప్రకారం అత్యధిక అటవీ ప్రాంతం ఉన్న భారత రాష్ట్రం ఏది?",
     ["Madhya Pradesh", "Arunachal Pradesh", "Chhattisgarh", "Odisha"], ["మధ్యప్రదేశ్", "అరుణాచల్ ప్రదేశ్", "ఛత్తీస్‌గఢ్", "ఒడిశా"], 0,
     "Madhya Pradesh has the largest forest cover in absolute area.", "సంపూర్ణ విస్తీర్ణంలో మధ్యప్రదేశ్ అటవీ ప్రాంతం అత్యధికం."),
    ("The Dandi March led by Gandhiji in 1930 was associated with which movement?", "1930లో గాంధీజీ నేతృత్వంలోని దండి యాత్ర ఏ ఉద్యమంతో సంబంధం కలిగి ఉంది?",
     ["Civil Disobedience (Salt Satyagraha)", "Non-Cooperation", "Quit India", "Khilafat"],
     ["శాసనోల్లంఘన (ఉప్పు సత్యాగ్రహం)", "సహాయ నిరాకరణ", "క్విట్ ఇండియా", "ఖిలాఫత్"], 0,
     "The Dandi March launched the Civil Disobedience Movement against the salt tax.", "దండి యాత్ర ఉప్పు పన్నుకు వ్యతిరేకంగా శాసనోల్లంఘన ఉద్యమాన్ని ప్రారంభించింది."),
    ("Which instrument is used to measure atmospheric pressure?", "వాతావరణ పీడనాన్ని కొలవడానికి ఉపయోగించే పరికరం ఏది?",
     ["Barometer", "Thermometer", "Hygrometer", "Anemometer"], ["బారోమీటర్", "థర్మామీటర్", "హైగ్రోమీటర్", "ఎనిమోమీటర్"], 0,
     "A barometer measures atmospheric pressure.", "బారోమీటర్ వాతావరణ పీడనాన్ని కొలుస్తుంది."),
    ("The famous 'Hampi' ruins are in which Indian state?", "ప్రసిద్ధ 'హంపి' శిథిలాలు ఏ భారత రాష్ట్రంలో ఉన్నాయి?",
     ["Karnataka", "Tamil Nadu", "Telangana", "Maharashtra"], ["కర్ణాటక", "తమిళనాడు", "తెలంగాణ", "మహారాష్ట్ర"], 0,
     "Hampi (Vijayanagara empire ruins) is in Karnataka.", "హంపి (విజయనగర సామ్రాజ్య శిథిలాలు) కర్ణాటకలో ఉన్నాయి."),
    ("How many players are there in a kabaddi team on the court?", "కోర్టులో ఒక కబడ్డీ జట్టులో ఎంతమంది ఆటగాళ్ళు ఉంటారు?",
     ["7", "5", "9", "11"], ["7", "5", "9", "11"], 0,
     "A kabaddi team has 7 players on the court.", "కబడ్డీలో కోర్టుపై 7 మంది ఆటగాళ్ళు ఉంటారు."),
]


def g_static_gk(rng):
    en, te, opts_en, opts_te, ans, expl_en, expl_te = rng.choice(_STATIC_GK)
    # shuffle options together, preserving the correct-answer link
    idx = list(range(4))
    rng.shuffle(idx)
    o_en = [opts_en[i] for i in idx]
    o_te = [opts_te[i] for i in idx]
    ai = idx.index(ans)
    return {"id": "", "channel": "CURRENT", "topic": "static gk",
            "q_en": en, "q_te": f"⤷ {te}", "options_en": o_en, "options_te": o_te,
            "answer_index": ai,
            "explanation_en": expl_en,
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
    """Generate one question for the target channel.
    CURRENT channel gets exam-aligned static GK (never news); aptitude
    channels get numeric/reasoning questions re-tagged to that channel."""
    if ch == "CURRENT":
        try:
            return g_static_gk(rng)
        except Exception:
            return None
    qs = generate_offline(1, seed=rng.randint(0, 10 ** 6))
    if not qs:
        return None
    q = qs[0]
    if ch in _APTITUDE_CHANNELS and q["channel"] in _APTITUDE_CHANNELS:
        q["channel"] = ch
    return q


def top_up(per_channel_min=20, max_add=400, use_llm=True):
    """
    Ensure every channel has >= per_channel_min UNUSED (never-posted) questions.
    Counts only unseen questions and rejects any newly-generated question whose
    content signature already exists — guaranteeing NO repeats, ever.
    """
    from .question_bank import load_bank, q_signature
    bank = load_bank()
    extra = load_json(config.BANK_EXTRA_JSON, {"questions": []})
    shown = load_json(config.DATA / "shown_signatures.json", {"sigs": []})
    used = load_json(config.STORE_USED, {})

    used_ids = {ch: set(ids) for ch, ids in used.items()}
    existing_sigs = set(shown.get("sigs", []))
    # include signatures of all questions already in the bank
    for q in bank + extra.get("questions", []):
        existing_sigs.add(q_signature(q))

    have_unused = {ch: 0 for ch in config.PUBLIC_CHANNELS}
    for q in bank + extra.get("questions", []):
        ch = q.get("channel")
        if ch in have_unused and q["id"] not in used_ids.get(ch, set()):
            if q_signature(q) not in set(shown.get("sigs", [])):
                have_unused[ch] += 1

    added = []
    counter = len({q["id"] for q in extra.get("questions", [])})
    rng = random.Random()
    order = sorted(config.PUBLIC_CHANNELS, key=lambda c: have_unused.get(c, 0))
    for ch in order:
        # CURRENT can now top up from offline static-GK facts, but the pool is
        # finite (facts list), so its target floor is smaller to avoid
        # exhausting signature space on one run.
        target = n_min_current if ch == "CURRENT" else per_channel_min
        need = max(0, target - have_unused.get(ch, 0))
        made = tries = 0
        recent_topics = set()
        while made < need and len(added) < max_add and tries < need * 10:
            tries += 1
            q = _generate_for_channel(ch, rng)
            if not q:
                continue
            if validate_question(q):
                continue
            # HARD no-repeat: reject duplicate content signature
            sig = q_signature(q)
            if sig in existing_sigs:
                continue
            # topic variety within a fresh batch
            tkey = q["topic"]
            if tkey in recent_topics and rng.random() < 0.5:
                continue
            recent_topics.add(tkey)
            if len(recent_topics) > 8:
                recent_topics.pop()
            counter += 1
            q["id"] = f"G{counter:03d}"
            added.append(q)
            existing_sigs.add(sig)
            have_unused[ch] = have_unused.get(ch, 0) + 1
            made += 1
    extra.setdefault("questions", []).extend(added)
    save_json_atomic(config.BANK_EXTRA_JSON, extra)
    from .question_bank import rebuild_json
    qs, errs = rebuild_json()
    return added, errs


n_min_current = 12   # CURRENT channel relies on curated/LLM GK — smaller pool


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
