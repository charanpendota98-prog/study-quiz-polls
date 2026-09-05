# 🎓 StudentUp — India's Advanced Telegram Quiz-Poll Bot for TS & AP Students

**Telangana (TS) & Andhra Pradesh (AP) aspirants కోసం** — an advanced, self-running
Telegram bot that posts **bilingual (English + Telugu) quiz polls** every day for
**TSPSC, APPSC, Banking (IBPS/SBI/RRB), Railway (RRB), Police (Constable/SI),
Defence (NDA/CDS/Agniveer), and Current Affairs GK** — plus a private
**Jobs & Exams updates** channel.

> The whole engine runs on the **Python standard library** (no pip install needed).
> Drop in optional API keys / a bot token and it posts live; without them it still
> generates, validates and dry-runs everything.

---

## ✨ What makes it "ultra advanced"

| Feature | Detail |
|---|---|
| **Native quiz polls** | `sendPoll` type `quiz` with `correct_option_id` → Telegram gives instant right/wrong feedback + an **explanation**. |
| **Fully bilingual** | Every poll shows English **and** Telugu (U+0C00–0C7F) in the question and options. Forbidden Indic scripts (Hindi/Kannada/Malayalam…) are rejected. |
| **Self-filling question bank** | An **offline procedural generator** creates an *unlimited* supply of aptitude questions whose answers are **computed in code and independently test-verified** (percentages, SI/CI, ratio, time-work, averages, series, coding, clock, calendar, direction, ranking…). AI keys add worded/reasoning/GK questions when present. |
| **Real RSS aggregation** | 12+ CA + jobs feeds (stdlib XML parser, feedparser if installed), 2-tier relevance filter, other-state hard block, blocked-topic filter. |
| **4-layer dedup** | Fingerprint + Jaccard + character-shingle similarity; CA 48h / jobs 12h / global 6h TTL stores; in-batch collapse; number-aware so "15% of 5000" ≠ "25% of 200". |
| **Zero-downtime philosophy** | **Never silent.** If feeds/LLM/network fail → curated CA, curated jobs and offline-generated quizzes keep every slot running. Atomic JSON writes survive crashes (no database needed — 1 GB RAM friendly). |
| **Leaderboard + streaks** | Non-anonymous quizzes in study groups feed per-user accuracy, daily streaks and a weekly 🥇🥈🥉 leaderboard. Interactive bot: `/quiz /stats /leaderboard`. |
| **Smart slot selection** | Each slot picks questions for **topic diversity** and **answer-key balance** (never all-A), with rotation so no question repeats until the bank cycles. |
| **Validation gate** | `finalize.py` machine-checks every question (4+4 options, valid index, Telugu policy, length caps, blocked-topic, duplicates, answer-key skew) before deploy. |
| **Telegram-safe pacing** | 2.2–3.2 s gaps between polls, ~72 msgs/channel/day, no links in public — avoids spam flags. |
| **IST scheduler** | One 24/7 process (`watch.py`) with an Asia/Kolkata clock; reminders 10/5/1 min before each slot. |

---

## 📅 Daily schedule (IST)

| Time | What |
|---|---|
| 06:00 | Auto top-up question bank if any pool runs low |
| 07:00 | Morning greeting + today's schedule (all 7 public channels) |
| 07:30 / 10:30 / 13:30 / 16:30 / 19:30 | **Quiz slots** — 10 bilingual polls per channel + 🎌 completion message |
| (−10/−5/−1 min) | Reminders (EN + Telugu) before each slot |
| 14:30 | Daily study tip (rotating, EN + Telugu) |
| 21:30 | Current Affairs digest — 6 exam-relevant items, EN + Telugu, no links |
| Every :00 / :30 | Jobs & Exams update to the **private** jobs channel (links allowed, max 5) |

---

## 🗂 Project layout

```
study-quiz-polls/
├── scripts/
│   ├── watch.py              # 24/7 IST scheduler (master service)
│   ├── bot.py                # interactive bot: /quiz /stats /leaderboard (long-poll)
│   ├── quiz_engine.py        # CLI: quiz|morning|tip|evening|jobs|reminder|leaderboard
│   ├── filler_gen.py         # auto top-up question bank
│   ├── personal_news.py      # refresh jobs feeds + post (private channel)
│   ├── finalize.py           # pre-deploy validation gate
│   ├── check.py              # health check (env, bank, bot, feeds)
│   ├── multi_api_rotator.py  # back-compat wrapper → core/llm.py
│   ├── dedup_store.py        # back-compat wrapper → core/store.py
│   ├── deploy.sh             # idempotent deploy (+ systemd)
│   └── core/                 # the engine
│       ├── config.py         # channels, schedule, policy, paths, IST clock
│       ├── telegram.py       # Bot API client (stdlib + requests), retry/backoff, DRY
│       ├── llm.py            # Groq→DeepSeek→OpenAI→Gemini key rotation
│       ├── content.py        # filters, Telugu validation, poll formatters
│       ├── question_bank.py  # markdown→JSON parser, rotation, validation
│       ├── generator.py      # offline procedural + LLM question generation
│       ├── feeds.py          # RSS aggregator + filters + dedup
│       ├── translator.py     # English→Telugu (LLM + phrasebook fallback)
│       ├── store.py          # atomic JSON stores, TTL, similarity
│       ├── leaderboard.py    # streaks + weekly rankings
│       └── engine.py         # posting brain (slots/digest/jobs/tips/reminders)
├── data/
│   ├── quiz_bank_advanced.md # human-maintained bank (parsed → JSON)
│   ├── question_bank.json    # canonical machine bank (built)
│   ├── ca_curated.json       # offline CA fallback (never silent)
│   ├── jobs_curated.json     # offline jobs fallback
│   └── study_tips.json       # 15 bilingual study tips
├── env/.env.template         # copy to env/.env and fill keys
├── deploy/*.service          # systemd units
├── tests/test_bot.py         # 21 tests incl. answer-correctness proofs
└── sources/                  # source reference notes
```

---

## 🚀 Quick start

```bash
# 1) Configure (optional for dry-run; required for live posting)
cp env/.env.template env/.env
#   edit env/.env → BOT_TOKEN, channel ids, optional LLM keys
chmod 600 env/.env

# 2) Validate everything (no deps needed)
cd scripts
python3 finalize.py            # validation gate
python3 check.py               # health check
python3 check.py --feeds       # also probe RSS reachability (needs network)

# 3) Try it in DRY mode (prints every poll/post, sends nothing)
python3 quiz_engine.py quiz --dry
python3 quiz_engine.py morning --dry
python3 quiz_engine.py evening --dry
python3 watch.py --sim 07:30 --dry     # simulate a whole slot at a given time

# 4) Go live
python3 watch.py              # 24/7 scheduler
python3 bot.py                # interactive commands + leaderboard (separate terminal/service)
```

### Useful commands

```bash
python3 quiz_engine.py quiz                       # 10 polls × 7 channels, live
python3 quiz_engine.py quiz --channel BANKING     # one channel only
python3 filler_gen.py --min 30                    # top banks up to 30 unused each
python3 -m core.generator --demo 5                # preview generated questions
python3 -m unittest -v ../tests/test_bot.py       # run the test suite
```

---

## 🧠 How the question bank never runs dry

1. **Curated** previous-paper questions live in `data/quiz_bank_advanced.md`
   (parsed into `question_bank.json`).
2. The **offline generator** (`core/generator.py`) produces verified arithmetic /
   reasoning questions on demand — 16 generator types, answers computed in code.
3. When an LLM key is present, `filler_gen` can additionally generate worded
   reasoning/GK, gated by the same strict validator.
4. `watch.py` calls the filler at 06:00 and whenever a channel has fewer than a
   slot's worth of unused questions.

The validation gate (`finalize.py`) and the test suite (`tests/test_bot.py`)
**independently recompute** the numeric answers to prove correctness.

---

## 🛡 Reliability

- **Never crashes, never silent** — every external call is wrapped; failures fall
  back to curated/offline content.
- **Atomic JSON** writes (temp → rename); TTL-pruned stores; no database.
- **Multi-key LLM rotation** with exponential backoff; all keys used, none wasted.
- **Sandbox note:** outbound HTTPS may be blocked in dev sandboxes; feeds/LLM
  fail gracefully there and work from the production server.

---

## 📈 Growth hooks (already scaffolded)

Weekly leaderboard (`/leaderboard`), daily streaks with 7-day celebrations,
`studentup.in` channel-join landing, and per-state banks — see `data/engine_config.json`.

---

*Built for TS & AP aspirants. 🇮🇳 — Source: StudentUp.*
