#!/usr/bin/env python3
"""
STUDENTUP — SOURCE SCOUT  (continuous deep source discovery, safe & capped)

Never stops looking. Every night it walks known "hub" pages per exam, follows
links that look like previous-paper / question-paper pages, and keeps a
READY QUEUE of candidate PDFs + index pages in data/scout_candidates.json.
Candidates are promoted into data/pyq_papers.json only after a HEAD/GET probe
proves they are real PDFs (magic bytes, size within limits). Nothing here can
crash the scheduler: every network call is wrapped, every run is time-boxed,
and every store is size-capped and pruned.

Safety / "unbreakable" rules
  * time-box per run (default 8 min) and per fetch (25 s)
  * max pages per run, max new candidates per run, polite 1.2 s gap per host
  * data/scout_candidates.json capped at MAX_CANDIDATES (oldest unverified pruned)
  * data/pdf_inbox capped at INBOX_CAP_MB (oldest *ingested* PDFs deleted first)
  * dead hosts (3 consecutive failures) are paused 7 days
  * pyq_papers.json is only ever APPENDED to, atomically, with de-dup by URL
  * every exception is caught and recorded in data/scout_state.json["errors"]

CLI:
  python3 -m core.scout run [--dry] [--minutes 8]
  python3 -m core.scout status
  python3 -m core.scout hubs        # print hub list
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import config
from .store import load_json, save_json_atomic

CAND_FILE = config.DATA / "scout_candidates.json"
STATE_FILE = config.DATA / "scout_state.json"
PAPERS_FILE = config.DATA / "pyq_papers.json"
INBOX = config.DATA / "pdf_inbox"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36 StudentUpBot/1.0 (+education; polite)")

# ---- hard caps (storage-safe) ----
MAX_CANDIDATES = 1500          # queue size in scout_candidates.json
MAX_NEW_PER_RUN = 120          # new candidates accepted per run
MAX_PAGES_PER_RUN = 40         # hub/sub pages fetched per run
MAX_PROMOTE_PER_RUN = 25       # candidates probed + promoted per run
RUN_MINUTES = 8                # time-box
FETCH_TIMEOUT = 25
HOST_GAP_S = 1.2
PAGE_BYTES = 1_500_000         # never read more than this from a page
PDF_MAX_MB = 30
INBOX_CAP_MB = int(getattr(config, "PDF_INBOX_CAP_MB", 400))
STATE_ERRORS_KEEP = 60
DEAD_AFTER = 3
DEAD_PAUSE_DAYS = 7

# Hub pages: where new previous-paper pages keep appearing. Each hub is
# (channel, exam-hint, url). The scout follows links from these that match
# PAPER_PAGE_RE, then collects PDF links from those pages.
HUBS = [
    ("TSPSC", "TSPSC", "https://www.tspsc.gov.in/"),
    ("TSPSC", "TSPSC", "https://www.freshersnow.com/tspsc-previous-papers/"),
    ("TSPSC", "TSPSC", "https://www.careerpower.in/tspsc.html"),
    ("TSPSC", "TSPSC", "https://www.adda247.com/exams/telangana/"),
    ("TSPSC", "TSPSC", "https://studybizz.com/"),
    ("TSPSC", "TSPSC", "https://education.sakshi.com/en/tspsc/previous-papers"),
    ("TSPSC", "TSPSC Group-2", "https://education.sakshi.com/en/group-2/previous-papers-2024"),
    ("TSPSC", "TSPSC", "https://education.sakshi.com/en/tags/tspsc-previous-papers"),
    ("APPSC", "APPSC", "https://psc.ap.gov.in/"),
    ("APPSC", "APPSC", "https://www.freshersnow.com/appsc-previous-papers/"),
    ("APPSC", "APPSC", "https://www.adda247.com/exams/andhra-pradesh/"),
    ("APPSC", "APPSC", "https://www.careerpower.in/appsc.html"),
    ("APPSC", "APPSC", "https://education.sakshi.com/en/appsc/previous-papers"),
    ("APPSC", "APPSC", "https://www.adda247.com/jobs/appsc-group-2-previous-question-papers/"),
    ("APPSC", "APPSC", "https://education.sakshi.com/en/tags/appsc-previous-papers"),
    ("POLICE", "TS Police", "https://www.freshersnow.com/telangana-police-previous-papers/"),
    ("POLICE", "AP Police", "https://prepp.in/ap-police-constable-exam/previous-year-question-paper"),
    ("POLICE", "TS Police", "https://www.tslprb.in/"),
    ("POLICE", "AP Police", "https://slprb.ap.gov.in/"),
    ("POLICE", "AP Police", "https://education.sakshi.com/en/ap-police/previous-papers"),
    ("POLICE", "TS Police", "https://education.sakshi.com/en/ts-police/previous-papers"),
    ("SSC", "SSC", "https://www.adda247.com/exams/ssc/"),
    ("SSC", "SSC", "https://www.sscadda.com/"),
    ("SSC", "SSC", "https://ssc.gov.in/"),
    ("SSC", "SSC", "https://www.careerpower.in/ssc.html"),
    ("RAILWAY", "RRB", "https://www.adda247.com/exams/railway/"),
    ("RAILWAY", "RRB", "https://www.careerpower.in/railway.html"),
    ("RAILWAY", "RRB", "https://www.rrbcdg.gov.in/"),
    ("BANKING", "IBPS/SBI", "https://www.bankersadda.com/"),
    ("BANKING", "IBPS/SBI", "https://www.careerpower.in/bank.html"),
    ("BANKING", "IBPS", "https://www.ibps.in/"),
    ("DEFENCE", "NDA/CDS/AFCAT", "https://www.adda247.com/exams/upsc/"),
    ("DEFENCE", "NDA/CDS", "https://upsc.gov.in/examinations/previous-question-papers"),
    ("DEFENCE", "NDA/CDS", "https://education.sakshi.com/en/nda/previous-papers"),
    ("DEFENCE", "CDS", "https://education.sakshi.com/en/cds/previous-papers"),
    ("SSC", "SSC CGL", "https://education.sakshi.com/en/cgl/previous-papers"),
    ("SSC", "SSC CHSL", "https://education.sakshi.com/en/chsl/previous-papers"),
    ("BANKING", "IBPS/SBI", "https://education.sakshi.com/en/bank-exams/previous-papers"),
    ("RAILWAY", "RRB", "https://education.sakshi.com/en/rrb-exams/previous-papers"),
    ("DEFENCE", "NDA/CDS/AFCAT", "https://www.careerpower.in/defence.html"),
    ("CURRENT", "GK", "https://www.gktoday.in/quizbase/"),
]

# Sub-page links worth following from a hub
PAPER_PAGE_RE = re.compile(
    r"previous[-_ ]?(year)?[-_ ]?(question)?[-_ ]?papers?|question[-_ ]papers?|"
    r"old[-_ ]papers?|pyq|model[-_ ]papers?|answer[-_ ]?key|memory[-_ ]based", re.I)
# Which PDF links are worth queuing
PDF_GOOD_RE = re.compile(r"question|paper|pyq|shift|set|key|prelim|mains|tier|cbt|"
                         r"group|constable|\bsi\b|nda|cds|afcat|clerk|\bpo\b|ntpc|alp|"
                         r"mts|cgl|chsl|\bgd\b", re.I)
PDF_BAD_RE = re.compile(r"syllabus|admit|hall[-_ ]?ticket|result|cut-?off|notification|"
                        r"brochure|hindi|_hi\b|-hi\.pdf|advertisement|application|fee|"
                        r"analysis|salary|calendar", re.I)
# Junk hosts we never crawl
SKIP_HOSTS = ("facebook.com", "twitter.com", "x.com", "youtube.com", "instagram.com",
              "whatsapp.com", "t.me", "telegram.me", "linkedin.com", "play.google.com",
              "apps.apple.com", "amazon.", "flipkart.", "google.com", "goo.gl",
              "drive.google.com", "adda247.go.link")

CHANNEL_HINT_RE = {
    "TSPSC": re.compile(r"tspsc|telangana|group-?[1-4]|hostel|aee|\bvro\b", re.I),
    "APPSC": re.compile(r"appsc|andhra|\bap-?group|panchayat|apgenco|aptransco", re.I),
    "POLICE": re.compile(r"police|constable|\bsi\b|tslprb|slprb|sub-?inspector", re.I),
    "SSC": re.compile(r"\bssc\b|cgl|chsl|\bmts\b|\bgd\b|cpo|steno|selection-?post", re.I),
    "RAILWAY": re.compile(r"\brrb\b|railway|ntpc|\balp\b|group-?d|technician|rpf", re.I),
    "BANKING": re.compile(r"ibps|\bsbi\b|\brbi\b|bank|clerk|\bpo\b|nabard|lic|insurance", re.I),
    "DEFENCE": re.compile(r"\bnda\b|\bcds\b|afcat|agniveer|army|navy|airforce|capf|defence", re.I),
}


# ------------------------------------------------------------------ utils
def _now():
    return datetime.now(config.IST)


def _ts():
    return _now().strftime("%Y-%m-%d %H:%M")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self._cur = [], None

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
            self.links.append((self._cur[0], " ".join(self._cur[1].split())[:160]))
            self._cur = None


def _host(url):
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _fetch(url, binary=False, limit=PAGE_BYTES, timeout=FETCH_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
        final = r.geturl()
    return (data if binary else data.decode("utf-8", "replace")), final


def _probe_pdf(url):
    """Read the first bytes only: True if it really is a PDF and not huge."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-1023"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        head = r.read(1024)
        length = r.headers.get("Content-Range", "").split("/")[-1] or r.headers.get("Content-Length", "0")
    try:
        size = int(length)
    except ValueError:
        size = 0
    return head.startswith(b"%PDF") and size <= PDF_MAX_MB * 1024 * 1024


def _guess_channel(text, default):
    for ch, rx in CHANNEL_HINT_RE.items():
        if rx.search(text):
            return ch
    return default


def _guess_year(text):
    m = re.findall(r"(20[0-3]\d)", text)
    return int(m[-1]) if m else _now().year


# ------------------------------------------------------------------ stores
def _load_cands():
    d = load_json(CAND_FILE, {})
    return d if isinstance(d, dict) and "items" in d else {"items": {}, "updated": ""}


def _save_cands(d):
    items = d["items"]
    if len(items) > MAX_CANDIDATES:
        # prune oldest unverified/rejected first, keep verified
        order = sorted(items.items(), key=lambda kv: (kv[1].get("status") == "verified",
                                                      kv[1].get("seen", "")))
        for k, _ in order[: len(items) - MAX_CANDIDATES]:
            items.pop(k, None)
    d["updated"] = _ts()
    save_json_atomic(CAND_FILE, d)


def _load_state():
    st = load_json(STATE_FILE, {})
    st.setdefault("hosts", {})
    st.setdefault("errors", [])
    st.setdefault("runs", 0)
    st.setdefault("pages_seen", {})
    return st


def _save_state(st):
    st["errors"] = st["errors"][-STATE_ERRORS_KEEP:]
    # pages_seen: keep 30 days only
    cutoff = (_now() - timedelta(days=30)).strftime("%Y-%m-%d")
    st["pages_seen"] = {k: v for k, v in st["pages_seen"].items() if v >= cutoff}
    save_json_atomic(STATE_FILE, st)


def _err(st, where, e):
    st["errors"].append({"when": _ts(), "where": where[:140], "error": str(e)[:160]})


def _host_ok(st, host):
    h = st["hosts"].get(host, {})
    until = h.get("paused_until")
    return not (until and until > _ts())


def _host_fail(st, host):
    h = st["hosts"].setdefault(host, {"fails": 0})
    h["fails"] = h.get("fails", 0) + 1
    if h["fails"] >= DEAD_AFTER:
        h["paused_until"] = (_now() + timedelta(days=DEAD_PAUSE_DAYS)).strftime("%Y-%m-%d %H:%M")
        h["fails"] = 0


def _host_good(st, host):
    st["hosts"].setdefault(host, {})["fails"] = 0
    st["hosts"][host]["last_ok"] = _ts()


# ------------------------------------------------------------------ inbox cap
def enforce_inbox_cap(dry=False):
    """Keep data/pdf_inbox under INBOX_CAP_MB. Deletes oldest PDFs that are
    already ingested (present in collector seen-list) first, then oldest."""
    if not INBOX.exists():
        return {"deleted": 0, "mb": 0}
    files = [f for f in INBOX.glob("*.pdf") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    cap = INBOX_CAP_MB * 1024 * 1024
    if total <= cap:
        return {"deleted": 0, "mb": round(total / 1048576, 1)}
    try:
        from .collector import load_seen_urls
        seen = load_seen_urls()
    except Exception:
        seen = set()
    ingested = [f for f in files if f"file://{f.name}" in seen]
    others = [f for f in files if f not in ingested]
    order = sorted(ingested, key=lambda f: f.stat().st_mtime) + \
        sorted(others, key=lambda f: f.stat().st_mtime)
    deleted = 0
    for f in order:
        if total <= cap:
            break
        total -= f.stat().st_size
        if not dry:
            try:
                f.unlink()
            except OSError:
                continue
        deleted += 1
    return {"deleted": deleted, "mb": round(total / 1048576, 1)}


# ------------------------------------------------------------------ crawl
def _harvest_page(url, channel_default, st, cands, seen_urls, budget):
    """Fetch one page; return (subpages, new_candidates)."""
    host = _host(url)
    if not host or any(s in host for s in SKIP_HOSTS) or not _host_ok(st, host):
        return [], 0
    try:
        html, final = _fetch(url)
        _host_good(st, host)
    except Exception as e:
        _host_fail(st, host)
        _err(st, url, e)
        return [], 0
    p = _Links()
    try:
        p.feed(html)
    except Exception:
        return [], 0
    subpages, added = [], 0
    for href, text in p.links:
        try:
            u = urljoin(final, href.split("#")[0].strip())
        except Exception:
            continue
        if not u.startswith("http"):
            continue
        if "viewer.html" in u.lower():          # Sakshi-style pdf.js wrapper
            from .pyq import unwrap_viewer
            real = unwrap_viewer(u)
            if real != u:
                u, text = real, f"{text} {url}"  # page URL carries the paper words
        h = _host(u)
        if any(s in h for s in SKIP_HOSTS):
            continue
        blob = f"{text} {u}"
        if re.search(r"\.pdf(\?|$)", u, re.I):
            if u in seen_urls or u in cands["items"]:
                continue
            # hard reject: syllabus / admit card / hindi-only etc. always lose,
            # even if the same link also says "paper" (URLs often carry exam slugs)
            if PDF_BAD_RE.search(blob) or not PDF_GOOD_RE.search(blob):
                continue
            if budget["new"] >= MAX_NEW_PER_RUN:
                continue
            cands["items"][u] = {
                "channel": _guess_channel(blob, channel_default),
                "exam_hint": text[:100], "year": _guess_year(blob),
                "from": url, "seen": _ts(), "status": "new"}
            budget["new"] += 1
            added += 1
        elif h == host and PAPER_PAGE_RE.search(blob):
            subpages.append(u)
    return subpages, added


def run(dry=False, minutes=RUN_MINUTES, hubs=None):
    """One time-boxed discovery + promotion pass. Never raises."""
    t0 = time.time()
    deadline = t0 + minutes * 60
    st = _load_state()
    cands = _load_cands()
    stats = {"pages": 0, "new": 0, "probed": 0, "promoted": 0, "rejected": 0,
             "inbox_deleted": 0, "errors_before": len(st["errors"])}
    try:
        papers = load_json(PAPERS_FILE, {"papers": []})
        known = {p.get("url") or p.get("index") for p in papers.get("papers", [])}
        budget = {"new": 0}
        last_hit = {}
        today = _now().strftime("%Y-%m-%d")

        # ---- 1. discovery: hubs → paper pages → PDFs (round-robin so no channel starves)
        queue = [(ch, u, 0) for ch, _, u in (hubs or HUBS)]
        visited = set()
        while queue and time.time() < deadline and stats["pages"] < MAX_PAGES_PER_RUN:
            ch, url, depth = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            # skip pages already crawled in the last 3 days (hubs always re-crawled)
            last = st["pages_seen"].get(url)
            if depth > 0 and last and last >= (_now() - timedelta(days=3)).strftime("%Y-%m-%d"):
                continue
            host = _host(url)
            gap = HOST_GAP_S - (time.time() - last_hit.get(host, 0))
            if gap > 0:
                time.sleep(min(gap, HOST_GAP_S))
            last_hit[host] = time.time()
            subs, added = _harvest_page(url, ch, st, cands, known, budget)
            stats["pages"] += 1
            stats["new"] += added
            st["pages_seen"][url] = today
            if depth < 1:
                for s in subs[:12]:
                    queue.append((ch, s, depth + 1))

        # ---- 2. promotion: probe 'new' candidates, append verified to pyq_papers.json
        new_items = [(u, c) for u, c in cands["items"].items() if c.get("status") == "new"]
        new_items.sort(key=lambda kv: -kv[1].get("year", 0))     # newest papers first
        appended = []
        for u, c in new_items[:MAX_PROMOTE_PER_RUN]:
            if time.time() >= deadline:
                break
            host = _host(u)
            if not _host_ok(st, host):
                continue
            stats["probed"] += 1
            try:
                ok = _probe_pdf(u)
                _host_good(st, host)
            except Exception as e:
                ok = False
                _host_fail(st, host)
                _err(st, u, e)
            if ok and u not in known:
                c["status"] = "verified"
                c["verified"] = _ts()
                entry = {"channel": c["channel"], "exam": (c.get("exam_hint") or c["channel"])[:80],
                         "year": c.get("year", _now().year), "paper": "auto-discovered",
                         "lang": "en", "via": f"scout {today} ← {_host(c.get('from', ''))}",
                         "url": u}
                appended.append(entry)
                known.add(u)
                stats["promoted"] += 1
            else:
                c["status"] = "rejected"
                stats["rejected"] += 1
        if appended and not dry:
            papers.setdefault("papers", []).extend(appended)
            papers["updated"] = today
            save_json_atomic(PAPERS_FILE, papers)

        # ---- 3. storage hygiene
        stats["inbox_deleted"] = enforce_inbox_cap(dry=dry)["deleted"]
    except Exception as e:                       # belt and braces: never crash
        _err(st, "run", e)
    finally:
        st["runs"] += 1
        st["last_run"] = _ts()
        st["last_stats"] = stats
        if not dry:
            try:
                _save_cands(cands)
                _save_state(st)
            except Exception as e:
                print(f"   [scout] state save note: {e}")
    stats["seconds"] = int(time.time() - t0)
    print(f"[scout] {stats}")
    return stats


def status_text():
    st = _load_state()
    cands = _load_cands()["items"]
    by = {}
    for c in cands.values():
        by.setdefault(c.get("status", "?"), 0)
        by[c["status"]] += 1
    paused = [h for h, v in st["hosts"].items() if v.get("paused_until", "") > _ts()]
    inbox_mb = 0.0
    if INBOX.exists():
        inbox_mb = round(sum(f.stat().st_size for f in INBOX.glob("*.pdf")) / 1048576, 1)
    lines = [f"🔭 Scout: {st.get('runs', 0)} runs · last {st.get('last_run', '—')}",
             f"  queue: {len(cands)}/{MAX_CANDIDATES} → " +
             ", ".join(f"{k} {v}" for k, v in sorted(by.items())),
             f"  last run: {st.get('last_stats', {})}",
             f"  inbox: {inbox_mb} MB / {INBOX_CAP_MB} MB cap",
             f"  paused hosts: {', '.join(paused) or 'none'}",
             f"  recent errors: {len(st.get('errors', []))}"]
    return "\n".join(lines)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "status":
        print(status_text())
    elif a[0] == "run":
        mins = int(a[a.index("--minutes") + 1]) if "--minutes" in a else RUN_MINUTES
        run(dry="--dry" in a, minutes=mins)
    elif a[0] == "hubs":
        for ch, ex, u in HUBS:
            print(f"{ch:8} {ex:14} {u}")
    else:
        print(__doc__)
