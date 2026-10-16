# -*- coding: utf-8 -*-
"""College Exam PRO: anti-copy shuffle, live control room, scheduled
auto-start, question/topic analytics, inter-college league."""
import shutil
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core import config
from core import campus as C
from core.content import build_options
from core.question_bank import Bank


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV(); self.members = {}

    def _get(self, uid):
        return self.members.setdefault(str(uid), {})


class _TG:
    dry = True

    def __init__(self):
        self.msgs = []; self.pid = 0; self.quizzes = {}

    def send_message(self, chat, text, **kw):
        self.msgs.append((str(chat), text))

    def send_quiz(self, chat_id, question, options, correct_index, **kw):
        self.pid += 1
        pid = f"c{self.pid}"
        self.quizzes[pid] = (str(chat_id), list(options), correct_index)
        return {"result": {"poll": {"id": pid}}}


class TestCampusPro(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._o = C.PATH; C.PATH = self.tmp / "c.json"
        self._used = config.STORE_USED; config.STORE_USED = self.tmp / "used.json"
        self._sig = config.DATA / "shown_signatures.json"
        self._sig_bak = self._sig.read_bytes() if self._sig.exists() else None

    def tearDown(self):
        C.PATH = self._o; config.STORE_USED = self._used
        if self._sig_bak is not None:
            self._sig.write_bytes(self._sig_bak)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _started(self, n_students=3):
        m, tg = _Members(), _TG()
        code = C.new_event("Pro Fest", "Guntur", ["Alpha College"], 8, "easy",
                           created_by="admin")
        for i in range(1, n_students + 1):
            ok, _, _ = C.join(m, str(i), code, 1, name_hint=f"S{i}")
            assert ok
            m.members[str(i)].update({"registered": True, "name": f"S{i}"})
            C.on_registered(m, str(i))
        ok, info = C.start(Bank(), m, tg, code)
        assert ok, info
        return m, tg, code

    def _pid(self, d, code, uid, qi=0):
        for pid, (c, qpos, owner) in d["polls"].items():
            if c == code and owner == str(uid) and qpos == qi:
                return pid

    def test_shuffle_anti_copy(self):
        m, tg, code = self._started(3)
        d = C._load(); e = d["events"][code]
        self.assertTrue(e["shuffle"])
        orders = [tuple(e["qorder"][str(i)]) for i in (1, 2, 3)]
        self.assertFalse(orders[0] == orders[1] == orders[2],
                         "students must not all share one question order")
        for uid in ("1", "2", "3"):
            pid = self._pid(d, code, uid)
            chat, opts, correct_display = tg.quizzes[pid]
            q = e["questions"][e["qorder"][uid][0]]
            expected_correct_text = build_options(q, telugu_first=True)[q["answer_index"]]
            self.assertEqual(opts[correct_display], expected_correct_text,
                             "displayed correct option must map to the real answer")
            ok = C.record_answer(pid, uid, correct_display)
            self.assertTrue(ok)
        d = C._load(); e = d["events"][code]
        for uid in ("1", "2", "3"):
            self.assertEqual(e["players"][uid]["correct"], 1)
        # a displayed WRONG option must score 0 even though positions differ
        m2, tg2, code2 = self._started(2)
        d2 = C._load(); e2 = d2["events"][code2]
        pid = self._pid(d2, code2, "1")
        _, opts, correct_display = tg2.quizzes[pid]
        wrong_display = (correct_display + 1) % len(opts)
        C.record_answer(pid, "1", wrong_display)
        d2 = C._load()
        self.assertEqual(d2["events"][code2]["players"]["1"]["correct"], 0)

    def test_live_control_room(self):
        m, tg, code = self._started(3)
        snap = C.live_snapshot(code)
        self.assertEqual(snap["state"], "question")
        self.assertEqual((snap["qi"], snap["joined"], snap["answered_now"]), (1, 3, 0))
        self.assertTrue(snap["shuffle"])
        d = C._load()
        C.record_answer(self._pid(d, code, "1"), "1", tg.quizzes[self._pid(d, code, "1")][2])
        snap = C.live_snapshot(code)
        self.assertEqual(snap["answered_now"], 1)
        self.assertEqual(snap["players"][0]["name"], "S1")
        ok, msg = C.advance_now(tg, m, code)
        self.assertTrue(ok, msg)
        snap = C.live_snapshot(code)
        self.assertEqual(snap["qi"], 2)
        ok, msg = C.finish_now(tg, m, code)
        self.assertTrue(ok, msg)
        d = C._load(); e = d["events"][code]
        self.assertEqual(e["state"], "done")
        self.assertEqual(e["players"]["1"]["rank"], 1)
        self.assertEqual(C.live_snapshot(code)["state"], "done")
        self.assertFalse(C.finish_now(tg, m, code)[0])
        self.assertIsNone(C.live_snapshot("CE-NOPE"))

    def test_scheduled_autostart(self):
        m, tg = _Members(), _TG()
        past = (C._now() - timedelta(minutes=1)).isoformat()
        code = C.new_event("Timed Fest", "Guntur", ["Alpha College"], 8, "easy",
                           created_by="admin", start_at=past)
        for i in (1, 2):
            C.join(m, str(i), code, 1, name_hint=f"S{i}")
            m.members[str(i)].update({"registered": True, "name": f"S{i}"})
            C.on_registered(m, str(i))
        C.tick(tg, m, C._now())
        d = C._load()
        self.assertIn(d["events"][code]["state"], ("question", "gap"))
        future = (C._now() + timedelta(hours=2)).isoformat()
        code2 = C.new_event("Later Fest", "Guntur", ["Alpha College"], 8, "easy",
                            created_by="admin", start_at=future)
        C.tick(tg, m, C._now())
        self.assertEqual(C._load()["events"][code2]["state"], "open")

    def test_analytics_and_league(self):
        def mk(college, scores):
            code = C.new_event(f"{college} Day", "Guntur", [college], 5, "easy",
                               created_by="admin")
            d = C._load(); e = d["events"][code]
            e["questions"] = [
                {"id": "q1", "q_en": "Reasoning Q", "q_te": "", "options_en": ["a", "b", "c", "d"],
                 "options_te": [], "answer_index": 0, "window": 40, "channel": "TSPSC",
                 "topic": "Reasoning", "subject": "reasoning"},
                {"id": "q2", "q_en": "Science Q", "q_te": "", "options_en": ["a", "b", "c", "d"],
                 "options_te": [], "answer_index": 1, "window": 40, "channel": "TSPSC",
                 "topic": "Science", "subject": "science"},
            ]
            e["state"] = "done"
            e["players"] = {}
            e["answers"] = {"0": {}, "1": {}}
            for uid, (corr, pts) in scores.items():
                e["players"][uid] = {"college": college, "name": f"P{uid}", "pts": pts,
                                     "correct": corr, "answered": 2, "joined": "x",
                                     "first": None, "last": None}
                e["answers"]["0"][uid] = 10 if corr >= 1 else 0
                e["answers"]["1"][uid] = 10 if corr >= 2 else 0
            C._save(d)
            return code

        code_a = mk("Alpha College", {"1": (2, 24), "2": (1, 10)})
        mk("Beta College", {"3": (0, 0), "4": (1, 8)})
        rep = C.report_dict(code_a)
        by_topic = {t["topic"]: t["pct"] for t in rep["topic_stats"]}
        self.assertEqual(by_topic["Reasoning"], 100)
        self.assertEqual(by_topic["Science"], 50)
        hardest = rep["question_stats"][0]
        self.assertEqual(hardest["pct"], 50)
        league = C.league_table()
        self.assertEqual(league[0]["college"], "Alpha College")
        self.assertEqual(league[0]["wins"], 1)
        self.assertEqual(league[0]["events"], 1)
        self.assertEqual(league[0]["students"], 2)

    def test_dashboard_wiring(self):
        src = (Path(__file__).resolve().parents[1]
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/campus/live"', '"/api/campus/control"',
                       '"/api/campus/league"', "watchCampusLive",
                       "controlCampus", "loadCampusLeague", "campus-start-at",
                       "campus.advance_now", "campus.finish_now",
                       "campus.live_snapshot", "campus.league_table"):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
