# -*- coding: utf-8 -*-
"""🏆 Certificates + 🏙️ District League + 🌟 Hall of Fame.

Pins: only Top-3 exam winners can download a certificate PNG, district
league aggregates member points by district, public winners feed excludes
unfinished exams, badges surface in profile, dashboard wiring.
"""
import sys
import tempfile
import unittest
from datetime import timedelta
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
                                            "badges": [], "review": [],
                                            "streak": 0})

    def award_answer(self, uid, username="", correct=True, topic="", qid=""):
        m = self._get(uid)
        t = m.setdefault("topics", {}).setdefault(
            (topic or "general").lower(), {"correct": 0, "total": 0})
        t["total"] += 1
        if correct:
            t["correct"] += 1
            m["points"] = m.get("points", 0) + 10
        return {}


class TestFameLeague(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        portal.PATH = self._old

    def _reg(self, name, phone, district="Guntur"):
        ok, inf = portal.register_student(self.mem, name, phone, district, "groups")
        assert ok, inf
        return inf

    def test_district_league(self):
        self._reg("Anitha", "9812345601", "Guntur")
        self._reg("Ravi", "9812345602", "Guntur")
        self._reg("Kiran", "9812345603", "Warangal")
        self.mem.d["w9812345601"]["points"] = 300
        self.mem.d["w9812345602"]["points"] = 200
        self.mem.d["w9812345603"]["points"] = 900
        lg = portal.district_league(self.mem, "Guntur")
        self.assertEqual(lg["rows"][0]["name"], "Warangal")   # 900 > 500
        self.assertEqual(lg["rows"][1]["pts"], 500)           # 300+200
        self.assertEqual(lg["rows"][1]["students"], 2)
        self.assertEqual(lg["my_rank"], 2)
        tok = portal.register_student(self.mem, "A2", "9812345609",
                                      "Guntur", "groups")[1]["token"]
        st = portal.state(self.mem, tok)
        self.assertEqual(st["district_league"]["my_rank"], 2)

    def test_certificate_only_for_winners(self):
        st_time = (portal._now() - timedelta(minutes=5)).isoformat()
        e = portal.create_exam("Cert Test", "mixed", st_time, 30, 10)
        a = self._reg("Anitha", "9812345601")
        b = self._reg("Ravi", "9812345602")
        portal.exam_join(self.mem, a["token"], e["id"])
        portal.exam_join(self.mem, b["token"], e["id"])
        d = portal._load()
        q0 = d["exams"][e["id"]]["qs"][0]
        _o, perm = portal._display(q0, f"{e['id']}:w9812345601:0")
        portal.exam_answer(self.mem, a["token"], e["id"], 0,
                           perm.index(q0["answer_index"]))
        # not finished yet → no certificate
        self.assertIsNone(portal.exam_certificate(self.mem, a["token"], e["id"]))
        d = portal._load()
        d["exams"][e["id"]]["starts_at"] = (portal._now() - timedelta(hours=2)).isoformat()
        portal._save(d)
        try:
            import PIL  # noqa: F401
        except Exception:
            self.skipTest("pillow not installed")
        png = portal.exam_certificate(self.mem, a["token"], e["id"])
        self.assertTrue(png.startswith(b"\x89PNG"), "winner certificate PNG")
        self.assertIsNone(portal.exam_certificate(self.mem, b["token"], e["id"]))
        wall = portal.winners_public()
        self.assertEqual(wall[0]["winners"][0]["name"], "Anitha")

    def test_badges_and_wiring(self):
        a = self._reg("Anitha", "9812345601")
        self.mem.d["w9812345601"]["badges"] = ["streak_3", "quiz_10"]
        st = portal.state(self.mem, a["token"])
        self.assertTrue(any("3-Day Streak" in b for b in st["student"]["badges"]), st["student"]["badges"])  # badges ippudu labels
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/portal/exam/certificate"', "portal.exam_certificate",
                       "district_league", "district-league", '"/winners"',
                       "portal.winners_public", "my_winner"):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
