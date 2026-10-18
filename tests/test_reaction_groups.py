#!/usr/bin/env python3
"""Emoji reaction polls — GROUPS end-to-end (owner: channels+groups only).

Guarantee under test: a Telegram GROUP target gets the same 👍❤️😂😮
reaction text-poll as a channel (never a native sendPoll), group members'
per-user reactions are counted (message_reaction carries the user in
groups), and the ✅ reveal lands back in the same group chat. The
dashboard hand-picked send must use the same channel/group style.
DM scoring paths are untouched (native polls — separate suites).
Run: python3 -m unittest discover -s tests -p "test_reaction_groups.py"
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import config, flags, item_intel, reaction_polls as rp  # noqa: E402

Q = {"id": "GQ1", "channel": "SSC", "topic": "Polity",
     "q_en": "Capital of India?", "q_te": "భారత రాజధాని?",
     "options_en": ["Delhi", "Mumbai", "Chennai", "Kolkata"],
     "options_te": ["ఢిల్లీ", "ముంబై", "చెన్నై", "కోలకాతా"],
     "answer_index": 0, "explanation_en": "Delhi is the capital."}
GROUP_KEY = "GRPTEST"
GROUP_CHAT = "-100555777"


class FakeTg:
    dry = True

    def __init__(self):
        self.calls = []

    def send_quiz(self, chat, text, opts, correct, expl, **kw):
        self.calls.append(("quiz", chat, text))
        return {"ok": True, "result": {"poll": {"id": "p1"}}}

    def send_message(self, chat, text, **kw):
        self.calls.append(("msg", chat, text))
        return {"ok": True, "result": {"message_id": 42}}


class TestGroupReactionPoll(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (rp.STORE_FILE, flags.FLAGS_FILE, item_intel.STATS_FILE)
        rp.STORE_FILE = self.tmp / "reaction_polls.json"
        rp._cache["mtime"] = None
        rp._cache["data"] = None
        flags.FLAGS_FILE = self.tmp / "feature_flags.json"
        item_intel.STATS_FILE = self.tmp / "item_stats.json"
        item_intel._cache["mtime"] = None
        item_intel._cache["data"] = {}
        # exactly how a dashboard-registered group lands in runtime config
        config.CHANNELS[GROUP_KEY] = {
            "emoji": "👥", "subject": "Study Group", "chat_type": "group",
            "chat_id": GROUP_CHAT, "public": True}

    def tearDown(self):
        rp.STORE_FILE, flags.FLAGS_FILE, item_intel.STATS_FILE = self._orig
        rp._cache["mtime"] = None
        rp._cache["data"] = None
        item_intel._cache["mtime"] = None
        config.CHANNELS.pop(GROUP_KEY, None)

    def test_group_default_is_direct_poll(self):
        from core.engine import Engine
        tg = FakeTg()
        eng = Engine(dry=True)
        eng.tg = tg
        # owner rule: Telegram groups get DIRECT polls by default
        self.assertTrue(eng._send_channel_question(GROUP_KEY, dict(Q)))
        self.assertEqual(tg.calls[-1][0], "quiz")

    def test_group_gets_emoji_poll_votes_and_reveal(self):
        from core.engine import Engine
        flags.set_flag("channel_reaction_polls", True)   # owner opt-in
        tg = FakeTg()
        eng = Engine(dry=True)
        eng.tg = tg

        # 1) post → TEXT message with the 4 emojis, NOT a native poll
        self.assertTrue(eng._send_channel_question(GROUP_KEY, dict(Q)))
        kind, chat, text = tg.calls[-1]
        self.assertEqual(kind, "msg")
        self.assertEqual(str(chat), GROUP_CHAT)
        for e in rp.REACTION_EMOJIS:
            self.assertIn(e, text)
        self.assertNotIn("quiz", [c[0] for c in tg.calls])
        self.assertIn(f"{GROUP_CHAT}:42", rp._load())

        # 2) group members react (per-user updates carry the user id)
        def upd(uid, emoji):
            return {"message_reaction": {
                "chat": {"id": int(GROUP_CHAT), "type": "supergroup"},
                "message_id": 42, "user": {"id": uid},
                "new_reaction": ([{"type": "emoji", "emoji": emoji}]
                                 if emoji else [])}}

        rp.apply_update(upd(11, "👍"))
        rp.apply_update(upd(12, "❤️"))
        rp.apply_update(upd(13, "👍"))
        rp.apply_update(upd(12, "👍"))          # change of mind counts once
        counts, total = rp.tally(rp._load()[f"{GROUP_CHAT}:42"])
        self.assertEqual((counts, total), ([3, 0, 0, 0], 3))

        # 3) after the window, reveal lands in the SAME group chat
        rec = rp._load()[f"{GROUP_CHAT}:42"]
        rec["closes"] = time.time() - 1
        rp._save(rp._load())
        out = rp.tick(tg)
        self.assertEqual(out["revealed"], 1)
        kind, chat, text = tg.calls[-1]
        self.assertEqual((kind, str(chat)), ("msg", GROUP_CHAT))
        self.assertIn("✅ Correct answer: 👍", text)
        self.assertIn("100% correct", text)


class TestHandPickedSendStyle(unittest.TestCase):
    def test_dashboard_handpicked_uses_channel_group_style(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        block = src.split('p.path == "/api/questions/send"', 1)[1][:1200]
        self.assertIn("_send_channel_question(send_key, q)", block)
        self.assertNotIn("eng.send_quiz(send_key", block)


if __name__ == "__main__":
    unittest.main()
