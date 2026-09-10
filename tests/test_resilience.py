"""Offline tests: Telegram preview parser, answer-pending flow, supply guard."""
import json, os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from core import tgsource, resilience  # noqa: E402

PREVIEW = """
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="EducationalHub/7971">
 <div class="tgme_widget_message_poll">
  <div class="tgme_widget_message_poll_question">Which Indian state is the first writer to receive the 59th Jnanpith Award from?</div>
  <div class="tgme_widget_message_poll_options">
   <div class="tgme_widget_message_poll_option"><div class="tgme_widget_message_poll_option_text">Uttar Pradesh</div></div>
   <div class="tgme_widget_message_poll_option"><div class="tgme_widget_message_poll_option_text">Madhya Pradesh</div></div>
   <div class="tgme_widget_message_poll_option"><div class="tgme_widget_message_poll_option_text">Bihar</div></div>
   <div class="tgme_widget_message_poll_option"><div class="tgme_widget_message_poll_option_text">Chhattisgarh</div></div>
  </div></div>
 <time datetime="2025-03-26T10:21:00+00:00"></time>
</div>
<div class="tgme_widget_message js-widget_message" data-post="EducationalHub/7972">
 <div class="tgme_widget_message_text js-message_text">Q1. Which river is called the Sorrow of Bengal?<br/>(a) Kosi<br/>(b) Damodar<br/>(c) Hooghly<br/>(d) Teesta<br/>Ans: b</div>
</div>
<div class="tgme_widget_message js-widget_message" data-post="EducationalHub/7973">
 <div class="tgme_widget_message_document_title">Daily Current Affairs Quiz 10 Sept 2026.pdf</div>
</div>
<div class="tgme_widget_message js-widget_message" data-post="EducationalHub/7974">
 <div class="tgme_widget_message_poll">
  <div class="tgme_widget_message_poll_question">Join our paid batch today?</div>
  <div class="tgme_widget_message_poll_option_text">Yes</div><div class="tgme_widget_message_poll_option_text">No</div>
  <div class="tgme_widget_message_poll_option_text">Maybe</div><div class="tgme_widget_message_poll_option_text">Later</div>
 </div>
</div>
"""


class TgSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._o = (tgsource.STATE_FILE, resilience.PENDING_FILE, resilience.STATE_FILE)
        tgsource.STATE_FILE = Path(self.tmp.name) / "tg.json"
        resilience.PENDING_FILE = Path(self.tmp.name) / "pend.json"
        resilience.STATE_FILE = Path(self.tmp.name) / "sup.json"

    def tearDown(self):
        tgsource.STATE_FILE, resilience.PENDING_FILE, resilience.STATE_FILE = self._o
        self.tmp.cleanup()

    def test_parse_preview_splits_messages(self):
        msgs = tgsource.parse_preview(PREVIEW)
        self.assertEqual(len(msgs), 4)
        self.assertEqual(msgs[0]["options"], ["Uttar Pradesh", "Madhya Pradesh", "Bihar", "Chhattisgarh"])
        self.assertEqual(msgs[0]["date"], "2025-03-26")
        self.assertIn("Sorrow of Bengal", msgs[1]["text"])
        self.assertTrue(msgs[2]["doc"].endswith(".pdf"))

    def test_items_poll_is_answer_pending_and_text_mcq_keyed(self):
        raws, pdfs = tgsource.items_from_messages(tgsource.parse_preview(PREVIEW), "EducationalHub", "CURRENT")
        polls = [r for r in raws if r.get("answer_pending")]
        keyed = [r for r in raws if isinstance(r.get("answer_index"), int)]
        self.assertEqual(len(polls), 1, "promo poll must be filtered")
        self.assertIsNone(polls[0]["answer_index"])
        self.assertEqual(len(keyed), 1)
        self.assertEqual(keyed[0]["answer_index"], 1)
        self.assertEqual(len(pdfs), 1)

    def test_pull_paginates_and_tracks_last_id(self):
        calls = []
        def hg(u):
            calls.append(u); return PREVIEW
        raws, pdfs = tgsource.pull("EducationalHub", "CURRENT", pages=3, http_get=hg)
        self.assertEqual(len(calls), 2, "page 2 repeats ids → stop (never loops to page 3)")
        st = json.loads(tgsource.STATE_FILE.read_text())
        self.assertEqual(st["channels"]["EducationalHub"]["last_id"], 7974)
        raws2, _ = tgsource.pull("EducationalHub", "CURRENT", pages=1, http_get=hg)
        self.assertEqual(raws2, [], "second pull yields nothing new")

    def test_pull_network_failure_is_safe(self):
        def boom(u): raise OSError("offline")
        raws, pdfs = tgsource.pull("X", "SSC", http_get=boom)
        self.assertEqual((raws, pdfs), ([], []))
        self.assertEqual(json.loads(tgsource.STATE_FILE.read_text())["channels"]["X"]["fails"], 1)

    def test_solve_pending_requires_agreement(self):
        resilience._park([{"q_en": "Capital of Telangana is which city among these options?",
                           "options_en": ["Warangal", "Hyderabad", "Nizamabad", "Karimnagar"],
                           "channel_hint": "TSPSC"}])
        class Agree:
            def available(self): return True
            def chat(self, sys_, user): return json.dumps({"answer_index": 1, "confidence": 0.95, "reason": "state capital", "flags": []})
        st = resilience.solve_pending(llm=Agree(), dry=True)
        self.assertEqual(st["solved"], 1)
        class Weak:
            def available(self): return True
            def chat(self, sys_, user): return json.dumps({"answer_index": 1, "confidence": 0.5, "reason": "", "flags": []})
        st = resilience.solve_pending(llm=Weak(), dry=False)
        self.assertEqual(st["solved"], 0)
        self.assertEqual(json.loads(resilience.PENDING_FILE.read_text())["items"][0]["tries"], 1)

    def test_supply_guard_escalates_until_ok(self):
        state = {"n": 0}
        orig = resilience.runway
        def fake_runway(bank=None):
            return {"SSC": (5, 0.2) if state["n"] < 2 else (200, 10.0), "TSPSC": (200, 10.0)}
        resilience.runway = fake_runway
        try:
            def step():
                state["n"] += 1; return "ok"
            rep = resilience.supply_guard(dry=True, actions=[("a", step), ("b", step), ("c", step)])
        finally:
            resilience.runway = orig
        self.assertEqual(rep["low_before"], ["SSC"])
        self.assertEqual(len(rep["did"]), 2, "stops as soon as runway is healthy")
        self.assertEqual(rep["low_after"], [])

    def test_curated_channels_are_unique_and_tagged(self):
        names = [u.lower() for u, _, _ in tgsource.CHANNELS]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 30)
        from core import config
        for _, ch, _ in tgsource.CHANNELS:
            self.assertIn(ch, config.CHANNELS)


if __name__ == "__main__":
    unittest.main()
