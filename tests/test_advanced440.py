# -*- coding: utf-8 -*-
"""440X — Bot Board Subject Tests: /boards → channel → subject → test.

Pins:
  * catalog/readiness honestly count the 8 TS/AP board channels
    and their grouped subjects from the real academic stock;
  * the bot flow is strict (own channel + own subject only,
    unknown channel/subject errors honestly, no mixed fallback);
  * served questions are poll_safe snapshots — displayed options
    are a permutation whose stored answer_index still points at
    the original correct answer;
  * scoring happens exactly once per question (repeat/stale taps
    and other users' taps never double-award);
  * every callback stays within Telegram's 64-byte limit;
  * bot + dashboard wiring: /boards command, bb: callbacks, and
    the "Board Bot Tests (440X)" go-live row (16 checks total).
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import boardbot, config  # noqa: E402

BOT = (ROOT / "scripts" / "bot.py").read_text(encoding="utf-8")
DASH = (ROOT / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")


def _q(n, chan, topic, ans=1):
    opts = [f"opt{n}A", f"opt{n}B", f"opt{n}C", f"opt{n}D"]
    return {"id": f"T-{chan}-{n}", "channel": chan, "topic": topic,
            "q_en": f"Question {n}?", "q_te": f"ప్రశ్న {n}?",
            "options_en": opts, "options_te": list(opts),
            "answer_index": ans,
            "explanation_en": f"why {n}", "explanation_te": f"why {n}",
            "source": "curated", "bank": "academic"}


def _items():
    return [
        _q(1, "TS_INTER", "Physics — Motion", ans=0),
        _q(2, "TS_INTER", "Physics — Heat", ans=2),
        _q(3, "TS_INTER", "Chemistry — Atoms", ans=1),
        _q(4, "AP_10TH", "AP Mathematics — Real Numbers", ans=3),
        _q(5, "TS_10TH", "Mathematics — Polynomials", ans=1),
    ]


class _Members:
    def __init__(self):
        self.calls = []
        self.registered = True
        self.reg_calls = []

    def is_registered(self, uid):
        return self.registered

    def pending_step(self, uid):
        return None

    def start_registration(self, uid, username=""):
        self.reg_calls.append((uid, username))

    def award_answer(self, uid, username="", correct=True, topic="", qid=""):
        self.calls.append({"uid": uid, "correct": correct,
                           "topic": topic, "qid": qid})
        return {"earned": 10 if correct else 0, "points": 100,
                "locked": 0, "level_up": None, "new_badges": [],
                "streak": 1}


class _FakeTg:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, buttons=None, **kw):
        self.sent.append((str(chat_id), text, buttons, kw))
        return {"ok": True, "result": {"message_id": 1}}

    def answer_callback(self, *a, **kw):
        return {"ok": True}


class TestCatalogReadiness(unittest.TestCase):
    def test_real_stock_honest(self):
        rows = {r["channel"]: r for r in boardbot.catalog()}
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows["TS_INTER"]["total"], 8)
        self.assertEqual(rows["AP_INTER"]["total"], 8)
        self.assertEqual(rows["TS_10TH"]["total"], 6)
        names = {s["subject"] for s in rows["TS_INTER"]["subjects"]}
        self.assertIn("Physics", names)
        r = boardbot.readiness()
        self.assertTrue(r["ready"])
        self.assertEqual(r["boards"], 8)
        self.assertEqual(r["empty"], [])
        self.assertGreaterEqual(r["subjects"], 40)

    def test_menu_callbacks_within_limit(self):
        for _label, cb in [b for row in boardbot.menu_buttons()
                           for b in row]:
            self.assertTrue(cb.startswith("bb:"))
            self.assertLessEqual(len(cb.encode("utf-8")), 64)


class TestBotFlow(unittest.TestCase):
    def setUp(self):
        self._old = config.DATA
        config.DATA = Path(tempfile.mkdtemp())
        self.items = _items()
        self.m = _Members()
        self.uid = 4242

    def tearDown(self):
        config.DATA = self._old

    def _start_physics(self):
        ev = boardbot.dispatch(self.m, self.uid, "subj:2:0",
                               items=self.items)
        self.assertEqual(len(ev), 2)               # intro + Q1
        _txt, buttons = ev[1]
        cbs = [cb for row in buttons for _l, cb in row]
        run_id = cbs[0].split(":")[2]
        return run_id, buttons

    def test_subject_run_strict_stock_and_full_flow(self):
        run_id, _b = self._start_physics()
        run = boardbot.get_run(run_id)
        self.assertIsNotNone(run)
        self.assertEqual(len(run["qs"]), 2)        # only 2 Physics Qs
        for q in run["qs"]:
            self.assertEqual(q["channel"], "TS_INTER")
            self.assertTrue(q["topic"].startswith("Physics"))
            # poll_safe snapshot: displayed order is a permutation,
            # stored answer still points at the ORIGINAL correct text.
            orig = next(i for i in self.items if i["id"] == q["id"])
            self.assertEqual(sorted(q["options_en"]),
                             sorted(orig["options_en"]))
            self.assertEqual(q["options_en"][q["answer_index"]],
                             orig["options_en"][orig["answer_index"]])
        # answer every question correctly via the real callbacks
        for qi in range(2):
            run = boardbot.get_run(run_id)
            choice = run["qs"][qi]["answer_index"]
            ev = boardbot.dispatch(
                self.m, self.uid, f"ans:{run_id}:{qi}:{choice}",
                items=self.items)
            self.assertIn("✅ Correct!", ev[0][0])
        self.assertEqual(len(self.m.calls), 2)
        self.assertTrue(all(c["correct"] for c in self.m.calls))
        run = boardbot.get_run(run_id)
        self.assertTrue(run["done"])
        self.assertEqual(run["correct"], 2)
        last = ev[0][0]
        self.assertIn("🏁 Test complete!", last)
        self.assertIsNotNone(ev[0][1])             # completion buttons

    def test_full_board_and_wrong_answer_feedback(self):
        ok, run = boardbot.start_run(self.uid, "TS_INTER",
                                     items=self.items, seed="s1")
        self.assertTrue(ok, run)
        self.assertEqual(len(run["qs"]), 3)        # whole channel stock
        q0 = run["qs"][0]
        wrong = (q0["answer_index"] + 1) % 4
        ok, res = boardbot.answer_run(self.m, self.uid, run["run_id"],
                                      0, wrong)
        self.assertTrue(ok)
        self.assertFalse(res["correct"])
        txt = boardbot.feedback_text(run, res)
        self.assertIn("Correct answer:", txt)
        self.assertEqual(len(self.m.calls), 1)
        self.assertFalse(self.m.calls[0]["correct"])

    def test_repeat_stale_and_foreign_taps_never_double_award(self):
        run_id, _b = self._start_physics()
        run = boardbot.get_run(run_id)
        choice = run["qs"][0]["answer_index"]
        boardbot.dispatch(self.m, self.uid, f"ans:{run_id}:0:{choice}",
                          items=self.items)
        self.assertEqual(len(self.m.calls), 1)
        ev = boardbot.dispatch(self.m, self.uid, f"ans:{run_id}:0:{choice}",
                               items=self.items)
        self.assertIn("already answer", ev[0][0])
        self.assertEqual(len(self.m.calls), 1)     # no double award
        ok, err = boardbot.answer_run(self.m, 9999, run_id, 1, 0)
        self.assertFalse(ok)                       # someone else's run
        self.assertEqual(len(self.m.calls), 1)
        ok, err = boardbot.answer_run(self.m, self.uid, run_id, 7, 0)
        self.assertFalse(ok)                       # stale/future question

    def test_strict_failures_honest(self):
        ok, err = boardbot.start_run(self.uid, "SSC", items=self.items)
        self.assertFalse(ok)
        ok, err = boardbot.start_run(self.uid, "TS_INTER",
                                     subject="Astronomy", items=self.items)
        self.assertFalse(ok)
        self.assertIn("levu", err)
        ev = boardbot.dispatch(self.m, self.uid, "subj:2:99",
                               items=self.items)
        self.assertIn("⚠️", ev[0][0])
        ev = boardbot.dispatch(self.m, self.uid, "hack", items=self.items)
        self.assertIn("⚠️", ev[0][0])

    def test_quit_and_callback_sizes(self):
        run_id, buttons = self._start_physics()
        for _l, cb in [b for row in buttons for b in row]:
            self.assertLessEqual(len(cb.encode("utf-8")), 64)
        ev = boardbot.dispatch(self.m, self.uid, f"quit:{run_id}",
                               items=self.items)
        self.assertIn("⏹ Test stopped", ev[0][0])
        run = boardbot.get_run(run_id)
        self.assertTrue(run["done"] and run["abandoned"])


class TestBotIntegration(unittest.TestCase):
    """Real Bot routing: /boards message -> bb: taps -> scored answer."""

    def setUp(self):
        self._old = config.DATA
        self.tmp = Path(tempfile.mkdtemp())
        config.DATA = self.tmp
        # boardbot store lives under config.DATA; the academic stock
        # file must travel with the patch or the bot sees zero stock.
        (self.tmp / "academic_bank.md").write_bytes(
            (self._old / "academic_bank.md").read_bytes())
        self.m = _Members()
        from bot import Bot
        self.bot = Bot.__new__(Bot)
        self.bot.members = self.m
        self.bot.tg = _FakeTg()
        self.bot.bank = None
        self.bot._poll_q = {}
        self.user = {"id": 4242, "first_name": "Test",
                     "username": "testuser"}

    def tearDown(self):
        config.DATA = self._old

    def _tap(self, data):
        self.bot.handle_callback(
            {"from": dict(self.user), "id": "cb1", "data": data,
             "message": {"chat": {"id": 4242}, "message_id": 1}})

    def _all_buttons(self):
        return [b for _c, _t, btns, _k in self.bot.tg.sent if btns
                for row in btns for b in row]

    def test_boards_command_to_scored_answer(self):
        self.bot.handle_message({"chat": {"id": 4242},
                                 "from": dict(self.user),
                                 "text": "/boards"})
        menu = [s for s in self.bot.tg.sent if "Board Tests" in s[1]]
        self.assertEqual(len(menu), 1)
        chan_cb = next(cb for lab, cb in self._all_buttons()
                       if "Telangana Inter" in lab)
        self._tap(chan_cb)
        subj_cb = next(cb for _lab, cb in self._all_buttons()
                       if cb.startswith("bb:subj:2:"))
        self._tap(subj_cb)
        run_id = next(cb.split(":")[2] for _lab, cb in self._all_buttons()
                      if cb.startswith("bb:ans:"))
        run = boardbot.get_run(run_id)
        self.assertIsNotNone(run)
        choice = run["qs"][0]["answer_index"]
        self._tap(f"bb:ans:{run_id}:0:{choice}")
        self.assertTrue(any("✅ Correct!" in s[1]
                            for s in self.bot.tg.sent))
        self.assertEqual(len(self.m.calls), 1)
        self.assertTrue(self.m.calls[0]["correct"])

    def test_unregistered_boards_starts_registration(self):
        self.m.registered = False
        self.bot.handle_message({"chat": {"id": 4242},
                                 "from": dict(self.user),
                                 "text": "/boards"})
        self.assertEqual(len(self.m.reg_calls), 1)
        self.assertFalse(any("Board Tests" in s[1]
                             for s in self.bot.tg.sent))


class TestWiring440(unittest.TestCase):
    def test_bot_and_golive_wiring(self):
        self.assertIn('low.startswith("/boards")', BOT)
        self.assertIn('kind == "bb"', BOT)
        self.assertIn('"Board Bot Tests (440X)"', DASH)
        self.assertIn("/boards", DASH)

    def test_golive_row(self):
        import dashboard_server as dash
        r = dash._golive_checks()
        self.assertEqual(len(r["checks"]), 16)
        row = next(c for c in r["checks"]
                   if c["name"] == "Board Bot Tests (440X)")
        self.assertEqual(row["status"], "ok")
        self.assertIn("8 board channels", row["detail"])
        self.assertIn("/boards", row["detail"])


if __name__ == "__main__":
    unittest.main()
