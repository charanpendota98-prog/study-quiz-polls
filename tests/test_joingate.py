import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, joingate as J


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        self.members = {"1": {"registered": True, "name": "Ravi", "exam": "TSPSC", "points": 0},
                        "2": {"registered": True, "name": "Sita", "exam": "Banking", "points": 0}}
    def _get(self, u): return self.members.setdefault(str(u), {})


class _TG:
    def __init__(self, member_of): self.member_of = member_of
    def _call(self, m, p):
        key = p["chat_id"]
        return {"result": {"status": "member" if key in self.member_of else "left"}}


class TestJoinGate(unittest.TestCase):
    def test_verify_awards_once_and_gates(self):
        m = _Members()
        self.assertEqual(J.required_for(m.members["1"]), ["CURRENT", "TSPSC"])
        hub = config.channel_chat_id("CURRENT"); ts = config.channel_chat_id("TSPSC")
        ok, txt = J.verify(_TG({hub}), m, "1")
        self.assertFalse(ok); self.assertIn("+30", txt); self.assertIn("ఇంకా join కాలేదు", txt)
        self.assertEqual(m.members["1"]["points"], 30)
        ok, txt = J.verify(_TG({hub, ts}), m, "1")
        self.assertTrue(ok); self.assertEqual(m.members["1"]["points"], 60)
        ok, txt = J.verify(_TG({hub, ts}), m, "1")
        self.assertTrue(ok); self.assertEqual(m.members["1"]["points"], 60); self.assertIn("అన్ని channels", txt)
        self.assertTrue(J.joined_all(m.members["1"])); self.assertFalse(J.joined_all(m.members["2"]))
        self.assertEqual(J.nudge_targets(m), ["2"])
        b = J.buttons(m.members["2"])
        self.assertTrue(any(cb == "join:verify" for row in b for _, cb in row))
        self.assertTrue(any(str(cb).startswith("url:https://t.me/") for row in b for _, cb in row))
        self.assertIn("Verify", J.nudge_text(m.members["2"]))


if __name__ == "__main__":
    unittest.main()
