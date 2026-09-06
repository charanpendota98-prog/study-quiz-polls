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
             r"\bgk\b|previous year|memory based|current affairs")
QUIZ_NOT = (r"notification|admit card|hall ticket|result|cut[\s-]?off|syllabus|"
            r"editorial|interview|recruitment|vacancy|salary|eligibility|exam date|"
            r"exam analysis|answer key|apply online|registration|motivation|topper|"
            r"schedule|mindmap|test series launch|webinar|course|success stor")

# Broader CA-quiz filter for specialist CA/UPSC blogs
CA_MUST = (r"current affairs|daily ca|quiz|mcq|gk|prelims|upsc|banking awareness|"
           r"static gk|scheme|budget|rbi|isro|defence|parliament")
CA_NOT = QUIZ_NOT

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
           max_pages: int = 0, enabled: bool = True,
           adapter: str = "") -> dict:
    """Deep index crawl (listing page -> article pages)."""
    s = {
        "name": name, "enabled": enabled, "type": "index", "exam": exam,
        "url": url, "link_re": link_re, "max_links": max_links,
        "audit": {"status": "live" if enabled else "unverified",
                  "checked": "2026-09-06", "note": note},
    }
    if adapter:
        s["adapter"] = adapter
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


def _cand_index(name: str, url: str, exam: str, note: str, link_re: str,
                max_links: int = 2) -> dict:
    """Unverified deep-index candidate — auditor enables after content gate."""
    return {
        "name": name, "enabled": False, "type": "index", "exam": exam,
        "url": url, "link_re": link_re, "max_links": max_links,
        "auto_enable_if_live": True,
        "audit": {"status": "unverified", "checked": "2026-09-06", "note": note},
    }


def _archive(name: str, url: str, note: str, kind: str = "rss") -> dict:
    status = note.split("|")[0].strip()
    row = {
        "name": f"ARCHIVE:{name}", "enabled": False, "type": kind,
        "exam": "all",
        "audit": {"status": status, "checked": "2026-09-06", "note": note},
    }
    if kind == "rss":
        row["feed"] = url
        row["title_must"] = QUIZ_MUST
        row["title_not"] = QUIZ_NOT
    else:
        row["url"] = url
        row["link_re"] = r"(?!)"  # never matches — archive tracking only
    return row


# ---------------------------------------------------------------------------
# EXAM-QUIZ SOURCES
# ---------------------------------------------------------------------------
def _dead_confirmed() -> list[dict]:
    """Confirmed-dead quiz sources (never auto-enabled)."""
    rows = [
        ("GKToday Quiz", "https://www.gktoday.in/feed/", "ssc-upsc",
         "dead | HTTP 500 'Feed is temporarily not available' on 06 Sep 2026"),
        ("Testbook Quizzes", "https://testbook.com/blog/feed/", "all",
         "dead | feed serves junk (Test post title / COVID spam) — not exam quiz content"),
        ("Guidely Quiz", "https://guidely.in/blog/feed", "banking",
         "dead | 404 Page Not Found (blog feed removed; /feed also 404)"),
        ("RailwayAdda Quiz", "https://www.rrbadda.com/feed", "railway",
         "dead | host unreachable 06 Sep 2026 (site itself failed)"),
        ("Adda247 Quiz", "https://www.adda247.com/feed/", "all",
         "dead | docs: 403 blocked"),
        ("BankersAdda Old Feed", "https://www.bankersadda.com/feed/rss/", "banking",
         "dead | legacy URL"),
        ("Testbook Quiz Category", "https://testbook.com/blog/category/quiz/feed/",
         "all", "dead | category feed guess, no quiz content"),
        ("Smartkeeda Old Root", "https://smartkeeda.com/feed/", "all",
         "dead | 404 (Aug 2026)"),
        ("IASbaba Root Feed", "https://www.iasbaba.com/feed/", "upsc",
         "dead | TLS (Aug 2026)"),
        ("CivilServicesToday", "https://civilstoday.com/feed/", "upsc",
         "dead | 500 (Aug 2026)"),
    ]
    out = []
    for name, feed, exam, note in rows:
        out.append(_rss(name, feed, exam, note, enabled=False))
    return out


def _archive_rows() -> list[dict]:
    """Historical / archive / re-scan tracking — complete 100+ database."""
    rows = [
        # ---- DEAD regional / news (tracking only) ----
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
        ("PIB Old", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
         "tested | structured RSS may vary; auditor re-checks"),
        ("PRS Legislative", "https://prsindia.org/feed/", "dead | 404 (Aug 2026)"),
        ("NewsOnAir", "https://newsonair.gov.in/feed/", "dead | timeout (Aug 2026)"),
        ("RecruitmentIndia", "https://recruitmentindia.in/feed/", "dead | HTML only (Aug 2026)"),
        ("BBC India", "https://feeds.bbci.co.uk/news/world/india/rss.xml",
         "dead | 404 (Aug 2026) — foreign, blocked"),
        ("The Week India", "https://www.theweek.in/feed/india-news.xml",
         "dead | 403 (Aug 2026) — blocked"),
        ("ABP Live", "https://abplive.com/feed/", "dead | HTML only (Aug 2026)"),
        ("Business Standard Old", "https://feed.business-standard.com/feed/",
         "dead | HTML only (Aug 2026)"),
        # ---- ARCHIVE re-scan (monthly) ----
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
        # ---- Extended archive tracking (deep research Sep 2026) ----
        ("Eenadu Telugu", "https://www.eenadu.net/rss", "archive | Telugu state news re-scan"),
        ("AndhraJyothy", "https://www.andhrajyothy.com/rss", "archive | Telugu state news re-scan"),
        ("NamastheTelangana", "https://www.ntnews.com/feed", "archive | TS Telugu re-scan"),
        ("TelanganaToday", "https://telanganatoday.com/feed", "archive | TS English re-scan"),
        ("HansIndia", "https://www.thehansindia.com/feed", "archive | south India re-scan"),
        ("NewIndianExpress", "https://www.newindianexpress.com/Nation/rssfeed/?id=170&getXmlFeed=XML",
         "archive | national re-scan"),
        ("ThePrint", "https://theprint.in/feed/", "archive | policy depth re-scan"),
        ("Scroll.in", "https://scroll.in/feed", "archive | longform re-scan"),
        ("Wire.in", "https://thewire.in/rss", "archive | policy re-scan"),
        ("Moneycontrol Markets", "https://www.moneycontrol.com/rss/latestnews.xml",
         "archive | economy/markets re-scan"),
        ("BusinessStandard RSS", "https://www.business-standard.com/rss/latest.rss",
         "archive | economy re-scan"),
        ("LiveMint Markets", "https://www.livemint.com/rss/markets",
         "archive | markets re-scan"),
        ("ORF Expert", "https://www.orfonline.org/feed", "archive | foreign-policy research"),
        ("IDSA", "https://idsa.in/feed", "archive | defence research"),
        ("MyGov", "https://www.mygov.in/feed/", "archive | gov portal re-scan"),
        ("India.gov", "https://www.india.gov.in/rss", "archive | gov portal re-scan"),
        ("SarkariResult", "https://www.sarkariresult.com/feed/", "archive | jobs re-scan"),
        ("SarkariExam", "https://www.sarkariexam.com/feed/", "archive | jobs re-scan"),
        ("AllIndiaJobs", "https://www.allindiajobs.in/feed/", "archive | jobs re-scan"),
        ("Jobriya", "https://www.jobriya.in/feed/", "archive | jobs re-scan"),
        ("FreshersLive", "https://www.fresherslive.com/feed", "archive | jobs re-scan"),
        ("SSBCrack", "https://www.ssbcrack.com/feed", "archive | defence re-scan"),
        ("MajorKalshiClasses", "https://www.majorkalshiclasses.com/feed/",
         "archive | defence exam re-scan"),
        ("Wifistudy", "https://www.wifistudy.com/blog/feed", "archive | exam prep re-scan"),
        ("Embibe Blog", "https://www.embibe.com/blog/feed/", "archive | exam prep re-scan"),
        ("Toppr Bytes", "https://www.toppr.com/bytes/feed/", "archive | student prep re-scan"),
        ("Vedantu Blog", "https://www.vedantu.com/blog/feed/", "archive | student prep re-scan"),
        ("EduRev", "https://edurev.in/feed", "archive | exam notes re-scan"),
        ("Gradeup Legacy", "https://gradeup.co/feed", "archive | BYJU Exam Prep legacy"),
        ("Unacademy Content", "https://unacademy.com/content/feed/", "archive | content re-scan"),
        ("CareerLauncher", "https://www.careerlauncher.com/feed/", "archive | CAT/bank re-scan"),
        ("VisionIAS Blog", "https://www.visionias.in/blog/feed", "archive | UPSC coaching re-scan"),
        ("Vajiram", "https://vajiramandravi.com/feed/", "archive | UPSC coaching re-scan"),
        ("ShankarIAS", "https://www.shankariasacademy.com/feed/", "archive | UPSC coaching re-scan"),
        ("NextIAS", "https://www.nextias.com/blog/feed", "archive | UPSC coaching re-scan"),
        ("ForumIAS", "https://forumias.com/blog/feed/", "archive | UPSC community re-scan"),
        ("SleepyClasses", "https://sleepyclasses.com/feed/", "archive | UPSC re-scan"),
        ("OnlyIAS", "https://onlyias.com/feed/", "archive | UPSC re-scan"),
        ("ChahalAcademy", "https://chahalacademy.com/feed/", "archive | UPSC re-scan"),
        ("PlutusIAS", "https://plutusias.com/feed/", "archive | UPSC re-scan"),
        ("UPSCPathshala", "https://upscpathshala.com/feed/", "archive | UPSC re-scan"),
        ("KhanGlobalStudies", "https://www.khanglobalstudies.com/blog/feed",
         "archive | UPSC re-scan"),
        ("ISRO Updates", "https://www.isro.gov.in/rss.xml", "archive | space GK re-scan"),
        ("RBI Press Releases", "https://rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx",
         "archive | banking GK re-scan (HTML page, not RSS)"),
        ("SSC Portal", "https://sscportal.in/feed", "archive | SSC portal legacy re-scan"),
        ("Qmaths SSC", "https://www.qmaths.in/feed/", "archive | SSC math prep re-scan"),
    ]
    return [_archive(n, u, note) for n, u, note in rows]


SOURCES: list[dict] = [
    # ---- LIVE, AUDITED 2026-09-06 (platform + content verified) ----------
    _rss("AffairsCloud", "https://affairscloud.com/feed", "all",
         "live | verified 05 Sep 2026 — 30+ fresh CA quiz/current-affairs posts"),
    _rss("InsightsIndia Quiz", "https://www.insightsonindia.com/feed", "upsc",
         "live | verified 06 Sep 2026 — daily UPSC Current Affairs Quiz post"),
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
    _ibx("non-verbal-reasoning", "all", "verified 06 Sep 2026"),
    _ibx("general-knowledge", "ssc-upsc-railway",
         "verified 06 Sep 2026 — static GK sections"),
    _ibx("data-interpretation", "banking-ssc",
         "verified 06 Sep 2026 — DI tables/charts (exported from same verified markup)"),
    _ibx("verbal-ability", "ssc-banking",
         "verified 06 Sep 2026 — English usage questions"),
    _ibx("current-affairs", "ssc-upsc-banking",
         "verified 06 Sep 2026 — CA Q&A on the verified IndiaBIX platform"),

    # ---- DEAD / UNUSABLE — audited, never re-enabled --------------------
    *_dead_confirmed(),

    # ---- CANDIDATES — deep research Sep 2026; auto-enable after content gate
    # Specialist exam/quiz blogs & category feeds (quiz title filter)
    _candidate("AffairsCloud Quiz Category",
               "https://affairscloud.com/category/current-affairs-quiz/feed/",
               "all", "category feed — auditor content gate", must=CA_MUST, notp=CA_NOT),
    _candidate("AffairsCloud Banking Awareness",
               "https://affairscloud.com/category/banking-awareness/feed/",
               "banking", "banking-awareness posts for IBPS/SBI", must=CA_MUST, notp=CA_NOT),
    _candidate("AffairsCloud Static GK",
               "https://affairscloud.com/category/static-gk/feed/",
               "ssc-upsc-railway", "static GK for SSC/RRB/UPSC", must=CA_MUST, notp=CA_NOT),
    _candidate("BankersAdda Quiz Category",
               "https://www.bankersadda.com/category/quiz/feed/",
               "banking", "unverified category feed — auditor checks + content gate"),
    _candidate("CareerPower Practice Category",
               "https://www.careerpower.in/blog/category/practice-set/feed/",
               "ssc", "unverified category feed — auditor checks + content gate"),
    _candidate("Oliveboard Quiz Category",
               "https://www.oliveboard.in/blog/category/quiz/feed/",
               "banking", "unverified category feed — auditor checks + content gate"),
    _candidate("Oliveboard Banking Category",
               "https://www.oliveboard.in/blog/category/banking/feed/",
               "banking", "banking exam posts", must=CA_MUST, notp=CA_NOT),
    _candidate("Oliveboard SSC Category",
               "https://www.oliveboard.in/blog/category/ssc/feed/",
               "ssc", "SSC exam posts", must=CA_MUST, notp=CA_NOT),
    _candidate("Oliveboard RRB Category",
               "https://www.oliveboard.in/blog/category/rrb/feed/",
               "railway", "RRB exam posts", must=CA_MUST, notp=CA_NOT),
    _candidate("Oliveboard Free Practice",
               "https://www.oliveboard.in/blog/category/free-practice-questions/feed/",
               "all", "free practice MCQ posts"),
    _candidate("PracticeMock Quiz Category",
               "https://www.practicemock.com/blog/category/quiz/feed/",
               "all", "unverified category feed — auditor checks + content gate"),
    _candidate("PracticeMock Banking Category",
               "https://www.practicemock.com/blog/category/banking/feed/",
               "banking", "banking mocks/practice", must=CA_MUST, notp=CA_NOT),
    _candidate("PracticeMock SSC Category",
               "https://www.practicemock.com/blog/category/ssc/feed/",
               "ssc", "SSC mocks/practice", must=CA_MUST, notp=CA_NOT),
    _candidate("SSCAdda Quiz Category",
               "https://www.sscadda.com/category/quiz/feed/",
               "ssc", "unverified category feed — auditor checks + content gate"),
    _candidate("InsightsIndia Quizzes Category",
               "https://www.insightsonindia.com/category/quizzes/feed/",
               "upsc", "UPSC daily quiz category", must=r"quiz|mcq|current affairs", notp=QUIZ_NOT),
    _candidate("InsightsIndia Secure",
               "https://www.insightsonindia.com/category/secure-initiative/feed/",
               "upsc", "UPSC Mains Secure initiative — CA depth", must=CA_MUST, notp=CA_NOT),
    _candidate("Drishti IAS", "https://www.drishtiias.com/feed", "upsc",
               "UPSC current affairs + quiz depth", must=CA_MUST, notp=CA_NOT),
    _candidate("ClearIAS", "https://www.clearias.com/feed/", "upsc",
               "UPSC prelims MCQ + CA", must=CA_MUST, notp=CA_NOT),
    _candidate("BYJU IAS Prep", "https://byjus.com/free-ias-prep/feed/", "upsc",
               "UPSC free IAS prep feed", must=CA_MUST, notp=CA_NOT),
    _candidate("PMF IAS", "https://www.pmfias.com/feed/", "upsc",
               "geography/environment UPSC depth", must=CA_MUST, notp=CA_NOT),
    _candidate("CivilsDaily", "https://www.civilsdaily.com/feed/", "upsc",
               "UPSC daily CA", must=CA_MUST, notp=CA_NOT),
    _candidate("IASExpress", "https://www.iasexpress.net/feed/", "upsc",
               "UPSC notes/CA", must=CA_MUST, notp=CA_NOT),
    _candidate("BankExamsToday",
               "https://www.bankexamstoday.com/feeds/posts/default?alt=rss",
               "banking", "banking awareness + quizzes"),
    _candidate("Bankersdaily", "https://bankersdaily.in/feed/", "banking",
               "banking daily quizzes + CA"),
    _candidate("IxamBee Blog", "https://www.ixambee.com/blog/feed", "banking-ssc-railway",
               "banking/SSC/railway exam blog"),
    _candidate("Mahendras Blog", "https://www.mahendras.org/blog/feed", "banking-ssc",
               "banking/SSC practice blog"),
    _candidate("Cracku Blog", "https://cracku.in/blog/feed/", "banking-ssc",
               "quant/reasoning practice"),
    _candidate("StudyIQ Articles", "https://www.studyiq.com/articles/feed/", "all",
               "exam CA/articles — content gate required", must=CA_MUST, notp=CA_NOT),
    _candidate("PendulumEdu Quiz", "https://pendulumedu.com/feed", "all",
               "unverified URL — auditor checks feed + content"),
    _candidate("Smartkeeda Quiz", "https://www.smartkeeda.com/feed/", "all",
               "docs marked 404 in Aug 2026; re-verify before use"),
    _candidate("IBPSGuide Quiz", "https://www.ibpsguide.com/feed", "banking",
               "docs: stale ~180 days; re-verify before use"),
    _candidate("Jagran Josh Current Affairs Quiz",
               "https://www.jagranjosh.com/rss/current-affairs-quizzes.xml",
               "all", "unverified RSS URL — auditor checks + content gate"),
    _candidate("Jagran Josh Education",
               "https://www.jagranjosh.com/rss/edu.xml",
               "all", "education/exam desk RSS", must=CA_MUST, notp=CA_NOT),
    _candidate("Testbook Daily Quiz", "https://testbook.com/feed/", "all",
               "unverified main feed — auditor checks + content gate"),
    _candidate("Adda247 Current Affairs",
               "https://currentaffairs.adda247.com/feed/",
               "all", "Adda247 CA desk — content gate", must=CA_MUST, notp=CA_NOT),
    _candidate("SSBCrackExams", "https://www.ssbcrackexams.com/feed/", "defence",
               "NDA/CDS/Agniveer exam desk", must=CA_MUST, notp=CA_NOT),
    _candidate("The Hindu Education",
               "https://www.thehindu.com/education/feeder/default.rss",
               "all", "education desk — exam-relevant only", must=CA_MUST, notp=CA_NOT),
    _candidate("India Today Education",
               "https://www.indiatoday.in/rss/education",
               "all", "education desk RSS", must=CA_MUST, notp=CA_NOT),
    _candidate("TOI Education",
               "https://timesofindia.indiatimes.com/rssfeeds/913168846.cms",
               "all", "education desk RSS", must=CA_MUST, notp=CA_NOT),
    _candidate("PRS Blog", "https://prsindia.org/theprsblog/feed", "upsc",
               "legislative research — polity PYQ depth", must=CA_MUST, notp=CA_NOT),

    # Deep-index candidates (no reliable RSS — crawl listing pages)
    _cand_index("BankersAdda Reasoning",
                "https://www.bankersadda.com/category/reasoning/",
                "banking",
                "reasoning practice listing — content-gated deep crawl",
                r"^https://www\.bankersadda\.com/[a-z0-9\-]*reasoning[a-z0-9\-]*/?$"),
    _cand_index("BankersAdda Quant",
                "https://www.bankersadda.com/category/quantitative-aptitude/",
                "banking",
                "quant practice listing — content-gated deep crawl",
                r"^https://www\.bankersadda\.com/[a-z0-9\-]*(quant|aptitude|di)[a-z0-9\-]*/?$"),
    _cand_index("SSCAdda Reasoning",
                "https://www.sscadda.com/category/reasoning/",
                "ssc",
                "SSC reasoning listing",
                r"^https://www\.sscadda\.com/[a-z0-9\-]*reasoning[a-z0-9\-]*/?$"),
    _cand_index("SSCAdda Quant",
                "https://www.sscadda.com/category/quantitative-aptitude/",
                "ssc",
                "SSC quant listing",
                r"^https://www\.sscadda\.com/[a-z0-9\-]*(quant|aptitude)[a-z0-9\-]*/?$"),
    _cand_index("CareerPower Practice Sets",
                "https://www.careerpower.in/blog/category/practice-set/",
                "ssc",
                "practice-set listing deep crawl",
                r"^https://www\.careerpower\.in/blog/[a-z0-9\-]+/?$"),
    _cand_index("IndiaBIX Mechanical",
                "https://www.indiabix.com/mechanical-engineering/questions-and-answers/",
                "ssc-railway",
                "IndiaBIX mechanical section (RRB JE / SSC JE syllabus)",
                rf"^{IBX_ESCAPED}/mechanical-engineering/[a-z0-9\-]+(?:/[0-9]+)?/?$"),
    _cand_index("IndiaBIX Electrical",
                "https://www.indiabix.com/electrical-engineering/questions-and-answers/",
                "ssc-railway",
                "IndiaBIX electrical section (RRB JE / SSC JE syllabus)",
                rf"^{IBX_ESCAPED}/electrical-engineering/[a-z0-9\-]+(?:/[0-9]+)?/?$"),
    _cand_index("IndiaBIX Civil",
                "https://www.indiabix.com/civil-engineering/questions-and-answers/",
                "ssc-railway",
                "IndiaBIX civil section (RRB JE / SSC JE syllabus)",
                rf"^{IBX_ESCAPED}/civil-engineering/[a-z0-9\-]+(?:/[0-9]+)?/?$"),
    _cand_index("IndiaBIX Computer Science",
                "https://www.indiabix.com/computer-science/questions-and-answers/",
                "banking-ssc",
                "IndiaBIX computer awareness (IBPS/SBI/SSC)",
                rf"^{IBX_ESCAPED}/computer-science/[a-z0-9\-]+(?:/[0-9]+)?/?$"),

    # SSC & Central Exam Specialist Candidates
    _candidate("SSCAdda CGL Tier 1", "https://www.sscadda.com/ssc-cgl/feed/", "ssc", "SSC CGL prep feed"),
    _candidate("SSCAdda CHSL Tier 1", "https://www.sscadda.com/ssc-chsl/feed/", "ssc", "SSC CHSL prep feed"),
    _candidate("SSCAdda MTS Exam", "https://www.sscadda.com/ssc-mts/feed/", "ssc", "SSC MTS prep feed"),
    _candidate("SSCAdda GD Constable", "https://www.sscadda.com/ssc-gd-constable/feed/", "ssc", "SSC GD prep feed"),
    _candidate("SSCAdda CPO Exam", "https://www.sscadda.com/ssc-cpo/feed/", "ssc", "SSC CPO prep feed"),
    _candidate("SSCAdda Selection Post", "https://www.sscadda.com/ssc-selection-post/feed/", "ssc", "SSC Selection Post feed"),
    _candidate("CareerPower SSC CGL", "https://www.careerpower.in/blog/ssc-cgl/feed/", "ssc", "CareerPower SSC CGL feed"),
    _candidate("CareerPower SSC CHSL", "https://www.careerpower.in/blog/ssc-chsl/feed/", "ssc", "CareerPower SSC CHSL feed"),
    _candidate("CareerPower SSC MTS", "https://www.careerpower.in/blog/ssc-mts/feed/", "ssc", "CareerPower SSC MTS feed"),
    _candidate("CareerPower SSC GD", "https://www.careerpower.in/blog/ssc-gd/feed/", "ssc", "CareerPower SSC GD feed"),
    _candidate("Testbook SSC CGL", "https://testbook.com/ssc-cgl/feed/", "ssc", "Testbook SSC CGL feed"),
    _candidate("Testbook SSC CHSL", "https://testbook.com/ssc-chsl/feed/", "ssc", "Testbook SSC CHSL feed"),
    _candidate("Testbook SSC MTS", "https://testbook.com/ssc-mts/feed/", "ssc", "Testbook SSC MTS feed"),
    _candidate("Testbook SSC GD", "https://testbook.com/ssc-gd-constable/feed/", "ssc", "Testbook SSC GD feed"),
    _candidate("BYJU Exam Prep SSC", "https://byjusexamprep.com/ssc-exams/feed/", "ssc", "BYJU Exam Prep SSC feed"),
    _candidate("BYJU Exam Prep Railway", "https://byjusexamprep.com/railway-exams/feed/", "railway", "BYJU Exam Prep Railway feed"),
    _candidate("BYJU Exam Prep Banking", "https://byjusexamprep.com/banking-exams/feed/", "banking", "BYJU Exam Prep Banking feed"),
    _candidate("PracticeMock SSC CGL", "https://www.practicemock.com/blog/ssc-cgl/feed/", "ssc", "PracticeMock SSC CGL feed"),
    _candidate("PracticeMock SSC CHSL", "https://www.practicemock.com/blog/ssc-chsl/feed/", "ssc", "PracticeMock SSC CHSL feed"),
    _candidate("PracticeMock SSC MTS", "https://www.practicemock.com/blog/ssc-mts/feed/", "ssc", "PracticeMock SSC MTS feed"),
    _candidate("PracticeMock RRB NTPC", "https://www.practicemock.com/blog/rrb-ntpc/feed/", "railway", "PracticeMock RRB NTPC feed"),
    _candidate("Oliveboard SSC CGL", "https://www.oliveboard.in/blog/ssc-cgl/feed/", "ssc", "Oliveboard SSC CGL feed"),
    _candidate("Oliveboard SSC CHSL", "https://www.oliveboard.in/blog/ssc-chsl/feed/", "ssc", "Oliveboard SSC CHSL feed"),
    _candidate("Oliveboard RRB Group D", "https://www.oliveboard.in/blog/rrb-group-d/feed/", "railway", "Oliveboard RRB Group D feed"),
    _candidate("BankersAdda IBPS PO", "https://www.bankersadda.com/ibps-po/feed/", "banking", "BankersAdda IBPS PO feed"),
    _candidate("BankersAdda SBI PO", "https://www.bankersadda.com/sbi-po/feed/", "banking", "BankersAdda SBI PO feed"),
    _cand_index("SSCAdda General Awareness", "https://www.sscadda.com/category/general-awareness/", "ssc", "SSC GA listing", r"^https://www\.sscadda\.com/[a-z0-9\-]*general-awareness[a-z0-9\-]*/?$"),
    _cand_index("SSCAdda English Language", "https://www.sscadda.com/category/english-language/", "ssc", "SSC English listing", r"^https://www\.sscadda\.com/[a-z0-9\-]*english[a-z0-9\-]*/?$"),
    _cand_index("CareerPower Reasoning", "https://www.careerpower.in/blog/category/reasoning/", "ssc", "CareerPower Reasoning listing", r"^https://www\.careerpower\.in/blog/[a-z0-9\-]+/?$"),
    _cand_index("CareerPower Quant", "https://www.careerpower.in/blog/category/quantitative-aptitude/", "ssc", "CareerPower Quant listing", r"^https://www\.careerpower\.in/blog/[a-z0-9\-]+/?$"),
    _cand_index("IndiaBIX General Science", "https://www.indiabix.com/general-knowledge/general-science/questions-and-answers/", "ssc-railway", "IndiaBIX General Science", rf"^{IBX_ESCAPED}/general-knowledge/general-science/[a-z0-9\-]+(?:/[0-9]+)?/?$"),
    _cand_index("IndiaBIX Indian History", "https://www.indiabix.com/general-knowledge/indian-history/questions-and-answers/", "ssc-upsc", "IndiaBIX Indian History", rf"^{IBX_ESCAPED}/general-knowledge/indian-history/[a-z0-9\-]+(?:/[0-9]+)?/?$"),

    # ---- FULL HISTORY: every tracked/archived source --------------------
    *_archive_rows(),
]


NEWS_FEEDS = {
    "ca": [
        ("AffairsCloud", "https://affairscloud.com/feed", "live 2026-09-06"),
        ("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss",
         "tested (Aug 2026)"),
        ("The Hindu Business", "https://www.thehindu.com/business/feeder/default.rss",
         "tested (Aug 2026)"),
        ("The Hindu Education", "https://www.thehindu.com/education/feeder/default.rss",
         "candidate 2026-09-06"),
        ("India Today", "https://www.indiatoday.in/rss/india", "tested (Aug 2026)"),
        ("India Today Education", "https://www.indiatoday.in/rss/education",
         "candidate 2026-09-06"),
        ("TOI Top", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
         "tested (Aug 2026)"),
        ("TOI Education", "https://timesofindia.indiatimes.com/rssfeeds/913168846.cms",
         "candidate 2026-09-06"),
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
        ("Drishti IAS", "https://www.drishtiias.com/feed", "candidate 2026-09-06"),
        ("ClearIAS", "https://www.clearias.com/feed/", "candidate 2026-09-06"),
        ("PRS Blog", "https://prsindia.org/theprsblog/feed", "candidate 2026-09-06"),
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
        ("Adda247 Banking Jobs", "https://www.adda247.com/jobs/banking-jobs/feed",
         "candidate 2026-09-06"),
        ("SarkariResult", "https://www.sarkariresult.com/feed/", "candidate 2026-09-06"),
        ("AllIndiaJobs", "https://www.allindiajobs.in/feed/", "candidate 2026-09-06"),
    ],
}


def build() -> dict:
    return {
        "version": "4.0",
        "description": ("STUDENTUP central source registry — 100+ exam-quiz sources, "
                        "CA/jobs feeds and tracked-dead/archive sources in one place. "
                        "Collector, auditor and feeds aggregator all read this file. "
                        "Regenerate with scripts/rebuild_registry.py. "
                        "Deep research Sep 2026: only previous-paper / syllabus-aligned "
                        "sources; candidates auto-enable only after content-gated audit."),
        "last_audit": "2026-09-06",
        "audit_note": ("Live sources checked 2026-09-06 with content-level audit. "
                       "Registry expanded to 100+ with deep specialist candidates "
                       "(UPSC/Banking/SSC/Railway/Defence/IndiaBIX JE sections) + "
                       "full archive tracking. Candidates auto-enable only after a "
                       "real content-gated check. No dummy, no sample, no junk."),
        "defaults": {
            "max_articles_per_source": 2,
            "max_links_per_index": 3,
            "max_pages_per_index": 2,
            "max_questions_per_run": 200,
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
    if len(data.get("sources", [])) < 100:
        errs.append(f"need >=100 sources, got {len(data.get('sources', []))}")
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
    # Live coverage of core exam tags
    live_exams = " ".join(s.get("exam", "") for s in data["sources"] if s.get("enabled"))
    for tag in ("banking", "ssc", "upsc", "railway"):
        if tag not in live_exams:
            errs.append(f"no live source covers exam tag {tag}")
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
        n_live = sum(1 for s in data["sources"] if s.get("enabled"))
        n_cand = sum(1 for s in data["sources"]
                     if not s.get("enabled") and s.get("auto_enable_if_live"))
        n_arch = len(data["sources"]) - n_live - n_cand
        print(f"registry OK: {len(data['sources'])} sources "
              f"(live={n_live} candidates={n_cand} archive/dead={n_arch}), "
              f"{len(data['news_feeds']['ca'])} CA + {len(data['news_feeds']['jobs'])} jobs feeds")
        sys.exit(0)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    n_live = sum(1 for s in data["sources"] if s.get("enabled"))
    print(f"wrote {OUT} ({len(data['sources'])} sources, {n_live} live)")
