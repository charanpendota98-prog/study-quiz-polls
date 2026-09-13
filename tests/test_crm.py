import sys, unittest, tempfile, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from core import crm, config


class Rec:
    def __init__(self, ok=True):
        self.calls = []; self.ok = ok
    def __call__(self, url, payload):
        self.calls.append(payload); return self.ok


MEM = {"1": {"registered": True, "name": "Ravi", "district": "Warangal", "state": "Telangana", "mobile": "9", "points": 120, "correct": 8, "total": 10,
             "college": "KITS", "branch": "CSE", "year": "3", "tests": [{"pct": 40, "date": "2026-09-01"}, {"pct": 70, "date": "2026-09-10"}],
             "joined_channels": ["a", "b"], "badges": ["streak7"], "referrals": 2, "ambassador": True},
       "2": {"registered": True, "name": "Sita", "district": "Guntur", "state": "Andhra Pradesh", "points": 10, "college": "KITS"},
       "3": {"registered": False, "name": "x"}}


class CRMv2(unittest.TestCase):
    def setUp(self):
        crm.SHEET_URL = "https://script.google.com/x"; crm.SHEET_SECRET = "s"
        self.tmp = tempfile.TemporaryDirectory(); crm.QUEUE = pathlib.Path(self.tmp.name) / "q.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_member_row_new_fields(self):
        r = crm.member_row("1", MEM["1"])
        self.assertEqual(r["tests"], 2); self.assertEqual(r["best_pct"], 70); self.assertEqual(r["last_pct"], 70)
        self.assertEqual(r["verified_channels"], 2); self.assertEqual(r["badges"], "streak7"); self.assertTrue(r["ambassador"])
        self.assertEqual(r["accuracy"], 80.0)
        self.assertEqual(set(r), set(crm.COLUMNS))

    def test_push_all_and_colleges(self):
        p = Rec()
        self.assertEqual(crm.push_all(MEM, post=p), 2)
        self.assertEqual(p.calls[0]["action"], "bulk"); self.assertEqual(len(p.calls[0]["rows"]), 2)
        self.assertEqual(crm.push_colleges(MEM, post=p), 1)
        row = p.calls[-1]["rows"][0]
        self.assertEqual(row["college"], "KITS"); self.assertEqual(row["students"], 2); self.assertEqual(row["improved"], 1)
        self.assertEqual(row["ambassador"], "Ravi"); self.assertEqual(row["avg_last_pct"], 70)

    def test_campus_daily_campaign(self):
        p = Rec()
        self.assertTrue(crm.push_campus("CE-1", "Fest", "Warangal", [{"rank": 1, "uid": "1", "name": "Ravi", "college": "KITS", "correct": 7, "total": 10, "pts": 100}], members=MEM, post=p))
        r = p.calls[-1]["rows"][0]
        self.assertEqual(p.calls[-1]["action"], "campus"); self.assertEqual(r["phone"], "9"); self.assertEqual(r["pct"], 70); self.assertEqual(r["branch"], "CSE")
        self.assertTrue(crm.push_daily(MEM, post=p))
        d = p.calls[-1]["row"]; self.assertEqual(d["members"], 2); self.assertEqual(d["ts_members"], 1); self.assertEqual(d["colleges"], 1)
        self.assertTrue(crm.push_campaign({"by": "1", "seg": {}, "text": "hi", "report": {"total": 5, "sent": 4, "blocked": 1}}, post=p))
        self.assertEqual(p.calls[-1]["action"], "campaign"); self.assertEqual(p.calls[-1]["row"]["sent"], 4)

    def test_offline_queue_and_flush(self):
        bad = Rec(ok=False)
        self.assertFalse(crm.push_member("2", MEM["2"], post=bad))
        self.assertEqual(crm.queue_size(), 1)
        good = Rec()
        self.assertEqual(crm.flush_queue(post=good), 1)
        self.assertEqual(crm.queue_size(), 0)
        self.assertEqual(good.calls[0]["action"], "upsert"); self.assertEqual(good.calls[0]["secret"], "s")

    def test_nightly_sync(self):
        p = Rec()
        out = crm.nightly_sync(MEM, post=p)
        self.assertEqual(out["members"], 2); self.assertEqual(out["colleges"], 1); self.assertTrue(out["daily"])
        self.assertIn("partners", out)

    def test_disabled(self):
        crm.SHEET_URL = ""
        self.assertFalse(crm.push_member("1", MEM["1"])); self.assertEqual(crm.push_all(MEM), 0)
        self.assertIn("not set", crm.sheet_status_text(MEM))


if __name__ == "__main__":
    unittest.main()
