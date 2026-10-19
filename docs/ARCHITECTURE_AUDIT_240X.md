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
