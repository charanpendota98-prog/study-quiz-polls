# -*- coding: utf-8 -*-
"""🚀 70X Perfection round: focus, mistakes, hub, reminders, admin UI.

Feature pins (probe-verified before pinning):
  • Focus Timer: log_study clamps 1–240, focus_log separate field
    (daylog [answered, correct] list shape untouchable), state focus
  • Mistake Notebook: ONLY answered-wrong questions (unanswered must
    NOT count), correct answer + explanation, .txt download shape
  • Notice Center: goal-filtered full notice list
  • Exam-wise Goal Hub: stock/papers/attempts/best/next + validation
  • Live Exam reminder: set/unset stored, state rows carry 'remind'
  • Admin Students/Flags UI wiring + new routes + SPA functions
  • flags = 18 (+focus_timer, goal_hub, mistake_notebook)
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
            "name": "Adv70 Tester", "district": "Guntur", "points": 0,
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
        ok, info = portal.register_student(self.mem, "Adv70 Tester",
                                           "9822000070", "Guntur",
                                           "railway")
        assert ok, info
        self.tok = info["token"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf

    def _wrong_practice_answer(self):
        ok, run = portal.practice_start(self.mem, self.tok, "polity")
        assert ok, run
        d = portal._load()
        snap = d["practice"][run["run_id"]]["qs"][0]
        _opts, perm = portal._display(snap, f"{run['run_id']}:0")
        correct_disp = perm.index(snap["answer_index"])
        wrong = (correct_disp + 1) % len(_opts)
        ok, res = portal.practice_answer(self.mem, self.tok,
                                         run["run_id"], 0, wrong)
        assert ok, res
        assert res.get("correct") is False, res
        return run


class TestFlags70(_Base):
    def test_flags_18_and_new_enabled(self):
        self.assertEqual(len(flags.all_flags()), 20)
        for f in ("focus_timer", "goal_hub", "mistake_notebook"):
            self.assertTrue(flags.enabled(f), f)


class TestFocus70(_Base):
    def test_log_study_accumulates_and_clamps(self):
        ok, r = portal.log_study(self.mem, self.tok, 25)
        self.assertTrue(ok, r)
        self.assertEqual(r["today_min"], 25)
        ok, r = portal.log_study(self.mem, self.tok, 999)
        self.assertTrue(ok, r)
        self.assertEqual(r["logged"], 240)  # clamp
        self.assertEqual(r["today_min"], 265)
        self.assertGreaterEqual(r["week_min"], 265)
        ok, _e = portal.log_study(self.mem, "badtoken", 10)
        self.assertFalse(ok)

    def test_state_carries_focus_and_daylog_shape_untouched(self):
        portal.log_study(self.mem, self.tok, 15)
        st = portal.state(self.mem, self.tok)
        self.assertEqual(st["focus"]["today_min"], 15)
        m = self.mem._get("w9822000070")
        for v in (m.get("daylog") or {}).values():
            self.assertIsInstance(v, list)  # [answered, correct] shape


class TestMistakes70(_Base):
    def test_notebook_counts_only_answered_wrong(self):
        ok, nb = portal.mistake_notebook(self.mem, self.tok)
        self.assertTrue(ok, nb)
        self.assertEqual(nb["count"], 0)  # nothing answered yet
        self._wrong_practice_answer()
        ok, nb = portal.mistake_notebook(self.mem, self.tok)
        self.assertTrue(ok, nb)
        self.assertEqual(nb["count"], 1)  # unanswered 9 must NOT count
        self.assertTrue(nb["filename"].endswith(".txt"))
        self.assertIn("Correct:", nb["text"])
        self.assertIn("Mistake Notebook", nb["text"])

    def test_notebook_bad_token(self):
        ok, _e = portal.mistake_notebook(self.mem, "badtoken")
        self.assertFalse(ok)


class TestNoticesHubRemind70(_Base):
    def test_notices_for_goal_filtered(self):
        portal.add_notice("For all", "b", "")
        portal.add_notice("Railway only", "b", "", goal="railway")
        portal.add_notice("SSC only", "b", "", goal="ssc")
        ok, nf = portal.notices_for(self.mem, self.tok)
        self.assertTrue(ok, nf)
        titles = [n["title"] for n in nf["notices"]]
        self.assertIn("For all", titles)
        self.assertIn("Railway only", titles)
        self.assertNotIn("SSC only", titles)

    def test_goal_hub(self):
        ok, hub = portal.goal_hub(self.mem, self.tok, "railway")
        self.assertTrue(ok, hub)
        self.assertEqual(hub["goal"], "railway")
        self.assertGreaterEqual(hub["total"], hub["pyq"])
        self.assertIn("next", hub)
        self.assertIn("topics", hub)
        ok, _e = portal.goal_hub(self.mem, self.tok, "bogusgoal")
        self.assertFalse(ok)

    def test_exam_reminder_set_unset(self):
        ok, r = portal.set_exam_reminder(self.mem, self.tok, "EX-T", True)
        self.assertTrue(ok, r)
        self.assertTrue(r["remind"])
        ok, r = portal.set_exam_reminder(self.mem, self.tok, "EX-T", False)
        self.assertTrue(ok, r)
        self.assertFalse(r["remind"])
        ok, _e = portal.set_exam_reminder(self.mem, "badtoken", "EX-T")
        self.assertFalse(ok)


class TestWiring70(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        cls.ign = (ROOT / ".gitignore").read_text(encoding="utf-8")

    def test_new_routes_exist(self):
        for r in ('p.path == "/api/portal/mistakes"',
                  'p.path == "/api/portal/notices"',
                  'p.path == "/api/portal/goal_hub"',
                  'p.path == "/api/portal/focus"',
                  'p.path == "/api/portal/exam/remind"'):
            self.assertIn(r, self.dash)

    def test_spa_functions_exist(self):
        for fn in ("downloadMistakes", "showAllNotices", "focusToggle",
                   "focusPreset", "loadGoalHub", "remindExam",
                   "searchAdminStudents", "loadAdminFlags",
                   "loadPortalAnalytics"):
            self.assertIn(fn, self.dash)
        for el in ('id="focus-card"', 'id="focus-clock"', 'id="hub-chips"',
                   'id="goal-hub"', 'id="pt-students"', 'id="pt-flags"'):
            self.assertIn(el, self.dash)

    def test_gitignore_keeps_schedules_ignored(self):
        self.assertIn("data/whatsapp_schedules.json", self.ign)


if __name__ == "__main__":
    unittest.main()
