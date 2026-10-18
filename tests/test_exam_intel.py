# -*- coding: utf-8 -*-
"""🧠 Exam Intelligence 2.0: negative marking (real-exam scoring,
journal-replay consistent), question-wise 👥 analytics, personal
Score Card PNG andariki, countdown wiring.

Pins: wrong answer ki negative points correct ga apply avthayi mariyu
crash-recovery tarvatha kuda same score untundi; result lo prati
question entha mandi correct pettaro telusthundi; score card kevalam
exam finish chesina student ke vasthundi.
"""
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import portal  # noqa: E402
from tests.test_portal import FakeMembers, _reg  # noqa: E402

DASH = (Path(__file__).resolve().parent.parent
        / "scripts" / "dashboard_server.py")


def _drop_cache():
    portal._close_journal()
    portal._STORE.update({"path": None, "d": None, "dirty": False, "jfh": None})


def _cc(q, seed):
    _o, perm = portal._display(q, seed)
    return perm.index(q["answer_index"])


class TestExamIntel(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        _drop_cache()
        portal.PATH = self._old

    def _live_exam(self, neg=0.0, n_q=5):
        start = (portal._now() - timedelta(minutes=5)).isoformat()
        return portal.create_exam("Intel Test", "mixed", start,
                                  duration_min=120, n_q=n_q, neg=neg)

    def test_negative_marking_and_replay(self):
        tok, uid = _reg(self.mem), "w9812345601"
        e = self._live_exam(neg=0.5)
        portal._flush_store()                     # exam snapshot disk ki
        portal.exam_join(self.mem, tok, e["id"])
        d = portal._load()
        qs = d["exams"][e["id"]]["qs"]
        for i, q in enumerate(qs):
            cc = _cc(q, f"{e['id']}:{uid}:{i}")
            ch = cc if i < 3 else (cc + 1) % 4    # 3 correct, 2 wrong
            ok, _r = portal.exam_answer(self.mem, tok, e["id"], i, ch)
            self.assertTrue(ok)
        ent = portal._load()["exams"][e["id"]]["entries"][uid]
        self.assertEqual((ent["correct"], ent["wrong"]), (3, 2))
        self.assertEqual(ent["pts"], 20)          # 30 − 2×(10×0.5)
        _drop_cache()                             # 💥 crash → journal replay
        ent2 = portal._load()["exams"][e["id"]]["entries"][uid]
        self.assertEqual(ent2["pts"], 20)         # replay kuda same score
        self.assertEqual(ent2["wrong"], 2)

    def test_qstats_and_scorecard(self):
        t1 = _reg(self.mem)
        t2 = _reg(self.mem, name="Second", phone="9812345602")
        e = self._live_exam(n_q=4)
        portal.exam_join(self.mem, t1, e["id"])
        portal.exam_join(self.mem, t2, e["id"])
        d = portal._load()
        qs = d["exams"][e["id"]]["qs"]
        for tok, uid, good in ((t1, "w9812345601", True),
                               (t2, "w9812345602", False)):
            for i, q in enumerate(qs):
                cc = _cc(q, f"{e['id']}:{uid}:{i}")
                portal.exam_answer(self.mem, tok, e["id"], i,
                                   cc if good else (cc + 1) % 4)
        # done cheyyi
        d = portal._load()
        d["exams"][e["id"]]["starts_at"] = (
            portal._now() - timedelta(hours=3)).isoformat()
        d["exams"][e["id"]]["duration_min"] = 30
        portal._save(d, flush=True)
        view = portal.exam_result(self.mem, t1, e["id"])
        self.assertTrue(view["qstats"] and all(x == 50 for x in view["qstats"]))  # okkaru right
        png = portal.exam_scorecard(self.mem, t1, e["id"])
        self.assertIsNotNone(png)
        self.assertTrue(png.startswith(b"\x89PNG"))
        ok, key = portal.key_paper(self.mem, t1, "exam", e["id"])
        self.assertTrue(ok)
        t3 = _reg(self.mem, name="Third", phone="9812345603")
        self.assertIsNone(portal.exam_scorecard(self.mem, t3, e["id"]))

    def test_keypaper_negative_line(self):
        tok, uid = _reg(self.mem), "w9812345601"
        e = self._live_exam(neg=0.25, n_q=3)
        portal.exam_join(self.mem, tok, e["id"])
        d = portal._load()
        for i, q in enumerate(d["exams"][e["id"]]["qs"]):
            cc = _cc(q, f"{e['id']}:{uid}:{i}")
            portal.exam_answer(self.mem, tok, e["id"], i,
                               cc if i else (cc + 1) % 4)     # first wrong
        d = portal._load()
        d["exams"][e["id"]]["starts_at"] = (
            portal._now() - timedelta(hours=3)).isoformat()
        d["exams"][e["id"]]["duration_min"] = 30
        portal._save(d, flush=True)
        ok, key = portal.key_paper(self.mem, tok, "exam", e["id"])
        self.assertTrue(ok)
        self.assertIn("Negative marking", key["text"])

    def test_wiring(self):
        src = DASH.read_text(encoding="utf-8")
        for needle in ("pex-neg", "/api/portal/exam/scorecard", "qstats",
                       "cdTick", 'class="cd"'):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
