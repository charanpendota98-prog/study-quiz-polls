#!/usr/bin/env python3
"""
STUDENTUP — JOBS DESK (private channel only)

Structured job-notification pipeline for the PRIVATE jobs channel:

  sources (verified 09 Sep 2026)
    * FreeJobAlert latest-notifications table  — every board (Banks/SSC/UPSC/
      Railways/Defence/PSU + Telangana + Andhra Pradesh sections), with
      post date, board, post name + vacancies, qualification, last date and
      the article URL; the article gives apply/notification links + salary.
    * FreeJobAlert RSS                          — walk-ins, results, admit
      cards, exam dates the moment they are published.
    * Eenadu Pratibha (Telugu) latest notifications, walk-ins, private jobs,
      freshers — native Telugu title + eligibility + last date + PDF/official.
    * SarkariResult RSS                         — central forms/results/keys.
    * Sakshi Education jobs (Telugu) list page.

  filter
    * TS/AP + Central/All-India + PSU/bank/railway/defence + private/IT/
      walk-in/outsourcing.  Other-state-only notifications are dropped
      (a notification that mentions Telangana/AP or is All-India stays).

  post
    * One card per job (never a list dump), Telugu + English, with the
      exact official/apply/PDF links and the key facts
      (posts, vacancies, qualification, age, fee, salary, last date, mode).
    * Dedup by canonical URL + title similarity (TTL 7 days), so nothing is
      repeated; "closing soon" (<=3 days) cards are re-posted once as ⏳.

Nothing here ever reaches the public quiz channels.
"""
from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import config
from .store import load_json, save_json_atomic, normalize, similarity

STATE = config.DATA / "jobs_state.json"          # posted URLs + ttl
FALLBACK = config.DATA / "jobs_curated.json"

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
JOB_SOURCES = [
    # name, kind, url, lang, tags
    ("FreeJobAlert Latest", "fja_table",
     "https://www.freejobalert.com/latest-notifications/", "en", "govt"),
    ("FreeJobAlert RSS", "rss", "https://www.freejobalert.com/feed", "en", "govt"),
    ("Eenadu Pratibha Govt Jobs (TE)", "eenadu_list",
     "https://pratibha.eenadu.net/notifications/latestnotifications/government-jobs/2-8-27", "te", "govt"),
    ("Eenadu Pratibha Walk-ins (TE)", "eenadu_list",
     "https://pratibha.eenadu.net/notifications/latestnotifications/walk-ins/2-8-32", "te", "walkin"),
    ("Eenadu Pratibha Private Jobs (TE)", "eenadu_list",
     "https://pratibha.eenadu.net/notifications/latestnotifications/private-jobs/2-8-29", "te", "private"),
    ("Eenadu Pratibha Freshers (TE)", "eenadu_list",
     "https://pratibha.eenadu.net/notifications/latestnotifications/Freshers/2-8-30", "te", "freshers"),
    ("Eenadu Pratibha Scholarships (TE)", "eenadu_list",
     "https://pratibha.eenadu.net/notifications/latestnotifications/scholorships/2-8-31", "te", "scholarship"),
    ("SarkariResult RSS", "rss", "https://www.sarkariresult.com/feed/", "en", "govt"),
    ("Sakshi Education Jobs (TE)", "sakshi_list",
     "https://education.sakshi.com/jobs/education-news", "te", "govt"),
]

# ---------------------------------------------------------------------------
# Relevance: TS/AP + central + PSU/bank/rail/defence + private/IT/walk-in
# ---------------------------------------------------------------------------
_TSAP = re.compile(
    r"telangana|andhra|\btg\b|\bts\b|\bap\b|tspsc|tgpsc|appsc|tslprb|apspsc|hyderabad|"
    r"secunderabad|warangal|karimnagar|nizamabad|khammam|nalgonda|mahabubnagar|"
    r"vijayawada|visakhapatnam|vizag|guntur|tirupati|nellore|kurnool|kadapa|anantapur|"
    r"rajahmundry|kakinada|ongole|eluru|srikakulam|vizianagaram|chittoor|"
    r"తెలంగాణ|ఆంధ్ర|హైదరాబాద్|సికింద్రాబాద్|వరంగల్|కరీంనగర్|నిజామాబాద్|ఖమ్మం|నల్గొండ|"
    r"మహబూబ్.?నగర్|ఆదిలాబాద్|మెదక్|సంగారెడ్డి|రంగారెడ్డి|విజయవాడ|విశాఖ|గుంటూరు|తిరుపతి|"
    r"నెల్లూరు|కర్నూలు|కడప|అనంతపురం|రాజమండ్రి|కాకినాడ|ఒంగోలు|ఏలూరు|శ్రీకాకుళం|విజయనగరం|"
    r"చిత్తూరు|బాపట్ల|టీఎస్‌?పీఎస్సీ|టీజీపీఎస్సీ|ఏపీపీఎస్సీ|ఉస్మానియా|కాకతీయ|సింగరేణి|"
    r"ఆర్టీసీ|ఎన్‌?జీఆర్‌?ఐ|ఐఐసీటీ|సీసీఎంబీ|డీఆర్‌?డీఎల్|ఎన్‌?ఐటీ వరంగల్|ఐఐటీ హైదరాబాద్|"
    r"ఐఐఎస్‌?ఈఆర్ తిరుపతి|బీడీఎల్|ఈసీఐఎల్|మిధాని|డీఎల్‌?ఎస్‌?ఏ|జిల్లా కోర్టు|హైకోర్టు|"
    r"tsgenco|tstransco|aptransco|apgenco|tsspdcl|tsnpdcl|apspdcl|apepdcl|singareni|"
    r"tsrtc|tgsrtc|apsrtc|osmania|kakatiya|andhra university|ngri|iict|ccmb|drdl|"
    r"nit warangal|iit hyderabad|iiit hyderabad|iiser tirupati|isb|bdl|becil|midhani|"
    r"ecil|hal hyderabad|dlsa|district court|high court", re.I)
_CENTRAL = re.compile(
    r"\bssc\b|\bupsc\b|\bibps\b|\bsbi\b|\brbi\b|\brrb\b|railway|\bnda\b|\bcds\b|agniveer|"
    r"army|navy|air ?force|\bcapf\b|\bbsf\b|\bcrpf\b|\bcisf\b|\bitbp\b|\bssb\b|coast guard|"
    r"india post|\bgds\b|\blic\b|\bnabard\b|\bsebi\b|\bepfo\b|\besic\b|\bisro\b|\bdrdo\b|"
    r"\bbarc\b|\bnpcil\b|\bntpc\b|\bongc\b|\bgail\b|\biocl\b|\bbpcl\b|\bhpcl\b|\bbhel\b|"
    r"\bsail\b|\bcoal india\b|powergrid|\bnhpc\b|\bnlc\b|\bbel\b|\bhal\b|\bbdl\b|\bmidhani\b|"
    r"\baiims\b|\bpgimer\b|\bjipmer\b|\bnit\b|\biit\b|\biiit\b|\biim\b|\bugc\b|\bnta\b|\bcsir\b|"
    r"\bicar\b|\bdst\b|\bcdac\b|c-dac|\bnielit\b|\bbecil\b|\becil\b|bank of|canara|union bank|"
    r"indian bank|central bank|pnb|punjab national|bank of baroda|idbi|nainital bank|"
    r"all india|central govt|government of india|ministry|supreme court|\bnhai\b|\bnhm\b|"
    r"\bipc\b|\bkvs\b|\bnvs\b|\bctet\b|\bugc net\b|\bgate\b|\buiic\b|\bniacl\b|\boicl\b|"
    r"\bnew india\b|\bexim\b|\bnabfid\b|\bsidbi\b|\bcbi\b|\bib\b|\bacio\b|\bmha\b|\bnsg\b|"
    r"pan[- ]india|walk-?in|walkin|apprentice|apprenticeship|internship|fresher|"
    r"ఎస్‌?ఎస్‌?సీ|యూపీఎస్సీ|ఐబీపీఎస్|ఎస్‌?బీఐ|ఆర్‌?బీఐ|ఆర్‌?ఆర్‌?బీ|రైల్వే|ఆర్మీ|నేవీ|"
    r"వాయుసేన|అగ్నివీర్|ఈఎస్‌?ఐసీ|ఈపీఎఫ్‌?ఓ|ఇస్రో|డీఆర్‌?డీఓ|ఎన్‌?టీపీసీ|ఓఎన్‌?జీసీ|"
    r"భెల్|సెయిల్|కోల్ ఇండియా|పవర్‌?గ్రిడ్|బీఈఎల్|హెచ్‌?ఏఎల్|ఎయిమ్స్|ఐఐటీ|ఎన్‌?ఐటీ|"
    r"ఐఐఎం|సీఎస్‌?ఐఆర్|ఐసీఏఆర్|సీడ్యాక్|బీఈసీఐఎల్|ప్రసార్ భారతి|ఇండియా పోస్ట్|"
    r"పోస్టల్|ఎల్‌?ఐసీ|నాబార్డ్|బ్యాంక్|కేంద్ర|అఖిల భారత|కేంద్ర ప్రభుత్వ|ప్రభుత్వరంగ|"
    r"అప్రెంటిస్|ఇంటర్న్|ఫ్రెషర్|జేఆర్‌?ఎఫ్|ఫ్యాకల్టీ|ప్రొఫెసర్", re.I)
_OTHER_STATE = re.compile(
    r"\b(karnataka|maharashtra|tamil ?nadu|kerala|punjab|rajasthan|gujarat|madhya ?pradesh|"
    r"chhattisgarh|odisha|bihar|uttar ?pradesh|west ?bengal|assam|goa|himachal|jammu|kashmir|"
    r"ladakh|sikkim|haryana|jharkhand|puducherry|chandigarh|uttarakhand|manipur|meghalaya|"
    r"mizoram|nagaland|tripura|arunachal|andaman|lakshadweep|daman|dadra|delhi)\b|"
    r"\b(upsssc|uppsc|bpsc|mpsc|mppsc|kpsc|tnpsc|opsc|hpsc|hssc|rpsc|rsmssb|gpsc|wbpsc|jpsc|"
    r"ukpsc|uksssc|cgpsc|psssb|ppsc|jkssb|jkpsc|apsc|mpesb|dsssb|bssc|osssc|mahatransco|"
    r"tnusrb|ksp|up police|mp police|bihar police)\b", re.I)
_BLOCK = re.compile(
    r"time ?table|semester|\bresult\b.*(university|college|b\.?a\b|b\.?sc|b\.?ed|m\.?sc|ug|pg)|"
    r"hall ?ticket.*(class 10|class 12|nios|board)|counselling|cutoff.*college|"
    r"admission.*(college|university|school)|\bnios\b|scholarship test|olympiad", re.I)
_ACTION = re.compile(
    r"recruit|vacanc|notification|apply|walk-?in|admit card|hall ticket|result|answer key|"
    r"exam date|last date|posts?|jobs?|openings?|hiring|drive|mela|fresher|trainee|"
    r"intern|apprentice|ఖాళీ|ఉద్యోగ|నోటిఫికేషన్|పోస్టు|"
    r"నియామక|దరఖాస్తు|వాక్|ఇంటర్వ్యూ|ఫలితాలు|హాల్ టికెట్|అడ్మిట్", re.I)
_PRIVATE_IT = re.compile(
    r"\btcs\b|infosys|wipro|\bhcl\b|tech mahindra|cognizant|accenture|capgemini|amazon|"
    r"google|microsoft|deloitte|ibm|oracle|dxc|mphasis|mindtree|ltimindtree|hexaware|"
    r"cyient|virtusa|zensar|software|developer|engineer trainee|\bit jobs?\b|off ?campus|"
    r"campus drive|mega job mela|job mela|rozgar mela|outsourcing|contract basis|"
    r"ఒప్పంద|అవుట్‌సోర్సింగ్|జాబ్ మేళా|ప్రైవేటు", re.I)


def classify(title: str, body: str = "") -> tuple[bool, str]:
    """(keep?, category). Categories: ts-ap / central / psu-bank-rail /
    private-it / walk-in / scholarship / drop."""
    text = f"{title} {body}"
    if _BLOCK.search(title):
        return False, "drop:not-a-job"
    if not _ACTION.search(text):
        return False, "drop:no-action"
    tsap = bool(_TSAP.search(text))
    central = bool(_CENTRAL.search(text))
    other = bool(_OTHER_STATE.search(title))
    if other and not tsap and not central:
        return False, "drop:other-state"
    if re.search(r"walk-?in|వాక్|job mela|జాబ్ మేళా", text, re.I):
        return True, "walk-in"
    if re.search(r"scholarship|fellowship|స్కాలర్|ఫెలోషిప్", text, re.I):
        return True, "scholarship"
    if tsap:
        return True, "ts-ap"
    if _PRIVATE_IT.search(text):
        return True, "private-it"
    if central:
        return True, "central"
    return False, "drop:no-relevance"


CATEGORY_LABEL = {
    "ts-ap": "🟢 TS/AP",
    "central": "🇮🇳 Central / All-India",
    "private-it": "💻 Private / IT / Outsourcing",
    "walk-in": "🚶 Walk-in",
    "scholarship": "🎓 Scholarship / Fellowship",
}


# ---------------------------------------------------------------------------
# Job record
# ---------------------------------------------------------------------------
@dataclass
class Job:
    title: str
    url: str
    source: str
    lang: str = "en"
    category: str = ""
    board: str = ""
    posts: str = ""
    vacancies: str = ""
    qualification: str = ""
    age: str = ""
    fee: str = ""
    salary: str = ""
    last_date: str = ""
    mode: str = ""
    location: str = ""
    apply_url: str = ""
    notification_url: str = ""
    official_url: str = ""
    title_te: str = ""
    posted: str = ""
    extra: dict = field(default_factory=dict)

    def key(self) -> str:
        u = self.url.split("#")[0].split("?")[0].rstrip("/")
        return u.lower()


# ---------------------------------------------------------------------------
# Tiny HTML helpers (stdlib only)
# ---------------------------------------------------------------------------
class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.links = [], []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href:
                self.links.append((href, ""))
        if tag in ("p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "table"):
            self.parts.append("\n")
        if tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        if tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)
            if self.links and not self.links[-1][1]:
                href = self.links[-1][0]
                self.links[-1] = (href, data.strip())


def _text_and_links(page: str):
    p = _Text()
    try:
        p.feed(page)
    except Exception:
        pass
    text = _html.unescape("".join(p.parts))
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.split("\n")]
    return [ln for ln in lines if ln], p.links


_LINK_RE = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)


def _strip(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _html.unescape(s or ""))).strip()


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------
_FJA_ROW = re.compile(
    r"<tr[^>]*>\s*<td[^>]*>(?P<date>[^<]*)</td>\s*<td[^>]*>(?P<board>.*?)</td>\s*"
    r"<td[^>]*>(?P<post>.*?)</td>\s*<td[^>]*>(?P<qual>.*?)</td>\s*<td[^>]*>(?P<advt>.*?)</td>\s*"
    r"<td[^>]*>(?P<last>.*?)</td>\s*<td[^>]*>(?P<more>.*?)</td>\s*</tr>", re.I | re.S)
_FJA_SECTION = re.compile(r'<h4[^>]*>\s*([^<]{2,60}?)\s*</h4>', re.I)


def parse_fja_table(page: str, base="https://www.freejobalert.com/") -> list[Job]:
    """FreeJobAlert /latest-notifications/ — one row per notification, grouped
    under <h4>Section</h4> (Banks, SSC, Telangana, Andhra Pradesh, ...)."""
    out = []
    # walk sections in order so each row knows its board section
    sections = [(m.start(), m.group(1).strip()) for m in _FJA_SECTION.finditer(page)]
    for m in _FJA_ROW.finditer(page):
        sec = ""
        for pos, name in sections:
            if pos < m.start():
                sec = name
        lm = _LINK_RE.search(m.group("more"))
        if not lm:
            continue
        url = urljoin(base, lm.group(1))
        post = _strip(m.group("post"))
        board = _strip(m.group("board"))
        vac = ""
        mv = re.search(r"(\d[\d,]*)\s*Posts?", post, re.I)
        if mv:
            vac = mv.group(1)
        title = f"{board} {post}".strip()
        j = Job(title=title, url=url, source="FreeJobAlert", board=board,
                posts=re.sub(r"\s*[–-]\s*\d[\d,]*\s*Posts?", "", post, flags=re.I).strip(),
                vacancies=vac, qualification=_strip(m.group("qual")),
                last_date=_strip(m.group("last")), posted=_strip(m.group("date")),
                extra={"section": sec, "advt": _strip(m.group("advt"))})
        if sec:
            j.location = sec
        out.append(j)
    return out


def parse_fja_article(page: str, job: Job) -> Job:
    """Enrich a FreeJobAlert article: apply/notification/official links,
    salary, age, fee, mode, location."""
    lines, links = _text_and_links(page)
    body = "\n".join(lines)
    for href, txt in links:
        t = (txt or "").lower()
        if "freejobalert.com" in href or href.startswith("#") or href.startswith("mailto"):
            continue
        if not job.apply_url and re.search(r"apply online|apply here|registration|online application", t):
            job.apply_url = href
        elif not job.notification_url and re.search(r"notification|advertisement|detailed advt|pdf", t):
            job.notification_url = href
        elif not job.official_url and re.search(r"official website|official site|website", t):
            job.official_url = href
    def grab(pat):
        m = re.search(pat, body, re.I)
        return _strip(m.group(1))[:120] if m else ""
    job.salary = job.salary or grab(r"(?:Salary|Pay Scale|Pay Level)[^\n:]*:?\s*([^\n]{4,120})")
    job.age = job.age or grab(r"Age Limit[^\n:]*:?\s*([^\n]{4,100})")
    job.fee = job.fee or grab(r"Application Fee[^\n:]*:?\s*([^\n]{4,100})")
    job.mode = job.mode or grab(r"Application mode[^\n:]*:?\s*([^\n]{3,40})")
    job.location = grab(r"Job location[^\n:]*:?\s*([^\n]{3,60})") or job.location
    if not job.last_date:
        job.last_date = grab(r"(?:Last date|Closing date)[^\n:]*:?\s*([0-9][^\n]{6,40})")
    if not job.official_url:
        m = re.search(r"Official Website\s*\|?\s*(www\.[a-z0-9.\-]+\.[a-z]{2,}[^\s|]*)", body, re.I)
        if m:
            job.official_url = "https://" + m.group(1)
    return job


_EEN_CARD = re.compile(
    r'<a[^>]+href="(?P<url>https://pratibha\.eenadu\.net/notifications/notification_article/[^"]+)"[^>]*>'
    r'(?P<body>.*?)</a>', re.I | re.S)


def parse_eenadu_list(page: str) -> list[Job]:
    """Eenadu Pratibha Telugu notification listing → title (TE), issuer,
    eligibility, last date (day + month + year blocks)."""
    out, seen = [], set()
    for m in _EEN_CARD.finditer(page):
        url = m.group("url")
        if url in seen:
            continue
        body = m.group("body")
        title_m = re.search(r"<(?:strong|b|h\d)[^>]*>(.*?)</(?:strong|b|h\d)>", body, re.S)
        title = _strip(title_m.group(1)) if title_m else _strip(body)[:120]
        if not title or len(title) < 6:
            continue
        seen.add(url)
        txt = _strip(body)
        board = ""
        mb = re.search(r"జారీ చేసినది\s*-\s*(.+?)(?:అర్హతలు|$)", txt)
        if mb:
            board = mb.group(1).strip(" -")
        qual = ""
        mq = re.search(r"అర్హతలు\s*-\s*(.+?)(?:\s\d{1,2}\s|$)", txt)
        if mq:
            qual = mq.group(1).strip(" -")
        last = ""
        ml = re.search(r"(\d{1,2})\s+(జనవరి|ఫిబ్రవరి|మార్చి|ఏప్రిల్|మే|జూన్|జులై|జూలై|ఆగస్టు|ఆగస్ట్|"
                       r"సెప్టెంబర్|సెప్టెంబరు|అక్టోబర్|అక్టోబరు|నవంబర్|నవంబరు|డిసెంబర్|డిసెంబరు)\s+(\d{4})", txt)
        if ml:
            last = f"{ml.group(1)} {ml.group(2)} {ml.group(3)}"
        out.append(Job(title=title, title_te=title, url=url, source="Eenadu Pratibha",
                       lang="te", board=board, qualification=qual, last_date=last))
    return out


def parse_eenadu_article(page: str, job: Job) -> Job:
    lines, links = _text_and_links(page)
    body = "\n".join(lines)
    for href, txt in links:
        if href.endswith(".pdf") and not job.notification_url:
            job.notification_url = href
        elif (txt or "").strip().lower() in ("official website", "అధికారిక వెబ్‌సైట్") and not job.official_url:
            job.official_url = href
        elif re.search(r"apply|దరఖాస్తు", txt or "", re.I) and "eenadu" not in href and not job.apply_url:
            job.apply_url = href
    def grab(label):
        m = re.search(r"(?:" + label + r")\s*[:：]\s*([^\n]{3,160})", body)
        return m.group(1).strip() if m else ""
    job.qualification = grab(r"అర్హత(?:లు)?") or job.qualification
    job.age = grab(r"(?:గరిష్ఠ\s*)?వయ(?:ో|సు)\s*పరిమితి") or job.age
    job.fee = grab(r"దరఖాస్తు రుసుము") or job.fee
    job.salary = grab(r"(?:వేతనం|జీతం|పే స్కేల్)") or job.salary
    job.mode = grab(r"దరఖాస్తు విధానం") or job.mode
    job.last_date = grab(r"దరఖాస్తుకు చివరి తేదీ|చివరి తేదీ") or job.last_date
    mv = re.search(r"మొత్తం ఖాళీల సంఖ్య\s*-?\s*(\d+)", body)
    if mv:
        job.vacancies = mv.group(1)
    posts = re.findall(r"^\d+\.\s*([^:\n]{3,60}):\s*\d+", body, re.M)
    if posts:
        job.posts = ", ".join(p.strip() for p in posts[:4])
    m = re.search(r"^# (.+)$", body, re.M)
    if m and not job.title_te:
        job.title_te = m.group(1).strip()
    # English gloss from the <title> "DLSA Mahabubnagar : మహబూబ్..." pattern
    mt = re.search(r"<title>([^<]+)</title>", page, re.I)
    if mt and ":" in mt.group(1):
        en = mt.group(1).split(":")[0].strip()
        if re.search(r"[A-Za-z]", en) and len(en) > 3:
            job.extra["title_en"] = en
    return job


def parse_rss_titles(xml: str, source: str) -> list[Job]:
    out = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S | re.I):
        it = m.group(1)
        t = re.search(r"<title>(.*?)</title>", it, re.S | re.I)
        l = re.search(r"<link>(.*?)</link>", it, re.S | re.I)
        d = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S | re.I)
        if not (t and l):
            continue
        title = _strip(re.sub(r"<!\[CDATA\[|\]\]>", "", t.group(1)))
        link = _strip(l.group(1))
        out.append(Job(title=title, url=link, source=source,
                       posted=_strip(d.group(1)) if d else ""))
    return out


def parse_sakshi_list(page: str) -> list[Job]:
    out, seen = [], set()
    for href, txt in _LINK_RE.findall(page):
        if "/jobs/education-news/" not in href:
            continue
        title = _strip(txt)
        url = urljoin("https://education.sakshi.com/", href)
        if len(title) < 10 or url in seen:
            continue
        seen.add(url)
        out.append(Job(title=title, title_te=title, url=url, source="Sakshi Education", lang="te"))
    return out


# ---------------------------------------------------------------------------
# Card rendering
# ---------------------------------------------------------------------------
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_TE_MONTHS = {"జనవరి": 1, "ఫిబ్రవరి": 2, "మార్చి": 3, "ఏప్రిల్": 4, "మే": 5, "జూన్": 6, "జులై": 7,
              "జూలై": 7, "ఆగస్టు": 8, "ఆగస్ట్": 8, "సెప్టెంబర్": 9, "సెప్టెంబరు": 9, "అక్టోబర్": 10,
              "అక్టోబరు": 10, "నవంబర్": 11, "నవంబరు": 11, "డిసెంబర్": 12, "డిసెంబరు": 12}


def parse_date(s: str):
    """'03-10-2026' / '03.10.2026' / '30 సెప్టెంబరు 2026' / '03 Oct 2026' -> date|None"""
    if not s:
        return None
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9}|[\u0C00-\u0C7F]+)\s+(\d{4})", s)
    if m:
        mon = m.group(2)
        mi = _TE_MONTHS.get(mon) or _MONTHS.get(mon[:3].lower())
        if mi:
            try:
                return date(int(m.group(3)), mi, int(m.group(1)))
            except ValueError:
                return None
    return None


def days_left(j: Job, today: date | None = None):
    d = parse_date(j.last_date)
    if not d:
        return None
    return (d - (today or datetime.now(config.IST).date())).days


def render_card(j: Job, today: date | None = None) -> str:
    cat = CATEGORY_LABEL.get(j.category, "💼 Job")
    head_te = j.title_te or ""
    head_en = j.extra.get("title_en") or ("" if j.lang == "te" else j.title)
    lines = [f"{cat} · {j.source}"]
    if head_te:
        lines.append(f"📌 {head_te}")
    if head_en and head_en != head_te:
        lines.append(f"📌 {head_en}" if not head_te else f"   {head_en}")
    facts = []
    if j.board and j.board.lower() not in (head_en or "").lower():
        facts.append(f"🏢 Board: {j.board}")
    if j.posts:
        facts.append(f"🧾 Posts: {j.posts}")
    if j.vacancies:
        facts.append(f"🔢 Vacancies: {j.vacancies}")
    if j.qualification:
        facts.append(f"🎓 Qualification / అర్హత: {j.qualification}")
    if j.age:
        facts.append(f"🎂 Age / వయసు: {j.age}")
    if j.fee:
        facts.append(f"💳 Fee / రుసుము: {j.fee}")
    if j.salary:
        facts.append(f"💰 Salary / జీతం: {j.salary}")
    if j.mode:
        facts.append(f"📝 Mode: {j.mode}")
    if j.location:
        facts.append(f"📍 {j.location}")
    dl = days_left(j, today)
    if j.last_date:
        tag = ""
        if dl is not None:
            tag = " — ⏳ TODAY!" if dl == 0 else (f" — ⏳ {dl} days left" if 0 < dl <= 7 else "")
        facts.append(f"📅 Last date / చివరి తేదీ: {j.last_date}{tag}")
    lines += facts
    links = []
    if j.apply_url:
        links.append(f"✅ Apply: {j.apply_url}")
    if j.notification_url:
        links.append(f"📄 Notification PDF: {j.notification_url}")
    if j.official_url:
        links.append(f"🌐 Official: {j.official_url}")
    links.append(f"🔗 Details: {j.url}")
    lines += [""] + links
    lines.append("— StudentUp Jobs Desk · TS/AP + Central + Private/IT/Walk-ins ✅")
    return "\n".join(lines)[: config.TG_MSG_MAX]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def _fetch(url: str):
    try:
        from .collector import http_get
        return http_get(url, respect_robots=False)
    except Exception:
        return None


def _load_state():
    st = load_json(STATE, {"posted": {}, "ts": ""})
    cutoff = (datetime.now(config.IST) - timedelta(days=7)).isoformat()
    st["posted"] = {k: v for k, v in st.get("posted", {}).items() if v.get("ts", "") >= cutoff}
    return st


def _is_dup(st, j: Job) -> bool:
    if j.key() in st["posted"]:
        return True
    nt = normalize(j.title)
    for v in st["posted"].values():
        if similarity(j.title, v.get("title", "")) >= 0.8 or (nt and nt == normalize(v.get("title", ""))):
            return True
    return False


def collect_jobs(fetch=None, max_per_source=12, enrich=True) -> list[Job]:
    """Fetch every source, parse, classify, enrich (article page) and return
    fresh Job records (not yet deduped against posted state)."""
    fetch = fetch or _fetch
    jobs: list[Job] = []
    for name, kind, url, lang, tag in JOB_SOURCES:
        page = fetch(url)
        if not page:
            print(f"   [jobs] {name}: fetch failed — skipped")
            continue
        try:
            if kind == "fja_table":
                found = parse_fja_table(page)
            elif kind == "eenadu_list":
                found = parse_eenadu_list(page)
            elif kind == "sakshi_list":
                found = parse_sakshi_list(page)
            else:
                found = parse_rss_titles(page, name.replace(" RSS", ""))
        except Exception as e:
            print(f"   [jobs] {name}: parse error {e}")
            continue
        kept = 0
        for j in found:
            j.lang = j.lang or lang
            ok, cat = classify(j.title, f"{j.board} {j.extra.get('section', '')} {j.qualification}")
            if not ok:
                continue
            if tag == "walkin":
                cat = "walk-in"
            elif tag == "private" and cat == "central":
                cat = "private-it"
            elif tag == "scholarship":
                cat = "scholarship"
            j.category = cat
            jobs.append(j)
            kept += 1
            if kept >= max_per_source:
                break
        print(f"   [jobs] {name}: {len(found)} found, {kept} relevant")
    # collapse duplicates across sources (same URL / near-same title)
    uniq: list[Job] = []
    for j in jobs:
        if any(j.key() == u.key() or similarity(j.title, u.title) >= 0.8 for u in uniq):
            continue
        uniq.append(j)
    if enrich:
        for j in uniq:
            if j.source in ("FreeJobAlert", "Eenadu Pratibha") and "/articles/" in j.url or "notification_article" in j.url:
                page = fetch(j.url)
                if page:
                    try:
                        if j.source == "FreeJobAlert":
                            parse_fja_article(page, j)
                        else:
                            parse_eenadu_article(page, j)
                    except Exception as e:
                        print(f"   [jobs] enrich {j.url}: {e}")
    return uniq


def _priority(j: Job) -> tuple:
    order = {"ts-ap": 0, "central": 1, "walk-in": 2, "private-it": 3, "scholarship": 4}
    vac = int(re.sub(r"\D", "", j.vacancies) or 0)
    return (order.get(j.category, 9), -vac)


def run(tg, dry=False, max_posts=6, fetch=None, today=None) -> int:
    """Post fresh job cards to the PRIVATE jobs channel. Returns posts made."""
    chat = config.channel_chat_id("JOBS")
    st = _load_state()
    jobs = collect_jobs(fetch=fetch)
    fresh = [j for j in jobs if not _is_dup(st, j)]
    fresh.sort(key=_priority)
    # closing-soon re-alerts (once)
    reposts = []
    for k, v in list(st["posted"].items()):
        if v.get("realerted"):
            continue
        dl = None
        d = parse_date(v.get("last_date", ""))
        if d:
            dl = (d - (today or datetime.now(config.IST).date())).days
        if dl is not None and 0 <= dl <= 2:
            reposts.append((k, v))
    posted = 0
    for j in fresh[:max_posts]:
        try:
            card = render_card(j, today)
            jid, btn = None, None
            if not dry:
                try:
                    from . import jobradar
                    jid = jobradar.record(j, card)
                    btn = jobradar.channel_buttons(jid)
                except Exception as e:
                    print(f"   [jobs] radar record failed: {e}")
            tg.send_message(chat, card, disable_preview=True, buttons=btn)
            st["posted"][j.key()] = {"title": j.title, "ts": datetime.now(config.IST).isoformat(),
                                     "last_date": j.last_date, "card": card[:1500], "jid": jid}
            posted += 1
            tg.polite_gap(not dry)
        except Exception as e:
            print(f"   [jobs] post failed {j.url}: {e}")
    for k, v in reposts[:2]:
        try:
            tg.send_message(chat, "⏳ CLOSING SOON — చివరి తేదీ దగ్గరలో!\n" + v.get("card", ""), disable_preview=True)
            v["realerted"] = True
            posted += 1
            tg.polite_gap(not dry)
        except Exception as e:
            print(f"   [jobs] re-alert failed: {e}")
    if not posted and not st["posted"]:
        # never silent on the very first run — curated fallback (one card)
        items = load_json(FALLBACK, {"items": []}).get("items", [])[:3]
        for it in items:
            j = Job(title=it["en"], title_te=it.get("te", ""), url=it.get("link", ""),
                    source=it.get("source", "StudentUp"), category="central")
            try:
                tg.send_message(chat, render_card(j, today), disable_preview=True)
                posted += 1
            except Exception as e:
                print(f"   [jobs] fallback failed: {e}")
    st["ts"] = datetime.now(config.IST).isoformat()
    if not dry:
        save_json_atomic(STATE, st)
    print(f"[jobs] {len(jobs)} collected, {len(fresh)} fresh, {posted} posted (private channel)")
    return posted
