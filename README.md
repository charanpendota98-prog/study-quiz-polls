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
| **2 big quiz rounds daily** | ⛅ **07:30 morning** + 🌙 **19:30 evening** — 10 polls per channel per round (80/round). Add more rounds with one config line. |
| 🚫 **Questions NEVER repeat** | Every posted question is recorded permanently by a **content signature** (channel + topic + key numbers + keywords). A question — even if regenerated with a new id — is **never posted twice**. The rotation never resets; verified over 600+ questions with zero repeats. |
| 🎯 **Exam-paper sources only** | Quiz questions come **only** from exam-aligned sources (`pyq`, `curated`, `llm-gen`, `offline-gen`). **Newspapers and articles never become quiz questions** — news feeds feed the Current-Affairs *digest* only, and soft headlines (opinion/blog/sports/lifestyle/etc.) are filtered out even there. |
| **Previous-Year Questions first** | Authentic PYQ banks (`data/pyq_bank.json` + `pyq_bank_2.json` + `pyq_bank_3.json` + `pyq_bank_4_ssc.json`, TSPSC/APPSC/RRB/IBPS/SBI/Police/NDA/CDS/SSC patterns, **170 verified bilingual PYQs**) are **prioritised in every round**, then curated, then generated. |
| 🧑‍🏫 **Daily expert coach lesson** | A friendly, professional expert posts a **reasoning/aptitude shortcut with a worked example** at **12:30 IST** to every channel (`data/coach_lessons.json`, 16 lessons EN+Telugu) — plus `/coach` any time in the bot DM. |
| 🕷️ **Deep multi-source scraper** | `core/collector.py` pulls fresh exam **quiz/MCQ content from 15 verified-live sources, 8×/day including immediately after each quiz** (`07:45` & `19:45`) — AffairsCloud, InsightsIndia, PracticeMock, Oliveboard, BankersAdda, SSCAdda, CareerPower + **8 deep-crawled IndiaBIX sections** (Aptitude, Verbal/Logical/Non-Verbal Reasoning, GK, Data Interpretation, Verbal Ability, Current Affairs) via a dedicated adapter. Browser fetching, retries, **robots.txt**, polite pacing, seen-URL paging, index pagination, per-site parsers & **LLM-API Telugu translation**. Everything merges into the same validated, no-repeat bank. |
| 🗂️ **Central source registry + auto-auditor** | **187 sources in ONE registry** (`data/collector_sources.json` v4.0): 15 audited-live, 81 candidates (auto-enable), 91 archive/dead tracked. `scripts/audit_sources.py` daily (04:45) checks every source **with a content gate** (feed must be live *and* return quiz-matching items): dead sources auto-pause/disable after 3 failures, genuinely-fresh candidates auto-enable. No junk, no guesses. Regenerate the registry with `scripts/rebuild_registry.py`. |
| **Member registration** | `/register` guided sign-up (name → exam target → language), +25 bonus points. Members stored in `data/members.json`. |
| **Points, levels & ranks** | +10 per correct answer, +5 daily activity, streak bonuses (3/7/15/30/100 days), levels 🆕→🥉→🥈→🥇→💎→👑 Champion, weekly + all-time leaderboards. |
| **Native quiz polls** | `sendPoll` type `quiz` with `correct_option_id` → instant right/wrong feedback + **explanation**. Bot quizzes are non-anonymous so they earn points. |
| **Telugu-first + delayed key** | Every poll shows **Telugu above English** (TS/AP first). Default = instant ✅/❌. Set `ANSWER_MODE=delayed` for a full bilingual answer-key post at 08:00 / 20:00 IST after each round. |
| **Fully bilingual** | Every poll shows English **and** Telugu (U+0C00–0C7F). Forbidden Indic scripts (Hindi/Kannada/Malayalam…) are rejected. |
| **Self-filling question bank** | An **offline procedural generator** creates an *unlimited* supply of verified-correct aptitude questions (answers computed in code & test-proven). AI keys add worded/GK when present. |
| **Real RSS aggregation** | 12+ CA + jobs feeds (stdlib XML, feedparser if present), 2-tier relevance filter, other-state & blocked-topic filters. |
| **4-layer dedup** | Fingerprint + Jaccard + char-shingle similarity; CA 48h / jobs 12h / global 6h TTL; number-aware so "15% of 5000" ≠ "25% of 200". |
| **Never silent** | If feeds/LLM/network fail → curated CA, curated jobs, PYQ and offline quizzes keep every round live. Atomic JSON, no database. |
| **Smart round selection** | PYQ-first ordering + topic diversity + answer-key balance (never all-A) + rotation. |
| **Validation gate** | `finalize.py` machine-checks every question before deploy. 28 tests including answer-correctness proofs. |
| **Exam-hall paced rounds** | One question at a time in every channel (lockstep across channels): ⚡ easy 60 s · 🔶 medium 75 s · 🔥 hard / reasoning / aptitude 90 s; each poll shows `Q 3/10 • 🔥 Hard • ⏱ 1.5 min`; next question posts only after the timer. 10 Q ≈ 13 min. `PACED_ROUNDS=0` = old burst mode. |
| **Polls-only public channels** | `PUBLIC_POLLS_ONLY=1` (default): quiz channels carry only alerts + rounds. Greeting/tip/coach/digest/leaderboard are suppressed there. |
| **Jobs Desk (private channel only)** | `core/jobs.py` — structured job cards (Telugu + English) from FreeJobAlert latest-notifications table + RSS, Eenadu Pratibha (govt / walk-ins / private / freshers / scholarships, Telugu), SarkariResult, Sakshi jobs. Filter: TS/AP + Central/All-India + PSU/bank/rail/defence + private/IT/walk-in/outsourcing; other-state-only dropped. Each card: board, posts, vacancies, qualification, age, fee, salary, mode, last date (⏳ days left), **Apply / Notification PDF / Official / Details URLs**. URL+title dedup (7 days), closing-soon re-alert once. Every 30 min. |
| **Professional alerts** | Exactly two: **T-5** round preview (questions, subjects, pace) and **T-1** "starting now". No 10-min spam. |
| **Telegram-safe pacing** | 2.2–3.2 s gaps; no links in public; IST scheduler. |

### 🧠 Adaptive learning (100x mode)
- **Weak-topic detection** — the bot tracks each member's per-topic accuracy and
  auto-feeds practice questions on the topics they get wrong (`/quiz` adapts to them).
- **Spaced-repetition revision** — a missed question comes back the same day
  (`/review`), then at 3 days, then 7 days; answering correctly graduates it.
- **Achievement badges** — 🎯 First Answer · ✅ 10 Correct · 💯 Century ·
  🔥 3/7/30-day streaks · 🧠 Sharp Shooter (90%+) · 👑 Champion (`/badges`).
- **Admin analytics** — `/analytics` (admin only): members by exam target, state,
  district, medium, acquisition source, active-today count, aggregate accuracy.
- **Auto-ingestion webhook** — Google Forms can push submissions straight into the
  bot (no CSV): run `scripts/webhook_server.py` (stdlib, port 8080) and set
  `POST_WEBHOOK_URL` in the Apps Script. CSV import also works.

### 🏆 Points system (in the bot)
- **+25** completing `/register`
- **+10** every correct answer
- **+5** first activity each day
- **Streak bonus:** 3 days +20 · 7 days +75 · 15 days +200 · 30 days +500 · 100 days +2000 🔥
- **Levels:** 🆕 Newcomer (0) → 🥉 Bronze (100) → 🥈 Silver (300) → 🥇 Gold (700) → 💎 Platinum (1500) → 👑 Champion (3000)

> Channel auto-polls are anonymous (Telegram rule) — members earn points by playing
> `/quiz` **in the bot / study group**. Add `@DailyQuizPosterbot` to your group so
> everyone competes on the leaderboard.

### 📋 Registration — two paths (hybrid, recommended)

**Path A — in the bot (instant, for points):** users send `/register` → name →
exam target → language. They get +25 points and appear on `/leaderboard`.

**Path B — Google Form (rich data, for growth):** build the form in
[`forms/GOOGLE_FORM_BLUEPRINT.md`](forms/GOOGLE_FORM_BLUEPRINT.md) (15 min), put
its short link in `env/.env` as `FORM_URL=...`, and the bot's `/regform` command
shares it. The form captures phone, district, WhatsApp, stage etc. — data the bot
can't. Google Apps Script ([`forms/google_apps_script.gs`](forms/google_apps_script.gs))
pings Telegram on every signup. Responses export to CSV, then:

```bash
cd scripts
python3 import_members.py ~/Downloads/responses.csv          # preview
python3 import_members.py ~/Downloads/responses.csv --commit  # import
```

Username-only form sign-ups auto-link the first time that user taps `/start` in
the bot (matched by Telegram @username) — no duplicate accounts.

> ⚠️ **You do these two things** (they need your accounts): create the Google
> Form, and paste the BotFather token in `env/.env`. All code is provided.

---

## 📅 Daily schedule (IST)

| Time (IST) | What |
|---|---|
| 01:30 | **Backfill sweep** — walks every live source 5× deeper + ingests harvested PDFs until the 90-day archive is covered (`data/collector_backfill.json`) |
| 04:45 | **Deep source audit** — content-gated check of all 303 registry sources; auto-pause dead, auto-enable fresh candidates |
| 🕷️ **05:30 / 07:45 / 08:15 / 11:00 / 16:00 / 19:45 / 20:15 / 22:30** | **Deep multi-source scraping (8× daily)** — fresh quizzes from websites/apps/APIs, translated & validated; **07:45 & 19:45 run immediately after each quiz round** |
| 06:00 | Auto top-up question bank if any pool runs low |
| 07:00 | Morning greeting + today's schedule (all 7 public channels) |
| **⛅ 07:30** | **Morning quiz round** — 10 bilingual PYQ-first polls per channel |
| (−10/−5/−1 min) | Reminders (EN + Telugu) before each round |
| 🧠 **12:30** | **Daily expert coach lesson** — a reasoning/aptitude shortcut with worked example (EN + Telugu) |
| 14:30 | Daily study tip (rotating, EN + Telugu) |
| **🌙 19:30** | **Evening quiz round** — 10 bilingual PYQ-first polls per channel |
| 21:00 Sunday | Weekly member leaderboard (points + ranks) |
| 21:30 | Current Affairs digest — 6 exam-relevant items, EN + Telugu |
| Every :00 / :30 | Jobs & Exams update to the **private** jobs channel (links, max 5) |

> Want more than 2 rounds? Add a line to `SCHEDULE` in `core/config.py`,
> e.g. `"13:30": ("quiz", {"slot": 3, "round": "Afternoon ☀️"})`. Reminders update automatically.

---

## 🗂 Project layout

```
study-quiz-polls/
├── scripts/
│   ├── watch.py              # 24/7 IST scheduler (master service)
│   ├── bot.py                # interactive bot: /quiz /coach /review /badges /stats (long-poll)
│   ├── quiz_engine.py        # CLI: quiz|morning|tip|coach|collect|evening|jobs|reminder|leaderboard
│   ├── filler_gen.py         # auto top-up question bank
│   └── core/collector.py     # daily multi-website/app exam-quiz scraper (robots, polite, LLM TE)
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

## 📐 Exam-paper blueprints (every round looks like the real paper)

`data/exam_blueprints.json` + `core/blueprint.py` compose each 10-poll round the
way the actual exam sets its paper, instead of picking 10 random items:

| Channel | Subject mix per round | Hard share |
|---|---|---|
| SSC (CGL/CHSL/MTS Tier-I) | Reasoning 25 · Quant 25 · English 25 · GK 25 | ≥ 30 % |
| BANKING (IBPS/SBI prelims) | Quant 40 · Reasoning 35 · English 10 · Banking GK 15 | ≥ 35 % |
| RAILWAY (NTPC/Group-D) | GK+Science 40 · Maths 30 · Reasoning 30 | ≥ 25 % |
| TSPSC / APPSC (Group I–IV) | GS + state GK 50 · Reasoning 30 · Quant 20 | ≥ 30 % |
| POLICE (SI/Constable) | Reasoning 40 · GK 35 · Arithmetic 25 | ≥ 30 % |
| DEFENCE (NDA/CDS/Agniveer) | GK 40 · Maths 30 · Reasoning 20 · English 10 | ≥ 30 % |
| CURRENT | Current affairs 100 | — |

Every question is classified into a subject (`subject_of`: topic keywords from the
blueprint) and a difficulty (`difficulty_of`: statement-type stems, "which of the
above", multi-step arithmetic, long option sets ⇒ *hard*). The composer fills
each subject quota **PYQ-first**, balances topics inside a subject, guarantees
the minimum hard share, **interleaves subjects randomly** (so a reasoning or
aptitude item can land anywhere in the round — only for channels whose syllabus
contains it) and ramps difficulty easy → hard through the round. If a subject
runs short the shortfall is re-spread over the remaining subjects, and if the
blueprint itself is unavailable `Bank.pick` falls back to the classic picker.

---

## 🧠 How the bank never repeats and never runs dry

1. **PYQ banks** — `data/pyq_bank.json` + `data/pyq_bank_2.json` (60+ authentic
   previous-paper questions, EN+Telugu) plus curated GK from `quiz_bank_advanced.md`.
2. **The offline generator** (`core/generator.py`) produces verified
   arithmetic/reasoning questions on demand — 16 numeric generator types plus a
   fixed bank of 40 exam-aligned **static-GK** facts for the Current-Affairs
   channel; answers computed/verified in code.
3. When LLM keys are present, worded reasoning/GK is also generated, gated by the
   same strict validator.
4. `watch.py` tops up at 06:00, and `Bank.pick()` **auto-generates fresh
   questions mid-round** whenever fewer than a slot's worth of unseen questions
   remain — so a round is never short.

### 🚫 The no-repeat guarantee

- Every question has a **content signature** (`channel | topic | sorted numbers |
  sorted keywords` — answer-position-independent, so shuffling options doesn't
  make a question "new").
- When questions post, their ids **and** signatures are written permanently to
  `data/shown_signatures.json` / `data/used_questions.json`. This history
  **never resets**.
- A candidate question whose signature has been shown is rejected — even if it
  was freshly generated with a different id. The same check runs inside
  `generator.top_up()` before new questions are accepted.
- Verified in tests: 600+ picks across all channels → **zero repeats**.

### 🎯 Source policy (no news quizzes)

`ALLOWED_QUIZ_SOURCES = {pyq, curated, llm-gen, offline-gen, scraped}` — the quiz
bank loads only exam-paper-aligned sources. RSS/news feeds feed **only** the
Current-Affairs digest (and soft/opinion/entertainment headlines are dropped
there by `feeds.is_weak_content`); they never produce quiz polls.

The validation gate (`finalize.py`) and the test suite (`tests/test_bot.py`)
**independently recompute** the numeric answers to prove correctness.

---

## 🕷️ Advanced exam-content collector (daily scraping)

`core/collector.py` neatly gathers **fresh exam quiz content all day from many
websites, apps and APIs**, with **careful per-site handling so nothing breaks**,
and turns it into validated bilingual questions:

- **Deep source registry (303 sources: 84 live, 128 auto-enable candidates,
  91 archived)** — three families:
  - `type: index` **deep MCQ banks** — **GKToday quizbase** (Polity, Ancient/
    Medieval/Modern History, Geography, Economy, Physics/Chemistry/Biology,
    Environment, Art & Culture, **Telangana GK**, **APPSC GK**, topic-wise CA
    for Schemes/Banking/Defence/SciTech/Reports/Awards/Days and **native Telugu
    Current Affairs**), **Examveda** (40+ reasoning topics, 35+ arithmetic
    topics, non-verbal, English, GK, DI — 83 Q per topic, worked solutions),
    **Testmocks** (quant/logical/verbal reasoning/English, 20 Q with
    explanations per topic via `link_suffix: start/`) and IndiaBIX.
    Paginated sections (`?pageno=N`, `?page=N`) are followed on the section
    page **and** on every discovered topic page.
  - Mock-test apps you asked for — **mockers.in, futurekul, testranking,
    testmocks exam papers, sscgov-style portals** — are registered as
    *candidates*: the daily auditor's **content gate** (must yield quiz links
    or ≥1 parseable MCQ) auto-enables them the moment their pages serve
    server-rendered questions, and auto-disables anything that dies.
  - Also two kinds of feeds:
  - `type: rss` — AffairsCloud, GKToday, Insights on India, Testbook, BankersAdda,
    Guidely, Oliveboard (banking); SSCAdda, CareerPower (SSC/UPSC); RailwayAdda
    (RRB). Feeds are scanned for *quiz* pages (title `must`/`not` regexes skip
    notifications, results, editorials, recruitment posts).
  - `type: index` — **deep HTML crawl** of big static MCQ banks: IndiaBIX
    Aptitude, Verbal Reasoning, Logical Reasoning, Non-Verbal Reasoning and
    General Knowledge. The section page is parsed directly AND its per-topic
    links are discovered (`link_re`) and crawled one level deep.
  Add or tune any source without code via `data/collector_sources.json`.
- **Per-site adapters** — the WordPress quiz parser handles most blogs; sites
  with non-standard markup get a **dedicated adapter** (`ADAPTERS` registry,
  e.g. `indiabix` reads `bix-div-container` / `bix-td-qtxt` / option cells /
  `Answer: Option X` / Explanation blocks), so each source is parsed correctly.
- **Advanced, polite fetching** — browser `User-Agent`, retries with exponential
  backoff, per-host delay + jitter, **`robots.txt` enforcement** (robotparser),
  optional proxy, `feedparser` if installed.
- **Tolerant generic parser** — article-aware text extraction, then a
  state-machine reads `Q.. A) B) C) D) Correct Answer: B / Explanation:` blocks
  (separate lines **or** inline).
- **All-day collection** — scheduled at **05:30, 08:15, 11:00, 16:00, 20:15 and
  22:30 IST** (including right after both quiz rounds). A **seen-URL store**
  (`collector_seen.json`) makes successive small runs page forward to NEW
  content instead of refetching.
- **Bilingual** — worded questions/options are translated by the multi-key LLM
  rotator (Groq→DeepSeek→OpenAI→Gemini). Numeric/aptitude stems get an **offline
  Telugu template** so quant works with no key. Worded items that can't be
  translated yet **park in `scraped_pending.json`** and auto-retry when a key
  exists.
- **No-repeat + validation** — a stable SHA1 fingerprint (normalized
  question+options) blocks re-scraped duplicates; the content-signature gate
  blocks dupes against the whole bank/history. Every question passes
  `validate_question`; saved to `data/scraped_bank.json` (`source: scraped`) and
  merged into the canonical bank.

- **PDF / previous-paper ingestion** — drop any PYQ or model-paper PDF (or
  `.txt`) into **`data/pdf_inbox/`** and run `--inbox`; text is extracted via
  `pdftotext` → `pypdf` → `PyPDF2` (whichever is installed), glued options like
  `(a) 2 (b) 3 (c) 6 (d) 9` are split, `Ans: (c)` / `Answer: b` keys are read,
  and the file name becomes the provenance (`bank: pdf`, tagged as PYQ).
- **Telugu-native sources** — pages whose stems are already Telugu (GKToday
  Telugu CA) are accepted as-is with `q_te == q_en`, no LLM needed.
- **TS/AP native sources (Telugu, verified 07 Sep 2026)** — **Sakshi Education**
  (`/current-affairs/practice-test` daily CA quiz, `/groups/tspsc-bitbank` +
  `/groups/practice-test` APPSC/TSPSC subject bit banks, `/ts-police/bitbank/*`
  TS Police history/geography/polity/science/economy — numeric `1) .. 4)` options
  and `సమాధానం: 2` keys are normalised automatically), **MCQBits** (TSPSC/APPSC/
  TSLPRB previous-year papers, RRB NTPC, SBI, quant, reasoning, TET-DSC) and
  **Eenadu Pratibha** previous-paper/model-paper PDFs (auto-harvested via
  `pdf_re` into `data/pdf_inbox/`, ≤25 MB, `%PDF` checked, then ingested).
  Telugu labels `ఎ) బి) సి) డి)` and `జవాబు:/సమాధానం:` keys parse natively;
  a single-exam source tag (`exam: police|tspsc|appsc|…`) pins its questions to
  that channel, so questions land on the right exam's channel.
- **More verified sources (07 Sep 2026)** — **Sakshi Daily Current Affairs
- **Round-3 sources (07 Sep 2026):** GKSeries chapter-wise Polity/History/Geography/Economy/Sports (bare-label folding), AffairsCloud reasoning/quant/static-GK topic sets (5-option banking format), plus Eenadu Pratibha Telugu quiz hubs, PendulumEdu, Examrace, Smartkeeda as gated candidates. `scripts/gen_sources_md.py` regenerates `sources/SOURCES.md`.
  quiz** (30 Telugu MCQs/day), **FreshersNow** (Telangana GK, Andhra Pradesh GK,
  60+ reasoning topic quizzes, 40+ aptitude topic quizzes, GK topic quizzes —
  25 Q each with explanation), **Examsbook** reasoning articles (`Q :` label
  format, `/2../4` pagination), **Target Defence Academy** 100-Q current-affairs
  sets. Candidates queued for the auditor: CompetitiveExamsIndia,
  SSC Study, LSR Updates (Telugu TS history), SRM Tutors, QuizDunia, ReadingRoomz
  (APPSC bilingual CA), Careerride, AP Police Exams, QuestionPapersOnline
  (AP Police PYQ PDFs via `pdf_re`).
- **Bilingual policy** — Telugu pages are kept as-is; English/Hindi pages go
  through `translate_mcq` (exam-paper-style Telugu, stem + all options +
  explanation in one strict-JSON call, per-string fallback) and are posted with
  **Telugu + English together**; other-script pages are skipped.
- **Backfill (3-month+ archive sweep)** — `--backfill` runs the collector with
  `--depth 5` (5× more index pages/links per source), harvests PDFs and ingests
  the inbox; state lives in `data/collector_backfill.json` and the 01:30 slot
  keeps sweeping nightly until three consecutive idle runs mark it `done`.

```bash
python3 -m core.collector --collect          # live run (writes scraped_bank.json)
python3 -m core.collector --pdf paper.pdf    # ingest one previous-paper PDF/TXT
python3 -m core.collector --inbox            # ingest every file in data/pdf_inbox/
python3 -m core.collector --collect --dry    # fetch + parse, don't save
python3 -m core.collector --retry-pending    # translate parked questions
python3 -m core.collector --backfill --depth 5          # 90-day archive sweep (resumable)
python3 -m core.collector --collect --only sakshi --dry # one source family, no writes
python3 -m core.collector --fixture page.html --title "IBPS Quiz"  # offline parse
python3 audit_sources.py                     # deep audit ALL 303 registry sources
python3 audit_sources.py --only-enabled      # audit only live sources (fast)
python3 rebuild_registry.py --check          # validate the central registry
python3 check.py --sources                   # registry + health summary
```
> In dev sandboxes outbound HTTPS may be blocked — the collector fails silently
> there (never crashes) and runs from the production server. Verified offline via
> a bundled fixture (`tests/fixture_quiz.html`).

---

## 🛡 Reliability

- **Never crashes, never silent** — every external call is wrapped; failures fall
  back to curated/offline content.
- **Atomic JSON** writes (temp → rename); TTL-pruned stores; no database.
- **Multi-key LLM rotation** — Groq → DeepSeek → OpenAI → **Gemini (unlimited keys)** → Dify, precise failover + exponential backoff; all keys used, none wasted. Web layer: **Jina Reader auto-fallback** (`JINA_API_KEY`) for sites that block scrapers + **Serper.dev search** utility (`core/search.py`) for deep discovery.
- **Sandbox note:** outbound HTTPS may be blocked in dev sandboxes; feeds/LLM
  fail gracefully there and work from the production server.

---

## 📈 Growth hooks (already scaffolded)

Weekly leaderboard (`/leaderboard`), daily streaks with 7-day celebrations,
`studentup.in` channel-join landing, and per-state banks — see `data/engine_config.json`.

---

*Built for TS & AP aspirants. 🇮🇳 — Source: StudentUp.*
