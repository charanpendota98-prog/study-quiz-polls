# -*- coding: utf-8 -*-
"""300X — Theme Studio Pro: aurora/paper/exam-focus themes, 🌓 auto
day/night, font-size + calm accessibility, and an appearance engine
that composes theme/font/calm WITHOUT wiping the lang-te/lang-en
classes (the old setTheme reset body.className on every tap).
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")


class TestThemeStudioPro(unittest.TestCase):
    def test_registry_has_12_themes(self):
        m = re.search(r"const THEMES300 = \[(.*?)\];", SRC)
        self.assertIsNotNone(m)
        for t in ("ocean", "sunset", "forest", "light", "royal", "grape",
                  "rose", "aurora", "paper", "focus", "auto"):
            self.assertIn(f"'{t}'", m.group(1))

    def test_new_theme_css_defined(self):
        for cls in ("body.theme-aurora", "body.theme-paper",
                    "body.theme-focus"):
            self.assertIn(cls, SRC)
        self.assertIn("body.theme-paper .opt", SRC)   # reading comfort
        self.assertIn("body.theme-focus .card", SRC)  # exam contrast

    def test_chips_present(self):
        for th in ("aurora", "paper", "focus", "auto"):
            self.assertIn(f'data-th="{th}"', SRC)
        for fs in ("s", "m", "l"):
            self.assertIn(f'data-fs="{fs}"', SRC)
        self.assertIn('data-calm="1"', SRC)

    def test_auto_day_night_logic(self):
        self.assertIn("new Date().getHours()", SRC)
        self.assertIn("(h >= 6 && h < 19) ? 'light' : ''", SRC)
        self.assertIn("}, 60000);", SRC)  # auto re-evaluates every minute

    def test_engine_preserves_lang_classes(self):
        self.assertIn("classList.contains('lang-te')", SRC)
        self.assertIn("classList.contains('lang-en')", SRC)
        # Scope: the PORTAL script (with applyAppearance) must not use the
        # old class-wiping assignment. The separate admin template's
        # setSiteTheme has no lang classes to preserve — out of scope.
        blocks = re.findall(r"<script>(.*?)</script>", SRC, flags=re.S)
        portal = [b for b in blocks if "applyAppearance" in b]
        self.assertTrue(portal)
        self.assertNotIn("document.body.className = t ? ('theme-' + t) : '';",
                         portal[0],
                         "old class-wiping setTheme must stay gone (portal)")

    def test_font_and_calm_persist(self):
        for key in ("su_theme", "su_font", "su_calm", "su_accent"):
            self.assertIn(key, SRC)
        self.assertIn("['s', 'm', 'l'].includes(fs)", SRC)
        self.assertIn("body.font-l .qte", SRC)
        self.assertIn("body.font-s .opt", SRC)
        self.assertIn("body.calm *", SRC)

    def test_settheme_validates(self):
        self.assertIn("THEMES300.includes(t) ? t : ''", SRC)

    def test_esc_still_quote_safe(self):
        defs = re.findall(r"const esc = .*", SRC)
        self.assertGreaterEqual(len(defs), 3)
        for d in defs:
            self.assertIn("&#39;", d)

    @unittest.skipUnless(shutil.which("node"), "node not available")
    def test_portal_js_syntax_valid(self):
        blocks = re.findall(r"<script>(.*?)</script>", SRC, flags=re.S)
        portal = [b for b in blocks if "applyAppearance" in b]
        self.assertTrue(portal, "portal script block not found")
        with tempfile.NamedTemporaryFile(
                "w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(portal[0])
            name = f.name
        r = subprocess.run(["node", "--check", name],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[:400])


if __name__ == "__main__":
    unittest.main()
