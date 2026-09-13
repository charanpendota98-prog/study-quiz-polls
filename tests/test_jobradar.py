import sys, unittest, tempfile, pathlib
from datetime import date
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from core import jobradar as JR, jobs, config


class FakeMembers:
    def __init__(self, members):
        self.members = members
        class KV:
            def save(self_): pass
        self.kv = KV()


class TG:
    def __init__(self): self.sent = []
    def send_message(self, chat, text, **kw): self.sent.append((str(chat), text, kw.get("buttons")))
    def polite_gap(self, a=False): pass


def J(title, qual, last, cat="ts-ap", url="https://x/a", loc=""):
    return jobs.Job(title=title, url=url, source="T", category=cat, qualification=qual, last_date=last, location=loc)


class Radar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); JR.BOARD = pathlib.Path(self.tmp.name) / "b.json"
        self.today = date(2026, 9, 13)
        self.mem = FakeMembers({"1": {"registered": True, "name": "Ravi", "qualification": "INTER", "state": "Telangana", "points": 0},
                                "2": {"registered": True, "name": "Sita", "qualification": "PG", "state": "Andhra Pradesh", "points": 0},
                                "3": {"registered": True, "name": "Blk", "qualification": "UG", "dm_blocked": True}})

    def tearDown(self): self.tmp.cleanup()

    def test_min_qual(self):
        self.assertEqual(JR.min_qualification("Degree / Post Graduation"), "UG")
        self.assertEqual(JR.min_qualification("10th pass, ITI"), "SSC")
        self.assertEqual(JR.min_qualification("డిగ్రీ ఉత్తీర్ణత"), "UG")
        self.assertEqual(JR.min_qualification("Any Graduate"), "UG")
        self.assertEqual(JR.min_qualification(""), "")

    def test_record_and_matching(self):
        a = JR.record(J("TSPSC Group-4 2026", "Inter", "20-09-2026", loc="Telangana"), "card A")
        b = JR.record(J("APPSC Junior Lecturer", "PG", "25-09-2026", url="https://x/b", loc="Andhra Pradesh"), "card B")
        c = JR.record(J("SSC CGL 2026", "Degree", "01-10-2026", cat="central", url="https://x/c"), "card C")
        JR.record(J("Old job", "10th", "01-09-2026", url="https://x/d"), "card D")   # expired
        self.assertEqual((a, b, c), ("J1", "J2", "J3"))
        self.assertEqual(JR.record(J("TSPSC Group-4 2026", "Inter", "20-09-2026"), "again"), "J1")  # idempotent by url
        m1 = JR.matches(self.mem.members["1"], today=self.today)
        self.assertEqual([v["id"] for v in m1], ["J1"])          # INTER TS: not PG job, not degree job, not AP job
        m2 = JR.matches(self.mem.members["2"], today=self.today)
        self.assertEqual([v["id"] for v in m2], ["J2", "J3"])   # PG AP: AP job + central; TS-only job excluded
        txt = JR.radar_text(self.mem, "1", today=self.today)
        self.assertIn("J1", txt); self.assertIn("eligible open jobs: 1", txt)
        self.assertTrue(JR.radar_buttons(self.mem, "1", today=self.today))

    def test_track_apply_checklist_reminders(self):
        JR.record(J("TSPSC Group-4 2026", "Inter", "16-09-2026"), "card A")   # 3 days left
        self.assertIn("Tracking J1", JR.track("1", "J1"))
        self.assertIn("already", JR.track("1", "J1"))
        self.assertIn("Aadhaar", JR.checklist_text("J1"))
        tg = TG()
        self.assertEqual(JR.deadline_reminders(self.mem, tg, today=self.today), 1)
        self.assertEqual(JR.deadline_reminders(self.mem, tg, today=self.today), 0)   # once per stage
        self.assertEqual(JR.deadline_reminders(self.mem, tg, today=date(2026, 9, 15)), 1)  # 1-day stage
        self.assertIn("REMINDER", tg.sent[0][1])
        r = JR.applied(self.mem, "1", "J1")
        self.assertIn("+5 pts", r); self.assertEqual(self.mem.members["1"]["points"], 5)
        self.assertNotIn("J1", JR._load()["tracks"]["1"])       # applied → auto-untrack
        self.assertIn("Applied (1)", JR.mine_text("1", today=self.today))
        self.assertIn("J1", JR.stats_text(self.mem))

    def test_digest_respects_optout_and_blocked(self):
        JR.record(J("SSC MTS 2026", "10th", "30-09-2026", cat="central"), "card")
        JR.set_digest("2", False)
        tg = TG()
        n = JR.daily_digest(self.mem, tg, today=self.today)
        self.assertEqual(n, 1)                                     # only member 1 (2 opted out, 3 blocked)
        self.assertEqual(tg.sent[0][0], "1"); self.assertIn("JOB RADAR", tg.sent[0][1])
        self.assertEqual(JR.daily_digest(self.mem, tg, today=self.today), 0)   # once per day
        self.assertIn("ON", JR.set_digest("2", True))

    def test_job_card_and_start_arg(self):
        self.assertEqual(JR.parse_start_arg("job12"), "J12"); self.assertIsNone(JR.parse_start_arg("ref12"))
        JR.record(J("X", "Degree", "13-09-2026"), "the card")
        txt, btn = JR.job_card("J1", "1", today=self.today)
        self.assertIn("ఈరోజే", txt); self.assertIn("the card", txt); self.assertTrue(btn)
        self.assertIn("board లో లేదు", JR.job_card("J9")[0])

    def test_jobs_run_records_board(self):
        import core.jobs as jobs_mod
        old_state, old_collect = jobs_mod.STATE, jobs_mod.collect_jobs; jobs_mod.STATE = pathlib.Path(self.tmp.name) / "s.json"
        try:
            tg = TG()
            jobs_mod.collect_jobs = lambda fetch=None, **k: [J("TSPSC Group-4 2026 Notification apply online", "Inter", "20-09-2026")]
            n = jobs_mod.run(tg, dry=False, today=self.today)
            self.assertEqual(n, 1)
            self.assertEqual(len(JR._load()["jobs"]), 1)
        finally:
            jobs_mod.STATE = old_state; jobs_mod.collect_jobs = old_collect
    

if __name__ == "__main__":
    unittest.main()
