import sys, unittest, tempfile, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, rewards
from core.content import build_missed_explanations, most_missed


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        self.members = {"1": {"registered": True, "name": "Ravi", "district": "Warangal", "points": 450, "phone": "9xxxx"},
                        "2": {"registered": True, "name": "Sita", "district": "Guntur", "points": 50}}
    def _get(self, uid): return self.members.setdefault(str(uid), {})


class TestRewards(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._o = (rewards.CATALOG_PATH, rewards.LEDGER_PATH)
        rewards.CATALOG_PATH = self.tmp / "cat.json"; rewards.LEDGER_PATH = self.tmp / "led.json"
    def tearDown(self):
        rewards.CATALOG_PATH, rewards.LEDGER_PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wallet_and_hold_verify_flow(self):
        m = _Members()
        w = rewards.render_wallet(m, "1")
        self.assertIn("450 pts", w); self.assertIn("Next unlock", w)
        ok, txt, admin = rewards.redeem(m, "1", "app50")            # 400 pts
        self.assertTrue(ok); self.assertIn("SU-", txt); self.assertIn("/verify", admin)
        code = [l for l in txt.splitlines() if l.startswith("Code:")][0].split("`")[1]
        b = rewards.balance(m, "1")
        self.assertEqual((b["points"], b["held"], b["available"]), (450, 400, 50))
        ok2, txt2, _ = rewards.redeem(m, "1", "app20")               # 200 > 50 available → blocked
        self.assertFalse(ok2)
        # counter verify burns points; second verify refuses
        res = rewards.verify(m, code, staff_uid="9")
        self.assertTrue(res.startswith("✅")); self.assertEqual(m.members["1"]["points"], 50)
        self.assertIn("already USED", rewards.verify(m, code))
        # cancel path releases hold
        ok3, txt3, _ = rewards.redeem(m, "2", "print10")
        self.assertFalse(ok3)                                        # 50 < 100
        m.members["2"]["points"] = 120
        ok4, txt4, _ = rewards.redeem(m, "2", "print10")
        c2 = [l for l in txt4.splitlines() if l.startswith("Code:")][0].split("`")[1]
        self.assertIn("released", rewards.cancel(m, "2", c2))
        self.assertEqual(rewards.balance(m, "2")["available"], 120)
        self.assertIn("Rewards summary", rewards.admin_summary())

    def test_expiry_releases_points(self):
        from datetime import datetime, timedelta
        m = _Members()
        rewards.redeem(m, "1", "print10", when=datetime.now(config.IST) - timedelta(days=40))
        self.assertEqual(rewards.balance(m, "1")["held"], 100)
        self.assertEqual(rewards.expire_stale(m), 1)
        self.assertEqual(rewards.balance(m, "1")["held"], 0)

    def test_buttons_lock_unaffordable(self):
        rows = rewards.offer_buttons(_Members(), "2")
        self.assertTrue(all(cb.startswith("locked:") for [(lab, cb)] in rows))


class TestMostMissed(unittest.TestCase):
    def _q(self, i, ex=True):
        return {"id": f"q{i}", "q_en": f"Question {i}?", "q_te": f"ప్రశ్న {i}?", "answer_index": 2,
                "options_en": ["a", "b", "c", "d"], "options_te": ["ఎ", "బి", "సి", "డి"],
                "explanation_en": "Because X." if ex else "", "explanation_te": "ఎందుకంటే X." if ex else ""}

    def test_only_when_many_wrong_with_min_votes(self):
        qs = [self._q(1), self._q(2), self._q(3)]
        stats = {"q1": {"correct": 2, "total": 10},    # 80% wrong → explain
                 "q2": {"correct": 9, "total": 10},    # easy → skip
                 "q3": {"correct": 0, "total": 3}}     # too few votes → skip
        mm = most_missed(qs, stats)
        self.assertEqual([q["id"] for q, _, _ in mm], ["q1"])
        txt = build_missed_explanations(qs, stats, None, {"emoji": "🏛"})
        self.assertIn("80% wrong", txt); self.assertIn("ఎందుకంటే X.", txt); self.assertIn("Because X.", txt)
        self.assertNotIn("Question 2", txt)
        self.assertEqual(build_missed_explanations(qs, {}), "")
        self.assertEqual(build_missed_explanations([self._q(9, ex=False)], {"q9": {"correct": 0, "total": 20}}), "")

    def test_member_stats_fallback(self):
        qs = [self._q(1)]
        txt = build_missed_explanations(qs, {}, {"q1": {"correct": 1, "total": 8}})
        self.assertIn("Most missed", txt)


if __name__ == "__main__":
    unittest.main()
