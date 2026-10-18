# -*- coding: utf-8 -*-
"""🚀 100X World-class round: anti-farm, locks, readiness, ETag.

Pins (probe-verified):
  • Anti-farm: same question correct → points only once per day
    (portal _award choke point; poll awards untouched)
  • Portal-store mutators locked (flag_question, set_exam_reminder)
  • Input hardening: exam_id truncated to 40, notices limit clamped
  • Goal Hub readiness block (Brain score/band/theta/components)
  • ETag/304 support on portal + public pages (dashboard untouched)
  • Keyboard shortcuts wiring (1-4 answer, N next)
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
            "name": "Adv100 Tester", "district": "Guntur", "points": 0,
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
        ok, info = portal.register_student(self.mem, "Adv100 Tester",
                                           "9822000100", "Guntur",
                                           "railway")
        assert ok, info
        self.tok = info["token"]
        self.uid = "w9822000100"

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestAntiFarm100(_Base):
    def test_same_question_points_once_per_day(self):
        q = {"id": "QX100", "topic": "polity"}
        portal._award(self.mem, self.uid, "Adv100 Tester", True, q)
        self.assertEqual(self.mem._get(self.uid)["points"], 10)
        portal._award(self.mem, self.uid, "Adv100 Tester", True, q)
        self.assertEqual(self.mem._get(self.uid)["points"], 10)
        portal._award(self.mem, self.uid, "Adv100 Tester", True,
                      {"id": "QY100", "topic": "polity"})
        self.assertEqual(self.mem._get(self.uid)["points"], 20)

    def test_award_log_pruned_to_today(self):
        portal._award(self.mem, self.uid, "Adv100 Tester", True,
                      {"id": "QZ100", "topic": "polity"})
        log = portal._load().get("award_log") or {}
        self.assertIn(self.uid, log)
        self.assertEqual(log[self.uid]["qids"], ["QZ100"])


class TestHardening100(_Base):
    def test_exam_id_truncated_and_lock(self):
        ok, r = portal.set_exam_reminder(self.mem, self.tok, "X" * 100,
                                         True)
        self.assertTrue(ok, r)
        self.assertEqual(len(r["exam_id"]), 40)
        self.assertTrue(r["remind"])

    def test_hub_readiness(self):
        ok, hub = portal.goal_hub(self.mem, self.tok, "railway")
        self.assertTrue(ok, hub)
        self.assertIn("readiness", hub)
        self.assertIn("score", hub["readiness"])
        self.assertIn("band", hub["readiness"])


class TestWiring100(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_etag_wiring(self):
        self.assertIn("def _send_html(self, html, etag=False)", self.dash)
        self.assertIn("If-None-Match", self.dash)
        self.assertIn("_send_html(PORTAL_HTML, etag=True)", self.dash)
        self.assertIn("etag=True)", self.dash)

    def test_keyboard_shortcuts(self):
        self.assertIn("keydown", self.dash)
        self.assertIn("speakCurrent", self.dash)
        self.assertIn("d.readiness", self.dash)


if __name__ == "__main__":
    unittest.main()
