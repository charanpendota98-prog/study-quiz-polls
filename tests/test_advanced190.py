# -*- coding: utf-8 -*-
"""🚀 190X Total Bug-Hunt: outbox loss, stale-day sync, API hammering.

Bugs found & fixed (probe-verified):
  1. bot_outbox_jobs: limit daatithe claims delete ayyi migilina
     targets ki message poyedi → per-target sent_to tracking,
     partial claims retain the entry (no loss, no dupe).
  2. Offline daily answers: ninna queue aina answers next-day paper
     ki sync ayyevi (wrong record) → queue carries paper `day`,
     flush stale-day ni drop chestundi.
  3. _bot_username: failed getMe prathi request ki Telegram API ni
     hit chesedi → failure 300s negative-cache.
Also pins: daily_questions carries server paper date.
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
            "name": "Adv190 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": []})

    def award_answer(self, uid, username="", correct=True, topic="",
                     qid=""):
        return {"points": 0}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"
        self.mem = _Members()
        self.toks = []
        for i, tg in enumerate((555190, 555191, 555192)):
            ok, info = portal.register_student(
                self.mem, f"Adv190-{i}", f"982200019{i}", "Guntur",
                "railway")
            assert ok, info
            ok, c = portal.tg_link_code(self.mem, info["token"])
            assert ok, c
            ok, cl = portal.tg_link_claim(self.mem, tg, c["code"])
            assert ok, cl
            self.toks.append(info["token"])

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestBugFixes190(_Base):
    def test_outbox_partial_claim_no_loss(self):
        ok, b = portal.admin_bot_broadcast(self.mem, "Partial test")
        self.assertTrue(ok, b)
        j1 = portal.bot_outbox_jobs(self.mem, limit=2)
        self.assertEqual(len(j1), 2)
        pending = portal._load().get("bot_outbox") or []
        self.assertEqual(len(pending), 1)  # retained, not deleted
        j2 = portal.bot_outbox_jobs(self.mem, limit=2)
        self.assertEqual(len(j2), 1)
        all_ids = [j["tg_id"] for j in j1 + j2]
        self.assertEqual(sorted(all_ids),
                         ["555190", "555191", "555192"])  # no dupe/loss
        self.assertEqual(portal.bot_outbox_jobs(self.mem), [])
        an = portal.portal_analytics(self.mem)
        self.assertEqual(an["bot"]["msgs"], 3)

    def test_daily_questions_date(self):
        q = portal.daily_questions(self.mem, self.toks[0])
        self.assertEqual(q["date"], portal._today())


class TestBotUsernameNegCache190(unittest.TestCase):
    def test_failed_lookup_cached_300s(self):
        import ast
        import time as _time
        src = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_bot_username")
        calls = {"n": 0}

        class _Tg:
            def _call(self, method, payload):
                calls["n"] += 1
                raise RuntimeError("no network")

        class _Cfg:
            BOT_USERNAME = ""

        cache = {"name": "", "ts": 0}
        ns = {"config": _Cfg, "time": _time,
              "_BOT_USERNAME_CACHE": cache, "Telegram": _Tg}
        exec(compile(ast.Module(body=[fn], type_ignores=[]),
                     "<bu>", "exec"), ns)
        self.assertEqual(ns["_bot_username"](), "StudentUpBot")
        self.assertEqual(calls["n"], 1)
        # cached failure: same fallback, NO second API attempt
        self.assertEqual(ns["_bot_username"](), "StudentUpBot")
        self.assertEqual(calls["n"], 1)


class TestWiring190(unittest.TestCase):
    def test_wiring(self):
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        for s in ("a.day !== todayStr", "window._qDay",
                  'get("tried")', "migilina targets"):
            self.assertIn(s if s != "migilina targets" else "su_offq",
                          dash)
        src = (ROOT / "scripts" / "core" / "portal.py").read_text(
            encoding="utf-8")
        self.assertIn("sent_to", src)
        self.assertIn('"date": _today()', src)


if __name__ == "__main__":
    unittest.main()
