"""370X — Paper Factory: official papers → draft → owner approve.

Locks: filename provenance, tolerant parse with provenance stamp,
bank-untranslated questions stay OUT of the bank (translation gate),
go_bank idempotency semantics, reject gating.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import config, paperfactory  # noqa: E402
from core.store import save_json_atomic  # noqa: E402

PAPER = ("1. The HCF of 12 and 18 is (a) 2 (b) 3 (c) 6 (d) 9\n"
         "Ans: (c)\n"
         "2. Capital of Telangana? (a) Warangal (b) Hyderabad "
         "(c) Nizamabad (d) Khammam\nAnswer: b\n")


class PaperFactoryTest(unittest.TestCase):
    DIR = None

    @classmethod
    def setUpClass(cls):
        cls.DIR = config.DATA
        cls.TMP = Path(tempfile.mkdtemp())
        config.DATA = cls.TMP

    @classmethod
    def tearDownClass(cls):
        config.DATA = cls.DIR

    def test_paper_meta_filename(self):
        m = paperfactory.paper_meta("TSPSC Group-II 2023 Paper-I.pdf")
        self.assertEqual(m["exam"], "TSPSC")
        self.assertEqual(m["year"], "2023")
        self.assertEqual(m["paper"], "Paper-I")
        m2 = paperfactory.paper_meta("some-notes.pdf")
        self.assertEqual(m2["exam"], "")

    def test_parse_stamps_provenance(self):
        qs = paperfactory.parse_questions(
            PAPER, paperfactory.paper_meta("TSPSC 2023 Paper-I.txt"),
            "TSPSC 2023 Paper-I.txt")
        self.assertEqual(len(qs), 2)
        self.assertTrue(all(q["id"].startswith("PAPER-TSPSC-2023-")
                            for q in qs))
        self.assertTrue(all(q.get("exam") == "TSPSC" for q in qs))
        # EN-only sample parks for translation (honest draft flag)
        self.assertTrue(all(q.get("translation_pending") for q in qs))

    def test_draft_go_bank_translation_gate(self):
        p = self.TMP / "APPSC 2022 Paper-II.txt"
        p.write_text(PAPER, encoding="utf-8")
        r = paperfactory.make_draft(p)
        self.assertTrue(r["ok"] and r["parsed"] == 2)
        self.assertEqual(r["needs_translation"], 2)
        g1 = paperfactory.go_bank(r["draft_id"])
        self.assertEqual(g1["added"], 0)
        self.assertEqual(g1["translation_pending"], 2)
        # still draft (partial) — owner can retry after translation
        again = paperfactory.list_drafts()
        self.assertEqual(again[0]["status"], "draft")
        # manually "translated" question banks cleanly
        d = paperfactory._load_drafts()
        draft = d["drafts"][r["draft_id"]]
        q0 = draft["questions"][0]
        q0.pop("translation_pending", None)
        q0["q_te"] = "12 සහ 18 గ.సా.గు ఎంత?"
        q0["options_te"] = list(q0["options_en"])
        save_json_atomic(paperfactory._drafts_path(), d)
        g2 = paperfactory.go_bank(r["draft_id"])
        self.assertEqual(g2["added"], 1)

    def test_go_bank_dedupes(self):
        p = self.TMP / "AP 2021 Paper-I.txt"
        p.write_text(PAPER, encoding="utf-8")
        r = paperfactory.make_draft(p)
        d = paperfactory._load_drafts()
        draft = d["drafts"][r["draft_id"]]
        for q in draft["questions"]:
            q.pop("translation_pending", None)
            q["q_te"] = q["q_en"] + " తెలుగు అనువాదం"
        save_json_atomic(paperfactory._drafts_path(), d)
        g1 = paperfactory.go_bank(r["draft_id"])
        self.assertEqual(g1["added"], 2)
        draft2 = paperfactory.make_draft(p)
        self.assertEqual(draft2["duplicates"], 2)
        self.assertEqual(draft2["fresh"], 0)

    def test_reject_gate(self):
        p = self.TMP / "rejectme.txt"
        p.write_text(PAPER, encoding="utf-8")
        r = paperfactory.make_draft(p)
        self.assertTrue(paperfactory.reject_draft(r["draft_id"])["ok"])
        self.assertFalse(paperfactory.reject_draft(r["draft_id"])["ok"])
        self.assertFalse(paperfactory.reject_draft("nope")["ok"])

    def test_missing_file_honest_error(self):
        r = paperfactory.make_draft(self.TMP / "nope.pdf")
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
