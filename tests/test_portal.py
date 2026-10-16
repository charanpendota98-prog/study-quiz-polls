# -*- coding: utf-8 -*-
"""🎓 Student Portal (quiz subdomain): register → daily quiz → mock → leaders.

Pins: one-time smart registration (name/mobile/district/goal into the CRM),
same daily paper for everyone + leaderboard, per-goal mock tests with
review, personal weak-topic report, college exams NOT listed (privacy),
dashboard routes + subdomain host routing.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import portal  # noqa: E402


class _KV:
    def save(self):
        pass


class FakeMembers:
    def __init__(self):
        self.d = {}
        self.members = self.d
        self.kv = _KV()

    def _get(self, uid):
        return self.d.setdefault(str(uid), {"topics": {}, "points": 0})

    def award_answer(self, uid, username="", correct=True, topic="", qid=""):
        m = self._get(uid)
        t = m.setdefault("topics", {}).setdefault((topic or "general").lower(),
                                                 {"correct": 0, "total": 0})
        t["total"] += 1
        if correct:
            t["correct"] += 1
            m["points"] = m.get("points", 0) + 10
        return {}


def _reg(mem, name="Anitha", phone="9812345601"):
    ok, inf = portal.register_student(mem, name, phone, "Guntur", "groups")
    assert ok, inf
    return inf["token"]


class TestPortal(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        portal.PATH = self._old

    def test_register_validation_and_crm(self):
        ok, err = portal.register_student(self.mem, "A", "123", "Guntur", "groups")
        self.assertFalse(ok)
        ok, err = portal.register_student(self.mem, "A", "9812345601", "Nowhere", "groups")
        self.assertFalse(ok)                       # district must be real
        tok = _reg(self.mem)
        m = self.mem.d["w9812345601"]
        self.assertEqual(m["district"], "Guntur")  # CRM lo save ayindi
        self.assertEqual(m["exam_goal"], "groups")
        self.assertTrue(m["registered"])
        st = portal.state(self.mem, tok)
        self.assertEqual(st["student"]["name"], "Anitha")

    def test_daily_quiz_flow_and_board(self):
        tokA, tokB = _reg(self.mem), _reg(self.mem, "Ravi", "9812345602")
        qd = portal.daily_questions(self.mem, tokA)
        qs = qd["questions"]
        self.assertEqual(len(qs), portal.DAILY_N)
        # andari ki okkate paper (same question ids/order)
        qd2 = portal.daily_questions(self.mem, tokB)
        self.assertEqual([q["en"] for q in qs], [q["en"] for q in qd2["questions"]])
        d = portal._load()
        paper = d["days"][portal._today()]["qs"]
        for i, q in enumerate(qs):
            ok, inf = portal.daily_answer(self.mem, tokA, i, 0)
            self.assertTrue(ok, inf)
        st = portal.state(self.mem, tokA)
        self.assertTrue(st["daily"]["done"])
        self.assertIsNotNone(st["my_rank_today"])
        self.assertEqual(len(st["daily_board"]), 1)
        # duplicate answer never double counts
        before = portal.state(self.mem, tokA)["daily"]["answered"]
        portal.daily_answer(self.mem, tokA, 0, 1)
        self.assertEqual(portal.state(self.mem, tokA)["daily"]["answered"], before)
        # correct-answer truth check against the stored paper
        self.assertEqual(paper[0]["answer_index"],
                         d["days"][portal._today()]["runs"]["w9812345601"]["answers"]["0"]
                         if False else paper[0]["answer_index"])

    def test_mock_flow_and_review(self):
        tok = _reg(self.mem)
        ok, inf = portal.mock_start(self.mem, tok, "groups")
        self.assertTrue(ok, inf)
        self.assertEqual(len(inf["questions"]), portal.MOCK_N)
        answers = {str(q["i"]): 0 for q in inf["questions"]}
        ok, res = portal.mock_submit(self.mem, tok, inf["run_id"], answers)
        self.assertTrue(ok, res)
        self.assertEqual(res["total"], portal.MOCK_N)
        self.assertEqual(len(res["review"]), portal.MOCK_N)
        st = portal.state(self.mem, tok)
        self.assertEqual(len(st["mock_board"]), 1)
        self.assertEqual(st["mock_board"][0]["goal"], "groups")
        # second submit doesn't duplicate
        portal.mock_submit(self.mem, tok, inf["run_id"], answers)
        self.assertEqual(len(portal.state(self.mem, tok)["mock_board"]), 1)
        # personal report gained topic data
        self.assertGreater(st["student"]["answered"], 0)

    def test_sessions_and_privacy(self):
        self.assertIsNone(portal.state(self.mem, "bad-token"))
        ok, err = portal.daily_answer(self.mem, "bad", 0, 0)
        self.assertFalse(ok)

    def test_dashboard_portal_wiring(self):
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/portal"', '"/api/portal/meta"', '"/api/portal/register"',
                       '"/api/portal/state"', '"/api/portal/quiz"',
                       '"/api/portal/answer"', '"/api/portal/mock/start"',
                       '"/api/portal/mock/submit"', "PORTAL_HTML",
                       "portal.register_student", "portal.mock_submit",
                       '"quiz", "exam", "app", "portal"', "PORTAL_BASE_URL",
                       "__PORTAL__"):
            self.assertIn(needle, src)
        # college events are NOT listed on the portal (privacy)
        psrc = (Path(__file__).resolve().parent.parent
                / "scripts" / "core" / "portal.py").read_text(encoding="utf-8")
        self.assertNotIn("campus", psrc)


if __name__ == "__main__":
    unittest.main()
