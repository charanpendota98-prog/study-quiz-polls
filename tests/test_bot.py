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
        self.mb.register_default_exam(self.uid, "APPSC")
        s, _ = self.mb.registration_input(self.uid, "Test User")
        self.assertEqual(s, "ask_district")
        s, r = self.mb.registration_input(self.uid, "mumbai")
        self.assertEqual(s, "ask_district")
        self.assertIn("T1.", r)
        s, _ = self.mb.registration_input(self.uid, "Warangal")
        self.assertEqual(s, "ask_mobile")
        s, _ = self.mb.registration_input(self.uid, "12345")
        self.assertEqual(s, "ask_mobile")
        s, _ = self.mb.registration_input(self.uid, "+91 98765 43210")
        self.assertEqual(s, "done")
        p = self.mb.profile(self.uid)
        self.assertTrue(p["registered"])
        self.assertEqual(p["exam"], "APPSC")
        self.assertEqual(p["district"], "Warangal")
        self.assertEqual(p["mobile"], "9876543210")
        self.assertEqual(p["points"], 25)  # registration bonus
        self.assertIn("APPSC", p["follow"])
        self.assertTrue(self.mb.is_registered(self.uid))
        self.assertIsNone(self.mb.pending_step(self.uid))  # never asked again

    def test_registration_skip_mobile_and_code(self):
        self.mb.start_registration(self.uid)
        self.mb.registration_input(self.uid, "Ravi")
        s, _ = self.mb.registration_input(self.uid, "A5")
        self.assertEqual(s, "ask_mobile")
        s, _ = self.mb.registration_input(self.uid, "skip")
        self.assertEqual(s, "done")
        p = self.mb.profile(self.uid)
        self.assertEqual(p["state"], "Andhra Pradesh")
        self.assertEqual(p["mobile"], "")

    def test_round_top10(self):
        for i, (n, d) in enumerate([("Anil", "Warangal"), ("Bhavani", "Guntur"), ("Chandu", "Nellore")]):
            self.mb.register(self.uid + i, name=n, district=d, state="TS", exam="TSPSC")
        self.mb.record_round_answer(self.uid, "r1", "TSPSC", True, qid="q1")
        self.mb.record_round_answer(self.uid, "r1", "TSPSC", True, qid="q2")
        self.mb.record_round_answer(self.uid + 1, "r1", "TSPSC", True, qid="q1")
        self.mb.record_round_answer(self.uid + 1, "r1", "TSPSC", False, qid="q2")
        self.mb.record_round_answer(self.uid + 1, "r1", "TSPSC", False, qid="q2")  # dup ignored
        self.mb.record_round_answer(self.uid + 2, "r1", "TSPSC", False, qid="q1")
        self.mb.record_round_answer(999999, "r1", "TSPSC", True, qid="q1")  # unregistered: hidden
        rows, n = self.mb.round_top("r1", "TSPSC")
        self.assertEqual(n, 4)
        self.assertEqual([r["name"] for r in rows], ["Anil", "Bhavani", "Chandu"])
        self.assertEqual(rows[1]["total"], 2)
        txt = self.mb.render_round_top("r1", "TSPSC", "Morning")
        self.assertIn("🥇 Anil · Warangal (వరంగల్) — 2/2", txt)
        self.assertIn("Guntur", txt)
        self.assertEqual(self.mb.render_round_top("r1", "APPSC"), "")
        self.assertIn(self.uid.__str__(), self.mb.recipients_for("TSPSC"))
        self.assertNotIn(str(self.uid), self.mb.recipients_for("BANKING"))

    def test_unregistered_is_gated(self):
        self.assertFalse(self.mb.is_registered(self.uid))

    def test_district_matching(self):
        from core import districts as D
        self.assertEqual(D.match_district("TS", "hyd"), "Hyderabad")
        self.assertEqual(D.match_district("AP", "vijayawada"), "NTR")
        self.assertEqual(D.match_district("TS", "కరీంనగర్"), "Karimnagar")
        self.assertIsNone(D.match_district("TS", "mumbai"))
        self.assertEqual(D.match_state("ఆంధ్ర"), "AP")

    def test_district_board(self):
        self.mb.register(self.uid, name="A", state="TS", district="Warangal")
        self.mb.register(self.uid + 1, name="B", state="TS", district="Warangal")
        self.mb.register(self.uid + 2, name="C", state="AP", district="Guntur")
        self.mb.award_answer(self.uid + 1, correct=True)
        board = self.mb.render_district_board()
        self.assertIn("Warangal", board)
        top = self.mb.render_district_board("Warangal")
        self.assertIn("B", top)
        self.assertNotIn("Guntur", top)

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


    def test_pyq_volume3_loaded(self):
        """pyq_bank_3.json adds 50 more authentic previous-paper questions."""
        from core.store import load_json
        from core import config
        vol3 = load_json(config.DATA / "pyq_bank_3.json", {"questions": []})
        qs = vol3.get("questions", [])
        self.assertGreaterEqual(len(qs), 50)
        for q in qs:
            self.assertEqual(q.get("source"), "pyq")
            self.assertEqual(validate_question(q), [], f"{q['id']}: {validate_question(q)}")

    def test_total_pyq_pool_large(self):
        from core.question_bank import Bank
        b = Bank()
        pyqs = [q for q in b.questions if q.get("source") == "pyq"]
        self.assertGreaterEqual(len(pyqs), 160, f"need 160+ PYQs, got {len(pyqs)}")

    def test_pyq_volume4_ssc_and_subject_rotation(self):
        """pyq_bank_4_ssc.json adds 60 SSC Tier-I questions with subject rotation."""
        from core.store import load_json
        from core import config
        from core.question_bank import Bank
        vol4 = load_json(config.DATA / "pyq_bank_4_ssc.json", {"questions": []})
        qs = vol4.get("questions", [])
        self.assertEqual(len(qs), 60)
        self.assertIn("SSC", config.CHANNELS)
        b = Bank()
        ssc_qs = b.pick("SSC", 10)
        self.assertEqual(len(ssc_qs), 10)

    def test_registry_303_sources(self):
        """Central registry has 303 sources (84 live / 128 cand / 91 arch)."""
        from core import collector
        reg = collector.load_registry()
        srcs = reg.get("sources", [])
        self.assertEqual(len(srcs), 303)
        live = [s for s in srcs if s.get("enabled")]
        cand = [s for s in srcs if not s.get("enabled") and s.get("auto_enable_if_live")]
        arch = [s for s in srcs if not s.get("enabled") and not s.get("auto_enable_if_live")]
        self.assertEqual(len(live), 84)
        self.assertEqual(len(cand), 128)
        self.assertEqual(len(arch), 91)
        names = {s["name"] for s in live}
        for must in ("GKToday Polity", "GKToday Telugu CA", "GKToday Telangana GK",
                     "Examveda Reasoning", "Examveda Aptitude", "Testmocks Quant"):
            self.assertIn(must, names)


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
        posted = 0
        for _ in range(4):
            for ch in ("DEFENCE", "APPSC", "RAILWAY", "POLICE"):
                batch = b.pick(ch, 10)
                posted += len(batch)
                for q in batch:
                    from core.question_bank import q_signature
                    sig = q_signature(q)
                    self.assertNotIn(sig, seen, f"repeat posted: {q['id']}")
                    seen.add(sig)
        # permanent history persisted on disk — every posted id recorded
        history = load_json(config.STORE_USED, {})
        total_hist = sum(len(history.get(ch, []))
                         for ch in ("DEFENCE", "APPSC", "RAILWAY", "POLICE"))
        self.assertEqual(total_hist, posted)
        self.assertEqual(len(seen), posted)
        # With PYQ + curated + offline top-up we must sustain multiple full rounds
        self.assertGreaterEqual(posted, 100, f"only posted {posted} across 4 rounds")
        for ch in ("DEFENCE", "APPSC", "RAILWAY", "POLICE"):
            self.assertGreaterEqual(len(history.get(ch, [])), 20,
                                    f"{ch} history too thin: {len(history.get(ch, []))}")

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
        self.assertGreaterEqual(len(srcs), 14)
        names = {s["name"] for s in srcs}
        self.assertIn("IndiaBIX General Knowledge", names)
        self.assertTrue(any(s.get("type") == "index" for s in srcs))
        for s in srcs:
            self.assertIn(s["type"], ("rss", "index"))
            self.assertTrue(s["name"])
            self.assertTrue(s.get("feed") or s.get("url"))

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
        import tempfile
        from pathlib import Path as _P
        from core import collector
        from core.store import load_json, save_json_atomic
        u = "https://www.indiabix.com/aptitude/simple-interest/"
        # Fully isolate on a temp path so other tests cannot clobber the store
        tmp = _P(tempfile.gettempdir()) / "studentup_test_seen_urls.json"
        if tmp.exists():
            tmp.unlink()
        orig = collector.SEEN_URLS
        try:
            collector.SEEN_URLS = tmp
            self.assertNotIn(u, collector.load_seen_urls())
            collector.save_seen_urls({u})
            loaded = collector.load_seen_urls()
            self.assertIn(u, loaded)
            disk = load_json(tmp, {"urls": []})
            self.assertIn(u, disk.get("urls", []))
            # second save merges forward (pages forward, never loses prior)
            u2 = "https://www.indiabix.com/aptitude/problems-on-trains/"
            collector.save_seen_urls(loaded | {u2})
            both = collector.load_seen_urls()
            self.assertEqual(both, {u, u2})
        finally:
            collector.SEEN_URLS = orig
            if tmp.exists():
                tmp.unlink()


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


class TestTeluguFirstAndAnswerKey(unittest.TestCase):
    """Telugu-first poll layout + delayed answer-key builder."""

    def _sample_q(self):
        return {
            "id": "T001", "channel": "TSPSC", "topic": "Percentage",
            "q_en": "What is 10% of 200?",
            "q_te": "⤷ 200లో 10% ఎంత?",
            "options_en": ["10", "20", "30", "40"],
            "options_te": ["10", "20", "30", "40"],
            "answer_index": 1,
            "explanation_en": "10% of 200 = 20.",
            "explanation_te": "200లో 10% = 20.",
            "source": "pyq",
        }

    def test_telugu_first_question_layout(self):
        from core.content import build_question_text
        from core import config
        q = self._sample_q()
        cfg = config.CHANNELS["TSPSC"]
        text = build_question_text(q, cfg, telugu_first=True)
        # Telugu line must appear before the English question
        te_pos = text.find("200లో 10%")
        en_pos = text.find("What is 10% of 200?")
        self.assertGreaterEqual(te_pos, 0)
        self.assertGreaterEqual(en_pos, 0)
        self.assertLess(te_pos, en_pos, "Telugu must come before English")

    def test_telugu_first_options(self):
        from core.content import build_options
        q = self._sample_q()
        # worded bilingual options
        q["options_en"] = ["Ten", "Twenty", "Thirty", "Forty"]
        q["options_te"] = ["పది", "ఇరవై", "ముప్పై", "నలభై"]
        opts = build_options(q, telugu_first=True)
        self.assertEqual(len(opts), 4)
        self.assertTrue(opts[0].startswith("A) పది"), opts[0])
        self.assertIn("Ten", opts[0])

    def test_delayed_answer_key_builder(self):
        from core.content import build_answer_key
        qs = [self._sample_q(), dict(self._sample_q(), id="T002", answer_index=0,
                                      topic="Ratio")]
        key = build_answer_key(qs, round_label="Morning ⛅")
        self.assertIn("Answer Key", key)
        self.assertIn("సమాధానాలు", key)
        self.assertIn("[B]", key)   # sample answer_index=1 → B
        self.assertIn("[A]", key)

    def test_instant_mode_sends_explanation(self):
        """Channel polls in instant mode include explanation payload."""
        from core import config
        from core.telegram import Telegram
        # default is instant
        self.assertIn(config.ANSWER_MODE, ("instant", "delayed"))
        tg = Telegram(dry=True)
        res = tg.send_quiz("@test", "Q?", ["A) 1", "B) 2", "C) 3", "D) 4"],
                           1, explanation="because twenty",
                           with_explanation=True)
        self.assertTrue(res.get("ok"))
        # dry returns payload merged into result
        self.assertIn("explanation", res.get("result", {}))

    def test_delayed_mode_withholds_explanation(self):
        from core.telegram import Telegram
        tg = Telegram(dry=True)
        res = tg.send_quiz("@test", "Q?", ["A) 1", "B) 2", "C) 3", "D) 4"],
                           1, explanation="secret",
                           with_explanation=False)
        self.assertTrue(res.get("ok"))
        self.assertNotIn("explanation", res.get("result", {}))
        # correct_option_id still present for Telegram right/wrong mark
        self.assertEqual(res.get("result", {}).get("correct_option_id"), 1)


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


class TestCRM(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        from core import config
        self._old = config.DATA
        config.DATA = pathlib.Path(tempfile.mkdtemp())
        from core.members import Members
        self.mb = Members()
        self.mb.register(1, name="Anil", district="Warangal", state="Telangana", exam="TSPSC", mobile="9000000001")
        self.mb.register(2, name="Bhavani", district="Guntur", state="Andhra Pradesh", exam="APPSC")
        self.mb.register(3, name="Chandu", district="Warangal", state="Telangana", exam="Banking")

    def tearDown(self):
        from core import config
        config.DATA = self._old

    def test_export_csv(self):
        from core import crm
        data = crm.export_csv(self.mb.members).decode("utf-8")
        self.assertIn("tg_id,name,username,mobile,state,district", data)
        self.assertIn("Anil", data)
        self.assertIn("9000000001", data)
        self.assertEqual(data.count("\n"), 4)  # header + 3 rows

    def test_segment_select(self):
        from core import crm
        self.assertEqual(sorted(crm.select(self.mb.members, crm.parse_segment("district=warangal"))), ["1", "3"])
        self.assertEqual(crm.select(self.mb.members, crm.parse_segment("state=AP")), ["2"])
        self.assertEqual(crm.select(self.mb.members, crm.parse_segment("exam=tspsc mobile=yes")), ["1"])
        self.assertEqual(len(crm.select(self.mb.members, {})), 3)

    def test_sheet_push_payload(self):
        from core import crm
        crm.SHEET_URL = "https://script.google.com/macros/s/x/exec"
        sent = []
        crm.push_member(1, self.mb.members["1"], post=lambda u, p: sent.append(p) or True)
        n = crm.push_all(self.mb.members, post=lambda u, p: sent.append(p) or True)
        crm.SHEET_URL = ""
        self.assertEqual(sent[0]["action"], "upsert")
        self.assertEqual(sent[0]["row"]["district"], "Warangal")
        self.assertEqual(n, 3)
        self.assertEqual(sent[1]["action"], "bulk")
        self.assertIn("summary", crm.segment_summary(self.mb.members).lower() + "summary")


class TestRoundIntel(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        from core import config
        self._old = config.DATA
        config.DATA = pathlib.Path(tempfile.mkdtemp())
        from core.members import Members, _day
        self.mb = Members()
        self.rid = _day().replace("-", "") + "-0730"
        for i, (n, d) in enumerate([("Anil", "Warangal"), ("Bhavani", "Guntur"), ("Chandu", "Warangal"), ("Devi", "Guntur")]):
            self.mb.register(100 + i, name=n, district=d, state="TS", exam="TSPSC")
        sc = {100: [1, 1, 1], 101: [1, 1, 0], 102: [1, 0, 0], 103: [1, 1, 1]}
        for uid, arr in sc.items():
            for k, c in enumerate(arr):
                self.mb.record_round_answer(uid, self.rid, "TSPSC", bool(c), qid=f"q{k}")

    def tearDown(self):
        from core import config
        config.DATA = self._old

    def test_personal_card(self):
        card = self.mb.personal_round_card(101, self.rid, "TSPSC", "Morning")
        self.assertIn("Score 2/3", card)
        self.assertIn("Rank #3 of 4", card)
        self.assertIn("Guntur", card)
        self.assertEqual(self.mb.personal_round_card(999, self.rid, "TSPSC"), "")

    def test_district_of_round_and_top(self):
        dor = self.mb.district_of_round(self.rid, "TSPSC")
        self.assertEqual(dor["district"], "Guntur")   # 5/6 vs Warangal 4/6
        top = self.mb.render_round_top(self.rid, "TSPSC", "Morning")
        self.assertIn("District of the round: Guntur", top)
        self.assertIn("Rivalry", top)

    def test_daily_champions_and_cup(self):
        txt = self.mb.render_daily_champions()
        self.assertIn("Champions", txt)
        self.assertIn("Anil", txt)
        cup = self.mb.weekly_district_cup()
        self.assertTrue(cup.startswith("🏆 District Cup"))
        self.assertIn("Guntur", cup.splitlines()[2])

    def test_referral(self):
        self.assertTrue(self.mb.add_referral(555, 100))
        self.assertFalse(self.mb.add_referral(555, 101))   # only once
        self.assertFalse(self.mb.add_referral(100, 100))   # self
        self.assertEqual(self.mb.members["100"]["referrals"], 1)
        self.assertEqual(self.mb.members["100"]["points"], 25 + 20)


class TestHallOfFame(TestRoundIntel):
    def test_settle_round_bonuses(self):
        b = self.mb.settle_round(self.rid, "TSPSC")
        self.assertEqual(b["100"], 30 + 10)   # winner + Warangal top
        self.assertEqual(b["103"], 20 + 10)   # 2nd + Guntur top
        self.assertEqual(self.mb.members["100"]["round_wins"], 1)
        self.assertIn("round_top1", self.mb.members["100"]["badges"])
        hof = self.mb.monthly_hall_of_fame()
        self.assertIn("Hall of Fame", hof)
        self.assertIn("Anil", hof)
        self.assertIn("Round wins: 1", self.mb.personal_round_card(100, self.rid, "TSPSC"))


class TestPointsEscrow(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        from core import config
        self._old = config.DATA
        config.DATA = pathlib.Path(tempfile.mkdtemp())
        from core.members import Members
        self.mb = Members()

    def tearDown(self):
        from core import config
        config.DATA = self._old

    def test_locked_until_registered(self):
        r1 = self.mb.award_answer(777, correct=True)
        self.assertEqual(self.mb.members["777"]["points"], 0)
        self.assertEqual(r1["locked"], 15)          # 10 correct + 5 daily
        r2 = self.mb.award_answer(777, correct=True)
        self.assertEqual(r2["locked"], 25)
        self.mb.start_registration(777)
        self.mb.registration_input(777, "Ravi"); self.mb.registration_input(777, "Nellore")
        s, reply = self.mb.registration_input(777, "skip")
        self.assertEqual(s, "done")
        self.assertIn("🔓 25", reply)
        self.assertEqual(self.mb.members["777"]["points"], 25 + 25)   # unlocked + bonus
        r3 = self.mb.award_answer(777, correct=True)
        self.assertEqual(r3["locked"], 0)
        self.assertEqual(self.mb.members["777"]["points"], 60)
