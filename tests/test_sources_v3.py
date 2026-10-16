#!/usr/bin/env python3
"""
STUDENTUP — SCRAPER v3 TESTS (many sources + auto-discovery + easy setup)
Covers: the 500+ source registry (v3 wave is candidate-only, well-formed,
exam-broad), feed auto-discovery from a homepage, sitemap-index following,
the source-manager CLI core (add/discover/enable without JSON editing),
and parallel cross-source collection (COLLECT_WORKERS).
Offline — no network. Run:  python3 -m unittest -v tests.test_sources_v3
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import collector, source_manager  # noqa: E402


class TestRegistryV3(unittest.TestCase):
    def setUp(self):
        self.reg = collector.load_registry()
        self.srcs = self.reg["sources"]

    def test_more_than_500_sources(self):
        self.assertGreaterEqual(len(self.srcs), 500)

    def test_v3_wave_is_large_and_candidate_only(self):
        v3 = [s for s in self.srcs
              if s.get("audit", {}).get("checked") == "2026-10-14"]
        self.assertGreaterEqual(len(v3), 80)
        for s in v3:                       # no guesses ever enabled
            self.assertFalse(s.get("enabled"), s["name"])
            self.assertTrue(s.get("auto_enable_if_live"), s["name"])
            self.assertEqual(s["audit"]["status"], "unverified", s["name"])

    def test_v3_covers_official_pyq_and_new_domains(self):
        names = " ".join(s["name"] for s in self.srcs)
        for token in ("UPSC Official", "TGPSC Official", "APPSC Official",
                      "Sanfoundry", "ExamsDaily", "Examveda Trains",
                      "IndiaBIX ECE"):
            self.assertIn(token, names)
        official = [s for s in self.srcs if s.get("pdf_re")]
        self.assertGreaterEqual(len(official), 10)

    def test_rebuild_registry_keeps_v3_wave(self):
        import subprocess
        r = subprocess.run([sys.executable, "scripts/rebuild_registry.py",
                            "--check"], cwd=ROOT, capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("registry OK:", r.stdout)


class TestDiscovery(unittest.TestCase):
    def test_discover_feed_urls_from_homepage(self):
        html = ('<html><head>'
                '<link rel="alternate" type="application/rss+xml" '
                'title="RSS" href="/feed.xml">'
                '<link rel="alternate" type="application/atom+xml" '
                'href="https://blog.example.com/atom">'
                '<link rel="stylesheet" href="/style.css">'
                '</head></html>')
        feeds = collector.discover_feed_urls(html, "https://blog.example.com/")
        self.assertEqual(feeds, ["https://blog.example.com/feed.xml",
                                 "https://blog.example.com/atom"])

    def test_sitemap_index_is_followed(self):
        index = ('<sitemapindex><sitemap>'
                 '<loc>https://x/post-sitemap1.xml</loc></sitemap>'
                 '</sitemapindex>')
        sub = ('<urlset><url><loc>https://x/daily-quiz-9/</loc></url>'
               '<url><loc>https://x/about/</loc></url></urlset>')
        pages = {"https://x/sitemap.xml": index,
                 "https://x/post-sitemap1.xml": sub}
        with mock.patch.object(collector, "http_get",
                               side_effect=lambda u, **k: pages.get(u)):
            links = collector.fetch_sitemap_links(
                "https://x/sitemap.xml", r"quiz")
        self.assertEqual([lk["link"] for lk in links],
                         ["https://x/daily-quiz-9/"])


class TestSourceManager(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "reg.json"
        seed = {"sources": [{"name": "Seed", "enabled": True, "type": "rss",
                             "exam": "all", "feed": "https://seed.example/feed",
                             "title_must": "quiz", "title_not": "x",
                             "audit": {"status": "live"}}],
                "defaults": {}}
        collector.save_json_atomic(self.tmp, seed)
        self._old = source_manager.REG
        source_manager.REG = self.tmp

    def tearDown(self):
        source_manager.REG = self._old

    def test_add_rss_candidate_and_dedup(self):
        r = source_manager.add_source("https://new.example/feed",
                                      exam="banking", name="NewBank")
        self.assertTrue(r["added"])
        self.assertFalse(r["source"]["enabled"])     # candidate, not live
        r2 = source_manager.add_source("https://new.example/feed")
        self.assertFalse(r2["added"])                # duplicate URL blocked

    def test_add_rejects_non_https(self):
        r = source_manager.add_source("http://insecure.example/feed")
        self.assertFalse(r["added"])

    def test_add_index_infers_type_and_enable_flow(self):
        r = source_manager.add_source("https://site.example/quiz/",
                                      exam="ssc", name="SiteQuiz")
        self.assertTrue(r["added"])
        self.assertEqual(r["source"]["type"], "index")
        on = source_manager.set_enabled("SiteQuiz", True)
        self.assertTrue(on["changed"])
        off = source_manager.set_enabled("SiteQuiz", False)
        self.assertTrue(off["changed"])
        self.assertFalse(source_manager.find_source(
            source_manager._load(), "SiteQuiz")["enabled"])


class TestParallelCollect(unittest.TestCase):
    def test_parallel_discovery_collects_all_sources(self):
        tmp = Path(tempfile.mkdtemp())
        keys = ("SCRAPED_BANK", "PENDING", "SEEN_URLS", "HEALTH",
                "_sources", "_feed_entries", "http_get")
        saved = {k: getattr(collector, k) for k in keys}
        old_workers = os.environ.get("COLLECT_WORKERS")
        # no real LLM calls in tests (a leaked fake key would hang on net)
        llm_keys = [k for k in os.environ if any(
            k.startswith(p) for p in
            ("GEMINI", "GROQ", "DEEPSEEK", "OPENAI", "DIFY"))]
        llm_saved = {k: os.environ.pop(k) for k in llm_keys}
        html = (ROOT / "tests" / "fixture_quiz.html").read_text(
            encoding="utf-8")
        try:
            os.environ["COLLECT_WORKERS"] = "3"
            collector.SCRAPED_BANK = tmp / "bank.json"
            collector.PENDING = tmp / "pending.json"
            collector.SEEN_URLS = tmp / "seen.json"
            collector.HEALTH = tmp / "health.json"
            srcs = [{"name": f"FakeRSS{i}", "type": "rss", "exam": "all",
                     "feed": f"https://x{i}/feed", "title_must": r"quiz",
                     "title_not": r"(?!)\Z"} for i in range(3)]
            collector._sources = lambda: [dict(s) for s in srcs]
            collector._feed_entries = lambda url: [
                {"title": "Daily Quiz", "link": url.replace("/feed", "/q1"),
                 "published": ""}]
            collector.http_get = lambda url, **k: html
            st = collector.collect_daily()
            self.assertEqual(st["sources"], 3)
            self.assertEqual(st["articles"], 3)
            self.assertGreaterEqual(st["parsed"], 12)
        finally:
            for k, v in saved.items():
                setattr(collector, k, v)
            os.environ.update(llm_saved)
            if old_workers is None:
                os.environ.pop("COLLECT_WORKERS", None)
            else:
                os.environ["COLLECT_WORKERS"] = old_workers


if __name__ == "__main__":
    unittest.main(verbosity=2)
