"""Offline tests for core.scout — discovery, promotion, caps, never-crash."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from core import scout  # noqa: E402

HUB = "https://hub.example.com/exams/"
PAGE = "https://hub.example.com/exams/ssc-cgl-previous-year-question-paper/"
PDF_OK = "https://cdn.example.com/2026/SSC-CGL-2025-Shift-1-Question-Paper.pdf"
PDF_BAD = "https://cdn.example.com/2026/SSC-CGL-Syllabus.pdf"
PDF_HINDI = "https://cdn.example.com/2026/SSC-CGL-2025-Shift-1-Question-Paper-Hindi.pdf"

FAKE = {
    HUB: f'<a href="{PAGE}">SSC CGL Previous Year Question Paper</a>'
         '<a href="https://facebook.com/x">fb</a>',
    PAGE: f'<a href="{PDF_OK}">SSC CGL 2025 Shift 1 Question Paper PDF</a>'
          f'<a href="{PDF_BAD}">Syllabus PDF</a>'
          f'<a href="{PDF_HINDI}">Hindi paper</a>',
}


class ScoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self._orig = (scout.CAND_FILE, scout.STATE_FILE, scout.PAPERS_FILE, scout.INBOX,
                      scout._fetch, scout._probe_pdf, scout.HOST_GAP_S)
        scout.CAND_FILE = d / "c.json"
        scout.STATE_FILE = d / "s.json"
        scout.PAPERS_FILE = d / "p.json"
        scout.INBOX = d / "inbox"
        scout.HOST_GAP_S = 0
        (d / "p.json").write_text(json.dumps({"papers": []}))
        scout._fetch = lambda url, **k: (FAKE.get(url, ""), url)
        scout._probe_pdf = lambda url: url == PDF_OK

    def tearDown(self):
        (scout.CAND_FILE, scout.STATE_FILE, scout.PAPERS_FILE, scout.INBOX,
         scout._fetch, scout._probe_pdf, scout.HOST_GAP_S) = self._orig
        self.tmp.cleanup()

    def test_discovers_probes_and_promotes(self):
        st = scout.run(hubs=[("SSC", "SSC", HUB)], minutes=1)
        self.assertEqual(st["pages"], 2)
        self.assertEqual(st["new"], 1, "syllabus + hindi PDFs must be filtered")
        self.assertEqual(st["promoted"], 1)
        papers = json.loads(scout.PAPERS_FILE.read_text())["papers"]
        self.assertEqual(papers[0]["url"], PDF_OK)
        self.assertEqual(papers[0]["channel"], "SSC")
        self.assertEqual(papers[0]["year"], 2025)
        self.assertTrue(papers[0]["via"].startswith("scout"))

    def test_second_run_is_idempotent(self):
        scout.run(hubs=[("SSC", "SSC", HUB)], minutes=1)
        st = scout.run(hubs=[("SSC", "SSC", HUB)], minutes=1)
        self.assertEqual(st["new"], 0)
        self.assertEqual(st["promoted"], 0)
        self.assertEqual(len(json.loads(scout.PAPERS_FILE.read_text())["papers"]), 1)

    def test_bad_probe_rejects_not_promotes(self):
        scout._probe_pdf = lambda url: False
        st = scout.run(hubs=[("SSC", "SSC", HUB)], minutes=1)
        self.assertEqual(st["promoted"], 0)
        self.assertEqual(st["rejected"], 1)
        self.assertEqual(json.loads(scout.PAPERS_FILE.read_text())["papers"], [])

    def test_network_failure_never_crashes_and_pauses_dead_host(self):
        def boom(url, **k):
            raise OSError("no network")
        scout._fetch = boom
        for _ in range(scout.DEAD_AFTER):
            st = scout.run(hubs=[("SSC", "SSC", HUB)], minutes=1)
        self.assertEqual(st["new"], 0)
        state = json.loads(scout.STATE_FILE.read_text())
        self.assertTrue(state["hosts"]["hub.example.com"].get("paused_until"))
        self.assertTrue(state["errors"])
        self.assertIn("paused hosts: hub.example.com", scout.status_text())

    def test_candidate_queue_is_capped(self):
        cands = {"items": {f"https://x/{i}.pdf": {"status": "new", "seen": f"2026-01-{i%28+1:02d}"}
                           for i in range(scout.MAX_CANDIDATES + 50)}}
        scout._save_cands(cands)
        self.assertEqual(len(json.loads(scout.CAND_FILE.read_text())["items"]), scout.MAX_CANDIDATES)

    def test_inbox_cap_deletes_oldest_first(self):
        scout.INBOX.mkdir()
        old = scout.INBOX / "old.pdf"; old.write_bytes(b"%PDF" + b"0" * 600_000)
        os.utime(old, (1_600_000_000, 1_600_000_000))
        new = scout.INBOX / "new.pdf"; new.write_bytes(b"%PDF" + b"0" * 600_000)
        orig = scout.INBOX_CAP_MB
        scout.INBOX_CAP_MB = 1          # 1 MB cap, 1.2 MB present
        try:
            r = scout.enforce_inbox_cap()
        finally:
            scout.INBOX_CAP_MB = orig
        self.assertEqual(r["deleted"], 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_channel_guess(self):
        self.assertEqual(scout._guess_channel("TSLPRB SI prelims 2018", "SSC"), "POLICE")
        self.assertEqual(scout._guess_channel("RRB NTPC CBT-1", "SSC"), "RAILWAY")
        self.assertEqual(scout._guess_channel("nothing here", "APPSC"), "APPSC")


if __name__ == "__main__":
    unittest.main()
