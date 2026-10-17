# -*- coding: utf-8 -*-
"""🚀 50X Perfection round: bug-hunt R4 + perfection features.

Bug/perf pins:
  • load_bank prathi call ki full parse — mtime/size cache (perf)
  • Portal badge chips raw ids ('correct10') — icon+name labels
Feature pins: question search (q/topic/options), daily review,
resume unfinished mock, flag-a-question quality loop, my-data
export, admin student search, health portal summary, JSON-LD,
routes + JS wiring.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, brain  # noqa: E402
from core import question_bank  # noqa: E402


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
            "name": "Adv50 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0, "answers_today": 0,
            "badges": ["correct10", "first"]})

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
        ok, info = portal.register_student(self.mem, "Adv50 Tester",
                                           "9822000050", "Guntur", "railway")
        assert ok, info
        self.tok = info["token"]
        self.uid = info["uid"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestPerfection(_Base):
    def test_load_bank_cache(self):
        a = question_bank.load_bank()
        b = question_bank.load_bank()
        self.assertEqual(a, b)
        self.assertIsNot(a, b)  # callers get their own list
        self.assertGreater(len(a), 100)

    def test_badge_labels_not_raw_ids(self):
        prof = portal._profile(self.mem, self.uid)
        self.assertTrue(prof["badges"])
        for b in prof["badges"]:
            self.assertNotEqual(b, "correct10")
        self.assertTrue(any("10 Correct" in b for b in prof["badges"]))

    def test_search_practice(self):
        ok, run = portal.search_practice(self.mem, self.tok, "the")
        self.assertTrue(ok, run)
        self.assertEqual(run["mode"], "search")
        ok, msg = portal.search_practice(self.mem, self.tok, "ab")
        self.assertFalse(ok)

    def test_daily_review_partial(self):
        portal.daily_answer(self.mem, self.tok, 0, 0)
        rev = portal.daily_review(self.mem, self.tok)
        self.assertEqual(len(rev["rows"]), 1)
        self.assertFalse(rev["done"])
        self.assertIn("explanation", rev["rows"][0])

    def test_resume_mock(self):
        ok, run = portal.mock_start(self.mem, self.tok, "railway")
        self.assertTrue(ok)
        rs = portal.resume_latest(self.mem, self.tok)
        self.assertIsNotNone(rs["mock"])
        self.assertEqual(rs["mock"]["run_id"], run["run_id"])
        ok, res = portal.mock_submit(self.mem, self.tok, run["run_id"], {})
        self.assertTrue(ok)
        rs2 = portal.resume_latest(self.mem, self.tok)
        self.assertIsNone(rs2["mock"])

    def test_flag_question_dedup(self):
        ok, info = portal.flag_question(self.mem, self.tok, "Q01", "doubt")
        self.assertTrue(ok)
        ok, info = portal.flag_question(self.mem, self.tok, "Q01", "again")
        self.assertTrue(info.get("already"))
        fl = portal.question_flags()
        self.assertEqual(len(fl), 1)
        self.assertTrue(fl[0]["question"])

    def test_my_data_export(self):
        ok, info = portal.my_data_export(self.mem, self.tok)
        self.assertTrue(ok)
        self.assertTrue(info["filename"].endswith(".json"))
        self.assertIn("profile", info["text"])

    def test_admin_students(self):
        rows = portal.admin_students(self.mem, "Adv50")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], self._name())
        rows = portal.admin_students(self.mem, "no-such-person-xyz")
        self.assertEqual(rows, [])

    def _name(self):
        return "Adv50 Tester"


class TestPerfectionWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_routes_present(self):
        for route in ("/api/portal/search", "/api/portal/flag",
                      "/api/portal/daily_review", "/api/portal/resume",
                      "/api/portal/mydata",
                      "/api/portal/admin/students",
                      "/api/portal/admin/flags"):
            self.assertIn(route, self.dash)

    def test_ui_and_seo_present(self):
        for needle in ("searchPractice()", "loadDailyReview()",
                       "resumeMock()", "downloadMyData()", "flagCurrent()",
                       "application/ld+json", "FAQPage",
                       'rep["portal"]'):
            self.assertIn(needle, self.dash)


if __name__ == "__main__":
    unittest.main()
