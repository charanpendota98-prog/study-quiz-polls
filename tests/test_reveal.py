"""Reveal policy: the correct option is never exposed before a person answers."""
import json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from core import config, content  # noqa: E402
from core.telegram import Telegram  # noqa: E402

Q = {"id": "T1", "channel": "SSC", "topic": "polity", "q_en": "Who is the head of the Union Council of Ministers?",
     "q_te": "కేంద్ర మంత్రి మండలికి అధిపతి ఎవరు?", "options_en": ["President", "Prime Minister", "Speaker", "Chief Justice"],
     "options_te": ["రాష్ట్రపతి", "ప్రధాన మంత్రి", "స్పీకర్", "ప్రధాన న్యాయమూర్తి"], "answer_index": 1,
     "explanation_en": "Article 74.", "source": "pyq"}


class RevealPolicy(unittest.TestCase):
    def test_default_no_auto_close(self):
        self.assertFalse(config.POLL_AUTO_CLOSE)

    def test_send_quiz_omits_open_period_by_default(self):
        tg = Telegram(dry=True)
        res = tg.send_quiz("1", "q?", ["a", "b", "c", "d"], 2, "why", open_period=90)
        self.assertNotIn("open_period", res["result"])
        self.assertEqual(res["result"]["correct_option_id"], 2)
        old = config.POLL_AUTO_CLOSE
        config.POLL_AUTO_CLOSE = True
        try:
            res = tg.send_quiz("1", "q?", ["a", "b", "c", "d"], 2, "why", open_period=90)
            self.assertEqual(res["result"]["open_period"], 90)
        finally:
            config.POLL_AUTO_CLOSE = old

    def test_balance_is_deterministic_and_consistent(self):
        a = content.balance_options(Q, "20260911-0730")
        b = content.balance_options(Q, "20260911-0730")
        self.assertEqual(a["options_en"], b["options_en"])
        self.assertEqual(a["options_en"][a["answer_index"]], "Prime Minister")
        self.assertEqual(a["options_te"][a["answer_index"]], "ప్రధాన మంత్రి")
        c = content.balance_options(Q, "20260911-1930")
        self.assertEqual(c["options_en"][c["answer_index"]], "Prime Minister")

    def test_balance_spreads_key_positions(self):
        pos = {content.balance_options(dict(Q, id=f"T{i}"), "s")["answer_index"] for i in range(40)}
        self.assertEqual(pos, {0, 1, 2, 3})

    def test_fixed_order_sets_untouched(self):
        q = dict(Q, options_en=["10", "20", "30", "40"], answer_index=2)
        self.assertEqual(content.balance_options(q, "x")["options_en"], ["10", "20", "30", "40"])
        q = dict(Q, options_en=["Only 1", "Only 2", "Both 1 and 2", "Neither 1 nor 2"], answer_index=2)
        self.assertEqual(content.balance_options(q, "x")["answer_index"], 2)
        q = dict(Q, options_en=["1947", "1950", "1952", "1956"], answer_index=1)
        self.assertEqual(content.balance_options(q, "x")["options_en"][1], "1950")

    def test_poll_safe_strips_markers_and_refuses_leaks(self):
        q = dict(Q, options_en=["President", "Prime Minister ✅", "Speaker", "Chief Justice"])
        s = content.poll_safe(q, "s")
        self.assertIsNotNone(s)
        self.assertTrue(all("✅" not in o for o in s["options_en"]))
        leak = dict(Q, q_en="The Prime Minister heads the council. Who heads the Union Council of Ministers?")
        self.assertIsNone(content.poll_safe(leak, "s"))
        bad = dict(Q, answer_index=7)
        self.assertIsNone(content.poll_safe(bad, "s"))

    def test_engine_round_posts_no_key_until_next_round(self):
        from core.engine import Engine
        tmp = tempfile.TemporaryDirectory()
        old_data = config.DATA
        # isolate last_round.json
        lr = Path(tmp.name) / "last_round.json"
        eng = Engine(dry=True)
        sent = []
        eng.tg._call = lambda m, p, timeout=30: (sent.append((m, p)) or
                                                 {"ok": True, "result": {"message_id": 1, "poll": {"id": "p%d" % len(sent)}, **p}})
        try:
            import core.engine as E
            orig_load = E.load_json
            E.load_json = lambda path, default=None: (orig_load(path, default) if "last_round" not in str(path) else {})
            n = eng.run_quiz_slot(channels=["SSC"], round_label="Test")
            E.load_json = orig_load
        finally:
            tmp.cleanup()
        polls = [p for m, p in sent if m == "sendPoll" and str(p.get("chat_id")) == str(config.channel_chat_id("SSC"))]
        self.assertTrue(polls)
        for p in polls:
            self.assertNotIn("open_period", p, "channel poll must not auto-close/reveal")
        # nothing posted during/after this round may contain the per-question key list
        msgs = [p.get("text", "") for m, p in sent if m == "sendMessage"]
        self.assertFalse(any("Round Report" in t or "🔑 Previous round key" in t for t in msgs),
                         "Q-by-Q key must wait for the next round")


if __name__ == "__main__":
    unittest.main()
