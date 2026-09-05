#!/usr/bin/env python3
"""
STUDENTUP — TEST SUITE (stdlib unittest, no dependencies)
Verifies: bank validity, generator answer CORRECTNESS, content filters,
Telugu policy, dedup, option formatting, and slot scheduling.
Run:  python3 -m unittest -v tests.test_bot   (from scripts/ parent:  cd scripts && python3 -m pytest ../tests  OR  python3 tests/test_bot.py)
"""
import sys
import random
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import config
from core import content
from core.generator import (generate_offline, g_percentage, g_simple_interest,
                            g_ratio, g_squares, g_cubes, g_geometric,
                            g_linear_2n1, g_symbol_math, g_ranking,
                            _options)
from core.question_bank import Bank, rebuild_json, parse_markdown
from core.store import similarity, normalize, SeenStore
from core.content import build_options, build_question_text, validate_question
from core.engine import Engine


class TestBank(unittest.TestCase):
    def test_rebuild_valid(self):
        qs, errs = rebuild_json()
        self.assertEqual(len(errs), 0, f"validation errors: {errs[:5]}")
        self.assertGreaterEqual(len(qs), 60)

    def test_every_question_valid(self):
        qs, _ = rebuild_json()
        bad = []
        for q in qs:
            errs = validate_question(q)
            if errs:
                bad.append((q["id"], errs))
        self.assertEqual(bad, [], f"invalid questions: {bad[:3]}")

    def test_channels_stocked(self):
        b = Bank()
        for ch in config.PUBLIC_CHANNELS:
            self.assertGreaterEqual(len(b.by_channel(ch)), config.POLLS_PER_SLOT,
                                    f"{ch} under-stocked")

    def test_pick_is_diverse_and_balanced(self):
        b = Bank()
        for ch in ("BANKING", "RAILWAY"):
            qs = b.pick(ch, 10)
            self.assertEqual(len(qs), 10)
            keys = [q["answer_index"] for q in qs]
            # answer key not all the same
            self.assertGreater(len(set(keys)), 1)
            # no duplicate question ids in a slot
            ids = [q["id"] for q in qs]
            self.assertEqual(len(ids), len(set(ids)))


class TestGeneratorCorrectness(unittest.TestCase):
    """Independently recompute each answer and verify it matches answer_index."""

    def _correct_value(self, q):
        return q["options_en"][q["answer_index"]]

    def test_percentage(self):
        rng = random.Random(1)
        for _ in range(50):
            q = g_percentage(rng)
            # recompute from question text: "What is P% of B?"
            import re
            p, b = map(int, re.findall(r"\d+", q["q_en"]))
            # text is "What is {p}% of {base}?"
            expected = b * p // 100
            self.assertIn(str(expected), self._correct_value(q),
                          f"percentage wrong: {q['q_en']} -> {q['options_en'][q['answer_index']]}")

    def test_simple_interest(self):
        rng = random.Random(2)
        import re
        for _ in range(50):
            q = g_simple_interest(rng)
            nums = list(map(int, re.findall(r"\d+", q["q_en"])))
            p, r, t = nums[0], nums[1], nums[2]
            expected = p * r * t // 100
            self.assertIn(str(expected), self._correct_value(q),
                          f"SI wrong: {q['q_en']} got {q['options_en'][q['answer_index']]} exp {expected}")

    def test_ratio(self):
        rng = random.Random(3)
        import re
        for _ in range(50):
            q = g_ratio(rng)
            nums = list(map(int, re.findall(r"\d+", q["q_en"])))
            total = nums[0]
            a, b = nums[1], nums[2]
            unit = total // (a + b)
            expected = b * unit
            self.assertIn(str(expected), self._correct_value(q),
                          f"ratio wrong: {q['q_en']} got {q['options_en'][q['answer_index']]} exp {expected}")

    def test_squares_cubes(self):
        rng = random.Random(4)
        for _ in range(30):
            q = g_squares(rng)
            import re
            nums = list(map(int, re.findall(r"\d+", q["q_en"].split("?")[0])))
            # missing term present; verify answer is a perfect square
            ans = int(re.findall(r"\d+", self._correct_value(q))[0])
            self.assertEqual(int(ans ** 0.5) ** 2, ans)
        rng = random.Random(5)
        for _ in range(30):
            q = g_cubes(rng)
            import re
            ans = int(re.findall(r"\d+", self._correct_value(q))[0])
            root = round(ans ** (1/3))
            self.assertIn(ans, [root**3, (root+1)**3, (root-1)**3])

    def test_symbol_math(self):
        rng = random.Random(6)
        import re
        for _ in range(50):
            q = g_symbol_math(rng)
            # expr: a C b B c A d => a*b - c + d
            nums = list(map(int, re.findall(r"\d+", q["q_en"])))
            a, b, c, d = nums
            expected = a * b - c + d
            self.assertIn(str(expected), self._correct_value(q),
                          f"symbol math wrong: {q['q_en']} got {q['options_en'][q['answer_index']]} exp {expected}")

    def test_ranking(self):
        rng = random.Random(7)
        import re
        for _ in range(50):
            q = g_ranking(rng)
            nums = list(map(int, re.findall(r"\d+", q["q_en"])))
            left, right = nums[0], nums[1]
            expected = left + right - 1
            self.assertIn(str(expected), self._correct_value(q),
                          f"ranking wrong: {q['q_en']}")

    def test_generated_all_valid(self):
        qs = generate_offline(120, seed=99)
        self.assertGreaterEqual(len(qs), 100)
        for q in qs:
            self.assertEqual(validate_question(q), [], f"{q['id']} invalid: {validate_question(q)}")
            self.assertEqual(len(q["options_en"]), 4)
            self.assertIn(q["answer_index"], (0, 1, 2, 3))


class TestContentPolicy(unittest.TestCase):
    def test_blocked_topics(self):
        for bad in ["IPL 2026 final cricket score", "New Bollywood movie review",
                    "Weather forecast for Hyderabad rain", "Actor announces new film",
                    "Tech company layoffs job cuts"]:
            blocked, why = content.is_blocked(bad)
            self.assertTrue(blocked, f"should block: {bad}")

    def test_clean_topics_pass(self):
        for good in ["TSPSC Group IV notification released apply online",
                     "RBI keeps repo rate at 6.5 percent",
                     "ISRO Aditya L1 solar mission update",
                     "IBPS clerk recruitment 2026 eligibility"]:
            blocked, _ = content.is_blocked(good)
            self.assertFalse(blocked, f"should not block: {good}")

    def test_other_state_blocked_for_jobs(self):
        self.assertTrue(content.is_other_state("Karnataka police recruitment 2026"))
        self.assertFalse(content.is_other_state("Indian Railways nationwide recruitment"))

    def test_jobs_relevance(self):
        self.assertEqual(content.jobs_relevance("IBPS clerk recruitment apply online bank")[:4], "keep")
        self.assertTrue(content.jobs_relevance("Karnataka film festival").startswith("drop"))

    def test_telugu_detection(self):
        self.assertTrue(content.has_telugu("రెపో రేటు 6.50%"))
        self.assertFalse(content.has_telugu("repo rate 6.50%"))
        self.assertIsNone(content.forbidden_script("రెపో రేటు"))
        self.assertEqual(content.forbidden_script("रेपो रेट"), "Devanagari/Hindi")


class TestDedup(unittest.TestCase):
    def test_similarity_identical(self):
        self.assertGreater(similarity("RBI keeps repo rate at 6.50 percent",
                                      "RBI kept repo rate at 6.50 percent"), 0.5)

    def test_similarity_different(self):
        self.assertLess(similarity("TSPSC Group IV notification",
                                   "ISRO launches solar mission Aditya"), 0.5)

    def test_seen_store(self):
        import tempfile, os
        p = Path(tempfile.gettempdir()) / "test_seen.json"
        if p.exists():
            p.unlink()
        s = SeenStore(p, 1.0)
        self.assertFalse(s.is_dup("IBPS clerk recruitment 2026 apply online"))
        s.add("IBPS clerk recruitment 2026 apply online")
        self.assertTrue(s.is_dup("IBPS clerk recruitment 2026 apply online"))
        self.assertTrue(s.is_dup("IBPS clerk recruitment 2026 apply online now"))
        p.unlink()


class TestPollFormat(unittest.TestCase):
    def test_options_within_limits(self):
        b = Bank()
        for ch in config.PUBLIC_CHANNELS:
            for q in b.by_channel(ch)[:5]:
                opts = build_options(q)
                self.assertEqual(len(opts), 4, f"{q['id']} options")
                for o in opts:
                    self.assertLessEqual(len(o), 100, f"{q['id']} option too long: {o}")
                cfg = config.CHANNELS[ch]
                qt = build_question_text(q, cfg)
                self.assertLessEqual(len(qt), 300, f"{q['id']} question too long")


class TestScheduler(unittest.TestCase):
    def test_schedule_has_all_slots(self):
        for t in ("07:00", "07:30", "10:30", "13:30", "16:30", "19:30",
                  "14:30", "21:30", "06:00"):
            self.assertIn(t, config.SCHEDULE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
