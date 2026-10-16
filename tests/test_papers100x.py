# -*- coding: utf-8 -*-
"""📜 100X Advanced: ALL sources registry + Previous Papers full-test
mode + Today's Smart Plan + public /papers & /exams pages.

Pins:
  • registry sources anni https/well-formed, generator rebuild file ni
    shrink cheyyadu (sources count malli taggakudadhu)
  • pyq.papers_index real bank nunchi honest paper sets isthundi
  • portal.paper_start -> mock submit round trip (score + review)
  • today_plan checklist state lo vastundi
  • public pages /papers /exams dashboard source lo wired
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, pyq  # noqa: E402


class TestRegistryComplete(unittest.TestCase):
    def test_all_sources_wellformed_and_growing(self):
        reg = json.loads((ROOT / "data" / "collector_sources.json")
                         .read_text(encoding="utf-8"))
        srcs = reg["sources"]
        self.assertGreaterEqual(len(srcs), 580)
        names = set()
        official = 0
        for s in srcs:
            self.assertNotIn(s["name"], names)
            names.add(s["name"])
            u = s.get("feed") or s.get("url") or ""
            self.assertTrue(u.startswith("https://"), s["name"])
            if "Official" in s["name"]:
                official += 1
            if s.get("enabled"):
                self.assertEqual(s.get("audit", {}).get("status"), "live",
                                 s["name"])
        self.assertGreaterEqual(official, 60)

    def test_rebuild_never_shrinks_registry(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "rb", str(ROOT / "scripts" / "rebuild_registry.py"))
        rb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rb)
        data = rb.build()
        self.assertEqual(rb.validate(data), [])
        reg = json.loads((ROOT / "data" / "collector_sources.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(len(data["sources"]), len(reg["sources"]))


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
            "points": 0, "total": 0, "topics": {}, "review": []})


class TestPapersMode(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp = portal.PATH
        portal.PATH = self.tmp / "portal.json"

    def tearDown(self):
        portal.PATH = self._pp

    def test_papers_index_honest(self):
        idx = pyq.papers_index(min_q=5)
        self.assertGreaterEqual(len(idx), 5)
        for row in idx:
            self.assertGreaterEqual(row["count"], 5)
            self.assertEqual(len(row["ids"]), row["count"])
            self.assertTrue(row["exam"])

    def test_catalog_and_state(self):
        cat = portal.paper_catalog()
        self.assertTrue(cat)
        mem = _Members()
        ok, info = portal.register_student(
            mem, "Paper Tester", "9812345680", "Guntur", "ssc")
        self.assertTrue(ok, info)
        st = portal.state(mem, info["token"])
        self.assertTrue(st["papers"])
        self.assertEqual(st["today_plan"]["total"], 4)
        self.assertIn("daily", [t["key"] for t in st["today_plan"]["tasks"]])

    def test_full_paper_attempt_roundtrip(self):
        mem = _Members()
        ok, info = portal.register_student(
            mem, "Paper Tester", "9812345681", "Guntur", "ssc")
        self.assertTrue(ok, info)
        cat = portal.paper_catalog()
        top = cat[0]
        ok2, run = portal.paper_start(mem, info["token"],
                                      top["exam"], top.get("year") or "",
                                      top.get("paper") or "")
        self.assertTrue(ok2, run)
        self.assertEqual(len(run["questions"]), top["count"])
        # answer all with the student's displayed correct option
        d = portal._load()
        mrun = d["mocks"][run["run_id"]]
        answers = {}
        for i, q in enumerate(mrun["qs"]):
            _opts, perm = portal._display(q, f"{run['run_id']}:{i}")
            answers[str(i)] = perm.index(q["answer_index"])
        ok3, res = portal.mock_submit(mem, info["token"], run["run_id"],
                                      answers)
        self.assertTrue(ok3, res)
        self.assertEqual(res["correct"], top["count"])
        self.assertEqual(res["total"], top["count"])

    def test_unknown_paper_rejected(self):
        mem = _Members()
        ok, info = portal.register_student(
            mem, "Paper Tester", "9812345682", "Guntur", "ssc")
        self.assertTrue(ok, info)
        ok2, msg = portal.paper_start(mem, info["token"],
                                      "NO SUCH EXAM", "1999", "")
        self.assertFalse(ok2)


class TestPublicAdvancedPages(unittest.TestCase):
    def test_wiring(self):
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        for needle in ("/papers", "/exams", "renderPapers",
                       "startPaper(", "/api/portal/paper/start",
                       "today_plan", "renderPlan("):
            self.assertIn(needle, dash)


if __name__ == "__main__":
    unittest.main()
