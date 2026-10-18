# -*- coding: utf-8 -*-
"""🚀 270X: No-VPS shared-host mode — Stateless wiring + signed claims.

Pins (probe-verified):
  • Registration validates district against the canonical AP/TS lists
    and coerces an unknown goal to "mixed" (260X accepted garbage).
  • Daily serving shuffles options per student and never leaks the
    answer index; grading maps DISPLAY -> ORIGINAL via the same seed.
  • record_answer anti-farm parity with portal._award: once per
    question — points/topics/answers cannot be farmed by replay.
  • Attempts: sections fold through syllabus.subject_of_topic, topic
    keys normalized trim+lower, answers tolerate int/str keys and
    values, attempt tokens are single-use (nonce).
  • Signed claims (typ="c", 7-day TTL): round-trip, kind filter,
    tamper rejection, garbage-state rejection.
  • progress_summary normalizes legacy mixed-case topic keys and is
    explicitly "verified": False (claims carry truth, tokens don't).
  • Dashboard wiring: st270 routes before the admin gate
    (1 GET view + register/answer/attempt/claims POSTs),
    registration UI toggle + su_stateless preference, golive
    No-VPS check, SW pin unchanged (studentup-v5).
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import stateless_client as sc  # noqa: E402

SECRET = "adv270-test-secret"


def _q(qid="X1", answer=2, topic="Algebra"):
    return {"id": qid, "channel": "BANKING", "topic": topic,
            "q_en": "?", "q_te": "?",
            "options_en": ["a", "b", "c", "d"],
            "options_te": ["a", "b", "c", "d"],
            "answer_index": answer, "source": "curated"}


class _SlBase(unittest.TestCase):
    def setUp(self):
        qs = [_q("X1", 2, "Algebra"),
              _q("X2", 0, "  Mensuration  "),
              _q("X3", 1, "Polity")]
        self._real = sc._bank
        sc._bank = lambda: qs
        self.tok, err = sc.register_student(
            "Adv270 Tester", "9849112700", "Guntur", "banking",
            secret=SECRET)
        assert self.tok, err

    def tearDown(self):
        sc._bank = self._real


class TestRegistration270(_SlBase):
    def test_valid_registration(self):
        view = sc.public_view(self.tok, secret=SECRET)
        self.assertEqual(view["profile"]["uid"], "w9849112700")
        self.assertEqual(view["profile"]["district"], "Guntur")

    def test_bad_district_rejected(self):
        tok, err = sc.register_student("Ab", "9849112701", "NoSuch",
                                       "railway", secret=SECRET)
        self.assertIsNone(tok)
        self.assertIn("district", err)

    def test_unknown_goal_coerced(self):
        tok, err = sc.register_student("Ab", "9849112702", "Guntur",
                                       "unknown-goal", secret=SECRET)
        self.assertIsNotNone(tok, err)
        self.assertEqual(sc.decode_token(tok, secret=SECRET)
                         ["profile"]["goal"], "mixed")


class TestServingGrading270(_SlBase):
    def _disp(self, q, seed):
        return sc._display(q, seed)[1]

    def test_daily_serving_no_answer_leak(self):
        quiz = sc.daily_quiz(self.tok, secret=SECRET,
                             today="2026-10-26")
        qs = quiz["questions"]
        self.assertIsNotNone(quiz)
        self.assertGreaterEqual(len(qs), 1)
        for item in qs:
            self.assertNotIn("answer_index", item)
            self.assertNotIn("answer", item)
            self.assertEqual(len(item["options"]), 4)

    def test_daily_display_grading(self):
        quiz = sc.daily_quiz(self.tok, secret=SECRET,
                             today="2026-10-26")
        it = quiz["questions"][0]
        q = [x for x in sc._bank() if str(x["id"]) == it["id"]][0]
        perm = self._disp(q, "w9849112700:2026-10-26:0")
        disp = perm.index(int(q["answer_index"]))
        nt, res = sc.record_answer(self.tok, it["id"], disp,
                                   secret=SECRET,
                                   today="2026-10-26",
                                   idx=it.get("i", 0))
        self.assertTrue(res["correct"])
        self.assertEqual(res["correct_display"], disp)

    def test_antifarm_replay(self):
        perm = self._disp(_q("X9", 1), "w9849112700:2026-10-26:0")
        disp = perm.index(1)
        real = sc._bank
        sc._bank = lambda: [_q("X9", 1)]
        try:
            tok, res = self.tok, None
            for _ in range(4):
                tok, res = sc.record_answer(
                    tok, "X9", disp, secret=SECRET,
                    today="2026-10-26", idx=0)
            st = sc.decode_token(tok, secret=SECRET)
            self.assertEqual(res["points"], 10)
            self.assertEqual(st["prog"]["answers"], 1)
            self.assertEqual(st["prog"]["topics"]["algebra"]["total"], 1)
        finally:
            sc._bank = real

    def test_attempt_sections_and_single_use(self):
        qs = [_q("X1", 2, "Algebra"), _q("X2", 0, "  Mensuration  ")]
        real = sc._bank
        sc._bank = lambda: qs
        try:
            atok, info = sc.start_attempt(self.tok, secret=SECRET)
            self.assertIsNotNone(atok)
            self.assertEqual(len(info["questions"]), 2)
            for item in info["questions"]:
                self.assertNotIn("answer_index", item)
            answers = {}
            for pos, item in enumerate(info["questions"]):
                q = [x for x in qs
                     if str(x["id"]) == str(item["id"])][0]
                perm = self._disp(q, f"sl-att:w9849112700:{pos}")
                answers[str(item["id"])] = perm.index(
                    int(q["answer_index"]))
            nt, sub = sc.submit_attempt(self.tok, atok, answers,
                                        secret=SECRET)
            self.assertTrue(sub["ok"], sub)
            self.assertEqual(sub["correct"], 2, sub)
            st = sc.decode_token(nt, secret=SECRET)
            self.assertEqual(st["prog"]["topics"]["mensuration"]
                             ["total"], 1)
            self.assertEqual(st["prog"]["topics"]["algebra"]
                             ["total"], 1)
            _n2, again = sc.submit_attempt(nt, atok, answers,
                                           secret=SECRET)
            self.assertFalse(again["ok"])
            self.assertIn("already submitted", again["error"])
        finally:
            sc._bank = real

    def test_attempt_int_keys_and_bad_values(self):
        qs = [_q("X1", 2)]
        real = sc._bank
        sc._bank = lambda: qs
        try:
            atok, info = sc.start_attempt(self.tok, secret=SECRET)
            perm = self._disp(qs[0], "sl-att:w9849112700:0")
            # int qid key + string pick
            _nt, sub = sc.submit_attempt(
                self.tok, atok,
                {"X1": str(perm.index(2))}, secret=SECRET)
            self.assertEqual(sub["correct"], 1, sub)
            atok2, _i = sc.start_attempt(self.tok, secret=SECRET)
            _n2, sub2 = sc.submit_attempt(
                self.tok, atok2, {"X1": "junk"}, secret=SECRET)
            self.assertEqual(sub2["correct"], 0, sub2)
        finally:
            sc._bank = real


class TestLegacyState270(unittest.TestCase):
    def test_legacy_int_qid_seen_and_mixed_case_topics(self):
        real = sc._bank
        sc._bank = lambda: [_q(42, 1)]
        try:
            tok, _ = sc.register_student("Ab", "9849112720", "Guntur",
                                         "banking", secret=SECRET)
            st = sc.decode_token(tok, secret=SECRET)
            st["prog"]["seen"] = [42]
            st["prog"]["topics"] = {"Algebra": {"total": 4,
                                                "correct": 1}}
            tok = sc.encode_token(st, secret=SECRET)
            perm = sc._display(_q(42, 1),
                               "w9849112720:2026-10-26:0")[1]
            tok, res = sc.record_answer(tok, 42, perm.index(1),
                                        secret=SECRET,
                                        today="2026-10-26", idx=0)
            self.assertTrue(res["already"])
            st2 = sc.decode_token(tok, secret=SECRET)
            self.assertEqual(st2["prog"]["answers"], 0)
            self.assertIn("42", st2["prog"]["seen"])
            ps = sc.progress_summary(tok, secret=SECRET)
            self.assertEqual(ps["weak_topics"][0]["topic"], "algebra")
        finally:
            sc._bank = real


class TestClaims270(_SlBase):
    def test_claim_round_trip(self):
        claim = sc.issue_claim(self.tok, "weekly_winner",
                               "Weekly Grand Test — rank 2",
                               secret=SECRET)
        self.assertIsNotNone(claim)
        v = sc.verify_claim(claim, secret=SECRET,
                            want_kind="weekly_winner")
        self.assertEqual(v["uid"], "w9849112700")
        self.assertEqual(v["claim"], "weekly_winner")

    def test_claim_kind_filter_and_garbage(self):
        claim = sc.issue_claim(self.tok, "milestone_100", "x",
                               secret=SECRET)
        self.assertIsNone(sc.verify_claim(
            claim, secret=SECRET, want_kind="weekly_winner"))
        self.assertIsNone(sc.issue_claim("garbage-token",
                                         "weekly_winner", "x",
                                         secret=SECRET))

    def test_claim_tamper_and_wrong_type(self):
        claim = sc.issue_claim(self.tok, "weekly_winner", "x",
                               secret=SECRET)
        bad = claim[:-4] + ("AAAA" if not claim.endswith("AAAA")
                            else "BBBB")
        self.assertIsNone(sc.verify_claim(bad, secret=SECRET))
        # a state token is not a claim
        self.assertIsNone(sc.verify_claim(self.tok, secret=SECRET))
        # claim cannot be used as state
        self.assertIsNone(sc.public_view(claim, secret=SECRET))

    def test_record_answer_already_flag(self):
        real = sc._bank
        sc._bank = lambda: [_q("F1", 1)]
        try:
            perm = sc._display(_q("F1", 1),
                               "w9849112700:2026-10-26:0")[1]
            tok, res1 = sc.record_answer(
                self.tok, "F1", perm.index(1), secret=SECRET,
                today="2026-10-26", idx=0)
            self.assertFalse(res1["already"])
            _t2, res2 = sc.record_answer(
                tok, "F1", perm.index(1), secret=SECRET,
                today="2026-10-26", idx=0)
            self.assertTrue(res2["already"])
            self.assertEqual(res2["points_gained"], 0)
        finally:
            sc._bank = real

    def test_progress_summary(self):
        ps = sc.progress_summary(self.tok, secret=SECRET)
        self.assertEqual(ps["uid"], "w9849112700")
        self.assertFalse(ps["verified"])
        claims = {"typ": "u", "uid": "w9849112709",
                  "profile": {"name": "Ab", "phone": "9849112709",
                              "uid": "w9849112709",
                              "district": "Guntur",
                              "goal": "banking"},
                  "prog": {"answers": 4, "correct": 1, "points": 10,
                           "streak": 1, "best_streak": 1,
                           "topics": {"Algebra": {"total": 4,
                                                  "correct": 1}},
                           "seen": [], "last_day": ""}}
        tok = sc.encode_token(claims, secret=SECRET)
        ps2 = sc.progress_summary(tok, secret=SECRET)
        self.assertEqual(ps2["weak_topics"][0]["topic"], "algebra")


class TestWiring270(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts"
                    / "dashboard_server.py").read_text(
                        encoding="utf-8")

    def test_claims_verify_route(self):
        i = self.dash.find('"/api/portal/st270/claims"')
        self.assertGreater(i, 0)
        postdef = self.dash.find("def _do_POST")
        deny = self.dash.rfind('if not self._authed():', postdef,
                               postdef + 60000)
        self.assertGreater(i, postdef)
        self.assertLess(i, deny)
        self.assertIn("verify_claim", self.dash[i:i + 700])

    def test_routes_before_gate(self):
        postdef = self.dash.find("def _do_POST")
        self.assertGreater(postdef, 0)
        # deny-by-default gate = the LAST 'unauthorized' gate in
        # _do_POST (earlier _authed() hits are per-route checks such
        # as harvest_run, not the gate)
        deny = self.dash.rfind(
            'if not self._authed():', postdef,
            postdef + 60000)
        self.assertGreater(deny, postdef)
        for route in ("/api/portal/st270/register",
                      "/api/portal/st270/answer",
                      "/api/portal/st270/attempt/start",
                      "/api/portal/st270/attempt/submit"):
            i = self.dash.find(f'"{route}"')
            self.assertGreater(i, postdef, route)
            self.assertLess(i, deny, route)

    def test_get_route(self):
        self.assertIn('"/api/portal/st270"', self.dash)
        self.assertIn("stoken", self.dash)

    def test_ui_toggle_and_storage(self):
        for s in ("r-stateless", "su_stateless", "loadStatelessHome",
                  "No-VPS mode", "localStorage.removeItem"
                  "('su_stateless')"):
            self.assertIn(s, self.dash)

    def test_golive_novps_check(self):
        i = self.dash.find("def _golive_checks")
        self.assertIn("No-VPS shared-host mode (270X)",
                      self.dash[i:i + 9000])

    def test_sw_pin_unchanged(self):
        self.assertIn("studentup-v5", self.dash)
        self.assertNotIn("studentup-v6", self.dash)


if __name__ == "__main__":
    unittest.main()
