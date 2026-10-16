# -*- coding: utf-8 -*-
"""✨ Smart Day Planner: plan from active hours + weak topics, one-click apply."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core import planner


class TestPlanner(unittest.TestCase):
    def test_plan_items(self):
        channels = [("TSPSC", {"name": "TSPSC Hub"}), ("BANKING", {"name": "Banking"})]

        def fake_rates(ch):
            return {"algebra": {"attempts": 20, "correct": 8, "rate": 0.4},
                    "history": {"attempts": 30, "correct": 27, "rate": 0.9}} if ch == "TSPSC" else {}

        plan = planner.today_plan(channels=channels, rates_fn=fake_rates,
                                  slots=["07:00", "20:30"])
        tg_items = [i for i in plan["items"] if i["mode"] == "tg"]
        self.assertEqual(len(tg_items), 2)
        first, second = tg_items
        self.assertEqual((first["time"], first["channels"], first["count"]),
                         ("07:00", ["TSPSC"], 5))
        self.assertEqual(first["topics"], ["algebra"])
        self.assertIn("algebra", first["reason"])
        self.assertEqual(second["topics"], [])
        self.assertIn("General revision", second["reason"])

    def test_apply_creates_jobs(self):
        calls = []

        def fake_add(time_str, **kw):
            calls.append((time_str, kw))
            return {"id": f"job_{len(calls)}"}

        items = [{"time": "07:00", "name": "TSPSC Hub", "channels": ["TSPSC"], "count": 5},
                 {"time": "20:30", "name": "Ghost", "channels": [], "count": 5},
                 {"time": "21:00", "name": "Banking", "channels": ["BANKING"], "count": 99}]
        created = planner.apply_plan(items, add_fn=fake_add)
        self.assertEqual(created, ["job_1", "job_2"])   # empty-channel item skipped
        self.assertEqual(calls[0][1]["mode"], "tg")
        self.assertEqual(calls[0][1]["telegram_channels"], ["TSPSC"])
        self.assertEqual(calls[1][1]["questions_count"], 20)   # clamped

    def test_best_slots_defaults(self):
        slots = planner._best_slots(3)
        self.assertEqual(len(slots), 3)
        self.assertTrue(all(len(s) == 5 and s[2] == ":" for s in slots))

    def test_dashboard_wiring(self):
        src = (Path(__file__).resolve().parents[1]
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/planner/today"', '"/api/planner/apply"',
                       "planner.today_plan()", "planner.apply_plan",
                       "loadPlanner", "applyPlanner", "planner-box"):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
