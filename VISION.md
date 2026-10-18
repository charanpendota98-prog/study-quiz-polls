# 🎯 StudentUp — Vision

**Prathi TS/AP aspirant ki — prathi roju, thana exam ki saripoyina previous-exam
(PYQ) + fresh questions, bilingual (Telugu/English) polls ga, Telegram mariyu
WhatsApp rendu chotla, miss avvakunda — rank, streak mariyu district pride tho.**

Oka government-exam student ki kavalsindi textbook kaadu — **roju repeat
ayye practice habit**. StudentUp aa habit ni phone lone, already vaade
apps (Telegram/WhatsApp) lone build chesthundi.

## 🏛️ Vision pillars (anni ippudu live + measurable)

| Pillar | System | Measurement |
|---|---|---|
| 📚 **Content Engine** | 517 sources (118 live, 308 audit queue), collector 8×/day, 04:45 content-gated audit, 01:00 scout, 01:30 backfill, PYQ papers harvest 02:15+13:45, guarantee 40% PYQ share in every round | bank questions, PYQ %, unused/channel, papers harvested |
| 📲 **Dual-Platform Delivery** | Telegram native quiz polls (validated single path, smart retry) + WhatsApp native polls via Baileys bridge (two-phase: poll → 60s → answer key, anti-ban pacing, localhost+token security) | last-7d LIVE polls per platform |
| 🎮 **Engagement Loop** | Points, streaks, district war, arena, squads, campus events, coach DMs, win-back, report cards | students with points, activity |
| 🛠️ **Zero-Effort Setup** | Excel multi-sheet import (+ Telegram sheet), Manual Setup form (exam/timings/subjects/custom exam), bundles, schedules (WA/TG/both), `bash start_all.sh` one-command stack | active schedules, coverage gaps |
| 🛡️ **Trust & Safety** | No fake sends (honest NOT SENT), validation gate, duplicate protection, no-repeat guarantee, anti-ban pacing, IP+password dashboard lock | gate status, dry vs live ratio |
| 🎯 **Mission Control** | Dashboard home lo **Vision Score (0–100)** + pillars + priority "Next actions"; `python3 -m core.vision`; `/api/vision` | vision score & actions |

## 🔁 Daily rhythm (scheduler — watch.py)

04:45 audit → 05:30/07:45/08:15/11:00/16:00/19:45/20:15/22:30 collect →
quiz slots, answer keys, coach, digest, war, leaderboards — anni automatic.
Question stock eppudu aagipodu: seed bank (566) is just the start.

## 🚀 100x roadmap (next leaps)

1. ✅ **Item intelligence** (DONE): difficulty auto-calibration
   (blueprint), suspect-key quarantine (verifier), too-easy retire
   (Bank.unused safety-valve tho), Item Intel Ops dashboard, reaction-
   poll bulk learning kuda close ayindi.
2. ✅ **Personal syllabus graph** (DONE): `core/syllabus.py` — weak
   topics + due reviews + fresh mix personal rounds (coach DM), /myplan,
   /api/syllabus.
3. ✅ **Multi-number WhatsApp scale** (DONE): bridge named sessions
   (`WA_SESSION_NAME` + per-session auth), pipeline bridge pool
   (`WA_BRIDGE_URLS`, sticky per-group routing, `/api/whatsapp/bridges`) —
   failed deliveries ki persistent retry queue (backoff, max 3) kuda live.
4. **Paper factory**: ✅ index-expansion DONE — official index page
   (33 entries) lo unna anni papers registry loki auto-register
   (`discover_index_papers`, host-whitelist, URL guessing ledu), batch
   ingest + migilinavi next runs lo drain, weekly rescan, channel-need
   priority (weakest stock first). Migilina pani: state board
   (10th/Inter) papers — official index sources registry loki vachaka
   ive factory drain chesthundi.
5. ✅ **Campus growth + monetization view** (DONE): Business Pulse
   (`core/pulse.py`, Dashboard → 📈 Growth & Revenue, `/api/pulse`) —
   real funnel (registered → activated → active 7d), referral engine
   (joins, activated, top referrers + tiers), partner-offer economy,
   monetization planner (real active base × admin price/conversion
   what-if — fake revenue kadu, projection ani clear label). Vision
   report lo growth pillar + referral/activation actions kuda.

6. ✅ **Pro Ops layer** (DONE): top-company observability — `core/metrics.py`
   (real event counters + hourly series, dry runs count avvavu),
   `core/flags.py` (feature flags/kill switches wired into verifier,
   autopilot, blueprint PYQ floor, retry queue), `core/auditlog.py`
   (admin action trail), `core/health.py` deep subsystem checks —
   anni Dashboard → 🏢 Pro Ops tab lo (`/api/metrics`, `/api/health/full`,
   `/api/flags`, `/api/audit`), Vision report lo ops summary kuda.

7. ✅ **Exam Conductor** (DONE): owner oka screen lo exam schedule
   chesthe time ki automatic launch — `core/conductor.py` + Dashboard →
   🎓 Exam Conductor (`/api/conductor`). Grand Test (Engine, background
   thread), District War (lobby → bot tick start), Campus Exam (join
   code mundu share, time ki start; players <2 unte honest fail).
   Daily fixed polls status strip kuda ade tab lo.

8. ✅ **Emoji text-polls ONLY WhatsApp Channel** (DONE, owner final rule):
   WhatsApp Channel (@newsletter) ki direct poll ledu kabatti akkade
   👍❤️😂😮 emoji text-poll + answer key; migilina anni chotla (Telegram
   channel/group, WhatsApp group, DM) DIRECT/native polls. Telegram
   reaction path opt-in flag (`channel_reaction_polls`, default OFF).
   Registration: poll aadagane Telegram profile tho AUTO-register,
   data members.csv/.xlsx + Google Sheet loki (source=poll_auto) +
   one-tap district/exam/mobile buttons.
   Question + emoji options text ga, 45 min window, tarvata ✅ answer +
   📊 % reveal; anonymous counts kuda tally avuthayi, reveal bulk ga
   item-intel loki (learning loop). DM polls native scoring tho ne.

## ✅ Ela verify cheyali

```bash
cd scripts && python3 -m core.vision     # vision report (score + actions)
python3 -m core.source_manager stats     # sources + bank + PYQ counts
python3 ../scripts/finalize.py           # validation gate
```
