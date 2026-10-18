# -*- coding: utf-8 -*-
"""🚀 210X: Section Report + District Deep-Dive + Bank-Gap Planner.

Pins (probe-verified on the real bank):
  • mock submit + attempt analysis carry exam-subject sections that
    reconcile exactly with the attempt totals.
  • district deep-dive: honest rank/champion/overtake gaps from the
    members store (no invented students).
  • bank_gap_plan: exam-weight × thinness priorities; Banking
    reasoning (35% weight, 0 bank questions) must surface.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, brain  # noqa: E402


class _KV:
    def save(self):
        pass

    def save_debounced(self):
        pass


class _Members:
    def __init__(self):
        self.members = {}
        self.kv = _KV()

    def _get(self, uid):
        return self.members.setdefault(str(uid), {
            "name": "Adv210 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": [], "registered": True})

    def award_answer(self, uid, username="", correct=True, topic="",
                     qid=""):
        return {"points": 0}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"
        self.mem = _Members()

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf

    def _reg(self, name, phone, points):
        ok, info = portal.register_student(
            self.mem, "Adv210 " + name, phone, "Guntur", "railway")
        self.assertTrue(ok, info)
        self.mem.members["w" + phone]["points"] = points
        self.mem.members["w" + phone]["registered"] = True
        return info["token"]


class TestSections210(_Base):
    def test_sections_reconcile_submit_and_analysis(self):
        tok = self._reg("Sec", "9822000501", 0)
        ok, st = portal.mock_start(self.mem, tok, "railway")
        self.assertTrue(ok, st)
        self.assertIn("subject", st["questions"][0])
        run = portal._load()["mocks"][st["run_id"]]
        answers = {}
        for i, q in enumerate(run["qs"]):
            _o, perm = portal._display(q, f"{st['run_id']}:{i}")
            # alternate: even correct, odd wrong -> mixed sections
            want = q["answer_index"] if i % 2 == 0 else (
                q["answer_index"] + 1) % 4
            answers[str(i)] = perm.index(want) if want in perm else 0
        ok, res = portal.mock_submit(self.mem, tok, st["run_id"], answers)
        self.assertTrue(ok, res)
        secs = res["sections"]
        self.assertTrue(secs)
        self.assertEqual(sum(r["total"] for r in secs), res["total"])
        self.assertEqual(sum(r["correct"] for r in secs), res["correct"])
        for r in secs:
            self.assertEqual(
                r["accuracy"],
                round(100 * r["correct"] / max(1, r["total"])))
        an = portal.attempt_analysis(self.mem, tok, st["run_id"])
        self.assertEqual(an["sections"], secs)


class TestDistrictDeep210(_Base):
    def test_rank_champion_and_chase_gaps(self):
        self._reg("Champ", "9822000502", 900)
        self._reg("Mid", "9822000503", 500)
        tok_me = self._reg("Me", "9822000504", 300)
        self._reg("Low", "9822000505", 100)
        dd = portal.district_deep(self.mem, tok_me)
        self.assertEqual(dd["my_rank"], 3)
        self.assertEqual(dd["students_in_district"], 4)
        self.assertEqual(dd["champion"]["points"], 900)
        gaps = sorted(c["gap"] for c in dd["chase"])
        self.assertEqual(gaps, [200, 600])
        self.assertTrue(dd["board"])

    def test_district_leader_has_no_chase(self):
        tok = self._reg("Top", "9822000506", 700)
        self._reg("Other", "9822000507", 100)
        dd = portal.district_deep(self.mem, tok)
        self.assertEqual(dd["my_rank"], 1)
        self.assertEqual(dd["chase"], [])


class TestBankGapPlan210(unittest.TestCase):
    def test_priorities_sorted_and_banking_reasoning_surfaces(self):
        gaps = portal.bank_gap_plan(12)
        self.assertTrue(gaps)
        prios = [g["priority"] for g in gaps]
        self.assertEqual(prios, sorted(prios, reverse=True))
        hit = [g for g in gaps
               if g["channel"] == "BANKING" and g["subject"] == "reasoning"]
        self.assertTrue(hit)
        self.assertEqual(hit[0]["bank_q"], 0)
        self.assertEqual(hit[0]["need"], 50)
        for g in gaps:
            self.assertEqual(g["need"], max(0, 50 - g["bank_q"]))


class TestWiring210(unittest.TestCase):
    def test_dashboard_wiring(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        for needle in ("/api/portal/district", "function loadDistrict",
                       "District Deep-Dive", "an.sections",
                       "d.bank_gaps210", "an.sections.map"):
            self.assertIn(needle, src)
        psrc = (ROOT / "scripts" / "core" / "portal.py").read_text()
        for needle in ("def district_deep", "def bank_gap_plan",
                       "def _section_rows"):
            self.assertIn(needle, psrc)


if __name__ == "__main__":
    unittest.main()
