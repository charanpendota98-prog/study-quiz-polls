import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, hooks


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        now = datetime.now(config.IST)
        dby = (now - timedelta(days=2)).strftime("%Y-%m-%d")
        self.members = {"1": {"registered": True, "name": "Ravi", "district": "Warangal", "points": 100,
                              "streak": 12, "shields": 1, "last_correct": dby},
                        "2": {"registered": True, "name": "Sita", "district": "Guntur", "points": 50,
                              "streak": 5, "shields": 0, "last_correct": dby},
                        "3": {"registered": True, "name": "Kiran", "district": "Guntur", "points": 10}}
        rid = now.strftime("%Y%m%d-0730")
        self.data = {"rounds": {rid: {"by_channel": {"TSPSC": {
            "1": {"correct": 8, "total": 10, "qids": [f"q{i}" for i in range(10)], "right": [f"q{i}" for i in range(8)]},
            "2": {"correct": 3, "total": 10, "qids": [f"q{i}" for i in range(10)], "right": ["q0", "q1", "q2"]}}}}}}
        self.rid = rid
    def _get(self, uid): return self.members.setdefault(str(uid), {})
    def add_referral(self, a, b): self.members[str(b)]["referrals"] = self.members[str(b)].get("referrals", 0) + 1


class TestHooks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self._o = hooks.SQUADS_PATH
        hooks.SQUADS_PATH = self.tmp / "s.json"
    def tearDown(self):
        hooks.SQUADS_PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_shield_saves_streak_only_with_shield(self):
        m = _Members()
        saved = hooks.protect_streaks(m)
        self.assertEqual([u for u, _ in saved], ["1"])
        self.assertEqual(m.members["1"]["shields"], 0)
        yday = (datetime.now(config.IST) - timedelta(days=1)).strftime("%Y-%m-%d")
        self.assertEqual(m.members["1"]["last_correct"], yday)
        self.assertNotEqual(m.members["2"]["last_correct"], yday)

    def test_shield_earn_and_milestones(self):
        m = {"streak": 7, "points": 0}
        out = hooks.on_daily_activity(m, "d", "y")
        self.assertTrue(out["shield_earned"]); self.assertEqual(out["milestone"], 7); self.assertEqual(m["points"], 50)
        self.assertEqual(hooks.on_daily_activity(m, "d", "y")["bonus"], 0)     # idempotent
        m["streak"] = 14; hooks.on_daily_activity(m, "d", "y")
        m["streak"] = 21; hooks.on_daily_activity(m, "d", "y")
        self.assertEqual(m["shields"], hooks.SHIELD_MAX)                         # capped

    def test_mystery_deterministic_and_applied(self):
        m = _Members()
        idx, mult = hooks.mystery_pick(m.rid, "TSPSC", 10)
        self.assertEqual((idx, mult), hooks.mystery_pick(m.rid, "TSPSC", 10))
        self.assertIn(mult, (2, 3, 5))
        won = hooks.apply_mystery(m, m.rid, "TSPSC", [f"q{i}" for i in range(10)])
        for uid, bonus in won.items():
            self.assertEqual(bonus, (mult - 1) * 10)
        self.assertIn(f"Q{idx + 1}", hooks.mystery_line(m.rid, "TSPSC", 10, len(won)))

    def test_squads(self):
        m = _Members()
        code, msg = hooks.squad_create(m, "1", "Warangal Warriors")
        self.assertIsNotNone(code); self.assertIn(code, msg)
        s, msg2 = hooks.squad_join(m, "2", code)
        self.assertEqual(len(s["members"]), 2); self.assertEqual(m.members["1"]["referrals"], 1)
        self.assertIsNone(hooks.squad_join(m, "2", code)[0])
        top = hooks.render_squad_top(m)
        self.assertIn("Warangal Warriors", top); self.assertIn("11 ✅", top)
        self.assertIn("squad rank #1", hooks.render_squad(m, "1"))
        self.assertIn("Squad నుంచి", hooks.squad_leave("2"))
        self.assertIn("/squad new", hooks.render_squad(m, "2"))

    def test_live_line(self):
        m = _Members()
        ll = hooks.live_line(m, "TSPSC", "Guntur")
        self.assertIn("2 aspirants", ll); self.assertIn("1 from Guntur", ll)
        self.assertEqual(hooks.live_line(m, "SSC"), "")


if __name__ == "__main__":
    unittest.main()
