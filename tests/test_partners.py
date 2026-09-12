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


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._o = (P.PATH, rewards.CATALOG_PATH, rewards.LEDGER_PATH)
        P.PATH = self.tmp / "p.json"; rewards.CATALOG_PATH = self.tmp / "c.json"; rewards.LEDGER_PATH = self.tmp / "l.json"
    def tearDown(self):
        P.PATH, rewards.CATALOG_PATH, rewards.LEDGER_PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)

class TestPartners(_Base):
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
        self.assertEqual(m.members["1"]["points"], 500 + P.REF_ACTIVATED + 3 * P.REF_MENTOR_PTS)
        self.assertIsNone(P.on_round_played(m, "2"))                     # activation once only (mentor share continues)
        self.assertIn("Smart Referral", P.referral_explainer("1", "https://t.me/x?start=ref1"))


class TestAdvancedPartners(_Base):
    def test_exam_checkin_unlocks_and_flash_and_mentor(self):
        m = _Members()
        pid = P.add_partner("Hotel Raju", "Warangal", "food", merchant_uid="900")
        o = P.add_offer(pid, "ఫ్రీ లంచ్", "Free lunch", 50, kind="examday", exam="TSPSC",
                        exam_from=P._now().date().isoformat(), exam_to=P._now().date().isoformat())
        # in window, right exam, but not checked in → locked
        row = [r for r in P.offers_for(m, "1") if r[0]["id"] == o][0]
        self.assertFalse(row[2]); self.assertIn("examdone", row[3])
        prompts = P.examday_prompts(m)
        self.assertTrue(any(u == "1" for u, _, _ in prompts))
        ok, txt = P.exam_checkin(m, "1", "tspsc")
        self.assertTrue(ok); self.assertIn("+25", txt)
        self.assertEqual(m.members["1"]["points"], 500 + P.EXAM_CHECKIN_PTS)
        ok2, _ = P.exam_checkin(m, "1", "TSPSC"); self.assertFalse(ok2)      # once/day
        row = [r for r in P.offers_for(m, "1") if r[0]["id"] == o][0]
        self.assertTrue(row[2])
        self.assertFalse(any(u == "1" for u, _, _ in P.examday_prompts(m)))  # no re-prompt
        # flash: sorts first, tagged, stock respected, ad picks it first
        P.add_offer(pid, "కాఫీ ఫ్రీ", "Free coffee", 20, kind="discount")
        fo = P.add_offer(pid, "50% off", "50% off", 30, flash_hours=2, total=1)
        rows = P.offers_for(m, "1")
        self.assertEqual(rows[0][0]["id"], fo)
        self.assertIn("⚡", P._flash_tag(rows[0][0]))
        ad_o, _ = P.next_ad(); self.assertEqual(ad_o["id"], fo)
        self.assertIn("FLASH", P.ad_card(_, ad_o))
        # merchant dashboard + weekly reports
        self.assertIn("Hotel Raju", P.merchant_dashboard("900"))
        self.assertIn("🔒", P.merchant_dashboard("123"))
        self.assertEqual(len(P.weekly_merchant_reports()), 1)
        # category filter
        self.assertEqual(P.offers_for(m, "1", category="salon"), [])
        self.assertEqual(len(P.offers_for(m, "1", category="food")), 3)

    def test_mentor_share_and_weekly_top(self):
        m = _Members()
        m.members["2"]["referred_by"] = "1"; m.members["2"]["registered_at"] = P._now().isoformat()
        base = m.members["1"]["points"]
        for _ in range(2):
            self.assertIsNone(P.on_round_played(m, "2"))
        self.assertEqual(m.members["1"]["points"], base + 2 * P.REF_MENTOR_PTS)
        act = P.on_round_played(m, "2")
        self.assertEqual(act["bonus"], P.REF_ACTIVATED)
        self.assertEqual(m.members["1"]["points"], base + 3 * P.REF_MENTOR_PTS + P.REF_ACTIVATED)
        for _ in range(100):                                  # mentor cap
            P.on_round_played(m, "2")
        self.assertEqual(m.members["1"]["points"], base + P.REF_MENTOR_CAP + P.REF_ACTIVATED)
        txt, win = P.weekly_top_recruiters(m)
        self.assertEqual(win, "1"); self.assertIn("TOP RECRUITERS", txt)
        self.assertEqual(m.members["1"]["points"], base + P.REF_MENTOR_CAP + P.REF_ACTIVATED + P.REF_WEEKLY_TOP)
        self.assertEqual(P.weekly_top_recruiters(m), (None, None))   # counters reset


if __name__ == "__main__":
    unittest.main()


class TestScopes(_Base):
    def test_state_mandal_scope_and_digest(self):
        m = _Members()
        m.members["1"]["state_code"] = "TS"; m.members["1"]["mandal"] = "Hanamkonda"
        m.members["2"]["state_code"] = "AP"; m.members["3"]["state_code"] = "TS"
        ts = P.add_partner("Big Bazaar TS", "TS", "shop"); o_ts = P.add_offer(ts, "10% off", "10% off", 40)
        al = P.add_partner("Amazon-ish", "ALL", "tech"); o_al = P.add_offer(al, "5% off", "5% off", 20)
        loc = P.add_partner("Raju Xerox", "Warangal", "tech", mandal="Hanamkonda"); o_loc = P.add_offer(loc, "free print", "free print", 60)
        ids1 = [r[0]["id"] for r in P.offers_for(m, "1")]
        self.assertEqual(ids1[0], o_loc)                                   # mandal first
        self.assertEqual(set(ids1), {o_ts, o_al, o_loc})
        self.assertEqual({r[0]["id"] for r in P.offers_for(m, "2")}, {o_al})   # AP: no TS, no Warangal
        self.assertIn("state-wide", P.scope_label(P._load()["partners"][ts]))
        self.assertIn("Hanamkonda mandal", P.scope_label(P._load()["partners"][loc]))
        self.assertEqual(set(P.district_targets(m, "TS", partner={"district": "TS"})), {"1", "3"})
        self.assertEqual(set(P.district_targets(m, "ALL", partner={"district": "ALL"})), {"1", "2", "3"})
        txt, btns = P.digest_for_member(m, "1", 500)
        self.assertIn("🏠", txt); self.assertEqual(len(btns), 3); self.assertTrue(btns[0][0][1].startswith("poffer:"))
        self.assertIsNone(P.digest_for_member(m, "99", 0)[0])
        ch = P.digest_for_channel(m)
        self.assertIn("TS+AP", ch); self.assertIn("start=offers", ch); self.assertIn("Warangal/Hanamkonda", ch)
        self.assertIn("StudentUp —", P.whatsapp_post(m))
