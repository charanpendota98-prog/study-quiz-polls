# 🚀 GO-LIVE 400X — quiz.studentup.in on the Oracle VM (owner runbook)

Exact order. Approximate total hands-on time: **30–45 min** (plus DNS
propagation). Secrets go **only** into `env/.env` on the VM — never
into chat, git, or screenshots. VM (from earlier sessions):
`80.225.205.135`, user `ubuntu`, app dir `/home/ubuntu/studentup`.

> ⚠️ **Remote rule:** this repo's `main` already contains 360X–390X.
> The VM must run `main` (or any branch deployed deliberately). The
> session branches (`arena/*`) are work-in-progress lanes, not the
> deploy source.

## Step 0 — From your Windows PC (PowerShell)

```powershell
ssh ubuntu@80.225.205.135
```

## Step 1 — Get the code (first time)

```bash
cd /home/ubuntu
git clone https://github.com/charanpendota98-prog/study-quiz-polls.git studentup
cd studentup && git checkout main
```

(Already cloned? `cd /home/ubuntu/studentup && git fetch && git checkout main && git pull`.)

## Step 2 — Secrets: `env/.env` (create once; `chmod 600`)

```bash
mkdir -p env logs data && nano env/.env
```

Minimum for go-live (fill real values on the VM only):

```ini
BOT_TOKEN=
BOT_USERNAME=
ADMIN_ID=
DASHBOARD_PASSWORD=
PORTAL_STATELESS_SECRET=
PUBLIC_BASE_URL=https://quiz.studentup.in
PORTAL_BASE_URL=https://quiz.studentup.in/portal
```

Optional: `GROQ_API_KEY=` (or `GEMINI_API_KEY=` / `OPENAI_API_KEY=` —
Paper Factory 🌐 Translate + LLM features), `WP_USERNAME=` +
`WP_APP_PASSWORD=` + `WP_SITE_URL=` (310X WordPress push,
Application Password only), `WEBHOOK_SECRET=` (form webhook).

```bash
chmod 600 env/.env
```

## Step 3 — Deploy (one command; idempotent)

```bash
bash scripts/deploy.sh --systemd
```

This now (400X): restores the question bank on fresh checkouts
(`bank_restore.py` — step [3b]), runs the finalize validation gate,
and installs **all four** systemd units with paths that match
where each app resolves `env/.env`:

| Service | Process | Surface |
|---|---|---|
| `studentup` | `scripts/watch.py` | 24/7 scheduler (quiz/CA/jobs) |
| `studentup-bot` | `scripts/bot.py` | interactive bot + 📄 390X paper intake |
| `studentup-dashboard` | `scripts/dashboard_server.py` | portal + dashboard, `127.0.0.1:5000` |
| `studentup-webhook` | `scripts/webhook_server.py` | form webhook `:8080` (`WEBHOOK_SECRET` from `.env`) |

Optional WhatsApp bridge (Baileys/Node) when needed:
`sudo systemctl enable --now studentup-bridge` after installing
`deploy/studentup-bridge.service` the same sed way deploy.sh does
(bridge `:3900`, dashboard reaches it via `WA_BRIDGE_URL`).

## Step 4 — Smoke BEFORE DNS (app must answer locally first)

```bash
systemctl is-active studentup studentup-bot studentup-dashboard
curl -s http://127.0.0.1:5000/api/health/golive | head -c 600
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/portal
```

`/api/health/golive` should show no `fail` rows (BOT_TOKEN = ok is
the one that unlocks WebApp login + broadcasts). Dashboard login:
`https://…` comes later; locally just confirm HTTP 200s.

## Step 5 — HTTPS reverse proxy (Caddy, automatic TLS)

```bash
sudo apt-get update && sudo apt-get install -y caddy
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy   # or: enable --now caddy
```

Caddy binds the dashboard to the public name. The app itself stays
on `127.0.0.1:5000` — never expose port 5000 directly.

## Step 6 — DNS (MilesWeb panel) — only now

| Type | Name | Value |
|---|---|---|
| A | `quiz` | `80.225.205.135` |

(optional later, same IP: `exam`, `app`, `portal` — Caddyfile has
the block ready to uncomment.) Main `studentup.in` stays on
WordPress — the quiz subdomain inherits the domain's AdSense
approval; `ads.txt` stays at the **root** domain.

Wait for propagation, then:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://quiz.studentup.in/portal
```

Caddy fetches the Let's Encrypt cert automatically on first hit.

## Step 7 — WordPress icon (studentup.in → portal)

WordPress admin → Custom HTML block (header/menu/home section) →
paste `integrations/wordpress/studentup-portal-icon.html`. Buttons
deep-link `?go=quiz|exams|mocks|papers|hub`.

## Step 8 — Owner verification (5 minutes)

1. Phone: `https://quiz.studentup.in` → register → Daily Quiz opens.
2. Telegram `/start` → bot buttons point at `quiz.studentup.in`.
3. Bot DM: send any official **paper PDF** → draft + ✅/🌐/❌
   buttons (390X). `/papers` lists drafts.
4. Dashboard → Ops/Health → 🚀 Subdomain Go-Live card: no red.
5. Dashboard → PYQ card → 📄 Paper Factory: drafts visible there too.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Service `activating`/crash loop | `journalctl -u studentup-dashboard -n 50` — usually cwd/env; 400X units use absolute ExecStart + `WorkingDirectory=…/scripts` |
| `bot_not_configured` on WebApp login | `BOT_TOKEN` missing in the **dashboard** process env (it's read from `env/.env` at repo root — the unit's cwd fix in 400X covers this) |
| 502 from Caddy | dashboard not on `127.0.0.1:5000` yet — Step 4 first |
| Cert error | DNS not propagated, or port 80 blocked in OCI security list — open 80/443 ingress |
| Links point at wrong host | `PUBLIC_BASE_URL` unset/wrong in `.env` → restart dashboard |
| Bank looks small on fresh VM | run `python3 scripts/bank_restore.py` (deploy.sh [3b] does this; check its log line) |

## Day-2 commands

```bash
cd /home/ubuntu/studentup && git pull && bash scripts/deploy.sh --systemd
python3 scripts/paper_factory.py list        # paper drafts (CLI twin of bot/dashboard)
python3 scripts/bank_health.py               # bank grades/invalid/bias
```

**Never** point DNS at the VM before Step 4 passes, and never paste
real secrets anywhere but the VM's `env/.env`.
