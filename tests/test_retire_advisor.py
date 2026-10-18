#!/usr/bin/env python3
"""Retire + Smart Slot Advisor tests.

Item-intelligence loop closure under test: too-easy questions (≥95%
correct with enough data) retire from fresh rounds via Bank.unused —
with a safety valve so a channel never goes short — and metrics expose
an hour-of-day answer profile the Conductor advisor renders.
Run: python3 -m unittest discover -s tests -p "test_retire_advisor.py"
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import item_intel, metrics  # noqa: E402
from core.question_bank import Bank  # noqa: E402


def _q(qid, ch="SSC"):
    return {"id": qid, "channel": ch, "source": "pyq",
            "q_en": f"Question {qid} about polity and governance?",
            "q_te": "", "options_en": ["A1", "B2", "C3", "D4"],
            "options_te": [], "answer_index": 0, "topic": "polity"}


def _bank(qs):
    b = object.__new__(Bank)
    b.questions = qs
    b.used = {}
    b._sig_set = set()
    b.shown_sigs = {"sigs": []}
    return b


class TmpIntel(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = item_intel.STATS_FILE
        item_intel.STATS_FILE = self.tmp / "item_stats.json"
        item_intel._cache["mtime"] = None
        item_intel._cache["data"] = {}
        # EASY1: 29/30 correct -> too_easy (retire); HARD1: suspect-free normal
        for i in range(30):
            item_intel.record("EASY1", i != 0, topic="polity", channel="SSC")

    def tearDown(self):
        item_intel.STATS_FILE = self._orig
        item_intel._cache["mtime"] = None


class TestRetiredIds(TmpIntel):
    def test_classify_and_ids(self):
        self.assertTrue(item_intel.is_retired("EASY1"))
        self.assertIn("EASY1", item_intel.retired_ids())
        self.assertFalse(item_intel.is_retired("NOPE"))


class TestBankRetireValve(TmpIntel):
    def test_retired_dropped_when_pool_healthy(self):
        qs = [_q(f"F{i}") for i in range(12)] + [_q("EASY1")]
        out = _bank(qs).unused("SSC")
        ids = {q["id"] for q in out}
        self.assertNotIn("EASY1", ids)              # retired from fresh pool
        self.assertEqual(len(ids), 12)

    def test_valve_keeps_round_full_when_pool_thin(self):
        qs = [_q(f"F{i}") for i in range(5)] + [_q("EASY1")]
        out = _bank(qs).unused("SSC")
        ids = {q["id"] for q in out}
        self.assertIn("EASY1", ids)                 # valve: never go short
        self.assertEqual(len(ids), 6)


class TestHourProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (metrics.METRICS_FILE, metrics._state)
        metrics.METRICS_FILE = self.tmp / "metrics.json"
        metrics._state = {
            "counters": {"answers": 22},
            "hourly": {
                "2026-10-13T08": {"answers": 10, "wa_sent": 3},
                "2026-10-14T08": {"answers": 5},
                "2026-10-14T21": {"answers": 7},
                "2026-10-14T21b": {"answers": 100},   # malformed key skipped
            },
            "started_at": "2026-10-13T00:00:00",
        }

    def tearDown(self):
        metrics.METRICS_FILE, metrics._state = self._orig

    def test_profile_aggregates_by_hour(self):
        prof = metrics.hour_profile()
        self.assertEqual(prof[8], 15)
        self.assertEqual(prof[21], 7)
        snap = metrics.snapshot()
        self.assertEqual(snap["hour_profile"][8], 15)

    def test_advisor_wired(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("conductor-advisor", src)
        self.assertIn("applySmartHour", src)


if __name__ == "__main__":
    unittest.main()
