#!/usr/bin/env python3
"""Bulk setup v5 tests — Excel sample + import (WhatsApp + Telegram).

Covers: template sheets, WA/TG import, duplicate skipping, invalid-JID
rejection, auto-schedules (WA + TG modes), and honest dry-run (writes
nothing). bundle_manager is imported lazily (see test_messaging_v4 note
about channel_router pollution) and all state files point at tmp dirs.
Run: python3 -m unittest discover -s tests -p "test_bulk_setup.py"
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

WA_ROWS = [
    ["Group Name", "Invite Link or JID", "Exam Category", "Shift", "Group Type",
     "Daily Times", "Polls Per Slot", "Days (0=Always)", "Subjects"],
    ["Warangal SI Batch 1", "120363000000000101@g.us", "POLICE", "ALL_DAY",
     "EXAM_SPECIFIC", "08:00+20:30", "5", "0", "REASONING+GK"],
    ["Bad JID Group", "not-a-jid", "SSC", "ALL_DAY", "EXAM_SPECIFIC", "", "", "", ""],
]

TG_ROWS = [
    ["Channel/Group Name", "Chat ID / @username / t.me link", "Exam Category",
     "Type (channel/group)", "Daily Times", "Polls Per Slot", "Days (0=Always)", "Subjects"],
    ["SSC Daily Quiz Telugu", "@StudentUpSSCTest", "SSC", "channel",
     "08:00+20:00", "5", "0", "GK"],
    ["Bad TG Row", "not a chat", "SSC", "channel", "", "", "", ""],
]


class TestBulkSetup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core import bundle_manager, whatsapp_pipeline, channel_router, config
        cls.bm, cls.wap, cls.cr, cls.config = bundle_manager, whatsapp_pipeline, channel_router, config

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (self.wap.WA_CONFIG_FILE, self.wap.WA_SCHEDULES_FILE,
                      self.cr.CUSTOM_CHANNELS_FILE)
        self.wap.WA_CONFIG_FILE = self.tmp / "whatsapp_groups.json"
        self.wap.WA_SCHEDULES_FILE = self.tmp / "whatsapp_schedules.json"
        self.cr.CUSTOM_CHANNELS_FILE = self.tmp / "custom_channels.json"
        # seed one existing WA group (dedupe baseline)
        self.wap.save_wa_registry({
            "groups": [{"id": "G_SEED", "name": "Seed Group",
                        "jid": "120363000000000999@g.us", "category": "SSC",
                        "shift": "ALL_DAY", "active": True}],
            "gateway_url": "", "anti_ban": {},
        })
        self._tg_keys_before = set(self.config.CHANNELS.keys())

    def tearDown(self):
        (self.wap.WA_CONFIG_FILE, self.wap.WA_SCHEDULES_FILE,
         self.cr.CUSTOM_CHANNELS_FILE) = self._orig
        # undo register_channel's in-memory config injection
        for k in set(self.config.CHANNELS.keys()) - self._tg_keys_before:
            self.config.CHANNELS.pop(k, None)
            if k in self.config.PUBLIC_CHANNELS:
                self.config.PUBLIC_CHANNELS.remove(k)

    def _book(self, sheets):
        return self.bm.build_multisheet_xlsx_bytes(sheets)

    def test_template_has_telegram_sheet(self):
        data = self.bm.parse_xlsx_sheets_data(self.bm.build_groups_template_xlsx())
        self.assertIn("📢 Telegram_Channels", data)
        self.assertIn("✍️ My_Groups", data)
        tg = data["📢 Telegram_Channels"]
        self.assertEqual(tg[0][0], "Channel/Group Name")

    def test_wa_import_dedupe_and_validation(self):
        book = self._book({"Police_Groups": WA_ROWS})
        res = self.bm.import_from_multisheet_excel(book)
        self.assertEqual(res["imported_groups_count"], 1)
        self.assertEqual(len(res["errors"]), 1)          # bad JID rejected
        self.assertEqual(len(res["schedules_created"]), 2)  # 08:00 + 20:30 = 2 slots
        # re-import same file → all duplicates, zero new, schedule not duplicated
        res2 = self.bm.import_from_multisheet_excel(book)
        self.assertEqual(res2["imported_groups_count"], 0)
        self.assertGreaterEqual(res2["skipped_duplicates_count"], 1)
        self.assertEqual(len(self.wap.load_schedules()), 2)

    def test_telegram_import_registers_and_schedules(self):
        book = self._book({"📢 Telegram_Channels": TG_ROWS})
        res = self.bm.import_from_multisheet_excel(book)
        self.assertEqual(res["imported_channels_count"], 1)
        self.assertEqual(len(res["errors"]), 1)          # bad chat rejected
        self.assertEqual(len(res["tg_schedules_created"]), 2)  # 08:00 + 20:00
        job = self.wap.load_schedules()[0]
        self.assertEqual(job["mode"], "tg")
        self.assertIn("SSC_DAILY_QUIZ_TELUGU", job["telegram_channels"])
        cust = self.cr.load_custom_channels()["channels"]
        self.assertIn("SSC_DAILY_QUIZ_TELUGU", cust)
        # re-import → duplicate, no second job
        res2 = self.bm.import_from_multisheet_excel(book)
        self.assertEqual(res2["imported_channels_count"], 0)
        self.assertEqual(len(self.wap.load_schedules()), 2)

    def test_dry_run_writes_nothing(self):
        book = self._book({"Police_Groups": WA_ROWS, "📢 Telegram_Channels": TG_ROWS})
        before_wa = (self.tmp / "whatsapp_groups.json").read_text()
        res = self.bm.import_from_multisheet_excel(book, dry_run=True)
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["imported_groups_count"], 1)
        self.assertEqual(res["imported_channels_count"], 1)
        self.assertEqual((self.tmp / "whatsapp_groups.json").read_text(), before_wa)
        self.assertFalse((self.tmp / "whatsapp_schedules.json").exists())
        self.assertFalse((self.tmp / "custom_channels.json").exists())

    def test_seed_jid_counts_as_duplicate(self):
        rows = [WA_ROWS[0],
                ["Dup Seed", "120363000000000999@g.us", "SSC", "ALL_DAY",
                 "EXAM_SPECIFIC", "", "", "", ""]]
        res = self.bm.import_from_multisheet_excel(self._book({"G": rows}))
        self.assertEqual(res["imported_groups_count"], 0)
        self.assertEqual(res["skipped_duplicates_count"], 1)


if __name__ == "__main__":
    unittest.main()
