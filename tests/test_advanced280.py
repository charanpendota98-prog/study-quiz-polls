# -*- coding: utf-8 -*-
"""🚀 280X: bank-health + answer-bias shield on EVERY poll surface,
CORS allowlist (F7 closure), golive bank-health visibility.

Probe-verified before pinning:
  • Raw bank (305 Q): position B holds 43% -> bias flag; 2 duplicate-
    option questions invalid; balance_options/poll_safe existed but
    were wired only into scheduled rounds — DM quiz, coach, arena,
    district war, challenge and ALL WhatsApp sends used raw order.
  • Dashboard sent `Access-Control-Allow-Origin: *` on every JSON
    response; no do_OPTIONS handler existed.
Pins: bankhealth math (bias/defects/duplicates/rebalance text
invariance), source wiring on every send path, the _cors_origin
contract (AST-exec, 160X pattern), golive check presence.
"""
import ast
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import bankhealth  # noqa: E402


def _q(i, ai=1, exam="POLICE", stem=None, opts=None, expl="because"):
    return {"id": f"T{i}", "exam": exam,
            "q_en": stem if stem is not None else f"Question number {i}?",
            "q_te": "", "options_en": opts or ["alpha", "beta", "gamma", "delta"],
            "options_te": [], "answer_index": ai,
            "explanation_en": expl, "source": "curated"}


def _slice(src, start_marker, end_marker=None):
    i = src.index(start_marker)
    j = src.index(end_marker, i) if end_marker else len(src)
    return src[i:j]


class TestBankHealth280(unittest.TestCase):
    def test_bias_detected_on_skewed_bank(self):
        qs = [_q(i, ai=1) for i in range(50)]
        flags = bankhealth.bias_flags(qs)
        self.assertTrue(flags)
        self.assertEqual(flags[0]["scope"], "ALL")
        self.assertEqual(flags[0]["top_position"], 1)
        self.assertEqual(flags[0]["top_share"], 1.0)

    def test_balanced_bank_has_no_flags(self):
        qs = [_q(i, ai=i % 4) for i in range(48)]
        self.assertEqual(bankhealth.bias_flags(qs), [])

    def test_small_sample_never_accused(self):
        qs = [_q(i, ai=0) for i in range(10)]
        self.assertEqual(bankhealth.bias_flags(qs), [])

    def test_per_group_bias_flag(self):
        qs = ([_q(i, ai=2, exam="SSC") for i in range(45)]
              + [_q(100 + i, ai=i % 4, exam="POLICE") for i in range(44)])
        scopes = {f["scope"] for f in bankhealth.bias_flags(qs)}
        self.assertIn("SSC", scopes)
        self.assertNotIn("POLICE", scopes)

    def test_defects_and_duplicates(self):
        qs = [_q(1, ai=9), _q(2, opts=["x", "x"], ai=0),
              _q(3, stem="Same stem?"), _q(4, stem="Same stem?"),
              _q(5, expl="")]
        rep = bankhealth.bank_health_report(qs)
        self.assertEqual(rep["total"], 5)
        self.assertIn("T1", rep["invalid"])          # bad answer index
        self.assertIn("T2", rep["invalid"])          # duplicate options
        self.assertEqual(rep["duplicates"]["stems"], 1)
        self.assertEqual(rep["missing_explanation"], 1)
        self.assertFalse(rep["ok"])

    def test_pyq_share_is_honest(self):
        qs = [_q(i) for i in range(4)]
        qs[0]["source"] = "pyq"
        rep = bankhealth.bank_health_report(qs)
        self.assertEqual(rep["pyq"], {"count": 1, "share": 0.25})

    def test_rebalance_preserves_correct_text(self):
        qs = [_q(i, ai=1) for i in range(30)]
        out = bankhealth.rebalance_bank(qs)
        for orig, new in zip(qs, out):
            self.assertEqual(
                new["options_en"][new["answer_index"]],
                orig["options_en"][orig["answer_index"]])
            self.assertEqual(orig["answer_index"], 1)   # input untouched

    def test_rebalance_breaks_the_bias(self):
        qs = [_q(i, ai=1) for i in range(200)]
        out = bankhealth.rebalance_bank(qs)
        dist = bankhealth.position_distribution(out)
        self.assertLessEqual(max(dist.values()) / 200, 0.45)

    def test_defective_questions_pass_through_untouched(self):
        bad = _q(1, ai=9)
        out = bankhealth.rebalance_bank([bad])
        self.assertEqual(out[0]["answer_index"], 9)


class TestSendShieldWiring280(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = (ROOT / "scripts/core/engine.py").read_text("utf-8")
        cls.bot = (ROOT / "scripts/bot.py").read_text("utf-8")
        cls.auto = (ROOT / "scripts/core/autopilot.py").read_text("utf-8")
        cls.arena = (ROOT / "scripts/core/arena.py").read_text("utf-8")
        cls.war = (ROOT / "scripts/core/districtwar.py").read_text("utf-8")
        cls.wa = (ROOT / "scripts/core/whatsapp_pipeline.py").read_text("utf-8")

    def test_engine_channel_and_mirror_shielded(self):
        body = _slice(self.engine, "def send_quiz", "def _send_channel_question")
        self.assertIn("poll_safe(q, seed=str(channel_key))", body)
        self.assertLess(body.index("poll_safe"),
                        body.index("res = self.tg.send_quiz("))
        mirror = _slice(self.engine, "def _mirror_to_members", "def _dm_round_cards")
        self.assertIn("poll_safe(q, seed=str(round_id))", mirror)

    def test_engine_reaction_branch_shielded(self):
        body = _slice(self.engine, "def _send_channel_question",
                      "def _fmt_min")
        self.assertIn("poll_safe", body)
        self.assertLess(body.index("poll_safe"),
                        body.index("build_reaction_text"))

    def test_bot_dm_and_challenge_shielded(self):
        body = _slice(self.bot, "def send_quiz_to", "def _step_buttons")
        self.assertIn('poll_safe(q, seed=f"dm:{chat_id}")', body)
        chal = _slice(self.bot, "def _start_challenge", "def _me_username")
        self.assertIn('poll_safe(q, seed=f"ch:{uid}")', chal)
        self.assertLess(chal.index("poll_safe"),
                        chal.index('self.tg._call("sendPoll"'))

    def test_coach_arena_war_shielded(self):
        self.assertIn('poll_safe(q, seed=f"coach:{uid}")', self.auto)
        room = _slice(self.arena, "def room_start", "def tick")
        self.assertIn("poll_safe", room)
        war = _slice(self.war, "def start_war", "def _open_question")
        self.assertIn("poll_safe", war)

    def test_whatsapp_delivery_shielded_once_up_front(self):
        body = _slice(self.wa, "def deliver_whatsapp_question",
                      "def _bridge_urls")
        self.assertIn('q = poll_safe(q, seed=f"wa:{jid}")', body)
        i = body.index("q = poll_safe")
        self.assertLess(i, body.index("build_reaction_text(q"))
        self.assertLess(i, body.index("build_native_poll_payload(q"))
        self.assertLess(i, body.index("build_answer_key_post(q"))
        self.assertLess(i, body.index('"correct": int(q.get("answer_index", 0))'))


class TestCors280(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "scripts/dashboard_server.py").read_text("utf-8")
        tree = ast.parse(cls.src)
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "_cors_origin")
        cls.ns = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]),
                     "<cors280>", "exec"), cls.ns)

    def test_wildcard_gone_and_options_handler_present(self):
        self.assertNotIn('Access-Control-Allow-Origin", "*"', self.src)
        self.assertIn("def do_OPTIONS", self.src)

    def test_empty_and_evil_origins_rejected(self):
        f = self.ns["_cors_origin"]
        self.assertEqual(f(""), "")
        self.assertEqual(f("https://evil.example.com"), "")
        self.assertEqual(f("not a url"), "")

    def test_localhost_dev_origin_allowed(self):
        f = self.ns["_cors_origin"]
        self.assertEqual(f("http://localhost:5000"), "http://localhost:5000")
        self.assertEqual(f("http://127.0.0.1:5000"), "http://127.0.0.1:5000")

    def test_configured_public_origin_allowed(self):
        f = self.ns["_cors_origin"]
        old = os.environ.get("PUBLIC_BASE_URL")
        os.environ["PUBLIC_BASE_URL"] = "https://quiz.studentup.in"
        try:
            self.assertEqual(f("https://quiz.studentup.in"),
                             "https://quiz.studentup.in")
            self.assertEqual(f("https://quiz.studentup.in.evil.com"), "")
        finally:
            if old is None:
                os.environ.pop("PUBLIC_BASE_URL", None)
            else:
                os.environ["PUBLIC_BASE_URL"] = old


class TestGoliveBankHealth280(unittest.TestCase):
    def test_golive_reports_bank_health_guarded(self):
        src = (ROOT / "scripts/dashboard_server.py").read_text("utf-8")
        body = _slice(src, "def _golive_checks", "def _public_base")
        self.assertIn("Bank health (280X)", body)
        self.assertIn("bankhealth", body)
        self.assertIn("summarize", body)


if __name__ == "__main__":
    unittest.main()
