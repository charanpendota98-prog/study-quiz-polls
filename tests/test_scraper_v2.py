#!/usr/bin/env python3
"""
STUDENTUP — SCRAPER v2 TESTS (advanced perfect-scrape upgrade)
Covers: embedded-JSON questions (JSON-LD / __NEXT_DATA__ / window data),
table-layout pages, dash options, answer-as-text keys, unnumbered stems,
small answer-key tables, RSS-1.0/RDF + Atom feeds (fresh-first), sitemap
discovery, gzip fetching, seen-URL retry, and the poll-posting guarantee
(every bank question builds a Telegram-legal poll whose correct_option_id
still points at the correct option after balancing).
Offline — no network. Run:  python3 -m unittest -v tests.test_scraper_v2
"""
import gzip
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import collector  # noqa: E402


class TestEmbeddedJSON(unittest.TestCase):
    def test_json_ld_quiz(self):
        html = ('<html><head><script type="application/ld+json">'
                '{"@type":"Quiz","hasPart":[{"@type":"Question",'
                '"text":"Capital of Telangana?",'
                '"acceptedAnswer":{"@type":"Answer","text":"Hyderabad"},'
                '"suggestedAnswer":[{"@type":"Answer","text":"Hyderabad"},'
                '{"@type":"Answer","text":"Warangal"},'
                '{"@type":"Answer","text":"Nizamabad"},'
                '{"@type":"Answer","text":"Karimnagar"}]}]}'
                '</script></head><body></body></html>')
        raws = collector.parse_page({}, html, "t", "u")
        self.assertEqual(len(raws), 1)
        self.assertEqual(raws[0]["answer_index"], 0)
        self.assertEqual(raws[0]["options_en"][0], "Hyderabad")

    def test_next_data_index_and_text_answers(self):
        html = ('<script id="__NEXT_DATA__" type="application/json">'
                '{"props":{"questions":['
                '{"question":"What is 20% of 500?",'
                '"options":["100","200","50","150"],"answer_index":0,'
                '"explanation":"500*0.2=100"},'
                '{"question":"Capital of India is which city?",'
                '"options":["Mumbai","Chennai","Delhi","Kolkata"],'
                '"correctAnswer":"Delhi"}]}}</script>')
        raws = collector.parse_page({}, html, "t", "u")
        self.assertEqual(len(raws), 2)
        self.assertEqual([r["answer_index"] for r in raws], [0, 2])
        self.assertEqual(raws[0]["explanation_en"], "500*0.2=100")

    def test_window_assignment_one_based_answer(self):
        html = ('<script>window.__Q__ = {"questions":[{"q":'
                '"Ramappa temple is located in which state?",'
                '"choices":["Telangana","Kerala","Punjab","Goa"],'
                '"answer":1,"solution":"In Telangana."}]};</script>')
        raws = collector.parse_page({}, html, "t", "u")
        self.assertEqual(len(raws), 1)
        self.assertEqual(raws[0]["answer_index"], 0)   # 1-based "1" -> idx 0

    def test_embedded_and_text_never_duplicate(self):
        html = ('<script type="application/json">{"questions":[{"question":'
                '"Capital of Telangana is which city?",'
                '"options":["Warangal","Hyderabad","Nizamabad","Karimnagar"],'
                '"answer_index":1}]}</script>'
                '<article><p>1. Capital of Telangana is which city?</p>'
                '<p>A) Warangal</p><p>B) Hyderabad</p><p>C) Nizamabad</p>'
                '<p>D) Karimnagar</p><p>Answer: B</p></article>')
        raws = collector.parse_page({}, html, "t", "u")
        self.assertEqual(len(raws), 1)


class TestNewTextFormats(unittest.TestCase):
    def _parse(self, lines):
        return collector.parse_quiz_lines(lines, "t", "u")

    def test_table_layout_not_glued(self):
        html = ('<article><table>'
                '<tr><td>1. Capital of Telangana?</td></tr>'
                '<tr><td>A) Warangal</td><td>B) Hyderabad</td></tr>'
                '<tr><td>C) Nizamabad</td><td>D) Karimnagar</td></tr>'
                '<tr><td>Answer: B</td></tr></table></article>')
        raws = collector.parse_page({}, html, "t", "u")
        self.assertEqual(len(raws), 1)
        self.assertEqual(raws[0]["options_en"],
                         ["Warangal", "Hyderabad", "Nizamabad", "Karimnagar"])

    def test_dash_options(self):
        raws = self._parse(["1. Capital of Telangana?",
                            "A - Warangal", "B - Hyderabad",
                            "C - Nizamabad", "D - Karimnagar", "Answer: B"])
        self.assertEqual(len(raws), 1)
        self.assertEqual(raws[0]["answer_index"], 1)

    def test_answer_as_option_text(self):
        raws = self._parse(["1. Capital of Telangana?",
                            "A) Warangal", "B) Hyderabad",
                            "C) Nizamabad", "D) Karimnagar",
                            "Answer: Hyderabad"])
        self.assertEqual(len(raws), 1)
        self.assertEqual(raws[0]["answer_index"], 1)

    def test_unnumbered_question(self):
        raws = self._parse(["Which is the capital of Telangana?",
                            "A) Warangal", "B) Hyderabad",
                            "C) Nizamabad", "D) Karimnagar", "Answer: B"])
        self.assertEqual(len(raws), 1)
        self.assertEqual(raws[0]["answer_index"], 1)

    def test_unnumbered_does_not_split_substatements(self):
        html = (ROOT / "tests" / "fixture_gktoday.html").read_text(
            encoding="utf-8")
        raws = collector.parse_quiz_lines(collector.html_to_lines(html),
                                          "Quiz", "x")
        self.assertEqual(len(raws), 4)
        self.assertIn("1. Manikyamba", raws[2]["q_en"])

    def test_small_answer_key_table(self):
        raws = self._parse([
            "1. Capital of Telangana?",
            "A) Warangal", "B) Hyderabad", "C) Nizamabad", "D) Karimnagar",
            "2. Capital of India?",
            "A) Mumbai", "B) Delhi", "C) Chennai", "D) Kolkata",
            "Answers: 1-B 2-B"])
        self.assertEqual(len(raws), 2)
        self.assertEqual([r["answer_index"] for r in raws], [1, 1])


class TestFeedsV2(unittest.TestCase):
    def _entries(self, xml):
        with mock.patch.object(collector, "http_get", return_value=xml):
            return collector._feed_entries("https://x/feed")

    def test_rdf_feed_freshest_first(self):
        xml = ('<?xml version="1.0"?><rdf:RDF '
               'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
               'xmlns="http://purl.org/rss/1.0/" '
               'xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<item rdf:about="https://x/q1"><title>Quiz Old</title>'
               '<link>https://x/q1</link>'
               '<dc:date>2026-01-01T00:00:00Z</dc:date></item>'
               '<item rdf:about="https://x/q2"><title>Quiz New</title>'
               '<link>https://x/q2</link>'
               '<dc:date>2026-09-01T00:00:00Z</dc:date></item></rdf:RDF>')
        entries = self._entries(xml)
        self.assertEqual([e["link"] for e in entries],
                         ["https://x/q2", "https://x/q1"])

    def test_atom_prefers_alternate_link(self):
        xml = ('<?xml version="1.0"?><feed '
               'xmlns="http://www.w3.org/2005/Atom"><entry>'
               '<title>Quiz 1</title>'
               '<link rel="self" href="https://x/feed"/>'
               '<link rel="alternate" href="https://x/q1"/>'
               '<updated>2026-01-01T00:00:00Z</updated></entry></feed>')
        entries = self._entries(xml)
        self.assertEqual(entries[0]["link"], "https://x/q1")

    def test_feed_with_html_entities_still_parses(self):
        xml = ('<?xml version="1.0"?><rss version="2.0"><channel>'
               '<item><title>Daily Quiz&nbsp;2026</title>'
               '<link>https://x/a</link>'
               '<pubDate>Mon, 01 Sep 2026 10:00:00 GMT</pubDate></item>'
               '</channel></rss>')
        entries = self._entries(xml)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "Daily Quiz 2026")

    def test_sitemap_links(self):
        xml = ('<?xml version="1.0"?><urlset>'
               '<url><loc>https://x/daily-quiz-1/</loc></url>'
               '<url><loc>https://x/about/</loc></url>'
               '<url><loc>https://x/daily-quiz-2/</loc></url></urlset>')
        links = collector.sitemap_links(xml, r"daily-quiz")
        self.assertEqual([lk["link"] for lk in links],
                         ["https://x/daily-quiz-1/", "https://x/daily-quiz-2/"])


class _FakeResp:
    def __init__(self, raw, headers=None):
        self._raw, self.headers = raw, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._raw


class TestFetchV2(unittest.TestCase):
    def test_gzip_body_decoded(self):
        body = gzip.compress("<article>quiz</article>".encode())
        fake = _FakeResp(body, {"Content-Type": "text/html; charset=utf-8",
                                "Content-Encoding": "gzip"})
        with mock.patch.object(collector, "robots_allowed",
                               return_value=True), \
                mock.patch.object(collector, "_sleep_polite",
                                  return_value=None), \
                mock.patch.object(collector.urllib.request, "urlopen",
                                  return_value=fake):
            self.assertEqual(collector.http_get("https://x/q"),
                             "<article>quiz</article>")

    def test_registry_defaults_wired(self):
        self.assertEqual(collector._cfg_default("max_questions_per_run", 1),
                         200)
        self.assertEqual(collector._cfg_default("polite_delay_sec", 9), 2.0)
        self.assertEqual(collector._cfg_default("no_such_key", 7), 7)


class TestSeenRetry(unittest.TestCase):
    """A failed article fetch must NOT be marked seen — it is retried."""

    def test_failed_fetch_retried_next_run(self):
        tmp = Path(tempfile.mkdtemp())
        saved = {k: getattr(collector, k) for k in
                 ("SCRAPED_BANK", "PENDING", "SEEN_URLS", "HEALTH",
                  "_sources", "_feed_entries", "http_get")}
        src = {"name": "FakeRSS", "type": "rss", "exam": "all",
               "feed": "https://x/feed", "title_must": r"quiz",
               "title_not": r"(?!)\Z"}
        html = (ROOT / "tests" / "fixture_quiz.html").read_text(
            encoding="utf-8")
        try:
            collector.SCRAPED_BANK = tmp / "bank.json"
            collector.PENDING = tmp / "pending.json"
            collector.SEEN_URLS = tmp / "seen.json"
            collector.HEALTH = tmp / "health.json"
            collector._sources = lambda: [dict(src)]
            collector._feed_entries = lambda url: [
                {"title": "Daily Quiz", "link": "https://x/q1",
                 "published": ""}]
            collector.http_get = lambda url, **k: None     # site down
            collector.collect_daily()
            self.assertNotIn("https://x/q1", collector.load_seen_urls())
            collector.http_get = lambda url, **k: html     # site back
            st = collector.collect_daily()
            self.assertEqual(st["parsed"], 4)
            self.assertIn("https://x/q1", collector.load_seen_urls())
        finally:
            for k, v in saved.items():
                setattr(collector, k, v)


class TestPollPostingGuarantee(unittest.TestCase):
    """Every bank question must become a Telegram-legal quiz poll whose
    correct_option_id still points at the truly-correct option after
    send-time balancing (this is what 'polls post correctly' means)."""

    def test_all_bank_questions_build_correct_polls(self):
        from core.question_bank import load_bank
        from core.content import (build_options, build_question_text,
                                  poll_safe, validate_question)
        from core import config
        checked = 0
        for q in load_bank():
            if q.get("channel") not in config.CHANNELS:
                continue      # academic/custom channels post via their own cfg
            self.assertEqual(validate_question(q), [], q.get("id"))
            sq = poll_safe(q, seed="20260101")
            if sq is None:                 # leak-guarded: skipped, by design
                continue
            cfg = config.CHANNELS[sq["channel"]]
            text = build_question_text(sq, cfg, position="Q 10/10")
            opts = build_options(sq)
            self.assertLessEqual(len(text), 300, sq["id"])
            self.assertEqual(len(opts), 4, sq["id"])
            self.assertTrue(all(0 < len(o) <= 100 for o in opts), sq["id"])
            # balanced copy: correct slot holds the ORIGINAL correct option
            orig = q["options_en"][q["answer_index"]].strip().lower()
            now = sq["options_en"][sq["answer_index"]].strip().lower()
            self.assertEqual(orig, now, sq["id"])
            checked += 1
        self.assertGreaterEqual(checked, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
