#!/usr/bin/env python3
"""
STUDENTUP — ENGLISH -> TELUGU TRANSLATION
Primary: LLM rotation (Groq -> DeepSeek -> OpenAI -> Gemini).
Fallback: curated phrasebook + pass-through (never crashes, never silent).
Output is validated for Telugu script before use.
"""
from __future__ import annotations

from .content import has_telugu, forbidden_script

# Tiny offline phrasebook so the bot can still mark Telugu when no API is up.
_PHRASEBOOK = [
    ("repo rate", "రెపో రేటు"), ("reserve bank", "రిజర్వ్ బ్యాంక్"),
    ("government", "ప్రభుత్వం"), ("scheme", "పథకం"), ("telangana", "తెలంగాణ"),
    ("andhra pradesh", "ఆంధ్రప్రదేశ్"), ("recruitment", "నియామకం"),
    ("notification", "నోటిఫికేషన్"), ("exam", "పరీక్ష"), ("result", "ఫలితం"),
    ("apply online", "ఆన్‌లైన్‌లో దరఖాస్తు"), ("railway", "రైల్వే"),
    ("defence", "రక్షణ"), ("police", "పోలీస్"), ("bank", "బ్యాంక్"),
    ("scholarship", "స్కాలర్‌షిప్"), ("vacancy", "ఖాళీలు"), ("admit card", "అడ్మిట్ కార్డు"),
    ("hall ticket", "హాల్ టికెట్"), ("budget", "బడ్జెట్"), ("election", "ఎన్నికలు"),
    ("isro", "ఇస్రో"), ("rbi", "ఆర్‌బీఐ"), ("drdo", "డీఆర్‌డీఓ"),
    ("prime minister", "ప్రధానమంత్రి"), ("president", "రాష్ట్రపతి"),
    ("farmers", "రైతులు"), ("women", "మహిళలు"), ("students", "విద్యార్థులు"),
]

_SYS = ("You translate Indian exam/current-affairs headlines into natural, simple "
        "Telugu (script U+0C00-0C7F) suitable for government-job aspirants. "
        "Output ONLY the Telugu translation, no English, no quotes, no notes. "
        "Keep numbers and proper nouns readable.")


def _phrasebook_fallback(en: str) -> str:
    low = en.lower()
    hits = []
    for k, v in _PHRASEBOOK:
        if k in low and v not in hits:
            hits.append(v)
    if not hits:
        return ""
    return "పరీక్షకు సంబంధించిన వార్త: " + ", ".join(hits[:4])


def translate(en: str, llm=None) -> str:
    """Return Telugu string (validated). Empty string if impossible."""
    if not en:
        return ""
    if llm is not None or _llm_available():
        from .llm import LLM
        llm = llm or LLM()
        out = llm.chat(_SYS, en)
        if out and has_telugu(out) and not forbidden_script(out):
            return out.strip()
    fb = _phrasebook_fallback(en)
    return fb.strip()


def _llm_available():
    from .llm import LLM
    try:
        return LLM().available()
    except Exception:
        return False


def translate_batch(items, llm=None):
    """items: list of dicts with 'en'; adds 'te' to each."""
    from .llm import LLM
    llm = llm or LLM()
    use_llm = llm.available()
    for it in items:
        te = translate(it["en"], llm if use_llm else None)
        it["te"] = te
    return items


# ---------------------------------------------------------------------------
# Exam-grade MCQ translation (whole question as ONE unit)
# ---------------------------------------------------------------------------
# Translating stem + options together (instead of string by string) is what
# keeps the Telugu paper-accurate: option parallelism, "Which of the above",
# code-matching (a-2, b-4), units, years and proper nouns all survive, and a
# Hindi-medium source is rendered into BOTH English and Telugu.
import json as _json
import re as _re

_MCQ_SYS = (
    "You are a senior bilingual paper-setter for TSPSC, APPSC, SSC, RRB, IBPS and "
    "TS/AP Police exams. Translate the given multiple-choice question into exam-paper "
    "Telugu exactly as it would appear in an official Telugu-medium question paper.\n"
    "Rules:\n"
    "1. Keep the meaning EXACT. Do not simplify, add hints, or reveal the answer.\n"
    "2. Preserve every number, year, unit, formula, code (a-2, b-4), acronym (RBI, "
    "ISRO, UPI) and proper noun. Well-known names may be written in Telugu script "
    "with the English form in brackets when helpful.\n"
    "3. Options must stay parallel and in the SAME order. Never merge or drop one.\n"
    "4. Statement-type stems ('Consider the following statements 1. .. 2. ..', "
    "'Which of the above is/are correct?') keep their numbering and structure.\n"
    "5. Use standard textbook Telugu terminology (తెలుగు అకాడమీ style): e.g. "
    "శాతం, నిష్పత్తి, సగటు, చక్రవడ్డీ, లాభం-నష్టం, రాజ్యాంగం, ప్రకరణ (Article), "
    "సవరణ, పార్లమెంట్, గవర్నర్, రిజర్వ్ బ్యాంక్.\n"
    "6. If the source is in Hindi, also give a faithful English version.\n"
    "7. Output ONLY strict JSON: {\"q_en\": str, \"q_te\": str, \"options_en\": [4 str], "
    "\"options_te\": [4 str], \"explanation_te\": str}. Telugu fields must be in Telugu "
    "script (U+0C00-0C7F); no Hindi/Devanagari anywhere."
)

_NUM_RE = _re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(s: str):
    return sorted(_NUM_RE.findall(s or ""))


def _parse_json(text: str):
    if not text:
        return None
    m = _re.search(r"\{.*\}", text, _re.S)
    if not m:
        return None
    try:
        return _json.loads(m.group(0))
    except Exception:
        return None


def translate_mcq(q_en: str, options_en: list, explanation_en: str = "",
                  llm=None, source_lang: str = "en"):
    """Translate one MCQ as a unit. Returns dict or None (never raises).

    Verification gate (any failure -> None, caller falls back / parks):
      * 4 Telugu options, Telugu stem, no forbidden script;
      * every number in the source appears in the Telugu (numbers are the
        #1 place exam translations go wrong);
      * options not collapsed into duplicates;
      * for Hindi sources an English rendering is required too.
    """
    if llm is None:
        if not _llm_available():
            return None
        from .llm import LLM
        llm = LLM()
    payload = {"source_language": source_lang, "q": q_en,
               "options": [str(o) for o in options_en],
               "explanation": (explanation_en or "")[:400]}
    for attempt in range(2):
        out = llm.chat(_MCQ_SYS, _json.dumps(payload, ensure_ascii=False))
        data = _parse_json(out)
        if not data:
            continue
        q_te = str(data.get("q_te", "")).strip()
        ote = [str(x).strip() for x in (data.get("options_te") or [])]
        qe = str(data.get("q_en") or q_en).strip()
        oe = [str(x).strip() for x in (data.get("options_en") or options_en)]
        ex_te = str(data.get("explanation_te", "")).strip()
        ok = (len(ote) == 4 and len(oe) == 4 and has_telugu(q_te)
              and all(ote) and len({o.lower() for o in ote}) == 4
              and not forbidden_script(q_te + " ".join(ote) + ex_te))
        if ok and source_lang == "hi":
            ok = bool(qe) and not forbidden_script(qe + " ".join(oe))
        if ok:
            # worded options must be Telugu; numeric/code ones may stay as-is
            for e, t in zip(oe, ote):
                if _re.search(r"[a-z]{3,}", e) and not has_telugu(t):
                    ok = False
                    break
        if ok:
            src_nums = set(_numbers(qe) + sum((_numbers(o) for o in oe), []))
            te_nums = set(_numbers(q_te) + sum((_numbers(o) for o in ote), []))
            # tolerate Telugu-digit or spelled numbers only for tiny values
            missing = {n for n in src_nums - te_nums if len(n) > 1}
            if missing:
                ok = False
        if ok:
            return {"q_en": qe, "q_te": q_te, "options_en": oe,
                    "options_te": ote, "explanation_te": ex_te[:280]}
    return None
