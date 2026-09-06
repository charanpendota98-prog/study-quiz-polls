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


if __name__ == "__main__":
    unittest.main(verbosity=2)
