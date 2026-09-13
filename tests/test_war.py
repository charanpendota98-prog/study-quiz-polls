import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, districtwar as W
from core.question_bank import Bank


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        self.members = {}
        for i, d in enumerate(["Warangal"] * 3 + ["Guntur"] * 5 + ["Adilabad"] * 2, 1):
            self.members[str(i)] = {"registered": True, "name": f"P{i}", "district": d, "points": 0, "badges": []}
        self.members["99"] = {"registered": False}
    def _get(self, uid): return self.members.setdefault(str(uid), {})


class _TG:
    dry = True
    def __init__(self): self.msgs = []; self.polls = []; self.pid = 0
    def send_message(self, chat, text, **kw): self.msgs.append((str(chat), text))
    def _call(self, m, payload, **kw):
        self.pid += 1; self.polls.append(payload["chat_id"]); return {"result": {"poll": {"id": f"w{self.pid}"}}}


class TestWar(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self._o = W.PATH; W.PATH = self.tmp / "w.json"
        # isolate bank state
        self._used = config.STORE_USED
        config.STORE_USED = self.tmp / "used.json"
        self._sig = config.DATA / "shown_signatures.json"
        self._sig_bak = self._sig.read_bytes() if self._sig.exists() else None
    def tearDown(self):
        W.PATH = self._o; config.STORE_USED = self._used
        if self._sig_bak is not None: self._sig.write_bytes(self._sig_bak)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pid(self, d, uid):
        for pid, (qi, owner) in d["polls"].items():
            if owner == uid and qi == d["live"]["qi"]:
                return pid

    def test_compose_mix_all_exams(self):
        qs = W.compose(Bank())
        self.assertGreaterEqual(len(qs), 8)
        subs = {W._subject(q) for q in qs}
        self.assertTrue({"gk", "reasoning", "quant"} <= subs)
        chans = {q.get("channel") for q in qs}
        self.assertGreaterEqual(len(chans), 3)          # drawn across exams, not one syllabus

    def test_lobby_lock(self):
        m, tg = _Members(), _TG()
        self.assertFalse(W.lobby_join(m, "1")[0])                 # lobby not open
        W.open_lobby()
        ok, txt = W.lobby_join(m, "1"); self.assertTrue(ok); self.assertIn("fighter #1", txt)
        self.assertFalse(W.lobby_join(m, "99")[0])                # unregistered
        self.assertEqual(W.start_war(Bank(), m, tg)[0], False)    # only 1 opted in
        W.open_lobby(); W.lobby_join(m, "1"); W.lobby_join(m, "4")
        ok, info = W.start_war(Bank(), m, tg)
        self.assertTrue(ok); self.assertEqual(info["fighters"], 2)
        self.assertFalse(W.lobby_join(m, "5")[0])                 # 🔒 locked after start
        self.assertEqual(len(tg.polls), 2)                        # only opted-in got polls

    def test_full_war(self):
        m, tg = _Members(), _TG()
        W.open_lobby()
        for u in m.members:
            W.lobby_join(m, u)
        ok, info = W.start_war(Bank(), m, tg)
        self.assertTrue(ok, info); self.assertEqual(info["fighters"], 10)
        self.assertEqual(len(tg.polls), 10)
        self.assertEqual(W.start_war(Bank(), m, tg)[0], False)     # no double start
        now = datetime.now(config.IST)
        d = W._load(); n_q = len(d["live"]["questions"])
        # Q1: Warangal all right, Guntur 2/5 right, Adilabad none answer
        for uid in ("1", "2", "3", "4", "5"):
            ans = d["live"]["questions"][0]["answer_index"]
            self.assertTrue(W.record_answer(self._pid(d, uid), uid, ans))
        for uid in ("6", "7", "8"):
            self.assertTrue(W.record_answer(self._pid(d, uid), uid, (d["live"]["questions"][0]["answer_index"] + 1) % 4))
        t = now
        for i in range(n_q):
            t += timedelta(seconds=80); self.assertTrue(W.tick(tg, m, now=t) or i == n_q - 1)
            t += timedelta(seconds=W.GAP_SEC + 1); W.tick(tg, m, now=t)
        d = W._load()
        self.assertEqual(d["live"]["state"], "done")
        rows = d["season"][now.strftime("%Y%m")]["wars"][now.strftime("%Y-%m-%d")]["rows"]
        self.assertEqual(rows[0]["district"], "Warangal")           # 3 sharp > 5 mixed
        self.assertEqual([r["district"] for r in rows], ["Warangal", "Guntur"])   # Adilabad never fought
        self.assertEqual(m.members["1"]["points"] % 10, 5 if m.members["1"].get("war_mvp") else 0)
        self.assertTrue(any("DISTRICT WAR" in t and "🥇 Warangal" in t for _, t in tg.msgs))
        post = W.pop_channel_post(); self.assertIn("Warangal", post); self.assertIsNone(W.pop_channel_post())
        self.assertIn("season table", W.season_table())
        self.assertIn("Warangal", W.my_war(m, "1"))
        self.assertIn("5 నిమిషాల్లో", W.alert_text(5))
        self.assertTrue(any("LIVE after Q3" in t for _, t in tg.msgs))
        self.assertTrue(any("Top fighters" in t for _, t in tg.msgs))


if __name__ == "__main__":
    unittest.main()


class TestWarRanksSquads(TestWar):
    def test_compose_mix_all_exams(self): pass
    def test_lobby_lock(self): pass

    def test_streaks_squads_tiers(self):
        from core import hooks
        m, tg = _Members(), _TG()
        hp = hooks.SQUADS_PATH; hooks.SQUADS_PATH = self.tmp / "sq.json"
        try:
            hooks.squad_create(m, "1", "Warangal Gang"); hooks.squad_join(m, "2", hooks._sq()["by_uid"]["1"])
            hooks.squad_create(m, "4", "Guntur Boys"); hooks.squad_join(m, "5", hooks._sq()["by_uid"]["4"])
            W.open_lobby()
            for u in "12345":
                W.lobby_join(m, u)
            ok, info = W.start_war(Bank(), m, tg)
            self.assertTrue(ok, info)
            d = W._load()
            self.assertEqual(d["live"]["fighters"]["1"]["squad"]["name"], "Warangal Gang")
            self.assertEqual(d["live"]["fighters"]["1"]["tier"], "🪖 Recruit")
            n_q = len(d["live"]["questions"])
            for qi in range(n_q):
                d = W._load()
                for u in "12345":
                    pid = self._pid(d, u)
                    ans = d["live"]["questions"][qi]["answer_index"]
                    W.record_answer(pid, u, ans if u in "12" or (u == "4" and qi % 2 == 0) else (ans + 1) % 4)
                d = W._load()
                d["live"]["state"] = "gap"; d["live"]["q_open"] = W._now().isoformat(); W._save(d)
                W.tick(tg, m, W._now() + timedelta(seconds=1))
            d = W._load()
            f1 = d["live"]["fighters"]["1"]
            self.assertEqual(f1["best_streak"], n_q); self.assertIn("☄️ 8-streak", f1["streak_bonus"])
            self.assertGreater(f1["pts"], n_q * 10 + 35)                       # streak bonuses landed
            self.assertEqual(d["live"]["squad_rows"][0]["name"], "Warangal Gang")
            self.assertGreaterEqual(d["war_points"]["1"], 150)
            self.assertNotEqual(W.war_tier(d, "1"), "🪖 Recruit"); self.assertTrue(d["live"]["tier_ups"])
            post = d["_channel_post"]
            self.assertEqual(len(d["live"]["state_rows"]), 2)          # Warangal (TS) vs Guntur (AP)
            self.assertIn(" vs ", post); self.assertIn("Telangana", post)
            for s_ in ("SQUAD BATTLE", "Warangal Gang", "RANK UP", "Streaks"):
                self.assertIn(s_, post)
            self.assertIn("War Rank", W.war_rank_text("1")); self.assertIn("WAR RANKS", W.war_leaderboard(m))
            self.assertIn("overall #1/", [t for c, t in tg.msgs if c == "1"][-1])
        finally:
            hooks.SQUADS_PATH = hp


class ManualLaunch(unittest.TestCase):
    def test_manual_launch_and_auto_start(self):
        import tempfile, pathlib
        from datetime import datetime, timedelta
        from core import districtwar as W, config
        tmp = tempfile.TemporaryDirectory(); W.PATH = pathlib.Path(tmp.name) / "w.json"
        config.BOT_USERNAME = "StudentUpBot"

        class KV:
            def save(self): pass

        class M:
            members = {"1": {"registered": True, "district": "Warangal"}, "2": {"registered": True, "district": "Guntur"},
                       "3": {"registered": False}}
            kv = KV()

        class TG:
            def __init__(self): self.sent = []; self.polls = 0
            def send_message(self, c, t, **k): self.sent.append((str(c), t, k.get("buttons")))
            def polite_gap(self, a=False): pass
            def _call(self, m, p, **k):
                self.polls += 1; return {"ok": True, "result": {"poll": {"id": f"p{self.polls}"}}}
            def admin_notify(self, t): self.sent.append(("admin", t, None))

        class Bank:
            def pick(self, ch, n): return []
            def pick_adaptive(self, *a, **k): return []
            questions = []
        tg = TG(); now = datetime(2026, 9, 13, 18, 0, tzinfo=config.IST)
        ok, txt = W.manual_launch(M(), tg, bank=None, minutes=5, now=now)
        self.assertTrue(ok); self.assertIn("2 fighters alerted", txt)
        chan = [s for s in tg.sent if s[0].startswith("@") or s[0].startswith("-")]
        self.assertEqual(len(chan), len(config.WAR_CHANNELS)); self.assertIn("start=war", chan[0][2][0][0][1])
        W.lobby_join(M(), "1"); W.lobby_join(M(), "2")
        self.assertIn("Lobby OPEN", W.owner_status(M()))
        self.assertFalse(W.maybe_auto_start(Bank(), M(), tg, now=now + timedelta(minutes=2)))   # not yet
        # at start time: compose() finds no questions in the fake bank → not started, admin notified, lobby closed
        W.maybe_auto_start(Bank(), M(), tg, now=now + timedelta(minutes=6))
        self.assertFalse(W.lobby_status()["open"])
        self.assertTrue(any(s[0] == "admin" for s in tg.sent))
        tmp.cleanup()
