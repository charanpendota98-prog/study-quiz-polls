#!/usr/bin/env python3
"""
STUDENTUP — ADVANCED EXAM-CONTENT COLLECTOR
=================================================
Daily, neatly pulls EXAM quiz content from many websites / apps / APIs and
turns it into validated, bilingual, no-repeat bank questions.

WHAT IT COLLECTS (exam-prep sources only — NEVER news):
  * Current-Affairs QUIZZES for IBPS/SBI/RRB/SSC/Railway/TSPSC/APPSC
  * Reasoning / Quantitative-aptitude practice MCQs
  * Static GK / GS / Science question sets
RSS indexes are used to discover fresh quiz articles; the article HTML is
then parsed with a tolerant WordPress-style quiz extractor.

ADVANCED TOOLING (stdlib-only, keys optional):
  * Browser-like fetching with retries + exponential backoff + per-host
    polite delay + jitter; optional HTTP/HTTPS proxy.
  * robots.txt respect (urllib.robotparser, cached per host).
  * feedparser used automatically when present.
  * API keys (LLM rotation) translate scraped worded questions into Telugu;
    numeric/code questions are language-neutral and pass immediately.
  * Content-signature dedup (same engine as the no-repeat bank) — scraped
    questions can never duplicate existing or future posts.
  * Worded questions that cannot be translated yet are parked in
    scraped_pending.json and auto-retried when keys are present.

OUTPUT:
  data/scraped_bank.json      -> accepted, validated questions (source "scraped")
  data/scraped_pending.json   -> needs Telugu translation (retried later)
Then question_bank.rebuild_json() merges them into the canonical bank.

CLI:
  python3 -m core.collector --collect          # live run (network)
  python3 -m core.collector --collect --dry    # fetch+parse, do not save
  python3 -m core.collector --fixture FILE.html TITLE   # offline parse test
  python3 -m core.collector --retry-pending    # translate parked questions
  python3 -m core.collector --pdf paper.pdf    # ingest a PYQ / model-paper PDF
  python3 -m core.collector --inbox            # ingest data/pdf_inbox/*.pdf|txt
"""
from __future__ import annotations

import os
import re
import time
import random
import html
import urllib.request
import urllib.error
import urllib.robotparser
from urllib.parse import urljoin
from html.parser import HTMLParser
from datetime import datetime

from . import config
from .store import load_json, save_json_atomic
from .content import validate_question, is_blocked
from .question_bank import q_signature

USER_AGENT = ("Mozilla/5.0 (compatible; StudentUpBot/4.0; "
              "+https://studentup.in; exam-quiz collector; respectful)")

# Jina Reader — automatic fallback when a page blocks plain fetches.
# Set JINA_API_KEY=... in env/.env (optional; collector keeps working without).
JINA_API = "https://r.jina.ai/"
FEED_URL_RE = re.compile(r"(?:/feed/?$|\.xml(?:\?|$)|/rss(?:\?|$)|\.rss(?:\?|$))", re.I)

SCRAPED_BANK = config.DATA / "scraped_bank.json"
PENDING = config.DATA / "scraped_pending.json"
SEEN_URLS = config.DATA / "collector_seen.json"
REGISTRY = config.DATA / "collector_sources.json"     # central source registry
HEALTH = config.DATA / "collector_health.json"        # per-source health store

# Title filters shared by most quiz feeds.
_QUIZ_MUST = r"quiz|mcq|questions?|practice set|practice questions|model paper|mock|reasoning|quant|aptitude|general awareness|general knowledge|\bgk\b|previous year"
_QUIZ_NOT = (r"notification|admit card|hall ticket|result|cut[\s-]?off|syllabus|"
             r"editorial|interview|recruitment|vacancy|salary|eligibility|exam date|"
             r"exam analysis|answer key|apply online|registration|motivation|topper|"
             r"schedule|mindmap|test series launch|webinar|course")

# ---------------------------------------------------------------------------
# SOURCE REGISTRY — exam-prep sources only (NEVER news). Two kinds:
#   type "rss"   : an RSS/Atom feed; quiz articles discovered by title filter.
#   type "index" : an HTML listing/section page; quiz links discovered by
#                  link_re (regex on href), optionally crawled one level deep
#                  (section -> topic pages). An optional "adapter" names a
#                  dedicated parser for sites whose markup is not WordPress.
# Central exams (SSC/UPSC/Railway/Banking/Defence/Police) are weighted heavily.
# A source can be disabled with "enabled": false; data/collector_sources.json
# (same shape, key "sources") is merged on top to tune without code changes.
# ---------------------------------------------------------------------------
DEFAULT_SOURCES = [
    # ---- Current-affairs + all-exam daily quizzes --------------------------------
    {"name": "AffairsCloud", "enabled": True, "type": "rss", "exam": "all",
     "feed": "https://affairscloud.com/feed",
     "title_must": _QUIZ_MUST, "title_not": _QUIZ_NOT},
    {"name": "GKToday Quiz", "enabled": True, "type": "rss", "exam": "ssc-upsc",
     "feed": "https://www.gktoday.in/feed/",
     "title_must": r"quiz|gk questions?|mcq|current affairs [0-9]|practice",
     "title_not": _QUIZ_NOT},
    {"name": "InsightsIndia Quiz", "enabled": True, "type": "rss", "exam": "upsc",
     "feed": "https://www.insightsonindia.com/feed",
     "title_must": r"quiz", "title_not": _QUIZ_NOT},
    {"name": "Testbook Quizzes", "enabled": True, "type": "rss", "exam": "all",
     "feed": "https://testbook.com/blog/feed/",
     "title_must": r"quiz|mcq|questions?|practice set", "title_not": _QUIZ_NOT},

    # ---- Banking / Insurance (IBPS, SBI, RRB, RBI, LIC) ---------------------------
    {"name": "BankersAdda Quiz", "enabled": True, "type": "rss", "exam": "banking",
     "feed": "https://www.bankersadda.com/feed",
     "title_must": r"quiz|questions?|reasoning|quant|aptitude|practice",
     "title_not": _QUIZ_NOT},
    {"name": "Guidely Quiz", "enabled": True, "type": "rss", "exam": "banking",
     "feed": "https://guidely.in/blog/feed",
     "title_must": r"quiz|questions?|practice set|mcq", "title_not": _QUIZ_NOT},
    {"name": "Oliveboard Quiz", "enabled": True, "type": "rss", "exam": "banking",
     "feed": "https://www.oliveboard.in/blog/feed/",
     "title_must": r"quiz|questions?|practice|mcq", "title_not": _QUIZ_NOT},

    # ---- SSC / UPSC / central -----------------------------------------------------
    {"name": "SSCAdda Quiz", "enabled": True, "type": "rss", "exam": "ssc",
     "feed": "https://www.sscadda.com/feed",
     "title_must": r"quiz|questions?|reasoning|general awareness|practice|gs set|gk",
     "title_not": _QUIZ_NOT},
    {"name": "CareerPower SSC", "enabled": True, "type": "rss", "exam": "ssc",
     "feed": "https://www.careerpower.in/blog/feed",
     "title_must": r"quiz|questions?|practice set|mcq|ssc", "title_not": _QUIZ_NOT},

    # ---- Railway (RRB NTPC / Group-D / ALP) ---------------------------------------
    {"name": "RailwayAdda Quiz", "enabled": True, "type": "rss", "exam": "railway",
     "feed": "https://www.rrbadda.com/feed",
     "title_must": r"quiz|questions?|practice|reasoning|gs set|general awareness",
     "title_not": _QUIZ_NOT},

    # ---- Deep static MCQ banks (HTML index/section pages, dedicated adapter) ------
    {"name": "IndiaBIX Aptitude", "enabled": True, "type": "index",
     "exam": "banking-ssc-railway", "adapter": "indiabix",
     "url": "https://www.indiabix.com/aptitude/questions-and-answers/",
     "link_re": r"^https://www\.indiabix\.com/aptitude/[a-z0-9\-]+/?$",
     "max_links": 3},
    {"name": "IndiaBIX Verbal Reasoning", "enabled": True, "type": "index",
     "exam": "all", "adapter": "indiabix",
     "url": "https://www.indiabix.com/verbal-reasoning/questions-and-answers/",
     "link_re": r"^https://www\.indiabix\.com/verbal-reasoning/[a-z0-9\-]+/?$",
     "max_links": 3},
    {"name": "IndiaBIX Logical Reasoning", "enabled": True, "type": "index",
     "exam": "all", "adapter": "indiabix",
     "url": "https://www.indiabix.com/logical-reasoning/questions-and-answers/",
     "link_re": r"^https://www\.indiabix\.com/logical-reasoning/[a-z0-9\-]+/?$",
     "max_links": 3},
    {"name": "IndiaBIX Non-Verbal Reasoning", "enabled": True, "type": "index",
     "exam": "all", "adapter": "indiabix",
     "url": "https://www.indiabix.com/non-verbal-reasoning/questions-and-answers/",
     "link_re": r"^https://www\.indiabix\.com/non-verbal-reasoning/[a-z0-9\-]+/?$",
     "max_links": 2},
    {"name": "IndiaBIX General Knowledge", "enabled": True, "type": "index",
     "exam": "ssc-upsc-railway", "adapter": "indiabix",
     "url": "https://www.indiabix.com/general-knowledge/questions-and-answers/",
     "link_re": r"^https://www\.indiabix\.com/general-knowledge/[a-z0-9\-]+/?$",
     "max_links": 3},
]

# Polite throughput per run. Collection runs many times a day, so each run is
# small; the seen-URL store makes successive runs page forward to NEW content.
# These are FALLBACKS — the central registry (data/collector_sources.json)
# carries per-source limits and its "defaults" block overrides these live.
MAX_ARTICLES_PER_SOURCE = 2
MAX_LINKS_PER_INDEX = 3
MAX_PAGES_PER_INDEX = 2
MAX_QUESTIONS_PER_RUN = 160
POLITE_DELAY_SEC = 2.0          # min seconds between hits on the same host
FETCH_TIMEOUT = 20
AUTO_PAUSE_AFTER_FAILURES = 3   # pause a source after N consecutive bad runs


def _registry_defaults() -> dict:
    data = load_json(REGISTRY, {})
    return data.get("defaults", {}) if isinstance(data, dict) else {}


def load_registry() -> dict:
    """The single, central source registry (data/collector_sources.json)."""
    return load_json(REGISTRY, {"sources": [], "defaults": {}})


def registry_sources() -> list[dict]:
    """Enabled sources from the central registry, minus health-paused ones.

    When the registry is absent (fresh checkout) the built-in DEFAULT_SOURCES
    are used instead, so the engine never breaks.
    """
    data = load_registry()
    srcs = data.get("sources") or []
    if not srcs:
        return []
    health = load_json(HEALTH, {"sources": {}}).get("sources", {})
    out = []
    for s in srcs:
        if not s.get("enabled", True):
            continue
        name = s.get("name", "?")
        h = health.get(name, {})
        if h.get("paused"):
            print(f"   [collect] {name} PAUSED "
                  f"({h.get('consecutive_failures', 0)} consecutive failures)")
            continue
        out.append(dict(s))
    return out


def record_health(source_name: str, ok: bool, detail: str = "",
                  path=None) -> None:
    """Append one run result to the per-source health store (atomic JSON).

    After AUTO_PAUSE_AFTER_FAILURES consecutive failures the source is paused
    automatically; `core.auditor.audit_all()` re-checks paused sources and
    unpauses them when they come back live.
    """
    data = load_json(path or HEALTH, {"sources": {}})
    if not isinstance(data, dict) or "sources" not in data:
        data = {"sources": {}}
    h = data["sources"].setdefault(source_name, {
        "ok_runs": 0, "fail_runs": 0, "consecutive_failures": 0, "paused": False,
    })
    now = datetime.now(config.IST).strftime("%Y-%m-%d %H:%M:%S")
    if ok:
        h["ok_runs"] = h.get("ok_runs", 0) + 1
        h["consecutive_failures"] = 0
        h["paused"] = False
        h["last_ok"] = now
        h.pop("last_error", None)
        h.pop("last_fail", None)
        if detail:
            h["last_note"] = detail
    else:
        h["fail_runs"] = h.get("fail_runs", 0) + 1
        h["consecutive_failures"] = h.get("consecutive_failures", 0) + 1
        h["last_fail"] = now
        h["last_error"] = detail[:200] if detail else "unknown"
        if h["consecutive_failures"] >= AUTO_PAUSE_AFTER_FAILURES:
            h["paused"] = True
    try:
        save_json_atomic(path or HEALTH, data)
    except Exception as e:
        print(f"   [collect] health write note: {e}")


def health_summary() -> dict:
    data = load_json(HEALTH, {"sources": {}})
    srcs = data.get("sources", {})
    return {
        "sources": srcs,
        "ok": sum(1 for h in srcs.values() if not h.get("paused")
                  and h.get("consecutive_failures", 0) == 0),
        "paused": sum(1 for h in srcs.values() if h.get("paused")),
        "failing": sum(1 for h in srcs.values() if not h.get("paused")
                       and h.get("consecutive_failures", 0) > 0),
    }

# ---------------------------------------------------------------------------
# Channel / topic inference
# ---------------------------------------------------------------------------
_CHANNEL_KEYWORDS = [
    ("TSPSC", r"tspsc|tgpsc|telangana|తెలంగాణ|టీజీపీఎస్సీ|టీఎస్‌?పీఎస్సీ"),
    ("APPSC", r"appsc|andhra pradesh|ap police|ఆంధ్ర|ఏపీపీఎస్సీ|ఏపీ "),
    ("RAILWAY", r"railway|rrb\b|ntpc|group[\s-]?d|alp|je[e]? exam|రైల్వే"),
    ("POLICE", r"police|constable|sub[\s-]?inspector|\bsi\b|dsp|tslprb|slprb|పోలీసు|పోలీస్|కానిస్టేబుల్|ఎస్సై|ఎస్‌ఐ"),
    ("DEFENCE", r"\bnda\b|cds|defen[cs]e|agniveer|army|navy|air[\s-]?force|capf|రక్షణ|సైనిక"),
    ("SSC", r"\bssc\b|cgl|chsl|\bmts\b|ssc[\s-]?gd|\bcpo\b|selection post|ఎస్‌ఎస్‌సీ"),
    ("BANKING", r"bank|ibps|sbi|rrb po|rrb clerk|po exam|clerk|insurance|lic|niacl|rbi assistant|బ్యాంక్|ఐబీపీఎస్"),
    ("CURRENT", r"current affairs|general awareness|static gk|gk quiz|upsc|polity|history|geograph|econom|science|biology|physics|chemistry"),
]

_TOPIC_KEYWORDS = [
    ("percentage", r"percent|percentage|%|శాతం"),
    ("ratio", r"\bratio\b|proportion|నిష్పత్తి|అనుపాతం"),
    ("simple interest", r"simple interest|\bsi\b|సాధారణ వడ్డీ|బారువడ్డీ"),
    ("compound interest", r"compound interest|\bci\b|చక్రవడ్డీ"),
    ("profit & loss", r"profit|loss|discount|marked price|లాభం|నష్టం|డిస్కౌంట్"),
    ("average", r"average|సగటు"),
    ("time-work", r"work.*days|days.*work|pipes?|cist ern|time and work|పని.*రోజుల|రోజుల.*పని|గొట్టా"),
    ("time-distance", r"speed|distance|train|boat|stream|వేగం|దూరం|రైలు|పడవ|ప్రవాహ"),
    ("number series", r"series|sequence|missing number|next term|శ్రేణి|తరువాత సంఖ్య|తప్పిపోయిన సంఖ్య"),
    ("number system", r"number system|hcf|lcm|divisib|remainder|గ\.సా\.భా|క\.సా\.గు|భాజనీయత|శేషం"),
    ("coding-decoding", r"cod(e|ing)|decod|cipher|కోడింగ్|సంకేత"),
    ("blood relation", r"blood relation|related to|father|mother|daughter|son of|రక్త సంబంధ|తండ్రి|తల్లి|కుమారుడు|కుమార్తె"),
    ("direction", r"direction|north|south|east|west|facing|దిశ|ఉత్తరం|దక్షిణం|తూర్పు|పడమర"),
    ("syllogism", r"syllogis|న్యాయవాక్య"),
    ("seating", r"seating|sitting|row|circular arrangement"),
    ("clock-calendar", r"clock|calendar|day of the week|angle between"),
    ("analogy", r"analog|::|similar to"),
    ("ranking", r"rank|position in|row of|from the (left|right)"),
    ("current affairs", r"current affairs|recent|appointed|launched|summit|award|scheme|cabinet|bill passed"),
    ("polity", r"article|constitution|parliament|lok sabha|rajya sabha|amendment|fundamental"),
    ("history", r"battle|empire|dynasty|independence|movement|mughal|british|founded in"),
    ("geography", r"river|mountain|state|capital|coastline|dam|national park|border"),
    ("economy", r"gdp|gst|rbi|repo|inflation|bank rate|currency|fiscal"),
    ("general science", r"vitamin|chemical|planet|cell|gas|metal|unit of|hormone|enzyme|blood group"),
]


# ---------------------------------------------------------------------------
# Offline Telugu for numeric/aptitude stems (works with NO API key).
# Matches common quantitative phrasings and renders proper Telugu with the
# numbers/values preserved. Worded GK/reasoning still parks until an LLM key
# is present (quality matters for those).
# ---------------------------------------------------------------------------
def _te_digits(s):
    table = str.maketrans("0123456789", "౦౧౨౩౪౫౬౭౮౯")
    return s.translate(table)


_APT_TEMPLATES = [
    (r"what is\s+([\d.]+)\s*%\s+of\s+([\d,]+)",
     "{n1} లో {n0}% ఎంత?"),
    (r"simple interest on\s*(?:rs\.?|₹?)\s*([\d,]+).*?([\d.]+)\s*%.*?([\d]+)\s*year",
     "₹{n0}పై సంవత్సరానికి {n1}% చొప్పున {n2} సంవత్సరాల సాధారణ వడ్డీ ఎంత?"),
    (r"compound interest on\s*(?:rs\.?|₹?)\s*([\d,]+).*?([\d.]+)\s*%.*?([\d]+)\s*year",
     "₹{n0}పై {n1}% వార్షిక చక్రవడ్డీ {n2} సంవత్సరాలకు ఎంత?"),
    (r"missing number\s*:?\s*([\d,\s?]+)",
     "తప్పిపోయిన సంఖ్యను కనుగొనండి: {n0}"),
    (r"next (?:number|term).*?[:\-]?\s*([\d,\s?]+)",
     "తర్వాతి సంఖ్య ఏది: {n0}"),
    (r"complete the series\s*:?\s*([\d,\s?]+)",
     "శ్రేణిని పూర్తి చేయండి: {n0}"),
    (r"average of\s+(\d+).*?(?:numbers?|is)\s+([\d.]+)",
     "{n0} సంఖ్యల సగటు {n1}."),
    (r"ratio\s+([\d]+)\s*:\s*([\d]+)",
     "నిష్పత్తి {n0}:{n1}."),
    (r"speed of\s+([\d.]+)\s*(?:km|kmph)",
     "వేగం గంటకు {n0} కి.మీ."),
    (r"cost price|selling price",
     "లాభం/నష్టం ప్రశ్న — కొన్నధర/అమ్మకధర ఆధారంగా."),
    (r"\b(\d+)\s*%\s+of\s+([\d,]+)",
     "{n1} లో {n0}% ఎంత?"),
]


def aptitude_telugu(en: str):
    """Return a Telugu rendering for a numeric/aptitude stem, or '' if no match."""
    low = (en or "").lower()
    for pat, tmpl in _APT_TEMPLATES:
        m = re.search(pat, low)
        if not m:
            continue
        nums = [_te_digits(g.strip()) for g in m.groups()]
        try:
            out = tmpl.format(*nums, **{f"n{i}": v for i, v in enumerate(nums)})
            return f"⤷ {out}"
        except Exception:
            continue
    return ""


def scrape_fingerprint(raw):
    """Stable content identity for a parsed question (independent of inferred
    channel/topic), so re-scraping the same article never duplicates."""
    import hashlib
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    q = norm(raw["q_en"])
    opts = "|".join(norm(str(o)) for o in raw["options_en"])
    return hashlib.sha1(f"{q}::{opts}".encode("utf-8")).hexdigest()[:24]


_EXAM_TAG_CHANNEL = [
    ("tspsc", "TSPSC"), ("tgpsc", "TSPSC"), ("appsc", "APPSC"),
    ("police", "POLICE"), ("banking", "BANKING"), ("railway", "RAILWAY"),
    ("defence", "DEFENCE"), ("ssc", "SSC"), ("upsc", "CURRENT"),
]


def channel_for_source(src: dict):
    """A source tagged for exactly one exam family pins its questions to that
    channel (e.g. exam='tspsc' -> TSPSC). Multi-exam tags ('ssc-upsc-railway',
    'all') return None so per-question inference decides."""
    tag = str((src or {}).get("exam", "")).lower().strip()
    if not tag or tag == "all":
        return None
    parts = [p for p in re.split(r"[-_/,\s]+", tag) if p]
    hits = []
    for p in parts:
        for key, ch in _EXAM_TAG_CHANNEL:
            if p == key and ch not in hits:
                hits.append(ch)
    if len(hits) == 1:
        return hits[0]
    if hits and hits[0] in ("TSPSC", "APPSC") and set(hits) <= {"TSPSC", "APPSC"}:
        return hits[0]           # 'tspsc-appsc' Telugu material -> TSPSC (shared)
    return None


def infer_channel(*texts):
    blob = " ".join(t or "" for t in texts).lower()
    for ch, pat in _CHANNEL_KEYWORDS:
        if re.search(pat, blob):
            return ch
    return "CURRENT"


def infer_topic(*texts):
    blob = " ".join(t or "" for t in texts).lower()
    for topic, pat in _TOPIC_KEYWORDS:
        if re.search(pat, blob):
            return topic
    return "exam practice"


# ---------------------------------------------------------------------------
# Polite fetching (retries, backoff, robots, per-host delay)
# ---------------------------------------------------------------------------
_HOST_LAST_HIT = {}
_ROBOTS_CACHE = {}


def _sleep_polite(host):
    now = time.time()
    last = _HOST_LAST_HIT.get(host, 0.0)
    wait = POLITE_DELAY_SEC - (now - last) + random.uniform(0, 0.8)
    if wait > 0:
        time.sleep(wait)
    _HOST_LAST_HIT[host] = time.time()


def robots_allowed(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).netloc
    if host in _ROBOTS_CACHE:
        return _ROBOTS_CACHE[host]
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(urljoin(url, "/robots.txt"))
    allowed = True
    try:
        rp.read()
        allowed = rp.can_fetch(USER_AGENT, url)
    except Exception:
        allowed = True  # no robots / unreachable -> polite defaults still apply
    _ROBOTS_CACHE[host] = allowed
    return allowed


def _jina_fetch(url: str, timeout=FETCH_TIMEOUT):
    """Jina Reader fallback (r.jina.ai) — bypasses bot-blocking / anti-scrape
    walls on sites that refuse plain requests. Returns text or None."""
    key = config.env("JINA_API_KEY", "")
    if not key:
        return None
    jurl = JINA_API + url
    headers = {"Authorization": f"Bearer {key}", "Accept": "text/plain"}
    try:
        req = urllib.request.Request(jurl, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"   [collect] jina fallback note {url}: {e}")
        return None


def is_feed_url(url: str) -> bool:
    """True for RSS/Atom feed URLs (Jina fallback is useless there — it
    returns rendered markdown, not XML)."""
    return bool(FEED_URL_RE.search(url or ""))


def http_get(url: str, timeout=FETCH_TIMEOUT, retries=2, respect_robots=True):
    """GET with browser headers, backoff, robots check. Returns text or None.
    If the direct fetch fails AND the URL is an HTML page (not a feed), tries
    the Jina Reader as an optional second path (when JINA_API_KEY is set)."""
    if respect_robots and not robots_allowed(url):
        print(f"   [collect] robots.txt disallows: {url}")
        return None
    from urllib.parse import urlparse
    host = urlparse(url).netloc
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-IN,en;q=0.8",
    }
    for attempt in range(retries + 1):
        _sleep_polite(host)
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            # decode best-effort
            ctype = resp.headers.get("Content-Type", "")
            enc = "utf-8"
            m = re.search(r"charset=([\w-]+)", ctype)
            if m:
                enc = m.group(1)
            try:
                return raw.decode(enc, errors="replace")
            except Exception:
                return raw.decode("utf-8", errors="replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            print(f"   [collect] fetch failed {url}: {e}")
            # anti-scrape walls often 403 the plain GET -> Jina Reader fallback
            if not is_feed_url(url):
                via_jina = _jina_fetch(url, timeout)
                if via_jina and len(via_jina) > 400:
                    print(f"   [collect] recovered via Jina Reader: {url}")
                    return via_jina
            return None
        except Exception as e:  # never crash the collector on a bad page
            print(f"   [collect] parse/fetch error {url}: {e}")
            return None
    return None


# ---------------------------------------------------------------------------
# HTML -> text blocks (article-aware, script/style/nav stripped)
# ---------------------------------------------------------------------------
_DROP_TAGS = {"script", "style", "noscript", "nav", "header", "footer",
              "aside", "form", "button", "svg", "iframe"}
_BLOCK_TAGS = {"p", "li", "div", "br", "tr", "h1", "h2", "h3", "h4",
               "blockquote", "section", "figcaption"}
_JUNK_CLS = re.compile(
    r"(menu|nav|sidebar|footer|header|comment|share|related|advert|sponsor|"
    r"breadcrumb|popup|newsletter|social|tag-list|author-box|post-nav)", re.I)


class _ArticleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0
        self.article_depth = 0
        self.saw_article = False
        self.in_article = True

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag == "article":
            self.saw_article = True
            self.article_depth += 1
            self.in_article = True
        if tag in _DROP_TAGS:
            self.skip_depth += 1
            return
        cls = (ad.get("class", "") or "") + " " + (ad.get("id", "") or "")
        if tag in ("div", "section", "ul", "ol") and _JUNK_CLS.search(cls):
            self.skip_depth += 1
            self._junk = True
            return
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "article" and self.article_depth > 0:
            self.article_depth -= 1
        if self.skip_depth > 0:
            self.skip_depth -= 1
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        if self.saw_article and self.article_depth == 0:
            return  # outside the article body
        self.parts.append(data)


def html_to_lines(page_html: str):
    """Extract ordered text lines from the article/main content."""
    p = _ArticleText()
    try:
        p.feed(page_html)
    except Exception:
        pass
    text = "".join(p.parts)
    text = html.unescape(text)
    lines = []
    for ln in text.split("\n"):
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln:
            lines.append(ln)
    return lines


# ---------------------------------------------------------------------------
# Quiz-block state machine
# ---------------------------------------------------------------------------
QSTART_RE = re.compile(r"^(?:q(?:uestion)?\.?\s*|ప్రశ్న\s*|प्रश्न\s*)?(\d{1,3})[\)\.:\-]\s*(.+)$", re.I)
# Option labels: Latin A-D, Telugu ఎ/బి/సి/డి, Hindi अ/ब/स/द
_TE_LABELS = {"ఎ": "A", "బి": "B", "సి": "C", "డి": "D"}
_HI_LABELS = {"अ": "A", "ब": "B", "स": "C", "द": "D"}
_LBL = r"([A-Da-d]|ఎ|బి|సి|డి|अ|ब|स|द)"
OPT_RE = re.compile(r"^[\(\[]?" + _LBL + r"[\)\].:\-]\s+(.+)$")
OPT_INLINE_RE = re.compile(r"(?:^|\s)[\(\[]?" + _LBL + r"[\)\].:\-]\s+")
# "Answer: B" / "Ans- C" / "Correct Answer: C [1952]" / "Answer: Option D" /
# "Correct option is (B)" / Telugu "జవాబు: B)" "సమాధానం: బి" / Hindi "उत्तर: (b)"
# — but NOT "Answer & Solution Discuss..." chrome.
ANS_RE = re.compile(
    r"(?:correct\s+answer|correct\s+option|answer|ans|జవాబు|సమాధానం|సరైన\s*సమాధానం|उत्तर|सही\s*उत्तर)"
    r"\s*(?:is|:|-|=|–)?\s*(?:option)?\s*(?:\(|\[)?\s*" + _LBL + r"(?:[\)\].\]]|\b|(?=\s)|$)", re.I)
EXPL_RE = re.compile(r"^(?:explanation|solution|sol|exp|notes?|hint|వివరణ|व्याख्या)[\.:\-]\s*(.+)$", re.I)
# label-only lines ("Notes:", "Explanation:") -> the body follows on the next line(s)
EXPL_LABEL_RE = re.compile(r"^(?:explanation|solution|notes?|hint|answer\s*&\s*solution|వివరణ|व्याख्या)\s*[\.:\-]?\s*$", re.I)
# UI chrome that quiz sites render between questions (never content)
_JUNK_LINE_RE = re.compile(
    r"^(?:show answer|hide answer|view (?:answer|explanation|solution|score)|discuss in board|"
    r"save for later|report(?: error)?|share|prev(?:ious)?|next|answer\s*&\s*solution"
    r"(?:\s+discuss in board)?(?:\s+save for later)?|workspace|\d+\s*/\s*\d+|"
    r"page \d+ of \d+|advertisement|sponsored|spread the love|correct|incorrect|"
    r"unattempted|మీ స్కోర్.*|your score.*|\d+ points?|codes?:)\s*[:\.]?$", re.I)
_LABELS = "ABCD"


def _norm_label(tok: str) -> str:
    return _TE_LABELS.get(tok, _HI_LABELS.get(tok, tok)).upper()


def _split_leading_options(rest: str):
    """'question? ఎ) x  బి) y' (first 1-3 options glued to the stem) ->
    (question, [labels], [opts]) or None."""
    marks = list(OPT_INLINE_RE.finditer(rest))
    if not marks:
        return None
    labels = [_norm_label(m.group(1)) for m in marks]
    if labels != list("ABCD")[:len(labels)] or len(labels) >= 4:
        return None
    qtext = rest[:marks[0].start()].strip()
    if len(qtext) < 8:
        return None
    opts = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(rest)
        opts.append(rest[m.end():end].strip(" \t;|"))
    if all(opts):
        return qtext, labels, opts
    return None


def _inline_options(rest: str):
    """'question ... A) x  B) y  C) z  D) w' -> (question, [opts]) or None."""
    marks = list(OPT_INLINE_RE.finditer(rest))
    labels = [_norm_label(m.group(1)) for m in marks]
    if labels != ["A", "B", "C", "D"]:
        return None
    qtext = rest[:marks[0].start()].strip()
    opts = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(rest)
        val = rest[m.end():end].strip(" \t;|")
        opts.append(val)
    if qtext and all(opts):
        return qtext, opts
    return None


# Sakshi bitbank style: options numbered "1) .. 4)" (option 1 often glued to the
# stem line) and a numeric key "సమాధానం: 2".  Rewrite to A)-D) before parsing.
_NUM_OPT_RE = re.compile(r"^([1-4])\)\s*(.+)$")
_NUM_STEM_GLUE_RE = re.compile(r"^(.+?\S)\s+1\)\s*(.+)$")
_NUM_ANS_RE = re.compile(
    r"^(?:\W*)(answer|ans|జవాబు|సమాధానం|సరైన\s*సమాధానం|उत्तर|सही\s*उत्तर)\s*[:\-=–]?\s*"
    r"(?:option\s*)?\(?([1-5])\)?(?:\s*[\)\.:\-–]?\s*[^\d].{0,80})?\s*$", re.I)
# Banking-style 5th option that can be dropped when it is not the key
_NUM_OPT5_RE = re.compile(r"^5\)\s*(.+)$")
_FILLER_OPT_RE = re.compile(
    r"^(?:none of (?:these|the above|them)|cannot be determined|can't be determined|"
    r"data inadequate|other than (?:those|the) given(?: as)? options?|none)\.?$", re.I)


# Examsbook / some blogs: a bare "Q :" / "Question:" label line followed by the
# stem on the next line, with no numbering at all -> synthesise "N. stem".
_BARE_Q_RE = re.compile(r"^(?:q|que|question|ప్రశ్న|प्रश्न)\s*[:.\-)]?\s*$", re.I)


# GKSeries / IndiaBIX-style markup: the question NUMBER sits alone on a line
# ("1") followed by the stem, and each option LABEL sits alone ("A") followed
# by the option text -> fold them into "1. stem" / "A) text".
_BARE_NUM_RE = re.compile(r"^(\d{1,3})[\.\)]?$")
_BARE_LBL_RE = re.compile(r"^[\(\[]?([A-Da-d]|ఎ|బి|సి|డి)[\)\].]?$")


def _fold_bare_labels(lines):
    out, i, n, folded = [], 0, len(lines), 0
    while i < n:
        ln = lines[i]
        nxt = lines[i + 1] if i + 1 < n else ""
        if nxt and _BARE_NUM_RE.match(ln) and len(nxt) >= 8 \
                and not OPT_RE.match(nxt) and not _BARE_LBL_RE.match(nxt) \
                and not QSTART_RE.match(nxt) and not ANS_RE.search(nxt):
            out.append(f"{_BARE_NUM_RE.match(ln).group(1)}. {nxt}")
            i += 2
            folded += 1
            continue
        if nxt and _BARE_LBL_RE.match(ln) and not _BARE_LBL_RE.match(nxt) \
                and not QSTART_RE.match(nxt) and not ANS_RE.search(nxt) \
                and 0 < len(nxt) <= 120:
            out.append(f"{_BARE_LBL_RE.match(ln).group(1).upper()}) {nxt}")
            i += 2
            folded += 1
            continue
        out.append(ln)
        i += 1
    return out if folded else lines


def _number_bare_questions(lines):
    out, n, i = [], 0, 0
    while i < len(lines):
        if _BARE_Q_RE.match(lines[i]) and i + 1 < len(lines) \
                and not OPT_RE.match(lines[i + 1]) and not QSTART_RE.match(lines[i + 1]):
            n += 1
            out.append(f"{n}. {lines[i + 1]}")
            i += 2
            continue
        out.append(lines[i])
        i += 1
    return out if n else lines


def _normalize_numeric_options(lines):
    """Convert '1)..4)' numbered options + numeric answer keys to A)-D) labels
    (only when a full 2)3)4) run follows, so numbered sub-statements are safe)."""
    out = []
    i, n = 0, len(lines)
    letters = "ABCD"
    while i < n:
        line = lines[i]
        mq = QSTART_RE.match(line)
        converted = False
        if mq:
            rest = mq.group(2).strip()
            glue = _NUM_STEM_GLUE_RE.match(rest)
            # case 1: "N. stem 1) opt" + "2) .." "3) .." "4) .."
            if glue and i + 3 < n and all(
                    _NUM_OPT_RE.match(lines[i + k]) and lines[i + k].startswith(f"{k + 1})")
                    for k in range(1, 4)):
                out.append(f"{mq.group(1)}. {glue.group(1)}")
                out.append(f"A) {glue.group(2)}")
                for k in range(1, 4):
                    out.append(f"{letters[k]}) {_NUM_OPT_RE.match(lines[i + k]).group(2)}")
                i += 4
                converted = True
            # case 2: "N. stem" + "1) .." .. "4) .."
            elif i + 4 < n and all(
                    _NUM_OPT_RE.match(lines[i + k]) and lines[i + k].startswith(f"{k})")
                    for k in range(1, 5)):
                out.append(line)
                for k in range(1, 5):
                    out.append(f"{letters[k - 1]}) {_NUM_OPT_RE.match(lines[i + k]).group(2)}")
                i += 5
                converted = True
        if converted:
            # AffairsCloud / banking sets: a 5th filler option ("None of these")
            # follows -- drop it as long as the key is 1-4.
            m5 = _NUM_OPT5_RE.match(lines[i]) if i < n else None
            if m5 and _FILLER_OPT_RE.match(m5.group(1).strip()):
                i += 1
            # numeric answer key within the next few lines
            j = i
            while j < n and j < i + 4:
                ma = _NUM_ANS_RE.match(lines[j])
                if ma:
                    k = int(ma.group(2))
                    if k == 5:
                        # key was the dropped filler -> make the question unusable
                        lines[j] = "Answer: -"
                    else:
                        lines[j] = f"{ma.group(1)}: {letters[k - 1]}"
                    break
                if QSTART_RE.match(lines[j]):
                    break
                j += 1
            continue
        out.append(line)
        i += 1
    return out


def parse_quiz_lines(lines, article_title="", url=""):
    """Tolerant quiz extractor for WordPress / GKToday / Examveda-style pages.

    Handles:
      * "1) Q", "Q1. Q", "1. Q" stems, options as A) / (A) / [A] / A. lines,
        or all four options inline on the stem line;
      * numbered SUB-STATEMENTS inside a stem ("Consider the following: 1. ...
        2. ...") -- a numbered line that breaks the running question sequence
        while the current question has no options yet is a continuation;
      * "Answer: B", "Correct Answer: C [1952]", "Answer: Option D",
        "Correct option is (B)";
      * "Explanation:/Solution:/Notes:" on the same or the NEXT line(s) --
        multi-line explanations are joined (capped);
      * UI chrome ("Show Answer", "Discuss in Board", "1 / 20") is ignored.
    Returns list of raw question dicts.
    """
    raw_qs = []
    keyless = []               # complete questions whose key comes in a table
    cur = None
    next_num = None            # expected number of the next question stem
    in_expl = False            # collecting explanation body lines

    def finalize():
        nonlocal cur, in_expl
        in_expl = False
        if not cur:
            return
        opts = cur["opts"]
        q = re.sub(r"\s+", " ", cur["q"]).strip()
        if len(opts) == 4 and cur["ans"] is None and 8 <= len(q) <= 300:
            keyless.append({"num": cur.get("num"), "q": q, "opts": opts[:],
                            "expl": cur["expl"]})
        if (len(opts) == 4 and cur["ans"] is not None
                and len(q) >= 8 and len(q) <= 300
                and all(0 < len(o) <= 90 for o in opts)
                and len({o.lower() for o in opts}) == 4):
            blocked, _ = is_blocked(q + " " + " ".join(opts))
            if not blocked:
                raw_qs.append({
                    "q_en": q, "options_en": opts,
                    "answer_index": cur["ans"],
                    "explanation_en": re.sub(r"\s+", " ", cur["expl"]).strip()[:280],
                    "title": article_title, "url": url,
                })
        cur = None

    lines = _normalize_numeric_options(_number_bare_questions(_fold_bare_labels(list(lines))))
    for line in lines:
        if len(line) > 400:
            line = line[:400]
        if _JUNK_LINE_RE.match(line):
            continue
        mo = OPT_RE.match(line)
        mq = QSTART_RE.match(line)
        ma = ANS_RE.search(line)
        mex = EXPL_RE.match(line)
        mlabel = EXPL_LABEL_RE.match(line)

        if mq and not mo:
            num = int(mq.group(1))
            rest = mq.group(2).strip()
            # numbered sub-statement inside the current stem?
            if (cur is not None and not cur["opts"] and cur["ans"] is None
                    and next_num is not None and num != next_num
                    and len(cur["q"]) + len(rest) < 300):
                cur["q"] += f" {num}. {rest}"
                continue
            inline = _inline_options(rest)
            if inline:
                finalize()
                qtext, opts = inline
                cur = {"q": qtext, "opts": opts[:], "ans": None,
                       "expl": "", "labels": ["A", "B", "C", "D"], "num": num}
                if ma:
                    cur["ans"] = _ans_index(ma.group(1))
                next_num = num + 1
                continue
            finalize()
            cur = {"q": rest, "opts": [], "ans": None, "expl": "",
                   "labels": [], "num": num}
            lead = _split_leading_options(rest)
            if lead:
                cur["q"], cur["labels"], cur["opts"] = lead[0], lead[1], lead[2]
            if ma:
                cur["ans"] = _ans_index(ma.group(1))
            next_num = num + 1
            continue

        if mo and cur is not None and len(cur["opts"]) < 4:
            label = _norm_label(mo.group(1))
            val = mo.group(2).strip()
            if label not in cur["labels"] and val:
                cur["labels"].append(label)
                cur["opts"].append(val)
            if ma and cur["ans"] is None:
                cur["ans"] = _ans_index(ma.group(1))
            continue

        # MCQBits-style: after "View Answer" the correct option is repeated
        # verbatim as its own "C) text" line -> that label is the answer.
        if mo and cur is not None and len(cur["opts"]) == 4 and cur["ans"] is None:
            label = _norm_label(mo.group(1))
            val = mo.group(2).strip().lower()
            if label in cur["labels"]:
                i = cur["labels"].index(label)
                if val[:30] == cur["opts"][i].lower()[:30]:
                    cur["ans"] = i
                    continue

        if cur is None:
            continue

        # stem continuation: text between the stem and the first option
        if (not cur["opts"] and cur["ans"] is None and not ma and not mex
                and not mlabel and len(cur["q"]) + len(line) < 300
                and not re.match(r"^(?:directions?|instructions?)\b", line, re.I)):
            cur["q"] += " " + line
            continue

        if ma and cur["ans"] is None:
            cur["ans"] = _ans_index(ma.group(1))
            # "Correct Answer: C [1952]" may carry no explanation on this line
            in_expl = False
            tail = line[ma.end():].strip(" :-[]")
            if mex:
                cur["expl"] = mex.group(1)
                in_expl = True
            continue
        if mex:
            cur["expl"] = (cur["expl"] + " " + mex.group(1)).strip()
            in_expl = True
            continue
        if mlabel:
            in_expl = True
            continue
        if in_expl and cur["ans"] is not None and len(cur["expl"]) < 280:
            # short heading-like lines (no sentence punctuation) end the body
            if len(line) < 45 and not re.search(r"[\.;:,=%)]", line):
                in_expl = False
                continue
            cur["expl"] = (cur["expl"] + " " + line).strip()

    finalize()
    # Previous-paper layout: questions first, then an ANSWER KEY table
    # ("1. (c) 2. (b) 3. (a)..." / "1-C 2-A" / "1) 3  2) 1"). Resolve keyless
    # questions against it (numbered 1-4 keys are accepted too).
    if keyless:
        key = _answer_key_table(lines)
        for item in keyless:
            idx = key.get(item["num"])
            if idx is None:
                continue
            opts = item["opts"]
            if (all(0 < len(o) <= 90 for o in opts)
                    and len({o.lower() for o in opts}) == 4):
                blocked, _ = is_blocked(item["q"] + " " + " ".join(opts))
                if not blocked:
                    raw_qs.append({
                        "q_en": item["q"], "options_en": opts,
                        "answer_index": idx,
                        "explanation_en": re.sub(r"\s+", " ", item["expl"]).strip()[:280],
                        "title": article_title, "url": url,
                    })
        raw_qs.sort(key=lambda r: 0)  # stable; keep discovery order
    return raw_qs


_KEY_PAIR_RE = re.compile(
    r"(?<![\d.])(\d{1,3})\s*[\)\.:\-–]\s*[\(\[]?([A-Da-d1-4]|ఎ|బి|సి|డి|अ|ब|स|द)[\)\]]?(?![\w\)])")


def _answer_key_table(lines):
    """Find a dense 'N. (x)' key block (>=5 pairs in a window) -> {num: idx}."""
    key = {}
    dense_started = False
    for ln in lines:
        pairs = _KEY_PAIR_RE.findall(ln)
        head = re.match(r"^(?:answer\s*key|answers|key|జవాబులు|సమాధానాలు|उत्तर\s*कुंजी)\b", ln, re.I)
        if head:
            dense_started = True
        if len(pairs) >= 5 or (dense_started and len(pairs) >= 1 and len(ln) < 40):
            dense_started = True
            for n, tok in pairs:
                idx = _ans_index(tok)
                if idx is not None and int(n) not in key:
                    key[int(n)] = idx
    return key if len(key) >= 5 else {}


def _ans_index(token: str):
    t = token.strip()
    t = _TE_LABELS.get(t, _HI_LABELS.get(t, t)).upper()
    if t in ("A", "B", "C", "D"):
        return "ABCD".index(t)
    if t in ("1", "2", "3", "4"):
        return int(t) - 1
    return None


# ---------------------------------------------------------------------------
# RSS quiz-article discovery
# ---------------------------------------------------------------------------
def _feed_entries(feed_url):
    """Stdlib RSS/Atom parser (feedparser is used by feeds.py if installed)."""
    from xml.etree import ElementTree as ET
    from email.utils import parsedate_to_datetime
    page = http_get(feed_url, respect_robots=False)
    if not page:
        return []
    out = []
    try:
        root = ET.fromstring(page)
    except Exception:
        return []
    for item in root.iter("item"):
        title = re.sub(r"<[^>]+>", " ", item.findtext("title", "") or "")
        link = (item.findtext("link", "") or "").strip()
        if title and link:
            out.append({"title": html.unescape(re.sub(r"\s+", " ", title)).strip(),
                        "link": link,
                        "published": (item.findtext("pubDate", "") or "").strip()})
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for e in root.findall(".//a:entry", ns):
        title = e.findtext("a:title", "", ns)
        link_el = e.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        if title and link:
            out.append({"title": html.unescape(re.sub(r"\s+", " ", title)).strip(),
                        "link": link,
                        "published": (e.findtext("a:updated", "", ns)
                                      or e.findtext("a:published", "", ns) or "").strip()})
    return out


def quiz_articles_for_source(src, entries=None):
    """Return [{title, link}] quiz articles for one configured RSS source.

    `entries` is optional so the discovery loop can fetch the feed once and
    reuse it (single fetch per run, then record health).
    """
    if entries is None:
        entries = _feed_entries(src["feed"])
    must = re.compile(src.get("title_must", r"quiz|questions|mcq"), re.I)
    notp = re.compile(src.get("title_not", r"(?!)\Z"), re.I)
    limit = int(src.get("max_articles", MAX_ARTICLES_PER_SOURCE))
    picked = []
    for e in entries:
        t = e["title"]
        if must.search(t) and not notp.search(t):
            picked.append(e)
        if len(picked) >= limit:
            break
    return picked


# ---------------------------------------------------------------------------
# HTML index / section crawling (deep sources without usable RSS)
# ---------------------------------------------------------------------------
class _LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._txt = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            ad = dict(attrs)
            self._href = ad.get("href")
            self._txt = []

    def handle_data(self, data):
        if self._href is not None:
            self._txt.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            title = re.sub(r"\s+", " ", "".join(self._txt)).strip()
            self.links.append((self._href, title))
            self._href = None
            self._txt = []


def extract_links(page_html, base_url, link_re):
    """Return [{title, link}] anchors whose absolute href matches link_re."""
    p = _LinkExtractor()
    try:
        p.feed(page_html)
    except Exception:
        return []
    rx = re.compile(link_re) if isinstance(link_re, str) else link_re
    # section landing/index pages are not per-topic quiz pages
    landing = re.compile(r"/(?:questions-and-answers|feed|forum|login|register)"
                         r"(?:[/?#].*)?$", re.I)
    out, seen = [], set()
    for href, title in p.links:
        if not href:
            continue
        link = urljoin(base_url, href)
        link = link.split("#")[0]
        if landing.search(link):
            continue
        if rx.search(link) and link not in seen:
            seen.add(link)
            out.append({"title": title or link, "link": link})
    return out


def _strip_tags(chunk):
    t = re.sub(r"<[^>]+>", " ", chunk or "")
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


# ---------------------------------------------------------------------------
# Per-site adapters — sites whose markup is NOT the standard WordPress quiz
# layout get a dedicated, carefully-tested extractor.
# ---------------------------------------------------------------------------
def parse_indiabix(page_html, article_title="", url=""):
    """IndiaBIX classic Q&A pages: bix-div-container blocks with bix-td-qtxt,
    bix-td-option-val cells, 'Answer: Option X' and an Explanation block."""
    raws = []
    # Each question lives in its own .bix-div-container block.
    blocks = re.split(r'class="bix-div-container"', page_html)
    for blk in blocks[1:]:
        mq = re.search(r'bix-td-qtxt[^>]*>(.*?)</(?:div|td)>', blk, re.S)
        if not mq:
            continue
        q = _strip_tags(mq.group(1))
        q = re.sub(r"^\s*\d{1,3}[\)\.:\-]\s*", "", q)
        opts = [_strip_tags(x) for x in
                re.findall(r'bix-td-option-val[^>]*>(.*?)</td>', blk, re.S)]
        opts = [re.sub(r"^[A-D][\)\.:]\s*", "", o).strip() for o in opts if o]
        if len(opts) < 4:
            continue
        opts = opts[:4]
        ma = (re.search(r"Answer\s*:?\s*(?:Option)?\s*<[^>]*>?\s*([A-D])", blk, re.I)
              or re.search(r"Answer\s*:?\s*(?:Option)?\s*([A-D])\b", blk, re.I))
        if not ma:
            continue
        ans = _ans_index(ma.group(1))
        me = re.search(r"Explanation\s*:?(.*?)(?:<div class=\"bix-|<input|</body)",
                       blk, re.S | re.I)
        expl = _strip_tags(me.group(1))[:280] if me else ""
        if (q and len(opts) == 4 and ans is not None and len(q) <= 300
                and len({o.lower() for o in opts}) == 4
                and all(0 < len(o) <= 90 for o in opts)):
            blocked, _ = is_blocked(q + " " + " ".join(opts))
            if not blocked:
                raws.append({"q_en": q, "options_en": opts, "answer_index": ans,
                             "explanation_en": expl, "title": article_title,
                             "url": url})
    return raws


ADAPTERS = {"indiabix": parse_indiabix}


def parse_page(src, page_html, title, url):
    """Dispatch to the source's dedicated adapter, else the generic parser."""
    adapter = src.get("adapter")
    if adapter and adapter in ADAPTERS:
        try:
            return ADAPTERS[adapter](page_html, title, url)
        except Exception as e:
            print(f"   [collect] adapter {adapter} error: {e}")
            return []
    lines = html_to_lines(page_html)
    return parse_quiz_lines(lines, article_title=title, url=url)


# ---------------------------------------------------------------------------
# Seen-URL store — so many small daily runs keep paging forward to NEW
# articles/sections instead of refetching the same pages.
# ---------------------------------------------------------------------------
SEEN_URLS_CAP = 4000


def load_seen_urls():
    return set(load_json(SEEN_URLS, {"urls": []}).get("urls", []))


def save_seen_urls(urls):
    urls = sorted(urls)[-SEEN_URLS_CAP:]
    save_json_atomic(SEEN_URLS, {"urls": urls})


# ---------------------------------------------------------------------------
# Normalization -> canonical question dict
# ---------------------------------------------------------------------------
def _id_for(n):
    return f"S{n:04d}"


def normalize_raw(raw, source_name, idx, llm=None, src=None):
    """Build a canonical question dict from a parsed raw item.
    Returns (question_or_None, needs_translation_bool).

    Language handling:
      * Telugu-native page -> kept verbatim (q_te == q_en), no LLM;
      * Hindi-medium page  -> LLM renders English + Telugu (else parked);
      * English page       -> whole-MCQ exam-grade translation (translate_mcq),
                              falling back to per-string translation.
    `src` (registry entry) pins the channel when its exam tag is unambiguous.
    """
    from .translator import translate, translate_mcq
    from .content import forbidden_script as _forbidden
    channel = (channel_for_source(src) if src else None) or \
        infer_channel(raw.get("title", ""), raw["q_en"])
    topic = infer_topic(raw.get("title", ""), raw["q_en"])
    q = {
        "id": _id_for(idx),
        "channel": channel,
        "topic": topic,
        "q_en": raw["q_en"],
        "q_te": "",
        "options_en": raw["options_en"],
        "options_te": [],
        "answer_index": raw["answer_index"],
        "explanation_en": raw.get("explanation_en", ""),
        "note": "",
        "source": "scraped",
        "bank": "pdf" if str(raw.get("url", "")).startswith("file://") else "scraped",
        "provenance": f"{source_name} :: {raw.get('url','')}",
        "collected_on": datetime.now(config.IST).strftime("%Y-%m-%d"),
    }
    # Telugu-native source page (e.g. GKToday Telugu CA MCQs): the stem and
    # options are already Telugu — keep them as both EN and TE (no LLM).
    from .content import has_telugu as _has_te
    if _has_te(raw["q_en"]):
        q["q_te"] = raw["q_en"]
        q["options_te"] = [str(o) for o in raw["options_en"]]
        q["explanation_te"] = raw.get("explanation_en", "")
        errs = validate_question(q)
        return (q, False) if not errs else (None, False)
    # Hindi-medium source: needs EN + TE from the LLM, else park it.
    blob = raw["q_en"] + " " + " ".join(map(str, raw["options_en"]))
    if _forbidden(blob) == "Devanagari/Hindi":
        tx = translate_mcq(raw["q_en"], raw["options_en"],
                           raw.get("explanation_en", ""), llm, source_lang="hi")
        if not tx:
            return None, True
        q.update({"q_en": tx["q_en"], "q_te": tx["q_te"],
                  "options_en": tx["options_en"], "options_te": tx["options_te"],
                  "explanation_te": tx["explanation_te"]})
        q["explanation_en"] = ""          # Hindi explanation is not shown
        errs = validate_question(q)
        return (q, False) if not errs else (None, False)
    if _forbidden(blob):
        return None, False                # other non-Telugu Indic scripts: skip
    # English source: exam-grade whole-MCQ translation first
    worded_q = re.search(r"[a-z]{3,}", raw["q_en"]) is not None
    if worded_q:
        tx = translate_mcq(raw["q_en"], raw["options_en"],
                           raw.get("explanation_en", ""), llm)
        if tx:
            q.update({"q_te": tx["q_te"], "options_te": tx["options_te"],
                      "explanation_te": tx["explanation_te"]})
            errs = validate_question(q)
            if not errs:
                return q, False
    # Fallback: per-string translation. Numeric/code options are language-neutral.
    worded_opts = [re.search(r"[a-z]{3,}", str(o)) is not None for o in raw["options_en"]]
    if worded_q:
        q["q_te"] = translate(raw["q_en"], llm)
        if not q["q_te"]:
            q["q_te"] = aptitude_telugu(raw["q_en"])   # offline numeric fallback
    else:
        q["q_te"] = f"⤷ {raw['q_en']}"
    q["options_te"] = [
        (translate(str(o), llm) if wo else str(o))
        for o, wo in zip(raw["options_en"], worded_opts)
    ]
    needs_tx = (worded_q and not q["q_te"]) or any(
        wo and not te for wo, te in zip(worded_opts, q["options_te"]))
    errs = validate_question(q)
    if errs:
        if needs_tx:
            return None, True          # park for later translation
        return None, False             # unusable
    return q, False


# ---------------------------------------------------------------------------
# Collection driver
# ---------------------------------------------------------------------------
def _sources():
    """Sources to collect from — central registry first, built-ins as fallback."""
    srcs = registry_sources()
    if srcs:
        return srcs
    return [dict(s) for s in DEFAULT_SOURCES if s.get("enabled", True)]


def collect_daily(dry=False, llm=None, max_questions=MAX_QUESTIONS_PER_RUN,
                  fixture=None, depth=1.0, only=None):
    """
    Collect fresh exam questions from all enabled sources.
    fixture=(html, title, url) -> parse local content offline (tests/demo).
    depth  -> multiplies every source's max_links / max_pages (backfill uses
              4-6x so a 3-month archive is walked in a few nights).
    only   -> optional substring filter on source names.
    Returns a stats dict. Never raises.
    """
    from .translator import _llm_available
    if llm is None and _llm_available():
        from .llm import LLM
        llm = LLM()

    bank = load_json(SCRAPED_BANK, {"questions": []})
    accepted = bank.get("questions", [])
    pending = load_json(PENDING, {"questions": []}).get("questions", [])

    existing_sigs = {q_signature(q) for q in accepted}
    # stable fingerprints from previously scraped questions (cross-run dedup)
    existing_fps = {q.get("_fp") for q in accepted if q.get("_fp")}
    for p in load_json(PENDING, {"questions": []}).get("questions", []):
        existing_fps.add(p.get("_fp"))
    # also never duplicate the canonical bank or anything already shown
    try:
        from .question_bank import load_bank
        from .store import load_json as _lj
        for q in load_bank():
            existing_sigs.add(q_signature(q))
            if q.get("_fp"):
                existing_fps.add(q["_fp"])
        shown = _lj(config.DATA / "shown_signatures.json", {"sigs": []})
        existing_sigs |= set(shown.get("sigs", []))
    except Exception:
        pass

    stats = {"sources": 0, "articles": 0, "parsed": 0, "accepted": 0,
             "duplicates": 0, "rejected": 0, "parked": 0, "per_source": {}}
    next_id = max([int(q["id"][1:]) for q in accepted if q.get("id", "").startswith("S")]
                  + [0]) + 1
    seen_urls = load_seen_urls() if not fixture else set()

    jobs = []  # (source_dict, title, url, html)
    if fixture:
        fhtml, ftitle, furl = fixture
        jobs.append(({"name": "fixture", "adapter": None}, ftitle, furl, fhtml))
    else:
        for src in _sources():
            name = src["name"]
            if only and only.lower() not in name.lower():
                continue
            stats["sources"] += 1
            stats["per_source"][name] = {"articles": 0, "kept": 0}
            try:
                if src.get("type") == "index":
                    # Deep crawl: the section page may itself contain MCQs AND
                    # links to per-topic pages; queue NEW links only. Paginated
                    # topic pages (page_re + max_pages) are crawled too.
                    page = http_get(src["url"])
                    if not page:
                        record_health(name, False, "index page fetch failed")
                        continue
                    record_health(name, True)
                    jobs.append((src, name, src["url"], page))
                    self_url = src["url"].split("#")[0].rstrip("/")
                    seen_urls.add(self_url)
                    links = extract_links(page, src["url"],
                                          src.get("link_re", r"(?!)"))
                    limit = max(1, int(int(src.get("max_links", MAX_LINKS_PER_INDEX)) * depth))
                    added = 0
                    page_re = src.get("page_re")
                    max_pages = int(int(src.get("max_pages", MAX_PAGES_PER_INDEX)) * depth)
                    # previous-paper PDFs linked from the index (Eenadu
                    # Pratibha / official boards) -> download into the inbox
                    if src.get("pdf_re") and not dry:
                        for lk in extract_links(page, src["url"], src["pdf_re"]):
                            if lk["link"] in seen_urls:
                                continue
                            if _harvest_pdf(lk["link"], lk["title"]):
                                seen_urls.add(lk["link"])
                                stats["per_source"][name]["pdfs"] = \
                                    stats["per_source"][name].get("pdfs", 0) + 1
                    suffix = src.get("link_suffix", "")   # e.g. "start/"
                    p_added = 0
                    sub_pages = []       # pages whose own pagination we follow
                    for lk in links:
                        if added >= limit:
                            break
                        target = lk["link"]
                        if suffix and not target.endswith(suffix):
                            target = target.rstrip("/") + "/" + suffix
                        if target in seen_urls or \
                                target.split("#")[0].rstrip("/") == self_url:
                            continue
                        seen_urls.add(target)
                        sub = http_get(target)
                        if sub:
                            jobs.append((src, lk["title"], target, sub))
                            sub_pages.append((target, sub))
                            added += 1
                            stats["articles"] += 1
                            stats["per_source"][name]["articles"] += 1
                    # numbered/query pagination pages (one level deeper) —
                    # discovered on the index page AND on each topic page
                    # (GKToday ?pageno=N, Examveda ?page=N, IndiaBIX /N/).
                    if page_re and max_pages > 0:
                        for base_url, base_html in [(src["url"], page)] + sub_pages:
                            for lk in extract_links(base_html, base_url, page_re):
                                if p_added >= max_pages:
                                    break
                                if lk["link"] in seen_urls:
                                    continue
                                seen_urls.add(lk["link"])
                                sub = http_get(lk["link"])
                                if sub:
                                    jobs.append((src, lk["title"] or "page",
                                                 lk["link"], sub))
                                    p_added += 1
                                    stats["articles"] += 1
                                    stats["per_source"][name]["articles"] += 1
                            if p_added >= max_pages:
                                break
                else:
                    entries = _feed_entries(src["feed"])
                    if not entries:
                        # feed unreachable/empty -> health fail (auto-pause)
                        record_health(name, False,
                                      f"feed returned 0 entries (dead/empty)")
                        continue
                    record_health(name, True, f"{len(entries)} feed entries")
                    arts = quiz_articles_for_source(src, entries=entries)
                    for a in arts:
                        if a["link"] in seen_urls:
                            continue
                        seen_urls.add(a["link"])
                        page = http_get(a["link"])
                        if not page:
                            continue
                        jobs.append((src, a["title"], a["link"], page))
                        stats["articles"] += 1
                        stats["per_source"][name]["articles"] += 1
            except Exception as e:
                print(f"   [collect] {name} discovery error: {e}")
                record_health(name, False, f"discovery error: {str(e)[:120]}")
                continue

    for src, title, url, page in jobs:
        source_name = src["name"] if isinstance(src, dict) else str(src)
        try:
            raws = parse_page(src if isinstance(src, dict) else {},
                              page, title, url)
        except Exception as e:
            print(f"   [collect] parse error {source_name}: {e}")
            continue
        stats["parsed"] += len(raws)
        for raw in raws:
            if stats["accepted"] + stats["parked"] >= max_questions:
                break
            fp = scrape_fingerprint(raw)
            sig = q_signature({
                "channel": infer_channel(title, raw["q_en"]),
                "topic": infer_topic(title, raw["q_en"]),
                "q_en": raw["q_en"], "answer_index": raw["answer_index"]})
            if fp in existing_fps or sig in existing_sigs:
                stats["duplicates"] += 1
                continue
            q, needs_tx = normalize_raw(raw, source_name, next_id, llm=llm,
                                        src=src if isinstance(src, dict) else None)
            if q is None:
                if needs_tx:
                    pending.append({**raw, "_fp": fp, "source_name": source_name,
                                    "provenance": f"{source_name} :: {url}"})
                    existing_fps.add(fp)
                    stats["parked"] += 1
                else:
                    stats["rejected"] += 1
                continue
            existing_sigs.add(sig)
            existing_fps.add(fp)
            q["_fp"] = fp
            accepted.append(q)
            next_id += 1
            stats["accepted"] += 1
            if source_name in stats["per_source"]:
                stats["per_source"][source_name]["kept"] += 1

    if not dry:
        save_json_atomic(SCRAPED_BANK, {"version": "1.0",
                                        "count": len(accepted),
                                        "questions": accepted})
        save_json_atomic(PENDING, {"count": len(pending), "questions": pending})
        if not fixture:
            save_seen_urls(seen_urls)
        if stats["accepted"]:
            try:
                from .question_bank import rebuild_json
                rebuild_json()
            except Exception as e:
                print(f"   [collect] rebuild note: {e}")
    print(f"[collect] {stats}")
    return stats


# ---------------------------------------------------------------------------
# PDF / local-file ingestion — previous-year papers, coaching PDFs, model
# papers. Text is extracted with the best available tool (pdftotext ->
# pypdf -> PyPDF2) and pushed through the SAME parser + validation + no-repeat
# pipeline as web content. Drop files into data/pdf_inbox/ (processed once,
# tracked in collector_seen.json) or run:  python3 -m core.collector --pdf F
# ---------------------------------------------------------------------------
PDF_INBOX = config.DATA / "pdf_inbox"


def pdf_to_text(path) -> str:
    """Extract text from a PDF. Returns '' when no extractor is available."""
    import shutil
    import subprocess
    path = str(path)
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
                                 capture_output=True, timeout=120)
            if out.returncode == 0 and out.stdout:
                return out.stdout.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"   [pdf] pdftotext note: {e}")
    for mod in ("pypdf", "PyPDF2"):
        try:
            lib = __import__(mod)
            reader = lib.PdfReader(path)
            return "\n".join((pg.extract_text() or "") for pg in reader.pages)
        except ImportError:
            continue
        except Exception as e:
            print(f"   [pdf] {mod} note: {e}")
    print("   [pdf] no PDF text extractor found — install poppler-utils "
          "(pdftotext) or `pip install pypdf`")
    return ""


def text_to_lines(text: str):
    """Plain text (PDF dump / pasted paper) -> clean lines for the parser.
    Repairs the two classic PDF artefacts: options glued on one line
    ('(a) 12 (b) 14 (c) 16 (d) 18') and lowercase option labels."""
    lines = []
    for ln in (text or "").splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if not ln:
            continue
        # answer-key rows ("1. (c) 2. (b) 3. (a) ...") must stay intact
        if len(_KEY_PAIR_RE.findall(ln)) >= 3:
            lines.append(ln)
            continue
        # split "(a) x (b) y (c) z (d) w" onto separate lines
        parts = re.split(r"\s(?=[\(\[]?[a-dA-D][\)\]\.]\s)", " " + ln)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) >= 4 and all(re.match(r"^[\(\[]?[a-dA-D][\)\]\.]\s", p)
                                   for p in parts[-4:]):
            lines.extend(parts)
        else:
            lines.append(ln)
    return lines


def ingest_pdf(path, title="", dry=False, llm=None):
    """Parse one PDF / .txt file into the scraped bank. Returns stats."""
    from pathlib import Path as _P
    p = _P(path)
    title = title or p.stem.replace("_", " ").replace("-", " ")
    text = p.read_text(encoding="utf-8", errors="replace") if p.suffix.lower() == ".txt" \
        else pdf_to_text(p)
    if not text.strip():
        return {"accepted": 0, "parsed": 0, "error": "no text extracted"}
    lines = text_to_lines(text)
    # reuse the fixture path: hand the parser pre-split lines
    html_like = "<article>" + "".join(f"<p>{html.escape(l)}</p>" for l in lines) + "</article>"
    return collect_daily(fixture=(html_like, title, f"file://{p.name}"), dry=dry, llm=llm)


def ingest_inbox(dry=False, llm=None):
    """Process every new PDF/TXT in data/pdf_inbox/ exactly once."""
    PDF_INBOX.mkdir(parents=True, exist_ok=True)
    seen = load_seen_urls()
    total = {"files": 0, "accepted": 0, "parsed": 0}
    for f in sorted(PDF_INBOX.glob("*")):
        if f.suffix.lower() not in (".pdf", ".txt"):
            continue
        key = f"file://{f.name}"
        if key in seen:
            continue
        st = ingest_pdf(f, dry=dry, llm=llm)
        total["files"] += 1
        total["accepted"] += st.get("accepted", 0)
        total["parsed"] += st.get("parsed", 0)
        if not dry:
            seen.add(key)
            save_seen_urls(seen)
        print(f"   [pdf] {f.name}: parsed={st.get('parsed', 0)} accepted={st.get('accepted', 0)}")
    return total


MAX_PDF_BYTES = 25 * 1024 * 1024


def _harvest_pdf(url: str, title: str = "") -> bool:
    """Download a previous-paper PDF into data/pdf_inbox/ (once). The inbox
    ingester turns it into questions on the next --inbox / collect run."""
    try:
        PDF_INBOX.mkdir(parents=True, exist_ok=True)
        from urllib.parse import urlparse
        name = os.path.basename(urlparse(url).path) or "paper.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"
        slug = re.sub(r"[^a-z0-9]+", "-", (title or "")[:60].lower()).strip("-")
        dest = PDF_INBOX / (f"{slug}--{name}" if slug else name)
        if dest.exists():
            return True
        _sleep_polite(urlparse(url).netloc)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT * 2) as resp:
            data = resp.read(MAX_PDF_BYTES + 1)
        if len(data) > MAX_PDF_BYTES or not data.startswith(b"%PDF"):
            return False
        dest.write_bytes(data)
        print(f"   [pdf] harvested {dest.name} ({len(data)//1024} KB)")
        return True
    except Exception as e:
        print(f"   [pdf] harvest failed {url}: {e}")
        return False


BACKFILL_STATE = config.DATA / "collector_backfill.json"


def backfill(days: int = 90, depth: float = 5.0, per_run: int = 600,
             dry=False, llm=None, only=None):
    """Historical sweep: walk every live source `depth`x deeper than a daily
    run and ingest harvested PDFs. Resumable — progress (pages already seen)
    lives in collector_seen.json; this store tracks the campaign itself so
    the nightly scheduler keeps going until the target window is covered.
    """
    st = load_json(BACKFILL_STATE, {"started": None, "runs": 0, "accepted": 0,
                                    "days": days, "done": False})
    if st.get("done") and st.get("days", 0) >= days:
        print("[backfill] campaign already complete")
        return st
    if not st.get("started"):
        st["started"] = datetime.now(config.IST).strftime("%Y-%m-%d")
    stats = collect_daily(dry=dry, llm=llm, max_questions=per_run,
                          depth=depth, only=only)
    inbox = ingest_inbox(dry=dry, llm=llm)
    st["runs"] = st.get("runs", 0) + 1
    st["accepted"] = st.get("accepted", 0) + stats.get("accepted", 0) + inbox.get("accepted", 0)
    st["last_run"] = datetime.now(config.IST).strftime("%Y-%m-%d %H:%M")
    st["last_stats"] = {"web": stats.get("accepted", 0), "pdf": inbox.get("accepted", 0),
                        "articles": stats.get("articles", 0)}
    # a sweep that finds no new articles anywhere has exhausted the archives
    if stats.get("articles", 0) == 0 and inbox.get("files", 0) == 0:
        st["idle_runs"] = st.get("idle_runs", 0) + 1
        if st["idle_runs"] >= 3:
            st["done"] = True
    else:
        st["idle_runs"] = 0
    if not dry:
        save_json_atomic(BACKFILL_STATE, st)
    print(f"[backfill] run {st['runs']}: +{st['last_stats']} total={st['accepted']} done={st['done']}")
    return st


def retry_pending(dry=False, llm=None):
    """Translate parked worded questions now that a key may be available."""
    pending = load_json(PENDING, {"questions": []}).get("questions", [])
    if not pending:
        return {"retried": 0, "accepted": 0}
    from .llm import LLM
    llm = llm or LLM()
    if not llm.available():
        print("[collect] no LLM key yet — pending questions stay parked.")
        return {"retried": len(pending), "accepted": 0}
    bank = load_json(SCRAPED_BANK, {"questions": []})
    accepted = bank.get("questions", [])
    existing = {q_signature(q) for q in accepted}
    next_id = max([int(q["id"][1:]) for q in accepted
                   if q.get("id", "").startswith("S")] + [0]) + 1
    still = []
    moved = 0
    done_fps = {q.get("_fp") for q in accepted if q.get("_fp")}
    for raw in pending:
        fp = raw.get("_fp") or scrape_fingerprint(raw)
        if fp in done_fps:
            continue
        q, needs_tx = normalize_raw(
            {k: raw[k] for k in ("q_en", "options_en", "answer_index",
                                "explanation_en", "title", "url")
             if k in raw}, raw.get("source_name", "scraped"), next_id, llm=llm)
        if q:
            q["_fp"] = fp
            accepted.append(q)
            done_fps.add(fp)
            next_id += 1
            moved += 1
        elif needs_tx:
            still.append(raw)
    if not dry:
        save_json_atomic(SCRAPED_BANK, {"version": "1.0", "count": len(accepted),
                                        "questions": accepted})
        save_json_atomic(PENDING, {"count": len(still), "questions": still})
        if moved:
            from .question_bank import rebuild_json
            rebuild_json()
    print(f"[collect] retry-pending: {moved} translated & accepted, "
          f"{len(still)} still parked")
    return {"retried": len(pending), "accepted": moved}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="StudentUp exam-content collector")
    ap.add_argument("--collect", action="store_true", help="live collection run")
    ap.add_argument("--retry-pending", action="store_true")
    ap.add_argument("--dry", action="store_true", help="do not write files")
    ap.add_argument("--fixture", help="parse a local HTML quiz file offline")
    ap.add_argument("--title", default="Banking Current Affairs Quiz 2026")
    ap.add_argument("--pdf", help="ingest one PDF/TXT question paper")
    ap.add_argument("--inbox", action="store_true",
                    help="ingest every new file in data/pdf_inbox/")
    ap.add_argument("--backfill", action="store_true",
                    help="deep historical sweep (3-month archive campaign)")
    ap.add_argument("--depth", type=float, default=5.0,
                    help="backfill depth multiplier for links/pages")
    ap.add_argument("--only", help="restrict to sources whose name contains this")
    args = ap.parse_args()
    if args.backfill:
        print(backfill(depth=args.depth, dry=args.dry, only=args.only))
        raise SystemExit(0)
    if args.pdf:
        print(ingest_pdf(args.pdf, title=args.title, dry=args.dry))
    elif args.inbox:
        print(ingest_inbox(dry=args.dry))
    elif args.fixture:
        htmltxt = open(args.fixture, encoding="utf-8").read()
        print(collect_daily(fixture=(htmltxt, args.title, "file://" + args.fixture),
                            dry=args.dry))
    elif args.retry_pending:
        print(retry_pending(dry=args.dry))
    else:
        print(collect_daily(dry=args.dry))
