#!/usr/bin/env python3
"""Messaging v4 tests — Telegram + WhatsApp made perfect/honest.

Telegram: urllib HTTPError fatal-vs-retry handling, send_quiz validation
clamps + centralised poll sends.
WhatsApp: two-phase answer key (question first, key after the thinking
window, never an orphan key), bridge poll/JID validation, bridge
localhost-binding + optional token auth, and the legacy broadcaster's
honest no-gateway mode (no fake "simulated OK").
Run from repo root: python3 -m unittest tests.test_messaging_v4
"""
import io
import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core.telegram import Telegram, TelegramError  # noqa: E402

# NOTE: whatsapp_pipeline / whatsapp_bot are imported LAZILY inside the
# test classes below — importing them at module top pulls channel_router,
# which merges data/custom_channels.json into the global config and
# pollutes other test modules (PUBLIC_CHANNELS) during unittest discovery.


ZW = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)


def clean(s):
    return " ".join((s or "").translate(ZW).split())


def sample_q(**kw):
    q = {
        "id": "q1", "channel": "SSC",
        "q_en": "Capital of India?", "q_te": "భారత రాజధాని?",
        "options_en": ["Delhi", "Mumbai", "Chennai", "Kolkata"],
        "options_te": ["ఢిల్లీ", "ముంబై", "చెన్నై", "కోల్‌కతా"],
        "answer_index": 0,
        "explanation_en": "Delhi is the capital.",
        "explanation_te": "ఢిల్లీ రాజధాని.",
    }
    q.update(kw)
    return q


class TestTelegramHttpErrors(unittest.TestCase):
    """Stdlib urllib transport must honour fatal vs retry semantics."""

    def _client(self):
        tg = Telegram(token="123:abc", dry=False)
        tg.session = None  # force urllib path
        return tg

    def _http_error(self, code, payload):
        body = json.dumps(payload).encode()
        return urllib.error.HTTPError(
            "https://api.telegram.org/x", code, "err", None, io.BytesIO(body))

    def test_fatal_400_not_retried(self):
        tg = self._client()
        calls = []

        def boom(req, timeout=0):
            calls.append(1)
            raise self._http_error(400, {"ok": False,
                                         "description": "Bad Request: chat not found"})

        with mock.patch("urllib.request.urlopen", boom):
            with self.assertRaises(TelegramError):
                tg._call("sendMessage", {"chat_id": 1, "text": "hi"})
        self.assertEqual(len(calls), 1)  # fatal => exactly one attempt

    def test_429_retry_after_then_success(self):
        tg = self._client()
        seq = [
            self._http_error(429, {"ok": False,
                                   "description": "Too Many Requests",
                                   "parameters": {"retry_after": 1}}),
            None,
        ]

        class Resp:
            status = 200

            def read(self):
                return b'{"ok": true, "result": {"message_id": 7}}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=0):
            item = seq.pop(0)
            if item is not None:
                raise item
            return Resp()

        with mock.patch("urllib.request.urlopen", fake), \
                mock.patch("time.sleep") as sleep:
            out = tg._call("sendMessage", {"chat_id": 1, "text": "hi"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["result"]["message_id"], 7)
        sleep.assert_called()  # retry_after honoured (capped wait)


class TestTelegramSendQuiz(unittest.TestCase):
    def _capture(self):
        tg = Telegram(token="x", dry=False)
        seen = {}
        tg._call = lambda m, p, **k: seen.update(payload=p) or {"ok": True, "result": {}}
        return tg, seen

    def test_clamps_to_telegram_limits(self):
        tg, seen = self._capture()
        tg.send_quiz(1, "Q" * 400, ["A" * 150, "b", "c"], 2)
        p = seen["payload"]
        self.assertLessEqual(len(p["question"]), 300)
        self.assertTrue(all(len(o["text"]) <= 100 for o in p["options"]))
        self.assertEqual(p["correct_option_id"], 2)

    def test_bad_correct_index_raises(self):
        tg, _ = self._capture()
        with self.assertRaises(TelegramError):
            tg.send_quiz(1, "q", ["a", "b"], 5)
        with self.assertRaises(TelegramError):
            tg.send_quiz(1, "q", ["only"], 0)

    def test_anonymous_flag(self):
        tg, seen = self._capture()
        tg.send_quiz(1, "q", ["a", "b"], 0)
        self.assertTrue(seen["payload"]["is_anonymous"])
        tg.send_quiz(1, "q", ["a", "b"], 0, is_anonymous=False)
        self.assertFalse(seen["payload"]["is_anonymous"])


class TestWhatsAppTwoPhase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global wap
        from core import whatsapp_pipeline as _wap
        globals()["wap"] = _wap

    def test_key_follows_question_after_window(self):
        sent = []
        sleeps = []

        def fake_dispatch(gw, jid, text, attachment="", poll=None):
            sent.append({"text": text, "poll": poll})
            return True, "ok"

        with mock.patch.object(wap, "_dispatch_raw", fake_dispatch):
            out = wap.deliver_whatsapp_question(
                "", "123@g.us", sample_q(), "SSC", answer_delay_sec=45,
                sleep_fn=sleeps.append)
        self.assertTrue(out["sent_poll"])
        self.assertTrue(out["sent_key"])
        self.assertEqual(sleeps, [45.0])
        self.assertEqual(len(sent), 2)
        self.assertIsNotNone(sent[0]["poll"])           # phase 1 = native poll
        self.assertIsNone(sent[1]["poll"])              # phase 2 = text key
        self.assertIn("Correct Option", clean(sent[1]["text"]))
        # question message promises the key, key itself carries the answer
        self.assertIn("45", clean(sent[0]["text"]))

    def test_no_orphan_key_when_question_fails(self):
        calls = []

        def failing(gw, jid, text, attachment="", poll=None):
            calls.append(text)
            return False, "NOT SENT"

        with mock.patch.object(wap, "_dispatch_raw", failing):
            out = wap.deliver_whatsapp_question(
                "", "123@g.us", sample_q(), "SSC",
                sleep_fn=lambda s: None)
        self.assertFalse(out["sent_poll"])
        self.assertFalse(out["sent_key"])

    def test_two_phase_disabled_sends_only_poll(self):
        sent = []

        def fake_dispatch(gw, jid, text, attachment="", poll=None):
            sent.append(poll)
            return True, "ok"

        with mock.patch.object(wap, "_dispatch_raw", fake_dispatch):
            out = wap.deliver_whatsapp_question(
                "", "123@g.us", sample_q(), "SSC", two_phase_answer=False)
        self.assertTrue(out["sent_poll"])
        self.assertFalse(out["sent_key"])
        self.assertEqual(len(sent), 1)

    def test_poll_fallback_to_text_still_gets_key(self):
        kinds = []

        def dispatch(gw, jid, text, attachment="", poll=None):
            kinds.append("poll" if poll else "text")
            if poll:
                return False, "poll rejected"
            return True, "ok"

        with mock.patch.object(wap, "_dispatch_raw", dispatch):
            out = wap.deliver_whatsapp_question(
                "", "123@g.us", sample_q(), "SSC", sleep_fn=lambda s: None)
        self.assertTrue(out["sent_poll"])
        self.assertTrue(out["sent_key"])
        self.assertEqual(kinds, ["poll", "text", "text"])


class TestLegacyWhatsAppBotHonesty(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global wab
        from core import whatsapp_bot as _wab
        globals()["wab"] = _wab

    def test_no_gateway_means_not_sent(self):
        reg = {"groups": [{"id": "g1", "name": "G", "jid": "1@g.us",
                           "category": "SSC", "active": True}],
               "gateway_url": ""}
        with mock.patch.object(wab, "load_wa_registry", lambda: reg):
            out = wab.broadcast()
        self.assertFalse(out["ok"])
        self.assertEqual(out["sent"], 0)
        self.assertIn("NOT SENT", out["log"])

    def test_question_text_hides_answer_key_follows(self):
        text = wab.build_wa_poll_text(sample_q(), "G", "SSC")
        self.assertNotIn("Correct Answer", clean(text))
        key = wab.build_wa_answer_text(sample_q(), "SSC")
        self.assertIn("Correct Answer", clean(key))
        self.assertIn("Option *A*", clean(key))


class TestBridgeSource(unittest.TestCase):
    SRC = (ROOT / "gateway" / "wa_bridge.js").read_text()

    def test_node_syntax(self):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("node not available")
        r = subprocess.run(["node", "--check", str(ROOT / "gateway" / "wa_bridge.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_localhost_default_and_token_auth(self):
        self.assertIn("WA_BRIDGE_HOST || '127.0.0.1'", self.SRC)
        self.assertIn("WA_BRIDGE_TOKEN", self.SRC)
        self.assertIn("x-bridge-token", self.SRC)
        self.assertIn("server.listen(PORT, HOST", self.SRC)

    def test_poll_dedupe_and_jid_validation(self):
        self.assertIn("poll needs >=2 unique options", self.SRC)
        self.assertIn("invalid WhatsApp jid", self.SRC)


if __name__ == "__main__":
    unittest.main()
