import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, messenger as MS


class _KV:
    def save(self): pass


class _M:
    def __init__(self):
        self.kv = _KV()
        now = datetime.now(config.IST); d = lambda i: (now - timedelta(days=i)).strftime("%Y-%m-%d")
        self.members = {"1": {"registered": True, "name": "Ravi Kumar", "district": "Warangal", "state": "Telangana", "exam": "TSPSC", "points": 300, "streak": 3, "college": "KITS", "last_active": d(0), "mobile": "9"},
                        "2": {"registered": True, "name": "Sita", "district": "Guntur", "state": "Andhra Pradesh", "exam": "Banking", "points": 50, "last_active": d(10)},
                        "3": {"registered": True, "name": "Blocked", "dm_blocked": True, "district": "Warangal"},
                        "4": {"registered": False, "name": "NotReg"}}


class _TG:
    def __init__(self, fail=()): self.msgs = []; self.fail = set(fail)
    def send_message(self, c, t, buttons=None, **k):
        if str(c) in self.fail: raise RuntimeError("Forbidden: bot was blocked by the user")
        self.msgs.append((str(c), t, buttons))


class TestMessenger(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self._o = MS.PATH; MS.PATH = self.tmp / "c.json"
    def tearDown(self):
        MS.PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_segments(self):
        m = _M()
        self.assertEqual(MS.select(m, {}), ["1", "2"])
        self.assertEqual(MS.select(m, {"district": "Warangal"}), ["1"])
        self.assertEqual(MS.select(m, {"inactive": "7"}), ["2"])
        self.assertEqual(MS.select(m, {"active": "7"}), ["1"])
        self.assertEqual(MS.select(m, {"campus": "yes"}), ["1"])
        self.assertEqual(MS.select(m, {"top": "1"}), ["1"])
        self.assertEqual(MS.select(m, {"college": "kits"}), ["1"])
        self.assertTrue(any("Warangal" in lbl for row in MS.pick_buttons(m, "district") for lbl, _ in row))

    def test_personalise_buttons_preview_send_report(self):
        m, tg = _M(), _TG(fail={"2"})
        MS.start_draft("9", {})
        MS.set_content("9", "Hi {first}, {district} లో మీ points {points}.\n[Open quiz](/quiz)\n[Site](https://x.y)")
        pv, rows, n = MS.preview(m, "9")
        self.assertEqual(n, 2); self.assertIn("Hi Ravi, Warangal లో మీ points 300.", pv); self.assertIn("2 students", pv)
        self.assertTrue(any("Send now" in lbl for row in rows for lbl, _ in row))
        job = MS.schedule("9", MS.when_for("now", datetime(2026, 9, 14, 12, 0, tzinfo=config.IST)))
        self.assertIsNone(MS.get_draft("9"))
        rep = MS.run_job(tg, m, job)
        self.assertEqual((rep["sent"], rep["blocked"], rep["total"]), (1, 1, 2))
        self.assertTrue(m.members["2"]["dm_blocked"])
        uid, txt, btns = tg.msgs[0]
        self.assertEqual(uid, "1"); self.assertNotIn("[Open quiz]", txt)
        self.assertEqual(btns, [[("Open quiz", "cmd:/quiz"), ("Site", "url:https://x.y")]])
        self.assertIn("✅ 1 sent", MS.report_text(job)); self.assertIn("✅1 🚫1", MS.history_text())

    def test_quiet_hours_and_schedule_due(self):
        night = datetime(2026, 9, 14, 23, 0, tzinfo=config.IST)
        self.assertEqual(MS.when_for("now", night).strftime("%d %H:%M"), "15 07:05")
        self.assertEqual(MS.when_for("18", night).strftime("%d %H:%M"), "15 18:00")
        self.assertEqual(MS.when_for("tom9", night).strftime("%d %H:%M"), "15 09:00")
        m, tg = _M(), _TG()
        MS.start_draft("9", {"district": "Guntur"}); MS.set_content("9", "hello {name}")
        job = MS.schedule("9", night + timedelta(hours=8))
        self.assertEqual(MS.run_due(tg, m, now=night), [])
        out = MS.run_due(tg, m, now=night + timedelta(hours=9))
        self.assertEqual(len(out), 1); self.assertEqual(tg.msgs[0][:2], ("2", "hello Sita"))
        self.assertTrue(any(c == "9" and "Delivered" in t for c, t, _ in tg.msgs))
        self.assertEqual(MS.cancel_scheduled(job["id"]), 0)


if __name__ == "__main__":
    unittest.main()
