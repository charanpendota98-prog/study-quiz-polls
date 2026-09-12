import sys, unittest
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, roundshow as R


class _KV:
    def save(self): pass


class _Members:
    def __init__(self, n=18):
        self.kv = _KV()
        base = datetime.now(config.IST)
        self.members, ch = {}, {}
        for i in range(n):
            uid = str(i + 1)
            self.members[uid] = {"registered": True, "name": f"P{i+1}", "district": ["Warangal", "Guntur", "Khammam"][i % 3],
                                 "points": 50 * i, "rounds": 1 if i == 5 else 20}
            correct = max(0, 10 - i // 2)
            ch[uid] = {"correct": correct, "total": 10, "first": base.isoformat(),
                       "last": (base + timedelta(seconds=60 + i * 10)).isoformat()}
        ch["99"] = {"correct": 10, "total": 10}                       # unregistered
        self.members["1"]["rounds"] = 20
        self.data = {"rounds": {"20260901-0900": {"by_channel": {"TSPSC": {"1": {"correct": 4, "total": 10}}}},
                                "20260902-0900": {"by_channel": {"TSPSC": ch}}}}
    def _get(self, uid): return self.members.setdefault(str(uid), {})
    def district_of_round(self, rid, ch, min_players=2):
        return {"district": "Warangal", "avg": 80, "players": 6}


class TestRoundShow(unittest.TestCase):
    def test_full_show(self):
        m = _Members()
        t = R.render(m, "20260902-0900", "TSPSC", 10, "Morning", {"emoji": "🏛"})
        for s in ("TOP 10", "RISING 5", "SCORE SPREAD", "SPECIALS", "⚡ Fastest", "🆕 Best newcomer: P6",
                  "📈 Comeback: P1", "🎯 Perfect", "District of the round", "18 players", "1 unregistered"):
            self.assertIn(s, t)
        self.assertIn("🥇 P1 · Warangal — 10/10", t)
        self.assertIn("Rank #1/18", R.my_line(m, "1", "20260902-0900", "TSPSC", 10))
        ml = R.my_line(m, "14", "20260902-0900", "TSPSC", 10)
        self.assertIn("Rank #14/18", ml); self.assertIn("Top 10 కి ఇంకా", ml)
        self.assertEqual(R.my_line(m, "99", "20260902-0900", "TSPSC", 10), "")
        self.assertEqual(R.render(m, "nope", "TSPSC", 10), "")

    def test_small_round(self):
        m = _Members(n=3)
        t = R.render(m, "20260902-0900", "TSPSC", 10)
        self.assertIn("TOP 10", t); self.assertNotIn("RISING", t)


if __name__ == "__main__":
    unittest.main()
