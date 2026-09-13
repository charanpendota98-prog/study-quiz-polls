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
    stats = {"papers": 0, "pdfs": 0, "questions": 0, "skipped": 0, "errors": 0}
    for entry in _papers():
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
        if limit is not None and stats["papers"] >= limit:
            break
        stats["papers"] += 1
        name = f"{entry['exam']} {entry['year']} {entry.get('paper','')}"
        try:
            targets = []
            if entry.get("url"):
                targets = [(entry["url"], name)]
            else:
                html = _get(entry["index"])
                targets = pdf_links_from_index(html, entry["index"], entry.get("max_pdfs", 4),
                                               entry.get("lang", "en"))
                if not targets:
                    raise ValueError("no PDF links found on index page")
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
                except Exception as e:
                    print(f"   [pyq] {url}: {e}")
                    stats["errors"] += 1
            stats["questions"] += got
            st[key] = {"status": "done" if (got or dry) else "empty", "questions": got,
                       "when": datetime.now(config.IST).strftime("%Y-%m-%d %H:%M"),
                       "exam": entry["exam"], "year": entry["year"]}
        except Exception as e:
            print(f"   [pyq] {name}: {e}")
            st[key] = {"status": "error", "error": str(e)[:160],
                       "when": datetime.now(config.IST).strftime("%Y-%m-%d %H:%M")}
            stats["errors"] += 1
        if not dry:
            save_json_atomic(STATE_FILE, st)
    print(f"[pyq] {stats}")
    return stats


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
