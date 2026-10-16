#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""🚀 HTTP 10K Load Test — nijamaina dashboard server meeda, nijamaina
HTTP requests tho students exam raastharu (in-process simulation kaadu).

Portal/Members stores oka tmp folder loki redirect chestham — real
student data touch avadu.

Run:  python3 scripts/loadtest_http.py --students 2000 --questions 10
"""
import argparse
import json
import sys
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TMP = Path(tempfile.mkdtemp(prefix="su-http-load-"))

from core import config  # noqa: E402

config.DATA = TMP  # members/portal stores isolated (bank read real DATA nunchi)

from core import campus, portal  # noqa: E402

portal.PATH = TMP / "portal.json"
campus.PATH = TMP / "campus.json"

import dashboard_server as ds  # noqa: E402


class _Srv(ds.ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256


def _req(base, method, path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=2000)
    ap.add_argument("--questions", type=int, default=10)
    ap.add_argument("--threads", type=int, default=64)
    args = ap.parse_args()
    n, nq = args.students, args.questions

    srv = _Srv(("127.0.0.1", 0), ds.DashboardHandler)
    port = srv.server_address[1]
    base = f"http://127.0.0.1:{port}"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for _ in range(50):
        try:
            _req(base, "GET", "/portal")
            break
        except Exception:
            time.sleep(0.2)
    print(f"🌐 Server ready: {base} (tmp store: {TMP})")

    exam = portal.create_exam(
        "HTTP Grand Live Test", "mixed",
        (portal._now() - timedelta(minutes=1)).isoformat(),
        duration_min=180, n_q=nq)
    eid = exam["id"]
    qs = portal._load()["exams"][eid]["qs"]
    assert len(qs) == nq, qs

    errors = []

    def register(i):
        phone = f"96{i:08d}"[:10]
        d = _req(base, "POST", "/api/portal/register",
                 {"name": f"Student{i}", "phone": phone,
                  "district": "Guntur", "goal": "ssc"})
        assert d.get("ok"), d
        return "w" + phone, d["token"]

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        students = list(ex.map(register, range(n)))
    t_reg = time.time() - t0

    def join(pair):
        _uid, tok = pair
        d = _req(base, "POST", "/api/portal/exam/join",
                 {"token": tok, "exam_id": eid})
        assert d.get("ok"), d

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        list(ex.map(join, students))
    t_join = time.time() - t0

    def answer_all(pair):
        uid, tok = pair
        try:
            for i, q in enumerate(qs):
                _o, perm = portal._display(q, f"{eid}:{uid}:{i}")
                d = _req(base, "POST", "/api/portal/exam/answer",
                         {"token": tok, "exam_id": eid, "idx": i,
                          "choice": perm.index(q["answer_index"])})
                assert d.get("ok"), d
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        list(ex.map(answer_all, students))
    t_ans = time.time() - t0

    entries = portal._load()["exams"][eid]["entries"]
    total_answers = sum(len(x["answers"]) for x in entries.values())
    print(f"👥 Students: {n:,} · Questions: {nq} · Threads: {args.threads} (real HTTP)")
    print(f"📝 Register: {t_reg:.1f}s ({n / max(t_reg, 0.01):,.0f}/s) · "
          f"🚪 Join: {t_join:.1f}s ({n / max(t_join, 0.01):,.0f}/s)")
    print(f"✍️ Answers: {total_answers:,} in {t_ans:.1f}s "
          f"({total_answers / max(t_ans, 0.01):,.0f}/s) · errors: {len(errors)}")
    print(f"🎯 Entries recorded: {len(entries):,}")
    assert not errors, errors[:3]
    assert len(entries) == n and total_answers == n * nq
    srv.shutdown()
    print("✅ HTTP LOAD TEST PASSED — real server, okka answer kuda poledu!")


if __name__ == "__main__":
    main()
