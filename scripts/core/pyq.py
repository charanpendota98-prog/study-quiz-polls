#!/usr/bin/env python3
"""
STUDENTUP — OFFICIAL PREVIOUS-PAPER (PYQ) HARVESTER

Turns data/pyq_papers.json (official / verified paper PDFs) into
provenance-stamped questions:

    📜 TSPSC Group-2 2024 · Paper-1        <- shown on every poll from that paper

Flow (idempotent, resumable, polite):
  1. entry has "url"   -> download PDF once into data/pdf_inbox/
     entry has "index" -> fetch the page, pick up to max_pdfs *.pdf links
                          (same host or known CDN), download each once
  2. ingest via collector.ingest_pdf() -> parser -> validate -> translate
  3. every accepted question gets: source="pyq", exam, year, paper, paper_url
  4. state in data/pyq_state.json  (url -> {status, questions, when})

CLI:
  python3 -m core.pyq harvest [--dry] [--only TSPSC] [--limit 5]
  python3 -m core.pyq add <CHANNEL> "<exam>" <year> "<paper>" <pdf-or-index-url>
  python3 -m core.pyq status
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import config
from .store import load_json, save_json_atomic

PAPERS_FILE = config.DATA / "pyq_papers.json"
STATE_FILE = config.DATA / "pyq_state.json"
INBOX = config.DATA / "pdf_inbox"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 StudentUpBot/1.0 (+education; polite)")
MAX_PDF = 30 * 1024 * 1024

# CDNs that host the real paper PDFs for the index sites we use
_PDF_HOSTS = ("careerpower.in", "adda247.com", "bankersadda.com", "sscadda.com",
              "sakshi.com", "eenadu.net", "pratibhaassets.eenadu.net", "tspsc.gov.in",
              "psc.ap.gov.in", "ssc.gov.in", "ssc.nic.in", "rrbcdg.gov.in", "upsc.gov.in",
              "ibps.in", "sbi.co.in", "tslprb.in", "slprb.ap.gov.in", "wp.com", "cloudfront.net",
              "files.freshersnow.com", "cdn-images.prepp.in", "images.collegedunia.com",
              "studybizz.com", "testbook.com")


# ----------------------------------------------------------------- helpers
def load_papers():
    return _papers()


def _papers():
    d = load_json(PAPERS_FILE, {})
    return d.get("papers", []) if isinstance(d, dict) else []


def _state():
    return load_json(STATE_FILE, {})


# 🧠 harvest intelligence: dead-paper damping
_MAX_ATTEMPTS = 5          # innisari fail aithe "dead" — budget waste avvadu
_BACKOFF_HOURS = 6         # attempt ki 6h×attempts gap (max ~30h)


def _eligible(rec: dict, now_ts: float) -> bool:
    """Error records back off exponentially; dead papers never retry."""
    if rec.get("status") in ("done", "dead"):
        return False
    if rec.get("status") == "expanded":
        # 🏭 expanded index: kotha papers kosam week ki okkasari rescan
        return now_ts >= float(rec.get("next_try_ts", 0) or 0)
    if int(rec.get("attempts", 0)) >= _MAX_ATTEMPTS:
        return False
    nxt = float(rec.get("next_try_ts", 0) or 0)
    return now_ts >= nxt


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:70]


def _get(url, timeout=40, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_PDF + 1)
    return data if binary else data.decode("utf-8", "replace")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._cur = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._cur = [href, ""]

    def handle_data(self, data):
        if self._cur:
            self._cur[1] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._cur:
            self.links.append((self._cur[0], self._cur[1].strip()))
            self._cur = None


_VIEWER_RE = re.compile(r"[?&]file=([^&#]+)", re.I)


def unwrap_viewer(url: str) -> str:
    """Sakshi/Eenadu embed papers through a pdf.js viewer:
    .../libraries/pdf.js/web/viewer.html?file=https%3A%2F%2F...%2Fpaper.pdf
    Return the real PDF URL (decoded) when the link is such a wrapper."""
    if "viewer.html" in url.lower() or "/pdf.js/" in url.lower():
        m = _VIEWER_RE.search(url)
        if m:
            from urllib.parse import unquote
            inner = unquote(m.group(1)).strip()
            if inner.lower().startswith("http") and re.search(r"\.pdf(\?|$)", inner, re.I):
                return inner
    return url


def pdf_links_from_index(page_html: str, base_url: str, limit: int = 4, prefer_lang="en"):
    """Pick paper PDF links from an index page. Prefers links whose text or
    URL mention 'question paper'/'pdf' and English medium; skips answer-key-only,
    Hindi-only, syllabus, admit-card links."""
    p = _Links()
    p.feed(page_html)
    seen, out = set(), []
    bad = re.compile(r"syllabus|admit|result|cut-?off|notification|hindi|answer-?key-only|analysis", re.I)
    for href, text in p.links:
        url = unwrap_viewer(urljoin(base_url, href.split("#")[0]))
        if not re.search(r"\.pdf(\?|$)", url, re.I):
            continue
        host = urlparse(url).netloc.lower()
        if not any(host.endswith(h) for h in _PDF_HOSTS):
            continue
        blob = f"{text} {url}"
        if bad.search(blob) and not re.search(r"question|paper|pyq|shift", blob, re.I):
            continue
        if prefer_lang == "en" and re.search(r"hindi|_hi\b|-hi\.pdf", blob, re.I):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append((url, text))
        if len(out) >= limit:
            break
    return out


def _download(url: str, name_hint: str, dry=False):
    INBOX.mkdir(parents=True, exist_ok=True)
    base = os.path.basename(urlparse(url).path) or "paper.pdf"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    dest = INBOX / f"{_slug(name_hint)}--{base}"
    if dest.exists():
        return dest
    if dry:
        print(f"   [pyq][DRY] would download {url}")
        return dest
    data = _get(url, timeout=90, binary=True)
    if len(data) > MAX_PDF or not data.startswith(b"%PDF"):
        raise ValueError("not a PDF or too large")
    dest.write_bytes(data)
    print(f"   [pyq] downloaded {dest.name} ({len(data)//1024} KB)")
    return dest


def _stamp(entry: dict):
    """Provenance dict copied onto each question from this paper."""
    return {"source": "pyq", "exam": entry["exam"], "year": int(entry["year"]),
            "paper": entry.get("paper", ""), "paper_date": entry.get("date", ""),
            "paper_url": entry.get("url") or entry.get("index", ""),
            "channel_pin": entry["channel"], "lang_hint": entry.get("lang", "en")}


def pyq_label(q: dict) -> str:
    """'📜 TSPSC Group-2 2024 · Paper-1' for poll headers / report cards."""
    if q.get("source") != "pyq" or not q.get("exam"):
        return ""
    paper = (q.get("paper") or "").split(" ")[0]
    paper = f" · {paper}" if paper and paper.lower().startswith("paper") else ""
    yr = f" {q['year']}" if q.get("year") else ""
    return f"📜 {q['exam']}{yr}{paper}"


# ----------------------------------------------------------------- harvest
def discover_index_papers(entry, page_html, limit=40):
    """🏭 PAPER FACTORY: official index page lo unna anni paper PDFs ni
    registry loki register chesthundi. URL guessing eppudu ledu — links
    index page lone untayi, host-whitelist + quality filters
    pdf_links_from_index lone apply avuthayi. Returns (added, total)."""
    links = pdf_links_from_index(page_html, entry["index"], limit,
                                 entry.get("lang", "en"))
    d = load_json(PAPERS_FILE, {"papers": []})
    papers = d.get("papers", []) if isinstance(d, dict) else []
    known = {(p.get("url") or "") for p in papers}
    known.update(_state().keys())
    added = 0
    for url, text in links:
        if url in known:
            continue
        known.add(url)
        label = (text or "").strip()[:60] or os.path.basename(urlparse(url).path)[:60]
        papers.append({"channel": entry["channel"], "exam": entry["exam"],
                       "year": entry["year"], "paper": label or "Paper",
                       "url": url, "lang": entry.get("lang", "en"),
                       "via": f"index-discovery: {entry['exam']}"})
        added += 1
    if added:
        d["papers"] = papers
        save_json_atomic(PAPERS_FILE, d)
    return added, len(links)


def _channel_need() -> dict:
    """Channel ki inka enni fresh questions kavalo (unused stock) —
    harvest priority ki. Fail aithe {} (registry order ne vadutham)."""
    try:
        from .question_bank import Bank
        return {str(ch).upper(): int(s.get("unused", 0))
                for ch, s in Bank().stats().items()}
    except Exception:
        return {}


def _sort_by_need(entries, need):
    """Weakest-stock channel papers first — deadline lopale ave mundu vastayi."""
    if not need:
        return list(entries)
    return sorted(entries,
                  key=lambda e: need.get(str(e.get("channel", "")).upper(), 10 ** 9))


def harvest(dry=False, only=None, limit=None, llm=None):
    if llm is None:                       # auto-pick rotating API keys from env
        try:
            from .llm import LLM
            cand = LLM()
            llm = cand if cand.available() else None
        except Exception:
            llm = None
    """Download + ingest every pending paper. Returns stats."""
    from . import collector
    import time as _t
    try:                                   # storage hygiene before downloading more
        from .scout import enforce_inbox_cap
        enforce_inbox_cap(dry=dry)
    except Exception:
        pass
    deadline = _t.time() + 20 * 60         # never hold the scheduler > 20 min
    st = _state()
    stats = {"papers": 0, "pdfs": 0, "questions": 0, "skipped": 0, "errors": 0,
             "discovered": 0}
    for entry in _sort_by_need(_papers(), _channel_need()):
        if _t.time() > deadline:
            break
        if only and entry["channel"].upper() != only.upper():
            continue
        key = entry.get("url") or entry.get("index")
        if not key:
            continue
        rec = st.get(key, {})
        if rec.get("status") == "done":
            stats["skipped"] += 1
            continue
        if rec and not _eligible(rec, _t.time()):
            stats["skipped"] += 1     # backoff window / dead — budget save
            continue
        if limit is not None and stats["papers"] >= limit:
            break
        stats["papers"] += 1
        name = f"{entry['exam']} {entry['year']} {entry.get('paper','')}"
        try:
            targets = []
            discovered_total = 0
            if entry.get("url"):
                targets = [(entry["url"], name)]
            else:
                html = _get(entry["index"])
                targets = pdf_links_from_index(html, entry["index"], entry.get("max_pdfs", 4),
                                               entry.get("lang", "en"))
                if not targets:
                    raise ValueError("no PDF links found on index page")
                # 🏭 index lo migatha papers anni registry loki — ee run lo
                # batch matrame ingest, migilinavi next runs drain chesthayi
                _added, discovered_total = discover_index_papers(entry, html)
                stats["discovered"] += _added
            got = 0
            for url, text in targets:
                try:
                    dest = _download(url, f"{name} {text}", dry=dry)
                    if dry:
                        got += 1
                        continue
                    res = collector.ingest_pdf(dest, title=name, dry=dry, llm=llm,
                                               stamp=_stamp(entry))
                    got += res.get("accepted", 0)
                    stats["pdfs"] += 1
                    if not entry.get("url"):
                        st[url] = {"status": "done",
                                   "questions": res.get("accepted", 0),
                                   "when": datetime.now(config.IST).strftime("%Y-%m-%d %H:%M"),
                                   "exam": entry["exam"], "year": entry["year"],
                                   "via": "index-batch"}
                except Exception as e:
                    print(f"   [pyq] {url}: {e}")
                    stats["errors"] += 1
            stats["questions"] += got
            if not entry.get("url") and discovered_total > len(targets):
                # inka drain avvalsina papers unnayi — week tarvata rescan
                st[key] = {"status": "expanded", "found": discovered_total,
                           "questions": int(rec.get("questions", 0)) + got,
                           "next_try_ts": _t.time() + 7 * 24 * 3600,
                           "when": datetime.now(config.IST).strftime("%Y-%m-%d %H:%M"),
                           "exam": entry["exam"], "year": entry["year"]}
            else:
                st[key] = {"status": "done" if (got or dry) else "empty", "questions": got,
                           "when": datetime.now(config.IST).strftime("%Y-%m-%d %H:%M"),
                           "exam": entry["exam"], "year": entry["year"]}
        except Exception as e:
            print(f"   [pyq] {name}: {e}")
            _att = int(rec.get("attempts", 0)) + 1
            st[key] = {"status": "dead" if _att >= _MAX_ATTEMPTS else "error",
                       "attempts": _att,
                       "next_try_ts": _t.time() + _BACKOFF_HOURS * 3600 * _att,
                       "error": str(e)[:160],
                       "when": datetime.now(config.IST).strftime("%Y-%m-%d %H:%M")}
            stats["errors"] += 1
        if not dry:
            save_json_atomic(STATE_FILE, st)
    print(f"[pyq] {stats}")
    return stats


def papers_index(min_q: int = 5) -> list:
    """📜 Real PYQ paper index: bank loni previous-year questions ni
    exam (+ year + paper) batti group chesi FULL-paper sets ga
    isthundi. Year unna papers first, tarvatha pedda sets.
    Honest counts — bank lo unna questions matrame count avuthayi."""
    import collections
    try:
        from .question_bank import load_bank
        qs = load_bank()
    except Exception:
        return []
    groups = collections.defaultdict(list)
    for q in qs:
        if q.get("source") != "pyq":
            continue
        exam = (q.get("exam") or "").strip()
        if not exam:
            continue
        year = q.get("year")
        paper = (q.get("paper") or "").strip()
        groups[(exam, str(year) if year else "", paper)].append(q)
    out = []
    for (exam, year, paper), items in groups.items():
        if len(items) < int(min_q or 5):
            continue
        label = exam + (f" {year}" if year else "") + (f" · {paper}" if paper else "")
        _tc = collections.Counter((q.get("topic") or "general") for q in items)
        out.append({
            "exam": exam, "year": year, "paper": paper, "label": label,
            "count": len(items),
            "ids": [q.get("id") for q in items],
            "channels": sorted({q.get("channel", "") for q in items
                                if q.get("channel")}),
            "topics": [t for t, _n in _tc.most_common(4)],
        })
    out.sort(key=lambda r: (0 if r["year"] else 1, -r["count"], r["exam"]))
    return out


def coverage_gaps(target: int = 50) -> list:
    """🎯 PYQ COVERAGE GAPS: channel-wise real PYQ stock + target ki
    gap — harvest priority list (takkuva unna channel mundhu)."""
    cov = by_channel()  # {channel: {"pyq": n, "total": t}}
    rows = [{"channel": ch, "pyq": int(v.get("pyq") or 0),
             "total": int(v.get("total") or 0),
             "gap": max(0, int(target) - int(v.get("pyq") or 0))}
            for ch, v in cov.items()]
    rows.sort(key=lambda r: (r["pyq"], r["channel"]))
    return rows


def by_channel():
    """Exam-wise real-PYQ coverage — prati channel ki enni previous-year
    questions bank lo unnayo (harvest priority + admin visibility)."""
    import collections
    try:
        from .question_bank import load_bank
        qs = load_bank()
    except Exception:
        return {}
    c = collections.Counter()
    t = collections.Counter()
    for q in qs:
        ch = q.get("channel") or "OTHER"
        t[ch] += 1
        if q.get("source") == "pyq":
            c[ch] += 1
    return {ch: {"pyq": c.get(ch, 0), "total": t[ch]} for ch in sorted(t)}


def status_text():
    st = _state()
    papers = _papers()
    done = sum(1 for p in papers if st.get(p.get("url") or p.get("index"), {}).get("status") == "done")
    qs = sum(v.get("questions", 0) for v in st.values())
    by = {}
    for p in papers:
        by.setdefault(p["channel"], [0, 0])
        by[p["channel"]][1] += 1
        if st.get(p.get("url") or p.get("index"), {}).get("status") == "done":
            by[p["channel"]][0] += 1
    lines = [f"📜 PYQ papers: {done}/{len(papers)} harvested · {qs} questions with provenance"]
    lines += [f"  {ch}: {d}/{t}" for ch, (d, t) in sorted(by.items())]
    disc = sum(1 for p in papers if str(p.get("via", "")).startswith("index"))
    if disc:
        lines.append(f"  🧭 {disc} papers official indexes nunchi auto-discovered (factory)")
    exp = sum(1 for v in st.values() if v.get("status") == "expanded")
    if exp:
        lines.append(f"  🔁 {exp} indexes expanded — weekly rescan lo kotha papers vastayi")
    dead = sum(1 for v in st.values() if v.get("status") == "dead")
    if dead:
        lines.append(f"  🪦 {dead} papers dead (5× fail — auto-retired, budget save)")
    errs = [(k, v) for k, v in st.items() if v.get("status") == "error"]
    if errs:
        lines.append(f"  ⚠️ {len(errs)} errors — see data/pyq_state.json")
    return "\n".join(lines)


def add_paper(channel, exam, year, paper, url):
    d = load_json(PAPERS_FILE, {"papers": []})
    entry = {"channel": channel.upper(), "exam": exam, "year": int(year), "paper": paper,
             "lang": "en", "via": "manual"}
    entry["url" if re.search(r"\.pdf(\?|$)", url, re.I) else "index"] = url
    d.setdefault("papers", []).append(entry)
    save_json_atomic(PAPERS_FILE, d)
    return entry


PYQ_BANK_FILE = config.DATA / "pyq_bank.json"
IMPORT_TEMPLATE = (
    "question,option1,option2,option3,option4,answer,explanation,exam,year,channel,topic\n"
    "\"The Finance Commission is constituted under which Article?\","
    "\"Article 280\",\"Article 263\",\"Article 312\",\"Article 368\",1,"
    "\"Article 280 of the Constitution provides for a Finance Commission.\","
    "\"UPSC CSE Prelims\",2023,CURRENT,polity\n")



PENDING_FILE = config.DATA / "pyq_pending.json"


def _park_pending(q):
    """Telugu translation kosam wait chese English PYQs — keys enable
    chesaka translate chesi bank loki testham (em data loss kadhu)."""
    data = load_json(PENDING_FILE, {"questions": []})
    qs = data.get("questions", []) if isinstance(data, dict) else []
    from .question_bank import q_signature
    sigs = {q_signature(x) for x in qs}
    if q_signature(q) not in sigs:
        qs.append(q)
        data["questions"] = qs
        save_json_atomic(PENDING_FILE, data)
    return len(qs)

def import_csv(text, rebuild=True):
    """📥 REAL previous-year questions bulk import (CSV paste/upload).

    Format: question,option1..4,answer(1-4 / A-D / option text),explanation,
    exam,year,channel,topic. Validated + deduped (question signature) and
    appended to data/pyq_bank.json as source="pyq" with full provenance
    (exam + year), so every poll can show "📜 Exam Year"."""
    import csv
    import io
    try:
        rows = list(csv.DictReader(io.StringIO(text or "")))
    except Exception as ex:
        return {"added": 0, "skipped_dup": 0, "errors": [f"CSV parse: {ex}"]}
    from .content import validate_question
    from .question_bank import q_signature
    data = load_json(PYQ_BANK_FILE, {"questions": []})
    qs = data.get("questions", []) if isinstance(data, dict) else []
    sigs = {q_signature(q) for q in qs}
    try:                                   # bank-wide dedupe (cheap file read)
        bank = load_json(config.BANK_JSON, {"questions": []})
        sigs.update(q_signature(q) for q in bank.get("questions", []))
    except Exception:
        pass
    added = skipped = pending = 0
    errors = []
    for i, r in enumerate(rows, start=2):
        def g(*names):
            for nm in names:
                v = r.get(nm)
                if v:
                    return str(v).strip()
            return ""
        q_en = g("question", "q_en", "Question")
        opts = [g("option1", "Option 1"), g("option2", "Option 2"),
                g("option3", "Option 3"), g("option4", "Option 4")]
        ans_raw = g("answer", "correct", "Answer")
        if not q_en or any(not o for o in opts):
            errors.append(f"row {i}: question/options missing")
            continue
        ai = None
        if ans_raw.isdigit() and 1 <= int(ans_raw) <= 4:
            ai = int(ans_raw) - 1
        elif ans_raw.upper() in ("A", "B", "C", "D"):
            ai = "ABCD".index(ans_raw.upper())
        elif ans_raw in opts:
            ai = opts.index(ans_raw)
        if ai is None:
            errors.append(f"row {i}: answer must be 1-4 / A-D / option text")
            continue
        try:
            year = int(g("year", "Year") or 0)
        except Exception:
            year = 0
        q = {"id": f"PYQ-I{len(qs) + added + 1:04d}", "source": "pyq",
             "channel": (g("channel", "Channel") or "CURRENT").upper(),
             "exam": g("exam", "Exam"), "year": year,
             "topic": g("topic", "Topic") or "general",
             "q_en": q_en, "q_te": g("question_te", "q_te"),
             "options_en": opts,
             "options_te": [g("option1_te"), g("option2_te"),
                            g("option3_te"), g("option4_te")],
             "answer_index": ai,
             "explanation": g("explanation", "Explanation")}
        if not q["q_te"]:
            # Telugu lekapothe live server lo translation keys unte
            # auto-translate; lekapothe pending park (dataสูญหาย avadu).
            try:
                from .translator import translate_mcq
                tr = translate_mcq(q["q_en"], q["options_en"], q["explanation"])
            except Exception:
                tr = None
            if tr:
                q["q_te"] = tr.get("q_te", "")
                q["options_te"] = tr.get("options_te", [])
        errs = validate_question(q)
        if errs:
            _te_only = all(("Telugu" in e or " TE " in e or "options_te" in e
                            or "TE option" in e) for e in errs)
            if _te_only and not q["q_te"]:
                _park_pending(q)
                pending += 1
            else:
                errors.append(f"row {i}: {'; '.join(errs[:2])}")
            continue
        sig = q_signature(q)
        if sig in sigs:
            skipped += 1
            continue
        sigs.add(sig)
        qs.append(q)
        added += 1
    if added:
        data["questions"] = qs
        save_json_atomic(PYQ_BANK_FILE, data)
        if rebuild:
            try:
                from .question_bank import load_bank
                load_bank(force_rebuild=True)
            except Exception as ex:
                errors.append(f"bank rebuild: {ex}")
    return {"added": added, "skipped_dup": skipped, "pending_translation": pending,
            "errors": errors[:12], "pyq_file_total": len(qs)}


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "status":
        print(status_text())
    elif args[0] == "harvest":
        only = args[args.index("--only") + 1] if "--only" in args else None
        lim = int(args[args.index("--limit") + 1]) if "--limit" in args else None
        harvest(dry="--dry" in args, only=only, limit=lim)
    elif args[0] == "add" and len(args) >= 6:
        print(add_paper(*args[1:6]))
    else:
        print(__doc__)
