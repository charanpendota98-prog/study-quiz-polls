# -*- coding: utf-8 -*-
"""320X — perfection round:
① Academic parser root fix: '(...)' counts as the Telugu gloss only
   when it contains Telugu script — math/code options ('O(log n)',
   '1 - (T2/T1)') were shredded into duplicate EN stubs, which
   bank-health flagged as invalid. Bank: invalid 0, grade C → B.
② Go-Live announcement (310X completion): announcement text builder
   + dashboard auto-send to Telegram admin + copy-to-WhatsApp.
③ Syllabus graph memoization regression pin (260X cache intact).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import publish_queue  # noqa: E402

DASH = (ROOT / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
QB = (ROOT / "scripts" / "core" / "question_bank.py").read_text(encoding="utf-8")


class TestAcademicParserFix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.question_bank import load_academic_questions
        cls.items = load_academic_questions()

    def _find(self, frag):
        return next(q for q in self.items if frag in q["q_en"])

    def test_math_options_not_shredded(self):
        q = self._find("Binary Search")
        self.assertEqual(q["options_en"],
                         ["O(1)", "O(n)", "O(log n)", "O(n log n)"])
        self.assertEqual(q["options_en"][q["answer_index"]], "O(log n)")

    def test_carnot_options_and_answer(self):
        q = self._find("Carnot engine")
        self.assertEqual(q["options_en"][q["answer_index"]], "1 - (T2 / T1)")
        self.assertEqual(len(set(q["options_en"])), 4)

    def test_no_duplicate_options_anywhere(self):
        for q in self.items:
            opts = [o.strip().lower() for o in q["options_en"]]
            self.assertEqual(len(opts), len(set(opts)),
                             f"dup options: {q['id']}")

    def test_parser_guard_present(self):
        self.assertIn("320X root fix", QB)
        self.assertIn("re.search", QB)

    def test_bank_health_invalid_zero(self):
        from core import bankhealth
        from core.question_bank import load_bank
        bank = load_bank()
        qs = bank.questions if hasattr(bank, "questions") else list(bank)
        rep = bankhealth.bank_health_report(qs)
        self.assertEqual(rep["invalid"], {},
                         f"invalid questions remain: {rep['invalid']}")


class TestAnnouncement(unittest.TestCase):
    def _draft(self, **kw):
        d = publish_queue.build_draft(
            "2026-10-25",
            [{"source": "pyq"}] * 4 + [{"source": "curated"}] * 6,
            [{"id": "E1", "title": "Sunday Mock", "n_q": 15,
              "starts_at": "2026-10-25T10:00", "status": "scheduled"}],
            True, {"n_q": 25, "time": "10:00"})
        d.update(kw)
        return d

    def test_full_announcement(self):
        txt = publish_queue.announcement_text(
            self._draft(), "https://quiz.studentup.in/portal")
        self.assertIn("Daily Quiz: 10 questions (PYQ 4)", txt)
        self.assertIn("Live Exam: Sunday Mock", txt)
        self.assertIn("Weekly Grand Test: 25", txt)
        self.assertTrue(txt.endswith("https://quiz.studentup.in/portal"))

    def test_plain_day_no_grand_no_url(self):
        d = publish_queue.build_draft("2026-10-19", [], [], False)
        txt = publish_queue.announcement_text(d)
        self.assertNotIn("Weekly Grand", txt)
        self.assertNotIn("http", txt)

    def test_dashboard_wiring(self):
        i = DASH.index('p.path == "/api/publish/go_live"')
        seg = DASH[i:i + 1600]
        self.assertIn("announcement_text", seg)
        self.assertIn("sent_to_admin", seg)
        self.assertIn("navigator.clipboard.writeText(d.announcement)", DASH)


class TestSyllabusMemoPin(unittest.TestCase):
    def test_exam_graph_cached_identity(self):
        from core import syllabus

        class FakeBank:
            questions = [{"topic": "Polity"}]

            def by_channel(self, ch):
                return [{"topic": "Polity", "q_en": "x"}]

        g1 = syllabus.exam_graph(FakeBank(), "TSPSC")
        g2 = syllabus.exam_graph(FakeBank(), "TSPSC")
        self.assertIs(g1, g2, "260X memoization regressed")


if __name__ == "__main__":
    unittest.main()
