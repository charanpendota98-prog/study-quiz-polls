# -*- coding: utf-8 -*-
"""🚀 120X Bot Command Center: /portal pack, /top, /unlink, bot funnel.

Pins (probe-verified):
  • tg_daily_pack: linked-only; carries daily status, readiness,
    weak topics, goal label, next exam
  • bot_leaders: today's board + my rank + linked flag
  • tg_unlink_bot: clears tg_map + member tg_id (idempotent-false)
  • tg_stats counters: claims on link, logins on WebApp auth;
    portal_analytics["bot"] funnel (linked/claims/logins/link_pct)
  • Wiring: bot /portal /today /top /unlink + admin Bot Funnel render
"""
import hashlib
import hmac
import json
import sys
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from core import portal, brain, config  # noqa: E402

TEST_TOKEN = "123456:TESTTOKEN120"


class _KV:
    def save(self):
        pass

    def save_debounced(self):
        pass


class _Members:
    def __init__(self):
        self.members = {}
        self.kv = _KV()

    def _get(self, uid):
        return self.members.setdefault(str(uid), {
            "name": "Adv120 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": []})

    def award_answer(self, uid, username="", correct=True, topic="",
                     qid=""):
        m = self._get(uid)
        m["points"] = m.get("points", 0) + (10 if correct else 0)
        m["total"] = m.get("total", 0) + 1
        return {"points": m["points"]}


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        self._bt = config.BOT_TOKEN
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"
        config.BOT_TOKEN = TEST_TOKEN
        self.mem = _Members()
        ok, info = portal.register_student(self.mem, "Adv120 Tester",
                                           "9822000120", "Guntur",
                                           "railway")
        assert ok, info
        self.tok = info["token"]
        ok, c = portal.tg_link_code(self.mem, self.tok)
        assert ok, c
        ok, cl = portal.tg_link_claim(self.mem, 555120, c["code"])
        assert ok, cl

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf
        config.BOT_TOKEN = self._bt


class TestBotCommands120(_Base):
    def test_daily_pack(self):
        ok, pack = portal.tg_daily_pack(self.mem, 555120)
        self.assertTrue(ok, pack)
        self.assertEqual(pack["name"], "Adv120 Tester")
        self.assertTrue(pack["goal_label"])
        self.assertEqual(pack["daily"]["n"], 10)
        self.assertIn("score", pack["readiness"])
        ok, err = portal.tg_daily_pack(self.mem, 424242)
        self.assertFalse(ok)
        self.assertEqual(err, "not_linked")

    def test_leaders(self):
        ok, lb = portal.bot_leaders(self.mem, 555120)
        self.assertTrue(ok, lb)
        self.assertTrue(lb["linked"])
        self.assertIn("leaders", lb)

    def test_unlink(self):
        ok, un = portal.tg_unlink_bot(self.mem, 555120)
        self.assertTrue(ok, un)
        self.assertEqual(self.mem._get("w9822000120").get("tg_id"), "")
        ok, err = portal.tg_unlink_bot(self.mem, 555120)
        self.assertFalse(ok)

    def test_bot_funnel_counters(self):
        pairs = {"auth_date": str(int(time.time())),
                 "query_id": "AAE120",
                 "user": json.dumps({"id": 555120,
                                     "first_name": "Adv120"})}
        dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        secret = hmac.new(b"WebAppData", TEST_TOKEN.encode(),
                          hashlib.sha256).digest()
        pairs["hash"] = hmac.new(secret, dcs.encode(),
                                 hashlib.sha256).hexdigest()
        ok, au = portal.tg_auth(self.mem, urllib.parse.urlencode(pairs))
        self.assertTrue(ok, au)
        an = portal.portal_analytics(self.mem)
        self.assertEqual(an["bot"]["linked"], 1)
        self.assertEqual(an["bot"]["claims"], 1)
        self.assertEqual(an["bot"]["logins"], 1)
        self.assertEqual(an["bot"]["link_pct"], 100.0)


class TestWiring120(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        cls.bot = (ROOT / "scripts" / "bot.py").read_text(encoding="utf-8")

    def test_bot_commands_and_funnel_ui(self):
        for cmd in ('"/portal"', '"/today"', '"/top"', '"/unlink"'):
            self.assertIn(cmd, self.bot)
        for fn in ("tg_daily_pack", "bot_leaders", "tg_unlink_bot",
                   "_portal_base120"):
            self.assertIn(fn, self.bot)
        self.assertIn("d.bot.linked", self.dash)
        self.assertIn("Bot commands: /portal", self.dash)


if __name__ == "__main__":
    unittest.main()
