#!/usr/bin/env python3
"""
STUDENTUP — INTERACTIVE BOT (DM + study groups)
Long-polls getUpdates. Member registration, points, levels, ranks, leaderboard.

Commands:
  /start, /help       welcome (EN + Telugu)
  /register           one-time sign-up (name -> state -> district -> qualification -> mobile) = +25 pts
  /hof                monthly Hall of Fame
  /setupsheet /crm /export /syncsheet /broadcast   admin: member database, CSV, Google Sheet, segment DM
  /exam <name>        change exam target   /follow <channels>  which rounds come to your DM
  /invite             referral link (+20 pts per friend)
  /challenge          🥊 Beat yesterday's topper (same 5 Q, +15 pts)
  /squad              👥 friend squad (3–5) — weekly Squad Top-5 in channel
  /battle             ⚔️ SQUAD BATTLE ARENA — live squad-vs-squad rooms (PUBG style)
  /war                ⚔️ District War — daily 9 PM, all-exams common syllabus, fight for your district
  /wallet             👛 points balance + ₹ value at StudentUp centre
  /offers             🏪 మీ జిల్లా shops / coaching / restaurants — points తో discounts
  /join               📢 channels join + ✅ verify → +30 pts each
  /claim CODE         📸 Instagram/YouTube auto-DM code → points (/follow = how)
  /scout              🕵️ మీ జిల్లా shop/coaching ని refer చేయండి → partner అయితే +150
  /jobs               📡 Job Radar — jobs matching YOUR qualification, track, reminders
  /notebook           📓 NotebookLM → official PYQ import (prompt, paste, ✅ import)
  /sheet              📊 Google Sheet status, sync, tabs (staff)
  /msg                📣 Message Studio: personalised DM to segments, preview, schedule (staff)
  /card               📇 my weekly report card (share on WhatsApp status)
  /profile            📚 branch / year (college boards)
  /retest <College> [| 15 | 18:30]   🔁 same students, exam again in DM (staff)
  /roster <College>   📋 college data + CSV (staff)
  /coach              🎯 daily weak-topic coach (07:30) · /coach off
  /mandal <పేరు>      🏠 మీ mandal offers ముందు · /mydistrict <జిల్లా> = జిల్లా మార్చు
  /examdone           📝 exam రాశాక tap → +25 pts + exam-day offers unlock
  /partner apply      🤝 business owners: advertise to students + accept points
  /mystats            🏪 merchants: your vouchers + weekly numbers
  /redeem             🎁 turn points into vouchers (applications, prints, photos)
  /report             📋 your weekly report card
  /district [name]    your district toppers   /districts  TS/AP district leaderboard
  /quiz [channel]     one NON-anonymous PYQ-first practice poll (earns points)
  /coach [channel]    a friendly expert reasoning/aptitude trick (EN+Telugu)
  /review             due spaced-repetition questions (missed ones come back)
  /badges             your earned achievement badges
  /stats /profile     your points, level, rank, accuracy, streak
  /rank /leaderboard  points-based top players
  /hq                 🏢 owner dashboard (staff) · /college = college clubs
  /college add        🏫 phone-friendly college event wizard (name → district buttons)
  /campus             🎓 college event / college-vs-college war (organisers)
  /cup                🏆 College Cup — cricket-style knockout (3–16 colleges, parallel rounds)
  /campuswar          🎓 students: request your own college war (staff approve)
  /warrank            🎖 మీ War rank (🪖→🐉) + all-time war board
  /top tspsc          📊 exam-wise Top 10 (today) · /top tspsc week · /top tspsc districts
  /levels             points & level rules
Group quizzes via this bot are the ones that earn points (channel auto-polls
are anonymous by Telegram design); add the bot to your study group to compete.

Usage:
  python3 bot.py           # production long-poll loop
  python3 bot.py --dry
"""
from datetime import datetime
import re
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import config
from core.telegram import Telegram, TelegramError
from core.question_bank import Bank
from core.content import build_question_text, build_options, build_explanation
from core.members import Members, EXAM_TARGETS, LANGUAGES, level_for

WELCOME = (
    "👋 *StudentUp* — TS & AP aspirants కోసం India's most advanced quiz arena\n"
    "(TSPSC · APPSC · SSC · Banking · Railway · Police · Defence · Current Affairs)\n\n"
    "🎯 *రోజూ*\n"
    "• 7:30 AM & 7:30 PM — exam-hall paced rounds in the channel → Top-10 పేరు+జిల్లా\n"
    "• 1:00 PM — 🥊 Beat the Topper (నిన్నటి topper వి 5 Q)\n"
    "• 9:00 PM — ⚔️ *District War* — మీ జిల్లా కోసం, అన్ని exams common syllabus\n\n"
    "👥 *Friends తో*\n"
    "• /squad — 2–5 friends team (కొత్త group అవసరం లేదు — ఇక్కడే ఆడతారు)\n"
    "• /battle — Squad vs Squad live rooms (PUBG style) · ELO tiers 🥉→💎\n\n"
    "🏆 *వారం / నెల*: Sunday Grand Test · Monthly Mega · District League · Hall of Fame\n"
    "👛 *Points = real value*: /wallet → application filing discounts + study materials @ StudentUp centre\n"
    "📋 /report · 🔁 /review · /me · /invite (+20 per friend) · /help\n\n"
    "⤷ ఒక్కసారి register — ఆ తర్వాత అన్నీ automatic. Let's go! 🔥"
)

FIRST_TIME_ASK = (
    "👋 First time here? One-time registration (30 seconds) — asked only once, never again.\n"
    "⤷ మొదటిసారా? ఒక్కసారి రిజిస్టర్ చేసుకోండి — మళ్లీ అడగము.\n\n"
    "🏆 Registered players' NAME + DISTRICT appear in the channel Top-10 after every round!\n"
    "⤷ ప్రతి రౌండ్ తర్వాత Top-10 లో మీ పేరు + జిల్లా ఛానల్‌లో పోస్ట్ అవుతుంది!\n\n"
    "📝 Step 1 of 5 — What is your full name?\n⤷ మీ పూర్తి పేరు పంపండి:"
)

SHEET_SETUP = (
    "📊 Google Sheet CRM — status: {status}\n"
    "Sheet: {view}\n\n"
    "One-time bridge setup (3 min, no API keys):\n"
    "1️⃣ Open the Sheet → Extensions → Apps Script\n"
    "2️⃣ Delete the sample code, paste docs/sheet_webapp.gs from the repo → Save\n"
    "3️⃣ Change SECRET = \"...\" to a long random string\n"
    "4️⃣ Run ▶ setupSheet once (creates 📊 Dashboard, members, rounds, daily, log tabs + nightly snapshot)\n"
    "5️⃣ Deploy → New deployment → Web app → Execute as: Me · Access: Anyone → Deploy → Authorize\n"
    "6️⃣ Copy the URL ending in /exec → .env:\n"
    "   SHEET_WEBAPP_URL=<that url>\n   SHEET_SECRET=<same secret>\n"
    "7️⃣ Restart bot → /setupsheet shows ✅ connected → /syncsheet pushes everyone.\n"
    "🔁 After editing the script later: Deploy → Manage deployments → ✏ → New version.\n"
    "⤷ Sheet link మాత్రమే సరిపోదు — Google rule ప్రకారం write చేయాలంటే ఈ web-app URL కావాలి."
)

LOCKED_FIRST = (
    "🔒 +{pts} points earned — but LOCKED.\n"
    "⤷ మీరు {pts} పాయింట్లు సంపాదించారు — కానీ లాక్ అయ్యాయి.\n\n"
    "Register once (30 sec) to UNLOCK them and enter the Top-10 with your name + district 🏆\n"
    "⤷ ఒక్కసారి రిజిస్టర్ చేస్తే అన్‌లాక్ + Top-10 లో మీ పేరు, జిల్లా!\n\n"
    "📝 Step 1 of 5 — What is your full name?\n⤷ మీ పూర్తి పేరు పంపండి:"
)
LOCKED_NUDGE = (
    "🔒 {pts} points waiting for you. Finish registration to unlock — just send your name.\n"
    "⤷ {pts} పాయింట్లు లాక్‌లో ఉన్నాయి — పేరు పంపి రిజిస్ట్రేషన్ పూర్తి చేయండి."
)

COLLEGE_WIZ_NAME = (
    "🏫 New college event — Step 1/3 (ఇకపై | కొట్టాల్సిన అవసరం లేదు)\n"
    "College పేరు పంపండి / Send the college name (type only this one thing):"
)

HELP = (
    "ℹ️ *StudentUp — ఎలా పనిచేస్తుంది*\n"
    "1️⃣ ఒక్కసారి register (పేరు → జిల్లా → exam → mobile) +25 pts. మళ్ళీ అడగము.\n"
    "2️⃣ Channel rounds 7:30 AM / 7:30 PM — అవే ప్రశ్నలు మీకు ఇక్కడ DM లో వస్తాయి (పేరుతో score). "
    "✅ +10 · daily first +5 · streak 3/7/15/30/100 🔥 · 🛡 shield ప్రతి 7 రోజులకి.\n"
    "3️⃣ 1 PM 🥊 /challenge — నిన్నటి topper వి 5 Q · 9 PM ⚔️ /war — District War (అన్ని exams common syllabus).\n"
    "4️⃣ Friends: /squad (2–5, కొత్త group అవసరం లేదు) → /battle — squad vs squad live rooms, ELO tiers.\n"
    "5️⃣ ఆదివారం 9 AM 🏟 Grand Test · నెల చివరి ఆదివారం 🏆 Mega · సోమవారం League/Squad/Arena boards.\n"
    "6️⃣ /wallet — points = application filing discounts + study materials @ StudentUp centre.\n"
    "7️⃣ /report weekly report card · /review missed Qs · /me · /rank · /invite (+20 per friend).\n"
    "ప్రశ్నలు ఎప్పుడూ repeat అవ్వవు · real exam-paper sources · Telugu + English.\n"
)

LEVELS_TEXT = (
    "🏆 *Points & Levels*\n"
    "• +25 — completing /register\n"
    "• +10 — every correct answer\n"
    "• +5 — first activity each day\n"
    "• Streak bonus — 3d:+20, 7d:+75, 15d:+200, 30d:+500, 100d:+2000 🔥\n\n"
    "Levels by total points:\n"
    "🆕 Newcomer → 🥉 Bronze (100) → 🥈 Silver (300) → 🥇 Gold (700) → "
    "💎 Platinum (1500) → 👑 Champion (3000)\n\n"
    "⤷ రోజూ ఆడితే స్ట్రీక్ బోనస్‌లతో వేగంగా లెవల్ పెరుగుతారు!"
)


class Bot:
    def __init__(self, dry=False):
        self.tg = Telegram(dry=dry)
        self.bank = Bank()
        self.members = Members()
        self.dry = dry
        self._poll_q = {}
        self._load_polls()

    def _name(self, user):
        return (user.get("username") or
                " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or
                str(user.get("id")))

    # ------------------------------------------------------------ quiz
    def send_quiz_to(self, chat_id, channel=None, uid=None, adaptive=True):
        ch = channel if channel in config.PUBLIC_CHANNELS else None
        # Adaptive personalization in private chats (member has a profile).
        weak = review = None
        if adaptive and uid:
            weak = self.members.weak_topics(uid)
            review = [r["qid"] for r in self.members.due_reviews(uid)]
        if ch is None:
            # default channel = member's exam target mapped to a channel
            prof = self.members.profile(uid) if uid else None
            exam = (prof or {}).get("exam", "")
            ch = self._exam_to_channel(exam)
        q = None
        tag = ""
        if adaptive and uid and (review or weak):
            q = self.bank.pick_adaptive(ch, weak_topics=weak, review_qids=review)
            is_review = review and q and q["id"] in review
            tag = "🔁 Revision" if is_review else ("📌 Focus (weak topic)" if weak else "📝 Practice")
        if q is None:
            qs = self.bank.pick(ch, 1)
            q = qs[0] if qs else None
        if not q:
            # 📭 never stay silent: tell the player + make it visible for staff
            try:
                self.tg.send_message(chat_id,
                    "📭 ఇప్పుడు ఈ కేటగిరీలో కొత్త ప్రశ్నలు లేవు (అన్నీ వాడేశాం) — కొత్తవి వచ్చాక మళ్ళీ /quiz ట్రై చేయండి.\n"
                    "⤷ No fresh questions in stock right now — staff has been notified. Try /quiz again soon!\n"
                    "(Staff: collector run చెయ్యండి / VERIFY_STRICT చూడండి — /hq లో స్టాక్ కనిపిస్తుంది)")
            except TelegramError:
                pass
            for aid in self._staff_ids():
                try:
                    self.tg.send_message(aid, f"⚠️ /quiz empty stock alert — channel {ch or 'default'}, user {uid}. "
                                              "Run the collector or check verification (see /hq).")
                except TelegramError:
                    pass
            return
        if not tag:
            tag = "📜 PYQ" if q.get("source") == "pyq" else "📝 Practice"
        cfg = config.CHANNELS[ch]
        tf = bool(getattr(config, "TELUGU_FIRST", True))
        text = f"{tag} {build_question_text(q, cfg, telugu_first=tf)}"
        opts = build_options(q, telugu_first=tf)
        expl = build_explanation(q, telugu_first=tf)
        # DM/group quizzes ALWAYS use instant correct/wrong (points need it)
        payload = {
            "chat_id": chat_id, "question": text[:300],
            "options": [{"text": o} for o in opts], "type": "quiz",
            "is_anonymous": False,               # track members for points
            "allows_multiple_answers": False,
            "correct_option_id": q["answer_index"],
        }
        if getattr(config, "POLL_AUTO_CLOSE", False):
            payload["open_period"] = getattr(config, "QUIZ_OPEN_PERIOD", 300)
        if expl.strip():
            payload["explanation"] = expl[:config.TG_POLL_EXPLANATION_MAX]
        res = self.tg._call("sendPoll", payload)
        poll = res.get("result", {}).get("poll") or {}
        if poll.get("id"):
            # channel, qid, answer_index, topic
            self._poll_q[poll["id"]] = (ch, q["id"], q["answer_index"],
                                        q.get("topic", ""))
            self._save_polls()

    def _step_buttons(self, uid, status):
        """Inline keyboard for the current registration step (None for text steps)."""
        if status == "ask_state":
            return [[("🟪 Telangana / తెలంగాణ", "state:TS")],
                    [("🟦 Andhra Pradesh / ఆంధ్రప్రదేశ్", "state:AP")],
                    [("🌐 Other state", "state:OTHER")]]
        if status == "ask_district":
            from core import districts as D
            st = self.members.pending_step(uid) or {}
            rows, row = [], []
            for en, te in D.sorted_districts(st.get("state_code", "")):
                label = en if len(en) <= 22 else en[:21] + "…"
                row.append((label, f"dist:{en}"[:64]))
                if len(row) == 2:
                    rows.append(row); row = []
            if row:
                rows.append(row)
            return rows or None
        if status == "ask_qualification":
            return self._qual_buttons()
        return None

    @staticmethod
    def _qual_buttons():
        from core.members import QUALIFICATIONS
        rows, row = [], []
        for c, en, te in QUALIFICATIONS:
            row.append((f"{en}", f"qual:{c}"))
            if len(row) == 2:
                rows.append(row); row = []
        if row:
            rows.append(row)
        return rows

    def _finish_college_wizard(self, chat_id, uid, district):
        """Wizard step 3 done → create the event(s).

        1 college → quick event · 2 colleges → college-vs-college war ·
        3+ colleges → ask: war (one shot) or 🏆 cricket-style knockout CUP.
        """
        from core import campus
        wz = campus.wiz_get(uid) or {}
        colleges = wz.get("colleges") or []
        first = (wz.get("name") or "").strip()
        if first and first not in colleges:
            colleges.insert(0, first)
        colleges = [c.strip()[:40] for c in colleges if c and c.strip()]
        if not colleges:
            colleges = ["General"]
        if len(colleges) >= 3:
            campus.wiz_set(uid, district=district, step="mode")
            self.tg.send_message(chat_id,
                f"🏫 {len(colleges)} colleges · {district}\n\n"
                "ఎలా ఆడించాలి? / How should they play?\n"
                "🏆 CUP = cricket-style knockout (rounds → semis → FINAL, matches parallel)\n"
                "🤝 WAR = అందరూ ఒకేసారి ఒకటే exam (college-vs-college)",
                buttons=[[("🏆 KNOCKOUT CUP (smart)", "cwmode:cup")],
                         [("🤝 Single WAR (one exam)", "cwmode:war")]])
            return
        campus.wiz_clear(uid)
        try:
            if len(colleges) == 1:
                code = campus.quick_event(colleges[0], district, created_by=uid)
            else:
                code = campus.new_event(f"{district} College War ⚔️", district, colleges,
                                        created_by=uid)
        except Exception as ex:
            self.tg.send_message(chat_id, f"❌ Event create fail: {ex}")
            return
        self.tg.send_message(chat_id, f"✅ {code} ready — {', '.join(colleges)} · {district} ✅\n"
                                      "Students కి ఈ link పంపండి / తరగతి గదిలో చూపించండి 👇")
        self.tg.send_message(chat_id, campus.poster_text(code))
        self.tg.send_message(chat_id, campus.panel_text(self.members, code),
                             buttons=campus.panel_buttons(code))

    def _refresh_panel(self, cq, chat_id, code):
        """Smart admin panel: update the SAME message in place instead of
        spamming a new one after every button tap (edit → fallback to send)."""
        from core import campus
        txt = campus.panel_text(self.members, code)
        btns = campus.panel_buttons(code)
        mid = (cq.get("message") or {}).get("message_id")
        if mid:
            try:
                payload = {"chat_id": chat_id, "message_id": mid,
                           "text": txt[:config.TG_MSG_MAX]}
                if btns:
                    payload["reply_markup"] = {"inline_keyboard": [
                        [({"text": lab, "url": str(cb)[4:]} if str(cb).startswith("url:") else
                          {"text": lab, "callback_data": str(cb)[:64]}) for lab, cb in row]
                        for row in btns]}
                self.tg._call("editMessageText", payload)
                return
            except Exception:
                pass
        self.tg.send_message(chat_id, txt, buttons=btns)

    def handle_callback(self, cq):
        """Inline-button taps (qualification step, future menus)."""
        uid = cq.get("from", {}).get("id")
        data = cq.get("data") or ""
        chat_id = str(cq.get("message", {}).get("chat", {}).get("id") or uid)
        try:
            self.tg.answer_callback(cq.get("id", ""))
        except TelegramError:
            pass
        kind, _, value = data.partition(":")
        if kind == "challenge" and uid:
            self._start_challenge(uid, chat_id)
            return
        if kind == "war" and uid:
            from core import districtwar
            if not self.members.is_registered(uid):
                self.members.start_registration(uid, username="")
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            ok, txt = districtwar.lobby_join(self.members, uid, via_squad=(value == "squad"))
            self.tg.send_message(chat_id, txt)
            if ok:
                try:   # button disappears: replace the alert message text
                    mid = cq.get("message", {}).get("message_id")
                    if mid:
                        self.tg._call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": mid,
                                                                  "reply_markup": {"inline_keyboard": []}})
                except Exception:
                    pass
            return
        if kind == "redeem" and uid:
            from core import rewards
            ok, txt, admin = rewards.redeem(self.members, uid, value)
            self.tg.send_message(chat_id, txt, parse_mode="Markdown" if ok else "")
            if ok and value.startswith("mat_"):
                code = [l for l in txt.splitlines() if l.startswith("Code:")][0].split("`")[1]
                path, note = rewards.deliver_material(self.members, uid, code)
                if path:
                    try:
                        self.tg.send_document(chat_id, path.name, path.read_bytes(), caption=note[:900])
                    except TelegramError as e:
                        self.tg.send_message(chat_id, "📚 File పంపడంలో సమస్య — voucher active, centre లో తీసుకోండి.")
                elif note:
                    self.tg.send_message(chat_id, note)
            if ok and admin:
                for aid in self._staff_ids():
                    try:
                        self.tg.send_message(aid, admin)
                    except TelegramError:
                        pass
            return
        if kind == "poffer" and uid:
            from core import partners, rewards
            ok, txt, merch = partners.redeem(self.members, uid, value, rewards)
            self.tg.send_message(chat_id, txt, parse_mode="Markdown" if ok else "")
            if ok and merch:
                uids, mtxt = merch
                for mu in list(uids) + list(self._staff_ids()):
                    try:
                        self.tg.send_message(mu, mtxt)
                    except TelegramError:
                        pass
            return
        if kind == "shot" and uid and str(uid) in self._staff_ids():
            from core import social
            tu, plat, ok = (value.split(":") + ["ig", "0"])[:3]
            social.review_screenshot(self.members, tu, plat, ok == "1")
            try:
                self.tg.send_message(tu, f"✅ Follow verified → +{social.SCREENSHOT_PTS} pts! /offers చూడండి" if ok == "1"
                                     else "❌ Screenshot లో follow కనబడలేదు — follow అయ్యి మళ్ళీ పంపండి.")
            except TelegramError:
                pass
            try:
                self.tg.answer_callback(cq.get("id", ""), "done")
            except TelegramError:
                pass
            return
        if kind == "hq" and uid and str(uid) in self._staff_ids():
            from core import hq, campus
            if value == "campus":
                self.tg.send_message(chat_id, campus.panel_text(self.members), buttons=campus.panel_buttons())
            elif value == "partners":
                from core import partners
                self.tg.send_message(chat_id, partners.list_partners())
            elif value == "colleges":
                self.tg.send_message(chat_id, hq.club_list_text(self.members), buttons=hq.club_buttons(self.members))
            elif value == "digest":
                self.tg.send_message(chat_id, self._ad_now())
            elif value == "nudge":
                from core.engine import Engine
                self.tg.send_message(chat_id, f"🔔 nudged {Engine(dry=self.dry).join_nudge()}")
            elif value == "export":
                from core import crm
                self.tg.send_document(chat_id, "members.csv", crm.export_csv(self.members.members), caption="All members")
            elif value == "sheet":
                from core import crm
                self.tg.send_message(chat_id, crm.sheet_status_text(self.members.members), buttons=crm.sheet_buttons())
            elif value == "war":
                from core import districtwar
                self.tg.send_message(chat_id, districtwar.owner_status(self.members),
                                     buttons=[[("⚔️ Launch war now (5 min)", "cmd:war now"), ("🔄 Status", "cmd:war status")]])
            else:
                txt, _, _ = hq.render(self.members, self.bank)
                self.tg.send_message(chat_id, txt, buttons=hq.buttons())
            try:
                self.tg.answer_callback(cq.get("id", ""), "ok")
            except TelegramError:
                pass
            return
        if kind == "club" and uid and str(uid) in self._staff_ids():
            from core import hq, campus
            act, _, college = value.partition(":")
            if act == "show":
                txt, btns = hq.club_card(self.members, college)
                self.tg.send_message(chat_id, txt, buttons=btns)
            elif act == "rerun":
                c = hq.clubs(self.members).get(college, {})
                code = campus.quick_event(college, c.get("district", ""), created_by=uid)
                self.tg.send_message(chat_id, f"✅ {code} ready for {college}"); self.tg.send_message(chat_id, campus.poster_text(code))
                self.tg.send_message(chat_id, campus.panel_text(self.members, code), buttons=campus.panel_buttons(code))
            elif act == "retest":
                from core import roster
                code, n = roster.schedule_retest(self.members, college, created_by=uid)
                if code:
                    pinged = roster.ping_retest(self.tg, code)
                    self.tg.send_message(chat_id, f"🧪 {code}: {n} students enrolled, {pinged} invited · auto-start in 10 min", buttons=campus.panel_buttons(code))
                else:
                    self.tg.send_message(chat_id, "❌ no registered students for this college")
            elif act == "roster":
                from core import roster
                self.tg.send_message(chat_id, roster.roster_text(self.members, college))
                try:
                    self.tg.send_document(chat_id, f"roster_{college[:20]}.csv", roster.roster_csv(self.members, college).encode("utf-8"), caption="Roster + all test attempts")
                except Exception:
                    pass
            elif act == "progress":
                from core import roster
                self.tg.send_message(chat_id, roster.progress_report(self.members, college) or "No tests yet for this college.")
            elif act == "msg":
                if not hasattr(self, "_club_msg"):
                    self._club_msg = {}
                self._club_msg[str(uid)] = college
                self.tg.send_message(chat_id, f"✍️ {college} members అందరికీ పంపే message type చేయండి (next message):")
            elif act == "lead":
                c = hq.clubs(self.members).get(college, {})
                if c.get("top", ("", -1))[0]:
                    hq.set_leader(college, c["top"][0], self.members)
                    try:
                        self.tg.send_message(c["top"][0], f"👑 Congratulations! మీరు {college} StudentUp Ambassador (+50 pts).\n"
                                                          "మీ పని: friends ని /invite, college events కి help, రోజూ ఆడటం. నెలకి rewards 🎁")
                    except TelegramError:
                        pass
                    self.tg.send_message(chat_id, "👑 leader set + notified")
            elif act == "board":
                b = hq.club_board(self.members, college)
                for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
                    try:
                        self.tg.send_message(config.channel_chat_id(ch), b)
                    except TelegramError:
                        pass
                self.tg.send_message(chat_id, "🏆 posted")
            try:
                self.tg.answer_callback(cq.get("id", ""), "ok")
            except TelegramError:
                pass
            return
        if kind == "cmd" and uid:
            # button from a campaign message → run that command for the student
            self.handle_message({"chat": {"id": int(chat_id)}, "from": {"id": uid, "first_name": ""}, "text": value if value.startswith("/") else "/" + value})
            return
        if kind == "msg" and uid and str(uid) in self._staff_ids():
            from core import messenger as MS
            act, _, v = value.partition(":")
            if act == "home":
                MS.clear_draft(uid)
                self.tg.send_message(chat_id, "📣 MESSAGE STUDIO — ఎవరికి పంపాలి?", buttons=MS.audience_buttons())
            elif act == "aud":
                spec = next((a for a in MS.AUDIENCES if a[0] == v), None)
                if spec and spec[2] is None:
                    self.tg.send_message(chat_id, f"ఎంచుకోండి ({v}):", buttons=MS.pick_buttons(self.members, v))
                elif spec:
                    MS.start_draft(uid, spec[2])
                    n = len(MS.select(self.members, spec[2]))
                    self.tg.send_message(chat_id, f"✅ Audience: {spec[1]} — {n} students\n\n✍️ ఇప్పుడు మీ message type చేయండి (text లేదా photo+caption).\n"
                                                  "Placeholders: {name} {district} {points} · Button line: [Open quiz](/quiz)\nTemplates: /msg templates")
            elif act == "set":
                k, _, val = v.partition("=")
                MS.start_draft(uid, {k: val})
                n = len(MS.select(self.members, {k: val}))
                self.tg.send_message(chat_id, f"✅ Audience: {MS.seg_label({k: val})} — {n} students\n\n✍️ ఇప్పుడు మీ message type చేయండి.")
            elif act == "send":
                when = MS.when_for(v)
                job = MS.schedule(uid, when)
                if not job:
                    self.tg.send_message(chat_id, "❌ draft లేదు — /msg"); return
                if v == "now" and not MS.in_quiet():
                    rep = MS.run_job(self.tg, self.members, job)
                    self.tg.send_message(chat_id, MS.report_text(job))
                else:
                    self.tg.send_message(chat_id, f"⏰ Scheduled: {when.strftime('%d %b %I:%M %p')} · {MS.seg_label(job['seg'])}\nCancel: /msg cancel {job['id']}")
            elif act == "edit":
                self.tg.send_message(chat_id, "✏️ కొత్త text పంపండి (audience అలాగే ఉంటుంది):")
            elif act == "cancel":
                MS.clear_draft(uid); self.tg.send_message(chat_id, "❌ Cancelled.")
            elif act == "history":
                self.tg.send_message(chat_id, MS.history_text())
            elif act == "templates":
                self.tg.send_message(chat_id, MS.templates_text())
            return
        if kind == "sheet" and uid and str(uid) in self._staff_ids():
            from core import crm
            if value == "sync":
                n = self.members.sync_sheet_all(); self.tg.send_message(chat_id, f"🔁 pushed {n} members" if crm.sheet_enabled() else "⚠️ SHEET_WEBAPP_URL not set")
            elif value == "flush":
                self.tg.send_message(chat_id, f"📦 flushed {crm.flush_queue()} queued pushes · {crm.queue_size()} left")
            elif value == "colleges":
                self.tg.send_message(chat_id, f"🏫 colleges tab: {crm.push_colleges(self.members.members)} rows")
            elif value == "partners":
                self.tg.send_message(chat_id, f"🏪 partners tab: {crm.push_partners()} rows")
            elif value == "daily":
                self.tg.send_message(chat_id, "📅 daily snapshot " + ("✅" if crm.push_daily(self.members.members) else "❌ (queued)"))
            elif value == "csv":
                self.tg.send_document(chat_id, f"studentup_members_{datetime.now(config.IST):%Y%m%d}.csv", crm.export_csv(self.members.members), caption="All registered members")
            else:
                self.tg.send_message(chat_id, crm.sheet_status_text(self.members.members), buttons=crm.sheet_buttons())
            return
        if kind == "nb" and uid and str(uid) in self._staff_ids():
            from core import notebook as NB
            act, _, arg = value.partition(":")
            if act == "p":
                self.tg.send_message(chat_id, NB.prompt_for(arg))
            elif act == "commit":
                n, txt = NB.commit(uid, by=str(uid))
                self.tg.send_message(chat_id, txt)
                if n:
                    try:
                        self.bank = Bank()
                    except Exception:
                        pass
            elif act == "discard":
                NB.clear_draft(uid); self.tg.send_message(chat_id, "🗑 discarded")
            elif act == "status":
                self.tg.send_message(chat_id, NB.status_text())
            else:
                self.tg.send_message(chat_id, NB.howto_text(), buttons=NB.buttons())
            return
        if kind == "gate" and uid:
            if self.members.is_registered(uid):
                self.tg.send_message(chat_id, "✅ మీరు already registered! /quiz ఆడండి · /wallet చూడండి")
            else:
                if not self.members.pending_step(uid):
                    self.members.start_registration(uid, username="")
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
            return
        if kind == "jr" and uid:
            from core import jobradar
            if not self.members.is_registered(uid):
                self.members.start_registration(uid, username="")
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            act, _, jid = value.partition(":")
            if act == "t":
                self.tg.send_message(chat_id, jobradar.track(uid, jid), buttons=[[("📋 Checklist", f"jr:c:{jid}"), ("✅ I applied", f"jr:a:{jid}")]])
            elif act == "u":
                self.tg.send_message(chat_id, jobradar.untrack(uid, jid))
            elif act == "a":
                self.tg.send_message(chat_id, jobradar.applied(self.members, uid, jid))
            elif act == "c":
                self.tg.send_message(chat_id, jobradar.checklist_text(jid))
            elif act == "mine":
                self.tg.send_message(chat_id, jobradar.mine_text(uid))
            else:
                self.tg.send_message(chat_id, jobradar.radar_text(self.members, uid), buttons=jobradar.radar_buttons(self.members, uid))
            return
        if kind == "rp" and uid:
            from core import roster
            k, _, v = value.partition(":")
            txt, b = roster.handle_callback(self.members, uid, k, v)
            self.tg.send_message(chat_id, txt, buttons=b)
            return
        if kind == "cupc" and uid and str(uid) in self._staff_ids():
            from core import cup as C
            act, _, code = value.partition(":")
            if act == "bracket":
                txt = C.render_cup(code)
                edited = False
                mid = (cq.get("message") or {}).get("message_id")
                if mid:      # refresh the same bracket message in place
                    try:
                        self.tg._call("editMessageText", {
                            "chat_id": chat_id, "message_id": mid, "text": txt[:config.TG_MSG_MAX],
                            "reply_markup": {"inline_keyboard": [
                                [{"text": lab, "callback_data": cb} for lab, cb in row]
                                for row in (C.cup_buttons(code) or [])]}})
                        edited = True
                    except Exception:
                        pass
                if not edited:
                    self.tg.send_message(chat_id, txt, buttons=C.cup_buttons(code))
            elif act == "panel":
                from core import campus
                self.tg.send_message(chat_id, campus.panel_text(self.members),
                                     buttons=campus.panel_buttons())
            try:
                self.tg.answer_callback(cq.get("id", ""), "ok")
            except TelegramError:
                pass
            return
        if kind == "cwr" and uid and str(uid) in self._staff_ids():
            from core import campus
            rid, _, act = value.partition(":")
            info = campus.request_act(rid, approve=(act == "1"))
            if info:
                r = info["request"]
                if info.get("approved"):
                    code = info.get("code")
                    self.tg.send_message(chat_id, f"✅ {rid} approved → {code} created · organiser tg {r.get('uid')}")
                    try:
                        self.tg.send_message(r["uid"],
                            f"🎉 మీ '{r.get('college', '')}' college war APPROVE అయింది! Event: {code}\n"
                            "ఈ poster + link classmates కి పంపండి — వాళ్ళు ఓపెన్ చేయగానే join అవుతారు.\n"
                            "అందరూ join అయ్యాక కింద 🚀 START exam బటన్ నొక్కండి — ప్రశ్నలు అందరికీ ఒకేసారి వస్తాయి 👇")
                        self.tg.send_message(r["uid"], campus.poster_text(code))
                        self.tg.send_message(r["uid"], campus.panel_text(self.members, code),
                                             buttons=campus.panel_buttons(code))
                    except TelegramError:
                        pass
                else:
                    self.tg.send_message(chat_id, f"🚫 {rid} denied")
                    try:
                        self.tg.send_message(r["uid"], "❌ మీ college war request ఇప్పుదుకి approve కాలేదు — వివరాలకి StudentUp staff ని అడగండి.")
                    except TelegramError:
                        pass
            else:
                self.tg.send_message(chat_id, "⏳ ఈ request ఇప్పటికే పూర్తయింది లేదా దొరకలేదు.")
            try:
                self.tg.answer_callback(cq.get("id", ""), "ok")
            except TelegramError:
                pass
            return
        if kind in ("cwstate", "cw", "cwmore", "cwmode") and uid and str(uid) in self._staff_ids():
            from core import campus
            wz = campus.wiz_get(uid)
            if not wz:
                return
            if kind == "cwmore" and wz.get("step") == "more":
                if value == "again":
                    campus.wiz_set(uid, step="name2")
                    self.tg.send_message(chat_id, "🏫 Next college పేరు పంపండి / Send the next college name:")
                else:  # done → pick state
                    campus.wiz_set(uid, step="state")
                    self.tg.send_message(chat_id,
                        "🗺 ఈ colleges ఏ జిల్లాలో? / Which district?\nTap a button ⬇️",
                        buttons=[[("🟪 Telangana / తెలంగాణ", "cwstate:TS"),
                                  ("🟦 Andhra Pradesh / ఆంధ్రప్రదేశ్", "cwstate:AP")],
                                 [("🌐 Other / typed district", "cwstate:OTHER")]])
                try:
                    self.tg.answer_callback(cq.get("id", ""), "ok")
                except TelegramError:
                    pass
                return
            if kind == "cwmode" and wz.get("step") == "mode":
                from core import cup as C
                colleges = wz.get("colleges") or []
                district = wz.get("district") or ""
                campus.wiz_clear(uid)
                if value == "cup":
                    code, msg = C.cup_new(district, colleges, name=f"{district} College Cup",
                                          created_by=uid)
                    self.tg.send_message(chat_id, msg)
                    if code:
                        self.tg.send_message(chat_id, C.render_cup(code), buttons=C.cup_buttons(code))
                else:
                    try:
                        code = campus.new_event(f"{district} College War ⚔️", district, colleges,
                                                created_by=uid)
                        self.tg.send_message(chat_id, f"✅ {code} ready — {len(colleges)} colleges war ⚔️")
                        self.tg.send_message(chat_id, campus.links_text(code))
                        self.tg.send_message(chat_id, campus.panel_text(self.members, code),
                                             buttons=campus.panel_buttons(code))
                    except Exception as ex:
                        self.tg.send_message(chat_id, f"❌ {ex}")
                try:
                    self.tg.answer_callback(cq.get("id", ""), "ok")
                except TelegramError:
                    pass
                return
            if wz.get("step") not in ("state", "district"):
                return
            if kind == "cwstate":
                if value == "OTHER":
                    campus.wiz_set(uid, state_code="OTHER", step="district_text")
                    self.tg.send_message(chat_id, "📍 జిల్లా పేరు టైప్ చేయండి / Type the district name:")
                else:
                    from core import districts as D
                    campus.wiz_set(uid, state_code=value, step="district")
                    rows, row = [], []
                    for en, _te in D.sorted_districts(value):
                        label = en if len(en) <= 28 else en[:27] + "…"
                        row.append((label, f"cw:{en}"[:64]))
                        if len(row) == 2:
                            rows.append(row); row = []
                    if row:
                        rows.append(row)
                    st = D.STATES.get(value, (value, value))
                    self.tg.send_message(chat_id,
                        f"✅ {st[0]}\n\n📍 Step 3/3 — ఏ జిల్లా? / Which district?\nTap your district below ⬇️",
                        buttons=rows)
            else:
                self._finish_college_wizard(chat_id, uid, value)
            try:
                self.tg.answer_callback(cq.get("id", ""), "ok")
            except TelegramError:
                pass
            return
        if kind == "cp" and uid:
            from core import campus
            act, _, code = value.partition(":")
            code = None if code == "-" else code
            # staff always; a student organiser may control ONLY their own event
            is_staff = str(uid) in self._staff_ids()
            if not is_staff:
                ev = campus._load()["events"].get(code) if code else None
                organiser = bool(ev and str(ev.get("by")) == str(uid))
                if not organiser or act == "new":
                    try:
                        self.tg.answer_callback(cq.get("id", ""), "staff only")
                    except TelegramError:
                        pass
                    return
            if act == "new":
                campus.wiz_start(uid)
                self.tg.send_message(chat_id, COLLEGE_WIZ_NAME)
                try:
                    self.tg.answer_callback(cq.get("id", ""), "ok")
                except TelegramError:
                    pass
                return
            if act == "start" and code:
                ok, info = campus.start(self.bank, self.members, self.tg, code)
                self.tg.send_message(chat_id, f"🚀 Started: {info}" if ok else f"❌ {info}")
            elif act == "ping" and code:
                self.tg.send_message(chat_id, f"🔔 pinged {campus.waiting_room_ping(self.tg, self.members, code)}")
            elif act == "mode" and code:
                cur = campus._load()["events"].get(code, {}).get("mode", "college")
                new = campus.set_mode(code, "exam" if cur == "college" else "college")
                self.tg.send_message(chat_id, campus.panel_text(self.members, code) if new else "❌ only before start",
                                     buttons=campus.panel_buttons(code) if new else None)
            elif act == "poster" and code:
                self.tg.send_message(chat_id, campus.poster_text(code))
            elif act == "csv" and code:
                csv = campus.csv_text(code) or ""
                try:
                    self.tg.send_document(chat_id, f"{code}.csv", csv.encode("utf-8"), caption="Full student data")
                except Exception:
                    self.tg.send_message(chat_id, csv[:3500])
            elif act == "report" and code:
                e = campus._load()["events"].get(code)
                self.tg.send_message(chat_id, campus.college_report(e) if e else "not found")
            elif act == "post" and code:
                e = campus._load()["events"].get(code)
                if e and e["state"] == "done":
                    for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
                        try:
                            self.tg.send_message(config.channel_chat_id(ch), campus.channel_post_from(e))
                            for post in campus.full_list_posts(e):
                                self.tg.send_message(config.channel_chat_id(ch), post)
                        except TelegramError:
                            pass
                    self.tg.send_message(chat_id, "✅ posted")
            elif act == "certs" and code:
                e = campus._load()["events"].get(code)
                if e:
                    for rank, (u, p) in enumerate(campus.ranking(e)[:3], 1):
                        card = campus.certificate_card(e, rank, p); txt = campus.certificate_text(e, rank, p)
                        try:
                            if card:
                                self.tg.send_photo(u, card, caption=txt[:1000], filename=f"cert{rank}.png")
                            else:
                                self.tg.send_message(u, txt)
                        except TelegramError:
                            pass
                    self.tg.send_message(chat_id, "🏅 sent")
            elif act == "help":
                self.tg.send_message(chat_id, "కొత్త event (buttons తో): ➕ బటన్ లేదా /college add\n"
                                              "typing తో అయితే: /go SR College | Warangal\n"
                                              "(2+ colleges: /college add లో ➕ బటన్ తో ఎన్ని అయినా · /cup new = knockout)\n"
                                              "(2 colleges war: /campus new Fest | Warangal | A ; B)")
            self._refresh_panel(cq, chat_id, code)      # same message updates in place
            try:
                self.tg.answer_callback(cq.get("id", ""), "ok")
            except TelegramError:
                pass
            return
        if kind == "join" and uid:
            from core import joingate
            ok, txt = joingate.verify(self.tg, self.members, uid)
            m = self.members.members.get(str(uid), {})
            self.tg.send_message(chat_id, txt, buttons=None if ok else joingate.buttons(m))
            try:
                self.tg.answer_callback(cq.get("id", ""), "✅" if ok else "⏳")
            except TelegramError:
                pass
            return
        if kind == "pexam" and uid:
            from core import partners
            ok, txt = partners.exam_checkin(self.members, uid, value)
            if ok:
                try:
                    mid = cq.get("message", {}).get("message_id")
                    if mid:
                        self.tg._call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": mid,
                                                                  "reply_markup": {"inline_keyboard": []}})
                except Exception:
                    pass
            self.tg.send_message(chat_id, txt)
            return
        if kind == "plocked":
            try:
                self.tg.answer_callback(cq.get("id", ""), f"🔒 {value} pts కావాలి — /quiz /war ఆడండి!" if value != "0" else "⏳ Exam window లో unlock అవుతుంది")
            except TelegramError:
                pass
            return
        if kind == "locked":
            try:
                self.tg.answer_callback(cq.get("id", ""), f"🔒 {value} pts కావాలి — /quiz ఆడండి!")
            except TelegramError:
                pass
            return
        if kind in ("state", "dist", "qual") and uid:
            st = self.members.pending_step(uid)
            expected = {"state": "state", "dist": "district", "qual": "qualification"}[kind]
            if st and st.get("step") == expected:
                status, reply = self.members.registration_input(uid, value)
                if reply:
                    self.tg.send_message(chat_id, reply, buttons=self._step_buttons(uid, status))
            elif self.members.is_registered(uid):
                self.tg.send_message(chat_id, "✅ Already registered — no need to fill again.\n⤷ ఇప్పటికే రిజిస్టర్ అయ్యారు.")

    def _ad_now(self):
        from core.engine import Engine
        try:
            return f"posted {Engine(dry=self.dry).partner_ad()} ad(s)"
        except Exception as e:
            return f"ad error: {e}"

    def _staff_ids(self):
        ids = set(getattr(config, "STAFF_IDS", []) or [])
        if config.ADMIN_ID:
            ids.add(str(config.ADMIN_ID))
        return ids

    def _start_challenge(self, uid, chat_id):
        """🥊 Serve yesterday's topper's questions as a timed DM set."""
        from core import growth
        if not self.members.is_registered(uid):
            self.members.start_registration(uid, username="")
            self.tg.send_message(chat_id, FIRST_TIME_ASK)
            return
        data = growth.build_daily_challenge(self.members, self.bank)
        if not data:
            self.tg.send_message(chat_id, "🥊 ఈరోజు challenge లేదు (నిన్న topper లేరు). రేపు మళ్ళీ చూడండి.")
            return
        if not growth.start_attempt(uid, data):
            self.tg.send_message(chat_id, "🥊 ఈరోజు already attempt చేశారు — one attempt per day. రేపు మళ్ళీ!")
            return
        t = data["topper"]
        self.tg.send_message(chat_id, f"🥊 Challenge start! Topper {t['name']} — {t['score']}/{t['total']}. "
                                      f"{len(data['qids'])} Q, same timer. Go 🔥")
        cfg = config.CHANNELS.get(data["channel"], {})
        tf = bool(getattr(config, "TELUGU_FIRST", True))
        for i, qid in enumerate(data["qids"], 1):
            q = self.bank.by_id(qid)
            if not q:
                continue
            payload = {"chat_id": chat_id,
                       "question": f"🥊 {i}/{len(data['qids'])} {build_question_text(q, cfg, telugu_first=tf)}"[:300],
                       "options": [{"text": o} for o in build_options(q, telugu_first=tf)],
                       "type": "quiz", "is_anonymous": False, "allows_multiple_answers": False,
                       "correct_option_id": q["answer_index"]}
            try:
                res = self.tg._call("sendPoll", payload)
                pid = (res.get("result", {}).get("poll") or {}).get("id")
                if pid:
                    growth.register_poll(data, pid, uid, qid, q["answer_index"])
            except TelegramError as e:
                print(f"   [challenge] send {qid}: {e}")
                break
            self.tg.polite_gap(True)

    def _me_username(self):
        if getattr(self, "_me", None) is None:
            try:
                self._me = (self.tg._call("getMe", {}) or {}).get("result", {}).get("username", "")
            except Exception:
                self._me = ""
        return self._me

    def _round_polls(self):
        from core.store import load_json
        import time as _t
        now = _t.time()
        if now - getattr(self, "_rp_ts", 0) > 5:
            self._rp = load_json(config.DATA / "round_polls.json", {})
            self._rp_ts = now
        return self._rp

    @staticmethod
    def _channel_to_exam(ch):
        m = {"TSPSC": "TSPSC", "APPSC": "APPSC", "BANKING": "Banking", "RAILWAY": "Railway",
             "POLICE": "Police", "DEFENCE": "Defence", "SSC": "SSC/UPSC", "CURRENT": "Current Affairs GK"}
        return m.get(ch, "TSPSC")

    @staticmethod
    def _exam_to_channel(exam):
        m = {"TSPSC": "TSPSC", "APPSC": "APPSC", "Banking": "BANKING",
             "Railway": "RAILWAY", "Police": "POLICE", "Defence": "DEFENCE",
             "SSC": "SSC", "SSC/UPSC": "SSC", "Current Affairs GK": "CURRENT"}
        return m.get(exam, "TSPSC")

    def _coach_lesson(self, channel=None):
        from core.store import load_json
        lessons = load_json(config.DATA / "coach_lessons.json",
                            {"lessons": []}).get("lessons", [])
        if not lessons:
            return None
        import random as _r
        pool = [l for l in lessons if l.get("channel") == channel] if channel else lessons
        l = _r.choice(pool or lessons)
        te = l["te"].lstrip()
        while te.startswith("⤷"):
            te = te[1:].lstrip()
        return f"{l['en']}\n\n⤷ {te}"

    _polls_file = config.DATA / "poll_state.json"

    def _load_polls(self):
        from core.store import load_json
        self._poll_q = {str(k): tuple(v) for k, v in
                        load_json(self._polls_file, {}).items()}

    def _save_polls(self):
        from core.store import save_json_atomic
        save_json_atomic(self._polls_file, {k: list(v) for k, v in self._poll_q.items()})

    # ------------------------------------------------------------ messages
    def handle_message(self, msg):
        chat_id = str(msg["chat"]["id"])
        who = msg.get("from", {})
        uid = who.get("id")
        text = (msg.get("text") or msg.get("caption") or "").strip()
        low = text.lower()

        if uid and str(uid) in self._staff_ids() and chat_id == str(uid):
            from core import notebook as NB
            doc = msg.get("document") or {}
            fname = (doc.get("file_name") or "").lower()
            blob = None
            if doc and (fname.endswith(".txt") or fname.endswith(".json") or fname.endswith(".md")):
                try:
                    blob = self.tg.download_file(doc.get("file_id", "")).decode("utf-8", "replace")
                except Exception as e:
                    self.tg.send_message(chat_id, f"⚠️ file download failed: {e}"); return
            elif re.search(r"^\s*#{2,4}\s*Q\b", text, re.M) or (text.startswith("[") and '"q_en"' in text):
                blob = text
            if blob is not None:
                pv = NB.preview(blob)
                NB.save_draft(uid, blob)
                btn = [[("✅ Import " + str(len(pv["ok"])), "nb:commit"), ("❌ Discard", "nb:discard")]] if pv["ok"] else None
                self.tg.send_message(chat_id, NB.preview_text(pv), buttons=btn)
                return
        if msg.get("photo") and uid and str(uid) in self._staff_ids():
            from core import messenger as MS
            if MS.get_draft(uid) is not None:
                MS.set_content(uid, text, msg["photo"][-1].get("file_id", ""))
                pv, rows, n = MS.preview(self.members, uid)
                if n == 0:
                    self.tg.send_message(chat_id, "⚠️ ఈ audience లో students లేరు. /msg"); MS.clear_draft(uid)
                else:
                    self.tg.send_message(chat_id, pv, buttons=rows)
                return
        if msg.get("photo") and uid and chat_id == str(uid) and not low.startswith("/partner"):
            from core import social
            plat = "yt" if "you" in low or "yt" in low else "ig"
            self.tg.send_message(chat_id, social.queue_screenshot(uid, self._name(who), msg["photo"][-1].get("file_id", ""), plat))
            for aid in self._staff_ids():
                try:
                    self.tg._call("sendPhoto", {"chat_id": aid, "photo": msg["photo"][-1].get("file_id", ""),
                                                "caption": f"📸 follow proof · {self._name(who)} ({uid}) · {plat}",
                                                "reply_markup": {"inline_keyboard": [[
                                                    {"text": "✅ approve", "callback_data": f"shot:{uid}:{plat}:1"},
                                                    {"text": "❌ reject", "callback_data": f"shot:{uid}:{plat}:0"}]]}})
                except Exception:
                    pass
            return

        # Registration guided flow takes priority
        if uid and self.members.pending_step(uid) and not low.startswith("/"):
            status, reply = self.members.registration_input(uid, text)
            if reply:
                self.tg.send_message(chat_id, reply, buttons=self._step_buttons(uid, status))
            if status == "duplicate":
                # 🚫 same mobile twice → staff alert (no second account created)
                dup = (self.members.pending_step(uid) or {}).get("last_dup") or {}
                for aid in self._staff_ids():
                    try:
                        self.tg.send_message(aid, f"🚫 Duplicate mobile blocked — {dup.get('mobile', '?')} "
                                                  f"already belongs to {dup.get('name', '')} ({dup.get('district', '')}, "
                                                  f"tg {dup.get('holder', '')}); attempted by {self._name(who)} ({uid}).")
                    except TelegramError:
                        pass
            if status == "done":
                self.tg.admin_note = None
                try:
                    from core import campus
                    ev = campus.on_registered(self.members, uid)
                    if ev:
                        self.tg.send_message(chat_id,
                            f"🎓 {ev['name']} కి ready ✅ (+{campus.JOIN_PTS} pts)\n"
                            f"⏳ Organiser 'Start' అనగానే Q1 ఇక్కడే వస్తుంది — ప్రతి Q కి timer, ఒక్కసారే answer.\n\n"
                            f"🎁 ఈరోజు తర్వాత కూడా మీకు:\n"
                            f"• రోజూ /quiz → points · 9 PM ⚔️ District War ({ev['district']})\n"
                            f"• Points = మీ జిల్లా shops/coaching/restaurant discounts (/offers) + application discounts\n"
                            f"• Results & toppers పేర్లతో మా channels లో — join అయ్యి చూడండి 👇",
                            buttons=campus.join_buttons())
                        from core import roster
                        if roster.needs_profile(self.members.members.get(str(uid), {})):
                            t, b = roster.profile_prompt(); self.tg.send_message(chat_id, t, buttons=b)
                except Exception:
                    pass
                try:
                    from core import joingate
                    m = self.members.members.get(str(uid), {})
                    self.tg.send_message(chat_id, joingate.hub_text(m), buttons=joingate.buttons(m))
                except Exception:
                    pass
                try:
                    from core import social
                    self.tg.send_message(chat_id, "🎁 ఇంకా bonus points:\n" + social.follow_prompt())
                except Exception:
                    pass
            return

        # 🏫 College-add wizard (staff, phone-friendly: name → ➕ more colleges → state → district buttons)
        if uid and str(uid) in self._staff_ids() and not low.startswith("/"):
            from core import campus
            wz = campus.wiz_get(uid)
            if wz and wz.get("step") in ("name", "name2"):
                name = text.strip()[:40]
                if len(name) < 2:
                    self.tg.send_message(chat_id, "College పేరు 2+ అక్షరాలు — మళ్ళీ పంపండి:")
                else:
                    cols = wz.get("colleges") or []
                    if name not in cols:
                        cols.append(name)
                    campus.wiz_set(uid, name=name, colleges=cols, step="more")
                    shown = "\n".join(f"  {i}. {c}" for i, c in enumerate(cols, 1))
                    self.tg.send_message(chat_id,
                        f"🏫 Colleges so far ({len(cols)}):\n{shown}\n\n"
                        "ఇంకా కాలేజీలు ఉన్నాయా? / More colleges?\n"
                        "➕ నొక్కి ఇంకా యాడ్ చేయొచ్చు — ఎన్ని అయినా (క్రికెట్ కప్ లాగ!)\n"
                        "అయిపోయాక ✅ నొక్కండి",
                        buttons=[[("➕ Add another college", "cwmore:again"),
                                  ("✅ Done → district", "cwmore:done")]])
                return
            if wz and wz.get("step") == "district_text":
                from core import districts as D
                _st, canon = D.match_any_district(text)
                if canon:
                    self._finish_college_wizard(chat_id, uid, canon)
                else:
                    self.tg.send_message(chat_id, "❓ జిల్లా దొరకలేదు — పేరు సరిగ్గా టైప్ చేయండి (e.g. Warangal / Siddipet):")
                return

        if low.startswith("/start"):
            linked = self.members.link_if_pending(uid, self._name(who),
                                                  name=who.get("first_name", ""))
            # deep link: t.me/<bot>?start=ref<uid>
            arg = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
            if arg.startswith("ref") and arg[3:].isdigit() and uid:
                if self.members.add_referral(uid, arg[3:]):
                    try:
                        self.tg.send_message(arg[3:], "🎁 Your friend joined via your link — +20 points!\n⤷ మీ ఫ్రెండ్ join అయ్యారు — +20 పాయింట్లు!")
                    except TelegramError:
                        pass
            camp = None
            try:
                from core import campus
                camp = campus.parse_start_arg(arg)
            except Exception:
                camp = None
            if camp and uid:
                from core import campus
                ok, txt, need = campus.join(self.members, uid, camp[0], camp[1], name_hint=who.get("first_name", ""))
                self.tg.send_message(chat_id, txt)
                if ok and need and not self.members.pending_step(uid):
                    e = campus._load()["events"][camp[0]]
                    from core import districts as D
                    self.members.start_registration(uid, username=self._name(who), quick={
                        "state_code": D.state_of(e["district"]) or "AP",
                        "state": "Telangana" if D.state_of(e["district"]) == "TS" else "Andhra Pradesh",
                        "district": e["district"], "exam": "Current Affairs GK"})
                    self.tg.send_message(chat_id, "✍️ Step 1 of 2 — మీ పూర్తి పేరు? / Your full name:")
                return
            try:
                from core import jobradar
                jid = jobradar.parse_start_arg(arg)
            except Exception:
                jid = None
            if jid and uid:
                if self.members.is_registered(uid):
                    txt, btn = jobradar.job_card(jid, uid)
                    self.tg.send_message(chat_id, txt, buttons=btn)
                    return
                self.members.start_registration(uid, username=self._name(who))
                self.tg.send_message(chat_id, "🔔 Job track + reminders కోసం 1 నిమిషం register (+25 pts) 👇 తర్వాత /jobs")
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            if arg == "war" and uid:
                from core import districtwar
                if self.members.is_registered(uid):
                    ok, txt = districtwar.lobby_join(self.members, uid)
                    self.tg.send_message(chat_id, txt, buttons=None if ok else None)
                    return
                if not self.members.pending_step(uid):
                    self.members.start_registration(uid, username=self._name(who))
                self.tg.send_message(chat_id, "⚔️ War ఆడాలంటే 1 నిమిషం register (జిల్లా కావాలి, +25 pts) 👇 తర్వాత /war join")
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            if arg in ("quiz", "register", "reg") and uid and not self.members.is_registered(uid):
                if not self.members.pending_step(uid):
                    self.members.start_registration(uid, username=self._name(who))
                lp = (self.members.members.get(str(uid)) or {}).get("locked_points", 0)
                self.tg.send_message(chat_id, (f"🔓 {lp} points unlock అవుతాయి — " if lp else "") + "1 నిమిషం registration (+25 bonus pts) 👇")
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            if arg == "offers":
                self.tg.send_message(chat_id, "🛍 Offers claim చేయాలంటే 1 నిమిషం register (+25 pts bonus) → తర్వాత /offers 👇"
                                     if not self.members.is_registered(uid) else "🛍 మీ offers 👇 /offers")
                if self.members.is_registered(uid):
                    from core import partners, rewards
                    bal = rewards.balance(self.members, uid)["available"]
                    self.tg.send_message(chat_id, partners.render_offers(self.members, uid, bal),
                                         buttons=partners.offer_buttons(self.members, uid, bal) or None)
            self.tg.send_message(chat_id, WELCOME, parse_mode="Markdown")
            if uid and not self.members.is_registered(uid) and not self.members.pending_step(uid):
                self.members.start_registration(uid, username=self._name(who))
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
            if linked:
                self.tg.send_message(
                    chat_id, "✅ Found your Google-Form registration — linked! "
                             "Your +25 points are ready. Send /quiz to play.\n"
                             "⤷ మీ Google ఫారమ్ రిజిస్ట్రేషన్ లింక్ అయింది! /quiz ఆడండి.")
        elif low.startswith("/regform") or low.startswith("/form") or low.startswith("/googleform"):
            self.tg.send_message(
                chat_id,
                "📋 *Full Registration (Google Form)*\n"
                f"👉 {config.FORM_URL}\n\n"
                "Use it for your complete profile (phone, district, WhatsApp, "
                "target exam, language). For *points & the leaderboard*, also "
                "send /register here and play /quiz.\n\n"
                "⤷ పూర్తి వివరాల కోసం ఫారమ్ నింపండి; పాయింట్ల కోసం ఇక్కడ /register చేయండి.",
                parse_mode="Markdown", disable_preview=False)
        elif low.startswith("/help"):
            self.tg.send_message(chat_id, HELP, parse_mode="Markdown")
        elif low.startswith("/levels") or low.startswith("/points"):
            self.tg.send_message(chat_id, LEVELS_TEXT, parse_mode="Markdown")
        elif low.startswith("/register") or low.startswith("/signup"):
            # One-time only: registered members are never asked again.
            if uid and self.members.is_registered(uid):
                self.tg.send_message(chat_id, self.members.already_registered_text(uid))
            else:
                self.members.start_registration(uid, username=self._name(who))
                self.tg.send_message(
                    chat_id,
                    "📝 One-time registration (name → state → district → qualification → mobile).\nStep 1 of 5 — What is your full name?\n"
                    "⤷ మీ పూర్తి పేరు పంపండి:")
        elif low.startswith("/cancel"):
            self.members.cancel_registration(uid)
            self.tg.send_message(chat_id, "Registration cancelled. /register to retry.\n⤷ రద్దు చేయబడింది.")
        elif low.startswith("/quiz"):
            # Registration-first: the form (name → state → district → exam →
            # language) must be completed once before playing.
            if getattr(config, "REQUIRE_REGISTRATION", True) and uid \
                    and not self.members.is_registered(uid):
                self.members.start_registration(uid, username=self._name(who))
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            parts = low.split()
            ch = parts[1].upper() if len(parts) > 1 else None
            if ch not in config.PUBLIC_CHANNELS:
                ch = None
            self.send_quiz_to(chat_id, ch, uid=uid)
        elif low.startswith("/exam"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                self.tg.send_message(chat_id, "Usage: /exam TSPSC | APPSC | Banking | Railway | Police | Defence | SSC | GK\n⤷ ఉదా: /exam APPSC")
            else:
                ex = self.members.set_exam(uid, parts[1])
                if ex:
                    self.members.set_follow(uid, [self._exam_to_channel(ex), "CURRENT"])
                    self.tg.send_message(chat_id, f"🎯 Target updated: {ex}. Round questions for this exam will come to you here.\n⤷ లక్ష్యం మార్చబడింది: {ex}")
                else:
                    self.tg.send_message(chat_id, "Exam not recognised. Try /exam TSPSC")
        elif low.startswith("/follow"):
            parts = low.split()[1:]
            chans = [p.upper() for p in parts if p.upper() in config.PUBLIC_CHANNELS]
            if not chans:
                self.tg.send_message(chat_id, "Usage: /follow TSPSC APPSC BANKING … (channels whose rounds you want here)\n"
                                              f"Available: {' '.join(config.PUBLIC_CHANNELS)}")
            else:
                f = self.members.set_follow(uid, chans)
                self.tg.send_message(chat_id, f"🔔 Following rounds: {', '.join(f)}\n⤷ ఈ ఛానల్ రౌండ్లు మీకు ఇక్కడ వస్తాయి.")
        elif low.startswith("/warrank") or low.startswith("/myrank"):
            from core import districtwar
            self.tg.send_message(chat_id, districtwar.war_rank_text(uid) + "\n\n" + districtwar.war_leaderboard(self.members))
        elif low.startswith("/war") or low.startswith("/districtwar"):
            from core import districtwar
            parts = low.split()
            if len(parts) > 1 and parts[1] == "now" and str(uid) in self._staff_ids():
                mins = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 5
                ok, txt = districtwar.manual_launch(self.members, self.tg, bank=self.bank, minutes=max(2, min(mins, 30)))
                self.tg.send_message(chat_id, txt)
            elif len(parts) > 1 and parts[1] == "status" and str(uid) in self._staff_ids():
                self.tg.send_message(chat_id, districtwar.owner_status(self.members),
                                     buttons=[[("⚔️ Launch war now (5 min)", "cmd:war now"), ("🔄 Status", "cmd:war status")]])
            elif len(parts) > 1 and parts[1] in ("join", "play", "in"):
                ok, txt = districtwar.lobby_join(self.members, uid, via_squad=(len(parts) > 2 and parts[2] == "squad"))
                self.tg.send_message(chat_id, txt)
            else:
                st = districtwar.lobby_status()
                extra = ""
                if st["open"]:
                    extra = f"\n\n🟢 Lobby OPEN — {st['n']} fighters in. Join: button లేదా /war join (squad మొత్తం: /war join squad)"
                self.tg.send_message(chat_id, districtwar.my_war(self.members, uid) + extra,
                                     buttons=districtwar.lobby_buttons(5) if st["open"] else None)
        elif low.startswith("/battle") or low.startswith("/room") or low.startswith("/arena"):
            from core import arena
            parts = text.split()
            sub = parts[1].lower() if len(parts) > 1 else ""
            arg = parts[2] if len(parts) > 2 else ""
            if not self.members.is_registered(uid) and sub not in ("list", "top", ""):
                self.members.start_registration(uid, username=self._name(who))
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            if sub == "new":
                n = int(arg) if arg.isdigit() else arena.DEFAULT_Q
                r, msg = arena.room_new(self.members, uid, n)
                self.tg.send_message(chat_id, msg)
                if r:      # tell squad mates
                    for u in r["players"]:
                        if u != str(uid):
                            try:
                                self.tg.send_message(u, f"🎮 మీ squad room {r['code']} open చేసింది — match start అయ్యాక ప్రశ్నలు ఇక్కడే వస్తాయి. Ready ఉండండి!")
                            except TelegramError:
                                pass
            elif sub == "join":
                r, msg = arena.room_join(self.members, uid, arg)
                self.tg.send_message(chat_id, msg)
                if r:
                    for u in r["players"]:
                        if u != str(uid):
                            try:
                                self.tg.send_message(u, f"⚔️ {msg}")
                            except TelegramError:
                                pass
            elif sub == "start":
                r, err = arena.room_start(self.bank, uid=uid)
                if err:
                    self.tg.send_message(chat_id, err)
                else:
                    arena._broadcast(self.tg, r, arena.countdown_text(r))
            elif sub == "list":
                self.tg.send_message(chat_id, arena.list_rooms())
            elif sub == "watch":
                self.tg.send_message(chat_id, arena.room_watch(uid, arg))
            elif sub == "leave":
                self.tg.send_message(chat_id, arena.room_leave(uid))
            elif sub == "top":
                self.tg.send_message(chat_id, arena.render_top(self.members))
            elif sub == "tournament":
                if str(uid) not in self._staff_ids():
                    self.tg.send_message(chat_id, "🔒 Admin only.")
                else:
                    created, msg = arena.tournament_create(self.bank, self.members)
                    self.tg.send_message(chat_id, msg)
            else:
                self.tg.send_message(chat_id, arena.my_status(self.members, uid))
        elif low.startswith("/squad") or low.startswith("/team"):
            from core import hooks
            parts = text.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else ""
            if sub in ("new", "create"):
                _c, msg = hooks.squad_create(self.members, uid, parts[2] if len(parts) > 2 else "")
            elif sub == "join":
                _s, msg = hooks.squad_join(self.members, uid, parts[2] if len(parts) > 2 else "")
            elif sub == "leave":
                msg = hooks.squad_leave(uid)
            else:
                msg = hooks.render_squad(self.members, uid)
            self.tg.send_message(chat_id, msg)
        elif low.startswith("/offers") or low.startswith("/shops") or low.startswith("/deals"):
            from core import partners, rewards
            if not self.members.is_registered(uid):
                self.members.start_registration(uid, username=self._name(who))
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            bal = rewards.balance(self.members, uid)["available"]
            cat = (low.split() + [""])[1]
            cat = {"restaurant": "food", "cafe": "food", "mall": "shop", "shops": "shop", "institute": "coaching",
                   "gym": "health", "xerox": "tech", "pg": "hostel"}.get(cat, cat)
            cat = cat if cat in partners.CATEGORIES else ""
            self.tg.send_message(chat_id, partners.render_offers(self.members, uid, bal, category=cat),
                                 buttons=partners.offer_buttons(self.members, uid, bal, category=cat) or None)
        elif low.startswith("/claim"):
            from core import social
            parts = text.split()
            if len(parts) < 2:
                self.tg.send_message(chat_id, social.follow_prompt()); return
            ok, txt = social.claim(self.members, uid, parts[1])
            self.tg.send_message(chat_id, txt)
        elif low.startswith("/follow") or low.startswith("/insta") or low.startswith("/youtube"):
            from core import social
            self.tg.send_message(chat_id, social.follow_prompt())
        elif low.startswith("/scout"):
            from core import social
            rest = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
            m = self.members.members.get(str(uid), {})
            if not m.get("registered"):
                self.tg.send_message(chat_id, "ముందు register అవ్వండి → /start"); return
            lead = social.add_lead(uid, m.get("district", ""), rest) if rest else None
            if not lead:
                self.tg.send_message(chat_id, f"🕵️ Business Scout — మీ జిల్లాలో shop / coaching / restaurant / salon / కొత్త opening తెలుసా?\n"
                                              f"/scout <business పేరు> | <type> | <owner phone> | <area>\n"
                                              f"వాళ్ళు partner అయితే మీకు +{social.SCOUT_CONVERT_PTS} pts + free voucher 🎁")
                return
            self.tg.send_message(chat_id, f"✅ Lead {lead['id']} received — StudentUp team వాళ్ళకి call చేస్తుంది. Partner అయితే +{social.SCOUT_CONVERT_PTS} pts మీకు!")
            for aid in self._staff_ids():
                try:
                    self.tg.send_message(aid, f"🕵️ New lead {lead['id']} · {lead['district']} · {lead['name']} ({lead['type']}) 📞 {lead['phone']} {lead['area']}\nscout: {m.get('name')} ({uid})")
                except TelegramError:
                    pass
        elif low.startswith("/pitch") and str(uid) in self._staff_ids():
            from core import social
            dist = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else self.members.members.get(str(uid), {}).get("district", "")
            self.tg.send_message(chat_id, social.district_pitch(self.members, dist))
        elif low.startswith("/social") and str(uid) in self._staff_ids():
            from core import social
            parts = text.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else ""
            rest = parts[2] if len(parts) > 2 else ""
            if sub == "new":
                f = [x.strip() for x in rest.split("|")]
                if len(f) < 2:
                    self.tg.send_message(chat_id, "Usage: /social new ig|<post title>|[pts]|[days]|[CODE]|[cap]"); return
                code = social.new_campaign(f[0], f[1], int(f[2]) if len(f) > 2 and f[2] else social.CLAIM_PTS_DEFAULT,
                                           int(f[3]) if len(f) > 3 and f[3] else 3, f[4] if len(f) > 4 else "",
                                           int(f[5]) if len(f) > 5 and f[5] else 0)
                self.tg.send_message(chat_id, f"✅ Campaign {code}\n\nInstagram auto-DM / ManyChat reply లో ఇది paste చేయండి:\n\n{social.auto_dm_text(code)}")
            elif sub == "leads":
                self.tg.send_message(chat_id, social.leads_text(rest.strip()))
            elif sub == "convert":
                f = rest.split()
                l = social.convert_lead(self.members, f[0], f[1]) if len(f) == 2 else None
                if l:
                    try:
                        self.tg.send_message(l["uid"], f"🎉 మీరు scout చేసిన {l['name']} StudentUp partner అయింది → +{social.SCOUT_CONVERT_PTS} pts! /offers చూడండి")
                    except TelegramError:
                        pass
                self.tg.send_message(chat_id, "✅ converted, scout rewarded" if l else "Usage: /social convert <LID> <PID>")
            elif sub == "opening":
                from core import partners
                f = rest.split()
                ok = partners.set_opening(f[0], int(f[1]) if len(f) > 1 else 7) if f else False
                self.tg.send_message(chat_id, "🎉 opening package on (2× ads, NEW OPENING tag)" if ok else "Usage: /social opening <PID> [days]")
            elif sub == "call":
                from core.engine import Engine
                self.tg.send_message(chat_id, f"posted: {Engine(dry=self.dry).partner_call()}")
            elif sub == "kit":
                self.tg.send_message(chat_id, social.partner_kit())
            elif sub == "pending":
                ps = social.pending_screenshots()
                self.tg.send_message(chat_id, f"{len(ps)} screenshots pending (buttons were sent to staff when received)")
            else:
                self.tg.send_message(chat_id, social.campaign_stats() + "\n\nCommands: new · leads [district] · convert <LID> <PID> · opening <PID> [days] · kit · call · pending")
        elif low.startswith("/filed") and str(uid) in self._staff_ids():
            from core import rewards
            parts = text.split()
            if len(parts) < 2:
                self.tg.send_message(chat_id, "Usage: /filed <telegram id | 10-digit phone> [rupees]  — application cashback"); return
            res = rewards.filed_application(self.members, parts[1], int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 100, uid)
            if "@@MEMBER@@" in res:
                staff_msg, _, rest = res.partition("@@MEMBER@@")
                mu, _, mm = rest.partition("@@")
                try:
                    self.tg.send_message(mu, mm)
                except TelegramError:
                    pass
                res = staff_msg
            self.tg.send_message(chat_id, res)
        elif low.startswith("/hq") and str(uid) in self._staff_ids():
            from core import hq
            txt, _, _ = hq.render(self.members, self.bank)
            self.tg.send_message(chat_id, txt, buttons=hq.buttons())
        elif low.startswith("/college") and str(uid) in self._staff_ids():
            from core import hq
            rest = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
            if rest.lower() in ("add", "new"):
                from core import campus
                campus.wiz_start(uid)
                self.tg.send_message(chat_id, COLLEGE_WIZ_NAME)
                return
            if rest.lower().startswith("lead "):
                f = [x.strip() for x in rest[5:].split("|")]
                if len(f) == 2:
                    hq.set_leader(f[0], f[1], self.members); self.tg.send_message(chat_id, f"👑 {f[0]} leader set")
                else:
                    self.tg.send_message(chat_id, "Usage: /college lead <College> | <telegram id>")
                return
            if rest:
                txt, btns = hq.club_card(self.members, rest)
                self.tg.send_message(chat_id, txt, buttons=btns)
            else:
                self.tg.send_message(chat_id, hq.club_list_text(self.members), buttons=hq.club_buttons(self.members))
        elif uid and str(uid) in self._staff_ids() and not low.startswith("/") and __import__("core.messenger", fromlist=["x"]).get_draft(uid) is not None:
            from core import messenger as MS
            photo = msg["photo"][-1].get("file_id", "") if msg.get("photo") else ""
            if not text and not photo:
                return
            MS.set_content(uid, text, photo)
            pv, rows, n = MS.preview(self.members, uid)
            if n == 0:
                self.tg.send_message(chat_id, "⚠️ ఈ audience లో students లేరు. /msg", buttons=None); MS.clear_draft(uid); return
            self.tg.send_message(chat_id, pv, buttons=rows)
        elif getattr(self, "_club_msg", {}).get(str(uid)) and not low.startswith("/"):
            from core import hq
            college = self._club_msg.pop(str(uid))
            n = 0
            for mu in hq.club_members(self.members, college):
                try:
                    self.tg.send_message(mu, f"🏫 {college} — message from StudentUp:\n\n{text}"); n += 1
                except TelegramError:
                    pass
            self.tg.send_message(chat_id, f"📢 sent to {n} members of {college}")
        elif low.startswith("/go ") and str(uid) in self._staff_ids():
            from core import campus
            f = [x.strip() for x in text[4:].split("|")]
            if len(f) < 2:
                self.tg.send_message(chat_id, "Usage: /go <College name> | <district> [| questions] [| easy/medium/hard]"); return
            lvl = f[3].lower() if len(f) > 3 else "easy"
            code = campus.quick_event(f[0], f[1], int(f[2]) if len(f) > 2 and f[2].isdigit() else campus.DEFAULT_Q,
                                      "medium" if lvl == "exam" else lvl, created_by=uid, mode="exam" if lvl == "exam" else "college")
            self.tg.send_message(chat_id, f"✅ {code} ready. Students కి ఇది పంపండి / projector లో చూపండి:")
            self.tg.send_message(chat_id, campus.poster_text(code))
            self.tg.send_message(chat_id, campus.panel_text(self.members, code), buttons=campus.panel_buttons(code))
        elif low.startswith("/join") or low.startswith("/channels"):
            from core import joingate
            m = self.members.members.get(str(uid), {}) if uid else {}
            if not m.get("registered"):
                self.tg.send_message(chat_id, "ముందు register అవ్వండి → /start"); return
            self.tg.send_message(chat_id, joingate.hub_text(m), buttons=joingate.buttons(m))
        elif low.startswith("/myscore"):
            from core import campus, joingate
            m = self.members.members.get(str(uid), {}) if uid else {}
            if m.get("registered") and not joingate.joined_all(m):
                self.tg.send_message(chat_id, joingate.gate_text(m, "Full list"), buttons=joingate.buttons(m))
                return
            self.tg.send_message(chat_id, campus.my_score(self.members, uid), buttons=campus.join_buttons())
        elif low.startswith("/campuswar") and uid:
            # 🎓 students create their own college war/test (staff approve with one tap)
            from core import campus
            if not self.members.is_registered(uid):
                if self.members.start_registration(uid, username=self._name(who)):
                    self.tg.send_message(chat_id, "🎓 College war పెట్టాలంటే ముందు 1 నిమిషం రిజిస్టర్ (+25 pts) 👇")
                    self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            arg = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
            f = [x.strip() for x in arg.split("|")]
            if len(f) < 2 or not f[0] or not f[1]:
                self.tg.send_message(chat_id, "🎓 మీ సొంత college war/test — ఇక్కడే పెట్టుకోండి!\n"
                                              "Usage: /campuswar <College పేరు> | <District>\n"
                                              "e.g.  /campuswar SR College | Warangal\n\n"
                                              "Staff approve చేయగానే మీకు poster + classmates కి పంపే link వస్తుంది 🚀\n"
                                              "⤷ అప్పటిదాకా ఫ్రెండ్స్‌తో /squad · /battle ఆడండి!")
                return
            m = self.members.members.get(str(uid)) or {}
            rid = campus.student_request(uid, f[0], f[1], name=m.get("name", ""))
            self.tg.send_message(chat_id, f"✅ Request {rid} పంపారు — {f[0]}, {f[1]}.\n"
                                          "Staff ఒకే అనగానే మీకు ఇక్కడే poster + share link వస్తుంది 🚀\n"
                                          "Classmates అందరూ ఆ లింక్ తో join అవుతారు — పేర్లతో results!\n"
                                          "⤷ ఆగలేకపోతే ఇప్పుడే /squad /battle!")
            for aid in self._staff_ids():
                try:
                    self.tg.send_message(aid, f"🎓 College-war request {rid}: {f[0]} | {f[1]} — "
                                              f"by {m.get('name', '') or uid} ({uid})",
                                         buttons=[[("✅ Approve", f"cwr:{rid}:1"), ("❌ Deny", f"cwr:{rid}:0")]])
                except TelegramError:
                    pass
            return
        elif low.startswith("/cup") and str(uid) in self._staff_ids():
            from core import cup as C
            parts = text.split(maxsplit=2)
            sub = parts[1].strip() if len(parts) > 1 else ""
            rest = parts[2] if len(parts) > 2 else ""
            if sub == "new":
                f = [x.strip() for x in rest.split("|")]
                if len(f) < 2 or ";" not in f[1]:
                    self.tg.send_message(chat_id,
                        "🏆 Usage: /cup new <District> | College A ; College B ; College C …\n"
                        "(3–16 colleges · cricket-style knockout · rounds parallel · auto semis/final)")
                    return
                cols = [c.strip() for c in f[1].split(";") if c.strip()]
                code, msg = C.cup_new(f[0], cols, name=f"{f[0]} College Cup", created_by=uid)
                self.tg.send_message(chat_id, msg)
                if code:
                    self.tg.send_message(chat_id, C.render_cup(code), buttons=C.cup_buttons(code))
            elif sub.upper().startswith("CUP-"):
                self.tg.send_message(chat_id, C.render_cup(sub.upper()), buttons=C.cup_buttons(sub.upper()))
            else:
                self.tg.send_message(chat_id, C.list_cups())
        elif low.startswith("/campus"):
            from core import campus
            parts = text.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else ""
            rest = parts[2] if len(parts) > 2 else ""
            if str(uid) not in self._staff_ids():
                self.tg.send_message(chat_id, "🎓 మీ college లో StudentUp exam + college-vs-college war కావాలా?\n"
                                              "📲 మీరే పెట్టుకోండి: /campuswar <College> | <District> (staff ఒకే అంటే చాలు)\n"
                                              "లేదా College పేరు · జిల్లా · students సంఖ్య · మీ phone → /partner apply లో పంపండి, team వస్తుంది!\n"
                                              "(Top 10 కి gifts · అందరికీ points · results channel లో పేర్లతో)")
                return
            if sub == "new":
                f = [x.strip() for x in rest.split("|")]
                if len(f) < 3:
                    self.tg.send_message(chat_id, "Usage: /campus new <event name> | <district> | <College A> ; <College B> ; … [| questions] [| easy/medium/hard]"); return
                code = campus.new_event(f[0], f[1], f[2].split(";"), int(f[3]) if len(f) > 3 and f[3].isdigit() else campus.DEFAULT_Q,
                                        f[4].lower() if len(f) > 4 else "medium", created_by=uid)
                self.tg.send_message(chat_id, f"✅ Event {code}\n\n" + campus.links_text(code))
            elif sub == "links":
                self.tg.send_message(chat_id, campus.links_text(rest.strip()))
            elif sub == "poster":
                self.tg.send_message(chat_id, campus.poster_text(rest.strip()))
            elif sub == "status":
                self.tg.send_message(chat_id, campus.status_text(self.members, rest.strip()))
            elif sub == "ping":
                self.tg.send_message(chat_id, f"pinged {campus.waiting_room_ping(self.tg, self.members, rest.strip())}")
            elif sub == "start":
                ok, info = campus.start(self.bank, self.members, self.tg, rest.strip())
                self.tg.send_message(chat_id, f"🚀 Started: {info}" if ok else f"❌ {info}")
            elif sub == "csv":
                csv = campus.csv_text(rest.strip())
                if not csv:
                    self.tg.send_message(chat_id, "Event not found."); return
                try:
                    self.tg.send_document(chat_id, f"{rest.strip()}.csv", csv.encode("utf-8"), caption="Full student data")
                except Exception:
                    for i in range(0, len(csv), 3500):
                        self.tg.send_message(chat_id, csv[i:i + 3500])
            elif sub == "post":
                txt = campus.channel_post(rest.strip())
                if not txt:
                    self.tg.send_message(chat_id, "Event not finished."); return
                for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
                    try:
                        self.tg.send_message(config.channel_chat_id(ch), txt)
                    except TelegramError:
                        pass
                self.tg.send_message(chat_id, "✅ posted to hub channels")
            elif sub == "prize":
                f = rest.split(maxsplit=2)
                if len(f) < 3 or not f[1].isdigit():
                    self.tg.send_message(chat_id, "Usage: /campus prize <CODE> <rank> <message>"); return
                e = campus._load()["events"].get(f[0])
                rows = campus.ranking(e) if e else []
                if not rows or int(f[1]) > len(rows):
                    self.tg.send_message(chat_id, "rank not found"); return
                u, p = rows[int(f[1]) - 1]
                self.tg.send_message(u, f"🎁 {e['name']} — Rank #{f[1]} prize!\n{f[2]}")
                self.tg.send_message(chat_id, f"sent to {p['name']}")
            else:
                self.tg.send_message(chat_id, campus.panel_text(self.members), buttons=campus.panel_buttons())
        elif low.startswith("/jobs") and uid:
            from core import jobradar
            arg = (low.split(maxsplit=1)[1] if len(low.split()) > 1 else "").strip()
            if arg == "stats" and str(uid) in self._staff_ids():
                self.tg.send_message(chat_id, jobradar.stats_text(self.members))
            elif not self.members.is_registered(uid):
                if not self.members.pending_step(uid):
                    self.members.start_registration(uid, username=self._name(who))
                self.tg.send_message(chat_id, "📡 Job Radar (మీ qualification కి match అయ్యే jobs + reminders) కోసం ముందు register (+25 pts) 👇")
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
            elif arg in ("off", "on"):
                self.tg.send_message(chat_id, jobradar.set_digest(uid, arg == "on"))
            elif arg.upper().startswith("J") and arg[1:].isdigit():
                txt, btn = jobradar.job_card(arg.upper(), uid)
                self.tg.send_message(chat_id, txt, buttons=btn)
            else:
                self.tg.send_message(chat_id, jobradar.radar_text(self.members, uid), buttons=jobradar.radar_buttons(self.members, uid))
        elif low.startswith("/notebook") and uid and str(uid) in self._staff_ids():
            from core import notebook as NB
            parts = text.split()
            sub = parts[1].lower() if len(parts) > 1 else ""
            if sub == "prompt" and len(parts) > 2:
                ch = parts[2].upper()
                if ch not in config.CHANNELS:
                    self.tg.send_message(chat_id, "channel: TSPSC APPSC SSC BANKING RAILWAY POLICE DEFENCE CURRENT")
                else:
                    extra = " ".join(parts[3:])
                    self.tg.send_message(chat_id, NB.prompt_for(ch, paper=extra))
            elif sub == "status":
                self.tg.send_message(chat_id, NB.status_text())
            else:
                self.tg.send_message(chat_id, NB.howto_text(), buttons=NB.buttons())
        elif low.startswith("/sheet") and uid and str(uid) in self._staff_ids():
            from core import crm
            self.tg.send_message(chat_id, crm.sheet_status_text(self.members.members), buttons=crm.sheet_buttons())
        elif low.startswith("/msg") and uid and str(uid) in self._staff_ids():
            from core import messenger as MS
            arg = text[4:].strip()
            if arg.startswith("history"):
                self.tg.send_message(chat_id, MS.history_text())
            elif arg.startswith("templates"):
                self.tg.send_message(chat_id, MS.templates_text())
            elif arg.startswith("cancel"):
                jid = arg.split()[-1]
                self.tg.send_message(chat_id, f"🗑 cancelled {MS.cancel_scheduled(jid)} job(s)")
            else:
                MS.clear_draft(uid)
                self.tg.send_message(chat_id, "📣 MESSAGE STUDIO — register అయిన students కి individual DM.\nఎవరికి పంపాలి?", buttons=MS.audience_buttons())
        elif low.startswith("/card") and uid:
            from core import reportcard
            if not self.members.members.get(str(uid), {}).get("registered"):
                self.tg.send_message(chat_id, "📇 Report card కి ముందు register అవ్వండి: /register"); return
            reportcard.send_card(self.tg, self.members, str(uid))
        elif low.startswith("/profile"):
            from core import roster
            m = self.members.members.get(str(uid), {}) if uid else {}
            m.pop("_prof_skipped", None)
            t, b = roster.profile_prompt()
            self.tg.send_message(chat_id, (f"📚 ఇప్పుడు: {m.get('branch', '—')} {m.get('year', '')}\n" if m.get("branch") else "") + t, buttons=b)
        elif low.startswith("/retest") and uid and str(uid) in self._staff_ids():
            from core import roster, campus
            arg = text[7:].strip()
            if not arg:
                cols = sorted({m.get("college") for m in self.members.members.values() if m.get("college")})
                self.tg.send_message(chat_id, "🔁 /retest <College> [| N Q] [| HH:MM]\nColleges: " + (", ".join(cols[:30]) or "none yet"))
                return
            f = [x.strip() for x in arg.split("|")]
            n_q = int(f[1]) if len(f) > 1 and f[1].isdigit() else 15
            at = None
            for x in f[1:]:
                if ":" in x:
                    try:
                        hh, mm = x.split(":"); at = datetime.now(config.IST).replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                    except Exception:
                        at = None
            code, n = roster.schedule_retest(self.members, f[0], n_q, at, created_by=uid)
            if not code:
                self.tg.send_message(chat_id, f"❌ '{f[0]}' కి students లేరు. /college చూడండి."); return
            pinged = roster.ping_retest(self.tg, code)
            self.tg.send_message(chat_id, f"🔁 {code} scheduled · {n} students enrolled · {pinged} invited\n"
                                          f"⏰ Auto-start {datetime.fromisoformat(campus._load()['events'][code]['auto_start']).strftime('%H:%M')} (or start now below)",
                                 buttons=campus.panel_buttons(code))
        elif low.startswith("/roster") and uid and str(uid) in self._staff_ids():
            from core import roster
            college = text[7:].strip()
            if not college:
                self.tg.send_message(chat_id, "📋 /roster <College> → roster card + CSV"); return
            self.tg.send_message(chat_id, roster.roster_text(self.members, college))
            try:
                self.tg.send_document(chat_id, f"roster_{college[:20]}.csv", roster.roster_csv(self.members, college).encode("utf-8"), caption="Roster with all test attempts")
            except Exception:
                pass
        elif low.startswith("/coach"):
            m = self.members.members.get(str(uid), {}) if uid else {}
            parts = low.split()
            if len(parts) > 1 and parts[1] in ("off", "stop"):
                m["no_coach"] = True; self.members.kv.save(); self.tg.send_message(chat_id, "🎯 Coach DMs off. మళ్ళీ: /coach on"); return
            if len(parts) > 1 and parts[1] == "on":
                m["no_coach"] = False; self.members.kv.save(); self.tg.send_message(chat_id, "🎯 Coach DMs on — రోజూ 07:30"); return
            weak = self.members.weak_topics(uid) if uid else []
            self.tg.send_message(chat_id, "🎯 Personal Coach — రోజూ 07:30 కి మీ weak topics నుంచి 3 Q\n"
                                          + (f"మీ weak topics: {', '.join(t.title() for t in weak)}\n" if weak else "ఇంకా data లేదు — కొన్ని rounds ఆడండి\n")
                                          + f"Coach streak: {m.get('coach_streak', 0)} రోజులు · 5 → 🎯 Focus badge\nఇప్పుడే ఒకటి: /quiz · Off: /coach off")
        elif low.startswith("/mandal"):
            m = self.members.members.get(str(uid), {}) if uid else {}
            if not m.get("registered"):
                self.tg.send_message(chat_id, "ముందు register అవ్వండి → /start"); return
            rest = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
            if not rest:
                self.tg.send_message(chat_id, f"🏠 మీ mandal: {m.get('mandal') or '— set కాలేదు'}\nSet: /mandal <పేరు>  (మీ mandal shops offers ముందు వస్తాయి)"); return
            m["mandal"] = rest[:40]; self.members.kv.save()
            self.tg.send_message(chat_id, f"✅ Mandal: {rest[:40]} — local offers ఇప్పుడు ముందు కనిపిస్తాయి → /offers")
        elif low.startswith("/mydistrict") or low.startswith("/changedistrict"):
            from core import districts as D
            m = self.members.members.get(str(uid), {}) if uid else {}
            if not m.get("registered"):
                self.tg.send_message(chat_id, "ముందు register అవ్వండి → /start"); return
            rest = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else ""
            d = (D.match_district("TS", rest) or D.match_district("AP", rest)) if rest else None
            if not d:
                self.tg.send_message(chat_id, f"📍 మీ జిల్లా: {m.get('district', '—')}\nమారాలంటే: /mydistrict <కొత్త జిల్లా>  (exam centre / hostel వేరే జిల్లా అయితే)\n30 రోజులకి ఒకసారి మాత్రమే."); return
            last = m.get("district_changed", "")
            try:
                if last and (datetime.now(config.IST) - datetime.fromisoformat(last)).days < 30:
                    self.tg.send_message(chat_id, "⏳ జిల్లా 30 రోజులకి ఒకసారే మార్చవచ్చు."); return
            except Exception:
                pass
            m["district"], m["state_code"] = d, (D.state_of(d) or "AP")
            m["mandal"] = ""; m["district_changed"] = datetime.now(config.IST).isoformat(); self.members.kv.save()
            self.tg.send_message(chat_id, f"✅ జిల్లా మారింది → {d} ({D.telugu_name(d)}). /offers, /district, District War అన్నీ ఇప్పుడు {d} కి.")
        elif low.startswith("/whatsapp") and str(uid) in self._staff_ids():
            from core import partners
            self.tg.send_message(chat_id, partners.whatsapp_post(self.members) or "No active offers.")
        elif low.startswith("/examdone"):
            from core import partners
            if not self.members.is_registered(uid):
                self.tg.send_message(chat_id, "ముందు register అవ్వండి → /start"); return
            parts = low.split()
            exam = parts[1].upper() if len(parts) > 1 else (self.members.members.get(str(uid), {}).get("exam") or "").upper()
            if not exam:
                self.tg.send_message(chat_id, "Usage: /examdone TSPSC  (ఏ exam రాశారో)"); return
            ok, txt = partners.exam_checkin(self.members, uid, exam)
            self.tg.send_message(chat_id, txt)
        elif low.startswith("/mystats"):
            from core import partners
            self.tg.send_message(chat_id, partners.merchant_dashboard(uid))
        elif low.startswith("/pcancel"):
            from core import partners
            parts = low.split()
            self.tg.send_message(chat_id, partners.cancel(uid, parts[1]) if len(parts) > 1 else "Usage: /pcancel PT-XXXXXX")
        elif low.startswith("/pverify"):
            from core import partners
            parts = text.split()
            if len(parts) < 2:
                self.tg.send_message(chat_id, "Usage: /pverify PT-XXXXXX  (shop counter లో)")
            else:
                res = partners.verify(self.members, parts[1], uid, self._staff_ids())
                self.tg.send_message(chat_id, res)
                if res.startswith("✅"):
                    from core.partners import _load as _pl
                    v = _pl()["vouchers"].get(parts[1].upper().strip())
                    if v:
                        try:
                            self.tg.send_message(v["uid"], f"✅ Voucher {v['code']} used — enjoy! ⭐ {v['pts']} pts deducted. మళ్ళీ సంపాదించండి → /quiz")
                        except TelegramError:
                            pass
        elif low.startswith("/noads"):
            m = self.members._get(uid); m["no_ads"] = not m.get("no_ads"); self.members.kv.save()
            self.tg.send_message(chat_id, "🔕 Partner offer DMs off. మళ్ళీ on: /noads" if m["no_ads"] else "🔔 Partner offer DMs on.")
        elif low.startswith("/partner"):
            from core import partners
            parts = text.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else ""
            rest = parts[2] if len(parts) > 2 else ""
            if sub == "apply":
                if not rest:
                    self.tg.send_message(chat_id, "🤝 మీ business StudentUp partner అవ్వాలంటే:\n/partner apply <business పేరు> | <జిల్లా> | <coaching/books/food/salon/shop/hostel/tech/health> | <phone>\n\n"
                                                  "మీ ad మా Telegram channels లో + ఆ జిల్లా students DM లో; students points తో మీ offer claim చేస్తారు; exam-day specials కూడా.")
                else:
                    from core import social
                    self.tg.send_message(chat_id, partners.apply_partner(uid, rest) + "\n\n" + social.partner_kit())
                    for aid in self._staff_ids():
                        try:
                            self.tg.send_message(aid, f"📥 Partner application from {uid} ({self._name(who)}):\n{rest}")
                        except TelegramError:
                            pass
            elif str(uid) not in self._staff_ids():
                self.tg.send_message(chat_id, "🤝 Business owner? → /partner apply\n(management commands are admin-only)")
            elif sub == "add":
                f = [x.strip() for x in rest.split("|")]
                if len(f) < 3:
                    self.tg.send_message(chat_id, "Usage: /partner add <name> | <district / TS / AP / ALL> | <category> | <phone> | <merchant_tg_id> | <address> | [mandal]")
                else:
                    pid = partners.add_partner(f[0], f[1], f[2], f[3] if len(f) > 3 else "", f[4] if len(f) > 4 else "", f[5] if len(f) > 5 else "",
                                               mandal=f[6] if len(f) > 6 else "")
                    self.tg.send_message(chat_id, f"✅ Partner {pid} added. Now: /partner offer {pid} | <title_te> | <title_en> | <pts> | <kind discount/freebie/examday> | <exam> | <from YYYY-MM-DD> | <to> | <cta>")
            elif sub == "offer":
                f = [x.strip() for x in rest.split("|")]
                if len(f) < 4:
                    self.tg.send_message(chat_id, "Usage: /partner offer <PID> | <title_te> | <title_en> | <pts> | [kind] | [exam] | [from] | [to] | [cta]")
                else:
                    oid = partners.add_offer(f[0], f[1], f[2], int(f[3]), kind=(f[4] if len(f) > 4 and f[4] else "discount"),
                                             exam=(f[5] if len(f) > 5 else ""), exam_from=(f[6] if len(f) > 6 else ""),
                                             exam_to=(f[7] if len(f) > 7 else ""), cta=(f[8] if len(f) > 8 else ""))
                    self.tg.send_message(chat_id, f"✅ Offer {oid} live — rotates in ad slots + DMs to that district." if oid else "Partner id not found.")
            elif sub == "merchant":
                f = rest.split()
                ok = partners.set_merchant(f[0], f[1]) if len(f) == 2 else False
                self.tg.send_message(chat_id, "✅ merchant can now /pverify" if ok else "Usage: /partner merchant <PID> <telegram_user_id>")
            elif sub == "stats":
                self.tg.send_message(chat_id, partners.partner_stats(rest.strip()))
            elif sub == "flash":
                from core.engine import Engine
                f = [x.strip() for x in rest.split("|")]
                if len(f) < 6:
                    self.tg.send_message(chat_id, "Usage: /partner flash <PID> | <title_te> | <title_en> | <pts> | <hours> | <stock>")
                else:
                    oid = partners.add_offer(f[0], f[1], f[2], int(f[3]), flash_hours=int(f[4]), total=int(f[5]), per_member=1)
                    if oid:
                        n = Engine(dry=self.dry).partner_ad()
                        self.tg.send_message(chat_id, f"⚡ Flash offer {oid} live for {f[4]}h, stock {f[5]} — posted now ({n} ads)")
                    else:
                        self.tg.send_message(chat_id, "Partner not found.")
            elif sub == "photo":
                # reply to a photo with /partner photo <PID>  (or send photo with caption "/partner photo PID")
                ph = (msg.get("reply_to_message") or {}).get("photo") or msg.get("photo") or []
                ok = partners.set_photo(rest.strip(), ph[-1]["file_id"]) if ph and rest.strip() else False
                self.tg.send_message(chat_id, "✅ photo set — next ad slot uses it" if ok else "Reply to a photo with: /partner photo <PID>")
            elif sub == "preview":
                self.tg.send_message(chat_id, partners.digest_for_channel(self.members) or "No active offers.")
            elif sub == "weekly":
                from core.engine import Engine
                self.tg.send_message(chat_id, f"sent {Engine(dry=self.dry).partner_weekly()} merchant reports")
            elif sub == "examday":
                from core.engine import Engine
                self.tg.send_message(chat_id, f"prompted {Engine(dry=self.dry).examday_checkins()} students")
            elif sub in ("on", "off"):
                partners.toggle_partner(rest.strip(), sub == "on"); self.tg.send_message(chat_id, "done")
            elif sub == "ad":
                eng_txt = self._ad_now()
                self.tg.send_message(chat_id, eng_txt)
            else:
                self.tg.send_message(chat_id, partners.list_partners() + "\n\nCommands: add (district/TS/AP/ALL + mandal) · offer · flash · photo · preview · merchant · stats <PID> · on/off <PID> · ad (post now) · weekly · examday")
        elif low.startswith("/wallet") or low.startswith("/points"):
            from core import rewards
            self.tg.send_message(chat_id, rewards.render_wallet(self.members, uid))
        elif low.startswith("/redeem") or low.startswith("/offers"):
            from core import rewards
            if not self.members.is_registered(uid):
                self.members.start_registration(uid, username=self._name(who))
                self.tg.send_message(chat_id, FIRST_TIME_ASK)
                return
            b = rewards.balance(self.members, uid)
            self.tg.send_message(chat_id, f"🎁 Offers — మీ balance {b['available']} pts (≈ ₹{b['rupees']})\n"
                                          "✅ = ఇప్పుడు తీసుకోవచ్చు · 🔒 = ఇంకా points కావాలి",
                                 buttons=rewards.offer_buttons(self.members, uid))
        elif low.startswith("/cancel"):
            from core import rewards
            parts = low.split()
            self.tg.send_message(chat_id, rewards.cancel(self.members, uid, parts[1]) if len(parts) > 1
                                 else "Usage: /cancel SU-XXXXXX")
        elif low.startswith("/verify") or low.startswith("/vouchers"):
            from core import rewards
            if str(uid) not in self._staff_ids():
                self.tg.send_message(chat_id, "🔒 Centre staff only.\n⤷ సెంటర్ స్టాఫ్ కోసం మాత్రమే.")
                return
            parts = text.split()
            if low.startswith("/vouchers") or len(parts) < 2:
                self.tg.send_message(chat_id, rewards.admin_summary() + "\n\nUsage: /verify SU-XXXXXX")
                return
            res = rewards.verify(self.members, parts[1], staff_uid=uid)
            self.tg.send_message(chat_id, res)
            if res.startswith("✅"):
                from core.rewards import _ledger
                v = _ledger()["vouchers"].get(parts[1].upper().strip())
                note = rewards.member_voucher_note(self.members, v["uid"], v["code"]) if v else None
                if note:
                    try:
                        self.tg.send_message(v["uid"], note)
                    except TelegramError:
                        pass
        elif low.startswith("/challenge") or low.startswith("/beat"):
            self._start_challenge(uid, chat_id)
        elif low.startswith("/report"):
            from core import growth
            txt = growth.weekly_report(self.members, uid) or \
                "📋 ఈ వారం ఇంకా rounds ఆడలేదు — /quiz ఆడండి, ఆదివారం రాత్రి report వస్తుంది."
            self.tg.send_message(chat_id, txt)
        elif low.startswith("/invite") or low.startswith("/refer"):
            bu = config.BOT_USERNAME or (self._me_username() or "")
            link = f"https://t.me/{bu}?start=ref{uid}" if bu else "(set BOT_USERNAME in .env)"
            p = self.members.profile(uid) or {}
            from core import partners
            self.tg.send_message(chat_id, partners.referral_explainer(uid, link) +
                                 f"\n\nReferrals: {p.get('referrals', 0)} · activated: {p.get('ref_activated', 0)}")
        elif low.startswith("/districts"):
            self.tg.send_message(chat_id, self.members.render_district_board(), parse_mode="Markdown")
        elif low.startswith("/district"):
            parts = text.split(maxsplit=1)
            d = None
            if len(parts) > 1:
                from core import districts as D
                d = D.match_district("TS", parts[1]) or D.match_district("AP", parts[1])
            if not d:
                prof = self.members.profile(uid) if uid else None
                d = (prof or {}).get("district")
            if not d:
                self.tg.send_message(chat_id, "Send /district <name> or /register with your district.\n⤷ /register లో జిల్లా ఇవ్వండి.")
            else:
                self.tg.send_message(chat_id, self.members.render_district_board(d), parse_mode="Markdown")
        elif low.startswith("/review") or low.startswith("/revise"):
            due = self.members.due_reviews(uid) if uid else []
            if not due:
                self.tg.send_message(chat_id,
                    "✅ No revision questions due — answer a few /quiz, missed ones come back automatically.\n"
                    "⤷ రివిజన్ ప్రశ్నలు లేవు. /quiz ఆడండి.")
            else:
                self.send_quiz_to(chat_id, None, uid=uid, adaptive=True)
        elif low.startswith("/coach") or low.startswith("/trick") or low.startswith("/lesson"):
            parts = low.split()
            ch = parts[1].upper() if len(parts) > 1 and parts[1].upper() in config.PUBLIC_CHANNELS else None
            lesson = self._coach_lesson(ch)
            if lesson:
                self.tg.send_message(chat_id, lesson)
        elif low.startswith("/badges"):
            self.tg.send_message(chat_id, self._render_badges(uid))
        elif low.startswith("/analytics") or low.startswith("/admin"):
            if str(uid) == str(config.ADMIN_ID) or not config.ADMIN_ID:
                self.tg.send_message(chat_id, self.members.render_analytics(),
                                     parse_mode="Markdown")
            else:
                self.tg.send_message(chat_id, "🔒 Admin only.\n⤷ అడ్మిన్ కోసం మాత్రమే.")
        elif low.startswith("/stats") or low.startswith("/profile") or low.startswith("/me"):
            if not self.members.profile(uid):
                self.tg.send_message(chat_id, "You're not registered yet — send /register to start! ⭐\n⤷ /register చేయండి.")
            else:
                self.tg.send_message(chat_id, self.members.render_profile(uid))
        elif low.startswith("/rank") or low.startswith("/leaderboard") or low.startswith("/top"):
            parts = low.split()
            ch = parts[1].upper() if len(parts) > 1 else ""
            ch = {"BANK": "BANKING", "RRB": "RAILWAY", "UPSC": "SSC", "CA": "CURRENT", "GROUPS": "TSPSC"}.get(ch, ch)
            if ch in config.PUBLIC_CHANNELS:
                from core import examboard
                mode = parts[2] if len(parts) > 2 else ""
                if mode.startswith("dist"):
                    self.tg.send_message(chat_id, examboard.render_districts(self.members, ch, "week"))
                else:
                    self.tg.send_message(chat_id, examboard.render_board(self.members, ch, "week" if mode == "week" else "today")
                                         or f"{ch}: ఈరోజు ఇంకా rounds లేవు — /top {ch.lower()} week చూడండి")
            elif len(parts) > 1 and parts[1] not in ("week", "today"):
                self.tg.send_message(chat_id, "Usage: /top tspsc | appsc | banking | railway | police | defence | ssc | current  [week | districts]")
            else:
                self.tg.send_message(chat_id, self.members.render_leaderboard(), parse_mode="Markdown")
        elif low.startswith("/verify"):
            from core.verifier import status_text as vstat, run as vrun
            parts = low.split()
            if len(parts) > 1 and parts[1] == "run":
                st = vrun(limit=40)
                self.tg.send_message(chat_id, f"🔎 verify run: {st}")
            else:
                self.tg.send_message(chat_id, vstat())
        elif low.startswith("/supply"):
            from core.resilience import status_text as _sup
            self.tg.send_message(chat_id, _sup())
        elif low.startswith("/scout"):
            from core.scout import status_text as _scout_status
            self.tg.send_message(chat_id, _scout_status())
        elif low.startswith("/pyq") and len(low.split()) > 1 and low.split()[1] == "papers" and str(uid) in self._staff_ids():
            # official paper PDF list per channel → paste into NotebookLM as sources
            from core.pyq import load_papers
            ch = low.split()[2].upper() if len(low.split()) > 2 else ""
            papers = [p for p in load_papers() if not ch or p.get("channel") == ch]
            if not papers:
                self.tg.send_message(chat_id, "usage: /pyq papers TSPSC (APPSC SSC BANKING RAILWAY POLICE DEFENCE)")
            else:
                lines = [f"{p.get('channel')} · {p.get('exam')} {p.get('year')} · {p.get('paper', '')}\n{p.get('url') or p.get('index')}" for p in papers]
                body = "\n\n".join(lines)
                if len(body) > 3500:
                    self.tg.send_document(chat_id, f"pyq_papers_{ch or 'all'}.txt", body.encode("utf-8"),
                                          caption=f"📜 {len(papers)} official paper PDFs — NotebookLM లో upload చేయండి → /notebook prompt {ch or 'TSPSC'}")
                else:
                    self.tg.send_message(chat_id, f"📜 {len(papers)} official papers\n\n" + body)
        elif low.startswith("/pyq"):
            from core.pyq import status_text
            from core.question_bank import Bank
            b = self.bank
            qs = getattr(b, "questions", None) or getattr(b, "_questions", None) or []
            npyq = sum(1 for q in qs if q.get("source") == "pyq" and q.get("year"))
            self.tg.send_message(chat_id, status_text() + f"\n\n🏦 Bank: {len(qs)} questions · {npyq} with exam+year provenance")
        elif low.startswith("/hof") or low.startswith("/halloffame"):
            self.tg.send_message(chat_id, self.members.monthly_hall_of_fame() or "No rounds yet this month.")
        elif low.startswith("/crm") or low.startswith("/export") or low.startswith("/broadcast") \
                or low.startswith("/syncsheet") or low.startswith("/setupsheet"):
            if config.ADMIN_ID and str(uid) != str(config.ADMIN_ID):
                self.tg.send_message(chat_id, "🔒 Admin only.\n⤷ అడ్మిన్ కోసం మాత్రమే.")
                return
            from core import crm
            if low.startswith("/setupsheet"):
                pg = crm.ping()
                status = (f"✅ connected — {pg.get('members', 0)} rows in Sheet" if pg.get("ok")
                          else f"⚠️ not connected ({pg.get('error')})")
                self.tg.send_message(chat_id, SHEET_SETUP.format(view=config.SHEET_URL_VIEW, status=status))
                return
            if low.startswith("/crm"):
                self.tg.send_message(chat_id, crm.segment_summary(self.members.members), parse_mode="Markdown")
            elif low.startswith("/syncsheet"):
                n = self.members.sync_sheet_all()
                self.tg.send_message(chat_id, f"📊 Sheet sync: {n} members pushed." if crm.sheet_enabled()
                                     else "⚠️ SHEET_WEBAPP_URL not set — see docs/sheet_webapp.gs")
            elif low.startswith("/export"):
                data = crm.export_csv(self.members.members)
                fn = f"studentup_members_{datetime.now(config.IST):%Y%m%d}.csv"
                self.tg.send_document(chat_id, fn, data,
                                      caption=f"👥 {self.members.count_form()} registered members — name, mobile, district, exam, points")
            else:
                # /broadcast district=Warangal exam=TSPSC <message text>
                seg_part, _, msg = text.partition("\n") if "\n" in text else (text, "", "")
                seg = crm.parse_segment(seg_part)
                if not msg:
                    # allow one-line form: /broadcast key=val key=val message words…
                    words = text.split()[1:]
                    kv = [w for w in words if "=" in w]
                    msg = " ".join(w for w in words if "=" not in w)
                    seg = crm.parse_segment(" ".join(kv))
                if not msg.strip():
                    self.tg.send_message(chat_id, "Usage:\n/broadcast district=Warangal exam=TSPSC active=7 mobile=yes\n<message>\n"
                                                  "Filters optional: district, state (TS/AP), exam, active=<days>, minpoints, mobile=yes")
                    return
                targets = crm.select(self.members.members, seg)
                sent = 0
                for t in targets:
                    try:
                        self.tg.send_message(t, msg)
                        sent += 1
                    except TelegramError:
                        self.members.mark_blocked(t)
                    if sent % 25 == 0:
                        import time as _t
                        _t.sleep(1.2)
                self.tg.send_message(chat_id, f"📣 Broadcast sent to {sent}/{len(targets)} members (segment: {seg or 'all'})")
        elif low.startswith("/members") or low.startswith("/count"):
            n_bot = self.members.count()
            n_all = self.members.count_form()
            self.tg.send_message(chat_id,
                f"👥 Registered members: {n_all} (in-bot active: {n_bot})\n"
                f"⤷ నమోదైన సభ్యులు: {n_all}")
        elif low.startswith("/channels"):
            self.tg.send_message(chat_id, self._channels_list())
        elif low.startswith("/") and chat_id == str(uid):
            # unknown command or a staff-only command sent by a student → friendly menu instead of silence
            cmd = low.split()[0].split("@")[0]
            self.tg.send_message(chat_id, f"🤔 {cmd} నాకు తెలియదు లేదా staff కోసం మాత్రమే.\n\n"
                                          "ముఖ్యమైనవి:\n• /quiz — practice · /coach — weak topics\n• /wallet /offers — points & discounts\n"
                                          "• /rank /card — మీ rank, report card\n• /squad — friends తో · /war — 9 PM District War\n"
                                          "• /jobs — notifications · /help — అన్నీ")

    def _render_badges(self, uid):
        p = self.members.profile(uid) if uid else None
        if not p:
            return ("No profile yet — send /register to start earning badges! 🏅\n"
                    "⤷ /register చేసి బ్యాడ్జ్‌లు సంపాదించండి!")
        earned = {b["id"]: b for b in self.members._earned_badges(
            self.members.members[str(uid)])}
        # include already-earned stored
        for b in self.members._all_badge_defs():
            pass
        profile_m = self.members.members[str(uid)]
        earned_ids = set(profile_m.get("badges", []))
        lines = ["🏅 *Your badges / మీ బ్యాడ్జ్‌లు*", ""]
        all_defs = [
            ("first", "🎯", "First Answer", "మొదటి సమాధానం"),
            ("correct10", "✅", "10 Correct", "10 సరైనవి"),
            ("correct100", "💯", "100 Correct (Century)", "100 సరైనవి"),
            ("streak3", "🔥", "3-Day Streak", "3 రోజుల స్ట్రీక్"),
            ("streak7", "🔥", "7-Day Streak", "7 రోజుల స్ట్రీక్"),
            ("streak30", "🔥", "30-Day Streak", "30 రోజుల స్ట్రీక్"),
            ("sharp", "🧠", "Sharp Shooter (90%+)", "90%+ ఖచ్చితత్వం"),
            ("champion", "👑", "Champion", "ఛాంపియన్"),
        ]
        for bid, icon, en, te in all_defs:
            mark = earned_ids and bid in earned_ids
            lines.append(f"{'✅' if mark else '⬜'} {icon} {en} / {te}")
        lines.append("\nKeep playing /quiz to unlock them all! ⭐")
        return "\n".join(lines)

    def _channels_list(self):
        lines = ["📚 *StudentUp daily channels*\n"]
        for k in config.PUBLIC_CHANNELS:
            c = config.CHANNELS[k]
            lines.append(f"{c['emoji']} {c['title']}")
        lines.append(f"{config.CHANNELS['JOBS']['emoji']} {config.CHANNELS['JOBS']['title']}")
        lines.append("\n2 quiz rounds daily: ⛅ 07:30 & 🌙 19:30 IST")
        return "\n".join(lines)

    # ------------------------------------------------------------ poll answers
    def handle_poll_answer(self, upd):
        pa = upd.get("poll_answer") or {}
        uid = pa.get("user", {}).get("id")
        poll_id = pa.get("poll_id")
        chosen = pa.get("option_ids")
        if not (uid and poll_id is not None and chosen):
            return
        user = pa.get("user", {})
        # 🎓 Campus event polls
        try:
            from core import campus
            if campus.record_answer(poll_id, uid, int(chosen[0])):
                return
        except Exception as e:
            print(f"[campus] answer error: {e}")
        # ⚔️ District War polls
        try:
            from core import districtwar
            if districtwar.record_answer(poll_id, uid, int(chosen[0])):
                return
        except Exception as e:
            print(f"   [war] {e}")
        # ⚔️ Squad Battle Arena polls
        try:
            from core import arena
            if arena.record_answer(self.members, self.tg, poll_id, uid, int(chosen[0]), bank=self.bank):
                return
        except Exception as e:
            print(f"   [arena] {e}")
        # 🥊 Beat-the-Topper challenge polls (replays; no points per question)
        try:
            from core import growth
            is_ch, res = growth.record_answer(self.members, poll_id, uid, int(chosen[0]))
            if is_ch:
                if res:
                    self.tg.send_message(uid, res)
                return
        except Exception as e:
            print(f"   [challenge] {e}")
        meta = self._poll_q.get(str(poll_id))
        round_id = None
        if not meta:
            # Round poll mirrored to DM by the engine (data/round_polls.json)
            rp = self._round_polls().get(str(poll_id))
            if not rp:
                return
            round_id, ch, qid, correct_idx, topic = rp[0], rp[1], rp[2], rp[3], (rp[5] if len(rp) > 5 else "")
        else:
            ch, qid, correct_idx = meta[0], meta[1], meta[2]
            topic = meta[3] if len(meta) > 3 else ""
        is_correct = int(chosen[0]) == int(correct_idx)
        # First-time player? Ask for registration ONCE (name → district → mobile).
        # The answer still counts; the ask is never repeated after completion.
        first_ask = False
        if uid and not self.members.is_registered(uid) and not self.members.pending_step(uid):
            self.members.start_registration(uid, username=self._name(user))
            self.members.register_default_exam(uid, self._channel_to_exam(ch))
            first_ask = True
        if round_id:
            e = self.members.record_round_answer(uid, round_id, ch, is_correct, qid=qid)
            if e and e.get("total") == 1:      # first answer of a round → counts as a round played
                try:
                    from core import partners
                    act = partners.on_round_played(self.members, uid)
                    if act:
                        self.tg.send_message(act["referrer"],
                                             f"🎉 మీ friend {act['name']} active అయ్యారు (3 rounds) → +{act['bonus']} pts! "
                                             f"Activated referrals: {act['activated']}")
                except Exception:
                    pass
        result = self.members.award_answer(
            uid, username=self._name(user),
            correct=is_correct, topic=topic, qid=qid)
        if result.get("locked"):
            # 🔒 unregistered: points are held. First time → full ask; later → short nudge.
            try:
                if first_ask:
                    self.tg.send_message(uid, LOCKED_FIRST.format(pts=result["locked"]))
                elif self.members.pending_step(uid) and result["locked"] % 30 == 0:
                    self.tg.send_message(uid, LOCKED_NUDGE.format(pts=result["locked"]))
            except TelegramError:
                pass
            return
        if round_id:
            return   # DM round poll: Telegram already shows ✅/❌ + explanation
        # Private feedback to the player (DMs only — groups can't DM via poll)
        note = None
        if result.get("new_badges"):
            b = result["new_badges"][0]
            note = (f"{b['icon']} Badge unlocked: *{b['en']}* / {b['te']}!\n"
                    f"⤷ కొత్త బ్యాడ్జ్: {b['te']}! బాగుంది! 🏅")
        elif result["level_up"]:
            lu = result["level_up"]
            note = (f"🎉 Level up! You are now {lu['icon']} {lu['title_en']} ({lu['title_te']})!\n"
                    f"⤷ మీరు ఇప్పుడు {lu['icon']} {lu['title_te']}! అభినందనలు!")
        elif is_correct:
            note = (f"✅ Correct! +{result['earned']} points (total ⭐{result['points']}). "
                    f"Streak 🔥{result['streak']} day(s).\n"
                    f"⤷ సరైనది! +{result['earned']} పాయింట్లు.")
        else:
            note = (f"❌ Not this time — but you earned +{result['earned']} activity points. "
                    f"This question will come back for revision 🔁. Try /quiz again!\n"
                    f"⤷ ఈసారి కాదు — ఇది రివిజన్‌కి తిరిగి వస్తుంది. మళ్లీ /quiz ఆడండి.")
        try:
            self.tg.send_message(pa.get("user", {}).get("id"), note)
        except TelegramError:
            pass  # user hasn't started the bot in DM — ignore

    # ------------------------------------------------------------ run
    def run(self):
        self._load_polls()
        print("STUDENTUP interactive bot — long-polling (Ctrl-C to stop)")
        if self.dry:
            print("(dry run — not polling)")
            return
        while True:
            try:
                live = False
                try:      # ⚔️ advance live battle rooms; poll fast while a match runs
                    from core import arena
                    arena.tick(self.bank, self.tg, self.members)
                    live = any(r["state"] in ("countdown", "question", "gap")
                               for r in arena._load()["rooms"].values())
                    from core import districtwar
                    districtwar.maybe_auto_start(self.bank, self.members, self.tg)
                    if districtwar.tick(self.tg, self.members):
                        live = True
                    from core import campus
                    try:
                        from core import roster as _R
                        _R.auto_start_due(self.bank, self.members, self.tg)
                    except Exception:
                        pass
                    if campus.tick(self.tg, self.members):
                        live = True
                    try:      # 🏆 College Cup: next-round / champion announcements
                        from core import cup as C
                        for an in C.pop_announces():
                            if an.get("to") == "hub":
                                for ch in getattr(config, "CHAMPION_CHANNELS", ["CURRENT"]):
                                    try:
                                        self.tg.send_message(config.channel_chat_id(ch), an["text"])
                                    except TelegramError:
                                        pass
                            for aid in self._staff_ids():
                                try:
                                    self.tg.send_message(aid, an["text"])
                                except TelegramError:
                                    pass
                    except Exception as e:
                        print(f"[cup] announce note: {e}")
                except Exception as e:
                    print(f"[arena] tick error: {e}")
                for upd in self.tg.get_updates(timeout=3 if live else 50):
                    if "message" in upd:
                        try:
                            self.handle_message(upd["message"])
                        except TelegramError as e:
                            print("message error:", e)
                    elif "callback_query" in upd:
                        try:
                            self.handle_callback(upd["callback_query"])
                        except Exception as e:
                            print(f"[bot] callback error: {e}")
                    elif "poll_answer" in upd:
                        try:
                            self.handle_poll_answer(upd)
                        except Exception as e:
                            print("poll answer error:", e)
                    elif "poll" in upd:
                        try:      # channel poll vote totals → miss-rate per question
                            from core.leaderboard import Leaderboard
                            Leaderboard().record_poll_totals(upd["poll"])
                        except Exception as e:
                            print("poll totals error:", e)
            except Exception as e:
                print("poll loop error:", e)
                time.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    Bot(dry=args.dry).run()


if __name__ == "__main__":
    main()
