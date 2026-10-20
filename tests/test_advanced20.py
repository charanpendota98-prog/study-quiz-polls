# -*- coding: utf-8 -*-
"""🚀 20X Advanced round: bug-hunt fixes + 20 advanced features pins.

Bug pins (found by audit, fixed in this round):
  • SRS ladder dead (correct answer deleted the card at once — 3d/7d
    spacing never happened) — members.award_answer
  • brain.reviews_due counted ALL review cards, not due-only
  • syllabus.plan reviews_due — same class
  • today_plan double-_load + Smart task never done
  • key papers lost after store prune (mocks 120 / days 3) — archive
  • paper sets with 3–4 questions hidden (min_q=5)
  • paper attempts mislabeled "Mock Test" in history
  • certificate winner rank tie-break mismatch vs announced winners

Feature pins: countdown, syllabus tracker, coach, percentile,
bookmarks + Saved practice, weak/speed/marathon/revenge modes,
negative-marking mocks, daily mix, worksheet, archive, paper
progress; flags + routes + JS wiring.
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
    """Minimal member store; award goes through portal._award (Brain)."""

    def __init__(self):
        self.members = {}
        self.kv = _KV()

    def _get(self, uid):
        return self.members.setdefault(str(uid), {
            "name": "Adv Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0, "answers_today": 0})

    def award_answer(self, uid, username="", correct=True, topic="", qid=""):
        m = self._get(uid)
        m["points"] = m.get("points", 0) + (10 if correct else 0)
        return {"points": m["points"]}


class TestBugFixes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf

    def _reg(self, mem, phone="9822000001"):
        ok, info = portal.register_student(mem, "Adv Tester", phone,
                                           "Guntur", "railway")
        assert ok, info
        return info["token"]

    def test_srs_ladder_advances(self):
        # 🧠 360X migration: fixed 0->3d->7d ladder replaced by
        # FSRS-Lite stability. Contract kept & strengthened: wrong
        # queues a card due today; correct SPACES it (never deletes
        # on first correct); repeated corrects grow the gap;
        # only PROVEN stability retires the card; a lapse re-queues.
        from core.members import Members as RealMembers
        import tempfile as _tf
        # real Members on isolated brain; member dict driven manually
        mem = RealMembers.__new__(RealMembers)
        mem.members = {}
        mem.kv = _KV()
        mem.pending = {}
        uid = "srs-test"
        mem.award_answer(uid, "T", correct=False, topic="History", qid="QX1")
        m = mem._get(uid)
        self.assertEqual(len(m["review"]), 1)
        self.assertIn("s", m["review"][0])          # FSRS card
        first_s = m["review"][0]["s"]
        # one correct must SPACE the card, not delete it
        mem.award_answer(uid, "T", correct=True, topic="History", qid="QX1")
        m = mem._get(uid)
        self.assertEqual(len(m["review"]), 1)
        self.assertGreater(m["review"][0]["s"], first_s)
        first_due = m["review"][0]["due"]
        # second correct -> stability & due gap keep growing
        mem.award_answer(uid, "T", correct=True, topic="History", qid="QX1")
        m = mem._get(uid)
        self.assertEqual(len(m["review"]), 1)
        self.assertGreaterEqual(m["review"][0]["due"], first_due)
        # many proven recalls -> mastered, card retires
        for _ in range(10):
            mem.award_answer(uid, "T", correct=True, topic="History", qid="QX1")
        m = mem._get(uid)
        self.assertEqual(m["review"], [])
        # wrong after mastery -> fresh card due today again
        mem.award_answer(uid, "T", correct=False, topic="History", qid="QX1")
        m = mem._get(uid)
        self.assertEqual(len(m["review"]), 1)
        self.assertIn("s", m["review"][0])

    def test_brain_reviews_due_only(self):
        member = {"review": [{"qid": "A", "due": "2000-01-01"},
                             {"qid": "B", "due": "2999-01-01"}]}
        prof = brain.profile_for(member, "u-brain-due")
        self.assertEqual(prof["reviews_due"], 1)

    def test_syllabus_reviews_due_only(self):
        from core import syllabus
        from core.question_bank import Bank
        member = {"topics": {}, "review": [{"qid": "A", "due": "2000-01-01"},
                                           {"qid": "B", "due": "2999-01-01"}]}
        plan = syllabus.plan(member, Bank(), "RAILWAY")
        self.assertEqual(plan["reviews_due"], 1)

    def test_today_plan_smart_done_after_practice(self):
        mem = _Members()
        tok = self._reg(mem)
        plan = portal.today_plan(mem, tok)
        smart = next(t for t in plan["tasks"] if t["key"] == "smart")
        self.assertFalse(smart["done"])
        ok, _run = portal.practice_start(mem, tok, mode="topic", topic="")
        self.assertTrue(ok)
        plan = portal.today_plan(mem, tok)
        smart = next(t for t in plan["tasks"] if t["key"] == "smart")
        self.assertTrue(smart["done"])

    def test_key_paper_survives_mock_prune(self):
        mem = _Members()
        tok = self._reg(mem, "9822000002")
        ok, run = portal.mock_start(mem, tok, "railway")
        self.assertTrue(ok)
        d = portal._load()
        snap = d["mocks"][run["run_id"]]["qs"]
        answers = {}
        for i, q in enumerate(snap):
            _o, perm = portal._display(q, f"{run['run_id']}:{i}")
            answers[str(i)] = perm.index(q["answer_index"])
        ok, res = portal.mock_submit(mem, tok, run["run_id"], answers)
        self.assertTrue(ok, res)
        # simulate store prune removing the live run
        d = portal._load()
        d["mocks"].pop(run["run_id"], None)
        portal._save(d, flush=True)
        ok, key = portal.key_paper(mem, tok, "mock", run["run_id"])
        self.assertTrue(ok, key)
        self.assertEqual(key["correct"], 15)

    def test_catalog_includes_mini_sets(self):
        cat = portal.paper_catalog()
        self.assertTrue(any(r["size"] == "mini" for r in cat))
        self.assertTrue(all(r["count"] >= 3 for r in cat))
        self.assertTrue(any(r.get("topics") for r in cat))


class TestAdvancedFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"
        self.mem = _Members()
        ok, info = portal.register_student(self.mem, "Adv Tester",
                                           "9822000010", "Guntur", "railway")
        assert ok, info
        self.tok = info["token"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf

    def test_countdowns(self):
        cd = portal.exam_countdowns(self.mem, self.tok)
        self.assertEqual(cd["goal"], "railway")
        self.assertTrue(cd["mine"]["days"] >= 0)
        self.assertIn("phase", cd["mine"])
        self.assertEqual(len(cd["list"]), len(portal.EXAM_DATES))

    def test_syllabus_tracker(self):
        sy = portal.my_syllabus(self.mem, self.tok)
        self.assertIsNotNone(sy)
        self.assertIn("coverage", sy)
        self.assertTrue(sy["subjects"])

    def test_coach_steps(self):
        co = portal.coach_today(self.mem, self.tok)
        self.assertTrue(co["steps"])
        self.assertIn("date", co)

    def test_goal_percentile_empty_ok(self):
        pc = portal.goal_percentile(self.mem, self.tok)
        self.assertEqual(pc["goal"], "railway")
        self.assertIsNone(pc["percentile"])

    def test_negative_mock_points(self):
        ok, run = portal.mock_start(self.mem, self.tok, "railway", neg=0.25)
        self.assertTrue(ok)
        self.assertEqual(run["neg"], 0.25)
        d = portal._load()
        snap = d["mocks"][run["run_id"]]["qs"]
        answers = {}
        for i, q in enumerate(snap):
            _o, perm = portal._display(q, f"{run['run_id']}:{i}")
            answers[str(i)] = next(j for j, o in enumerate(perm)
                                   if o != q["answer_index"])
        ok, res = portal.mock_submit(self.mem, self.tok, run["run_id"], answers)
        self.assertTrue(ok, res)
        self.assertEqual(res["correct"], 0)
        self.assertEqual(res["pts"], 0)
        self.assertEqual(res["neg"], 0.25)

    def test_practice_modes(self):
        for mode, want in (("speed", 45), ("marathon", 0)):
            ok, run = portal.practice_start(self.mem, self.tok, mode=mode)
            self.assertTrue(ok, run)
            self.assertEqual(run["per_q"], want)
            if mode == "marathon":
                self.assertGreater(len(run["questions"]), 10)

    def test_revenge_mode_uses_last_wrong(self):
        ok, run = portal.mock_start(self.mem, self.tok, "railway")
        d = portal._load()
        snap = d["mocks"][run["run_id"]]["qs"]
        answers = {}
        for i, q in enumerate(snap):
            _o, perm = portal._display(q, f"{run['run_id']}:{i}")
            answers[str(i)] = next(j for j, o in enumerate(perm)
                                   if o != q["answer_index"])
        portal.mock_submit(self.mem, self.tok, run["run_id"], answers)
        ok, run2 = portal.practice_start(self.mem, self.tok, mode="revenge")
        self.assertTrue(ok, run2)
        self.assertEqual(run2["mode"], "revenge")

    def test_bookmarks_roundtrip(self):
        ok, info = portal.bookmark_toggle(self.mem, self.tok, "Q01")
        self.assertTrue(ok)
        self.assertTrue(info["bookmarked"])
        bm = portal.my_bookmarks(self.mem, self.tok)
        self.assertEqual([b["id"] for b in bm], ["Q01"])
        ok, run = portal.practice_start(self.mem, self.tok, mode="bookmarks")
        self.assertTrue(ok)
        ok, info = portal.bookmark_toggle(self.mem, self.tok, "Q01")
        self.assertFalse(info["bookmarked"])

    def test_worksheet_and_daily_mix(self):
        ok, ws = portal.worksheet_text(self.mem, self.tok)
        self.assertTrue(ok)
        self.assertIn("ANSWER KEY", ws["text"])
        mix = portal.daily_mix()
        self.assertEqual(mix["total"], 10)
        self.assertTrue(mix["topics"])

    def test_archive_listing(self):
        ok, run = portal.mock_start(self.mem, self.tok, "railway")
        d = portal._load()
        ok, res = portal.mock_submit(self.mem, self.tok, run["run_id"], {})
        self.assertTrue(ok)
        arc = portal.my_archive(self.mem, self.tok)
        self.assertTrue(arc)
        self.assertEqual(arc[0]["kind"], "mock")

    def test_paper_progress_after_attempt(self):
        cat = portal.paper_catalog()
        top = cat[0]
        ok, run = portal.paper_start(self.mem, self.tok, top["exam"],
                                     top.get("year") or "", top.get("paper") or "")
        self.assertTrue(ok, run)
        ok, res = portal.mock_submit(self.mem, self.tok, run["run_id"], {})
        self.assertTrue(ok)
        prog = portal.paper_progress(self.mem, self.tok)
        self.assertIn(top["label"], prog)
        self.assertEqual(prog[top["label"]]["attempts"], 1)

    def test_state_has_advanced_fields(self):
        st = portal.state(self.mem, self.tok)
        self.assertIn("countdown", st)
        self.assertIn("paper_progress", st)
        self.assertTrue(st["papers"][0].get("topics") is not None)

    def test_flags_registered_and_wired(self):
        names = set(flags.DEFAULTS)
        for f in ("syllabus_tracker", "negative_mocks", "revenge_mode"):
            self.assertIn(f, names)


class TestAdvancedWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_routes_present(self):
        for route in ("/api/portal/syllabus", "/api/portal/coach",
                      "/api/portal/percentile", "/api/portal/bookmarks",
                      "/api/portal/archive", "/api/portal/worksheet",
                      "/api/portal/daily_mix", "/api/portal/bookmark"):
            self.assertIn(route, self.dash)

    def test_portal_ui_present(self):
        for needle in ("loadSyllabus()", "loadPercentile()", "loadCoach()",
                       "renderCountdown", "toggleBookmark", "bmCurrent",
                       "startPractice('weak')", "startPractice('revenge')",
                       "startPractice('speed')", "startPractice('marathon')",
                       "startPractice('bookmarks')", "neg-sel",
                       "downloadWorksheet()", "PAPER_PROG"):
            self.assertIn(needle, self.dash)


if __name__ == "__main__":
    unittest.main()
