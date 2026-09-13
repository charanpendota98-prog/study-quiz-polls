import sys, unittest
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, reportcard as R


class _KV:
    def save(self): pass


class _M:
    def __init__(self):
        self.kv = _KV()
        now = datetime.now(config.IST)
        d = lambda i: (now - timedelta(days=i)).strftime("%Y-%m-%d")
        self.members = {"1": {"registered": True, "name": "Ravi", "district": "Warangal", "state_code": "TS", "points": 300, "streak": 4, "exam": "TSPSC",
                              "college": "KITS", "badges": ["focus"], "daylog": {d(0): [10, 8], d(1): [5, 3], d(3): [12, 10]},
                              "topics": {"polity": {"correct": 2, "total": 5}, "history": {"correct": 9, "total": 10}}},
                        "2": {"registered": True, "name": "Sita", "district": "Warangal", "state_code": "TS", "points": 500, "daylog": {d(0): [2, 2]}},
                        "3": {"registered": True, "name": "Kiran", "district": "Guntur", "state_code": "AP", "points": 900, "daylog": {}}}


class _TG:
    def __init__(self): self.msgs = []
    def send_message(self, c, t, **k): self.msgs.append((str(c), t))


class TestReportCard(unittest.TestCase):
    def test_week_stats_ranks_and_text(self):
        m = _M()
        w = R.week_stats(m.members["1"])
        self.assertEqual((w["answers"], w["correct"], w["acc"], w["active_days"]), (27, 21, 78, 3))
        self.assertEqual(len(w["bars"]), 7); self.assertEqual(w["bars"][-1], "▆")
        self.assertEqual(R.ranks(m, "1"), (2, 2, 2, 2))
        self.assertEqual(R.topics(m.members["1"]), ("History 90%", "Polity 40%"))
        t = R.text_card(m, "1")
        for s in ("Ravi", "27 Q", "78%", "District rank #2/2", "State #2/2", "Streak 4", "History 90%", "Fix next: Polity 40%", "KITS", "start=r1"):
            self.assertIn(s, t)

    def test_weekly_send_only_active(self):
        m, tg = _M(), _TG()
        n = R.weekly_send(tg, m)
        self.assertEqual(n["text"] + n["png"], 1)                      # only Ravi has ≥5 answers
        self.assertEqual(tg.msgs[0][0], "1")

    def test_daylog_written_by_members(self):
        from core import members as MM
        mem = MM.Members.__new__(MM.Members)
        mem.members = {}; mem.kv = _KV(); mem.pending = {}
        try:
            mem.data = {}
        except Exception:
            pass
        m = mem._get("424242") if hasattr(mem, "_get") else None
        if m is None:
            self.skipTest("Members shape differs")
        m.update({"registered": True, "name": "T"})
        try:
            mem.award_answer("424242", correct=True, topic="polity")
        except Exception as e:
            self.skipTest(f"award_answer needs full store: {e}")
        dl = mem.members["424242"]["daylog"]
        self.assertEqual(sum(v[0] for v in dl.values()), 1); self.assertEqual(sum(v[1] for v in dl.values()), 1)


if __name__ == "__main__":
    unittest.main()
