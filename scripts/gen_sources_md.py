#!/usr/bin/env python3
"""Generate sources/SOURCES.md (per-exam listing) from data/collector_sources.json.

Usage: python3 scripts/gen_sources_md.py
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "collector_sources.json"
OUT = ROOT / "sources" / "SOURCES.md"

CHANNELS = [
    ("TSPSC (Telangana Groups / other TG exams)", {"tspsc", "tgpsc", "telangana"}),
    ("APPSC (AP Groups / other AP exams)", {"appsc", "andhra", "ap"}),
    ("Police (TS/AP SI & Constable)", {"police", "tslprb", "si", "constable"}),
    ("SSC (CGL/CHSL/MTS/GD)", {"ssc"}),
    ("Banking (IBPS/SBI/RBI)", {"banking", "bank", "ibps", "sbi", "rbi"}),
    ("Railway (RRB NTPC/Group D/ALP)", {"railway", "rrb"}),
    ("Defence (NDA/CDS/Agniveer)", {"defence", "nda", "cds"}),
    ("UPSC / General Studies", {"upsc", "gs"}),
    ("Current Affairs", {"current", "affairs", "current-affairs", "ca"}),
]


def _tokens(exam: str) -> set[str]:
    toks = set()
    for t in exam.replace("|", "-").replace(",", "-").split("-"):
        t = t.strip().lower()
        if t:
            toks.add(t)
    if "current-affairs" in exam:
        toks.add("current-affairs")
    return toks


def _row(s: dict) -> str:
    typ = f"`{s.get('type', '')}`"
    flags = []
    if s.get("lang") == "te":
        flags.append("`te`")
    if s.get("pdf_re"):
        flags.append("`pdf`")
    url = s.get("url") or s.get("feed") or ""
    note = (s.get("audit", {}).get("note") or "").replace("|", "/")
    note = note.replace("live / verified", "verified").strip()
    if note.startswith("live /"):
        note = note[6:].strip()
    return f"| {s['name']} | {typ} {' '.join(flags)} | {url} | {note[:160]} |"


def main() -> None:
    doc = json.loads(REG.read_text())
    srcs = doc["sources"] if isinstance(doc, dict) else doc
    live = [s for s in srcs if s.get("enabled")]
    cand = [s for s in srcs if not s.get("enabled") and s.get("auto_enable_if_live")]
    arch = [s for s in srcs if not s.get("enabled") and not s.get("auto_enable_if_live")]
    today = dt.date.today().isoformat()
    lines = [
        f"# StudentUp — Complete Source Registry (v4.2, generated {today})",
        "",
        "Source of truth: `data/collector_sources.json` (regenerate with `python3 scripts/rebuild_registry.py`,"
        " then `python3 scripts/gen_sources_md.py`).",
        "",
        f"**Totals:** {len(srcs)} sources — {len(live)} live (verified, scraped daily), "
        f"{len(cand)} candidates (auditor auto-enables once quiz content is confirmed), "
        f"{len(arch)} archive/dead (never used).",
        "",
        "Legend: 🟢 live · 🟡 candidate · `index` = deep crawl listing→articles, `rss` = feed · "
        "`te` = Telugu-native (no translation) · `pdf` = previous-paper PDFs auto-harvested. "
        "A source tagged for several exams appears under each.",
        "",
    ]
    hdr = ["| Source | Type | URL | Notes |", "|---|---|---|---|"]
    used = set()
    for title, keys in CHANNELS:
        l_rows = [s for s in live if _tokens(s.get("exam", "")) & keys]
        c_rows = [s for s in cand if _tokens(s.get("exam", "")) & keys]
        for s in l_rows + c_rows:
            used.add(s["name"])
        if not l_rows and not c_rows:
            continue
        lines += [f"## {title}", ""]
        if l_rows:
            lines += [f"### 🟢 Live ({len(l_rows)})", ""] + hdr + [_row(s) for s in l_rows] + [""]
        if c_rows:
            lines += [f"### 🟡 Candidates ({len(c_rows)})", ""] + hdr + [_row(s) for s in c_rows] + [""]
    shared_l = [s for s in live if s["name"] not in used or "all" in _tokens(s.get("exam", ""))]
    shared_c = [s for s in cand if s["name"] not in used or "all" in _tokens(s.get("exam", ""))]
    lines += ["## All exams (shared reasoning / aptitude / GK)", ""]
    if shared_l:
        lines += [f"### 🟢 Live ({len(shared_l)})", ""] + hdr + [_row(s) for s in shared_l] + [""]
    if shared_c:
        lines += [f"### 🟡 Candidates ({len(shared_c)})", ""] + hdr + [_row(s) for s in shared_c] + [""]
    lines += [
        f"## ⚫ Archive / dead (not used) — {len(arch)}", "",
        "Checked and rejected (dead domain, paywall, JS-only, redirect to home, parked domain, news-only). "
        "Kept so the auditor never re-adds them.", "",
        "| Source | Reason |", "|---|---|",
    ]
    for s in arch:
        note = (s.get("audit", {}).get("note") or "").replace("|", "/")
        lines.append(f"| {s['name'].removeprefix('ARCHIVE:')} | {s.get('audit', {}).get('status', '')} | {note[:110]} |")
    lines += [
        "", "## How new sources get in", "",
        "1. Add in `scripts/rebuild_registry.py` (`_index` = verified live, `_cand_index` = unverified), "
        "run `--check` and rebuild.",
        "2. `scripts/audit_sources.py` (04:45 daily) content-gates every source: live ones that stop returning "
        "MCQs pause after 3 failures; candidates that return MCQs auto-enable.",
        "3. Every question passes the language gate (Telugu kept; English/Hindi → `translate_mcq` with "
        "number/script/duplicate checks, else parked) and the exam-blueprint gate before reaching a channel.",
        "",
    ]
    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT} ({len(srcs)} sources, {len(live)} live, {len(cand)} cand, {len(arch)} arch)")


if __name__ == "__main__":
    main()
