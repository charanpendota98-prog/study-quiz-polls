# -*- coding: utf-8 -*-
"""🚀 110X Bot × Portal bridge: Telegram link + WebApp auto-login.

Pins (probe-verified):
  • tg_link_code → one-time code (10 min TTL), single-use claim
  • tg_link_claim links tg_id <-> portal uid (tg_map + member tg_id)
  • Expired code rejected; bot_link_state reflects link
  • tg_auth: Telegram WebApp initData HMAC verify (BOT_TOKEN) —
    linked user gets a working portal session; tampered hash and
    unlinked Telegram user rejected (bad_hash / not_linked)
  • Wiring: bot /start plink_ branch, routes, WebApp JS + auto-login
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

TEST_TOKEN = "123456:TESTTOKEN110"


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
            "name": "Adv110 Tester", "district": "Guntur", "points": 0,
            "total": 0, "topics": {}, "review": [], "last_active": "",
            "daylog": {}, "streak": 0, "best_streak": 0,
            "answers_today": 0, "badges": []})

    def award_answer(self, uid, username="", correct=True, topic="",
                     qid=""):
        return {"points": 0}


def _init_data(tg_id, token=TEST_TOKEN):
    pairs = {"auth_date": str(int(time.time())), "query_id": "AAE110",
             "user": json.dumps({"id": tg_id, "first_name": "Adv110"})}
    dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(),
                      hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, dcs.encode(),
                             hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(pairs)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._pp, self._bf = portal.PATH, brain.BRAIN_FILE
        self._bt = config.BOT_TOKEN
        portal.PATH = self.tmp / "portal.json"
        brain.BRAIN_FILE = self.tmp / "brain.json"
        config.BOT_TOKEN = TEST_TOKEN
        self.mem = _Members()
        ok, info = portal.register_student(self.mem, "Adv110 Tester",
                                           "9822000110", "Guntur",
                                           "railway")
        assert ok, info
        self.tok = info["token"]

    def tearDown(self):
        portal.PATH, brain.BRAIN_FILE = self._pp, self._bf
        config.BOT_TOKEN = self._bt


class TestBotLink110(_Base):
    def test_link_claim_single_use(self):
        ok, c = portal.tg_link_code(self.mem, self.tok)
        self.assertTrue(ok, c)
        self.assertTrue(c["param"].startswith("plink_"))
        ok, cl = portal.tg_link_claim(self.mem, 555110, c["code"])
        self.assertTrue(ok, cl)
        self.assertEqual(cl["uid"], "w9822000110")
        self.assertEqual(self.mem._get("w9822000110").get("tg_id"),
                         "555110")
        ok, _e = portal.tg_link_claim(self.mem, 555110, c["code"])
        self.assertFalse(ok)  # single-use
        ok, st = portal.bot_link_state(self.mem, self.tok)
        self.assertTrue(st["linked"])

    def test_expired_code_rejected(self):
        ok, c = portal.tg_link_code(self.mem, self.tok)
        d = portal._load()
        d["tg_links"][c["code"]]["exp"] = "2000-01-01T00:00:00"
        portal._save(d)
        ok, _e = portal.tg_link_claim(self.mem, 555111, c["code"])
        self.assertFalse(ok)

    def test_tg_auth_flow(self):
        ok, c = portal.tg_link_code(self.mem, self.tok)
        portal.tg_link_claim(self.mem, 555112, c["code"])
        ok, au = portal.tg_auth(self.mem, _init_data(555112))
        self.assertTrue(ok, au)
        st = portal.state(self.mem, au["token"])
        self.assertEqual(st["student"]["name"], "Adv110 Tester")
        ok, err = portal.tg_auth(self.mem,
                                 _init_data(555112).replace("AAE110",
                                                            "AAE999"))
        self.assertFalse(ok)
        self.assertEqual(err, "bad_hash")
        ok, err = portal.tg_auth(self.mem, _init_data(999999))
        self.assertFalse(ok)
        self.assertEqual(err, "not_linked")


class TestWiring110(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dash = (ROOT / "scripts" / "dashboard_server.py").read_text(
            encoding="utf-8")
        cls.bot = (ROOT / "scripts" / "bot.py").read_text(encoding="utf-8")

    def test_routes_spa_bot(self):
        for s in ('p.path == "/api/portal/tg_link"',
                  'p.path == "/api/portal/tg_auth"',
                  'p.path == "/api/portal/bot_link"',
                  "telegram-web-app.js", "loadBotLink", "linkBot",
                  "wa.initData", 'id="bot-link-card"'):
            self.assertIn(s, self.dash)
        self.assertIn('arg.startswith("plink_")', self.bot)
        self.assertIn("tg_link_claim", self.bot)


if __name__ == "__main__":
    unittest.main()
