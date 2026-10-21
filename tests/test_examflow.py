# -*- coding: utf-8 -*-
"""🎓 Exam Flow 2.0: exam-first registration, goal switch, exam-wise PYQ
stock, Answer Key Paper (download eppudaina — stored attempt nunchi),
history, and many-students-at-once concurrency safety.

Pins: key paper lo prathi question ki mee right/wrong + correct answer +
explanation untundi; exam done ayye varaku key raadu; goal marchukovachu;
chala mandi threads okesari answer chesthe okka answer kuda podu.
"""
import sys
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import portal  # noqa: E402
from tests.test_portal import FakeMembers, _reg  # noqa: E402

DASH = (Path(__file__).resolve().parent.parent
        / "scripts" / "dashboard_server.py")


def _cc(q, seed):
    _opts, perm = portal._display(q, seed)
    return perm.index(q["answer_index"])


class TestExamFlow(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        portal.PATH = self._old

    def test_goal_switch_and_stock(self):
        tok = _reg(self.mem)
        ok, prof = portal.set_goal(self.mem, tok, "ssc")
        self.assertTrue(ok)
        self.assertEqual(prof["goal"], "ssc")
        bad, _e = portal.set_goal(self.mem, tok, "nope")
        self.assertFalse(bad)
        st = portal.exam_stock()
        self.assertIn("ssc", st)
        self.assertLessEqual(st["banking"]["pyq"], st["banking"]["total"])
        sta = portal.state(self.mem, tok)
        self.assertIn("stock", sta)
        self.assertIn("history", sta)

    def test_daily_and_mock_key_papers(self):
        tok, uid = _reg(self.mem), "w9812345601"
        d = portal._load()
        day = portal._daily_paper(d)
        for i, q in enumerate(day["qs"]):
            cc = _cc(q, f"{uid}:{portal._today()}:{i}")
            ch = cc if i else (cc + 1) % 4          # first one wrong
            ok, _r = portal.daily_answer(self.mem, tok, i, ch)
            self.assertTrue(ok)
        ok, key = portal.key_paper(self.mem, tok, "daily", portal._today())
        self.assertTrue(ok)
        self.assertIn("Answer Key Paper", key["text"])
        self.assertIn("❌ Meeru:", key["text"])      # the wrong one
        self.assertIn("✅ Meeru:", key["text"])      # and correct ones
        if any(q.get("explanation") for q in day["qs"]):
            self.assertIn("💡", key["text"])
        hist = portal.state(self.mem, tok)["history"]
        self.assertTrue(any(h["kind"] == "daily" and h["key"] for h in hist))
        # mock key
        ok, m = portal.mock_start(self.mem, tok, "ssc")
        self.assertTrue(ok)
        run = portal._load()["mocks"][m["run_id"]]
        ans = {str(i): _cc(q, f"{m['run_id']}:{i}")
               for i, q in enumerate(run["qs"])}
        ok, _res = portal.mock_submit(self.mem, tok, m["run_id"], ans)
        self.assertTrue(ok)
        ok, key2 = portal.key_paper(self.mem, tok, "mock", m["run_id"])
        self.assertTrue(ok)
        self.assertEqual(key2["correct"], key2["total"])
        hist = portal.state(self.mem, tok)["history"]
        self.assertTrue(any(h["kind"] == "mock" and h["key"] for h in hist))

    def test_exam_key_gated_until_done(self):
        tok, uid = _reg(self.mem), "w9812345601"
        start = (portal._now() - timedelta(minutes=5)).isoformat()
        e = portal.create_exam("Gate Test", "mixed", start,
                               duration_min=90, n_q=5)
        ok, _j = portal.exam_join(self.mem, tok, e["id"])
        self.assertTrue(ok)
        d = portal._load()
        exam = d["exams"][e["id"]]
        for i, q in enumerate(exam["qs"]):
            ok, _r = portal.exam_answer(
                self.mem, tok, e["id"], i, _cc(q, f"{e['id']}:{uid}:{i}"))
            self.assertTrue(ok)
        # live ga unnapudu key raakudadu
        ok, _why = portal.key_paper(self.mem, tok, "exam", e["id"])
        self.assertFalse(ok)
        # exam done cheyyi (time venakki vellinattu store update)
        d = portal._load()
        d["exams"][e["id"]]["starts_at"] = (
            portal._now() - timedelta(hours=3)).isoformat()
        d["exams"][e["id"]]["duration_min"] = 30
        portal._save(d)
        ok, key = portal.key_paper(self.mem, tok, "exam", e["id"])
        self.assertTrue(ok)
        self.assertEqual(key["correct"], 5)
        self.assertIn("Gate Test", key["text"])
        # vere student ki ee key raakudadu
        tok2 = _reg(self.mem, name="Second", phone="9812345602")
        ok2, _w = portal.key_paper(self.mem, tok2, "exam", e["id"])
        self.assertFalse(ok2)

    def test_many_students_at_once(self):
        start = (portal._now() - timedelta(minutes=5)).isoformat()
        e = portal.create_exam("Crowd Test", "mixed", start,
                               duration_min=120, n_q=5)
        students = []
        for n in range(24):
            phone = f"98300000{n:02d}"
            inf = {"token": _reg(self.mem, name=f"S{n}", phone=phone),
                   "uid": "w" + phone}
            students.append(inf)
            portal.exam_join(self.mem, inf["token"], e["id"])
        errors = []

        def answer_all(inf):
            try:
                d = portal._load()
                exam = d["exams"][e["id"]]
                for i, q in enumerate(exam["qs"]):
                    cc = _cc(q, f"{e['id']}:{inf['uid']}:{i}")
                    ok, _r = portal.exam_answer(
                        self.mem, inf["token"], e["id"], i, cc)
                    assert ok
            except Exception as ex:  # noqa: BLE001
                errors.append(ex)

        threads = [threading.Thread(target=answer_all, args=(s,))
                   for s in students]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        d = portal._load()
        entries = d["exams"][e["id"]]["entries"]
        self.assertEqual(len(entries), 24)
        for ent in entries.values():
            self.assertEqual(len(ent["answers"]), 5)
            self.assertEqual(ent["correct"], 5)

    def test_frontend_and_pyq_coverage(self):
        src = DASH.read_text(encoding="utf-8")
        # 450X: PORTAL_HTML raw string ayindi (r""" — JS \' escapes
        # Python vadhili pettadaniki); extraction kuda adi telusukovali.
        html = src.split('PORTAL_HTML = r"""', 1)[1].split('"""', 1)[0]
        self.assertLess(html.index('id="r-goal"'), html.index('id="r-name"'),
                        "Registration lo exam select FIRST ravali")
        for needle in ("sec-exams", "sec-quiz", "scrollDoor", "goal-chips",
                       "history-list", "downloadKey", "/api/portal/key",
                       "/api/portal/goal", "Answer Key Paper Download"):
            self.assertIn(needle, src)
        from core import pyq
        cov = pyq.by_channel()
        self.assertTrue(cov)
        for v in cov.values():
            self.assertLessEqual(v["pyq"], v["total"])


if __name__ == "__main__":
    unittest.main()
