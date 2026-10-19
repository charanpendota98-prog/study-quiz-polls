# -*- coding: utf-8 -*-
"""310X — Approve-to-Live publish pipeline (Bridge Phase-3).

Daily draft auto-builds (quiz + today's live exams + Sunday grand);
NOTHING goes live without owner approval. WP push uses env-only
Application-Password creds and must fail soft, never crash.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import publish_queue, wp_push  # noqa: E402

DASH = (ROOT / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")


def _qs(n=10, pyq=4):
    return [{"id": f"Q{i}", "source": "pyq" if i < pyq else "curated",
             "topic": "History" if i % 2 else "Polity"} for i in range(n)]


class TestDraftBuilder(unittest.TestCase):
    def test_manifest_counts(self):
        d = publish_queue.build_draft(
            "2026-10-19", _qs(), [{"id": "E1", "title": "Mock", "n_q": 15,
                                   "starts_at": "2026-10-19T10:00",
                                   "status": "scheduled"}], False)
        self.assertEqual(d["id"], "PD-2026-10-19")
        self.assertEqual(d["status"], "draft")
        self.assertEqual(d["quiz"]["count"], 10)
        self.assertEqual(d["quiz"]["pyq"], 4)
        self.assertEqual(len(d["exams_today"]), 1)
        self.assertIsNone(d["weekly_grand"])

    def test_sunday_grand_included(self):
        d = publish_queue.build_draft("2026-10-25", _qs(), [], True,
                                      {"n_q": 25, "time": "10:00"})
        self.assertEqual(d["weekly_grand"]["n_q"], 25)


class TestStateMachine(unittest.TestCase):
    def setUp(self):
        from core import config
        self._tmp = tempfile.TemporaryDirectory()
        self._old = config.DATA
        config.DATA = Path(self._tmp.name)
        self.draft = publish_queue.get_or_build_today()
        self.did = self.draft["id"]

    def tearDown(self):
        from core import config
        config.DATA = self._old
        self._tmp.cleanup()

    def test_go_live_requires_approval(self):
        ok, _ = publish_queue.go_live(self.did)
        self.assertFalse(ok)  # approve lekunda live avvadu (owner rule)

    def test_approve_then_live(self):
        ok, _ = publish_queue.approve(self.did, by="owner")
        self.assertTrue(ok)
        ok2, _ = publish_queue.approve(self.did)
        self.assertFalse(ok2)  # double approve blocked
        ok3, _ = publish_queue.go_live(self.did)
        self.assertTrue(ok3)
        self.assertEqual(publish_queue.get(self.did)["status"], "live")

    def test_reject_then_rebuild(self):
        ok, _ = publish_queue.reject(self.did, reason="questions weak")
        self.assertTrue(ok)
        fresh = publish_queue.get_or_build_today()
        self.assertEqual(fresh["status"], "draft")  # rejected → rebuild

    def test_wp_mark(self):
        publish_queue.approve(self.did)
        publish_queue.mark_wp_pushed(self.did, True, stored=10)
        d = publish_queue.get(self.did)
        self.assertTrue(d["wp"]["pushed"])
        self.assertEqual(d["wp"]["stored"], 10)
        events = [h["event"] for h in d["history"]]
        self.assertIn("wp_pushed", events)
        self.assertIn("approved", events)

    def test_unknown_draft(self):
        ok, _ = publish_queue.approve("PD-1900-01-01")
        self.assertFalse(ok)


class TestWpPush(unittest.TestCase):
    def test_missing_creds_fails_soft(self):
        with mock.patch.object(wp_push, "creds", lambda: ("", "")):
            r = wp_push.push_quiz({"date": "2026-10-19",
                                   "questions": [{"q": "x"}]})
        self.assertFalse(r["ok"])
        self.assertTrue(r["creds_missing"])

    def test_empty_payload(self):
        r = wp_push.push_quiz({"questions": []})
        self.assertFalse(r["ok"])

    def test_dry_run(self):
        r = wp_push.push_quiz({"date": "d", "questions": [{"q": "x"}]},
                              dry_run=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["count"], 1)
        self.assertTrue(r["url"].endswith("/wp-json/studentup/v1/quiz"))

    def test_push_sends_basic_auth_and_parses(self):
        captured = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"ok": true, "stored": 7}'

        def fake_open(req, timeout=0):
            captured["url"] = req.full_url
            captured["auth"] = req.headers.get("Authorization")
            return _Resp()

        with mock.patch.object(wp_push, "creds",
                               lambda: ("admin", "abcd efgh")):
            r = wp_push.push_quiz({"date": "2026-10-19",
                                   "questions": [{"q": "x", "a": ["1"]}]},
                                  urlopen=fake_open)
        self.assertTrue(r["ok"])
        self.assertEqual(r["stored"], 7)
        self.assertTrue(captured["url"].endswith("/wp-json/studentup/v1/quiz"))
        self.assertTrue(captured["auth"].startswith("Basic "))

    def test_network_error_never_raises(self):
        def boom(req, timeout=0):
            raise OSError("dns fail")

        with mock.patch.object(wp_push, "creds", lambda: ("a", "b")):
            r = wp_push.push_quiz({"questions": [{"q": "x"}]}, urlopen=boom)
        self.assertFalse(r["ok"])


class TestDashboardWiring(unittest.TestCase):
    def test_routes_exist(self):
        for route in ("/api/publish/today", "/api/publish/approve",
                      "/api/publish/reject", "/api/publish/push_wp",
                      "/api/publish/go_live"):
            self.assertIn(route, DASH)

    def test_push_requires_approval_in_route(self):
        i = DASH.index('p.path == "/api/publish/push_wp"')
        self.assertIn("approve lekunda WP push avvadu", DASH[i:i + 900])

    def test_publish_center_ui(self):
        self.assertIn("pub-status", DASH)
        self.assertIn("Publish Center", DASH)
        for fn in ("pubLoad", "pubApprove", "pubPushWp", "pubGoLive"):
            self.assertIn(fn, DASH)

    def test_golive_check_guarded(self):
        self.assertIn("Daily publish draft (310X)", DASH)


if __name__ == "__main__":
    unittest.main()
