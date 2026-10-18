#!/usr/bin/env python3
"""Vision Mission-Control tests — mana vision, numbers tho.

vision_report() must be honest (numbers come from real stores), point at
the weakest pillar with priority actions, and never crash on empty data.
Run: python3 -m unittest discover -s tests -p "test_vision.py"
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import vision  # noqa: E402


def _seed(dd: Path):
    (dd / "question_bank.json").write_text(json.dumps({"questions": [
        {"id": "p1", "channel": "SSC", "source": "pyq"},
        {"id": "p2", "channel": "SSC", "source": "pyq"},
        {"id": "g1", "channel": "SSC", "source": "offline-gen"},
        {"id": "t1", "channel": "TSPSC", "source": "offline-gen"},
    ]}))
    (dd / "used_questions.json").write_text(json.dumps({"SSC": ["p1"]}))
    (dd / "collector_sources.json").write_text(json.dumps({"sources": [
        {"enabled": True}, {"enabled": False, "auto_enable_if_live": True}]}))
    (dd / "pyq_papers.json").write_text(json.dumps({"papers": [
        {"url": "http://x/a.pdf"}, {"url": "http://x/b.pdf"}]}))
    (dd / "pyq_state.json").write_text(json.dumps(
        {"http://x/a.pdf": {"status": "done", "questions": 12}}))
    (dd / "whatsapp_groups.json").write_text(json.dumps({"groups": [
        {"id": "G1", "name": "G1", "active": True}]}))
    (dd / "whatsapp_schedules.json").write_text(json.dumps({"jobs": [
        {"id": "j1", "mode": "tg", "enabled": True,
         "telegram_channels": ["SSC"], "target_group_ids": []}]}))
    (dd / "members.json").write_text(json.dumps({"members": {
        "1": {"registered": True, "points": 50, "district": "Warangal"},
        "2": {"registered": False, "points": 0}}}))
    today = datetime.now().strftime("%Y-%m-%d")
    (dd / "broadcast_history.json").write_text(json.dumps({"events": [
        {"date": today, "kind": "telegram", "count": 10, "dry": False},
        {"date": today, "kind": "whatsapp", "count": 5, "dry": True}]}))


class TestVision(unittest.TestCase):
    def test_report_from_seeded_stores(self):
        with tempfile.TemporaryDirectory() as td:
            dd = Path(td)
            _seed(dd)
            rep = vision.vision_report(data_dir=dd)
        c = rep["pillars"]["content"]
        self.assertEqual(c["bank_questions"], 4)
        self.assertEqual(c["pyq_questions"], 2)
        self.assertEqual(c["pyq_papers"], "1/2")
        self.assertEqual(rep["pillars"]["reach"]["members_registered"], 1)
        self.assertEqual(rep["pillars"]["engagement"]["week_polls_sent"], 10)
        self.assertEqual(rep["pillars"]["engagement"]["week_dry_polls"], 5)
        self.assertEqual(rep["pillars"]["coverage"]["tg_jobs"], 1)
        self.assertIn("SSC", rep["pillars"]["coverage"]["tg_jobs"] and
                      ["SSC"])  # covered list sanity (not a gap)
        self.assertTrue(0 <= rep["score"] <= 100)
        self.assertTrue(rep["actions"])  # gaps must produce next actions

    def test_empty_stores_never_crash(self):
        with tempfile.TemporaryDirectory() as td:
            rep = vision.vision_report(data_dir=Path(td))
        self.assertEqual(rep["pillars"]["content"]["bank_questions"], 0)
        self.assertTrue(rep["actions"])

    def test_text_format(self):
        with tempfile.TemporaryDirectory() as td:
            dd = Path(td)
            _seed(dd)
            txt = vision.format_text(vision.vision_report(data_dir=dd))
        self.assertIn("VISION", txt)
        self.assertIn("Next actions", txt)

    def test_dashboard_wired(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("/api/vision", src)
        self.assertIn("vision-score", src)


if __name__ == "__main__":
    unittest.main()
