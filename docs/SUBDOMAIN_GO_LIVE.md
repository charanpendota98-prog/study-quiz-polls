# 🚀 STUDENTUP.IN Subdomain — Go-Live Guide (160X)

Goal: `studentup.in` (WordPress main site) → **quiz icon** → `quiz.studentup.in`
(StudentUp Portal). Code is already host-agnostic — subdomain root and
`/portal` both open the portal; bot deep-links use `PUBLIC_BASE_URL`.

## Step 1 — DNS (hosting/domain panel, ~5 min)
`studentup.in` is registered/hosted wherever the WordPress site lives
(Hostinger/cPanel/Cloudflare — wherever DNS is managed):

| Type | Name | Value |
|---|---|---|
| A | `quiz` | `<your server IP>` (same server that runs the dashboard) |
| A (optional) | `exam`, `app`, `portal` | same server IP (all open the portal) |

If the dashboard runs behind a platform domain (Railway etc.), use a
**CNAME** instead: `quiz` → `<platform domain>`, and add the custom
domain in that platform.

## Step 2 — SSL (HTTPS is mandatory: login + Telegram WebApp)
- Cloudflare (recommended): DNS proxy ON → SSL/TLS mode **Full**.
- Or on the server: `certbot --nginx -d quiz.studentup.in` (Let's Encrypt).

## Step 3 — Server env (`.env` on the server)
```
PUBLIC_BASE_URL=https://quiz.studentup.in
PORTAL_BASE_URL=https://quiz.studentup.in/portal
BOT_USERNAME=<your bot username, no @>
BOT_TOKEN=<bot token>            # enables WebApp auto-login + broadcasts
```
Restart services:
```
bash scripts/deploy.sh --systemd      # first time
sudo systemctl restart studentup studentup-bot
```
TikTok of truth: `PUBLIC_BASE_URL` wins over the request Host for every
student-facing link (QR codes, bot buttons, share links) — set it once.

## Step 4 — WordPress icon (2 min)
In WordPress: paste `integrations/wordpress/studentup-portal-icon.html`
as a **Custom HTML** block (header/menu/front-page section). Buttons
deep-link into `?go=quiz|exams|mocks|papers|hub`. Details:
`docs/STUDENTUP_PORTAL_LINK.md`. The WordPress repo is NOT modified by
the platform — this is a paste-in snippet only.

## Step 5 — Verify (dashboard → Ops/Health tab)
The **🚀 Subdomain Go-Live** card (also `GET /api/health/golive`) must
show no red items:
- PUBLIC_BASE_URL https ✓ · Portal URL ✓ · BOT_TOKEN configured ✓
- Bot username resolved ✓ · WP snippet ready ✓ · PWA ✓

Then by hand:
1. Open `https://quiz.studentup.in` on a phone → register → Daily Quiz.
2. Telegram: `/start` → bot buttons point at `quiz.studentup.in`.
3. Portal → "🤖 Telegram Bot tho Link Chey" → bot → back → one-tap login.
4. `https://studentup.in` → quiz icon → lands in the portal.
5. AdSense (optional): `ads.txt` must live at `studentup.in` **root**
   (subdomains inherit approval — see AdSense note in the repo history).

## Troubleshooting
| Symptom | Fix |
|---|---|
| Subdomain shows WordPress/default page | DNS points at WP host, not the app server; check A/CNAME target |
| Links inside bot point to wrong host | `PUBLIC_BASE_URL` missing → restart dashboard after setting |
| WebApp login says `bot_not_configured` | `BOT_TOKEN` missing in the **dashboard** env (not only the bot) |
| Certificate error | Cloudflare SSL mode = Flexible with origin HTTPS → set **Full** |
| Icon click opens `/portal` on WP site | Snippet not pasted yet, or old cached page — hard refresh |
