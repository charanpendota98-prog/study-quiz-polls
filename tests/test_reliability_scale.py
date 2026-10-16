#!/usr/bin/env python3
"""Reliability + Scale tests — retry queue, per-job answer delay,
multi-number bridge pool (sticky routing, session naming).

Run: python3 -m unittest discover -s tests -p "test_reliability_scale.py"
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

Q = {"id": "q9", "q_en": "Q?", "q_te": "", "options_en": ["a", "b"],
     "options_te": [], "answer_index": 0}


class TestRetryQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core import whatsapp_pipeline as wap
        cls.wap = wap

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = self.wap.WA_RETRY_FILE
        self.wap.WA_RETRY_FILE = self.tmp / "retry.json"

    def tearDown(self):
        self.wap.WA_RETRY_FILE = self._orig

    def test_enqueue_due_process_and_drop(self):
        wap = self.wap
        wap.enqueue_retry("111@g.us", Q, "SSC")
        from core.store import load_json
        items = load_json(wap.WA_RETRY_FILE, {})["items"]
        self.assertEqual(len(items), 1)
        items[0]["next_at"] = time.time() - 1     # make it due
        from core.store import save_json_atomic
        save_json_atomic(wap.WA_RETRY_FILE, {"items": items})

        ok = {"sent_poll": True, "sent_key": True, "status": "ok"}
        with mock.patch.object(wap, "deliver_whatsapp_question", return_value=ok) as dv:
            res = wap.process_retry_queue()
        self.assertEqual(res["sent"], 1)
        self.assertEqual(load_json(wap.WA_RETRY_FILE, {})["items"], [])

        # failing delivery: attempts grow, dropped after 3rd
        wap.enqueue_retry("111@g.us", Q, "SSC")
        items = load_json(wap.WA_RETRY_FILE, {})["items"]
        items[0]["next_at"] = 0
        items[0]["attempts"] = 2
        save_json_atomic(wap.WA_RETRY_FILE, {"items": items})
        bad = {"sent_poll": False, "sent_key": False, "status": "no"}
        with mock.patch.object(wap, "deliver_whatsapp_question", return_value=bad):
            res = wap.process_retry_queue(now=time.time())
        self.assertEqual(res["dropped"], 1)
        self.assertEqual(load_json(wap.WA_RETRY_FILE, {})["items"], [])


class TestBridgePool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core import whatsapp_pipeline as wap
        cls.wap = wap

    def test_default_single_bridge(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WA_BRIDGE_URLS", None)
            self.assertEqual(self.wap._bridge_urls(), [self.wap.WA_BRIDGE_URL])

    def test_pool_parsing_and_sticky_routing(self):
        with mock.patch.dict(os.environ, {
                "WA_BRIDGE_URLS": "http://127.0.0.1:3900, http://127.0.0.1:3901/"}):
            urls = self.wap._bridge_urls()
            self.assertEqual(urls, ["http://127.0.0.1:3900", "http://127.0.0.1:3901"])
            self.assertEqual(self.wap.bridge_for_group({"bridge": 1}), urls[1])
            self.assertEqual(self.wap.bridge_for_group({}), urls[0])
            self.assertEqual(self.wap.bridge_for_group({"bridge": 9}), urls[0])

    def test_bridges_status(self):
        def fake(path, payload=None, method=None, timeout=40, base_url=None):
            if base_url and base_url.endswith("3901"):
                return {"connected": True, "phone": "91xx", "session": "sim2",
                        "groups_count": 40}
            return None
        with mock.patch.object(self.wap, "_bridge_call", fake), \
                mock.patch.dict(os.environ, {
                    "WA_BRIDGE_URLS": "http://127.0.0.1:3900,http://127.0.0.1:3901"}):
            st = self.wap.bridges_status()
        self.assertFalse(st[0]["online"])
        self.assertTrue(st[1]["connected"])
        self.assertEqual(st[1]["session"], "sim2")

    def test_scheduler_uses_job_answer_delay(self):
        src = (ROOT / "scripts" / "core" / "whatsapp_pipeline.py").read_text()
        self.assertIn('answer_delay_minutes', src)
        self.assertIn("worker", src.lower())


class TestBridgeNodeSource(unittest.TestCase):
    def test_session_naming(self):
        src = (ROOT / "gateway" / "wa_bridge.js").read_text()
        self.assertIn("WA_SESSION_NAME", src)
        self.assertIn("auth-${SESSION_NAME}", src)
        self.assertIn("session: SESSION_NAME", src)

    def test_node_syntax(self):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node not available")
        r = subprocess.run(["node", "--check", str(ROOT / "gateway" / "wa_bridge.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
