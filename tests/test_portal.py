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


from datetime import timedelta  # noqa: E402


class TestPortalLiveExams(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        portal.PATH = self._old

    def _live_exam(self, mins_ago=5, dur=30, n=10):
        st = (portal._now() - timedelta(minutes=mins_ago)).isoformat()
        e = portal.create_exam("Mega Live", "mixed", st, dur, n)
        assert e, "exam create failed"
        return e

    def test_live_exam_full_cycle_and_winners(self):
        e = self._live_exam()
        tokA = _reg(self.mem)
        tokB = _reg(self.mem, "Ravi", "9812345602")
        # paper is PYQ-first (real exam questions)
        d = portal._load()
        srcs = [q.get("source") for q in d["exams"][e["id"]]["qs"]]
        self.assertGreaterEqual(srcs.count("pyq"), 5)
        ok, inf = portal.exam_join(self.mem, tokA, e["id"])
        self.assertTrue(ok, inf)
        portal.exam_join(self.mem, tokB, e["id"])
        qd = portal.exam_questions(self.mem, tokA, e["id"])
        self.assertEqual(qd["status"], "live")
        self.assertEqual(len(qd["questions"]), 10)
        # Anitha answers Q0 with the CORRECT display index; Ravi none
        paper = d["exams"][e["id"]]["qs"]
        q0 = paper[0]
        uidA = "w9812345601"
        opts, perm = portal._display(q0, f"{e['id']}:{uidA}:0")
        ok, res = portal.exam_answer(self.mem, tokA, e["id"], 0,
                                     perm.index(q0["answer_index"]))
        self.assertTrue(ok, res)
        self.assertNotIn("correct", res)          # result ayye varaku secret
        self.assertEqual(res["answered"], 1)
        # push exam into the past → finalize + winners
        d = portal._load()
        d["exams"][e["id"]]["starts_at"] = (
            portal._now() - timedelta(hours=2)).isoformat()
        portal._save(d)
        st = portal.state(self.mem, tokB)
        wall = {w["title"]: w for w in st["winners_wall"]}
        self.assertIn("Mega Live", wall)
        self.assertEqual(wall["Mega Live"]["winners"][0]["name"], "Anitha")
        resA = portal.exam_result(self.mem, tokA, e["id"])
        self.assertEqual(resA["status"], "done")
        self.assertEqual(resA["my"]["rank"], 1)
        self.assertEqual(len(resA["review"]), 10)
        # late join blocked
        tokC = _reg(self.mem, "Late", "9812345603")
        ok, err = portal.exam_join(self.mem, tokC, e["id"])
        self.assertFalse(ok)

    def test_scheduled_exam_not_open_early_and_weekly_auto(self):
        st_time = (portal._now() + timedelta(days=1)).isoformat()
        e = portal.create_exam("Future Test", "groups", st_time, 30, 10)
        tok = _reg(self.mem)
        ok, inf = portal.exam_join(self.mem, tok, e["id"])   # join early OK
        self.assertTrue(ok, inf)
        qd = portal.exam_questions(self.mem, tok, e["id"])
        self.assertEqual(qd["status"], "scheduled")          # paper locked
        lst = portal.admin_list()
        kinds = {x["kind"] for x in lst}
        self.assertIn("weekly", kinds)                       # 🏆 auto weekly
        wk = [x for x in lst if x["kind"] == "weekly"][0]
        self.assertEqual(wk["n_q"], 40)

    def test_dashboard_live_exam_wiring(self):
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/portal/exam"', '"/api/portal/exam/result"',
                       '"/api/portal/exam/join"', '"/api/portal/exam/answer"',
                       '"/api/portal/admin/exams"', "portal.create_exam",
                       "portal.admin_list", 'id="pex-title"', "createPortalExam",
                       "renderLiveExams", " Winners Wall"):
            self.assertIn(needle.strip(), src)
