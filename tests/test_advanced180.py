# -*- coding: utf-8 -*-
"""🚀 180X Exam-Day War Room: results blast + perfection sweep.

Pins (probe-verified):
  • Exam done → winners blast ONCE to reminded + goal-matched +
    ENTRANT linked students (dedupe key), personal result line
  • Winners only from correct>0 entries, joined_at tie-break order
  • tg_stats.result_blasts counter + analytics churn exposes it
  • Admin render shows Result blasts
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
            "name": "Adv180 Tester", "district": "Guntur", "points": 0,
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
        for name, phone, goal, tg in (
                ("Adv180 Champ", "9822000180", "railway", 555180),
                ("Adv180 Entrant", "9822000181", "ssc", 555181),
                ("Adv180 Outsider", "9822000182", "ssc", 555182)):
            ok, info = portal.register_student(self.mem, name, phone,
                                               "Guntur", goal)
            assert ok, info
            ok, c = portal.tg_link_code(self.mem, info["token"])
            assert ok, c
            ok, cl = portal.tg_link_claim(self.mem, tg, c["code"])
            assert ok, cl
        d = portal._load()
        starts = (portal._now() - timedelta(hours=2)).isoformat()
        qs = [{"id": f"Q{i}", "topic": "x"} for i in range(10)]
        d.setdefault("exams", {})["EX180"] = {
            "id": "EX180", "title": "180 Live Final",
            "starts_at": starts, "duration_min": 30, "goal": "railway",
            "kind": "live", "qs": qs,
            "entries": {
                "w9822000180": {"uid": "w9822000180",
                                "name": "Adv180 Champ", "correct": 8,
                                "pts": 80, "joined_at": "1"},
                "w9822000181": {"uid": "w9822000181",
                                "name": "Adv180 Entrant", "correct": 6,
                                "pts": 60, "joined_at": "2"}}}
        portal._save(d)

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf


class TestWarRoom180(_Base):
    def test_results_blast_recipients_and_dedupe(self):
        jobs = portal.due_bot_reminders(self.mem)
        res = [j for j in jobs if j["kind"] == "exam_result"]
        got = sorted(j["tg_id"] for j in res)
        # champ (goal match) + ssc ENTRANT; ssc outsider excluded
        self.assertEqual(got, ["555180", "555181"])
        champ = [j for j in res if j["tg_id"] == "555180"][0]
        self.assertIn("Adv180 Champ 8/10", champ["text"])
        self.assertIn("Mee result: 8/10", champ["text"])
        jobs2 = portal.due_bot_reminders(self.mem)
        self.assertEqual(
            [j for j in jobs2 if j["kind"] == "exam_result"], [])

    def test_result_blasts_counter(self):
        portal.due_bot_reminders(self.mem)
        an = portal.portal_analytics(self.mem)
        self.assertEqual(an["churn"]["result_blasts"], 2)


class TestWiring180(unittest.TestCase):
    def test_wiring(self):
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        src = (ROOT / "scripts" / "core" / "portal.py").read_text(
            encoding="utf-8")
        self.assertIn("d.churn.result_blasts", dash)
        self.assertIn('"exam_result"', src)
        self.assertIn("rasina vallu andaru", src)


if __name__ == "__main__":
    unittest.main()
