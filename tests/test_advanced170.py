# -*- coding: utf-8 -*-
"""🚀 170X Retention Machine: win-back, churn analytics, shields.

Pins (probe-verified):
  • Win-back: 7d+ inactive linked students get ONE win-back job per
    ISO week (personalized with points); active students untouched
  • portal_analytics["churn"]: at_risk_7d + winback_sent counters
  • Profile carries streak shields (home chip renders them)
  • Wiring: admin churn render + shields chip
"""
import sys
import tempfile
import unittest
from datetime import timedelta
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
            "name": "Adv170 Tester", "district": "Guntur", "points": 120,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": [], "shields": 2})

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
        self.toks = {}
        for name, phone, tg in (("Adv170 Old", "9822000170", 555170),
                                ("Adv170 New", "9822000171", 555171)):
            ok, info = portal.register_student(self.mem, name, phone,
                                               "Guntur", "railway")
            assert ok, info
            ok, c = portal.tg_link_code(self.mem, info["token"])
            assert ok, c
            ok, cl = portal.tg_link_claim(self.mem, tg, c["code"])
            assert ok, cl
            self.toks[phone] = info["token"]
        old = (portal._now() - timedelta(days=12)).strftime("%Y-%m-%d")
        self.mem._get("w9822000170")["last_active"] = old
        self.mem._get("w9822000171")["last_active"] = portal._today()

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestRetention170(_Base):
    def test_winback_once_per_week(self):
        jobs = portal.due_bot_reminders(self.mem)
        wb = [j for j in jobs if j["kind"] == "winback"]
        self.assertEqual(len(wb), 1)
        self.assertEqual(wb[0]["tg_id"], "555170")
        self.assertIn("120 points", wb[0]["text"])
        jobs2 = portal.due_bot_reminders(self.mem)
        self.assertEqual([j for j in jobs2 if j["kind"] == "winback"],
                         [])

    def test_churn_analytics(self):
        portal.due_bot_reminders(self.mem)
        an = portal.portal_analytics(self.mem)
        self.assertEqual(an["churn"]["at_risk_7d"], 1)
        self.assertEqual(an["churn"]["winback_sent"], 1)

    def test_shields_in_profile(self):
        st = portal.state(self.mem, self.toks["9822000170"])
        self.assertEqual(st["student"]["shields"], 2)


class TestWiring170(unittest.TestCase):
    def test_wiring(self):
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        self.assertIn("d.churn.at_risk_7d", dash)
        self.assertIn("s.shields", dash)
        self.assertIn("winback", dash)


if __name__ == "__main__":
    unittest.main()
