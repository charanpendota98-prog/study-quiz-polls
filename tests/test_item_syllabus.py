#!/usr/bin/env python3
"""Item Intelligence + Personal Syllabus Graph tests.

Item intel: real answers → suspect-key quarantine (verifier blocks it),
too-easy detection, difficulty calibration beats heuristics.
Syllabus: mastery map, weak-topic plan, personal round composition
(weak/review/fresh mix), bot /myplan command wired.
Run: python3 -m unittest discover -s tests -p "test_item_syllabus.py"
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import item_intel, blueprint, verifier, syllabus  # noqa: E402


class TestItemIntel(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = item_intel.STATS_FILE
        item_intel.STATS_FILE = self.tmp / "item_stats.json"
        item_intel._cache["mtime"] = None
        item_intel._cache["data"] = {}

    def tearDown(self):
        item_intel.STATS_FILE = self._orig
        item_intel._cache["mtime"] = None

    def _feed(self, qid, correct_n, total):
        for i in range(total):
            item_intel.record(qid, i < correct_n, topic="polity", channel="SSC")

    def test_suspect_key_quarantined(self):
        self._feed("BAD1", 1, 20)                 # 5% correct ×20
        self.assertEqual(item_intel.classify("BAD1"), "suspect_key")
        self.assertTrue(item_intel.is_quarantined("BAD1"))
        q = {"id": "BAD1", "q_en": "x?", "q_te": "", "source": "pyq",
             "options_en": ["a", "b"], "answer_index": 0}
        self.assertFalse(verifier.postable(q))    # even PYQ blocked

    def test_too_easy_and_calibration(self):
        self._feed("EASY1", 30, 30)
        self._feed("HARD1", 2, 20)
        self.assertEqual(item_intel.classify("EASY1"), "too_easy")
        self.assertEqual(item_intel.calibrated_difficulty("EASY1", "hard"), "easy")
        self.assertEqual(item_intel.calibrated_difficulty("HARD1", "easy"), "hard")
        # blueprint prefers real data over heuristics
        q = {"id": "HARD1", "q_en": "Who is the President of India?",
             "topic": "polity"}
        self.assertEqual(blueprint.difficulty_of(q), "hard")

    def test_learning_until_enough_data(self):
        self._feed("NEW1", 0, 3)
        self.assertEqual(item_intel.classify("NEW1"), "learning")
        q = {"id": "NEW1", "q_en": "x?", "q_te": "", "source": "pyq",
             "options_en": ["a", "b"], "answer_index": 0}
        self.assertTrue(verifier.postable(q))     # trusted PYQ, data thin

    def test_report(self):
        self._feed("BAD2", 0, 16)
        rep = item_intel.report()
        self.assertEqual(rep["suspect_count"], 1)
        self.assertEqual(rep["tracked_questions"], 1)


class _FakeBank:
    def __init__(self):
        self._qs = [
            {"id": "w1", "channel": "SSC", "topic": "polity basics",
             "q_en": "Weak topic q?", "options_en": ["a", "b"], "answer_index": 0},
            {"id": "r1", "channel": "SSC", "topic": "history",
             "q_en": "Review q?", "options_en": ["a", "b"], "answer_index": 1},
            {"id": "f1", "channel": "SSC", "topic": "geography",
             "q_en": "Fresh q?", "options_en": ["a", "b"], "answer_index": 0},
        ]
        self.marked = []

    def by_channel(self, ch):
        return list(self._qs)

    def unused(self, ch):
        return list(self._qs)

    def by_id(self, qid):
        return next((q for q in self._qs if q["id"] == qid), None)

    def pick(self, ch, n):
        return [q for q in self._qs if q["id"] == "f1"][:n]

    def mark_posted(self, ch, qs):
        self.marked.extend(q["id"] for q in qs)


class TestSyllabus(unittest.TestCase):
    MEMBER = {"name": "Ravi",
              "topics": {"polity basics": {"total": 10, "correct": 3},
                         "geography": {"total": 10, "correct": 9}},
              "review": [{"qid": "r1", "due": "2026-10-14", "interval": 0}]}

    def test_mastery_and_plan(self):
        p = syllabus.plan(self.MEMBER, _FakeBank(), "SSC")
        self.assertLess(p["overall_mastery"], 0.7)
        self.assertEqual(p["weak_topics"][0]["topic"], "polity basics")
        self.assertEqual(p["reviews_due"], 1)
        txt = syllabus.plan_text(self.MEMBER, _FakeBank(), "SSC")
        self.assertIn("Polity", txt)
        self.assertIn("Focus topics", txt)

    def test_personal_round_mix(self):
        bank = _FakeBank()
        out = syllabus.compose_personal_round(bank, self.MEMBER, "SSC", n=3)
        ids = [q["id"] for q in out]
        self.assertIn("w1", ids)      # weak topic first
        self.assertIn("r1", ids)      # due review included
        self.assertEqual(len(ids), len(set(ids)))

    def test_bot_command_and_api_wired(self):
        bot = (ROOT / "scripts" / "bot.py").read_text()
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("/myplan", bot)
        self.assertIn("item_intel.record", bot)
        self.assertIn("/api/syllabus", dash)


if __name__ == "__main__":
    unittest.main()
