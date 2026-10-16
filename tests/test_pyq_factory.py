#!/usr/bin/env python3
"""Paper Factory tests — official-index expansion + priority harvest.

The factory rule under test: URLs are NEVER guessed. An official index
page's own links (host-whitelisted, quality-filtered) become registered
papers; each run ingests a batch and the rest drain over later runs,
with a weekly rescan for newly posted papers.
Run: python3 -m unittest discover -s tests -p "test_pyq_factory.py"
"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import pyq  # noqa: E402

INDEX_HTML = """
<html><body>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/TSPSC-Group-2-Paper-1.pdf">Paper 1</a>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/TSPSC-Group-2-Paper-2.pdf">Paper 2</a>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/TSPSC-Group-2-Paper-3.pdf">Paper 3</a>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/TSPSC-Group-2-Paper-4.pdf">Paper 4</a>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/TSPSC-Group-2-Paper-5.pdf">Paper 5</a>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/TSPSC-Group-2-Paper-6.pdf">Paper 6</a>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/Syllabus.pdf">Syllabus</a>
<a href="https://evil.example/x.pdf">x</a>
</body></html>
"""


class TmpFactory(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (pyq.PAPERS_FILE, pyq.STATE_FILE)
        pyq.PAPERS_FILE = self.tmp / "pyq_papers.json"
        pyq.STATE_FILE = self.tmp / "pyq_state.json"
        self.index_entry = {"channel": "TSPSC", "exam": "TSPSC Group-2",
                            "year": 2024, "paper": "All Papers",
                            "index": "https://www.careerpower.in/index",
                            "max_pdfs": 2, "lang": "en"}
        pyq.PAPERS_FILE.write_text(json.dumps({"papers": [
            self.index_entry,
            {"channel": "SSC", "exam": "SSC CGL", "year": 2024, "paper": "P1",
             "url": "https://www.careerpower.in/direct.pdf", "lang": "en"},
        ]}))

    def tearDown(self):
        pyq.PAPERS_FILE, pyq.STATE_FILE = self._orig

    def _papers(self):
        return json.loads(pyq.PAPERS_FILE.read_text())["papers"]

    def _state(self):
        if not pyq.STATE_FILE.exists():
            return {}
        return json.loads(pyq.STATE_FILE.read_text())


class TestDiscover(TmpFactory):
    def test_registers_all_index_papers_deduped(self):
        added, total = pyq.discover_index_papers(self.index_entry, INDEX_HTML)
        self.assertEqual(total, 6)                    # syllabus/evil filtered
        self.assertEqual(added, 6)
        urls = [p["url"] for p in self._papers() if p.get("url")]
        self.assertEqual(len(urls), 7)                # 6 new + 1 seeded direct
        new = [p for p in self._papers()
               if str(p.get("via", "")).startswith("index-discovery")]
        self.assertEqual(len(new), 6)
        self.assertTrue(all(p["channel"] == "TSPSC" for p in new))
        # second scan: nothing new (dedupe by URL)
        added2, _ = pyq.discover_index_papers(self.index_entry, INDEX_HTML)
        self.assertEqual(added2, 0)


class TestEligibility(unittest.TestCase):
    def test_expanded_rescan_window(self):
        now = time.time()
        self.assertFalse(pyq._eligible(
            {"status": "expanded", "next_try_ts": now + 1000}, now))
        self.assertTrue(pyq._eligible(
            {"status": "expanded", "next_try_ts": now - 5}, now))
        self.assertFalse(pyq._eligible({"status": "done"}, now))

    def test_sort_by_need(self):
        entries = [{"channel": "SSC"}, {"channel": "APPSC"}, {"channel": "TSPSC"}]
        out = pyq._sort_by_need(entries, {"APPSC": 5, "SSC": 100})
        self.assertEqual([e["channel"] for e in out], ["APPSC", "SSC", "TSPSC"])
        self.assertEqual(pyq._sort_by_need(entries, {}), entries)


class TestHarvestFactory(TmpFactory):
    def _run_harvest(self, **kw):
        with mock.patch.object(pyq, "_get", return_value=INDEX_HTML), \
             mock.patch.object(pyq, "_download", return_value="paper.pdf"), \
             mock.patch.object(pyq, "_channel_need", return_value={}), \
             mock.patch("core.collector.ingest_pdf",
                        return_value={"accepted": 7}) as ingest, \
             mock.patch("core.scout.enforce_inbox_cap", lambda dry=False: None):
            stats = pyq.harvest(dry=False, llm=False, **kw)
        return stats, ingest

    def test_index_expands_then_drains(self):
        # run 1 (limit=1): only the index is processed — batch of 2 now,
        # all 6 registered for later runs, index marked expanded
        stats, ingest = self._run_harvest(limit=1)
        self.assertEqual(stats["discovered"], 6)
        self.assertEqual(ingest.call_count, 2)        # max_pdfs batch
        st = self._state()
        idx = st["https://www.careerpower.in/index"]
        self.assertEqual(idx["status"], "expanded")
        self.assertEqual(idx["found"], 6)
        self.assertGreater(idx["next_try_ts"], time.time() + 6 * 24 * 3600)
        self.assertEqual(len(self._papers()), 8)      # 2 seeded + 6 factory

        # run 2: index in rescan backoff (skipped); remaining 4 factory
        # papers + 1 seeded direct drain through the normal path
        stats2, ingest2 = self._run_harvest()
        self.assertEqual(ingest2.call_count, 5)
        st2 = self._state()
        done_urls = [k for k, v in st2.items() if v.get("status") == "done"]
        self.assertEqual(len(done_urls), 7)           # 6 factory + 1 direct
        self.assertEqual(stats2["questions"], 35)     # 5 PDFs × 7 accepted

    def test_status_text_shows_factory(self):
        pyq.discover_index_papers(self.index_entry, INDEX_HTML)
        txt = pyq.status_text()
        self.assertIn("auto-discovered", txt)


if __name__ == "__main__":
    unittest.main()
