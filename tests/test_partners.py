import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, partners as P, rewards


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        now = datetime.now(config.IST).isoformat()
        self.members = {"1": {"registered": True, "name": "Ravi", "district": "Warangal", "points": 500, "exam": "TSPSC", "registered_at": now},
                        "2": {"registered": True, "name": "Sita", "district": "Guntur", "points": 500, "exam": "SSC", "registered_at": now, "referred_by": "1"},
                        "3": {"registered": True, "name": "Kiran", "district": "Warangal", "points": 50, "exam": "BANKING", "registered_at": now}}
    def _get(self, uid): return self.members.setdefault(str(uid), {})


class TestPartners(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._o = (P.PATH, rewards.CATALOG_PATH, rewards.LEDGER_PATH)
        P.PATH = self.tmp / "p.json"; rewards.CATALOG_PATH = self.tmp / "c.json"; rewards.LEDGER_PATH = self.tmp / "l.json"
    def tearDown(self):
        P.PATH, rewards.CATALOG_PATH, rewards.LEDGER_PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)

    def test_district_targeting_and_examday(self):
        m = _Members()
        pid = P.add_partner("Sri Coaching", "Warangal", "coaching", "98xxx", merchant_uid="777", address="Hanamkonda")
        o1 = P.add_offer(pid, "టెస్ట్ సిరీస్ ₹200 off", "₹200 off test series", 150)
        today = datetime.now(config.IST).date()
        o2 = P.add_offer(pid, "Exam day: free doubt session", "Exam-day free session", 100, kind="examday", exam="TSPSC",
                         exam_from=str(today + timedelta(days=3)), exam_to=str(today + timedelta(days=5)))
        self.assertEqual(len(P.offers_for(m, "2")), 0)                  # Guntur sees nothing
        rows = P.offers_for(m, "1")
        self.assertEqual(len(rows), 2)
        exam = [r for r in rows if r[0]["id"] == o2][0]
        self.assertFalse(exam[2]); self.assertIn("unlock", exam[3])    # locked till exam window
        k = [r for r in P.offers_for(m, "3") if r[0]["id"] == o2][0]
        self.assertFalse(k[2]); self.assertIn("TSPSC", k[3])          # banking aspirant sees it locked with reason

    def test_redeem_verify_by_merchant_only(self):
        m = _Members()
        pid = P.add_partner("Cafe Aroma", "Warangal", "food", merchant_uid="777")
        oid = P.add_offer(pid, "Free coffee", "Free coffee with meal", 100)
        ok, txt, merch = P.redeem(m, "1", oid, rewards)
        self.assertTrue(ok); self.assertIn("PT-", txt); self.assertEqual(merch[0], ["777"])
        code = [l for l in txt.splitlines() if l.startswith("Code:")][0].split("`")[1]
        self.assertEqual(rewards.balance(m, "1")["held"], 100)          # hold visible in wallet
        self.assertFalse(P.redeem(m, "1", oid, rewards)[0])            # per_member=1
        self.assertIn("🔒", P.verify(m, code, "999", set()))            # random user cannot verify
        res = P.verify(m, code, "777", set())
        self.assertTrue(res.startswith("✅")); self.assertEqual(m.members["1"]["points"], 400)
        self.assertIn("already USED", P.verify(m, code, "777", set()))
        self.assertIn("1 redeemed", P.partner_stats(pid))
        # insufficient points
        self.assertFalse(P.redeem(m, "3", P.add_offer(pid, "x", "x", 80), rewards)[0])

    def test_ads_rotate(self):
        pid = P.add_partner("A", "Warangal", "shop"); pid2 = P.add_partner("B", "Guntur", "salon")
        a = P.add_offer(pid, "a", "a", 10); b = P.add_offer(pid2, "b", "b", 10)
        first = P.next_ad()[0]["id"]; second = P.next_ad()[0]["id"]
        self.assertNotEqual(first, second)
        self.assertIn("StudentUp Partner", P.ad_card(*reversed(P.next_ad())) if False else P.ad_card(P._load()["partners"][pid], P._load()["offers"][a]))

    def test_smart_referral_activation(self):
        m = _Members()
        for _ in range(2):
            self.assertIsNone(P.on_round_played(m, "2"))
        act = P.on_round_played(m, "2")
        self.assertEqual(act["referrer"], "1"); self.assertEqual(act["bonus"], P.REF_ACTIVATED)
        self.assertEqual(m.members["1"]["points"], 500 + P.REF_ACTIVATED)
        self.assertIsNone(P.on_round_played(m, "2"))                     # once only
        self.assertIn("Smart Referral", P.referral_explainer("1", "https://t.me/x?start=ref1"))


if __name__ == "__main__":
    unittest.main()
