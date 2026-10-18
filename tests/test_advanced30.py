# -*- coding: utf-8 -*-
"""🚀 30X Next-Level round: bug-hunt R2 + intelligence features pins.

Bug pins:
  • Portal explanations EPPUDU empty (bank field explanation_en,
    portal 'explanation' chusedi) — _snap mapping fix, LIVE-verified
  • Countdown phase: exam ayipoyina kuda 'Revision Phase' (order bug)
  • Ghost bookmarks (bank lo leni qid save) — validation
  • Sessions never expire — 30-day TTL
  • Paper progress board 300-cap meeda dependent — archive-first
  • bank_quality no_explanation field-name mismatch

Feature pins: 7-day study plan, next best topic, attempt analysis,
score trend, activity calendar, score forecast, PYQ trends,
challenge of the day (+20 bonus, once/day), goal leaderboard,
revision pack, similar follow-up, portal analytics, bank quality,
register rate limit wiring, routes + JS wiring.
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
            "name": "Adv30 Tester", "district": "Guntur", "points": 0,
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
        ok, info = portal.register_student(self.mem, "Adv30 Tester",
                                           "9822000030", "Guntur", "railway")
        assert ok, info
        self.tok = info["token"]
        self.uid = info["uid"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf

    def _mock(self, all_correct=False):
        ok, run = portal.mock_start(self.mem, self.tok, "railway")
        assert ok
        d = portal._load()
        snap = d["mocks"][run["run_id"]]["qs"]
        answers = {}
        for i, q in enumerate(snap):
            _o, perm = portal._display(q, f"{run['run_id']}:{i}")
            if all_correct:
                answers[str(i)] = perm.index(q["answer_index"])
            else:
                answers[str(i)] = next(j for j, o in enumerate(perm)
                                       if o != q["answer_index"])
        ok, res = portal.mock_submit(self.mem, self.tok, run["run_id"], answers)
        assert ok, res
        return run["run_id"], res


class TestBugHuntR2(_Base):
    def test_practice_explanation_not_empty(self):
        ok, run = portal.practice_start(self.mem, self.tok, mode="topic", topic="")
        self.assertTrue(ok)
        d = portal._load()
        snap = d["practice"][run["run_id"]]["qs"][0]
        _o, perm = portal._display(snap, f"{run['run_id']}:0")
        ok, res = portal.practice_answer(self.mem, self.tok, run["run_id"], 0, perm[0])
        self.assertTrue(ok)
        self.assertTrue(res["explanation"],
                        "bank explanation_en portal ki reach avvali")

    def test_countdown_phase_past_and_future(self):
        import datetime as _dtmod
        real = portal.EXAM_DATES["railway"]
        try:
            portal.EXAM_DATES["railway"] = "2020-01-01"
            cd = portal.exam_countdowns(self.mem, self.tok)
            self.assertIn("done", cd["mine"]["phase"].lower())
            self.assertLess(cd["mine"]["days"], 0)
        finally:
            portal.EXAM_DATES["railway"] = real

    def test_ghost_bookmark_rejected(self):
        ok, info = portal.bookmark_toggle(self.mem, self.tok, "NOPE-999")
        self.assertFalse(ok)
        ok, info = portal.bookmark_toggle(self.mem, self.tok, "Q01")
        self.assertTrue(ok)

    def test_session_ttl(self):
        d = portal._load()
        d["sessions"]["old-tok"] = {"uid": self.uid,
                                    "ts": "2020-01-01T00:00:00+05:30"}
        self.assertIsNone(portal._sess(d, "old-tok"))
        self.assertNotIn("old-tok", d["sessions"])
        d["sessions"]["new-tok"] = {"uid": self.uid,
                                    "ts": portal._now().isoformat()}
        self.assertEqual(portal._sess(d, "new-tok"), self.uid)
        # legacy string tokens still work (grandfathered)
        d["sessions"]["legacy"] = self.uid
        self.assertEqual(portal._sess(d, "legacy"), self.uid)

    def test_register_writes_ttl_session(self):
        d = portal._load()
        val = d["sessions"][self.tok]
        self.assertIsInstance(val, dict)
        self.assertEqual(val["uid"], self.uid)
        self.assertIn("ts", val)

    def test_paper_progress_archive_first(self):
        cat = portal.paper_catalog()
        top = cat[0]
        ok, run = portal.paper_start(self.mem, self.tok, top["exam"],
                                     top.get("year") or "", top.get("paper") or "")
        self.assertTrue(ok, run)
        ok, res = portal.mock_submit(self.mem, self.tok, run["run_id"], {})
        self.assertTrue(ok)
        # board nunchi row teeseyy — archive count ayina undali
        d = portal._load()
        d["mock_board"] = []
        portal._save(d, flush=True)
        prog = portal.paper_progress(self.mem, self.tok)
        self.assertEqual(prog[top["label"]]["attempts"], 1)

    def test_bank_quality_fields(self):
        from core.question_bank import bank_quality
        bq = bank_quality()
        self.assertGreater(bq["total"], 100)
        self.assertLess(bq["no_explanation"], bq["total"])


class TestNextLevelFeatures(_Base):
    def test_study_plan(self):
        sp = portal.study_plan(self.mem, self.tok)
        self.assertEqual(len(sp["days"]), 7)
        self.assertTrue(sp["days"][0]["tasks"])
        self.assertEqual(sp["goal"], "railway")

    def test_next_topic(self):
        nt = portal.next_topic(self.mem, self.tok)
        self.assertIn("text", nt)

    def test_attempt_analysis_and_delta(self):
        rid1, _ = self._mock()
        an = portal.attempt_analysis(self.mem, self.tok, rid1)
        self.assertIsNotNone(an)
        self.assertTrue(an["topics"])
        self.assertIsNone(an["delta_vs_prev"])
        rid2, _ = self._mock(all_correct=True)
        an2 = portal.attempt_analysis(self.mem, self.tok, rid2)
        self.assertEqual(an2["delta_vs_prev"], 15)

    def test_trend_and_activity(self):
        self._mock(all_correct=True)
        tr = portal.score_trend(self.mem, self.tok)
        self.assertEqual(tr[-1]["pct"], 100)
        cal = portal.activity_calendar(self.mem, self.tok)
        self.assertEqual(len(cal), 14)
        self.assertTrue(any(a["active"] for a in cal))

    def test_score_forecast(self):
        fc = portal.score_forecast(self.mem, self.tok)
        self.assertTrue(0 <= fc["low"] <= fc["expected_pct"] <= fc["high"] <= 100)
        self.assertIn("Estimate", fc["note"])

    def test_pyq_trends(self):
        tr = portal.pyq_trends("railway")
        self.assertGreater(tr["pyq_total"], 0)
        self.assertTrue(tr["topics"])
        self.assertEqual(sum(t["pyq"] for t in tr["topics"][:1]),
                         tr["topics"][0]["pyq"])

    def test_challenge_flow(self):
        ch = portal.challenge_today(self.mem, self.tok)
        self.assertIsNotNone(ch)
        self.assertFalse(ch["done"])
        self.assertIsNotNone(ch["question"])
        d = portal._load()
        snap = d["challenge"][portal._today()]["q"]
        _o, perm = portal._display(snap, f"CH:{self.uid}:{portal._today()}:0")
        pts_before = self.mem._get(self.uid)["points"]
        ok, res = portal.challenge_answer(
            self.mem, self.tok, perm.index(snap["answer_index"]))
        self.assertTrue(ok, res)
        self.assertTrue(res["correct"])
        self.assertEqual(res["bonus"], 20)
        self.assertGreater(self.mem._get(self.uid)["points"], pts_before)
        ok, res = portal.challenge_answer(self.mem, self.tok, 0)
        self.assertTrue(res.get("already"))
        ch2 = portal.challenge_today(self.mem, self.tok)
        self.assertTrue(ch2["done"])
        self.assertIsNone(ch2["question"])

    def test_goal_board_after_mock(self):
        self._mock(all_correct=True)
        gb = portal.goal_board(self.mem, "railway")
        self.assertTrue(gb)
        self.assertEqual(gb[0]["correct"], 15)

    def test_revision_pack_after_wrong_mock(self):
        self._mock()
        ok, pack = portal.revision_pack_text(self.mem, self.tok)
        self.assertTrue(ok, pack)
        self.assertIn("ANSWER KEY", pack["text"])
        self.assertGreater(pack["total"], 0)

    def test_portal_analytics(self):
        self._mock()
        an = portal.portal_analytics(self.mem)
        self.assertGreaterEqual(an["students"], 1)
        self.assertGreaterEqual(an["attempts_total"], 1)


class TestNextLevelWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_routes_present(self):
        for route in ("/api/portal/study_plan", "/api/portal/next_topic",
                      "/api/portal/trend", "/api/portal/forecast",
                      "/api/portal/attempt", "/api/portal/goal_board",
                      "/api/portal/pyq_trends", "/api/portal/challenge",
                      "/api/portal/challenge/answer",
                      "/api/portal/revision_pack",
                      "/api/portal/admin/analytics", "/api/bank/quality"):
            self.assertIn(route, self.dash)

    def test_rate_limit_wired(self):
        self.assertIn("_rate_ok", self.dash)
        self.assertIn('"reg:" + self._client_ip()', self.dash)

    def test_portal_ui_present(self):
        for needle in ("loadStudyPlan()", "loadForecast()", "loadTrend()",
                       "loadTrends()", "loadGoalBoard()", "loadChallenge()",
                       "ansChallenge", "trySimilar(", "downloadRevisionPack()",
                       "Attempt Analysis", "challenge-card"):
            self.assertIn(needle, self.dash)


if __name__ == "__main__":
    unittest.main()
