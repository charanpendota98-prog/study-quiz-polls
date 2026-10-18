#!/usr/bin/env python3
"""🎉 Advanced registration: poll answer → AUTO-register → SHEET (owner).

Covers: Members.auto_register_from_poll (Telegram profile, source tag,
+25 released, wizard cleared, idempotent), sheet sync into members.csv
(crm paths tmp-patched so the real sheet is never touched), one-tap
profile enrichment (exam/district overwrite, unique-mobile guard), and
the bot-level flow: a DM poll_answer registers the player, sends the
welcome + buttons, and prof: button taps land in the profile.
Run: python3 -m unittest discover -s tests -p "test_poll_registration.py"
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import crm                                # noqa: E402
from core.members import Members                    # noqa: E402

USER = {"id": 777, "first_name": "Anitha", "last_name": "Rao",
        "username": "anitha_r"}


def _fresh_members():
    mb = Members()
    tmp = Path(tempfile.gettempdir()) / f"su_test_reg_{tempfile.mktemp()[-6:]}.json"
    mb.kv.path = tmp
    mb.data = {"members": {}, "pending": {}}
    mb.members = mb.data["members"]
    mb.pending = mb.data["pending"]
    return mb


class TmpSheet(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (crm.MEMBERS_CSV, crm.MEMBERS_XLSX)
        crm.MEMBERS_CSV = self.tmp / "members.csv"
        crm.MEMBERS_XLSX = self.tmp / "members.xlsx"

    def tearDown(self):
        crm.MEMBERS_CSV, crm.MEMBERS_XLSX = self._orig


class TestAutoRegister(TmpSheet):
    def test_poll_play_registers_and_sheets(self):
        mb = _fresh_members()
        mb.start_registration(777)                    # stale wizard state
        m = mb.auto_register_from_poll(777, USER, exam="SSC")
        self.assertTrue(m["registered"])
        self.assertEqual(m["name"], "Anitha Rao")
        self.assertEqual(m["username"], "anitha_r")
        self.assertEqual(m["exam"], "SSC")
        self.assertEqual(m["source"], "poll_auto")
        self.assertGreaterEqual(m["points"], 25)      # registration bonus
        self.assertIsNone(mb.pending_step(777))       # wizard cleared
        csv = (self.tmp / "members.csv").read_text()
        self.assertIn("777", csv)
        self.assertIn("Anitha Rao", csv)
        self.assertIn("poll_auto", csv)               # owner sees the source
        self.assertTrue((self.tmp / "members.xlsx").stat().st_size > 0)

    def test_idempotent_no_double_bonus(self):
        mb = _fresh_members()
        mb.auto_register_from_poll(777, USER, exam="SSC")
        pts = mb._get(777)["points"]
        mb.auto_register_from_poll(777, USER, exam="Banking")
        self.assertEqual(mb._get(777)["points"], pts)
        self.assertEqual(mb._get(777)["exam"], "SSC")


class TestEnrichment(TmpSheet):
    def test_exam_district_overwrite_and_mobile_guard(self):
        mb = _fresh_members()
        mb.auto_register_from_poll(777, USER, exam="SSC")
        mb.update_profile(777, exam="Banking", district="Warangal", state="TS")
        m = mb._get(777)
        self.assertEqual((m["exam"], m["district"], m["state"]),
                         ("Banking", "Warangal", "TS"))
        self.assertIsNotNone(mb.update_profile(777, mobile="9848012345"))
        mb.auto_register_from_poll(888, {"id": 888, "first_name": "Raj"})
        # same mobile for another account → refused, original untouched
        self.assertIsNone(mb.update_profile(888, mobile="9848012345"))
        self.assertEqual(mb._get(888).get("mobile", ""), "")


class FakeTg:
    def __init__(self):
        self.sent = []

    def send_message(self, chat, text, buttons=None, **kw):
        self.sent.append((str(chat), text, buttons))
        return {"ok": True, "result": {"message_id": 1}}

    def answer_callback(self, *a, **kw):
        return {"ok": True}


def _fake_bot(members):
    from bot import Bot
    b = Bot.__new__(Bot)
    b.members = members
    b.tg = FakeTg()
    b.bank = None
    b._poll_q = {"p9": ("SSC", "Q1", 0, "Polity")}
    return b


class TestBotFlow(TmpSheet):
    def test_poll_answer_auto_registers_player(self):
        mb = _fresh_members()
        bot = _fake_bot(mb)
        bot.handle_poll_answer({"poll_answer": {
            "user": dict(USER), "poll_id": "p9", "option_ids": [0]}})
        m = mb._get(777)
        self.assertTrue(m["registered"])              # played → registered
        self.assertEqual(m["source"], "poll_auto")
        welcome = [s for s in bot.tg.sent if "registration automatic" in s[1]]
        self.assertEqual(len(welcome), 1)
        self.assertIsNotNone(welcome[0][2])           # enrichment buttons
        csv = (self.tmp / "members.csv").read_text()
        self.assertIn("Anitha Rao", csv)              # data in the SHEET

    def test_profile_buttons_enrich(self):
        mb = _fresh_members()
        mb.auto_register_from_poll(777, USER, exam="SSC")
        bot = _fake_bot(mb)

        def tap(data):
            bot.handle_callback({"from": {"id": 777}, "id": "c1",
                                 "data": data,
                                 "message": {"chat": {"id": 777}}})

        tap("prof:menu_district")
        self.assertTrue(any("state pick" in s[1] for s in bot.tg.sent))
        tap("prof:st:TS")
        tap("prof:di:Warangal")
        self.assertEqual(mb._get(777)["district"], "Warangal")
        tap("prof:ex:Banking")
        self.assertEqual(mb._get(777)["exam"], "Banking")


if __name__ == "__main__":
    unittest.main()
