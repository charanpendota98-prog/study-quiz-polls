#!/usr/bin/env python3
"""
STUDENTUP — WEB SEARCH UTILITY (Serper.dev)
===========================================
Optional Google-search wrapper used for deep source discovery and QA
(checks a URL/query live without hard-coding). Requires in env/.env:

    SERPER_API_KEY=997c...

CLI:
  python3 -m core.search "TSPSC group 4 previous papers 2026"   # print results
  python3 -m core.search --json "IBPS daily quiz 2026"          # raw JSON
"""
from __future__ import annotations

import json
import urllib.request

from . import config


def web_search(query: str, limit: int = 10) -> list[dict]:
    """Serper Google search. Returns [{title, link, snippet}]. Empty on no key."""
    key = config.env("SERPER_API_KEY", "")
    if not key:
        print("   [search] SERPER_API_KEY not set — web search disabled")
        return []
    body = json.dumps({"q": query, "num": limit, "gl": "in",
                       "hl": "en"}).encode("utf-8")
    req = urllib.request.Request(
        "https://google.serper.dev/search",
        data=body,
        headers={"X-API-KEY": key, "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"   [search] failed: {e}")
        return []
    out = []
    for it in data.get("organic", [])[:limit]:
        out.append({"title": it.get("title", ""),
                    "link": it.get("link", ""),
                    "snippet": it.get("snippet", "")})
    return out


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "TSPSC previous papers"
    for r in web_search(q):
        print(f"{r['title']}\n  {r['link']}\n  {r['snippet'][:120]}\n")
