#!/usr/bin/env python3
"""Easy Setup Wizard tests — dashboard one-flow setup.

Real dashboard server on an ephemeral port: /api/whatsapp/bridges,
/api/whatsapp/retry_queue, and the wizard tab wiring in the HTML.
Run: python3 -m unittest discover -s tests -p "test_setup_wizard.py"
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


class TestSetupWizard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dashboard_server as ds
        from core import whatsapp_pipeline as wap
        cls.ds = ds
        cls.tmp = Path(tempfile.mkdtemp())
        cls._auth_orig = ds.AUTH_FILE
        (cls.tmp / "auth.json").write_text(json.dumps(
            {"tokens": ["test-token"], "ip_lock_enabled": False}))
        ds.AUTH_FILE = cls.tmp / "auth.json"
        cls._retry_orig = wap.WA_RETRY_FILE
        wap.WA_RETRY_FILE = cls.tmp / "retry.json"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ds.DashboardHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.ds.AUTH_FILE = cls._auth_orig
        from core import whatsapp_pipeline as wap
        wap.WA_RETRY_FILE = cls._retry_orig

    def _get(self, path):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            headers={"Cookie": "su_auth=test-token"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode(), r.headers.get_content_type()

    def test_bridges_endpoint(self):
        body, _ = self._get("/api/whatsapp/bridges")
        d = json.loads(body)
        self.assertEqual(d["pool_size"], 1)
        self.assertEqual(len(d["bridges"]), 1)
        self.assertIn("connected", d["bridges"][0])

    def test_retry_queue_endpoint(self):
        body, _ = self._get("/api/whatsapp/retry_queue")
        d = json.loads(body)
        self.assertEqual(d["count"], 0)
        self.assertEqual(d["items"], [])

    def test_wizard_tab_in_html(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("tab-setup-wizard", src)
        self.assertIn("loadSetupWizard", src)
        self.assertIn("Easy Setup Wizard", src)
        self.assertIn("id === 'tab-setup-wizard'", src)
        for api in ("/api/health", "/api/whatsapp/bridges", "/api/vision",
                    "/api/whatsapp/retry_queue"):
            self.assertIn(api, src)


if __name__ == "__main__":
    unittest.main()
