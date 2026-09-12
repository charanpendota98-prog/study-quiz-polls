import sys, unittest
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, examboard as E


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        day = datetime.now(config.IST).strftime("%Y%m%d")
        self.members = {"1": {"registered": True, "name": "Ravi", "district": "Warangal", "points": 0},
                        "2": {"registered": True, "name": "Sita", "district": "Guntur", "points": 0},
                        "3": {"registered": True, "name": "Kiran", "district": "Warangal", "points": 0},
                        "4": {"registered": False}}
        r = lambda c, t: {"correct": c, "total": t, "last": "x"}
        self.data = {"rounds": {f"{day}-0900": {"by_channel": {"TSPSC": {"1": r(8, 10), "2": r(9, 10), "3": r(6, 10), "4": r(10, 10)},
                                                                "SSC": {"2": r(5, 10)}}},
                                f"{day}-1300": {"by_channel": {"TSPSC": {"1": r(7, 10), "3": r(7, 10)}}}}}
    def _get(self, uid): return self.members.setdefault(str(uid), {})


class TestExamBoard(unittest.TestCase):
    def test_aggregate_and_renders(self):
        m = _Members()
        rows, drows, n = E.aggregate(m, "TSPSC")
        self.assertEqual(n, 2); self.assertEqual(rows[0]["name"], "Ravi"); self.assertEqual(rows[0]["correct"], 15)
        self.assertEqual({r["uid"] for r in rows}, {"1", "2", "3"})                 # unregistered excluded
        # Guntur: acc 90 + 2 = 92 ; Warangal: 28/40=70 + 4 = 74 → Guntur leads on score
        self.assertEqual(drows[0]["district"], "Guntur")
        self.assertIn("జిల్లాల clash", E.round_clash(m, list(m.data["rounds"])[0], "TSPSC"))
        self.assertEqual(E.round_clash(m, list(m.data["rounds"])[1], "TSPSC"), "")   # single district → no clash
        b = E.render_board(m, "TSPSC"); self.assertIn("Ravi", b); self.assertIn("2 rounds", b)
        self.assertEqual(E.render_board(m, "BANKING"), "")
        self.assertIn("Guntur", E.render_districts(m, "TSPSC"))
        w = E.weekly_close(m, "TSPSC")
        self.assertIn("WEEKLY CHAMPIONS", w); self.assertIn("District of the week", w)
        self.assertEqual(m.members["1"]["points"], 40)              # 1st
        self.assertEqual(m.members["3"]["points"], 25)              # Kiran 13 ✅ → 2nd
        self.assertEqual(m.members["2"]["points"], 15 + 10)         # Sita 3rd + Guntur district of the week


if __name__ == "__main__":
    unittest.main()
