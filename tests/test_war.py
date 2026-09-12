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

    def test_full_war(self):
        m, tg = _Members(), _TG()
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


if __name__ == "__main__":
    unittest.main()
