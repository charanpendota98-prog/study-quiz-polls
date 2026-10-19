# -*- coding: utf-8 -*-
"""330X — TS & AP Exam Hub: state-separate goals (TSPSC/APPSC),
honest state hub counts, goal-scoped subject tests, academic strip.
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


class TestStateGoals(unittest.TestCase):
    def test_ts_ap_goals_exist(self):
        self.assertEqual(portal.GOALS["tspsc"]["channels"],
                         ["TSPSC", "CURRENT"])
        self.assertEqual(portal.GOALS["appsc"]["channels"],
                         ["APPSC", "CURRENT"])
        self.assertIn("Telangana", portal.GOALS["tspsc"]["label"])
        self.assertIn("Andhra Pradesh", portal.GOALS["appsc"]["label"])

    def test_exam_keys_and_dates(self):
        self.assertIn("tspsc", portal.GOAL_EXAM_KEYS["tspsc"])
        self.assertIn("appsc", portal.GOAL_EXAM_KEYS["appsc"])
        self.assertIn("tspsc", portal.EXAM_DATES)
        self.assertIn("appsc", portal.EXAM_DATES)


class TestStateHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hub = portal.state_hub()

    def test_structure(self):
        names = [s["state"] for s in self.hub["states"]]
        self.assertEqual(names, ["Telangana", "Andhra Pradesh"])
        goals = {e["goal"] for s in self.hub["states"] for e in s["exams"]}
        self.assertIn("tspsc", goals)
        self.assertIn("appsc", goals)

    def test_honest_counts(self):
        for s in self.hub["states"]:
            for e in s["exams"]:
                self.assertGreaterEqual(e["total"], e["pyq"])
                counts = [x["count"] for x in e["subjects"]]
                self.assertEqual(counts, sorted(counts, reverse=True))

    def test_tspsc_pool_real_stock(self):
        ts = next(s for s in self.hub["states"]
                  if s["state"] == "Telangana")
        e = next(x for x in ts["exams"] if x["goal"] == "tspsc")
        self.assertGreater(e["total"], 50)  # TSPSC channel is well stocked

    def test_academic_strip(self):
        chans = {a["channel"] for a in self.hub["academic"]}
        self.assertIn("TS_INTER", chans)
        self.assertIn("AP_10TH", chans)


class TestGoalScopedPractice(unittest.TestCase):
    def test_pin(self):
        i = PORTAL.index('mode == "section"')
        self.assertIn("_bank_pool(_chans or None)", PORTAL[i:i + 1600])


class TestFunctional(unittest.TestCase):
    def setUp(self):
        from core import config, members
        self._tmp = tempfile.TemporaryDirectory()
        self._old = config.DATA
        config.DATA = Path(self._tmp.name)
        self.m = members.Members()
        ok, info = portal.register_student(
            self.m, "Ananya Reddy", "9000000001", "Hyderabad", "tspsc")
        self.assertTrue(ok, info)
        self.token = info["token"]

    def tearDown(self):
        from core import config
        config.DATA = self._old
        self._tmp.cleanup()

    def test_tspsc_mock_uses_ts_pool(self):
        ok, info = portal.mock_start(self.m, self.token, "tspsc")
        self.assertTrue(ok, info)
        qs = info.get("questions") or []
        self.assertTrue(qs)
        chans = {q.get("channel") for q in qs}
        self.assertTrue(chans <= {"TSPSC", "CURRENT"},
                        f"vere exam questions mix ayyayi: {chans}")

    def test_section_test_goal_scoped(self):
        ok, info = portal.practice_start(self.m, self.token, mode="section",
                                         topic="quant", goal="tspsc")
        self.assertTrue(ok, info)
        qs = info.get("questions") or []
        if qs:
            chans = {q.get("channel") for q in qs}
            self.assertTrue(chans <= {"TSPSC", "CURRENT"},
                            f"section pool goal-scoped kadu: {chans}")


class TestDashboardWiring(unittest.TestCase):
    def test_route_and_ui(self):
        self.assertIn("/api/portal/state_hub", DASH)
        self.assertIn("state-hub", DASH)
        self.assertIn("loadStateHub", DASH)
        self.assertIn("TS & AP Exam Hub", DASH.replace("&amp;", "&"))


if __name__ == "__main__":
    unittest.main()
