#!/usr/bin/env python3
"""
STUDENTUP — CENTRAL SOURCE REGISTRY BUILDER (single source of truth)
====================================================================
Regenerates  data/collector_sources.json  from the definitions below.

Every EXAM-QUIZ source, every CA/JOBS feed and every known-dead / archive
source lives in ONE central registry that the collector, auditor, feeds
aggregator and health checks all read.

Safety rules baked into the registry:
  * enabled=true  -> source was AUDITED and verified live (see audit note).
  * enabled=false + auto_enable_if_live=true -> candidate; the daily auditor
    may auto-enable it ONLY after a real check shows a live feed whose items
    also pass the source's title filter (content_ok). No junk, no guesses.
  * enabled=false + status=dead -> confirmed dead (500/404/TLS/junk). Never
    auto-enabled.

Usage:
  python3 rebuild_registry.py            # write data/collector_sources.json
  python3 rebuild_registry.py --check    # validate only, no write
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "collector_sources.json"

# ---------------------------------------------------------------------------
# Shared title filters (same philosophy as the engine: quiz pages ONLY)
# ---------------------------------------------------------------------------
QUIZ_MUST = (r"quiz|mcq|questions?|practice set|practice questions|model paper|"
             r"mock|reasoning|quant|aptitude|general awareness|general knowledge|"
             r"\bgk\b|previous year|memory based")
QUIZ_NOT = (r"notification|admit card|hall ticket|result|cut[\s-]?off|syllabus|"
            r"editorial|interview|recruitment|vacancy|salary|eligibility|exam date|"
            r"exam analysis|answer key|apply online|registration|motivation|topper|"
            r"schedule|mindmap|test series launch|webinar|course|success stor")

IBX = "https://www.indiabix.com"
IBX_ESCAPED = IBX.replace(".", r"\.")

def _ibx(section: str, exam: str, note: str, max_pages: int = 2) -> dict:
    """Deep-crawl source for one IndiaBIX section (verified markup)."""
    return {
        "name": f"IndiaBIX {section.title().replace('-', ' ')}",
        "enabled": True,
        "type": "index",
        "exam": exam,
        "adapter": "indiabix",
        "url": f"{IBX}/{section}/questions-and-answers/",
        "link_re": (rf"^{IBX_ESCAPED}/{section}/[a-z0-9\-]+"
                    r"(?:/[0-9]+)?/?$"),
        "page_re": r"(?:/[0-9]+/?$|\?page=[0-9]+$)",
        "max_links": 3,
        "max_pages": max_pages,
        "audit": {"status": "live", "checked": "2026-09-06", "note": note},
    }


def _index(name: str, url: str, exam: str, note: str,
           link_re: str, max_links: int = 2, page_re: str = "",
           max_pages: int = 0) -> dict:
    """Deep index crawl (listing page -> article pages) with the tolerant
    generic MCQ parser. Only pages that really contain 4-option questions
    with an answer marker ever produce bank questions — content-gated."""
    s = {
        "name": name, "enabled": True, "type": "index", "exam": exam,
        "url": url, "link_re": link_re, "max_links": max_links,
        "audit": {"status": "live", "checked": "2026-09-06", "note": note},
    }
    if page_re:
        s["page_re"] = page_re
        s["max_pages"] = max_pages
    return s


def _rss(name: str, feed: str, exam: str, note: str,
         enabled: bool = True, must: str = QUIZ_MUST, notp: str = QUIZ_NOT,
         auto: bool = False, max_articles: int | None = None) -> dict:
    s = {
        "name": name, "enabled": enabled, "type": "rss", "exam": exam,
        "feed": feed, "title_must": must, "title_not": notp,
        "audit": {"checked": "2026-09-06"},
    }
    if max_articles:
        s["max_articles"] = max_articles
    if auto:
        s["auto_enable_if_live"] = True
    if enabled:
        s["audit"]["status"] = "live"
        s["audit"]["note"] = note
    else:
        s["audit"]["status"] = note.split("|")[0].strip()
        s["audit"]["note"] = note
    return s


def _candidate(name: str, feed: str, exam: str, note: str,
               must: str = QUIZ_MUST, notp: str = QUIZ_NOT,
               max_articles: int | None = None) -> dict:
    """Unverified candidate — only auto-enabled after a real content check."""
    s = {
        "name": name, "enabled": False, "type": "rss", "exam": exam,
        "feed": feed, "title_must": must, "title_not": notp,
        "auto_enable_if_live": True,
        "audit": {"status": "unverified", "checked": "2026-09-06",
                  "note": note},
    }
    if max_articles:
        s["max_articles"] = max_articles
    return s


# ---------------------------------------------------------------------------
# EXAM-QUIZ SOURCES (the registry the collector runs on)
# ---------------------------------------------------------------------------
def _dead_archive() -> list[dict]:
    """Historical / archive sources carried in the database for tracking.
    None of these is queried; they exist so the registry is complete and the
    monthly re-scan can re-verify URL life."""
    rows = [
        ("Deccan Chronicle", "https://deccanchronus.com/feed", "dead | TLS cert dead (Aug 2026)"),
        ("Deccan Herald", "https://www.deccanherald.com/rss", "dead | 404 (Aug 2026)"),
        ("TOI Hyderabad City", "https://timesofindia.indiatimes.com/rssfeeds/2223817529.cms",
         "dead | 404 (Aug 2026)"),
        ("TOI Vijayawada City", "https://timesofindia.indiatimes.com/rssfeeds/1224655363.cms",
         "dead | 200 but 0 entries (Aug 2026)"),
        ("Firstpost News", "https://www.firstpost.com/feed/", "dead | 403 (Aug 2026)"),
        ("Livemint Top", "https://www.livemint.com/feed/latest", "dead | HTML only (Aug 2026)"),
        ("The Quint India", "https://www.thequint.com/feed", "dead | 404 (Aug 2026)"),
        ("Frontline Magazine", "https://frontline.thehindu.com/feed/", "dead | HTML only (Aug 2026)"),
        ("Telegraph India", "https://www.telegraphindia.com/feed", "dead | 403 (Aug 2026)"),
        ("Sakshi Telugu", "https://sakshi.com/rss/feed.xml",
         "tested | sandbox 403, server OK per Aug-2026 audit"),
        ("Samayam Telugu", "https://samayam.com/telugu/feed", "dead | TLS (Aug 2026)"),
        ("10MinuteTelugu", "https://10minutetelugu.com/feed", "dead | TLS (Aug 2026)"),
        ("APJobs", "https://www.apjobs.in/feed", "dead | junk/spam — permanently blocked"),
        ("PIB", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
         "tested | structured RSS may vary; auditor re-checks"),
        ("PRS Legislative", "https://prsindia.org/feed/", "dead | 404 (Aug 2026)"),
        ("IASbaba", "https://www.iasbaba.com/feed/", "dead | TLS (Aug 2026)"),
        ("CivilServicesToday", "https://civilstoday.com/feed/", "dead | 500 (Aug 2026)"),
        ("NewsOnAir", "https://newsonair.gov.in/feed/", "dead | timeout (Aug 2026)"),
        ("Smartkeeda", "https://smartkeeda.com/feed/", "dead | 404 (Aug 2026)"),
        ("RecruitmentIndia", "https://recruitmentindia.in/feed/", "dead | HTML only (Aug 2026)"),
        ("BBC India", "https://feeds.bbci.co.uk/news/world/india/rss.xml",
         "dead | 404 (Aug 2026) — foreign, blocked"),
        ("The Week India", "https://www.theweek.in/feed/india-news.xml",
         "dead | 403 (Aug 2026) — blocked"),
        ("ABP Live", "https://abplive.com/feed/", "dead | HTML only (Aug 2026)"),
        ("Business Standard Old", "https://feed.business-standard.com/feed/",
         "dead | HTML only (Aug 2026)"),
        ("Times Now", "https://timesnownews.com/feed/", "archive | re-scan"),
        ("India TV", "https://www.indiatvnews.com/feed/", "archive | re-scan"),
        ("CNN News18", "https://www.news18.com/feed/", "archive | re-scan"),
        ("Aaj Tak", "https://www.aajtak.in/feed/", "archive | re-scan"),
        ("Republic TV", "https://www.republicworld.com/feed/", "archive | re-scan"),
        ("FreeJobAlert", "https://www.freejobalert.com/feed",
         "tested | main jobs feed — used by news_feeds, verified Aug 2026"),
        ("SarkariYojana", "https://www.sarkariyojana.com/feed",
         "tested | Telugu jobs feed — used by news_feeds, verified Aug 2026"),
        ("GovtJobs.com", "https://www.govtjobs.com/feed", "dead | stale 170+ days"),
        ("SarkariNaukri", "https://www.sarkarinaukri.com/feed/", "archive | re-scan"),
        ("Freshersworld", "https://www.freshersworld.com/feed/", "dead | 403"),
        ("NaukriGazzette", "https://naukri-gazzette.com/feed", "dead | timeout"),
        ("TSJobs.in", "https://tsjobs.in/feed", "dead | 404"),
        ("RailBiz", "https://railbiz.com/feed/", "dead | timeout"),
        ("IBPS Guide (jobs)", "https://www.ibpsguide.com/feed", "dead | stale"),
    ]
    out = []
    for name, url, note in rows:
        out.append({
            "name": f"ARCHIVE:{name}", "enabled": False, "type": "rss",
            "exam": "all", "feed": url, "title_must": QUIZ_MUST,
            "title_not": QUIZ_NOT,
            "audit": {"status": note.split("|")[0].strip(), "checked": "2026-08-30",
                      "note": note},
        })
    return out


SOURCES: list[dict] = [
    # ---- LIVE, AUDITED 2026-09-06 (platform + content verified) ----------
    _rss("AffairsCloud", "https://affairscloud.com/feed", "all",
         "live | verified 05 Sep 2026 — 30+ fresh CA quiz/current-affairs posts"),
    _rss("InsightsIndia Quiz", "https://www.insightsonindia.com/feed", "upsc",
         "live | verified 06 Sep 2026 — daily UPSC Current Affairs Quiz post"),
    # Feed URL verified to redirect to the homepage (no RSS) -> deep crawl
    # the verified listing pages instead; generic parser keeps only real MCQs.
    _index("BankersAdda Quiz", "https://www.bankersadda.com/current-affairs/",
           "banking",
           "live | verified 05 Sep 2026 — daily banking CA quiz posts listed; /feed redirects to homepage (no RSS)",
           r"^https://www\.bankersadda\.com/daily-current-affairs-quiz-[a-z0-9\-]+/?$",
           max_links=2),
    _rss("Oliveboard Quiz", "https://www.oliveboard.in/blog/feed/", "banking",
         "live | verified 04 Sep 2026 — exam blog RSS parses, quiz posts strictly filtered"),
    _index("SSCAdda Quiz", "https://www.sscadda.com/",
           "ssc",
           "live | verified Sep 2026 — homepage verified; /feed redirects, so article links are deep-crawled and content-gated",
           r"^https://www\.sscadda\.com/[a-z0-9\-]+/?$",
           max_links=2),
    _index("CareerPower Quiz", "https://www.careerpower.in/blog/",
           "ssc",
           "live | verified Sep 2026 — blog listing verified; /blog/feed redirects, article links deep-crawled + content-gated",
           r"^https://www\.careerpower\.in/blog/[a-z0-9\-]+/?$",
           max_links=2),
    _rss("PracticeMock Quiz", "https://www.practicemock.com/blog/feed/", "all",
         "live | verified 06 Sep 2026 — banking/SSC/UPSC exam blog"),
    _ibx("aptitude", "banking-ssc-railway",
         "verified 06 Sep 2026 — 35+ quant topics (trains, SI/CI, % etc.)"),
    _ibx("verbal-reasoning", "all", "verified 06 Sep 2026"),
    _ibx("logical-reasoning", "all", "verified 06 Sep 2026"),
    _ibx("non-verbal-reasoning", "all", "verified 06 Sep 2026"),  # figures: parked if untranslated
    _ibx("general-knowledge", "ssc-upsc-railway",
         "verified 06 Sep 2026 — static GK sections"),
    _ibx("data-interpretation", "banking-ssc",
         "verified 06 Sep 2026 — DI tables/charts (exported from same verified markup)"),
    _ibx("verbal-ability", "ssc-banking",
         "verified 06 Sep 2026 — English usage questions"),
    _ibx("current-affairs", "ssc-upsc-banking",
         "verified 06 Sep 2026 — CA Q&A on the verified IndiaBIX platform"),

    # ---- DEAD / UNUSABLE — audited 2026-09-06, never re-enabled -----------
    _rss("GKToday Quiz", "https://www.gktoday.in/feed/", "ssc-upsc",
         "dead | HTTP 500 'Feed is temporarily not available' on 06 Sep 2026",
         enabled=False),
    _rss("Testbook Quizzes", "https://testbook.com/blog/feed/", "all",
         "dead | feed serves junk (Test post title / COVID spam) — not exam quiz content",
         enabled=False),
    _rss("Guidely Quiz", "https://guidely.in/blog/feed", "banking",
         "dead | 404 Page Not Found (blog feed removed; /feed also 404)",
         enabled=False),
    _rss("RailwayAdda Quiz", "https://www.rrbadda.com/feed", "railway",
         "dead | host unreachable 06 Sep 2026 (site itself failed)",
         enabled=False),
    _rss("Adda247 Quiz", "https://www.adda247.com/feed/", "all",
         "dead | docs: 403 blocked", enabled=False),
    _rss("BankersAdda Old Feed", "https://www.bankersadda.com/feed/rss/", "banking",
         "dead | legacy URL", enabled=False),
    _rss("Testbook Quiz Category", "https://testbook.com/blog/category/quiz/feed/",
         "all", "dead | category feed guess, no quiz content", enabled=False),

    # ---- CANDIDATES — unverified; auditor may auto-enable after real check --
    _candidate("Smartkeeda Quiz", "https://www.smartkeeda.com/feed/", "all",
               "docs marked 404 in Aug 2026; re-verify before use"),
    _candidate("IBPSGuide Quiz", "https://www.ibpsguide.com/feed", "banking",
               "docs: stale ~180 days; re-verify before use"),
    _candidate("StudyIQ Quiz", "https://www.studyiq.com/feed", "all",
               "unverified URL — auditor checks feed + content"),
    _candidate("PendulumEdu Quiz", "https://pendulumedu.com/feed", "all",
               "unverified URL — auditor checks feed + content"),
    _candidate("AffairsCloud Quiz Category",
               "https://affairscloud.com/category/current-affairs-quiz/feed/",
               "all", "unverified category feed — auditor checks + content gate"),
    _candidate("BankersAdda Quiz Category",
               "https://www.bankersadda.com/category/quiz/feed/",
               "banking", "unverified category feed — auditor checks + content gate"),
    _candidate("CareerPower Practice Category",
               "https://www.careerpower.in/blog/category/practice-set/feed/",
               "ssc", "unverified category feed — auditor checks + content gate"),
    _candidate("Oliveboard Quiz Category",
               "https://www.oliveboard.in/blog/category/quiz/feed/",
               "banking", "unverified category feed — auditor checks + content gate"),
    _candidate("PracticeMock Quiz Category",
               "https://www.practicemock.com/blog/category/quiz/feed/",
               "all", "unverified category feed — auditor checks + content gate"),
    _candidate("SSCAdda Quiz Category",
               "https://www.sscadda.com/category/quiz/feed/",
               "ssc", "unverified category feed — auditor checks + content gate"),
    _candidate("Testbook Daily Quiz", "https://testbook.com/feed/", "all",
               "unverified main feed — auditor checks + content gate"),
    _candidate("Jagran Josh Current Affairs Quiz",
               "https://www.jagranjosh.com/rss/current-affairs-quizzes.xml",
               "all", "unverified RSS URL — auditor checks + content gate"),

    # ---- FULL HISTORY: every tracked/archived source (re-scan tracking only)
    *_dead_archive(),
]


NEWS_FEEDS = {
    "ca": [
        ("AffairsCloud", "https://affairscloud.com/feed", "live 2026-09-06"),
        ("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss",
         "tested (Aug 2026)"),
        ("The Hindu Business", "https://www.thehindu.com/business/feeder/default.rss",
         "tested (Aug 2026)"),
        ("India Today", "https://www.indiatoday.in/rss/india", "tested (Aug 2026)"),
        ("TOI Top", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
         "tested (Aug 2026)"),
        ("ET Top", "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
         "tested (Aug 2026)"),
        ("Insights on India", "https://www.insightsonindia.com/feed", "live 2026-09-06"),
        ("PIB Delhi", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
         "re-check (auditor)"),
        ("NDTV News", "https://www.ndtv.com/feeds/rss/news", "tested (server OK)"),
        ("Zee News India", "https://zeenews.india.com/rss/india-national-news.xml",
         "tested (server OK)"),
        ("Indian Express", "https://indianexpress.com/feed/", "tested (server OK)"),
        ("Hindustan Times India", "https://www.hindustantimes.com/feeds/rss/india-news",
         "tested (server OK)"),
    ],
    "jobs": [
        ("FreeJobAlert", "https://www.freejobalert.com/feed", "tested (Aug 2026)"),
        ("SarkariYojana", "https://www.sarkariyojana.com/feed", "tested (Aug 2026)"),
        ("AffairsCloud Jobs", "https://affairscloud.com/feed", "live 2026-09-06"),
        ("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss",
         "tested (Aug 2026)"),
        ("The Hindu Business", "https://www.thehindu.com/business/feeder/default.rss",
         "tested (Aug 2026)"),
        ("ET Top", "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
         "tested (Aug 2026)"),
        ("TOI Top", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
         "tested (Aug 2026)"),
    ],
}


def build() -> dict:
    return {
        "version": "3.0",
        "description": ("STUDENTUP central source registry — every exam-quiz source, "
                        "CA/jobs feed and tracked-dead source in one place. "
                        "Collector, auditor and feeds aggregator all read this file. "
                        "Regenerate with scripts/rebuild_registry.py."),
        "last_audit": "2026-09-06",
        "audit_note": ("Live/statuses below were checked on 2026-09-06 with a "
                       "content-level audit (feed entries + title filters). "
                       "Candidates auto-enable only after a real content-gated check."),
        "defaults": {
            "max_articles_per_source": 2,
            "max_links_per_index": 3,
            "max_pages_per_index": 2,
            "max_questions_per_run": 160,
            "polite_delay_sec": 2.0,
            "fetch_timeout": 20,
            "auto_pause_after_failures": 3,
        },
        "news_feeds": NEWS_FEEDS,
        "sources": SOURCES,
    }


def validate(data: dict) -> list[str]:
    """Hard integrity checks — returns list of problems (empty == OK)."""
    errs = []
    if not data.get("sources"):
        errs.append("no sources")
    names = set()
    for i, s in enumerate(data["sources"]):
        name = s.get("name", "")
        if not name:
            errs.append(f"sources[{i}]: missing name")
            continue
        if name in names:
            errs.append(f"duplicate source name: {name}")
        names.add(name)
        if s.get("type") not in ("rss", "index", "page"):
            errs.append(f"{name}: bad type {s.get('type')}")
        url = s.get("feed") or s.get("url") or ""
        if not url.startswith("https://"):
            errs.append(f"{name}: non-https url {url!r}")
        if s.get("type") == "rss" and not s.get("feed"):
            errs.append(f"{name}: rss without feed")
        if s.get("type") == "index" and not s.get("url"):
            errs.append(f"{name}: index without url")
        if s.get("enabled") and s.get("audit", {}).get("status") not in ("live",):
            errs.append(f"{name}: enabled but audit status {s.get('audit', {}).get('status')}")
    for scope in ("ca", "jobs"):
        if not data.get("news_feeds", {}).get(scope):
            errs.append(f"news_feeds missing scope {scope}")
    return errs


if __name__ == "__main__":
    data = build()
    errs = validate(data)
    if errs:
        print("REGISTRY INVALID:")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    if "--check" in sys.argv:
        print(f"registry OK: {len(data['sources'])} sources, "
              f"{len(data['news_feeds']['ca'])} CA + {len(data['news_feeds']['jobs'])} jobs feeds")
        sys.exit(0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT} ({len(data['sources'])} sources)")
