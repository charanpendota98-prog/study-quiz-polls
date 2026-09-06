#!/usr/bin/env python3
"""
COMPATIBILITY WRAPPER — the multi-provider rotator now lives in
core/llm.py (Groq -> DeepSeek -> OpenAI -> Gemini, every key rotated).
This file preserves the old import path (`from multi_api_rotator import MultiAPI`)
and old attributes (.groq / .gemini / health_report) while adding the new
providers and a working chat() method.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core.llm import LLM as _LLM


class MultiAPI(_LLM):
    """Back-compat alias. Adds .groq/.gemini style health on top of core LLM."""
    def __init__(self, shuffle=False):
        super().__init__()
        self.shuffle = shuffle

    def health_report(self):
        report = super().health_report()
        print(report)
        return report


# Back-compat module-level key lists
_llm = _LLM()
GROQ_KEYS = _llm.groq
GEMINI_KEYS = _llm.gemini
DEEPSEEK_KEYS = _llm.deepseek
OPENAI_KEYS = _llm.openai
BOT_TOKEN = None
ADMIN_ID = None

from core import config  # noqa: E402
BOT_TOKEN = config.BOT_TOKEN
ADMIN_ID = config.ADMIN_ID


if __name__ == "__main__":
    MultiAPI().health_report()
