#!/usr/bin/env python3
"""Business Pulse tests — growth funnel, referral engine, planner, API.

Numbers must come from the real member/partner stores; the planner is a
labelled what-if (real base × admin assumptions), never fake revenue.
Run: python3 -m unittest discover -s tests -p "test_pulse.py"
"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import pulse, vision  # noqa: E402
from core import config  # noqa: E402


def _members(now=None):
    today = (now or datetime.now(config.IST)).strftime("%Y-%m-%d")
    return {
        "1": {"registered": True, "name": "Top Referrer", "district": "Warangal",
              "points": 500, "total": 40, "last_active": today,
              "referrals": 12, "ref_activated": 5},
        "2": {"registered": True, "name": "Referred Active",
              "points": 120, "total": 10, "last_active": today,
              "referred_by": "1"},
        "3": {"registered": True, "name": "Referred Dormant",
              "points": 25, "total": 0, "referred_by": "1"},
        "4": {"registered": True, "name": "Organic Dormant",
              "points": 25, "total": 0},
        "5": {"registered": False, "points": 0, "total": 9},
    }


class TestPulseMath(unittest.TestCase):
    def test_funnel_and_referrals(self):
        f = pulse.funnel_from(_members())
        self.assertEqual(f["registered"], 4)          # unregistered excluded
        self.assertEqual(f["activated"], 2)           # total > 0
        self.assertEqual(f["activation_pct"], 50.0)
        self.assertEqual(f["referred_members"], 2)
        self.assertEqual(f["referred_activated"], 1)  # only #2 answered
        self.assertEqual(f["total_referrals"], 12)
        self.assertEqual(f["referrers"], 1)
        top = f["top_referrers"][0]
        self.assertEqual(top["name"], "Top Referrer")
        self.assertEqual(top["tier"], "🥈 Recruiter")  # 12 ≥ 10

    def test_planner_is_labelled_projection(self):
        f = pulse.funnel_from(_members())
        p = pulse.planner(f, {"price_inr": 100, "conversion_pct": 10,
                              "plan_name": "Pro"})
        self.assertEqual(p["base_members"], 2)         # active 7d base
        self.assertEqual(p["paying_est"], 0)           # 10% of 2 rounds to 0
        p2 = pulse.planner({**f, "active_7d": 200},
                           {"price_inr": 100, "conversion_pct": 10,
                            "plan_name": "Pro"})
        self.assertEqual(p2["paying_est"], 20)
        self.assertEqual(p2["mrr_inr"], 2000)
        self.assertEqual(p2["arr_inr"], 24000)

    def test_empty_never_raises(self):
        f = pulse.funnel_from({})
        self.assertEqual(f["registered"], 0)
        self.assertEqual(pulse.growth_score(f), 0)
        e = pulse.economy_from({}, {})
        self.assertEqual(e["partners"], 0)

    def test_settings_roundtrip_tmp(self):
        with tempfile.TemporaryDirectory() as td:
            s = pulse.save_settings(price_inr=199, conversion_pct=7.5,
                                    plan_name="Pro X", data_dir=td)
            self.assertEqual(s["price_inr"], 199)
            s2 = pulse.load_settings(td)
            self.assertEqual(s2["conversion_pct"], 7.5)
            self.assertEqual(s2["plan_name"], "Pro X")
            # clamps
            s3 = pulse.save_settings(price_inr=10 ** 9, conversion_pct=500,
                                     data_dir=td)
            self.assertEqual(s3["price_inr"], 100000)
            self.assertEqual(s3["conversion_pct"], 100)


class TestVisionGrowth(unittest.TestCase):
    def test_growth_pillar_in_vision(self):
        with tempfile.TemporaryDirectory() as td:
            dd = Path(td)
            (dd / "question_bank.json").write_text(json.dumps({"questions": []}))
            (dd / "members.json").write_text(json.dumps({"members": _members()}))
            rep = vision.vision_report(data_dir=dd)
        g = rep["pillars"]["growth"]
        self.assertEqual(g["total_referrals"], 12)
        self.assertEqual(g["referred_members"], 2)


class TestPulseApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dashboard_server as ds
        cls.ds = ds
        cls.tmp = Path(tempfile.mkdtemp())
        cls._auth_orig = ds.AUTH_FILE
        (cls.tmp / "auth.json").write_text(json.dumps(
            {"tokens": ["test-token"], "ip_lock_enabled": False}))
        ds.AUTH_FILE = cls.tmp / "auth.json"
        cls._settings_orig = pulse.SETTINGS_FILE
        pulse.SETTINGS_FILE = cls.tmp / "pulse_settings.json"
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ds.DashboardHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.ds.AUTH_FILE = cls._auth_orig
        pulse.SETTINGS_FILE = cls._settings_orig

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json",
                     "Cookie": "su_auth=test-token"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())

    def test_pulse_endpoint_and_settings_save(self):
        d = self._call("GET", "/api/pulse")
        self.assertTrue(d["ok"])
        self.assertIn("funnel", d)
        self.assertIn("planner", d)
        d2 = self._call("POST", "/api/pulse/settings",
                        {"price_inr": 249, "conversion_pct": 8,
                         "plan_name": "Pro Max"})
        self.assertEqual(d2["planner"]["price_inr"], 249)
        self.assertEqual(pulse.load_settings()["plan_name"], "Pro Max")

    def test_tab_wired(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("tab-growth", src)
        self.assertIn("loadPulse", src)


if __name__ == "__main__":
    unittest.main()
