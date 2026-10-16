#!/usr/bin/env python3
"""🏆 WhatsApp Group Winners — vote-tracked top-5 @mentions + answer key.

Owner format: ONE message per group after a round — full answer key,
tie-aware top-5 (@number mentions), tie overflow line, players +
accuracy, Hall of Fame. Bridge (Baileys) collects real poll votes via
messages.upsert → /poll-results; the tally/render/HoF logic is pure and
tested here, bridge changes are textual + node-checked. whatsapp_pipeline
is imported lazily (module-level import has scheduler side effects).
Run: python3 -m unittest discover -s tests -p "test_wa_winners.py"
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

POLLS = [{"poll_id": f"P{i}", "qid": f"Q{i}", "correct": c}
         for i, c in enumerate([1, 1, 2, 0, 0], 1)]     # key: 1.B 2.B 3.C 4.A 5.A


def _results(votes):
    """votes: {voter_jid: [chosen idx per question]} → bridge-shaped map."""
    out = {}
    for pi, p in enumerate(POLLS):
        voters = {j: ch[pi] for j, ch in votes.items() if ch[pi] is not None}
        out[p["poll_id"]] = {"ok": True, "voters": voters}
    return out


class TestTallyRender(unittest.TestCase):
    def _wp(self):
        from core import whatsapp_pipeline as wp
        return wp

    def test_tally_and_owner_format(self):
        wp = self._wp()
        A, B, C, D = ("911111111111@s.whatsapp.net", "912222222222@s.whatsapp.net",
                      "913333333333@s.whatsapp.net", "914444444444@s.whatsapp.net")
        E, F, G = ("915555555555@s.whatsapp.net", "916666666666@s.whatsapp.net",
                   "917777777777@s.whatsapp.net")
        votes = {A: [1, 1, 2, 1, 1],      # 3 correct
                 B: [1, 1, 0, 1, 1],      # 2
                 C: [1, 0, 2, 1, 1],      # 2
                 D: [0, 1, 2, 1, 1],      # 2
                 E: [1, 1, 1, 1, 1],      # 2
                 F: [1, 0, 0, 0, 1],      # 2 (6th player — tie overflow)
                 G: [0, 0, 1, 1, 1]}      # 0 correct
        tally = wp.tally_wa_round(POLLS, _results(votes))
        self.assertEqual(tally["players"], 7)
        self.assertEqual(tally["standings"][0][0], A)
        msg = wp.render_wa_winners("Paper PDF Test", POLLS, tally)
        self.assertIn("✅ *Answer Key — Paper PDF Test*", msg)
        self.assertIn("*1.B 2.B 3.C 4.A 5.A*", msg)
        self.assertIn("🥇 @911111111111 — 3/5", msg)
        self.assertEqual(msg.count("🥈 @"), 4)          # 4 shown at rank 2
        self.assertIn("🤝 మరో 1 మంది కూడా 2/5 score!", msg)
        self.assertIn("👥 7 players", msg)
        self.assertIn("📤 *Share with friends!*", msg)

    def test_channel_never_gets_winners(self):
        wp = self._wp()
        out = wp.send_wa_winners("", {"jid": "120@newsletter", "name": "Ch"},
                                 POLLS, "X", sleep_fn=lambda s: None)
        self.assertFalse(out["sent"])                   # mentions impossible
        self.assertEqual(out.get("skipped"), "channel")

    def test_no_votes_no_message(self):
        wp = self._wp()
        self.assertEqual(wp.tally_wa_round(POLLS, {})["players"], 0)
        out = wp.send_wa_winners("", {"jid": "1@g.us", "name": "G"}, POLLS,
                                 "X", sleep_fn=lambda s: None)
        self.assertFalse(out["sent"])                   # bridge down → skip


class TestCaptureAndSend(unittest.TestCase):
    def test_poll_id_capture_and_collect(self):
        from core import whatsapp_pipeline as wp
        orig_bridge, orig_disp = wp._bridge_call, wp._dispatch_raw

        def fake_bridge(path, payload=None, timeout=40, base_url=None, method=None):
            return {"ok": True, "sent": ["poll"], "poll_id": "PID42"}

        wp._bridge_call = fake_bridge
        try:
            ok, _ = wp._dispatch_raw("", "120@g.us", "t",
                                     poll={"name": "q", "options": ["a", "b"]})
            self.assertTrue(ok)
            self.assertEqual(wp._LAST_WA_POLL["120@g.us"], "PID42")

            def fake_disp(gw, jid, text, attachment="", poll=None,
                          bridge_url=None, mentions=None):
                wp._LAST_WA_POLL[str(jid)] = "PID42"
                return True, "ok"

            wp._dispatch_raw = fake_disp
            collect = []
            q = {"id": "WQ1", "channel": "SSC", "topic": "Polity",
                 "q_en": "Capital?", "q_te": "", "answer_index": 1,
                 "options_en": ["A", "B", "C", "D"], "options_te": [],
                 "explanation_en": ""}
            out = wp.deliver_whatsapp_question("", "120@g.us", q, "SSC",
                                               two_phase_answer=False,
                                               collect=collect)
            self.assertTrue(out["sent_poll"])
            self.assertEqual(collect, [{"poll_id": "PID42", "qid": "WQ1",
                                        "correct": 1}])
        finally:
            wp._bridge_call, wp._dispatch_raw = orig_bridge, orig_disp
            wp._LAST_WA_POLL.pop("120@g.us", None)

    def test_send_winners_mentions_top5(self):
        from core import whatsapp_pipeline as wp
        tmp = Path(tempfile.mkdtemp())
        orig = (wp._bridge_call, wp._dispatch_raw, wp.WA_HOF_FILE)
        sent = {}

        def fake_bridge(path, payload=None, timeout=40, base_url=None, method=None):
            pid = path.split("poll=")[-1]
            return {"ok": True, "voters": {"919999999999@s.whatsapp.net": 1}}

        def fake_disp(gw, jid, text, attachment="", poll=None,
                      bridge_url=None, mentions=None):
            sent.update({"text": text, "mentions": mentions})
            return True, "ok"

        wp._bridge_call, wp._dispatch_raw = fake_bridge, fake_disp
        wp.WA_HOF_FILE = tmp / "hof.json"
        try:
            out = wp.send_wa_winners("", {"jid": "1@g.us", "name": "G"},
                                     [{"poll_id": "P1", "correct": 1}],
                                     "Demo", sleep_fn=lambda s: None)
            self.assertTrue(out["sent"])
            self.assertEqual(sent["mentions"], ["919999999999@s.whatsapp.net"])
            self.assertIn("🥇 @919999999999 — 1/1", sent["text"])
            hof = wp.wa_hall_of_fame(1)
            self.assertEqual(hof[0]["phone"], "919999999999")
            self.assertEqual(hof[0]["quizzes"], 1)
        finally:
            wp._bridge_call, wp._dispatch_raw, wp.WA_HOF_FILE = orig


class TestBridgeWiring(unittest.TestCase):
    def test_bridge_tracks_votes_and_mentions(self):
        src = (ROOT / "gateway" / "wa_bridge.js").read_text()
        self.assertIn("getAggregateVotesInPollMessage", src)
        self.assertIn("pollUpdateMessage", src)
        self.assertIn("'/poll-results'", src)
        self.assertIn("poll_id: r.pollId", src)
        self.assertIn("mentionsOf", src)


if __name__ == "__main__":
    unittest.main()
