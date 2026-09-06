# 📋 StudentUp Registration — Google Form (one-click build)

You do **not** add questions by hand. The script
[`build_studentup_form.gs`](build_studentup_form.gs) builds the entire form for
you — **59 districts (33 Telangana + 26 Andhra Pradesh)**, validation, and the
thank-you page — in about 60 seconds.

---

## ✅ Build the form in 3 minutes

1. Open **<https://script.google.com>** → click **New project**.
2. Delete the sample code in `Code.gs`, then **paste the whole content of
   [`build_studentup_form.gs`](build_studentup_form.gs)**.
3. (Optional) change `BOT_USERNAME` at the top to your bot.
4. Click the **▶ Run** button. Function must be `buildStudentUpForm`.
   When asked, **Review permissions** → your Google account → **Advanced** →
   **Go to project (unsafe)** → **Allow**. (It's safe — the script is yours.)
5. Open the **Execution log** (bottom). It prints:
   - `LIVE FORM (share this): https://docs.google.com/forms/d/...`
   - `EDIT URL: https://docs.google.com/forms/d/.../edit`
6. Open the **LIVE FORM** URL → click **Send** → copy the link. Put it in
   `env/.env` as `FORM_URL=...` (so the bot's `/regform` command shares it).

> Responses are saved automatically to a linked Google Sheet.

---

## 🔔 Get a Telegram alert on every signup

In the **same** Apps Script project:

1. **New script file** (the `+` next to "Files") → name it e.g. `Notify`.
2. Paste the contents of [`google_apps_script.gs`](google_apps_script.gs),
   fill in `BOT_TOKEN` (BotFather) and `ADMIN_CHAT_ID` (your numeric Telegram id
   — message [@userinfobot](https://t.me/userinfobot)).
3. **Triggers** (clock/⏰ icon, left sidebar) → **Add Trigger**:
   - Function: `onFormSubmit`
   - Event source: **From spreadsheet**
   - Event type: **On form submit**
4. Save / authorize. Run `testNotification` once to confirm the ping arrives.

---

## 📝 What the form collects

**1. Basic details**
- Full name / పేరు *(required)*
- WhatsApp / mobile — **validated to a 10-digit Indian number** *(required)*
- Telegram username or numeric ID — **links quiz points & rank** *(required, validated)*
- Email — collected automatically by Google Forms

**2. Location**
- State: Telangana · Andhra Pradesh · Other
- District — single searchable dropdown with all districts prefixed:
  - `TS · …` = **33 Telangana districts**
  - `AP · …` = **26 Andhra Pradesh districts**
  - plus an "Other / not listed" option for each

**3. Preparation / study**
- Target exam: TSPSC · APPSC · Banking · Railway · Police · Defence · SSC/UPSC · GK
- Education level (10th/Inter → Degree → B.Tech → PG → working professional)
- Target exam year (2026 / 2027 / 2028 / exploring)
- Medium (English / Telugu / Both)
- Study mode (self / coaching / college / online)
- Daily study hours

**4. Updates & feedback**
- WhatsApp / Telegram update consent
- How they found you (for growth tracking)
- Open suggestion box

---

## 🔁 Bring signups into the bot (points + leaderboard)

The Google Sheet → **File → Download → CSV**, then:

```bash
cd scripts
python3 import_members.py ~/Downloads/responses.csv          # preview
python3 import_members.py ~/Downloads/responses.csv --commit  # import
```

The importer:
- normalises districts (`TS · Hyderabad` → **Hyderabad**, state **Telangana**),
  exam labels (`Banking — IBPS / SBI…` → **Banking**), language, phone (strips
  `91` country code / dashes), and reads the auto-collected email;
- creates members who gave a **numeric Telegram id** immediately (+25 points);
- holds **username-only** sign-ups in a pending list — they **auto-link** the
  first time the person taps `/start` in the bot (matched by @username), keeping
  all their form details and points, with no duplicate accounts.

---

## 📣 Where to share the form link
- Pinned post in all 7 channels + the bot `/start` message (`/regform`).
- YouTube description, WhatsApp broadcast, Instagram bio.
- After submit, the form thanks students and sends them straight to the Telegram
  bot to `/register` and play `/quiz`.
