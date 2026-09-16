#!/usr/bin/env python3
"""
STUDENTUP — COLLEGE CUP TESTS (cricket-style knockout between colleges)
Verifies: seeded bracket order, byes for non-power-of-2 draws, parallel match
events, winner advancement, auto next-round creation, champion crowning with
rewards + MVP, walkovers, and cup rendering.
Run:  python3 -m unittest -v tests.test_cup
"""
import sys
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import config          # noqa: E402
from core import cup             # noqa: E402
from core import campus          # noqa: E402


class _KV:
    def save(self):
        pass


class _Members:
    def __init__(self, colleges=()):
        self.kv = _KV()
        self.members = {}
        for i, col in enumerate(colleges, 1):
            self.members[str(i)] = {"registered": True, "name": f"S{i}", "college": col,
                                    "points": 0, "district": "Warangal"}

    def _get(self, uid):
        return self.members.setdefault(str(uid), {"registered": True, "points": 0})


def _event(code, colleges_scores):
    """Fake finished campus event: {college: (pts_sum, players)}."""
    players = {}
    n = 0
    for col, (pts, k) in colleges_scores.items():
        for j in range(k):
            n += 1
            players[str(1000 + n)] = {"college": col, "name": f"P{col[:2]}{n}",
                                      "pts": pts // max(k, 1), "correct": 5,
                                      "answered": 5, "last": "t"}
    return {"code": code, "players": players, "questions": list(range(15))}


class TestBracketMath(unittest.TestCase):
    def test_seed_order(self):
        self.assertEqual(cup.seed_order(2), [1, 2])
        self.assertEqual(cup.seed_order(4), [1, 4, 2, 3])
        self.assertEqual(cup.seed_order(8), [1, 8, 4, 5, 2, 7, 3, 6])
        o16 = cup.seed_order(16)
        self.assertEqual(sorted(o16), list(range(1, 17)))
        # seed 1 meets seed 16, classic cricket/IPL pairing
        self.assertEqual(o16[:2], [1, 16])

    def test_labels(self):
        self.assertIn("FINAL", cup.label_for(1))
        self.assertIn("SEMI", cup.label_for(2))
        self.assertIn("QUARTER", cup.label_for(4))
        self.assertIn("ROUND OF 16", cup.label_for(8))


class TestCup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cup_old, self._campus_old = cup.PATH, campus.PATH
        cup.PATH = self.tmp / "cup.json"
        campus.PATH = self.tmp / "campus.json"

    def tearDown(self):
        cup.PATH, campus.PATH = self._cup_old, self._campus_old

    def test_guards(self):
        code, msg = cup.cup_new("Warangal", ["A", "B"])
        self.assertIsNone(code)                     # need >= 3 colleges
        self.assertIn("కనీసం", msg)
        code, msg = cup.cup_new("Warangal", [f"C{i}" for i in range(17)])
        self.assertIsNone(code)                     # max 16

    def test_ten_colleges_byes_and_parallel_round1(self):
        cols = [f"College{i}" for i in range(1, 11)]
        code, msg = cup.cup_new("Warangal", cols, name="Test Cup", created_by="9")
        self.assertTrue(code.startswith("CUP-"))
        d = cup._load()
        c = d["cups"][code]
        r1 = c["rounds"][0]
        self.assertIn("ROUND OF 16", r1["label"])
        self.assertEqual(len(r1["pairs"]), 8)       # bracket of 16 slots
        byes = [p for p in r1["pairs"] if p["bye"]]
        live = [p for p in r1["pairs"] if not p["bye"]]
        self.assertEqual(len(byes), 6)              # 16 - 10 = 6 byes
        self.assertEqual(len(live), 2)              # only 2 real matches in R1
        self.assertEqual({p["winner"] for p in byes},
                         {"College1", "College2", "College3", "College4", "College5", "College6"})
        # parallel: every live match already has its own campus event
        ev = campus._load()["events"]
        self.assertEqual(len(ev), 2)
        for p in live:
            self.assertIn(p["event"], ev)
            self.assertEqual(ev[p["event"]].get("cup"), code)
            self.assertEqual(len(ev[p["event"]]["colleges"]), 2)

    def test_full_run_to_champion_with_rewards(self):
        # 4 colleges → clean semis + final (no byes)
        cols = ["Alpha", "Beta", "Gamma", "Delta"]
        members = _Members(colleges=["Alpha", "Alpha", "Beta"])   # 2 Alpha students, 1 Beta
        code, _ = cup.cup_new("Warangal", cols, name="District Cup", created_by="9")
        d = cup._load()
        c = d["cups"][code]
        self.assertIn("SEMI", c["rounds"][0]["label"])
        # play the two semis: Alpha beats Delta; Gamma beats Beta
        r1 = c["rounds"][0]["pairs"]
        ev = campus._load()["events"]
        for p in r1:
            win = "Alpha" if "Alpha" in (p["a"], p["b"]) else "Gamma"
            lose = p["b"] if win == p["a"] else p["a"]
            fake = _event(p["event"], {win: (100, 2), lose: (40, 2)})
            cup.on_event_done(members, fake)
        d = cup._load()
        c = d["cups"][code]
        self.assertEqual(len(c["rounds"]), 2)                    # FINAL auto-created
        fin = c["rounds"][1]
        self.assertIn("FINAL", fin["label"])
        self.assertEqual(len(fin["pairs"]), 1)
        self.assertEqual({fin["pairs"][0]["a"], fin["pairs"][0]["b"]}, {"Alpha", "Gamma"})
        # Alpha wins the final
        fp = fin["pairs"][0]
        win, lose = "Alpha", "Gamma"
        fake = _event(fp["event"], {win: (90, 2), lose: (30, 2)})
        cup.on_event_done(members, fake)
        d = cup._load()
        c = d["cups"][code]
        self.assertEqual(c["state"], "done")
        self.assertEqual(c["champion"], "Alpha")
        self.assertEqual(c["runner"], "Gamma")
        # rewards: both Alpha members +50
        self.assertEqual(members.members["1"]["points"], cup.CHAMPION_PTS)
        self.assertEqual(members.members["2"]["points"], cup.CHAMPION_PTS)
        # champion announcement queued for the hub channels
        self.assertTrue(any(a["to"] == "hub" and "CHAMPION" in a["text"] for a in c["announce"]))

    def test_walkover_when_nobody_answers(self):
        cols = ["One", "Two", "Three"]
        code, _ = cup.cup_new("Guntur", cols)
        d = cup._load()
        c = d["cups"][code]
        live = [p for p in c["rounds"][0]["pairs"] if not p["bye"]]
        self.assertEqual(len(live), 1)                 # 3 colleges → 1 match + 1 bye
        e = _event(live[0]["event"], {})               # zero players
        cup.on_event_done(_Members(), e)
        d = cup._load()
        pairs = d["cups"][code]["rounds"][0]["pairs"]
        p = next(x for x in pairs if x.get("event") == live[0]["event"])
        self.assertTrue(p["winner"])                   # walkover winner, cup not stuck
        self.assertIn("walkover", p["score"])

    def test_render_bracket(self):
        code, _ = cup.cup_new("Siddipet", ["A", "B", "C", "D"], name="Render Cup")
        txt = cup.render_cup(code)
        self.assertIn("Render Cup", txt)
        self.assertIn("SEMI", txt)
        self.assertIn("vs", txt)
        self.assertIn("/campus start", txt)             # actionable next step
        self.assertIn("దొరకలేదు", cup.render_cup("CUP-ZZZZ"))


class TestCupWizardMode(unittest.TestCase):
    """The campus wizard offers CUP vs WAR when >=3 colleges are collected."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._campus_old = campus.PATH
        campus.PATH = self.tmp / "campus.json"

    def tearDown(self):
        campus.PATH = self._campus_old

    def test_wizard_collects_many_colleges(self):
        campus.wiz_start(5)
        campus.wiz_set(5, name="SR College", colleges=["SR College"], step="more")
        wz = campus.wiz_get(5)
        cols = wz["colleges"] + ["Vignan"]
        campus.wiz_set(5, colleges=cols, step="more")
        wz = campus.wiz_get(5)
        self.assertEqual(wz["colleges"], ["SR College", "Vignan"])
        self.assertEqual(wz["step"], "more")

    def test_wizard_cup_kind_flag(self):
        """Zero-typing cup flow: /cup new starts the wizard in kind=cup mode."""
        campus.wiz_start(6)
        campus.wiz_set(6, kind="cup")
        self.assertEqual(campus.wiz_get(6)["kind"], "cup")


class TestCupOps(unittest.TestCase):
    """Progress display, ping targets, and buttons for running a cup."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cup_old, self._campus_old = cup.PATH, campus.PATH
        cup.PATH = self.tmp / "cup.json"
        campus.PATH = self.tmp / "campus.json"

    def tearDown(self):
        cup.PATH, campus.PATH = self._cup_old, self._campus_old

    def test_progress_ping_and_buttons(self):
        code, _ = cup.cup_new("Warangal", ["A", "B", "C", "D"], name="Ops Cup")
        c = cup._load()["cups"][code]
        label, done, total = cup.cup_progress(c)
        self.assertIn("SEMI", label)
        self.assertEqual((done, total), (0, 2))
        # both semis are open → both are ping targets
        targets = cup.cup_ping_targets(code)
        self.assertEqual(len(targets), 2)
        # buttons: refresh + ping + panel
        flat = [cb for row in cup.cup_buttons(code) for _lab, cb in row]
        self.assertTrue(any(x.startswith("cupc:ping:") for x in flat))
        self.assertTrue(any(x.startswith("cupc:bracket:") for x in flat))
        # render shows the live progress line
        txt = cup.render_cup(code)
        self.assertIn("0/2", txt)
        self.assertIn("Now:", txt)


class TestSmartPanelRefresh(unittest.TestCase):
    """Button taps must NEVER spam duplicate panels:
    edit in place; if nothing changed → do nothing; only send on real errors."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._campus_old = campus.PATH
        campus.PATH = self.tmp / "campus.json"
        import bot as botmod
        self.botmod = botmod

    def tearDown(self):
        campus.PATH = self._campus_old

    def _bot(self, raise_msg=None):
        class _TG:
            def __init__(self):
                self.raised = raise_msg
                self.sent, self.edited = [], []

            def _call(self, method, payload):
                if self.raised:
                    from core.telegram import TelegramError
                    raise TelegramError(self.raised)
                self.edited.append(payload)
                return {"ok": True}

            def send_message(self, chat, text, **kw):
                self.sent.append((chat, text))
                return {}

        class _Members:
            members = {}

        b = object.__new__(self.botmod.Bot)
        b.members = _Members()
        b.tg = _TG()
        return b

    def test_edit_in_place(self):
        b = self._bot()
        b._refresh_panel({"message": {"message_id": 5}}, "123", None)
        self.assertEqual(len(b.tg.edited), 1)
        self.assertEqual(b.tg.sent, [])                 # no new message

    def test_not_modified_never_duplicates(self):
        b = self._bot("Bad Request: message is not modified")
        b._refresh_panel({"message": {"message_id": 5}}, "123", None)
        self.assertEqual(b.tg.sent, [])                 # identical → silence
        self.assertEqual(b.tg.edited, [])

    def test_real_error_falls_back_to_send(self):
        b = self._bot("Bad Request: message identifier is not specified")
        b._refresh_panel({}, "123", None)               # no message_id → send
        self.assertEqual(len(b.tg.sent), 1)


if __name__ == "__main__":
    unittest.main()
