import os, sys, unittest, tempfile, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, grandtest


class _Bank:
    def __init__(self, qs):
        self.qs = {q["id"]: q for q in qs}
        self.used = {}
        self.picked = []
    def by_id(self, i): return self.qs.get(i)
    def pick(self, ch, n):
        fresh = [q for q in self.qs.values() if q["id"].startswith("f")][:n]
        self.picked += [q["id"] for q in fresh]
        return fresh


class _LB:
    def __init__(self, st): self.st = st
    def stats_by_qid(self, qids): return {k: v for k, v in self.st.items() if k in qids}


class TestGrandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._old = grandtest.WEEK_LOG
        grandtest.WEEK_LOG = self.tmp / "week.json"

    def tearDown(self):
        grandtest.WEEK_LOG = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compose_revision_plus_fresh_sorted_by_sections(self):
        from datetime import datetime, timedelta
        now = datetime.now(config.IST)
        qs = []
        for i in range(12):
            qs.append({"id": f"r{i}", "q_en": f"rev {i}", "topic": f"t{i%5}",
                       "difficulty": ["easy", "medium", "hard"][i % 3], "answer_index": 0,
                       "options_en": ["a", "b", "c", "d"]})
        for i in range(10):
            qs.append({"id": f"f{i}", "q_en": f"fresh {i}", "topic": "x",
                       "difficulty": "hard", "answer_index": 1, "options_en": ["a", "b", "c", "d"]})
        for i in range(1, 7):
            grandtest.log_round("TSPSC", [f"r{i*2-2}", f"r{i*2-1}"], when=now - timedelta(days=i))
        self.assertEqual(len(grandtest.week_qids("TSPSC", now=now)), 12)
        stats = {"r3": {"correct": 1, "total": 10}, "r0": {"correct": 9, "total": 10}}
        bank = _Bank(qs)
        out, meta = grandtest.compose_grand_test(bank, "TSPSC", n=10, lb=_LB(stats), now=now)
        self.assertEqual(meta["total"], 10)
        self.assertEqual(meta["revision"], 6)
        self.assertEqual(meta["fresh"], 4)
        rev = [q["id"] for q in out if q["_grand_revision"]]
        self.assertIn("r3", rev)              # most-missed question comes back
        order = [grandtest._difficulty(q) for q in out]
        rank = {"easy": 0, "medium": 1, "hard": 2}
        self.assertEqual(order, sorted(order, key=rank.get))   # Section A→B→C
        self.assertEqual(len(bank.picked), 4)                    # fresh consumed via no-repeat pick

    def test_marks_negative(self):
        self.assertEqual(grandtest.marks(20, 25), round(20 - 5 / 3, 2))
        self.assertEqual(grandtest.marks(0, 0), 0)

    def test_week_log_rolls(self):
        from datetime import datetime, timedelta
        now = datetime.now(config.IST)
        grandtest.log_round("SSC", ["a"], when=now - timedelta(days=20))
        grandtest.log_round("SSC", ["b"], when=now)
        from core.store import load_json
        self.assertEqual(len(load_json(grandtest.WEEK_LOG, {})), 1)

    def test_teaser_and_opener_render(self):
        cfg = {"emoji": "🏛", "subject": "TSPSC"}
        t = grandtest.teaser(cfg)
        self.assertIn("GRAND TEST", t)
        o = grandtest.opener(cfg, {"total": 25, "revision": 15, "fresh": 10,
                                   "sections": {"easy": 8, "medium": 9, "hard": 8}}, "31 min")
        self.assertIn("Section A", o); self.assertIn("−⅓", o)

    def test_watch_sunday_reminder(self):
        import watch
        self.assertIsNone(watch.due_reminders("08:55", 2))
        self.assertEqual(watch.due_reminders("08:55", 6), 5)
        self.assertEqual(watch.due_reminders("08:59", 6), 1)


if __name__ == "__main__":
    unittest.main()
