# -*- coding: utf-8 -*-
"""🚀 80X Exam-Separation round: exam-wise previous papers only.

Pins (probe-verified):
  • _goal_pyq_pool: strict per-exam PYQs (channel + exam-name match)
  • Exam PYQ Mock (kind='exam'): only that exam's channel questions,
    label carries honest real-PYQ count
  • _paper(strict=True): live/grand papers never fill from other exams
  • PYQ Drill goal-scoped (Railway drill = Railway PYQs only)
  • _snap/_serve carry PYQ provenance (source/exam/year) for badges
  • Goal Hub 80X fields (pyq_exam, channels_stock, paper_labels)
  • flags = 19 (+exam_pyq_mocks), hub deep link + wiring
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, brain, flags  # noqa: E402


class _KV:
    def save(self):
        pass

    def save_debounced(self):
        pass


class _Members:
    def __init__(self):
        self.members = {}
        self.kv = _KV()

    def _get(self, uid):
        return self.members.setdefault(str(uid), {
            "name": "Adv80 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": []})

    def award_answer(self, uid, username="", correct=True, topic="",
                     qid=""):
        m = self._get(uid)
        m["points"] = m.get("points", 0) + (10 if correct else 0)
        return {"points": m["points"]}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"
        self.mem = _Members()
        ok, info = portal.register_student(self.mem, "Adv80 Tester",
                                           "9822000080", "Guntur",
                                           "railway")
        assert ok, info
        self.tok = info["token"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestSeparation80(_Base):
    def test_goal_pyq_pool_strict(self):
        rp = portal._goal_pyq_pool("railway")
        self.assertGreaterEqual(len(rp), 1)
        for q in rp:
            self.assertEqual(q.get("source"), "pyq")
            self.assertEqual(q.get("channel"), "RAILWAY")
        sp = portal._goal_pyq_pool("ssc")
        for q in sp:
            self.assertEqual(q.get("source"), "pyq")
            self.assertIn(q.get("channel"), portal.GOALS["ssc"]["channels"])

    def test_exam_mock_only_that_exam(self):
        ok, run = portal.mock_start(self.mem, self.tok, "railway",
                                    kind="exam")
        self.assertTrue(ok, run)
        self.assertEqual(run["kind"], "exam")
        self.assertIn("PYQ Mock", run["label"])
        self.assertGreaterEqual(len(run["questions"]), 10)
        d = portal._load()
        snaps = d["mocks"][run["run_id"]]["qs"]
        for q in snaps:
            self.assertEqual(q["channel"], "RAILWAY")
        self.assertGreaterEqual(
            sum(1 for q in snaps if q["source"] == "pyq"), 5)

    def test_strict_paper_no_foreign_fill(self):
        pap = portal._paper(["RAILWAY"], 15, "seed80", strict=True)
        self.assertEqual(len(pap), 15)
        for q in pap:
            self.assertEqual(q["channel"], "RAILWAY")

    def test_pyq_drill_goal_scoped(self):
        ok, run = portal.practice_start(self.mem, self.tok, "pyq",
                                        goal="railway")
        self.assertTrue(ok, run)
        d = portal._load()
        qs = d["practice"][run["run_id"]]["qs"]
        self.assertTrue(qs)
        for q in qs:
            self.assertEqual(q["source"], "pyq")
            self.assertEqual(q["channel"], "RAILWAY")

    def test_provenance_served(self):
        q = portal._goal_pyq_pool("railway")[0]
        served = portal._serve([portal._snap(q)], "probe", {})
        self.assertEqual(served[0]["source"], "pyq")
        self.assertIn("exam", served[0])
        self.assertIn("year", served[0])

    def test_hub80_fields(self):
        ok, hub = portal.goal_hub(self.mem, self.tok, "railway")
        self.assertTrue(ok, hub)
        self.assertGreaterEqual(hub["pyq_exam"], 1)
        chans = {c["channel"] for c in hub["channels_stock"]}
        self.assertEqual(chans, set(portal.GOALS["railway"]["channels"]))
        self.assertIsInstance(hub["paper_labels"], list)

    def test_flags_19(self):
        self.assertEqual(len(flags.all_flags()), 19)
        self.assertTrue(flags.enabled("exam_pyq_mocks"))


class TestWiring80(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_hub_deep_link(self):
        self.assertIn("hub: 'goal-hub-card'", self.dash)
        self.assertIn("su_hub_goal", self.dash)
        self.assertIn("?go=hub&goal=", self.dash)

    def test_exam_mock_and_badges_wiring(self):
        self.assertIn("kind: kind || 'mock'", self.dash)
        self.assertIn("\\'exam\\'", self.dash)
        self.assertIn("function qMeta", self.dash)
        self.assertIn("goal: goal || ''", self.dash)


if __name__ == "__main__":
    unittest.main()
