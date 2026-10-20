# -*- coding: utf-8 -*-
"""360X — FSRS-Lite spaced repetition.

The fixed 0->3d->7d ladder mastered a question after ONE lucky
correct. 360X grades by stability: correct recalls grow stability
(harder-earned recalls grow most), lapses collapse it, proven
cards retire. Legacy ladder cards migrate on first touch.
"""
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import fsrs_lite as fs  # noqa: E402
from core import portal  # noqa: E402

D0 = date(2026, 10, 1)


class TestFsrsLite(unittest.TestCase):
    def test_new_log_due_today_for_daily_batch(self):
        log = fs.new_log("Q1", D0, topic="polity")
        self.assertEqual(log["due"], D0.isoformat())
        self.assertEqual(log["reps"], 0)

    def test_correct_grows_stability_and_interval(self):
        log = fs.new_log("Q1", D0)
        prev_due = log["due"]
        for _ in range(3):
            log = fs.grade(log, True, prev_due)
            self.assertGreater(log["s"], 1.0)
            self.assertGreater(log["due"], prev_due)
            prev_due = log["due"]

    def test_eventual_mastery(self):
        log = fs.new_log("Q1", D0)
        for _ in range(12):
            log = fs.grade(log, True, log["due"])
            if fs.mastered(log):
                break
        self.assertTrue(fs.mastered(log),
                        f"12 on-time recalls ki mastery ravali: {log}")

    def test_lapse_collapses_but_floors(self):
        log = {"qid": "Q1", "s": 40.0, "last": "2026-09-01",
               "reps": 5, "due": "2026-10-01"}
        out = fs.grade(log, False, "2026-10-01")
        self.assertAlmostEqual(out["s"], 10.0)
        self.assertLess(out["due"], "2026-11-01")

    def test_retrievability_decays(self):
        log = fs.new_log("Q1", D0)
        self.assertEqual(fs.retrievability(log, D0), 1.0)
        r30 = fs.retrievability(log, D0 + timedelta(days=30))
        self.assertLess(r30, 0.5)
        self.assertGreater(r30, 0.0)

    def test_hard_recall_grows_more(self):
        fresh = fs.grade(fs.new_log("Q1", D0), True, D0)
        late_log = fs.new_log("Q1", D0)
        late = fs.grade(late_log, True, D0 + timedelta(days=20))
        self.assertGreater(late["s"], fresh["s"])

    def test_never_raises_on_junk(self):
        out = fs.grade({}, True, "2026-10-02")
        self.assertIn("due", out)
        self.assertEqual(fs.retrievability({}, "2026-10-02"), 0.0)


class TestMembersIntegration(unittest.TestCase):
    def setUp(self):
        from core import config, members
        self._tmp = tempfile.TemporaryDirectory()
        self._old = config.DATA
        config.DATA = Path(self._tmp.name)
        self.m = members.Members()
        self.m.register(42, name="Test Student")

    def tearDown(self):
        from core import config
        config.DATA = self._old
        self._tmp.cleanup()

    def test_wrong_creates_fsrs_card(self):
        self.m.award_answer(42, correct=False, topic="polity", qid="QX1")
        cards = self.m.members["42"]["review"]
        self.assertEqual(len(cards), 1)
        self.assertIn("s", cards[0])
        self.assertEqual(cards[0]["qid"], "QX1")

    def test_legacy_card_migrates(self):
        from core.store import now_iso
        _ = now_iso
        import datetime as _dt
        from core import config
        today = _dt.datetime.now(config.IST).strftime("%Y-%m-%d")
        rec = self.m.members["42"]
        rec["review"] = [{"qid": "QL1", "due": today, "interval": 3,
                          "topic": "history"}]
        self.m.kv.save()
        self.m.award_answer(42, correct=True, topic="history", qid="QL1")
        cards = self.m.members["42"]["review"]
        self.assertEqual(len(cards), 1)
        self.assertIn("s", cards[0], "legacy card FSRS ki migrate avvali")


class TestMemoryDeck(unittest.TestCase):
    def setUp(self):
        from core import config, members
        self._tmp = tempfile.TemporaryDirectory()
        self._old = config.DATA
        config.DATA = Path(self._tmp.name)
        self.m = members.Members()
        ok, info = portal.register_student(
            self.m, "Ananya Reddy", "9000000007", "Hyderabad", "tspsc")
        self.assertTrue(ok, info)
        self.token = info["token"]
        self.uid = info["uid"]

    def tearDown(self):
        from core import config
        config.DATA = self._old
        self._tmp.cleanup()

    def test_deck_counts_and_order(self):
        import datetime as _dt
        from core import config
        now = _dt.datetime.now(config.IST).date()
        today = now.isoformat()
        old = (now - timedelta(days=30)).isoformat()
        rec = self.m._get(self.uid)
        rec["review"] = [
            {"qid": "A", "topic": "polity", "due": today,
             "interval": 0},
            {"qid": "B", "topic": "history", "due": "2999-01-01",
             "s": 2.0, "last": old, "reps": 1},
            {"qid": "C", "topic": "maths", "due": "2999-01-01",
             "s": 30.0, "last": today, "reps": 5},
        ]
        self.m.kv.save()
        deck = portal.memory_deck(self.m, self.token)
        self.assertEqual(deck["due"], 1)
        self.assertEqual(deck["total"], 3)
        self.assertEqual(deck["strong"], 1)
        self.assertTrue(deck["cards"][0]["due_now"])

    def test_deck_bad_token(self):
        self.assertIsNone(portal.memory_deck(self.m, "bad-token"))


class TestWiring(unittest.TestCase):
    def test_pins(self):
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        mem = (ROOT / "scripts" / "core" / "members.py").read_text(
            encoding="utf-8")
        self.assertIn("/api/portal/memory", dash)
        self.assertIn("loadMemoryDeck", dash)
        self.assertIn("Memory Booster", dash)
        self.assertIn("fsrs_lite", mem)
        self.assertIn("360X", mem)


if __name__ == "__main__":
    unittest.main()
