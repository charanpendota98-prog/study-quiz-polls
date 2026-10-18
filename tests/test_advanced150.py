# -*- coding: utf-8 -*-
"""🚀 150X Offline + Pacing: daily timing, offline queue, SW v4, share.

Pins (probe-verified):
  • daily_answer sec: per-question seconds clamped + avg_sec on
    completion (state daily carries it); repeat answer idempotent
  • /api/portal/answer route passes sec through
  • Offline: state/daily snapshots in localStorage, offline answer
    queue + auto flush on reconnect/online, offline banner
  • Service worker v4 (old caches cleaned, manifest precached)
  • Share-progress (Web Share API + clipboard fallback)
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
            "name": "Adv150 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": []})

    def award_answer(self, uid, username="", correct=True, topic="",
                     qid=""):
        m = self._get(uid)
        m["points"] = m.get("points", 0) + (10 if correct else 0)
        m["total"] = m.get("total", 0) + 1
        return {"points": m["points"]}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"
        self.mem = _Members()
        ok, info = portal.register_student(self.mem, "Adv150 Tester",
                                           "9822000150", "Guntur",
                                           "railway")
        assert ok, info
        self.tok = info["token"]
        self.uid = "w9822000150"

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf

    def _correct_choice(self, i):
        d = portal._load()
        paper = portal._daily_paper(d)
        _o, perm = portal._display(
            paper["qs"][i], f"{self.uid}:{portal._today()}:{i}")
        return perm.index(paper["qs"][i]["answer_index"])


class TestDailyPacing150(_Base):
    def test_avg_sec_and_idempotent(self):
        q = portal.daily_questions(self.mem, self.tok)
        n = len(q["questions"])
        last = None
        for i in range(n):
            last = portal.daily_answer(self.mem, self.tok, i,
                                       self._correct_choice(i),
                                       sec=(100 if i == 0 else 40))
        ok, res = last
        self.assertTrue(ok, res)
        self.assertTrue(res["done"])
        self.assertEqual(res["avg_sec"], 46.0)
        self.assertEqual(res["score"], n)
        ok, again = portal.daily_answer(self.mem, self.tok, 0, 0, sec=5)
        self.assertTrue(again.get("already"))
        st = portal.state(self.mem, self.tok)
        self.assertEqual(st["daily"]["avg_sec"], 46.0)


class TestWiring150(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_offline_and_pacing_wiring(self):
        for s in ("body.get(\"sec\")", "sec: Math.round",
                  "su_offline_state", "su_offline_daily", "su_offq",
                  "flushOffline", "window.addEventListener('online'",
                  "offline-bar", "studentup-v4", "shareProgress",
                  "navigator.share", "su_offline"):
            self.assertIn(s, self.dash)


if __name__ == "__main__":
    unittest.main()
