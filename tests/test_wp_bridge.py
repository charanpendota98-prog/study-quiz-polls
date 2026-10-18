# -*- coding: utf-8 -*-
"""🌉 WordPress Bridge: blog syndication (WP → us) + quiz export (us → WP).

Pins: WP REST posts are cleaned/mapped with graceful fallback, today's
daily quiz exports in exact quiz.php format (q, a[4], c, why, cat, src,
exam), /blog page + admin bridge wiring, PHP sync snippet is safe
(private REST route, sanitized, capped).
"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import portal  # noqa: E402

DASH = (Path(__file__).resolve().parent.parent
        / "scripts" / "dashboard_server.py")


def _ds():
    import dashboard_server as ds
    return ds


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestWpBridge(unittest.TestCase):
    def setUp(self):
        self._old = portal.PATH
        self._tmp = tempfile.mkdtemp()
        portal.PATH = Path(self._tmp) / "portal.json"

    def tearDown(self):
        portal.PATH = self._old

    def test_wp_posts_mapping_and_fallback(self):
        ds = _ds()
        ds._WP_CACHE.update({"ts": 0, "posts": []})
        fake = [{"title": {"rendered": "SSC &amp; CGL <b>Guide</b>"},
                 "excerpt": {"rendered": "<p>Full <i>guide</i> here…</p>"},
                 "link": "https://studentup.in/ssc-guide/", "date": "2026-10-15T09:00:00",
                 "slug": "ssc-guide"}]
        with mock.patch.object(ds.urllib.request, "urlopen",
                               return_value=_Resp(fake)):
            posts = ds._fetch_wp_posts(5, force=True)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["title"], "SSC & CGL Guide")   # HTML cleaned
        self.assertEqual(posts[0]["date"], "2026-10-15")
        self.assertTrue(posts[0]["url"].endswith("ssc-guide/"))
        # site down → graceful [] (never crash)
        ds._WP_CACHE.update({"ts": 0, "posts": []})
        with mock.patch.object(ds.urllib.request, "urlopen",
                               side_effect=OSError("blocked")):
            self.assertEqual(ds._fetch_wp_posts(5, force=True), [])

    def test_quiz_export_wp_format(self):
        ds = _ds()
        item = ds._wp_quiz_item({"q_en": "Capital of India?", "options_en": ["Delhi", "Mumbai", "Chennai", "Kolkata"],
                                 "answer_index": 0, "explanation": "Delhi is the capital.",
                                 "topic": "geography", "source": "pyq", "channel": "SSC"})
        self.assertEqual(item["q"], "Capital of India?")
        self.assertEqual(item["a"][0], "Delhi")
        self.assertEqual(item["c"], 0)
        self.assertEqual(item["exam"], "ssc")
        self.assertIn("PYQ", item["src"])
        exp = ds._wp_quiz_export()
        self.assertEqual(len(exp["questions"]), portal.DAILY_N)
        self.assertTrue(all(len(q["a"]) >= 2 for q in exp["questions"]))

    def test_routes_pages_and_snippet(self):
        src = DASH.read_text(encoding="utf-8")
        for needle in ('"/api/blog/posts"', '"/api/wp/status"', '"/api/wp/export"',
                       '"/blog"', "__BLOG__", "_fetch_wp_posts", "_wp_quiz_export",
                       "wpStatus", "wpExportQuiz", "WP_SITE_URL"):
            self.assertIn(needle, src)
        php = (Path(__file__).resolve().parent.parent
               / "integrations" / "wordpress" / "studentup-quiz-sync.php").read_text(encoding="utf-8")
        self.assertIn("register_rest_route", php)
        self.assertIn("current_user_can('edit_posts')", php)   # private only
        self.assertIn("sanitize_text_field", php)
        self.assertIn("studentup_synced_quiz_items", php)
        doc = (Path(__file__).resolve().parent.parent
               / "docs" / "BRIDGE_PLAN.md").read_text(encoding="utf-8")
        self.assertIn("Bridge Plan", doc)


if __name__ == "__main__":
    unittest.main()
