"""390X — Bot Paper Factory: Telegram upload -> draft -> buttons.

Locks: upload sanitisation (no traversal, no clobber), callback
shape/length, action dispatch honoring the paperfactory gates
(translate-then-bank; reject final; invalid actions refused).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import config, paperbot  # noqa: E402

PAPER = ("1. The HCF of 12 and 18 is (a) 2 (b) 3 (c) 6 (d) 9\n"
         "Ans: (c)\n"
         "2. Capital of Telangana? (a) Warangal (b) Hyderabad "
         "(c) Nizamabad (d) Khammam\nAnswer: b\n")


class _StubLLM:
    def chat(self, system, user):
        payload = json.loads(user)
        q = payload["q"]
        if "HCF" in q:
            return json.dumps({
                "q_en": q, "q_te": "12 మరియు 18 యొక్క గ.సా.గు ఎంత?",
                "options_en": payload["options"],
                "options_te": ["2", "3", "6", "9"],
                "explanation_te": ""}, ensure_ascii=False)
        return json.dumps({
            "q_en": q, "q_te": "తెలంగాణ రాజధాని ఏది?",
            "options_en": payload["options"],
            "options_te": ["వరంగల్", "హైదరాబాద్", "నిజామాబాద్", "ఖమ్మం"],
            "explanation_te": ""}, ensure_ascii=False)


class BotPaperFactoryTest(unittest.TestCase):
    DIR = None

    @classmethod
    def setUpClass(cls):
        cls.DIR = config.DATA
        cls.TMP = Path(tempfile.mkdtemp())
        config.DATA = cls.TMP

    @classmethod
    def tearDownClass(cls):
        config.DATA = cls.DIR

    def test_save_incoming_sanitizes(self):
        p = paperbot.save_incoming("../../evil plan.txt", b"x")
        self.assertEqual(p.parent.name, "pdf_inbox")
        self.assertNotIn("..", p.name)
        p2 = paperbot.save_incoming("../../evil plan.txt", b"y")
        self.assertNotEqual(p, p2)          # never clobbers
        self.assertTrue(paperbot.is_paper_file("a.PDF"))
        self.assertFalse(paperbot.is_paper_file("a.docx"))

    def test_upload_to_bank_flow(self):
        text, buttons = paperbot.make_from_upload(
            "TSPSC 2022 Paper-I.txt", PAPER.encode())
        self.assertIn("Paper Draft Ready", text)
        self.assertIn("pending", text)
        cbs = [cb for row in buttons for _, cb in row]
        self.assertTrue(all(c.startswith("pf:") for c in cbs))
        self.assertTrue(all(len(c) <= 64 for c in cbs))
        did = cbs[0].split(":", 2)[2]
        out = paperbot.handle_action("tr", did, llm=_StubLLM())
        self.assertIn("2 ready", out)
        out = paperbot.handle_action("bank", did)
        self.assertIn("2 questions", out)
        out = paperbot.handle_action("bank", did)
        self.assertIn("⚠️", out)             # double-bank refused

    def test_reject_and_invalid(self):
        text, buttons = paperbot.make_from_upload(
            "APPSC 2021 Paper-II.txt", PAPER.encode())
        did = buttons[0][0][1].split(":", 2)[2]
        self.assertIn("rejected", paperbot.handle_action("rej", did))
        self.assertIn("⚠️", paperbot.handle_action("bank", did))
        self.assertIn("⚠️", paperbot.handle_action("hack", did))
        self.assertIn("⚠️", paperbot.handle_action("bank", ""))

    def test_junk_pdf_honest_error(self):
        text, buttons = paperbot.make_from_upload(
            "scan.pdf", b"%PDF-1.4 not a real pdf")
        self.assertIn("⚠️", text)
        self.assertIsNone(buttons)

    def test_list_text(self):
        paperbot.make_from_upload("POLICE 2020 Paper-I.txt",
                                  PAPER.encode())
        self.assertIn("Paper Drafts", paperbot.list_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
