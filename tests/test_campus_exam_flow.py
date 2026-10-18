# -*- coding: utf-8 -*-
"""College Exam flow (dashboard Exam tab): structured marks, local QR, links.

Pins the fixes for: dashboard Report showing empty forever (text report fed
to a JSON table), QR depending on an external QR website, and join links
pointing at a guessed bot name."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from core import campus


class TestCampusExamFlow(unittest.TestCase):
    def setUp(self):
        self._old = campus.PATH
        self._tmp = tempfile.mkdtemp()
        campus.PATH = Path(self._tmp) / "campus.json"

    def tearDown(self):
        campus.PATH = self._old

    def _event_with_players(self):
        code = campus.new_event("Sri Chaitanya College", "Guntur",
                                ["Sri Chaitanya College"], n_q=10, level="easy",
                                created_by="999", mode="college")
        d = campus._load()
        e = d["events"][code]
        e["questions"] = [{"id": f"q{i}"} for i in range(10)]
        e["state"] = "done"
        e["players"] = {
            "111": {"college": "Sri Chaitanya College", "name": "Anitha", "pts": 130,
                    "correct": 9, "answered": 10, "joined": "x", "first": None, "last": None},
            "222": {"college": "Sri Chaitanya College", "name": "Ravi", "pts": 80,
                    "correct": 6, "answered": 10, "joined": "x", "first": None, "last": None},
            "333": {"college": "Sri Chaitanya College", "name": "", "pts": 0,
                    "correct": 0, "answered": 0, "joined": "x", "first": None, "last": None},
        }
        campus._save(d)
        return code

    def test_report_dict_marks(self):
        code = self._event_with_players()
        rep = campus.report_dict(code)
        self.assertEqual(rep["name"], "Sri Chaitanya College")
        self.assertEqual(rep["state"], "done")
        self.assertEqual(rep["players_count"], 3)   # joined
        self.assertEqual(rep["answered"], 2)        # only students who answered get marks rows
        top = rep["players"][0]
        self.assertEqual((top["name"], top["score"], top["total"], top["pts"]),
                         ("Anitha", 9, 10, 130))
        self.assertEqual(rep["players"][1]["name"], "Ravi")
        self.assertEqual(rep["average_pct"], 75)    # (9+6) of 20
        self.assertIsNone(campus.report_dict("CE-NOPE"))

    def test_qr_png_local(self):
        code = self._event_with_players()
        try:
            import qrcode  # noqa: F401
        except Exception:
            self.skipTest("qrcode not installed")
        data = campus.qr_png(code, bot="MyStudyBot")
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertGreater(len(data), 500)
        self.assertIsNone(campus.qr_png("CE-NOPE"))

    def test_deep_link_roundtrip(self):
        link = campus.deep_link("CE-K7P2", bot="MyStudyBot")
        self.assertEqual(link, "https://t.me/MyStudyBot?start=cK7P2-1")
        arg = link.split("start=", 1)[1]
        self.assertEqual(campus.parse_start_arg(arg), ("CE-K7P2", 1))

    def test_dashboard_wiring(self):
        src = (Path(__file__).resolve().parent.parent
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        self.assertIn("campus.report_dict(code)", src)       # marks actually reach the UI
        self.assertIn('"/api/campus/qr"', src)               # local QR endpoint
        self.assertIn('"/api/campus/start"', src)            # dashboard Start Exam
        self.assertIn('"/api/campus/excel"', src)            # marks sheet download
        seg = src.split('"/api/campus/create"', 1)[1][:1600]
        self.assertNotIn("qrserver", seg)                    # campus QR is generated locally
        self.assertIn("campus.deep_link(code, bot)", seg)
        self.assertIn("_bot_username()", src)                # links open the real bot


if __name__ == "__main__":
    unittest.main()
