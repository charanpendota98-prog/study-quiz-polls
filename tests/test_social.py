import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, social as S, partners as P


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        now = datetime.now(config.IST).isoformat()
        self.members = {"1": {"registered": True, "name": "Ravi", "district": "Warangal", "points": 100, "exam": "TSPSC", "registered_at": now, "last_active": now},
                        "2": {"registered": True, "name": "Sita", "district": "Warangal", "points": 0, "exam": "SSC", "registered_at": now},
                        "9": {"registered": False}}
    def _get(self, uid): return self.members.setdefault(str(uid), {})


class TestSocial(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self._o = (S.PATH, P.PATH)
        S.PATH = self.tmp / "s.json"; P.PATH = self.tmp / "p.json"
    def tearDown(self):
        S.PATH, P.PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_campaign_claim_once_cap_superfan(self):
        m = _Members()
        code = S.new_campaign("ig", "Polity reel", 30, cap=1)
        self.assertIn(f"/claim {code}", S.auto_dm_text(code))
        self.assertFalse(S.claim(m, "9", code)[0])                       # unregistered
        ok, txt = S.claim(m, "1", code); self.assertTrue(ok); self.assertIn("+30", txt)
        self.assertEqual(m.members["1"]["points"], 130)
        self.assertFalse(S.claim(m, "1", code)[0])                       # once
        self.assertFalse(S.claim(m, "2", code)[0])                       # cap reached
        self.assertFalse(S.claim(m, "2", "SU-NOPE")[0])
        for i in range(4):
            S.claim(m, "1", S.new_campaign("yt", f"v{i}", 10))
        self.assertEqual(m.members["1"]["points"], 130 + 40 + S.SUPERFAN_PTS)
        self.assertTrue(m.members["1"]["follows"]["yt"])
        self.assertIn("claims", S.campaign_stats())

    def test_screenshot_queue_and_review(self):
        m = _Members()
        self.assertIn("received", S.queue_screenshot("2", "Sita", "fid"))
        self.assertIn("already", S.queue_screenshot("2", "Sita", "fid"))
        self.assertEqual(len(S.pending_screenshots()), 1)
        S.review_screenshot(m, "2", "ig", True)
        self.assertEqual(m.members["2"]["points"], S.SCREENSHOT_PTS)
        self.assertEqual(S.pending_screenshots(), [])
        self.assertIn("already verified", S.queue_screenshot("2", "Sita", "fid"))

    def test_leads_pitch_opening(self):
        m = _Members()
        self.assertIsNone(S.add_lead("1", "Warangal", "bad"))
        lead = S.add_lead("1", "Warangal", "Sri Coaching | coaching | 98xxx | Hanamkonda")
        self.assertIn("Sri Coaching", S.leads_text("Warangal"))
        pid = P.add_partner("Sri Coaching", "Warangal", "coaching", merchant_uid="7")
        self.assertIsNotNone(S.convert_lead(m, lead["id"], pid))
        self.assertIsNone(S.convert_lead(m, lead["id"], pid))
        self.assertEqual(m.members["1"]["points"], 100 + S.SCOUT_CONVERT_PTS)
        pitch = S.district_pitch(m, "Warangal")
        self.assertIn("2 registered", pitch); self.assertIn("TSPSC 1", pitch)
        self.assertIn("Warangal — 2", S.weekly_partner_call(m))
        # opening package: tag on card + ≈2× frequency
        o1 = P.add_offer(pid, "a", "a", 10)
        p2 = P.add_partner("Old Shop", "Warangal", "shop"); o2 = P.add_offer(p2, "b", "b", 10)
        self.assertTrue(P.set_opening(pid, 7))
        d = P._load(); self.assertIn("NEW OPENING", P.ad_card(d["partners"][pid], d["offers"][o1]))
        seq = [P.next_ad()[0]["id"] for _ in range(6)]
        self.assertGreaterEqual(seq.count(o1), 4)


if __name__ == "__main__":
    unittest.main()
