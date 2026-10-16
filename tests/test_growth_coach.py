# -*- coding: utf-8 -*-
"""🤝 Referrals + 📩 Personal Coach reports + 📲 PWA.

Pins: referral bonus (once, not self), referral code in profile, top
referrers board, detailed my_report, Telegram report text builder,
dashboard send-reports wiring (BOT_TOKEN guard), student manifest + SW.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import portal  # noqa: E402


class _KV:
    def save(self):
        pass


class FakeMembers:
    def __init__(self):
        self.d = {}
        self.members = self.d
        self.kv = _KV()

    def _get(self, uid):
        return self.d.setdefault(str(uid), {"topics": {}, "points": 0,
                                            "review": [], "streak": 0})

    def award_answer(self, uid, username="", correct=True, topic="", qid=""):
        m = self._get(uid)
        t = m.setdefault("topics", {}).setdefault(
            (topic or "general").lower(), {"correct": 0, "total": 0})
        t["total"] += 1
        if correct:
            t["correct"] += 1
            m["points"] = m.get("points", 0) + 10
        return {}


class TestReferralReport(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        portal.PATH = self._old

    def _reg(self, name, phone, ref=""):
        ok, inf = portal.register_student(self.mem, name, phone,
                                          "Guntur", "groups", ref)
        assert ok, inf
        return inf

    def test_referral_bonus_once_and_not_self(self):
        a = self._reg("Anitha", "9812345601")
        code = a["ref_code"]
        self.assertEqual(code, portal._ref_code("w9812345601"))
        # friend joins with code → Anitha gets bonus
        b = self._reg("Ravi", "9812345602", ref=code)
        self.assertEqual(b["referred_by"], "Anitha")
        self.assertEqual(self.mem.d["w9812345601"]["points"], portal.REF_BONUS)
        self.assertEqual(self.mem.d["w9812345601"]["referrals"], 1)
        # self-referral gives nothing
        c = self._reg("Self", "9812345603", ref=portal._ref_code("w9812345603"))
        self.assertEqual(c["referred_by"], "")
        self.assertEqual(self.mem.d["w9812345603"].get("points", 0), 0)
        # same friend re-registering doesn't re-pay
        self._reg("Ravi", "9812345602", ref=code)
        self.assertEqual(self.mem.d["w9812345601"]["points"], portal.REF_BONUS)
        # top referrers board
        st = portal.state(self.mem, b["token"])
        self.assertEqual(st["top_referrers"][0]["name"], "Anitha")
        self.assertEqual(st["student"]["ref_code"], b["ref_code"])

    def test_my_report_and_text(self):
        a = self._reg("Anitha", "9812345601")
        ok, inf = portal.practice_start(self.mem, a["token"], "smart")
        assert ok
        portal.practice_answer(self.mem, a["token"], inf["run_id"], 0, 0)
        rep = portal.my_report(self.mem, a["token"])
        self.assertIsNotNone(rep)
        self.assertGreaterEqual(len(rep["topics"]), 1)
        self.assertEqual(rep["student"]["name"], "Anitha")
        txt = portal.report_text(self.mem, "w9812345601",
                                 "https://quiz.studentup.in/portal")
        self.assertIn("Anitha", txt)
        self.assertIn("quiz.studentup.in", txt)
        self.assertIn("Weak topics", txt)
        self.assertIsNone(portal.my_report(self.mem, "bad"))

    def test_dashboard_growth_wiring(self):
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/portal/report"', "portal.my_report",
                       '"/api/portal/admin/send_reports"', "portal.report_text",
                       "BOT_TOKEN", "config.BOT_TOKEN",
                       '"/sw.js"', "serviceWorker.register('/sw.js')",
                       '"start_url": "/portal"', "ref-link", "loadReport",
                       "top_referrers", "sendPersonalReports"):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
