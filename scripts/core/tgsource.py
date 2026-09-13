#!/usr/bin/env python3
"""
STUDENTUP — TELEGRAM PUBLIC-CHANNEL SOURCE  (no API key, no login)

Every public Telegram channel has a web preview at  https://t.me/s/<username>
(and older pages via ?before=<msg_id>). Exam-prep channels post two things we
want:
  1. QUIZ POLLS  — "Anonymous Quiz" blocks: question + options. The correct
     option is not exposed in the preview, so these are queued as
     `answer_pending` and solved by the verifier's double-LLM check before
     they can ever be posted (never guessed).
  2. PDF DOCUMENTS — "Daily CA Quiz 10 Sept.pdf" style files. The message id
     is recorded; the file itself is fetched via the message's public link
     when a download URL is exposed, otherwise the *title* is used to target
     the same PDF on the publisher's site.
  3. TEXT MCQs — plain messages that contain "Q1. … (a) … Ans: b" style text
     go through the normal quiz-line parser and arrive with answers.

Failure-proof: fetch problems return [], nothing raises; pagination is
bounded; per-channel state (last seen msg id) lives in data/tg_source_state.json.

CLI:
  python3 -m core.tgsource pull <username> [--pages 2]
  python3 -m core.tgsource list
"""
from __future__ import annotations

import html as _html
import re
import sys
from datetime import datetime
from html.parser import HTMLParser

from . import config
from .store import load_json, save_json_atomic

STATE_FILE = config.DATA / "tg_source_state.json"
PREVIEW = "https://t.me/s/{u}"
MAX_PAGES = 3
MAX_MSGS_PER_CHANNEL = 60
CROWD_MIN_VOTERS = 60      # vote share is used as a 3rd opinion only when enough people voted
CROWD_LEAD_GAP = 12        # …and the leading option is clearly ahead (percentage points)


# ---- curated public exam channels (username, channel, lang) ----------------
# Only channels that publish quiz polls / MCQ text / official-style paper PDFs.
# Junk-y "join our paid batch" channels are excluded deliberately.
CHANNELS = [
    # ---- TS / AP (Telugu-first) ----
    ("Adda247Telugu", "TSPSC", "en"),             # 27K · daily CA quiz polls, TS/AP focus (live 2026-09)
    ("civiccentredotin", "APPSC", "en"),          # CivicCentre IAS APPSC/TGPSC (live 2026-09)
    ("EducationalHub", "CURRENT", "en"),          # daily CA/GA/GS quiz polls (UPSC/TSPSC/APPSC/SSC)
    ("telangana_groups", "TSPSC", "te"),          # studybizz TS group exams
    ("telangana_jobs", "TSPSC", "te"),
    ("andhrapradeshjobs", "APPSC", "te"),
    ("studybizz", "TSPSC", "te"),
    ("vmsaspirantsacademyforallexams", "TSPSC", "te"),  # TGPSC/APPSC maths+reasoning
    ("dscaspirant", "APPSC", "te"),
    ("csetopper_appsc", "APPSC", "en"),
    ("group1_mains_tspsc", "TSPSC", "en"),
    ("appsc_groups_materials", "APPSC", "te"),
    ("gvs_rajkumar_ias_study_circle", "TSPSC", "te"),
    ("aphistorygroup2", "APPSC", "te"),
    # ---- SSC ----
    ("sscquizparmar", "SSC", "en"),               # 542K · GK/Eng/Reasoning/Maths quiz polls daily (live 2026-09)
    ("sscwallahpw", "SSC", "en"),                 # 171K · PW SSC polls + PYQs (live 2026-09)
    ("ThePundits_Official", "SSC", "en"),         # 421K · SSC quizzes (live 2026-09)
    ("sscadda_official", "SSC", "en"),            # SSC Adda247 (quiz polls + CA quiz PDFs)
    ("SSC_CGL_QUIZ_TREASURE", "SSC", "en"),
    ("SscAdda", "SSC", "en"),
    ("SscZoneOfficial", "SSC", "en"),
    ("SSC_Railway_Zone", "SSC", "en"),
    ("Mock4Exams", "SSC", "en"),
    ("Quiz4Exam", "SSC", "en"),
    ("testbook_quiz", "SSC", "en"),
    # ---- Railway ----
    ("sscaddaRailways", "RAILWAY", "en"),         # Mission Railways (Adda247)
    ("RailwayZone", "RAILWAY", "en"),
    ("RailwayZoneOfficial", "RAILWAY", "en"),
    ("Railway_Ntpc_Group_D_Ssc", "RAILWAY", "en"),
    # ---- Banking ----
    ("bankersaddaofficialgroup", "BANKING", "en"),
    ("IbpsZone", "BANKING", "en"),
    ("BankingZoneOfficial", "BANKING", "en"),
    ("SbiZone", "BANKING", "en"),
    ("RbiZone", "BANKING", "en"),
    ("InsuranceZone", "BANKING", "en"),
    ("UPSC_Prelims_MCQs_Quiz", "DEFENCE", "en"),  # PYQ/MCQ polls (GS overlap NDA/CDS)
    # ---- Defence ----
    ("sscadda_247", "DEFENCE", "en"),             # UPSC/State PSC (NDA/CDS GK overlaps)
    ("CivilServicesAdda", "DEFENCE", "en"),
    # ---- Current affairs / GK ----
    ("GA_Buzz", "CURRENT", "en"),
    ("GSdiscussionsgroup", "CURRENT", "en"),      # General Studies quiz & free PDF
    ("GovtAdda", "CURRENT", "en"),
    ("current_affairs4u", "CURRENT", "en"),
    ("adda247youtube", "CURRENT", "en"),
]


# ---------------------------------------------------------------- HTML → messages
class _Msgs(HTMLParser):
    """Split the preview page into message blocks with text, poll and doc info."""

    def __init__(self):
        super().__init__()
        self.msgs = []
        self._cur = None
        self._stack = []
        self._in_poll_q = self._in_opt = self._in_text = self._in_doc = False
        self._in_pct = self._in_votes = False
        self._buf = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "") or ""
        if "tgme_widget_message " in cls + " " and a.get("data-post"):
            self._flush()
            self._cur = {"id": a["data-post"], "text": "", "poll_q": "", "options": [],
                         "doc": "", "date": "", "shares": [], "voters": 0}
        if not self._cur:
            return
        if "tgme_widget_message_poll_question" in cls:
            self._in_poll_q = True; self._buf = ""
        elif "tgme_widget_message_poll_option_percent" in cls:
            self._in_pct = True; self._buf = ""
        elif "tgme_widget_message_poll_option_text" in cls:
            self._in_opt = True; self._buf = ""
        elif "tgme_widget_message_poll_votes" in cls:
            self._in_votes = True; self._buf = ""
        elif "tgme_widget_message_text" in cls and "js-message_text" in cls:
            self._in_text = True; self._buf = ""
        elif "tgme_widget_message_document_title" in cls:
            self._in_doc = True; self._buf = ""
        elif tag == "time" and a.get("datetime"):
            self._cur["date"] = a["datetime"][:10]
        elif tag == "br" and self._in_text:
            self._buf += "\n"

    def handle_data(self, data):
        if self._in_poll_q or self._in_opt or self._in_text or self._in_doc or self._in_pct or self._in_votes:
            self._buf += data

    def handle_endtag(self, tag):
        if not self._cur:
            return
        if tag == "div" and self._in_poll_q:
            self._cur["poll_q"] = _clean(self._buf); self._in_poll_q = False
        elif tag == "div" and self._in_opt:
            self._cur["options"].append(_clean(self._buf)); self._in_opt = False
        elif tag == "div" and self._in_pct:
            m = re.search(r"(\d+)", self._buf)
            self._cur["shares"].append(int(m.group(1)) if m else 0); self._in_pct = False
        elif tag == "div" and self._in_votes:
            m = re.search(r"([\d,.]+)\s*(K?)", self._buf, re.I)
            if m:
                try:
                    self._cur["voters"] = int(float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1))
                except ValueError:
                    pass
            self._in_votes = False
        elif tag == "div" and self._in_text:
            self._cur["text"] = _html.unescape(self._buf).strip(); self._in_text = False
        elif tag == "div" and self._in_doc:
            self._cur["doc"] = _clean(self._buf); self._in_doc = False

    def _flush(self):
        if self._cur:
            self.msgs.append(self._cur)
            self._cur = None

    def close(self):
        super().close()
        self._flush()


def _clean(s):
    return re.sub(r"\s+", " ", _html.unescape(s or "")).strip()


def parse_preview(page_html: str):
    p = _Msgs()
    try:
        p.feed(page_html)
        p.close()
    except Exception:
        pass
    return p.msgs


# ---------------------------------------------------------------- items
_BAD_Q = re.compile(r"\b(?:join(?:ed|ing)?|batch|discount|offer|subscribe|link in bio|paid|telegram|whatsapp)\b",
                    re.I)


def items_from_messages(msgs, username, channel_default, lang="en"):
    """Turn parsed messages into collector-ready raws + PDF hints."""
    from .collector import parse_quiz_lines, infer_channel
    raws, pdfs = [], []
    for m in msgs:
        link = f"https://t.me/{m['id']}"
        title = f"@{username} {m.get('date', '')}"
        # 1. quiz poll -> answer-pending raw (verifier solves before use)
        if m["poll_q"] and 2 <= len(m["options"]) <= 4 and not _BAD_Q.search(m["poll_q"]):
            opts = [o for o in m["options"] if o]
            if len(opts) == 4 and len(m["poll_q"]) >= 15:
                crowd = None
                if len(m.get("shares") or []) == 4 and m.get("voters", 0) >= CROWD_MIN_VOTERS:
                    order = sorted(range(4), key=lambda i: -m["shares"][i])
                    if m["shares"][order[0]] - m["shares"][order[1]] >= CROWD_LEAD_GAP:
                        crowd = order[0]
                raws.append({"q_en": m["poll_q"], "options_en": opts, "answer_index": None,
                             "explanation_en": "", "title": title, "url": link,
                             "answer_pending": True, "lang": lang,
                             "channel_hint": channel_default,
                             "crowd_index": crowd, "voters": m.get("voters", 0)})
        # 2. text MCQs with answers (Q1 ... (a) ... Ans: b)
        if m["text"] and re.search(r"(?i)\bans(?:wer)?\s*[:\-–]|జవాబు|उत्तर", m["text"]):
            lines = [ln.strip() for ln in m["text"].split("\n") if ln.strip()]
            try:
                got = parse_quiz_lines(lines, article_title=title, url=link)
            except Exception:
                got = []
            for r in got:
                r["channel_hint"] = channel_default
                r["lang"] = lang
            raws.extend(got)
        # 3. PDF documents that look like quizzes / papers
        if m["doc"] and re.search(r"\.pdf$", m["doc"], re.I) and \
                re.search(r"quiz|question|paper|mcq|pyq|set|shift|key", m["doc"], re.I) and \
                not re.search(r"hindi", m["doc"], re.I):
            pdfs.append({"title": m["doc"], "msg": link, "channel": channel_default,
                         "date": m.get("date", "")})
    return raws, pdfs


# ---------------------------------------------------------------- pull
def _state():
    return load_json(STATE_FILE, {"channels": {}})


def pull(username, channel_default="CURRENT", lang="en", pages=MAX_PAGES, http_get=None,
         dry=False):
    """Fetch newest preview pages for one channel; return (raws, pdfs). Never raises."""
    if http_get is None:
        from .collector import http_get as _hg
        http_get = lambda u: _hg(u, respect_robots=False)
    st = _state()
    rec = st["channels"].setdefault(username, {"last_id": 0, "pulls": 0, "fails": 0})
    all_msgs, before, seen_ids = [], None, set()
    for _ in range(max(1, pages)):
        url = PREVIEW.format(u=username) + (f"?before={before}" if before else "")
        try:
            page = http_get(url)
        except Exception:
            page = None
        if not page:
            rec["fails"] += 1
            break
        msgs = parse_preview(page)
        if not msgs:
            break
        rec["fails"] = 0
        ids = []
        for m in msgs:
            try:
                ids.append(int(m["id"].rsplit("/", 1)[-1]))
            except ValueError:
                pass
        if not ids or set(ids) <= seen_ids:      # server ignored ?before= → stop
            break
        seen_ids |= set(ids)
        oldest = min(ids)
        # only messages newer than what we've already consumed
        fresh = [m for m in msgs if int(m["id"].rsplit("/", 1)[-1]) > rec["last_id"]]
        all_msgs.extend(fresh)
        if len(fresh) < len(msgs) or len(all_msgs) >= MAX_MSGS_PER_CHANNEL or not oldest:
            break
        before = oldest
    raws, pdfs = items_from_messages(all_msgs, username, channel_default, lang)
    if all_msgs:
        rec["last_id"] = max(rec["last_id"], max(int(m["id"].rsplit("/", 1)[-1]) for m in all_msgs))
    rec["pulls"] += 1
    rec["last"] = datetime.now(config.IST).strftime("%Y-%m-%d %H:%M")
    rec["last_raws"] = len(raws)
    if not dry:
        save_json_atomic(STATE_FILE, st)
    return raws, pdfs


def pull_all(limit_channels=None, http_get=None, dry=False):
    """Round-robin all curated channels (bounded). Returns (raws, pdfs, stats)."""
    raws, pdfs, stats = [], [], {"channels": 0, "raws": 0, "pdfs": 0, "failed": 0}
    st = _state()
    for username, ch, lang in CHANNELS[: limit_channels or len(CHANNELS)]:
        rec = st["channels"].get(username, {})
        if rec.get("fails", 0) >= 5 and rec.get("pulls", 0) % 7:   # dead-ish: try 1 in 7 runs
            continue
        r, p = pull(username, ch, lang, pages=1, http_get=http_get, dry=dry)
        stats["channels"] += 1
        if not r and not p and st["channels"].get(username, {}).get("fails"):
            stats["failed"] += 1
        raws.extend(r); pdfs.extend(p)
    stats["raws"], stats["pdfs"] = len(raws), len(pdfs)
    return raws, pdfs, stats


def status_text():
    st = _state()["channels"]
    ok = sum(1 for v in st.values() if v.get("fails", 0) == 0 and v.get("pulls"))
    return (f"📡 Telegram sources: {len(CHANNELS)} curated · {ok} healthy · "
            f"{sum(v.get('last_raws', 0) for v in st.values())} items last pull")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "list":
        for u, ch, lg in CHANNELS:
            print(f"{ch:8} {lg} https://t.me/s/{u}")
    elif a[0] == "pull" and len(a) > 1:
        pg = int(a[a.index("--pages") + 1]) if "--pages" in a else MAX_PAGES
        ch = next((c for u, c, _ in CHANNELS if u.lower() == a[1].lower()), "CURRENT")
        r, p = pull(a[1], ch, pages=pg)
        print(f"{len(r)} raws, {len(p)} pdfs")
        for x in r[:5]:
            print(" -", x["q_en"][:80], x["options_en"], x["answer_index"])
        for x in p[:5]:
            print(" 📎", x["title"], x["msg"])
    else:
        print(__doc__)
