"""
STUDENTUP CORE PACKAGE — India's most advanced Telegram quiz-poll engine
for Telangana (TS) & Andhra Pradesh (AP) aspirants.

Modules:
    config        — channels, schedule, policies, env loading, IST clock
    store         — atomic JSON stores + TTL + Jaccard/shingle dedup
    telegram      — Bot API client (sendQuiz / sendMessage / poll updates), stdlib+requests
    llm           — multi-provider key rotation (Groq, Gemini, DeepSeek, OpenAI)
    content       — blocked/context filters, Telugu validation, bilingual formatters
    question_bank — load canonical JSON bank, markdown parser, rotation, validation gate
    generator     — offline procedural Q generator (infinite, verified) + LLM generation
    feeds         — RSS aggregator (stdlib + feedparser fallback), 2-tier filter, dedup
    translator    — English -> Telugu via LLM rotation, graceful fallback
    leaderboard   — poll-answer tracking, streaks, weekly leaderboard (groups)
"""

__version__ = "3.0.0-ultra"
