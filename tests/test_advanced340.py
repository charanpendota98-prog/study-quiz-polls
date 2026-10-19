# -*- coding: utf-8 -*-
"""340X — stock growth: +16 curated bilingual board questions
(10th/Inter/Diploma/B.Tech × TS/AP, 4→6 per channel), hub stock
targets with honest gap alerts, dashboard go-live stock check.
"""
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal  # noqa: E402

DASH = (ROOT / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
BOARD = ("TS_10TH", "AP_10TH", "TS_INTER", "AP_INTER",
         "TS_DIPLOMA", "AP_DIPLOMA", "TS_BTECH", "AP_BTECH")


class TestAcademicGrowth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.question_bank import load_academic_questions
        cls.items = load_academic_questions()

    def test_six_per_board_channel(self):
        c = Counter(q["channel"] for q in self.items)
        for ch in BOARD:
            self.assertEqual(c[ch], 6, f"{ch} stock 6 undali")
        self.assertEqual(len(self.items), 68)

    def test_new_questions_present_and_valid(self):
        by_q = {q["q_en"]: q for q in self.items}
        checks = {
            "binary equivalent of the decimal number 10": "1010",
            "full form of TCP in computer networks":
                "Transmission Control Protocol",
            "derivative of sin(x)": "cos(x)",
            "worst-case time complexity of Linear Search": "O(n)",
            "roots of the quadratic equation": "2 and 3",
            "Battle of Plassey": "1757",
        }
        for frag, want in checks.items():
            q = next(v for k, v in by_q.items() if frag in k)
            self.assertEqual(q["options_en"][q["answer_index"]], want,
                             f"{frag}: correct option tappu")
            self.assertTrue(q["q_te"], "Telugu stem undali")

    def test_no_dup_options(self):
        for q in self.items:
            opts = [o.strip().lower() for o in q["options_en"]]
            self.assertEqual(len(opts), len(set(opts)), q["id"])


class TestHubTargets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = portal.state_hub()
        cls.exams = {e["goal"]: e for s in cls.hub["states"]
                     for e in s["exams"]}

    def test_target_fields(self):
        for e in self.exams.values():
            self.assertIn("target", e)
            self.assertEqual(e["gap_total"],
                             max(0, e["target"]["total"] - e["total"]))
            self.assertEqual(e["gap_pyq"],
                             max(0, e["target"]["pyq"] - e["pyq"]))

    def test_apps_gap_flagged_ts_ready(self):
        # Relative (not absolute) so suite test-order bank state
        # cannot flake it: AP must trail TS on stock health.
        self.assertGreater(self.exams["appsc"]["gap_total"], 0)
        self.assertGreater(self.exams["tspsc"]["total"],
                           self.exams["appsc"]["total"])
        self.assertLessEqual(self.exams["tspsc"]["gap_total"],
                             self.exams["appsc"]["gap_total"])


class TestDashboardWiring(unittest.TestCase):
    def test_golive_stock_check(self):
        self.assertIn("Exam stock targets (340X)", DASH)

    def test_hub_gap_chip(self):
        self.assertIn("stock kavali", DASH)
        self.assertIn("gap_total", DASH)


if __name__ == "__main__":
    unittest.main()
