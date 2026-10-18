#!/usr/bin/env python3
"""🧠 Adaptive Anti-Ban Brain — risk-aware WhatsApp pacing.

Owner floor is sacred: base gaps never shrink. Failures expand the
multiplier (+0.45, max x2.5), a ban/block signal triggers a 30-minute
CRAWL (x3.0), successes relax gradually, long broadcasts gain fatigue,
media sends get a small extra pause, and rare human interruptions can
occur. whatsapp_pipeline is imported lazily (scheduler side effects).
Run: python3 -m unittest discover -s tests -p "test_whatsapp_pacing.py"
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _wp():
    from core import whatsapp_pipeline as wp
    return wp


class FakeRng:
    def __init__(self, random_value=0.99, uniforms=None):
        self.random_value = random_value
        self.uniforms = list(uniforms or [])

    def random(self):
        return self.random_value

    def uniform(self, a, b):
        return self.uniforms.pop(0) if self.uniforms else a


class TestAdaptivePacing(unittest.TestCase):
    def setUp(self):
        self.wp = _wp()
        self.wp.reset_pacing_state()

    def tearDown(self):
        self.wp.reset_pacing_state()

    def test_failures_expand_and_success_relaxes(self):
        wp = self.wp
        wp.pacing_begin_broadcast(now=1000.0)
        snap = None
        for _ in range(3):
            snap = wp.pacing_note_result(False, "bridge timeout", now=1000.0)
        self.assertEqual(snap["risk_multiplier"], 2.35)     # 1 + 3*0.45
        self.assertEqual(snap["mode"], "CAUTIOUS")
        self.assertEqual(snap["consecutive_fails"], 3)
        plan = wp.pacing_plan(70, now=1000.0, rng=FakeRng())
        self.assertAlmostEqual(plan["sleep_seconds"], 164.5)
        snap = wp.pacing_note_result(True, "ok", now=1000.0)
        self.assertEqual(snap["risk_multiplier"], 2.20)     # relax -0.15
        self.assertEqual(snap["consecutive_fails"], 0)

    def test_ban_signal_crawls_for_30_minutes(self):
        wp = self.wp
        wp.pacing_begin_broadcast(now=1000.0)
        snap = wp.pacing_note_result(False, "403 forbidden: account blocked", now=1000.0)
        self.assertEqual(snap["risk_multiplier"], 3.0)
        self.assertEqual(snap["mode"], "CRAWL")
        self.assertEqual(snap["crawl_until"], 2800.0)
        # success during crawl does not speed anything up
        snap = wp.pacing_note_result(True, "ok", now=1500.0)
        self.assertEqual(snap["risk_multiplier"], 3.0)
        self.assertEqual(snap["mode"], "CRAWL")
        # after the window, success starts relaxing from cautious ceiling
        snap = wp.pacing_note_result(True, "ok", now=2801.0)
        self.assertLessEqual(snap["risk_multiplier"], 2.35)
        self.assertNotEqual(snap["mode"], "CRAWL")

    def test_never_speeds_below_base_gap(self):
        wp = self.wp
        wp.pacing_begin_broadcast(now=500.0)
        for _ in range(10):
            wp.pacing_note_result(True, "ok", now=500.0)
        plan = wp.pacing_plan(60, now=500.0, rng=FakeRng())
        self.assertEqual(plan["sleep_seconds"], 60.0)       # 60s floor intact

    def test_fatigue_grows_and_caps(self):
        wp = self.wp
        wp.pacing_begin_broadcast(now=0.0)
        snap = wp.pacing_snapshot(now=2 * 3600.0)
        self.assertEqual(snap["fatigue"], 1.24)             # +12%/hour
        snap = wp.pacing_snapshot(now=8 * 3600.0)
        self.assertEqual(snap["fatigue"], 1.35)             # capped +35%

    def test_media_extra_and_phone_call_pause(self):
        wp = self.wp
        wp.pacing_begin_broadcast(now=100.0)
        media = wp.pacing_plan(0, media=True, now=100.0,
                               rng=FakeRng(uniforms=[3.0]))
        self.assertEqual(media["media_extra_seconds"], 3.0)
        self.assertEqual(media["sleep_seconds"], 3.0)
        pause = wp.pacing_plan(70, now=100.0,
                               rng=FakeRng(random_value=0.01, uniforms=[180.0]))
        self.assertEqual(pause["interruption_seconds"], 180.0)
        self.assertEqual(pause["sleep_seconds"], 250.0)

    def test_pacing_sleep_dry_cap(self):
        wp = self.wp
        wp.pacing_begin_broadcast(now=100.0)
        slept = []
        plan = wp.pacing_sleep(70, real_mode=False, sleep_fn=slept.append,
                               rng=FakeRng(), now=100.0)
        self.assertEqual(plan["planned_seconds"], 70.0)
        self.assertEqual(slept, [2.0])                      # tests stay fast

    def test_status_and_dashboard_observability(self):
        wp = self.wp
        status = wp.get_broadcast_status()
        self.assertIn("pacing", status)
        self.assertIn("multiplier", status["pacing"])
        self.assertIn("fatigue", status["pacing"])
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("pipeline-pacing-text", dash)
        self.assertIn("d.pacing", dash)
        src = (ROOT / "scripts" / "core" / "whatsapp_pipeline.py").read_text()
        self.assertIn("media_sleep_fn=lambda: _anti_ban_sleep(0, media=True)", src)
        self.assertIn("pacing_note_result(_send_ok, res)", src)


if __name__ == "__main__":
    unittest.main()
