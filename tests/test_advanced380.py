"""380X — Paper Factory Pro: OCR fallback + translation bridge.

Locks: scanned/junk PDFs report ocr-needed (never crash, never
fake text); translate_draft with a working translator clears the
pending flag so go_bank banks the question; a broken translator
keeps questions parked; terminal drafts refuse translation.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import config, paperfactory  # noqa: E402

PAPER = ("1. The HCF of 12 and 18 is (a) 2 (b) 3 (c) 6 (d) 9\n"
         "Ans: (c)\n"
         "2. Capital of Telangana? (a) Warangal (b) Hyderabad "
         "(c) Nizamabad (d) Khammam\nAnswer: b\n")


class _StubLLM:
    """Deterministic exam-grade translator stand-in."""

    def chat(self, system, user):
        payload = json.loads(user)
        q = payload["q"]
        if "HCF" in q:
            return json.dumps({
                "q_en": q,
                "q_te": "12 మరియు 18 యొక్క గ.సా.గు ఎంత?",
                "options_en": payload["options"],
                "options_te": ["2", "3", "6", "9"],
                "explanation_te": ""}, ensure_ascii=False)
        return json.dumps({
            "q_en": q,
            "q_te": "తెలంగాణ రాజధాని ఏది?",
            "options_en": payload["options"],
            "options_te": ["వరంగల్", "హైదరాబాద్", "నిజామాబాద్", "ఖమ్మం"],
            "explanation_te": ""}, ensure_ascii=False)


class _BadLLM:
    def chat(self, system, user):
        return "not json at all"


class PaperFactoryProTest(unittest.TestCase):
    DIR = None

    @classmethod
    def setUpClass(cls):
        cls.DIR = config.DATA
        cls.TMP = Path(tempfile.mkdtemp())
        config.DATA = cls.TMP

    @classmethod
    def tearDownClass(cls):
        config.DATA = cls.DIR

    def _draft(self, name):
        p = self.TMP / name
        p.write_text(PAPER, encoding="utf-8")
        r = paperfactory.make_draft(p)
        self.assertTrue(r["ok"] and r["needs_translation"] == 2)
        return r["draft_id"]

    def test_ocr_needed_for_junk_pdf(self):
        p = self.TMP / "scanned.pdf"
        p.write_bytes(b"%PDF-1.4 this is not a real pdf at all")
        text, extractor = paperfactory.extract_text(p)
        self.assertEqual(text, "")
        self.assertEqual(extractor, "ocr-needed")
        r = paperfactory.make_draft(p)
        self.assertFalse(r["ok"])
        self.assertTrue(r["ocr_needed"])

    def test_translate_then_bank(self):
        did = self._draft("TSPSC 2020 Paper-I.txt")
        r = paperfactory.translate_draft(did, llm=_StubLLM())
        self.assertEqual(r["translated"], 2)
        self.assertEqual(r["still_pending"], 0)
        drafts = {d["id"]: d for d in paperfactory.list_drafts()}
        self.assertEqual(drafts[did]["needs_translation"], 0)
        g = paperfactory.go_bank(did)
        self.assertEqual(g["added"], 2)

    def test_bad_translator_keeps_parked(self):
        did = self._draft("APPSC 2019 Paper-II.txt")
        r = paperfactory.translate_draft(did, llm=_BadLLM())
        self.assertEqual(r["translated"], 0)
        self.assertEqual(r["still_pending"], 2)
        g = paperfactory.go_bank(did)
        self.assertEqual(g["added"], 0)
        self.assertEqual(g["translation_pending"], 2)

    def test_translate_guards(self):
        self.assertFalse(paperfactory.translate_draft("nope")["ok"])
        did = self._draft("SSC 2018 Paper-I.txt")
        paperfactory.reject_draft(did)
        self.assertFalse(
            paperfactory.translate_draft(did, llm=_StubLLM())["ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
