import sys, unittest, tempfile, pathlib
from datetime import date
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from core import gate, config


class KV:
    def save(self): pass


class M:
    def __init__(self):
        self.members = {"1": {"registered": True, "registered_at": "2026-09-13T10:00", "points": 50},
                        "2": {"registered": False, "locked_points": 40},
                        "3": {"registered": False, "locked_points": 0},
                        "4": {"registered": False, "locked_points": 10, "dm_blocked": True}}
        self.pending = {"3": {"step": "name"}}
        self.data = {"rounds": {"R1": {"by_channel": {"TSPSC": {"1": {"correct": 8, "total": 10}, "2": {"correct": 9, "total": 10}, "3": {"correct": 2, "total": 10}}}}}}
        self.kv = KV()

    def round_top(self, rid, ch, limit=10):
        return [{"uid": "1"}], 3


class TG:
    def __init__(self): self.sent = []
    def send_message(self, c, t, **k): self.sent.append((str(c), t, k.get("buttons")))
    def polite_gap(self, a=False): pass


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); gate.STATE = pathlib.Path(self.tmp.name) / "g.json"
        config.BOT_USERNAME = "StudentUpBot"

    def tearDown(self): self.tmp.cleanup()

    def test_counts_footer_buttons(self):
        m = M(); c = gate.counts(m)
        self.assertEqual((c["registered"], c["locked_players"], c["locked_points"], c["pending"]), (1, 2, 50, 1))
        f = gate.footer(m); self.assertIn("1 registered", f); self.assertIn("50 pts locked", f)
        self.assertIn("t.me/StudentUpBot?start=quiz", gate.cta_buttons()[0][0][1])
        self.assertIn("register", gate.alert_block(m).lower())
        self.assertIn("2 players", gate.top10_tail(m, 2))

    def test_chase_days(self):
        m = M(); tg = TG()
        d0 = date(2026, 9, 13)
        self.assertEqual(gate.chase_locked(m, tg, today=d0), 0)          # day 0: first_seen recorded, no DM
        self.assertEqual(gate.chase_locked(m, tg, today=date(2026, 9, 14)), 2)   # day 1: uid 2 (locked) + 3 (pending); 4 blocked
        self.assertEqual(gate.chase_locked(m, tg, today=date(2026, 9, 14)), 0)   # once per day
        self.assertEqual(gate.chase_locked(m, tg, today=date(2026, 9, 17)), 0)   # day 4 not a chase day
        self.assertEqual(gate.chase_locked(m, tg, today=date(2026, 9, 20)), 2)   # day 7
        self.assertIn("40 points", tg.sent[0][1]); self.assertEqual(tg.sent[0][2][0][0][1], "gate:reg")

    def test_after_round_dms(self):
        m = M(); tg = TG()
        self.assertEqual(gate.after_round_dms(m, tg, "R1", "TSPSC", 10), 2)   # uids 2 and 3
        self.assertIn("9/10", tg.sent[0][1]); self.assertIn("40 points", tg.sent[0][1])
        self.assertEqual(gate.after_round_dms(m, tg, "R1", "TSPSC", 10), 0)   # once per day
        self.assertIn("Gate:", gate.owner_line(m))


if __name__ == "__main__":
    unittest.main()
