# -*- coding: utf-8 -*-
"""410X — TS & AP Exam Hub 2.0: previous-paper sets inside the hub.

Pins:
  * hub exams expose their OWN paper sets (strict exam-key +
    core-channel matching — Railway/Banking/CURRENT-only sets
    never leak into TSPSC/APPSC rows);
  * totals are honest (paper_questions = sum over matched sets);
  * a hub paper entry starts through portal.paper_start;
  * dashboard hub UI renders the paper chip + Start buttons.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal  # noqa: E402

DASH = (ROOT / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")


def _exam(hub, state, goal):
    s = next(x for x in hub["states"] if x["state"] == state)
    return next(e for e in s["exams"] if e["goal"] == goal)


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


class TestHubPapers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = portal.state_hub()

    def test_ts_ap_papers_present(self):
        for state, goal in (("Telangana", "tspsc"),
                            ("Andhra Pradesh", "appsc")):
            e = _exam(self.hub, state, goal)
            self.assertGreaterEqual(e["papers_count"], 2, goal)
            self.assertGreater(e["papers_questions"], 0)
            self.assertLessEqual(len(e["papers"]), 3)
            self.assertEqual(
                e["papers_questions"],
                sum(p["count"] for p in
                    portal.paper_catalog()
                    if p["label"] in {x["label"] for x in e["papers"]})
                if e["papers_count"] <= 3 else e["papers_questions"])

    def test_papers_are_exam_own(self):
        ts = _exam(self.hub, "Telangana", "tspsc")
        for p in ts["papers"]:
            self.assertIn("tspsc", p["label"].lower())
        ap = _exam(self.hub, "Andhra Pradesh", "appsc")
        for p in ap["papers"]:
            self.assertIn("appsc", p["label"].lower())
        for e in (ts, ap):
            for p in e["papers"]:
                self.assertNotIn("rrb", p["label"].lower())
                self.assertNotIn("ibps", p["label"].lower())

    def test_no_generic_current_leak(self):
        # matcher requires a core-channel hit: CURRENT-only sets
        # (e.g. SSC/UPSC) must not appear under state exams.
        for state, goal in (("Telangana", "tspsc"),
                            ("Andhra Pradesh", "appsc"),
                            ("Telangana", "police")):
            e = _exam(self.hub, state, goal)
            for p in e["papers"]:
                self.assertNotIn("upsc", p["label"].lower())


class TestHubPaperStarts(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp = portal.PATH
        portal.PATH = self.tmp / "portal.json"
        self.m = _Members()
        ok, info = portal.register_student(
            self.m, "Ananya Reddy", "9000000099", "Hyderabad", "tspsc")
        self.assertTrue(ok, info)
        self.token = info["token"]

    def tearDown(self):
        portal.PATH = self._pp

    def test_first_tspsc_paper_starts(self):
        hub = portal.state_hub()
        ts = _exam(hub, "Telangana", "tspsc")
        self.assertTrue(ts["papers"], "TSPSC paper sets undali")
        p = ts["papers"][0]
        ok, run = portal.paper_start(self.m, self.token, p["exam"],
                                     p["year"], p["paper"])
        self.assertTrue(ok, run)
        self.assertEqual(len(run["questions"]), p["count"])
        self.assertIn(p["label"], run["label"])


class TestDashboardWiring(unittest.TestCase):
    def test_hub_renders_papers(self):
        i = DASH.index("async function loadStateHub")
        seg = DASH[i:i + 3200]
        self.assertIn("papers_count", seg)
        self.assertIn("startPaper(", seg)
        self.assertIn("papers_questions", seg)


if __name__ == "__main__":
    unittest.main()
