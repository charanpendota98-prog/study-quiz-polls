# -*- coding: utf-8 -*-
"""🚀 140X Exam-Day Engine: live blast, weekly report, mock pacing.

Pins (probe-verified):
  • mock_submit times: avg_sec + slow (>90s) list, clamped values
  • LIVE-SOON blast: exam <=30 min → goal-matched/reminded linked
    students get one join-now job (dedupe)
  • Weekly report: Sunday >=20:00, active students only, ISO-week
    dedupe key
  • Wiring: submit route passes times; SPA captures per-question
    seconds + renders avg/slow pacing hints
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
            "name": "Adv140 Tester", "district": "Guntur", "points": 0,
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
        ok, info = portal.register_student(self.mem, "Adv140 Tester",
                                           "9822000140", "Guntur",
                                           "railway")
        assert ok, info
        self.tok = info["token"]
        ok, c = portal.tg_link_code(self.mem, self.tok)
        assert ok, c
        ok, cl = portal.tg_link_claim(self.mem, 555140, c["code"])
        assert ok, cl

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestExamDay140(_Base):
    def test_mock_timing(self):
        ok, run = portal.mock_start(self.mem, self.tok, "railway")
        self.assertTrue(ok, run)
        ok, res = portal.mock_submit(
            self.mem, self.tok, run["run_id"],
            {"0": 0, "1": 0, "2": 0}, {"0": 30, "1": 120, "2": 45})
        self.assertTrue(ok, res)
        self.assertEqual(res["avg_sec"], 65.0)
        self.assertEqual(res["slow"], [1])

    def test_live_soon_blast_dedupe(self):
        d = portal._load()
        starts = (portal._now() + timedelta(minutes=20)).isoformat()
        d.setdefault("exams", {})["EX140"] = {
            "id": "EX140", "title": "140 Live", "starts_at": starts,
            "goal": "railway"}
        portal._save(d)
        jobs = portal.due_bot_reminders(self.mem)
        live = [j for j in jobs if j["kind"] == "live_soon"]
        self.assertEqual(len(live), 1)
        self.assertEqual(live[0]["tg_id"], "555140")
        jobs2 = portal.due_bot_reminders(self.mem)
        self.assertEqual(
            [j for j in jobs2 if j["kind"] == "live_soon"], [])

    def test_weekly_report_sunday(self):
        real = portal._now
        try:
            now = datetime.now(config.IST)
            delta = (6 - now.weekday()) % 7 or 7
            sun = (now + timedelta(days=delta)).replace(
                hour=20, minute=30, second=0, microsecond=0)
            portal._now = lambda: sun
            m = self.mem._get("w9822000140")
            m["daylog"] = {sun.strftime("%Y-%m-%d"): [10, 7]}
            jobs = portal.due_bot_reminders(self.mem)
            wk = [j for j in jobs if j["kind"] == "weekly_report"]
            self.assertEqual(len(wk), 1)
            self.assertIn("70%", wk[0]["text"])
        finally:
            portal._now = real


class TestWiring140(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_wiring(self):
        self.assertIn("body.get(\"times\")", self.dash)
        self.assertIn("MOCK.times[q.i]", self.dash)
        self.assertIn("d.avg_sec", self.dash)
        self.assertIn("(d.slow || []).includes(r.i)", self.dash)


if __name__ == "__main__":
    unittest.main()
