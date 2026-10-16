#!/usr/bin/env python3
"""🧠 Smart 3.0 — weak-topic smart rounds, contact-share mobile,
one-time profile nudge, advisor→daily-schedule wiring.

Bank tests reuse the object.__new__ pattern (no generation machinery);
item_intel/members stores are tmp-isolated; crm sheet paths patched so
the real sheet is never rewritten by tests.
Run: python3 -m unittest discover -s tests -p "test_smart3.py"
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import crm, item_intel                       # noqa: E402
from core.members import Members                       # noqa: E402
from core.question_bank import Bank                    # noqa: E402

USER = {"id": 777, "first_name": "Anitha", "last_name": "Rao",
        "username": "anitha_r"}


def _q(qid, topic, source="curated"):   # curated/pyq = postable sources
    return {"id": qid, "channel": "SSC", "source": source,
            "q_en": f"Question {qid} about {topic} and governance in India?",
            "q_te": "", "options_en": ["A1", "B2", "C3", "D4"],
            "options_te": [], "answer_index": 0, "topic": topic}


def _bank(qs):
    b = object.__new__(Bank)
    b.questions = qs
    b.used = {}
    b._sig_set = set()
    b.shown_sigs = {"sigs": []}
    return b


def _fresh_members():
    mb = Members()
    tmp = Path(tempfile.gettempdir()) / f"su_test_s3_{tempfile.mktemp()[-6:]}.json"
    mb.kv.path = tmp
    mb.data = {"members": {}, "pending": {}}
    mb.members = mb.data["members"]
    mb.pending = mb.data["pending"]
    return mb


class TmpIntel(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = item_intel.STATS_FILE
        item_intel.STATS_FILE = self.tmp / "item_stats.json"
        item_intel._cache["mtime"] = None
        item_intel._cache["data"] = {}
        # polity = channel weak topic (0/12), geography = strong (12/12)
        for i in range(12):
            item_intel.record(f"XP{i}", False, topic="polity", channel="SSC")
            item_intel.record(f"XG{i}", True, topic="geography", channel="SSC")

    def tearDown(self):
        item_intel.STATS_FILE = self._orig
        item_intel._cache["mtime"] = None


class TestSmartRounds(TmpIntel):
    def test_channel_topic_rates(self):
        rates = item_intel.channel_topic_rates("SSC")
        self.assertEqual(rates["polity"]["rate"], 0.0)
        self.assertEqual(rates["geography"]["rate"], 1.0)
        self.assertEqual(item_intel.channel_topic_rates("NOPE"), {})

    def test_pick_smart_swaps_in_weak_topic(self):
        fresh_weak = [_q("W1", "polity"), _q("W2", "polity")]
        bank = _bank([_q("G1", "geography"), _q("G2", "geography"),
                      _q("P1", "geography", source="pyq")] + fresh_weak)
        base = [_q("G1", "geography"), _q("G2", "geography"),
                _q("P1", "geography", source="pyq")]
        bank.pick = lambda ch, n=10: list(base)       # isolate swap logic
        out = bank.pick_smart("SSC", 3)
        ids = [q["id"] for q in out]
        self.assertIn("P1", ids)                      # PYQ slot protected
        self.assertTrue(any(i in ids for i in ("W1", "W2")))   # weak swapped in
        self.assertEqual(len(out), 3)

    def test_pick_smart_no_data_falls_back(self):
        bank = _bank([_q("G1", "geography")])
        base = [_q("G1", "geography")]
        bank.pick = lambda ch, n=10: list(base)
        self.assertEqual(bank.pick_smart("SSC", 1)[0]["id"], "G1")


class FakeTg:
    def __init__(self):
        self.sent = []

    def send_message(self, chat, text, buttons=None, **kw):
        self.sent.append((str(chat), text, buttons, kw))
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


class TmpSheet(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (crm.MEMBERS_CSV, crm.MEMBERS_XLSX)
        crm.MEMBERS_CSV = self.tmp / "members.csv"
        crm.MEMBERS_XLSX = self.tmp / "members.xlsx"

    def tearDown(self):
        crm.MEMBERS_CSV, crm.MEMBERS_XLSX = self._orig


class TestContactShare(TmpSheet):
    def test_menu_mobile_sends_contact_button(self):
        mb = _fresh_members()
        mb.auto_register_from_poll(777, USER, exam="SSC")
        bot = _fake_bot(mb)
        bot.handle_callback({"from": {"id": 777}, "id": "c1",
                             "data": "prof:menu_mobile",
                             "message": {"chat": {"id": 777}}})
        with_markup = [s for s in bot.tg.sent if s[3].get("markup")]
        self.assertEqual(len(with_markup), 1)
        btn = with_markup[0][3]["markup"]["keyboard"][0][0]
        self.assertTrue(btn["request_contact"])

    def test_contact_message_saves_mobile(self):
        mb = _fresh_members()
        mb.auto_register_from_poll(777, USER, exam="SSC")
        bot = _fake_bot(mb)
        bot.handle_message({"chat": {"id": 777}, "from": dict(USER),
                            "contact": {"phone_number": "+91 98480 12345",
                                        "user_id": 777}})
        self.assertEqual(mb._get(777)["mobile"], "9848012345")
        self.assertTrue(any(s[3].get("markup", {}).get("remove_keyboard")
                            for s in bot.tg.sent))


class TestSmartNudge(TmpSheet):
    def test_nudge_once_at_10_answers(self):
        mb = _fresh_members()
        mb.auto_register_from_poll(777, USER, exam="SSC")
        mb._get(777)["total"] = 9
        bot = _fake_bot(mb)
        upd = {"poll_answer": {"user": dict(USER), "poll_id": "p9",
                               "option_ids": [0]}}
        bot.handle_poll_answer(upd)                   # 10th answer → nudge
        nudges = [s for s in bot.tg.sent if "Smart check" in s[1]]
        self.assertEqual(len(nudges), 1)
        bot.handle_poll_answer(upd)                   # never twice
        nudges = [s for s in bot.tg.sent if "Smart check" in s[1]]
        self.assertEqual(len(nudges), 1)


class TestAdvisorSchedule(unittest.TestCase):
    def test_advisor_can_create_daily_schedule(self):
        src = (ROOT / "scripts" / "dashboard_server.py").read_text()
        self.assertIn("scheduleSmartHour", src)
        self.assertIn("/api/telegram/schedule", src)
        eng = (ROOT / "scripts" / "core" / "engine.py").read_text()
        self.assertIn('pick_smart(ch, config.POLLS_PER_SLOT)', eng)


if __name__ == "__main__":
    unittest.main()
