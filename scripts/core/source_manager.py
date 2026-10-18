#!/usr/bin/env python3
"""
STUDENTUP — SOURCE MANAGER (easy source setup, no JSON editing)
================================================================
Add / discover / list / enable / disable quiz sources from the command
line. New sources are added as CANDIDATES: the daily content-gated auditor
auto-enables them only when they really serve fresh quiz questions —
so adding a source can never pollute the polls.

CLI (run from scripts/):
  python3 -m core.source_manager stats
  python3 -m core.source_manager list [--enabled|--candidates] [--exam banking]
  python3 -m core.source_manager discover https://any-exam-site.example/
  python3 -m core.source_manager add https://any-exam-site.example/feed --exam banking --name "My Source"
  python3 -m core.source_manager add https://site.example/quiz/ --type index --exam ssc
  python3 -m core.source_manager enable "My Source"   /  disable "My Source"

`discover` fetches the site's homepage, finds its REAL advertised feed
(<link rel=alternate>), its sitemap, and tells you the exact `add` command.
Everything is stdlib; network is used only by discover/audit paths.
"""
from __future__ import annotations

import re
import sys
from urllib.parse import urlparse

from . import collector
from .store import load_json, save_json_atomic

REG = collector.REGISTRY


def _load():
    data = load_json(REG, {"sources": [], "defaults": {}})
    if not isinstance(data, dict) or "sources" not in data:
        data = {"sources": [], "defaults": {}}
    return data


def _save(data):
    save_json_atomic(REG, data)


def _norm(u):
    return (u or "").strip().rstrip("/").lower()


def stats() -> dict:
    data = _load()
    srcs = data.get("sources", [])
    out = {
        "total": len(srcs),
        "live_enabled": sum(1 for s in srcs if s.get("enabled")),
        "candidates_waiting_audit": sum(
            1 for s in srcs if not s.get("enabled")
            and s.get("auto_enable_if_live")),
        "archive_dead": sum(
            1 for s in srcs if not s.get("enabled")
            and not s.get("auto_enable_if_live")),
        "rss": sum(1 for s in srcs if s.get("type") == "rss"),
        "index": sum(1 for s in srcs if s.get("type") == "index"),
        "with_sitemap_field": sum(1 for s in srcs if s.get("sitemap")),
        "with_pdf_harvest": sum(1 for s in srcs if s.get("pdf_re")),
        "domains": len({urlparse(s.get("feed") or s.get("url") or "").netloc
                        for s in srcs}),
        # 📈 bank growth — collector (watch.py, 8x/day) keeps adding to
        # this number; it must never stay frozen at the seed bank size.
        "bank_questions": _bank_count(),
    }
    out.update(_pyq_stats())
    return out


def _pyq_stats() -> dict:
    """📜 Previous-exam (PYQ) coverage: questions in bank + papers harvested."""
    try:
        from core import config
        from core.store import load_json
        d = load_json(config.DATA / "question_bank.json", {})
        qs = d if isinstance(d, list) else d.get("questions", []) or []
        pyq_qs = [q for q in qs if q.get("source") == "pyq"]
        papers = load_json(config.DATA / "pyq_papers.json", {}).get("papers", [])
        state = load_json(config.DATA / "pyq_state.json", {})
        done = sum(1 for pp in papers
                   if state.get(pp.get("url") or pp.get("index"), {}).get("status") == "done")
        return {
            "pyq_questions": len(pyq_qs),
            "pyq_papers_harvested": f"{done}/{len(papers)}",
        }
    except Exception:
        return {"pyq_questions": 0, "pyq_papers_harvested": "0/0"}


def _bank_count() -> int:
    try:
        from core import config  # local import: keeps CLI start fast
        from core.store import load_json
        d = load_json(config.DATA / "question_bank.json", {})
        if isinstance(d, list):
            return len(d)
        return len(d.get("questions", []) or [])
    except Exception:
        return 0


def find_source(data, needle):
    n = (needle or "").lower()
    for s in data.get("sources", []):
        if s.get("name", "").lower() == n:
            return s
    for s in data.get("sources", []):
        if n and n in s.get("name", "").lower():
            return s
    return None


def add_source(url, exam="all", name="", stype="", link_re="",
               sitemap="", dry=False) -> dict:
    """Add one source as a content-gated candidate. Returns a result dict
    ({added, reason, source}); never enables directly, never duplicates."""
    data = _load()
    url = (url or "").strip()
    if not url.startswith("https://"):
        return {"added": False, "reason": "url must start with https://"}
    for s in data["sources"]:
        if _norm(s.get("feed") or s.get("url") or "") == _norm(url):
            return {"added": False,
                    "reason": f"already registered as {s.get('name')!r}"}
    if not stype:
        stype = "rss" if collector.is_feed_url(url) or url.rstrip("/").endswith(
            ("/feed", ".xml", "/rss")) else "index"
    host = urlparse(url).netloc
    if not name:
        name = host.replace("www.", "").split(".")[0].title() + " Quiz"
    if any(s.get("name", "").lower() == name.lower() for s in data["sources"]):
        name = f"{name} ({host})"
    sample = next((s for s in data["sources"] if s.get("title_must")), {})
    if stype == "rss":
        src = {"name": name, "enabled": False, "type": "rss", "exam": exam,
               "feed": url,
               "title_must": sample.get("title_must", r"quiz|mcq|questions?"),
               "title_not": sample.get("title_not", r"(?!)\Z"),
               "auto_enable_if_live": True,
               "audit": {"status": "unverified", "checked": "via source_manager",
                         "note": "added by source_manager - content-gated "
                                 "auto-enable only"}}
    else:
        esc = re.escape(host)
        src = {"name": name, "enabled": False, "type": "index", "exam": exam,
               "url": url,
               "link_re": link_re or rf"^https://{esc}/[a-z0-9\-/]+$",
               "max_links": 2, "auto_enable_if_live": True,
               "audit": {"status": "unverified", "checked": "via source_manager",
                         "note": "added by source_manager - content-gated "
                                 "auto-enable only"}}
        if sitemap:
            src["sitemap"] = sitemap
    if not dry:
        data["sources"].append(src)
        _save(data)
    return {"added": True, "reason": "candidate added (auditor will "
            "auto-enable after a live content check)", "source": src}


def set_enabled(needle, enabled, dry=False) -> dict:
    data = _load()
    s = find_source(data, needle)
    if not s:
        return {"changed": False, "reason": f"no source matching {needle!r}"}
    s["enabled"] = bool(enabled)
    if enabled:
        s.setdefault("audit", {})["status"] = "live"
    if not dry:
        _save(data)
    return {"changed": True, "source": s.get("name"), "enabled": bool(enabled)}


def discover(url) -> dict:
    """Fetch a site and report its real feed(s), sitemap and quiz links —
    the recon step before `add` (no guessing of /feed URLs)."""
    page = collector.http_get(url, respect_robots=False)
    if not page:
        return {"ok": False, "reason": f"could not fetch {url}"}
    feeds = collector.discover_feed_urls(page, url)
    host = urlparse(url)
    sitemap = f"{host.scheme}://{host.netloc}/sitemap.xml"
    sm_links = collector.fetch_sitemap_links(sitemap, r"quiz|mcq|question")
    quiz_links = collector.extract_links(page, url, r"quiz|mcq|questions?")
    return {"ok": True, "feeds": feeds, "sitemap": sitemap,
            "sitemap_quiz_links": len(sm_links), "quiz_links": len(quiz_links),
            "suggested": (f'add {feeds[0]} --exam all' if feeds else
                          f"add {url} --type index --exam all")}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]

    def opt(flag, default=""):
        return rest[rest.index(flag) + 1] if flag in rest and \
            rest.index(flag) + 1 < len(rest) else default

    if cmd == "stats":
        st = stats()
        for k, v in st.items():
            print(f"  {k:26s} {v}")
        return 0
    if cmd == "list":
        data = _load()
        exam = opt("--exam")
        for s in data["sources"]:
            if "--enabled" in rest and not s.get("enabled"):
                continue
            if "--candidates" in rest and (s.get("enabled")
                                           or not s.get("auto_enable_if_live")):
                continue
            if exam and exam not in s.get("exam", ""):
                continue
            print(f"  [{'ON ' if s.get('enabled') else 'off'}] "
                  f"{s.get('name'):52s} {s.get('type'):5s} {s.get('exam','')}")
        return 0
    if cmd == "add":
        if not rest:
            print("usage: add <url> [--exam banking] [--name X] [--type rss|index]")
            return 2
        r = add_source(rest[0], exam=opt("--exam", "all") or "all",
                       name=opt("--name"), stype=opt("--type"),
                       link_re=opt("--link-re"), sitemap=opt("--sitemap"))
        print(("✅ " if r["added"] else "⚠️ ") + r["reason"])
        if r.get("source"):
            print(f"   {r['source']['name']} :: "
                  f"{r['source'].get('feed') or r['source'].get('url')}")
        return 0 if r["added"] else 1
    if cmd in ("enable", "disable"):
        if not rest:
            print(f"usage: {cmd} \"<source name>\"")
            return 2
        r = set_enabled(rest[0], cmd == "enable")
        print(("✅ " if r["changed"] else "⚠️ ") + str(r))
        return 0 if r["changed"] else 1
    if cmd == "discover":
        if not rest:
            print("usage: discover <site-url>")
            return 2
        r = discover(rest[0])
        if not r["ok"]:
            print("⚠️ " + r["reason"])
            return 1
        print(f"  feeds advertised : {r['feeds'] or 'none'}")
        print(f"  sitemap          : {r['sitemap']} "
              f"({r['sitemap_quiz_links']} quiz links via sitemap)")
        print(f"  quiz links on page: {r['quiz_links']}")
        print(f"  suggested: python3 -m core.source_manager {r['suggested']}")
        return 0
    print(f"unknown command {cmd!r} — try: stats | list | add | discover | "
          "enable | disable")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
