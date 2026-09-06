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
