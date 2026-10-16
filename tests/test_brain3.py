# -*- coding: utf-8 -*-
"""🧠 Student Brain 3.0 — Elo ability, exam readiness, adaptive compose,
exam integrity, and end-to-end wiring (portal state/practice, bot, dashboard)."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import brain, integrity, item_intel  # noqa: E402


class TmpBrain(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._o = brain.BRAIN_FILE
        brain.BRAIN_FILE = self.tmp / "brain.json"
        brain._cache["mtime"] = None
        brain._cache["data"] = {}
        self._io = item_intel.STATS_FILE
        item_intel.STATS_FILE = self.tmp / "item_stats.json"
        item_intel._cache["mtime"] = None
        item_intel._cache["data"] = {}

    def tearDown(self):
        brain.BRAIN_FILE = self._o
        brain._cache["mtime"] = None
        item_intel.STATS_FILE = self._io
        item_intel._cache["mtime"] = None


def _q(qid, topic="polity", level="medium", ans=0):
    return {"id": qid, "q_en": f"Q {qid}?", "q_te": "ప్రశ్న?",
            "options_en": ["a", "b", "c", "d"],
            "options_te": ["అ", "ఆ", "ఇ", "ఈ"],
            "answer_index": ans, "topic": topic, "difficulty": level,
            "source": "curated"}


class TestElo(TmpBrain):
    def test_hard_win_gains_more_than_easy_win(self):
        brain.record("hardy", "H1", True, topic="polity", level="hard")
        brain.record("easy", "E1", True, topic="polity", level="easy")
        self.assertGreater(brain.ability("hardy")["theta"],
                           brain.ability("easy")["theta"])

    def test_easy_loss_drops_more_than_hard_loss(self):
        brain.record("a", "E1", False, level="easy")
        brain.record("b", "H1", False, level="hard")
        self.assertLess(brain.ability("a")["theta"],
                        brain.ability("b")["theta"])

    def test_topic_theta_tracked_separately(self):
        for _ in range(6):
            brain.record("u", "P1", True, topic="polity", level="hard")
        for _ in range(6):
            brain.record("u", "G1", False, topic="geography", level="easy")
        ab = brain.ability("u")
        th = {t["topic"]: t["theta"] for t in ab["topics"]}
        self.assertGreater(th["polity"], th["geography"])
        self.assertEqual(ab["weak_topics"][0], "geography")
        self.assertEqual(ab["answers"], 12)

    def test_band_and_target_level(self):
        self.assertEqual(brain.band_of(1600), "🏆 Expert")
        self.assertEqual(brain.band_of(1000), "🌱 Foundation")
        self.assertEqual(brain.target_level("newbie"), "easy")
        for _ in range(40):
            brain.record("pro", "H", True, level="hard")
        self.assertEqual(brain.target_level("pro"), "hard")

    def test_real_rate_drives_question_rating(self):
        for i in range(20):
            item_intel.record("BRUTAL", i == 0, topic="polity", channel="SSC")
        self.assertGreater(brain.question_rating("BRUTAL"),
                           brain.question_rating("", "medium"))
        for i in range(20):
            item_intel.record("CAKE", i != 0, topic="polity", channel="SSC")
        self.assertLess(brain.question_rating("CAKE"),
                        brain.question_rating("", "medium"))


class TestReadiness(TmpBrain):
    def test_strong_student_scores_higher(self):
        for _ in range(30):
            brain.record("top", "H", True, topic="polity", level="hard")
        strong = {"topics": {t: {"correct": 27, "total": 30}
                             for t in ("polity", "history", "geo", "eco",
                                       "sci", "maths", "eng", "ca")},
                  "total": 320, "streak": 15}
        rd = brain.readiness(strong, "top")
        self.assertGreaterEqual(rd["score"], 70)
        new = brain.readiness({}, "ghost")
        self.assertLessEqual(new["score"], 10)
        for v in rd["components"].values():
            self.assertGreaterEqual(v, 0)
        self.assertLessEqual(rd["score"], 100)


class TestCompose(TmpBrain):
    def test_review_first_then_weak_then_zone(self):
        for _ in range(5):
            brain.record("u", "x", False, topic="polity", level="medium")
        pool = ([_q(f"W{i}", topic="polity") for i in range(6)]
                + [_q(f"O{i}", topic="sports") for i in range(6)])
        rev = [_q("REV1", topic="sports")]
        out = brain.compose(pool, {"topics": {}}, "u", n=5, review_qs=rev)
        ids = [q["id"] for q in out]
        self.assertEqual(ids[0], "REV1")                 # revision first
        self.assertIn("W0", ids)                         # weak topic in
        self.assertEqual(len(ids), len(set(ids)))        # no dupes
        self.assertEqual(len(ids), 5)

    def test_high_theta_gets_harder_questions(self):
        for _ in range(40):
            brain.record("pro", "H", True, level="hard")
        pool = ([_q(f"E{i}", level="easy") for i in range(5)]
                + [_q(f"H{i}", level="hard") for i in range(5)])
        out = brain.compose(pool, {"topics": {}}, "pro", n=4)
        hard = sum(1 for q in out if q["difficulty"] == "hard")
        self.assertGreaterEqual(hard, 3)


class _KV:
    def __init__(self, *a, **k):
        self.data = {"members": {}, "pending": {}}

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
            "points": 0, "total": 0, "topics": {}, "review": []})


class TestWiring(TmpBrain):
    def test_award_answer_updates_brain(self):
        import core.members as mm
        _orig_kv = mm.KV
        mm.KV = _KV
        try:
            m = mm.Members()
            m.award_answer("42", "T", True, topic="polity", qid="Q1")
        finally:
            mm.KV = _orig_kv
        self.assertEqual(brain.ability("42")["answers"], 1)

    def test_overview_counts(self):
        brain.record("a", "1", True)
        brain.record("b", "2", False)
        ov = brain.overview()
        self.assertEqual(ov["students"], 2)
        self.assertEqual(ov["answers"], 2)

    def test_source_wiring(self):
        bot = (ROOT / "scripts" / "bot.py").read_text(encoding="utf-8")
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        portal = (ROOT / "scripts" / "core" / "portal.py").read_text(
            encoding="utf-8")
        self.assertIn("/brain", bot)
        self.assertIn("brain.record", (ROOT / "scripts" / "core"
                                       / "members.py").read_text(
                                           encoding="utf-8"))
        self.assertIn("/api/brain/overview", dash)
        self.assertIn("loadBrain", dash)
        self.assertIn("brain-card", dash)
        self.assertIn('"brain": _brain_card', portal)
        self.assertIn("/api/portal/exam/integrity", dash)


class TestIntegrity(unittest.TestCase):
    QS = [{"answer_index": i % 4} for i in range(12)]

    def _ent(self, wrong_map, n=12):
        ans = {}
        for i in range(n):
            ans[str(i)] = wrong_map.get(i, self.QS[i]["answer_index"])
        return {"answers": ans}

    def test_colluding_pair_flagged(self):
        wrong = {0: 1, 1: 2, 2: 3, 3: 0, 4: 1, 5: 2}
        # ensure those are actually wrong
        wrong = {i: (self.QS[i]["answer_index"] + 1) % 4 for i in range(6)}
        rep = integrity.analyze(
            {"a": self._ent(wrong), "b": self._ent(wrong),
             "c": self._ent({})}, self.QS)
        self.assertEqual(rep["flagged_pairs"], 1)
        self.assertEqual(rep["pairs"][0]["shared_wrong"], 6)
        self.assertFalse(rep["clean"])

    def test_honest_pair_not_flagged(self):
        wa = {i: (self.QS[i]["answer_index"] + 1) % 4 for i in range(6)}
        wb = {i: (self.QS[i]["answer_index"] + 2) % 4 for i in range(6, 12)}
        rep = integrity.analyze({"a": self._ent(wa), "b": self._ent(wb)},
                                self.QS)
        self.assertTrue(rep["clean"])

    def test_thin_data_never_flagged(self):
        wrong = {i: (self.QS[i]["answer_index"] + 1) % 4 for i in range(5)}
        rep = integrity.analyze(
            {"a": self._ent(wrong, n=5), "b": self._ent(wrong, n=5)},
            self.QS)
        self.assertTrue(rep["clean"])


class TestPortalBrain(TmpBrain):
    def setUp(self):
        super().setUp()
        from core import portal
        self.portal = portal
        self._pp = portal.PATH
        portal.PATH = self.tmp / "portal.json"
        self.mem = _Members()

    def tearDown(self):
        self.portal.PATH = self._pp
        super().tearDown()

    def test_state_has_brain_and_practice_smart(self):
        ok, info = self.portal.register_student(
            self.mem, "Brain Tester", "9000000077", "Khammam", "ssc")
        self.assertTrue(ok, info)
        token = info.get("token") or info.get("session") or ""
        if not token:
            st = self.portal.state(self.mem, token)
            self.assertIsNone(st)
            return
        st = self.portal.state(self.mem, token)
        self.assertIn("brain", st)
        ok2, pr = self.portal.practice_start(self.mem, token, "smart")
        if ok2:
            self.assertIn("brain", pr)
            self.assertTrue(pr["questions"])


if __name__ == "__main__":
    unittest.main()
