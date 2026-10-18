# -*- coding: utf-8 -*-
"""🚀 240X: FAANG-level architect audit fixes (security hardening).

Pins (source-level, same never-import-dashboard rule as 160X):
  • /api/admin/harvest_run is behind _authed() (it previously sat
    before the deny-by-default gate with NO check — found by audit).
  • Dashboard password compared in constant time.
  • POST payload cap (5 MB -> 413) with safe Content-Length parsing.
  • Baseline security headers from the 3 central senders.
  • Secure cookie flag when served over https.
  • Go-live checks warn when the DEFAULT dashboard password is used.
  • The audit report itself exists with all 8 CTO sections.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH = (ROOT / "scripts" / "dashboard_server.py").read_text()


class TestSecurity240(unittest.TestCase):
    def test_harvest_run_requires_admin(self):
        i = DASH.find('"/api/admin/harvest_run"')
        self.assertGreater(i, 0)
        block = DASH[i:i + 400]
        self.assertIn("self._authed()", block)
        self.assertIn("401", block)

    def test_materials_add_still_guarded(self):
        i = DASH.find('"/api/admin/materials_add"')
        self.assertIn("self._authed()", DASH[i:i + 300])

    def test_constant_time_password_compare(self):
        self.assertIn("hmac.compare_digest(pw, _dash_password())", DASH)
        self.assertNotIn("pw == _dash_password()", DASH)
        self.assertIn("import hmac", DASH)

    def test_body_cap(self):
        self.assertIn("5_000_000", DASH)
        self.assertIn("payload too large", DASH)
        self.assertIn("413", DASH)

    def test_security_headers(self):
        for h in ("X-Content-Type-Options", "nosniff", "X-Frame-Options",
                  "SAMEORIGIN", "Referrer-Policy"):
            self.assertIn(h, DASH)
        self.assertGreaterEqual(DASH.count("self._sec_headers()"), 3)

    def test_cookie_secure_on_https(self):
        self.assertIn('"; Secure"', DASH)
        self.assertIn("X-Forwarded-Proto", DASH)
        self.assertIn("HttpOnly; SameSite=Lax", DASH)

    def test_golive_password_warning(self):
        i = DASH.find("def _golive_checks")
        seg = DASH[i:i + 6000]
        self.assertIn("Dashboard password", seg)
        self.assertIn("DEFAULT_DASH_PASSWORD", seg)


class TestAuditDoc240(unittest.TestCase):
    def test_report_has_all_sections(self):
        p = ROOT / "docs" / "ARCHITECTURE_AUDIT_240X.md"
        self.assertTrue(p.exists())
        txt = p.read_text()
        for sec in ("ARCHITECTURE", "CODE REVIEW", "PERFORMANCE",
                    "SECURITY", "DATABASE", "DEVOPS", "AI", "TESTING"):
            self.assertIn(sec, txt)
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            self.assertIn(sev, txt)


if __name__ == "__main__":
    unittest.main()
