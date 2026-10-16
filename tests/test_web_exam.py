# -*- coding: utf-8 -*-
"""🌐 Web Exam: link click → browser exam (no Telegram app needed).

Same engine as the bot path: dashboard creates event → student opens
/exam/<CODE> → joins with name+phone → answers in browser → marks/review.
Pins web_join/web_state/web_answer + shared scoring parity with bot polls.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import campus  # noqa: E402


class _KV:
    def save(self):
        pass


class FakeMembers:
    def __init__(self):
        self.d = {}
        self.members = self.d
        self.kv = _KV()

    def _get(self, uid):
        return self.d.setdefault(str(uid), {})


class FakeBank:
    def pick(self, *a, **kw):
        return []


class FakeTG:
    def __init__(self):
        self.polls = {}
        self.sent = []

    def send(self, chat, text):
        self.sent.append((chat, text))
        return {"message_id": 1}

    def send_message(self, chat, text):
        self.sent.append((chat, text))
        return {"message_id": 1}

    def send_quiz(self, chat, q, opts, correct, **kw):
        pid = f"qz{len(self.polls)}"
        self.polls[pid] = (chat, q)
        return {"result": {"message_id": 1, "poll": {"id": pid}}}

    def send_poll(self, chat, q, opts, **kw):
        pid = f"p{len(self.polls)}"
        self.polls[pid] = (chat, q)
        return {"message_id": 1, "poll": {"id": pid}}

    def stop_poll(self, chat, mid):
        pass


def _qs(n=3):
    return [{"id": f"wq{i}", "source": "curated", "subject": "polity",
             "topic": "constitution", "q_en": f"Question {i}?", "q_te": f"Te {i}?",
             "options_en": ["A", "B", "C", "D"], "options_te": ["A", "B", "C", "D"],
             "answer_index": 1, "explanation": ""} for i in range(n)]


class TestWebExam(unittest.TestCase):
    def setUp(self):
        self._old = campus.PATH
        self._tmp = tempfile.mkdtemp()
        campus.PATH = Path(self._tmp) / "campus.json"
        self.mem = FakeMembers()

    def tearDown(self):
        campus.PATH = self._old

    def _started(self):
        code = campus.new_event("Web College", "Guntur", ["Web College"],
                                n_q=3, level="easy", created_by="1", mode="college")
        tokA = tokB = None
        okA, infA = campus.web_join(self.mem, code, "Anitha", "9812345601", 1)
        okB, infB = campus.web_join(self.mem, code, "Ravi", "9812345602", 1)
        self.assertTrue(okA, infA)
        self.assertTrue(okB, infB)
        tokA, tokB = infA["token"], infB["token"]
        d = campus._load()
        d["events"][code]["questions"] = _qs(3)
        campus._save(d)
        tg = FakeTG()
        campus.start(FakeBank(), self.mem, tg, code)
        return code, tokA, tokB

    def _correct_display(self, code, uid):
        d = campus._load(); e = d["events"][code]
        qi = e["qi"]
        qidx = campus._order_for(e, uid)[qi]
        perm = campus._omap_for(e, uid, qidx)
        return perm.index(e["questions"][qidx]["answer_index"])

    def test_full_web_exam_flow(self):
        code, tokA, tokB = self._started()
        uidA = "w9812345601"
        st = campus.web_state(code, tokA)
        self.assertEqual(st["state"], "question")
        self.assertEqual(st["position"], 1)
        self.assertEqual(len(st["question"]["options"]), 4)
        self.assertFalse(st["question"]["answered"])
        idx = self._correct_display(code, uidA)
        ok, info = campus.web_answer(code, tokA, 1, idx)
        self.assertTrue(ok, info)
        st = campus.web_state(code, tokA)
        self.assertTrue(st["question"]["answered"])
        self.assertEqual(st["my"]["answered"], 1)
        # duplicate answer never double-counts
        campus.web_answer(code, tokA, 1, idx)
        st = campus.web_state(code, tokA)
        self.assertEqual(st["my"]["answered"], 1)
        # finish → result with rank + review
        ok, txt = campus.finish_now(FakeTG(), self.mem, code)
        self.assertTrue(ok, txt)
        done = campus.web_state(code, tokA)
        self.assertEqual(done["state"], "done")
        self.assertEqual(done["rank"], 1)          # Ravi answered 0
        self.assertEqual(len(done["review"]), 1)
        self.assertEqual(len(done["top"]), 1)   # only answered students rank
        # report works for web students too
        rep = campus.report_dict(code)
        names = [p["name"] for p in rep["players"]]
        self.assertIn("Anitha", names)

    def test_web_join_validation_and_resume(self):
        code = campus.new_event("Web College", "Guntur", ["Web College"],
                                n_q=3, level="easy", created_by="1", mode="college")
        ok, err = campus.web_join(self.mem, code, "Anitha", "123", 1)
        self.assertFalse(ok)                        # bad phone
        ok, err = campus.web_join(self.mem, code, "", "9812345601", 1)
        self.assertFalse(ok)                        # no name
        ok, inf = campus.web_join(self.mem, code, "Anitha", "9812345601", 1)
        self.assertTrue(ok, inf)
        self.assertEqual(inf["uid"], "w9812345601")
        st = campus.web_state(code, inf["token"])
        self.assertEqual(st["state"], "open")
        # same phone joins again → resume token, still ONE player
        ok2, inf2 = campus.web_join(self.mem, code, "Anitha", "9812345601", 1)
        self.assertTrue(ok2)
        d = campus._load()
        self.assertEqual(len(d["events"][code]["players"]), 1)

    def test_web_vs_bot_scoring_parity(self):
        # bot poll answer and web answer go through the SAME _apply_answer
        code, tokA, tokB = self._started()
        uidA, uidB = "w9812345601", "w9812345602"
        d = campus._load()
        e = d["events"][code]
        poll_id = None
        for pid, (c, qi, owner) in d["polls"].items():
            if owner == uidA:
                poll_id = pid
        self.assertIsNotNone(poll_id, list(d["polls"].items())[:1])
        # bot path: poll id + Anitha's own shuffled display index
        self.assertTrue(campus.record_answer(poll_id, uidA,
                                             self._correct_display(code, uidA)))
        # web path: B answers with B's own (different) shuffled display index
        ok, info = campus.web_answer(code, tokB, 1, self._correct_display(code, uidB))
        self.assertTrue(ok, info)
        self.assertTrue(info["correct"])
        d = campus._load()
        e = d["events"][code]
        self.assertEqual(e["players"][uidA]["correct"], 1)
        self.assertEqual(e["players"][uidB]["correct"], 1)
        self.assertEqual(e["players"][uidA]["pts"], e["players"][uidB]["pts"])

    def test_dashboard_web_exam_wiring(self):
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        self.assertIn('p.path.startswith("/exam/")', src)     # public page
        self.assertIn('"/api/exam/join"', src)
        self.assertIn('"/api/exam/answer"', src)
        self.assertIn('"/api/exam/state"', src)
        self.assertIn('"/api/exam/info"', src)
        self.assertIn("WEB_EXAM_HTML", src)
        self.assertIn("campus.web_join", src)
        self.assertIn("campus.web_answer", src)
        self.assertIn("PUBLIC_BASE_URL", src)
        self.assertIn("_public_base(self)", src)
        self.assertIn("d.web_qr || d.qr", src)
        self.assertIn("🌐 Copy Web Link", src)

    def test_qr_png_web_link(self):
        try:
            import qrcode  # noqa: F401
        except Exception:
            self.skipTest("qrcode not installed")
        code = campus.new_event("Web College", "Guntur", ["Web College"],
                                n_q=3, level="easy", created_by="1", mode="college")
        data = campus.qr_png(code, link="https://exam.example.com/exam/" + code)
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertIsNone(campus.qr_png("CE-NOPE", link="https://x/exam/CE-NOPE"))


if __name__ == "__main__":
    unittest.main()
