# -*- coding: utf-8 -*-
"""📲 Install prompt + 📣 Auto winners announce + 📚 Materials + 📅 Heatmap.

Pins: exam finalize → automatic winners notice on portal, winners_text
for Telegram/WhatsApp announcements, 28-day activity in my_report,
dashboard announce endpoint + materials page + install prompt wiring.
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


class TestTop100x(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        portal.PATH = self._old

    def test_auto_winners_notice_and_text_and_heatmap(self):
        st_time = (portal._now() - timedelta(minutes=5)).isoformat()
        e = portal.create_exam("Mega Test", "mixed", st_time, 30, 10)
        ok, a = portal.register_student(self.mem, "Anitha", "9812345601", "Guntur", "groups")
        portal.exam_join(self.mem, a["token"], e["id"])
        d = portal._load()
        q0 = d["exams"][e["id"]]["qs"][0]
        _o, perm = portal._display(q0, f"{e['id']}:w9812345601:0")
        portal.exam_answer(self.mem, a["token"], e["id"], 0, perm.index(q0["answer_index"]))
        # heatmap: today's activity recorded via ledger
        rep = portal.my_report(self.mem, a["token"])
        self.assertEqual(len(rep["activity"]), 28)
        self.assertGreater(rep["activity"][-1]["pts"], 0)
        # push to past → finalize → AUTO notice + winners text
        d = portal._load()
        d["exams"][e["id"]]["starts_at"] = (portal._now() - timedelta(hours=2)).isoformat()
        portal._save(d)
        st = portal.state(self.mem, a["token"])
        titles = [n["title"] for n in st["notices"]]
        self.assertTrue(any("Winners!" in t for t in titles), titles)
        txt = portal.winners_text(e["id"])
        self.assertIn("Anitha", txt)
        self.assertIn("Guntur", txt)
        self.assertIn("WINNERS", txt)

    def test_wiring(self):
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/portal/admin/announce"', "portal.winners_text",
                       "announceWinners", '"/materials"', "__MATERIALS__",
                       "Study Materials", "beforeinstallprompt", "install-card",
                       "activity", "Last 28 Days Activity"):
            self.assertIn(needle, src)


if __name__ == "__main__":
    unittest.main()
