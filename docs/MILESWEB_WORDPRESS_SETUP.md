# 🌐 StudentUp — MilesWeb WordPress + Quiz Portal Setup Guide

**Architecture (idi final, inthe best):**

```
studentup.in            → WordPress (MilesWeb hosting) — brand, blog,
                          AdSense, materials landing, toppers pages
quiz.studentup.in       → StudentUp Python platform (VPS) — Daily Quiz,
                          Mocks, Live Exams, Weekly Grand Test, Portal
t.me/<bot>              → Telegram bot (same VPS) — polls, college
                          exams, materials file delivery
WhatsApp                → Channel + Groups (same VPS)
```

## ⚠️ Okka mukhyamaina vishayam — MilesWeb gurinchi

MilesWeb **shared WordPress hosting lo Python bot/dashboard 24×7 run
avvadu** (long-running processes, cron limits untayi). Anduke:

- **WordPress (MilesWeb)** = website + blog + AdSense (ippudu unnatte).
- **Python platform** = oka chinna VPS (₹300–500/month, 1–2 GB RAM
  chalu — e.g. Hostinger/Contabo/Hetzner) meeda run avvali. Bot,
  dashboard, portal, WhatsApp scheduler anni akkade.
- Rendu **DNS tho connect** avthayi (kinda steps). Students ki okka
  experience lage kanipisthundi.

Meeru already VPS vaduthunte (deploy.sh `/home/ubuntu/studentup`
chupistundi) — ade perfect, MilesWeb steps DNS varake.

---

## Step 1 — DNS (MilesWeb cPanel → Zone Editor)

| Type | Host | Value | TTL |
|---|---|---|---|
| A | `quiz` | `<mee VPS IP>` | 3600 |
| A | `exam` | `<mee VPS IP>` (optional, same portal) | 3600 |
| A | `app` | `<mee VPS IP>` (optional) | 3600 |

- `studentup.in` + `www` MilesWeb ke undanivvandi (WordPress akkade).
- DNS propagate: 10 min – 4 hrs.

## Step 2 — VPS meeda platform

```bash
cd /home/ubuntu/studentup && bash scripts/deploy.sh
# .env lo ivi set cheyyandi:
PUBLIC_BASE_URL=https://quiz.studentup.in
PORTAL_BASE_URL=https://quiz.studentup.in/portal
BOT_USERNAME=<mee bot username>
```

SSL: VPS meeda Caddy (automatic HTTPS) leda Nginx + certbot:

```bash
sudo certbot --nginx -d quiz.studentup.in
```

## Step 3 — WordPress nunchi Portal ki ICON/link

`integrations/wordpress/studentup-portal-icon.html` ni WordPress lo
paste cheyyandi (Appearance → Customize → Additional CSS/HTML block,
leda header menu lo custom link):

- 🎯 **Smart Quiz & Exams** → `https://quiz.studentup.in/portal`
- Menu + homepage hero renditlo link pettandi — students WordPress
  nunchi okka tap tho portal loki vastharu.

## Step 4 — WordPress ↔ Portal Bridge (automatic)

- `bridge_sync`: WordPress blog posts → portal `/blog` lo kanipistayi
  (WordPress master), quiz bank → WordPress quiz export.
- `ads.txt`: MilesWeb WordPress root (`public_html/ads.txt`) lo
  AdSense line undali — subdomain ki kuda ade valid (Google policy:
  root domain approve ayithe anni subdomains ki ads automatic).

## Step 5 — Harvest (PYQ scraping) production lo

Harvest **VPS meedaney** run avvali (internet open akkade):

```bash
# Dashboard → Analytics → "🚜 Run #1 Harvest" button, leda CLI:
python3 -m core.pyq harvest --only BANKING   # reasoning focus (230X targets)
```

- 230X **Harvest Targets** prathi exam (APPSC/TSPSC/SSC/BANKING/
  RAILWAY/POLICE) ki reasoning/aptitude + thin sections ni weight ×
  need tho rank chesthundi — eppudu scrape cheyyalo data chepthundi.
- Cron (weekly, VPS): `0 3 * * 1 cd /home/ubuntu/studentup && python3 -m core.pyq harvest`
- ⚠️ Honest rule: bank lo enni real PYQs unte anne cheptam — counts
  eppudu inflate cheyyam.

## Step 6 — Live Exams & Weekly Grand Test

- **Portal Live Exams**: Dashboard → Portal Live Exams → schedule
  (date/time, goal, questions) → students portal lo join → auto
  finalize → top-3 winners (correct > 0) + certificates.
- **Weekly Grand Test**: prathi **Sunday 10:00 AM IST** — 40 Qs,
  60 min, mixed. Bot auto-announce chesthundi.
- **Sectional timing (230X)**: prathi mock/grand result lo section-
  wise time vs budget (60s/question) — real exam lage pressure
  training.

## Step 7 — Materials students ki (BEST ga)

Rendhu channels, rendhu purposes:

1. **📚 Portal Materials Vault** (primary) — Dashboard Analytics lo
   material add cheyyandi (title, file name `data/materials/` lo
   upload chesina PDF, goal, points cost). Student portal lo goal-
   wise materials kanipistayi; points tho unlock → permanent
   download. Free materials cost = 0 pettandi.
2. **🤖 Bot vouchers** (Telegram) — `/redeem` → `mat_` voucher →
   bot file direct ga DM chesthundi (centre collection option kuda).

Materials files VPS `data/materials/` lo pettandi (SCP/upload).
WordPress `/materials` page public catalog/showcase ga vadandi —
actual delivery portal/bot nunchi (points economy kosam).

## Step 8 — Score system (advanced, already built)

- **Score Forecast v2**: subject-weighted (weak section score ni
  drag chesthundi, honest confidence shrink).
- **Sections + Sectional Timing (210X/230X)**: prathi attempt ki
  subject-wise accuracy + time budget.
- **Rank Predictor v2**: goal/district/overall rank + next-rank gap.
- **🏆 Score Intelligence card**: ivi anni okka chota — forecast +
  rank + weak section + next action advice.
- Certificates/Score cards: PNG (English certificates, Telugu names
  with real Noto Sans Telugu fonts).

## Checklist (go-live roju)

- [ ] DNS `quiz` A record → VPS IP, propagate ayinda
- [ ] VPS `.env`: `PUBLIC_BASE_URL=https://quiz.studentup.in`
- [ ] SSL active (https padlock)
- [ ] WordPress menu/hero lo portal link/icon
- [ ] `ads.txt` WordPress root lo unda
- [ ] Dashboard → Health/Go-live checks anni green
- [ ] Test student: register → daily quiz → mock → materials unlock
- [ ] Weekly Grand Test next Sunday schedule confirm
