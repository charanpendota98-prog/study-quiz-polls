# -*- coding: utf-8 -*-
"""🏆 Top-Expert round: gzip + keep-alive, daily store backups with
corruption recovery, exam-result Top%, live rank polling wiring.

Pins: portal.json corrupt ayina kuda backup nunchi data recover
avthundi; result view lo rank tho paatu Top% vasthundi; server
responses gzip + HTTP/1.1 keep-alive disciplined ga unnayi.
"""
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import portal  # noqa: E402
from tests.test_portal import FakeMembers, _reg  # noqa: E402

DASH = (Path(__file__).resolve().parent.parent
        / "scripts" / "dashboard_server.py")


def _drop_cache():
    portal._close_journal()
    portal._STORE.update({"path": None, "d": None, "dirty": False, "jfh": None})


class TestTopAdvanced(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        _drop_cache()
        portal.PATH = self._old

    def test_backup_and_corruption_recovery(self):
        tok = _reg(self.mem)
        portal._flush_store()                       # first snapshot
        d = portal._load()
        d["sessions"]["marker"] = "w9812345601"
        portal._save(d, flush=True)                 # backup of previous day-file
        baks = list(Path(self._tmp).glob("portal.json.bak-*"))
        self.assertTrue(baks, "daily backup create avvali")
        # 💥 main file corrupt chesi restart simulate
        portal.PATH.write_text("{CORRUPT!!!", encoding="utf-8")
        _drop_cache()
        d2 = portal._load()
        self.assertIn(tok, d2["sessions"])          # backup nunchi recovery
        self.assertIsNotNone(portal.state(self.mem, tok))

    def test_result_top_pct(self):
        start = (portal._now() - timedelta(hours=2)).isoformat()
        e = portal.create_exam("Percentile Exam", "mixed", start,
                               duration_min=30, n_q=10)
        d = portal._load()
        me = "w5550001111"
        entries = {me: {"uid": me, "answers": {}, "correct": 8, "pts": 80,
                        "joined_at": "x", "name": "Me", "district": "Guntur"}}
        for i in range(9):  # 9 others: correct 0..8 → me rank 1-2 band
            u = f"w777{i:07d}"
            entries[u] = {"uid": u, "answers": {}, "correct": i, "pts": i * 10,
                          "joined_at": "x", "name": f"S{i}", "district": "Guntur"}
        d["exams"][e["id"]]["entries"] = entries
        portal._save(d, flush=True)
        portal._refresh(d, portal._now())
        view = portal._exam_view(portal._load()["exams"][e["id"]],
                                 self.mem, me, portal._now())
        self.assertIsNotNone(view["my"]["rank"])
        expect = max(1, (100 * view["my"]["rank"] + 9) // 10)
        self.assertEqual(view["my"]["top_pct"], expect)
        self.assertLessEqual(view["my"]["top_pct"], 20)   # 8/10 → top band

    def test_server_perf_wiring(self):
        src = DASH.read_text(encoding="utf-8")
        for needle in ('protocol_version = "HTTP/1.1"', "def _gz",
                       "gzip", "Content-Encoding", "pollRank",
                       "rankTimer", "top_pct"):
            self.assertIn(needle, src)
        psrc = (Path(__file__).resolve().parent.parent
                / "scripts" / "core" / "portal.py").read_text(encoding="utf-8")
        self.assertIn(".bak-", psrc)


if __name__ == "__main__":
    unittest.main()
