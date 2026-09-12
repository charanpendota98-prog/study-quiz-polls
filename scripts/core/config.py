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

# Google Form for rich registration (phone/district/WhatsApp). Put your form URL
# in env/.env as FORM_URL=... In-bot /register handles points; this handles
# growth + detailed analytics. See forms/GOOGLE_FORM_BLUEPRINT.md.
# Member CRM → Google Sheet (Apps Script web app, see docs/sheet_webapp.gs)
SHEET_WEBAPP_URL = env("SHEET_WEBAPP_URL", "")
# The owner's Sheet (view link). Data is written via the Apps Script web app
# deployed FROM this sheet (SHEET_WEBAPP_URL) — Google does not allow direct
# writes from a bot without OAuth, the web app is the zero-key bridge.
SHEET_ID = env("SHEET_ID", "1XXeHg9rym05O_4a0-5vjbUxHTNW57MAok8H7uod3C0A")
SHEET_URL_VIEW = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
SHEET_SECRET = env("SHEET_SECRET", "")
FORM_URL = env("FORM_URL", "https://forms.gle/your-studentup-registration")

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
    "SSC": {
        "name": "SSC",
        "emoji": "🏛️",
        "subject": "SSC Exams (CGL/CHSL/MTS/GD)",
        "public": True,
        "title": "StudentUp SSC Exams Quiz (TS & AP)",
        "username": "StudentUpSSC",
        "audience": "SSC CGL | CHSL | MTS | GD | CPO aspirants",
        "topics": ["Reasoning", "Quantitative Aptitude", "English Comprehension",
                   "General Knowledge", "General Science", "History & Polity",
                   "Geography & Economy"],
        "ts_ap_weight": 0.20,
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

for _k, _v in CHANNELS.items():
    _v.setdefault("key", _k)
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
PDF_INBOX_CAP_MB = 400   # hard disk cap for downloaded papers (oldest ingested deleted first)

SCHEDULE = {
    # Deep multi-source exam-quiz scraping — runs all day AND twice
    # immediately after each quiz round (07:45 / 19:45), so fresh exam
    # content is collected right after every round. Small polite batches +
    # seen-URL tracking mean each run pages forward to NEW content.
    # Failing sources auto-pause via collector_health.json; the 04:45 auditor
    # re-verifies all sources (content-gated) and auto-pauses/enables them.
    "01:30": ("backfill", {}),     # deep archive sweep (3-month campaign; idle when done)
    "01:00": ("scout", {}),        # continuous source discovery → ready queue (time-boxed, capped)
    "02:15": ("pyq", {}),          # official previous-paper PDFs → provenance-stamped questions
    "04:45": ("audit", {}),        # daily deep source audit (content-gated)
    "03:00": ("verify", {}),       # API-key answer + Telugu audit of new questions
    "05:30": ("collect", {"reason": "pre-dawn scrape"}),
    "05:45": ("telegram", {}),     # public Telegram exam channels (2nd independent content path)
    "17:15": ("telegram", {}),
    "06:15": ("supply", {}),       # supply guard: escalates fallbacks when runway < 3 days
    "18:15": ("supply", {}),
    "06:30": ("verify", {"limit": 60}),
    "18:30": ("verify", {"limit": 60}),
    "06:00": ("filler", {"reason": "morning top-up"}),
    "07:00": ("morning", {}),
    "07:30": ("quiz", {"slot": 1, "round": "Morning ⛅"}),
    "08:00": ("answer_key", {"round": "Morning ⛅"}),  # delayed key (no-op if instant)
    "07:45": ("collect", {"reason": "post-morning-quiz"}),   # after the ~13-min paced round
    "08:15": ("collect", {"reason": "post-morning deep scrape"}),
    "11:00": ("collect", {"reason": "late-morning scrape"}),
    "12:30": ("coach", {}),        # daily expert reasoning/aptitude trick
    "14:30": ("tip", {}),
    "16:00": ("collect", {"reason": "pre-evening top-up scrape"}),
    "19:30": ("quiz", {"slot": 2, "round": "Evening 🌙"}),
    "20:00": ("answer_key", {"round": "Evening 🌙"}),  # delayed key (no-op if instant)
    "19:45": ("collect", {"reason": "post-evening-quiz"}),   # after the ~13-min paced round
    "20:15": ("collect", {"reason": "post-evening deep scrape"}),
    "21:00": ("leaderboard", {"when": "sunday"}),   # weekly toppers, Sunday only
    "21:30": ("digest", {}),
    "22:30": ("collect", {"reason": "late-evening deep scrape"}),
}

# Quiz slot minutes (2/day) — reminders derive from these automatically.
QUIZ_SLOT_TIMES = ["07:30", "19:30"]
QUIZ_SLOT_HOURS = {t.split(":")[0]: 0 for t in []}  # placeholder

# Reminders: exactly TWO professional alerts — 5 min before (round preview)
# and 1 min before ("starting now"). No 10-min spam.
REMINDER_BEFORE_MIN = (5, 1)

# Jobs every 30 minutes (:00 / :30) — handled specially by watch loop.
JOBS_INTERVAL_MIN = 30

POLLS_PER_SLOT = 10
# Sunday Grand Test — weekly real-exam mock (revision of the week's toughest
# questions + fresh ones, sections easy→hard, negative marking, double points).
GRAND_TEST_TIME = env("GRAND_TEST_TIME", "09:00")
GRAND_TEST_QUESTIONS = int(env("GRAND_TEST_QUESTIONS", "25") or 25)
GRAND_TEST_TEASER_TIME = env("GRAND_TEST_TEASER_TIME", "18:00")   # Saturday
MEGA_TEST_QUESTIONS = int(env("MEGA_TEST_QUESTIONS", "50") or 50)  # last Sunday of month
RANK_CARDS = env("RANK_CARDS", "1").lower() not in ("0", "false", "no", "off")  # PNG cards (needs Pillow)
BRAND_NAME = env("BRAND_NAME", "StudentUp")
BRAND_HANDLE = env("BRAND_HANDLE", "t.me/StudentUpQuiz")   # printed on rank cards
CHALLENGE_TIME = env("CHALLENGE_TIME", "13:00")                    # Mon–Sat Beat-the-Topper DM
REWARDS_PROMO_TIME = env("REWARDS_PROMO_TIME", "12:00")            # Tue & Fri hub promo
VOUCHER_DAYS = int(env("VOUCHER_DAYS", "30") or 30)
POINT_VALUE_PAISE = int(env("POINT_VALUE_PAISE", "10") or 10)       # 100 pts ≈ ₹10 (display only)
STAFF_IDS = [x.strip() for x in env("STAFF_IDS", "").split(",") if x.strip()]  # can /verify vouchers
WAR_TIME = env("WAR_TIME", "21:00")                                # daily District War (DM, all members)
WAR_QUESTIONS = int(env("WAR_QUESTIONS", "10") or 10)
LEAGUE_POST_TIME = env("LEAGUE_POST_TIME", "08:00")                # Monday district league standings
POLL_GAP_MIN = 2.2          # never faster than 2.2s — avoids Telegram spam flag
POLL_GAP_MAX = 3.2
FILLER_TRIGGER_UNUSED = 20  # if a channel bank has < this unused, top-up

# Poll presentation
# TELUGU_FIRST=1 (default) → Telugu line above English in every poll (TS/AP first).
# ANSWER_MODE=instant (default) → Telegram quiz poll with correct_option_id
#   (instant ✅/❌ feedback + explanation).
# ANSWER_MODE=delayed → regular quiz still uses correct_option_id for scoring,
#   but explanation is withheld; a full bilingual answer-key is posted after
#   the round (advanced delayed answer key).
TELUGU_FIRST = env("TELUGU_FIRST", "1").lower() not in ("0", "false", "no", "off")
ANSWER_MODE = (env("ANSWER_MODE", "instant") or "instant").strip().lower()
if ANSWER_MODE not in ("instant", "delayed"):
    ANSWER_MODE = "instant"
QUIZ_OPEN_PERIOD = int(env("QUIZ_OPEN_PERIOD", "300") or "300")  # legacy default (unpaced)
# REVEAL POLICY — the correct option must NEVER show before a person answers.
# A Telegram quiz poll with open_period auto-CLOSES when the timer ends and a
# closed quiz reveals ✅ to everyone (even non-voters). So polls are posted
# WITHOUT open_period: the pace timer only decides when the NEXT poll goes out;
# each poll stays open and reveals ✅/❌ privately, only after that person votes.
POLL_AUTO_CLOSE = env("POLL_AUTO_CLOSE", "0").lower() in ("1", "true", "yes", "on")
# Balance the correct option across A/B/C/D (deterministic per question+day)
BALANCE_OPTIONS = env("BALANCE_OPTIONS", "1").lower() not in ("0", "false", "no", "off")

# ---------------------------------------------------------------------------
# PACED ROUNDS (exam-hall timing) — one question at a time, not a dump.
# Every question is posted alone, stays open for a difficulty-based timer
# and the next one is posted only after the timer ends:
#   easy 60 s · medium 75 s · hard 90 s   (reasoning/quant hard = 90 s)
# 10 questions ≈ 12–13 min per round, exactly like a sectional mock.
# PACED_ROUNDS=0 restores the old burst mode.
# ---------------------------------------------------------------------------
PACED_ROUNDS = env("PACED_ROUNDS", "1").lower() not in ("0", "false", "no", "off")

# PUBLIC_POLLS_ONLY=1 (default): the public quiz channels carry ONLY the quiz
# rounds (T-5/T-1 alert, opener, polls, closer, answer key). Morning greeting,
# study tip, coach lesson, CA digest and leaderboard are suppressed there
# (they still work in the bot group / on demand). Jobs never go public.
# REQUIRE_REGISTRATION=1: /quiz in the bot works only after the 5-step form
# (name, state, district, exam, language) — profile saved in data/members.json.
REQUIRE_REGISTRATION = env("REQUIRE_REGISTRATION", "1").lower() not in ("0", "false", "no", "off")
# Where the daily champions / district cup posts go (people-content, not polls).
# Default: CURRENT hub only, so exam channels stay 100% polls.
CHAMPION_CHANNELS = [c.strip().upper() for c in env("CHAMPION_CHANNELS", "CURRENT").split(",") if c.strip()]
BOT_USERNAME = env("BOT_USERNAME", "")
PUBLIC_POLLS_ONLY = env("PUBLIC_POLLS_ONLY", "1").lower() not in ("0", "false", "no", "off")
QUIZ_PACE_SEC = {
    "easy": int(env("PACE_EASY_SEC", "60") or 60),
    "medium": int(env("PACE_MEDIUM_SEC", "75") or 75),
    "hard": int(env("PACE_HARD_SEC", "90") or 90),
}
PACE_BUFFER_SEC = 4          # breathing gap after a poll closes before the next

# Telegram limits
TG_POLL_OPTION_MAX = 100    # chars per option
TG_POLL_QUESTION_MAX = 300
TG_POLL_EXPLANATION_MAX = 200
TG_MSG_MAX = 4096

# Dedup TTLs (hours)
TTL_CA = 48
TTL_JOBS = 12
TTL_GLOBAL = 6


# Question verification gate (core/verifier.py):
#   True  -> scraped/generated questions post ONLY after the API-key audit
#   False -> lenient (post once structurally valid)
#   "auto"-> strict whenever at least one LLM key is configured
VERIFY_STRICT = os.environ.get("VERIFY_STRICT", "auto")
if VERIFY_STRICT.lower() in ("1", "true", "yes"):
    VERIFY_STRICT = True
elif VERIFY_STRICT.lower() in ("0", "false", "no"):
    VERIFY_STRICT = False
