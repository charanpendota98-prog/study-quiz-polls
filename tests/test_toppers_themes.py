# -*- coding: utf-8 -*-
"""👑 Toppers Week/Month/Year + 🎨 Themes.

Pins: dated points ledger feeds toppers (old entries excluded), names +
district in rows, toppers in portal state + public /toppers page, daily
paper PYQ count, theme switcher wiring on portal and public site.
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


class TestToppers(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        portal.PATH = self._old

    def test_ledger_and_periods(self):
        ok, a = portal.register_student(self.mem, "Anitha", "9812345601", "Guntur", "groups")
        ok, b = portal.register_student(self.mem, "Ravi", "9812345602", "Warangal", "ssc")
        d0 = portal._load()

        def correct_choice(run_id, uid, i):
            run = d0["practice"][run_id]
            q = run["qs"][i]
            _o, perm = portal._display(q, f"{run_id}:{i}")
            return perm.index(q["answer_index"])

        ok, s = portal.practice_start(self.mem, a["token"], "smart")
        d0 = portal._load()
        for i in range(3):   # Anitha: 3 correct
            portal.practice_answer(self.mem, a["token"], s["run_id"], i,
                                   correct_choice(s["run_id"], a["uid"], i))
        ok, s2 = portal.practice_start(self.mem, b["token"], "smart")
        d0 = portal._load()
        cc = correct_choice(s2["run_id"], b["uid"], 0)
        portal.practice_answer(self.mem, b["token"], s2["run_id"], 0,
                               (cc + 1) % 4)   # Ravi: deliberately wrong
        # Anitha's real correct count from the paper decides pts; compare ordering only
        wk = portal.toppers(self.mem, "week")
        self.assertTrue(wk)
        self.assertEqual(wk[0]["name"], "Anitha")
        self.assertEqual(wk[0]["district"], "Guntur")
        self.assertGreater(wk[0]["pts"], 0)
        # old ledger entries (last year) never appear in any period
        d = portal._load()
        d["ledger"].append({"uid": "w9812345602", "pts": 9999, "date": "2020-01-01"})
        portal._save(d)
        for per in ("week", "month", "year"):
            rows = portal.toppers(self.mem, per)
            self.assertLess(rows[0]["pts"], 9999)
        # state carries all periods + daily PYQ count
        st = portal.state(self.mem, a["token"])
        self.assertEqual(set(st["toppers"]), {"week", "month", "year"})
        paper = portal._load()["days"][portal._today()]["qs"]
        self.assertEqual(st["daily"]["pyq_count"],
                         sum(1 for q in paper if q.get("source") == "pyq"))

    def test_wiring_and_public_page(self):
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/toppers"', "portal.toppers_all", "__TOP_WEEK__",
                       "Toppers of the Week", "showToppers", "setTheme",
                       "su_theme", "theme-ocean", "theme-light",
                       "pyq_count"):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
