import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, growth


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        now = datetime.now(config.IST)
        rid = (now - timedelta(days=1)).strftime("%Y%m%d-1930")
        self.members = {
            "1": {"registered": True, "name": "Ravi", "district": "Warangal", "points": 300, "streak": 4,
                  "topics": {"Polity": {"correct": 8, "total": 10}, "Number Series": {"correct": 2, "total": 6}},
                  "referrals": 4, "badges": []},
            "2": {"registered": True, "name": "Sita", "district": "Guntur", "points": 200, "topics": {},
                  "referred_by": "1", "registered_at": now.isoformat()},
            "3": {"registered": True, "name": "Kiran", "district": "Guntur", "points": 100, "topics": {}},
        }
        self.data = {"rounds": {rid: {"by_channel": {"TSPSC": {
            "1": {"correct": 9, "total": 10, "qids": [f"q{i}" for i in range(10)],
                  "first": (now - timedelta(days=1, minutes=12)).isoformat(), "last": (now - timedelta(days=1)).isoformat()},
            "2": {"correct": 6, "total": 10, "qids": []},
            "3": {"correct": 4, "total": 10, "qids": []}}}}}}
    def _get(self, uid): return self.members.setdefault(str(uid), {})
    def weak_topics(self, uid, limit=3): return [("Number Series", 0.33)]
    def top_in_district(self, d, limit=10):
        return [(u, m) for u, m in self.members.items() if m.get("district") == d]
    def rank(self, uid): return 1


class _Bank:
    def by_id(self, qid):
        return {"id": qid, "q_en": "Q?", "q_te": "ప్ర?", "options_en": ["a", "b", "c", "d"], "answer_index": 1, "topic": "Polity"}


class TestGrowth(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self._old = growth.CHALLENGE_PATH
        growth.CHALLENGE_PATH = self.tmp / "c.json"
    def tearDown(self):
        growth.CHALLENGE_PATH = self._old; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_report_card(self):
        m = _Members()
        txt = growth.weekly_report(m, "1")
        self.assertIn("Weekly Report Card", txt); self.assertIn("Warangal", txt)
        self.assertIn("Subject-wise", txt); self.assertIn("Number Series", txt); self.assertIn("goal", txt)
        self.assertEqual(growth.weekly_report(m, "999"), "")
        self.assertEqual(set(growth.active_members(m)), {"1", "2", "3"})

    def test_referral_board(self):
        txt = growth.referral_board(_Members())
        self.assertIn("Ravi", txt); self.assertIn("🥉 Connector", txt); self.assertIn("This week", txt)

    def test_challenge_flow_win_and_one_attempt(self):
        m, b = _Members(), _Bank()
        data = growth.build_daily_challenge(m, b)
        self.assertEqual(data["topper"]["name"], "Ravi"); self.assertEqual(len(data["qids"]), 5)
        self.assertTrue(growth.start_attempt("3", data))
        self.assertFalse(growth.start_attempt("3", data))
        for i, qid in enumerate(data["qids"]):
            growth.register_poll(data, f"p{i}", "3", qid, 1)
        res = None
        for i in range(5):
            is_ch, res = growth.record_answer(m, f"p{i}", "3", 1)   # all correct → 5/5 beats 4.5
            self.assertTrue(is_ch)
        self.assertIn("BEAT THE TOPPER", res)
        self.assertEqual(m.members["3"]["points"], 100 + growth.CHALLENGE_WIN_PTS)
        self.assertIn("beat_topper", m.members["3"]["badges"])
        self.assertEqual(growth.record_answer(m, "nope", "3", 0), (False, None))
        self.assertIn("Ravi", growth.challenge_invite_text(data))


if __name__ == "__main__":
    unittest.main()
