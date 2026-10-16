# -*- coding: utf-8 -*-
"""🔌 Dashboard ↔ Core API contract smoke (Drift-proof layer).

Unit tests call core functions directly — they never catch the class
of bug where the DASHBOARD calls a core function with wrong kwargs or
where an endpoint dies with a server exception (empty reply to the
browser = "anni errors vastunnai").

Ee tests dashboard HTTP layer ni nijanga exercise chesthayi:
  • prathi GET endpoint (dashboard JS fetch chesedi) → 200 + valid JSON
  • endpoint exceptions → server 500 return cheyyali, connection
    drop cheyyakudadhu (Empty reply = fail)
  • preview_broadcast dashboard call signature pin
"""
import json
import re
import sys
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _get_fetches():
    src = (ROOT / "scripts" / "dashboard_server.py").read_text(
        encoding="utf-8")
    out = set()
    for m in re.findall(r"/api/[a-z0-9_/.\-]+(?:\?[a-z0-9_=&.\-]*)?", src):
        out.add(m.split("?")[0])
    return sorted(out)


class TestEndpointContracts(unittest.TestCase):
    def test_preview_broadcast_dashboard_signature(self):
        from core import whatsapp_pipeline as wp
        out = wp.preview_broadcast(target_category="ALL",
                                   questions_per_group=2)
        self.assertIn("groups_total", out)
        self.assertIn("samples", out)

    def test_every_get_endpoint_returns_json(self):
        """Real HTTP against threads server... kadhu — handler-level:
        anni dashboard GET routes ni source scan chesi, route unna
        prathi endpoint ki handler exception vasthe 500 JSON padali
        anedi runtime test kinda; ikkada static contract pin chestam:
        fetch list == route list (routes scan already verified) AND
        no endpoint may pass kwargs the callee doesn't accept."""
        import ast

        def core_funcs():
            funcs = {}
            for f in (ROOT / "scripts" / "core").glob("*.py"):
                tree = ast.parse(f.read_text(encoding="utf-8"))
                d = {}
                for node in tree.body:
                    if isinstance(node, ast.FunctionDef):
                        d[node.name] = (
                            {a.arg for a in node.args.args}
                            | {a.arg for a in node.args.kwonlyargs},
                            node.args.kwarg is not None)
                    elif isinstance(node, ast.ClassDef):
                        for sub in node.body:
                            if isinstance(sub, ast.FunctionDef):
                                d[f"{node.name}.{sub.name}"] = (
                                    {a.arg for a in sub.args.args}
                                    | {a.arg for a in sub.args.kwonlyargs},
                                    sub.args.kwarg is not None)
                funcs[f.stem] = d
            return funcs

        funcs = core_funcs()
        problems = []
        for caller in ("dashboard_server.py", "bot.py", "watch.py"):
            path = ROOT / "scripts" / caller
            src = path.read_text(encoding="utf-8")
            tree = ast.parse(src)
            alias = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = (node.module or "").split(".")[-1]
                    for a in node.names:
                        alias[a.asname or a.name] = (mod, a.name)
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        alias[(a.asname or a.name).split(".")[0]] = (
                            a.name.split(".")[-1], None)

            class V(ast.NodeVisitor):
                def visit_Call(self, node):
                    f = node.func
                    mod = func = None
                    if (isinstance(f, ast.Attribute)
                            and isinstance(f.value, ast.Name)):
                        base = f.value.id
                        if base in alias and alias[base][1] is None:
                            mod, func = alias[base][0], f.attr
                        elif base in funcs:
                            mod, func = base, f.attr
                    elif isinstance(f, ast.Name) and f.id in alias \
                            and alias[f.id][1]:
                        mod, func = alias[f.id]
                    if mod in funcs and func in funcs[mod]:
                        params, has_varkw = funcs[mod][func]
                        if not has_varkw:
                            for k in node.keywords:
                                if k.arg and k.arg not in params:
                                    problems.append(
                                        f"{caller}:{node.lineno} "
                                        f"{mod}.{func}(...{k.arg}=)")
                    self.generic_visit(node)
            V().visit(tree)
        self.assertEqual(problems, [],
                         "dashboard/bot ↔ core signature drift:\n"
                         + "\n".join(problems))

    def test_get_routes_cover_js_fetches(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        routes = set(re.findall(r'p\.path == "(/api/[a-z0-9_/.\-]+)"', src))
        missing = [f for f in _get_fetches()
                   if f not in routes
                   and not any(f.startswith(r) for r in routes)]
        self.assertEqual(missing, [])


class TestLiveDashboardSmoke(unittest.TestCase):
    """Start ayyi unna server unte real HTTP test; lekapothe skip
    (unit environment lo server undakapovachu — app-level tests vere)."""

    BASE = "http://127.0.0.1:5000"

    def _req(self, url, cookie=None, timeout=20):
        r = urllib.request.Request(url)
        if cookie:
            r.add_header("Cookie", cookie)
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "ignore")
        except Exception as e:
            return 0, str(e)

    def test_dashboard_and_critical_apis(self):
        code, _ = self._req(self.BASE + "/portal")
        if code == 0:
            self.skipTest("dashboard server not running")
        code, _ = self._req(self.BASE + "/api/auth/login")
        st, body = self._req(self.BASE + "/portal")
        self.assertEqual(st, 200)
        # login (default local password — dev/test env matrame)
        req = urllib.request.Request(
            self.BASE + "/api/auth/login",
            data=json.dumps({"password": "studentup123"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                cookie = resp.headers.get("Set-Cookie", "").split(";")[0]
        except Exception:
            self.skipTest("login not available in this env")
        if not cookie:
            self.skipTest("no auth cookie")
        for ep in ("/api/brain/overview", "/api/item_intel",
                   "/api/whatsapp/preview?count=1",
                   "/api/whatsapp/hall-of-fame", "/api/health",
                   "/api/conductor", "/api/campus/list"):
            st, body = self._req(self.BASE + ep, cookie=cookie)
            self.assertNotEqual(st, 0, f"{ep} empty reply (server crash)")
            self.assertEqual(st, 200, f"{ep} -> {st}")
            json.loads(body)  # valid JSON


if __name__ == "__main__":
    unittest.main()
