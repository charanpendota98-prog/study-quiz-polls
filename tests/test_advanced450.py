# -*- coding: utf-8 -*-
"""450X — Dashboard perfection audit: the served JS must LIVE.

The audit found the worst mistake class yet: PORTAL_HTML and
HTML_PAGE were plain (non-raw) Python strings, so Python ate
every `\'` escape the JS authors wrote — the served inline
<script> of BOTH the student portal and the admin dashboard
had hard syntax errors (portal: downloadKey history row;
admin: paperDraftAct buttons) and the whole page script was
dead in the browser while every HTTP smoke still returned 200.

Pins (no node needed — pure Python, fails on the old code):
  * both page constants are raw strings in the source;
  * the exact historically-broken lines serve with their JS
    escapes intact;
  * every onclick handler used in a page is defined in that
    same page's script (the addMaterial230/runHarvest230
    cross-page leak is closed);
  * when node IS available, every inline script of every page
    must pass `node --check` (skipped cleanly without node).
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SRC = (ROOT / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
import dashboard_server as dash  # noqa: E402

PAGES = ("HTML_PAGE", "PORTAL_HTML", "WEB_EXAM_HTML", "LOGIN_PAGE")


def _js_blocks(html):
    return [b for b in re.findall(r'<script(?![^>]*src)[^>]*>(.*?)</script>',
                                  html, re.S)
            if not b.lstrip().startswith("{")]   # JSON-LD data block


def _defs(js):
    s = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)", js))
    s |= set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)"
                        r"\s*=\s*(?:async\s*)?(?:function|\()", js))
    s |= set(re.findall(r"([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?"
                        r"(?:function|\()", js))
    s |= set(re.findall(r"window\.([A-Za-z_$][\w$]*)\s*=", js))
    return s


class TestRawPages(unittest.TestCase):
    def test_pages_are_raw_strings(self):
        for name in ("PORTAL_HTML", "HTML_PAGE"):
            self.assertRegex(SRC, rf"(?m)^{name} = r\"\"\"", name)

    def test_historically_broken_lines_serve_escaped(self):
        portal_js = "\n".join(_js_blocks(dash.PORTAL_HTML))
        admin_js = "\n".join(_js_blocks(dash.HTML_PAGE))
        # portal history Key button + admin Paper Factory buttons
        self.assertIn(r"downloadKey(\'' + h.kind + '\'", portal_js)
        self.assertIn(r"paperDraftAct(\'approve\'", admin_js)
        # the pre-fix served (dead) shapes must never come back
        self.assertNotIn("downloadKey('' +", portal_js)
        self.assertNotIn("paperDraftAct('approve',''", admin_js)

    def test_squad_replace_not_pre_doubled(self):
        admin_js = "\n".join(_js_blocks(dash.HTML_PAGE))
        self.assertIn('replace(/\'/g, "\\\'")', admin_js)
        self.assertNotIn(r'''replace(/'/g, "\\'")''', admin_js)


class TestHandlerClosure(unittest.TestCase):
    def test_every_onclick_handler_defined_in_its_page(self):
        for name in PAGES:
            html = getattr(dash, name)
            js = "\n".join(_js_blocks(html))
            handlers = set(re.findall(r'onclick="([A-Za-z_$][\w$]*)\(',
                                      html))
            missing = sorted(h for h in handlers
                             if h not in _defs(js)
                             and h not in ("if", "for", "while", "return"))
            self.assertEqual(missing, [], f"{name}: {missing}")

    def test_admin_230_functions_live_in_admin_page(self):
        admin_js = "\n".join(_js_blocks(dash.HTML_PAGE))
        self.assertIn("async function addMaterial230()", admin_js)
        self.assertIn("async function runHarvest230()", admin_js)
        self.assertIn("fetch('/api/admin/materials_add'", admin_js)
        self.assertIn("fetch('/api/admin/harvest_run'", admin_js)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TestNodeSyntax(unittest.TestCase):
    def test_all_inline_scripts_parse(self):
        for name in PAGES:
            html = getattr(dash, name)
            for i, block in enumerate(_js_blocks(html)):
                with tempfile.NamedTemporaryFile(
                        "w", suffix=".js", delete=False,
                        encoding="utf-8") as f:
                    f.write(block)
                    path = f.name
                r = subprocess.run(["node", "--check", path],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0,
                                 f"{name} block {i}: {r.stderr[:300]}")


if __name__ == "__main__":
    unittest.main()
