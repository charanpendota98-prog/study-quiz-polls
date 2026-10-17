# -*- coding: utf-8 -*-
"""🚀 60X Advanced round: adaptive intelligence + STUDENTUP.IN bridge.

Feature pins (probe-verified before pinning):
  • Daily paper ≥ PYQ share (PYQ-first), served questions carry level
  • practice_answer returns explanation_te alongside explanation
  • Adaptive Mock (Brain compose + due review), flag-guarded
  • Goal-targeted notices (only matching-goal students see them)
  • Sprint Mode (active only 0–14 days before exam)
  • Second goal (goal2) quick access, GOALS-validated
  • Weekly report .txt download, Series certificate gate (≥10)
  • portal_analytics funnel keys
  • STUDENTUP.IN → portal bridge: ?go= deep links, public icon grid,
    nav portal entry, analytics funnel admin UI, routes + JS wiring.
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
            "name": "Adv60 Tester", "district": "Guntur", "points": 0,
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
        ok, info = portal.register_student(self.mem, "Adv60 Tester",
                                           "9822000060", "Guntur",
                                           "railway")
        assert ok, info
        self.tok = info["token"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestFlags60(_Base):
    def test_flags_15_and_new_enabled(self):
        self.assertEqual(len(flags.all_flags()), 19)
        self.assertTrue(flags.enabled("adaptive_mock"))
        self.assertTrue(flags.enabled("sprint_mode"))


class TestDailyAndPractice60(_Base):
    def test_daily_paper_has_pyq_share(self):
        st = portal.state(self.mem, self.tok)
        self.assertGreaterEqual(st["daily"]["n"], 1)
        self.assertGreaterEqual(st["daily"]["pyq_count"], 1)

    def test_practice_level_and_telugu_explanation_key(self):
        ok, run = portal.practice_start(self.mem, self.tok, "polity")
        self.assertTrue(ok, run)
        q0 = run["questions"][0]
        self.assertIn(q0.get("level"), ("easy", "medium", "hard"))
        ok, res = portal.practice_answer(self.mem, self.tok,
                                         run["run_id"], 0, 0)
        self.assertTrue(ok, res)
        self.assertIn("explanation_te", res)


class TestAdaptiveMock60(_Base):
    def test_adaptive_mock_starts(self):
        ok, run = portal.mock_start(self.mem, self.tok, "railway",
                                    kind="adaptive")
        self.assertTrue(ok, run)
        self.assertTrue(run["label"].startswith("🧠 Adaptive Mock"))
        self.assertGreaterEqual(len(run["questions"]), 10)


class TestNotices60(_Base):
    def test_goal_targeted_notices(self):
        ok2, info2 = portal.register_student(
            self.mem, "Adv60 SSC", "9822000061",
            "Sri Potti Sriramulu Nellore", "ssc")
        assert ok2, info2
        n1 = portal.add_notice("Railway only", "for railway", "",
                               goal="railway")
        portal.add_notice("For everyone", "all", "")
        n3 = portal.add_notice("Bad goal", "x", "", goal="bogusgoal")
        self.assertEqual(n1.get("goal"), "railway")
        self.assertEqual(n3.get("goal"), "")  # invalid goal normalised
        rail = [n["title"] for n in portal.state(self.mem, self.tok)
                ["notices"]]
        ssc = [n["title"] for n in portal.state(self.mem, info2["token"])
               ["notices"]]
        self.assertIn("Railway only", rail)
        self.assertNotIn("Railway only", ssc)
        self.assertIn("For everyone", ssc)


class TestSprintGoal2Report60(_Base):
    def test_sprint_inactive_far_from_exam(self):
        sp = portal.sprint_plan(self.mem, self.tok)
        self.assertIsNotNone(sp)
        self.assertFalse(sp["active"])
        st = portal.state(self.mem, self.tok)
        self.assertIsNone(st["sprint"])
        self.assertIn("goal2", st)

    def test_goal2_set_and_validate(self):
        ok, info = portal.set_goal2(self.mem, self.tok, "ssc")
        self.assertTrue(ok, info)
        st = portal.state(self.mem, self.tok)
        self.assertEqual(st["goal2"]["goal"], "ssc")
        self.assertTrue(st["goal2"]["label"])
        ok, _info = portal.set_goal2(self.mem, self.tok, "bogusgoal")
        self.assertFalse(ok)

    def test_weekly_report_and_series_gate(self):
        ok, wr = portal.weekly_report_text(self.mem, self.tok)
        self.assertTrue(ok, wr)
        self.assertTrue(wr["filename"].endswith(".txt"))
        self.assertIn("StudentUp", wr["text"])
        ok, _e = portal.weekly_report_text(self.mem, "badtoken")
        self.assertFalse(ok)
        self.assertIsNone(portal.series_certificate(self.mem, self.tok))


class TestAnalytics60(_Base):
    def test_funnel_keys(self):
        portal.register_student(self.mem, "Adv60 Two", "9822000062",
                                "Guntur", "ssc")
        an = portal.portal_analytics(self.mem)
        fn = an["funnel"]
        self.assertEqual(fn["registered"], 2)
        for k in ("attempted", "active_today", "attempt_rate"):
            self.assertIn(k, fn)


class TestBridgeWiring60(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_new_portal_routes_exist(self):
        for r in ('p.path == "/api/portal/sprint"',
                  'p.path == "/api/portal/weekly_report"',
                  'p.path == "/api/portal/series/certificate"',
                  'p.path == "/api/portal/goal2"',
                  'p.path == "/api/portal/admin/analytics"'):
            self.assertIn(r, self.dash)

    def test_spa_functions_exist(self):
        for fn in ("startAdaptive", "weeklyReport", "seriesCert",
                   "setGoal2", "renderPalette", "_applyGo",
                   "loadPortalAnalytics"):
            self.assertIn(fn, self.dash)
        self.assertIn('id="m-palette"', self.dash)
        self.assertIn('id="sprint-card"', self.dash)
        self.assertIn('id="sec-papers"', self.dash)
        self.assertIn('id="pt-analytics"', self.dash)

    def test_studentup_bridge_deep_links(self):
        # Public home icon grid + nav entry → portal deep links
        self.assertIn("StudentUp Portal — Anni Okka Chota", self.dash)
        self.assertIn("__PORTAL__?go=quiz", self.dash)
        self.assertIn("__PORTAL__?go=exams", self.dash)
        self.assertIn("__PORTAL__?go=mocks", self.dash)
        self.assertIn('<a class="login" href="/portal">🚀 Student Portal</a>',
                      self.dash)
        # Portal consumes ?go= and remembers it through login
        self.assertIn("su_go", self.dash)
        self.assertIn("sec-quiz", self.dash)
        self.assertIn("sec-exams", self.dash)

    def test_wp_snippet_and_doc_exist(self):
        snip = (ROOT / "integrations" / "wordpress"
                / "studentup-portal-icon.html")
        self.assertTrue(snip.exists())
        txt = snip.read_text(encoding="utf-8")
        self.assertIn("quiz.studentup.in/?go=quiz", txt)
        self.assertIn("quiz.studentup.in/?go=exams", txt)
        self.assertIn("quiz.studentup.in/?go=mocks", txt)
        self.assertTrue((ROOT / "docs" / "STUDENTUP_PORTAL_LINK.md")
                        .exists())


if __name__ == "__main__":
    unittest.main()
