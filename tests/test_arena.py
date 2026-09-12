import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, arena, hooks


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        self.members = {str(i): {"registered": True, "name": f"P{i}", "district": "Warangal" if i < 3 else "Guntur",
                                 "points": 0, "exam": "TSPSC"} for i in range(1, 6)}
        self.data = {"rounds": {}}
    def _get(self, uid): return self.members.setdefault(str(uid), {})
    def add_referral(self, a, b): pass


class _Bank:
    def __init__(self): self.n = 0
    def pick(self, ch, n):
        out = []
        for _ in range(n):
            self.n += 1
            out.append({"id": f"q{self.n}", "q_en": f"Q{self.n}?", "q_te": f"ప్ర{self.n}?", "difficulty": "easy",
                        "options_en": ["a", "b", "c", "d"], "answer_index": 1, "topic": "polity"})
        return out


class _TG:
    def __init__(self): self.msgs = []; self.polls = []; self.pid = 0
    def send_message(self, chat, text, **kw): self.msgs.append((str(chat), text)); return {"ok": True}
    def _call(self, method, payload, **kw):
        self.pid += 1
        self.polls.append((payload["chat_id"], payload["question"]))
        return {"result": {"poll": {"id": f"pl{self.pid}"}}}


class TestArena(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._o = (arena.PATH, hooks.SQUADS_PATH)
        arena.PATH = self.tmp / "a.json"; hooks.SQUADS_PATH = self.tmp / "s.json"
        self.m, self.b, self.tg = _Members(), _Bank(), _TG()
        hooks.squad_create(self.m, "1", "Warangal Warriors"); hooks.squad_join(self.m, "2", hooks._sq()["by_uid"]["1"])
        hooks.squad_create(self.m, "4", "Guntur Giants"); hooks.squad_join(self.m, "5", hooks._sq()["by_uid"]["4"])

    def tearDown(self):
        arena.PATH, hooks.SQUADS_PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)

    def _poll_for(self, uid):
        d = arena._load()
        for pid, (code, qi, owner) in d["polls"].items():
            if owner == str(uid) and qi == d["rooms"][code]["qi"]:
                return pid
        return None

    def test_full_match(self):
        r, msg = arena.room_new(self.m, "1", 5)
        self.assertIsNotNone(r); code = r["code"]
        self.assertIsNone(arena.room_new(self.m, "3", 5)[0])          # no squad
        self.assertIsNone(arena.room_join(self.m, "5", code)[0])       # not leader
        r2, msg2 = arena.room_join(self.m, "4", code)
        self.assertEqual(len(r2["squads"]), 2)
        self.assertIn(code, arena.list_rooms())
        r3, err = arena.room_start(self.b, uid="1")
        self.assertIsNone(err); self.assertEqual(r3["state"], "countdown"); self.assertEqual(r3["n_q"], 5)
        now = datetime.now(config.IST)
        # countdown → Q1
        arena.tick(self.b, self.tg, self.m, now=now + timedelta(seconds=arena.COUNTDOWN_SEC + 1))
        self.assertEqual(arena._load()["rooms"][code]["state"], "question")
        self.assertEqual(len(self.tg.polls), 4)                        # 4 players got Q1
        # Warriors both right (fast), Giants: one right, one wrong
        for uid, ans in (("1", 1), ("2", 1), ("4", 1), ("5", 0)):
            self.assertTrue(arena.record_answer(self.m, self.tg, self._poll_for(uid), uid, ans))
        self.assertTrue(arena.record_answer(self.m, self.tg, self._poll_for("1"), "1", 1))   # dup ignored
        # all answered → close immediately on tick → gap + scoreboard broadcast
        arena.tick(self.b, self.tg, self.m, now=now + timedelta(seconds=arena.COUNTDOWN_SEC + 5))
        d = arena._load(); r = d["rooms"][code]
        self.assertEqual(r["state"], "gap")
        self.assertTrue(any("After Q1/5" in t for _, t in self.tg.msgs))
        self.assertEqual(r["players"]["5"]["pts"], arena.PTS_WRONG)
        self.assertGreater(r["players"]["1"]["pts"], arena.PTS_CORRECT)
        # run remaining questions: nobody answers, windows expire
        t = now + timedelta(seconds=arena.COUNTDOWN_SEC + 5)
        for _ in range(4):
            t += timedelta(seconds=arena.GAP_SEC + 1); arena.tick(self.b, self.tg, self.m, now=t)
            self.assertEqual(arena._load()["rooms"][code]["state"], "question")
            t += timedelta(seconds=80); arena.tick(self.b, self.tg, self.m, now=t)
        t += timedelta(seconds=arena.GAP_SEC + 1); arena.tick(self.b, self.tg, self.m, now=t)
        d = arena._load(); r = d["rooms"][code]
        self.assertEqual(r["state"], "done")
        self.assertTrue(any("WINNER: Warangal Warriors" in t for _, t in self.tg.msgs))
        self.assertEqual(self.m.members["1"]["points"], arena.REWARD_WIN + arena.REWARD_MVP)   # winner + MVP
        self.assertEqual(self.m.members["4"]["points"], arena.REWARD_SECOND)
        w, g = hooks._sq()["by_uid"]["1"], hooks._sq()["by_uid"]["4"]
        self.assertGreater(d["elo"][w], arena.ELO_START); self.assertLess(d["elo"][g], arena.ELO_START)
        so = arena.pop_shoutouts()
        self.assertEqual(so[0]["winner"], "Warangal Warriors"); self.assertEqual(arena.pop_shoutouts(), [])
        self.assertIn("Warangal Warriors", arena.render_top(self.m))
        self.assertEqual(self.b.n, 5)                                   # questions came via bank.pick (no-repeat)

    def test_autostart_and_ttl(self):
        r, _ = arena.room_new(self.m, "1", 5); code = r["code"]
        arena.room_join(self.m, "4", code)
        now = datetime.now(config.IST)
        arena.tick(self.b, self.tg, self.m, now=now + timedelta(seconds=arena.LOBBY_AUTOSTART_SEC + 1))
        self.assertEqual(arena._load()["rooms"][code]["state"], "countdown")
        arena.room_leave("1")   # match running → refused
        self.assertEqual(arena._load()["rooms"][code]["state"], "countdown")

    def test_fair_scaling(self):
        r = {"squads": {"A": {"name": "A", "members": ["1", "2"]}, "B": {"name": "B", "members": ["4", "5", "3"]}},
             "players": {"1": {"pts": 100}, "2": {"pts": 100}, "4": {"pts": 80}, "5": {"pts": 80}, "3": {"pts": 80}}}
        rows = arena._squad_scores(r)
        self.assertEqual(rows[0][2], "A")      # 200*5/2=500 beats 240*5/3=400

    def test_tournament(self):
        for i in (6, 7, 8, 9):
            self.m.members[str(i)] = {"registered": True, "name": f"P{i}", "district": "Nellore", "points": 0, "exam": "SSC"}
        hooks.squad_create(self.m, "6", "C"); hooks.squad_join(self.m, "7", hooks._sq()["by_uid"]["6"])
        hooks.squad_create(self.m, "8", "D"); hooks.squad_join(self.m, "9", hooks._sq()["by_uid"]["8"])
        created, txt = arena.tournament_create(self.b, self.m)
        self.assertEqual(len(created), 2); self.assertIn("Round 1", txt)


if __name__ == "__main__":
    unittest.main()
