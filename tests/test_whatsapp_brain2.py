#!/usr/bin/env python3
"""🧠 Anti-Ban Brain 2.0 — scheduler CRAWL gate + brain-aware retries.

CRAWL lo scheduler WA legs start avvavu (pending defer, fake count
kadu), retry attempts burn avvavu (crawl end ki defer), failure backoff
risk multiplier tho peruguthundi. Telegram 429 handling already smart
(retry_after honoured) — textual guard. Lazy wp import (pollution rule).
Run: python3 -m unittest discover -s tests -p "test_whatsapp_brain2.py"
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _wp():
    from core import whatsapp_pipeline as wp
    return wp


class TestGate(unittest.TestCase):
    def setUp(self):
        self.wp = _wp()
        self.wp.reset_pacing_state()

    def tearDown(self):
        self.wp.reset_pacing_state()

    def test_gate_blocks_only_in_crawl(self):
        wp = self.wp
        wp.pacing_begin_broadcast(now=1000.0)
        self.assertTrue(wp.pacing_gate(now=1000.0)["allowed"])
        wp.pacing_note_result(False, "bridge timeout", now=1000.0)
        self.assertTrue(wp.pacing_gate(now=1000.0)["allowed"])   # CAUTIOUS ok
        wp.pacing_note_result(False, "403 forbidden: blocked", now=1000.0)
        gate = wp.pacing_gate(now=1000.0)
        self.assertFalse(gate["allowed"])                        # CRAWL blocks
        self.assertEqual(gate["wait_seconds"], 1800.0)
        self.assertTrue(wp.pacing_gate(now=2900.0)["allowed"])   # window done


class TestRetryBrain(unittest.TestCase):
    def setUp(self):
        self.wp = _wp()
        self.wp.reset_pacing_state()
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = self.wp.WA_RETRY_FILE
        self.wp.WA_RETRY_FILE = self.tmp / "wa_retry_queue.json"
        q = {"id": "RQ1", "channel": "SSC", "topic": "Polity",
             "q_en": "Capital?", "q_te": "", "options_en": ["A", "B"],
             "options_te": [], "answer_index": 0}
        self.wp.WA_RETRY_FILE.write_text(json.dumps({"items": [{
            "jid": "120@g.us", "q": q, "category": "SSC",
            "english_first": True, "attempts": 0,
            "next_at": 900.0, "created": "now"}]}))

    def tearDown(self):
        self.wp.WA_RETRY_FILE = self._orig
        self.wp.reset_pacing_state()

    def test_crawl_defers_without_burning_attempts(self):
        wp = self.wp
        wp.pacing_begin_broadcast(now=1000.0)
        wp.pacing_note_result(False, "spam restricted 403", now=1000.0)
        out = wp.process_retry_queue(now=1000.0)
        self.assertEqual(out["tried"], 0)
        self.assertEqual(out["deferred"], 1)
        items = json.loads(wp.WA_RETRY_FILE.read_text())["items"]
        self.assertEqual(items[0]["attempts"], 0)                # not burned
        self.assertGreater(items[0]["next_at"], 2800.0)           # past crawl

    def test_failure_backoff_scales_with_risk(self):
        wp = self.wp
        wp.pacing_begin_broadcast(now=1000.0)
        wp.pacing_note_result(False, "bridge timeout", now=1000.0)   # x1.45
        orig = wp.deliver_whatsapp_question
        wp.deliver_whatsapp_question = lambda *a, **k: {
            "sent_poll": False, "sent_key": False, "status": "bridge timeout"}
        try:
            out = wp.process_retry_queue(now=1000.0)
        finally:
            wp.deliver_whatsapp_question = orig
        self.assertEqual(out["tried"], 1)
        items = json.loads(wp.WA_RETRY_FILE.read_text())["items"]
        # 300 * attempts(1) * multiplier(>=1.45 after another fail note)
        self.assertGreaterEqual(items[0]["next_at"], 1000.0 + 300 * 1.8)


class TestWiring(unittest.TestCase):
    def test_scheduler_gate_and_telegram_429(self):
        src = (ROOT / "scripts" / "core" / "whatsapp_pipeline.py").read_text()
        self.assertIn('pacing_gate() if jmode in ("wa", "both")', src)
        self.assertIn('"crawl_until": _gate.get("crawl_until")', src)
        tg = (ROOT / "scripts" / "core" / "telegram.py").read_text()
        self.assertIn("retry_after", tg)          # TG already honours 429s


if __name__ == "__main__":
    unittest.main()
