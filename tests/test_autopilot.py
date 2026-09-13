import sys, unittest, tempfile, shutil
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from core import config, autopilot as A, campus as C


class _KV:
    def save(self): pass


class _Members:
    def __init__(self):
        self.kv = _KV()
        now = datetime.now(config.IST)
        d = lambda n: (now - timedelta(days=n)).strftime("%Y-%m-%d")
        self.members = {"1": {"registered": True, "name": "Ravi", "district": "Warangal", "exam": "TSPSC", "points": 100, "last_active": d(0),
                              "topics": {"polity": {"correct": 1, "total": 5}, "history": {"correct": 9, "total": 10}}},
                        "2": {"registered": True, "name": "Sita", "district": "Guntur", "exam": "Banking", "points": 40, "last_active": d(3)},
                        "3": {"registered": True, "name": "Kiran", "district": "Guntur", "exam": "SSC", "points": 10, "last_active": d(21)},
                        "4": {"registered": True, "name": "B", "dm_blocked": True, "last_active": d(3)}}
        self.data = {"rounds": {"C" + now.strftime("%Y%m%d"): {"by_channel": {"TSPSC": {"1": {"correct": 2, "total": 3}}}}}}
    def _get(self, u): return self.members.setdefault(str(u), {})
    def weak_topics(self, uid, limit=3, weak_below=0.75):
        m = self.members.get(str(uid), {})
        return [t for t, s in (m.get("topics") or {}).items() if s["correct"] / max(s["total"], 1) < weak_below][:limit]


class _Bank:
    n = 0
    def unused(self, ch): return [1] * (10 if ch == "BANKING" else 500)
    def pick_adaptive(self, ch, weak_topics=None, review_qids=None):
        _Bank.n += 1
        return {"id": f"q{_Bank.n}", "q_en": "Q?", "q_te": "ప్ర?", "options_en": ["a", "b", "c", "d"], "options_te": ["అ", "ఆ", "ఇ", "ఈ"], "answer_index": 1, "topic": "polity"}
    def pick(self, ch, n=1): return [self.pick_adaptive(ch)]


class _TG:
    def __init__(self): self.msgs = []; self.polls = 0
    def send_message(self, c, t, **k): self.msgs.append((str(c), t))
    def _call(self, m, p, **k): self.polls += 1; return {"result": {"poll": {"id": f"p{self.polls}"}}}


class TestAutopilot(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self._o = (A.PATH, C.PATH); A.PATH = self.tmp / "a.json"; C.PATH = self.tmp / "c.json"
        self._rp = config.DATA / "round_polls.json"; self._rp_bak = self._rp.read_bytes() if self._rp.exists() else None
    def tearDown(self):
        A.PATH, C.PATH = self._o; shutil.rmtree(self.tmp, ignore_errors=True)
        if self._rp_bak is not None: self._rp.write_bytes(self._rp_bak)

    def test_heal_coach_winback_report(self):
        m, tg, bank = _Members(), _TG(), _Bank()
        code = C.quick_event("Old College", "Warangal", 5, "easy", "adm")
        d = C._load(); d["events"][code]["created"] = (A._now() - timedelta(hours=13)).isoformat(); C._save(d)
        done = A.heal(bank, m, tg, dry=True)
        self.assertTrue(any("low stock" in x and "BANKING" in x for x in done))
        self.assertTrue(any("auto-closed" in x for x in done))
        self.assertEqual(C._load()["events"][code]["state"], "cancelled")
        self.assertFalse(any("low stock" in x for x in A.heal(bank, m, tg, dry=True)))       # once a day
        # coach: only active (≤14d) + not blocked → 1 and 2
        self.assertEqual(sorted(A.coach_targets(m)), ["1", "2"])
        n = A.coach_round(bank, m, tg)
        self.assertEqual(n, 2); self.assertEqual(tg.polls, 2 * A.COACH_Q)
        self.assertTrue(any("Weak topics: Polity" in t for c, t in tg.msgs if c == "1"))
        self.assertEqual(A.coach_round(bank, m, tg), 0)                                      # once a day
        played, badges = A.coach_streaks(m, tg)
        self.assertEqual(played, 1); self.assertEqual(m.members["1"]["coach_streak"], 1)
        m.members["1"]["coach_streak"] = 4; A._load(); 
        # win-back: 2 (3d) and 3 (21d), never 4 (blocked) or 1 (active)
        tg.msgs.clear()
        self.assertEqual(A.winback(m, tg), 2)
        self.assertTrue(any(c == "2" and "3 రోజులు" in t for c, t in tg.msgs))
        self.assertTrue(any(c == "3" and "చివరి" in t for c, t in tg.msgs))
        self.assertEqual(A.winback(m, tg), 0)
        rep = A.night_report(m, tg, dry=True)
        self.assertIn("coach", rep); self.assertIn("win-back", rep); self.assertIn("auto-closed", rep)

    def test_countdown(self):
        m, tg = _Members(), _TG()
        old = config.EXAM_DATES
        config.EXAM_DATES = f"TSPSC={(A._now() + timedelta(days=7)).date().isoformat()}"
        try:
            self.assertEqual(A.exam_countdown(m, tg), 1)
            self.assertIn("D-7", tg.msgs[-1][1]); self.assertEqual(tg.msgs[-1][0], "1")
        finally:
            config.EXAM_DATES = old


if __name__ == "__main__":
    unittest.main()
