#!/usr/bin/env python3
"""Exam Conductor tests — one-screen exam scheduling, honest launches.

Covers: validation, campus join-code creation, due-tick launching for
war (mocked engine boundary), campus (real engine, honest <2 players
failure), grand (fake engine, background thread), cancel, auto-finish,
and the dashboard API. Engines themselves are tested in their own files.
Run: python3 -m unittest discover -s tests -p "test_conductor.py"
"""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import auditlog, campus, conductor  # noqa: E402
from core import config  # noqa: E402


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M")


class TmpEvents(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (conductor.EVENTS_FILE, campus.PATH)
        conductor.EVENTS_FILE = self.tmp / "exam_events.json"
        campus.PATH = self.tmp / "campus_events.json"

    def tearDown(self):
        conductor.EVENTS_FILE, campus.PATH = self._orig

    def now(self):
        return conductor._now()


class TestCreate(TmpEvents):
    def test_validation(self):
        with self.assertRaises(ValueError):
            conductor.create_event("X", "quiz", _fmt(self.now()))
        with self.assertRaises(ValueError):
            conductor.create_event("X", "grand", "not-a-date")
        with self.assertRaises(ValueError):
            conductor.create_event("X", "grand", _fmt(self.now()), channel="NOPE")
        with self.assertRaises(ValueError):
            conductor.create_event("X", "war", "")

    def test_schedule_war_event(self):
        ev = conductor.create_event("Sunday War", "war",
                                    _fmt(self.now() + timedelta(days=1)),
                                    lobby_min=10)
        self.assertEqual(ev["status"], "scheduled")
        self.assertEqual(ev["lobby_min"], 10)
        listed = conductor.list_events()
        self.assertEqual(listed[0]["id"], ev["id"])
        self.assertGreater(listed[0]["starts_in_min"], 1000)

    def test_campus_event_creates_join_code(self):
        ev = conductor.create_event("College Test", "campus",
                                    _fmt(self.now() + timedelta(hours=2)),
                                    campus_name="ABC College", district="Warangal")
        self.assertTrue(ev["engine_ref"].startswith("CE-"))
        self.assertIn(ev["engine_ref"], ev["note"])
        # real campus store got the event
        d = campus._load()
        self.assertIn(ev["engine_ref"], d["events"])


class TestTick(TmpEvents):
    def test_war_launch_and_autofinish(self):
        ev = conductor.create_event("War", "war",
                                    _fmt(self.now() - timedelta(minutes=40)),
                                    duration_min=30, lobby_min=5)
        with mock.patch("core.districtwar.manual_launch",
                        return_value=(True, "lobby open")) as ml:
            out = conductor.tick(bank=None, members=None, tg=None)
            self.assertEqual(out["launched"], [ev["id"]])
            self.assertTrue(ml.called)
            self.assertEqual(conductor.get_event(ev["id"])["status"], "live")
            # launched ippude — ventane done avvakudadu; +40 min tarvata done
            out_mid = conductor.tick(bank=None, members=None, tg=None)
            self.assertEqual(out_mid["finished"], [])
            out2 = conductor.tick(now=self.now() + timedelta(minutes=40),
                                  bank=None, members=None, tg=None)
            self.assertEqual(out2["finished"], [ev["id"]])
        self.assertEqual(conductor.get_event(ev["id"])["status"], "done")

    def test_campus_launch_honest_failure(self):
        # real campus.start: 0 players joined -> honest fail, no fake live
        ev = conductor.create_event("Campus", "campus",
                                    _fmt(self.now() - timedelta(minutes=1)),
                                    campus_name="XYZ College")
        fake_members = SimpleNamespace(members={})
        out = conductor.tick(bank=None, members=fake_members, tg=None)
        self.assertEqual(len(out["failed"]), 1)
        self.assertIn("registered", out["failed"][0]["error"])
        self.assertEqual(conductor.get_event(ev["id"])["status"], "failed")

    def test_grand_launch_background_thread(self):
        ev = conductor.create_event("Grand", "grand",
                                    _fmt(self.now() - timedelta(minutes=1)),
                                    channel="CURRENT")
        calls = []

        class FakeEngine:
            def run_grand_test(self, channels=None):
                calls.append(channels)

        out = conductor.tick(bank=None, members=None, tg=None,
                             engine_factory=lambda: FakeEngine())
        self.assertEqual(out["launched"], [ev["id"]])
        for _ in range(50):                       # thread completes async
            if conductor.get_event(ev["id"])["status"] == "done":
                break
            time.sleep(0.1)
        self.assertEqual(calls, [["CURRENT"]])
        self.assertEqual(conductor.get_event(ev["id"])["status"], "done")

    def test_cancel(self):
        ev = conductor.create_event("Later", "war",
                                    _fmt(self.now() + timedelta(hours=3)))
        self.assertTrue(conductor.cancel_event(ev["id"]))
        self.assertFalse(conductor.cancel_event(ev["id"]))
        self.assertEqual(conductor.due_events(), [])


class TestConductorApi(TmpEvents):
    @classmethod
    def setUpClass(cls):
        import dashboard_server as ds
        cls.ds = ds

    def setUp(self):
        super().setUp()
        self._auth_orig = self.ds.AUTH_FILE
        self._audit_orig = auditlog.AUDIT_FILE
        (self.tmp / "auth.json").write_text(json.dumps(
            {"tokens": ["test-token"], "ip_lock_enabled": False}))
        self.ds.AUTH_FILE = self.tmp / "auth.json"
        auditlog.AUDIT_FILE = self.tmp / "audit_log.jsonl"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                          self.ds.DashboardHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.ds.AUTH_FILE = self._auth_orig
        auditlog.AUDIT_FILE = self._audit_orig
        super().tearDown()

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json",
                     "Cookie": "su_auth=test-token"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())

    def test_create_list_cancel(self):
        when = _fmt(conductor._now() + timedelta(days=2))
        d = self._call("POST", "/api/conductor/create",
                       {"title": "API War", "kind": "war", "starts_at": when})
        self.assertTrue(d["ok"], d)
        eid = d["event"]["id"]
        lst = self._call("GET", "/api/conductor")
        self.assertTrue(lst["ok"])
        self.assertTrue(lst["channels"])
        self.assertEqual(lst["events"][0]["id"], eid)
        c = self._call("POST", "/api/conductor/cancel", {"id": eid})
        self.assertTrue(c["ok"])
        bad = self._call("POST", "/api/conductor/create",
                         {"kind": "quiz", "starts_at": when})
        self.assertFalse(bad["ok"])

    def test_tab_wired(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("tab-conductor", src)
        self.assertIn("loadConductor", src)
        bot = (ROOT / "scripts" / "bot.py").read_text()
        self.assertIn("conductor.tick", bot)


if __name__ == "__main__":
    unittest.main()
