# -*- coding: utf-8 -*-
"""🌍 Public Website + AdSense kit (subdomain/domain readiness).

Pins: public pages exist without login (home/about/privacy/terms/contact/
study), "/" shows public site to visitors but dashboard to the organiser,
ads appear ONLY on public pages and ONLY when ADSENSE_* env is configured,
ads.txt/robots/sitemap are served, exam pages never carry ads.
dashboard_server is imported lazily (it pulls channel_router like the
other WA modules — importing it at discovery time is a known trap).
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

DASH = (Path(__file__).resolve().parent.parent
        / "scripts" / "dashboard_server.py")


def _ds():
    import dashboard_server as ds
    return ds


class TestPublicSite(unittest.TestCase):
    def test_public_routes_wired_before_auth(self):
        src = DASH.read_text(encoding="utf-8")
        for needle in ('PUBLIC_PAGE_PATHS', '"/ads.txt"', '"/robots.txt"',
                       '"/sitemap.xml"', 'public_page(self, "home")', '_send_text(' ,
                       "ads_txt_content()", 'Disallow: /exam/',
                       '"/privacy"'):
            self.assertIn(needle, src)
        # public pages must not be behind the admin deny
        pub_idx = src.index("# 🌍 Public Website + AdSense kit")
        deny_idx = src.index('self._deny(is_api=p.path.startswith("/api/"))')
        self.assertLess(pub_idx, deny_idx)

    def test_exam_page_has_no_ads(self):
        src = DASH.read_text(encoding="utf-8")
        start = src.index("WEB_EXAM_HTML")
        end = src.index("def _bot_username")
        exam_block = src[start:end]
        self.assertNotIn("adsbygoogle", exam_block)
        self.assertNotIn("ADSENSE", exam_block)

    def test_pages_render_and_ads_env_gated(self):
        ds = _ds()
        clean = {k: v for k, v in os.environ.items()
                 if not k.startswith("ADSENSE")}
        with mock.patch.dict(os.environ, clean, clear=True):
            home = ds.public_page(None, "home")
            self.assertIn("College Exams", home)
            self.assertIn("exam-entry", home)          # code → /exam/ entry
            self.assertNotIn("adsbygoogle", home)      # no env → no ads
            self.assertEqual(ds.ads_txt_content(), "")
            for pg in ("about", "privacy", "terms", "contact", "study"):
                self.assertGreater(len(ds.public_page(None, pg)), 800)
            self.assertIn("AdSense", ds.public_page(None, "privacy"))
        env = dict(clean, ADSENSE_CLIENT_ID="ca-pub-1234567890123456",
                   ADSENSE_SLOT_HOME="987654321")
        with mock.patch.dict(os.environ, env, clear=True):
            home = ds.public_page(None, "home")
            self.assertIn("adsbygoogle", home)
            self.assertIn("ca-pub-1234567890123456", home)
            self.assertEqual(ds.ads_txt_content(),
                             "google.com, pub-1234567890123456, DIRECT, "
                             "f08c47fec0942fa0\n")
            # ad UNITS only where slots are placed (home/study); policy
            # pages never carry units (loader script in head is site-wide)
            self.assertNotIn('<ins class="adsbygoogle"',
                             ds.public_page(None, "terms"))
            self.assertIn('<ins class="adsbygoogle"',
                          ds.public_page(None, "home"))

    def test_robots_and_sitemap(self):
        ds = _ds()
        r = ds.robots_txt(None)
        self.assertIn("Disallow: /api/", r)
        self.assertIn("Disallow: /exam/", r)       # sessions not indexed
        sm = ds.sitemap_xml(None)
        for u in ("/study", "/about", "/privacy", "/terms", "/contact"):
            self.assertIn(u, sm)


if __name__ == "__main__":
    unittest.main()
