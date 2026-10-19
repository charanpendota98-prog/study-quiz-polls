# -*- coding: utf-8 -*-
"""290X — stored-XSS root fix.

Display names enter from attacker-controlled surfaces (Telegram
profiles, chat registration, portal forms) and are rendered into
leaderboards, winners walls and the admin dashboard. 290X cleans ONCE
at write time (core/textsafe) at every entry point, and upgrades every
dashboard esc() to be quote-safe as defense-in-depth.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import textsafe  # noqa: E402


class TestTextsafe(unittest.TestCase):
    def test_script_payload_neutralized(self):
        out = textsafe.clean_display_name('<script>alert(1)</script>Raju')
        for ch in '<>"\'&`/\\':
            self.assertNotIn(ch, out)
        self.assertIn("Raju", out)

    def test_img_onerror_neutralized(self):
        out = textsafe.clean_display_name('x"><img src=x onerror=alert(1)>')
        self.assertNotIn("<", out)
        self.assertNotIn('"', out)
        self.assertNotIn(">", out)

    def test_telugu_names_preserved(self):
        self.assertEqual(textsafe.clean_display_name("రాజు కుమార్"),
                         "రాజు కుమార్")
        self.assertEqual(textsafe.clean_display_name("Ananya Reddy"),
                         "Ananya Reddy")

    def test_normal_punctuation_kept(self):
        self.assertEqual(textsafe.clean_display_name("Md. Abdul-Rahim"),
                         "Md. Abdul-Rahim")

    def test_whitespace_and_controls(self):
        self.assertEqual(textsafe.clean_display_name("  Sai \t\n Kumar  "),
                         "Sai Kumar")
        self.assertEqual(textsafe.clean_display_name("a\x00b\x7fc"), "a b c")

    def test_zero_width_stripped(self):
        self.assertNotIn("​", textsafe.clean_display_name("Ra​ju"))

    def test_length_cap_and_empty(self):
        self.assertEqual(len(textsafe.clean_display_name("x" * 200)), 60)
        self.assertEqual(textsafe.clean_display_name(None), "")
        self.assertEqual(textsafe.clean_display_name("<><>"), "")
        self.assertEqual(textsafe.clean_display_name("  ok  ", max_len=2), "ok")

    def test_contains_markup(self):
        self.assertTrue(textsafe.contains_markup("<b>x</b>"))
        self.assertFalse(textsafe.contains_markup("Plain Name"))


class TestWritePathWiring(unittest.TestCase):
    def _src(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_members_register_and_poll_auto_clean(self):
        src = self._src("scripts/core/members.py")
        self.assertGreaterEqual(
            src.count("textsafe.clean_display_name"), 2,
            "register + poll-auto paths must both clean names")

    def test_portal_and_stateless_clean(self):
        self.assertIn("textsafe.clean_display_name",
                      self._src("scripts/core/portal.py"))
        self.assertIn("textsafe.clean_display_name",
                      self._src("scripts/core/stateless_client.py"))

    def test_campus_paths_clean(self):
        src = self._src("scripts/core/campus.py")
        self.assertGreaterEqual(src.count("textsafe.clean_display_name"), 3,
                                "web-exam register + event + join-request")

    def test_dashboard_esc_quote_safe_everywhere(self):
        src = self._src("scripts/dashboard_server.py")
        defs = re.findall(r"const esc = .*", src)
        self.assertGreaterEqual(len(defs), 3)
        for d in defs:
            self.assertIn("&gt;", d)
            self.assertIn("&quot;", d)
            self.assertIn("&#39;", d, f"weak esc remains: {d}")


class TestMembersFunctional(unittest.TestCase):
    def setUp(self):
        from core import members
        self.members_mod = members
        self._tmp = tempfile.TemporaryDirectory()
        self._old = members.config.DATA
        members.config.DATA = Path(self._tmp.name)
        self.m = members.Members()

    def tearDown(self):
        self.members_mod.config.DATA = self._old
        self._tmp.cleanup()

    def test_register_cleans_name(self):
        self.m.register(42, name='<img src=x onerror=alert(1)> evil')
        name = self.m.members["42"]["name"]
        for ch in '<>"\'&':
            self.assertNotIn(ch, name)
        self.assertIn("evil", name)

    def test_poll_auto_cleans_telegram_name(self):
        self.m.auto_register_from_poll(
            77, {"first_name": "<script>x</script>", "last_name": 'a"b',
                 "username": "ok_user"})
        name = self.m.members["77"]["name"]
        for ch in '<>"\'':
            self.assertNotIn(ch, name)

    def test_clean_name_roundtrip_unchanged(self):
        self.m.register(43, name="Sravani Reddy")
        self.assertEqual(self.m.members["43"]["name"], "Sravani Reddy")


if __name__ == "__main__":
    unittest.main()
