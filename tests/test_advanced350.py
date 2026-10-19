# -*- coding: utf-8 -*-
"""350X — bank resilience: the served bank is generated state.
Canonical restore (rebuild_json + offline top_up) must keep the
bank valid (invalid 0), honestly sourced, and stocked enough for
TS/AP mocks — on a fresh clone (321Q floor) and after restore.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import bankhealth, portal  # noqa: E402
from core.question_bank import load_bank, q_signature  # noqa: E402


def _all_qs():
    bank = load_bank()
    return bank.questions if hasattr(bank, "questions") else list(bank)


class TestBankResilience(unittest.TestCase):
    def test_invalid_zero_and_grade(self):
        rep = bankhealth.bank_health_report(_all_qs())
        self.assertEqual(rep["invalid"], {})
        self.assertIn(rep["grade"], ("A", "B", "C"))

    def test_signatures_unique(self):
        sigs = [q_signature(q) for q in _all_qs()]
        self.assertEqual(len(sigs), len(set(sigs)),
                         "duplicate content signatures in served bank")

    def test_sources_honest(self):
        # Generated stock must never masquerade as PYQ.
        for q in _all_qs():
            if q.get("source") in ("offline-gen", "llm-gen"):
                self.assertNotIn("PYQ", str(q.get("exam") or ""))

    def test_hub_floors_fresh_clone_safe(self):
        hub = portal.state_hub()
        exams = {e["goal"]: e for s in hub["states"] for e in s["exams"]}
        # Floors hold even on the canonical 321Q bank (no restore).
        self.assertGreaterEqual(exams["tspsc"]["total"], 50)
        self.assertGreaterEqual(exams["appsc"]["pyq"], 25)
        self.assertGreaterEqual(exams["police"]["total"], 45)

    def test_restore_tool_exists(self):
        tool = ROOT / "scripts" / "bank_restore.py"
        src = tool.read_text(encoding="utf-8")
        self.assertIn("rebuild_json", src)
        self.assertIn("top_up", src)
        self.assertIn("bank_health_report", src)


if __name__ == "__main__":
    unittest.main()
