# 📲 Messaging v4 — Telegram & WhatsApp Perfect / Advanced

Telegram mariyu WhatsApp delivery renditini audit chesi, dorikina bugs fix chesi,
rendu platforms oka consistent, validated, honest pipeline ga marchadam ee phase.

## 🐛 Dorikina pedda bugs

1. **WhatsApp answer key eppudu vellede kaadu** — question text *"Key &
   Explanation 60 seconds lo post chestham"* ani promise chesedi, kani
   `two_phase_answer` parameter ni broadcast worker ignore chesevadu.
   Students ki correct answer eppatiki telisedi kaadu.
2. **Telegram stdlib retry bug** — `requests` lekapote `urllib` transport lo
   Telegram 400/429 errors *raise* avutaayi; old code danini "network error"
   ga 5 sarlu retry chesedi, `retry_after` eppudu honour ayyedi kaadu.
3. **Legacy WhatsApp bot fake success** — gateway lekunda kuda
   "Dispatched via Stealth Simulated Buffer: OK" ani log chesi sent count
   penchestunde; question lone correct answer reveal chesedi.
4. **Bridge security** — WhatsApp bridge `0.0.0.0` ki bind ayyi, elanti auth
   lekunda evaraina mee WhatsApp number nunchi messages pampagalaru.
5. **Poll validation gaps** — bridge duplicate poll options reject
   chesevadu kaadu; invalid JID deep errors ichhedi; Telegram poll sends
   7 places lo manual payloads tho limits/validation bypass ayyevi.

## ✅ Telegram fixes (`core/telegram.py` + callers)

- `_call`: urllib `HTTPError` ni ippudu parse chesi — fatal (400/401/403)
  ventane fail, 429/5xx ki `retry_after` honour chestu exponential backoff.
  `requests` transport exceptions (`OSError` family) kuda same path.
- `send_quiz` central validation: 2–10 options, non-empty, correct index
  range check, question ≤300 / option ≤100 clamp, `is_anonymous` +
  `force_open_period` (timed games ki) params.
- **Anni poll sends ippudu okkate validated path**: engine DM mirrors,
  bot `/quiz`, challenge, arena, district-war, campus, autopilot coach.
- `sendPhoto`/`sendDocument` kuda Telegram JSON error ni `TelegramError`
  ga (real description tho) raise chestayi.

## ✅ WhatsApp fixes

- **Two-phase delivery nijam ga work avvuthundi** (`deliver_whatsapp_question`):
  Phase 1 native tappable poll (reject aithe text fallback) → thinking
  window (default 60s, configurable `answer_delay_sec`) → Phase 2 official
  answer key + bilingual explanation. Question fail aithe key velladu
  (orphan key = answer leak, already fix).
- Text lo promise chese seconds ippudu real delay tho match avvuthundi.
- Bridge running kani WhatsApp not-connected unte, configured legacy
  gateway ni kuda try chestundi; ledante honest `NOT SENT` + real reason.
- Legacy `whatsapp_bot.py`: gateway lekapote `ok: False, sent: 0` +
  "NOT SENT"; sent count kevalam real HTTP 2xx ke; question lo answer
  undadu — key separate follow-up message ga velthundi.

## 🔐 Bridge hardening (`gateway/wa_bridge.js`)

- Default bind **127.0.0.1** (same-machine dashboard ke saripothundi);
  kavalsinte `WA_BRIDGE_HOST=0.0.0.0` (firewall tho matrame).
- Optional `WA_BRIDGE_TOKEN`: set cheste anni API calls ki
  `x-bridge-token` header tappanissari (Python pipeline auto-gane pamputhundi).
- Poll validation bridge level lo: duplicate/empty options remove,
  <2 unique unte clear error; JID format (`...@g.us` /
  `...@s.whatsapp.net`) validation.

## 🧪 Verification

- Kottha `tests/test_messaging_v4.py` — 14 tests (Telegram 400-fatal /
  429-retry, clamps, two-phase order, no-orphan-key, poll→text fallback,
  legacy honesty, bridge source checks).
- **Full suite: 350/350 tests OK** (4 test fake Telegram doubles ki
  `send_quiz` add chesi update chesam).
- Validation gate: **PASSED (566 questions, 0 errors)**; dry quiz round:
  **78 polls / 8 channels**; `node --check gateway/wa_bridge.js` OK.

## ⚠️ Honest limits

- Sandbox lo real BOT_TOKEN / WhatsApp session ledu kabatti real sending
  test cheyaledu — anni dry-run + mocked/unit tests tho verify chesam.
  Mee server meeda `bash start_all.sh` tho QR scan cheste two-phase
  delivery live ga work avuthundi.
- `WA_BRIDGE_TOKEN` production lo set cheyadam strongly recommended.
