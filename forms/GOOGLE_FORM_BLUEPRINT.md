# 📋 StudentUp Registration — Google Form Blueprint

Create this once at <https://forms.google.com> (takes ~15 min). It collects
**rich member data** (phone, district, WhatsApp, exam target) that the Telegram
bot can't. The in-bot `/register` still handles **points/leaderboard**; this form
handles **growth + analytics + broadcasts**. They are linked by **Telegram username/id**.

> Tip: responses auto-save to a Google Sheet. That sheet can export a CSV which
> `scripts/import_members.py` loads into the bot's points system.

---

## Form title
**StudentUp — Free Daily Quiz for TS & AP Aspirants | రిజిస్ట్రేషన్**

## Description (paste this)
> Join 50,000+ TS/AP aspirants practising FREE daily quiz polls in English +
> Telugu for TSPSC, APPSC, Banking, Railway, Police, Defence & Current Affairs.
>
> ⤷ TSPSC, APPSC, బ్యాంక్, రైల్వే, పోలీస్, డిఫెన్స్ అభ్యర్థుల కోసం ప్రతిరోజూ
> ఉచిత బైలింగ్వల్ క్విజ్. రిజిస్టర్ చేసుకోండి — మీ లక్ష్యానికి తగ్గ క్విజ్‌లు,
> ఉద్యోగ అప్‌డేట్స్, వీక్లీ లీడర్‌బోర్డ్ మీకు నేరుగా!

---

## Questions (in this exact order)

| # | Question | Type | Options / Notes | Required |
|---|----------|------|-----------------|----------|
| 1 | Full Name / పేరు | Short answer | | ✅ |
| 2 | Mobile number (WhatsApp) / మొబైల్ | Short answer | Validation: 10 digits | ✅ |
| 3 | Telegram username or numeric id / టెలిగ్రామ్ | Short answer | e.g. `@charan` or `123456789` — **this links to quiz points** | ✅ |
| 4 | Email | Short answer | Validation: email | ⬜ |
| 5 | State / రాష్ట్రం | Multiple choice | Telangana · Andhra Pradesh · Other | ✅ |
| 6 | District / జిల్లా | Dropdown | (full list below) | ✅ |
| 7 | Exam target / మీ లక్ష్యం | Dropdown | TSPSC · APPSC · Banking (IBPS/SBI/RRB) · Railway (RRB) · Police (Constable/SI) · Defence (NDA/CDS/Agniveer) · SSC/UPSC · Current Affairs GK | ✅ |
| 8 | Current preparation stage | Multiple choice | Just starting · Foundation · Serious/Revision · Exam soon (1–2 months) | ✅ |
| 9 | Preferred language / మాధ్యమం | Multiple choice | English · Telugu · Both | ✅ |
| 10 | Coaching / self study? | Multiple choice | Self study · Coaching institute · College student | ⬜ |
| 11 | How did you find us? | Dropdown | Friend · YouTube · WhatsApp · Telegram search · Other | ⬜ |

---

## Districts (for question 6 dropdown)

**Telangana:** Hyderabad, Medchal-Malkajgiri, Ranga Reddy, Sangareddy, Vikarabad,
Medak, Siddipet, Nizamabad, Kamareddy, Adilabad, Nirmal, Mancherial, Komaram Bheem,
Karimnagar, Rajanna Sircilla, Jagtial, Peddapalli, Jayashankar Bhupalpally, Warangal
Urban, Warangal Rural, Mahabubabad, Jangaon, Yadadri Bhuvanagiri, Nalgonda,
Suryapet, Khammam, Bhadradri Kothagudem, Mahabubnagar, Nagarkurnool, Wanaparthy,
Jogulamba Gadwal, Narayanpet.

**Andhra Pradesh:** Visakhapatnam, Anakapalli, Alluri Sitharama Raju,
Annamayya, Anantapur, Bapatla, Chittoor, East Godavari, Eluru, Guntur, Kadapa
(YSR), Kakinada, Konaseema, Krishna, Kurnool, Nandyal, Nellore, NTR,
Palnadu, Parvathipuram Manyam, Prakasam, Sri Sathya Sai, Srikakulam,
Tirupati, Visakhapatnam, Vizianagaram, West Godavari.

---

## Settings to enable
- ☑️ **Collect email addresses** (Settings → Responses)
- ☑️ **Limit to 1 response** (requires Google sign-in)
- ☑️ Edit after submit: OFF
- After each submit → "Show link to your Telegram quiz bot" in the confirmation:
  `👉 Open Telegram → @DailyQuizPosterbot → send /register then /quiz`

## Where to share the form
- All 7 channel "pinned" posts + the bot `/start` message (`/regform`).
- YouTube description, WhatsApp broadcast, Instagram bio.

---

## Linking form ↔ bot (automatic)
When a response comes in, **Apps Script** (see `forms/google_apps_script.gs`)
sends you a Telegram alert and can stamp the member into the bot. For points,
users must ALSO tap `/register` inside the bot (Telegram identity is the key).

## Bulk import
Responses → Google Sheet → **File → Download → CSV** → then run:
```
cd scripts && python3 import_members.py ../Downloads/responses.csv
```
That matches Telegram usernames/ids to bot profiles, adds name/district/exam,
and grants the +25 registration bonus so form users appear on the leaderboard.
