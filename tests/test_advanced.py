#!/usr/bin/env python3
"""
STUDENTUP — ADVANCED PIPELINE TESTS
Covers the exam-paper blueprint composer, the upgraded multi-site quiz parser
(GKToday / Examveda / PDF-text layouts), Telugu-native ingestion, PDF/TXT
ingestion and the content-gated index audit. Offline — no network.
Run:  python3 -m unittest -v tests.test_advanced
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import config, collector, blueprint  # noqa: E402
from core.question_bank import Bank, rebuild_json  # noqa: E402
from core.content import validate_question  # noqa: E402

FX = ROOT / "tests"


def _clean():
    for f in ("question_bank.json", "question_bank_extra.json",
              "shown_signatures.json", "used_questions.json",
              "scraped_bank.json", "scraped_pending.json", "collector_seen.json"):
        p = config.DATA / f
        if p.exists():
            p.unlink()


class TestParserLayouts(unittest.TestCase):
    def _parse(self, name):
        html = (FX / name).read_text(encoding="utf-8")
        return collector.parse_quiz_lines(collector.html_to_lines(html), "Quiz", "x")

    def test_gktoday_layout(self):
        """[A]..[D] options, 'Correct Answer: C [1952]', Notes: on next line,
        numbered sub-statements folded into the stem, Show Answer ignored."""
        raws = self._parse("fixture_gktoday.html")
        self.assertEqual(len(raws), 4)
        self.assertEqual([r["answer_index"] for r in raws], [2, 1, 3, 1])
        self.assertTrue(raws[0]["explanation_en"].startswith("The first Lok Sabha"))
        self.assertIn("1. Manikyamba", raws[2]["q_en"])
        self.assertIn("correctly matched?", raws[2]["q_en"])
        self.assertEqual(raws[2]["options_en"][3], "All are correct")
        for r in raws:
            self.assertNotIn("Show Answer", r["q_en"] + r["explanation_en"])

    def test_examveda_layout(self):
        """'A. x' options, 'Answer: Option B', Solution: body, chrome skipped."""
        raws = self._parse("fixture_examveda.html")
        self.assertEqual(len(raws), 3)
        self.assertEqual([r["answer_index"] for r in raws], [1, 3, 1])
        self.assertEqual(raws[2]["options_en"], ["SUITER", "VIOUER", "WALKER", "SUFFER"])
        self.assertTrue(raws[0]["explanation_en"].startswith("Each letter of FIRE"))
        for r in raws:
            self.assertNotIn("Discuss in Board", r["explanation_en"])

    def test_legacy_wordpress_layout_unchanged(self):
        raws = self._parse("fixture_quiz.html")
        self.assertEqual(len(raws), 4)
        self.assertEqual(raws[3]["explanation_en"], "Rule x2+1: 31×2+1 = 63.")

    def test_answer_regex_ignores_chrome(self):
        self.assertIsNone(collector.ANS_RE.search("Answer & Solution Discuss in Board"))
        self.assertEqual(collector.ANS_RE.search("Correct Answer: C [1952]").group(1), "C")
        self.assertEqual(collector.ANS_RE.search("Answer: Option D").group(1), "D")
        self.assertEqual(collector.ANS_RE.search("Ans- b").group(1), "b")

    def test_pdf_text_lines_split_glued_options(self):
        txt = ("1. The HCF of 12 and 18 is (a) 2 (b) 3 (c) 6 (d) 9\n"
               "Ans: (c)\nSolution: 6 divides both.\n"
               "2. Capital of Telangana? (a) Warangal (b) Hyderabad (c) Nizamabad (d) Khammam\n"
               "Answer: b\n")
        lines = collector.text_to_lines(txt)
        raws = collector.parse_quiz_lines(lines, "TSPSC PYQ 2023", "file://x.pdf")
        self.assertEqual(len(raws), 2)
        self.assertEqual(raws[0]["options_en"], ["2", "3", "6", "9"])
        self.assertEqual(raws[0]["answer_index"], 2)
        self.assertEqual(raws[1]["answer_index"], 1)


class TestIngestion(unittest.TestCase):
    def setUp(self):
        _clean()

    def tearDown(self):
        _clean()

    def test_telugu_native_page_needs_no_translation(self):
        html = ("<article><p>1. ‘దీర్ఘవధి కృషక్ పుంజీ సహకార యోజన’ను ఏ సంస్థ ప్రారంభించింది?</p>"
                "<p>[A] NCDC</p><p>[B] వ్యవసాయ మంత్రిత్వ శాఖ</p><p>[C] RBI</p><p>[D] NABARD</p>"
                "<p>Show Answer</p><p>Correct Answer: A [NCDC]</p>"
                "<p>Notes:</p><p>సహకార మంత్రిత్వ శాఖ ఆధ్వర్యంలోని NCDC ఈ పథకాన్ని ప్రారంభించింది.</p>"
                "</article>")
        st = collector.collect_daily(fixture=(html, "Telugu Current Affairs", "http://t/1"))
        self.assertEqual(st["accepted"], 1)
        self.assertEqual(st["parked"], 0)
        qs, _ = rebuild_json()
        q = [x for x in qs if x.get("source") == "scraped"][0]
        self.assertEqual(validate_question(q), [])
        self.assertEqual(q["q_te"], q["q_en"])

    def test_txt_paper_ingest(self):
        import tempfile
        p = Path(tempfile.gettempdir()) / "ssc_cgl_2024_pyq.txt"
        p.write_text("1. 15% of 240 is (a) 32 (b) 36 (c) 40 (d) 45\nAns: (b)\n"
                     "2. 3, 7, 15, 31, ? (a) 62 (b) 63 (c) 64 (d) 65\nAnswer: b\n",
                     encoding="utf-8")
        try:
            st = collector.ingest_pdf(p)
            self.assertEqual(st["accepted"], 2)
            bank = collector.load_json(collector.SCRAPED_BANK, {"questions": []})
            self.assertTrue(all(q["bank"] == "pdf" for q in bank["questions"]))
            self.assertTrue(all("ssc_cgl_2024_pyq" in q["provenance"] for q in bank["questions"]))
        finally:
            p.unlink()


class TestBlueprint(unittest.TestCase):
    def setUp(self):
        _clean()

    def tearDown(self):
        _clean()

    def test_blueprint_loaded_for_every_public_channel(self):
        bp = blueprint.blueprint()
        for ch in config.PUBLIC_CHANNELS:
            self.assertIn(ch, bp["channels"], ch)
            self.assertAlmostEqual(sum(bp["channels"][ch]["weights"].values()), 1.0, places=2)

    def test_subject_and_difficulty_heuristics(self):
        self.assertEqual(blueprint.subject_of({"topic": "Quantitative Aptitude - Percentage"}), "quant")
        self.assertEqual(blueprint.subject_of({"topic": "English Comprehension - Idioms"}), "english")
        self.assertEqual(blueprint.subject_of({"topic": "Reasoning - Syllogism"}), "reasoning")
        self.assertEqual(blueprint.subject_of({"topic": "History"}), "gk")
        hard = {"q_en": "Consider the following statements: 1. A 2. B 3. C Which of the above statements is/are correct?",
                "options_en": ["1 only", "2 and 3", "1 and 3", "1, 2 and 3"]}
        easy = {"q_en": "Capital of Telangana?", "options_en": ["Hyderabad", "Warangal", "Nizamabad", "Karimnagar"]}
        self.assertEqual(blueprint.difficulty_of(hard), "hard")
        self.assertEqual(blueprint.difficulty_of(easy), "easy")
        self.assertEqual(blueprint.difficulty_of({"q_en": "x", "difficulty": "medium", "options_en": []}), "medium")

    def test_ssc_round_matches_tier1_paper(self):
        """SSC Tier-I = 25/25/25/25 -> a 10-Q round carries all 4 subjects,
        2-3 each, at least 3 non-easy, subjects at mixed positions."""
        b = Bank()
        qs = b.pick("SSC", 10)
        prof = blueprint.round_profile(qs)
        self.assertEqual(len(qs), 10)
        self.assertEqual(set(prof["subjects"]), {"reasoning", "quant", "english", "gk"})
        self.assertTrue(all(2 <= v <= 3 for v in prof["subjects"].values()), prof)
        self.assertGreaterEqual(prof["difficulty"].get("medium", 0) + prof["difficulty"].get("hard", 0), 3)
        subj_seq = [blueprint.subject_of(q) for q in qs]
        # not neat blocks: at least 5 subject changes across 10 positions
        changes = sum(1 for a, c in zip(subj_seq, subj_seq[1:]) if a != c)
        self.assertGreaterEqual(changes, 5, subj_seq)

    def test_banking_round_is_quant_heavy(self):
        b = Bank()
        qs = b.pick("BANKING", 10)
        prof = blueprint.round_profile(qs)
        self.assertGreaterEqual(prof["subjects"].get("quant", 0), 4, prof)

    def test_rounds_never_repeat_across_blueprint_picks(self):
        b = Bank()
        seen = set()
        for _ in range(3):
            for q in b.pick("RAILWAY", 10):
                self.assertNotIn(q["id"], seen)
                seen.add(q["id"])
            b = Bank()


class TestIndexAudit(unittest.TestCase):
    def test_index_page_with_mcqs_but_no_links_is_live(self):
        from core.auditor import check_source
        html = (FX / "fixture_gktoday.html").read_text(encoding="utf-8")
        src = {"name": "GKToday Polity", "type": "index", "url": "https://www.gktoday.in/quizbase/x",
               "link_re": r"(?!)", "page_re": r"\?pageno=[0-9]+$"}
        r = check_source(src, http_get=lambda u, **k: html)
        self.assertEqual(r["status"], "live")
        self.assertGreaterEqual(r["questions"], 4)
        self.assertGreaterEqual(r["links"], 2)

    def test_index_page_without_content_is_warn(self):
        from core.auditor import check_source
        src = {"name": "Empty", "type": "index", "url": "https://x/", "link_re": r"(?!)"}
        r = check_source(src, http_get=lambda u, **k: "<html><body>Please wait...</body></html>")
        self.assertEqual(r["status"], "warn")


class TestTeluguSources(unittest.TestCase):
    """Sakshi / MCQBits layouts + backfill & PDF-harvest plumbing (offline)."""

    def _parse(self, name, url):
        html = (FX / name).read_text(encoding="utf-8")
        return collector.parse_quiz_lines(collector.html_to_lines(html), "t", url)

    def test_sakshi_bitbank_numeric_options_and_key(self):
        qs = self._parse("fixture_sakshi_bitbank.html",
                         "https://education.sakshi.com/ts-police/bitbank/telangana-history/x-1")
        self.assertEqual(len(qs), 3)
        self.assertEqual(qs[0]["q_en"], "కాకతీయ రాజ్య స్థాపకుడు ఎవరు?")
        self.assertEqual(qs[0]["options_en"][0], "బేతరాజు")
        self.assertEqual([q["answer_index"] for q in qs], [0, 1, 0])

    def test_sakshi_practice_telugu_labels(self):
        qs = self._parse("fixture_sakshi_practice.html",
                         "https://education.sakshi.com/groups/practice-test/ap-economy/x-1")
        self.assertEqual(len(qs), 2)
        self.assertEqual([q["answer_index"] for q in qs], [1, 2])
        self.assertEqual(qs[1]["options_en"][2], "కృష్ణా")

    def test_mcqbits_repeated_answer_line(self):
        qs = self._parse("fixture_mcqbits.html", "https://mcqbits.com/x/")
        self.assertEqual(len(qs), 2)
        self.assertEqual([q["answer_index"] for q in qs], [1, 2])
        self.assertIn("86th Amendment", qs[0]["explanation_en"])

    def test_numbered_substatements_not_mangled(self):
        # only a full 1)..4) run is rewritten to A)..D); two sub-statements stay as-is
        lines = ["1. Consider the following statements:", "1) India is a republic",
                 "2) India has a President", "Which is correct?",
                 "A) 1 only", "B) 2 only", "C) Both", "D) None", "Answer: C"]
        self.assertEqual(collector._normalize_numeric_options(list(lines)), lines)

    def test_channel_for_source_telugu_tags(self):
        self.assertEqual(collector.channel_for_source({"exam": "police"}), "POLICE")
        self.assertEqual(collector.channel_for_source({"exam": "tspsc"}), "TSPSC")
        self.assertIsNone(collector.channel_for_source({"exam": "all"}))

    def test_registry_has_sakshi_and_mcqbits_live(self):
        reg = collector.load_registry()
        live = {s["name"]: s for s in reg["sources"] if s.get("enabled")}
        self.assertTrue(any(n.startswith("Sakshi TS Police Bitbank") for n in live))
        self.assertTrue(any(n.startswith("MCQBits") for n in live))
        pdfs = [s for s in reg["sources"] if s.get("enabled") and s.get("pdf_re")]
        self.assertTrue(pdfs, "Eenadu Pratibha PDF sources must be live")
        for s in live.values():
            if "sakshi.com" in s.get("url", s.get("index", "")):
                self.assertNotIn("/ts-police/practice-test", s["url"])

    def test_backfill_state_dry_run(self):
        import json
        st_path = collector.BACKFILL_STATE
        bak = st_path.read_text(encoding="utf-8") if st_path.exists() else None
        try:
            if st_path.exists():
                st_path.unlink()
            orig = collector.collect_daily
            collector.collect_daily = lambda **kw: {"accepted": 0, "articles": 0}
            orig_inbox = collector.ingest_inbox
            collector.ingest_inbox = lambda **kw: {"accepted": 0, "files": 0}
            try:
                st = collector.backfill(days=90, dry=True)
            finally:
                collector.collect_daily = orig
                collector.ingest_inbox = orig_inbox
            self.assertEqual(st["runs"], 1)
            self.assertFalse(st["done"])
            self.assertEqual(st["idle_runs"], 1)
            self.assertFalse(st_path.exists())   # dry run never persists
        finally:
            if bak is not None:
                st_path.write_text(bak, encoding="utf-8")

    def test_freshersnow_answer_with_text(self):
        qs = self._parse("fixture_freshersnow.html", "https://www.freshersnow.com/telangana-gk-quiz/")
        self.assertEqual(len(qs), 2)
        self.assertEqual([q["answer_index"] for q in qs], [3, 0])
        self.assertIn("Godavari", qs[0]["explanation_en"])

    def test_examsbook_bare_q_label(self):
        qs = self._parse("fixture_examsbook.html", "https://www.examsbook.com/reasoning-questions-and-answers")
        self.assertEqual(len(qs), 2)
        self.assertEqual([q["answer_index"] for q in qs], [2, 3])
        self.assertTrue(qs[0]["q_en"].startswith("If PARTICLE"))

    def test_gkseries_bare_labels(self):
        qs = self._parse("fixture_gkseries.html",
                         "https://www.gkseries.com/general-knowledge/indian-polity/x/fundamental-rights")
        self.assertEqual(len(qs), 2)
        self.assertEqual([q["answer_index"] for q in qs], [2, 1])
        self.assertEqual(qs[1]["options_en"], ["Part II", "Part III", "Part IV", "Part V"])

    def test_affairscloud_five_options(self):
        from core.collector import parse_quiz_lines
        lines = ["1. A is the daughter of B's only son. How is A related to B?",
                 "1) Sister", "2) Granddaughter", "3) Cousin", "4) Aunt", "5) None of these",
                 "Answer- 2) Granddaughter", "Solution:", "B's son is A's father.",
                 "2. Which one cannot be determined?",
                 "1) Father", "2) Uncle", "3) Brother", "4) Mother", "5) None of these",
                 "Answer- 5) None of these"]
        qs = parse_quiz_lines(lines, "Blood Relation Set 24", "https://affairscloud.com/x/")
        self.assertEqual(len(qs), 1)
        self.assertEqual(qs[0]["answer_index"], 1)
        self.assertEqual(len(qs[0]["options_en"]), 4)

    def test_paced_round_timing(self):
        from core.blueprint import pace_seconds, pace_label
        easy = {"q_en": "Capital of Telangana?", "options_en": ["A", "B", "C", "D"], "topic": "gk"}
        hard = {"q_en": "Consider the following statements: 1. x 2. y 3. z. Which of the above are correct with respect to the Governor?", "options_en": ["1 and 2 only", "2 and 3 only", "1 and 3 only", "1, 2 and 3"], "topic": "polity"}
        self.assertEqual(pace_seconds(easy), 60)
        self.assertEqual(pace_seconds(hard), 90)
        self.assertIn("⏱ 1 min", pace_label(easy))
        self.assertIn("1.5 min", pace_label(hard))
        # reasoning medium gets the long slot (needs working)
        med = {"q_en": "In a certain code MOBILE is written as NPCJMF. How is PHONE coded?", "options_en": ["QIPOF", "QIPPF", "QJPOF", "OGNMD"], "topic": "reasoning - coding"}
        self.assertEqual(pace_seconds(med), 90)

    def test_two_reminders_only(self):
        self.assertEqual(tuple(config.REMINDER_BEFORE_MIN), (5, 1))
        import watch
        self.assertEqual(watch.due_reminders("07:25"), 5)
        self.assertEqual(watch.due_reminders("07:29"), 1)
        self.assertIsNone(watch.due_reminders("07:20"))

    def test_question_header_has_position_and_badge(self):
        from core.content import build_question_text
        q = {"q_en": "Capital of Telangana?", "q_te": "తెలంగాణ రాజధాని?", "topic": "gk"}
        t = build_question_text(q, {"emoji": "📘", "subject": "TSPSC"}, position="Q 3/10", badge="⚡ Easy • ⏱ 1 min")
        self.assertIn("Q 3/10 • ⚡ Easy • ⏱ 1 min", t)
        self.assertLessEqual(len(t), 300)

    def test_schedule_has_nightly_backfill(self):
        self.assertIn("backfill", {v[0] for v in config.SCHEDULE.values()})


if __name__ == "__main__":
    unittest.main(verbosity=2)
