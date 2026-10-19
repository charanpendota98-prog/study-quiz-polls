# -*- coding: utf-8 -*-
"""🚀 250X: churn cohorts + AI materials suggestions + F8 split + CI.

Pins:
  • _churn_cohorts tiers are honest last_active buckets (active /
    cooling / at_risk / critical incl. never-tracked), and analytics
    exposes them as churn250 without dropping the legacy key.
  • materials_suggest matches vault items to the student's weak
    topic/section (from the revision planner) with a reason string.
  • Bot: /health branch is extracted to _cmd_health220 (F8 step-1);
    the method renders the armor stats message unchanged.
  • CI workflow runs the real suite + finalize gate.
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
            "name": "Adv250 Tester", "district": "Guntur", "points": 0,
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


class TestChurn250(_Base):
    def test_tiers_and_analytics_key(self):
        now = portal._now()
        for uid, days in (("u1", 0), ("u2", 5), ("u3", 10), ("u4", 30)):
            self.mem.members[uid] = {
                "name": uid, "registered": True,
                "last_active": (now - timedelta(days=days)).strftime("%Y-%m-%d")}
        self.mem.members["u5"] = {"name": "u5", "registered": True,
                                  "last_active": ""}
        c = portal._churn_cohorts(list(self.mem.members.values()))
        self.assertEqual(
            (c["active"], c["cooling"], c["at_risk"], c["critical"]),
            (1, 1, 1, 2))
        self.assertEqual(c["total"], 5)
        an = portal.portal_analytics(self.mem)
        self.assertIn("churn250", an)
        self.assertIn("at_risk_7d", an["churn"])


class TestSuggest250(_Base):
    def test_weak_topic_matches_vault(self):
        ok, info = portal.register_student(
            self.mem, "Adv250 Sug", "9822001001", "Guntur", "railway")
        self.assertTrue(ok, info)
        tok = info["token"]
        self.mem.members["w9822001001"]["topics"] = {
            "algebra": {"total": 10, "correct": 3}}
        hit = portal.materials_add(self.mem, "Algebra Mastery PDF",
                                   "algebra.pdf", goal="railway",
                                   topic="algebra", cost=0)
        portal.materials_add(self.mem, "History Notes", "hist.pdf",
                             goal="railway", topic="history", cost=0)
        sg = portal.materials_suggest(self.mem, tok)
        titles = [s["title"] for s in sg["suggestions"]]
        self.assertIn("Algebra Mastery PDF", titles)
        self.assertNotIn("History Notes", titles)
        s0 = sg["suggestions"][0]
        self.assertEqual(s0["id"], hit["id"])
        self.assertIn("algebra", s0["reason"])


class TestBotSplit250(unittest.TestCase):
    def test_health_method_extracted_and_works(self):
        import bot as botmod
        b = botmod.Bot(dry=True)
        self.assertTrue(hasattr(b, "_cmd_health220"))
        sent = []
        b.tg.send_message = lambda cid, text, **kw: sent.append(text)
        b._cmd_health220(1, 1)
        self.assertTrue(sent and "Bot Health" in sent[0])
        src = (ROOT / "scripts" / "bot.py").read_text()
        i = src.find('low.startswith("/health")')
        self.assertIn("self._cmd_health220(uid, chat_id)", src[i:i + 200])


class TestWiring250(unittest.TestCase):
    def test_dashboard_and_ci(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        for needle in ("/api/portal/materials_suggest",
                       "d.churn250", "materials_suggest"):
            self.assertIn(needle, src)
        psrc = (ROOT / "scripts" / "core" / "portal.py").read_text()
        for needle in ("def _churn_cohorts", "def materials_suggest"):
            self.assertIn(needle, psrc)
        ci = ROOT / ".github" / "workflows" / "tests.yml"
        self.assertTrue(ci.exists())
        txt = ci.read_text()
        self.assertIn("unittest discover", txt)
        self.assertIn("finalize.py", txt)


if __name__ == "__main__":
    unittest.main()
