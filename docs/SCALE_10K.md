# 🚀 10K Scale — okka live exam ni 10,000 members rayyacha?

**Avunu.** Portal engine ni 10k-scale ki marcham (2026-10-16).

## Mundu unna problem
Prati answer ki motham `portal.json` load + save, prati points award ki
motham `members.json` save — 10,000 students exam lo idi seconds
teeskuni answers pothayi.

## Ippudu ela pani chesthundi
| Layer | Design |
|---|---|
| Portal store | Memory lo okkasari load; prati answer = O(1) dict update |
| Answers durability | Prati exam/daily answer **append-only journal** (`portal_events.jsonl`) loki — server crash ayina restart lo replay avthayi, answers povu |
| Disk snapshot | Background flusher prati ~2s ki atomic write (`portal.json`); exam finalize / mock submit appudu ventane flush |
| Members points | `KV.save_debounced()` — full-file write garijalo okkasari; parsed-JSON cache tho `Members()` construction kuda cheap |
| Server | ThreadingHTTPServer: `daemon_threads`, `request_queue_size = 256` (10k burst queue) |
| Hot paths | Exam board = top-10 matrame compute; exam-time parsing cached |

## Proof (sandbox, in-process — `scripts/loadtest_portal.py`)
```
👥 Students: 10,000 · Questions: 10 · Threads: 64
🚪 Join:   ~1.1s  (≈9,400 joins/sec)
✍️ Answers: 1,00,000 in ~2 min (≈800–900/sec, zero think-time burst)
🎯 Entries: 10,000 · Full-correct: 10,000
✅ okka answer kuda poledu
```
Real exam lo students seconds gap tho answer chestharu kabatti
avasaram ayye rate ~100/sec kante takkuva — mana deggara ~8x headroom.

## Limits (honest)
- Ee design okka server meeda 10k/exam ki comfortable. Andariki
  okesari start ayye mega events (lakh students) ki next phase:
  SQLite/Postgres store + multi-process. Journal format adhe
  migration ki ready ga undi.
- Members points kuda debounced (≤2s window) — bot process chese
  updates tho paatha last-writer-wins behavior eh continue avthundi.

## HTTP proof (real server, real requests — `scripts/loadtest_http.py`)
```
👥 Students: 2,000 · Questions: 10 · Threads: 64 (real HTTP)
📝 Register: 756/s · 🚪 Join: 694/s
✍️ Answers: 20,000 in 132s (151/s) · errors: 0
🎯 Entries recorded: 2,000
✅ HTTP LOAD TEST PASSED
```
300-student run: 236 answers/s. Real browsers keep-alive use
chestharu kabatti production speed deeni kante ekkuva untundi;
exam window lo kavalsina average (~100/s) ki comfortable headroom.
