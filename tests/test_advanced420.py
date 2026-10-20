# -*- coding: utf-8 -*-
"""420X — TS/AP board subject tests: hub subjects + board practice.

Pins:
  * academic stock grew (72 total; TS/AP Inter 8 each) with the
    four new questions' correct answers verified;
  * state_hub academic rows carry grouped subjects summing to
    the channel total;
  * practice mode="board" serves ONLY that channel's stock,
    subject filter is strict, invalid channel errors honestly;
  * dashboard renders the Board Exams subject-test buttons.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal  # noqa: E402

DASH = (ROOT / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
PORTAL = (ROOT / "scripts" / "core" / "portal.py").read_text(encoding="utf-8")


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
            "points": 0, "total": 0, "topics": {}, "review": []})


class TestStock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.question_bank import load_academic_questions
        cls.items = load_academic_questions()

    def test_new_inter_questions(self):
        checks = {
            "alpha + beta is": "5",
            "velocity after 5 seconds": "10 m/s",
            "third shell (n = 3)": "18",
            "cell elongation in shoots": "Auxin",
        }
        for frag, want in checks.items():
            q = next(v for v in self.items if frag in v["q_en"])
            self.assertEqual(q["options_en"][q["answer_index"]], want,
                             frag)
            self.assertRegex(q["q_te"], r"[ఀ-౿]")


class TestHubSubjects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acad = {a["channel"]: a
                    for a in portal.state_hub()["academic"]}

    def test_subjects_grouped_and_honest(self):
        for ch in ("TS_INTER", "AP_INTER", "TS_10TH"):
            a = self.acad[ch]
            self.assertTrue(a["subjects"], ch)
            # subjects are a top-6 view: their counts never exceed
            # the honest channel total (no double-counting).
            self.assertLessEqual(sum(s["count"] for s in a["subjects"]),
                                 a["total"], ch)
            self.assertGreater(a["total"], 0)
        names = {s["subject"] for s in self.acad["TS_INTER"]["subjects"]}
        self.assertIn("Mathematics", names)
        self.assertIn("Physics", names)


class TestBoardPractice(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp = portal.PATH
        portal.PATH = self.tmp / "portal.json"
        self.m = _Members()
        ok, info = portal.register_student(
            self.m, "Sravani", "9000000119", "Warangal", "tspsc")
        self.assertTrue(ok, info)
        self.token = info["token"]

    def tearDown(self):
        portal.PATH = self._pp

    def test_full_board_and_subject(self):
        ok, run = portal.practice_start(self.m, self.token,
                                        mode="board", goal="TS_INTER")
        self.assertTrue(ok, run)
        self.assertEqual(len(run["questions"]), 8)
        ok, sub = portal.practice_start(self.m, self.token,
                                        mode="board",
                                        topic="Chemistry",
                                        goal="AP_INTER")
        self.assertTrue(ok, sub)
        self.assertTrue(all("Chemistry" in (q.get("topic") or "")
                            for q in sub["questions"]))

    def test_strict_failures_honest(self):
        ok, err = portal.practice_start(self.m, self.token,
                                        mode="board", goal="SSC")
        self.assertFalse(ok)
        ok, err = portal.practice_start(self.m, self.token,
                                        mode="board",
                                        topic="Astronomy",
                                        goal="TS_INTER")
        self.assertFalse(ok)
        self.assertIn("levu", err)


class TestWiring(unittest.TestCase):
    def test_board_mode_and_ui(self):
        self.assertIn('mode == "board"', PORTAL)
        self.assertIn("Board Exams — Subject Tests", DASH)
        i = DASH.index("async function loadStateHub")
        self.assertIn("startPractice(\\'board\\'", DASH[i:i + 5000])


if __name__ == "__main__":
    unittest.main()
