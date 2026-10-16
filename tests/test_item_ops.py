#!/usr/bin/env python3
"""Item Ops + Paper Factory tests — harvest backoff & dashboard item ops.

Run: python3 -m unittest discover -s tests -p "test_item_ops.py"
"""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import item_intel, pyq  # noqa: E402


class TestHarvestBackoff(unittest.TestCase):
    def test_eligibility_rules(self):
        now = time.time()
        self.assertFalse(pyq._eligible({"status": "done"}, now))
        self.assertFalse(pyq._eligible({"status": "dead"}, now))
        self.assertFalse(pyq._eligible(
            {"status": "error", "attempts": 2, "next_try_ts": now + 1000}, now))
        self.assertTrue(pyq._eligible(
            {"status": "error", "attempts": 2, "next_try_ts": now - 5}, now))
        self.assertFalse(pyq._eligible({"status": "error", "attempts": 5}, now))

    def test_dead_after_max_attempts(self):
        self.assertGreaterEqual(pyq._MAX_ATTEMPTS, 3)


class TestItemOpsApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dashboard_server as ds
        cls.ds = ds
        cls.tmp = Path(tempfile.mkdtemp())
        cls._auth_orig = ds.AUTH_FILE
        (cls.tmp / "auth.json").write_text(json.dumps(
            {"tokens": ["test-token"], "ip_lock_enabled": False}))
        ds.AUTH_FILE = cls.tmp / "auth.json"
        cls._stats_orig = item_intel.STATS_FILE
        item_intel.STATS_FILE = cls.tmp / "item_stats.json"
        item_intel._cache["mtime"] = None
        item_intel._cache["data"] = {}
        # seed a suspect question
        for i in range(20):
            item_intel.record("BADQ", i == 0, topic="polity", channel="SSC")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ds.DashboardHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.ds.AUTH_FILE = cls._auth_orig
        item_intel.STATS_FILE = cls._stats_orig
        item_intel._cache["mtime"] = None

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json",
                     "Cookie": "su_auth=test-token"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())

    def test_report_and_reset(self):
        d = self._call("GET", "/api/item_intel")
        self.assertTrue(d["ok"])
        self.assertEqual(d["suspect_count"], 1)
        self.assertEqual(d["suspect_key"][0]["qid"], "BADQ")
        r = self._call("POST", "/api/item_intel/reset", {"qid": "BADQ"})
        self.assertTrue(r["ok"])
        d2 = self._call("GET", "/api/item_intel")
        self.assertEqual(d2["suspect_count"], 0)

    def test_card_wired(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("item-intel-body", src)
        self.assertIn("loadItemIntel", src)


if __name__ == "__main__":
    unittest.main()
