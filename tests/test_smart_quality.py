# -*- coding: utf-8 -*-
"""Smart Quality round: campus result poster, WhatsApp group health,
broadcast preview, planner WhatsApp leg, members radar, multi-college."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core import campus as C
from core import planner


def _wp():
    from core import whatsapp_pipeline as wp
    return wp


class TestSmartQuality(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._o = C.PATH; C.PATH = self.tmp / "c.json"
        wp = _wp()
        self._gh = wp.GROUP_HEALTH_FILE
        wp.GROUP_HEALTH_FILE = self.tmp / "health.json"

    def tearDown(self):
        C.PATH = self._o
        _wp().GROUP_HEALTH_FILE = self._gh
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _done_event(self):
        code = C.new_event("Poster Fest", "Guntur", ["Alpha College"], 5, "easy",
                           created_by="admin")
        d = C._load(); e = d["events"][code]
        e["questions"] = [{"id": f"q{i}"} for i in range(5)]
        e["state"] = "done"
        e["players"] = {
            "1": {"college": "Alpha College", "name": "Anitha", "pts": 140, "correct": 5,
                  "answered": 5, "joined": "x", "first": None, "last": None},
            "2": {"college": "Alpha College", "name": "Ravi", "pts": 90, "correct": 3,
                  "answered": 5, "joined": "x", "first": None, "last": None},
        }
        C._save(d)
        return code

    def test_poster_png(self):
        code = self._done_event()
        try:
            from PIL import Image  # noqa: F401
        except Exception:
            self.skipTest("Pillow not installed")
        data = C.poster_png(code)
        self.assertIsNotNone(data)
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertIsNone(C.poster_png("CE-NOPE"))

    def test_group_health(self):
        wp = _wp()
        wp.group_health_record("g1@g.us", sent=8, failed=2, name="G1")
        h = wp.group_health()["g1@g.us"]
        self.assertEqual((h["rate"], h["status"]), (80, "good"))
        for _ in range(5):
            wp.group_health_record("g2@g.us", sent=0, failed=1, name="G2")
        h2 = wp.group_health()["g2@g.us"]
        self.assertEqual(h2["status"], "paused")
        self.assertTrue(wp.group_health_reset("g2@g.us"))
        self.assertEqual(wp.group_health()["g2@g.us"]["status"], "weak")
        wp.group_health_record("g2@g.us", sent=3, failed=0)
        self.assertEqual(wp.group_health()["g2@g.us"]["consec_fail"], 0)

    def test_preview_no_send(self):
        wp = _wp()
        fake_reg = {"groups": [{"id": "G1", "jid": "111@g.us", "name": "Preview Group",
                                "category": "SSC", "group_type": "EXAM_SPECIFIC",
                                "active": True}], "gateway_url": ""}
        with mock.patch.object(wp, "load_wa_registry", return_value=fake_reg):
            out = wp.preview_broadcast(questions_per_group=2)
        self.assertTrue(out["ok"])
        self.assertEqual(out["groups_total"], 1)
        self.assertEqual(len(out["samples"]), 1)
        self.assertTrue(out["samples"][0]["messages"])
        self.assertIn("Preview", out["note"])

    def test_planner_whatsapp_leg(self):
        fake_reg = {"groups": [{"id": "G1", "jid": "111@g.us", "name": "WA One",
                                "category": "SSC", "active": True}], "gateway_url": ""}
        wp = _wp()
        with mock.patch.object(wp, "load_wa_registry", return_value=fake_reg):
            plan = planner.today_plan(channels=[("TSPSC", {"name": "TSPSC Hub"})],
                                      rates_fn=lambda ch: {},
                                      slots=["07:00"])
        wa_items = [i for i in plan["items"] if i["mode"] == "wa"]
        self.assertEqual(len(wa_items), 1)
        self.assertEqual(wa_items[0]["target_group_ids"], ["G1"])
        calls = []

        def fake_add(time_str, **kw):
            calls.append(kw)
            return {"id": "job_x"}

        created = planner.apply_plan(wa_items, add_fn=fake_add)
        self.assertEqual(created, ["job_x"])
        self.assertEqual(calls[0]["mode"], "wa")
        self.assertEqual(calls[0]["target_group_ids"], ["G1"])

    def test_dashboard_wiring(self):
        src = (Path(__file__).resolve().parents[1]
               / "scripts" / "dashboard_server.py").read_text(encoding="utf-8")
        for needle in ('"/api/campus/poster"', "campus.poster_png",
                       '"/api/whatsapp/group_health"', '"/api/whatsapp/preview"',
                       "whatsapp_pipeline.preview_broadcast", "group_health_reset",
                       "Colleges × StudentUp Challenge", '"colleges": colleges',
                       '"weak_topic"', "mb.weak_topics", "waHealthBadge",
                       "runWaPreview", "Result Poster"):
            self.assertIn(needle, src)
        psrc = Path(_wp().__file__).read_text(encoding="utf-8")
        for needle in ("def group_health(", "def preview_broadcast(",
                       "Group health:", "group_health_record(grp"):
            self.assertIn(needle, psrc)


if __name__ == "__main__":
    unittest.main()
