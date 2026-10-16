#!/usr/bin/env python3
"""Manual Setup v6 tests — Excel + dashboard manual form for timings,
exams and subjects (one unified code path).

Covers /api/setup/options (live exams + subjects), /api/setup/manual_add
(WA group + TG channel, custom exam, times → auto-schedule, custom
subjects, duplicate + invalid rejection). Runs a real dashboard server
on an ephemeral localhost port with all state files in a tmp dir.
Run: python3 -m unittest discover -s tests -p "test_manual_setup.py"
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


class TestManualSetup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dashboard_server as ds
        from core import whatsapp_pipeline as wap, channel_router as cr, config
        cls.ds, cls.wap, cls.cr, cls.config = ds, wap, cr, config
        cls.tmp = Path(tempfile.mkdtemp())
        cls._orig = (wap.WA_CONFIG_FILE, wap.WA_SCHEDULES_FILE, cr.CUSTOM_CHANNELS_FILE)
        cls._auth_orig = ds.AUTH_FILE
        (cls.tmp / "auth.json").write_text(json.dumps(
            {"tokens": ["test-token"], "ip_lock_enabled": False}))
        ds.AUTH_FILE = cls.tmp / "auth.json"
        wap.WA_CONFIG_FILE = cls.tmp / "whatsapp_groups.json"
        wap.WA_SCHEDULES_FILE = cls.tmp / "whatsapp_schedules.json"
        cr.CUSTOM_CHANNELS_FILE = cls.tmp / "custom_channels.json"
        wap.save_wa_registry({"groups": [], "gateway_url": "", "anti_ban": {}})
        cls._keys_before = set(config.CHANNELS.keys())
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ds.DashboardHandler)
        cls.port = cls.server.server_address[1]
        cls.th = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        (cls.wap.WA_CONFIG_FILE, cls.wap.WA_SCHEDULES_FILE,
         cls.cr.CUSTOM_CHANNELS_FILE) = cls._orig
        cls.ds.AUTH_FILE = cls._auth_orig
        for k in set(cls.config.CHANNELS.keys()) - cls._keys_before:
            cls.config.CHANNELS.pop(k, None)
            if k in cls.config.PUBLIC_CHANNELS:
                cls.config.PUBLIC_CHANNELS.remove(k)

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json",
                     "Cookie": "su_auth=test-token"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return json.loads(e.read().decode() or "{}")

    def test_options_are_live(self):
        d = self._call("GET", "/api/setup/options")
        self.assertIn("SSC", d["exams"])
        for s in ("MATHS", "REASONING", "GK", "CURRENT", "ENGLISH", "SCIENCE"):
            self.assertIn(s, d["subjects"])

    def test_manual_add_whatsapp_with_schedule(self):
        d = self._call("POST", "/api/setup/manual_add", {
            "platform": "wa", "name": "Warangal SI Batch 1",
            "link": "120363000000000777@g.us", "exam": "POLICE",
            "shift": "ALL_DAY", "type": "EXAM_SPECIFIC",
            "times": "08:00+20:30", "count": 5, "days": 0,
            "subjects": ["REASONING", "GK", "HISTORY"],   # HISTORY = custom subject
        })
        self.assertTrue(d["ok"], d)
        self.assertEqual(d["added_groups"], 1)
        self.assertEqual(d["schedules_created"], 2)       # 2 times → 2 slots
        job = [j for j in self.wap.load_schedules() if j.get("mode") == "wa"][0]
        self.assertIn("HISTORY", job["subjects"])         # custom subject preserved
        self.assertIn("REASONING", job["subjects"])
        # duplicate → skipped, no extra schedule
        d2 = self._call("POST", "/api/setup/manual_add", {
            "platform": "wa", "name": "Warangal SI Batch 1",
            "link": "120363000000000777@g.us", "exam": "POLICE",
            "times": "08:00", "count": 5, "days": 0, "subjects": []})
        self.assertFalse(d2["ok"])
        wa_jobs = [j for j in self.wap.load_schedules() if j.get("mode") == "wa"]
        self.assertEqual(len(wa_jobs), 2)

    def test_manual_add_telegram_custom_exam(self):
        d = self._call("POST", "/api/setup/manual_add", {
            "platform": "tg", "type": "channel", "name": "TS Police SI 2027 Channel",
            "link": "@tspolicesi2027test", "exam": "TS Police SI 2027",
            "times": "07:00", "count": 5, "days": 30, "subjects": ["GK"]})
        self.assertTrue(d["ok"], d)
        self.assertEqual(d["added_channels"], 1)
        self.assertEqual(d["schedules_created"], 1)
        job = [j for j in self.wap.load_schedules() if j["mode"] == "tg"][0]
        self.assertEqual(job["telegram_channels"], ["TS_POLICE_SI_2027_CHANNEL"])

    def test_manual_add_invalid_rejected(self):
        d = self._call("POST", "/api/setup/manual_add", {
            "platform": "wa", "name": "Bad Group", "link": "not-a-jid",
            "exam": "SSC", "times": "", "count": 5, "days": 0, "subjects": []})
        self.assertFalse(d["ok"])
        self.assertTrue(d["errors"])


if __name__ == "__main__":
    unittest.main()
