#!/usr/bin/env python3
"""
STUDENTUP — RSS FEED AGGREGATOR
- Fetches all configured CA + Jobs feeds (stdlib urllib + xml, feedparser fallback).
- Per-entry filters: blocked-topic, 2-tier jobs relevance, other-state hard block.
- Dedup across ca/jobs/global stores (Jaccard + shingle), in-batch collapse.
- Telugu translation via LLM rotation (graceful fallback).
- Writes data/aggregated_ca.json and data/aggregated_jobs.json.
Never crashes on a dead feed — logs and skips.
"""
from __future__ import annotations

import re
import time
import html
import urllib.request
import urllib.error
from xml.etree import ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import config
from .store import Dedup, save_json_atomic, load_json
from .content import jobs_relevance, ca_relevance, is_other_state, is_blocked
from .translator import translate_batch

try:
    import feedparser  # optional
    _HAS_FP = True
except Exception:
    _HAS_FP = False

USER_AGENT = "StudentUpBot/3.0 (+https://studentup.in; quiz feed reader)"

# Exam-relevant feeds (TS/AP + national/current-affairs + jobs).
FEEDS = {
    "ca": [
        ("AffairsCloud", "https://affairscloud.com/feed"),
        ("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss"),
        ("The Hindu Business", "https://www.thehindu.com/business/feeder/default.rss"),
        ("India Today", "https://www.indiatoday.in/rss/india"),
        ("TOI Top", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"),
        ("ET Top", "https://economictimes.indiatimes.com/rssfeedstopstories.cms"),
        ("Insights on India", "https://www.insightsonindia.com/feed"),
        ("PIB Delhi", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"),
    ],
    "jobs": [
        ("FreeJobAlert", "https://www.freejobalert.com/feed"),
        ("SarkariYojana", "https://www.sarkariyojana.com/feed"),
        ("AffairsCloud Jobs", "https://affairscloud.com/feed"),
        ("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss"),
    ],
}


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_dt(entry):
    for key in ("published", "updated", "pubDate"):
        val = entry.get(key)
        if not val:
            continue
        try:
            dt = parsedate_to_datetime(val)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            pass
    return None


def fetch_feed(name, url, timeout=15):
    """Return list of {title, link, published} using feedparser if available, else stdlib."""
    if _HAS_FP:
        try:
            d = feedparser.parse(url, agent=USER_AGENT)
            out = []
            for e in d.entries[:25]:
                out.append({
                    "title": _clean(getattr(e, "title", "")),
                    "link": getattr(e, "link", ""),
                    "published": getattr(e, "published", ""),
                })
            return out
        except Exception as ex:
            print(f"   [feed] {name} feedparser error: {ex} — trying stdlib")
    # stdlib fallback
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        out = []
        # RSS 2.0
        for item in root.iter("item"):
            title = _clean(item.findtext("title", ""))
            link = _clean(item.findtext("link", ""))
            pub = item.findtext("pubDate", "")
            if title:
                out.append({"title": title, "link": link, "published": pub})
        # Atom
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            title = _clean(entry.findtext("a:title", "", ns))
            link_el = entry.find("a:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            pub = entry.findtext("a:updated", "", ns)
            if title:
                out.append({"title": title, "link": link, "published": pub})
        return out[:25]
    except Exception as ex:
        print(f"   [feed] {name} DEAD/SKIP ({type(ex).__name__}: {str(ex)[:80]})")
        return []


def aggregate(dry=False, translate=True, max_ca=6, max_jobs=5, max_age_hours=72):
    dedup = Dedup()
    ca_items, jobs_items = [], []
    stats = {"feeds_ok": 0, "feeds_dead": 0, "entries": 0,
             "ca_kept": 0, "jobs_kept": 0, "blocked": 0, "dup": 0}

    for scope, feeds in FEEDS.items():
        for name, url in feeds:
            entries = fetch_feed(name, url)
            if entries is None:
                stats["feeds_dead"] += 1
                continue
            stats["feeds_ok"] += 1 if entries else 0
            stats["feeds_dead"] += 0 if entries else 1
            stats["entries"] += len(entries)
            for e in entries:
                title = e["title"]
                if not title:
                    continue
                blocked, _ = is_blocked(title)
                if blocked:
                    stats["blocked"] += 1
                    continue
                if is_other_state(title) and scope == "jobs":
                    stats["blocked"] += 1
                    continue
                if dedup.seen(title, scope="ca" if scope == "ca" else "jobs"):
                    stats["dup"] += 1
                    continue
                if scope == "ca":
                    if not ca_relevance(title):
                        continue
                    if len(ca_items) >= max_ca:
                        continue
                    ca_items.append({"en": title, "te": "", "link": e["link"],
                                     "source": name})
                    if not dry:
                        dedup.mark(title, "ca", {"source": name})
                    stats["ca_kept"] += 1
                else:
                    rel = jobs_relevance(title)
                    if rel.startswith("drop"):
                        if rel == "drop:no_relevance":
                            continue
                        stats["blocked"] += 1
                        continue
                    if len(jobs_items) >= max_jobs:
                        continue
                    jobs_items.append({"en": title, "te": "", "link": e["link"],
                                       "source": name})
                    if not dry:
                        dedup.mark(title, "jobs", {"source": name})
                    stats["jobs_kept"] += 1
            time.sleep(0.4)

    # in-batch collapse
    ca_items = dedup.batch_collapse(ca_items, key=lambda x: x["en"])[:max_ca]
    jobs_items = dedup.batch_collapse(jobs_items, key=lambda x: x["en"])[:max_jobs]

    if translate:
        try:
            translate_batch(ca_items)
            translate_batch(jobs_items)
        except Exception as ex:
            print(f"   [translate] batch note: {ex}")

    save_json_atomic(config.DATA / "aggregated_ca.json",
                     {"items": ca_items, "stats": stats,
                      "ts": datetime.now(config.IST).isoformat()})
    save_json_atomic(config.DATA / "aggregated_jobs.json",
                     {"items": jobs_items, "stats": stats,
                      "ts": datetime.now(config.IST).isoformat()})
    print(f"FEEDS — ok={stats['feeds_ok']} dead={stats['feeds_dead']} "
          f"entries={stats['entries']} CA={len(ca_items)} JOBS={len(jobs_items)} "
          f"blocked={stats['blocked']} dup={stats['dup']}")
    return ca_items, jobs_items, stats


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-translate", action="store_true")
    a = ap.parse_args()
    ca, jobs, _ = aggregate(dry=a.dry, translate=not a.no_translate)
    print("\n— CA —")
    for i in ca:
        print(" •", i["en"], ("| " + i["te"][:40]) if i["te"] else "")
    print("\n— JOBS —")
    for i in jobs:
        print(" •", i["en"])
