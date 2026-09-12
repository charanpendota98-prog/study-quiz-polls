# 🚀 STUDENTUP — WINDOWS DEPLOY GUIDE (SCP + SSH)

> Server (from `sources/source_database_100plus.md`): **80.225.205.135**
> User: `ubuntu` · Key: `C:\Users\Charan\Downloads\ssh-key-2026-08-23.key`
> Zip: `studentup_deploy_v3.zip` (download from Arena workspace → `Downloads`)
>
> ✅ Zip already contains `env/.env` with BOT_TOKEN + 8 channels + all API keys.

---

## Step 1 — Copy the zip to the server (PowerShell, NOT ssh)

```powershell
scp -i C:\Users\Charan\Downloads\ssh-key-2026-08-23.key C:\Users\Charan\Downloads\studentup_deploy_v3.zip ubuntu@80.225.205.135:~/
```

## Step 2 — SSH into the server

```powershell
ssh -i C:\Users\Charan\Downloads\ssh-key-2026-08-23.key ubuntu@80.225.205.135
```

## Step 3 — On the server (paste these one by one)

```bash
cd ~
rm -rf studentup
mkdir studentup
unzip -o ~/studentup_deploy_v3.zip -d studentup
cd studentup
bash scripts/deploy.sh --audit --systemd
```

What deploy.sh does:
1. Backup (if any prior deploy) · 2. Copies files (keeps `.env` safe) · 3. Python + optional deps
4. Validation gate (finalize.py) · 5. Health check **+ channel-ID auto-detect (getChat → `-100...` ids)**
6. Installs & starts systemd services: `studentup` (watch/scheduler), `studentup-bot`, `studentup-webhook`

## Step 4 — Verify live (paste one by one)

```bash
systemctl status studentup studentup-bot --no-pager | tail -20
tail -f /home/ubuntu/studentup/logs/watch.log
cd /home/ubuntu/studentup/scripts
python3 check.py            # env keys + bank + channels OK?
python3 quiz_engine.py quiz --dry   # dry-run a full round
python3 audit_sources.py --only-enabled --no-write
```

Then check your Telegram channels — bot should post at the next scheduled slot
(07:30 / 19:30 IST, plus jobs every 30 min).

## Step 5 — Cleanup (important — zip has secrets)

```bash
rm ~/studentup_deploy_v3.zip
```

> ⚠️ Never share the zip, `.env`, or the SSH key. Regenerate the OpenAI key you
> pasted in chat after deployment (best practice).

---

## If your StudentUp server is different (e.g. Oracle 129.159.229.134)
Swap in the IP + key that belong to **this** server, e.g.:

```powershell
scp -i C:\Users\Charan\Downloads\ssh-key-2026-08-01.key C:\Users\Charan\Downloads\studentup_deploy_v3.zip ubuntu@129.159.229.134:~/
ssh -i C:\Users\Charan\Downloads\ssh-key-2026-08-01.key ubuntu@129.159.229.134
```

*(Only if that is the actual StudentUp Oracle VM — the repo docs name
80.225.205.135 + ssh-key-2026-08-23.key. Use whichever is real.)*


---

## ⚠️ BEFORE GOING LIVE — two mandatory secret fixes

1. **Replace `ADMIN_ID=YOUR_ID`** in `env/.env` on the server with your real
   Telegram numeric user id (message `@userinfobot` to get it). Admin alerts
   and `/analytics` will not work until this is a real id.

2. **Regenerate any OpenAI / Groq / Gemini keys** you pasted in chat after
   deploy (best practice). Update `env/.env` on the server only — never commit.

Optional presentation toggles in `env/.env`:

```
TELUGU_FIRST=1
ANSWER_MODE=instant          # or: delayed
QUIZ_OPEN_PERIOD=300
```

## Google Sheet CRM — live connection (set on the server)

```
SHEET_WEBAPP_URL=https://script.google.com/macros/s/AKfycbx2_JSBl2_zvfYVIuaKxpv8-_ObmoSD5oysdWLgeJYStV3QpxpUefB-b2x_BN7vs6QG8A/exec
SHEET_SECRET=<the SECRET value inside docs/sheet_webapp.gs on the Sheet>
```

**Deployment must be public to the script (not to the data):** Deploy → Manage deployments →
✏️ Edit → *Execute as: Me* · *Who has access: **Anyone*** → Version: New → Deploy.
Test: open the /exec URL in a private/incognito window — it must show a small JSON like
`{"ok":true,"service":"StudentUp CRM"}` and NOT a Google sign-in page. Then in the bot: `/syncsheet`.
The Sheet itself stays private; the SECRET blocks anyone else from writing.

## Source wave 11 Sep 2026 — TS/AP official papers via Sakshi + Adda247

* `data/pyq_papers.json` → **199 papers** (TSPSC 25, APPSC 37, POLICE 42, SSC 37,
  BANKING 25, DEFENCE 19, RAILWAY 14). New: TSPSC Group-2 2024 **master QP + final
  key for all 4 papers**, Group-3 2024 P1–P3, APPSC Group-1 Prelims 2024 P1/P2,
  APPSC Group-2 2025/2019/2017 prelims+mains (adda247 mirrors), AP Constable 2023,
  TS SI 2023 (GS + Arithmetic/Reasoning), TS Constable 2022/2023, AP SI 2018/2023.
* Sakshi embeds PDFs in a pdf.js viewer (`viewer.html?file=…pdf`). `core.pyq.unwrap_viewer`
  now resolves those, so both the harvester and the scout can use every
  `education.sakshi.com/en/<exam>/previous-papers-<year>` page (site covers TS/AP
  Police, Groups, DSC, TET, SSC, Bank, NDA/CDS back to 2002). 13 Sakshi/Adda hubs added
  to the scout.
* **WhatsApp channels** (`data/whatsapp_channels.json`): WhatsApp gives no public
  preview/API, so they cannot be scraped. They are a *manual* tier — follow on a
  phone, forward PDFs to the bot / `data/pdf_inbox/`. Only publisher-verified links
  are listed (Sakshi Education for now).
* Run on the server: `cd scripts && python3 -m core.pyq harvest --only TSPSC --limit 8`
  then `python3 -m core.pyq status`.

## Source wave 2 — 11 Sep 2026 (quiz websites, no-repeat hardening)

* `data/collector_sources.json`: **436 sources, 118 enabled** (+34 verified live today):
  FreeOnlineTest9 daily CA quiz archive + 10 subject mocks (Polity, Economy, History,
  Geography, Physics, Chemistry, **Telugu**, Maths, Puzzles, Aptitude); DailyGK SSC-CGL /
  SSC-CHSL / RRB-NTPC daily CA hubs + 7 static-GK topic hubs (20 polity sub-topic sets
  verified); Sakshi Groups per-subject Telugu practice hubs (15 subjects).
  Guessed URLs that redirected to a homepage (`/en/<exam>/bitbank`, `/appsc/practice-test`,
  mcqbits category) were **not** added.
* No-repeat now has three layers: (1) scrape fingerprint (`sha1(q|options)`) at collect
  time, (2) permanent posted-id + content-signature store at pick time, (3) NEW paraphrase
  guard `Bank._near_posted` — same channel, ≥3 identical options and ≥0.72 content-word
  overlap with any of the last 400 posted questions ⇒ treated as a repeat.

## 🏟 Sunday Grand Test (weekly real-exam mock)

* **Saturday 18:00** — teaser in every quiz channel (`GRAND_TEST_TEASER_TIME`).
* **Sunday 09:00** — `GRAND_TEST_QUESTIONS` (25) per channel (`GRAND_TEST_TIME`); T-5 / T-1
  alerts fire automatically for it.
* Composition: ~60 % **revision** = Mon–Sat questions ranked by how many players missed
  them (from poll stats), topic-capped; ~40 % **fresh** via the normal no-repeat pick.
  Ordered Section A easy → B medium → C hard, with a divider line before each section.
* Scoring: +1 / −⅓ / 0 (negative marking). Sunday bonus: correct ×2 points,
  🥇+100 🥈+60 🥉+40, district topper +25. Result post shows Top-10 with name + district,
  ✅/❌ counts, Top-10 % / Top-50 % cut-offs, average and **District of the week**.
* Q-by-Q answer key follows the same rule as daily rounds — posted before the next round.
* State: `data/week_rounds.json` (rolling 14 days). Module: `scripts/core/grandtest.py`.

## 🏆 Monthly Mega Test · 🏟 District League · 🖼 Rank cards

* **Monthly Mega Test** — the **last Sunday** of each month the 09:00 slot becomes a 50-Q
  final (`MEGA_TEST_QUESTIONS`): revision window = whole month, correct ×3 points,
  🥇+300 🥈+200 🥉+120, `mega_wins` recorded for the Hall of Fame. Saturday teaser adapts.
* **District League** — Monday `LEAGUE_POST_TIME` (08:00) in the hub channel. Weekly
  district score = avg correct per player ×10 + participation (≤10 players ×2) + Grand Test
  podium (5/3/2). Two tiers (🅰 Premier top-8 / 🅱 Challengers); month end (with the Hall of
  Fame post) bottom-2 ⬇ / top-2 ⬆. Form arrows ▲▼, District MVPs. State `data/league.json`.
* **Rank cards** — after every round / Grand / Mega test a 1080×1350 PNG certificate
  (name, district in English + Telugu, exam, score, date, handle) goes to the channel for 🥇
  and by DM to 🥇🥈🥉. Needs `pip install pillow`; for Telugu text on the image install
  Noto Sans Telugu (`sudo apt install fonts-noto-core` or drop the .ttf in `data/fonts/`).
  Without Pillow it silently skips (text Top-10 still posts). `RANK_CARDS=0` disables.
  Brand/handle on cards: `BRAND_NAME`, `BRAND_HANDLE`.

## 📋 Weekly Report Card · 🤝 Referral Leaderboard · 🥊 Beat the Topper

* **Weekly Report Card** — Sunday 21:15 DM to every member who played this week: rounds
  played/available, accuracy, best round rank, district & overall rank, points trend vs last
  week, subject-wise bars (GK / Reasoning / Aptitude / English), weak topics to revise and one
  concrete goal for next week. On demand: `/report`.
* **Referral Leaderboard** — Monday with the League: this-week and all-time top referrers,
  tiers 🥉3 · 🥈10 · 🥇25 friends, district referral race. Referral link: `/invite`.
* **Beat the Topper** — Mon–Sat `CHALLENGE_TIME` (13:00) DM with a 🥊 Challenge button:
  yesterday's best round (≥3 players, topper ≥5 correct) → the topper's own 5 questions,
  same timer, one attempt per day. Beat the topper's scaled score (tie → faster time) ⇒
  +15 pts and 🥊 badge. Also `/challenge`. State `data/challenges.json` (one day at a time).
  Replays are intentional and do not touch the no-repeat store.

---

## 🔄 UPDATE AN EXISTING SERVER (Sep 2026 — advanced engine)

Everything since the first deploy is in the branch `arena/01a07852-study-quiz-polls`.
On the server (SSH in first):

```bash
cd /home/ubuntu/studentup
sudo systemctl stop studentup studentup-bot studentup-webhook

# 1) fetch the new code (keeps env/.env and data/ untouched)
git fetch origin arena/01a07852-study-quiz-polls 2>/dev/null \
  || git clone https://github.com/charanpendota98-prog/study-quiz-polls.git /tmp/su_new
if [ -d /tmp/su_new ]; then
  cd /tmp/su_new && git checkout -q arena/01a07852-study-quiz-polls && cd -
  rsync -a --exclude env/.env --exclude data/ --exclude logs/ /tmp/su_new/ /home/ubuntu/studentup/
  rm -rf /tmp/su_new
else
  git checkout -q arena/01a07852-study-quiz-polls && git pull -q
fi

# 2) deps + font (Pillow → rank cards; Noto Telugu → Telugu on the cards)
python3 -m pip install -q -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -q -r requirements.txt
sudo apt-get install -y -q fonts-noto-core

# 3) add the new keys to env/.env (once) — copy the block from .env.example:
nano env/.env      # SHEET_WEBAPP_URL, SHEET_SECRET, BRAND_HANDLE, BOT_USERNAME

# 4) health + dry run
cd scripts && python3 check.py && python3 quiz_engine.py quiz --dry | tail -5 && cd ..

# 5) restart
sudo systemctl start studentup studentup-bot studentup-webhook
systemctl status studentup studentup-bot --no-pager | tail -6
tail -n 30 logs/watch.log
```

### First-day commands (run once after restart, paste the outputs to Arena)
```bash
cd /home/ubuntu/studentup/scripts
python3 -m core.collector --limit 20          # live web scrape sample
python3 -m core.pyq harvest --only TSPSC --limit 8
python3 -m core.scout run --minutes 3
python3 -m core.resilience telegram
python3 -m core.resilience status
python3 -m core.crm sync                      # members → Google Sheet
```

### What is live after this update
Paced rounds (no auto-reveal, shuffled keys, Q-by-Q key before next round) · registration
in bot · Top-10 with name + district · podium bonuses · daily champions · 🏟 Sunday Grand
Test · 🏆 Monthly Mega Test · District Cup · 🏟 District League · 🤝 Referral board ·
🖼 rank cards · 📋 weekly report cards · 🥊 Beat the Topper · Hall of Fame · 436 web
sources + 199 PYQ papers + 37 Telegram channels · supply guard · Google Sheet CRM.

## 👛 Points Wallet → real discounts at StudentUp Internet Centre

* Members: `/wallet` (balance, ₹ value, what they can redeem, next unlock, active vouchers),
  `/redeem` (offer buttons — ✅ affordable / 🔒 locked), `/cancel SU-XXXXXX`.
* Redeem = points **held** + one-time code `SU-XXXXXX` voucher (Telugu + English, centre
  address/phone/hours, validity). Admin + `STAFF_IDS` get a notification.
* Counter: staff sends `/verify SU-XXXXXX` → bot shows name/district/phone/offer, marks
  USED and only then **burns** the points; a second `/verify` warns "already USED".
  `/vouchers` = summary. Expired holds auto-release at 00:20 daily.
* Two categories only — 📝 **application filing discounts** (₹20 / ₹50 / 1 free / 3 free +
  priority; redeemed at the counter with `/verify`) and 📚 **study materials** (monthly CA
  PDF, PYQ pack for the member's exam, most-missed 100 Q + explanations, printed set at the
  centre). Material PDFs are sent by the bot instantly from `data/materials/` (see README
  there; `{exam}` in the filename → member's exam, `_general` fallback). Missing file →
  voucher stays active and points are NOT deducted until delivered.
  Edit prices/offers/centre details in `data/rewards_catalog.json` (auto-created; hot-reloaded).
* Hub channel promo Tue & Fri 12:00 (`REWARDS_PROMO_TIME`).

## 🧠 Most-missed explanation (no lessons, no audio)
With the previous-round key, if ≥50 % of voters (min 5 votes) got a question wrong, the
bot posts that question's own verified explanation in Telugu + English (max 2 per round).
Uses channel poll totals (`poll` updates now recorded) with DM-mirror member stats as
fallback. Nothing is generated at post time.

## 🧲 Addiction & acquisition hooks (`scripts/core/hooks.py`)

* **Streak Shield** — every 7-day streak banks a 🛡 (max 2); a missed day consumes one
  instead of resetting (00:10 job, member gets a DM). Milestones 7/30/100 days: +50/+200/+1000
  pts and a channel shout-out with name + district.
* **Mystery Multiplier** — one secret question per round is ×2/×3/×5 (60/30/10 %),
  deterministic per (round, channel); revealed only in the Top-10 post. Opener teases it.
* **Friend Squads** — `/squad new <name>`, `/squad join CODE`, `/squad leave`, `/squad`
  (3–5 members; joining counts as the leader's referral +20). Monday 08:05 "Squad of the
  week" Top-5 in the hub with all names + districts. State `data/squads.json`.
* **Share posters** — after every round each registered player (ranks 4+) gets a personal
  "నా స్కోర్" PNG (rank, district, score, streak, handle) for WhatsApp status; podium keeps
  the gold/silver/bronze cards.
* **Social proof** — opener shows "🔴 N aspirants played the last round · M registered".

## ⚔️ SQUAD BATTLE ARENA (`scripts/core/arena.py`) — PUBG-style rooms

* Squad leader `/battle new [10]` → room `RM-XXXX` (mode = leader's exam channel). Opponent
  leaders `/battle join RM-XXXX` (whole squad enters, 2–4 squads). `/battle list` = public
  lobby; `/battle start` (host) or auto-start 3 min after the 2nd squad; `/battle watch` for
  live scoreboard; `/battle top` season rankings; `/battle` status; `/battle tournament`
  (admin) = top-8 ELO bracket.
* Match: 30 s countdown → each Q to every player at the same moment (DM quiz poll, 45/60/75 s
  by difficulty, auto-closes) → live scoreboard after every Q (squad ranks, per-player pts,
  🔥 streaks, "neck and neck") → final.
* Scoring: ✅ +100 + speed bonus (≤50) · ❌ −25 · skip 0 · squad score fair-scaled to 5 players.
  Rewards: winners +30 pts each, 2nd +15, MVP +20; channel shout-out with names + districts.
* Season ELO per squad (K=32) → 🥉 Bronze 🥈 Silver 🥇 Gold 💠 Diamond 💎 Conqueror; Monday
  08:05 Arena rankings in hub; season resets monthly.
* Questions come through `Bank.pick()` → permanent no-repeat still holds. The bot loop polls
  every 3 s while a match is live (50 s otherwise). State `data/arena.json`.

## ⚔️ DISTRICT WARS (`scripts/core/districtwar.py`) — daily, everyone, every exam

* Daily `WAR_TIME` (21:00): T-5 alert opens the **opt-in lobby** — DM with "⚔️ I want to play"
  and "👥 Squad మొత్తం join" buttons (+hub post). Only people who tap (or `/war join`,
  `/war join squad` for a whole squad by its leader) are fighters; T-1 alert goes only to those
  not yet in; at start the lobby **locks** (no entry after start; button removed after tap).
  Fighters get the same 10 Q in DM at the same time (45/60/75 s, auto-close, no negative marks).
  Live board with bars + personal line after Q3, Q6 and before the last Q; result shows
  district bars, accuracy, each district's top fighter and the Top-5 fighters by name.
* **Common syllabus across all state & central exams**: 3 GK · 3 Reasoning · 2 Aptitude ·
  1 English · 1 Current Affairs, drawn across every channel's bank via `Bank.unused()` and
  marked posted (permanent no-repeat).
* Result (bot loop finishes; watch publishes to the hub ~18 min later): district ranking by
  avg pts per fighter ×10 + fighters (≤10) ×3, each district's top fighter, War MVP (+25),
  winning district's fighters +10, rivalry line, month season table (wins/points), 🛡 Defender
  badge for 5 wars in a row. Personal DM with own score + district rank. `/war` = status.
* Sunday 21:45 season table in the hub. State `data/district_war.json`.
* Squads are **not** Telegram groups — each member answers in their own bot DM; the bot sums.

## 🤝 Partner Marketplace (`scripts/core/partners.py`) — district merchants × students

* Admin: `/partner add <name> | <district> | <category> | <phone> | <merchant_tg_id> | <address>` then
  `/partner offer <PID> | <title_te> | <title_en> | <pts> | [discount|freebie|examday] | [EXAM] | [from] | [to] | [cta]`.
  `/partner merchant <PID> <tg_id>` authorises a counter person; `/partner stats <PID>` = impressions,
  vouchers, redemptions, unique students (your sales deck); `/partner on|off <PID>`; `/partner ad` posts now.
  Merchants self-apply with `/partner apply …` (admin gets a DM).
* Ads: `AD_SLOTS` (10:30 / 15:30 / 20:45) → round-robin offer card in `AD_CHANNELS` + DM only to
  members of that partner's district (`/noads` to opt out). District `ALL` = state-wide.
* Students: `/offers` → their district's offers (✅ affordable / 🔒 need points / ⏳ exam window),
  tap → `PT-XXXXXX` voucher (points held); merchant `/pverify PT-…` at the counter → points burn;
  `/pcancel`. Exam-day offers unlock only inside the exam window for members whose target exam
  matches ("exam రాసి వచ్చి claim"). Per-member and total caps, expiry, auto-release.
* Smart referral: +20 on registration, **+30 when the friend plays 3 rounds within 7 days**,
  milestones 5/10/25 activated → +50/+100/+300; `/invite` explains it.
* **Exam-day check-in loop**: 12:30 on any day inside an exam-day offer window, matching students of
  that district get a DM with **"✅ నేను <EXAM> exam రాశాను"** → +25 pts (Exam Warrior) and only then
  the exam-day offers unlock (`/examdone` also works). Exam hall → partner restaurant/coaching footfall.
* **Flash deals**: `/partner flash <PID> | title_te | title_en | pts | hours | stock` → posted immediately,
  countdown + "N left", shown first everywhere. Category filter: `/offers food|coaching|shop|salon|…`.
* **Merchant self-service**: `/mystats` (their numbers + pending vouchers); every Monday 08:30 an
  automatic report DM (`/partner weekly` to force).
* **Referral v3**: +20 register · +30 activated (3 rounds/7 days) · **mentor share +2 per round the
  friend plays for 30 days (cap 60)** · milestones 5/10/25 → +50/+100/+300 · **Monday 08:30 Top
  Recruiters of the week** in hub channels, winner +100.

## 📸 Social Growth Engine (`scripts/core/social.py`) — Instagram / YouTube followers

**Code-drop loop (no screenshot review needed):**
1. `/social new ig | Polity reel 7 May | 30 | 3` → bot replies with code `SU-XXXX` **and the exact auto-DM
   text**. Paste it into Instagram's native auto-reply / ManyChat for that post ("Comment QUIZ").
2. Post caption: *"Follow + comment QUIZ → DM లో code → bot లో /claim CODE → +30 pts"*. Instagram only
   auto-DMs followers, so the code itself proves the follow.
3. Student: `/claim SU-XXXX` → points once per campaign; every 5th claim = 🌟 Super Fan +100.
   YouTube: say the code at the end of the video / pinned comment → `/social new yt | …`.
4. Fallback: student sends a follow screenshot to the bot → staff get the photo with ✅/❌ buttons → +20.
5. `/social` = claims per campaign (= verified new followers). Saturday 11:00 hub promo; the prompt is
   also shown right after registration. `.env`: `INSTAGRAM_HANDLE`, `YOUTUBE_HANDLE`.

**Inbound business leads (every district's shops should contact us):**
* Students: `/scout <business> | <type> | <owner phone> | <area>` → staff DM; when you convert
  (`/social convert L0001 P001`) the scout gets +150.
* `/pitch <district>` → sales sheet with that district's live numbers to forward to any owner.
* `/social opening <PID> [days]` → 🎉 NEW OPENING tag + ≈2× ad frequency for a week.
* Monday 08:30 hub post "Partner with StudentUp" listing biggest districts (`/social call` to force).

## 🛍 Ad scopes, digest slots, onboarding (partners v3)
* Partner scope = `district` field: a district name, **`TS` / `AP` (state-wide)**, or **`ALL`**; optional
  7th field **mandal** → shown first (🏠) to members who set `/mandal <name>`. Members can move once per
  30 days with `/mydistrict <district>` (exam centre / hostel).
* Each `AD_SLOTS` run now sends **one digest**: hub channels get a card of all live offers (state → district →
  mandal, flash first, register CTA `t.me/<bot>?start=offers`), every member gets ONE personal DM with only
  their relevant offers + claim buttons — all 3 slots carry every partner, no partner ever waits for a turn.
  `/partner preview` shows the card; `/whatsapp` gives a plain-text copy for WhatsApp groups/status.
  `/partner photo <PID>` (reply to a photo) attaches the partner's poster to the hub card.
* Onboarding: `/social kit` = the "how to join + packages" message to forward to any owner;
  `/partner apply` replies with the same kit. Claims require registration (+25 bonus) — the CTA says so.

## 📊 Exam-wise boards (`scripts/core/examboard.py`)
Every exam channel now has its own competition next to the all-exam District War:
* Round close → Top-10 **+ "🏙 <EXAM> జిల్లాల clash"** (district accuracy bars, players, best fighter).
* 21:30 daily → "Today in <EXAM>" Top-10 across the day's rounds + district table, posted in that channel.
* Sunday 20:15 → **<EXAM> WEEKLY CHAMPIONS**: +40/+25/+15, District of the week +10 to all its members.
* Bot: `/top tspsc` (today) · `/top tspsc week` · `/top tspsc districts`. District score = accuracy +
  2×players (capped at 15) so small districts can win.

## 🏁 Round Show + ⚔️ War ranks/squads
* **Round close post** (`core/roundshow.py`) now counts EVERY answerer: 🏆 Top 10 (level badge, ⚡ fastest),
  🌱 Rising 5 (rank 11+, "+N ✅ to Top 10"), 📊 score-spread histogram, 🏅 specials (fastest, best newcomer,
  comeback vs last round, perfect scores, District of the round), 🧮 points formula, unregistered count.
  Personal DM card adds "Rank #k/N · tier · you beat X% of players".
* **District War**: fighters carry their squad → 👥 SQUAD BATTLE table inside the same war (≥2 squad members
  fighting), winning squad +15 each; kill-streaks 3/5/8/10 → +5/+10/+20/+40; lifetime war points →
  ranks 🪖 Recruit → ⚔️ Fighter → 🛡 Warrior → 🔥 Veteran → 👑 Warlord → 🐉 Legend, RANK UP line in result;
  `/warrank` = your rank + all-time war board.

## 🎓 Campus events (`scripts/core/campus.py`) — college-vs-college in minutes
1. `/campus new KU Fest | Warangal | Kakatiya Univ ; SR College ; Vaagdevi | 15 | medium`
   → code `CE-XXXX` + **one deep link per college** (`t.me/<bot>?start=cXXXX-2`). Print/QR/WhatsApp them.
2. Student taps the link → college + district auto-tagged → only **name + phone** asked (2 steps, degree
   default) → "ready" (+25 pts). `/campus status CE-XXXX` shows joined per college.
3. `/campus start CE-XXXX` → questions to every joined student's DM one at a time (timed, degree-friendly
   common syllabus: GK/reasoning/aptitude/English/CA, level easy|medium|hard, no-repeat).
4. Auto result to all students + organiser: 🏫 COLLEGE vs COLLEGE (avg + participation), 🏆 winner,
   Top 10 (+100/+60/+40), Rising 5, join-channel CTA (Telegram `BRAND_HANDLE`, WhatsApp `WHATSAPP_CHANNEL`).
   `/campus csv CE-XXXX` = full data file; `/campus post CE-XXXX` = public post to hub channels;
   `/campus prize CE-XXXX 1 <msg>` DMs a gift note. Students stay as normal members (district set).

## 🏛 State War + 🧾 application cashback
* Every District War result now shows **Telangana vs Andhra Pradesh** bar; **Saturday = STATE WAR NIGHT**
  (+10 to every fighter of the winning state, season tally).
* Counter: `/filed <telegram id | phone> [rupees]` after a paid application → +50 pts per ₹100 cashback,
  3rd application +100, 10th +500 (member gets a DM). Shown in `/wallet`.
