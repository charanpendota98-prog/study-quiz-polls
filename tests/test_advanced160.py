# -*- coding: utf-8 -*-
"""🚀 160X Subdomain Go-Live Kit.

Pins (probe-verified):
  • _golive_checks: readiness list (PUBLIC_BASE_URL, Portal URL,
    BOT_TOKEN, bot username, WP snippet, PWA, AdSense) + overall
  • Secrets never leak: only configured/unset booleans + names
  • Routes/UI: /api/health/golive + health/full carries golive +
    admin renders the Go-Live card
  • docs/SUBDOMAIN_GO_LIVE.md + .env.example carry the exact keys
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


class TestGoLive160(unittest.TestCase):
    def test_checks_shape_no_secrets(self):
        # NOTE: dashboard_server ni import chesthe heavy package init
        # (collector) bank channels ni mutate chesthundi — anduke ikkada
        # function ni AST nunchi isolate chesi exec chestham (side-effect
        # free). Wiring tests (kindha) source text meda pin chesthayi.
        import ast
        src = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_golive_checks")
        import core.config as _cfg
        from pathlib import Path as _P

        class _Cfg:
            env = staticmethod(_cfg.env)
            BOT_TOKEN = getattr(_cfg, "BOT_TOKEN", "")

        ns = {"config": _Cfg, "Path": _P, "__file__": str(
            ROOT / "scripts" / "dashboard_server.py"),
            "_bot_username": lambda: "StudentUpBot"}
        exec(compile(ast.Module(body=[fn], type_ignores=[]),
                     "<golive>", "exec"), ns)
        g = ns["_golive_checks"]()
        self.assertIn(g["overall"], ("ready", "pending"))
        names = [c["name"] for c in g["checks"]]
        for want in ("PUBLIC_BASE_URL", "Portal URL", "BOT_TOKEN",
                     "Bot username", "WP portal icon snippet", "PWA (manifest + SW v4)"):
            self.assertIn(want, names)
        blob = str(g)
        # only booleans/details — never a token value
        self.assertNotIn("api.telegram.org", blob)
        bot_check = [c for c in g["checks"]
                     if c["name"] == "BOT_TOKEN"][0]
        self.assertIn(bot_check["detail"], ("configured",
                                            "bot features (WebApp login, broadcasts) pani cheyyavu"))
        self.assertIn(bot_check["status"], ("ok", "fail"))


class TestWiring160(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        cls.doc = (ROOT / "docs" / "SUBDOMAIN_GO_LIVE.md").read_text(
            encoding="utf-8")
        cls.env = (ROOT / ".env.example").read_text(encoding="utf-8")

    def test_wiring(self):
        self.assertIn('p.path == "/api/health/golive"', self.dash)
        self.assertIn('rep["golive"] = _golive_checks()', self.dash)
        self.assertIn("h.golive.overall", self.dash)
        for key in ("PUBLIC_BASE_URL=https://quiz.studentup.in",
                    "PORTAL_BASE_URL=https://quiz.studentup.in/portal"):
            self.assertIn(key, self.env)
            self.assertIn(key, self.doc)
        self.assertIn("studentup-portal-icon.html", self.doc)


if __name__ == "__main__":
    unittest.main()
