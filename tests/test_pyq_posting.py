#!/usr/bin/env python3
"""PYQ posting tests — previous-exam questions posted perfectly.

Every quiz round must carry a guaranteed share of previous-exam (PYQ)
questions when the unused pool allows (blueprint min_pyq_share), both
platforms must label PYQ provenance (📜 Exam Year · Paper), and the
harvest backlog must drain on schedule (2 runs/day).
Run: python3 -m unittest discover -s tests -p "test_pyq_posting.py"
"""
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import blueprint, config  # noqa: E402


def _q(i, source, topic="Polity", ans=0):
    return {"id": f"q{i}", "channel": "SSC", "topic": topic,
            "q_en": f"Question number {i} about Indian polity and governance?",
            "options_en": ["A1", "B2", "C3", "D4"], "answer_index": ans % 4,
            "source": source}


class TestRoundPyqShare(unittest.TestCase):
    def test_pyq_floor_met_when_pool_allows(self):
        pool = ([_q(i, "pyq", f"T{i % 6}", i) for i in range(8)]
                + [_q(100 + i, "offline-gen", f"G{i % 6}", i) for i in range(22)])
        chosen = blueprint.compose_round("SSC", pool, 10, rng=random.Random(7))
        pyq = [q for q in chosen if q["source"] == "pyq"]
        self.assertEqual(len(chosen), 10)
        self.assertGreaterEqual(len(pyq), 4)   # min_pyq_share 0.4 of 10

    def test_pyq_floor_never_blocks_round(self):
        pool = ([_q(i, "pyq", f"T{i}", i) for i in range(2)]
                + [_q(100 + i, "offline-gen", f"G{i}", i) for i in range(20)])
        chosen = blueprint.compose_round("SSC", pool, 10, rng=random.Random(3))
        self.assertEqual(len(chosen), 10)                    # round still full
        self.assertEqual(sum(1 for q in chosen if q["source"] == "pyq"), 2)

    def test_blueprints_declare_share(self):
        bp = blueprint.blueprint()
        self.assertGreaterEqual(bp.get("min_pyq_share_default", 0), 0.3)
        for ch, cfg in bp["channels"].items():
            self.assertGreaterEqual(cfg.get("min_pyq_share", 0), 0.3, ch)


class TestHarvestSchedule(unittest.TestCase):
    def test_two_pyq_runs_daily(self):
        pyq_slots = [t for t, v in config.SCHEDULE.items() if v[0] == "pyq"]
        self.assertEqual(sorted(pyq_slots), ["02:15", "13:45"])

    def test_harvest_batch(self):
        src = (ROOT / "scripts" / "core" / "engine.py").read_text()
        self.assertIn("limit=12", src)

    def test_stats_show_pyq(self):
        from core import source_manager
        st = source_manager.stats()
        self.assertIn("pyq_questions", st)
        self.assertIn("pyq_papers_harvested", st)
        self.assertGreaterEqual(st["pyq_questions"], 100)


class TestPyqLabelsBothPlatforms(unittest.TestCase):
    Q = {"q_en": "Capital of India?", "q_te": "భారత రాజధాని?",
         "options_en": ["Delhi", "Mumbai"], "options_te": ["ఢిల్లీ", "ముంబై"],
         "answer_index": 0, "source": "pyq", "exam": "TSPSC Group-2",
         "year": 2024, "paper": "Paper-1", "topic": "Polity"}

    def test_telegram_text_has_provenance(self):
        from core.content import build_question_text
        cfg = {"emoji": "🎯", "subject": "TSPSC"}
        txt = build_question_text(self.Q, cfg)
        self.assertIn("TSPSC Group-2", txt)
        self.assertIn("2024", txt)

    def test_whatsapp_poll_has_provenance(self):
        from core import whatsapp_pipeline as wap
        p = wap.build_native_poll_payload(self.Q, "TSPSC")
        self.assertIn("TSPSC Group-2", p["name"])
        self.assertIn("2024", p["name"])
        t = wap.build_question_only_post(self.Q, "G", "TSPSC")
        self.assertIn("Group-2", t)


if __name__ == "__main__":
    unittest.main()
