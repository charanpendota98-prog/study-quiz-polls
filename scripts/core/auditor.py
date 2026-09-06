#!/usr/bin/env python3
"""
STUDENTUP — CENTRAL SOURCE AUDITOR (deep, content-gated, automated)
====================================================================
Audits EVERY source in the central registry (data/collector_sources.json):
RSS feeds, deep index crawls, news feeds — checking reachability, feed parse,
entry freshness and whether the item titles actually match the source's quiz
filter (content-gate). Nothing is trusted on "HTTP 200" alone.

Behaviours (all safe, all reversible):
  * Writes per-source health to data/collector_health.json (atomic).
  * Candidates (enabled=false + auto_enable_if_live=true) are auto-enabled
    ONLY when: fetch OK + feed has entries + content matches the quiz filter
    + content is fresh (<= 14 days). No junk, no guesses.
  * Enabled sources are auto-disabled after 3 consecutive dead audits and
    re-enabled automatically if they come back live (content-gated again).
  * Collector health-paused sources are unpaused the moment they pass a live,
    content-gated check.

CLI:
  python3 -m core.auditor                     # full audit + registry update
  python3 -m core.auditor --no-write          # check only, touch nothing
  python3 -m core.auditor --only-enabled      # skip archive/candidates
  python3 scripts/audit_sources.py            # same, prints a summary table
"""
from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime

from . import config
from . import collector
from .store import load_json, save_json_atomic

STALE_DAYS = 30          # feed newer than this = "stale" (warn)
AUTO_ENABLE_MAX_AGE = 14  # candidates must also be FRESH to auto-enable
AUTO_DISABLE_FAILURES = collector.AUTO_PAUSE_AFTER_FAILURES


# ---------------------------------------------------------------------------
# Single-source check (injectable HTTP/parse hooks => fully testable offline)
# ---------------------------------------------------------------------------
def _parse_date(v: str):
    if not v:
        return None
    try:
        dt = parsedate_to_datetime(v)
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def check_source(src, http_get=collector.http_get,
                 feed_entries=collector._feed_entries,
                 extract_links=collector.extract_links) -> dict:
    """Return {'status', 'entries', 'newest', 'freshness_days', 'links',
    'content_ok', 'checked', 'error'} for one registry source. Never raises."""
    name = src.get("name", "?")
    now = datetime.now(config.IST)
    res = {"status": "dead", "entries": 0, "newest": None,
           "freshness_days": None, "links": 0, "content_ok": False,
           "checked": now.strftime("%Y-%m-%d %H:%M:%S"), "error": ""}
    try:
        if src.get("type") == "index":
            page = http_get(src["url"])
            if not page:
                res["error"] = "index page fetch failed"
                return res
            links = extract_links(page, src["url"], src.get("link_re", r"(?!)"))
            pages = (extract_links(page, src["url"], src["page_re"])
                     if src.get("page_re") else [])
            res["links"] = len(links) + len(pages)
            # CONTENT gate: the page must yield quiz links/pagination OR carry
            # parseable MCQs itself (GKToday/Examveda topic pages do).
            n_q = 0
            try:
                n_q = len(collector.parse_page(src, page, src.get("name", ""),
                                               src["url"]))
            except Exception:
                n_q = 0
            res["questions"] = n_q
            res["content_ok"] = res["links"] > 0 or n_q > 0
            res["status"] = "live" if res["content_ok"] else "warn"
            if res["status"] == "warn":
                res["error"] = "page fetched but no quiz links and no parseable MCQs"
            return res

        # RSS / Atom
        entries = feed_entries(src["feed"])
        res["entries"] = len(entries)
        if not entries:
            res["error"] = "feed returned 0 entries (dead/empty/unparseable)"
            return res
        dates = [_parse_date(e.get("published", "")) for e in entries]
        dates = [d for d in dates if d]
        if dates:
            newest = max(dates)
            res["newest"] = newest.strftime("%Y-%m-%d %H:%M:%S")
            res["freshness_days"] = max(
                0, (now - newest.astimezone(config.UTC)).days)
        # content gate: at least one entry must match must/not filters
        must = re.compile(src.get("title_must", r"quiz|questions|mcq"), re.I)
        notp = re.compile(src.get("title_not", r"(?!)\Z"), re.I)
        res["content_ok"] = any(
            must.search(e["title"]) and not notp.search(e["title"])
            for e in entries)
        if not res["content_ok"]:
            res["status"] = "warn"
            res["error"] = "feed is live but no items match the quiz filter"
        elif res["freshness_days"] is not None and res["freshness_days"] > STALE_DAYS:
            res["status"] = "warn"
            res["error"] = f"stale: newest item {res['freshness_days']} days old"
        else:
            res["status"] = "live"
        return res
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return res


# ---------------------------------------------------------------------------
# Full audit
# ---------------------------------------------------------------------------
def audit_all(update_registry: bool = True, only_enabled: bool = False,
              registry_path=None, health_path=None,
              http_get=collector.http_get,
              feed_entries=collector._feed_entries,
              extract_links=collector.extract_links,
              verbose: bool = True) -> dict:
    """Audit the central registry + news feeds. Returns summary dict.
    update_registry=False = check-only mode (no files touched except health
    when health_path given)."""
    reg_path = registry_path or collector.REGISTRY
    hpath = health_path or collector.HEALTH
    data = load_json(reg_path, {})
    srcs = data.get("sources", [])
    summary = {"checked": 0, "live": 0, "warn": 0, "dead": 0, "skipped": 0,
               "enabled_changed": [], "news": {}}

    for i, src in enumerate(srcs):
        name = src.get("name", "?")
        if only_enabled and not src.get("enabled", True):
            summary["skipped"] += 1
            continue
        r = check_source(src, http_get=http_get, feed_entries=feed_entries,
                         extract_links=extract_links)
        ok = r["status"] != "dead"
        if hpath is not None:
            collector.record_health(name, ok,
                                    r["error"] or f"{r['entries']} entries",
                                    path=hpath)
        summary["checked"] += 1
        summary[r["status"]] = summary.get(r["status"], 0) + 1

        # ---- auto-enable candidates (content-gated + fresh) ---------------
        if (not src.get("enabled", True)
                and src.get("auto_enable_if_live")
                and r["status"] == "live" and r["content_ok"]):
            age = r["freshness_days"]
            if age is None or age <= AUTO_ENABLE_MAX_AGE:
                src["enabled"] = True
                src.setdefault("audit", {})["status"] = "live"
                src["audit"]["last_checked"] = r["checked"]
                src["audit"]["note"] = ("auto-enabled: content-gated audit "
                                        f"passed ({r['entries']} entries, "
                                        f"newest {age if age is not None else '?'}d)")
                summary["enabled_changed"].append(f"+ {name}")
                if verbose:
                    print(f"   [audit] AUTO-ENABLE {name} "
                          f"({r['entries']} entries, fresh={age}d)")

        # ---- auto-disable confirmed-dead enabled sources ------------------
        if src.get("enabled", True) and r["status"] == "dead":
            health = load_json(hpath, {"sources": {}}) if hpath else {"sources": {}}
            fails = (health.get("sources", {})
                     .get(name, {}).get("consecutive_failures", 1))
            if fails >= AUTO_DISABLE_FAILURES:
                src["enabled"] = False
                src.setdefault("audit", {})["status"] = "dead"
                src["audit"]["last_checked"] = r["checked"]
                src["audit"]["note"] = (f"auto-disabled: {fails} consecutive "
                                        f"dead audits — {r['error'][:120]}")
                summary["enabled_changed"].append(f"- {name}")
                if verbose:
                    print(f"   [audit] AUTO-DISABLE {name} ({fails} fails)")

        # ---- update audit metadata on every checked source ----------------
        src.setdefault("audit", {})["last_checked"] = r["checked"]
        if r["status"] in ("live", "warn", "dead") and not src["enabled"]:
            # keep history notes; never overwrite a verified status with
            # a transient warn — only dead/live get recorded here
            if r["status"] == "dead" or not src["audit"].get("status"):
                src["audit"]["status"] = r["status"]

    # ---- news feeds (CA + jobs) — checked, status stored separately -------
    news = {}
    for scope, feeds in (data.get("news_feeds") or {}).items():
        news[scope] = []
        for row in feeds:
            name, url = row[0], row[1]
            try:
                entries = feed_entries(url)
                ok = len(entries) > 0
                news[scope].append({"name": name, "url": url,
                                    "ok": ok, "entries": len(entries),
                                    "checked": datetime.now(config.IST)
                                    .strftime("%Y-%m-%d %H:%M:%S")})
                if verbose:
                    print(f"   [audit] news {scope}/{name}: "
                          f"{len(entries)} entries")
            except Exception as e:
                news[scope].append({"name": name, "url": url, "ok": False,
                                    "entries": 0,
                                    "error": str(e)[:80]})
    summary["news"] = news

    if update_registry and reg_path is not None:
        save_json_atomic(reg_path, data)

    if verbose:
        print(f"[audit] checked={summary['checked']} live={summary['live']} "
              f"warn={summary.get('warn', 0)} dead={summary['dead']} "
              f"changes={summary['enabled_changed']}")
    return summary


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true",
                    help="check only, do not update the registry")
    ap.add_argument("--only-enabled", action="store_true",
                    help="skip archive/candidate sources")
    args = ap.parse_args()
    audit_all(update_registry=not args.no_write,
              only_enabled=args.only_enabled)
