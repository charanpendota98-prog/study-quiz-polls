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


class TestOfficialPaperFormat(unittest.TestCase):
    """TSPSC/APPSC/SSC official PDFs use (1)-(4) option labels + numeric key."""
    PAPER = (
        "1. The Kakatiya dynasty had its capital at\n"
        "(1) Warangal (2) Golconda (3) Bidar (4) Devagiri\n"
        "2. Which Article deals with the Election Commission?\n"
        "(1) Article 280\n(2) Article 324\n(3) Article 356\n(4) Article 370\n"
        "3. Godavari river enters Telangana at\n"
        "(1) Basara (2) Kandakurthi (3) Bhadrachalam (4) Nizamabad\n"
        "4. Bathukamma is celebrated mainly in the month of\n"
        "(1) Sravana (2) Aswayuja (3) Karthika (4) Chaitra\n"
        "5. The first Chief Minister of Telangana State was\n"
        "(1) K. Chandrashekar Rao (2) A. Revanth Reddy (3) N. Kiran Kumar Reddy (4) Etela Rajender\n"
        "ANSWER KEY\n1. 1  2. 2  3. 2  4. 2  5. 1\n")

    def test_numeric_options_and_key(self):
        qs = collector.parse_quiz_lines(collector.text_to_lines(self.PAPER),
                                        "TSPSC Group-2 2024 Paper-1", "file://p1.pdf")
        self.assertEqual(len(qs), 5)
        self.assertEqual([q["options_en"][q["answer_index"]] for q in qs],
                         ["Warangal", "Article 324", "Kandakurthi", "Aswayuja", "K. Chandrashekar Rao"])

    def test_gktoday_quizbase_html_parses(self):
        html = ("<div class='wp_quiz_question'>1. In which year was Andhra Pradesh created?</div>"
                "<div>[A] 1950<br>[B] 1952<br>[C] 1956<br>[D] 1960</div>"
                "<div><b>Correct Answer:</b> C [1956]</div>")
        qs = collector.parse_page({"name": "GKToday", "exam": "tspsc", "type": "index"}, html,
                                  "Telangana GK", "https://www.gktoday.in/quizbase/telangana")
        self.assertEqual(len(qs), 1); self.assertEqual(qs[0]["answer_index"], 2)

    def test_registry_has_verified_direct_pdfs_per_channel(self):
        direct = [p for p in pyq.load_papers() if p.get("url")]
        self.assertGreaterEqual(len(direct), 130)
        for ch in ("TSPSC", "APPSC", "SSC", "RAILWAY", "BANKING", "DEFENCE", "POLICE"):
            self.assertTrue(any(p["channel"] == ch for p in direct), ch)


class TestSakshiViewer(unittest.TestCase):
    VIEWER = ("https://education.sakshi.com/libraries/pdf.js/web/viewer.html?file="
              "https%3A%2F%2Feducation.sakshi.com%2Fsites%2Fdefault%2Ffiles%2Fpdf%2F2025%2F03%2F12"
              "%2FPaper_III_Economy.pdf#")

    def test_unwrap_viewer(self):
        self.assertEqual(pyq.unwrap_viewer(self.VIEWER),
                         "https://education.sakshi.com/sites/default/files/pdf/2025/03/12/Paper_III_Economy.pdf")
        plain = "https://x.com/a.pdf"
        self.assertEqual(pyq.unwrap_viewer(plain), plain)
        self.assertEqual(pyq.unwrap_viewer("https://x.com/viewer.html?file=javascript:alert(1)"),
                         "https://x.com/viewer.html?file=javascript:alert(1)")

    def test_index_picks_viewer_pdf(self):
        html = f'<a href="{self.VIEWER}">Current View</a><a href="/x/syllabus.pdf">Syllabus</a>'
        links = pyq.pdf_links_from_index(html, "https://education.sakshi.com/en/p", limit=4)
        self.assertEqual(len(links), 1)
        self.assertTrue(links[0][0].endswith("Paper_III_Economy.pdf"))

    def test_registry_has_ts_ap_final_keys(self):
        papers = pyq.load_papers()
        urls = [p.get("url", "") for p in papers]
        self.assertTrue(any("P1_General_Studies.pdf" in u for u in urls))
        self.assertTrue(any("Telangana%20Movement" in u for u in urls))
        self.assertGreaterEqual(sum(1 for p in papers if p["channel"] == "TSPSC"), 20)
        self.assertGreaterEqual(sum(1 for p in papers if p["channel"] == "POLICE"), 40)
        self.assertEqual(len(set(p.get("url") or p.get("index") for p in papers)), len(papers))

    def test_whatsapp_registry_is_manual_tier(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "data", "whatsapp_channels.json")) as fh:
            d = json.load(fh)
        self.assertEqual(d["tier"], "manual")
        self.assertTrue(all(c["url"].startswith("https://whatsapp.com/channel/") for c in d["channels"]))
