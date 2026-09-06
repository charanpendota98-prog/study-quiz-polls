#!/usr/bin/env python3
"""
STUDENTUP — CENTRAL CONFIGURATION
Channels, schedule (IST), content policy, env loading, paths, clock.
All paths are project-relative so the engine runs anywhere (server / sandbox / CI).
"""
from __future__ import annotations

import os
from pathlib import Path
from datetime import timezone, timedelta
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Paths — resolved from the repo / deploy root, NOT hard-coded to /home/ubuntu
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]          # .../studentup (project root)
DATA = ROOT / "data"
SCRIPTS = ROOT / "scripts"
SOURCES = ROOT / "sources"
LOGS = ROOT / "logs"
ENV_FILE = ROOT / "env" / ".env"
CORE = SCRIPTS / "core"

for d in (DATA, LOGS):
    d.mkdir(parents=True, exist_ok=True)

# Canonical question bank files (JSON = machine source of truth, MD = human)
BANK_JSON = DATA / "question_bank.json"
BANK_EXTRA_JSON = DATA / "question_bank_extra.json"
BANK_MD = DATA / "quiz_bank_advanced.md"
BANK_PYQ_JSON = DATA / "pyq_bank.json"
CURATED_EXTRA_JSON = DATA / "curated_extra.json"
MEMBERS_JSON = DATA / "members.json"
CA_CURATED_JSON = DATA / "ca_curated.json"
TIPS_JSON = DATA / "study_tips.json"

# Runtime stores (created on demand)
STORE_USED = DATA / "used_questions.json"
STORE_CA_SEEN = DATA / "ca_seen.json"
STORE_JOBS_SEEN = DATA / "jobs_seen.json"
STORE_GLOBAL_SEEN = DATA / "global_seen.json"
STORE_POLL_STATE = DATA / "poll_state.json"
STORE_LEADERBOARD = DATA / "leaderboard.json"
STORE_STATS = DATA / "stats.json"

# ---------------------------------------------------------------------------
# Time — India Standard Time (UTC+5:30)
# ---------------------------------------------------------------------------
IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def now_ist():
    from datetime import datetime
    return datetime.now(IST)


# ---------------------------------------------------------------------------
# Environment loading (.env) — supports prefixed key rotation
# ---------------------------------------------------------------------------
def load_env(path: Path = ENV_FILE) -> None:
    """Load KEY=VALUE pairs from .env into os.environ (does not overwrite)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        os.environ.setdefault(key, val)


load_env()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


BOT_TOKEN = env("BOT_TOKEN")
ADMIN_ID = env("ADMIN_ID")
DRY = env("STUDENTUP_DRY", "").lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Channels — the 7 public + 1 private matrix
# Chat ids come from env:  CHANNEL_TSPSC=@handlename  or  CHANNEL_TSPSC=-1001234567890
# If unset, the public @username (below) is used for display / send-by-username.
# ---------------------------------------------------------------------------
CHANNELS = {
    "TSPSC": {
        "name": "TSPSC",
        "emoji": "📘",
        "subject": "TSPSC Reasoning",
        "public": True,
        "title": "StudentUp TSPSC Quiz (TS & AP)",
        "username": "StudentUpTSPSC",          # @StudentUpTSPSC (no @ when stored)
        "audience": "TSPSC Group II / III / IV aspirants",
        "topics": ["syllogism", "coding", "seating", "number series", "analogy",
                   "direction", "statement-assumption", "figure count", "logical order",
                   "blood relation", "TS GK"],
        "ts_ap_weight": 0.45,                  # fraction that should be TS/AP-specific
    },
    "APPSC": {
        "name": "APPSC",
        "emoji": "📗",
        "subject": "APPSC Reasoning",
        "public": True,
        "title": "StudentUp APPSC Quiz (TS & AP)",
        "username": "StudentUpAPPSC",
        "audience": "APPSC Group II / III / IV aspirants",
        "topics": ["arithmetic series", "alphabetical logic", "data interpretation",
                   "non-verbal", "critical reasoning", "family tree", "seating",
                   "direction", "puzzle", "statement-conclusion", "AP GK"],
        "ts_ap_weight": 0.45,
    },
    "BANKING": {
        "name": "BANKING",
        "emoji": "🏦",
        "subject": "Banking Aptitude",
        "public": True,
        "title": "StudentUp Banking Quiz (TS & AP)",
        "username": "StudentUpBanking",
        "audience": "IBPS PO/Clerk | SBI | RRB NTPC/Clerk/ALP",
        "topics": ["percentage", "ratio", "profit-loss", "time-work", "compound interest",
                   "simple interest", "mixture", "data interpretation", "series",
                   "average", "banking awareness"],
        "ts_ap_weight": 0.20,
    },
    "RAILWAY": {
        "name": "RAILWAY",
        "emoji": "🚆",
        "subject": "Railway RRB",
        "public": True,
        "title": "StudentUp Railway RRB Quiz (TS & AP)",
        "username": "StudentUpRailway",
        "audience": "RRB NTPC | Group D | ALP",
        "topics": ["series", "analogy", "classification", "syllogism", "direction sense",
                   "logical sequence", "clock", "symbol logic", "number series",
                   "non-verbal figure", "calendar"],
        "ts_ap_weight": 0.20,
    },
    "POLICE": {
        "name": "POLICE",
        "emoji": "👮",
        "subject": "Police Exams",
        "public": True,
        "title": "StudentUp Police Exams Quiz (TS & AP)",
        "username": "StudentUpPolice",
        "audience": "TS/AP Police | Constable | SI | Sub-Inspector",
        "topics": ["opposite words", "coding-decoding", "blood relation",
                   "direction-distance", "figure count", "statement-conclusion",
                   "missing letter series", "syllogism", "analogy", "number series"],
        "ts_ap_weight": 0.35,
    },
    "DEFENCE": {
        "name": "DEFENCE",
        "emoji": "🎖️",
        "subject": "Defence Exams",
        "public": True,
        "title": "StudentUp Defence Exams Quiz (TS & AP)",
        "username": "StudentUpDefence",
        "audience": "NDA | CDS | Agniveer | CISF | Army/Navy/Air Force",
        "topics": ["defence GK", "logical", "numerical", "prime/cube series",
                   "direction", "coding-decoding", "analogy", "missing number",
                   "non-verbal squares", "statement-conclusion", "logical career order"],
        "ts_ap_weight": 0.15,
    },
    "CURRENT": {
        "name": "CURRENT",
        "emoji": "🗞️",
        "subject": "Current Affairs GK",
        "public": True,
        "title": "StudentUp Current Affairs GK Quiz (TS & AP)",
        "username": "StudentUpCurrent",
        "audience": "UPSC Prelims | TSPSC/APPSC | SSC | IBPS",
        "topics": ["government schemes", "ISRO", "RBI", "constitution", "defence",
                   "central budget", "elections", "railway infrastructure", "health schemes"],
        "ts_ap_weight": 0.30,
    },
    "JOBS": {
        "name": "JOBS",
        "emoji": "💼",
        "subject": "Jobs & Exams Updates",
        "public": False,                          # private channel — links allowed
        "title": "Telugu Jobs Updates StudentUp (PRIVATE)",
        "username": "StudentUpJobs",
        "audience": "All students — TS/AP + Central only",
        "topics": ["recruitment", "notification", "result", "admit card"],
        "ts_ap_weight": 0.60,
        "max_items": 5,
        "links": True,
    },
}

PUBLIC_CHANNELS = [k for k, v in CHANNELS.items() if v["public"] and k != "JOBS"]


def channel_chat_id(key: str) -> str:
    """
    Resolve the Telegram chat target for a channel.
    Priority: env CHANNEL_<KEY> (numeric id or @username) -> config username.
    """
    explicit = env(f"CHANNEL_{key}", "")
    if explicit:
        return explicit.strip()
    cfg = CHANNELS.get(key, {})
    uname = cfg.get("username", "")
    return f"@{uname}" if uname else ""


# ---------------------------------------------------------------------------
# Schedule (IST). Each entry maps an IST "HH:MM" to a task.
# Slots are minute-aligned; watch.py evaluates once per minute.
# ---------------------------------------------------------------------------
# TWO main quiz rounds a day (India No.1 cadence — morning + evening).
# Add a line (e.g. "13:30": ("quiz", {"slot": 3})) to add more rounds anytime.
SCHEDULE = {
    "06:00": ("filler", {"reason": "morning top-up"}),
    "07:00": ("morning", {}),
    "07:30": ("quiz", {"slot": 1, "round": "Morning ⛅"}),
    "14:30": ("tip", {}),
    "19:30": ("quiz", {"slot": 2, "round": "Evening 🌙"}),
    "21:00": ("leaderboard", {"when": "sunday"}),   # weekly toppers, Sunday only
    "21:30": ("digest", {}),
}

# Quiz slot minutes (2/day) — reminders derive from these automatically.
QUIZ_SLOT_TIMES = ["07:30", "19:30"]
QUIZ_SLOT_HOURS = {t.split(":")[0]: 0 for t in []}  # placeholder

# Reminders fire 10 / 5 / 1 minutes before each quiz slot.
REMINDER_BEFORE_MIN = (10, 5, 1)

# Jobs every 30 minutes (:00 / :30) — handled specially by watch loop.
JOBS_INTERVAL_MIN = 30

POLLS_PER_SLOT = 10
POLL_GAP_MIN = 2.2          # never faster than 2.2s — avoids Telegram spam flag
POLL_GAP_MAX = 3.2
FILLER_TRIGGER_UNUSED = 20  # if a channel bank has < this unused, top-up

# Telegram limits
TG_POLL_OPTION_MAX = 100    # chars per option
TG_POLL_QUESTION_MAX = 300
TG_POLL_EXPLANATION_MAX = 200
TG_MSG_MAX = 4096

# Dedup TTLs (hours)
TTL_CA = 48
TTL_JOBS = 12
TTL_GLOBAL = 6
