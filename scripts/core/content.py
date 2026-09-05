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
_PROTECT = re.compile(r"\b(factory|factories|dramatic|remain|remains|commissioners?)\b", re.I)

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


def build_question_text(q: dict, channel_cfg: dict) -> str:
    """
    Compose the poll question (≤300 chars).
    Format: {emoji} {subject} • Q{n}
            {English question}
            {Telugu question}
    """
    en = (q.get("q_en") or "").strip()
    te = (q.get("q_te") or "").lstrip("⤷").strip()
    header = f"{channel_cfg['emoji']} {channel_cfg['subject']} • {q.get('topic','').title()}"
    body = en
    if te:
        body += f"\n⤷ {te}"
    text = f"{header}\n{body}"
    return _clamp(text, 300)


def build_options(q: dict) -> list:
    """
    Merge EN + TE into exactly 4 option strings (≤100 chars each).
    Style: "A) English — Telugu" (Telugu omitted if it would overflow).
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
        opt = f"{letters[i]}) {e}"
        if t and t != e:
            merged = f"{opt} — {t}"
            if len(merged) <= 100:
                opt = merged
        out.append(_clamp(opt, 100))
    return out


def build_explanation(q: dict) -> str:
    expl = (q.get("explanation_en") or q.get("note") or "").strip()
    if not expl:
        return ""
    te = q.get("explanation_te", "")
    text = f"✅ {expl}"
    if te:
        text += f"\n⤷ {te.lstrip('⤷').strip()}"
    return _clamp(text, 200)


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
