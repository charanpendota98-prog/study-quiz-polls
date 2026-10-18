# -*- coding: utf-8 -*-
"""Campus Exam 3.0: negative marking, one-click retest, command palette."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core import campus as C


def _q(qid, ans=0):
    return {"id": qid, "q_en": f"Q {qid}", "q_te": "", "options_en": ["a", "b", "c", "d"],
            "options_te": [], "answer_index": ans, "window": 40, "channel": "TSPSC",
            "topic": "Reasoning", "subject": "reasoning"}


class TestCampusExam3(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._o = C.PATH; C.PATH = self.tmp / "c.json"

    def tearDown(self):
        C.PATH = self._o
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _live_event(self, neg=0):
        code = C.new_event("Neg Fest", "Guntur", ["Alpha College"], 5, "easy",
                           created_by="admin", neg=neg)
        d = C._load(); e = d["events"][code]
        e["questions"] = [_q("q1", ans=1), _q("q2", ans=0)]
        e["state"] = "question"; e["qi"] = 0
        e["q_open"] = C._now().isoformat()
        e["players"] = {"1": {"college": "Alpha College", "name": "S1", "pts": 0,
                              "correct": 0, "answered": 0, "joined": "x",
                              "first": None, "last": None}}
        e["answers"] = {}
        d["polls"]["p1"] = [code, 0, "1"]
        C._save(d)
        return code

    def test_negative_marking(self):
        code = self._live_event(neg=2)
        C.record_answer("p1", "1", 0)                    # wrong (answer is 1)
        d = C._load(); e = d["events"][code]
        self.assertEqual(e["players"]["1"]["pts"], -2)
        self.assertEqual(e["players"]["1"]["correct"], 0)
        self.assertEqual(e["players"]["1"]["answered"], 1)

    def test_no_negative_by_default(self):
        code = self._live_event(neg=0)
        C.record_answer("p1", "1", 0)
        self.assertEqual(C._load()["events"][code]["players"]["1"]["pts"], 0)

    def test_correct_still_scores(self):
        code = self._live_event(neg=5)
        C.record_answer("p1", "1", 1)                    # correct
        p = C._load()["events"][code]["players"]["1"]
        self.assertGreater(p["pts"], 0)
        self.assertEqual(p["correct"], 1)

    def test_retest_clones_settings(self):
        code = C.new_event("Monthly Fest × StudentUp Challenge", "Guntur",
                           ["Alpha College", "Beta College"], 12, "hard",
                           created_by="adm", mode="exam",
                           subjects=["reasoning", "quant"], neg=2)
        new = C.retest_event(code)
        self.assertIsNotNone(new)
        self.assertNotEqual(new, code)
        d = C._load(); ne = d["events"][new]
        self.assertEqual(ne["state"], "open")
        self.assertEqual(ne["colleges"], ["Alpha College", "Beta College"])
        self.assertEqual((ne["n_q"], ne["level"], ne["neg"]), (12, "hard", 2))
        self.assertEqual(ne["subjects"], ["reasoning", "quant"])
        self.assertTrue(ne["retest"])
        self.assertEqual(ne["retest_of"], code)
        self.assertIsNone(C.retest_event("CE-NOPE"))

    def test_dashboard_wiring(self):
        src = (Path(__file__).resolve().parents[1]
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/campus/retest"', "campus.retest_event",
                       'id="campus-neg"', "retestCampus",
                       'id="cmdk-overlay"', "openCmdk", "Ctrl+K",
                       "cmdkDynamic"):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
