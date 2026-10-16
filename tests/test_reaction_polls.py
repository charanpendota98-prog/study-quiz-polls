#!/usr/bin/env python3
"""Reaction Text-Poll tests — 👍 ❤️ 😂 😮 channel answers (owner request).

Covers: text format (emoji options in order), vote tracking via both
Telegram update shapes (per-user message_reaction with change/remove,
anonymous message_reaction_count), tally math, timed reveal with
item-intel bulk learning, engine flag switch (reaction vs native), and
bot/telegram wiring. item_intel/flags/reaction stores are tmp-isolated.
Run: python3 -m unittest discover -s tests -p "test_reaction_polls.py"
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import flags, item_intel, reaction_polls as rp  # noqa: E402
from core.content import build_options, build_reaction_text  # noqa: E402

Q = {"id": "RQ1", "channel": "SSC", "topic": "Polity",
     "q_en": "Capital of India?", "q_te": "భారత రాజధాని?",
     "options_en": ["Delhi", "Mumbai", "Chennai", "Kolkata"],
     "options_te": ["ఢిల్లీ", "ముంబై", "చెన్నై", "కోలకాతా"],
     "answer_index": 0, "explanation_en": "Delhi is the capital."}
CFG = {"emoji": "🏛️", "subject": "SSC Exams"}


class TmpStores(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (rp.STORE_FILE, item_intel.STATS_FILE, flags.FLAGS_FILE)
        rp.STORE_FILE = self.tmp / "reaction_polls.json"
        rp._cache["mtime"] = None
        rp._cache["data"] = None
        item_intel.STATS_FILE = self.tmp / "item_stats.json"
        item_intel._cache["mtime"] = None
        item_intel._cache["data"] = {}
        flags.FLAGS_FILE = self.tmp / "feature_flags.json"

    def tearDown(self):
        rp.STORE_FILE, item_intel.STATS_FILE, flags.FLAGS_FILE = self._orig
        rp._cache["mtime"] = None
        rp._cache["data"] = None
        item_intel._cache["mtime"] = None


class TestFormat(unittest.TestCase):
    def test_reaction_text_shape(self):
        txt = build_reaction_text(Q, CFG, position="Q 1/5")
        for e in rp.REACTION_EMOJIS:
            self.assertIn(e, txt)
        # options appear in emoji order, bilingual content preserved
        self.assertLess(txt.index("👍"), txt.index("❤️"))
        self.assertLess(txt.index("😂"), txt.index("😮"))
        self.assertIn("long-press", txt)
        self.assertLessEqual(len(txt), 4096)
        # native options unchanged in style (emoji letters)
        opts = build_options(Q)
        self.assertTrue(opts[0].startswith("🅰️"), opts[0])


class TestVotes(TmpStores):
    def _register(self):
        return rp.register(-1001, 55, Q, "SSC", now_ts=time.time())

    def test_user_votes_change_and_remove(self):
        self._register()

        def upd(uid, new):
            return {"message_reaction": {
                "chat": {"id": -1001}, "message_id": 55,
                "user": {"id": uid},
                "new_reaction": ([{"type": "emoji", "emoji": new}] if new else [])}}

        self.assertTrue(rp.apply_update(upd(1, "👍")))
        self.assertTrue(rp.apply_update(upd(2, "❤️")))
        self.assertTrue(rp.apply_update(upd(3, "👍")))
        self.assertTrue(rp.apply_update(upd(2, "😂")))     # vote change
        rec = rp._load()["-1001:55"]
        counts, total = rp.tally(rec)
        self.assertEqual((counts, total), ([2, 0, 1, 0], 3))
        self.assertTrue(rp.apply_update(upd(1, None)))     # reaction removed
        counts, total = rp.tally(rp._load()["-1001:55"])
        self.assertEqual((counts, total), ([1, 0, 1, 0], 2))
        # unknown message ignored
        self.assertFalse(rp.apply_update(
            {"message_reaction": {"chat": {"id": -9}, "message_id": 1,
                                  "user": {"id": 5},
                                  "new_reaction": [{"type": "emoji", "emoji": "👍"}]}}))

    def test_anonymous_count_update(self):
        self._register()
        ok = rp.apply_update({"message_reaction_count": {
            "chat": {"id": -1001}, "message_id": 55,
            "reactions": [
                {"type": {"type": "emoji", "emoji": "👍"}, "total_count": 10},
                {"type": {"type": "emoji", "emoji": "❤️"}, "total_count": 4},
                {"type": {"type": "emoji", "emoji": "🔥"}, "total_count": 99},
            ]}})
        self.assertTrue(ok)
        counts, total = rp.tally(rp._load()["-1001:55"])
        self.assertEqual((counts, total), ([10, 4, 0, 0], 14))  # 🔥 ignored


class TestReveal(TmpStores):
    def test_reveal_posts_and_teaches_item_intel(self):
        rp.register(-1001, 77, Q, "SSC", now_ts=time.time() - 3600)  # due
        rp.apply_update({"message_reaction_count": {
            "chat": {"id": -1001}, "message_id": 77,
            "reactions": [
                {"type": {"type": "emoji", "emoji": "👍"}, "total_count": 8},
                {"type": {"type": "emoji", "emoji": "❤️"}, "total_count": 2},
            ]}})
        sent = []

        class FakeTg:
            def send_message(self, chat, text):
                sent.append((chat, text))
                return {"ok": True}

        out = rp.tick(FakeTg())
        self.assertEqual(out["revealed"], 1)
        self.assertEqual(out["answers"], 10)
        self.assertIn("✅ Correct answer: 👍", sent[0][1])
        self.assertIn("80% correct", sent[0][1])
        # item intelligence learned the aggregate (8 correct / 2 wrong)
        stats = json.loads(item_intel.STATS_FILE.read_text())
        self.assertEqual(stats["RQ1"]["a"], 10)
        self.assertEqual(stats["RQ1"]["c"], 8)
        # second tick: no double reveal
        self.assertEqual(rp.tick(FakeTg())["revealed"], 0)
        self.assertEqual(len(sent), 1)


class TestEngineSwitch(TmpStores):
    def test_flag_switches_channel_style(self):
        from core.engine import Engine
        calls = []

        class FakeTg:
            dry = True

            def send_quiz(self, chat, text, opts, correct, expl, **kw):
                calls.append(("quiz", text))
                return {"ok": True, "result": {"poll": {"id": "p1"}}}

            def send_message(self, chat, text, **kw):
                calls.append(("msg", text))
                return {"ok": True, "result": {"message_id": 99}}

        eng = Engine(dry=True)
        eng.tg = FakeTg()
        # owner rule (revised): Telegram = DIRECT polls by default;
        # emoji text-polls now belong to WhatsApp Channel only
        self.assertTrue(eng._send_channel_question("SSC", dict(Q)))
        self.assertEqual(calls[-1][0], "quiz")
        # opt-in switch ON → reaction text-poll style
        flags.set_flag("channel_reaction_polls", True)
        self.assertTrue(eng._send_channel_question("SSC", dict(Q)))
        self.assertEqual(calls[-1][0], "msg")
        self.assertIn("👍", calls[-1][1])

    def test_wiring(self):
        tg = (ROOT / "scripts" / "core" / "telegram.py").read_text()
        self.assertIn("message_reaction_count", tg)
        bot = (ROOT / "scripts" / "bot.py").read_text()
        self.assertIn("apply_update(upd)", bot)
        self.assertIn("_rp.tick(self.tg)", bot)
        pd = (ROOT / "scripts" / "core" / "poll_dispatch.py").read_text()
        self.assertIn("_send_channel_question", pd)


if __name__ == "__main__":
    unittest.main()
