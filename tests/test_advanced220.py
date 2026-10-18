# -*- coding: utf-8 -*-
"""🚀 220X: deep-audit fixes + bot armor + theme studio + planners.

Pins (all probe-verified):
  • _why() — the explanation single-source: bank questions (only
    explanation_en) now surface explanations everywhere (previously
    ALWAYS empty at 14 call sites).
  • Bot armor — _dispatch_update never raises; one poisonous update
    cannot eat the rest of the batch; malformed messages are skipped.
  • Telegram actually requests message_reaction updates (the branch
    that handled them could never fire before).
  • Smart Revision Planner tiers (SRS topics → weak section →
    bookmarks) and Rank Predictor v2 (cohort rank/percentile/gap).
  • Theme Studio wiring: 3 new themes, accent engine, SW v5, and the
    revision/rank2 routes + renderers.
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
            "name": "Adv220 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": [], "registered": True})

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

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf

    def _reg(self, name, phone, points):
        ok, info = portal.register_student(
            self.mem, "Adv220 " + name, phone, "Guntur", "railway")
        self.assertTrue(ok, info)
        self.mem.members["w" + phone]["points"] = points
        self.mem.members["w" + phone]["registered"] = True
        return info["token"]


class TestWhy220(unittest.TestCase):
    def test_why_fallback_chain(self):
        self.assertEqual(portal._why({"explanation_en": "EN"}), "EN")
        self.assertEqual(portal._why({"explanation_te": "TE"}), "TE")
        self.assertEqual(portal._why({"explanation": "RAW",
                                      "explanation_en": "EN"}), "RAW")
        self.assertEqual(portal._why({}), "")

    def test_no_raw_explanation_reads_left(self):
        src = (ROOT / "scripts" / "core" / "portal.py").read_text()
        self.assertNotIn('q.get("explanation", "")', src)
        self.assertNotIn('if q.get("explanation"):', src)
        self.assertGreaterEqual(src.count("_why(q)"), 10)


class TestBotArmor220(unittest.TestCase):
    def _bot(self):
        import bot as botmod
        return botmod.Bot(dry=True)

    def test_poisonous_update_isolated(self):
        b = self._bot()

        def boom(_x):
            raise RuntimeError("poison")

        b.handle_message = boom
        kind, ok = b._dispatch_update(
            {"message": {"chat": {"id": 1}, "text": "/quiz"}})
        self.assertEqual(kind, "message")
        self.assertFalse(ok)
        self.assertEqual(b._upd_stats["errors"], 1)

    def test_malformed_message_no_crash_and_unknown_kind_ok(self):
        b = self._bot()
        b.handle_message({"from": {"id": 1}, "text": "hi"})  # no chat
        kind, ok = b._dispatch_update({"edited_message": {"x": 1}})
        self.assertEqual(kind, "unknown")
        self.assertTrue(ok)
        h = b._bot_health220()
        self.assertGreaterEqual(h["updates"], 1)

    def test_reaction_updates_requested(self):
        src = (ROOT / "scripts" / "core" / "telegram.py").read_text()
        self.assertIn('"message_reaction"', src)
        self.assertIn('"message_reaction_count"', src)
        bsrc = (ROOT / "scripts" / "bot.py").read_text()
        self.assertIn("def _dispatch_update", bsrc)
        self.assertIn('low.startswith("/health")', bsrc)


class TestPlanners220(_Base):
    def test_revision_planner_tiers(self):
        tok = self._reg("Plan", "9822000701", 300)
        me = self.mem.members["w9822000701"]
        me["review"] = [
            {"qid": "x1", "topic": "algebra", "due": "2020-01-01"},
            {"qid": "x2", "topic": "algebra", "due": "2020-01-01"}]
        me["bookmarks"] = ["b1"]
        rp = portal.revision_planner(self.mem, tok)
        types = [p["type"] for p in rp["plan"]]
        self.assertIn("srs", types)
        self.assertIn("bookmarks", types)
        srs = next(p for p in rp["plan"] if p["type"] == "srs")
        self.assertEqual(srs["topic"], "algebra")
        self.assertEqual(srs["count"], 2)

    def test_rank_predict_cohorts(self):
        self._reg("Top", "9822000702", 900)
        self._reg("Mid", "9822000703", 500)
        tok = self._reg("Me", "9822000704", 300)
        rk = portal.rank_predict(self.mem, tok)
        self.assertEqual(rk["my_points"], 300)
        self.assertEqual(rk["goal_cohort"]["my_rank"], 3)
        self.assertEqual(rk["goal_cohort"]["next"]["gap"], 200)
        self.assertEqual(rk["overall"]["students"], 3)


class TestWiring220(unittest.TestCase):
    def test_dashboard_wiring(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        for needle in ("/api/portal/revision", "/api/portal/rank2",
                       "function loadRevision", "function loadRank2",
                       "theme-royal", "theme-grape", "theme-rose",
                       "function setAccent", "studentup-v5",
                       "explanation_te") or []:
            self.assertIn(needle, src)
        psrc = (ROOT / "scripts" / "core" / "portal.py").read_text()
        for needle in ("def revision_planner", "def rank_predict",
                       "def _why"):
            self.assertIn(needle, psrc)


if __name__ == "__main__":
    unittest.main()
