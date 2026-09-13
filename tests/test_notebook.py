import sys, unittest, tempfile, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from core import notebook as NB

BLOCK = """Here you go:
### Q
EXAM: TSPSC Group-2 | YEAR: 2024 | PAPER: Paper-1 | QNO: 17 | TOPIC: Indian Polity
EN: Which Article of the Constitution deals with the abolition of untouchability?
TE: రాజ్యాంగంలోని ఏ అధికరణ అంటరానితనం నిర్మూలనకు సంబంధించినది?
A) Article 14 | అధికరణ 14
B) Article 17 | అధికరణ 17
C) Article 19 | అధికరణ 19
D) Article 21 | అధికరణ 21
ANS: B
EXP: Article 17 abolishes untouchability. | అధికరణ 17 అంటరానితనాన్ని రద్దు చేస్తుంది.

### Q
EXAM: TSPSC Group-2 | YEAR: 2024 | PAPER: Paper-1 | QNO: 18 | TOPIC: Geography
EN: Godavari river enters Telangana at which district?
TE: गोदावरी नदी
A) Nizamabad | నిజామాబాద్
B) Adilabad | ఆదిలాబాద్
C) Khammam | ఖమ్మం
D) Warangal | వరంగల్
ANS: A

### Q
EXAM: TSPSC Group-2 | YEAR: 2024 | PAPER: Paper-1 | QNO: 19 | TOPIC: Maths
EN: If 3x + 5 = 20, what is the value of x?
TE: 3x + 5 = 20 అయితే, x విలువ ఎంత?
A) 3 | 3
B) 4 | 4
C) 5 | 5
D) 6 | 6
ANS: 3
"""


class Notebook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        NB.BANK = pathlib.Path(self.tmp.name) / "nb.json"; NB.DRAFTS = pathlib.Path(self.tmp.name) / "d.json"

    def tearDown(self): self.tmp.cleanup()

    def test_parse_blocks(self):
        raws = NB.parse_blocks(BLOCK)
        self.assertEqual(len(raws), 3)
        self.assertEqual(raws[0]["exam"], "TSPSC Group-2"); self.assertEqual(raws[0]["qno"], "17")
        self.assertEqual(raws[0]["answer_index"], 1); self.assertEqual(raws[0]["options_te"][1], "అధికరణ 17")
        self.assertEqual(raws[2]["answer_index"], 2)   # numeric ANS 3 → index 2

    def test_preview_validates(self):
        pv = NB.preview(BLOCK)
        self.assertEqual(pv["parsed"], 3)
        self.assertEqual(len(pv["ok"]), 2)                       # Q18 rejected (Hindi script)
        self.assertEqual(pv["rejected"][0][0], "18")
        q = pv["ok"][0]
        self.assertEqual(q["channel"], "TSPSC"); self.assertEqual(q["source"], "pyq"); self.assertEqual(q["year"], "2024")
        self.assertTrue(q["q_te"].startswith("⤷")); self.assertEqual(q["id"], "N0001")
        self.assertIn("valid 2", NB.preview_text(pv)); self.assertIn("Q18", NB.preview_text(pv))

    def test_json_input_and_hints(self):
        js = json.dumps([{"exam": "IBPS PO Prelims", "year": 2023, "q_en": "What is 15% of 200?", "q_te": "200 లో 15% ఎంత?",
                          "options_en": ["20", "25", "30", "35"], "answer": "C"}])
        pv = NB.preview(js)
        self.assertEqual(len(pv["ok"]), 1); self.assertEqual(pv["ok"][0]["channel"], "BANKING")
        self.assertEqual(pv["ok"][0]["options_te"], ["20", "25", "30", "35"])   # numeric options mirrored
        pv2 = NB.preview(js.replace("IBPS PO Prelims", "Unknown Exam"))
        self.assertEqual(pv2["rejected"][0][1], "exam→channel unknown")
        pv3 = NB.preview(js.replace("IBPS PO Prelims", "Unknown Exam"), channel_hint="SSC")
        self.assertEqual(pv3["ok"][0]["channel"], "SSC")

    def test_commit_dedupes_and_status(self):
        NB.save_draft("9", BLOCK)
        import core.notebook as M
        M.rebuild_json = None
        n, txt = NB.commit("9")
        self.assertEqual(n, 2); self.assertIn("imported", txt)
        self.assertIsNone(NB.get_draft("9"))
        NB.save_draft("9", BLOCK)
        pv = NB.preview(BLOCK)
        self.assertEqual(len(pv["ok"]), 0); self.assertEqual(pv["dupes"], 2)   # second import → all dupes
        self.assertIn("2 questions", NB.status_text()); self.assertIn("TSPSC Group-2 2024: 2", NB.status_text())

    def test_prompt(self):
        p = NB.prompt_for("TSPSC", year="2024", paper="Paper-1")
        self.assertIn("### Q", p); self.assertIn("official key", p); self.assertIn("Telugu script only", p)
        self.assertIn("YEAR: 2024", p)


if __name__ == "__main__":
    unittest.main()
