#!/usr/bin/env python3
"""👍 Emoji text-polls ONLY for WhatsApp Channel (owner rule, final).

WhatsApp Channels (@newsletter) have no direct poll option, so channel
targets get a 👍❤️😂😮 emoji TEXT poll (+ honest answer key, no fake %).
WhatsApp groups keep DIRECT native polls; Telegram keeps direct polls.
whatsapp_pipeline is imported lazily — importing it at module level has
scheduler side effects (known test-pollution trap).
Run: python3 -m unittest discover -s tests -p "test_whatsapp_channel.py"
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

Q = {"id": "WQ1", "channel": "SSC", "topic": "Polity",
     "q_en": "Capital of India?", "q_te": "భారత రాజధాని?",
     "options_en": ["Delhi", "Mumbai", "Chennai", "Kolkata"],
     "options_te": ["ఢిల్లీ", "ముంబై", "చెన్నై", "కోలకాతా"],
     "answer_index": 0, "explanation_en": "Delhi is the capital."}
CHANNEL_JID = "120363025555777001@newsletter"
GROUP_JID = "120363012345678901@g.us"


def _capture_deliver(jid):
    from core import whatsapp_pipeline as wp
    calls = []
    orig = wp._dispatch_raw

    def fake(gateway_url, j, text, attachment="", poll=None, bridge_url=None):
        calls.append({"jid": j, "text": text, "poll": poll})
        return True, "✅ FAKE SEND"

    wp._dispatch_raw = fake
    try:
        out = wp.deliver_whatsapp_question(
            "", jid, dict(Q), "SSC", q_index=1, total_q=1,
            english_first=False, two_phase_answer=True,
            answer_delay_sec=0, sleep_fn=lambda s: None)
    finally:
        wp._dispatch_raw = orig
    return out, calls


class TestWaChannel(unittest.TestCase):
    def test_is_wa_channel(self):
        from core import whatsapp_pipeline as wp
        self.assertTrue(wp.is_wa_channel(CHANNEL_JID))
        self.assertFalse(wp.is_wa_channel(GROUP_JID))
        self.assertFalse(wp.is_wa_channel(""))
        self.assertFalse(wp.is_wa_channel(None))

    def test_channel_gets_emoji_text_poll(self):
        out, calls = _capture_deliver(CHANNEL_JID)
        self.assertTrue(out["sent_poll"])
        self.assertEqual(len(calls), 2)               # question + answer key
        first = calls[0]
        self.assertIsNone(first["poll"])              # NO native poll to channel
        for e in ["👍", "❤️", "😂", "😮"]:
            self.assertIn(e, first["text"])
        self.assertIn("Capital of India?", first["text"])
        self.assertTrue(out["sent_key"])
        self.assertIn("Delhi", calls[1]["text"])      # honest key, no fake %

    def test_group_keeps_direct_native_poll(self):
        out, calls = _capture_deliver(GROUP_JID)
        self.assertTrue(out["sent_poll"])
        self.assertIsNotNone(calls[0]["poll"])        # direct tappable poll
        self.assertEqual(len(calls[0]["poll"]["options"]), 4)

    def test_bridge_and_dashboard_wiring(self):
        bridge = (ROOT / "gateway" / "wa_bridge.js").read_text()
        self.assertIn("@newsletter", bridge)
        self.assertIn("wantPoll", bridge)             # poll dropped for channels
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("@newsletter", dash)            # owner can add channel JID


if __name__ == "__main__":
    unittest.main()
