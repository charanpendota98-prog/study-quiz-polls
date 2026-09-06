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

    def test_form_import_and_autolink(self):
        # numeric id -> immediately linked
        status, _ = self.mb.import_form_signup({
            "name": "Numeric", "tg_id": "424242", "exam": "TSPSC", "district": "Hyderabad"})
        self.assertEqual(status, "linked")
        p = self.mb.profile("424242")
        self.assertEqual(p["district"], "Hyderabad")
        self.assertEqual(p["points"], 25)  # registration bonus
        # username only -> held pending
        status, _ = self.mb.import_form_signup({
            "name": "Handle", "username": "@wait_user", "exam": "Banking"})
        self.assertEqual(status, "pending")
        self.assertGreaterEqual(self.mb.count_form(), 2)
        # when that user /starts the bot, they auto-link and keep data
        linked = self.mb.link_if_pending(777, "wait_user", name="Handle")
        self.assertTrue(linked)
        p2 = self.mb.profile(777)
        self.assertEqual(p2["exam"], "Banking")


class TestAdaptiveLearning(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path as _P
        self.tmp = _P(tempfile.gettempdir()) / "test_adaptive.json"
        if self.tmp.exists():
            self.tmp.unlink()
        self.mb = Members()
        self.mb.kv.path = self.tmp
        self.mb.data = {"members": {}, "pending": {}, "form_pending": {}}
        self.mb.members = self.mb.data["members"]
        self.mb.pending = self.mb.data["pending"]
        self.mb.form_pending = self.mb.data["form_pending"]
        self.uid = 7007

    def tearDown(self):
        if self.tmp.exists():
            self.tmp.unlink()

    def test_weak_topics(self):
        self.mb.register(self.uid, name="W")
        for _ in range(3):
            self.mb.award_answer(self.uid, correct=False, topic="percentage", qid="x1")
        self.mb.award_answer(self.uid, correct=True, topic="percentage", qid="x2")  # 25%
        for _ in range(4):
            self.mb.award_answer(self.uid, correct=True, topic="ratio", qid="r1")  # 100%
        weak = self.mb.weak_topics(self.uid)
        self.assertIn("percentage", weak)
        self.assertNotIn("ratio", weak)

    def test_spaced_repetition_queues_missed(self):
        self.mb.register(self.uid, name="S")
        self.mb.award_answer(self.uid, correct=False, topic="coding", qid="MISS1")
        due = self.mb.due_reviews(self.uid)
        self.assertTrue(any(r["qid"] == "MISS1" for r in due))

    def test_badges_unlock(self):
        self.mb.register(self.uid, name="B")
        for _ in range(10):
            r = self.mb.award_answer(self.uid, correct=True, topic="series")
        ids = set(self.mb.members[str(self.uid)]["badges"])
        self.assertIn("first", ids)
        self.assertIn("correct10", ids)

    def test_analytics_structure(self):
        self.mb.register(1, name="A", exam="TSPSC", state="Telangana", district="Hyderabad")
        a = self.mb.analytics()
        self.assertGreaterEqual(a["registered"], 1)
        self.assertIn("by_exam", a)
        self.assertEqual(a["by_exam"]["TSPSC"], 1)


class TestWebhookNormalize(unittest.TestCase):
    def test_form_payload_normalizes(self):
        from core.formingest import normalize_signup
        info = normalize_signup({
            "Full name": "Kiran", "WhatsApp / Mobile number": "98765-43210",
            "Telegram username": "@kirant", "State": "Andhra Pradesh",
            "District": "AP · Guntur",
            "Which exam are you preparing for?": "Police — Constable / SI (TS & AP)",
            "Medium of preparation": "Telugu", "email": "k@x.com"})
        self.assertEqual(info["phone"], "9876543210")
        self.assertEqual(info["district"], "Guntur")
        self.assertEqual(info["state"], "Andhra Pradesh")
        self.assertEqual(info["exam"], "Police")
        self.assertEqual(info["lang"], "Telugu")
        self.assertEqual(info["username"], "kirant")
        self.assertEqual(info["email"], "k@x.com")


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


class TestNoRepeatAndSources(unittest.TestCase):
    """Phase-5 guarantees: questions NEVER repeat and quizzes never draw
    from news/article sources (exam-paper sources only)."""

    def setUp(self):
        # Start each test with a fresh rotation state so picks here do not
        # consume questions for other test classes (the store is permanent by
        # design — tests reset it explicitly).
        for f in ("question_bank.json", "question_bank_extra.json",
                  "shown_signatures.json", "used_questions.json",
                  "scraped_bank.json", "scraped_pending.json"):
            p = config.DATA / f
            if p.exists():
                p.unlink()

    def tearDown(self):
        self.setUp()

    def test_quiz_sources_are_exam_only(self):
        from core.question_bank import ALLOWED_QUIZ_SOURCES
        b = Bank()
        for q in b.questions:
            self.assertIn(q.get("source", ""), ALLOWED_QUIZ_SOURCES,
                          f"non-exam source leaked into quiz bank: {q.get('source')}")

    def test_questions_never_repeat(self):
        b = Bank()
        seen = set()
        for _ in range(4):
            for ch in ("DEFENCE", "APPSC", "RAILWAY", "POLICE"):
                for q in b.pick(ch, 10):
                    from core.question_bank import q_signature
                    sig = q_signature(q)
                    self.assertNotIn(sig, seen, f"repeat posted: {q['id']}")
                    seen.add(sig)
        # permanent history persisted on disk
        history = load_json(config.STORE_USED, {})
        self.assertTrue(all(len(history.get(ch, [])) >= 40
                            for ch in ("DEFENCE", "APPSC", "RAILWAY", "POLICE")))

    def test_digest_items_are_digest_only(self):
        """News-feed items must never carry a quiz question / answer key."""
        from core import feeds
        # no network: call the filter with a fake item containing blocked junk
        junk = {"en": "Blog: five lifestyle habits of a celebrity horoscope today",
                "te": "—", "link": "http://x"}
        self.assertTrue(feeds.is_weak_content(junk["en"]))
        self.assertFalse(feeds.is_weak_content(
            "Cabinet approves new national education policy implementation"))

    def test_coach_lessons_bilingual(self):
        lessons = load_json(config.DATA / "coach_lessons.json",
                            {"lessons": []}).get("lessons", [])
        self.assertGreaterEqual(len(lessons), 12)
        for l in lessons:
            self.assertTrue(l.get("en") and l.get("te"), l.get("id"))
            self.assertFalse(l["te"].lstrip().startswith("⤷ ⤷"))


class TestCollector(unittest.TestCase):
    """Advanced multi-source exam-content collector (website/app scraping)."""

    FIXTURE = ROOT / "tests" / "fixture_quiz.html"
    FIXTURE_INDIA = ROOT / "tests" / "fixture_indiabix.html"
    FIXTURE_INDEX = ROOT / "tests" / "fixture_index.html"
    FIXTURE_EXAMVEDA = ROOT / "tests" / "fixture_examveda.html"

    def setUp(self):
        for f in ("question_bank.json", "question_bank_extra.json",
                  "shown_signatures.json", "used_questions.json",
                  "scraped_bank.json", "scraped_pending.json",
                  "collector_seen.json"):
            p = config.DATA / f
            if p.exists():
                p.unlink()

    def tearDown(self):
        self.setUp()

    def test_fixture_parses_quiz_blocks(self):
        from core import collector
        html = self.FIXTURE.read_text(encoding="utf-8")
        lines = collector.html_to_lines(html)
        raws = collector.parse_quiz_lines(lines, article_title="IBPS Quiz", url="x")
        self.assertGreaterEqual(len(raws), 4)
        for r in raws:
            self.assertEqual(len(r["options_en"]), 4)
            self.assertIn(r["answer_index"], (0, 1, 2, 3))
            self.assertTrue(r["q_en"])
        # the inline-options question (Q2) was split correctly
        inline = [r for r in raws if r["q_en"].lower().startswith("the simple interest")]
        self.assertTrue(inline and inline[0]["options_en"] == ["750", "800", "850", "900"])

    def test_aptitude_telugu_offline(self):
        from core import collector
        te = collector.aptitude_telugu("What is 15% of 240?")
        self.assertIn("⤷", te)
        self.assertTrue(content.has_telugu(te))
        self.assertTrue(collector.aptitude_telugu(
            "The simple interest on Rs.5000 at 8% for 2 years"))

    def test_channel_topic_inference(self):
        from core import collector
        self.assertEqual(collector.infer_channel("RRB NTPC quiz", ""), "RAILWAY")
        self.assertEqual(collector.infer_channel("IBPS Clerk quant", ""), "BANKING")
        self.assertEqual(collector.infer_channel("NDA GK", ""), "DEFENCE")
        self.assertEqual(collector.infer_topic("", "find the simple interest"),
                         "simple interest")

    def test_collect_accepts_and_dedupes(self):
        from core import collector
        html = self.FIXTURE.read_text(encoding="utf-8")
        s1 = collector.collect_daily(
            fixture=(html, "IBPS Clerk Quant Practice Quiz", "http://x/q1"))
        self.assertGreaterEqual(s1["accepted"], 3)
        self.assertEqual(s1["duplicates"], 0)
        # re-scraping the same page must add nothing new
        s2 = collector.collect_daily(
            fixture=(html, "IBPS Clerk Quant Practice Quiz", "http://x/q1"))
        self.assertEqual(s2["accepted"], 0)
        self.assertGreaterEqual(s2["duplicates"], s1["accepted"])

    def test_scraped_questions_are_exam_source(self):
        from core import collector
        from core.question_bank import ALLOWED_QUIZ_SOURCES, rebuild_json
        self.assertIn("scraped", ALLOWED_QUIZ_SOURCES)
        html = self.FIXTURE.read_text(encoding="utf-8")
        collector.collect_daily(
            fixture=(html, "IBPS Clerk Quant Practice Quiz", "http://x/q1"))
        qs, errs = rebuild_json()
        scraped = [q for q in qs if q.get("source") == "scraped"]
        self.assertTrue(scraped)
        for q in scraped:
            self.assertEqual(validate_question(q), [], q["id"])
        # every scraped question carries provenance and merges into the Bank
        self.assertTrue(all(q.get("provenance") for q in scraped))
        b = Bank()
        self.assertTrue(any(q.get("source") == "scraped" for q in b.questions))

    def test_sources_are_quiz_only_filters(self):
        """RSS title filter must pick quiz pages, skip notifications."""
        from core import collector
        src = collector.DEFAULT_SOURCES[0]
        import re
        must = re.compile(src["title_must"], re.I)
        notp = re.compile(src["title_not"], re.I)
        self.assertTrue(must.search("IBPS Clerk Quantitative Aptitude Quiz 2026"))
        self.assertTrue(notp.search("IBPS Clerk Notification 2026 Apply Online"))
        self.assertFalse(notp.search("Reasoning Ability Practice Questions Set"))

    def test_large_deep_source_registry(self):
        """Many sources, central exams covered, all well-formed + enabled."""
        from core import collector
        srcs = collector.DEFAULT_SOURCES
        self.assertGreaterEqual(len(srcs), 20)
        names = {s["name"] for s in srcs}
        self.assertIn("IndiaBIX General Knowledge", names)
        self.assertIn("Examveda General Knowledge", names)
        self.assertTrue(any(s.get("type") == "index" for s in srcs))
        adapters = {s.get("adapter") for s in srcs if s.get("adapter")}
        self.assertIn("examveda", adapters)
        self.assertIn("indiabix", adapters)
        for s in srcs:
            self.assertIn(s["type"], ("rss", "index"))
            self.assertTrue(s["name"])
            self.assertTrue(s.get("feed") or s.get("url"))
            # every deep index source must name a real adapter
            if s["type"] == "index":
                self.assertIn(s.get("adapter"), collector.ADAPTERS)

    def test_indiabix_adapter(self):
        """Dedicated IndiaBIX adapter parses its table markup correctly."""
        from core import collector
        ib = self.FIXTURE_INDIA.read_text(encoding="utf-8")
        raws = collector.parse_indiabix(ib, "IndiaBIX Aptitude",
                                        "https://www.indiabix.com/aptitude/problems-on-trains/")
        self.assertGreaterEqual(len(raws), 3)
        for r in raws:
            self.assertEqual(len(r["options_en"]), 4)
            self.assertIn(r["answer_index"], (0, 1, 2, 3))
            self.assertFalse(r["q_en"][0].isdigit() and ")" in r["q_en"][:4])
        # known answers from the fixture: trains=B(1), notes=D(3), SI=B(1)
        self.assertEqual(raws[0]["answer_index"], 1)
        self.assertEqual(raws[1]["answer_index"], 3)
        self.assertEqual(raws[2]["answer_index"], 1)

    def test_examveda_adapter_unnumbered(self):
        """Unnumbered MCQ bank (Examveda) is recovered via answer anchors."""
        from core import collector
        ev = self.FIXTURE_EXAMVEDA.read_text(encoding="utf-8")
        raws = collector.parse_examveda(ev, "Examveda Trains",
                                        "https://www.examveda.com/problems-on-trains/")
        self.assertGreaterEqual(len(raws), 3)
        for r in raws:
            self.assertEqual(len(r["options_en"]), 4)
            self.assertIn(r["answer_index"], (0, 1, 2, 3))
            self.assertIn("train", r["q_en"].lower())
        # fixture answers: B(1), B(1), D(3)
        self.assertEqual([r["answer_index"] for r in raws[:3]], [1, 1, 3])
        # options match the fixture exactly
        self.assertIn("50 km/hr", raws[0]["options_en"])
        # adapter is wired into dispatch with generic fallback
        via_dispatch = collector.parse_page(
            {"name": "Examveda", "adapter": "examveda"}, ev,
            "Examveda", "https://www.examveda.com/problems-on-trains/")
        self.assertEqual(len(via_dispatch), len(raws))

    def test_index_link_extraction(self):
        """Deep index pages yield topic quiz links, not forum/sidebar junk."""
        from core import collector
        idx = self.FIXTURE_INDEX.read_text(encoding="utf-8")
        links = collector.extract_links(
            idx, "https://www.indiabix.com/aptitude/questions-and-answers/",
            r"^https://www\.indiabix\.com/aptitude/[a-z0-9\-]+/?$")
        hrefs = [l["link"] for l in links]
        self.assertTrue(any("problems-on-trains" in h for h in hrefs))
        self.assertFalse(any("/forum/" in h for h in hrefs))
        self.assertFalse(any("questions-and-answers" in h for h in hrefs))

    def test_seen_url_store_pages_forward(self):
        """Re-collection does not refetch URLs already collected."""
        from core import collector
        u = "https://www.indiabix.com/aptitude/simple-interest/"
        self.assertNotIn(u, collector.load_seen_urls())
        collector.save_seen_urls({u})
        try:
            self.assertIn(u, collector.load_seen_urls())
        finally:
            seen = collector.load_seen_urls()
            seen.discard(u)
            collector.save_seen_urls(seen)


class TestSchedule(unittest.TestCase):
    def test_two_daily_rounds(self):
        quiz_times = [t for t, (task, _) in config.SCHEDULE.items() if task == "quiz"]
        self.assertEqual(len(quiz_times), 2)
        self.assertIn("07:30", quiz_times)
        self.assertIn("19:30", quiz_times)


class TestFormDistricts(unittest.TestCase):
    """The Google-Form builder must include all TS + AP districts."""
    @classmethod
    def setUpClass(cls):
        import re as _re
        root = Path(__file__).resolve().parents[1]
        src = (root / "forms" / "build_studentup_form.gs").read_text(encoding="utf-8")
        def grab(var):
            m = _re.search(r"var %s = \[(.*?)\];" % var, src, _re.S)
            return _re.findall(r'"([^"]+)"', m.group(1))
        cls.ts = [d for d in grab("TS_DISTRICTS") if "Other" not in d]
        cls.ap = [d for d in grab("AP_DISTRICTS") if "Other" not in d]

    def test_ts_has_33_districts(self):
        self.assertGreaterEqual(len(self.ts), 33)
        self.assertTrue(any("Hyderabad" in d for d in self.ts))
        self.assertTrue(any("Mancherial" in d for d in self.ts))

    def test_ap_has_26_districts(self):
        self.assertGreaterEqual(len(self.ap), 26)
        self.assertTrue(any("Visakhapatnam" in d for d in self.ap))
        self.assertTrue(any("Kurnool" in d for d in self.ap))

    def test_no_duplicate_districts(self):
        self.assertEqual(len(self.ts), len(set(self.ts)))
        self.assertEqual(len(self.ap), len(set(self.ap)))


class TestFormImportNormalize(unittest.TestCase):
    def test_district_and_exam_normalization(self):
        from core.formingest import norm_district, norm_exam, norm_phone
        d, state = norm_district("TS · Warangal")
        self.assertEqual(d, "Warangal")
        self.assertEqual(state, "Telangana")
        self.assertEqual(norm_exam("Banking — IBPS / SBI / RRB Clerk-PO"), "Banking")
        self.assertEqual(norm_phone("98765-43210"), "9876543210")


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
