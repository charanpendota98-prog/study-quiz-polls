# -*- coding: utf-8 -*-
"""Dashboard neatness contract: grouped sidebar nav, Home-first default,
tab search — and every nav button still wired to a real pane (no orphans)."""
import re
import unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1]
       / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")

EXPECTED_TABS = {
    "tab-setup-wizard", "tab-bulk-broadcast", "tab-wa-dispatch", "tab-bundles",
    "tab-member-queue", "tab-excel-import", "tab-campus", "tab-dynamic-channels",
    "tab-control", "tab-squads", "tab-members", "tab-growth", "tab-proops",
    "tab-conductor", "tab-history",
}


def _nav_segment():
    i = SRC.index('<div class="tabs">')
    j = SRC.index("\n  </div>", i)
    return SRC[i:j]


class TestDashboardUI(unittest.TestCase):
    def test_nav_buttons_match_panes(self):
        nav = _nav_segment()
        nav_ids = set(re.findall(r"""onclick="switchTab\('(tab-[^']+)'\)\"""", nav))
        pane_ids = set(re.findall(r'id="(tab-[a-z-]+)" class="tab-pane', SRC))
        self.assertEqual(nav_ids, pane_ids)
        self.assertEqual(nav_ids, EXPECTED_TABS)

    def test_home_is_default(self):
        self.assertEqual(SRC.count('class="tab-pane active"'), 1)
        self.assertIn('<div id="tab-setup-wizard" class="tab-pane active">', SRC)
        nav = _nav_segment()
        active = re.findall(r'class="tab-btn active" onclick="switchTab\(\'(tab-[^\']+)\'\)"', nav)
        self.assertEqual(active, ["tab-setup-wizard"])

    def test_grouped_sidebar_and_search(self):
        nav = _nav_segment()
        for group in ("Main", "Dispatch", "Exams", "People", "Insights", "System"):
            self.assertIn(f'<div class="nav-group">{group}</div>', nav)
        self.assertIn('id="nav-search"', nav)
        self.assertIn("function filterNav", SRC)
        self.assertIn(".tabs { position: fixed;", SRC)       # sidebar, not a clutter row
        self.assertIn("padding-left: 260px", SRC)
        self.assertIn("@media (max-width: 920px)", SRC)      # mobile fallback exists

    def test_home_quick_actions(self):
        i = SRC.index('id="tab-setup-wizard"')
        seg = SRC[i:i + 4000]
        self.assertIn("New College Exam", seg)
        self.assertIn("switchTab('tab-campus')", seg)
        self.assertIn('<details class="adv">', seg)          # advanced stuff tucked away


if __name__ == "__main__":
    unittest.main()
