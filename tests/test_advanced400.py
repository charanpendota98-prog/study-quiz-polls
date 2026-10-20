"""400X — Go-live deploy perfection pins.

Locks the deploy contract that go-live depends on:
  * every systemd unit's WorkingDirectory/ExecStart resolves the
    SAME repo root, so config.load_env() finds env/.env (the
    400X cwd bug: dashboard/bot looked for <cwd>/scripts/env/.env);
  * webhook unit carries no hardcoded secret;
  * deploy.sh restores the bank (fresh-VM rule) and installs the
    full four-service stack including studentup-dashboard;
  * Caddyfile proxies quiz.studentup.in -> 127.0.0.1:5000 (the
    app is never exposed directly);
  * the go-live runbook names the real order (smoke before DNS)
    and keeps secrets VM-only.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy"


def _unit(name):
    return (DEPLOY / name).read_text(encoding="utf-8")


def _kv(unit, key):
    m = re.search(rf"^{key}=(.*)$", unit, re.M)
    return m.group(1).strip() if m else ""


class DeployUnits(unittest.TestCase):
    UNITS = {
        "studentup.service": "watch.py",
        "studentup-bot.service": "bot.py",
        "studentup-dashboard.service": "dashboard_server.py",
        "studentup-webhook.service": "webhook_server.py",
    }

    def test_execstart_absolute_under_scripts(self):
        for name, script in self.UNITS.items():
            exe = _kv(_unit(name), "ExecStart")
            self.assertIn(f"/home/ubuntu/studentup/scripts/{script}",
                          exe, name)

    def test_workingdir_inside_repo(self):
        # config.ROOT = parents[2] of scripts/core/config.py, and
        # load_env reads ROOT/env/.env — any cwd INSIDE the repo
        # keeps ROOT correct; scripts/ is the convention.
        for name in self.UNITS:
            wd = _kv(_unit(name), "WorkingDirectory")
            self.assertTrue(
                wd == "/home/ubuntu/studentup"
                or wd.startswith("/home/ubuntu/studentup/"), name)

    def test_python_units_cwd_is_scripts(self):
        # Apps self-insert their own dir into sys.path; running
        # from scripts/ keeps sibling relative lookups identical
        # to local dev (`cd scripts && python3 bot.py`).
        for name in self.UNITS:
            self.assertTrue(
                _kv(_unit(name), "WorkingDirectory")
                .endswith("/scripts"), name)

    def test_bridge_node_absolute(self):
        unit = _unit("studentup-bridge.service")
        self.assertIn("/home/ubuntu/studentup/gateway/wa_bridge.js",
                      _kv(unit, "ExecStart"))

    def test_no_hardcoded_secrets_in_units(self):
        for name in list(self.UNITS) + ["studentup-bridge.service"]:
            unit = _unit(name)
            self.assertNotIn("change-me", unit, name)
            self.assertNotRegex(
                unit, r"(?i)(secret|token|password)\s*=\s*\S+", name)


class DeployScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sh = (ROOT / "scripts" / "deploy.sh").read_text(
            encoding="utf-8")

    def test_bank_restore_runs(self):
        self.assertIn("bank_restore.py", self.sh)

    def test_installs_dashboard_unit(self):
        self.assertIn("studentup-dashboard.service", self.sh)
        self.assertIn("studentup-dashboard.service", self.sh.split(
            "enable --now")[-1])

    def test_all_four_units_installed(self):
        for u in ("studentup.service", "studentup-bot.service",
                  "studentup-webhook.service",
                  "studentup-dashboard.service"):
            self.assertIn(u, self.sh)


class ReverseProxyAndRunbook(unittest.TestCase):
    def test_caddyfile(self):
        caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
        self.assertIn("quiz.studentup.in", caddy)
        self.assertIn("reverse_proxy 127.0.0.1:5000", caddy)

    def test_runbook_order_and_hygiene(self):
        doc = (ROOT / "docs" / "GO_LIVE_400X.md").read_text(
            encoding="utf-8")
        smoke = doc.find("BEFORE DNS")
        dns = doc.find("## Step 6 — DNS")
        self.assertTrue(0 < smoke < dns)
        self.assertIn("env/.env", doc)
        self.assertIn("chmod 600", doc)
        self.assertIn("/api/health/golive", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
