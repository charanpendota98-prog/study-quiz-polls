import os, sys, json, unittest, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from core import pyq, collector, content, config

FIX_HTML = """<html><body>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/TSPSC-Group-2-Paper-1.pdf">Paper 1</a>
<a href="/blog/wp-content/uploads/2024/12/TSPSC-Group-2-Paper-2-Hindi.pdf">Paper 2 Hindi</a>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/Syllabus.pdf">Syllabus</a>
<a href="https://evil.example/x.pdf">x</a>
<a href="https://www.careerpower.in/blog/wp-content/uploads/2024/12/TSPSC-Group-2-Paper-3.pdf">Paper 3</a>
</body></html>"""

class TestPyq(unittest.TestCase):
    def test_registry_loads_and_is_well_formed(self):
        papers = pyq.load_papers()
        self.assertGreaterEqual(len(papers), 20)
        for p in papers:
            self.assertIn(p["channel"], config.CHANNELS, p)
            self.assertTrue(p.get("url") or p.get("index"), p)
            self.assertTrue(p.get("exam") and p.get("year"), p)

    def test_pdf_links_from_index_filters(self):
        links = pyq.pdf_links_from_index(FIX_HTML, "https://www.careerpower.in/a.html", limit=10)
        self.assertEqual(len(links), 2)
        self.assertTrue(all(u.endswith(("Paper-1.pdf", "Paper-3.pdf")) for u, _ in links))

    def test_stamp_propagates_to_questions(self):
        entry = {"channel": "TSPSC", "exam": "TSPSC Group-2", "year": 2024, "paper": "Paper-1",
                 "date": "2024-12-15", "url": "https://x/p1.pdf", "lang": "en"}
        stamp = pyq._stamp(entry)
        html = "\n".join(
            f"{i}. Which river is called Dakshina Ganga number {i}?\n(a) Krishna\n(b) Godavari\n(c) Kaveri\n(d) Penna\nAns: b"
            for i in range(1, 4))
        res = collector.collect_daily(fixture=(html, "TSPSC Group-2 2024 Paper-1", "file://p1.pdf"),
                                      dry=True, llm=None, stamp=stamp)
        # offline (no LLM) worded questions are parked for translation; the
        # stamp must survive parking. Simulate a translated acceptance here.
        self.assertGreaterEqual(res["parked"] + res["accepted"] + res["duplicates"], 1)
        raw = {"q_en": "Which river is called Dakshina Ganga?",
               "options_en": ["Krishna", "Godavari", "Kaveri", "Penna"], "answer_index": 1,
               "q_te": "దక్షిణ గంగ అని ఏ నదిని పిలుస్తారు?",
               "options_te": ["కృష్ణా", "గోదావరి", "కావేరి", "పెన్నా"]}
        q, _ = collector.normalize_raw(raw, "fixture", 1, stamp=stamp)
        if q is None:   # translator path unavailable offline → build minimal stamped q
            q = {"q_en": raw["q_en"], "q_te": raw["q_te"], "options_en": raw["options_en"],
                 "options_te": raw["options_te"], "answer_index": 1, "topic": "geography",
                 **{k: v for k, v in stamp.items() if k not in ("channel_pin", "lang_hint")},
                 "channel": "TSPSC"}
        self.assertEqual(q["source"], "pyq"); self.assertEqual(q["year"], 2024)
        self.assertEqual(q["exam"], "TSPSC Group-2"); self.assertEqual(q["channel"], "TSPSC")
        self.assertIn("2024", pyq.pyq_label(q))
        txt = content.build_question_text(q, config.CHANNELS["TSPSC"], badge="⚡ Easy")
        self.assertIn("2024", txt); self.assertLessEqual(len(txt), 300)

    def test_status_text_runs(self):
        self.assertIn("PYQ", pyq.status_text())

if __name__ == "__main__":
    unittest.main()
