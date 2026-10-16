# 🚀 Scraper v3 — More Sources + More Advanced + Easy Setup (2026-10-14)

## 📚 Sources: 436 → **517** (169 domains)

**+81 new sources**, all added as *content-gated candidates* — the daily
04:45 auditor auto-enables each one only after it proves live + fresh +
real quiz content. No guessed source ever reaches a poll directly
(that rule is now locked by tests).

| Wave part | Count | Examples |
|---|---|---|
| New MCQ domains | 14 | Sanfoundry, IncludeHelp, Studytonight, JavaTpoint, GeeksforGeeks Quiz, Hitbullseye, TutorialsPoint, ExamsDaily, AspirantsZone, DayTodayGK, DefenceXP |
| Deep sections on proven factories | 26 | Examveda (Polity/Economy/History/Geography/Science/Percentage/SI/Time-Work/Profit-Loss/Blood-Relation/Coding/Direction/Seating/Average/Trains/Synonyms/Antonyms/Idioms…), IndiaBIX (ECE, Chemical, Indian Politics/Geography/Economy, World Geography, Indian Culture — with the dedicated IndiaBIX adapter) |
| Category feeds on proven WordPress domains | 29 | BankersAdda / SSCAdda / CareerPower / Oliveboard / PracticeMock / Testbook / Guidely / IBPSGuide exam-category feeds + Telugu feeds (BankersAdda Telugu, Adda247 Telugu) |
| **Official PYQ-PDF indexes** | 12 | **UPSC, SSC, IBPS, TGPSC, TSPSC, APPSC, AP Police SLPRB, TS Police TGPRB, RRB, Indian Army / Navy / IAF Agniveer** — previous-paper PDFs are harvested into `data/pdf_inbox/` and ingested as PYQs |

Registry totals now: **517 sources · 118 live · 308 candidates waiting
audit · 91 archive/dead · 194 RSS + 323 index · 34 PDF-harvest sources**.
The same wave was also added to `scripts/rebuild_registry.py`, so
regenerating the registry no longer loses v3 sources (rebuild check: 384).

Manage sources without touching JSON:

```bash
cd scripts
python3 -m core.source_manager stats
python3 -m core.source_manager list --candidates --exam banking
python3 -m core.source_manager discover https://any-exam-site.example/
python3 -m core.source_manager add https://any-exam-site.example/feed --exam ssc --name "My Source"
python3 -m core.source_manager enable "My Source"   # / disable
```

`discover` reads the site's *own* advertised feed (`<link rel=alternate>`),
its sitemap (following sitemap-index → post-sitemaps), and counts quiz
links — then prints the exact `add` command. No more guessed `/feed` URLs.

## ⚙️ More advanced collection

- **Parallel discovery** — sources are discovered across a thread pool
  (`COLLECT_WORKERS=6`, 1 = old serial mode). Per-host politeness still
  applies inside `http_get`; question parsing/dedup stays serial, so the
  no-repeat guarantee is exact. Health writes are lock-protected.
- **Auto-sitemap probing** — an index source with no `sitemap` field and
  no listing links now probes its own host's `/sitemap.xml` automatically
  (one extra fetch, only when needed), following sitemap-index files.
- **Feed auto-discovery API** — `collector.discover_feed_urls(html, url)`
  + `collector.fetch_sitemap_links(url, link_re)` are reusable by the
  auditor, source manager and future tooling.
- Plus everything from v2 (embedded-JSON, table/dash/answer-text formats,
  RDF/Atom feeds, gzip fetch, seen-URL retry, registry defaults).

## 🪄 Easy setup — one command

```bash
bash setup.sh            # or: python3 scripts/setup.py
bash setup.sh --full     # also runs the full test suite
```

It checks Python, creates `env/.env` from the template, rebuilds the bank,
runs the validation gate + health check + a dry quiz round, prints source
stats, and ends with the exact 3 go-live steps. **Safety fix found while
building it:** template placeholders (`BOT_TOKEN=123456:ABC-YourBot...`,
`GROQ_KEY=gsk_...`) used to make the engine believe fake credentials
exist — setup now blanks placeholders automatically (real values are
never touched), and a test-suite env leak that did the same thing was
fixed too (`tests/test_sources.py`).

## ✅ Verification

| Check | Result |
|---|---|
| Full suite | **336 tests OK in ~3.4 s** (308 → +18 v2 → +10 v3) |
| Validation gate | PASSED |
| `bash setup.sh --quick` | completes; dry round posts, nothing sent |
| `source_manager stats` | 517 total / 118 live / 308 candidates / 169 domains |

## ⚠️ Honest limits

- New sources are *candidates by design*: how many of the 308 waiting
  candidates turn live depends on the first real auditor run on the
  server (this sandbox cannot reach exam sites). Expect the live count
  to climb after the first 04:45 audit + 8×/day collector cycles.
- Official-board pages change often; their `pdf_re` harvest is gated by
  the same auditor, so a redesigned board site pauses safely instead of
  scraping junk.
