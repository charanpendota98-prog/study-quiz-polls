# -*- coding: utf-8 -*-
"""🚀 200X: Full TE/EN toggle + Syllabus % v2 + Score Forecast v2.

Pins (probe-verified on the real bank):
  • _serve carries per-language option arrays aligned with the
    display perm (letters = original-index); 'en' students are
    scored against the SAME perm their options showed.
  • syllabus_plan: goal channels MERGED graph, exam-WEIGHTED
    coverage, case-variant topics counted once, blueprint subjects
    with zero bank questions are VISIBLE as bank_gap (honesty).
  • score_forecast v2: subject-weighted, no-data students get a
    low-confidence guessing-baseline estimate (v1 said 38-40%),
    monotone in real mastery, legacy keys untouched.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, brain  # noqa: E402


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
            "name": "Adv200 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": []})

    def award_answer(self, uid, username="", correct=True, topic="",
                     qid=""):
        return {"points": 0}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"
        self.mem = _Members()

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf

    def _reg(self, phone, goal):
        ok, info = portal.register_student(
            self.mem, "Adv200 " + phone, phone, "Guntur", goal)
        self.assertTrue(ok, info)
        return info["token"], "w" + phone


class TestLangToggle200(_Base):
    def test_split_arrays_aligned_and_scoring_consistent(self):
        tok, uid = self._reg("9822000301", "railway")
        ok, info = portal.set_lang(self.mem, tok, "en")
        self.assertTrue(ok)
        dq = portal.daily_questions(self.mem, tok)
        self.assertEqual(dq["lang"], "en")
        s = dq["questions"][0]
        self.assertEqual(len(s["options_en"]), 4)
        self.assertEqual(len(s["options_te"]), 4)
        # alignment: displayed correct position via the same perm the
        # server scores with must score correct, and its EN text must
        # be the question's real English correct option.
        day = portal._daily_paper(portal._load())
        q0 = day["qs"][0]
        _o, perm = portal._display(q0, f"{uid}:{portal._today()}:0",
                                   lang="en")
        disp = perm.index(q0["answer_index"])
        self.assertIn(str(q0["options_en"][q0["answer_index"]]),
                      s["options_en"][disp])
        self.assertIn(str(q0["options_te"][q0["answer_index"]]),
                      s["options_te"][disp])
        ok2, res = portal.daily_answer(self.mem, tok, 0, disp)
        self.assertTrue(ok2)
        self.assertTrue(res["correct"])

    def test_both_default_merged_unchanged(self):
        tok, uid = self._reg("9822000302", "railway")
        dq = portal.daily_questions(self.mem, tok)
        day = portal._daily_paper(portal._load())
        exp, _p = portal._display(day["qs"][0],
                                  f"{uid}:{portal._today()}:0")
        self.assertEqual(dq["questions"][0]["options"], exp)


class TestSyllabusPlan200(_Base):
    def test_merged_graph_weighted_coverage_and_case_once(self):
        tok, uid = self._reg("9822000303", "groups")
        sp = portal.syllabus_plan(self.mem, tok)
        self.assertIsNotNone(sp)
        # goal channels MERGED (v1 used only APPSC for groups)
        self.assertEqual(set(sp["channels"]),
                         {"APPSC", "TSPSC", "CURRENT"})
        self.assertAlmostEqual(
            sum(r["weight"] for r in sp["subjects"]), 1.0, places=2)
        wcov = round(sum(r["weight"] * 100 *
                         (r["done_topics"] / r["topics"] if r["topics"] else 0)
                         for r in sp["subjects"]))
        self.assertEqual(sp["coverage"], wcov)
        # case-variant counted once
        m = self.mem.members[uid]
        m["topics"] = {"number series": {"total": 4, "correct": 4}}
        sp2 = portal.syllabus_plan(self.mem, tok)
        self.assertEqual(sp2["topics_done"], 1)

    def test_bank_gap_visible_for_banking(self):
        tok, uid = self._reg("9822000304", "banking")
        sp = portal.syllabus_plan(self.mem, tok)
        by_subj = {r["subject"]: r for r in sp["subjects"]}
        # reasoning carries 35% blueprint weight, bank has none → gap
        self.assertIn("reasoning", sp["bank_gaps"])
        self.assertTrue(by_subj["reasoning"]["bank_gap"])
        self.assertEqual(by_subj["reasoning"]["bank_q"], 0)


class TestForecastV2(_Base):
    def test_low_confidence_baseline_and_monotonic(self):
        tok, uid = self._reg("9822000305", "railway")
        fc = portal.score_forecast(self.mem, tok)
        self.assertIn("v2", fc)
        self.assertEqual(fc["v2"]["confidence"], "low")
        self.assertLessEqual(fc["v2"]["expected_pct"], 35)
        self.assertLessEqual(fc["low"], fc["expected_pct"])
        self.assertLessEqual(fc["expected_pct"], fc["high"])
        # strong mastery must raise v2 (never below the weak student)
        m = self.mem.members[uid]
        m["topics"] = {"number series": {"total": 20, "correct": 4},
                       "clock": {"total": 20, "correct": 4},
                       "General Science": {"total": 10, "correct": 2}}
        weak = portal.score_forecast(self.mem, tok)["v2"]["expected_pct"]
        m["topics"] = {"number series": {"total": 20, "correct": 19},
                       "clock": {"total": 20, "correct": 18},
                       "General Science": {"total": 10, "correct": 9}}
        strong = portal.score_forecast(self.mem, tok)["v2"]["expected_pct"]
        self.assertGreater(strong, weak)
        self.assertGreaterEqual(strong, 60)

    def test_state_exposes_syllabus_v1(self):
        tok, uid = self._reg("9822000306", "railway")
        st = portal.state(self.mem, tok)
        self.assertIn("syllabus_v1", st)
        self.assertIsNotNone(st["syllabus_v1"])


class TestWiring200(unittest.TestCase):
    def test_dashboard_wiring(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        for needle in ("/api/portal/syllabus2", "function optText",
                       "optText(q, oi, opt)", "d.v2",
                       "Forecast v2", "(exam-weighted)"):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
