# -*- coding: utf-8 -*-
"""WhatsApp FULL SAFETY STACK: quiet hours (start + mid-send), duplicate
blast guard 45m, preflight 9-checks, spam/warm-up caps, on-time scheduler
catch-up, anti-fingerprint language alternation."""
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

def _wp():
    # lazy import (vere WA tests laga) — top-level import chesthe discovery
    # load lone channel_router mount ayyi config pollute avthundi
    from core import whatsapp_pipeline as wp
    return wp


wp = None  # setUp lo set avthundi


class TestSafetyStack(unittest.TestCase):
    def setUp(self):
        global wp
        wp = _wp()
        self._guard = wp.BLAST_GUARD_FILE
        wp.BLAST_GUARD_FILE = Path(tempfile.mkdtemp()) / "guard.json"
        self._exec = dict(wp.EXEC_STATE)
        wp.EXEC_STATE["running"] = False
        wp.EXEC_STATE["stop_requested"] = False

    def tearDown(self):
        wp.BLAST_GUARD_FILE = self._guard
        wp.EXEC_STATE.update(self._exec)

    # ---- 🌙 quiet hours ----
    def test_quiet_hours_window(self):
        def at(h):
            return wp.in_wa_quiet(datetime(2026, 10, 16, h, 30), start=22, end=7)
        self.assertTrue(at(23))
        self.assertTrue(at(22))
        self.assertTrue(at(6))
        self.assertTrue(at(0))
        self.assertFalse(at(7))
        self.assertFalse(at(12))
        self.assertFalse(at(21))

    def test_quiet_until(self):
        u = wp.wa_quiet_until(datetime(2026, 10, 16, 23, 30))
        self.assertEqual((u.day, u.hour), (17, 7))
        u = wp.wa_quiet_until(datetime(2026, 10, 16, 3, 0))
        self.assertEqual((u.day, u.hour), (16, 7))

    # ---- 🔀 language alternation (anti-fingerprint) ----
    def test_language_alternation(self):
        d = datetime(2026, 10, 16).toordinal()
        base = [wp.wa_english_first(g, 0, d) for g in range(4)]
        self.assertEqual(base, [True, False, True, False] if (d % 2 == 0) else [False, True, False, True])
        self.assertNotEqual(wp.wa_english_first(0, 0, d), wp.wa_english_first(1, 0, d))  # next group flips
        self.assertNotEqual(wp.wa_english_first(0, 0, d), wp.wa_english_first(0, 1, d))  # next question flips
        self.assertNotEqual(wp.wa_english_first(0, 0, d), wp.wa_english_first(0, 0, d + 1))  # next day flips

    # ---- 🛡️ duplicate blast guard ----
    def test_blast_guard(self):
        t = time.time()
        self.assertFalse(wp.blast_pair_recent("123@g.us", "Q1", now_ts=t))
        wp.blast_record("123@g.us", "Q1", now_ts=t)
        self.assertTrue(wp.blast_pair_recent("123@g.us", "Q1", now_ts=t + 600))
        self.assertFalse(wp.blast_pair_recent("123@g.us", "Q1", now_ts=t + 46 * 60))
        sig = wp.blast_signature(["b@g.us", "a@g.us"], "ALL", 5)
        self.assertEqual(sig, wp.blast_signature(["a@g.us", "b@g.us"], "ALL", 5))
        self.assertFalse(wp.blast_recent(sig, now_ts=t))
        wp.blast_record_blast(sig, ["a@g.us"], now_ts=t)
        self.assertTrue(wp.blast_recent(sig, now_ts=t + 60))
        # spam guard: warm-up cap for brand-new group, sent-today counting
        cap, warm = wp.wa_group_daily_cap("a@g.us", now_ts=t)
        self.assertEqual((cap, warm), (wp.WA_WARMUP_CAP, True))
        wp.blast_record("a@g.us", "Q9", now_ts=t)
        self.assertEqual(wp.wa_sent_today("a@g.us", now_ts=t), 1)

    # ---- ⏰ on-time scheduler ----
    def test_slot_due(self):
        today = "2026-10-16"
        self.assertTrue(wp._slot_due("10:00", today, datetime(2026, 10, 16, 10, 0), ""))
        self.assertTrue(wp._slot_due("10:00", today, datetime(2026, 10, 16, 10, 20), ""))   # catch-up
        self.assertFalse(wp._slot_due("10:00", today, datetime(2026, 10, 16, 10, 31), ""))  # too late
        self.assertFalse(wp._slot_due("10:00", today, datetime(2026, 10, 16, 9, 59), ""))   # early
        self.assertFalse(wp._slot_due("10:00", today, datetime(2026, 10, 16, 10, 5),
                                      "2026-10-16 10:00"))                                   # already fired
        self.assertFalse(wp._slot_due("bad", today, datetime(2026, 10, 16, 10, 5), ""))

    # ---- 🔍 preflight ----
    def _pf(self, bridge, quiet=False):
        groups = [{"jid": "111@g.us", "name": "G1", "category": "SSC", "active": True}]
        with mock.patch.object(wp, "_bridge_call", return_value=bridge), \
             mock.patch.object(wp, "in_wa_quiet", return_value=quiet), \
             mock.patch.object(wp, "pacing_gate",
                               return_value={"allowed": True, "mode": "HEALTHY", "multiplier": 1.0}):
            return wp.preflight_whatsapp(groups=groups, category="ALL", questions_per_group=5)

    def test_preflight_dry_ok(self):
        pf = self._pf(None)
        self.assertEqual(len(pf["checks"]), 9)
        self.assertTrue(pf["ok"], pf["blockers"])
        bridge_checks = [c for c in pf["checks"] if c["name"] in ("Bridge reachable", "WhatsApp session")]
        self.assertTrue(all(not c["block"] for c in bridge_checks))   # dry-run never blocked

    def test_preflight_quiet_blocks_real(self):
        pf = self._pf({"connected": True}, quiet=True)
        self.assertFalse(pf["ok"])
        self.assertIn("Quiet hours (22:00–07:00)", pf["blockers"])

    def test_preflight_duplicate_blocks_real(self):
        groups = [{"jid": "111@g.us", "name": "G1", "category": "SSC", "active": True}]
        sig = wp.blast_signature(["111@g.us"], "ALL", 5)
        wp.blast_record_blast(sig, ["111@g.us"])
        pf = self._pf({"connected": True})
        self.assertFalse(pf["ok"])
        self.assertIn("Duplicate Blast Guard (45m)", pf["blockers"])

    def test_safety_stack_and_wiring(self):
        stack = wp.safety_stack()
        self.assertEqual(len(stack["layers"]), 7)
        self.assertIn("pacing", stack)
        src = (Path(__file__).resolve().parents[1]
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/whatsapp/safety"', '"/api/whatsapp/preflight"',
                       "loadSafetyStack", "emergencyStopWA", 'id="wa-safety-stack"',
                       "whatsapp_pipeline.safety_stack()", "whatsapp_pipeline.preflight_whatsapp"):
            self.assertIn(needle, src)
        psrc = Path(wp.__file__).read_text(encoding="utf-8")
        for needle in ("🌙 Quiet hours (22:00–07:00) vachayi", "mid-send graceful stop",
                       "quiet_until", "_slot_due(job_time", "wa_english_first(grp_idx, q_idx)"):
            self.assertIn(needle, psrc)


if __name__ == "__main__":
    unittest.main()
