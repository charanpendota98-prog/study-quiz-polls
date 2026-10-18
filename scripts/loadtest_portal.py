#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🚀 Portal 10K Load Test — okka live exam ni 10,000 students
okkesari rayagalara? (In-process dry run — real portal code paths,
Members stub matrame; network ledu.)

Run:  python3 scripts/loadtest_portal.py --students 10000 --questions 10
"""
import argparse
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import portal  # noqa: E402


class _KV:
    def save(self):
        pass

    def save_debounced(self, min_interval=2.0):
        pass

    def flush_pending(self):
        pass


class StubMembers:
    def __init__(self):
        self.d = {}
        self.members = self.d
        self.kv = _KV()
        self._lk = threading.Lock()

    def _get(self, uid):
        with self._lk:
            return self.d.setdefault(str(uid), {"topics": {}, "points": 0})

    def award_answer(self, uid, username="", correct=True, topic="", qid=""):
        m = self._get(uid)
        if correct:
            m["points"] = m.get("points", 0) + 10
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=10000)
    ap.add_argument("--questions", type=int, default=10)
    ap.add_argument("--threads", type=int, default=64)
    args = ap.parse_args()
    n, nq = args.students, args.questions

    portal.PATH = Path(tempfile.mkdtemp()) / "portal.json"
    mem = StubMembers()

    t0 = time.time()
    tokens = {}
    for i in range(n):
        ok, inf = portal.register_student(
            mem, f"Student{i}", f"97{i:08d}"[:10], "Guntur", "ssc")
        assert ok, inf
        tokens[inf["uid"]] = inf["token"]
    t_reg = time.time() - t0

    from datetime import timedelta
    e = portal.create_exam("10K Grand Live Test", "mixed",
                           (portal._now() - timedelta(minutes=1)).isoformat(),
                           duration_min=180, n_q=nq)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        list(ex.map(lambda u: portal.exam_join(mem, tokens[u], e["id"]), tokens))
    t_join = time.time() - t0

    d = portal._load()
    qs = d["exams"][e["id"]]["qs"]

    def answer_all(uid):
        for i, q in enumerate(qs):
            _o, perm = portal._display(q, f"{e['id']}:{uid}:{i}")
            ok, _r = portal.exam_answer(mem, tokens[uid], e["id"], i,
                                        perm.index(q["answer_index"]))
            assert ok

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        list(ex.map(answer_all, tokens))
    t_ans = time.time() - t0

    d = portal._load()
    entries = d["exams"][e["id"]]["entries"]
    total_answers = sum(len(x["answers"]) for x in entries.values())
    all_correct = sum(1 for x in entries.values() if x["correct"] == nq)
    print(f"👥 Students: {n} · Questions: {nq} · Threads: {args.threads}")
    print(f"📝 Register: {t_reg:.1f}s · 🚪 Join: {t_join:.1f}s "
          f"({n / max(t_join, 0.01):,.0f}/s)")
    print(f"✍️ Answers: {total_answers:,} in {t_ans:.1f}s "
          f"({total_answers / max(t_ans, 0.01):,.0f}/s)")
    print(f"🎯 Entries: {len(entries):,} · Full-correct: {all_correct:,}")
    assert len(entries) == n and total_answers == n * nq and all_correct == n
    print("✅ 10K LOAD TEST PASSED — okka answer kuda poledu!")


if __name__ == "__main__":
    main()
