#!/usr/bin/env python3
"""Pro Ops tests — metrics, feature flags, audit log, deep health, API.

Company-level guarantees under test: metrics count only real events,
flags fail-open to code defaults and flip real behaviour (verifier
quarantine, retry queue), audit trail is append-only + newest-first,
deep health never hides a broken subsystem.
Run: python3 -m unittest discover -s tests -p "test_pro_ops.py"
"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import auditlog, flags, health, item_intel, metrics, verifier  # noqa: E402

# NOTE: whatsapp_pipeline is imported LAZILY (inside setUp) — it pulls in
# channel_router, whose import-time mount injects custom channels into
# config.PUBLIC_CHANNELS and would pollute other test modules (same
# convention as test_bulk_setup / test_reliability_scale).


class TmpState(unittest.TestCase):
    """Point every Pro-Ops store at a temp dir for the test."""

    def setUp(self):
        from core import whatsapp_pipeline as wp
        self.wp = wp
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (metrics.METRICS_FILE, flags.FLAGS_FILE,
                      auditlog.AUDIT_FILE, wp.WA_RETRY_FILE,
                      item_intel.STATS_FILE)
        metrics.METRICS_FILE = self.tmp / "metrics.json"
        metrics._state = None
        flags.FLAGS_FILE = self.tmp / "feature_flags.json"
        auditlog.AUDIT_FILE = self.tmp / "audit_log.jsonl"
        wp.WA_RETRY_FILE = self.tmp / "wa_retry_queue.json"
        item_intel.STATS_FILE = self.tmp / "item_stats.json"
        item_intel._cache["mtime"] = None
        item_intel._cache["data"] = {}

    def tearDown(self):
        (metrics.METRICS_FILE, flags.FLAGS_FILE, auditlog.AUDIT_FILE,
         self.wp.WA_RETRY_FILE, item_intel.STATS_FILE) = self._orig
        metrics._state = None
        item_intel._cache["mtime"] = None


class TestMetrics(TmpState):
    def test_counts_and_persistence(self):
        metrics.incr("answers", 3)
        metrics.incr("answers_correct", 2)
        metrics.incr("wa_sent", 4)
        metrics.incr("wa_failed", 1)
        metrics.flush()
        snap = metrics.snapshot()
        self.assertEqual(snap["counters"]["answers"], 3)
        self.assertEqual(snap["today"]["answers"], 3)
        self.assertEqual(snap["delivery"]["success_pct"], 80.0)
        self.assertEqual(len(snap["hourly_series"]["answers"]["values"]), 24)
        # reload from disk
        metrics._state = None
        self.assertEqual(metrics.snapshot()["counters"]["wa_sent"], 4)

    def test_empty_delivery_is_none_not_fake(self):
        snap = metrics.snapshot()
        self.assertIsNone(snap["delivery"]["success_pct"])


class TestFlags(TmpState):
    def test_defaults_and_override(self):
        self.assertTrue(flags.enabled("item_intel_quarantine"))
        self.assertTrue(flags.enabled("unknown_flag"))     # fail-open
        self.assertFalse(flags.set_flag("unknown_flag", True))
        self.assertTrue(flags.set_flag("pyq_floor", False))
        self.assertFalse(flags.enabled("pyq_floor"))
        row = [f for f in flags.all_flags() if f["name"] == "pyq_floor"][0]
        self.assertTrue(row["overridden"])
        self.assertEqual(len(flags.all_flags()), 20)  # +1 (90X): blueprint_mocks

    def test_flag_flips_verifier_quarantine(self):
        # BADQ: 20 answers, 1 correct -> suspect wrong key (quarantined)
        for i in range(20):
            item_intel.record("BADQ", i == 0, topic="polity", channel="SSC")
        q = {"id": "BADQ", "source": "pyq"}
        self.assertFalse(verifier.postable(q))             # flag ON (default)
        flags.set_flag("item_intel_quarantine", False)
        self.assertTrue(verifier.postable(q))              # kill-switch works

    def test_flag_flips_retry_queue(self):
        q = {"id": "Q1", "q_en": "x"}
        flags.set_flag("wa_retry_queue", False)
        self.wp.enqueue_retry("jid1", q, "SSC")
        self.assertFalse(self.wp.WA_RETRY_FILE.exists())   # nothing enqueued
        flags.set_flag("wa_retry_queue", True)
        self.wp.enqueue_retry("jid1", q, "SSC")
        d = json.loads(self.wp.WA_RETRY_FILE.read_text())
        self.assertEqual(len(d["items"]), 1)
        self.assertEqual(metrics.snapshot()["counters"].get("wa_retry_enqueued"), 1)


class TestAudit(TmpState):
    def test_append_and_recent(self):
        auditlog.log("flag.toggle", "pyq_floor -> False")
        auditlog.log("pulse.settings", "price=249")
        with open(auditlog.AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write("corrupt line\n")
        auditlog.log("item_intel.reset", "qid=BADQ")
        entries = auditlog.recent(10)
        self.assertEqual(len(entries), 3)                  # corrupt skipped
        self.assertEqual(entries[0]["action"], "item_intel.reset")  # newest first


class TestHealth(unittest.TestCase):
    def test_report_shape(self):
        rep = health.full_report()
        self.assertIn(rep["overall"], ("ok", "warn", "fail"))
        self.assertGreaterEqual(len(rep["checks"]), 10)
        for c in rep["checks"]:
            self.assertIn(c["status"], ("ok", "warn", "fail"))
            self.assertTrue(c["name"])


class TestProOpsApi(TmpState):
    @classmethod
    def setUpClass(cls):
        import dashboard_server as ds
        cls.ds = ds

    def setUp(self):
        super().setUp()
        self._auth_orig = self.ds.AUTH_FILE
        (self.tmp / "auth.json").write_text(json.dumps(
            {"tokens": ["test-token"], "ip_lock_enabled": False}))
        self.ds.AUTH_FILE = self.tmp / "auth.json"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                          self.ds.DashboardHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.ds.AUTH_FILE = self._auth_orig
        super().tearDown()

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json",
                     "Cookie": "su_auth=test-token"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())

    def test_endpoints(self):
        m = self._call("GET", "/api/metrics")
        self.assertIn("delivery", m)
        h = self._call("GET", "/api/health/full")
        self.assertIn("checks", h)
        self.assertIn("uptime_min", h)
        f = self._call("GET", "/api/flags")
        self.assertEqual(len(f["flags"]), 20)  # advanced flags
        r = self._call("POST", "/api/flags",
                       {"name": "pyq_floor", "enabled": False})
        self.assertTrue(r["ok"])
        self.assertFalse(flags.enabled("pyq_floor"))
        a = self._call("GET", "/api/audit")
        self.assertTrue(any(e["action"] == "flag.toggle" for e in a["entries"]))

    def test_tab_wired(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("tab-proops", src)
        self.assertIn("loadProOps", src)


if __name__ == "__main__":
    unittest.main()
