#!/usr/bin/env python3
"""
STUDENTUP — INTERACTIVE BOT (DM + study groups)
Long-polls getUpdates. Member registration, points, levels, ranks, leaderboard.

Commands:
  /start, /help       welcome (EN + Telugu)
  /register           guided sign-up (name -> exam target -> language) = +25 pts
  /quiz [channel]     one NON-anonymous PYQ-first practice poll (earns points)
  /stats /profile     your points, level, rank, accuracy, streak
  /rank /leaderboard  points-based top players
  /levels             points & level rules
Group quizzes via this bot are the ones that earn points (channel auto-polls
are anonymous by Telegram design); add the bot to your study group to compete.

Usage:
  python3 bot.py           # production long-poll loop
  python3 bot.py --dry
"""
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
    "• /stats — your level, rank, points & streak\n"
    "• /leaderboard — top players\n"
    "• /levels — how points & ranks work\n\n"
    "⤷ రిజిస్టర్ చేసుకోండి, రోజూ క్విజ్ ఆడి పాయింట్లు సంపాదించి, ఛాంపియన్‌గా ఎదగండి! 🏆"
)

HELP = (
    "ℹ️ *How it works*\n"
    "1️⃣ /register once (name, exam target, language) — +25 bonus points.\n"
    "2️⃣ Send /quiz in this chat — answer the poll. Correct = +10 points.\n"
    "3️⃣ Play daily — first activity each day +5, and streak bonuses at "
    "3/7/15/30/100 days 🔥.\n"
    "4️⃣ /rank shows the weekly+all-time leaderboard; levels go Bronze→Champion 👑.\n"
    "5️⃣ Channels post 2 big rounds daily (07:30 & 19:30 IST) + CA digest 21:30.\n\n"
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
    def send_quiz_to(self, chat_id, channel=None):
        ch = channel if channel in config.PUBLIC_CHANNELS else "TSPSC"
        qs = self.bank.pick(ch, 1)
        if not qs:
            return
        q = qs[0]
        cfg = config.CHANNELS[ch]
        tag = "📜 PYQ" if q.get("source") == "pyq" else "📝 Practice"
        text = f"{tag} {build_question_text(q, cfg)}"
        opts = build_options(q)
        expl = build_explanation(q)
        payload = {
            "chat_id": chat_id, "question": text[:300],
            "options": [{"text": o} for o in opts], "type": "quiz",
            "is_anonymous": False,               # track members for points
            "allows_multiple_answers": False,
            "correct_option_id": q["answer_index"], "open_period": 300,
        }
        if expl.strip():
            payload["explanation"] = expl[:config.TG_POLL_EXPLANATION_MAX]
        res = self.tg._call("sendPoll", payload)
        poll = res.get("result", {}).get("poll") or {}
        if poll.get("id"):
            self._poll_q[poll["id"]] = (ch, q["id"], q["answer_index"])
            self._save_polls()

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
                self.tg.send_message(chat_id, reply)
            if status == "done":
                self.tg.admin_note = None
            return

        if low.startswith("/start"):
            self.tg.send_message(chat_id, WELCOME, parse_mode="Markdown")
        elif low.startswith("/help"):
            self.tg.send_message(chat_id, HELP, parse_mode="Markdown")
        elif low.startswith("/levels") or low.startswith("/points"):
            self.tg.send_message(chat_id, LEVELS_TEXT, parse_mode="Markdown")
        elif low.startswith("/register") or low.startswith("/signup"):
            self.members.start_registration(uid, username=self._name(who))
            self.tg.send_message(
                chat_id,
                "📝 Registration — step 1 of 3.\nWhat is your full name?\n"
                "⤷ మీ పూర్తి పేరు పంపండి:")
        elif low.startswith("/cancel"):
            self.members.cancel_registration(uid)
            self.tg.send_message(chat_id, "Registration cancelled. /register to retry.\n⤷ రద్దు చేయబడింది.")
        elif low.startswith("/quiz"):
            parts = low.split()
            ch = parts[1].upper() if len(parts) > 1 else None
            self.send_quiz_to(chat_id, ch)
        elif low.startswith("/stats") or low.startswith("/profile") or low.startswith("/me"):
            if not self.members.profile(uid):
                self.tg.send_message(chat_id, "You're not registered yet — send /register to start! ⭐\n⤷ /register చేయండి.")
            else:
                self.tg.send_message(chat_id, self.members.render_profile(uid))
        elif low.startswith("/rank") or low.startswith("/leaderboard") or low.startswith("/top"):
            self.tg.send_message(chat_id, self.members.render_leaderboard(),
                                 parse_mode="Markdown")
        elif low.startswith("/members") or low.startswith("/count"):
            n = self.members.count()
            self.tg.send_message(chat_id, f"👥 Registered members: {n}\n⤷ నమోదైన సభ్యులు: {n}")
        elif low.startswith("/channels"):
            self.tg.send_message(chat_id, self._channels_list())

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
        meta = self._poll_q.get(str(poll_id))
        if not meta:
            return
        _ch, _qid, correct_idx = meta
        is_correct = int(chosen[0]) == int(correct_idx)
        result = self.members.award_answer(uid, username=self._name(pa.get("user", {})),
                                           correct=is_correct)
        # Private feedback to the player (DMs only — groups can't DM via poll)
        note = None
        if result["level_up"]:
            lu = result["level_up"]
            note = (f"🎉 Level up! You are now {lu['icon']} {lu['title_en']} ({lu['title_te']})!\n"
                    f"⤷ మీరు ఇప్పుడు {lu['icon']} {lu['title_te']}! అభినందనలు!")
        elif is_correct:
            note = (f"✅ Correct! +{result['earned']} points (total ⭐{result['points']}). "
                    f"Streak 🔥{result['streak']} day(s).\n"
                    f"⤷ సరైనది! +{result['earned']} పాయింట్లు.")
        else:
            note = (f"❌ Not this time — but you earned +{result['earned']} activity points. "
                    f"Try /quiz again!\n⤷ ఈసారి కాదు — మళ్లీ /quiz ఆడండి.")
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
