# -*- coding: utf-8 -*-
"""📜 PYQ Harvest & Import Center + 🎯 Practice 2.0 + 📢 Updates.

Pins: CSV import of REAL previous-year questions (validate + dedupe +
provenance into pyq_bank), harvest/add-paper dashboard wiring, portal
Smart/Topic/Revision practice with instant feedback, notices on portal &
public /updates, streak surfaced in profile.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import portal, pyq  # noqa: E402

CSV_OK = """question,question_te,option1,option1_te,option2,option2_te,option3,option3_te,option4,option4_te,answer,explanation,exam,year,channel,topic
"Drafting Committee chairman evaru?","డ్రాఫ్టింగ్ కమిటీ చైర్మన్ ఎవరు?","B. R. Ambedkar","బి. ఆర్. అంబేద్కర్","Jawaharlal Nehru","జవహర్‌లాల్ నెహ్రూ","Rajendra Prasad","రాజేంద్ర ప్రసాద్","Sardar Patel","సర్దార్ పటేల్",A,"Dr B. R. Ambedkar chaired it.","SSC CGL",2022,SSC,polity
"Capital of Australia enti?","ఆస్ట్రేలియా రాజధాని ఏది?","Sydney","సిడ్నీ","Canberra","కాన్‌బెర్రా","Melbourne","మెల్‌బోర్న్","Perth","పెర్త్",2,"Canberra is the capital.","SSC CGL",2022,SSC,geography
"Bad answer row?","చెడు వరుస?","One","ఒకటి","Two","రెండు","Three","మూడు","Four","నాలుగు",9,"x","SSC",2022,SSC,general
"""


class TestPyqImport(unittest.TestCase):
    def setUp(self):
        self._old = pyq.PYQ_BANK_FILE
        self._oldp = pyq.PENDING_FILE
        self._tmp = tempfile.mkdtemp()
        pyq.PYQ_BANK_FILE = Path(self._tmp) / "pyq_bank.json"
        pyq.PENDING_FILE = Path(self._tmp) / "pyq_pending.json"

    def tearDown(self):
        pyq.PYQ_BANK_FILE = self._old
        pyq.PENDING_FILE = self._oldp

    def test_english_only_rows_park_pending(self):
        csv_text = ("question,option1,option2,option3,option4,answer,exam,year,channel,topic\n"
                    "\"Largest planet in our solar system?\",\"Jupiter\",\"Saturn\",\"Earth\",\"Mars\",1,"
                    "\"SSC CGL\",2023,SSC,science\n")
        res = pyq.import_csv(csv_text, rebuild=False)
        self.assertEqual(res["added"], 0)          # Telugu lekunda bank loki veyyamu
        self.assertEqual(res["pending_translation"], 1)
        import json
        parked = json.loads(pyq.PENDING_FILE.read_text(encoding="utf-8"))
        self.assertEqual(len(parked["questions"]), 1)

    def test_import_validate_dedupe_provenance(self):
        res = pyq.import_csv(CSV_OK, rebuild=False)
        self.assertEqual(res["added"], 2, res)
        self.assertEqual(len(res["errors"]), 1)          # bad-answer row
        self.assertIn("answer", res["errors"][0])
        import json
        data = json.loads(pyq.PYQ_BANK_FILE.read_text(encoding="utf-8"))
        q0 = data["questions"][0]
        self.assertEqual(q0["source"], "pyq")
        self.assertEqual((q0["exam"], q0["year"]), ("SSC CGL", 2022))
        self.assertEqual(q0["answer_index"], 0)          # "A" → 0
        self.assertEqual(pyq.pyq_label(q0), "📜 SSC CGL 2022")
        # re-import = all duplicates skipped, no growth
        res2 = pyq.import_csv(CSV_OK, rebuild=False)
        self.assertEqual(res2["added"], 0)
        self.assertEqual(res2["skipped_dup"], 2)

    def test_dashboard_pyq_wiring(self):
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/pyq/status"', '"/api/pyq/harvest"',
                       '"/api/pyq/add_paper"', '"/api/pyq/import"',
                       "pyq.import_csv", "pyq.harvest", "pyq.add_paper",
                       'id="pyq-status"', "runPyqHarvest", "importPyqCsv",
                       "downloadPyqTemplate", '"/api/portal/admin/notices"',
                       "portal.add_notice", '"/updates"'):
            self.assertIn(needle, src)


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


class TestPortalPractice(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()
        ok, inf = portal.register_student(self.mem, "Anitha", "9812345601",
                                          "Guntur", "groups")
        assert ok, inf
        self.tok = inf["token"]

    def tearDown(self):
        portal.PATH = self._old

    def test_smart_practice_flow(self):
        ok, inf = portal.practice_start(self.mem, self.tok, "smart")
        self.assertTrue(ok, inf)
        self.assertEqual(len(inf["questions"]), 10)
        ok, res = portal.practice_answer(self.mem, self.tok, inf["run_id"], 0, 0)
        self.assertTrue(ok, res)
        self.assertIn("correct", res)              # instant feedback (practice)
        self.assertIn("answer_text", res)
        ok, res2 = portal.practice_answer(self.mem, self.tok, inf["run_id"], 0, 1)
        self.assertTrue(res2.get("already"))       # no double count
        st = portal.state(self.mem, self.tok)
        self.assertGreater(st["student"]["answered"], 0)

    def test_topics_and_notices_and_streak(self):
        topics = portal.topics_list()
        self.assertGreaterEqual(len(topics), 5)
        n = portal.add_notice("SSC CGL 2026 Notification", "Apply dates soon",
                              "https://ssc.gov.in")
        self.assertIsNotNone(n)
        st = portal.state(self.mem, self.tok)
        self.assertEqual(st["notices"][0]["title"], "SSC CGL 2026 Notification")
        self.mem.d["w9812345601"]["streak"] = 6
        st = portal.state(self.mem, self.tok)
        self.assertEqual(st["student"]["streak"], 6)

    def test_dashboard_practice_wiring(self):
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/portal/practice/start"', '"/api/portal/practice/answer"',
                       "portal.practice_start", "startPractice", "view-prc",
                       "notice-card", "rev-btn"):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
