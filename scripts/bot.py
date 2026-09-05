#!/usr/bin/env python3
"""
STUDENTUP — INTERACTIVE BOT (group + DM)
Long-polls getUpdates and serves:
  /start, /help     welcome + how it works (EN + Telugu)
  /quiz [channel]   one non-anonymous quiz poll to the current chat
  /stats            your accuracy + streak
  /leaderboard      weekly top scorers
When non-anonymous quiz polls are answered (groups), answers are recorded
into the leaderboard/streak engine.
Channel auto-posting is handled by watch.py; this handles live interaction.
Usage:
  python3 bot.py                 # long-poll loop (production)
  python3 bot.py --dry           # print updates without posting
"""
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import config
from core.telegram import Telegram, TelegramError
from core.engine import Engine
from core.question_bank import Bank
from core.content import build_question_text, build_options, build_explanation
from core.leaderboard import Leaderboard

WELCOME = (
    "👋 Welcome to StudentUp — India's advanced daily quiz coach for "
    "TS & AP aspirants (TSPSC, APPSC, Banking, Railway, Police, Defence, GK)!\n\n"
    "📌 Commands:\n"
    "• /quiz — one practice question\n"
    "• /stats — your accuracy & 🔥 streak\n"
    "• /leaderboard — weekly toppers\n"
    "• /help — how it works\n\n"
    "⤷ ప్రతిరోజూ క్విజ్ రాయండి, స్ట్రీక్ కొనసాగించండి! TSPSC/APPSC/బ్యాంక్/రైల్వే/పోలీస్/డిఫెన్స్.\n"
    "Answer polls in your study group to earn your rank 🏆"
)

HELP = (
    "ℹ️ How it works:\n"
    "1. Join the daily channels — 5 quiz slots (07:30,10:30,13:30,16:30,19:30 IST).\n"
    "2. Tap the right option — quiz polls give instant feedback + explanation.\n"
    "3. In groups, /quiz polls are tracked for the weekly leaderboard & streaks.\n"
    "4. 21:30 = Current Affairs digest; 14:30 = study tip; jobs every 30 min.\n\n"
    "⤷ రోజూ 5 స్లాట్‌లలో ప్రాక్టీస్ చేయండి; సరైన జవాబు ట్యాప్ చేస్తే వెంటనే వివరణ వస్తుంది. "
    "7 రోజుల స్ట్రీక్ పూర్తి చేస్తే లీడర్‌బోర్డ్‌లో చోటు! 🔥"
)


class Bot:
    def __init__(self, dry=False):
        self.tg = Telegram(dry=dry)
        self.bank = Bank()
        self.lb = Leaderboard()
        self.dry = dry

    def _name(self, user):
        return (user.get("username") or
                " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or
                str(user.get("id")))

    def send_quiz_to(self, chat_id, channel=None):
        ch = channel if channel in config.PUBLIC_CHANNELS else "TSPSC"
        qs = self.bank.pick(ch, 1)
        if not qs:
            return
        q = qs[0]
        cfg = config.CHANNELS[ch]
        text = build_question_text(q, cfg)
        opts = build_options(q)
        expl = build_explanation(q)
        payload = {
            "chat_id": chat_id, "question": text,
            "options": [{"text": o} for o in opts], "type": "quiz",
            "is_anonymous": False,            # track users for leaderboard
            "allows_multiple_answers": False,
            "correct_option_id": q["answer_index"], "open_period": 300,
        }
        if expl.strip():
            payload["explanation"] = expl[:config.TG_POLL_EXPLANATION_MAX]
        res = self.tg._call("sendPoll", payload)
        poll = res.get("result", {}).get("poll") or {}
        if poll.get("id"):
            self.lb.register_poll(poll["id"], q["answer_index"], ch, q["id"])

    def handle_message(self, msg):
        chat_id = str(msg["chat"]["id"])
        text = (msg.get("text") or "").strip().lower()
        who = msg.get("from", {})
        if text.startswith("/start"):
            self.tg.send_message(chat_id, WELCOME)
        elif text.startswith("/help"):
            self.tg.send_message(chat_id, HELP)
        elif text.startswith("/quiz"):
            parts = text.split()
            ch = parts[1].upper() if len(parts) > 1 else None
            self.send_quiz_to(chat_id, ch)
        elif text.startswith("/stats") or text.startswith("/mystats"):
            self.tg.send_message(chat_id, self.lb.render_user(who.get("id")))
        elif text.startswith("/leaderboard") or text.startswith("/rank"):
            self.tg.send_message(chat_id, self.lb.render_weekly())
        elif text.startswith("/channels"):
            self.tg.send_message(chat_id, self._channels_list())

    def _channels_list(self):
        lines = ["📚 StudentUp daily channels:\n"]
        for k in config.PUBLIC_CHANNELS:
            c = config.CHANNELS[k]
            lines.append(f"{c['emoji']} {c['title']}")
        lines.append(f"{config.CHANNELS['JOBS']['emoji']} {config.CHANNELS['JOBS']['title']}")
        return "\n".join(lines)

    def handle_poll_answer(self, upd):
        pa = upd.get("poll_answer") or {}
        uid = pa.get("user", {}).get("id")
        poll_id = pa.get("poll_id")
        chosen = pa.get("option_ids")
        if uid and poll_id is not None and chosen is not None and chosen:
            correct = self.lb.record_answer(poll_id, uid,
                                            self._name(pa.get("user", {})),
                                            chosen[0])
            if correct is not None and correct:
                u = self.lb.user_card(uid)
                if u and u["streak"] and u["streak"] % 7 == 0:
                    try:
                        self.tg.send_message(
                            pa.get("user", {}).get("id"),
                            f"🔥 {u['streak']}-day streak! Keep going — {u['name']}!\n"
                            f"⤷ {u['streak']} రోజుల స్ట్రీక్! కొనసాగించండి! 🎉")
                    except TelegramError:
                        pass

    def run(self):
        print("STUDENTUP interactive bot — long-polling getUpdates (Ctrl-C to stop)")
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
                        self.handle_poll_answer(upd)
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
