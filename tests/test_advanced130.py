# -*- coding: utf-8 -*-
"""🚀 130X Bot Delivery Loop: broadcasts + reminders (claim-once).

Pins (probe-verified):
  • admin_bot_broadcast: empty rejected; goal-filtered target count
  • bot_outbox_jobs: claim-once drain (second call empty), jobs only
    to linked users of the goal
  • due_bot_reminders: exam 24h window job + dedupe (no repeat);
    evening daily nudge (hour-gated) for unfinished linked students
  • tg_stats.bot_msgs counts delivered jobs; analytics exposes msgs
  • Wiring: bot notify tick (10-min throttle), admin route + composer
"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, brain, config  # noqa: E402


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
            "name": "Adv130 Tester", "district": "Guntur", "points": 0,
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
        self.toks = {}
        for name, phone, goal, tg in (
                ("Adv130 Rail", "9822000130", "railway", 555130),
                ("Adv130 SSC", "9822000131", "ssc", 555131)):
            ok, info = portal.register_student(self.mem, name, phone,
                                               "Guntur", goal)
            assert ok, info
            ok, c = portal.tg_link_code(self.mem, info["token"])
            assert ok, c
            ok, cl = portal.tg_link_claim(self.mem, tg, c["code"])
            assert ok, cl
            self.toks[goal] = info["token"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestDelivery130(_Base):
    def test_broadcast_claim_once_goal_filter(self):
        ok, err = portal.admin_bot_broadcast(self.mem, "   ")
        self.assertFalse(ok)
        ok, b = portal.admin_bot_broadcast(self.mem, "Grand Mock 7PM!",
                                           goal="railway")
        self.assertTrue(ok, b)
        self.assertEqual(b["targets"], 1)
        jobs = portal.bot_outbox_jobs(self.mem)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["tg_id"], "555130")
        self.assertEqual(jobs[0]["kind"], "broadcast")
        self.assertEqual(portal.bot_outbox_jobs(self.mem), [])

    def test_exam_reminder_dedupe(self):
        d = portal._load()
        starts = (portal._now() + timedelta(hours=5)).isoformat()
        d.setdefault("exams", {})["EX130"] = {
            "id": "EX130", "title": "Adv130 Live", "starts_at": starts}
        d.setdefault("exam_reminds", {})["EX130"] = ["w9822000130"]
        portal._save(d)
        jobs = portal.due_bot_reminders(self.mem)
        rem = [j for j in jobs if j["kind"] == "exam_remind"]
        self.assertEqual(len(rem), 1)
        self.assertEqual(rem[0]["tg_id"], "555130")
        jobs2 = portal.due_bot_reminders(self.mem)
        self.assertEqual(
            [j for j in jobs2 if j["kind"] == "exam_remind"], [])

    def test_daily_nudge_evening_only(self):
        real_now = portal._now
        try:
            fixed = datetime.now(config.IST).replace(
                hour=19, minute=0, second=0, microsecond=0)
            portal._now = lambda: fixed
            jobs = portal.due_bot_reminders(self.mem)
            daily = [j for j in jobs if j["kind"] == "daily_remind"]
            self.assertEqual(len(daily), 2)  # both linked, none done
        finally:
            portal._now = real_now

    def test_msgs_counter(self):
        portal.admin_bot_broadcast(self.mem, "Hello all")
        portal.bot_outbox_jobs(self.mem)
        an = portal.portal_analytics(self.mem)
        self.assertEqual(an["bot"]["msgs"], 2)
        self.assertEqual(an["bot"]["linked"], 2)


class TestWiring130(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        cls.bot = (ROOT / "scripts" / "bot.py").read_text(encoding="utf-8")

    def test_wiring(self):
        self.assertIn('p.path == "/api/portal/admin/bot_broadcast"',
                      self.dash)
        self.assertIn("sendBotBroadcast", self.dash)
        self.assertIn("d.bot.msgs", self.dash)
        self.assertIn("_bot_notify_tick130", self.bot)
        self.assertIn("due_bot_reminders", self.bot)
        self.assertIn("bot_outbox_jobs", self.bot)


if __name__ == "__main__":
    unittest.main()
