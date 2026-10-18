# 🕷️ Scraper v2 — Perfect-Scrape Upgrade (2026-10-14)

**Question asked:** *Quiz polls correct-ga post avuthaya? Chala sources nunchi
advanced-ga, perfectly scrape chesthunda?*

**Answer after this upgrade:** Polls — **yes, verified** (dry-run + a new
bank-wide guarantee test). Scraping — **yes, v2**: 7 real extraction bugs that
silently lost questions on modern sites are fixed, with tests locking each one.

## ✅ Poll posting — verified correct

| Check | Result |
|---|---|
| Full test suite | **326 tests, all pass** (308 old + 18 new) |
| Validation gate (`finalize.py`) | **PASSED — 246 questions, 0 errors** |
| Dry quiz round (`quiz_engine.py quiz --dry`) | **77 polls across 8 channels**, lockstep paced, PYQ-first |
| New guarantee test | Every public-channel bank question builds a Telegram-legal poll (question ≤300 chars, 4 options ≤100 chars) and, **after send-time option balancing, `correct_option_id` still points at the truly-correct option** — for 200+ questions |

Note: 2–3 questions per round are skipped by the *answer-leak guard*
(option text inside the stem / tick markers). That is by design — those polls
would have exposed their own answer.

## 🐛 Scraping bugs fixed (each was silently losing questions)

1. **Embedded-JSON pages scraped ZERO.** Testbook/Oliveboard/Adda-style apps
   and JSON-LD `Quiz` markup ship questions inside `<script>` JSON
   (`__NEXT_DATA__`, `window.__Q__ = {...}`), which the text parser drops.
   → New `extract_embedded_questions()` walks JSON-LD / Next.js / inline JSON:
   question/options keys in all common spellings, answers as 0-based index,
   1-based number, letter, option text, or `acceptedAnswer`.
2. **Table-layout quizzes glued options together** (`A) WarangalB) Hyderabad`)
   because `<td>/<th>` weren't text blocks. → Fixed.
3. **"Answer: Hyderabad"** (key as option *text*, no letter) — dropped.
   → Resolved against the option list.
4. **"A - Warangal" dash options** — dropped. → Accepted (`-`, `–`, `—`).
5. **Unnumbered questions** (stem + A–D, no `1.`) — dropped. → Numbered
   automatically, *without* splitting multi-part stems (numbered
   sub-statements + "Which of the pairs…?" stay one question).
6. **Small answer-key tables (2–4 Q papers)** — the key table needed ≥5 pairs,
   so daily bit-bank papers lost everything. → ≥2 pairs under an explicit
   `Answers:`/`Answer Key` header are now trusted.
7. **Feeds:** Atom entries fetched the *feed itself* (`rel=self` beat
   `rel=alternate`), RSS 1.0/RDF feeds parsed to zero, `&nbsp;`-style entities
   killed whole feeds, and entries weren't fresh-first (the per-source limit
   was spent on old posts). → Namespace-agnostic RDF/Atom/RSS-2 parsing,
   alternate-link wins, entity repair, **freshest-first**.

## 🚀 Fetch & discovery upgrades

- **gzip/deflate** decoding + `<meta charset>` sniffing (headers are now read
  inside the response context — previously read after close).
- **429/503** honoured via `Retry-After` (capped); 5xx retried.
- **Registry defaults actually work now:** `polite_delay_sec`,
  `fetch_timeout`, `max_articles/links/pages_per_index`,
  `auto_pause_after_failures` in `data/collector_sources.json` were read by
  *nobody* before — the collector now honours them live.
- **Seen-URL bug:** a URL was marked "seen" *before* fetching, so one failed
  fetch lost that article **forever**. Now a URL is marked only after a
  successful fetch — failures retry next run (tested).
- **Sitemap discovery:** add `"sitemap": "https://…/sitemap.xml"` to any index
  source and fresh quiz URLs are discovered from it before listing pages
  surface them.
- **Auditor:** ISO-8601/Atom dates now parse (freshness gate for
  auto-enabling candidates works for Atom sources too).

## 🧪 Tests

`tests/test_scraper_v2.py` (18 tests): JSON-LD, `__NEXT_DATA__`, window-data,
embedded+text dedup, table layout, dash options, answer-as-text, unnumbered
stems, sub-statement safety, small key tables, RDF/Atom/entity feeds,
sitemap, gzip fetch, registry defaults, seen-URL retry, and the bank-wide
poll-posting guarantee.

```bash
cd scripts && python3 -m unittest discover -s ../tests   # 326 tests, OK
python3 finalize.py                                       # gate PASSED
python3 quiz_engine.py quiz --dry                         # 77 polls, 8 channels
```

## ⚠️ Honest limits

- This sandbox has no live internet to exam sites, so v2 is proven on
  fixtures + unit tests, not a live crawl. On the server, the next
  `collect` runs (05:30 / 07:45 / … IST) exercise it against real pages;
  watch `data/collector_health.json` + `[collect]` stats
  (`parsed` should rise on JSON-app sources).
- Bank stock is still thin (246 Qs ≈ 1–2 days of rounds per channel).
  v2 raises the *yield per source*, but live yield depends on LLM keys for
  Telugu translation of worded questions (untranslated ones stay parked in
  `scraped_pending.json`, never lost).
