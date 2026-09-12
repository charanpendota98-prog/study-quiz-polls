import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, hq as H


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        today = datetime.now(config.IST).strftime("%Y-%m-%d")
        self.members = {"1": {"registered": True, "name": "Ravi", "district": "Warangal", "college": "SR College", "points": 300, "registered_at": today, "last_active": today, "joined_channels": {"CURRENT": "x"}},
                        "2": {"registered": True, "name": "Sita", "district": "Warangal", "college": "SR College", "points": 100, "registered_at": "2026-01-01", "last_active": "2026-01-02"},
                        "3": {"registered": True, "name": "Kiran", "district": "Guntur", "points": 50, "registered_at": "2026-01-01", "dm_blocked": True}}
        self.data = {"rounds": {today.replace("-", "") + "-0900": {"by_channel": {"TSPSC": {"1": {"correct": 8, "total": 10}}}}}}
    def _get(self, u): return self.members.setdefault(str(u), {})


class TestHQ(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self._o = H.PATH; H.PATH = self.tmp / "hq.json"
    def tearDown(self):
        H.PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_render_alerts_clubs(self):
        m = _Members()
        txt, mx, al = H.render(m)
        self.assertEqual(mx["members"], 3); self.assertEqual(mx["new_today"], 1); self.assertEqual(mx["players_today"], 1)
        self.assertIn("Members 3", txt); self.assertIn("SR College 2", txt)
        self.assertTrue(any("blocked" in a for a in al))
        self.assertIsNotNone(H.morning_brief(m))
        cs = H.clubs(m); self.assertEqual(cs["SR College"]["members"], 2); self.assertEqual(cs["SR College"]["top"][0], "1")
        H.set_leader("SR College", "1", m); self.assertEqual(m.members["1"]["points"], 350); self.assertIn("ambassador", m.members["1"]["badges"])
        card, btns = H.club_card(m, "SR College")
        self.assertIn("Ravi", card); self.assertTrue(any("club:rerun:" in cb for row in btns for _, cb in row))
        self.assertIn("CLUB BOARD", H.club_board(m, "SR College"))
        self.assertEqual(H.club_members(m, "SR College"), ["1", "2"])
        self.assertIn("SR College", H.club_list_text(m))
        self.assertEqual(H.club_card(m, "Nope")[0], "College not found.")


if __name__ == "__main__":
    unittest.main()
