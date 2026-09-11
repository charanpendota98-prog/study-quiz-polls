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
  /report             📋 your weekly report card
  /district [name]    your district toppers   /districts  TS/AP district leaderboard
  /quiz [channel]     one NON-anonymous PYQ-first practice poll (earns points)
  /coach [channel]    a friendly expert reasoning/aptitude trick (EN+Telugu)
  /review             due spaced-repetition questions (missed ones come back)
  /badges             your earned achievement badges
  /stats /profile     your points, level, rank, accuracy, streak
  /rank /leaderboard  points-based top players
  /levels             points & level rules
Group quizzes via this bot are the ones that earn points (channel auto-polls
are anonymous by Telegram design); add the bot to your study group to compete.

Usage:
  python3 bot.py           # production long-poll loop
  python3 bot.py --dry
"""
from datetime import datetime
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
    "👋 Welcome to *StudentUp* — India's advanced daily quiz coach for "
    "TS & AP aspirants (TSPSC, APPSC, Banking, Railway, Police, Defence, GK)!\n\n"
    "⭐ Earn *points*, levels and ranks:\n"
    "• /register — join as a member (+25 pts)\n"
    "• /quiz — play a previous-paper question (+10 per correct)\n"
    "• /district — your district toppers · /districts — TS/AP district ranking\n"
    "• /coach — a friendly expert trick that makes reasoning & aptitude easy 🧠\n"
    "• /stats — your level, rank, points & streak\n"
    "• /leaderboard — top players\n"
    "• /levels — how points & ranks work\n\n"
    "⤷ రిజిస్టర్ చేసుకోండి, రోజూ క్విజ్ ఆడి పాయింట్లు సంపాదించి, ఛాంపియన్‌గా ఎదగండి! 🏆"
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

HELP = (
    "ℹ️ *How it works*\n"
    "1️⃣ /register once (name, exam target, language) — +25 bonus points.\n"
    "2️⃣ Send /quiz in this chat — answer the poll. Correct = +10 points.\n"
    "3️⃣ Play daily — first activity each day +5, and streak bonuses at "
    "3/7/15/30/100 days 🔥.\n"
    "4️⃣ /rank shows the weekly+all-time leaderboard; levels go Bronze→Champion 👑.\n"
    "5️⃣ /coach gives you a quick expert trick any time; channels also post a "
    "daily expert lesson at 12:30 IST 🧠.\n"
    "6️⃣ Channels post 2 big rounds daily (07:30 & 19:30 IST) + CA digest 21:30. "
    "Questions NEVER repeat and come only from real exam-paper sources.\n\n"
    "⤷ పాయింట్లు సంపాదించడానికి ఈ బాట్‌లో /quiz ఆడండి. ఛానెళ్లలో ప్రాక్టీస్, "
    "బాట్‌లో పాయింట్లు + ర్యాంక్! 🏆"
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
        if kind in ("state", "dist", "qual") and uid:
            st = self.members.pending_step(uid)
            expected = {"state": "state", "dist": "district", "qual": "qualification"}[kind]
            if st and st.get("step") == expected:
                status, reply = self.members.registration_input(uid, value)
                if reply:
                    self.tg.send_message(chat_id, reply, buttons=self._step_buttons(uid, status))
            elif self.members.is_registered(uid):
                self.tg.send_message(chat_id, "✅ Already registered — no need to fill again.\n⤷ ఇప్పటికే రిజిస్టర్ అయ్యారు.")

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
        text = (msg.get("text") or "").strip()
        low = text.lower()

        # Registration guided flow takes priority
        if uid and self.members.pending_step(uid) and not low.startswith("/"):
            status, reply = self.members.registration_input(uid, text)
            if reply:
                self.tg.send_message(chat_id, reply, buttons=self._step_buttons(uid, status))
            if status == "done":
                self.tg.admin_note = None
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
            self.tg.send_message(chat_id,
                f"🎁 Invite friends — each new registration = +20 points for you.\n"
                f"⤷ ఫ్రెండ్స్‌ని పిలవండి — ఒక్కొక్కరికి +20 పాయింట్లు.\n\n{link}\n\n"
                f"Referrals so far: {p.get('referrals', 0)}")
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
            self.tg.send_message(chat_id, self.members.render_leaderboard(),
                                 parse_mode="Markdown")
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
            self.members.record_round_answer(uid, round_id, ch, is_correct, qid=qid)
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
                for upd in self.tg.get_updates(timeout=50):
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
