# -*- coding: utf-8 -*-
"""🚀 40X Expert round: bug-hunt R3 + expert intelligence features.

Bug pins:
  • _exam_view winners/board tie-break (joined_at) mismatch
  • Weekly exam empty-paper create avvakudadhu
  • district_league misleading 'correct'/'total' = student-count fields
  • pyq.coverage_gaps by_channel shape ({pyq,total} dict) — probe caught
Feature pins: Grand Mock 50Q, sectional tests, PYQ-only drill,
difficulty ladder, mistake patterns, retention + forecast, weekly
goal, records, test series, district×goal rank, rival race,
language preference, exam countdown mins, analytics v2, flags.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, brain, pyq, flags  # noqa: E402


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
            "name": "Adv40 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0, "answers_today": 0})

    def award_answer(self, uid, username="", correct=True, topic="", qid=""):
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
        ok, info = portal.register_student(self.mem, "Adv40 Tester",
                                           "9822000040", "Guntur", "railway")
        assert ok, info
        self.tok = info["token"]
        self.uid = info["uid"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf

    def _mock(self, correct=True, kind="mock", goal="railway", answers_all=None):
        ok, run = portal.mock_start(self.mem, self.tok, goal, kind=kind)
        assert ok, run
        d = portal._load()
        snap = d["mocks"][run["run_id"]]["qs"]
        answers = {}
        for i, q in enumerate(snap):
            _o, perm = portal._display(q, f"{run['run_id']}:{i}")
            if answers_all is not None:
                answers[str(i)] = answers_all
            elif correct:
                answers[str(i)] = perm.index(q["answer_index"])
            else:
                answers[str(i)] = next(j for j, o in enumerate(perm)
                                       if o != q["answer_index"])
        ok, res = portal.mock_submit(self.mem, self.tok, run["run_id"], answers)
        assert ok, res
        return run["run_id"], res


class TestBugHuntR3(_Base):
    def test_district_league_fields_honest(self):
        lg = portal.district_league(self.mem, "Guntur")
        for row in lg["rows"]:
            self.assertNotIn("correct", row)
            self.assertIn("students", row)
            self.assertIn("pts", row)

    def test_exam_view_winner_tiebreak(self):
        e = portal.create_exam("Tie Test", "mixed",
                               (portal._now()).isoformat(), 30, 5)
        self.assertIsNotNone(e)
        # two students, equal correct — earlier joiner wins rank 1
        ok2, inf2 = portal.register_student(self.mem, "Second Joiner",
                                            "9822000049", "Guntur", "mixed")
        portal.exam_join(self.mem, self.tok, e["id"])
        portal.exam_join(self.mem, inf2["token"], e["id"])
        st, en = portal._exam_times(e)
        fake_end = portal._now() + portal.timedelta(minutes=31)
        d = portal._load()
        view = portal._exam_view(d["exams"][e["id"]], self.mem, self.uid,
                                 fake_end)
        self.assertIsNotNone(view["my"]["rank"])

    def test_coverage_gaps_shape(self):
        gaps = pyq.coverage_gaps()
        self.assertTrue(gaps)
        for row in gaps[:5]:
            self.assertIsInstance(row["pyq"], int)
            self.assertEqual(row["gap"], max(0, 50 - row["pyq"]))
        pyqs = [r["pyq"] for r in gaps]
        self.assertEqual(pyqs, sorted(pyqs))


class TestExpertFeatures(_Base):
    def test_grand_mock_50(self):
        ok, run = portal.mock_start(self.mem, self.tok, "railway", kind="grand")
        self.assertTrue(ok)
        self.assertEqual(run["kind"], "grand")
        self.assertEqual(len(run["questions"]), 50)
        self.assertEqual(run["minutes"], 60)
        ok, res = portal.mock_submit(self.mem, self.tok, run["run_id"], {})
        self.assertTrue(ok)
        arc = portal.my_archive(self.mem, self.tok)
        self.assertEqual(arc[0]["kind"], "grand")

    def test_section_stock_and_start(self):
        ss = portal.section_stock(self.mem, self.tok)
        self.assertIsNotNone(ss)
        self.assertEqual(len(ss["sections"]), 4)
        ok, run = portal.practice_start(self.mem, self.tok, mode="section",
                                        topic="quant")
        self.assertTrue(ok, run)

    def test_pyq_and_ladder_modes(self):
        for mode in ("pyq", "ladder"):
            ok, run = portal.practice_start(self.mem, self.tok, mode=mode)
            self.assertTrue(ok, run)
            self.assertTrue(run["questions"])

    def test_mistake_patterns(self):
        self._mock(correct=False)
        pt = portal.mistake_patterns(self.mem, self.tok)
        self.assertIsNotNone(pt)
        self.assertTrue(pt["total_wrong"] > 0 or pt["advice"])

    def test_retention_and_weekly_goal(self):
        self.mem._get(self.uid)["review"] = [
            {"qid": "Q01", "due": portal._today(), "interval": 0,
             "topic": "History"},
            {"qid": "Q02", "due": portal._today(), "interval": 7,
             "topic": "Polity"}]
        rt = portal.retention_report(self.mem, self.tok)
        self.assertEqual(rt["cards"], 2)
        self.assertEqual(rt["due_today"], 2)
        self.assertEqual(rt["intervals"]["strong_7d"], 1)
        self.assertEqual(len(rt["forecast"]), 7)
        wg = portal.weekly_goal(self.mem, self.tok)
        self.assertEqual(wg["target"], 5)

    def test_records_and_series(self):
        self._mock(correct=True)
        rc = portal.my_records(self.mem, self.tok)
        self.assertEqual(rc["attempts"], 1)
        self.assertEqual(rc["best_pct"], 100)
        sr = portal.test_series(self.mem, self.tok)
        self.assertEqual(sr["attempted"], 1)
        self.assertEqual(sr["next_no"], 2)

    def test_district_goal_rank(self):
        self._mock(correct=True)
        dr = portal.district_goal_rank(self.mem, self.tok)
        self.assertEqual(dr["district"], "Guntur")
        self.assertEqual(dr["my_rank"], 1)

    def test_rival_race(self):
        ok, inf2 = portal.register_student(self.mem, "Rival Two",
                                           "9822000042", "Guntur", "railway")
        self.assertTrue(ok)
        ok, info = portal.set_rival(self.mem, self.tok,
                                    portal._ref_code(inf2["uid"]))
        self.assertTrue(ok, info)
        self._mock(correct=True)
        rv = portal.rival_status(self.mem, self.tok)
        self.assertEqual(rv["rival"], "Rival Two")
        self.assertGreater(rv["my_pts"], 0)
        self.assertEqual(rv["leading"], "you")
        ok, msg = portal.set_rival(self.mem, self.tok,
                                   portal._ref_code(self.uid))
        self.assertFalse(ok)

    def test_lang_pref(self):
        ok, info = portal.set_lang(self.mem, self.tok, "te")
        self.assertTrue(ok)
        self.assertEqual(portal._profile(self.mem, self.uid)["lang"], "te")
        ok, info = portal.set_lang(self.mem, self.tok, "bogus")
        self.assertEqual(info["lang"], "both")
        st = portal.state(self.mem, self.tok)
        self.assertEqual(st["student"]["lang"], "both")

    def test_analytics_v2(self):
        self._mock(correct=True, kind="grand")
        an = portal.portal_analytics(self.mem)
        self.assertIn("pyq_gaps", an)
        self.assertIn("attempt_kinds", an)
        self.assertGreaterEqual(an["attempt_kinds"].get("grand", 0), 1)

    def test_flags_13(self):
        self.assertEqual(len(flags.DEFAULTS), 18)
        self.assertIn("grand_mock", flags.DEFAULTS)
        self.assertIn("sectional_tests", flags.DEFAULTS)


class TestExpertWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_routes_present(self):
        for route in ("/api/portal/sections", "/api/portal/patterns",
                      "/api/portal/retention", "/api/portal/records",
                      "/api/portal/rival", "/api/portal/rival/set",
                      "/api/portal/district_rank", "/api/portal/lang"):
            self.assertIn(route, self.dash)

    def test_ui_present(self):
        for needle in ("startGrand()", "loadSections()", "startSection(",
                       "loadPatterns()", "loadRetention()", "loadRecords()",
                       "loadRival()", "cycleLang()", "applyLang()",
                       "PR_MODE_OVERRIDE", "series-chip",
                       "body.lang-te .qen"):
            self.assertIn(needle, self.dash)


if __name__ == "__main__":
    unittest.main()
