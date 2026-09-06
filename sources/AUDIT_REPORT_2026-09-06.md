# STUDENTUP — DEEP SOURCE AUDIT REPORT (2026-09-06)

**What changed:** all sources were re-audited with real HTTP + content checks
(no assumptions), a **central registry** was created
(`data/collector_sources.json`, 72 entries), the collector now runs off that
registry with **health auto-pausing**, and a **content-gated auditor**
(`scripts/audit_sources.py` + `core/auditor.py`) checks sources every day at
**04:45 IST** and enables/disables them safely.

---

## 1. Live & enabled (15 sources — audited one-by-one)

| Source | Type | Audit evidence (Sep 6, 2026) |
|---|---|---|
| AffairsCloud | RSS | Feed live — 32 fresh entries (Sep 1–5, 2026) |
| InsightsIndia Quiz | RSS | Feed live — daily `UPSC Current Affairs Quiz` post (Sep 5) |
| BankersAdda Quiz | Deep index | Site live — daily quiz posts (Sep 5) listed; `/feed` **redirects to homepage → crawled as index** |
| Oliveboard Quiz | RSS | Feed parses as XML (Sep 4) — quiz posts filtered strictly |
| SSCAdda Quiz | Deep index | Homepage live; `/feed` redirects → article links deep-crawled, content-gated |
| CareerPower Quiz | Deep index | Blog live (Sep 6) — memory-based papers + practice sets |
| PracticeMock Quiz | RSS | **NEW** — feed live (Sep 6, 10:01 UTC) — banking/SSC/UPSC |
| IndiaBIX Aptitude | Deep index | Live — 35+ quant topics |
| IndiaBIX Verbal Reasoning | Deep index | Live |
| IndiaBIX Logical Reasoning | Deep index | Live |
| IndiaBIX Non-Verbal Reasoning | Deep index | **NEW section verified** — 17 topics (Series, Analogy, Mirror/Water Images…) |
| IndiaBIX General Knowledge | Deep index | Live |
| IndiaBIX Data Interpretation | Deep index | **NEW section verified** — Table/Bar/Pie/Line charts |
| IndiaBIX Verbal Ability | Deep index | **NEW section verified** — 19 topics (Spotting Errors, Idioms…) |
| IndiaBIX Current Affairs | Deep index | **NEW section verified** — daily dated pages incl. Sep 1–3, 2026 |

All 8 IndiaBIX sections share the same verified markup (dedicated `indiabix`
adapter + content gate). Non-verbal figure questions are parked until Telugu
translation keys exist (numeric/aptitude stays offline-translatable).

## 2. Confirmed DEAD / unusable (audited, so never queried)

| Source | Verdict (Sep 6, 2026) |
|---|---|
| GKToday (`gktoday.in/feed/`) | **HTTP 500** — "Feed is temporarily not available" |
| Testbook (`testbook.com/blog/feed/`) | Feed parses but serves **junk** ("Test post title", COVID spam) — no quiz content |
| Guidely (`guidely.in/blog/feed`, `/feed`) | **404** Page Not Found (blog feed removed) |
| RailwayAdda (`rrbadda.com/feed`, homepage) | Host **unreachable** |
| Adda247 | 403 (docs confirm) |

## 3. Candidates (12) — auto-audited, auto-enabled only when safe

Smartkeeda, IBPSGuide, StudyIQ, PendulumEdu, Jagran Josh, Testbook main feed,
and category feeds for AffairsCloud / BankersAdda / CareerPower / Oliveboard /
PracticeMock / SSCAdda.

**Auto-enable rule (no mistakes):** a candidate is enabled only when the
auditor sees (a) fetch OK, (b) ≥1 feed entry, (c) at least one item matching
the source's own quiz title filter, and (d) newest item ≤ 14 days old.

## 4. Docs cleanup (old "100+ sources" claims vs reality)

- `sources/source_database_100plus.md` claimed scripts `test_feeds.py`,
  `feed_aggregator_advanced.py`, `filter_engine.py` — **none existed**; the
  archive file was **empty**. Now replaced by real, working tools:
  `scripts/rebuild_registry.py`, `scripts/audit_sources.py`, `core/auditor.py`.
- `sources/archive_sources_full.txt` is now **generated from the registry**
  (57 tracked rows) so it can never drift from what's actually configured.

## 5. Collection cadence (all-day + right after every quiz)

05:30 · **07:40 (right after morning quiz)** · 08:15 · 11:00 · 16:00 ·
**19:40 (right after evening quiz)** · 20:15 · 22:30 IST.
Each run is small and polite (2 s host delay, jitter, robots.txt, seen-URL
forward-paging); dead sources auto-pause after 3 bad runs.

*Source: StudentUp — audit executed 2026-09-06, Hyderabad. 72/72 tests pass.*
