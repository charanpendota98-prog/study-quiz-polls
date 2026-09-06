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
from core.members import Members, level_for, STREAK_BONUS
from core.store import load_json


class TestMembers(unittest.TestCase):
    def setUp(self):
        # isolate: use a throwaway members store (never touch real data)
        import tempfile
        from pathlib import Path as _P
        self.tmp = _P(tempfile.gettempdir()) / "test_members.json"
        if self.tmp.exists():
            self.tmp.unlink()
        self.mb = Members()
        self.mb.kv.path = self.tmp
        self.mb.data = {"members": {}, "pending": {}}
        self.mb.members = self.mb.data["members"]
        self.mb.pending = self.mb.data["pending"]
        self.uid = 999001

    def tearDown(self):
        if self.tmp.exists():
            self.tmp.unlink()

    def test_registration_flow(self):
        self.mb.start_registration(self.uid, username="tester")
        s, _ = self.mb.registration_input(self.uid, "Test User")
        self.assertEqual(s, "ask_exam")
        s, _ = self.mb.registration_input(self.uid, "1")  # TSPSC
        self.assertEqual(s, "ask_lang")
        s, _ = self.mb.registration_input(self.uid, "2")  # Telugu
        self.assertEqual(s, "done")
        p = self.mb.profile(self.uid)
        self.assertTrue(p["registered"])
        self.assertEqual(p["exam"], "TSPSC")
        self.assertEqual(p["lang"], "Telugu")
        self.assertEqual(p["points"], 25)  # registration bonus

    def test_points_correct_answer(self):
        self.mb.register(self.uid, name="T")
        before = self.mb.profile(self.uid)["points"]
        res = self.mb.award_answer(self.uid, correct=True)
        after = self.mb.profile(self.uid)["points"]
        self.assertGreater(after, before)
        self.assertTrue(any("correct" in e for e in res["events"]))  # +10 correct
        self.assertEqual(after - before, res["earned"])

    def test_levels(self):
        self.assertEqual(level_for(0)["title_en"], "Newcomer")
        self.assertEqual(level_for(150)["title_en"], "Bronze")
        self.assertEqual(level_for(400)["title_en"], "Silver")
        self.assertEqual(level_for(800)["title_en"], "Gold")
        self.assertEqual(level_for(1600)["title_en"], "Platinum")
        self.assertEqual(level_for(5000)["title_en"], "Champion")

    def test_ranking(self):
        self.mb.register(1, name="A")
        self.mb.register(2, name="B")
        for _ in range(3):
            self.mb.award_answer(1, correct=True)
        for _ in range(6):
            self.mb.award_answer(2, correct=True)
        self.assertEqual(self.mb.rank(2), 1)
        self.assertEqual(self.mb.rank(1), 2)

    def test_streak_bonus_present(self):
        self.assertIn(7, STREAK_BONUS)
        self.assertEqual(STREAK_BONUS[7], 75)


class TestPYQBank(unittest.TestCase):
    def test_pyq_loads_and_valid(self):
        data = load_json(config.BANK_PYQ_JSON, {"questions": []})
        pyq = data.get("questions", [])
        self.assertGreaterEqual(len(pyq), 20)
        for q in pyq:
            self.assertEqual(validate_question(q), [],
                             f"{q['id']} invalid: {validate_question(q)}")
            self.assertEqual(q.get("source"), "pyq")

    def test_round_includes_pyq(self):
        b = Bank()
        qs = b.pick("TSPSC", 10)
        sources = {q.get("source") for q in qs}
        self.assertIn("pyq", sources)


class TestSchedule(unittest.TestCase):
    def test_two_daily_rounds(self):
        quiz_times = [t for t, (task, _) in config.SCHEDULE.items() if task == "quiz"]
        self.assertEqual(len(quiz_times), 2)
        self.assertIn("07:30", quiz_times)
        self.assertIn("19:30", quiz_times)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
