#!/usr/bin/env python3
"""
STUDENTUP — CONTENT POLICY
- Blocked-topic filter (cricket / films / weather / job-cuts ...).
- 2-tier jobs filter (ACTION words + CONTEXT words) + other-state hard block.
- Telugu script validation (U+0C00–0C7F) + forbidden Indic-script rejection.
- Bilingual poll formatting (English + Telugu within Telegram limits).
All regexes use the lessons hard-won in production (word boundaries, lookarounds).
"""
from __future__ import annotations

import re
from . import config
import unicodedata

# ---------------------------------------------------------------------------
# Script ranges
# ---------------------------------------------------------------------------
TELUGU_RANGE = (0x0C00, 0x0C7F)
FORBIDDEN_SCRIPTS = {
    "Devanagari/Hindi": (0x0900, 0x097F),
    "Bengali": (0x0980, 0x09FF),
    "Gurmukhi": (0x0A00, 0x0A7F),
    "Gujarati": (0x0A80, 0x0AFF),
    "Oriya": (0x0B00, 0x0B7F),
    "Tamil": (0x0B80, 0x0BFF),
    "Kannada": (0x0C80, 0x0CFF),
    "Malayalam": (0x0D00, 0x0D7F),
    "Sinhala": (0x0D80, 0x0DFF),
    "Myanmar": (0x1000, 0x109F),
}


def _in_range(ch: str, rng) -> bool:
    return rng[0] <= ord(ch) <= rng[1]


def has_telugu(text: str) -> bool:
    return any(_in_range(c, TELUGU_RANGE) for c in text)


def telugu_count(text: str) -> int:
    return sum(1 for c in text if _in_range(c, TELUGU_RANGE))


def forbidden_script(text: str):
    """Return name of a forbidden Indic script present, else None."""
    for name, rng in FORBIDDEN_SCRIPTS.items():
        for c in text:
            if _in_range(c, rng):
                return name
    return None


# ---------------------------------------------------------------------------
# Blocked topics (exam-irrelevant entertainment / noise)
# ---------------------------------------------------------------------------
_BLOCK_RAW = [
    r"cricket", r"\bipl\b", r"football", r"soccer", r"bollywood", r"tollywood",
    r"telugu film", r"\bmovies?\b", r"\bfilms?\b", r"cinema", r"celebrity",
    r"\bactors?\b", r"actress", r"singers?", r"box office", r"web series",
    r"viral video", r"\bdrama\b", r"dramatic", r"weather forecast",
    r"film festival", r"music album", r"\bsongs?\b", r"composers?", r"soundtracks?",
    r"directors?", r"concerts?", r"\balbums?\b", r"\bweather\b",
    r"job cuts?", r"layoffs?", r"jobless", r"job loss",
]
BLOCKED_REGEX = re.compile("|".join(_BLOCK_RAW), re.IGNORECASE)

# Words that legitimately contain blocked substrings — protected.
# (e.g. "national song" is a GK topic, not music; "factory" contains no block)
_PROTECT = re.compile(
    r"\b(factory|factories|dramatic|remain|remains|commissioners?)\b|national song",
    re.I)

# Other-state hard block (jobs/CA must be TS/AP + central/pan-India only)
_OTHER_STATE = [
    r"karnataka", r"maharashtra", r"tamil nadu", r"kerala", r"punjab", r"rajasthan",
    r"gujarat", r"madhya pradesh", r"\bmp\b", r"chhattisgarh", r"odisha", r"bihar",
    r"uttar pradesh", r"\bup\b", r"west bengal", r"assam", r"\bgoa\b", r"himachal",
    r"jammu", r"kashmir", r"andaman", r"ladakh", r"northeast", r"sikkim", r"haryana",
    r"\bdelhi\b(?!\s*capital)", r"jharkhand", r"puducherry", r"chandigarh",
]
OTHER_STATE_REGEX = re.compile("|".join(_OTHER_STATE), re.IGNORECASE)

CENTRAL_WORDS = ["government", "scheme", "yojana", "union", "central", "indian",
                 "nationwide", "india", "pm-", "prime minister", "president", "rbi",
                 "isro", "drdo", "parliament", "supreme court"]

# Jobs 2-tier filter
ACTION_WORDS = [
    "recruit", "vacancy", "notification", "admit card", "hall ticket", "apply online",
    "apply offline", "apply before", "eligibility", "scholarship", "stipend",
    r"\bjobs?\b", r"\bexam", r"\bexams\b", r"\bmains\b", r"\bprelims\b",
    r"\bresults?\b", "selection", "shortlist", "interview", "answer key", "cutoff",
    "walk-in", "appointment notification", "posts out", "posts for", "posts open",
    "openings", "list released", "list out", "pension yojana", "pension scheme",
    "name list", "status check", "check status", "search name", "download pdf",
    "register", "registration", "last date",
]
CONTEXT_WORDS = [
    "telangana", r"\bts\b", "andhra", r"\bap\b", "tspsc", "appsc", "tsgenco",
    "tsspdcl", "tdpdcl", "hyderabad", "vijayawada", "visakhapatnam", "guntur",
    "nellore", "kurnool", "warangal", "karimnagar", "tirupati", "bank", "ibps",
    "sbi", r"\brrb\b", "railway", "police", "constable", "army", r"\bnda\b",
    r"\bcds\b", "agniveer", "defence", "central", "union", "indian", "nationwide",
    "government", "sarkari", "group ii", "group iii", "group iv", r"\bssc\b",
    r"\bupsc\b", "isro", r"\bpsu\b", r"\biit\b", "yojana", "scheme", "clerk",
    "officer", "engineer", "assistant", "manager", "steno", "technical", "fellow",
    "scientist", "lecturer", "professor", "nurse", "peon", "trainee", "executive",
    "si ", "sub-inspector",
]
ACTION_REGEX = re.compile("|".join(ACTION_WORDS), re.IGNORECASE)
CONTEXT_REGEX = re.compile("|".join(CONTEXT_WORDS), re.IGNORECASE)


def is_blocked(text: str):
    """Return (blocked: bool, reason: str|None)."""
    scan = _PROTECT.sub(" ", text)
    if BLOCKED_REGEX.search(scan):
        return True, "blocked_topic"
    return False, None


def is_other_state(text: str):
    if OTHER_STATE_REGEX.search(text):
        low = text.lower()
        if not any(w in low for w in CENTRAL_WORDS):
            return True
    return False


def jobs_relevance(text: str) -> str:
    """
    2-tier jobs filter.
      keep  -> ACTION + CONTEXT present (strong)
      weak  -> only one tier (candidate, needs translation/context)
      drop  -> neither, or blocked / other-state
    """
    blocked, why = is_blocked(text)
    if blocked:
        return "drop:" + why
    if is_other_state(text):
        return "drop:other_state"
    has_action = bool(ACTION_REGEX.search(text))
    has_context = bool(CONTEXT_REGEX.search(text))
    if has_action and has_context:
        return "keep"
    if has_action or has_context:
        return "weak"
    return "drop:no_relevance"


def ca_relevance(text: str) -> bool:
    """CA keeps exam-relevant vocabulary; blocks entertainment/noise."""
    blocked, _ = is_blocked(text)
    if blocked:
        return False
    return True


# ---------------------------------------------------------------------------
# Bilingual poll formatting
# ---------------------------------------------------------------------------
def _clamp(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_question_text(q: dict, channel_cfg: dict, telugu_first: bool = True,
                        position: str = "", badge: str = "") -> str:
    """
    Compose the poll question (≤300 chars).
    Telugu-first (default for TS/AP aspirants):
      {emoji} {subject} • {topic}            ← + "Q 3/10 • 🔥 Hard • ⏱ 1.5 min" in paced rounds
      {Telugu question}
      {English question}
    """
    en = (q.get("q_en") or "").strip()
    te = (q.get("q_te") or "").lstrip("⤷").strip()
    header = f"{channel_cfg['emoji']} {channel_cfg['subject']} • {q.get('topic','').title()}"
    try:
        from .pyq import pyq_label
        prov = pyq_label(q)
    except Exception:
        prov = ""
    meta = " • ".join(x for x in (position, badge, prov) if x)
    if meta:
        header += f"\n{meta}"
    if telugu_first and te:
        body = f"{te}"
        if en:
            body += f"\n{en}"
    else:
        body = en
        if te:
            body += f"\n⤷ {te}"
    text = f"{header}\n{body}"
    return _clamp(text, 300)


def build_options(q: dict, telugu_first: bool = True) -> list:
    """
    Merge EN + TE into exactly 4 option strings (≤100 chars each).
    Telugu-first style: "A) Telugu — English" (falls back to EN-only if needed).
    """
    letters = ["A", "B", "C", "D"]
    en = q.get("options_en", [])
    te = [t.lstrip("⤷").strip() for t in q.get("options_te", [])]
    out = []
    for i in range(4):
        e = (en[i] if i < len(en) else "").strip()
        t = (te[i] if i < len(te) else "").strip()
        # Strip a leading "A)" if the source already has it
        e = re.sub(r"^[A-D][\)\.\:]\s*", "", e)
        t = re.sub(r"^[A-D][\)\.\:]\s*", "", t)
        if telugu_first and t:
            opt = f"{letters[i]}) {t}"
            if e and e != t:
                merged = f"{opt} — {e}"
                if len(merged) <= 100:
                    opt = merged
        else:
            opt = f"{letters[i]}) {e}"
            if t and t != e:
                merged = f"{opt} — {t}"
                if len(merged) <= 100:
                    opt = merged
        out.append(_clamp(opt, 100))
    return out


def build_explanation(q: dict, telugu_first: bool = True) -> str:
    expl = (q.get("explanation_en") or q.get("note") or "").strip()
    te = (q.get("explanation_te") or "").lstrip("⤷").strip()
    if not expl and not te:
        return ""
    try:
        from .verifier import status_of
        verified = status_of(q.get("id", "")) in ("ok", "fixed")
    except Exception:
        verified = False
    tick = "✅" if not verified else "✅✔"   # ✔ = API-key audited answer + Telugu
    if telugu_first and te:
        text = f"{tick} {te}"
        if expl:
            text += f"\n{expl}"
    else:
        text = f"{tick} {expl}" if expl else tick
        if te:
            text += f"\n⤷ {te}"
    return _clamp(text, 200)


def build_answer_key(questions: list, round_label: str = "") -> str:
    """
    Delayed answer-key message (posted AFTER the quiz window closes).
    Lists correct option letter + short bilingual explanation per question.
    Used when ANSWER_MODE=delayed so polls hide the key until the round ends.
    """
    letters = "ABCD"
    label = f"{round_label} " if round_label else ""
    lines = [f"🔑 {label}Answer Key — సమాధానాలు\n"]
    for i, q in enumerate(questions, 1):
        idx = int(q.get("answer_index", 0))
        letter = letters[idx] if 0 <= idx < 4 else "?"
        topic = q.get("topic", "")
        opts = q.get("options_en") or []
        tops = q.get("options_te") or []
        en_opt = str(opts[idx]).strip() if 0 <= idx < len(opts) else ""
        te_opt = str(tops[idx]).lstrip("⤷").strip() if 0 <= idx < len(tops) else ""
        ans = te_opt or en_opt
        if te_opt and en_opt and te_opt != en_opt:
            ans = f"{te_opt} / {en_opt}"
        line = f"{i}. {topic} → [{letter}] {ans}" if topic else f"{i}. [{letter}] {ans}"
        expl_te = (q.get("explanation_te") or "").lstrip("⤷").strip()
        expl_en = (q.get("explanation_en") or q.get("note") or "").strip()
        if expl_te:
            line += f"\n   {expl_te}"
        elif expl_en:
            line += f"\n   {expl_en}"
        lines.append(line)
    lines.append("\n— StudentUp | PYQ-first · no repeats ✅")
    return _clamp("\n".join(lines), 4000)


def build_round_report(questions: list, round_label: str = "", channel_cfg: dict | None = None,
                       poll_stats: dict | None = None) -> str:
    """
    Post-round REPORT CARD (posted right after the last poll closes):
      • Q-by-Q line: number · topic · difficulty · correct letter + answer (TE/EN)
        · % of voters who got it right (when poll stats available)
      • Subject split, PYQ count, hardest question, quick revision tags
    Always ≤ 4000 chars.
    """
    from .blueprint import difficulty_of, subject_of
    letters = "ABCD"
    icon = {"easy": "⚡", "medium": "🔶", "hard": "🔥"}
    label = f"{round_label} " if round_label else ""
    head = f"{channel_cfg['emoji']} " if channel_cfg else ""
    lines = [f"{head}📋 {label}Round Report — రౌండ్ రిపోర్ట్", ""]
    subs, hard, pyq = {}, [], 0
    hardest = None
    for i, q in enumerate(questions, 1):
        idx = int(q.get("answer_index", 0))
        letter = letters[idx] if 0 <= idx < 4 else "?"
        opts = q.get("options_en") or []
        tops = q.get("options_te") or []
        en_opt = str(opts[idx]).strip() if 0 <= idx < len(opts) else ""
        te_opt = str(tops[idx]).lstrip("⤷").strip() if 0 <= idx < len(tops) else ""
        ans = te_opt or en_opt
        if te_opt and en_opt and te_opt != en_opt:
            ans = f"{te_opt} / {en_opt}"
        d = difficulty_of(q)
        sub = subject_of(q)
        subs[sub] = subs.get(sub, 0) + 1
        if q.get("source") == "pyq":
            pyq += 1
        topic = (q.get("topic") or sub).title()
        pct = ""
        st = (poll_stats or {}).get(q.get("id")) if poll_stats else None
        if st and st.get("total"):
            p = round(100 * st.get("correct", 0) / st["total"])
            pct = f" · ✅{p}%"
            if hardest is None or p < hardest[1]:
                hardest = (i, p, topic)
        src = " · 📜PYQ" if q.get("source") == "pyq" else ""
        lines.append(f"{i}. {icon[d]} {topic}{src} → [{letter}] {ans[:60]}{pct}")
    names = {"gk": "GK", "reasoning": "Reasoning", "quant": "Aptitude", "english": "English"}
    split = " · ".join(f"{names.get(k, k.title())} {v}" for k, v in sorted(subs.items(), key=lambda kv: -kv[1]))
    n_hard = sum(1 for q in questions if difficulty_of(q) == "hard")
    lines += ["", f"📚 {split} · 📜 PYQ {pyq}/{len(questions)} · 🔥 Hard {n_hard}"]
    if hardest:
        lines.append(f"🧠 Toughest: Q{hardest[0]} ({hardest[2]}) — only {hardest[1]}% got it")
    weak_topics = [(q.get("topic") or "").title() for q in questions
                   if difficulty_of(q) == "hard" and q.get("topic")]
    if weak_topics:
        lines.append("🔁 Revise today / ఈరోజు రివిజన్: " + ", ".join(dict.fromkeys(weak_topics[:4])))
    lines += ["", "🏆 Scores & district rank: /quiz · /district in our bot ⭐",
              "— StudentUp | PYQ-first · no repeats ✅"]
    return _clamp("\n".join(lines), 4000)


# ---------------------------------------------------------------------------
# Validation gate for a single question
# ---------------------------------------------------------------------------
def _needs_telugu(text: str) -> bool:
    """
    A line needs Telugu translation only if it carries a real English word
    (>=3 consecutive lowercase letters). Pure numbers (28), codes (BSNZ),
    currency (₹9,000) and all-caps acronyms are language-neutral.
    """
    return re.search(r"[a-z]{3,}", text or "") is not None


def validate_question(q: dict) -> list:
    """Return list of error strings (empty = valid)."""
    errs = []
    qid = q.get("id", "?")
    en, te = q.get("q_en", ""), q.get("q_te", "")
    if not en:
        errs.append(f"{qid}: missing q_en")
    if not te or not te.strip():
        errs.append(f"{qid}: Telugu question missing/empty (q_te)")
    elif _needs_telugu(en) and not has_telugu(te):
        errs.append(f"{qid}: English question has words but q_te has no Telugu script")
    fb = forbidden_script(te)
    if fb:
        errs.append(f"{qid}: forbidden script {fb} in Telugu question")
    oe = q.get("options_en", [])
    ot = q.get("options_te", [])
    if len(oe) != 4 or any(not str(x).strip() for x in oe):
        errs.append(f"{qid}: need exactly 4 non-empty EN options (got {len(oe)})")
    if len(ot) != 4 or any(not str(x).strip() for x in ot):
        errs.append(f"{qid}: need 4 non-empty TE options (got {len(ot)})")
    else:
        for i, (e, t) in enumerate(zip(oe, ot)):
            if _needs_telugu(str(e)) and not has_telugu(str(t)):
                errs.append(f"{qid}: TE option {i} has no Telugu script for worded option {str(e)[:20]!r}")
                break
    idx = q.get("answer_index")
    if not isinstance(idx, int) or not (0 <= idx <= 3):
        errs.append(f"{qid}: answer_index must be 0-3 (got {idx!r})")
    if len(en) > 300:
        errs.append(f"{qid}: English question >300 chars")
    for i, o in enumerate(oe):
        if len(str(o)) > 90:
            errs.append(f"{qid}: EN option {i} too long ({len(o)})")
    blocked, why = is_blocked(en + " " + " ".join(map(str, oe)))
    if blocked:
        errs.append(f"{qid}: blocked topic ({why})")
    # duplicate options
    if len({str(x).strip().lower() for x in oe}) < 4:
        errs.append(f"{qid}: duplicate EN options")
    return errs


# ---------------------------------------------------------------------------
# ANSWER-LEAK GUARD + OPTION BALANCING (applied at send time, never stored)
# ---------------------------------------------------------------------------
_MARK_RE = re.compile(r"(✅|✔|☑|✓|\(\s*correct\s*\)|\[\s*correct\s*\]|\*\s*$|"
                      r"\bans(?:wer)?\s*[:\-–]\s*[A-Da-d]\b)", re.I)
_FIXED_ORDER_RE = re.compile(r"\b(all|none|both|neither|either)\b.*\b(above|these|them|a|b|c|d)\b|"
                             r"\bonly\s+[a-d1-4]\b|\b[1-4a-d]\s*(and|&|,)\s*[1-4a-d]\b|"
                             r"\bcannot be determined|\bdata (in)?adequate", re.I)


def strip_answer_markers(text: str) -> str:
    """Remove any tick/'(correct)'/'Ans: B' markers that would betray the key."""
    return _MARK_RE.sub("", text or "").strip()


def answer_leaks(q: dict) -> str:
    """'' if safe, else a short reason the poll would expose its own answer."""
    opts = q.get("options_en") or []
    ai = q.get("answer_index")
    if not isinstance(ai, int) or not 0 <= ai < len(opts):
        return "bad_answer_index"
    for o in list(opts) + list(q.get("options_te") or []):
        if _MARK_RE.search(str(o or "")):
            return "marker_in_option"
    stem = f"{q.get('q_en','')} {q.get('q_te','')}".lower()
    ans = str(opts[ai] or "").strip().lower()
    if len(ans) > 3 and re.search(r"\b" + re.escape(ans) + r"\b", stem):
        return "answer_in_stem"
    if _MARK_RE.search(stem):
        return "marker_in_stem"
    return ""


def _is_fixed_order(opts) -> bool:
    """Options that must keep their order: 'All of the above', 'Both A and B',
    strictly sorted numeric ladders (10/20/30/40), year ladders."""
    txt = [str(o or "").strip() for o in opts]
    if any(_FIXED_ORDER_RE.search(o) for o in txt):
        return True
    nums = []
    for o in txt:
        m = re.fullmatch(r"[\s₹$]*(-?\d[\d,]*(?:\.\d+)?)\s*[%a-zA-Z/²³]*", o)
        if not m:
            return False
        nums.append(float(m.group(1).replace(",", "")))
    return nums == sorted(nums) or nums == sorted(nums, reverse=True)


def balance_options(q: dict, seed: str = "") -> dict:
    """Return a COPY of q with options shuffled so the key isn't predictably 'B'.
    Deterministic for (question id, seed) so channel poll, DM mirror, report and
    answer-key all agree. Fixed-order option sets are left untouched."""
    opts = list(q.get("options_en") or [])
    ai = q.get("answer_index")
    if len(opts) != 4 or not isinstance(ai, int) or not 0 <= ai < 4 or _is_fixed_order(opts):
        return dict(q)
    import hashlib
    import random as _r
    h = hashlib.sha256(f"{q.get('id','')}|{seed}".encode()).hexdigest()
    rng = _r.Random(int(h[:12], 16))
    perm = [0, 1, 2, 3]
    rng.shuffle(perm)                    # perm[new_pos] = old_pos
    te = list(q.get("options_te") or [])
    out = dict(q)
    out["options_en"] = [strip_answer_markers(opts[i]) for i in perm]
    if len(te) == 4:
        out["options_te"] = [strip_answer_markers(te[i]) for i in perm]
    out["answer_index"] = perm.index(ai)
    out["_perm"] = perm
    return out


def poll_safe(q: dict, seed: str = "") -> dict | None:
    """Send-time gate: strip markers, balance the key position, refuse leaky
    questions. Returns the safe copy or None (caller picks another question)."""
    q2 = balance_options(q, seed) if getattr(config, "BALANCE_OPTIONS", True) else dict(q)
    q2["q_en"] = strip_answer_markers(q2.get("q_en", ""))
    q2["q_te"] = strip_answer_markers(q2.get("q_te", ""))
    q2["options_en"] = [strip_answer_markers(o) for o in q2.get("options_en") or []]
    if q2.get("options_te"):
        q2["options_te"] = [strip_answer_markers(o) for o in q2["options_te"]]
    return None if answer_leaks(q2) else q2
