# -*- coding: utf-8 -*-
"""🚀 90X Smart Engine round: blueprint mocks, notes, levels, retention.

Pins (probe-verified):
  • Blueprint Mock (kind='blueprint'): exam-pattern compose, 15 Qs
  • Topic Notes from coach lessons bank (topic filter + goal default)
  • Student level + progress in profile/state (members LEVELS ladder)
  • portal_analytics retention block (new_7d/active_7d/pct)
  • exam_stock/paper_catalog TTL cache (stable within window)
  • flags = 20 (+blueprint_mocks) + SPA/routes wiring
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, brain, flags  # noqa: E402


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
            "name": "Adv90 Tester", "district": "Guntur", "points": 150,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": []})

    def award_answer(self, uid, username="", correct=True, topic="",
                     qid=""):
        m = self._get(uid)
        m["points"] = m.get("points", 0) + (10 if correct else 0)
        return {"points": m["points"]}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"
        self.mem = _Members()
        ok, info = portal.register_student(self.mem, "Adv90 Tester",
                                           "9822000090", "Guntur",
                                           "railway")
        assert ok, info
        self.tok = info["token"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestSmartEngine90(_Base):
    def test_blueprint_mock(self):
        ok, run = portal.mock_start(self.mem, self.tok, "railway",
                                    kind="blueprint")
        self.assertTrue(ok, run)
        self.assertEqual(run["kind"], "blueprint")
        self.assertIn("Blueprint Mock", run["label"])
        self.assertEqual(len(run["questions"]), 15)

    def test_level_progress(self):
        st = portal.state(self.mem, self.tok)
        lv = st["student"]["level"]
        self.assertEqual(lv["title"], "Bronze")  # 150 pts
        self.assertEqual(lv["next"], 300)
        self.assertEqual(lv["progress"], 25)

    def test_topic_notes(self):
        ok, nt = portal.topic_notes(self.mem, self.tok, "Percentage")
        self.assertTrue(ok, nt)
        self.assertGreaterEqual(nt["total"], 1)
        if nt["notes"]:
            self.assertIn("Percentage", nt["notes"][0]["topic"])
            self.assertTrue(nt["notes"][0]["en"])
        ok, nt2 = portal.topic_notes(self.mem, self.tok)
        self.assertTrue(ok, nt2)
        self.assertIsInstance(nt2["notes"], list)
        ok, _e = portal.topic_notes(self.mem, "badtoken")
        self.assertFalse(ok)

    def test_retention_block(self):
        from datetime import datetime, timedelta
        m = self.mem._get("w9822000090")
        m["registered"] = True
        m["registered_at"] = datetime.now().strftime("%Y-%m-%d")
        an = portal.portal_analytics(self.mem)
        self.assertIn("retention", an)
        self.assertEqual(an["retention"]["new_7d"], 1)
        self.assertIn("active_7d_pct", an["retention"])

    def test_stock_cache(self):
        self.assertIs(portal.exam_stock(), portal.exam_stock())
        self.assertIs(portal.paper_catalog(), portal.paper_catalog())

    def test_flags_20(self):
        self.assertEqual(len(flags.all_flags()), 20)
        self.assertTrue(flags.enabled("blueprint_mocks"))


class TestWiring90(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")

    def test_notes_route_and_spa(self):
        self.assertIn('p.path == "/api/portal/notes"', self.dash)
        for fn in ("startBlueprint", "loadTopicNotes", "speakCurrent"):
            self.assertIn(fn, self.dash)
        self.assertIn('id="level-bar"', self.dash)
        self.assertIn("lv.progress", self.dash)
        self.assertIn("d.retention", self.dash)
        self.assertIn("'blueprint'", self.dash)


if __name__ == "__main__":
    unittest.main()
