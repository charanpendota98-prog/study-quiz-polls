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
"""
from __future__ import annotations

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

SCRAPED_BANK = config.DATA / "scraped_bank.json"
PENDING = config.DATA / "scraped_pending.json"
SEEN_URLS = config.DATA / "collector_seen.json"

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

    # ---- More central / all-exam daily quiz feeds ---------------------------------
    {"name": "Adda247 Quiz", "enabled": True, "type": "rss", "exam": "all",
     "feed": "https://www.adda247.com/feed",
     "title_must": r"quiz|questions?|practice set|mcq|reasoning|quant",
     "title_not": _QUIZ_NOT},
    {"name": "JagranJosh Quiz", "enabled": True, "type": "rss", "exam": "all",
     "feed": "https://www.jagranjosh.com/rss/josh/feed.xml",
     "title_must": r"quiz|questions?|mcq|general knowledge|gk|current affairs",
     "title_not": _QUIZ_NOT},
    {"name": "FreshersNow Quiz", "enabled": True, "type": "rss", "exam": "all",
     "feed": "https://www.freshersnow.com/feed",
     "title_must": r"quiz|questions?|mcq|practice|previous papers?",
     "title_not": _QUIZ_NOT},
    {"name": "Aglasem Quiz", "enabled": True, "type": "rss", "exam": "ssc-upsc",
     "feed": "https://aglasem.com/feed",
     "title_must": r"quiz|questions?|mcq|practice|previous year|model",
     "title_not": _QUIZ_NOT},
    {"name": "CompetitionExam", "enabled": True, "type": "rss", "exam": "ssc-railway",
     "feed": "https://www.competitionexam.com/feeds/posts/default",
     "title_must": r"quiz|questions?|mcq|practice|gk|general knowledge",
     "title_not": _QUIZ_NOT},
    {"name": "Study2Online", "enabled": True, "type": "rss", "exam": "all",
     "feed": "https://www.study2online.com/feed",
     "title_must": r"quiz|questions?|mcq|practice|reasoning|aptitude",
     "title_not": _QUIZ_NOT},

    # ---- Deep static MCQ banks (HTML index/section pages, dedicated adapter) ------
    {"name": "Examveda Arithmetic", "enabled": True, "type": "index",
     "exam": "banking-ssc-railway", "adapter": "examveda",
     "url": "https://www.examveda.com/arithmetic-ability/",
     "link_re": r"^https://www\.examveda\.com/[a-z0-9\-]+/?$",
     "max_links": 3},
    {"name": "Examveda Reasoning", "enabled": True, "type": "index",
     "exam": "all", "adapter": "examveda",
     "url": "https://www.examveda.com/verbal-reasoning/",
     "link_re": r"^https://www\.examveda\.com/[a-z0-9\-]+/?$",
     "max_links": 3},
    {"name": "Examveda General Knowledge", "enabled": True, "type": "index",
     "exam": "ssc-upsc-railway", "adapter": "examveda",
     "url": "https://www.examveda.com/general-knowledge/",
     "link_re": r"^https://www\.examveda\.com/[a-z0-9\-]+/?$",
     "max_links": 3},

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
MAX_ARTICLES_PER_SOURCE = 2
MAX_LINKS_PER_INDEX = 3
MAX_QUESTIONS_PER_RUN = 160
POLITE_DELAY_SEC = 2.0          # min seconds between hits on the same host
FETCH_TIMEOUT = 20

# ---------------------------------------------------------------------------
# Channel / topic inference
# ---------------------------------------------------------------------------
_CHANNEL_KEYWORDS = [
    ("TSPSC", r"tspsc|telangana"),
    ("APPSC", r"appsc|andhra pradesh|ap police"),
    ("RAILWAY", r"railway|rrb\b|ntpc|group[\s-]?d|alp|je[e]? exam"),
    ("POLICE", r"police|constable|sub[\s-]?inspector|\bsi\b|dsp"),
    ("DEFENCE", r"\bnda\b|cds|defen[cs]e|agniveer|army|navy|air[\s-]?force|capf"),
    ("BANKING", r"bank|ibps|sbi|rrb po|rrb clerk|po exam|clerk|insurance|lic|niacl|rbi assistant"),
    ("CURRENT", r"current affairs|general awareness|static gk|gk quiz|upsc|ssc|polity|history|geograph|econom|science|biology|physics|chemistry"),
]

_TOPIC_KEYWORDS = [
    ("percentage", r"percent|percentage|%"),
    ("ratio", r"\bratio\b|proportion"),
    ("simple interest", r"simple interest|\bsi\b"),
    ("compound interest", r"compound interest|\bci\b"),
    ("profit & loss", r"profit|loss|discount|marked price"),
    ("average", r"average"),
    ("time-work", r"work.*days|days.*work|pipes?|cist ern|time and work"),
    ("time-distance", r"speed|distance|train|boat|stream"),
    ("number series", r"series|sequence|missing number|next term"),
    ("number system", r"number system|hcf|lcm|divisib|remainder"),
    ("coding-decoding", r"cod(e|ing)|decod|cipher"),
    ("blood relation", r"blood relation|related to|father|mother|daughter|son of"),
    ("direction", r"direction|north|south|east|west|facing"),
    ("syllogism", r"syllogis"),
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


def http_get(url: str, timeout=FETCH_TIMEOUT, retries=2, respect_robots=True):
    """GET with browser headers, backoff, robots check. Returns text or None."""
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
QSTART_RE = re.compile(r"^(?:q(?:uestion)?\.?\s*)?(\d{1,3})[\)\.:\-]\s*(.+)$", re.I)
OPT_RE = re.compile(r"^[\(\[]?([A-Da-d])[\)\].:\-]\s+(.+)$")
OPT_INLINE_RE = re.compile(r"(?:^|\s)[\(\[]?([A-Da-d])[\)\].:\-]\s+")
ANS_RE = re.compile(
    r"(?:correct\s+answer|correct option|answer|ans)\b[^A-Da-d1-4]{0,15}"
    r"([A-Da-d]|[1-4])(?:[\)\].]|\b)", re.I)
EXPL_RE = re.compile(r"^(?:explanation|solution|sol|exp)[\.:\-]\s*(.+)$", re.I)
_LABELS = "ABCD"


def _inline_options(rest: str):
    """'question ... A) x  B) y  C) z  D) w' -> (question, [opts]) or None."""
    marks = list(OPT_INLINE_RE.finditer(rest))
    labels = [m.group(1).upper() for m in marks]
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


def parse_quiz_lines(lines, article_title="", url=""):
    """Tolerant WordPress-quiz extractor. Returns list of raw question dicts."""
    raw_qs = []
    cur = None

    def finalize():
        nonlocal cur
        if not cur:
            return
        opts = cur["opts"]
        if (len(opts) == 4 and cur["ans"] is not None
                and len(cur["q"]) >= 8 and len(cur["q"]) <= 300
                and all(0 < len(o) <= 90 for o in opts)
                and len({o.lower() for o in opts}) == 4):
            blocked, _ = is_blocked(cur["q"] + " " + " ".join(opts))
            if not blocked:
                raw_qs.append({
                    "q_en": cur["q"], "options_en": opts,
                    "answer_index": cur["ans"],
                    "explanation_en": cur["expl"][:280],
                    "title": article_title, "url": url,
                })
        cur = None

    for line in lines:
        if len(line) > 400:
            line = line[:400]
        mo = OPT_RE.match(line)
        mq = QSTART_RE.match(line)

        # Answer / explanation lines (may appear on their own)
        ma = ANS_RE.search(line)
        mex = EXPL_RE.match(line)

        if mq and not mo:
            rest = mq.group(2).strip()
            inline = _inline_options(rest)
            if inline:
                # whole question + 4 options on one line
                finalize()
                qtext, opts = inline
                cur = {"q": qtext, "opts": opts[:], "ans": None,
                       "expl": "", "labels": ["A", "B", "C", "D"]}
                if ma:
                    cur["ans"] = _ans_index(ma.group(1))
                continue
            # otherwise it is a new question stem
            finalize()
            cur = {"q": rest, "opts": [], "ans": None, "expl": "",
                   "labels": []}
            if ma:
                cur["ans"] = _ans_index(ma.group(1))
            continue

        if mo and cur is not None and len(cur["opts"]) < 4:
            label = mo.group(1).upper()
            val = mo.group(2).strip()
            if label not in cur["labels"] and val:
                cur["labels"].append(label)
                cur["opts"].append(val)
            if ma and cur["ans"] is None:
                cur["ans"] = _ans_index(ma.group(1))
            continue

        if cur is not None and ma and cur["ans"] is None:
            cur["ans"] = _ans_index(ma.group(1))
        if cur is not None and mex:
            cur["expl"] = mex.group(1)
        # explanation sometimes follows answer marker on the same/next lines
        if cur is not None and not mex and cur["ans"] is not None and not cur["expl"]:
            low = line.lower()
            if low.startswith(("explanation", "solution", "sol:")):
                cur["expl"] = re.sub(r"^(?:explanation|solution|sol)[:\.\-]\s*",
                                     "", line, flags=re.I)

    finalize()
    return raw_qs


def _ans_index(token: str):
    t = token.strip().upper()
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
                        "link": link})
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for e in root.findall(".//a:entry", ns):
        title = e.findtext("a:title", "", ns)
        link_el = e.find("a:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        if title and link:
            out.append({"title": html.unescape(re.sub(r"\s+", " ", title)).strip(),
                        "link": link})
    return out


def quiz_articles_for_source(src):
    """Return [{title, link}] quiz articles for one configured RSS source."""
    entries = _feed_entries(src["feed"])
    must = re.compile(src.get("title_must", r"quiz|questions|mcq"), re.I)
    notp = re.compile(src.get("title_not", r"(?!)"), re.I)
    picked = []
    for e in entries:
        t = e["title"]
        if must.search(t) and not notp.search(t):
            picked.append(e)
        if len(picked) >= MAX_ARTICLES_PER_SOURCE:
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


# ---------------------------------------------------------------------------
# Answer-anchored adapter for UNNUMBERED MCQ banks (Examveda-style).
# The generic parser needs a "1." question marker; these pages only mark the
# OPTIONS (A. B. C. D.) and the ANSWER, so we split on answer markers and walk
# back to recover the question stem. Very tolerant, fails safe (returns []).
# ---------------------------------------------------------------------------
_ANCHOR_ANS_RE = re.compile(
    r"Answer\s*:?\s*(?:Option\s*)?([A-D])\b", re.I)
_ANCHOR_OPT_RE = re.compile(r"^\s*[\(\[]?([A-D])[\)\].:\-]\s+(.+)$")


def parse_answer_anchored(page_html, article_title="", url="",
                          stem_max=300):
    """Extract MCQs from HTML where questions are not numbered.

    For every 'Answer: Option X' marker we take the preceding window, find the
    last 4 A-D option lines and treat the longest suitable line before them as
    the question stem. Explanation is taken from the following block when
    present.
    """
    # Split the visible content into lines (script/style already ignored by
    # our article extractor via html_to_lines fallback below).
    lines = html_to_lines(page_html)
    raws = []
    n = len(lines)
    for i, ln in enumerate(lines):
        m = _ANCHOR_ANS_RE.search(ln)
        if not m:
            continue
        # walk back to collect options
        opts = {}          # label -> text
        opt_idx = []       # line indices of options
        for j in range(i - 1, max(-1, i - 12), -1):
            mo = _ANCHOR_OPT_RE.match(lines[j])
            if mo:
                lab = mo.group(1).upper()
                if lab not in opts and 0 < len(mo.group(2).strip()) <= 90:
                    opts[lab] = mo.group(2).strip()
                    opt_idx.append(j)
            elif len(opts) >= 4:
                break
        if len(opts) < 4:
            continue
        ordered = [opts.get(k) for k in "ABCD"]
        if not all(ordered) or len({o.lower() for o in ordered}) < 4:
            continue
        # stem: scan lines before the first option, pick the last long line
        # that is not an answer/option/header line.
        first_opt = min(opt_idx)
        stem = ""
        for j in range(first_opt - 1, max(-1, first_opt - 8), -1):
            cand = lines[j].strip()
            cl = cand.lower()
            if len(cand) < 12 or len(cand) > stem_max:
                continue
            if cl.startswith(("answer", "option", "solution", "explanation",
                              "explanation:", "home", "copyright")):
                continue
            if _ANCHOR_OPT_RE.match(cand) or _ANCHOR_ANS_RE.search(cand):
                continue
            # strip a leading question number if present
            cand = re.sub(r"^\d{1,3}[\)\.:\-]\s*", "", cand)
            stem = cand
            break
        if not stem:
            continue
        # explanation: next 1-3 lines after the answer marker
        expl = ""
        for j in range(i + 1, min(n, i + 4)):
            cl = lines[j].lower()
            if cl.startswith(("solution", "explanation", "explanation:")):
                expl = re.sub(r"^(?:solution|explanation)\s*:?\s*", "",
                              lines[j], flags=re.I)[:280]
                break
        ans = _ans_index(m.group(1).upper())
        blocked, _ = is_blocked(stem + " " + " ".join(ordered))
        if not blocked and ans is not None:
            raws.append({"q_en": stem, "options_en": ordered,
                         "answer_index": ans, "explanation_en": expl,
                         "title": article_title, "url": url})
    return raws


def parse_examveda(page_html, article_title="", url=""):
    return parse_answer_anchored(page_html, article_title, url)


ADAPTERS["examveda"] = parse_examveda


def parse_page(src, page_html, title, url):
    """Dispatch to the source's dedicated adapter, else the generic parser.
    Every path fails safe: if a dedicated adapter returns nothing, fall back to
    the generic WordPress parser so a source is never silently missed."""
    adapter = src.get("adapter")
    raws = []
    if adapter and adapter in ADAPTERS:
        try:
            raws = ADAPTERS[adapter](page_html, title, url)
        except Exception as e:
            print(f"   [collect] adapter {adapter} error: {e}")
            raws = []
    if not raws:
        lines = html_to_lines(page_html)
        raws = parse_quiz_lines(lines, article_title=title, url=url)
    return raws


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


def normalize_raw(raw, source_name, idx, llm=None):
    """Build a canonical question dict from a parsed raw item.
    Returns (question_or_None, needs_translation_bool)."""
    from .translator import translate
    channel = infer_channel(raw.get("title", ""), raw["q_en"])
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
        "bank": "scraped",
        "provenance": f"{source_name} :: {raw.get('url','')}",
        "collected_on": datetime.now(config.IST).strftime("%Y-%m-%d"),
    }
    # Translate worded content. Numeric/code options are language-neutral.
    worded_q = re.search(r"[a-z]{3,}", raw["q_en"]) is not None
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
    srcs = [dict(s) for s in DEFAULT_SOURCES if s.get("enabled", True)]
    override = load_json(config.DATA / "collector_sources.json", {"sources": []})
    for s in override.get("sources", []):
        if s.get("enabled", True):
            srcs.append(s)
    return srcs


def collect_daily(dry=False, llm=None, max_questions=MAX_QUESTIONS_PER_RUN,
                  fixture=None):
    """
    Collect fresh exam questions from all enabled sources.
    fixture=(html, title, url) -> parse local content offline (tests/demo).
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
            stats["sources"] += 1
            stats["per_source"][src["name"]] = {"articles": 0, "kept": 0}
            try:
                if src.get("type") == "index":
                    # Deep crawl: the section page may itself contain MCQs AND
                    # links to per-topic pages; queue NEW links only.
                    page = http_get(src["url"])
                    if not page:
                        continue
                    jobs.append((src, src["name"], src["url"], page))
                    self_url = src["url"].split("#")[0].rstrip("/")
                    seen_urls.add(self_url)
                    links = extract_links(page, src["url"],
                                          src.get("link_re", r"(?!)"))
                    limit = src.get("max_links", MAX_LINKS_PER_INDEX)
                    added = 0
                    for lk in links:
                        if added >= limit:
                            break
                        if lk["link"] in seen_urls or \
                                lk["link"].split("#")[0].rstrip("/") == self_url:
                            continue
                        seen_urls.add(lk["link"])
                        sub = http_get(lk["link"])
                        if sub:
                            jobs.append((src, lk["title"], lk["link"], sub))
                            added += 1
                            stats["articles"] += 1
                            stats["per_source"][src["name"]]["articles"] += 1
                else:
                    arts = quiz_articles_for_source(src)
                    for a in arts:
                        if a["link"] in seen_urls:
                            continue
                        seen_urls.add(a["link"])
                        page = http_get(a["link"])
                        if not page:
                            continue
                        jobs.append((src, a["title"], a["link"], page))
                        stats["articles"] += 1
                        stats["per_source"][src["name"]]["articles"] += 1
            except Exception as e:
                print(f"   [collect] {src['name']} discovery error: {e}")
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
            q, needs_tx = normalize_raw(raw, source_name, next_id, llm=llm)
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
    args = ap.parse_args()
    if args.fixture:
        htmltxt = open(args.fixture, encoding="utf-8").read()
        print(collect_daily(fixture=(htmltxt, args.title, "file://" + args.fixture),
                            dry=args.dry))
    elif args.retry_pending:
        print(retry_pending(dry=args.dry))
    else:
        print(collect_daily(dry=args.dry))
