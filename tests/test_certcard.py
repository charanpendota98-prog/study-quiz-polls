#!/usr/bin/env python3
"""🏅 Winners Certificate image — renderer, WA image send, TG wiring.

The PNG itself is really rendered (Pillow + bundled Noto Sans Telugu, so
student names never become tofu boxes); WA winners go as ONE image
message (caption = winners text + real @mentions) with a plain-text
fallback; Telegram channel rounds post the same certificate with names.
whatsapp_pipeline imports lazily (scheduler side effects at module level).
Run: python3 -m unittest discover -s tests -p "test_certcard.py"
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import certcard                              # noqa: E402

STANDINGS = [("u1", 5, 5), ("u2", 4, 5), ("u3", 4, 5), ("u4", 2, 5)]
NAMES = {"u1": "అనిత రావు", "u2": "Rajesh Kumar", "u3": "sravani", "u4": "Venkatesh"}


class TestRender(unittest.TestCase):
    def test_real_png_with_telugu_names(self):
        rows = certcard.rows_from_tally(STANDINGS, 5, lambda u: NAMES[u])
        self.assertEqual([r["rank"] for r in rows], [1, 2, 2, 4])   # ties
        png = certcard.render_certificate(
            "WINNERS CERTIFICATE", "Demo · SSC", rows,
            footer="Players: 9 · Accuracy: 60%")
        self.assertIsNotNone(png)
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertGreater(len(png), 8000)

    def test_empty_rows_still_renders(self):
        png = certcard.render_certificate("WINNERS CERTIFICATE", "Demo", [])
        self.assertTrue(png.startswith(b"\x89PNG"))


class TestWaCertSend(unittest.TestCase):
    def _run(self, render_ret):
        from core import whatsapp_pipeline as wp
        tmp = Path(tempfile.mkdtemp())
        orig = (wp._bridge_call, wp._dispatch_raw, wp.WA_HOF_FILE,
                certcard.render_certificate)
        sent = {}

        def fake_bridge(path, payload=None, timeout=40, base_url=None, method=None):
            return {"ok": True, "voters": {"919999999999@s.whatsapp.net": 1}}

        def fake_disp(gw, jid, text, attachment="", poll=None,
                      bridge_url=None, mentions=None):
            sent.update({"text": text, "attachment": attachment,
                         "mentions": mentions})
            return True, "ok"

        wp._bridge_call, wp._dispatch_raw = fake_bridge, fake_disp
        wp.WA_HOF_FILE = tmp / "hof.json"
        certcard.render_certificate = lambda *a, **k: render_ret
        try:
            out = wp.send_wa_winners("", {"jid": "1@g.us", "name": "G"},
                                     [{"poll_id": "P1", "correct": 1}],
                                     "Demo", sleep_fn=lambda s: None)
        finally:
            (wp._bridge_call, wp._dispatch_raw, wp.WA_HOF_FILE,
             certcard.render_certificate) = orig
        return out, sent

    def test_image_sent_when_rendered(self):
        out, sent = self._run(b"\x89PNG-fake-bytes")
        self.assertTrue(out["sent"])
        self.assertTrue(out["certificate"])
        self.assertTrue(sent["attachment"].endswith(".png"))
        self.assertEqual(sent["mentions"], ["919999999999@s.whatsapp.net"])

    def test_text_fallback_when_no_image(self):
        out, sent = self._run(None)
        self.assertTrue(out["sent"])                     # message never lost
        self.assertFalse(out["certificate"])
        self.assertEqual(sent["attachment"], "")
        self.assertIn("Congrats Top Scorers", sent["text"])


class TestEnglishTemplate(unittest.TestCase):
    def test_no_telugu_in_template(self):
        src = (ROOT / "scripts" / "core" / "certcard.py").read_text()
        self.assertIn("PRACTICE QUIZ · WINNERS", src)
        self.assertNotIn("ప్రాక్టీస్", src)   # template fully English
        eng = (ROOT / "scripts" / "core" / "engine.py").read_text()
        self.assertIn("Top {min(5, len(_rows))} of this round", eng)


class TestWiring(unittest.TestCase):
    def test_bridge_local_attachment(self):
        src = (ROOT / "gateway" / "wa_bridge.js").read_text()
        self.assertIn("fs.readFileSync(url)", src)
        self.assertIn("isLocal", src)

    def test_telegram_cert_and_dashboard_hof(self):
        eng = (ROOT / "scripts" / "core" / "engine.py").read_text()
        self.assertIn("WINNERS CERTIFICATE", eng)
        self.assertIn("send_photo", eng)
        dash = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("/api/whatsapp/hall-of-fame", dash)
        self.assertIn("wa-hof", dash)


if __name__ == "__main__":
    unittest.main()
