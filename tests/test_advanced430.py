# -*- coding: utf-8 -*-
"""430X — Fix audit: go-live card knows the Paper Factory state.

Pins:
  * _golive_checks gains a "Paper Factory (430X)" row (15 checks);
  * banked scraped questions are counted honestly;
  * open drafts warn, Telugu-pending counts are reported and are
    never presented as banked.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import config, paperfactory  # noqa: E402
from core.store import save_json_atomic  # noqa: E402
import dashboard_server as dash  # noqa: E402

PAPER = ("1. The HCF of 12 and 18 is (a) 2 (b) 3 (c) 6 (d) 9\n"
         "Ans: (c)\n"
         "2. Capital of Telangana? (a) Warangal (b) Hyderabad "
         "(c) Nizamabad (d) Khammam\nAnswer: b\n")


class GoLivePaperFactory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old = config.DATA
        cls.tmp = Path(tempfile.mkdtemp())
        config.DATA = cls.tmp
        cls._old_bank = config.BANK_JSON

    @classmethod
    def tearDownClass(cls):
        config.DATA = cls._old
        config.BANK_JSON = cls._old_bank

    def _row(self):
        r = dash._golive_checks()
        return next(c for c in r["checks"]
                    if c["name"] == "Paper Factory (430X)")

    def test_row_present_and_checks_16(self):
        r = dash._golive_checks()
        self.assertEqual(len(r["checks"]), 16)
        row = self._row()
        self.assertIn("banked", row["detail"])

    def test_open_draft_warns_with_pending(self):
        p = self.tmp / "TSPSC 2022 Paper-I.txt"
        p.write_text(PAPER, encoding="utf-8")
        paperfactory.make_draft(p)
        row = self._row()
        self.assertEqual(row["status"], "warn")
        self.assertIn("drafts open", row["detail"])
        self.assertIn("Telugu pending", row["detail"])

    def test_banked_counts(self):
        save_json_atomic(config.DATA / "scraped_bank.json",
                         {"questions": [{"id": "X1"}, {"id": "X2"}]})
        row = self._row()
        self.assertIn("2 approved paper questions banked",
                      row["detail"])


class CustomChannelInheritance(unittest.TestCase):
    """430X pattern fix: operator-created channels (bundle imports,
    dashboard Add-Channel) mount into config.PUBLIC_CHANNELS at import
    time but own no bank/blueprint. Without inheritance the daily
    engine would crash or send empty rounds for them; with it they
    draw their base exam's stock and paper blueprint."""

    def test_base_channels_resolve_to_themselves(self):
        self.assertEqual(config.bank_channel_of("POLICE"), "POLICE")
        self.assertEqual(config.bank_channel_of("NOPE_X"), "NOPE_X")

    def test_mounted_custom_channel_inherits(self):
        key = next((k for k in config.CHANNELS
                    if k not in config.BASE_CHANNEL_KEYS), None)
        if key is None:
            self.skipTest("no custom channels mounted in this process")
        base = config.CHANNELS[key].get("base_exam")
        self.assertTrue(base)
        from core.question_bank import Bank
        from core import blueprint
        self.assertEqual(config.bank_channel_of(key), base)
        self.assertEqual(Bank().by_channel(key),
                         Bank().by_channel(base))
        self.assertTrue(Bank().by_channel(key))
        pool = Bank().by_channel(key)
        picked = blueprint.compose_round(key, pool, 5)
        self.assertEqual(len(picked), 5)


if __name__ == "__main__":
    unittest.main()
