#!/usr/bin/env python3
"""Dispatch Safety tests — WhatsApp single-run lock, 60-80s gap floor,
weekday gate, Telegram emoji options.

Owner rules under test (2026-10-15):
  * okka WhatsApp broadcast run avuthunte inkoti vellakudadu — race-proof
    lock, busy aithe honest "busy" (silent drop + fake count kadu;
    scheduler pending-retry code kuda undi)
  * polls madhya 60-80s random gap — 60s floor pipeline lone enforce
  * weekdays select cheste aa days matrame post avvali
  * Telegram channel polls: emoji-letter options (🅰️🅱️🅲🅳) tho
    text-poll style, students tap chesi answer icheyochu

whatsapp_pipeline is imported LAZILY (channel_router pollution rule).
Run: python3 -m unittest discover -s tests -p "test_dispatch_safety.py"
"""
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core.content import build_options  # noqa: E402


def _wp():
    from core import whatsapp_pipeline as wp
    return wp


class TestWeekdayGate(unittest.TestCase):
    def test_js_weekday_convention(self):
        wp = _wp()
        monday = datetime(2026, 10, 12)      # 2026-10-12 = Monday
        sunday = datetime(2026, 10, 18)      # 2026-10-18 = Sunday
        self.assertEqual(wp._js_weekday(monday), 1)
        self.assertEqual(wp._js_weekday(sunday), 0)

    def test_weekday_ok(self):
        wp = _wp()
        monday = datetime(2026, 10, 12)
        self.assertTrue(wp._weekday_ok({}, monday))                    # no gate
        self.assertTrue(wp._weekday_ok({"weekdays": [1, 3]}, monday))
        self.assertFalse(wp._weekday_ok({"weekdays": [0, 6]}, monday))
        self.assertTrue(wp._weekday_ok({"weekdays": [0]}, datetime(2026, 10, 18)))


class TestBroadcastLock(unittest.TestCase):
    """Real worker (dry mode — bridge offline) against 1 fake group."""

    def setUp(self):
        self.wp = _wp()
        # wait for any previous broadcast to drain
        for _ in range(100):
            if not self.wp.EXEC_STATE.get("running"):
                break
            time.sleep(0.1)
        self._orig_reg = self.wp.load_wa_registry
        self.wp.load_wa_registry = lambda: {
            "groups": [{"id": "G1", "jid": "120363000000000001@g.us",
                        "name": "Lock Test Group", "category": "SSC",
                        "group_type": "EXAM_SPECIFIC", "active": True}],
            "gateway_url": "", "anti_ban": {}}
        self._deliver = mock.patch.object(
            self.wp, "deliver_whatsapp_question",
            return_value={"status": "dry", "sent_poll": True, "sent_key": True})
        self._deliver.start()

    def tearDown(self):
        self._deliver.stop()
        self.wp.load_wa_registry = self._orig_reg
        for _ in range(100):
            if not self.wp.EXEC_STATE.get("running"):
                break
            time.sleep(0.1)

    def _wait_idle(self):
        for _ in range(150):
            if not self.wp.EXEC_STATE.get("running"):
                return True
            time.sleep(0.1)
        return False

    def test_busy_is_honest_and_lock_releases(self):
        wp = self.wp
        wp._BROADCAST_LOCK.acquire()
        try:
            res = wp.start_interleaved_broadcast(questions_per_group=1)
            self.assertFalse(res["ok"])
            self.assertTrue(res.get("busy"))          # scheduler retries on this
        finally:
            wp._BROADCAST_LOCK.release()
        res2 = wp.start_interleaved_broadcast(questions_per_group=1)
        self.assertTrue(res2["ok"], res2)
        self.assertTrue(self._wait_idle())
        # lock released by worker -> next broadcast can start
        res3 = wp.start_interleaved_broadcast(questions_per_group=1)
        self.assertTrue(res3["ok"], res3)
        self.assertTrue(self._wait_idle())

    def test_gap_floor_60_80(self):
        res = self.wp.start_interleaved_broadcast(
            questions_per_group=1, delay_min=20, delay_max=35)
        self.assertTrue(res["ok"], res)
        self.assertTrue(self._wait_idle())
        logs = "\n".join(self.wp.EXEC_STATE.get("logs", []))
        # pushed-up range is what the worker actually used
        self.assertIn("Anti-Ban Timing: 60-60s", logs)

    def test_no_groups_releases_lock(self):
        self.wp.load_wa_registry = lambda: {"groups": [], "gateway_url": ""}
        res = self.wp.start_interleaved_broadcast(questions_per_group=1)
        self.assertFalse(res["ok"])
        self.assertFalse(self.wp._BROADCAST_LOCK.locked())


class TestSchedulerWiring(unittest.TestCase):
    def test_scheduler_uses_60_80_and_pending_retry(self):
        src = (ROOT / "scripts" / "core" / "whatsapp_pipeline.py").read_text()
        self.assertIn("delay_min=60", src)
        self.assertIn("delay_max=80", src)
        self.assertIn("_PENDING_WA", src)
        self.assertIn("_weekday_ok(j)", src)
        # busy bookkeeping must NOT count fake dispatches
        self.assertIn('res.get("busy")', src)


class TestEmojiOptions(unittest.TestCase):
    def test_emoji_letters(self):
        q = {"q_en": "Capital of India?", "q_te": "భారత రాజధాని?",
             "options_en": ["Delhi", "Mumbai", "Chennai", "Kolkata"],
             "options_te": ["ఢిల్లీ", "ముంబై", "చెన్నై", "కోలకాతా"],
             "answer_index": 0}
        opts = build_options(q, telugu_first=True)
        self.assertEqual(len(opts), 4)
        for i, e in enumerate(["🅰️", "🅱️", "🅲", "🅳"]):
            self.assertTrue(opts[i].startswith(e), opts[i])
            self.assertLessEqual(len(opts[i]), 100)
        self.assertIn("Delhi", opts[0])               # bilingual merge intact


if __name__ == "__main__":
    unittest.main()
