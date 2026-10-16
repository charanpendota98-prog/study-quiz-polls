# -*- coding: utf-8 -*-
"""🚀 10K Scale Engine: in-memory store + answer journal (crash-safe) +
write-behind disk. Pins: crash ayina journal nunchi answers replay
avthayi; 10,000 entries unna exam lo kuda board/winners correct;
chala mandi okesari answer chesthe okka answer kuda podu.

Real 10,000-student proof: scripts/loadtest_portal.py (suite lo kadu —
slow). Ikkada store semantics + 10k-entry maths matrame pin chestham.
"""
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import portal, store  # noqa: E402
from tests.test_portal import FakeMembers, _reg  # noqa: E402

DASH = (Path(__file__).resolve().parent.parent
        / "scripts" / "dashboard_server.py")


def _drop_cache():
    """Process crash simulate — flush cheyyakunda memory vadileyadam."""
    portal._close_journal()
    portal._STORE.update({"path": None, "d": None, "dirty": False, "jfh": None})


class TestScaleEngine(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"
        self.mem = FakeMembers()

    def tearDown(self):
        _drop_cache()
        portal.PATH = self._old

    def test_journal_crash_replay(self):
        tok = _reg(self.mem)
        portal._flush_store()  # session disk ki vellindi
        start = (portal._now() - timedelta(minutes=5)).isoformat()
        e = portal.create_exam("Crash Test", "mixed", start,
                               duration_min=120, n_q=5)
        portal.exam_join(self.mem, tok, e["id"])
        d = portal._load()
        exam = d["exams"][e["id"]]
        uid = "w9812345601"
        for i, q in enumerate(exam["qs"][:3]):
            _o, perm = portal._display(q, f"{e['id']}:{uid}:{i}")
            ok, _r = portal.exam_answer(self.mem, tok, e["id"], i,
                                        perm.index(q["answer_index"]))
            self.assertTrue(ok)
        _drop_cache()  # 💥 crash — snapshot lo answers levu, journal lo unnayi
        d2 = portal._load()
        ent = d2["exams"][e["id"]]["entries"][uid]
        self.assertEqual(len(ent["answers"]), 3)
        self.assertEqual(ent["correct"], 3)

    def test_10k_entries_board_and_winners(self):
        start = (portal._now() - timedelta(hours=2)).isoformat()
        e = portal.create_exam("Mega Exam", "mixed", start,
                               duration_min=30, n_q=5)
        d = portal._load()
        entries = {}
        for i in range(10000):
            entries[f"w{i:05d}"] = {
                "uid": f"w{i:05d}", "answers": {}, "correct": i % 6,
                "pts": (i % 6) * 10, "joined_at": f"2026-10-16T09:{i % 60:02d}:00",
                "name": f"S{i}", "district": "Guntur"}
        d["exams"][e["id"]]["entries"] = entries
        portal._save(d, flush=True)
        portal._refresh(d, portal._now())   # done → winners finalize
        exam = portal._load()["exams"][e["id"]]
        self.assertTrue(exam["final"])
        self.assertEqual(len(exam["winners"]), 3)
        self.assertTrue(all(w["correct"] == 5 for w in exam["winners"]))
        view = portal._exam_view(exam, self.mem, "w00001", portal._now())
        self.assertEqual(len(view["board"]), 10)
        self.assertTrue(1 <= view["my"]["rank"] <= 10000)

    def test_concurrent_answers_no_loss(self):
        start = (portal._now() - timedelta(minutes=5)).isoformat()
        e = portal.create_exam("Crowd", "mixed", start,
                               duration_min=120, n_q=6)
        students = []
        for n in range(120):
            phone = f"984{n:07d}"
            students.append((_reg(self.mem, name=f"S{n}", phone=phone),
                             "w" + phone))
        for tok, _u in students:
            portal.exam_join(self.mem, tok, e["id"])
        d = portal._load()
        qs = d["exams"][e["id"]]["qs"]

        def answer_all(pair):
            tok, uid = pair
            for i, q in enumerate(qs):
                _o, perm = portal._display(q, f"{e['id']}:{uid}:{i}")
                ok, _r = portal.exam_answer(self.mem, tok, e["id"], i,
                                            perm.index(q["answer_index"]))
                assert ok
        with ThreadPoolExecutor(max_workers=32) as ex:
            list(ex.map(answer_all, students))
        entries = portal._load()["exams"][e["id"]]["entries"]
        self.assertEqual(len(entries), 120)
        self.assertTrue(all(len(x["answers"]) == 6 and x["correct"] == 6
                            for x in entries.values()))

    def test_kv_debounce_and_parse_cache(self):
        tmp = Path(self._tmp) / "kv.json"
        kv = store.KV(tmp, default={"a": 1})
        kv.data["a"] = 2
        kv.save_debounced(min_interval=60)
        self.assertTrue(kv._dirty)          # inka disk ki vellaledu
        kv.flush_pending()
        self.assertFalse(kv._dirty)
        kv2 = store.KV(tmp, default={})
        self.assertEqual(kv2.data["a"], 2)
        self.assertIs(kv2.data, kv.data)    # parse cache — same object

    def test_wiring(self):
        src = DASH.read_text(encoding="utf-8")
        self.assertIn("request_queue_size = 256", src)
        psrc = (Path(__file__).resolve().parent.parent
                / "scripts" / "core" / "portal.py").read_text(encoding="utf-8")
        for needle in ("_journal(", "_flush_store", "_replay_journal",
                       "save_debounced"):
            self.assertIn(needle, psrc)
        lt = (Path(__file__).resolve().parent.parent
              / "scripts" / "loadtest_portal.py").read_text(encoding="utf-8")
        self.assertIn("10000", lt)


if __name__ == "__main__":
    unittest.main()
