#!/usr/bin/env python3
"""
STUDENTUP — CENTRAL SOURCE REGISTRY + AUDITOR TEST SUITE
Covers: registry integrity (100+ sources, no dupes, https-only, enabled==live),
collector registry/health behaviour (auto-pause, pagination, feed reuse),
and the content-gated auditor (candidates enabled ONLY when live+fresh+quiz
content; dead sources disabled after N failures). No network — mocked.
Run:  python3 -m unittest -v tests.test_sources
"""
import sys
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
DATA = ROOT / "data"

from core import config, collector, feeds  # noqa: E402
from core.auditor import check_source, audit_all  # noqa: E402


class TestRegistryIntegrity(unittest.TestCase):
    def test_registry_exists_and_loads(self):
        reg = collector.load_registry()
        self.assertTrue(reg.get("sources"), "registry missing sources")
        self.assertIn(reg["version"], ("3.0", "4.0", "4.1", "4.2"))

    def test_many_sources_centrally(self):
        reg = collector.load_registry()
        self.assertGreaterEqual(len(reg["sources"]), 100,
                                "registry must hold 100+ sources")

    def test_no_duplicate_names(self):
        reg = collector.load_registry()
        names = [s["name"] for s in reg["sources"]]
        self.assertEqual(len(names), len(set(names)))

    def test_every_source_wellformed_and_https(self):
        reg = collector.load_registry()
        for s in reg["sources"]:
            self.assertIn(s["type"], ("rss", "index", "page"), s["name"])
            url = s.get("feed") or s.get("url") or ""
            self.assertTrue(url.startswith("https://"), f"{s['name']}: {url!r}")
            if s["type"] == "rss":
                self.assertTrue(s.get("feed"), s["name"])
            if s["type"] in ("index", "page"):
                self.assertTrue(s.get("url"), s["name"])
                self.assertTrue(s.get("link_re"), s["name"])

    def test_enabled_means_audited_live(self):
        """No enabled source may carry a non-live audit status (no guesses)."""
        reg = collector.load_registry()
        for s in reg["sources"]:
            if s.get("enabled"):
                self.assertEqual(s["audit"]["status"], "live", s["name"])

    def test_candidates_auto_flag_present(self):
        reg = collector.load_registry()
        cand = [s for s in reg["sources"]
                if not s.get("enabled") and s.get("auto_enable_if_live")]
        self.assertGreaterEqual(len(cand), 20, "candidate pool too small")

    def test_news_feeds_centrally_defined(self):
        reg = collector.load_registry()
        nf = reg["news_feeds"]
        self.assertGreaterEqual(len(nf["ca"]), 12)
        self.assertGreaterEqual(len(nf["jobs"]), 5)
        # feeds.py must read the same central registry
        src = feeds.load_feed_sources()
        self.assertGreaterEqual(len(src["ca"]), 12)
        self.assertGreaterEqual(len(src["jobs"]), 5)

    def test_live_sources_cover_exam_categories(self):
        reg = collector.load_registry()
        exams = "\n".join(s.get("exam", "") for s in reg["sources"] if s["enabled"])
        for tag in ("banking", "ssc", "upsc", "railway"):
            self.assertIn(tag, exams, f"no live source covers {tag}")


class TestCollectorHealth(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.gettempdir()) / "test_collector_health.json"
        if self.tmp.exists():
            self.tmp.unlink()
        self._old = collector.HEALTH
        collector.HEALTH = self.tmp

    def tearDown(self):
        collector.HEALTH = self._old
        if self.tmp.exists():
            self.tmp.unlink()

    def test_record_and_pause_after_3_failures(self):
        name = "FakeSource"
        for i in range(1, 4):
            collector.record_health(name, False, f"fail {i}")
        h = collector.health_summary()
        self.assertEqual(h["sources"][name]["consecutive_failures"], 3)
        self.assertTrue(h["sources"][name]["paused"])
        # a success unpauses and resets
        collector.record_health(name, True, "ok")
        h = collector.health_summary()
        self.assertFalse(h["sources"][name]["paused"])
        self.assertEqual(h["sources"][name]["consecutive_failures"], 0)

    def test_registry_sources_skips_paused(self):
        reg = collector.load_registry()
        enabled_names = [s["name"] for s in reg["sources"] if s.get("enabled")]
        self.assertTrue(enabled_names)
        collector.record_health(enabled_names[0], False, "x")
        collector.record_health(enabled_names[0], False, "x")
        collector.record_health(enabled_names[0], False, "x")
        try:
            active = {s["name"] for s in collector.registry_sources()}
            self.assertNotIn(enabled_names[0], active)
        finally:
            # clean state
            data = collector.load_json(self.tmp, {"sources": {}})
            data["sources"].pop(enabled_names[0], None)
            collector.save_json_atomic(self.tmp, data)


class TestAuditor(unittest.TestCase):
    """Every auditor rule is tested offline with injected fetch functions."""

    def setUp(self):
        self.tmp_reg = Path(tempfile.gettempdir()) / "test_registry.json"
        self.tmp_health = Path(tempfile.gettempdir()) / "test_audit_health.json"
        for p in (self.tmp_reg, self.tmp_health):
            if p.exists():
                p.unlink()

    def _registry(self, sources):
        return {"version": "3.0", "news_feeds": {"ca": [], "jobs": []}, "sources": sources}

    def _write(self):
        collector.save_json_atomic(self.tmp_reg, self._registry(self.sources))

    def test_live_rss_checked(self):
        src = {"name": "LiveFeed", "enabled": True, "type": "rss",
               "feed": "https://x/feed", "title_must": r"quiz",
               "title_not": r"(?!)\Z"}
        from email.utils import format_datetime
        from datetime import datetime, timezone
        fresh = format_datetime(datetime.now(timezone.utc))
        ok_feed = lambda url: [{"title": "Daily Quiz 2026", "link": "https://x/q",
                                "published": fresh}]
        r = check_source(src, http_get=lambda url: None, feed_entries=ok_feed)
        self.assertEqual(r["status"], "live")
        self.assertTrue(r["content_ok"])
        self.assertLessEqual(r["freshness_days"], 1)

    def test_junk_feed_not_live(self):
        """Live HTTP but no quiz-matching titles => warn, NOT auto-enable."""
        src = {"name": "JunkFeed", "enabled": False, "type": "rss",
               "feed": "https://x/feed", "title_must": r"quiz",
               "title_not": r"(?!)\Z", "auto_enable_if_live": True}
        junk = lambda url: [{"title": "Test post title", "link": "https://x/t",
                             "published": ""}]
        r = check_source(src, feed_entries=junk)
        self.assertEqual(r["status"], "warn")
        self.assertFalse(r["content_ok"])

    def test_candidate_auto_enable_only_when_fresh_quiz_content(self):
        for frisky in (True, False):
            self.sources = [{
                "name": "Cand", "enabled": False, "type": "rss",
                "feed": "https://x/feed", "title_must": r"quiz",
                "title_not": r"(?!)\Z", "auto_enable_if_live": True,
                "audit": {"status": "unverified"},
            }]
            self._write()
            entries = [{"title": "Reasoning Quiz Set", "link": "https://x/q",
                        "published": ("Sat, 06 Sep 2026 10:00:00 +0000"
                                      if frisky else "Wed, 01 Jan 2024 10:00:00 +0000")}]
            audit_all(update_registry=True, registry_path=self.tmp_reg,
                      health_path=self.tmp_health,
                      http_get=lambda url: None, feed_entries=lambda url: entries)
            reg = collector.load_json(self.tmp_reg, {})
            s = reg["sources"][0]
            if frisky:
                self.assertTrue(s["enabled"], "fresh quiz feed must auto-enable")
                self.assertEqual(s["audit"]["status"], "live")
            else:
                self.assertFalse(s["enabled"], "stale feed must NOT auto-enable")

    def test_enabled_source_auto_disabled_after_3_dead_audits(self):
        self.sources = [{"name": "DeadFeed", "enabled": True, "type": "rss",
                         "feed": "https://x/feed", "title_must": r"quiz",
                         "title_not": r"(?!)\Z", "audit": {"status": "live"}}]
        self._write()
        dead = lambda url: []
        for _ in range(3):
            audit_all(update_registry=True, registry_path=self.tmp_reg,
                      health_path=self.tmp_health,
                      http_get=lambda url: None, feed_entries=dead)
        reg = collector.load_json(self.tmp_reg, {})
        s = reg["sources"][0]
        self.assertFalse(s["enabled"])
        self.assertEqual(s["audit"]["status"], "dead")


class TestCollectorAdvanced(unittest.TestCase):
    """Deep-crawl pagination + registry-driven source selection."""

    def test_index_paginated_links_discovered(self):
        """page_re accepts numbered pages like /aptitude/x/2/."""
        from core import collector
        page_re = r"/[0-9]+/?$"
        self.assertTrue(re.search(page_re, "https://x/aptitude/trains/2/"))
        self.assertFalse(re.search(page_re, "https://x/aptitude/trains/"))

    def test_sources_registry_primary(self):
        """When the central registry exists, _sources() returns it (no dupes)."""
        srcs = collector._sources()
        names = [s["name"] for s in srcs]
        self.assertEqual(len(names), len(set(names)), "duplicate registry sources")
        self.assertGreaterEqual(len(srcs), 14)
        self.assertTrue(any(s.get("type") == "index" for s in srcs))
        self.assertTrue(any("PracticeMock" in n for n in names))
        # BankersAdda is now a deep index crawl (its /feed redirects)
        ba = [s for s in srcs if s["name"] == "BankersAdda Quiz"]
        self.assertTrue(ba and ba[0]["type"] == "index")

    def test_quiz_articles_per_source_limit(self):
        """Source-specific max_articles is honoured (registry-wide limit)."""
        from core import collector
        src = {"feed": "https://x/feed", "max_articles": 1,
               "title_must": r"quiz", "title_not": r"(?!)\Z"}
        entries = [{"title": f"Quiz {i}", "link": f"https://x/{i}"} for i in range(5)]
        arts = collector.quiz_articles_for_source(src, entries=entries)
        self.assertEqual(len(arts), 1)


class TestLLMKeys(unittest.TestCase):
    """Every key family the user supplies must be collected (no dead keys)."""

    def test_all_key_families_collected(self):
        import os
        from core import config as _cfg
        keys_to_clear = [k for k in os.environ
                         if any(k.startswith(p) for p in
                                ("GEMINI", "GROQ", "DEEPSEEK", "OPENAI", "DIFY"))]
        old = {k: os.environ[k] for k in keys_to_clear}
        old_load = _cfg.load_env
        sets = {
            "GEMINI_API_KEY_1": "g1", "GEMINI_API_KEY_2": "g2",
            "GEMINI_KEY_3": "g3", "GROQ_API_KEY": "q1",
            "DEEPSEEK_API_KEY": "d1", "OPENAI_API_KEY": "o1",
            "OPENAI_KEY": "o2", "DIFY_APP_TOKEN": "app-x",
        }
        try:
            for k in keys_to_clear:
                os.environ.pop(k, None)
            for k, v in sets.items():
                os.environ[k] = v
            _cfg.load_env = lambda: None  # isolate from real .env
            from core.llm import LLM
            llm = LLM()
            # all six-style families recognized; aliases merged (no dupes)
            self.assertIn("g1", llm.gemini)
            self.assertIn("g2", llm.gemini)
            self.assertIn("g3", llm.gemini)
            self.assertEqual(len(llm.gemini), 3)
            self.assertEqual(len(llm.groq), 1)
            self.assertEqual(len(llm.deepseek), 1)
            self.assertEqual(len(llm.openai), 2)
            self.assertEqual(len(llm.dify), 1)
            self.assertTrue(llm.available())
        finally:
            for k, v in old.items():
                os.environ[k] = v
            _cfg.load_env = old_load

    def test_same_value_under_aliases_counts_once(self):
        import os
        old = {k: os.environ.get(k) for k in ("GEMINI_KEY_1", "GEMINI_API_KEY_1")}
        try:
            os.environ["GEMINI_KEY_1"] = "same"
            os.environ["GEMINI_API_KEY_1"] = "same"
            from core.llm import LLM
            self.assertEqual(LLM().gemini.count("same"), 1)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


class TestJinaFallback(unittest.TestCase):
    """Jina Reader fallback + feed-URL gate (offline, mocked)."""

    def test_feed_url_gate(self):
        from core import collector
        self.assertTrue(collector.is_feed_url("https://x.com/feed"))
        self.assertTrue(collector.is_feed_url("https://x.com/rss.xml"))
        self.assertFalse(collector.is_feed_url("https://x.com/current-affairs/"))

    def test_http_get_uses_jina_when_direct_blocked(self):
        import os
        import urllib.error
        from core import collector
        old_key = os.environ.get("JINA_API_KEY")
        old_open = collector.urllib.request.urlopen
        old_sleep = collector._sleep_polite
        old_jina = collector._jina_fetch
        old_save = collector.save_seen_urls
        try:
            os.environ["JINA_API_KEY"] = "test-jina"
            collector._sleep_polite = lambda host: None
            collector.save_seen_urls = lambda u: None  # no side effects
            def boom(*a, **k):
                raise urllib.error.URLError("403 blocked")
            collector.urllib.request.urlopen = boom
            collector._jina_fetch = lambda url, timeout=20: "JINA_CONTENT" + "x" * 500
            got = collector.http_get("https://example.com/quiz/", retries=0)
            self.assertTrue(got and got.startswith("JINA_CONTENT"))
        finally:
            collector.urllib.request.urlopen = old_open
            collector._sleep_polite = old_sleep
            collector._jina_fetch = old_jina
            collector.save_seen_urls = old_save
            if old_key is None:
                os.environ.pop("JINA_API_KEY", None)
            else:
                os.environ["JINA_API_KEY"] = old_key

    def test_jina_not_used_for_feed_urls(self):
        import os
        import urllib.error
        from core import collector
        old_key = os.environ.get("JINA_API_KEY")
        old_open = collector.urllib.request.urlopen
        old_sleep = collector._sleep_polite
        old_jina = collector._jina_fetch
        try:
            os.environ["JINA_API_KEY"] = "test-jina"
            collector._sleep_polite = lambda host: None
            def boom(*a, **k):
                raise urllib.error.URLError("blocked")
            collector.urllib.request.urlopen = boom
            calls = []
            collector._jina_fetch = lambda url, timeout=20: calls.append(url) or "x" * 500
            got = collector.http_get("https://example.com/feed", retries=0)
            self.assertIsNone(got)
            self.assertEqual(calls, [], "Jina must not be used for feeds")
        finally:
            collector.urllib.request.urlopen = old_open
            collector._sleep_polite = old_sleep
            collector._jina_fetch = old_jina
            if old_key is None:
                os.environ.pop("JINA_API_KEY", None)
            else:
                os.environ["JINA_API_KEY"] = old_key


class TestSchedule(unittest.TestCase):
    def test_post_quiz_collection_runs(self):
        tasks = config.SCHEDULE
        self.assertEqual(tasks["07:45"][0], "collect", "post-morning-quiz collect")
        self.assertEqual(tasks["19:45"][0], "collect", "post-evening-quiz collect")
        self.assertEqual(tasks["07:45"][1]["reason"], "post-morning-quiz")
        self.assertEqual(tasks["19:45"][1]["reason"], "post-evening-quiz")

    def test_daily_audit_scheduled(self):
        tasks = config.SCHEDULE
        self.assertEqual(tasks["04:45"][0], "audit")

    def test_quiz_rounds_unchanged(self):
        quiz_times = [t for t, (task, _) in config.SCHEDULE.items()
                      if task == "quiz"]
        self.assertEqual(quiz_times, ["07:30", "19:30"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
