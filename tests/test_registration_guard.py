#!/usr/bin/env python3
"""
STUDENTUP — ONE-TIME REGISTRATION + DUPLICATE GUARDS + RECORDING TESTS
Verifies:
  * registration is strictly one-time (never re-asked once registered)
  * one mobile = one account (duplicate number blocked, holder shown, no 2nd account)
  * register() never assigns a mobile that belongs to another member
  * squad codes display as SQ-XXXX and join accepts prefixed/messy codes
  * District War publishes each district's TOP-2 heroes
  * campus college-add wizard state machine (phone-friendly event creation)
Run:  python3 -m unittest -v tests.test_registration_guard
"""
import sys
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from core import config                     # noqa: E402
from core import hooks                      # noqa: E402
from core import campus                     # noqa: E402
from core import districtwar as W           # noqa: E402
from core.members import Members, norm_mobile  # noqa: E402


def _fresh_members():
    mb = Members()
    tmp = Path(tempfile.gettempdir()) / f"su_test_members_{tempfile.mktemp()[-6:]}.json"
    mb.kv.path = tmp
    mb.data = {"members": {}, "pending": {}}
    mb.members = mb.data["members"]
    mb.pending = mb.data["pending"]
    return mb


def _reg(mb, uid, name="User", district="Warangal", mobile=""):
    """Fast-path a full registration."""
    mb.start_registration(uid)
    mb.registration_input(uid, name)
    mb.registration_input(uid, "TS")
    mb.registration_input(uid, district)
    mb.registration_input(uid, "UG")
    s, _ = mb.registration_input(uid, mobile or "skip")
    assert s == "done", s
    return mb.members[str(uid)]


class TestNormMobile(unittest.TestCase):
    def test_normalizes(self):
        self.assertEqual(norm_mobile("+91 93944-83300"), "9394483300")
        self.assertEqual(norm_mobile("9394483300"), "9394483300")
        self.assertEqual(norm_mobile("09394483300x"), "")
        self.assertEqual(norm_mobile("12345"), "")
        self.assertEqual(norm_mobile(""), "")
        self.assertEqual(norm_mobile(None), "")


class TestOneTimeRegistration(unittest.TestCase):
    def setUp(self):
        self.mb = _fresh_members()

    def tearDown(self):
        try:
            self.mb.kv.path.unlink()
        except Exception:
            pass

    def test_start_registration_refuses_registered(self):
        _reg(self.mb, 11, mobile="9876543210")
        # registered member triggers /register again → must NOT start a form
        self.assertFalse(self.mb.start_registration(11))
        self.assertIsNone(self.mb.pending_step(11))
        txt = self.mb.already_registered_text(11)
        self.assertIn("ఇప్పటికే", txt)          # "already registered" (Telugu)
        self.assertIn("9876543210", txt)

    def test_start_registration_keeps_progress(self):
        self.assertTrue(self.mb.start_registration(12))
        self.mb.registration_input(12, "Half Way")
        # a second /register mid-form must not wipe the entered name
        self.assertTrue(self.mb.start_registration(12))
        self.assertEqual(self.mb.pending_step(12).get("name"), "Half Way")

    def test_duplicate_mobile_blocked(self):
        _reg(self.mb, 21, name="Charan", district="Siddipet", mobile="9394483300")
        # second person tries the SAME number
        self.mb.start_registration(22)
        self.mb.registration_input(22, "Mahesh")
        self.mb.registration_input(22, "TS")
        self.mb.registration_input(22, "Warangal")
        self.mb.registration_input(22, "UG")
        status, reply = self.mb.registration_input(22, "9394483300")
        self.assertEqual(status, "duplicate")
        self.assertIn("Charan", reply)
        self.assertIn("Siddipet", reply)
        # no second account was created; holder untouched
        self.assertFalse(self.mb.is_registered(22))
        self.assertEqual(self.mb.members["21"]["mobile"], "9394483300")
        # user stays in the mobile step → can send another number or skip
        dup = self.mb.pending_step(22).get("last_dup") or {}
        self.assertEqual(dup.get("holder"), "21")
        status, _ = self.mb.registration_input(22, "skip")
        self.assertEqual(status, "done")
        self.assertTrue(self.mb.is_registered(22))
        self.assertEqual(self.mb.members["22"]["mobile"], "")

    def test_duplicate_then_fresh_number_ok(self):
        _reg(self.mb, 31, mobile="9000000001")
        self.mb.start_registration(32)
        self.mb.registration_input(32, "Ravi")
        self.mb.registration_input(32, "TS")
        self.mb.registration_input(32, "Karimnagar")
        self.mb.registration_input(32, "UG")
        s, _ = self.mb.registration_input(32, "9000000001")
        self.assertEqual(s, "duplicate")
        s, _ = self.mb.registration_input(32, "9000000002")
        self.assertEqual(s, "done")
        self.assertEqual(self.mb.members["32"]["mobile"], "9000000002")
        self.assertEqual(self.mb.find_by_mobile("9000000002"), "32")

    def test_register_defends_mobile_conflict(self):
        _reg(self.mb, 41, mobile="8000000001")
        # direct register() call (e.g. form import) with someone else's number
        self.mb.register(42, name="Intruder", exam="TSPSC", mobile="8000000001")
        self.assertNotEqual(self.mb.members["42"].get("mobile"), "8000000001")
        self.assertEqual(self.mb.members["42"].get("mobile_conflict_with"), "41")
        # same member re-registering own number is fine
        self.mb.register(41, name="Self", mobile="8000000001")
        self.assertEqual(self.mb.members["41"]["mobile"], "8000000001")


class TestSquadCodes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "squads.json"
        self._old = hooks.SQUADS_PATH
        hooks.SQUADS_PATH = self.tmp
        self.mb = _fresh_members()

    def tearDown(self):
        hooks.SQUADS_PATH = self._old
        try:
            self.mb.kv.path.unlink()
        except Exception:
            pass

    def test_create_shows_sq_prefix_and_join_accepts_it(self):
        _reg(self.mb, 51, name="Leader", mobile="7000000001")
        _reg(self.mb, 52, name="Friend", mobile="7000000002")
        code, msg = hooks.squad_create(self.mb, 51, "Warriors")
        self.assertEqual(len(code), 4)
        self.assertIn(f"SQ-{code}", msg)
        # friend joins typing the messy prefixed code a phone user would send
        s, join_msg = hooks.squad_join(self.mb, 52, f"  sq-{code.lower()} ")
        self.assertIsNotNone(s, join_msg)
        self.assertIn("Warriors", join_msg)
        self.assertEqual(hooks._sq()["by_uid"]["52"], code)

    def test_join_bad_code(self):
        _reg(self.mb, 53, mobile="7000000003")
        s, msg = hooks.squad_join(self.mb, 53, "SQ-ZZZZ")
        self.assertIsNone(s)
        self.assertIn("దొరకలేదు", msg)


class TestDistrictHeroes(unittest.TestCase):
    def _live(self):
        return {"questions": list(range(10)), "fighters": {
            "1": {"district": "Warangal", "pts": 50, "correct": 5, "answered": 10},
            "2": {"district": "Warangal", "pts": 40, "correct": 4, "answered": 10},
            "3": {"district": "Warangal", "pts": 30, "correct": 3, "answered": 10},
            "4": {"district": "Guntur", "pts": 45, "correct": 4, "answered": 10},
            "5": {"district": "Guntur", "pts": 44, "correct": 4, "answered": 10},
            "6": {"district": "Siddipet", "pts": 10, "correct": 1, "answered": 0},
        }}

    def test_top2_per_district(self):
        heroes = W.district_heroes(self._live(), None, per=2)
        got = {d: [u for u, _ in hs] for d, hs in heroes}
        self.assertEqual(got["Warangal"], ["1", "2"])       # top-2 only, not 3rd
        self.assertEqual(got["Guntur"], ["4", "5"])
        self.assertNotIn("Siddipet", got)                    # never answered

    def test_result_post_contains_heroes_section(self):
        mb = _fresh_members()
        for u, d in [("1", "Warangal"), ("2", "Warangal"), ("3", "Warangal"),
                     ("4", "Guntur"), ("5", "Guntur")]:
            mb.members[u] = {"name": f"P{u}", "district": d, "registered": True, "points": 0}
        live = self._live()
        rows = W.district_table(live, mb)
        season = {"wins": {}, "points": {}}
        from datetime import datetime
        txt = W.render_result(live, rows, mb, "1", season, datetime.now(config.IST))
        self.assertIn("జిల్లా హీరోలు", txt)
        self.assertIn("Warangal: 1. P1", txt)
        self.assertIn("Guntur: 1. P4", txt)


class TestCampusWizard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "campus.json"
        self._old = campus.PATH
        campus.PATH = self.tmp

    def tearDown(self):
        campus.PATH = self._old

    def test_wizard_roundtrip(self):
        self.assertIsNone(campus.wiz_get(7))
        campus.wiz_start(7)
        self.assertEqual(campus.wiz_get(7)["step"], "name")
        campus.wiz_set(7, name="SR College", step="state")
        campus.wiz_set(7, state_code="TS", step="district")
        wz = campus.wiz_get(7)
        self.assertEqual(wz["name"], "SR College")
        self.assertEqual(wz["state_code"], "TS")
        campus.wiz_clear(7)
        self.assertIsNone(campus.wiz_get(7))

    def test_panel_has_new_button(self):
        btns = campus.panel_buttons()
        flat = [label for row in btns for label, _cb in row]
        self.assertTrue(any("New college event" in f for f in flat))


class TestStudentCreatedWars(unittest.TestCase):
    """Students request a college war; staff one-tap approve creates the event."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "campus.json"
        self._old = campus.PATH
        campus.PATH = self.tmp

    def tearDown(self):
        campus.PATH = self._old

    def test_request_approve_creates_event(self):
        rid = campus.student_request(77, "SR College", "Warangal", name="Charan")
        self.assertTrue(rid.startswith("RQ-"))
        pend = campus.pending_requests()
        self.assertEqual([p[0] for p in pend], [rid])
        info = campus.request_act(rid, approve=True)
        self.assertTrue(info["approved"])
        code = info["code"]
        self.assertTrue(code.startswith("CE-"))
        e = campus._load()["events"][code]
        self.assertEqual(e["by"], "77")                    # student = organiser
        self.assertEqual(e["colleges"], ["SR College"])
        self.assertEqual(campus.pending_requests(), [])    # no longer pending
        self.assertIsNone(campus.request_act(rid))         # double-tap is a no-op

    def test_request_deny(self):
        rid = campus.student_request(78, "XYZ College", "Guntur")
        info = campus.request_act(rid, approve=False)
        self.assertFalse(info["approved"])
        self.assertEqual(info["request"]["status"], "denied")
        self.assertEqual(campus._load()["events"], {})


if __name__ == "__main__":
    unittest.main()
