# 🏛️ ARCHITECTURE AUDIT — 240X (Chief-Architect Review)

Scope: 95 Python modules · ~49,700 LOC · 199 API routes · 103 test
files (780 tests) · data layer = JSON stores · surfaces = Dashboard,
Student Portal SPA, Telegram bot, WhatsApp pipeline, WordPress bridge.
Method: pyflakes (0 undefined names), route-vs-auth positional audit,
pattern sweeps (secrets, shells, bare excepts), loop/AST complexity
scan, live probes. Severity: **CRITICAL / HIGH / MEDIUM / LOW**.

## Findings register

| # | Severity | Finding | Status |
|---|---|---|---|
| F1 | **CRITICAL** | `/api/admin/harvest_run` sat *before* the deny-by-default auth gate with no check — anyone reaching the server could trigger a (production) PYQ harvest | ✅ FIXED 240X (explicit `_authed()` 401) |
| F2 | MEDIUM | Dashboard password compared with `==` (timing side-channel) | ✅ FIXED 240X (`hmac.compare_digest`) |
| F3 | MEDIUM | POST body read unbounded (`rfile.read(Content-Length)`) — trivial memory DoS | ✅ FIXED 240X (5 MB cap → 413, safe parse) |
| F4 | MEDIUM | Zero security headers on any response (MIME-sniff, clickjacking, referrer) | ✅ FIXED 240X (`_sec_headers()` in all 3 central senders) |
| F5 | LOW | Auth cookie lacks `Secure` (HTTPS deployments) | ✅ FIXED 240X (set when https proto) |
| F6 | HIGH | Default dashboard password `studentup123` with no operator warning | ✅ FIXED 240X (go-live check warns; set `DASHBOARD_PASSWORD`) |
| F7 | LOW | `Access-Control-Allow-Origin: *` on JSON API | Accepted — token-in-query API, no credentialed CORS; scope if cookies ever go cross-site |
| F8 | MEDIUM | God-handlers: bot `handle_message` 1,513 lines, `_do_POST` 1,167, `_do_GET` 988 | Roadmap — split into route-table modules behind the existing suites (never blind-refactor) |
| F9 | LOW | 272 `innerHTML` sinks in SPA | Mitigated by `esc()` discipline on user fields (names/districts/topics); keep the rule in review |
| F10 | MEDIUM | JSON full-file writes under write storms | Mitigated (debounce 2s, atomic rename, stamp cache); SQLite-WAL migration path documented below |

## 1. ARCHITECTURE

Modular monolith: `scripts/core/*` domain modules (portal, brain,
syllabus, pyq, members, rewards…) behind three hosts (dashboard HTTP,
bot long-poll, WA scheduler). Strengths: single-command deploy,
deny-by-default route gate, flag-gated features, honest-count rules
baked into domain code. Weaknesses = F8/F10. Target evolution: keep
the monolith (right-sized for ≤50k students), split the three god
handlers into route modules first; extract services only when a
second process truly needs them.

## 2. CODE REVIEW

pyflakes: **0 undefined names**; 0 bare `except:`; 0 `eval/exec/
os.system/shell=True`; 0 mutable default args; 0 hardcoded secrets.
220X unified explanations through `portal._why()` (14 dead sites).
Bot dispatch is poison-proof (220X armor). Residual smells: long
functions (F8), cosmetic f-string placeholders (pyflakes nits),
CORS breadth (F7). Edge cases pinned by tests: stale-day queues,
claim-once outbox, anti-farm once/day/question.

## 3. PERFORMANCE

Bank loads via mtime/size **signature cache**; portal store is
in-memory with RLock + flush saves; KV uses stamp-based parse cache
+ atomic writes + 2s debounced saves (10k-answer storms don't write
per answer); gzip + ETag/304 on pages; SW cache v5; HTTP request
queue 256; harvest self-caps at 20 min with per-source backoff.
Watch items: `syllabus_plan` is the loop-heaviest portal function
(cache its exam graphs per bank-signature), `Members()` per request
is amortized by the KV parse cache.

## 4. SECURITY (OWASP)

AuthN: server-side session tokens (cap 25), HttpOnly + SameSite=Lax
(+ Secure on HTTPS after F5), 1.2s login delay + attempt logging +
IP allowlist + per-key rate limiter. AuthZ: deny-by-default gate
after public routes (portal token APIs, exam join, public pages);
every admin route now explicitly or positionally gated (F1).
Input: body cap (F3), file downloads traversal-proof (230X),
HMAC single-use portal links (110X), anti-farm (100X). Headers:
baseline shipped (F4); HSTS = enable once behind permanent HTTPS.
Data: no secrets in repo (env only), secrets never leave
`_golive_checks` (booleans only). XSS: `esc()` discipline (F9).
CSP deferred deliberately — the SPA is inline-script heavy; adopt
with nonces during the F8 split.

## 5. DATABASE

"Tables" = JSON documents: `members.json` (KV), `portal.json`
(store), `brain.json`, bank JSONs, ledgers. Integrity: atomic
write-rename everywhere, `.bak` snapshots + backup module,
`finalize.py` validation gate (1,450+ questions, 0 errors).
No normalization/indexing concerns at this scale; the query layer
is in-memory scans over capped collections (boards ≤300, archive
trimmed). Migration path when writes measurably contend:
SQLite (stdlib, WAL mode) for members+portal behind the same KV
interface — no Postgres until multi-process writes are real.

## 6. DEVOPS

One-command `deploy.sh` (VPS), env-driven config, `/api/health/
golive` readiness checks, bot `/health` (220X), admin-notify on
errors, service-worker versioned rollouts (v5). Gaps → roadmap:
GitHub Actions running the 780-test suite per PR; log rotation;
uptime ping into `admin_notify`; HSTS + CSP during F8.

## 7. AI & AUTOMATION

Already agentic: Brain θ ability (400–2000) drives adaptive mocks;
forecast v2 shrinks by subject mastery; harvest targeting ranks
real PYQ gaps (never fabricates); revision planner composes SRS +
weak sections; retention win-back (170X) + winners blasts (180X)
run on claim-once queues. Next: LLM explanation enrichment for
gap subjects (`llm.py` rotating keys exists), auto-generated
materials from weakest topics into the 230X Vault, churn-risk
scoring from the existing 7-day at-risk cohort.

## 8. TESTING

780 deterministic tests, fully temp-isolated (no network, no real
sends, no real harvest), wiring pins for every round (50X–240X),
`finalize.py` as a merge gate. Known gap: the dashboard HTTP layer
is covered via AST-exec (160X pattern) + live smokes because
importing it at collection breaks an order-dependent legacy test —
convert to a fixture-based app factory during F8. WhatsApp timing
rules (60–80s gaps, one-broadcast lock, pacing floor 1.0×) are
pinned dry; production sends stay owner-triggered.

---
*Audit rule going forward: every CRITICAL/HIGH ships with a
regression pin in the same commit; the route-vs-auth positional
audit re-runs whenever a route is added before the gate.*

---

## ADDENDUM — 280X (perfection sweep, same branch)

**F7 CLOSED (CORS).** The dashboard no longer emits
`Access-Control-Allow-Origin: *`. `_cors_origin()` echoes only the
configured PUBLIC_BASE_URL/PORTAL_BASE_URL origin or a localhost dev
origin; `do_OPTIONS` answers preflight (204) only for allowlisted
origins, 403 otherwise. Pins: `TestCors280` (AST-exec, 160X pattern).

**F11 NEW → CLOSED (answer-position bias).** Raw bank measurement
(305 Q tracked bank): position B held 43% of keys; several live
surfaces sent raw bank order, leaking that skew to students. Fix is
serve-time, everywhere: `content.poll_safe` now wraps engine channel
polls + DM mirrors + reaction text-polls, bot DM/`/quiz` + Beat-the-
Topper challenge, autopilot coach, arena rooms (frozen into room
state at start), district wars (frozen into live state), and
WhatsApp delivery (one balanced copy feeds emoji text-poll, native
poll, tracked `correct` index and the phase-2 key — all four agree).
Campus already permuted per-user (untouched, verified). Measurement
lives in `core/bankhealth.py` (+ `scripts/bank_health.py` CLI,
dashboard golive "Bank health (280X)" check): per-group bias flags,
duplicate stems/options, invalid questions, honest PYQ share.
Three legacy tests migrated to the displayed-position contract
(arena, reaction groups, WA winners) — scoring was re-proven
against displayed options, never weakened. Suite: 842 OK.

---

## ADDENDUM — 290X (stored-XSS root fix)

**Decision (over per-sink patching):** with 265 `innerHTML`
sinks, escaping site-by-site is unverifiable. 290X fixes the
class at the root: (1) display text is cleaned ONCE at write
time, (2) every dashboard `esc()` is quote-safe, (3) the few
highest-risk raw sinks got explicit `esc()`. Portal exam options
already render via `textContent` (safe by design); question
stems are bank-controlled (collector + finalize validated) and
now escaped in admin previews.

**`core/textsafe.clean_display_name`** — strips HTML-significant
characters (`< > & " ' \` / \\`), control and zero-width/format
characters; collapses whitespace; caps length. Telugu/Unicode
names, dots and hyphens pass through untouched. Wired at EVERY
name entry point: `members.register` + `auto_register_from_poll`
(Telegram profile names — attacker-controlled), portal
`register_student`, stateless `register_student` (cleaned before
the profile is signed), campus web-exam register, campus
`new_event` (event + college names), campus `student_request`.

**`esc()` upgrade (x3, all dashboard pages)** — now escapes
`& < > " '` (previously only `& <`), closing attribute-breakout
in `onclick='...esc(x)...'` handlers. Explicit `esc()` added at:
bank search preview (stem/channel/topic), WA planner group rows
(name), bulk-target picker (name/category), admin member table
(name/weak-topic/district/exam).

**Residual (accepted, tracked):** remaining flagged sinks render
*numeric* fields (counts, percentages, timings — server-computed)
or now-cleaned stored names; bot messages render via Telegram
(no HTML injection surface for stored names, and names are
cleaned at the store anyway).

**290X tests:** `tests/test_advanced290.py` (15) — payload
neutralization (script/img-onerror), Telugu preservation,
whitespace/control/zero-width handling, caps, write-path wiring
pins for members/portal/stateless/campus, quote-safe `esc`
contract across all defs, functional register + poll-auto
cleaning. Full suite **857 OK** · finalize PASSED.

---

## ADDENDUM — 310X + 320X (Approve-to-Live + perfection round)

**310X — Approve-to-Live (Bridge Phase 3, owner-approved):**
daily draft auto-builds (`core/publish_queue.py`: Daily Quiz +
today's live exams + Sunday Weekly Grand), state machine
`draft → approved → live / rejected`, and **nothing publishes
without owner approval** (dashboard 🚦 Publish Center; push &
go-live hard-gated server-side). WP push (`core/wp_push.py`)
uses a revocable Application Password from env/.env only.
Suite 882 OK · live approve-gate smoke verified.

**320X — parser root fix:** the academic-bank parser treated any
`(...)` as the Telugu gloss, shredding math/code options
(`O(log n)` → EN `O` ×4) into duplicate stubs — the last two
"invalid" bank questions. Now `(...)` splits only when it
contains Telugu script. Bank health: **invalid 0, grade C → B**
(1517 Q, position-bias note unchanged — live polls still
`poll_safe`-balanced at send). Go-live now also emits a
Tanglish announcement (Telegram admin auto-send + copy-to-
WhatsApp). Suite **891 OK** · finalize PASSED.

---

## ADDENDUM — 330X (TS & AP Exam Hub)

State-separate goals (`tspsc`/`appsc` with own channels,
exam-keyword PYQ pools, countdown dates) join the combined
`groups` goal — a Telangana student now mocks from TSPSC stock
only (functionally pinned: picked channels ⊆ {TSPSC, CURRENT}).
`portal.state_hub()` serves honest per-exam totals + PYQ counts
and subject stock; the portal home renders the 🗺️ TS & AP Exam
Hub (one-tap Mock + goal-scoped subject tests — sectional pool
now filters by goal channels with all-bank fallback under 3).
Board-exam channels (10th/Inter/Diploma/B.Tech, both states)
listed with real counts. Live counts at ship time: TSPSC 356Q
(33 PYQ), APPSC 56Q (32 PYQ — AP harvest is the next stock
target). Suite **901 OK** · finalize PASSED · hub smoke 200.

---

## ADDENDUM — 340X (stock growth + targets)

Curated academic bank +16 bilingual questions (TS/AP 10th,
Inter, Diploma, B.Tech — 4→6 per board channel, 68 total,
answers position-varied, zero duplicate options). Hub now
carries stock targets per exam (`_HUB_TARGETS`) with honest
gap fields; the portal hub shows 📈 "+N stock kavali" chips
and the dashboard go-live checks gained a guarded "Exam stock
targets (340X)" item. Ship-time truth: APPSC remains the big
gap (56Q vs 150 target) — PYQ harvest, not filler, is the
planned fill. Bank: 1525Q, grade B, invalid 0. Suite **908 OK**
· finalize PASSED.

---

## ADDENDUM — 350X (bank resilience)

**Incident:** generated bank state (ignored `question_bank.json`)
was lost to a workspace snapshot restore; the canonical tracked
sources rebuild only 321Q. **Fix:** `scripts/bank_restore.py`
(rebuild_json → offline top_up → health report, idempotent) is
now the standard fresh-deploy step — it restored 501Q served
(170 real PYQ untouched; generated stock honestly labelled
`offline-gen`, never PYQ). Also fixed: `load_bank` content-
signature dedupe (a dynamically-generated question existed 5×;
497Q after dedupe, invalid 0, positions balanced, grade B).
Deploy rule: run `python3 scripts/bank_restore.py` once on any
fresh checkout/VM before starting services. Suite **913 OK** ·
finalize PASSED.

---

## ADDENDUM — 360X (FSRS-Lite spaced repetition)

The fixed 0→3d→7d review ladder mastered a question after ONE
lucky correct. `core/fsrs_lite.py` (pure, zero deps — informed
by FSRS retention curves, no native packages) now grades by
stability: retrievability R = 1/(1+t/9S), reviews target R=0.90,
hard-earned recalls grow stability most, lapses collapse it to
a floored 25%, and cards retire only when proven (S≥45, ≥4
recalls). Legacy ladder cards migrate on first touch; a fresh
mistake joins the same day's review batch (the product's daily
cadence), so bot /review behaviour is unchanged. Students get
a 🧠 Memory Deck (`/api/portal/memory` + portal strip: due /
falling / strong + per-topic retention) and a Memory Booster
task in Today's Smart Plan. Legacy SRS tests were migrated to
the stronger stability contract — spacing proven, mastery
earned, lapse re-queues. Suite **925 OK** · finalize PASSED.

---

## ADDENDUM — 370X (Paper Factory: PYQ papers → drafts → bank)

Official previous-paper PDFs used to need the collector's web
pipeline; there was no owner-reviewable on-ramp for a PDF the
owner already holds. `core/paperfactory.py` closes that gap:
filename provenance (exam/year/paper), best-available text
extraction (Docling when installed, else the collector's proven
pdftotext→pypdf chain), the tolerant quiz parser, and
provenance-stamped `PAPER-{exam}-{year}-NNN` ids. Two trust
gates keep the bank clean: (1) everything lands as a DRAFT in
`data/paper_drafts.json` — never straight into the bank, the
310X approve-to-live rule applied to papers; (2) questions
whose Telugu translation is unavailable stay flagged
`translation_pending` inside the draft and are NEVER banked
(`go_bank` skips them; the draft stays open for a later retry),
because `validate_question` requires real Telugu — silently
mirroring English would fake bilingual coverage. Draft-time
dedupe now checks the served bank PLUS `scraped_bank.json`
(approved papers land there before the next rebuild — missing
it re-admitted banked questions). Owner surfaces: dashboard
PYQ card → Paper Factory (path → draft → approve/reject) and
`scripts/paper_factory.py` CLI. `tests/test_advanced370.py`
(6) pins meta/parse/dedupe/translation-gate/reject. Suite
**931 OK** · finalize PASSED (1480 Q, 0 errors).

---

## ADDENDUM — 380X (Paper Factory Pro: OCR + translation bridge)

Two gaps closed on the 370X on-ramp. (1) **Scanned papers:**
extraction gained an optional OCR layer (PyMuPDF render →
PaddleOCR Telugu → Tesseract tel+eng, 30-page night-batch cap);
with no OCR stack installed a text-less PDF honestly returns
`ocr-needed` instead of crashing or faking text — installing
`pymupdf` + an OCR engine on the VM enables it with zero code
change. (2) **Translation bridge:** `translate_draft()` runs
the exam-grade MCQ translator (whole-question unit, number-
preservation gate in `translator.translate_mcq`) over a
draft's pending questions; each success is re-validated and
un-flagged so the next Approve banks it, each failure stays
parked. Dashboard drafts now show 📝 TE pending counts with a
🌐 Translate action (`/api/papers/translate`, login-locked
like every owner route); CLI gains `translate <draft_id>`.
`tests/test_advanced380.py` (4) pins ocr-needed honesty,
translate→bank, broken-translator parking, and terminal-draft
guards with a deterministic stub LLM. Suite **935 OK** ·
finalize PASSED (1477 Q, 0 errors).

---

## ADDENDUM — 390X (Bot Paper Factory)

The Paper Factory is now reachable where the owner already
works: the Telegram bot. Staff DM a paper PDF (or a .txt with
a /paper caption) → `core/paperbot.py` saves it to
`data/pdf_inbox/` (basename-sanitised, never clobbers), builds
the 370X draft, and replies with gate-honest counts plus
inline buttons — ✅ Bank / 🌐 Translate (only when pending) /
❌ Reject (`pf:{act}:{draft_id}`, sized under Telegram's
64-byte callback cap). Callbacks are staff-gated and simply
dispatch into paperfactory; a successful bank reloads the
bot's in-memory bank (same pattern as the Notebook import).
`/papers` lists drafts with TE-pending counts. One real hole
was closed on the way: `go_bank` banked 0 questions and
reported success on a REJECTED draft (buttons on an old
message could still act) — rejected is now terminal there too,
mirroring translate_draft. `tests/test_advanced390.py` (5)
pins sanitisation, the upload→translate→bank flow, reject
finality, and honest junk-PDF errors. Suite **940 OK** ·
finalize PASSED.

---

## ADDENDUM — 400X (go-live deploy perfection)

Merging code is not going live: the deploy layer had four
real defects that would only surface on the VM. (1) The
dashboard systemd unit — the only process serving
quiz.studentup.in — was never installed by deploy.sh;
`--systemd` now installs all four units. (2) Units launched
apps with `ExecStart=/usr/bin/python3 scripts/…` from a repo-root
cwd; units now use absolute ExecStart and
`WorkingDirectory=…/scripts` for every Python unit, matching
how the apps resolve `env/.env` (config.ROOT = repo root —
`scripts/env/.env` lookups could never find the real secrets
file under the old layout). (3) deploy.sh never ran
bank_restore: a fresh VM would have served the 321Q floor
instead of the restored bank — step [3b] now restores on
every deploy (idempotent). (4) The webhook unit hardcoded
`WEBHOOK_SECRET=change-me`; secrets live only in `env/.env`.
Also added: `deploy/Caddyfile` (quiz → 127.0.0.1:5000,
automatic HTTPS; app port never public) and
`docs/GO_LIVE_400X.md` — the ordered owner runbook
(smoke-before-DNS, VM-side secrets only). `_golive_checks`
executes standalone-clean (14 checks; the only sandbox fail is
BOT_TOKEN, by design). `tests/test_advanced400.py` (10) pins
the whole deploy contract. Suite **945 OK** · finalize
PASSED.
