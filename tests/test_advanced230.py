# -*- coding: utf-8 -*-
"""🚀 230X: exam harvest targets + sectional timing + materials vault.

Pins (probe-verified):
  • harvest_targets ranks BANKING reasoning (0 bank Qs, 35% weight)
    first thanks to the 230X reasoning/aptitude subject boost, and
    every job carries a runnable pyq command; dry runs stay dry.
  • mock_submit decorates 210X sections with per-section seconds,
    budget (60s per question) and over-budget flags.
  • Materials Vault: goal filter, free = owned, points unlock spends
    exactly once, insufficient points is an honest refusal, and the
    file guard rejects traversal / non-allowlisted extensions.
  • score_intelligence composes forecast + rank + advice text.
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
            "name": "Adv230 Tester", "district": "Guntur", "points": 0,
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

    def _reg(self, name="Vault", phone="9822000901", points=0):
        ok, info = portal.register_student(
            self.mem, "Adv230 " + name, phone, "Guntur", "railway")
        self.assertTrue(ok, info)
        self.mem.members["w" + phone]["points"] = points
        self.mem.members["w" + phone]["registered"] = True
        return info["token"]


class TestHarvestTargets230(unittest.TestCase):
    def test_reasoning_first_and_cmds_runnable(self):
        jobs = portal.harvest_targets(6)
        self.assertTrue(jobs)
        top = jobs[0]
        self.assertEqual((top["channel"], top["subject"]),
                         ("BANKING", "reasoning"))
        for j in jobs:
            self.assertEqual(j["cmd"], f"pyq harvest --only {j['channel']}")
            self.assertEqual(j["need"], max(0, 50 - j["bank_q"]))

    def test_analytics_carries_targets(self):
        mem = _Members()
        an = portal.portal_analytics(mem)
        self.assertIn("harvest_targets230", an)
        self.assertTrue(an["harvest_targets230"])


class TestSectionalTiming230(_Base):
    def test_sections_have_time_budget(self):
        tok = self._reg(points=0)
        ok, st = portal.mock_start(self.mem, tok, "railway")
        self.assertTrue(ok, st)
        run = portal._load()["mocks"][st["run_id"]]
        answers, times = {}, {}
        for i, q in enumerate(run["qs"]):
            _o, perm = portal._display(q, f"{st['run_id']}:{i}")
            answers[str(i)] = perm.index(q["answer_index"])
            times[str(i)] = 30
        ok, res = portal.mock_submit(self.mem, tok, st["run_id"],
                                     answers, times=times)
        self.assertTrue(ok, res)
        self.assertTrue(res["sections"])
        for s in res["sections"]:
            self.assertIn("seconds", s)
            self.assertEqual(s["budget_sec"], s["total"] * 60)
            self.assertEqual(s["seconds"], s["total"] * 30)
            self.assertFalse(s["over"])
        # blowing one section over budget flips the flag
        ok, st2 = portal.mock_start(self.mem, tok, "railway")
        run2 = portal._load()["mocks"][st2["run_id"]]
        a2, t2 = {}, {}
        for i, q in enumerate(run2["qs"]):
            _o, perm = portal._display(q, f"{st2['run_id']}:{i}")
            a2[str(i)] = perm.index(q["answer_index"])
            t2[str(i)] = 300
        ok, res2 = portal.mock_submit(self.mem, tok, st2["run_id"],
                                      a2, times=t2)
        self.assertTrue(any(s["over"] for s in res2["sections"]))


class TestMaterialsVault230(_Base):
    def test_unlock_spends_once_and_guards(self):
        tok = self._reg(points=500)
        item = portal.materials_add(
            self.mem, "Reasoning Tricks", "reasoning.pdf",
            goal="railway", subject="reasoning", cost=100)
        portal.materials_add(self.mem, "Free Notes", "notes.pdf",
                             goal="all", cost=0)
        cat = portal.materials_catalog(self.mem, tok)
        self.assertEqual(len(cat["items"]), 2)
        free = next(i for i in cat["items"] if i["cost"] == 0)
        self.assertTrue(free["owned"])
        ok, _msg = portal.materials_unlock(self.mem, tok, item["id"])
        self.assertTrue(ok)
        self.assertEqual(self.mem.members["w9822000901"]["points"], 400)
        ok, _ = portal.materials_unlock(self.mem, tok, item["id"])
        self.assertTrue(ok)  # already owned: no double charge
        self.assertEqual(self.mem.members["w9822000901"]["points"], 400)
        pricey = portal.materials_add(self.mem, "Big Pack", "big.pdf",
                                      goal="railway", cost=9999)
        ok, msg = portal.materials_unlock(self.mem, tok, pricey["id"])
        self.assertFalse(ok)
        self.assertIn("saripovu", msg)
        data, fname = portal.materials_file(self.mem, tok, pricey["id"])
        self.assertIsNone(data)  # not owned -> no file leak
        evil = portal.materials_add(self.mem, "Evil", "../../secret.py",
                                    goal="railway", cost=0)
        data, fname = portal.materials_file(self.mem, tok, evil["id"])
        self.assertIsNone(data)  # traversal/extension blocked

    def test_score_intelligence_advice(self):
        tok = self._reg(points=300)
        self.mem.members["w9822000901"]["topics"] = {
            "algebra": {"total": 12, "correct": 9}}
        si = portal.score_intelligence(self.mem, tok)
        self.assertIsNotNone(si)
        self.assertIn("Forecast", si["advice"])


class TestWiring230(unittest.TestCase):
    def test_dashboard_wiring(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        for needle in ("/api/portal/materials", "/api/portal/material_file",
                       "/api/portal/materials_unlock",
                       "/api/portal/score_intel", "/api/admin/harvest_run",
                       "/api/admin/materials_add", "function loadMaterials",
                       "function loadScoreIntel", "runHarvest230",
                       "harvest_targets230"):
            self.assertIn(needle, src)
        psrc = (ROOT / "scripts" / "core" / "portal.py").read_text()
        for needle in ("def harvest_targets", "def run_harvest_job",
                       "def materials_catalog", "def materials_unlock",
                       "def materials_file", "def score_intelligence"):
            self.assertIn(needle, psrc)


if __name__ == "__main__":
    unittest.main()
