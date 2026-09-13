import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from core import verifier

GOOD = {"id": "t1", "source": "scraped", "channel": "SSC",
        "q_en": "What is 25% of 200?", "q_te": "200 లో 25% ఎంత?",
        "options_en": ["25", "50", "75", "100"], "options_te": ["25", "50", "75", "100"],
        "answer_index": 1}

class FakeLLM:
    def __init__(self, answers, faithful=True):
        self.answers = list(answers); self.faithful = faithful
    def available(self): return True
    def chat(self, system, user):
        if "audit Telugu" in system:
            return '{"faithful": %s, "issues": ["x"], "fixed_q_te": null, "fixed_options_te": null}' % ("true" if self.faithful else "false")
        a = self.answers.pop(0)
        return '{"answer_index": %d, "confidence": 0.95, "reason": "calc", "flags": []}' % a

class TestVerifier(unittest.TestCase):
    def test_structural_gate(self):
        self.assertEqual(verifier.structural_issues(GOOD), [])
        bad = dict(GOOD, options_en=["a", "a", "b", "c"], q_te="", answer_index=9)
        self.assertIn("duplicate_options", verifier.structural_issues(bad))
        self.assertIn("no_telugu", verifier.structural_issues(bad))
        self.assertIn("bad_answer_index", verifier.structural_issues(bad))

    def test_no_key_pending(self):
        self.assertEqual(verifier.verify_question(GOOD, llm=None)["status"], "pending")

    def test_agree_ok(self):
        self.assertEqual(verifier.verify_question(GOOD, FakeLLM([1]))["status"], "ok")

    def test_two_models_disagree_with_us_fixes_scraped(self):
        v = verifier.verify_question(GOOD, FakeLLM([2, 2]))
        self.assertEqual(v["status"], "fixed"); self.assertEqual(v["patch"]["answer_index"], 2)

    def test_pyq_never_auto_fixed_only_quarantined(self):
        v = verifier.verify_question(dict(GOOD, source="pyq"), FakeLLM([2, 2]))
        self.assertEqual(v["status"], "quarantine")

    def test_unfaithful_telugu_quarantines(self):
        v = verifier.verify_question(GOOD, FakeLLM([1], faithful=False))
        self.assertEqual(v["status"], "quarantine")

    def test_postable_rules(self):
        self.assertTrue(verifier.postable(dict(GOOD, source="pyq"), strict=True))
        self.assertFalse(verifier.postable(GOOD, strict=True))     # unverified scraped
        self.assertTrue(verifier.postable(GOOD, strict=False))
        self.assertFalse(verifier.postable(dict(GOOD, q_te=""), strict=False))

if __name__ == "__main__":
    unittest.main()
