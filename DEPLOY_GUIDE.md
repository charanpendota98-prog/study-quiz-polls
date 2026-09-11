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
SHEET_WEBAPP_URL=https://script.google.com/macros/s/AKfycbzhwPyoWE20NUMFb5ngS0pkHMhg7ahMbLQlJCFkolDJgsdnehnpphmKUkzE_PzWCw5cdg/exec
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
