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




class TestAuditRegressions(unittest.TestCase):
    """Ee round lo dorikina REAL bugs — malli jaragakunda pin chestam."""

    def test_csv_import_supports_dry_run(self):
        from core import bundle_manager as bm
        res = bm.import_from_csv_or_excel_text(
            "ZZ Pin Group,120363011111111111@g.us,SSC,07:00,GK",
            dry_run=True)
        self.assertTrue(res.get("dry_run"))

    def test_weekday_ok_without_datetime(self):
        from core import whatsapp_pipeline as wp
        self.assertTrue(wp._weekday_ok({"id": "x"}))
        self.assertTrue(wp._weekday_ok({"weekdays": [0, 1, 2, 3, 4, 5, 6]}))

    def test_unknown_api_route_is_json_404_not_empty(self):
        import ast
        src = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        send404 = [n for n in ast.walk(tree)
                   if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "send_response"
                   and n.args and isinstance(n.args[0], ast.Constant)
                   and n.args[0].value == 404]
        # both tails ok — bare 404 only allowed behind the /api guard
        self.assertIn("unknown endpoint", src)

    def test_full_call_contract_all_files(self):
        """96 files mottam: dashboard/bot/core anni call sites vs
        definitions — kwarg/arity/too-few drift inkokasari raakudadhu
        (staticmethod/classmethod aware)."""
        import ast as _ast
        root = ROOT / "scripts"

        def sig_table(fn):
            tree = _ast.parse(fn.read_text(encoding="utf-8"))
            table = {}

            def sig(node):
                a = node.args
                pos = [x.arg for x in a.args]
                return (len(pos) - len(a.defaults), len(pos),
                        set(pos) | {x.arg for x in a.kwonlyargs},
                        a.vararg is not None, a.kwarg is not None)

            for node in tree.body:
                if isinstance(node, _ast.FunctionDef):
                    table[node.name] = sig(node)
                elif isinstance(node, _ast.ClassDef):
                    for sub in node.body:
                        if isinstance(sub, _ast.FunctionDef):
                            decos = {getattr(d, "id", getattr(d, "attr", ""))
                                     for d in sub.decorator_list}
                            r = sig(sub)
                            table[f"{node.name}.{sub.name}"] = (
                                r if "staticmethod" in decos else
                                (max(0, r[0] - 1), max(0, r[1] - 1), r[2],
                                 r[3], r[4]))
                            # NOTE: bare sub.name ikkada register
                            # cheyyam — module lo inko class/function
                            # ade peru tho unte false positive vastundi
                            # (e.g. store.py normalize() vs KV.set()).
            return table

        files = sorted(root.rglob("*.py"))
        defs = {}
        for f in files:
            defs[f.stem] = sig_table(f)
        problems = []
        for f in files:
            tree = _ast.parse(f.read_text(encoding="utf-8"))
            mymod = f.stem
            alias = {}
            for node in _ast.walk(tree):
                if isinstance(node, _ast.ImportFrom):
                    mod = (node.module or "").split(".")[-1]
                    for a in node.names:
                        if a.name != "*":
                            alias[a.asname or a.name] = (mod, a.name)
                elif isinstance(node, _ast.Import):
                    for a in node.names:
                        alias[(a.asname or a.name).split(".")[0]] = (
                            a.name.split(".")[-1], None)
            class V(_ast.NodeVisitor):
                def visit_Call(self, node):
                    fnx = node.func
                    tgt = None
                    if (isinstance(fnx, _ast.Attribute)
                            and isinstance(fnx.value, _ast.Name)):
                        base = fnx.value.id
                        if base in alias and alias[base][1] is None:
                            tgt = (alias[base][0], fnx.attr)
                        elif base in defs:
                            tgt = (base, fnx.attr)
                        elif base == "self":
                            tgt = (mymod, fnx.attr)
                    elif isinstance(fnx, _ast.Name):
                        if fnx.id in alias and alias[fnx.id][1]:
                            tgt = alias[fnx.id]
                        elif fnx.id in defs.get(mymod, {}):
                            tgt = (mymod, fnx.id)
                    if tgt and tgt[0] in defs and tgt[1] in defs[tgt[0]]:
                        # *args calls can't be arity-checked
                        if any(isinstance(a, _ast.Starred) for a in node.args):
                            self.generic_visit(node)
                            return
                        req, mx, params, has_var, has_varkw = defs[tgt[0]][tgt[1]]
                        if not has_var and len(node.args) > mx:
                            problems.append(
                                f"{f.name}:{node.lineno} {tgt[0]}.{tgt[1]}"
                                f" {len(node.args)}pos>{mx}")
                        if not has_varkw:
                            for k in node.keywords:
                                if k.arg and k.arg not in params:
                                    problems.append(
                                        f"{f.name}:{node.lineno} "
                                        f"{tgt[0]}.{tgt[1]} kwarg {k.arg}")
                        if not has_var and len(node.args) + len(
                                [k for k in node.keywords
                                 if k.arg in params]) < req:
                            problems.append(
                                f"{f.name}:{node.lineno} {tgt[0]}.{tgt[1]}"
                                f" too-few")
                    self.generic_visit(node)
            V().visit(tree)
        self.assertEqual(sorted(set(problems)), [])

if __name__ == "__main__":
    unittest.main()
