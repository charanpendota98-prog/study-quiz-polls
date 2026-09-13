import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, campus as C, roster as R


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        self.members = {"1": {"registered": True, "name": "Ravi", "college": "KITS", "district": "Warangal", "points": 0, "mobile": "9000000001"},
                        "2": {"registered": True, "name": "Sita", "college": "KITS", "district": "Warangal", "points": 0},
                        "3": {"registered": True, "name": "Kiran", "college": "Other", "points": 0}}
    def _get(self, u): return self.members.setdefault(str(u), {})


class _TG:
    def __init__(self): self.msgs = []; self.docs = []
    def send_message(self, c, t, **k): self.msgs.append((str(c), t))
    def send_document(self, c, n, b, **k): self.docs.append((str(c), n))
    def _call(self, m, p, **k): return {"result": {"poll": {"id": "p" + str(len(self.msgs))}}}


class TestRoster(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self._o = C.PATH; C.PATH = self.tmp / "c.json"
    def tearDown(self):
        C.PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_profile_capture(self):
        m = _Members()
        self.assertTrue(R.needs_profile(m.members["1"]))
        t, b = R.handle_callback(m, "1", "b", "B.Tech"); self.assertIn("year", t.lower()); self.assertTrue(b)
        t, b = R.handle_callback(m, "1", "y", "3rd"); self.assertIsNone(b)
        self.assertEqual((m.members["1"]["branch"], m.members["1"]["year"], m.members["1"]["points"]), ("B.Tech", "3rd", R.PROFILE_PTS))
        self.assertFalse(R.needs_profile(m.members["1"]))
        R.handle_callback(m, "2", "skip", "-"); self.assertFalse(R.needs_profile(m.members["2"]))

    def test_retest_enrols_college_pings_autostarts_and_tracks_improvement(self):
        m, tg = _Members(), _TG()
        code, n = R.schedule_retest(m, "KITS", n_q=5)
        self.assertEqual(n, 2)
        e = C._load()["events"][code]
        self.assertEqual(set(e["players"]), {"1", "2"}); self.assertTrue(e["retest"]); self.assertEqual(e["mode"], "college")
        self.assertEqual(R.ping_retest(tg, code), 2); self.assertIn("beat", tg.msgs[0][1])
        self.assertEqual(R.auto_start_due(None, m, tg, now=R._now()), [])                      # not yet
        started = R.auto_start_due(None, m, tg, now=R._now() + timedelta(minutes=11))
        self.assertEqual(started, [code])
        self.assertIn(C._load()["events"][code]["state"], ("question", "gap"))
        # improvement tracking: fake two attempts
        e = C._load()["events"][code]
        e["players"]["1"].update(correct=2, pts=20, rank=2, answered=5); e["players"]["2"].update(correct=4, pts=40, rank=1, answered=5)
        m.members["1"]["tests"] = [{"code": "X", "date": "2026-09-01", "pct": 20, "college": "KITS", "correct": 1, "n": 5, "pts": 10, "rank": 2, "of": 2}]
        m.members["2"]["tests"] = [{"code": "X", "date": "2026-09-01", "pct": 80, "college": "KITS", "correct": 4, "n": 5, "pts": 40, "rank": 1, "of": 2}]
        imp = R.record_event(m, e)
        self.assertEqual(len(imp), 1); self.assertEqual(imp[0][3], "1"); self.assertEqual(imp[0][0], 20)
        self.assertEqual(m.members["1"]["points"], R.IMPROVE_PTS[0]); self.assertIn("improver", m.members["1"]["badges"])
        self.assertIn("20% → 40%", R.improved_text(imp))
        rep = R.progress_report(m, "KITS")
        self.assertIn("1/2 students improved", rep)
        csv = R.roster_csv(m, "KITS")
        self.assertIn("Ravi,9000000001", csv); self.assertEqual(len(csv.splitlines()), 3)
        self.assertIn("KITS — ROSTER", R.roster_text(m, "KITS"))
        top = R.weekly_toppers(m)
        self.assertIn("KITS", top); self.assertIn("🥇 Ravi", top)

    def test_no_students(self):
        self.assertEqual(R.schedule_retest(_Members(), "Nope"), (None, 0))


if __name__ == "__main__":
    unittest.main()
