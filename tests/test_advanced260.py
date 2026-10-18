# -*- coding: utf-8 -*-
"""🚀 260X: archive-times invariant + syllabus memo + bot held metrics
+ Stateless Client core (signed zero-storage state).

Pins:
  • mock_submit sections == attempt_analysis sections EVEN after the
    attempt is archived and the run pruned — archive rows now persist
    per-question seconds; timed and untimed attempts both reconcile.
  • syllabus.exam_graph memoized per bank signature: same Bank ->
    identical cached graph object; bank growth -> recount.
  • Bot held-metrics snapshot: updates/errors/error-rate/uptime read
    from the bounded in-memory _upd_stats (no probing, no I/O pins).
  • Stateless Client: HMAC-signed state token registers, validates,
    grades answers, composes a deterministic daily set, runs an
    attempt with sections, and rejects tampered/expired/wrong-type
    tokens — with zero portal-store writes.
  • dashboard wiring pins: golive flags cert-engine deps + stateless
    round-trip.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, brain  # noqa: E402
from core import syllabus, question_bank  # noqa: E402
from core import stateless_client as sc  # noqa: E402

SECRET = "adv260-test-secret"


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
            "name": "Adv260 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": [], "registered": True})

    def award_answer(self, uid, username="", correct=True, topic="", qid=""):
        return {"points": 0}


class _FakeBank:
    def __init__(self, qs):
        self.questions = list(qs)

    def by_channel(self, ch):
        return [q for q in self.questions if q.get("channel") == ch]


def _members_with_tokens(tmp):
    portal.PATH = Path(tmp) / "portal.json"
    brain.BRAIN_FILE = Path(tmp) / "brain.json"
    mem = _Members()
    ok, info = portal.register_student(
        mem, "Adv260 Tester", "9822600260", "Guntur", "railway")
    assert ok, info
    return mem, info["token"]


def _sit_mock(mem, tok, correct_pick=None):
    ok, st = portal.mock_start(mem, tok, "railway")
    assert ok, st
    run = portal._load()["mocks"][st["run_id"]]
    answers = {}
    for i, q in enumerate(run["qs"]):
        _o, perm = portal._display(q, f"{st['run_id']}:{i}")
        answers[str(i)] = perm.index(
            q["answer_index"] if correct_pick is None
            else (q["answer_index"] + 1) % 4)
    return st["run_id"], answers


class Advanced260Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.mem, cls.tok = _members_with_tokens(cls.tmp)

    # ------------------------------------------------ 1) archive invariant
    def test_archive_times_keep_sections_identical(self):
        run_id, answers = _sit_mock(self.mem, self.tok)
        # timed: first two questions slow (300s), rest quick
        ok, res = portal.mock_submit(
            self.mem, self.tok, run_id, answers,
            times={str(i): (300 if i < 2 else 30)
                   for i in range(len(answers))})
        self.assertTrue(ok)
        an = portal.attempt_analysis(self.mem, self.tok, run_id)
        self.assertIsNotNone(an)
        # THE invariant: submit == analysis, with timing preserved
        self.assertEqual(res["sections"], an["sections"])
        timed = [s for s in res["sections"] if "seconds" in s]
        self.assertTrue(timed, res["sections"])

    def test_untimed_attempt_also_reconciles(self):
        run_id, answers = _sit_mock(self.mem, self.tok)
        ok, res = portal.mock_submit(self.mem, self.tok, run_id, answers)
        self.assertTrue(ok)
        an = portal.attempt_analysis(self.mem, self.tok, run_id)
        self.assertIsNotNone(an)
        self.assertEqual(res["sections"], an["sections"])
        for s in res["sections"]:
            self.assertNotIn("seconds", s)

    # ------------------------------------------------ 2) syllabus memoization
    def test_syllabus_graph_memoized_and_recounts(self):
        fb = _FakeBank([{"channel": "BANKING", "topic": "algebra"},
                        {"channel": "BANKING", "topic": "algebra"}])
        g1 = syllabus.exam_graph(fb, "BANKING")
        g2 = syllabus.exam_graph(fb, "BANKING")
        self.assertIs(g1, g2)                      # cache hit: same object
        self.assertEqual(g1["subjects"]["quant"]["algebra"], 2)
        fb.questions.append({"channel": "BANKING", "topic": "algebra"})
        g3 = syllabus.exam_graph(fb, "BANKING")    # bank grew -> recount
        self.assertIsNot(g3, g1)
        self.assertEqual(g3["subjects"]["quant"]["algebra"], 3)

    def test_syllabus_graph_real_bank(self):
        rb = question_bank.Bank()
        g = syllabus.exam_graph(rb, "SSC")
        self.assertEqual(g["channel"], "SSC")
        self.assertTrue(g["subjects"])

    # ------------------------------------------------ 3) bot held metrics
    def test_bot_held_metrics_snapshot(self):
        import time as _time
        from bot import Bot
        b = Bot.__new__(Bot)
        b._t0 = _time.time() - 3661
        b._upd_stats = {"total": 4, "errors": 1, "by_kind": {"message": 4},
                        "last_error": "message: boom",
                        "last_error_ts": _time.time() - 30}
        m = b._held_metrics260()
        self.assertEqual(m["updates"], 4)
        self.assertEqual(m["errors"], 1)
        self.assertAlmostEqual(m["error_rate"], 0.25)
        self.assertTrue(3600 < m["started_ago_sec"] < 3700)
        self.assertTrue(20 < m["last_error_age_sec"] < 40)
        b._upd_stats = {}
        m0 = b._held_metrics260()
        self.assertEqual(m0["error_rate"], 0.0)
        self.assertIsNone(m0["last_error_age_sec"])

    def test_bot_health_renders_held_metrics(self):
        bot_src = (ROOT / "scripts" / "bot.py").read_text(encoding="utf-8")
        self.assertIn("def _held_metrics260", bot_src)
        self.assertIn("self._held_metrics260()", bot_src)
        self.assertIn("stats[\"last_error_ts\"]", bot_src)

    # ------------------------------------------------ 4) stateless client
    def test_stateless_register_view_and_tamper(self):
        tok, err = sc.register_student("Ananya Rao", "9849112601",
                                       "Guntur", "railway", secret=SECRET)
        self.assertIsNone(err)
        v = sc.public_view(tok, secret=SECRET)
        self.assertEqual(v["profile"]["uid"], "w9849112601")
        self.assertEqual(v["points"], 0)
        pre, pb, sig = tok.split(".")
        bad = pre + "." + ("A" if pb[0] != "A" else "B") + pb[1:] + "." + sig
        self.assertIsNone(sc.public_view(bad, secret=SECRET))
        self.assertIsNone(sc.public_view(tok, secret="other-secret"))
        tok2, err2 = sc.register_student("A", "123", "Guntur", "railway",
                                         secret=SECRET)
        self.assertIsNone(tok2)
        self.assertTrue(err2)

    def test_stateless_answer_grading_updates_state(self):
        tok, _ = sc.register_student("Ananya Rao", "9849112602",
                                     "Guntur", "railway", secret=SECRET)
        dq = sc.daily_quiz(tok, secret=SECRET)
        self.assertEqual(dq, sc.daily_quiz(tok, secret=SECRET))  # deterministic
        self.assertTrue(dq["questions"])
        self.assertNotIn("answer_index", str(dq["questions"][0]))
        bank = {str(q["id"]): q for q in question_bank.load_bank()}
        q0 = dq["questions"][0]
        nt, res = sc.record_answer(tok, q0["id"],
                                   bank[str(q0["id"])]["answer_index"],
                                   secret=SECRET)
        self.assertTrue(res["correct"])
        self.assertEqual(res["points"], 10)
        wrong = (bank[str(q0["id"])]["answer_index"] + 1) % 4
        _nt2, res2 = sc.record_answer(nt, q0["id"], wrong, secret=SECRET)
        self.assertFalse(res2["correct"])
        self.assertEqual(res2["accuracy"], 50)
        v = sc.public_view(nt, secret=SECRET)
        self.assertEqual(v["topics_seen"], 1)

    def test_stateless_attempt_sections_and_typ_guard(self):
        tok, _ = sc.register_student("Ananya Rao", "9849112603",
                                     "Guntur", "railway", secret=SECRET)
        at, err = sc.start_attempt(tok, secret=SECRET)
        self.assertIsNone(err)
        self.assertIsNone(sc.public_view(at, secret=SECRET))  # typ!="u"
        bank = {str(q["id"]): q for q in question_bank.load_bank()}
        qids = sc.decode_token(at, secret=SECRET)["qids"]
        answers = {str(q): bank[str(q)]["answer_index"] for q in qids[:5]}
        nt, sub = sc.submit_attempt(tok, at, answers, secret=SECRET)
        self.assertTrue(sub["ok"])
        self.assertEqual(sub["correct"], 5)
        self.assertGreater(sub["points"], 0)
        self.assertTrue(sub["sections"])
        for row in sub["sections"]:
            self.assertIn("accuracy", row)

    def test_stateless_expired_token_refused(self):
        old = sc.encode_token({"typ": "u", "uid": "w1"},
                              secret=SECRET, ttl=-5)
        self.assertIsNone(sc.public_view(old, secret=SECRET))

    # ------------------------------------------------ 5) dashboard wiring pins
    def test_dashboard_golive_checks_wired(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        self.assertIn('"Certificate engine (PIL + QR)"', src)
        self.assertIn('"Stateless client (260X)"', src)
        self.assertIn("stateless_client", src)


if __name__ == "__main__":
    unittest.main()
