import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, campus as C
from core.question_bank import Bank


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV(); self.members = {}
    def _get(self, uid): return self.members.setdefault(str(uid), {})


class _TG:
    dry = True
    def __init__(self): self.msgs = []; self.pid = 0
    def send_message(self, chat, text, **kw): self.msgs.append((str(chat), text))
    def _call(self, m, payload, **kw):
        self.pid += 1; return {"result": {"poll": {"id": f"c{self.pid}"}}}


class TestCampus(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self._o = C.PATH; C.PATH = self.tmp / "c.json"
        self._used = config.STORE_USED; config.STORE_USED = self.tmp / "used.json"
        self._sig = config.DATA / "shown_signatures.json"
        self._sig_bak = self._sig.read_bytes() if self._sig.exists() else None
    def tearDown(self):
        C.PATH = self._o; config.STORE_USED = self._used
        if self._sig_bak is not None: self._sig.write_bytes(self._sig_bak)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pid(self, d, code, uid):
        e = d["events"][code]
        for pid, (c, qi, owner) in d["polls"].items():
            if c == code and owner == uid and qi == e["qi"]:
                return pid

    def test_full_event(self):
        m, tg = _Members(), _TG()
        code = C.new_event("KU Fest", "Warangal", ["Kakatiya Univ", "SR College", "  "], 8, "medium", created_by="admin")
        self.assertIn(f"start=c{code[3:]}-2", C.links_text(code))
        self.assertEqual(C.parse_start_arg(f"c{code[3:]}-2"), (code, 2))
        self.assertIsNone(C.parse_start_arg("ref123"))
        # 5 students join: 3 KU, 2 SR
        for i, col in enumerate([1, 1, 1, 2, 2], 1):
            ok, txt, need = C.join(m, str(i), code, col, name_hint=f"S{i}")
            self.assertTrue(ok); self.assertTrue(need)
            m.members[str(i)].update({"registered": True, "name": f"S{i}"})
            C.on_registered(m, str(i))
        self.assertEqual(m.members["1"]["college"], "Kakatiya Univ"); self.assertEqual(m.members["1"]["district"], "Warangal")
        self.assertEqual(m.members["1"]["points"], C.JOIN_PTS)
        C.on_registered(m, "1"); self.assertEqual(m.members["1"]["points"], C.JOIN_PTS)     # bonus once
        self.assertIn("joined 5 · registered 5", C.status_text(m, code))
        ok, info = C.start(Bank(), m, tg, code)
        self.assertTrue(ok, info)
        d = C._load(); e = d["events"][code]
        n_q = len(e["questions"]); self.assertGreaterEqual(n_q, 5)
        for qi in range(n_q):
            d = C._load(); e = d["events"][code]
            ans = e["questions"][qi]["answer_index"]
            for u in "12345":
                # SR students (4,5) answer all right; KU: 1 right, 2 half, 3 wrong
                right = u in "45" or u == "1" or (u == "2" and qi % 2 == 0)
                C.record_answer(self._pid(d, code, u), u, ans if right else (ans + 1) % 4)
            d = C._load(); e = d["events"][code]
            e["state"] = "gap"; e["q_open"] = C._now().isoformat(); C._save(d)
            C.tick(tg, m, C._now() + timedelta(seconds=1))
        d = C._load(); e = d["events"][code]
        self.assertEqual(e["state"], "done")
        cols = C.college_table(e)
        self.assertEqual(cols[0]["college"], "SR College")
        post = e["_post"]
        for s_ in ("COLLEGE vs COLLEGE", "WINNER: SR College", "TOP 10", "S4", "join"):
            self.assertIn(s_, post)
        self.assertTrue(any(c == "admin" and "Full data" in t for c, t in tg.msgs))
        csv = C.csv_text(code); self.assertEqual(len(csv.splitlines()), 6); self.assertIn("SR College", csv)
        self.assertIn("College winner: SR College", C.channel_post(code))
        # SR students got podium + college win; points credited
        self.assertGreater(m.members["4"]["points"], C.JOIN_PTS + 100)
        self.assertIn("#5/5", [t for c, t in tg.msgs if c == "3"][-1])
        self.assertFalse(C.start(Bank(), m, tg, code)[0])                  # can't restart

    def test_join_closed_and_min_players(self):
        m, tg = _Members(), _TG()
        code = C.new_event("Solo", "Guntur", ["A"], 5)
        C.join(m, "1", code, 1); m.members["1"]["registered"] = True
        self.assertFalse(C.start(Bank(), m, tg, code)[0])
        self.assertFalse(C.join(m, "2", "CE-NOPE", 1)[0])


if __name__ == "__main__":
    unittest.main()


class TestQuick(TestCampus):
    def test_full_event(self): pass
    def test_join_closed_and_min_players(self): pass

    def test_quick_poster_myscore(self):
        m, tg = _Members(), _TG()
        code = C.quick_event("Vaagdevi College", "Warangal", 6, "easy", "adm")
        pt = C.poster_text(code)
        self.assertIn(f"start=c{code[3:]}-1", pt); self.assertIn("qrserver", pt)
        self.assertEqual(C.my_score(m, "1"), "మీరు ఇంకా ఏ campus event లో ఆడలేదు.")
        for i in "12":
            C.join(m, i, code, 1); m.members[i].update({"registered": True, "name": f"S{i}"})
        self.assertIn("state: open", C.status_text(m, code))
        ok, _ = C.start(Bank(), m, tg, code); self.assertTrue(ok)
        self.assertIn("result వచ్చాక", C.my_score(m, "1"))


class TestAfterEvent(TestCampus):
    def test_full_event(self): pass
    def test_join_closed_and_min_players(self): pass

    def test_quick_registration_flow_and_drip(self):
        from core.members import Members
        import core.members as MM
        # registration: name → qualification → mobile with quick prefill
        class KV:
            def save(self): pass
        mem = Members.__new__(Members); mem.kv = KV(); mem.members = {}; mem.pending = {}; mem.data = {}
        mem.form_pending = {}
        mem.start_registration("5", "u", quick={"state_code": "TS", "state": "Telangana", "district": "Warangal", "exam": "Current Affairs GK"})
        st, _ = mem.registration_input("5", "Ravi Kumar"); self.assertEqual(st, "ask_qualification")
        st, txt = mem.registration_input("5", "4"); self.assertEqual(st, "ask_mobile"); self.assertIn("3 of 3", txt)
        # drip
        m, tg = _Members(), _TG()
        code = C.quick_event("SR College", "Warangal", 5)
        for i in "12":
            C.join(m, i, code, 1); m.members[i].update({"registered": True, "name": f"S{i}"})
        d = C._load(); e = d["events"][code]
        e["state"] = "done"; e["finished"] = (C._now() - timedelta(days=1)).isoformat(); e["questions"] = [{}] * 5
        for p in e["players"].values(): p["answered"] = 5
        C._save(d)
        self.assertEqual(C.onboarding_drip(tg, m), 2)
        self.assertIn("District War", tg.msgs[-1][1])
        self.assertEqual(C.onboarding_drip(tg, m), 0)                     # once per day-N
        m.data = {"rounds": {C._now().strftime("%Y%m%d") + "-0900": {"by_channel": {"TSPSC": {"1": {"correct": 7, "total": 10}}}}}}
        lg = C.college_league(m); self.assertIn("SR College", lg); self.assertIn("7 ✅", lg)
