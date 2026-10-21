#!/usr/bin/env python3
"""
STUDENTUP — FULL CONTROL WEB DASHBOARD & ADVANCED AUTOMATION HUB
Features:
  1. Live Question Bank Inventory & Channel Poll Counts.
  2. Excel / Google Sheets Importer: Direct Paste or Upload 100+ to 150+ WhatsApp Groups & Telegram Channels.
  3. Custom Cluster Bundles: Group specific channels and WhatsApp groups into single-click dispatch bundles.
  4. WhatsApp 100+ Interleaved Anti-Ban Pipeline: 2-by-2 groups with 20-30s natural thinking gaps, two-phase answer key delivery.
  5. TS & AP Academic (B.Tech, Degree, ITI, Open Universities, Diploma, Inter, 10th) & Competitive Channels.
"""
import sys
import os
import json
import time
import base64
import urllib.request
import urllib.parse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from core import config
from core.members import Members
from core.question_bank import Bank
from core import hooks, districtwar, arena, campus, crm, whatsapp_pipeline, channel_router, bundle_manager, member_queue, planner, portal, pyq
import threading as _threading
from core.telegram import Telegram


_BOT_USERNAME_CACHE = {"name": "", "ts": 0}


_PYQ_JOB = {"running": False, "last": ""}
_REPORT_JOB = {"running": False, "sent": 0, "failed": 0, "total": 0, "last": ""}
_WP_CACHE = {"ts": 0, "posts": []}


def _wp_base():
    return config.env("WP_SITE_URL", "https://studentup.in").strip().rstrip("/")


def _fetch_wp_posts(limit=12, force=False):
    """📰 WordPress (studentup.in) nunchi published blog posts — 10 min
    cache. Drafts REST lo public ga ravu (publish ayye varaku safe).
    Site reach avakapothe [] (site eppudu crash avadu)."""
    import html as _html
    import re as _re
    if not force and time.time() - _WP_CACHE["ts"] < 600 and _WP_CACHE["posts"]:
        return _WP_CACHE["posts"][:limit]

    def _clean(t):
        return _html.unescape(_re.sub(r"<[^>]+>", "", str(t or ""))).strip()

    try:
        req = urllib.request.Request(
            f"{_wp_base()}/wp-json/wp/v2/posts?per_page={int(limit)}&_fields=title,excerpt,link,date,slug",
            headers={"User-Agent": "StudentUp-Bridge/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            raw = json.loads(r.read().decode("utf-8", "ignore"))
        posts = [{"title": _clean(p.get("title", {}).get("rendered", "")),
                  "excerpt": _clean(p.get("excerpt", {}).get("rendered", ""))[:240],
                  "url": p.get("link", ""), "date": (p.get("date") or "")[:10],
                  "slug": p.get("slug", "")} for p in raw if p.get("link")]
        if posts:
            _WP_CACHE.update({"ts": time.time(), "posts": posts})
        return posts
    except Exception:
        return _WP_CACHE["posts"][:limit]


_WP_EXAM_TAGS = {"APPSC": "appsc", "TSPSC": "tspsc", "SSC": "ssc",
                 "BANKING": "banking", "RAILWAY": "rrb", "POLICE": "police",
                 "DEFENCE": "defence", "CURRENT": "all"}


def _wp_quiz_item(q):
    """Mana bank question → WordPress quiz.php format (q, a[4], c, why, cat, src, exam)."""
    return {"q": q.get("q_en", ""), "a": list(q.get("options_en") or []),
            "c": int(q.get("answer_index") or 0),
            "why": q.get("explanation") or q.get("explanation_en") or q.get("explanation_te") or "", "cat": q.get("topic") or "General",
            "src": "StudentUp PYQ" if q.get("source") == "pyq" else "StudentUp",
            "exam": _WP_EXAM_TAGS.get(q.get("channel") or "", "all")}


def _wp_quiz_export():
    d = portal._load()
    day = portal._daily_paper(d)
    return {"date": portal._today(), "source": "StudentUp Quiz Portal",
            "questions": [_wp_quiz_item(q) for q in day["qs"]]}


def _cors_origin(origin):
    """🔒 280X (F7 closure): CORS allowlist — never '*'. Echo the
    request Origin ONLY when it is the configured public/portal origin
    or a localhost dev origin; anything else gets no CORS grant ('').
    Self-contained (stdlib only) so it stays unit-testable in
    isolation; the .env file is consulted via core.config when
    importable, process env otherwise."""
    import os
    from urllib.parse import urlparse
    o = (origin or "").strip()
    if not o:
        return ""
    try:
        host = urlparse(o).hostname or ""
    except Exception:
        return ""
    if host in ("localhost", "127.0.0.1"):
        return o
    allowed = set()
    vals = []
    try:
        from core import config as _cfg280
        vals = [_cfg280.env("PUBLIC_BASE_URL", ""),
                _cfg280.env("PORTAL_BASE_URL", "")]
    except Exception:
        vals = [os.environ.get("PUBLIC_BASE_URL", ""),
                os.environ.get("PORTAL_BASE_URL", "")]
    for v in vals:
        try:
            p = urlparse((v or "").strip())
            if p.scheme and p.netloc:
                allowed.add(f"{p.scheme}://{p.netloc}")
        except Exception:
            pass
    return o if o in allowed else ""


def _golive_checks():
    """🚀 160X GO-LIVE CHECKS (subdomain launch readiness). Secrets
    eppudu bayataki ravu — only set/unset booleans matrame."""
    checks = []
    base = config.env("PUBLIC_BASE_URL", "").strip().rstrip("/")
    checks.append({
        "name": "PUBLIC_BASE_URL",
        "status": "ok" if base.startswith("https://") else "warn",
        "detail": base or "set ledu — request host nunchi derive avthundi (production lo https://quiz.studentup.in set cheyyandi)"})
    pbase = config.env("PORTAL_BASE_URL", "").strip()
    try:
        from core import rankcard as _rc260
        _f260 = _rc260._find_font(_rc260._LATIN) is not None
        _dep260 = bool(_f260)
    except Exception:
        _dep260 = False
    checks.append({
        "name": "Certificate engine (PIL + QR)",
        "status": "ok" if _dep260 else "warn",
        "detail": ("PIL + qrcode + TTF font ready"
                   if _dep260 else
                   "winner/score card PNGs degrade — VPS lo "
                   "'pip install pillow qrcode' cheyyandi")})
    checks.append({
        "name": "Portal URL",
        "status": "ok",
        "detail": pbase or ((base + "/portal") if base else "/portal")})
    checks.append({
        "name": "BOT_TOKEN",
        "status": "ok" if getattr(config, "BOT_TOKEN", "") else "fail",
        "detail": "configured" if getattr(config, "BOT_TOKEN", "") else "bot features (WebApp login, broadcasts) pani cheyyavu"})
    try:
        bu = _bot_username()
    except Exception:
        bu = ""
    checks.append({
        "name": "Bot username",
        "status": "ok" if bu else "warn",
        "detail": ("@" + bu) if bu else "BOT_USERNAME .env lo set cheyyandi (deep links kosam)"})
    try:
        snippet = Path(__file__).resolve().parent.parent / "integrations" / "wordpress" / "studentup-portal-icon.html"
        snip_ok = snippet.exists()
    except Exception:
        snip_ok = False
    checks.append({
        "name": "WP portal icon snippet",
        "status": "ok" if snip_ok else "warn",
        "detail": "integrations/wordpress/studentup-portal-icon.html ready" if snip_ok else "snippet missing"})
    checks.append({
        "name": "PWA (manifest + SW v4)",
        "status": "ok",
        "detail": "/manifest.json + /sw.js (v5) routes active"})
    ads = config.env("ADSENSE_CLIENT_ID", "").strip()
    checks.append({
        "name": "AdSense (optional)",
        "status": "ok" if ads else "warn",
        "detail": "configured" if ads else "set ledu — ads off (public pages matrame, exam pages lo eppudu levu)"})
    try:
        _dpw_default = _dash_password() == DEFAULT_DASH_PASSWORD
    except Exception:
        _dpw_default = False
    try:
        from core import stateless_client as _sl260
        _slt260, _sle260 = _sl260.register_student(
            "Go-Live Probe", "9000000001", "Guntur", "railway",
            secret="golive-probe")
        _sl_ok260 = _sle260 is None and _sl260.public_view(
            _slt260 or "", secret="golive-probe") is not None
    except Exception:
        _sle260 = "stateless module unavailable"
        _sl_ok260 = False
    checks.append({
        "name": "Stateless client (260X)",
        "status": "ok" if _sl_ok260 else "fail",
        "detail": ("signed-token round-trip verified (zero-storage "
                   "registration/auth)"
                   if _sl_ok260 else f"round-trip failed: {_sle260}")})
    checks.append({
        "name": "No-VPS shared-host mode (270X)",
        "status": "ok" if _sl_ok260 else "warn",
        "detail": ("portal Stateless routes active — MilesWeb Premium "
                   "shared hosting mide portal run cheyyavachu; bot/"
                   "broadcast ki matrame VPS kavali"
                   if _sl_ok260 else
                   "stateless module fail — hosting mode unavailable")})
    checks.append({
        "name": "Dashboard password",
        "status": "warn" if _dpw_default else "ok",
        "detail": ("DEFAULT password (studentup123) inka use avthundi — "
                   "DASHBOARD_PASSWORD env tho strong password set cheyyandi!")
                  if _dpw_default else "custom dashboard password set ayindi"})
    # 🏥 280X: bank health + answer-position bias (raw bank meda —
    # live polls anni send-time lo balanced ae; ikkada raw skew
    # kanipisthe admin ki teliyali, students ki kadu).
    try:
        from core import bankhealth as _bh280
        from core.question_bank import load_bank as _lb280
        _bk280 = _lb280()
        _qs280 = (_bk280.questions if hasattr(_bk280, "questions")
                  else list(_bk280))
        _rep280 = _bh280.bank_health_report(_qs280)
        _bad280 = _rep280["invalid_count"] > 0
        _bias280 = bool(_rep280["bias_flags"])
        checks.append({
            "name": "Bank health (280X)",
            "status": "warn" if (_bad280 or _bias280) else "ok",
            "detail": _bh280.summarize(_rep280) + (
                " — live polls balanced at send time (poll_safe)"
                if _bias280 and not _bad280 else
                (" — invalid questions fix cheyyandi (bank_health.py)"
                 if _bad280 else " — raw bank kuda clean"))})
    except Exception as _e280:
        checks.append({
            "name": "Bank health (280X)", "status": "warn",
            "detail": f"health report run avvaledu: {_e280}"})
    try:
        from core import publish_queue as _pq310, wp_push as _wpp310
        _d310 = _pq310.get_or_build_today()
        checks.append({
            "name": "Daily publish draft (310X)", "status": "ok" if _d310.get("status") in ("approved", "live") else "warn",
            "detail": f"{_d310.get('id')}: {_d310.get('status')} · quiz {_d310.get('quiz', {}).get('count', 0)}Q · WP creds {'set' if _wpp310.creds_ready() else 'not set (.env)'}"})
    except Exception as _e310:
        checks.append({
            "name": "Daily publish draft (310X)", "status": "warn",
            "detail": f"draft check run avvaledu: {_e310}"})
    # 📜 430X: Paper Factory readiness — approved papers in the
    # scraped bank + drafts waiting (strict: TE-pending never counts).
    try:
        from core import paperfactory as _pf430
        _banked430 = 0
        try:
            from core.store import load_json as _lj430
            _sb430 = _lj430(config.DATA / "scraped_bank.json",
                            {"questions": []})
            _banked430 = len(_sb430.get("questions") or [])
        except Exception:
            _banked430 = 0
        _drafts430 = _pf430.list_drafts()
        _open430 = [x for x in _drafts430 if x.get("status") == "draft"]
        _pend430 = sum(x.get("needs_translation") or 0 for x in _open430)
        checks.append({
            "name": "Paper Factory (430X)",
            "status": "warn" if _open430 else "ok",
            "detail": (f"{_banked430} approved paper questions banked · "
                       f"{len(_open430)} drafts open"
                       + (f" · {_pend430} Telugu pending (bank avvalevu)"
                          if _pend430 else ""))})
    except Exception as _e430:
        checks.append({"name": "Paper Factory (430X)", "status": "warn",
                       "detail": f"paper factory check run avvaledu: {_e430}"})
    # 🎓 440X: Board subject tests readiness — the same academic
    # stock must be playable on the portal (420X) AND in Telegram
    # via /boards; an empty board warns instead of looking live.
    try:
        from core import boardbot as _bb440
        _r440 = _bb440.readiness()
        checks.append({
            "name": "Board Bot Tests (440X)",
            "status": "ok" if _r440.get("ready") else "warn",
            "detail": (f"{_r440.get('boards', 0)} board channels · "
                       f"{_r440.get('questions', 0)} academic questions · "
                       f"{_r440.get('subjects', 0)} subject tests live on "
                       "portal + Telegram /boards"
                       + (f" · ⚠️ stock pending: "
                          f"{', '.join(_r440.get('empty') or [])}"
                          if _r440.get("empty") else ""))})
    except Exception as _e440:
        checks.append({"name": "Board Bot Tests (440X)", "status": "warn",
                       "detail": f"board bot check run avvaledu: {_e440}"})
    try:
        from core import portal as _p340
        _hub340 = _p340.state_hub()
        _gaps340 = [f"{e['goal']}: +{e['gap_total']}Q/+{e['gap_pyq']}PYQ"
                    for s in _hub340.get("states", []) for e in s.get("exams", [])
                    if e.get("gap_total", 0) > 0 or e.get("gap_pyq", 0) > 0]
        checks.append({
            "name": "Exam stock targets (340X)",
            "status": "warn" if _gaps340 else "ok",
            "detail": ("stock gaps: " + " · ".join(_gaps340[:4])
                       if _gaps340 else "anni exams healthy stock lo unnayi")})
    except Exception as _e340:
        checks.append({
            "name": "Exam stock targets (340X)", "status": "warn",
            "detail": f"stock check run avvaledu: {_e340}"})
    overall = "ready" if all(c["status"] != "fail" for c in checks) else "pending"
    return {"overall": overall, "checks": checks}


def _public_base(handler=None):
    """🌐 Student-facing links ki base URL: PUBLIC_BASE_URL env (meeru
    subdomain point cheste adhe vastundi) → lekapothe request Host
    (preview / domain ఏదైనా) nunchi derive chestham — app host-agnostic."""
    base = config.env("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if base:
        return base
    if handler is not None:
        host = (handler.headers.get("X-Forwarded-Host")
                or handler.headers.get("Host") or "")
        if host:
            proto = handler.headers.get("X-Forwarded-Proto") or (
                "http" if host.split(":")[0] in ("127.0.0.1", "localhost") else "https")
            return f"{proto}://{host}"
    return ""


# ================================================================== public site
# 🌍 Public brand website (students/visitors + Google AdSense review కోసం).
# Admin dashboard ilaage untundi — login leni vallaki "/" public site kanipisthundi.
# ⚠️ Ads kevalam PUBLIC pages lone (exam/session pages lo bao — policy + focus).
PUBLIC_PAGE_PATHS = {"/site": "home", "/about": "about", "/privacy": "privacy",
                     "/terms": "terms", "/contact": "contact", "/study": "study",
                     "/updates": "updates", "/winners": "winners",
                     "/toppers": "toppers", "/materials": "materials",
                     "/blog": "blog", "/papers": "papers",
                     "/exams": "exams"}


def _adsense_client():
    return config.env("ADSENSE_CLIENT_ID", "").strip()


def ads_txt_content():
    """ads.txt — AdSense seller verification (root domain lo undali,
    subdomains ki kuda ide valid). Env lekapothe empty (route 404)."""
    pub = config.env("ADSENSE_PUBLISHER_ID", "").strip()
    if not pub:
        cid = _adsense_client()
        pub = cid[3:] if cid.startswith("ca-pub-") else cid
    if not pub.startswith("pub-"):
        return ""
    return f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n"


def _adsense_head():
    cid = _adsense_client()
    if not cid.startswith("ca-pub-"):
        return ""
    return (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/'
            f'adsbygoogle.js?client={cid}" crossorigin="anonymous"></script>')


def _ad_slot(name):
    cid = _adsense_client()
    slot = config.env(f"ADSENSE_SLOT_{name}", "").strip()
    if not cid.startswith("ca-pub-") or not slot:
        return ""
    return ('<div class="adbox"><ins class="adsbygoogle" style="display:block" '
            f'data-ad-client="{cid}" data-ad-slot="{slot}" data-ad-format="auto" '
            'data-full-width-responsive="true"></ins>'
            '<script>(adsbygoogle = window.adsbygoogle || []).push({});</script></div>')


_PUB_CSS = """
  * { box-sizing: border-box; margin: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { background: #050811; color: #e2e8f0; line-height: 1.65; }
  a { color: #38bdf8; text-decoration: none; }
  .nav { display: flex; gap: 18px; align-items: center; flex-wrap: wrap; padding: 14px 20px; background: #0b1329; border-bottom: 1px solid #1e3a5f; position: sticky; top: 0; z-index: 9; }
  .nav .logo { font-size: 19px; font-weight: 800; color: #f8fafc; margin-right: auto; }
  .nav a { font-size: 13.5px; font-weight: 600; }
  .nav .login { background: #12233f; border: 1px solid #24466e; padding: 6px 12px; border-radius: 999px; }
  .wrap { max-width: 980px; margin: 0 auto; padding: 26px 18px 60px; }
  .hero { text-align: center; padding: 42px 14px 26px; }
  .hero h1 { font-size: 32px; line-height: 1.25; color: #f8fafc; }
  .hero h1 span { color: #10b981; }
  .hero p { color: #94a3b8; max-width: 640px; margin: 12px auto 0; font-size: 15px; }
  .cta { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin-top: 20px; }
  .btn { padding: 12px 20px; border-radius: 11px; font-weight: 800; font-size: 14px; border: none; cursor: pointer; }
  .btn-g { background: linear-gradient(90deg, #10b981, #38bdf8); color: #04121f; }
  .btn-o { background: #12233f; color: #e2e8f0; border: 1px solid #24466e; }
  .exambox { max-width: 460px; margin: 22px auto 0; background: #0b1329; border: 1px solid #1e3a5f; border-radius: 14px; padding: 16px; }
  .exambox input { width: 100%; padding: 11px 13px; font-size: 16px; background: #050811; color: #fff; border: 1px solid #24466e; border-radius: 9px; text-transform: uppercase; margin: 8px 0; }
  h2.sec { font-size: 21px; margin: 38px 0 14px; color: #f8fafc; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
  .card { background: #0b1329; border: 1px solid #1e3a5f; border-radius: 13px; padding: 16px; }
  .card h3 { font-size: 15px; margin-bottom: 6px; }
  .card p, .txt p { color: #94a3b8; font-size: 13.5px; }
  .txt p { margin-bottom: 12px; }
  .txt h3 { margin: 20px 0 8px; font-size: 16px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { background: #12233f; border: 1px solid #24466e; padding: 6px 13px; border-radius: 999px; font-size: 13px; font-weight: 700; }
  .steps { counter-reset: st; }
  .steps .card b { color: #10b981; }
  .faq .card { margin-bottom: 10px; }
  .adbox { margin: 26px auto; max-width: 970px; min-height: 90px; }
  footer { border-top: 1px solid #1e3a5f; padding: 22px; text-align: center; color: #64748b; font-size: 12.5px; }
  footer a { margin: 0 8px; }
  .tchip { padding: 4px 10px; border-radius: 999px; border: 1px solid #24466e; background: #12233f; color: #e2e8f0; font-size: 12px; cursor: pointer; font-weight: 700; }
  .appgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
  .apptile { display: block; background: #0b1329; border: 1px solid #1e3a5f; border-radius: 14px; padding: 18px 12px; text-align: center; }
  .apptile .ic { font-size: 30px; display: block; }
  .apptile b { color: #f8fafc; font-size: 14px; display: block; margin-top: 6px; }
  .apptile span.tx { color: #94a3b8; font-size: 12px; display: block; margin-top: 3px; }
  .apptile:hover { border-color: #10b981; }
  body.theme-ocean { background: #02141a; }
  body.theme-ocean .card, body.theme-ocean .nav { background: #06222b; border-color: #0e4a56; }
  body.theme-sunset { background: #170a1e; }
  body.theme-sunset .card, body.theme-sunset .nav { background: #22102e; border-color: #572a63; }
  body.theme-forest { background: #04150a; }
  body.theme-forest .card, body.theme-forest .nav { background: #0a2013; border-color: #1d4d2e; }
  body.theme-light { background: #eef2f7; color: #16233a; }
  body.theme-light .card, body.theme-light .nav { background: #ffffff; border-color: #c9d6e8; }
  body.theme-light .nav .logo, body.theme-light h1, body.theme-light h2.sec { color: #12233f; }
  body.theme-light .card p, body.theme-light .txt p { color: #5a6b84; }
"""


def _pub_bodies(bot, contact_email):
    home = """
  <div class="hero">
    <h1>Free Quiz Practice &amp; College Exams for <span>AP &amp; Telangana</span> Students</h1>
    <p>StudentUp helps students prepare for EAMCET, NEET, SSC, RRB and APPSC/TSPSC Group exams with daily quiz polls, previous-year questions and instant results — on Telegram, WhatsApp and right here in your browser.</p>
    <div class="cta">
      <a class="btn btn-g" href="__PORTAL__">🚀 Start Daily Quiz</a>
      <a class="btn btn-o" href="__BOT__" target="_blank" rel="noopener">🤖 Telegram Bot</a>
      <a class="btn btn-o" href="/study">📚 Study Guide</a>
    </div>
    <div class="exambox" id="exam-entry">
      <b>🏫 College Exam?</b>
      <div style="color:#94a3b8;font-size:13px;">Your teacher/organiser gave you an exam code? Enter it here — no app download needed.</div>
      <input id="exam-code" placeholder="e.g. CE-K7P2" maxlength="12">
      <button class="btn btn-g" style="width:100%;" onclick="var c=document.getElementById('exam-code').value.trim().toUpperCase(); if(c) location.href='/exam/'+c;">🚀 Open My Exam</button>
    </div>
  </div>
  __AD_HOME__
  <h2 class="sec">🚀 StudentUp Portal — Anni Okka Chota</h2>
  <div class="appgrid">
    <a class="apptile" href="__PORTAL__?go=quiz"><span class="ic">🧠</span><b>Smart Advanced Quiz</b><span class="tx">Daily Quiz · PYQ-first · Mee level ki taggattu adaptive questions</span></a>
    <a class="apptile" href="__PORTAL__?go=exams"><span class="ic">🔴</span><b>Live Exams</b><span class="tx">Real-time Live Exams + Weekly Grand Test (Sunday 10 AM) + Winners</span></a>
    <a class="apptile" href="__PORTAL__?go=mocks"><span class="ic">🎓</span><b>Exam-wise Quiz &amp; Mocks</b><span class="tx">SSC · RRB · Banking · Groups · Police — exam-wise mock tests</span></a>
    <a class="apptile" href="/papers"><span class="ic">📜</span><b>Previous Papers (PYQ)</b><span class="tx">Real previous-year paper sets — full test attempt cheyyandi</span></a>
    <a class="apptile" href="/exams"><span class="ic">🏛️</span><b>Exams Hub</b><span class="tx">Anni exam goals, PYQ counts mariyu repeat-topic trends</span></a>
    <a class="apptile" href="__PORTAL__"><span class="ic">🌟</span><b>All Portal Features</b><span class="tx">Personal Report · Toppers · Certificates · Answer Key Papers</span></a>
  </div>
  <h2 class="sec">✨ What you get</h2>
  <div class="grid">
    <div class="card"><h3>📊 Daily Quiz Polls</h3><p>Fresh practice questions every day on Telegram and WhatsApp channels — answer the poll, see the explanation, earn points.</p></div>
    <div class="card"><h3>📚 Previous-Year Questions</h3><p>A growing bank of 1,400+ previous-year and curated questions with sujet-wise and topic-wise practice.</p></div>
    <div class="card"><h3>🏫 College Exams in Browser</h3><p>Teachers create an exam, share one link or QR — students join with name + mobile and write the exam in the browser. No app needed.</p></div>
    <div class="card"><h3>🏆 Winners &amp; Certificates</h3><p>Daily winners, top-scorer certificates and district rankings keep practice fun and competitive.</p></div>
    <div class="card"><h3>🎯 Know Your Weak Topics</h3><p>Your profile shows accuracy and weak topics so you revise exactly what costs you marks.</p></div>
    <div class="card"><h3>⚡ Instant Results</h3><p>Speed points, negative-marking practice and instant answer review after every round and exam.</p></div>
  </div>
  <h2 class="sec">🚀 How it works</h2>
  <div class="grid steps">
    <div class="card"><b>Step 1</b><h3>Join free</h3><p>Open the Telegram bot or join a WhatsApp group through your college/class group link. Answering a quiz poll registers you automatically.</p></div>
    <div class="card"><b>Step 2</b><h3>Practice daily</h3><p>Attempt the daily polls and quizzes. Every correct answer earns points; fast correct answers earn bonus speed points.</p></div>
    <div class="card"><b>Step 3</b><h3>Write college exams</h3><p>Scan the QR your teacher shares, enter your name and mobile, and write the exam live in your browser.</p></div>
    <div class="card"><b>Step 4</b><h3>Track &amp; improve</h3><p>Check your rank, review every answer, and focus revision on your weak topics.</p></div>
  </div>
  <h2 class="sec">📖 Subjects we cover</h2>
  <div class="chips">
    <span class="chip">Mathematics</span><span class="chip">Physics</span><span class="chip">Chemistry</span>
    <span class="chip">Biology / Botany / Zoology</span><span class="chip">Indian Polity</span><span class="chip">History</span>
    <span class="chip">Geography</span><span class="chip">Economy</span><span class="chip">English</span>
    <span class="chip">Reasoning &amp; Aptitude</span><span class="chip">Current Affairs</span><span class="chip">General Science</span>
  </div>
  <h2 class="sec">❓ Frequently asked questions</h2>
  <div class="faq">
    <div class="card"><h3>Is StudentUp free?</h3><p>Yes. Daily practice, quizzes and college practice exams on StudentUp are free for students.</p></div>
    <div class="card"><h3>Do I need to install Telegram for college exams?</h3><p>No. College exams open directly in your mobile browser from the link or QR your organiser shares. Telegram is only an optional alternative.</p></div>
    <div class="card"><h3>Which exams does it help with?</h3><p>EAMCET (Engineering &amp; Medical streams), NEET basics, SSC, RRB and APPSC/TSPSC Group services — with subject-wise and topic-wise PYQs.</p></div>
    <div class="card"><h3>How do winners and points work?</h3><p>Correct answers earn points, faster correct answers earn bonus points, and toppers of each round are announced with certificates. Practice exams may include negative marking when the organiser enables it.</p></div>
  </div>
"""
    study = """
  <h2 class="sec">📚 Study Guide — how to prepare smart</h2>
  <div class="txt">
    <h3>🎓 EAMCET (AP &amp; TS)</h3>
    <p>EAMCET rewards speed with accuracy. Mathematics carries the highest weight in the engineering stream, so daily problem practice matters more than re-reading theory. Solve previous-year questions topic by topic, note the formulas you miss, and revise them weekly. StudentUp's topic-wise PYQ polls are built exactly for this routine.</p>
    <h3>🩺 NEET basics</h3>
    <p>Biology is half the paper. Read NCERT line by line, then test yourself with factual one-liners — Botany and Zoology diagrams included. Physics and Chemistry need formula + concept clarity; short daily quizzes beat one long weekly session.</p>
    <h3>🏛️ SSC, RRB &amp; APPSC/TSPSC Groups</h3>
    <p>Polity, History, Geography, Economy and Current Affairs decide these papers. Learn Polity article by article, keep a one-page timeline for History, and revise maps for Geography. Attempt mocks under time pressure — our polls simulate exactly that.</p>
    <h3>⏱️ Five habits that raise scores</h3>
    <p>1) Attempt questions daily, even if only ten. 2) Review every wrong answer the same day. 3) Track your weak topics and attack one per week. 4) Practise with negative marking so guessing becomes disciplined. 5) Sleep before the exam — memory consolidates at night.</p>
  </div>
  __AD_STUDY__
"""
    about = """
  <h2 class="sec">ℹ️ About StudentUp</h2>
  <div class="txt">
    <p>StudentUp is a free learning companion for students of Andhra Pradesh and Telangana preparing for competitive and entrance examinations. It began as a simple idea: students already spend time on Telegram and WhatsApp — why not turn those same apps into a daily study habit?</p>
    <p>Today StudentUp runs daily quiz polls, previous-year-question practice, district competitions, and full college exams that students can write in a mobile browser without installing any app. Teachers and colleges use it to conduct quick tests and get instant marks reports.</p>
    <p>Our question bank is built from previous-year papers and carefully curated items, organised by subject and topic, with explanations. We keep the experience simple: advanced preparation tools, presented in a way any student can use in the first minute.</p>
    <p>Questions about StudentUp? See the <a href="/contact">Contact</a> page.</p>
  </div>
"""
    privacy = """
  <h2 class="sec">🔐 Privacy Policy</h2>
  <div class="txt">
    <p><i>Last updated: 2026. This page explains what data StudentUp collects and why.</i></p>
    <h3>What we collect</h3>
    <p>When you use the Telegram bot, we receive your Telegram user id, display name and username. When you register or write a college web exam, you provide your name, mobile number and college. We record your quiz answers, scores and ranks to run competitions and exams.</p>
    <h3>How we use it</h3>
    <p>Data is used only to operate the service: registering you, delivering questions, computing scores, announcing winners, and giving organisers their marks reports. We do not sell personal data.</p>
    <h3>Cookies &amp; local storage</h3>
    <p>The web exam stores a session token in your browser's local storage so you can rejoin after a refresh. The organiser dashboard uses a login cookie. When advertising is enabled on our public pages, Google AdSense may set cookies to serve and measure ads; you can control this in your browser settings and via Google's ad settings.</p>
    <h3>Third parties</h3>
    <p>Messages are delivered through Telegram and WhatsApp, whose own privacy policies apply. Advertising on public pages (when enabled) is provided by Google AdSense.</p>
    <h3>Your choices</h3>
    <p>You may ask for your registration data to be corrected or deleted through the <a href="/contact">Contact</a> page or your college organiser.</p>
  </div>
"""
    terms = """
  <h2 class="sec">📜 Terms of Use</h2>
  <div class="txt">
    <p>By using StudentUp you agree to these simple terms.</p>
    <h3>Service</h3>
    <p>StudentUp provides free practice questions, quizzes and college practice exams for educational purposes. Scores on StudentUp are practice indicators only and are not official results of any examination board.</p>
    <h3>Fair use</h3>
    <p>Write exams yourself, without impersonating others. Organisers are responsible for the exams they create and for sharing links only with their intended students. Abuse, spam or attempts to disrupt the service may lead to removal.</p>
    <h3>Content</h3>
    <p>Previous-year questions remain the property of their respective examination boards and are used here for students' practice. Explanations and original content belong to StudentUp.</p>
    <h3>Changes</h3>
    <p>We may improve or change features over time. Continued use means you accept the updated terms.</p>
  </div>
"""
    contact = """
  <h2 class="sec">✉️ Contact</h2>
  <div class="txt">
    __CONTACT__
    <p>Students: for exam-related help (join problems, marks queries), contact your college organiser first — they created your exam and can see your report. For bot help, message the admin through the Telegram bot.</p>
    <p><a href="__BOT__" target="_blank" rel="noopener">🤖 Open the Telegram Bot</a></p>
  </div>
"""
    updates = """
  <h2 class="sec">📢 Exam Updates &amp; Notifications</h2>
  <div class="txt"><p>Official exam announcements, application dates and StudentUp news. Always verify dates on the official board website linked in each notice.</p></div>
  __NOTICES__
"""
    winners = """
  <h2 class="sec">🏆 Hall of Fame — StudentUp Winners</h2>
  <div class="txt"><p>Top scorers of our Weekly Grand Tests and Live Exams. Practice daily, rank daily — your name could be here next week.</p></div>
  __WINNERS__
"""
    toppers_pg = """
  <h2 class="sec">🏆 Toppers — Week · Month · Year</h2>
  <div class="txt"><p>StudentUp lo daily quiz, mock tests mariyu live exams raasi earn chesina points tho ee rankings vasthayi. Meeru kuda practice chesi ee list loki randi!</p></div>
  <h3 style="margin:18px 0 8px;">📅 Toppers of the Week</h3>
  __TOP_WEEK__
  <h3 style="margin:18px 0 8px;">🗓️ Toppers of the Month</h3>
  __TOP_MONTH__
  <h3 style="margin:18px 0 8px;">👑 Toppers of the Year</h3>
  __TOP_YEAR__
"""
    blog = """
  <h2 class="sec">📰 StudentUp Blog</h2>
  <div class="txt"><p>Exam guides, notifications mariyu study articles — mana main site <a href="__WPBASE__" target="_blank" rel="noopener">studentup.in</a> nunchi fresh ga ikkada kuda kanipisthayi.</p></div>
  __BLOG__
  <div class="card" style="margin-top:12px;"><p>Anni articles kosam: <a href="__WPBASE__" target="_blank" rel="noopener">studentup.in → Blog</a></p></div>
"""
    materials = """
  <h2 class="sec">📚 Study Materials &amp; Exam Plans</h2>
  <div class="txt"><p>StudentUp lo practice chese topics mariyu stream-wise study plans. Prati plan kinda unna topics ni portal lo Topic Practice tho daily revise cheyyandi.</p></div>
  __MATERIALS__
  <div class="card" style="margin-top:14px;"><h3>🚀 Ippude Start Cheyyandi</h3><p>Daily Quiz + Topic Practice + Weekly Grand Test — anni free. Portal open chesi, register ayyi, mee goal select cheskondi.</p><p style="margin-top:8px;"><a href="/portal">🎓 Student Portal Open Cheyyandi →</a></p></div>
"""
    papers = """
  <h2 class="sec">📜 Previous Year Papers (Real PYQ)</h2>
  <div class="txt"><p>Nijamaina previous-year exam questions — anni StudentUp bank lo nunche vastayi, counts kuda nijame (unna papers matrame chupistam). Full paper ni timer tho attempt chesi score, answer key, review teeskovachu.</p></div>
  __PAPERS__
  <div class="card" style="margin-top:14px;"><h3>🚀 Paper Attempt Cheyyandi</h3><p>Portal lo register ayyi — Previous Papers card lo Start nokkandi. Weekly Grand Test (Sunday 10 AM) kuda PYQ-first papers eh.</p><p style="margin-top:8px;"><a href="/portal">🎓 Student Portal →</a></p></div>
"""
    exams = """
  <h2 class="sec">🎓 Exams Hub — anni goals okka chota</h2>
  <div class="txt"><p>TSPSC, APPSC, SSC, Banking, Railway, Police, Defence — prathi goal ki daily quiz, mocks, live exams, previous papers. Mee goal select cheskunte paper aa exam pattern lone vasthundi.</p></div>
  __EXAMS__
  <div class="card" style="margin-top:14px;"><h3>🧠 Smart ga Start Cheyyandi</h3><p>Exam goal select cheyyandi → Daily Quiz → Smart Practice (mee level ki) → Weekly Grand Test. Brain readiness score mee preparation ni measure chestundi.</p><p style="margin-top:8px;"><a href="/portal">🎓 Portal Open Cheyyandi →</a></p></div>
"""
    return {"home": home, "study": study, "about": about,
            "papers": papers, "exams": exams,
            "privacy": privacy, "terms": terms, "contact": contact,
            "updates": updates, "winners": winners, "toppers": toppers_pg,
            "materials": materials}


def public_page(handler, page):
    """Full public page HTML (ads ONLY here — never on exam/session pages)."""
    bot = ("https://t.me/" + _bot_username()) if page in ("home", "about", "contact") else "#"
    email = config.env("PUBLIC_CONTACT_EMAIL", "").strip()
    contact_line = (f'<p>Email: <a href="mailto:{email}">{email}</a></p>' if email
                    else "<p>Reach the StudentUp team through the Telegram bot admin or your college organiser.</p>")
    titles = {"home": "StudentUp — Free Quiz Practice & College Exams (AP & Telangana)",
              "study": "Study Guide — StudentUp",
              "about": "About — StudentUp",
              "privacy": "Privacy Policy — StudentUp",
              "terms": "Terms of Use — StudentUp",
              "contact": "Contact — StudentUp",
              "updates": "Exam Updates & Notifications — StudentUp",
              "winners": "Hall of Fame — StudentUp Winners",
              "toppers": "Toppers of Week, Month & Year — StudentUp",
              "materials": "Study Materials & Exam Plans — StudentUp",
              "blog": "Blog — StudentUp Exam Guides & Articles",
              "papers": "Previous Year Papers (PYQ) — StudentUp",
              "exams": "Exams Hub — StudentUp"}
    bodies = _pub_bodies(bot, email)
    body = bodies.get(page, bodies["home"])
    try:
        _wf = portal.winners_public(8)
        _whtml = "".join(
            f'<div class="card" style="margin-bottom:10px;"><h3>🏆 {_w["title"]}</h3>'
            + "".join(
                f'<p>{["🥇","🥈","🥉"][i] if i < 3 else ""} <b>{ww["name"]}</b> · {ww["district"]} · ✅ {ww["correct"]}/{ww["total"]}</p>'
                for i, ww in enumerate(_w["winners"])) + "</div>"
            for _w in _wf) or '<div class="card"><p>First Weekly Grand Test winners ikkade vastaru — Sunday 10 AM ready ga undandi!</p></div>'
    except Exception:
        _whtml = '<div class="card"><p>Winners coming soon.</p></div>'
    try:
        _tops = portal.toppers_all(Members())

        def _trows(rows):
            if not rows:
                return '<div class="card"><p>Inka ee period lo points levu — first topper meeru avvandi!</p></div>'
            return "".join(
                f'<div class="card" style="margin-bottom:8px;"><p>{["🥇", "🥈", "🥉"][i] if i < 3 else "#" + str(i + 1)} <b>{r["name"]}</b> · {r["district"]} · ⭐ {r["pts"]} points · ✍️ {r["answers"]} correct</p></div>'
                for i, r in enumerate(rows))
        body = (body.replace("__TOP_WEEK__", _trows(_tops["week"]))
                    .replace("__TOP_MONTH__", _trows(_tops["month"]))
                    .replace("__TOP_YEAR__", _trows(_tops["year"])))
    except Exception:
        body = (body.replace("__TOP_WEEK__", '<div class="card"><p>Loading…</p></div>')
                    .replace("__TOP_MONTH__", "").replace("__TOP_YEAR__", ""))
    try:
        _posts = _fetch_wp_posts(12)
        _bhtml = "".join(
            f'<div class="card" style="margin-bottom:10px;"><h3><a href="{_p["url"]}" target="_blank" rel="noopener">{_p["title"]}</a></h3>'
            f'<p>{_p["excerpt"]}…</p><p class="muted" style="margin-top:6px;">{_p["date"]} · studentup.in lo chadavandi ↗</p></div>'
            for _p in _posts) or '<div class="card"><p>Articles loading… main site lo chudandi: <a href="' + _wp_base() + '">studentup.in</a></p></div>'
    except Exception:
        _bhtml = '<div class="card"><p>Articles loading…</p></div>'
    body = body.replace("__BLOG__", _bhtml).replace("__WPBASE__", _wp_base())
    try:
        _topics = portal.topics_list(24)
        _plans = [("🏛️ Groups (APPSC/TSPSC)", "Polity articles, AP/TG History, Geography maps, Economy basics, Current Affairs — daily 20 questions chalu."),
                  ("📄 SSC", "Reasoning speed, Maths shortcuts, English vocab, GK — mock tests tho time management nerchukondi."),
                  ("🏦 Banking", "Quant + Reasoning daily practice, English, Banking awareness — topic-wise ga strong avvandi."),
                  ("🚆 Railway (RRB)", "Maths, Reasoning, General Science — PYQs repeat avthayi, previous papers must."),
                  ("👮 Police & Defence", "GK, Maths, Reasoning + physical preparation parallel ga plan cheskondi.")]
        _mhtml = "".join(f'<div class="card" style="margin-bottom:10px;"><h3>{t}</h3><p>{dsc}</p></div>' for t, dsc in _plans)
        _mhtml += '<h3 style="margin:16px 0 8px;">🏷️ Portal lo Practice Cheyyagalige Topics</h3><div class="chips">' + "".join(f'<a class="chip" href="/portal">{t}</a>' for t in _topics) + '</div>'
    except Exception:
        _mhtml = '<div class="card"><p>Materials loading…</p></div>'
    body = body.replace("__MATERIALS__", _mhtml)
    try:
        _papers = portal.paper_catalog()
        _phtml = "".join(
            f'<div class="card" style="margin-bottom:10px;"><h3>📜 {r["label"]}</h3>'
            f'<p>{r["count"]} real previous-year questions · {", ".join(r["channels"]) or r["exam"]}'
            + (f'<br>🏷️ {", ".join(r.get("topics") or [])}' if r.get("topics") else "")
            + (' · <b>Mini set</b>' if r.get("size") == "mini" else "")
            + '</p>'
            f'<p style="margin-top:6px;"><a href="/portal">Full Paper Attempt Cheyyandi →</a></p></div>'
            for r in _papers) or '<div class="card"><p>Papers harvest avuthunnayi — prathi roju kottha sets add avuthayi. First sets thondaralo ikkade!</p></div>'
        _cov = portal.pyq_coverage_public() if hasattr(portal, "pyq_coverage_public") else {}
        _total_pyq = sum(r["count"] for r in _papers)
        _phtml = (f'<div class="card" style="margin-bottom:10px;"><h3>📊 Bank lo ippudu {_total_pyq} real PYQ questions · {len(_papers)} paper sets</h3>'
                  '<p>Harvest prathi roju (02:15 + 13:45) kottha official papers testhundi — count daily ga peruguthundi. Portal lo Syllabus Tracker, Personal Coach, Negative-marking mocks kuda unnayi!</p></div>') + _phtml
    except Exception:
        _phtml = '<div class="card"><p>Papers loading…</p></div>'
    body = body.replace("__PAPERS__", _phtml)
    try:
        _goals = portal.GOALS
        _stock = portal.exam_stock()
        _trends = {k: portal.pyq_trends(k) for k in _goals}
        _ehtml = "".join(
            f'<div class="card" style="margin-bottom:10px;"><h3>{v["label"]}</h3>'
            f'<p>📜 {_stock.get(k, {}).get("pyq", 0)} real PYQ questions in bank · Daily Quiz + Mocks + Live Exams</p>'
            + (f'<p style="margin-top:4px;">📈 Repeat ayye topics: '
               + ", ".join(f'{t["topic"]} ({t["pyq"]})'
                           for t in _trends.get(k, {}).get("topics", [])[:3])
               + '</p>' if _trends.get(k, {}).get("topics") else '')
            + f'<p style="margin-top:6px;"><a href="__PORTAL__?go=hub&goal={k}">🎓 {v["label"]} Hub — PYQ Mock & Drill →</a> · <a href="/papers">📜 Papers</a></p></div>'
            for k, v in _goals.items())
    except Exception:
        _ehtml = '<div class="card"><p>Exams loading…</p></div>'
    body = body.replace("__EXAMS__", _ehtml)
    body = body.replace("__WINNERS__", _whtml)
    try:
        _nts = portal.list_notices(20)
        _nhtml = "".join(
            f'<div class="card" style="margin-bottom:10px;"><h3>📢 {_nt["title"]}</h3>'
            f'<p>{_nt["body"]}</p><p style="margin-top:6px;"><span class="muted">{_nt["date"]}</span>'
            + (f' · <a href="{_nt["link"]}" target="_blank" rel="noopener">Official link \u2197</a>' if _nt.get("link") else "") + "</p></div>"
            for _nt in _nts) or '<div class="card"><p>No updates yet.</p></div>'
    except Exception:
        _nhtml = '<div class="card"><p>No updates yet.</p></div>'
    body = (body.replace("__NOTICES__", _nhtml)
            .replace("__BOT__", bot).replace("__CONTACT__", contact_line)
                .replace("__AD_HOME__", _ad_slot("HOME"))
                .replace("__AD_STUDY__", _ad_slot("STUDY")))
    base = _public_base(handler)
    canonical = (base + ("/" if page == "home" else "/" + page)) if base else ""
    shell = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#0b1329">
<meta name="description" content="StudentUp: free quiz polls, previous-year questions and browser-based college exams for AP & Telangana students (EAMCET, NEET, SSC, RRB, APPSC/TSPSC).">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite","name":"StudentUp","url":"https://studentup.in","description":"Free daily quiz, previous-year questions (PYQ), mock tests and live exams for AP & Telangana students.","potentialAction":{"@type":"SearchAction","target":"https://studentup.in/papers","query-input":"required name=query"}}</script>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[{"@type":"Question","name":"StudentUp lo previous-year questions (PYQ) unnaya?","acceptedAnswer":{"@type":"Answer","text":"Avunu — bank lo real previous-year questions unnayi, prathi paper exam-wise sets ga attempt cheyyavachu, counts kuda open ga chupistam."}},{"@type":"Question","name":"StudentUp free aa?","acceptedAnswer":{"@type":"Answer","text":"Avunu, Daily Quiz, Mock Tests, Previous Papers, Live Exams anni free."}},{"@type":"Question","name":"Weekly Grand Test eppudu?","acceptedAnswer":{"@type":"Answer","text":"Prathi Sunday 10:00 AM — 40 questions, 60 minutes, PYQ-first paper, winners certificate tho."}}]}</script>
__CANONICAL____ADSHEAD__
<style>__CSS__</style>
</head>
<body>
<div class="nav">
  <span class="logo">🎓 StudentUp</span>
  <a href="/">🏠 Home</a><a href="/study">📚 Study Guide</a><a href="/about">ℹ️ About</a>
  <a href="/privacy">🔐 Privacy</a><a href="/blog">📰 Blog</a><a href="/materials">📚 Materials</a><a href="/updates">📢 Updates</a><a href="/winners">🏆 Winners</a><a href="/toppers">👑 Toppers</a><a href="/papers">📜 Papers</a><a href="/exams">🎓 Exams</a><a href="/contact">✉️ Contact</a>
  <a class="login" href="/portal">🚀 Student Portal</a>
  <a class="login" href="/login">🔑 Organiser Login</a>
  <span>🎨 <button class="tchip" onclick="setSiteTheme('')">🌙</button> <button class="tchip" onclick="setSiteTheme('ocean')">🌊</button> <button class="tchip" onclick="setSiteTheme('sunset')">🌅</button> <button class="tchip" onclick="setSiteTheme('forest')">🌲</button> <button class="tchip" onclick="setSiteTheme('light')">☀️</button></span>
</div>
<div class="wrap">__BODY__</div>
<script>
function setSiteTheme(t) { document.body.className = t ? ('theme-' + t) : ''; localStorage.setItem('su_theme', t); }
(function () { var t = localStorage.getItem('su_theme'); if (t) document.body.className = 'theme-' + t; })();
setInterval(cdTick, 30000);
if ('serviceWorker' in navigator) { try { navigator.serviceWorker.register('/sw.js'); } catch (e) {} }
</script>
<footer>
  © StudentUp · Free study practice for AP &amp; Telangana students<br>
  <a href="/about">About</a><a href="/privacy">Privacy Policy</a><a href="/terms">Terms</a><a href="/contact">Contact</a>
</footer>
</body>
</html>"""
    portal_url = config.env("PORTAL_BASE_URL", "").strip() or "/portal"
    body = body.replace("__PORTAL__", portal_url)
    return (shell.replace("__TITLE__", titles.get(page, titles["home"]))
                 .replace("__CANONICAL__", f'<link rel="canonical" href="{canonical}">' if canonical else "")
                 .replace("__ADSHEAD__", _adsense_head())
                 .replace("__CSS__", _PUB_CSS)
                 .replace("__BODY__", body))


def robots_txt(handler):
    base = _public_base(handler)
    lines = ["User-agent: *", "Allow: /", "Disallow: /api/", "Disallow: /exam/"]
    if base:
        lines.append(f"Sitemap: {base}/sitemap.xml")
    return "\n".join(lines) + "\n"


def sitemap_xml(handler):
    base = _public_base(handler)
    urls = ["/", "/study", "/blog", "/materials", "/updates", "/winners",
            "/toppers", "/papers", "/exams", "/about", "/privacy", "/terms",
            "/contact"]
    items = "".join(f"<url><loc>{base}{u}</loc></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + items + "</urlset>")


def _bot_username():
    """The bot students must land on: .env BOT_USERNAME → live getMe lookup
    (cached 1h) → legacy fallback. QR/join links built with a wrong bot name
    are the #1 on-site failure, so never guess silently."""
    if getattr(config, "BOT_USERNAME", ""):
        return config.BOT_USERNAME
    if _BOT_USERNAME_CACHE["name"] and time.time() - _BOT_USERNAME_CACHE["ts"] < 3600:
        return _BOT_USERNAME_CACHE["name"]
    if _BOT_USERNAME_CACHE.get("tried") and time.time() - _BOT_USERNAME_CACHE["ts"] < 300:
        return "StudentUpBot"   # 🛠️ 190X: failed lookup 5-min cache (prathi request ki API hit avvadhu) — fallback tho consistent
    name = ""
    try:
        r = Telegram()._call("getMe", {}) or {}
        name = (r.get("result") or {}).get("username", "") or ""
    except Exception:
        name = ""
    _BOT_USERNAME_CACHE.update(ts=time.time(), tried=True)
    if name:
        _BOT_USERNAME_CACHE.update(name=name, ts=time.time())
        try:
            config.BOT_USERNAME = name
        except Exception:
            pass
    return name or "StudentUpBot"

PORT = int(config.env("DASHBOARD_PORT", "5000"))

# =====================================================================
# 🔒 DASHBOARD ACCESS LOCK — only the admin can open this panel.
# Password lives in data/dashboard_auth.json (or env DASHBOARD_PASSWORD).
# Login issues a 30-day HttpOnly cookie token; everything else is 401.
# =====================================================================
import secrets as _secrets

AUTH_FILE = config.DATA / "dashboard_auth.json"
LOGIN_AUDIT_FILE = config.DATA / "login_audit.json"
_START_TS = time.time()


def _log_login_attempt(ip: str, ok: bool):
    """🔐 Security audit: record every login attempt (success & failure)."""
    try:
        d = {"attempts": []}
        if LOGIN_AUDIT_FILE.exists():
            loaded = json.loads(LOGIN_AUDIT_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("attempts"), list):
                d = loaded
        d["attempts"].append({
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "ip": str(ip)[:60],
            "ok": bool(ok),
        })
        d["attempts"] = d["attempts"][-200:]
        LOGIN_AUDIT_FILE.write_text(json.dumps(d, indent=1), encoding="utf-8")
    except Exception:
        pass


def _recent_logins(limit: int = 8) -> list:
    try:
        if LOGIN_AUDIT_FILE.exists():
            d = json.loads(LOGIN_AUDIT_FILE.read_text(encoding="utf-8"))
            return list(reversed(d.get("attempts", [])[-limit:]))
    except Exception:
        pass
    return []
DEFAULT_DASH_PASSWORD = "studentup123"


def _load_auth() -> dict:
    try:
        if AUTH_FILE.exists():
            d = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
            d.setdefault("password", DEFAULT_DASH_PASSWORD)
            d.setdefault("tokens", [])
            return d
    except Exception:
        pass
    d = {"password": DEFAULT_DASH_PASSWORD, "tokens": []}
    _save_auth(d)
    return d


def _save_auth(d: dict):
    try:
        AUTH_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


def _dash_password() -> str:
    envp = os.environ.get("DASHBOARD_PASSWORD", "").strip()
    return envp if envp else _load_auth().get("password", DEFAULT_DASH_PASSWORD)


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="te">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🔒 StudentUp — Admin Login</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:radial-gradient(circle at 30% 20%, #0f2040 0%, #050811 70%);
         font-family:'Segoe UI', system-ui, sans-serif; color:#e2e8f0; }
  .card { background:#0b1329; border:1px solid #1e3a5f; border-radius:16px; padding:36px 32px;
          width:min(380px, 90vw); box-shadow:0 20px 60px rgba(0,0,0,0.6); text-align:center; }
  .lock { font-size:46px; margin-bottom:10px; }
  h1 { font-size:20px; margin:0 0 6px; color:#38bdf8; }
  p  { font-size:13px; color:#94a3b8; margin:0 0 20px; line-height:1.6; }
  input { width:100%; box-sizing:border-box; padding:12px 14px; font-size:16px; letter-spacing:2px;
          background:#050811; color:#f8fafc; border:1px solid #1e3a5f; border-radius:10px; outline:none; text-align:center; }
  input:focus { border-color:#38bdf8; }
  button { width:100%; margin-top:14px; padding:12px; font-size:15px; font-weight:800; border:none;
           border-radius:10px; background:linear-gradient(90deg, #10b981, #38bdf8); color:#050811; cursor:pointer; }
  button:hover { filter:brightness(1.1); }
  .err { color:#f87171; font-size:13px; font-weight:700; min-height:18px; margin-top:12px; }
  .hint { margin-top:18px; font-size:11px; color:#475569; }
</style>
</head>
<body>
  <div class="card">
    <div class="lock">🔒</div>
    <h1>StudentUp Admin Panel</h1>
    <p>ఈ డాష్‌బోర్డ్ లాక్ చేయబడింది.<br>Admin password ఎంటర్ చేస్తేనే లోపలికి వెళ్ళగలరు.</p>
    <input type="password" id="pw" placeholder="Admin Password" autofocus
           onkeydown="if(event.key==='Enter')doLogin()">
    <button onclick="doLogin()">🔓 Unlock Dashboard</button>
    <div class="err" id="err"></div>
    <div class="hint">Default password: <b>studentup123</b> — login అయ్యాక 🔑 బటన్‌తో వెంటనే మార్చుకోండి!</div>
  </div>
<script>
async function doLogin() {
  const pw = document.getElementById('pw').value;
  const err = document.getElementById('err');
  err.innerText = '';
  try {
    const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({password: pw})});
    const d = await r.json();
    if (d.ok) { location.href = '/'; }
    else { err.innerText = '❌ తప్పు పాస్‌వర్డ్! Wrong password.'; document.getElementById('pw').value=''; }
  } catch(e) { err.innerText = '❌ Server error: ' + e; }
}
</script>
</body>
</html>"""

PORTAL_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StudentUp Portal — Daily Quiz & Mock Tests</title>
<link rel="manifest" href="/manifest.json">
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { min-height: 100vh; background: radial-gradient(circle at 30% 10%, #12315e 0%, #050811 70%); color: #e2e8f0; padding: 16px 12px 50px; }
  .wrap { max-width: 560px; margin: 0 auto; }
  .brand { text-align: center; font-size: 22px; font-weight: 800; color: #f8fafc; margin: 6px 0 14px; }
  .brand span { display: block; font-size: 11px; color: #38bdf8; font-weight: 600; letter-spacing: 1.5px; margin-top: 3px; }
  .card { background: #0b1329; border: 1px solid #1e3a5f; border-radius: 16px; padding: 18px 16px; margin-bottom: 14px; box-shadow: 0 10px 30px rgba(0,0,0,.4); }
  h2 { font-size: 17px; margin-bottom: 8px; }
  h3 { font-size: 13.5px; color: #38bdf8; margin: 4px 0 8px; }
  .muted { color: #94a3b8; font-size: 12.5px; line-height: 1.6; }
  label { display: block; font-size: 12.5px; font-weight: 700; margin: 12px 0 5px; }
  input, select { width: 100%; padding: 12px 14px; font-size: 16px; background: #050811; color: #f8fafc; border: 1px solid #1e3a5f; border-radius: 10px; outline: none; }
  .btn-main { width: 100%; margin-top: 14px; padding: 14px; font-size: 15.5px; font-weight: 800; border: none; border-radius: 11px; background: linear-gradient(90deg, #10b981, #38bdf8); color: #04121f; cursor: pointer; }
  .btn-alt { width: 100%; margin-top: 9px; padding: 11px; font-size: 14px; font-weight: 700; border: 1px solid #24466e; border-radius: 11px; background: #12233f; color: #e2e8f0; cursor: pointer; }
  .err { color: #f87171; font-size: 13px; font-weight: 700; min-height: 18px; margin-top: 8px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .chip { background: #12233f; border: 1px solid #24466e; padding: 5px 11px; border-radius: 999px; font-size: 12px; font-weight: 700; }
  .chip.gold { border-color: #a16207; color: #facc15; }
  .chip.weak { border-color: #7f1d1d; color: #fca5a5; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }
  .mockbtn { padding: 13px 8px; border-radius: 12px; border: 1.5px solid #24466e; background: #0f1e38; color: #e2e8f0; font-size: 13.5px; font-weight: 700; cursor: pointer; }
  .mockbtn.mine { border-color: #10b981; }
  .trow { display: flex; gap: 8px; align-items: center; padding: 7px 10px; background: #0f1e38; border-radius: 10px; margin-top: 6px; font-size: 13px; }
  .trow b { flex: 1; }
  .qte { font-size: 16.5px; font-weight: 700; line-height: 1.55; }
  body.lang-te .qen { display: none; }
  body.lang-en .qte { display: none; }
  .qen { font-size: 14px; color: #a5c4e8; line-height: 1.55; margin-top: 5px; }
  .opt { display: block; width: 100%; text-align: left; margin-top: 9px; padding: 13px 14px; font-size: 14.5px; font-weight: 600; background: #0f1e38; color: #e2e8f0; border: 1.5px solid #24466e; border-radius: 12px; cursor: pointer; }
  .opt.picked { border-color: #38bdf8; background: #12315e; }
  .opt.right { border-color: #10b981; }
  .opt.wrong { border-color: #ef4444; }
  .opt:disabled { opacity: .8; cursor: default; }
  .feedback { min-height: 22px; margin-top: 11px; font-size: 13.5px; font-weight: 700; }
  .score-big { font-size: 42px; font-weight: 800; text-align: center; color: #10b981; }
  .rrow { padding: 9px 11px; border-radius: 10px; margin-top: 6px; font-size: 12.5px; line-height: 1.55; background: #0f1e38; }
  .rrow.ok { border-left: 4px solid #10b981; } .rrow.bad { border-left: 4px solid #ef4444; }
  .timer { color: #facc15; font-weight: 800; }
  .tchip { padding: 6px 11px; border-radius: 999px; border: 1px solid #24466e; background: #12233f; color: #e2e8f0; font-size: 13px; cursor: pointer; }
  .tchip.on { border-color: #10b981; color: #10b981; }
  /* 🎨 220X THEME STUDIO: accent engine — themes set --acc, students
     can override accent with one tap; everything glows from --acc. */
  body { --acc: #10b981; --acc2: #065f46; transition: background .35s ease, color .35s ease; }
  body.theme-ocean { --acc: #22d3ee; --acc2: #0e7490; }
  body.theme-sunset { --acc: #fb923c; --acc2: #9a3412; }
  body.theme-forest { --acc: #4ade80; --acc2: #166534; }
  body.theme-light { --acc: #2563eb; --acc2: #1e40af; }
  body.theme-royal { background: radial-gradient(circle at 30% 10%, #3f3005 0%, #0a0803 70%); --acc: #facc15; --acc2: #a16207; }
  body.theme-royal .card { background: #171204; border-color: #57500d; }
  body.theme-grape { background: radial-gradient(circle at 30% 10%, #4c1d95 0%, #12041f 70%); --acc: #c084fc; --acc2: #7e22ce; }
  body.theme-grape .card { background: #1d0b31; border-color: #4c1d95; }
  body.theme-rose { background: radial-gradient(circle at 30% 10%, #881337 0%, #1c050c 70%); --acc: #fb7185; --acc2: #be123c; }
  body.theme-rose .card { background: #2a0a14; border-color: #881337; }
  /* 🎨 300X THEME STUDIO PRO: aurora/paper/exam-focus + accessibility
     (font size + calm mode). Advanced inside, one tap outside. */
  body.theme-aurora { background: radial-gradient(circle at 20% 0%, #134e4a 0%, #1e1b4b 55%, #070312 100%); --acc: #5eead4; --acc2: #7c3aed; }
  body.theme-aurora .card { background: #0d1526; border-color: #155e63; }
  body.theme-paper { background: #f6efe0; color: #2f2417; --acc: #b45309; --acc2: #92400e; }
  body.theme-paper .card { background: #fffaf0; border-color: #d9c9a3; }
  body.theme-paper .brand, body.theme-paper h2, body.theme-paper .qte { color: #2f2417; }
  body.theme-paper .muted { color: #7a6a52; }
  body.theme-paper input, body.theme-paper select { background: #fffdf7; color: #2f2417; border-color: #d9c9a3; }
  body.theme-paper .opt, body.theme-paper .trow, body.theme-paper .rrow { background: #fdf6e3; color: #2f2417; border-color: #d9c9a3; }
  body.theme-paper .chip { background: #f3e8cf; border-color: #d9c9a3; color: #6b4e16; }
  body.theme-paper .qen { color: #6b5636; }
  body.theme-focus { background: #000000; --acc: #facc15; --acc2: #a16207; }
  body.theme-focus .card { background: #0a0a0a; border-color: #854d0e; }
  body.theme-focus .brand { text-shadow: none; }
  body.font-s .qte { font-size: 15px; } body.font-s .qen { font-size: 12.5px; } body.font-s .opt { font-size: 13px; }
  body.font-l .qte { font-size: 19px; } body.font-l .qen { font-size: 16px; } body.font-l .opt { font-size: 16.5px; }
  body.calm *, body.calm *::before, body.calm *::after { transition: none !important; animation: none !important; }
  .tchip.on { border-color: var(--acc); color: var(--acc); }
  .btn { background: linear-gradient(135deg, var(--acc), var(--acc2)); }
  .btn-alt { border-color: var(--acc2); }
  h2.sec, .brand span { color: var(--acc); }
  .brand { text-shadow: 0 0 22px var(--acc2); }
  .chip.gold { border-color: var(--acc); color: var(--acc); }
  .tdot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 4px; vertical-align: -1px; }
  .asw { width: 22px; height: 22px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; padding: 0; }
  .asw.on { border-color: #f8fafc; transform: scale(1.15); }
  .card { transition: background .35s ease, border-color .35s ease; }
  body.theme-ocean { background: radial-gradient(circle at 30% 10%, #065a60 0%, #02141a 70%); }
  body.theme-ocean .card { background: #06222b; border-color: #0e4a56; }
  body.theme-sunset { background: radial-gradient(circle at 30% 10%, #7c2d12 0%, #170a1e 70%); }
  body.theme-sunset .card { background: #22102e; border-color: #572a63; }
  body.theme-forest { background: radial-gradient(circle at 30% 10%, #14532d 0%, #04150a 70%); }
  body.theme-forest .card { background: #0a2013; border-color: #1d4d2e; }
  body.theme-light { background: #eef2f7; color: #16233a; }
  body.theme-light .card { background: #ffffff; border-color: #c9d6e8; }
  body.theme-light .brand, body.theme-light h2, body.theme-light .qte { color: #12233f; }
  body.theme-light .muted { color: #5a6b84; }
  body.theme-light input, body.theme-light select { background: #ffffff; color: #16233a; border-color: #b9c9de; }
  body.theme-light .opt, body.theme-light .trow, body.theme-light .rrow { background: #f2f6fc; color: #16233a; border-color: #b9c9de; }
  body.theme-light .chip { background: #e4edf8; border-color: #b9c9de; color: #26436b; }
  body.theme-light .qen { color: #3c5a80; }
  .tbar { height: 8px; background: #12233f; border-radius: 99px; overflow: hidden; }
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">🎓 StudentUp <span>DAILY QUIZ · MOCK TESTS · LEADERS</span></div>
  <div class="row" style="justify-content:center; margin-bottom:12px;">
    <span class="muted">🎨 Theme:</span>
    <button class="tchip" data-th="" onclick="setTheme('')">🌙 Midnight</button>
    <button class="tchip" data-th="ocean" onclick="setTheme('ocean')">🌊 Ocean</button>
    <button class="tchip" data-th="sunset" onclick="setTheme('sunset')">🌅 Sunset</button>
    <button class="tchip" data-th="forest" onclick="setTheme('forest')">🌲 Forest</button>
    <button class="tchip" data-th="light" onclick="setTheme('light')">☀️ Light</button>
    <button class="tchip" data-th="royal" onclick="setTheme('royal')"><span class="tdot" style="background:linear-gradient(135deg,#facc15,#a16207);"></span>👑 Royal</button>
    <button class="tchip" data-th="grape" onclick="setTheme('grape')"><span class="tdot" style="background:linear-gradient(135deg,#c084fc,#7e22ce);"></span>🍇 Grape</button>
    <button class="tchip" data-th="rose" onclick="setTheme('rose')"><span class="tdot" style="background:linear-gradient(135deg,#fb7185,#be123c);"></span>🌹 Rose</button>
    <button class="tchip" data-th="aurora" onclick="setTheme('aurora')"><span class="tdot" style="background:linear-gradient(135deg,#5eead4,#7c3aed);"></span>🌌 Aurora</button>
    <button class="tchip" data-th="paper" onclick="setTheme('paper')"><span class="tdot" style="background:linear-gradient(135deg,#f6efe0,#b45309);"></span>📜 Paper</button>
    <button class="tchip" data-th="focus" onclick="setTheme('focus')"><span class="tdot" style="background:linear-gradient(135deg,#facc15,#000000);"></span>🎯 Exam Focus</button>
    <button class="tchip" data-th="auto" onclick="setTheme('auto')">🌓 Auto</button>
  </div>
  <div class="row" style="justify-content:center; margin-bottom:12px; gap:6px; align-items:center;">
    <span class="muted">🔠 Font:</span>
    <button class="tchip" data-fs="s" onclick="setFont('s')">A-</button>
    <button class="tchip" data-fs="m" onclick="setFont('m')">A</button>
    <button class="tchip" data-fs="l" onclick="setFont('l')">A+</button>
    <button class="tchip" data-calm="1" onclick="toggleCalm()">🌿 Calm</button>
  </div>
  <div class="row" style="justify-content:center; margin-bottom:12px; gap:6px; align-items:center;">
    <span class="muted">✨ Accent:</span>
    <button class="asw" data-acc="#10b981" style="background:#10b981;" onclick="setAccent('#10b981')" aria-label="emerald accent"></button>
    <button class="asw" data-acc="#38bdf8" style="background:#38bdf8;" onclick="setAccent('#38bdf8')" aria-label="sky accent"></button>
    <button class="asw" data-acc="#f59e0b" style="background:#f59e0b;" onclick="setAccent('#f59e0b')" aria-label="amber accent"></button>
    <button class="asw" data-acc="#f472b6" style="background:#f472b6;" onclick="setAccent('#f472b6')" aria-label="pink accent"></button>
    <button class="asw" data-acc="#a78bfa" style="background:#a78bfa;" onclick="setAccent('#a78bfa')" aria-label="violet accent"></button>
    <button class="asw" data-acc="#facc15" style="background:#facc15;" onclick="setAccent('#facc15')" aria-label="gold accent"></button>
  </div>

  <!-- register -->
  <div id="view-reg" class="card" style="display:none;">
    <h2>👋 StudentUp loki welcome!</h2>
    <p class="muted">Okka sari register avandi — Daily Quiz, Mock Tests, mee personal report & leaderboards anni ready. Data mee bot account tho kuda link avthundi.</p>
    <p class="muted" style="margin-top:6px;">🔐 <b>No-VPS mode:</b> kindha checkbox pedithe mee progress signed token roopam lo mee phone lone untundi — separate server database akkarledu.</p>
    <label style="display:flex; gap:8px; align-items:center; margin-top:8px;"><input type="checkbox" id="r-stateless" style="width:auto;"> 🔐 Stateless (No-VPS) mode — progress naa phone lone save avvali</label>
    <p class="muted" style="margin-top:4px;">Browser data clear ayithe progress povachu — ranks/prizes ki server-signed receipts vastayi.</p>
    <label>🏆 Meeru Ae Exam Kosam Prepare Avthunnaru?</label>
    <select id="r-goal"></select>
    <label>Mee Peru (Full Name)</label>
    <input id="r-name" placeholder="e.g. Priya Sharma" autocomplete="name">
    <label>Mee District</label>
    <select id="r-district"><option value="">— District select cheyyandi —</option></select>
    <label>Mobile Number (WhatsApp)</label>
    <input id="r-phone" inputmode="numeric" maxlength="13" placeholder="10-digit mobile" autocomplete="tel">
    <button class="btn-main" onclick="doRegister()">🚀 Register & Start</button>
    <div id="reg-err" class="err"></div>
  </div>

  <!-- home -->
  <div id="view-home" style="display:none;">
    <div class="card">
      <h2 id="hello">👋</h2>
      <div class="row" id="mychips"></div>
      <div id="level-bar" style="margin-top:8px;"></div>
      <div class="row" id="goal-chips" style="margin-top:9px;"></div>
      <p class="muted" id="goal-stock" style="margin-top:6px;"></p>
      <div id="offline-bar" style="display:none; margin-top:8px; font-size:12.5px;">📴 Offline mode — last saved data chupisthunnam. Net ragane answers auto-sync avthayi.</div>
      <div id="bot-link-card" style="margin-top:10px;"></div>
      <button class="btn-alt" style="width:100%; margin-top:8px;" onclick="shareProgress()">📤 Naa Progress Share Chey</button>
      <div class="row" style="margin-top:10px;">
        <button class="btn-alt" style="flex:1;" onclick="logout()">↩️ Logout / Number Change</button>
      </div>
    </div>

    <div class="card">
      <div class="row">
        <button class="btn-main" style="flex:1; font-size:17px; padding:16px;" onclick="scrollDoor('sec-exams')">🎓 Exams</button>
        <button class="btn-main" style="flex:1; font-size:17px; padding:16px; background:linear-gradient(90deg,#0e7490,#06b6d4);" onclick="scrollDoor('sec-quiz')">📝 Quiz</button>
      </div>
      <p class="muted" style="margin-top:8px; text-align:center;">🎓 Exams = Live Exams · Weekly Test · Mock Tests &nbsp;|&nbsp; 📝 Quiz = Daily Quiz (anni exams PYQ-first!)</p>
    </div>

    <div class="card" id="state-hub-card">
      <h3>🗺️ TS &amp; AP Exam Hub</h3>
      <p class="muted">Meeku state exam select cheyyandi — aa exam previous papers nunchi mock + subject-wise tests (honest counts tho).</p>
      <div id="state-hub"><p class="muted">⏳ Load avthundi…</p></div>
    </div>

    <div class="card" id="install-card" style="display:none; border-color:#10b981;">
      <h3>📲 StudentUp App Install Cheyyandi</h3>
      <p class="muted">Home screen meeda app laaga untundi — Daily Quiz ki okka tap lo vellachu!</p>
      <button class="btn-main" id="install-btn">📲 Install App</button>
      <p class="muted" id="install-hint" style="margin-top:8px;"></p>
    </div>

    <div class="card" id="notice-card" style="display:none; border-color:#a16207;">
      <h3>📢 Exam Updates</h3>
      <div id="notices"></div>
    </div>

    <div class="card" id="sec-quiz">
      <h3>📅 Today's Daily Quiz</h3>
      <p class="muted" id="daily-info"></p>
      <button class="btn-main" id="daily-btn" onclick="openQuiz()">▶️ Start Daily Quiz</button>
    </div>

    <div class="card" id="sec-exams">
      <h3>🔴 Live &amp; Upcoming Exams</h3>
      <div id="live-exams"></div>
      <p class="muted">📚 Paper PYQ-first (real previous-year questions). Start time ki mundhe Join nokki ready ga undandi — Live avvagane rank board update avthune untundi!</p>
    </div>

    <div class="card">
      <h3>🏆 Winners Wall</h3>
      <div id="winners-wall"></div>
    </div>

    <div class="card">
      <h3>👑 Toppers — Week · Month · Year</h3>
      <div class="row">
        <button class="tchip" id="tt-week" onclick="showToppers('week')">📅 Week</button>
        <button class="tchip" id="tt-month" onclick="showToppers('month')">🗓️ Month</button>
        <button class="tchip" id="tt-year" onclick="showToppers('year')">👑 Year</button>
      </div>
      <div id="toppers-list" style="margin-top:6px;"></div>
    </div>

    <div class="card">
      <h3>🏙️ District League — mee district vs migatha districts</h3>
      <div id="district-league"></div>
    </div>

    <div class="card">
      <h3>📝 Mock Tests — mee exam select cheskondi</h3>
      <p class="muted">Real exam pattern practice: 15 questions, timer tho. Ayyaka instant score + full answer review.</p>
      <div class="grid" id="mock-grid"></div>
    </div>

    <div class="card">
      <h3>🎯 Practice — weak topics meeda focus, pressure ledu</h3>
      <p class="muted">Instant answers tho nerchukondi. Smart Practice mee weak topics + revision nunchi questions testhundi.</p>
      <button class="btn-main" onclick="startPractice('smart')">🧠 Smart Practice</button>
      <button class="btn-alt" id="rev-btn" onclick="startPractice('review')">🔁 Revision</button>
      <div class="row" style="margin-top:9px; flex-wrap:wrap; gap:6px;">
        <button class="btn-alt" style="width:auto; margin:0;" onclick="startPractice('weak')">🎯 Weak Drill</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="startPractice('revenge')">😤 Revenge</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="startPractice('speed')">⚡ Speed 45s</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="startPractice('marathon')">🏃 Marathon 25</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="startPractice('bookmarks')">🔖 Saved</button>
      </div>
      <div class="row" style="margin-top:9px;">
        <select id="topic-sel" style="flex:1;"></select>
        <button class="btn-alt" style="width:auto; margin-top:0;" onclick="startPractice('topic')">Topic ▶</button>
      </div>
      <div class="row" style="margin-top:9px;">
        <input id="search-q" type="text" placeholder="🔍 Question search (eg: photosynthesis, article 370)" style="flex:1;">
        <button class="btn-alt" style="width:auto; margin-top:0;" onclick="searchPractice()">Search ▶</button>
      </div>
      <div class="row" style="margin-top:9px;">
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadDailyReview()">📅 Daily Review</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="resumeMock()">▶️ Resume Aapina Mock</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="downloadMyData()">📦 Naa Data Download</button>
      </div>
      <div class="row" style="margin-top:9px;">
        <span class="muted">🏁 Real-exam negative marking tho mock:</span>
        <select id="neg-sel" style="width:auto;">
          <option value="0">No negative</option>
          <option value="0.25">−0.25</option>
          <option value="0.5">−0.5</option>
          <option value="1">−1</option>
        </select>
      </div>
    </div>

    <div class="card" id="sprint-card" style="display:none; border-color:#f59e0b;"></div>

    <div class="card">
      <h3>🚀 Advanced Study Tools</h3>
      <div id="countdown-card" style="margin-bottom:8px;"></div>
      <div id="coach-card" style="margin-bottom:8px;"></div>
      <div class="row" style="flex-wrap:wrap; gap:6px;">
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadSyllabus()">🗺️ Syllabus Tracker</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadPercentile()">📈 Naa Percentile</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadDistrict()">🏙️ District Deep-Dive</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadRevision()">🧠 Revision Planner</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadRank2()">🎯 Rank Predictor</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadMaterials()">📚 Materials Vault</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadScoreIntel()">🏆 Score Intelligence</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadBookmarks()">🔖 Saved Questions</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="downloadWorksheet()">🖨️ Worksheet</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadStudyPlan()">📅 7-Day Plan</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadForecast()">🔮 Score Forecast</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadTrend()">📊 Naa Trend</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadTrends()">📈 PYQ Trends</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadGoalBoard()">🏆 Goal Board</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="downloadRevisionPack()">🎁 Revision Pack</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="startGrand()">🏛️ Grand Mock 50Q</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="startAdaptive()">🧠 Adaptive Mock</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="startBlueprint()">🧩 Blueprint Mock (Exam Pattern)</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="weeklyReport()">📲 Weekly Report</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="downloadMistakes()">📕 Mistake Notebook</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="showAllNotices()">📢 Anni Notices</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="seriesCert()">🏅 Series Certificate</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadSections()">🧩 Sections</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadPatterns()">📉 Mistakes</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadRetention()">🧠 Retention</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadRecords()">🏆 Records + Series</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="loadRival()">🥊 Rival Race</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="cycleLang()">🌐 Language</button>
      </div>
      <div id="series-chip" style="margin-top:7px;"></div>
      <div id="challenge-card" style="margin-top:9px;"></div>
      <div id="adv-out" style="margin-top:9px;"></div>
    </div>

    <div class="card" id="focus-card">
      <h3>⏱️ Focus Timer — Deep Study</h3>
      <p class="muted" id="focus-stats">Ee roju focus: 0 min · Ee week: 0 min</p>
      <div id="focus-clock" style="font-size:34px; font-weight:800; text-align:center; margin:8px 0;">25:00</div>
      <div class="row" style="justify-content:center; gap:6px;">
        <button class="tchip" onclick="focusPreset(15)">15 min</button>
        <button class="tchip" onclick="focusPreset(25)">25 min</button>
        <button class="tchip" onclick="focusPreset(50)">50 min</button>
      </div>
      <div class="row" style="margin-top:9px;">
        <button class="btn-main" style="flex:1;" id="focus-btn" onclick="focusToggle()">▶️ Start Focus</button>
        <button class="btn-alt" style="width:auto; margin:0;" onclick="focusReset()">↺ Reset</button>
      </div>
      <p class="muted" style="margin-top:7px; text-align:center;">Timer complete aythe mee study minutes automatic ga log avthayi 📈</p>
    </div>

    <div class="card" id="goal-hub-card">
      <h3>🎓 Exam-wise Quiz Hub</h3>
      <div class="row" id="hub-chips" style="flex-wrap:wrap; gap:6px;"></div>
      <div id="goal-hub" style="margin-top:9px;"><p class="muted">Meeru prepare ayye exam select cheyyandi — PYQ stock, repeat topics, mee best score, next step anni ikkade.</p></div>
    </div>

    <div class="card">
      <h3>🧠 Student Brain 3.0</h3>
      <div id="brain-card"></div>
    </div>
    <div class="card" id="sec-papers">
      <h3>📜 Previous Papers (Real PYQ)</h3>
      <div id="plan-card" style="margin-bottom:10px;"></div>
      <div id="papers-list"><div class="muted">Loading papers…</div></div>
    </div>

    <div class="card">
      <h3>🎯 Naa Personal Report</h3>
      <div id="report"></div>
      <div id="report-full" style="margin-top:10px;"></div>
      <div class="row">
        <button class="btn-alt" style="flex:1;" onclick="loadReport()">📊 Full Report Chudu</button>
        <button class="btn-alt" style="flex:1;" id="wa-share">📲 Report WhatsApp ki</button>
      </div>
    </div>

    <div class="card">
      <h3>🤝 Friends ni Invite Cheyyi — Points Pondi</h3>
      <p class="muted">Mee link tho join ayina prati friend ki meeru <b>+50 points</b> bonus! Rank ki help avthundi.</p>
      <div class="row" style="margin-top:8px;">
        <input id="ref-link" readonly style="flex:1; font-size:13px;">
        <button class="btn-main" style="width:auto; margin-top:0; padding:11px 14px;" onclick="copyRef()">📋 Copy</button>
        <button class="btn-alt" style="width:auto; margin-top:0;" id="ref-share">📲 Share</button>
      </div>
      <div id="my-invites" class="muted" style="margin-top:8px;"></div>
      <h3 style="margin-top:12px;">👥 Top Referrers</h3>
      <div id="board-ref"></div>
    </div>

    <div class="card">
      <h3>🏆 Daily Quiz Leaders (Today)</h3>
      <div id="board-daily"></div>
      <h3 style="margin-top:16px;">📝 Mock Test Leaders</h3>
      <div id="board-mock"></div>
      <h3 style="margin-top:16px;">👑 Yesterday's Winners</h3>
      <div id="board-win"></div>
    </div>

    <div class="card">
      <h3>📋 Naa Exams &amp; Answer Keys</h3>
      <div id="history-list"></div>
      <p class="muted" style="margin-top:8px;">📄 Key Paper = anni questions + mee answers (right ✅/wrong ❌) + correct answer + 💡 explanation. Okka saari download cheste phone lo save avthundi — History lo nunchi <b>eppudaina malli</b> download chesukovachu!</p>
    </div>

    <div class="card">
      <h3>🏫 College Exam (Private)</h3>
      <p class="muted">College exams ikkada list avavu — mee teacher ichhina code/link tho maatrame open avthayi (privacy kosam).</p>
      <div class="row">
        <input id="ccode" placeholder="Exam code e.g. CE-K7P2" style="flex:1; text-transform:uppercase;">
        <button class="btn-main" style="width:auto; margin-top:0; padding:12px 18px;" onclick="var c=document.getElementById('ccode').value.trim().toUpperCase(); if(c) location.href='/exam/'+c;">Open</button>
      </div>
    </div>
  </div>

  <!-- daily quiz -->
  <div id="view-quiz" class="card" style="display:none;">
    <div class="row"><span id="q-pos" class="chip"></span><span id="q-topic" class="chip"></span><span id="q-score" class="chip gold"></span></div>
    <div id="q-te" class="qte" style="margin-top:12px;"></div>
    <div id="q-en" class="qen"></div>
    <div id="opts"></div>
    <div id="q-fb" class="feedback"></div>
    <div class="row"><button class="btn-alt" style="width:auto; margin:0;" onclick="speakCurrent('daily')">🔊 Listen</button></div>
    <button class="btn-main" id="q-next" style="display:none;" onclick="nextQ()">Next ➡️</button>
  </div>

  <!-- practice -->
  <div id="view-prc" class="card" style="display:none;">
    <div class="row"><span id="p-pos" class="chip"></span><span id="p-topic" class="chip"></span><span id="p-score" class="chip gold"></span><button class="btn-alt" style="width:auto; margin-top:0; padding:5px 12px;" onclick="backHome()">🏠 Exit</button></div>
    <div id="p-te" class="qte" style="margin-top:12px;"></div>
    <div id="p-en" class="qen"></div>
    <div id="p-opts"></div>
    <div id="p-fb" class="feedback"></div>
    <div class="row"><button class="btn-alt" style="width:auto; margin:0;" id="p-bm" onclick="bmCurrent()">🔖 Save Question</button><button class="btn-alt" style="width:auto; margin:0;" onclick="flagCurrent()">🚩 Wrong Question?</button><button class="btn-alt" style="width:auto; margin:0;" onclick="speakCurrent('prc')">🔊 Listen</button><button class="btn-alt" style="width:auto; margin:0;" onclick="loadTopicNotes()">📖 Topic Notes</button><span id="p-timer" class="chip" style="display:none;"></span></div>
    <button class="btn-main" id="p-next" style="display:none;" onclick="nextPr()">Next ➡️</button>
  </div>

  <!-- mock -->
  <div id="view-mock" class="card" style="display:none;">
    <div class="row"><span id="m-title" class="chip"></span><span class="chip timer" id="m-timer"></span></div>
    <div id="m-palette" style="display:flex; flex-wrap:wrap; gap:4px; margin:8px 0;"></div>
    <div id="m-qs"></div>
    <button class="btn-main" onclick="submitMock()">✅ Submit Mock Test</button>
    <div id="m-err" class="err"></div>
  </div>

  <!-- live exam runner -->
  <div id="view-exam" class="card" style="display:none;">
    <div class="row"><span id="x-title" class="chip"></span><span class="chip timer" id="x-timer"></span><span id="x-prog" class="chip gold"></span></div>
    <p class="muted" style="margin-top:8px;">⚠️ Live exam lo answers save avthayi kaani correct/wrong result ayye varaku teliyadu — real exam feel! Back vellina, refresh chesina answers safe.</p>
    <div id="x-qs"></div>
    <button class="btn-main" onclick="backHome()">✔️ Finish (Result exam ayyaka ikkade)</button>
  </div>

  <!-- mock result -->
  <div id="view-result" class="card" style="display:none;">
    <h2 style="text-align:center;">📝 Mock Result</h2>
    <div class="score-big" id="res-score"></div>
    <p class="muted" id="res-sub" style="text-align:center;"></p>
    <h3>📋 Answer Review</h3>
    <div id="res-review"></div>
    <button class="btn-main" onclick="backHome()">🏠 Home ki vellu</button>
  </div>
</div>

<script>
let token = localStorage.getItem('su_portal') || '';
let GOALS = {}, QUESTIONS = [], cur = 0, score = 0, MOCK = null, mockTimer = null;
const esc = (t) => String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');  // 🧼 290X quote-safe
async function api(path, body) {
  const opt = body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {};
  const r = await fetch(path, opt); return await r.json();
}
function show(id) {
  ['view-reg', 'view-home', 'view-quiz', 'view-mock', 'view-result', 'view-exam', 'view-prc'].forEach(v => {
    const el = document.getElementById(v); if (el) el.style.display = (v === id ? 'block' : 'none');
  });
}
function rows(list, emptyMsg) {
  if (!list || !list.length) return '<div class="muted">' + emptyMsg + '</div>';
  return list.map((t, i) => '<div class="trow"><span>' + (['🥇','🥈','🥉'][i] || (i + 1)) + '</span><b>' + esc(t.name) + '</b><span class="muted">' + esc(t.district || '') + '</span><span>✅ ' + t.correct + '/' + (t.total || 10) + ' · ⭐' + t.pts + '</span></div>').join('');
}
async function init() {
  setTheme(localStorage.getItem('su_theme') || '');
  setAccent(localStorage.getItem('su_accent') || '');
  try {
    const wa = window.Telegram && window.Telegram.WebApp;
    if (wa && wa.initData) {
      wa.ready(); wa.expand();
      const d = await api('/api/portal/tg_auth', {init_data: wa.initData});
      if (d.ok && d.token) { token = d.token; localStorage.setItem('su_portal', token); }
    }
  } catch (e) {}
  const _ref = new URLSearchParams(location.search).get('ref');
  if (_ref) localStorage.setItem('su_ref', _ref.toUpperCase());
  const _go = new URLSearchParams(location.search).get('go');
  if (_go) localStorage.setItem('su_go', _go);
  const _hg = new URLSearchParams(location.search).get('goal');
  if (_hg) localStorage.setItem('su_hub_goal', _hg);
  const meta = await api('/api/portal/meta');
  GOALS = meta.goals || {};
  const dg = document.getElementById('r-district');
  (meta.districts || []).forEach(d => { const o = document.createElement('option'); o.value = d.name; o.textContent = d.name + ' (' + d.state + ')'; dg.appendChild(o); });
  const ts = document.getElementById('topic-sel');
  (meta.topics || []).forEach(t => { const o = document.createElement('option'); o.value = t; o.textContent = t; ts.appendChild(o); });
  const gl = document.getElementById('r-goal');
  Object.entries(GOALS).forEach(([k, v]) => { const o = document.createElement('option'); o.value = k; o.textContent = v; gl.appendChild(o); });
  const _slTok = localStorage.getItem('su_stateless') || '';
  if (_slTok) { token = _slTok; loadStatelessHome(); }
  else if (token) { flushOffline(); loadHome(); } else { show('view-reg'); }
}
async function loadStatelessHome() {
  const st = (localStorage.getItem('su_stateless') || token || '');
  if (!st) { show('view-reg'); return; }
  token = st;  // keep su_portal fallback flow untouched below
  const d = await api('/api/portal/st270?token=' + encodeURIComponent(st));
  if (!d.ok) { localStorage.removeItem('su_stateless'); show('view-reg'); return; }
  show('view-home');
  const hello = document.getElementById('hello'); if (hello) hello.textContent = '👋 ' + ((d.profile || {}).name || 'Student');
  const hints = document.getElementById('daily-info'); if (hints) hints.textContent = '🔐 No-VPS mode: mee points/progress mee signed token lone untayi. Daily Quiz & attempts kindha primary buttons tho ne vasthayi.';
  alert('🔐 Stateless (No-VPS) mode active! Points: ' + (d.points || 0)
        + ' · Answers: ' + (d.answers || 0)
        + ' · Accuracy: ' + (d.accuracy || 0) + '%');
}
function copyRef() {
  const el = document.getElementById('ref-link');
  el.select(); navigator.clipboard.writeText(el.value).then(() => alert('✅ Link copied!'));
}
let _deferredInstall = null;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault(); _deferredInstall = e;
  document.getElementById('install-card').style.display = 'block';
});
function qMeta(q) {
  if (!q) return '';
  let m = '🏷️ ' + (q.topic || '') + (q.level ? ' · ' + q.level : '');
  if (q.source === 'pyq') m += ' · 📜 PYQ' + (q.exam ? ' · ' + q.exam : '') + (q.year ? ' ' + q.year : '');
  return m;
}
function scrollDoor(id) {
  const el = document.getElementById(id);
  if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); el.style.borderColor = '#facc15'; setTimeout(() => el.style.borderColor = '', 1600); }
}
function _applyGo() {
  const go = new URLSearchParams(location.search).get('go') || localStorage.getItem('su_go') || '';
  if (!go) return;
  localStorage.removeItem('su_go');
  const map = {quiz: 'sec-quiz', smart: 'sec-quiz', exams: 'sec-exams', live: 'sec-exams', mocks: 'mock-grid', mock: 'mock-grid', papers: 'sec-papers', pyq: 'sec-papers', hub: 'goal-hub-card'};
  setTimeout(() => {
    scrollDoor(map[go] || 'sec-quiz');
    if (go === 'hub') {
      const hg = new URLSearchParams(location.search).get('goal') || localStorage.getItem('su_hub_goal') || '';
      localStorage.removeItem('su_hub_goal');
      if (hg) setTimeout(() => loadGoalHub(hg), 450);
    }
  }, 350);
}
async function setGoal(k) {
  const d = await api('/api/portal/goal', {token, goal: k});
  if (d.ok) loadHome(); else alert('❌ ' + (d.error || ''));
}
async function downloadKey(kind, ref) {
  const d = await api('/api/portal/key?kind=' + encodeURIComponent(kind) + '&ref=' + encodeURIComponent(ref) + '&token=' + encodeURIComponent(token));
  if (!d.ok) { alert('❌ ' + (d.error || 'Key dorakaledu')); return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([d.text], {type: 'text/plain;charset=utf-8'}));
  a.download = d.filename || 'StudentUp-Key.txt'; a.click();
}
function renderHistory(list) {
  document.getElementById('history-list').innerHTML = (list || []).length ? list.map(h =>
    '<div class="trow"><span>' + (h.kind === 'exam' ? '🔴' : (h.kind === 'mock' ? '📝' : '📅')) + '</span><b style="flex:1;">' + esc(h.title) + '</b><span class="muted">' + esc(h.date || '') + '</span><span>✅ ' + h.correct + '/' + h.total + '</span>' +
    (h.key ? '<button class="btn-alt" style="width:auto; margin-top:0; padding:6px 10px;" onclick="downloadKey(\'' + h.kind + '\',\'' + esc(h.ref) + '\')">⬇️ Key</button>'
           : '<span class="chip">⏳ ' + esc(h.status || '') + '</span>') + '</div>').join('')
    : '<div class="muted">Inka meeru exams rayaledu — Daily Quiz tho start cheyyandi, ikkada key papers ready avthayi!</div>';
}
async function loadReport() {
  const d = await api('/api/portal/report?token=' + encodeURIComponent(token));
  const box = document.getElementById('report-full');
  if (!d.ok) { box.innerHTML = '<div class="muted">Report load avvaledu.</div>'; return; }
  const bars = (d.topics || []).map(t =>
    '<div style="margin-top:7px;"><div class="row"><span style="flex:1; font-size:12.5px;">' + esc(t.topic) + '</span><span class="chip">' + t.correct + '/' + t.total + ' · ' + t.accuracy + '%</span></div>' +
    '<div class="tbar" style="margin:4px 0 0;"><div style="height:100%; width:' + t.accuracy + '%; background:' + (t.accuracy >= 60 ? '#10b981' : (t.accuracy >= 40 ? '#facc15' : '#ef4444')) + ';"></div></div></div>').join('');
  const mocks = (d.mocks || []).map(m => '<div class="trow"><span>📝</span><b>' + esc(GOALS[m.goal] || m.goal) + '</b><span class="muted">' + esc(m.date) + '</span><span>✅ ' + m.correct + '/' + m.total + '</span></div>').join('');
  const heat = (d.activity || []).map(a =>
    '<span title="' + a.date + ' · ' + a.pts + ' pts" style="display:inline-block; width:15px; height:15px; margin:2px; border-radius:4px; background:' +
    (a.pts >= 50 ? '#10b981' : (a.pts >= 20 ? '#34d399' : (a.pts > 0 ? '#065f46' : '#12233f'))) + '; border:1px solid #1e3a5f;"></span>').join('');
  const exams = (d.exams || []).map(e => '<div class="trow"><span>🔴</span><b>' + esc(e.title) + '</b><span>✅ ' + e.correct + '/' + e.total + '</span></div>').join('');
  box.innerHTML = (heat ? '<h3>📅 Last 28 Days Activity</h3><div style="margin:8px 0 4px;">' + heat + '</div><div class="muted" style="margin-bottom:10px;">Prati roju color square = aa roju earn chesina points. Gap leni streak = topper sign!</div>' : '') +
    '<h3>📚 Topic-wise Performance</h3>' + (bars || '<div class="muted">Inka topic data ledu.</div>') +
    (mocks ? '<h3 style="margin-top:12px;">📝 Recent Mocks</h3>' + mocks : '') +
    (exams ? '<h3 style="margin-top:12px;">🔴 My Live Exams</h3>' + exams : '');
}
async function doRegister() {
  const err = document.getElementById('reg-err'); err.textContent = '';
  if (document.getElementById('r-stateless') && document.getElementById('r-stateless').checked) {
    const sd = await api('/api/portal/st270/register', {
      name: document.getElementById('r-name').value.trim(),
      phone: document.getElementById('r-phone').value.trim(),
      district: document.getElementById('r-district').value,
      goal: document.getElementById('r-goal').value});
    if (!sd.ok) { err.textContent = '❌ ' + (sd.error || 'Register avvaledu'); return; }
    token = sd.token; localStorage.setItem('su_stateless', token); localStorage.removeItem('su_portal');
    return loadStatelessHome();
  }
  const d = await api('/api/portal/register', {
    name: document.getElementById('r-name').value.trim(),
    phone: document.getElementById('r-phone').value.trim(),
    district: document.getElementById('r-district').value,
    goal: document.getElementById('r-goal').value,
    ref: localStorage.getItem('su_ref') || ''});
  if (!d.ok) { err.textContent = '❌ ' + (d.error || 'Register avvaledu'); return; }
  token = d.token; localStorage.setItem('su_portal', token);
  loadHome();
}
function logout() { localStorage.removeItem('su_portal'); localStorage.removeItem('su_stateless'); token = ''; show('view-reg'); }
const ACC2 = { '#10b981': '#065f46', '#38bdf8': '#0369a1', '#f59e0b': '#b45309', '#f472b6': '#be185d', '#a78bfa': '#6d28d9', '#facc15': '#a16207' };
function setAccent(a) {
  if (a) { document.body.style.setProperty('--acc', a); document.body.style.setProperty('--acc2', ACC2[a] || a); }
  else { document.body.style.removeProperty('--acc'); document.body.style.removeProperty('--acc2'); }
  localStorage.setItem('su_accent', a || '');
  document.querySelectorAll('.asw[data-acc]').forEach(b => b.classList.toggle('on', (b.dataset.acc || '') === (a || '')));
}
/* 🎨 300X APPEARANCE ENGINE: theme (+🌓 auto day/night) + font size
   + calm mode compose on <body>; lang-te/lang-en classes are always
   preserved (the old setTheme wiped them on every tap). */
const THEMES300 = ['', 'ocean', 'sunset', 'forest', 'light', 'royal', 'grape', 'rose', 'aurora', 'paper', 'focus', 'auto'];
function effectiveTheme(t) {
  if (t === 'auto') { const h = new Date().getHours(); return (h >= 6 && h < 19) ? 'light' : ''; }
  return THEMES300.includes(t) ? t : '';
}
function applyAppearance() {
  const t = localStorage.getItem('su_theme') || '';
  const eff = effectiveTheme(t);
  const fs = localStorage.getItem('su_font') || 'm';
  const calm = localStorage.getItem('su_calm') === '1';
  const lang = document.body.classList.contains('lang-te') ? 'lang-te'
             : document.body.classList.contains('lang-en') ? 'lang-en' : '';
  document.body.className = [eff ? ('theme-' + eff) : '', fs !== 'm' ? ('font-' + fs) : '',
                             calm ? 'calm' : '', lang].filter(Boolean).join(' ');
  document.querySelectorAll('.tchip[data-th]').forEach(b => b.classList.toggle('on', (b.dataset.th || '') === t));
  document.querySelectorAll('.tchip[data-fs]').forEach(b => b.classList.toggle('on', (b.dataset.fs || 'm') === fs));
  document.querySelectorAll('.tchip[data-calm]').forEach(b => b.classList.toggle('on', calm));
  const a = localStorage.getItem('su_accent');
  if (a) setAccent(a);
}
function setTheme(t) {
  localStorage.setItem('su_theme', THEMES300.includes(t) ? t : '');
  applyAppearance();
}
function setFont(fs) {
  localStorage.setItem('su_font', ['s', 'm', 'l'].includes(fs) ? fs : 'm');
  applyAppearance();
}
function toggleCalm() {
  localStorage.setItem('su_calm', localStorage.getItem('su_calm') === '1' ? '0' : '1');
  applyAppearance();
}
setInterval(() => { if (localStorage.getItem('su_theme') === 'auto') applyAppearance(); }, 60000);
let TOPP = {};
function showToppers(period) {
  ['week', 'month', 'year'].forEach(k => {
    const el = document.getElementById('tt-' + k);
    if (el) el.classList.toggle('on', k === period);
  });
  const list = (TOPP || {})[period] || [];
  document.getElementById('toppers-list').innerHTML = list.length ? list.map((t, i) =>
    '<div class="trow"><span>' + (['🥇','🥈','🥉'][i] || (i + 1)) + '</span><b>' + esc(t.name) + '</b><span class="muted">📍 ' + esc(t.district || '') + '</span><span>⭐ ' + t.pts + ' pts</span></div>').join('')
    : '<div class="muted">Ee period lo inka points levu — practice chesi first topper avvandi! 🔥</div>';
}
async function loadHome() {
  let d;
  try {
    d = await api('/api/portal/state?token=' + encodeURIComponent(token));
    if (d.ok) { try { localStorage.setItem('su_offline_state', JSON.stringify(d)); } catch (e) {} }
  } catch (e) {
    try { d = JSON.parse(localStorage.getItem('su_offline_state') || 'null'); } catch (e2) { d = null; }
    if (d) d._offline = true;
  }
  if (!d || !d.ok) { logout(); return; }
  const s = d.student; STATE = d;
  loadStateHub();
  document.getElementById('hello').textContent = '👋 ' + s.name;
  document.getElementById('mychips').innerHTML =
    '<span class="chip">🎯 ' + esc(GOALS[s.goal] || s.goal) + '</span>' +
    '<span class="chip">📍 ' + esc(s.district) + '</span>' +
    '<span class="chip gold">⭐ ' + s.points + ' pts</span>' +
    (d.my_rank_today ? '<span class="chip">🏆 Today Rank #' + d.my_rank_today + '</span>' : '') +
    (s.streak ? '<span class="chip">🔥 ' + s.streak + '-day streak</span>' : '') +
    (s.shields ? '<span class="chip">🛡️ ' + s.shields + ' streak shield' + (s.shields > 1 ? 's' : '') + '</span>' : '') +
    (s.badges || []).map(b => '<span class="chip gold">🏅 ' + esc(b) + '</span>').join('');
  document.getElementById('goal-chips').innerHTML = '<span class="muted" style="font-size:12px;">🏆 Mee Exam:</span>' + Object.entries(d.goals || {}).map(([k, v]) =>
    '<button class="tchip' + (k === s.goal ? ' on' : '') + '" onclick="setGoal(\'' + k + '\')">' + esc(v) + '</button>').join('') +
    '<br><span class="muted" style="font-size:12px;">🎯 Also preparing (2nd goal):</span>' + Object.entries(d.goals || {}).map(([k, v]) =>
    '<button class="tchip' + (d.goal2 && k === d.goal2.goal ? ' on' : '') + '" onclick="setGoal2(\'' + k + '\')">' + esc(v) + '</button>').join('');
  const lv = s.level || {};
  const lvEl = document.getElementById('level-bar');
  if (lvEl && lv.title) lvEl.innerHTML = '<div style="font-size:12px;">' + (lv.icon || '') + ' <b>' + esc(lv.title) + '</b>' + (lv.next ? ' · Next level ki ' + lv.next + ' pts' : ' · 👑 Top level!') + '</div>' +
    '<div style="height:8px; background:rgba(255,255,255,0.08); border-radius:4px; margin-top:4px;"><div style="height:8px; width:' + (lv.progress || 0) + '%; background:linear-gradient(90deg,#f59e0b,#34d399); border-radius:4px;"></div></div>';
  loadBotLink();
  const hubEl = document.getElementById('hub-chips');
  if (hubEl) hubEl.innerHTML = Object.entries(d.goals || {}).map(([k, v]) =>
    '<button class="tchip" onclick="loadGoalHub(\'' + k + '\')">' + esc(v) + '</button>').join('');
  if (d.focus) {
    const fst = document.getElementById('focus-stats');
    if (fst) fst.textContent = 'Ee roju focus: ' + d.focus.today_min + ' min · Ee week: ' + d.focus.week_min + ' min';
  }
  const st = (d.stock || {})[s.goal] || {};
  document.getElementById('goal-stock').textContent = '📚 Mee exam bank lo ' + (st.pyq || 0) + ' real previous-year (PYQ) questions + ' + (st.total || 0) + ' practice questions ready ga unnayi — backend lo scraping continue avthundi!';
  renderHistory(d.history || []);
  const nts = d.notices || [];
  document.getElementById('notice-card').style.display = nts.length ? 'block' : 'none';
  document.getElementById('notices').innerHTML = nts.map(n =>
    '<div style="margin-bottom:9px;"><b>' + esc(n.title) + '</b><div class="muted">' + esc(n.body) + '</div>' +
    (n.link ? '<a href="' + esc(n.link) + '" target="_blank" rel="noopener" style="font-size:12.5px;">Official link ↗</a>' : '') + '</div>').join('');
  document.getElementById('rev-btn').textContent = '🔁 Revision' + (s.review_due ? ' (' + s.review_due + ' due)' : '');
  const di = document.getElementById('daily-info'), db = document.getElementById('daily-btn');
  if (d.daily.done) { di.textContent = '✅ Ee roju quiz complete! Score: ' + d.daily.correct + '/' + d.daily.n + ' — repu malli randi.'; db.style.display = 'none'; }
  else { di.textContent = d.daily.n + ' questions · 📜 ' + (d.daily.pyq_count || 0) + ' real PYQ (previous-year) questions ee paper lo · andari ki okkate paper.'; db.textContent = d.daily.answered ? '▶️ Continue Quiz (' + d.daily.answered + '/' + d.daily.n + ')' : '▶️ Start Daily Quiz'; db.style.display = 'block'; }
  document.getElementById('mock-grid').innerHTML = Object.entries(GOALS).map(([k, v]) => {
    const gst = (d.stock || {})[k] || {};
    return '<button class="mockbtn' + (k === s.goal ? ' mine' : '') + '" onclick="startMock(\'' + k + '\')">' + esc(v) + '<br><span class="muted">15 Qs · Mock · 📜 ' + (gst.pyq || 0) + ' PYQ bank lo</span></button>';
  }).join('');
  const weak = (s.weak_topics || []).map(w => '<span class="chip weak">⚠️ ' + esc(w.topic) + ' · ' + w.accuracy + '%</span>').join('');
  document.getElementById('report').innerHTML =
    '<div class="row"><span class="chip">✅ Accuracy ' + s.accuracy + '%</span><span class="chip">✍️ ' + s.answered + ' answered</span><span class="chip gold">⭐ ' + s.points + ' pts</span></div>' +
    (weak ? '<div style="margin-top:9px;"><span class="muted">Mee weak topics — ivvi ekkuva practice cheyyandi:</span><div class="row" style="margin-top:6px;">' + weak + '</div></div>'
          : '<p class="muted" style="margin-top:8px;">Inka data ledu — Daily Quiz & Mocks raasthe mee weak topics ikkada kanipisthayi, personal ga improve avutharu.</p>');
  const BN = d.brain;
  const brainEl = document.getElementById('brain-card');
  if (brainEl) {
    if (BN && BN.answers > 0) {
      const comp = BN.components || {};
      const bar = (label, v) => '<div style="margin:3px 0;"><span class="muted">' + label + '</span><div style="background:rgba(255,255,255,.08); border-radius:6px; height:8px;"><div style="width:' + Math.min(100, v * 4) + '%; height:8px; border-radius:6px; background:linear-gradient(90deg,#38bdf8,#a78bfa);"></div></div></div>';
      brainEl.innerHTML = '<b>' + esc(BN.band) + '</b> · Ability θ ' + BN.theta + ' · Target level: ' + esc(BN.target_level || '') +
        '<div style="margin-top:6px;"><span style="font-size:27px; font-weight:800;">' + BN.score + '%</span> <span class="muted">Exam Readiness</span></div>' +
        bar('Ability', comp.ability || 0) + bar('Coverage', comp.coverage || 0) + bar('Practice', comp.volume || 0) + bar('Streak', comp.streak || 0) +
        (BN.weak_topics && BN.weak_topics.length ? '<div style="margin-top:6px;" class="muted">Focus topics: ' + BN.weak_topics.map(esc).join(', ') + '</div>' : '') +
        '<button class="btn-alt" style="width:auto; margin-top:9px;" onclick="startPractice(\'smart\')">🧠 Smart Practice (mee level)</button>' +
        (BN.reviews_due ? ' <span class="chip">🔁 ' + BN.reviews_due + ' revision due</span>' : '');
    } else {
      brainEl.innerHTML = '<div class="muted">Daily Quiz / Practice start cheyyandi — mee ability (θ), exam readiness, level-wise smart practice ikkada kanipistundi.</div><button class="btn-alt" style="width:auto; margin-top:8px;" onclick="startPractice(\'smart\')">🧠 Smart Practice Start</button>';
    }
  }
  const ib = document.getElementById('install-btn');
  if (ib) ib.onclick = async () => {
    if (_deferredInstall) { _deferredInstall.prompt(); await _deferredInstall.userChoice; _deferredInstall = null; document.getElementById('install-card').style.display = 'none'; }
  };
  if (/iphone|ipad/i.test(navigator.userAgent) && !window.navigator.standalone) {
    document.getElementById('install-card').style.display = 'block';
    document.getElementById('install-hint').textContent = 'iPhone: Share button ⬆️ → "Add to Home Screen" nokkandi.';
    ib.style.display = 'none';
  }
  const rl = location.origin + '/portal?ref=' + (s.ref_code || '');
  document.getElementById('ref-link').value = rl;
  document.getElementById('my-invites').textContent = '👥 Meeru invite chesina friends: ' + (s.referrals || 0) + ' · Bonus earned: ⭐ ' + ((s.referrals || 0) * 50);
  document.getElementById('ref-share').onclick = () => window.open('https://wa.me/?text=' + encodeURIComponent('🎓 StudentUp lo Daily Quiz + Mocks FREE! Na link tho join avvu: ' + rl), '_blank');
  document.getElementById('board-ref').innerHTML = rows(d.top_referrers, 'Inka referrals levu — first invite meere cheyyandi!');
  const rtext = '🎓 ' + s.name + ' — naa StudentUp Report\n⭐ Points: ' + s.points + ' · 🔥 Streak: ' + (s.streak || 0) + ' days\n🎯 Accuracy: ' + s.accuracy + '%\n' +
    ((s.weak_topics || []).length ? '⚠️ Weak topics: ' + s.weak_topics.map(w => w.topic + ' ' + w.accuracy + '%').join(', ') + '\n' : '') +
    '📝 Daily Quiz ikkade: ' + location.origin + '/portal';
  document.getElementById('wa-share').onclick = () => window.open('https://wa.me/?text=' + encodeURIComponent(rtext), '_blank');
  const dl = d.district_league || {rows: []};
  document.getElementById('district-league').innerHTML =
    (dl.my_rank ? '<div class="muted" style="margin-bottom:6px;">Mee district <b>' + esc(dl.my_district) + '</b> rank <b>#' + dl.my_rank + '</b> / ' + dl.districts + ' districts 🏙️</div>' : '') +
    (dl.rows || []).map((t, i) => '<div class="trow"><span>' + (['🥇','🥈','🥉'][i] || (i + 1)) + '</span><b>' + esc(t.name) + '</b><span class="muted">👥 ' + t.students + ' students</span><span>⭐ ' + t.pts + ' pts</span></div>').join('') || '<div class="muted">Inka district data ledu — points earn cheste league start avthundi!</div>';
  TOPP = d.toppers || {};
  showToppers('week');
  document.getElementById('board-daily').innerHTML = rows(d.daily_board, 'Inka evaru ee roju quiz complete cheyyaledu — meeru first avandi! 🔥');
  document.getElementById('board-mock').innerHTML = rows(d.mock_board, 'Inka mock leaders leru — okka mock raasi board meeda vacheyyandi!');
  document.getElementById('board-win').innerHTML = rows(d.yesterday_winners, 'Ninna winners inka leru.');
  renderPlan(d.today_plan); renderPapers(d.papers || [], d.paper_progress || {});
  renderCountdown(d.countdown); loadCoach(); loadChallenge(); applyLang();
  const sprintEl = document.getElementById('sprint-card');
  if (sprintEl) {
    if (d.sprint && d.sprint.active) {
      sprintEl.innerHTML = '<b>🔥 SPRINT MODE</b> <span class="chip gold">' + d.sprint.days + ' rojulu</span><div>' + esc(d.sprint.text) + '</div>' + (d.sprint.tasks || []).map(t => '<div>• ' + esc(t) + '</div>').join('');
      sprintEl.style.display = 'block';
    } else sprintEl.style.display = 'none';
  }
  api('/api/portal/records?token=' + encodeURIComponent(token)).then(rd => {
    const sc = document.getElementById('series-chip');
    if (sc && rd.ok && rd.series) sc.innerHTML = '<span class="muted">📚 Test Series: ' + (rd.series.attempted || 0) + '/' + (rd.series.target || 10) + ' ayyayi — Test #' + (rd.series.next_no || 1) + ' ready!</span>';
  });
  renderLiveExams(d.live_exams || []); cdTick();
  document.getElementById('winners-wall').innerHTML = (d.winners_wall || []).map(w =>
    '<div style="margin-top:8px;"><b style="font-size:13px;">' + esc(w.title) + '</b>' + rows(w.winners, '') + '</div>').join('') || '<div class="muted">Inka winners leru — Weekly Grand Test (Sunday 10 AM) first!</div>';
  show('view-home');
  const ob = document.getElementById('offline-bar');
  if (ob) ob.style.display = d._offline ? 'block' : 'none';
  _applyGo();
}
function backHome() { clearInterval(mockTimer); clearInterval(rankTimer); clearInterval(exTimer); loadHome(); }
function shareProgress() {
  const s = (STATE || {}).student || {};
  const lv = s.level || {};
  const text = '🏆 Nenu StudentUp lo ' + (s.points || 0) + ' points, ' + (lv.title || 'Newcomer') + ' level, ' + (s.streak || 0) + '-day streak! Daily Quiz + PYQ Mocks FREE: ' + location.origin + '/portal';
  if (navigator.share) { navigator.share({title: 'StudentUp Progress', text}).catch(() => {}); }
  else if (navigator.clipboard) { navigator.clipboard.writeText(text).then(() => alert('✅ Copied! WhatsApp lo paste cheyyandi.')); }
}
async function flushOffline() {
  let q = [];
  try { q = JSON.parse(localStorage.getItem('su_offq') || '[]'); } catch (e) {}
  if (!q.length || !token) return;
  const left = [];
  for (const a of q) {
    if (a.day) {
      // 🛠️ 190X FIX: ninna queue aina answer ni ee roju paper ki
      // sync cheyyam (verey paper — wrong record avuthundi). Drop.
      const todayStr = new Date().toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'});
      if (a.day !== todayStr) continue;
    }
    try { const d = await api('/api/portal/answer', {token, idx: a.idx, choice: a.choice}); if (!d.ok && !d.already) left.push(a); }
    catch (e) { left.push(a); }
  }
  try { localStorage.setItem('su_offq', JSON.stringify(left)); } catch (e) {}
}
window.addEventListener('online', flushOffline);
let qShownAt = 0;
async function openQuiz() {
  let d;
  try {
    d = await api('/api/portal/quiz?token=' + encodeURIComponent(token));
    try { localStorage.setItem('su_offline_daily', JSON.stringify(d)); } catch (e) {}
  } catch (e) {
    try { d = JSON.parse(localStorage.getItem('su_offline_daily') || 'null'); } catch (e2) { d = null; }
    if (!d || !d.ok) { alert('📴 Offline — munde okasari online lo quiz open cheste save avuthundi.'); return; }
  }
  if (!d.ok) { logout(); return; }
  QUESTIONS = d.questions || []; score = 0;
  window._qDay = d.date || '';
  try { JSON.parse(localStorage.getItem('su_offq') || '[]').forEach(a => { if ((!a.day || a.day === window._qDay) && QUESTIONS[a.idx]) QUESTIONS[a.idx].answered = true; }); } catch (e) {}
  cur = QUESTIONS.findIndex(q => !q.answered);
  if (cur < 0) { loadHome(); return; }
  show('view-quiz'); renderQ();
}
function renderQ() {
  qShownAt = Date.now();
  const q = QUESTIONS[cur];
  document.getElementById('q-pos').textContent = 'Q ' + (cur + 1) + '/' + QUESTIONS.length;
  document.getElementById('q-topic').textContent = qMeta(q);
  document.getElementById('q-score').textContent = '✅ ' + score;
  document.getElementById('q-te').textContent = q.te || '';
  document.getElementById('q-en').textContent = q.en || '';
  document.getElementById('q-fb').textContent = '';
  document.getElementById('q-next').style.display = 'none';
  const box = document.getElementById('opts'); box.innerHTML = '';
  q.options.forEach((opt, i) => {
    const b = document.createElement('button'); b.className = 'opt'; b.textContent = optText(q, i, opt);
    b.dataset.qref = regQ(q); b.dataset.oi = i;
    b.onclick = () => ansDaily(i, b); box.appendChild(b);
  });
}
async function ansDaily(i, btn) {
  document.querySelectorAll('#opts .opt').forEach(b => { b.disabled = true; });
  btn.classList.add('picked');
  const fb = document.getElementById('q-fb');
  let d;
  try {
    d = await api('/api/portal/answer', {token, idx: cur, choice: i, sec: Math.round((Date.now() - (qShownAt || Date.now())) / 1000)});
  } catch (e) {
    let q = [];
    try { q = JSON.parse(localStorage.getItem('su_offq') || '[]'); } catch (e2) {}
    q.push({idx: cur, choice: i, day: window._qDay || ''});
    try { localStorage.setItem('su_offq', JSON.stringify(q)); } catch (e3) {}
    if (QUESTIONS[cur]) QUESTIONS[cur].answered = true;
    fb.innerHTML = '📴 Offline — answer save ayyindi. Net ragane auto-sync avuthundi.';
    document.getElementById('q-next').style.display = 'block';
    return;
  }
  if (!d.ok) { fb.textContent = d.error || ''; return; }
  if (d.correct) { score = d.score; fb.innerHTML = '✅ Correct! ' + (d.explanation ? '<span class="muted">' + esc(d.explanation) + '</span>' : ''); }
  else { fb.innerHTML = '❌ Wrong. Correct: <b>' + esc(d.answer_text) + '</b>' + (d.explanation ? '<br><span class="muted">' + esc(d.explanation) + '</span>' : ''); }
  document.getElementById('q-score').textContent = '✅ ' + (d.score || score);
  if (d.done) { fb.innerHTML += '<br>🎉 Daily Quiz complete! Home lo rank chudandi.' + (d.avg_sec ? '<br>⏱ Mee speed: avg ' + d.avg_sec + 's/question' : ''); document.getElementById('q-next').textContent = '🏠 Home'; }
  document.getElementById('q-next').style.display = 'block';
}
function nextQ() {
  if (cur + 1 >= QUESTIONS.length) { loadHome(); return; }
  cur++; renderQ();
}
function renderPlan(plan) {
  const el = document.getElementById('plan-card');
  if (!el) return;
  if (!plan) { el.innerHTML = ''; return; }
  const rows = (plan.tasks || []).map(t =>
    '<div style="display:flex; gap:8px; align-items:center; margin:4px 0;"><span>' + (t.done ? '✅' : '⬜') + '</span><span>' + t.icon + ' <b>' + esc(t.label) + '</b>' + (t.count ? ' (' + t.count + ')' : '') + '</span><span class="muted">' + esc(t.hint || '') + '</span></div>').join('');
  el.innerHTML = '<b>🧭 Today\'s Smart Plan</b> <span class="chip">' + plan.done_count + '/' + plan.total + ' done</span>' +
    (plan.readiness != null ? ' <span class="chip gold">Readiness ' + plan.readiness + '%</span>' : '') + rows;
  loadMemoryDeck();
}
// 🧠 360X: Memory Deck strip — retention % prathi topic ki + booster.
async function loadMemoryDeck() {
  const pel = document.getElementById('plan-card');
  if (!pel || pel.dataset.mem) return;
  try {
    const d = await (await fetch('/api/portal/memory?token=' + encodeURIComponent(token))).json();
    if (!d.ok || !d.total) return;
    pel.dataset.mem = '1';
    const cards = (d.cards || []).map(c =>
      '<div style="margin:3px 0;"><span class="chip' + (c.due_now ? '" style="border-color:#f87171; color:#f87171;' : '') + '">' +
      esc(c.topic) + ' · ' + Math.round((c.retention || 0) * 100) + '% memory' + (c.due_now ? ' · DUE' : '') + '</span></div>').join('');
    pel.insertAdjacentHTML('beforeend',
      '<div style="margin-top:8px;"><b>🧠 Memory Deck</b> <span class="muted">' + d.due + ' due · ' + d.falling + ' falling · ' + d.strong + ' strong</span>' +
      cards + '<button class="btn-alt" style="width:auto; margin-top:6px;" onclick="startPractice(\'review\')">🚀 Memory Booster Start</button></div>');
  } catch (e) {}
}
let PAPER_PROG = {};
function renderPapers(papers, progress) {
  const el = document.getElementById('papers-list');
  if (!el) return;
  PAPER_PROG = progress || PAPER_PROG || {};
  if (!papers.length) { el.innerHTML = '<div class="muted">Inka real PYQ papers load avuthunnayi — Daily Quiz lo daily ga vastundi, harvest prathi roju papers penchuthundi.</div>'; return; }
  el.innerHTML = papers.map(pp => {
    const pg = PAPER_PROG[pp.label] || {};
    const badge = pg.attempts ? ' <span class="chip gold">Best ' + pg.best + '/' + (pg.total || pp.count) + ' · ' + pg.attempts + '× rayaru</span>' : '';
    const topics = (pp.topics || []).length ? '<br><span class="muted">🏷️ ' + esc(pp.topics.join(', ')) + '</span>' : '';
    const size = pp.size === 'mini' ? ' <span class="chip">Mini set</span>' : '';
    return '<div style="display:flex; justify-content:space-between; align-items:center; gap:8px; margin:6px 0; padding:8px 10px; background:rgba(56,189,248,0.07); border-radius:9px;"><span>📜 <b>' + esc(pp.label) + '</b> <span class="muted">' + pp.count + ' questions</span>' + size + badge + topics + '</span>' +
    '<button class="btn-alt" style="width:auto; margin:0;" onclick="startPaper(\'' + esc(pp.exam) + '\',\'' + esc(pp.year || '') + '\',\'' + esc(pp.paper || '') + '\')">' + (pg.attempts ? '↻ Malli' : 'Start ▶') + '</button></div>';
  }).join('') +
    '<div class="muted" style="margin-top:6px;">Full paper = timer test. Submit taruvatha score + answer key + review vastundi.</div>';
}
function renderCountdown(cd) {
  const el = document.getElementById('countdown-card');
  if (!el) return;
  if (!cd || !cd.mine) { el.innerHTML = ''; return; }
  const m = cd.mine;
  el.innerHTML = '<b>⏳ Exam Countdown</b> <span class="chip gold">' + esc(m.label) + '</span> ' +
    '<span style="font-size:15px;"><b>' + m.days + ' rojulu</b> unnayi · ' + esc(m.date) + ' · ' + esc(m.phase) + '</span>';
}
async function loadCoach() {
  const el = document.getElementById('coach-card');
  if (!el) return;
  const d = await api('/api/portal/coach?token=' + encodeURIComponent(token));
  if (!d.ok) { el.innerHTML = ''; return; }
  el.innerHTML = '<b>🧑‍🏫 Personal Coach — Today</b>' +
    (d.readiness != null ? ' <span class="chip gold">Readiness ' + d.readiness + '%</span>' : '') +
    (d.steps || []).map(s => '<div style="margin:4px 0;">' + s.icon + ' ' + esc(s.text) + '</div>').join('');
}
async function loadSyllabus() {
  const out = document.getElementById('adv-out');
  out.innerHTML = '<div class="muted">Loading syllabus…</div>';
  const d = await api('/api/portal/syllabus2?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || 'Syllabus ready ledu') + '</div>'; return; }
  out.innerHTML = '<b>🗺️ ' + esc(d.exam || 'Syllabus') + '</b> <span class="chip gold">Coverage ' + d.coverage + '% (exam-weighted)</span> <span class="muted">' + d.topics_done + '/' + d.topics_total + ' topics</span>' +
    (d.subjects || []).map(s => '<div style="display:flex; justify-content:space-between; margin:4px 0;"><span>' + esc(s.subject) + ' <span class="muted">(' + s.done_topics + '/' + s.topics + ' topics · weight ' + Math.round((s.weight || 0) * 100) + '% · bank ' + (s.bank_q || 0) + ' Qs' + (s.bank_gap ? ' · ⚠️ bank gap' : '') + ')</span></span><span>' + esc(s.status) + (s.mastery != null ? ' · ' + Math.round(s.mastery * 100) + '%' : '') + '</span></div>').join('') +
    (d.note ? '<div class="muted" style="margin-top:6px;">' + esc(d.note) + '</div>' : '') +
    (d.next_subject ? '<div class="muted">➡️ Next: <b>' + esc(d.next_subject) + '</b> topics cover cheyyandi</div>' : '');
}
async function loadPercentile() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/percentile?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  out.innerHTML = d.percentile == null
    ? '<div class="muted">📈 ' + esc(d.note || 'Inka data ledu') + '</div>'
    : '<b>📈 Goal Percentile</b> <span class="chip gold">Top ' + (100 - d.percentile) + '%</span><div class="muted">Rank #' + d.rank + ' / ' + d.students + ' students · Mee best: ' + d.my_best + ' · Top score: ' + d.top + ' (honest estimate — mock scores nunchi)</div>';
}
async function addMaterial230() {
  const body = { title: (document.getElementById('mat-title') || {}).value || '',
                 file: (document.getElementById('mat-file') || {}).value || '',
                 goal: (document.getElementById('mat-goal') || {}).value || 'all',
                 cost: parseInt((document.getElementById('mat-cost') || {}).value || '0', 10) || 0 };
  const d = await api('/api/admin/materials_add', 'POST', JSON.stringify(body));
  alert(d.ok ? '✅ Material added: ' + (d.item || {}).title : ('❌ ' + (d.error || 'failed')));
}
async function runHarvest230() {
  if (!confirm('Top harvest target run cheyyala? (production lo real PYQ download avthundi)')) return;
  const d = await api('/api/admin/harvest_run', 'POST', '{}');
  alert((d && d.message) || 'done');
}
async function loadDistrict() {
  const out = document.getElementById('adv-out');
  out.innerHTML = '<div class="muted">Loading district…</div>';
  const d = await api('/api/portal/district?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  out.innerHTML = '<b>🏙️ ' + esc(d.my_district || 'District') + ' Deep-Dive</b>' +
    (d.my_rank ? ' <span class="chip gold">Naa rank #' + d.my_rank + ' / ' + d.students_in_district + '</span>' : '') +
    (d.district_rank ? '<div class="muted">District league rank: <b>#' + d.district_rank + '</b> / ' + d.districts + ' districts · Naa points: ' + d.my_points + '</div>' : '') +
    (d.champion ? '<div style="margin-top:4px;">👑 District Champion: <b>' + esc(d.champion.name) + '</b> (' + d.champion.points + ' pts)</div>' : '') +
    (d.goal_champion ? '<div>🎯 Naa Goal Champion: <b>' + esc(d.goal_champion.name) + '</b> (' + d.goal_champion.points + ' pts)' + (d.goal_champion.me ? ' — meeru!' : '') + '</div>' : '') +
    ((d.chase || []).length ? '<div style="margin-top:6px;"><b>🎯 Overtake Targets</b>' + d.chase.map(c => '<div style="display:flex; justify-content:space-between; margin:3px 0;"><span>' + esc(c.name) + '</span><span class="muted">' + c.points + ' pts · gap ' + c.gap + '</span></div>').join('') + '</div>' : '<div class="muted" style="margin-top:6px;">🏆 Meeru district lo #1 — maintain cheyyandi!</div>') +
    ((d.board || []).length ? '<div style="margin-top:6px;"><b>🏙️ District League</b>' + d.board.map((r, i) => '<div style="display:flex; justify-content:space-between; margin:3px 0;"><span>#' + (i + 1) + ' ' + esc(r.name) + '</span><span class="muted">' + r.pts + ' pts · ' + r.students + ' students</span></div>').join('') + '</div>' : '');
}
async function loadRevision() {
  const out = document.getElementById('adv-out');
  out.innerHTML = '<div class="muted">Loading planner…</div>';
  const d = await api('/api/portal/revision?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  out.innerHTML = '<b>🧠 Smart Revision Planner</b>' +
    (d.empty ? '<div class="muted" style="margin-top:4px;">🎉 Ivalla revise cheyyalsindi em ledu — okka mock rayandi, plan tayaravthundi!</div>'
      : (d.plan || []).map(p => '<div style="display:flex; justify-content:space-between; margin:3px 0;"><span>' + p.icon + ' ' + esc(p.label) + '</span>' + (p.count ? '<span class="muted">' + p.count + '</span>' : '') + '</div>').join(''));
}
async function loadRank2() {
  const out = document.getElementById('adv-out');
  out.innerHTML = '<div class="muted">Loading rank…</div>';
  const d = await api('/api/portal/rank2?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  const coh = (c, label) => c ? '<div style="margin-top:4px;"><b>' + label + '</b>: Rank <b>#' + c.my_rank + '</b> / ' + c.students + ' · Percentile <b>' + c.percentile + '%</b>' + (c.next ? ' <span class="muted">· Next rank ki ' + c.next.gap + ' pts gap</span>' : ' <span class="muted">· 🏆 Meeru #1!</span>') + '</div>' : '';
  out.innerHTML = '<b>🎯 Rank Predictor v2</b><div class="muted">Naa points: <b>' + d.my_points + '</b> · Goal: ' + esc(d.goal || '') + '</div>' +
    coh(d.goal_cohort, '🎓 Naa Goal Cohort') + coh(d.district_cohort, '🏙️ Naa District') + coh(d.overall, '🌐 Overall');
}
async function loadMaterials() {
  const out = document.getElementById('adv-out');
  out.innerHTML = '<div class="muted">Loading materials…</div>';
  const d = await api('/api/portal/materials?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  out.innerHTML = '<b>📚 Materials Vault</b> <span class="muted">· ⭐ ' + d.points + ' pts · Goal: ' + esc(d.goal || '') + '</span>' +
    ((d.items || []).length ? d.items.map(it =>
      '<div style="display:flex; justify-content:space-between; align-items:center; margin:5px 0; gap:8px;"><span>' + esc(it.title) + (it.subject ? ' <span class="muted">' + esc(it.subject) + '</span>' : '') + '</span>' +
      (it.owned
        ? (it.kind === 'file'
            ? '<a class="btn-alt" style="width:auto; margin:0; padding:2px 10px;" href="/api/portal/material_file?token=' + encodeURIComponent(token) + '&id=' + encodeURIComponent(it.id) + '">⬇️ Download</a>'
            : '<span class="chip">✅ Unlocked</span>')
        : '<button class="btn-alt" style="width:auto; margin:0;" onclick="unlockMaterial(\'' + it.id + '\')">🔓 ' + it.cost + ' pts</button>') +
      '</div>').join('')
      : '<div class="muted" style="margin-top:4px;">Meeru goal ki materials inka levu — th్వరలో vasthayi!</div>');
  try {
    const sg = await api('/api/portal/materials_suggest?token=' + encodeURIComponent(token));
    if (sg.ok && (sg.suggestions || []).length) {
      out.innerHTML += '<div style="margin-top:8px;"><b>🤖 Meekosam AI Picks</b>' +
        sg.suggestions.map(s => '<div class="muted" style="margin:2px 0;">' + esc(s.title) + ' — <span class="muted">' + esc(s.reason || '') + '</span></div>').join('') + '</div>';
    }
  } catch (e) {}
}
async function unlockMaterial(id) {
  const d = await api('/api/portal/materials_unlock', 'POST', JSON.stringify({ token: token, id: id }));
  alert(d.message || (d.ok ? 'Unlocked!' : 'Failed'));
  if (d.ok) loadMaterials();
}
async function loadScoreIntel() {
  const out = document.getElementById('adv-out');
  out.innerHTML = '<div class="muted">Loading score intelligence…</div>';
  const d = await api('/api/portal/score_intel?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  const f = (d.forecast || {}).v2 || d.forecast || {};
  const rk = d.rank || {};
  out.innerHTML = '<b>🏆 Score Intelligence</b>' +
    (f.expected_pct != null ? '<div style="margin-top:4px;">🔮 Forecast: <b>' + f.expected_pct + '%</b> <span class="muted">(' + (f.low != null ? f.low + '–' + f.high + '% · ' : '') + esc(f.confidence || '') + ' confidence)</span></div>' : '') +
    (rk.goal_cohort ? '<div>🎯 Goal rank: <b>#' + rk.goal_cohort.my_rank + '</b> / ' + rk.goal_cohort.students + ' · Percentile ' + rk.goal_cohort.percentile + '%' + (rk.goal_cohort.next ? ' <span class="muted">· next rank ' + rk.goal_cohort.next.gap + ' pts</span>' : '') + '</div>' : '') +
    (d.weak_section ? '<div>🧩 Weak section: <b>' + esc(d.weak_section.subject) + '</b></div>' : '') +
    (d.advice ? '<div class="muted" style="margin-top:4px;">' + esc(d.advice) + '</div>' : '');
}
async function loadBookmarks() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/bookmarks?token=' + encodeURIComponent(token));
  const bm = d.bookmarks || [];
  out.innerHTML = '<b>🔖 Saved Questions (' + bm.length + ')</b>' + (bm.length ? '' : '<div class="muted">Inka em save cheyyaledu — practice lo 🔖 nokkandi.</div>') +
    bm.slice(0, 10).map(q => '<div class="rrow"><b>' + esc(q.topic || '') + '</b> ' + esc(q.q_en || q.q_te || '') + '<br><button class="btn-alt" style="width:auto; margin-top:4px;" onclick="toggleBookmark(\'' + esc(q.id) + '\')">✖ Remove</button></div>').join('');
}
async function toggleBookmark(qid) {
  const d = await api('/api/portal/bookmark', {token, qid});
  if (d.ok) loadBookmarks();
}
async function searchPractice() {
  const q = (document.getElementById('search-q').value || '').trim();
  if (q.length < 3) { alert('Kammi 3 letters ivvandi'); return; }
  const d = await api('/api/portal/search', {token, q});
  if (!d.ok) { alert('❌ ' + (d.error || 'Search avvaledu')); return; }
  PR = {run_id: d.run_id, questions: d.questions || [], cur: 0, score: 0, per_q: 0};
  show('view-prc'); renderPr();
}
async function loadDailyReview() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/daily_review?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  out.innerHTML = '<b>📅 Daily Review</b> <span class="chip">' + (d.correct || 0) + ' correct</span>' +
    (d.rows || []).map(r => '<div class="rrow ' + (r.right ? 'ok' : 'bad') + '"><b>Q' + (r.i + 1) + '.</b> ' + esc(r.en || r.te || '') +
      '<br><span class="muted">Meeru: ' + esc(r.given_text) + (r.right ? ' ✅' : ' ❌ · Correct: ' + esc(r.answer_text)) + '</span>' +
      (r.explanation ? '<br><span class="muted">💡 ' + esc(r.explanation) + '</span>' : '') + '</div>').join('');
}
async function resumeMock() {
  const d = await api('/api/portal/resume?token=' + encodeURIComponent(token));
  if (!d.ok || !d.mock) { alert('Resume cheyyadaniki aapina mock ledu'); return; }
  MOCK = {run_id: d.mock.run_id, answers: {}, t0: Date.now(), times: {}};
  document.getElementById('m-title').textContent = '▶️ Resume: ' + d.mock.label;
  const box = document.getElementById('m-qs'); box.innerHTML = '';
  d.mock.questions.forEach((q) => {
    const div = document.createElement('div'); div.id = 'mq' + q.i;
    div.innerHTML = '<div class="muted" style="font-size:11px; margin-top:12px;">' + esc(qMeta(q)) + '</div><div class="qte" style="margin-top:4px;">Q' + (q.i + 1) + '. ' + esc(q.te || q.en) + '</div>' + (q.te && q.en ? '<div class="qen">' + esc(q.en) + '</div>' : '');
    q.options.forEach((opt, oi) => {
      const b = document.createElement('button'); b.className = 'opt' + ((d.mock.answers || {})[q.i] === oi ? ' picked' : ''); b.textContent = optText(q, oi, opt);
      b.dataset.qref = regQ(q); b.dataset.oi = oi;
      if ((d.mock.answers || {})[q.i] === oi) MOCK.times = MOCK.times || {}; if (MOCK.times[q.i] == null) MOCK.times[q.i] = Math.round((Date.now() - (MOCK.t0 || Date.now())) / 1000); MOCK.answers[q.i] = oi;
      b.onclick = () => { div.querySelectorAll('.opt').forEach(x => x.classList.remove('picked')); b.classList.add('picked'); MOCK.times = MOCK.times || {}; if (MOCK.times[q.i] == null) MOCK.times[q.i] = Math.round((Date.now() - (MOCK.t0 || Date.now())) / 1000); MOCK.answers[q.i] = oi; markPalette(q.i); };
      div.appendChild(b);
    });
    box.appendChild(div);
  });
  show('view-mock');
  alert('▶️ ' + d.mock.answered + ' answers restore ayyayi — migithavi complete cheyyandi!');
}
async function downloadMyData() {
  const d = await api('/api/portal/mydata?token=' + encodeURIComponent(token));
  if (!d.ok || !d.text) { alert('❌ ' + (d.error || '')); return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([d.text], {type: 'application/json;charset=utf-8'}));
  a.download = d.filename || 'StudentUp-MyData.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
async function startBlueprint() {
  const goal = (STATE && STATE.student && STATE.student.goal) || 'mixed';
  const negEl = document.getElementById('neg-sel');
  const neg = negEl ? parseFloat(negEl.value || '0') : 0;
  const d = await api('/api/portal/mock/start', {token, goal, neg, kind: 'blueprint'});
  if (!d.ok) { alert('❌ ' + (d.error || 'Blueprint Mock start avvaledu')); return; }
  MOCK = d; MOCK.t0 = Date.now(); MOCK.times = {};
  document.getElementById('m-title').textContent = '🧩 ' + d.label;
  renderMockRun(d);
}
async function loadTopicNotes() {
  const q = PR && PR.questions[PR.cur];
  const topic = q ? (q.topic || '') : '';
  const d = await api('/api/portal/notes?topic=' + encodeURIComponent(topic) + '&token=' + encodeURIComponent(token));
  const fb = document.getElementById('p-fb');
  if (!d.ok) { fb.textContent = '❌ ' + (d.error || ''); return; }
  fb.innerHTML = (d.notes || []).length ? (d.notes || []).map(n =>
    '<div style="margin-top:7px; padding:8px 10px; background:#0f1e38; border:1px solid #24466e; border-radius:9px;"><b>📖 ' + esc(n.topic || '') + '</b><div style="margin-top:4px;">' + esc(n.en || '') + '</div>' +
    (n.te ? '<div class="muted" style="margin-top:4px;">' + esc(n.te) + '</div>' : '') + '</div>').join('')
    : '<div class="muted">Ee topic ki notes levu.</div>';
}
document.addEventListener('keydown', (e) => {
  // ⌨️ 100X keyboard shortcuts: 1-4 answer, N/Enter next (practice/quiz)
  if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT')) return;
  const prc = document.getElementById('view-prc');
  const quiz = document.getElementById('view-quiz');
  const inPrc = prc && prc.style.display !== 'none';
  const inQuiz = quiz && quiz.style.display !== 'none';
  if (!inPrc && !inQuiz) return;
  const box = document.getElementById(inPrc ? 'p-opts' : 'opts');
  if (['1', '2', '3', '4'].includes(e.key) && box) {
    const b = box.children[parseInt(e.key, 10) - 1];
    if (b && !b.disabled) b.click();
  } else if ((e.key === 'n' || e.key === 'N' || e.key === 'Enter')) {
    const nb = document.getElementById(inPrc ? 'p-next' : 'q-next');
    if (nb && nb.style.display !== 'none') nb.click();
  }
});
async function loadBotLink() {
  const el = document.getElementById('bot-link-card');
  if (!el || !token) return;
  try {
    const d = await api('/api/portal/bot_link?token=' + encodeURIComponent(token));
    if (!d.ok) { el.innerHTML = ''; return; }
    if (d.linked) {
      el.innerHTML = '<div class="muted" style="font-size:12.5px;">🤖 Telegram Bot: <b style="color:#34d399;">✅ Linked</b> — bot lopala portal one-tap login!<br>⌨️ Bot commands: /portal · /today · /top · /unlink</div>' +
        (d.bot ? '<a href="https://t.me/' + esc(d.bot) + '" target="_blank" rel="noopener"><button class="btn-alt" style="width:100%; margin-top:6px;">🤖 Bot Open Chey</button></a>' : '');
    } else {
      el.innerHTML = '<button class="btn-alt" style="width:100%;" onclick="linkBot()">🤖 Telegram Bot tho Link Chey (one-tap login)</button>';
    }
  } catch (e) { el.innerHTML = ''; }
}
async function linkBot() {
  const d = await api('/api/portal/tg_link', {token});
  if (!d.ok) { alert(d.error || 'Try again'); return; }
  if (!d.bot) { alert('Bot inka configure cheyyaledu — koddi sepatilo try cheyyandi.'); return; }
  window.open('https://t.me/' + d.bot + '?start=' + d.param, '_blank');
}
function speakCurrent(which) {
  try {
    const q = which === 'prc' ? (PR && PR.questions[PR.cur]) : QUESTIONS[cur];
    if (!q || !window.speechSynthesis) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance((q.te || '') + '. ' + (q.en || ''));
    u.lang = q.te ? 'te-IN' : 'en-IN';
    u.rate = 0.95;
    speechSynthesis.speak(u);
  } catch (e) { /* device support lekapothe silent */ }
}
async function startAdaptive() {
  const goal = (STATE && STATE.student && STATE.student.goal) || 'mixed';
  const negEl = document.getElementById('neg-sel');
  const neg = negEl ? parseFloat(negEl.value || '0') : 0;
  const d = await api('/api/portal/mock/start', {token, goal, neg, kind: 'adaptive'});
  if (!d.ok) { alert('❌ ' + (d.error || 'Adaptive Mock start avvaledu')); return; }
  MOCK = d; MOCK.t0 = Date.now(); MOCK.times = {};
  document.getElementById('m-title').textContent = '🧠 ' + d.label;
  renderMockRun(d);
}
function renderMockRun(d) {
  const box = document.getElementById('m-qs'); box.innerHTML = '';
  renderPalette(d.questions);
  d.questions.forEach((q) => {
    const div = document.createElement('div'); div.id = 'mq' + q.i;
    div.innerHTML = '<div class="muted" style="font-size:11px; margin-top:12px;">' + esc(qMeta(q)) + '</div><div class="qte" style="margin-top:4px;">Q' + (q.i + 1) + '. ' + esc(q.te || q.en) + '</div>' + (q.te && q.en ? '<div class="qen">' + esc(q.en) + '</div>' : '');
    q.options.forEach((opt, oi) => {
      const b = document.createElement('button'); b.className = 'opt'; b.textContent = optText(q, oi, opt);
      b.dataset.qref = regQ(q); b.dataset.oi = oi;
      b.onclick = () => { div.querySelectorAll('.opt').forEach(x => x.classList.remove('picked')); b.classList.add('picked'); MOCK.answers = MOCK.answers || {}; MOCK.times = MOCK.times || {}; if (MOCK.times[q.i] == null) MOCK.times[q.i] = Math.round((Date.now() - (MOCK.t0 || Date.now())) / 1000); MOCK.answers[q.i] = oi; markPalette(q.i); };
      div.appendChild(b);
    });
    box.appendChild(div);
  });
  renderPalette(d.questions);
  show('view-mock');
  let left = (d.minutes || 15) * 60;
  const tEl = document.getElementById('m-timer');
  clearInterval(mockTimer);
  mockTimer = setInterval(() => {
    left--; tEl.textContent = '⏱ ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
    if (left <= 0) { clearInterval(mockTimer); submitMock(); }
  }, 1000);
}
function renderPalette(questions) {
  let pal = document.getElementById('m-palette');
  if (!pal) return;
  pal.innerHTML = (questions || []).map(q =>
    '<button class="tchip" id="pal' + q.i + '" style="min-width:30px;" onclick="jumpQ(' + q.i + ')">' + (q.i + 1) + '</button>').join('');
}
function markPalette(i) {
  const el = document.getElementById('pal' + i);
  if (el) el.classList.add('on');
}
function jumpQ(i) {
  const el = document.getElementById('mq' + i);
  if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
}
async function weeklyReport() {
  const d = await api('/api/portal/weekly_report?token=' + encodeURIComponent(token));
  if (!d.ok || !d.text) { alert('❌ ' + (d.error || '')); return; }
  window.open('https://wa.me/?text=' + encodeURIComponent(d.text), '_blank');
}
function seriesCert() {
  window.open('/api/portal/series/certificate?token=' + encodeURIComponent(token), '_blank');
}
async function setGoal2(g) {
  const d = await api('/api/portal/goal2', {token, goal: g});
  if (d.ok) { alert('🎯 Second goal: ' + (d.label || 'cleared')); loadState(); }
}
async function downloadMistakes() {
  const d = await api('/api/portal/mistakes?token=' + encodeURIComponent(token));
  if (!d.ok || !d.text) { alert('❌ ' + (d.error || '')); return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([d.text], {type: 'text/plain;charset=utf-8'}));
  a.download = d.filename || 'StudentUp-Mistakes.txt'; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
async function showAllNotices() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/notices?token=' + encodeURIComponent(token));
  if (!d.ok) { alert('❌ ' + (d.error || '')); return; }
  out.innerHTML = '<h4 style="margin-bottom:6px;">📢 Anni Notices</h4>' + ((d.notices || []).map(n =>
    '<div style="padding:7px 10px; background:#0f1e38; border:1px solid #24466e; border-radius:9px; margin-top:6px;"><b>' + esc(n.title || '') + '</b><div class="muted">' + esc(n.body || '') + '</div></div>').join('')
    || '<div class="muted">Notices levu.</div>');
  out.scrollIntoView({behavior: 'smooth', block: 'center'});
}
let _focusTotal = 25 * 60, _focusLeft = 25 * 60, _focusTimer = null;
function _focusDraw() {
  const el = document.getElementById('focus-clock'); if (!el) return;
  const m = String(Math.floor(_focusLeft / 60)).padStart(2, '0'), s = String(_focusLeft % 60).padStart(2, '0');
  el.textContent = m + ':' + s;
}
function focusPreset(min) { focusReset(); _focusTotal = _focusLeft = min * 60; _focusDraw(); }
function focusReset() {
  clearInterval(_focusTimer); _focusTimer = null;
  _focusLeft = _focusTotal; _focusDraw();
  const b = document.getElementById('focus-btn'); if (b) b.textContent = '▶️ Start Focus';
}
async function _focusDone() {
  focusReset();
  const mins = Math.round(_focusTotal / 60);
  const d = await api('/api/portal/focus', {token, minutes: mins});
  if (d.ok) {
    const st = document.getElementById('focus-stats');
    if (st) st.textContent = 'Ee roju focus: ' + d.today_min + ' min · Ee week: ' + d.week_min + ' min';
    alert('🎉 ' + mins + ' min focus complete! Study minutes log ayyayi 📈');
    loadHome();
  }
}
function focusToggle() {
  const b = document.getElementById('focus-btn');
  if (_focusTimer) { clearInterval(_focusTimer); _focusTimer = null; if (b) b.textContent = '▶️ Resume Focus'; return; }
  if (b) b.textContent = '⏸️ Pause';
  _focusTimer = setInterval(() => {
    _focusLeft -= 1; _focusDraw();
    if (_focusLeft <= 0) _focusDone();
  }, 1000);
}
async function loadGoalHub(g) {
  const box = document.getElementById('goal-hub'); if (!box) return;
  box.innerHTML = '<p class="muted">Loading…</p>';
  const d = await api('/api/portal/goal_hub?goal=' + encodeURIComponent(g) + '&token=' + encodeURIComponent(token));
  if (!d.ok) { box.innerHTML = '<p class="muted">❌ ' + esc(d.error || '') + '</p>'; return; }
  box.innerHTML =
    '<b style="font-size:15px;">' + esc(d.label) + '</b>' +
    '<div class="row" style="margin-top:7px; flex-wrap:wrap; gap:6px;">' +
    '<span class="chip">📜 ' + d.pyq + ' real PYQ</span><span class="chip">🎯 ' + (d.pyq_exam != null ? d.pyq_exam : d.pyq) + ' ' + esc(d.label) + ' PYQ</span><span class="chip">🧠 ' + d.total + ' questions</span>' +
    '<span class="chip">📄 ' + d.papers + ' paper sets</span><span class="chip gold">✍️ Mee attempts: ' + d.attempts + ' · Best ' + d.best + '%</span>' +
    ((d.readiness && d.readiness.score != null) ? '<span class="chip" style="border-color:#34d399;">🎯 Readiness: ' + d.readiness.score + '/100' + (d.readiness.band ? ' · ' + esc(d.readiness.band) : '') + '</span>' : '') + '</div>' +
    ((d.paper_labels || []).length ? '<p class="muted" style="margin-top:7px;">📜 Papers: ' + d.paper_labels.map(esc).join(' · ') + '</p>' : '') +
    ((d.topics || []).length ? '<p class="muted" style="margin-top:7px;">📈 Repeat ayye topics: ' + d.topics.map(t => esc(t.topic) + ' (' + t.pyq + ')').join(' · ') + '</p>' : '') +
    '<p style="margin-top:7px;">👉 ' + esc(d.next) + '</p>' +
    '<div class="row" style="margin-top:8px; gap:6px;"><button class="btn-main" style="flex:1;" onclick="startMock(\'' + d.goal + '\', \'exam\')">📜 ' + esc(d.label) + ' PYQ Mock</button>' +
    '<button class="btn-alt" style="width:auto; margin:0;" onclick="startMock(\'' + d.goal + '\', \'blueprint\')">🧩 Blueprint</button>' +
    '<button class="btn-alt" style="width:auto; margin:0;" onclick="startMock(\'' + d.goal + '\')">📝 Mixed Mock</button>' +
    '<button class="btn-alt" style="width:auto; margin:0;" onclick="startPractice(\'pyq\', \'\', \'' + d.goal + '\')">🎯 PYQ Drill</button></div>';
}
async function remindExam(id, el) {
  const on = !(el && el.dataset && el.dataset.on === '1');
  const d = await api('/api/portal/exam/remind', {token, exam_id: id, on});
  if (!d.ok) { alert('❌ ' + (d.error || '')); return; }
  if (el) { el.dataset.on = d.remind ? '1' : '0'; el.textContent = d.remind ? '🔔 Reminder ON' : '🔕 Notify Me'; }
}
async function loadStudyPlan() {
  const out = document.getElementById('adv-out');
  out.innerHTML = '<div class="muted">Plan tayaru avuthondi…</div>';
  const d = await api('/api/portal/study_plan?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  out.innerHTML = '<b>📅 7-Day Study Plan</b>' + (d.exam_in ? ' <span class="chip gold">' + esc(d.exam_in.label) + ' — ' + d.exam_in.days + ' rojulu</span>' : '') +
    (d.days || []).map(x => '<div style="margin:5px 0;"><b>Day ' + x.day + '</b> <span class="muted">' + x.date + '</span> — 🎯 ' + esc(x.focus) + '<br><span class="muted">' + (x.tasks || []).map(esc).join(' · ') + '</span></div>').join('');
}
async function loadForecast() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/forecast?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  if (d.v2) {
    const v = d.v2;
    out.innerHTML = '<b>🔮 Score Forecast v2</b> <span class="chip gold">~' + v.expected_pct + '%</span> <span class="muted">confidence: ' + esc(v.confidence) + ' (' + v.answers_seen + ' answers)</span><div class="muted">Next mock expected range: ' + v.low + '–' + v.high + '% · Syllabus coverage: ' + (v.coverage != null ? v.coverage + '%' : '—') + '</div>' +
      (v.subjects || []).map(s => '<div style="display:flex; justify-content:space-between; margin:4px 0;"><span>' + esc(s.subject) + ' <span class="muted">(weight ' + Math.round((s.weight || 0) * 100) + '%' + (s.bank_gap ? ' · ⚠️ bank gap' : '') + ')</span></span><span>~' + s.expected_pct + '%' + (s.mastery != null ? ' · mastery ' + Math.round(s.mastery * 100) + '%' : '') + '</span></div>').join('') +
      (v.drivers || []).map(t => '<div class="muted" style="margin-top:4px;">' + esc(t) + '</div>').join('') +
      '<div class="muted" style="margin-top:6px;">' + esc(v.note || '') + '</div>';
    return;
  }
  out.innerHTML = '<b>🔮 Score Forecast</b> <span class="chip gold">~' + d.expected_pct + '%</span><div class="muted">Next mock expected range: ' + d.low + '–' + d.high + '% · Band: ' + esc(d.band || '') + '<br>' + esc(d.note || '') + '</div>';
}
async function loadTrend() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/trend?token=' + encodeURIComponent(token));
  const tr = d.trend || [];
  if (!tr.length) { out.innerHTML = '<div class="muted">📊 Inka attempts levu — okka mock rayandi, trend ikkada kanipisthundi.</div>'; return; }
  out.innerHTML = '<b>📊 Score Trend</b>' + tr.map(r => {
    const w = Math.max(4, r.pct);
    return '<div style="display:flex; align-items:center; gap:7px; margin:4px 0;"><span class="muted" style="width:118px; font-size:11px;">' + esc((r.title || r.kind || '').slice(0, 20)) + '</span><span style="flex:1; background:rgba(56,189,248,.15); border-radius:5px;"><span style="display:block; width:' + w + '%; height:13px; border-radius:5px; background:#38bdf8;"></span></span><b>' + r.pct + '%</b></div>';
  }).join('') + '<div class="muted">' + (d.activity || []).filter(a => a.active).length + ' active days (last 14)</div>';
}
async function loadTrends() {
  const out = document.getElementById('adv-out');
  const goal = (STATE && STATE.student && STATE.student.goal) || '';
  const d = await api('/api/portal/pyq_trends?goal=' + encodeURIComponent(goal));
  if (!d.ok) { out.innerHTML = '<div class="muted">Trends ready ledu</div>'; return; }
  out.innerHTML = '<b>📈 PYQ Trends</b> <span class="chip">' + d.pyq_total + ' PYQ questions</span><div class="muted">Previous papers lo ekkuva repeat ayye topics — ive master ayithe marks:</div>' +
    (d.topics || []).map(t => '<div style="display:flex; justify-content:space-between; margin:3px 0;"><span>' + esc(t.topic) + '</span><b>' + t.pyq + ' Qs · ' + t.share + '%</b></div>').join('');
}
async function loadGoalBoard() {
  const out = document.getElementById('adv-out');
  const goal = (STATE && STATE.student && STATE.student.goal) || 'mixed';
  const d = await api('/api/portal/goal_board?goal=' + encodeURIComponent(goal));
  const rows = d.board || [];
  out.innerHTML = '<b>🏆 Goal Leaderboard</b>' + (rows.length ? '' : '<div class="muted">Ee goal lo inka scores levu — first meeru avvandi!</div>') +
    rows.map((r, i) => '<div style="display:flex; justify-content:space-between; margin:3px 0;"><span>' + (i + 1) + '. ' + esc(r.name) + ' <span class="muted">' + esc(r.district || '') + '</span></span><b>' + r.correct + '/' + r.total + '</b></div>').join('');
}
async function startGrand() {
  const goal = (STATE && STATE.student && STATE.student.goal) || 'mixed';
  const negEl = document.getElementById('neg-sel');
  const neg = negEl ? parseFloat(negEl.value || '0') : 0;
  const d = await api('/api/portal/mock/start', {token, goal, neg, kind: 'grand'});
  if (!d.ok) { alert('❌ ' + (d.error || 'Grand Mock start avvaledu')); return; }
  MOCK = d; MOCK.t0 = Date.now(); MOCK.times = {};
  document.getElementById('m-title').textContent = '🏛️ ' + d.label;
  const box = document.getElementById('m-qs'); box.innerHTML = '';
  d.questions.forEach((q) => {
    const div = document.createElement('div'); div.id = 'mq' + q.i;
    div.innerHTML = '<div class="muted" style="font-size:11px; margin-top:12px;">' + esc(qMeta(q)) + '</div><div class="qte" style="margin-top:4px;">Q' + (q.i + 1) + '. ' + esc(q.te || q.en) + '</div>' + (q.te && q.en ? '<div class="qen">' + esc(q.en) + '</div>' : '');
    q.options.forEach((opt, oi) => {
      const b = document.createElement('button'); b.className = 'opt'; b.textContent = optText(q, oi, opt);
      b.dataset.qref = regQ(q); b.dataset.oi = oi;
      b.onclick = () => { div.querySelectorAll('.opt').forEach(x => x.classList.remove('picked')); b.classList.add('picked'); MOCK.answers = MOCK.answers || {}; MOCK.times = MOCK.times || {}; if (MOCK.times[q.i] == null) MOCK.times[q.i] = Math.round((Date.now() - (MOCK.t0 || Date.now())) / 1000); MOCK.answers[q.i] = oi; markPalette(q.i); };
      div.appendChild(b);
    });
    box.appendChild(div);
  });
  show('view-mock');
  let left = (d.minutes || 60) * 60;
  const tEl = document.getElementById('m-timer');
  clearInterval(mockTimer);
  mockTimer = setInterval(() => {
    left--; tEl.textContent = '⏱ ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
    if (left <= 0) { clearInterval(mockTimer); submitMock(); }
  }, 1000);
}
async function loadSections() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/sections?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  out.innerHTML = '<b>🧩 Sectional Tests</b>' + (d.sections || []).map(x =>
    '<div style="display:flex; justify-content:space-between; align-items:center; margin:5px 0;"><span>' + esc(x.label) + ' <span class="muted">' + x.total + ' Qs · ' + x.pyq + ' PYQ</span></span>' +
    '<button class="btn-alt" style="width:auto; margin:0;" onclick="startSection(\'' + x.subject + '\')">Start ▶</button></div>').join('');
}
function startSection(subject) {
  const sel = document.getElementById('topic-sel');
  PR_MODE_OVERRIDE = subject;
  startPractice('section', subject);
}
async function loadPatterns() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/patterns?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  out.innerHTML = '<b>📉 Mistake Patterns</b><div class="muted">Concept gaps: ' +
    ((d.concept_gaps || []).map(g => esc(g.topic) + ' ×' + g.wrongs).join(', ') || 'levu') +
    '<br>Slips: ' + ((d.slips || []).map(g => esc(g.topic)).join(', ') || 'levu') +
    ' · Skipped: ' + (d.skipped || 0) + '</div>' +
    (d.advice || []).map(a => '<div>' + esc(a) + '</div>').join('');
}
async function loadRetention() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/retention?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  const r = d.retention || {};
  out.innerHTML = '<b>🧠 Memory Retention</b> <span class="chip gold">' + (r.retention_score ?? '-') + '%</span>' +
    '<div class="muted">Cards: ' + (r.cards || 0) + ' · Today due: ' + (r.due_today || 0) +
    ' · Fresh ' + ((r.intervals || {}).fresh_0d || 0) + ' / 3d ' + ((r.intervals || {}).spaced_3d || 0) + ' / Strong 7d ' + ((r.intervals || {}).strong_7d || 0) + '</div>' +
    '<div class="muted">Next 7 days due: ' + (r.forecast || []).map(f => f.due).join(' · ') + '</div>' +
    (d.weekly_goal ? '<div>🎯 Weekly Goal: ' + esc(d.weekly_goal.text || '') + '</div>' : '');
}
async function loadRecords() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/records?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  const r = d.records || {}, sr = d.series || {};
  out.innerHTML = '<b>🏆 Personal Records</b><div class="muted">Attempts: ' + (r.attempts || 0) +
    ' · Best: ' + (r.best_pct != null ? r.best_pct + '% (' + esc(r.best_title || '') + ')' : '—') +
    '<br>Accuracy: ' + (r.accuracy || 0) + '% · Answered: ' + (r.answered || 0) +
    ' · 🔥 Streak ' + (r.streak || 0) + ' (best ' + (r.best_streak || 0) + ')</div>' +
    '<div>📚 Test Series: Test #' + (sr.next_no || 1) + ' ready · Progress ' + (sr.progress_pct || 0) + '%' +
    (sr.avg_pct != null ? ' · Avg ' + sr.avg_pct + '%' : '') + '</div>';
}
async function loadRival() {
  const out = document.getElementById('adv-out');
  const d = await api('/api/portal/rival?token=' + encodeURIComponent(token));
  if (!d.ok) { out.innerHTML = '<div class="muted">' + esc(d.error || '') + '</div>'; return; }
  if (!d.rival) {
    const code = prompt('🥊 Rival student SU code ivvandi (friend ref code):');
    if (!code) { out.innerHTML = '<div class="muted">Rival set cheyyaledu.</div>'; return; }
    const r = await api('/api/portal/rival/set', {token, ref: code});
    out.innerHTML = r.ok ? '<div>🥊 Rival: <b>' + esc(r.rival) + '</b> — ee week race start!</div>' : '<div class="muted">' + esc(r.error || '') + '</div>';
    return;
  }
  out.innerHTML = '<b>🥊 Rival Race (ee week)</b><div>Nenu: <b>' + d.my_pts + ' pts</b> · ' + esc(d.rival) + ': <b>' + d.rival_pts + ' pts</b><br>' +
    (d.leading === 'you' ? '🔥 Meeru mundhu unnaru (+' + d.diff + ') — maintain cheyyandi!' : '⚠️ Rival mundhu unnadu (' + d.diff + ') — oka mock raasi overtake cheyyandi!') + '</div>';
}
// 🌐 200X full-toggle: single-language option text (fallback merged)
window.__qpool = window.__qpool || {};
function regQ(q) {
  if (!q) return 'q' + (q && q.i);
  const key = 'k' + String(q.qid || '') + ':' + String(q.i);
  window.__qpool[key] = q;
  return key;
}
function optText(q, i, fallback) {
  const en = document.body.classList.contains('lang-en');
  const te = document.body.classList.contains('lang-te');
  if (en && q.options_en && q.options_en[i]) return q.options_en[i];
  if (te && q.options_te && q.options_te[i]) return q.options_te[i];
  return fallback;
}
let LANGS = ['both', 'te', 'en'];
async function cycleLang() {
  const cur = (STATE && STATE.student && STATE.student.lang) || localStorage.getItem('su_lang') || 'both';
  const nxt = LANGS[(LANGS.indexOf(cur) + 1) % LANGS.length];
  localStorage.setItem('su_lang', nxt);
  document.body.classList.remove('lang-te', 'lang-en');
  if (nxt !== 'both') document.body.classList.add('lang-' + nxt);
  if (STATE && STATE.student) STATE.student.lang = nxt;
  await api('/api/portal/lang', {token, lang: nxt});
  document.querySelectorAll('.opt').forEach(b => {
    if (b.dataset.qref != null && b.dataset.oi != null) {
      const pool = (window.__qpool || {});
      const q = pool[b.dataset.qref];
      if (q) b.textContent = optText(q, +b.dataset.oi, b.textContent);
    }
  });
  alert('🌐 Language: ' + (nxt === 'both' ? 'Telugu + English' : nxt === 'te' ? 'Telugu matrame' : 'English matrame'));
}
function applyLang() {
  const l = localStorage.getItem('su_lang') || (STATE && STATE.student && STATE.student.lang) || 'both';
  document.body.classList.remove('lang-te', 'lang-en');
  if (l !== 'both') document.body.classList.add('lang-' + l);
}
async function downloadRevisionPack() {
  const d = await api('/api/portal/revision_pack?token=' + encodeURIComponent(token));
  if (!d.ok || !d.text) { alert('❌ ' + (d.error || 'Revision pack avvaledu')); return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([d.text], {type: 'text/plain;charset=utf-8'}));
  a.download = d.filename || 'StudentUp-RevisionPack.txt'; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
let CHQ = null;
async function loadChallenge() {
  const el = document.getElementById('challenge-card');
  if (!el) return;
  const d = await api('/api/portal/challenge?token=' + encodeURIComponent(token));
  if (!d.ok) { el.innerHTML = ''; return; }
  if (d.done) { el.innerHTML = '<b>🏆 Challenge of the Day</b> <span class="chip gold">' + (d.correct ? '✅ +20 bonus!' : 'Ayipoyindi — repu malli') + '</span>'; return; }
  CHQ = d.question;
  if (!CHQ) { el.innerHTML = ''; return; }
  el.innerHTML = '<b>🏆 Challenge of the Day</b> <span class="chip">Correct ayithe +20 pts</span>' +
    '<div class="qte" style="margin-top:8px;">' + esc(CHQ.te || CHQ.en) + '</div>' + (CHQ.te && CHQ.en ? '<div class="qen">' + esc(CHQ.en) + '</div>' : '') +
    '<div id="ch-opts"></div><div id="ch-fb" class="feedback"></div>';
  const box = document.getElementById('ch-opts'); box.innerHTML = '';
  (CHQ.options || []).forEach((opt, i) => {
    const b = document.createElement('button'); b.className = 'opt'; b.textContent = opt;
    b.onclick = () => ansChallenge(i); box.appendChild(b);
  });
}
async function ansChallenge(i) {
  document.querySelectorAll('#ch-opts .opt').forEach(b => { b.disabled = true; });
  const d = await api('/api/portal/challenge/answer', {token, choice: i});
  const fb = document.getElementById('ch-fb');
  if (!d.ok) { fb.textContent = d.error || ''; return; }
  fb.innerHTML = d.correct ? '✅ Correct! +20 bonus points 🎉 ' + esc(d.explanation || '') : '❌ Correct: <b>' + esc(d.answer_text || '') + '</b> ' + esc(d.explanation || '');
}
async function downloadWorksheet() {
  const d = await api('/api/portal/worksheet?token=' + encodeURIComponent(token));
  if (!d.ok || !d.text) { alert('❌ ' + (d.error || 'Worksheet avvaledu')); return; }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([d.text], {type: 'text/plain;charset=utf-8'}));
  a.download = d.filename || 'StudentUp-Worksheet.txt'; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
async function startPaper(exam, year, paper) {
  const d = await api('/api/portal/paper/start', {token, exam, year, paper});
  if (!d.ok) { alert('❌ ' + (d.error || 'Paper start avvaledu')); return; }
  MOCK = d; MOCK.t0 = Date.now(); MOCK.times = {};
  document.getElementById('m-title').textContent = '📜 ' + d.label;
  const box = document.getElementById('m-qs'); box.innerHTML = '';
  d.questions.forEach((q) => {
    const div = document.createElement('div'); div.id = 'mq' + q.i;
    div.innerHTML = '<div class="muted" style="font-size:11px; margin-top:12px;">' + esc(qMeta(q)) + '</div><div class="qte" style="margin-top:4px;">Q' + (q.i + 1) + '. ' + esc(q.te || q.en) + '</div>' + (q.te && q.en ? '<div class="qen">' + esc(q.en) + '</div>' : '');
    q.options.forEach((opt, oi) => {
      const b = document.createElement('button'); b.className = 'opt'; b.textContent = optText(q, oi, opt);
      b.dataset.qref = regQ(q); b.dataset.oi = oi;
      b.onclick = () => { div.querySelectorAll('.opt').forEach(x => x.classList.remove('picked')); b.classList.add('picked'); MOCK.answers = MOCK.answers || {}; MOCK.times = MOCK.times || {}; if (MOCK.times[q.i] == null) MOCK.times[q.i] = Math.round((Date.now() - (MOCK.t0 || Date.now())) / 1000); MOCK.answers[q.i] = oi; markPalette(q.i); };
      div.appendChild(b);
    });
    box.appendChild(div);
  });
  renderPalette(d.questions);
  show('view-mock');
  let left = (d.minutes || 15) * 60;
  const tEl = document.getElementById('m-timer');
  clearInterval(mockTimer);
  mockTimer = setInterval(() => {
    left--; tEl.textContent = '⏱ ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
    if (left <= 0) { clearInterval(mockTimer); submitMock(); }
  }, 1000);
}
async function startMock(goal, kind) {
  const negEl = document.getElementById('neg-sel');
  const neg = negEl ? parseFloat(negEl.value || '0') : 0;
  const d = await api('/api/portal/mock/start', {token, goal, neg, kind: kind || 'mock'});
  if (!d.ok) { alert('❌ ' + (d.error || 'Mock start avvaledu')); return; }
  MOCK = d; MOCK.t0 = Date.now(); MOCK.times = {};
  document.getElementById('m-title').textContent = '📝 ' + d.label;
  const box = document.getElementById('m-qs'); box.innerHTML = '';
  d.questions.forEach((q) => {
    const div = document.createElement('div'); div.id = 'mq' + q.i;
    div.innerHTML = '<div class="muted" style="font-size:11px; margin-top:12px;">' + esc(qMeta(q)) + '</div><div class="qte" style="margin-top:4px;">Q' + (q.i + 1) + '. ' + esc(q.te || q.en) + '</div>' + (q.te && q.en ? '<div class="qen">' + esc(q.en) + '</div>' : '');
    q.options.forEach((opt, oi) => {
      const b = document.createElement('button'); b.className = 'opt'; b.textContent = optText(q, oi, opt);
      b.dataset.qref = regQ(q); b.dataset.oi = oi;
      b.onclick = () => { div.querySelectorAll('.opt').forEach(x => x.classList.remove('picked')); b.classList.add('picked'); MOCK.answers = MOCK.answers || {}; MOCK.times = MOCK.times || {}; if (MOCK.times[q.i] == null) MOCK.times[q.i] = Math.round((Date.now() - (MOCK.t0 || Date.now())) / 1000); MOCK.answers[q.i] = oi; markPalette(q.i); };
      div.appendChild(b);
    });
    box.appendChild(div);
  });
  renderPalette(d.questions);
  show('view-mock');
  let left = (d.minutes || 15) * 60;
  const tEl = document.getElementById('m-timer');
  clearInterval(mockTimer);
  mockTimer = setInterval(() => {
    left--; tEl.textContent = '⏱ ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
    if (left <= 0) { clearInterval(mockTimer); submitMock(); }
  }, 1000);
}
async function submitMock() {
  clearInterval(mockTimer);
  if (!MOCK) return;
  const answers = {};
  Object.entries(MOCK.answers || {}).forEach(([k, v]) => { answers[k] = v; });
  const d = await api('/api/portal/mock/submit', {token, run_id: MOCK.run_id, answers, times: MOCK.times || {}});
  if (!d.ok) { document.getElementById('m-err').textContent = d.error || ''; return; }
  document.getElementById('res-score').textContent = d.correct + '/' + d.total;
  document.getElementById('res-sub').textContent = '🎯 Accuracy ' + d.accuracy + '% · Leaderboard update ayindi!' +
    (d.neg ? ' 🏁 Negative −' + d.neg + ' apply ayyindi: Points ' + d.pts + ' (correct ' + d.correct + ', wrong ' + (d.wrong || 0) + ')' : '') +
    (d.avg_sec ? ' · ⏱ Avg ' + d.avg_sec + 's/question' + ((d.slow || []).length ? ' · 🐢 Slow: Q' + d.slow.map(i => i + 1).join(', Q') : '') : '');
  document.getElementById('res-review').innerHTML = (d.review || []).map(r => {
    const q = (d.questions || [])[r.i] || {};
    const opts = q.options || [];
    return '<div class="rrow ' + (r.right ? 'ok' : 'bad') + '"><b>Q' + (r.i + 1) + '.</b> ' + esc(q.en || q.te || '') +
      '<br><span class="muted">Meeru: ' + esc(opts[r.given] || '— (attempt cheyyaledu)') + (r.right ? ' ✅' : ' ❌ · Correct: ' + esc(opts[r.answer] || '')) + '</span>' +
      ((d.slow || []).includes(r.i) ? '<br><span class="muted">⏱ Ee question ki ekkuva time pattindi — shortcut practice cheyyandi.</span>' : '') +
      (q.explanation ? '<br><span class="muted">💡 ' + esc(q.explanation) + '</span>' : '') + '</div>';
  }).join('');
  const _mrun = MOCK.run_id;
  MOCK = null;
  api('/api/portal/attempt?token=' + encodeURIComponent(token) + '&run_id=' + encodeURIComponent(_mrun)).then(an => {
    if (!an.ok) return;
    const box = document.getElementById('res-review');
    const delta = an.delta_vs_prev == null ? '' : ' · Previous kante ' + (an.delta_vs_prev >= 0 ? '+' : '') + an.delta_vs_prev;
    box.insertAdjacentHTML('afterbegin', '<div class="rrow"><b>🔬 Attempt Analysis</b>' + delta +
      (an.weakest ? '<br><span class="muted">Weakest: ' + esc(an.weakest) + ' — ' + (an.wrong_topics || []).map(esc).join(', ') + '</span>' : '') +
      ((an.sections || []).length ? '<br><span class="muted">🧩 Sections: ' + an.sections.map(s => esc(s.subject) + ' ' + s.correct + '/' + s.total + ' (' + s.accuracy + '%' + (s.budget_sec ? ', ⏱' + Math.round((s.seconds || 0) / 60) + '/' + Math.round(s.budget_sec / 60) + 'm' + (s.over ? ' ⚠️over' : '') : '') + ')').join(' · ') + '</span>' : '') +
      (an.topics || []).map(t => '<br><span class="muted">' + esc(t.topic) + ': ' + t.correct + '/' + t.total + ' (' + t.accuracy + '%)</span>').join('') + '</div>');
  });
  show('view-result');
  document.getElementById('res-sub').insertAdjacentHTML('beforeend',
    '<br><button class="btn-alt" style="width:auto; margin-top:10px;" onclick="downloadKey(\'mock\',\'' + _mrun + '\')">⬇️ Answer Key Paper Download 📄</button>');
}
var STATE = null;
let PR = null;
let prTimer = null;
let PR_MODE_OVERRIDE = '';
// 🗺️ 330X: TS & AP Exam Hub — state-wise exams, honest counts,
// one-tap Mock (aa exam pool) + subject-wise tests (goal-scoped).
async function loadStateHub() {
  const box = document.getElementById('state-hub');
  if (!box || box.dataset.done) return;
  try {
    const d = await (await fetch('/api/portal/state_hub')).json();
    if (!d.ok) { box.innerHTML = '<p class="muted">Hub load avvaledu.</p>'; return; }
    box.dataset.done = '1';
    const subNames = {gk: 'GK', quant: 'Maths', reasoning: 'Reasoning', english: 'English', ca: 'Current Affairs', science: 'Science', polity: 'Polity', history: 'History'};
    box.innerHTML = (d.states || []).map(st =>
      '<p style="margin-top:10px;"><b>' + (st.state === 'Telangana' ? '🟢' : '🔵') + ' ' + esc(st.state) + '</b></p>' +
      st.exams.map(e =>
        '<div class="rrow"><b>' + esc(e.label) + '</b> <span class="muted">' + e.total + ' Q · PYQ ' + e.pyq + '</span>' +
        (e.papers_count ? ' <span class="chip">📜 ' + e.papers_count + ' paper sets · ' + e.papers_questions + ' Q</span>' : '') +
        (e.gap_total > 0 ? ' <span class="chip" style="border-color:#f59e0b; color:#f59e0b;">📈 +' + e.gap_total + ' stock kavali</span>' : ' <span class="chip gold">✅ Stock ready</span>') + '<br>' +
        '<button class="btn-alt" style="width:auto; margin-top:5px;" onclick="startMock(\'' + e.goal + '\')">🎯 Mock Test</button> ' +
        (e.papers || []).slice(0, 2).map(p2 =>
          '<button class="btn-alt" style="width:auto; margin-top:5px;" onclick="startPaper(\'' + esc(p2.exam) + '\',\'' + esc(p2.year || '') + '\',\'' + esc(p2.paper || '') + '\')">📜 ' + esc(p2.label) + ' (' + p2.count + ')</button>').join(' ') + ' ' +
        (e.subjects || []).filter(s2 => s2.count >= 3).slice(0, 4).map(s2 =>
          '<button class="btn-alt" style="width:auto; margin-top:5px;" onclick="startPractice(\'section\', \'' + s2.subject + '\', \'' + e.goal + '\')">🧩 ' + esc(subNames[s2.subject] || s2.subject) + '</button>').join(' ') +
        '</div>').join('')
    ).join('') +
    '<p style="margin-top:10px;"><b>🎓 Board Exams — Subject Tests (420X)</b></p>' +
    (d.academic || []).filter(a => a.total > 0).map(a =>
      '<div class="rrow"><b>' + esc(a.label) + '</b> <span class="muted">' + a.total + ' Q</span><br>' +
      '<button class="btn-alt" style="width:auto; margin-top:5px;" onclick="startPractice(\'board\', \'\', \'' + a.channel + '\')">🎓 Full Board Test</button> ' +
      (a.subjects || []).map(s2 =>
        '<button class="btn-alt" style="width:auto; margin-top:5px;" onclick="startPractice(\'board\', \'' + esc(s2.subject) + '\', \'' + a.channel + '\')">🧩 ' + esc(s2.subject) + ' (' + s2.count + ')</button>').join(' ') +
      '</div>').join('');
  } catch (e) { box.innerHTML = '<p class="muted">Hub load avvaledu.</p>'; }
}

async function startPractice(mode, subject, goal) {
  const topic = subject || PR_MODE_OVERRIDE || document.getElementById('topic-sel').value || '';
  PR_MODE_OVERRIDE = '';
  const d = await api('/api/portal/practice/start', {token, mode, topic, goal: goal || ''});
  if (!d.ok) { alert('❌ ' + (d.error || 'Practice start avvaledu')); return; }
  PR = {run_id: d.run_id, questions: d.questions || [], cur: 0, score: 0, per_q: d.per_q || 0};
  show('view-prc'); renderPr();
}
async function flagCurrent() {
  const q = PR && PR.questions[PR.cur];
  if (!q || !q.qid) return;
  const reason = prompt('🚩 Ee question lo emi tappu undi? (optional)') || '';
  const d = await api('/api/portal/flag', {token, qid: q.qid, reason});
  alert(d.ok ? '🚩 Report vellindi — team check chestundi, thanks!' : '❌ ' + (d.error || ''));
}
function bmCurrent() {
  const q = PR && PR.questions[PR.cur];
  if (!q || !q.qid) return;
  toggleBookmark(q.qid);
  const b = document.getElementById('p-bm');
  if (b) b.textContent = '🔖 Saved ✓';
}
function startPrTimer() {
  clearInterval(prTimer);
  const el = document.getElementById('p-timer');
  if (!PR || !PR.per_q) { if (el) el.style.display = 'none'; return; }
  let left = PR.per_q;
  el.style.display = 'inline-block'; el.textContent = '⚡ ' + left + 's';
  prTimer = setInterval(() => {
    left--;
    el.textContent = '⚡ ' + left + 's';
    if (left <= 0) {
      clearInterval(prTimer);
      // time ayipoyindi — correct answer chupinchi next ki ready
      const q = PR.questions[PR.cur];
      document.querySelectorAll('#p-opts .opt').forEach(b => { b.disabled = true; });
      api('/api/portal/practice/answer', {token, run_id: PR.run_id, idx: PR.cur, choice: -1}).then(d => {
        const fb = document.getElementById('p-fb');
        if (d && d.ok) {
          fb.innerHTML = '⏰ Time over! Correct: <b>' + esc(d.answer_text || '') + '</b>' + (d.explanation ? '<br><span class="muted">' + esc(d.explanation) + '</span>' : '');
          document.getElementById('p-score').textContent = '✅ ' + (d.score || PR.score);
        }
        const nb = document.getElementById('p-next');
        nb.textContent = (d && d.done) ? '🏠 Finish' : 'Next ➡️';
        nb.style.display = 'block';
      });
    }
  }, 1000);
}
function renderPr() {
  const q = PR.questions[PR.cur];
  const bmB = document.getElementById('p-bm');
  if (bmB) bmB.textContent = '🔖 Save Question';
  startPrTimer();
  document.getElementById('p-pos').textContent = 'Q ' + (PR.cur + 1) + '/' + PR.questions.length;
  document.getElementById('p-topic').textContent = qMeta(q);
  document.getElementById('p-score').textContent = '✅ ' + PR.score;
  document.getElementById('p-te').textContent = q.te || '';
  document.getElementById('p-en').textContent = q.en || '';
  document.getElementById('p-fb').textContent = '';
  document.getElementById('p-next').style.display = 'none';
  const box = document.getElementById('p-opts'); box.innerHTML = '';
  q.options.forEach((opt, i) => {
    const b = document.createElement('button'); b.className = 'opt'; b.textContent = optText(q, i, opt);
    b.dataset.qref = regQ(q); b.dataset.oi = i;
    b.onclick = () => ansPr(i, b); box.appendChild(b);
  });
}
async function ansPr(i, btn) {
  clearInterval(prTimer);
  document.querySelectorAll('#p-opts .opt').forEach(b => { b.disabled = true; });
  btn.classList.add('picked');
  const d = await api('/api/portal/practice/answer', {token, run_id: PR.run_id, idx: PR.cur, choice: i});
  const fb = document.getElementById('p-fb');
  if (!d.ok) { fb.textContent = d.error || ''; return; }
  PR.score = d.score || PR.score;
  const _exp = (d.explanation ? '<br><span class="muted">💡 ' + esc(d.explanation) + '</span>' : '') + (d.explanation_te ? '<br><span class="muted">💡 ' + esc(d.explanation_te) + '</span>' : '');
  fb.innerHTML = d.correct ? '✅ Correct! ' + _exp
    : '❌ Wrong. Correct: <b>' + esc(d.answer_text) + '</b>' + _exp +
      (d.similar ? '<br><button class="btn-alt" style="width:auto; margin-top:6px;" onclick="trySimilar(\'' + esc(d.similar.topic || '') + '\')">🔗 Similar Question Try Chey (' + esc(d.similar.topic || '') + ')</button>' : '');
  document.getElementById('p-score').textContent = '✅ ' + PR.score;
  const nb = document.getElementById('p-next');
  nb.textContent = d.done ? '🏠 Finish' : 'Next ➡️';
  nb.style.display = 'block';
}
function trySimilar(topic) {
  const sel = document.getElementById('topic-sel');
  if (sel && topic) {
    for (const o of sel.options) { if (o.value.toLowerCase() === String(topic).toLowerCase()) { sel.value = o.value; break; } }
  }
  backHome();
  setTimeout(() => startPractice('topic'), 60);
}
function nextPr() {
  clearInterval(prTimer);
  if (PR.cur + 1 >= PR.questions.length) { backHome(); return; }
  PR.cur++; renderPr();
}
let EX = null, exTimer = null, rankTimer = null;
async function pollRank() {
  if (!EX) return;
  try {
    const d = await api('/api/portal/exam/result?id=' + encodeURIComponent(EX.id) + '&token=' + encodeURIComponent(token));
    if (!d.ok) return;
    if (d.status === 'done') {
      clearInterval(rankTimer);
      document.getElementById('x-prog').textContent = '✅ Exam done!';
      showExamResult(EX.id);
      return;
    }
    if (d.my) document.getElementById('x-prog').textContent =
      '✍️ ' + (d.my.answered || 0) + '/' + d.n_q + (d.my.rank ? ' · 🏆 Live Rank #' + d.my.rank + ' / ' + (d.joined || '') : '');
  } catch (e) {}
}
function examBtn(e) {
  if (e.status === 'scheduled') return (e.my.joined ? '<span class="chip">✅ Joined — wait for start</span>' : '<button class="btn-main" style="margin-top:8px;" onclick="joinExam(\'' + e.id + '\')">🔔 Join Exam</button>') + ' <button class="btn-alt" style="width:auto; margin:8px 0 0;" data-on="' + (e.remind ? '1' : '0') + '" onclick="remindExam(\'' + e.id + '\', this)">' + (e.remind ? '🔔 Reminder ON' : '🔕 Notify Me') + '</button>';
  if (e.status === 'live') return e.my.joined ? '<button class="btn-main" style="margin-top:8px;" onclick="enterExam(\'' + e.id + '\')">▶️ Enter Live Exam</button>' : '<button class="btn-main" style="margin-top:8px;" onclick="joinExam(\'' + e.id + '\', true)">🚪 Join &amp; Enter</button>';
  return '<button class="btn-alt" onclick="showExamResult(\'' + e.id + '\')">📊 Result &amp; Winners</button>';
}
function cdTick() {
  document.querySelectorAll('.cd').forEach(el => {
    const t = new Date(el.dataset.ts) - new Date();
    if (isNaN(t)) return;
    if (t < 0) { el.textContent = '🔴 LIVE NOW!'; return; }
    const h = Math.floor(t / 36e5), m = Math.floor(t % 36e5 / 6e4);
    el.textContent = '⏰ ' + (h >= 24 ? Math.floor(h / 24) + 'd ' + (h % 24) + 'h' : h + 'h ' + m + 'm') + ' lo start avthundi';
  });
}
function renderLiveExams(list) {
  const box = document.getElementById('live-exams');
  if (!list.length) { box.innerHTML = '<div class="muted">Upcoming exams ikkade kanipisthayi.</div>'; return; }
  box.innerHTML = list.map(e => {
    const when = (e.starts_at || '').replace('T', ' ').slice(0, 16);
    const st = e.status === 'live' ? '<span style="color:#f87171; font-weight:800;">🔴 LIVE NOW</span>'
      : e.status === 'done' ? '<span class="muted">✅ Completed</span>'
      : '<span class="cd" data-ts="' + e.starts_at + '" style="color:#facc15; font-weight:700;">⏰ ' + when + ' ki start</span>';
    return '<div style="padding:11px; background:#0f1e38; border:1px solid #24466e; border-radius:12px; margin-top:9px;">' +
      '<b>' + esc(e.title) + '</b> ' + (e.kind === 'weekly' ? '<span class="chip gold">WEEKLY</span>' : '') + '<br>' +
      '<span class="muted">' + esc(e.goal_label) + ' · ' + e.n_q + ' Qs (' + e.pyq_count + ' real PYQs) · ' + e.duration_min + ' min · 👥 ' + e.joined + ' joined</span><br>' + st +
      (e.my && e.my.joined ? '<br><span class="muted">Mee progress: ' + e.my.answered + '/' + e.n_q + ' answered' + (e.my.rank ? ' · Rank #' + e.my.rank : '') + '</span>' : '') +
      (e.board ? rows(e.board.slice(0, 5), '') : '') +
      examBtn(e) + '</div>';
  }).join('');
}
async function joinExam(id, enter) {
  const d = await api('/api/portal/exam/join', {token, exam_id: id});
  if (!d.ok) { alert('❌ ' + (d.error || 'Join avvaledu')); return; }
  if (enter) { enterExam(id); } else { loadHome(); }
}
async function enterExam(id) {
  const d = await api('/api/portal/exam?id=' + encodeURIComponent(id) + '&token=' + encodeURIComponent(token));
  if (!d.ok) { alert('❌ Session expired'); logout(); return; }
  if (d.status !== 'live') { alert(d.status === 'scheduled' ? '⏰ Exam inka start avvaledu!' : 'Exam ayipoyindi / join avvaledu.'); loadHome(); return; }
  EX = {id, answers: {}};
  clearInterval(rankTimer);
  rankTimer = setInterval(pollRank, 20000);
  document.getElementById('x-title').textContent = '🔴 ' + d.title;
  const box = document.getElementById('x-qs'); box.innerHTML = '';
  (d.questions || []).forEach(q => {
    const div = document.createElement('div');
    div.innerHTML = '<div class="muted" style="font-size:11px; margin-top:12px;">' + esc(qMeta(q)) + '</div><div class="qte" style="margin-top:4px;">Q' + (q.i + 1) + '. ' + esc(q.te || q.en) + '</div>' + (q.te && q.en ? '<div class="qen">' + esc(q.en) + '</div>' : '');
    q.options.forEach((opt, oi) => {
      const b = document.createElement('button'); b.className = 'opt'; b.textContent = optText(q, oi, opt);
      b.dataset.qref = regQ(q); b.dataset.oi = oi;
      if (q.answered) { b.disabled = true; }
      else b.onclick = async () => {
        div.querySelectorAll('.opt').forEach(x => { x.disabled = true; });
        b.classList.add('picked');
        const r = await api('/api/portal/exam/answer', {token, exam_id: EX.id, idx: q.i, choice: oi});
        if (r.ok) document.getElementById('x-prog').textContent = '✍️ ' + r.answered + '/' + r.total_q;
      };
      div.appendChild(b);
    });
    box.appendChild(div);
  });
  show('view-exam');
  const prog = document.getElementById('x-prog');
  const ans = (d.questions || []).filter(q => q.answered).length;
  prog.textContent = '✍️ ' + ans + '/' + (d.questions || []).length;
  let left = Math.max(0, Math.round((new Date(d.ends_at) - Date.now()) / 1000));
  const tEl = document.getElementById('x-timer');
  clearInterval(exTimer);
  exTimer = setInterval(() => {
    left--;
    tEl.textContent = '⏱ ' + Math.floor(left / 60) + ':' + String(Math.max(0, left) % 60).padStart(2, '0');
    if (left <= 0) { clearInterval(exTimer); alert('⏰ Time ayipoyindi! Result ikkade chudandi.'); backHome(); }
  }, 1000);
}
async function showExamResult(id) {
  const d = await api('/api/portal/exam/result?id=' + encodeURIComponent(id) + '&token=' + encodeURIComponent(token));
  if (!d.ok) { alert('❌ Result dorakaledu'); return; }
  if (d.status !== 'done') { alert('⏳ Result exam complete ayyaka vastundi.'); return; }
  document.getElementById('res-score').textContent = (d.my ? d.my.correct : 0) + '/' + d.n_q;

  document.getElementById('res-sub').innerHTML = esc(d.title) + (d.my && d.my.rank ? ' · 🏆 Mee Rank #' + d.my.rank : '') + (d.my && d.my.top_pct ? ' · 🏅 Top ' + d.my.top_pct + '%' : '') +
    '<br>🏆 Winners: ' + (d.winners || []).map(w => esc(w.name) + ' (' + w.correct + '/' + w.total + ')').join(' · ');
  document.getElementById('res-review').innerHTML = (d.review || []).map(r => {
    const q = (d.questions || [])[r.i] || {}; const opts = q.options || [];
    return '<div class="rrow ' + (r.right ? 'ok' : 'bad') + '"><b>Q' + (r.i + 1) + '.</b> ' + esc(q.en || q.te || '') +
      '<br><span class="muted">Meeru: ' + esc(opts[r.given] || '— attempt cheyyaledu') + (r.right ? ' ✅' : ' ❌ · Correct: ' + esc(opts[r.answer] || '')) + '</span>' +
      (q.explanation ? '<br><span class="muted">💡 ' + esc(q.explanation) + '</span>' : '') + '</div>';
  }).join('') || '<div class="muted">Mee review ledu (answers ivvaledu).</div>';
  if ((d.qstats || []).length) {
    document.querySelectorAll('#res-review .rrow').forEach((el, i) => {
      const pc = (d.qstats || [])[i];
      if (pc != null) el.insertAdjacentHTML('beforeend', '<br><span class="muted">👥 ' + pc + '% students ee question correct pettaru' + (pc < 40 ? ' — 🔥 tough question!' : (pc > 85 ? ' — easy one' : '')) + '</span>');
    });
  }
  document.getElementById('res-sub').insertAdjacentHTML('beforeend',
    '<br><button class="btn-alt" style="width:auto; margin-top:10px;" onclick="downloadKey(\'exam\',\'' + id + '\')">⬇️ Answer Key Paper Download 📄</button>' +
    ' <a class="btn-alt" style="display:inline-block; width:auto; margin-top:10px; padding:8px 14px; text-decoration:none;" href="/api/portal/exam/scorecard?id=' + encodeURIComponent(id) + '&token=' + encodeURIComponent(token) + '">📸 Score Card</a>');
  if (d.my_winner) {
    document.getElementById('res-sub').insertAdjacentHTML('beforeend',
      '<br><a href="/api/portal/exam/certificate?id=' + encodeURIComponent(id) + '&token=' + encodeURIComponent(token) + '" style="display:inline-block; margin-top:10px; padding:11px 18px; background:linear-gradient(90deg,#a16207,#facc15); color:#1a1000; font-weight:800; border-radius:10px;">🏆 Naa Winners Certificate Download</a>');
    for (let i = 0; i < 40; i++) {
      const c = document.createElement('div');
      c.textContent = ['🎉', '⭐', '🏆', '✨'][i % 4];
      c.style.cssText = 'position:fixed; top:-30px; left:' + (Math.random() * 100) + '%; font-size:' + (14 + Math.random() * 16) + 'px; z-index:99; pointer-events:none; transition: transform ' + (1.6 + Math.random()) + 's ease-in, opacity 2.4s;';
      document.body.appendChild(c);
      requestAnimationFrame(() => { c.style.transform = 'translateY(105vh) rotate(' + (Math.random() * 360) + 'deg)'; c.style.opacity = '0'; });
      setTimeout(() => c.remove(), 2800);
    }
  }
  show('view-result');
}
if ('serviceWorker' in navigator) { try { navigator.serviceWorker.register('/sw.js'); } catch (e) {} }
init();
</script>
</body>
</html>
"""


WEB_EXAM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StudentUp — College Exam</title>
<style>
  * { box-sizing: border-box; margin: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
  body { min-height: 100vh; background: radial-gradient(circle at 30% 10%, #12315e 0%, #050811 70%); color: #e2e8f0; padding: 18px 14px 40px; }
  .wrap { max-width: 520px; margin: 0 auto; }
  .brand { text-align: center; font-size: 22px; font-weight: 800; color: #f8fafc; margin: 8px 0 16px; }
  .brand span { display: block; font-size: 12px; color: #38bdf8; font-weight: 600; letter-spacing: 1.5px; margin-top: 3px; }
  .card { background: #0b1329; border: 1px solid #1e3a5f; border-radius: 16px; padding: 22px 18px; box-shadow: 0 16px 40px rgba(0,0,0,.5); }
  h2 { font-size: 19px; margin-bottom: 8px; }
  h3 { font-size: 14px; margin: 16px 0 8px; color: #38bdf8; }
  .muted { color: #94a3b8; font-size: 13px; line-height: 1.6; }
  .small { font-size: 11.5px; margin-top: 12px; }
  label { display: block; font-size: 12.5px; font-weight: 700; margin: 14px 0 5px; color: #cbd5e1; }
  input, select { width: 100%; padding: 12px 14px; font-size: 16px; background: #050811; color: #f8fafc; border: 1px solid #1e3a5f; border-radius: 10px; outline: none; }
  input:focus, select:focus { border-color: #38bdf8; }
  .btn-main { width: 100%; margin-top: 18px; padding: 14px; font-size: 16px; font-weight: 800; border: none; border-radius: 11px; background: linear-gradient(90deg, #10b981, #38bdf8); color: #04121f; cursor: pointer; }
  .err { color: #f87171; font-size: 13px; font-weight: 700; min-height: 18px; margin-top: 10px; }
  .big { font-size: 44px; text-align: center; margin-bottom: 6px; }
  .pulse { text-align: center; color: #10b981; font-weight: 700; margin-top: 14px; animation: pl 1.6s infinite; }
  @keyframes pl { 0%,100% { opacity: 1; } 50% { opacity: .35; } }
  .row { display: flex; gap: 8px; align-items: center; }
  .between { justify-content: space-between; }
  .chip { background: #12233f; border: 1px solid #1e3a5f; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; }
  .timer { color: #facc15; }
  .tbar { height: 8px; background: #12233f; border-radius: 99px; overflow: hidden; margin: 12px 0 16px; }
  #tbar-fill { height: 100%; background: linear-gradient(90deg, #10b981, #facc15, #ef4444); width: 100%; transition: width .3s linear; }
  .qte { font-size: 17px; font-weight: 700; line-height: 1.55; }
  .qen { font-size: 14.5px; color: #a5c4e8; line-height: 1.55; margin-top: 6px; }
  .opt { display: block; width: 100%; text-align: left; margin-top: 10px; padding: 14px 15px; font-size: 15px; font-weight: 600; background: #0f1e38; color: #e2e8f0; border: 1.5px solid #24466e; border-radius: 12px; cursor: pointer; }
  .opt:active { transform: scale(.99); }
  .opt.picked { border-color: #38bdf8; background: #12315e; }
  .opt:disabled { opacity: .75; cursor: default; }
  .feedback { min-height: 22px; margin-top: 12px; font-size: 14px; font-weight: 700; }
  .score-big { font-size: 44px; font-weight: 800; text-align: center; color: #10b981; }
  .trow { display: flex; gap: 8px; align-items: center; padding: 8px 10px; background: #0f1e38; border-radius: 10px; margin-top: 6px; font-size: 13.5px; }
  .trow b { flex: 1; }
  .rrow { padding: 9px 11px; border-radius: 10px; margin-top: 6px; font-size: 13px; line-height: 1.55; background: #0f1e38; }
  .rrow.ok { border-left: 4px solid #10b981; }
  .rrow.bad { border-left: 4px solid #ef4444; }
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">🎓 StudentUp<span>COLLEGE EXAM · WEB</span></div>

  <div id="view-join" class="card">
    <h2 id="exam-name">College Exam</h2>
    <p class="muted" id="join-sub">Peru + mobile isthe chalu — app download akkarledu!</p>
    <label>Mee Peru (Full Name)</label>
    <input id="f-name" placeholder="e.g. Priya Sharma" autocomplete="name">
    <label>Mobile Number</label>
    <input id="f-phone" inputmode="numeric" maxlength="13" placeholder="10-digit mobile number" autocomplete="tel">
    <label id="college-label" style="display:none;">Mee College</label>
    <select id="f-college" style="display:none;"></select>
    <button class="btn-main" onclick="doJoin()">🚀 Join Exam</button>
    <div id="join-err" class="err"></div>
    <p class="muted small">📱 Ee link browser lo ne pani chesthundi. Telegram app unna vallu organiser ichina Telegram link kuda vadachu — rendu okkate exam, okkate marks!</p>
  </div>

  <div id="view-wait" class="card" style="display:none;">
    <div class="big">⏳</div>
    <h2 style="text-align:center;">Join ayyaru! ✅</h2>
    <p class="muted" id="wait-info" style="text-align:center;"></p>
    <p class="muted" style="text-align:center;">Exam start ayyaka questions ikkade vastayi — ee page close cheyyakandi.</p>
    <div class="pulse">● Waiting for exam to start…</div>
  </div>

  <div id="view-quiz" class="card" style="display:none;">
    <div class="row between"><span id="q-pos" class="chip"></span><span id="q-timer" class="chip timer"></span><span id="q-score" class="chip"></span></div>
    <div class="tbar"><div id="tbar-fill"></div></div>
    <div id="q-te" class="qte"></div>
    <div id="q-en" class="qen"></div>
    <div id="opts"></div>
    <div id="q-feedback" class="feedback"></div>
  </div>

  <div id="view-done" class="card" style="display:none;">
    <div class="big">🏆</div>
    <h2 id="done-title" style="text-align:center;">Result</h2>
    <div class="score-big" id="done-score"></div>
    <p class="muted" id="done-summary" style="text-align:center;"></p>
    <h3>🏅 Top 5</h3>
    <div id="done-top"></div>
    <h3>📝 Mee Answers Review</h3>
    <div id="done-review"></div>
  </div>
</div>

<script>
const CODE = location.pathname.split('/').filter(Boolean).pop().toUpperCase();
let token = localStorage.getItem('su_exam_' + CODE) || '';
let pollInt = null, timerInt = null, curPos = 0, qWindow = 40, endsAt = 0;
const esc = (t) => String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');  // 🧼 290X quote-safe

async function api(path, body) {
  const opt = body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {};
  const r = await fetch(path, opt);
  return await r.json();
}
function show(id) {
  ['view-join', 'view-wait', 'view-quiz', 'view-done'].forEach(v => {
    document.getElementById(v).style.display = (v === id ? 'block' : 'none');
  });
}
async function doJoin() {
  const name = document.getElementById('f-name').value.trim();
  const phone = document.getElementById('f-phone').value.trim();
  const sel = document.getElementById('f-college');
  const err = document.getElementById('join-err');
  err.textContent = '';
  const d = await api('/api/exam/join', {code: CODE, name, phone, college_idx: sel.style.display === 'none' ? 1 : (sel.selectedIndex + 1)});
  if (!d.ok) { err.textContent = '❌ ' + (d.error || 'Join avvaledu'); return; }
  token = d.token;
  localStorage.setItem('su_exam_' + CODE, token);
  startPolling();
}
async function refresh() {
  if (!token) return;
  let d;
  try { d = await api('/api/exam/state?code=' + encodeURIComponent(CODE) + '&token=' + encodeURIComponent(token)); }
  catch (e) { return; }
  if (!d.ok) { localStorage.removeItem('su_exam_' + CODE); token = ''; show('view-join'); return; }
  const s = d;
  if (s.state === 'open') {
    show('view-wait');
    document.getElementById('wait-info').textContent = s.joined + ' students join ayyaru · ' + s.n_q + ' questions' + (s.start_at ? ' · ⏰ ' + s.start_at.replace('T', ' ') + ' ki start avthundi' : '');
  } else if (s.state === 'question') {
    renderQ(s);
  } else if (s.state === 'gap') {
    show('view-wait');
    document.getElementById('wait-info').textContent = 'Next question vastundi… ⏳';
  } else if (s.state === 'done') {
    renderDone(s);
  }
}
function renderQ(s) {
  show('view-quiz');
  document.getElementById('q-pos').textContent = 'Q ' + s.position + '/' + s.n_q;
  document.getElementById('q-score').textContent = '⭐ ' + s.my.pts + ' pts · ✅ ' + s.my.correct;
  if (s.position !== curPos) {
    curPos = s.position;
    const q = s.question;
    document.getElementById('q-te').textContent = q.te || '';
    document.getElementById('q-en').textContent = q.en || '';
    document.getElementById('q-feedback').textContent = '';
    const box = document.getElementById('opts');
    box.innerHTML = '';
    q.options.forEach((opt, i) => {
      const b = document.createElement('button');
      b.className = 'opt';
      b.dataset.qref = regQ(q); b.dataset.oi = i;
      b.textContent = optText(q, i, opt);
      if (q.answered) { b.disabled = true; }
      else { b.onclick = () => answer(i, b); }
      box.appendChild(b);
    });
    qWindow = Math.max(5, s.ends_in || 40);
    endsAt = Date.now() + qWindow * 1000;
    clearInterval(timerInt);
    timerInt = setInterval(tickTimer, 250);
    tickTimer();
  }
}
function tickTimer() {
  const left = Math.max(0, Math.round((endsAt - Date.now()) / 1000));
  document.getElementById('q-timer').textContent = '⏱ ' + left + 's';
  document.getElementById('tbar-fill').style.width = Math.max(0, Math.min(100, left / qWindow * 100)) + '%';
  if (left <= 0) { clearInterval(timerInt); refresh(); }
}
async function answer(i, btn) {
  document.querySelectorAll('.opt').forEach(b => { b.disabled = true; });
  btn.classList.add('picked');
  const d = await api('/api/exam/answer', {code: CODE, token, position: curPos, choice: i});
  const fb = document.getElementById('q-feedback');
  if (d.ok) { fb.innerHTML = d.correct ? '✅ Correct! Points add ayyayi ⭐' : '❌ Wrong — parvaledu, next question undi!'; }
  else { fb.textContent = d.error || ''; }
  setTimeout(refresh, 900);
}
function renderDone(s) {
  show('view-done');
  clearInterval(pollInt);
  clearInterval(timerInt);
  document.getElementById('done-title').textContent = s.rank ? ('🎉 Meeru Rank #' + s.rank + ' / ' + s.total_players) : 'Exam Complete!';
  document.getElementById('done-score').textContent = s.my.correct + '/' + s.n_q;
  document.getElementById('done-summary').textContent = '⭐ ' + s.my.pts + ' points · ' + (s.my.college || '');
  document.getElementById('done-top').innerHTML = (s.top || []).map((t, i) =>
    '<div class="trow"><span>' + (['🥇', '🥈', '🥉'][i] || (i + 1)) + '</span><b>' + esc(t.name) + '</b><span class="muted">' + esc(t.college) + '</span><span>✅ ' + t.correct + ' · ⭐ ' + t.pts + '</span></div>').join('');
  document.getElementById('done-review').innerHTML = (s.review || []).map(r =>
    '<div class="rrow ' + (r.right ? 'ok' : 'bad') + '"><div><b>Q' + r.n + '.</b> ' + esc(r.q) + '</div><div class="muted">Meeru: ' + esc(r.your) + (r.right ? ' ✅' : ' ❌ · Correct: ' + esc(r.answer)) + '</div></div>').join('') || '<div class="muted">Review data ledu</div>';
}
function startPolling() {
  refresh();
  clearInterval(pollInt);
  pollInt = setInterval(refresh, 2000);
}
(async () => {
  try {
    const d = await api('/api/exam/info?code=' + encodeURIComponent(CODE));
    if (d.ok) {
      document.getElementById('exam-name').textContent = d.exam;
      document.getElementById('join-sub').textContent = d.n_q + ' questions · peru + mobile isthe chalu, app download akkarledu!';
      if (d.colleges && d.colleges.length > 1) {
        const sel = document.getElementById('f-college');
        const lab = document.getElementById('college-label');
        sel.innerHTML = d.colleges.map(c => '<option>' + esc(c) + '</option>').join('');
        sel.style.display = 'block';
        lab.style.display = 'block';
      }
      if (d.state === 'done') { document.getElementById('join-err').textContent = 'Ee exam ayipoyindi.'; }
    } else {
      document.getElementById('join-err').textContent = '❌ Exam link invalid — organiser ni adagandi.';
    }
  } catch (e) {}
  if (token) { startPolling(); }
})();
</script>
</body>
</html>
"""


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <!-- 📱 PWA: phone home-screen లో app లా install అవుతుంది -->
  <link rel="manifest" href="/manifest.json">
  <meta name="theme-color" content="#0b1220">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="icon" href="/icon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/icon.svg">
  <title>StudentUp — Ultimate Control, Excel Importer & Bundle Hub</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card: #131b2e;
      --border: #22304d;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #10b981;
      --accent-hover: #059669;
      --danger: #ef4444;
      --warning: #f59e0b;
      --purple: #8b5cf6;
      --pink: #ec4899;
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
    body { background: radial-gradient(circle at 10% 0%, #111d36 0%, var(--bg) 34%); color: var(--text); padding: 24px; min-height: 100vh; max-width: 1600px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 18px; margin-bottom: 22px; }
    .header h1 { font-size: 24px; font-weight: 800; display: flex; align-items: center; gap: 10px; }
    .badge-live { background: rgba(16, 185, 129, 0.15); color: var(--accent); border: 1px solid var(--accent); padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .badge-shield { background: rgba(139, 92, 246, 0.15); color: var(--purple); border: 1px solid var(--purple); padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }
    .grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 22px; }
    .stat-card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
    .stat-card .label { font-size: 12px; color: var(--text-muted); font-weight: 500; }
    .stat-card .val { font-size: 28px; font-weight: 800; margin-top: 5px; }
    .stat-card .desc { font-size: 11px; color: var(--text-muted); margin-top: 3px; }
    /* ===== 🧭 Neat grouped sidebar navigation (no more 16-tab clutter row) ===== */
    .tabs { position: fixed; left: 0; top: 0; bottom: 0; width: 236px; z-index: 40; display: flex; flex-direction: column; gap: 2px; padding: 16px 12px; overflow-y: auto; background: #0a0f1e; border-right: 1px solid var(--border); scrollbar-width: thin; }
    .tabs::-webkit-scrollbar { width: 6px; }
    .tabs::-webkit-scrollbar-thumb { background: #22304d; border-radius: 3px; }
    .nav-brand { font-size: 17px; font-weight: 800; color: #f8fafc; padding: 2px 8px; letter-spacing: .2px; }
    .nav-brand small { display: block; font-size: 10.5px; color: var(--text-muted); font-weight: 500; margin-top: 2px; }
    .nav-search { width: 100%; box-sizing: border-box; margin: 10px 0 6px; padding: 8px 10px; font-size: 12.5px; background: #050811; color: var(--text); border: 1px solid var(--border); border-radius: 9px; outline: none; }
    .nav-search:focus { border-color: var(--primary); }
    .nav-group { font-size: 10px; font-weight: 800; letter-spacing: 1.4px; color: #5b6b8c; margin: 14px 8px 5px; text-transform: uppercase; }
    .tab-btn { width: 100%; text-align: left; background: transparent; border: none; color: var(--text-muted); font-size: 13.5px; font-weight: 600; padding: 9px 12px; border-radius: 10px; cursor: pointer; transition: all .15s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .tab-btn:hover { background: rgba(59,130,246,.10); color: var(--text); }
    .tab-btn.active { background: linear-gradient(90deg, var(--primary), #0ea5e9); color: #fff; box-shadow: 0 4px 14px rgba(37,99,235,.35); }
    body { padding-left: 260px; }
    details.adv { border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px; margin-top: 12px; background: #0a1122; }
    details.adv summary { cursor: pointer; font-size: 12.5px; font-weight: 700; color: var(--text-muted); }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; animation: paneIn .25s ease; }
    @keyframes paneIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
    .panel-card { background: linear-gradient(145deg, rgba(19,27,46,.98), rgba(15,23,42,.98)); border: 1px solid var(--border); border-radius: 14px; padding: 22px; margin-bottom: 20px; box-shadow: 0 8px 28px rgba(0,0,0,0.22); }
    .panel-card h2 { font-size: 18px; margin-bottom: 14px; display: flex; align-items: center; gap: 8px; }
    .btn { background: var(--primary); color: #fff; border: none; padding: 9px 15px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.15); }
    .btn:hover { background: var(--primary-hover); transform: translateY(-1px); }
    .btn:active { transform: translateY(0); }
    .btn-accent { background: var(--accent); }
    .btn-accent:hover { background: var(--accent-hover); }
    .btn-purple { background: var(--purple); }
    .btn-pink { background: var(--pink); }
    .btn-danger { background: var(--danger); }
    .btn-outline { background: rgba(255,255,255,0.03); border: 1px solid var(--border); color: var(--text); }
    .btn-outline:hover { background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.2); }
    input, select, textarea { width: 100%; padding: 10px 13px; background: #0f172a; border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 13px; margin-top: 6px; margin-bottom: 14px; transition: border-color 0.2s; }
    input:focus, select:focus, textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(59,130,246,0.25); }
    table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 12px; font-size: 13px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border); }
    th, td { text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--border); }
    th { color: var(--text-muted); font-weight: 600; background: #0c1322; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
    tbody tr:hover { background: rgba(255,255,255,0.02); }
    tbody tr:last-child td { border-bottom: none; }
    .log-box { background: #050811; border: 1px solid var(--border); border-radius: 8px; padding: 14px; font-family: monospace; font-size: 12px; max-height: 240px; overflow-y: auto; color: #38bdf8; white-space: pre-wrap; margin-top: 12px; line-height: 1.6; }
    .status-pill { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .status-pill.open { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .status-pill.closed { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .category-tag { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); padding: 3px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .shift-tag { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); padding: 3px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .progress-bar-container { width: 100%; background: #1e293b; border-radius: 9999px; height: 10px; overflow: hidden; margin-top: 10px; margin-bottom: 10px; }
    .progress-bar { height: 100%; background: linear-gradient(90deg, var(--primary), var(--accent)); width: 0%; transition: width 0.3s; }
    .planner-hero{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:24px 26px;margin-bottom:16px;border:1px solid #294b78;border-radius:18px;background:linear-gradient(120deg,#13294b,#101827 65%,#18263d);box-shadow:0 12px 30px #0004}.planner-hero h2{font-size:25px;margin:5px 0 7px}.planner-hero p{color:#a9b9d0;font-size:13px}.eyebrow{font-size:10px;letter-spacing:1.5px;font-weight:800;color:#5eead4}.hero-actions{display:flex;gap:8px;flex-wrap:wrap}.planner-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px}.planner-card{background:linear-gradient(145deg,#151f34,#111827);border:1px solid #263b5d;border-radius:14px;padding:17px}.planner-card-head{display:flex;gap:10px;align-items:flex-start;margin-bottom:14px}.planner-card-head b{display:block;font-size:14px}.planner-card-head small{display:block;color:#8495ae;font-size:11px;margin-top:4px}.step{display:grid;place-items:center;background:#2563eb;color:white;border-radius:8px;width:29px;height:29px;font-size:11px;font-weight:800}.exam-pills{display:flex;gap:6px;flex-wrap:wrap}.exam-pill{background:#0d1728;border:1px solid #304766;color:#b9c8dc;border-radius:999px;padding:7px 10px;font-size:11px;cursor:pointer}.exam-pill:hover,.exam-pill.active{background:#2563eb;border-color:#60a5fa;color:#fff}.selection-summary{display:flex;justify-content:space-between;gap:8px;align-items:center;background:#0b1322;border-radius:9px;padding:10px;margin-bottom:12px}.selection-summary strong{color:#67e8f9;font-size:13px}.selection-summary span{font-size:10px;color:#8291a7}.mini-stat-row{display:flex;gap:8px;flex-wrap:wrap;color:#9fb2ca;font-size:11px;margin:17px 0}.mini-stat-row span{background:#0b1322;border-radius:6px;padding:6px 8px}
    /* ---------- 📱 MOBILE / TABLET RESPONSIVE (operate from phone) ---------- */
    @media (max-width: 920px) {
      body { padding: 12px; }
      .header { flex-direction: column; align-items: stretch; gap: 10px; padding-bottom: 12px; margin-bottom: 14px; }
      .header h1 { font-size: 18px; }
      .grid-stats { grid-template-columns: repeat(2, 1fr); gap: 8px; margin-bottom: 14px; }
      .stat-card { padding: 10px 12px; }
      .stat-card .val { font-size: 20px; }
      .stat-card .desc { display: none; }
      body { padding-left: 12px; }
      .tabs { position: static; width: auto; flex-direction: row; flex-wrap: wrap; align-items: center; border-right: none; border-bottom: 1px solid var(--border); padding: 10px 4px; margin-bottom: 12px; }
      .nav-group { display: none; }
      .nav-search { display: none; }
      .tab-btn { width: auto; font-size: 12px; padding: 8px 10px; }
      .panel-card { padding: 12px !important; }
      table { display: block; overflow-x: auto; white-space: nowrap; font-size: 11px; }
      #wa-login-number-badge { font-size: 16px !important; padding: 5px 12px !important; }
      .btn { min-height: 38px; }
      input, select, textarea { font-size: 16px !important; } /* stops mobile auto-zoom */
      .hist-grid { grid-template-columns: 1fr !important; }
    }
    @media (max-width: 520px) {
      .grid-stats { grid-template-columns: repeat(2, 1fr); }
      .header h1 { font-size: 16px; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>🚀 StudentUp Control Hub</h1>
      <p style="color:var(--text-muted); font-size:12px; margin-top:4px;">WhatsApp + Telegram Bulk Delivery · Anti-Ban Engine</p>
    </div>
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
      <span id="live-status-strip" style="display:flex; gap:6px; flex-wrap:wrap; align-items:center;">
        <span class="badge-shield">🛡️ ANTI-BAN INTERLEAVED</span>
        <span class="badge-live">● ENGINE LIVE</span>
      </span>
      <button class="btn btn-outline" onclick="location.reload()">🔄 Refresh</button>
      <button class="btn btn-outline" style="border-color:#f59e0b; color:#f59e0b;" onclick="changeDashPassword()" title="Change admin password">🔑 Password</button>
      <button class="btn btn-outline" style="border-color:#34d399; color:#34d399;" onclick="toggleIpLockPanel()" title="Allow only specific IP addresses">🛡️ IP Lock</button>
      <button class="btn btn-outline" style="border-color:#ef4444; color:#ef4444;" onclick="dashLogout()" title="Lock the dashboard">🔒 Lock / Logout</button>
    </div>
  </div>

  <!-- 🛡️ IP ALLOWLIST PANEL (2nd security layer on top of password) -->
  <div id="ip-lock-panel" style="display:none; background:#0f172a; border:1px solid #34d399; border-radius:12px; padding:18px; margin-bottom:18px;">
    <h3 style="font-size:15px; margin-bottom:6px;">🛡️ IP Allowlist — కొన్ని IP ల నుంచే dashboard open అవ్వాలి</h3>
    <p style="color:var(--text-muted); font-size:12px; margin-bottom:10px;">
      Password తో పాటు రెండో security layer. Lock ON అయితే, list లో ఉన్న IP ల నుంచి మాత్రమే login page కూడా కనిపిస్తుంది — మిగతా వాళ్ళకి 403 Access Denied.
    </p>
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:10px;">
      <span id="ip-lock-status" style="font-weight:800; font-size:13px;">...</span>
      <span style="font-size:12px; color:#94a3b8;">Your current IP: <b id="ip-lock-myip" style="color:#fbbf24;">...</b></span>
      <button class="btn btn-outline" style="font-size:11px; padding:4px 10px;" onclick="addMyIpToList()">➕ Add My Current IP</button>
    </div>
    <label>Allowed IPs (one per line — formats: <code>49.37.12.34</code> exact · <code>49.37.</code> prefix/range · <code>49.37.0.0/16</code> CIDR):</label>
    <textarea id="ip-allow-list" rows="4" style="width:100%; font-family:monospace; font-size:13px;" placeholder="49.37.12.34"></textarea>
    <div style="display:flex; gap:10px; margin-top:10px; flex-wrap:wrap;">
      <button class="btn btn-accent" onclick="saveIpLock(true)">🛡️ Save & Turn ON</button>
      <button class="btn btn-outline" style="border-color:#ef4444; color:#ef4444;" onclick="saveIpLock(false)">🔓 Turn OFF (password only)</button>
    </div>
    <div id="ip-lock-result" style="font-size:12px; margin-top:8px;"></div>
    <div id="login-audit" style="font-size:11px; margin-top:10px;"></div>
    <p style="color:#64748b; font-size:11px; margin-top:8px;">
      💡 Mobile data IP మారుతూ ఉంటుంది — exact IP బదులు prefix (ఉదా: <code>49.37.</code>) వాడితే safe. 🚨 Lockout అయితే: server ని <code>DISABLE_IP_LOCK=1</code> env తో restart చేయండి (sandbox/local నుంచి ఎప్పుడూ access ఉంటుంది).
    </p>
  </div>

  <div class="grid-stats">
    <div class="stat-card">
      <div class="label">Total Syllabus Polls Available</div>
      <div class="val" id="stat-polls-count" style="color:#38bdf8;">...</div>
      <div class="desc">Active question inventory</div>
    </div>
    <div class="stat-card">
      <div class="label">WhatsApp Groups Active</div>
      <div class="val" id="stat-wa-count" style="color:#60a5fa;">...</div>
      <div class="desc">100+ groups safe queue</div>
    </div>
    <div class="stat-card">
      <div class="label">Telegram Channels</div>
      <div class="val" id="stat-tg-count" style="color:var(--purple);">...</div>
      <div class="desc">TS & AP live channels</div>
    </div>
    <div class="stat-card">
      <div class="label">Custom Bundles</div>
      <div class="val" id="stat-bundle-count" style="color:var(--pink);">...</div>
      <div class="desc">Cluster groups & channels</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Points Earned</div>
      <div class="val" id="stat-points" style="color:var(--warning);">...</div>
      <div class="desc">Active student balance</div>
    </div>
  </div>

  <!-- 🎯 VISION MISSION CONTROL -->
  <div style="background:linear-gradient(135deg,#0d1b36,#131024); border:1px solid #a78bfa; border-radius:12px; padding:16px; margin-bottom:18px;">
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
      <div>
        <h3 style="font-size:15px; color:#c4b5fd; margin:0;">🎯 Vision Mission Control</h3>
        <div id="vision-tagline" style="font-size:11px; color:var(--text-muted); margin-top:2px;">Prathi TS/AP aspirant ki — prathi roju thana exam PYQ + fresh bilingual polls, rendu platforms lo, rank tho.</div>
      </div>
      <div style="text-align:center;">
        <div id="vision-score" style="font-size:30px; font-weight:900; color:#a78bfa; line-height:1;">…</div>
        <div style="font-size:10px; color:var(--text-muted);">VISION SCORE <span id="vision-grade"></span></div>
      </div>
    </div>
    <div id="vision-pillars" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; margin-top:12px; font-size:12px;"></div>
    <div id="vision-actions" style="margin-top:10px; font-size:12px;"></div>
    <div id="vision-next" style="margin-top:6px; font-size:11px; color:#64748b;"></div>
  </div>

  <!-- Global WhatsApp Device Connectivity Header -->
  <div style="background: linear-gradient(135deg, rgba(16,185,129,0.12) 0%, rgba(59,130,246,0.15) 100%); border:1px solid #10b981; border-radius:12px; padding:14px 18px; margin-bottom:18px;">
    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
      <div>
        <h3 style="font-size:14px; display:flex; align-items:center; gap:8px;">
          📱 WhatsApp Gateway Node & Anti-Ban Protection
          <span id="wa-session-status-badge" style="background:#10b981; color:#050811; font-size:11px; font-weight:800; padding:2px 8px; border-radius:12px;">● CONNECTED</span>
          <span style="background:rgba(59,130,246,0.2); color:#60a5fa; border:1px solid #3b82f6; border-radius:12px; padding:2px 8px; font-size:11px; font-weight:700;">🛡️ 100x Anti-Ban Active</span>
        </h3>
        <div id="wa-logged-in-card" style="display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-top:8px; background:#050811; border:1px solid #1e293b; border-radius:10px; padding:10px 14px;">
          <div id="wa-login-number-badge" style="font-family:'Consolas', monospace; font-size:20px; font-weight:800; letter-spacing:1px; color:#64748b; background:#0b1329; border:2px dashed #334155; border-radius:10px; padding:6px 16px;">
            📵 NOT LINKED
          </div>
          <div style="font-size:12px; color:var(--text-muted); line-height:1.7;">
            <div id="wa-session-desc"></div>
            <div>👤 Device: <b style="color:#f8fafc;" id="wa-device-name">—</b> <span id="wa-connected-since" style="color:#64748b;"></span></div>
            <div>💬 Synced Groups: <b style="color:#38bdf8;" id="wa-dialogs-count">0 Groups</b> · 🛡️ Anti-Ban: <b style="color:#10b981;">60-80s Jitter + Adaptive Risk Brain + 60-90s Batch Rest</b></div>
          </div>
          <span id="wa-device-phone" style="display:none;"></span>
        </div>

        <!-- ⏱️ GLOBAL SMART GAP ENGINE: no time restrictions, user-controlled pacing everywhere -->
        <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:8px; background:#050811; border:1px solid #1e293b; border-radius:10px; padding:8px 14px;">
          <b style="font-size:12px; color:#f59e0b;">⏱️ Anti-Ban Gap Engine:</b>
          <select id="global-gap-preset" onchange="applyGapPreset(this.value)" style="margin:0; padding:5px 8px; font-size:12px; background:#0b1329; border:1px solid #f59e0b; color:#f8fafc; border-radius:6px;">
            
            <option value="60,80" selected>🛡️ Safe — 60-80s (recommended)</option>
            <option value="90,150">🐢 Long — 1.5-2.5 min</option>
            <option value="180,300">🧘 Extra Long — 3-5 min</option>
            <option value="300,600">🌙 Marathon — 5-10 min</option>
            <option value="custom">⚙️ Custom</option>
          </select>
          <span style="font-size:11px; color:var(--text-muted);">Gap:</span>
          <input type="number" id="gap-min" value="40" min="3" style="width:64px; margin:0; padding:5px 6px; font-size:12px; text-align:center;" oninput="saveGapSettings()">
          <span style="font-size:11px; color:var(--text-muted);">–</span>
          <input type="number" id="gap-max" value="60" min="5" style="width:64px; margin:0; padding:5px 6px; font-size:12px; text-align:center;" oninput="saveGapSettings()">
          <span style="font-size:11px; color:var(--text-muted);">sec/poll</span>
          <span style="font-size:11px; color:#10b981; font-weight:700;">⏰ No time limits — మీ ఇష్టం వచ్చినప్పుడు పంపండి (day/night anytime)</span>
        </div>
      </div>
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
        <button class="btn btn-accent" style="font-size:12px; padding:6px 12px;" onclick="syncWADialogs()">🔄 Auto-Sync Joined Groups</button>
        <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="showQRLoginModal()">📷 Scan QR Login</button>
        <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="showCodeLoginModal()">🔢 Login with Code</button>
        <button class="btn btn-outline" style="font-size:12px; padding:6px 12px; border-color:#ef4444; color:#ef4444;" onclick="logoutWASession()">🚪 Unlink Device</button>
      </div>
    </div>
    <div id="wa-login-dialog" style="display:none; margin-top:14px; background:#050811; padding:14px; border-radius:8px; border:1px solid var(--border);"></div>
  </div>

  <div class="tabs">
    <div class="nav-brand">🎓 StudentUp<small>Admin Control · neat &amp; easy</small></div>
    <input class="nav-search" id="nav-search" placeholder="🔍 Search tabs… (exam, whatsapp, members)" oninput="filterNav(this.value)">
    <button class="btn btn-outline" style="margin:2px 0 4px; padding:6px 10px; font-size:11px; justify-content:center;" onclick="openCmdk()">⌨️ Quick Search · Ctrl+K</button>
    <div class="nav-group">Main</div>
    <button class="tab-btn active" onclick="switchTab('tab-setup-wizard')">🏠 Home · Easy Setup Wizard</button>
    <div class="nav-group">Dispatch</div>
    <button class="tab-btn" onclick="switchTab('tab-bulk-broadcast')">🚀 Bulk Broadcast</button>
    <button class="tab-btn" onclick="switchTab('tab-wa-dispatch')">🛡️ WhatsApp Dispatcher</button>
    <button class="tab-btn" onclick="switchTab('tab-bundles')">📦 Bundles</button>
    <button class="tab-btn" onclick="switchTab('tab-excel-import')">📊 Excel Import</button>
    <div class="nav-group">Exams</div>
    <button class="tab-btn" onclick="switchTab('tab-campus')">🏫 College Exams &amp; QR</button>
    <button class="tab-btn" onclick="switchTab('tab-conductor')">🎓 Exam Conductor</button>
    <div class="nav-group">People</div>
    <button class="tab-btn" onclick="switchTab('tab-members')">📋 Members &amp; CRM</button>
    <button class="tab-btn" onclick="switchTab('tab-member-queue')">👥 Member Queue</button>
    <button class="tab-btn" onclick="switchTab('tab-squads')">⚔️ Squad Wars &amp; Arena</button>
    <div class="nav-group">Live &amp; Content</div>
    <button class="tab-btn" onclick="switchTab('tab-dynamic-channels')">📢 Telegram Channels</button>
    <button class="tab-btn" onclick="switchTab('tab-control')">⚡ Fast Actions · War</button>
    <div class="nav-group">Insights</div>
    <button class="tab-btn" onclick="switchTab('tab-growth')">📈 Growth &amp; Revenue</button>
    <button class="tab-btn" onclick="switchTab('tab-history')">📊 History &amp; Analytics</button>
    <div class="nav-group">System</div>
    <button class="tab-btn" onclick="switchTab('tab-proops')">🏢 Pro Ops</button>
  </div>

  <!-- ⌨️ COMMAND PALETTE (Ctrl+K) -->
  <div id="cmdk-overlay" style="display:none; position:fixed; inset:0; background:rgba(3,6,12,.72); z-index:200;" onclick="if(event.target===this) closeCmdk()">
    <div style="max-width:560px; margin:9vh auto 0; background:#0b1329; border:1px solid #2b3f66; border-radius:14px; overflow:hidden; box-shadow:0 24px 60px rgba(0,0,0,.6);">
      <input id="cmdk-input" placeholder="🔍 Search — tabs, college exams, members… (↑↓ select · Enter open · Esc close)" oninput="cmdkSel=0; renderCmdk(this.value)" style="width:100%; margin:0; border:none; border-bottom:1px solid var(--border); border-radius:0; padding:14px 16px; font-size:15px; background:#0b1329;">
      <div id="cmdk-list" style="max-height:46vh; overflow-y:auto; padding:6px;"></div>
    </div>
  </div>

  <!-- TAB 1: WHATSAPP INTERLEAVED DISPATCHER -->
  <div id="tab-wa-dispatch" class="tab-pane">
    <div class="planner-hero"><div><div class="eyebrow">CONTROL CENTER · WHATSAPP AUTOMATION</div><h2>Plan once. Deliver automatically.</h2><p>Pick an exam, choose exact groups, set multiple daily times and let the server run the schedule.</p></div><div class="hero-actions"><button class="btn btn-accent" onclick="toggleScheduleBuilder()">＋ New smart schedule</button><button class="btn btn-outline" onclick="switchTab('tab-excel-import')">Import from Excel</button></div></div>
    <div class="planner-grid"><div class="planner-card"><div class="planner-card-head"><span class="step">01</span><div><b>Choose exam / poll pack</b><small>Only matching content will be sent</small></div></div><div class="exam-pills"><button onclick="setPlannerCategory('ALL',this)" class="exam-pill active">All exams</button><button onclick="setPlannerCategory('POLICE',this)" class="exam-pill">Police</button><button onclick="setPlannerCategory('TSPSC',this)" class="exam-pill">TSPSC</button><button onclick="setPlannerCategory('APPSC',this)" class="exam-pill">APPSC</button><button onclick="setPlannerCategory('SSC',this)" class="exam-pill">SSC / Railway</button><button onclick="setPlannerCategory('TET_DSC',this)" class="exam-pill">TET / DSC</button><button onclick="setPlannerCategory('CURRENT',this)" class="exam-pill">Current affairs</button></div></div><div class="planner-card"><div class="planner-card-head"><span class="step">02</span><div><b>Choose recipients</b><small>Tick exact groups in the directory below</small></div></div><div class="selection-summary"><strong id="planner-selected-count">0 groups selected</strong><span>Category filters remain available</span></div><button class="btn btn-outline" onclick="document.getElementById('table-wa-groups').scrollIntoView({behavior:'smooth',block:'center'})">Select groups ↓</button></div><div class="planner-card"><div class="planner-card-head"><span class="step">03</span><div><b>Set delivery plan</b><small>Times, frequency, duration and days</small></div></div><div class="mini-stat-row"><span>⏱ Multi-time</span><span>📅 Lifetime / days</span><span>🛡 Safe queue</span></div><button class="btn btn-accent" onclick="toggleScheduleBuilder()">Open scheduler →</button></div></div>
    <div class="panel-card">
      <h2>🛡️ Advanced WhatsApp Anti-Ban Dispatcher (5 Polls/Group, 60-80s Jitter, Adaptive Risk Brain)</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">
        ఖాతా పూర్తి భద్రత కోసం: ప్రతి గ్రూపులో <b>5 ప్రశ్నలు</b> పూర్తయ్యే వరకు <b>40-60 సెకన్ల</b> రాండమ్ గ్యాప్‌తో పోస్ట్ అవుతాయి. ప్రతి 5 గ్రూపుల తర్వాత <b>60-90 సెకన్ల</b> కూల్‌డౌన్ పాజ్ తీసుకుంటుంది. మొదటి 5 గ్రూపులకు ఇంగ్లీష్ మొదటి లైన్, తర్వాతి 5 గ్రూపులకు తెలుగు మొదటి లైన్ క్రమంలో ఆటోమేటిక్ బైలింగ్వల్ రోటేషన్ ఉంటుంది.
      </p>

      <div style="display:grid; grid-template-columns: 2fr 1fr; gap:20px;">
        <div>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
            <div>
              <label>🎯 Exam Category Filter:</label>
              <select id="wa-target-category">
                <option value="ALL">🌐 ALL Categories & Groups (100+ Mode)</option>
                <optgroup label="🎓 Telangana (TS) Student Communities">
                  <option value="TS_BTECH">💻 TS B.Tech (JNTUH/OU/Placements)</option>
                  <option value="TS_DEGREE">🎓 TS Degree (B.Com/B.Sc/B.A)</option>
                  <option value="TS_DIPLOMA">⚙️ TS Diploma & POLYCET</option>
                  <option value="TS_INTER">📘 TS Intermediate (MPC/BiPC)</option>
                  <option value="TS_10TH">🎒 TS 10th Class Board (SSC)</option>
                  <option value="TSPSC">🏛️ TSPSC State & TS Districts</option>
                </optgroup>
                <optgroup label="🌊 Andhra Pradesh (AP) Student Communities">
                  <option value="AP_BTECH">💻 AP B.Tech (JNTUK/JNTUA/Placements)</option>
                  <option value="AP_DEGREE">🎓 AP Degree (AU/SVU/ANU)</option>
                  <option value="AP_DIPLOMA">⚙️ AP Diploma & POLYCET</option>
                  <option value="AP_INTER">📘 AP Intermediate (BIEAP/EAPCET)</option>
                  <option value="AP_10TH">🎒 AP 10th Class Board (BSEAP)</option>
                  <option value="APPSC">🏛️ APPSC State & AP Districts</option>
                </optgroup>
                <optgroup label="🔧 Technical, Open Distance & Govt Exams">
                  <option value="TET_DSC">👩‍🏫 TS & AP TET / DSC (Teachers, SGT, TRT)</option>
                  <option value="ITI_ALL">🔧 TS & AP ITI (Electrician/Fitter/NCVT)</option>
                  <option value="OPEN_UNIV">🏛️ Open Universities (BRAOU/IGNOU/Distance)</option>
                  <option value="POLICE">👮 Police Exams (SI / Constable)</option>
                  <option value="SSC">🏛️ Central Jobs & SSC (CGL, CHSL, MTS)</option>
                  <option value="RAILWAY">🚆 Railway RRB (NTPC, Group D)</option>
                  <option value="BANKING">🏦 Banking Aspirants (SBI, IBPS)</option>
                </optgroup>
              </select>
            </div>
            <div>
              <label>⏰ Time / Shift Filter:</label>
              <select id="wa-target-shift">
                <option value="ALL">☀️/🌙 All Shifts (Morning + Evening)</option>
                <option value="MORNING">🌅 Morning Shift (07:00 AM - 12:00 PM)</option>
                <option value="EVENING">🌆 Evening Shift (05:00 PM - 10:00 PM)</option>
              </select>
            </div>
          </div>

          <label>Optional: Central Announcement or Message Text (Leave blank to send auto-built exam polls):</label>
          <textarea id="wa-broadcast-msg" rows="3" placeholder="Enter custom update or study notification..."></textarea>

          <label>Optional Photo / Poster URL (Posts image along with text):</label>
          <input type="text" id="wa-attachment-url" placeholder="https://example.com/daily-current-affairs-poster.jpg">

          <div style="display:flex; gap:10px; margin-top:8px; flex-wrap:wrap;">
            <button class="btn btn-accent" onclick="startInterleaved(true)">🚀 Start 5-Poll Anti-Ban Quiz Rounds</button>
            <button class="btn btn-purple" onclick="startInterleaved(false)">📢 Send Custom Announcement</button>
            <button class="btn btn-outline" onclick="toggleScheduleBuilder()">⏰ Schedule Daily Timed Quiz</button>
            <button class="btn btn-danger" onclick="stopInterleaved()">🛑 Stop Pipeline</button>
          </div>

          <!-- ⏰ ADVANCED VISUAL SCHEDULE BUILDER — any duration: 2d, 15d, 1 month, 2 months, life-long -->
          <div id="schedule-builder" style="display:none; margin-top:14px; background:linear-gradient(135deg,#0d1b36,#101d33); border:1px solid #fbbf24; border-radius:12px; padding:16px;">
            <h3 style="font-size:14px; color:#fbbf24; margin-bottom:10px;">🛠️ Advanced Schedule Builder</h3>
            <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:10px;">
              <div>
                <label>⏰ From Time</label>
                <input type="time" id="sb-time" value="10:00" oninput="updateTimesPreview()">
              </div>
              <div>
                <label>🕣 To Time (optional)</label>
                <input type="time" id="sb-time-to" oninput="updateTimesPreview()">
              </div>
              <div>
                <label>🔁 రోజుకి ఎన్నిసార్లు?</label>
                <input type="number" id="sb-times-per-day" min="1" max="12" value="1" oninput="updateTimesPreview()">
              </div>
              <div>
                <label>📊 Questions / slot</label>
                <input type="number" id="sb-count" min="1" max="20" value="5">
              </div>
              <div>
                <label>✅ Answer key delay (minutes)</label>
                <input type="number" id="sb-answer-delay" min="0" max="60" value="5">
              </div>
              <div>
                <label>🏷️ Slot పేరు (optional)</label>
                <input type="text" id="sb-label" placeholder="Morning Police Drill">
              </div>
            </div>
            <div id="sb-times-preview" style="font-size:11px; color:#38bdf8; margin-top:5px;">⏰ 1 slot: 10:00</div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-top:10px;">
              <div>
                <label>📅 From Date (ఖాళీ = ఈరోజే start)</label>
                <input type="date" id="sb-date-from" oninput="datesPicked()">
              </div>
              <div>
                <label>📅 To Date (exact last day — optional)</label>
                <input type="date" id="sb-date-to" oninput="datesPicked()">
              </div>
            </div>
            <label style="margin-top:10px; display:block;">📅 ఎన్ని రోజులు నడవాలి? (tap చేయండి — ఏదైనా పెట్టుకోవచ్చు)</label>
            <div id="sb-dur-chips" style="display:flex; gap:6px; flex-wrap:wrap; margin-top:4px;">
              <button class="btn btn-outline sb-chip" data-days="0" onclick="selectDurChip(0,this)" style="padding:5px 10px; font-size:12px;">♾️ Life-Long</button>
              <button class="btn btn-outline sb-chip" data-days="2" onclick="selectDurChip(2,this)" style="padding:5px 10px; font-size:12px;">2 Days</button>
              <button class="btn btn-outline sb-chip" data-days="7" onclick="selectDurChip(7,this)" style="padding:5px 10px; font-size:12px;">1 Week</button>
              <button class="btn btn-outline sb-chip" data-days="15" onclick="selectDurChip(15,this)" style="padding:5px 10px; font-size:12px;">15 Days</button>
              <button class="btn btn-outline sb-chip" data-days="30" onclick="selectDurChip(30,this)" style="padding:5px 10px; font-size:12px;">1 Month</button>
              <button class="btn btn-outline sb-chip" data-days="60" onclick="selectDurChip(60,this)" style="padding:5px 10px; font-size:12px;">2 Months</button>
              <button class="btn btn-outline sb-chip" data-days="90" onclick="selectDurChip(90,this)" style="padding:5px 10px; font-size:12px;">3 Months</button>
              <input type="number" id="sb-custom-days" min="1" max="3650" placeholder="Custom days" style="width:110px; padding:5px 8px; font-size:12px;" oninput="customDurTyped()">
            </div>
            <div id="sb-dur-note" style="font-size:11px; color:#fbbf24; margin-top:5px;">♾️ Life-Long selected — ఎప్పటికీ ఆగదు</div>
            <label style="margin-top:10px; display:block;">📅 వారంలో ఏ రోజులు? (ఖాళీ = ప్రతిరోజూ)</label>
            <div style="display:flex; gap:9px; flex-wrap:wrap; margin-top:5px; font-size:12px;">
              <label><input type="checkbox" class="sb-weekday" value="1"> Mon</label><label><input type="checkbox" class="sb-weekday" value="2"> Tue</label><label><input type="checkbox" class="sb-weekday" value="3"> Wed</label><label><input type="checkbox" class="sb-weekday" value="4"> Thu</label><label><input type="checkbox" class="sb-weekday" value="5"> Fri</label><label><input type="checkbox" class="sb-weekday" value="6"> Sat</label><label><input type="checkbox" class="sb-weekday" value="0"> Sun</label>
            </div>
            <label style="margin-top:10px; display:block;">📚 Subjects (ఏదీ select చేయకపోతే = ALL subjects mix)</label>
            <div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:4px; font-size:12px;">
              <label style="display:flex; align-items:center; gap:4px;"><input type="checkbox" class="sb-subj" value="MATHS">🔢 Maths</label>
              <label style="display:flex; align-items:center; gap:4px;"><input type="checkbox" class="sb-subj" value="REASONING">🧠 Reasoning</label>
              <label style="display:flex; align-items:center; gap:4px;"><input type="checkbox" class="sb-subj" value="GK">🌍 GK</label>
              <label style="display:flex; align-items:center; gap:4px;"><input type="checkbox" class="sb-subj" value="CURRENT">📰 Current Affairs</label>
              <label style="display:flex; align-items:center; gap:4px;"><input type="checkbox" class="sb-subj" value="ENGLISH">🔤 English</label>
              <label style="display:flex; align-items:center; gap:4px;"><input type="checkbox" class="sb-subj" value="SCIENCE">🔬 Science</label>
            </div>
            <input type="text" id="sb-subj-custom" placeholder="Custom subjects: HISTORY+GEOGRAPHY (+ tho) — bank topics tho match avuthaayi" style="margin-top:6px; font-size:12px;">
            <div style="display:flex; gap:10px; margin-top:12px; flex-wrap:wrap;">
              <button class="btn btn-accent" onclick="createScheduleFromBuilder()">✅ Create Schedule (Target: selected groups/category above)</button>
              <button class="btn btn-outline" onclick="toggleScheduleBuilder()">✖ Close</button>
            </div>
          </div>

          <div class="schedule-control-card" style="margin-top:16px; background:#0b1329; border:1px solid #38bdf8; border-radius:10px; padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
              <div>
                <h3 style="font-size:14px; color:#38bdf8; display:flex; align-items:center; gap:6px;">
                  ⏰ 24x7 Multi-Slot Daily Autonomous Quiz Scheduler
                  <span style="background:#10b981; color:#050811; font-size:10px; font-weight:800; padding:2px 7px; border-radius:12px;">● ALWAYS-ON DAEMON</span>
                </h3>
                <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">
                  రోజులో మీరు ఎన్ని సార్లైనా (ఉదయం, మధ్యాహ్నం, సాయంత్రం, రాత్రి) క్లాక్‌లో టైమ్ ఎంచుకుని సెట్ చేయవచ్చు. కంప్యూటర్ లేదా బ్రౌజర్ ఆఫ్ చేసినా సర్వరే ఆటోమేటిక్‌గా రన్ చేస్తుంది!
                </div>
              </div>
            </div>

            <!-- Instant Time Picker Bar (HTML5 Native Clock Picker) -->
            <div style="background:#070d1e; padding:14px; border-radius:8px; border:1px solid rgba(56,189,248,0.3); margin-bottom:12px;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
                <div style="font-size:13px; font-weight:800; color:#38bdf8;">⏰ Advanced Daily Recurring Quiz Scheduler & Auto-Continuous Engine</div>
                <div style="display:flex; gap:8px; align-items:center;">
                  <label style="font-size:12px; color:#a7f3d0; font-weight:700; cursor:pointer; display:flex; align-items:center; gap:5px;">
                    <input type="checkbox" id="sched-auto-continuous" checked onchange="toggleContinuousMode(this.checked)">
                    <span>⚡ Auto Continuous Mode (Daily non-stop without re-scheduling)</span>
                  </label>
                </div>
              </div>

              <!-- Real-time conflict warning banner inside Scheduler -->
              <div id="sched-conflict-alert" style="display:none; background:#7f1d1d; border:1px solid #ef4444; color:#fecaca; padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:10px;">
                ⚠️ <b>Conflict Alert:</b> <span id="sched-conflict-msg"></span>
              </div>

              <div style="display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap;">
                <div style="flex:1; min-width:130px;">
                  <label style="font-size:11px; color:#38bdf8; font-weight:700; margin:0 0 4px 0; display:block;">🕒 Primary Time:</label>
                  <input type="time" id="clock-slot-time" value="09:00" style="margin:0; padding:7px 10px; font-size:14px; font-weight:800; color:#38bdf8; background:#0b1329; border:1px solid #38bdf8;" onchange="checkSchedulerConflictLive()">
                </div>
                <div style="flex:2; min-width:170px;">
                  <label style="font-size:11px; color:#a7f3d0; font-weight:700; margin:0 0 4px 0; display:block;">🕒 Extra Daily Times (Multiple times per day):</label>
                  <input type="text" id="clock-extra-times" placeholder="e.g. 13:00, 18:30, 21:00" style="margin:0; padding:7px 10px; font-size:12px;" onchange="checkSchedulerConflictLive()">
                </div>
                <div style="flex:2; min-width:170px;">
                  <label style="font-size:11px; color:var(--text-muted); margin:0 0 4px 0; display:block;">📝 Slot Label / Purpose:</label>
                  <input type="text" id="clock-slot-label" placeholder="e.g. Daily Grand Practice Drill" style="margin:0; padding:7px 10px; font-size:12px;">
                </div>
                <div style="flex:1; min-width:140px;">
                  <label style="font-size:11px; color:var(--text-muted); margin:0 0 4px 0; display:block;">🎯 Target Exam:</label>
                  <select id="clock-slot-cat" style="margin:0; padding:7px 10px; font-size:12px;">
                    <option value="ALL">🌐 ALL Groups</option>
                    <option value="POLICE">👮 Police SI/Constable</option>
                    <option value="TSPSC">🏛️ TSPSC State</option>
                    <option value="APPSC">🏛️ APPSC State</option>
                    <option value="SSC">🏛️ SSC & Central</option>
                    <option value="TET_DSC">👩‍🏫 TET / DSC</option>
                    <option value="TS_BTECH">💻 TS B.Tech</option>
                    <option value="AP_BTECH">💻 AP B.Tech</option>
                    <option value="CURRENT">🗞️ Current Affairs</option>
                  </select>
                </div>
                <div id="sched-duration-container" style="flex:1; min-width:130px; display:none;">
                  <label style="font-size:11px; color:#f59e0b; margin:0 0 4px 0; display:block;">📅 Duration (Days):</label>
                  <input type="number" id="sched-days-duration" value="7" min="1" max="365" style="margin:0; padding:7px 10px; font-size:12px;">
                </div>
                <div style="display:flex; align-items:flex-end;">
                  <button class="btn btn-accent" style="padding:8px 16px; font-size:12px; white-space:nowrap;" onclick="addClockSlot()">➕ Add Daily Slot(s)</button>
                </div>
              </div>
            </div>

            <!-- Active Scheduled Jobs List -->
            <div id="wa-schedules-container" style="background:#050811; padding:12px; border-radius:8px; border:1px solid rgba(255,255,255,0.08);">
              <div id="wa-schedules-list" style="font-size:12px;"></div>
            </div>
          </div>

          <div style="margin-top:14px;">
            <div style="display:flex; justify-content:space-between; font-size:12px; color:var(--text-muted);">
              <span id="pipeline-status-text">Status: Idle</span>
              <span id="pipeline-progress-text">0 / 0 Groups</span>
            </div>
            <div class="progress-bar-container">
              <div id="pipeline-progress-bar" class="progress-bar"></div>
            </div>
            <div id="pipeline-pacing-text" style="font-size:11px; color:#93c5fd; margin-top:6px;">🧠 Adaptive Anti-Ban: ×1.00 · 🟢 HEALTHY · fatigue ×1.00</div>
            <div id="wa-safety-stack" style="margin-top:10px; font-size:12px;"></div>
            <div id="wa-safety-detail" style="margin-top:6px; font-size:11.5px;"></div>
          </div>
        </div>

        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:16px;">
          <h3 style="font-size:14px; margin-bottom:12px; color:#38bdf8;">⚙️ Interleaved Anti-Ban Setup</h3>
          <div style="font-size:12px; line-height:1.7; color:var(--text-muted);">
            ✔ <b>2-by-2 Group Rotation:</b> Rotates across groups while students contemplate answers.<br>
            ✔ <b>Random 20–30s Human Delays:</b> Zero robotic pattern.<br>
            ✔ <b>Two-Phase Delivery:</b> Question first, Answer Key after delay.<br>
            ✔ <b>Invisible Hash Markers:</b> Dynamic zero-width characters in each post.<br>
            ✔ <b>Exam Segregation:</b> Police questions never leak to Banking/SSC groups.<br>
          </div>
          <div style="margin-top:14px;">
            <label style="font-size:12px;">WhatsApp Webhook / Gateway Endpoint (Optional):</label>
            <input type="text" id="wa-gateway-input" placeholder="http://localhost:3000/send or GreenAPI/UltraMsg">
          </div>
        </div>
      </div>

      <div style="margin-top:24px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div>
            <h3 style="margin-bottom:4px;">📋 Managed WhatsApp Groups Directory</h3>
            <span style="font-size:12px; color:var(--text-muted);">Select specific groups or search by keyword to dispatch quizzes instantly</span>
          </div>
          <div style="display:flex; gap:8px; align-items:center;">
            <input type="text" id="wa-search-box" placeholder="🔍 Search groups..." onkeyup="filterWAGroups()" style="width:170px; margin:0; padding:6px 10px; font-size:12px;">
            <button class="btn btn-purple" style="font-size:12px; padding:6px 12px;" onclick="dispatchSelectedGroups()">⚡ Run Quiz on Selected</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="selectAllGroups(true)">Select All</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="selectAllGroups(false)">Clear</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="loadWAGroups()">🔄 Refresh</button>
          </div>
        </div>
        <table id="table-wa-groups">
          <thead>
            <tr>
              <th style="width:30px;"><input type="checkbox" id="wa-select-all" onchange="selectAllGroups(this.checked)"></th>
              <th>ID</th>
              <th>Group Title</th>
              <th>Assigned Exam Category</th>
              <th>Group Type</th>
              <th>Shift</th>
              <th>JID / Link</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
        <div style="margin-top:14px; background:rgba(212,175,55,0.07); border:1px solid rgba(212,175,55,0.45); border-radius:10px; padding:12px 14px;">
          <b>🏆 Hall of Fame — WhatsApp All-Time Champions</b>
          <div id="wa-hof" style="margin-top:8px; font-size:13px;"><span style="color:var(--text-muted);">Inka champions leru — first winners round tarvata ikkada kanipistharu.</span></div>
        </div>

        <div style="display:flex; gap:10px; margin-top:16px; background:#0f172a; padding:12px; border-radius:8px; flex-wrap:wrap; align-items:center;">
          <input type="text" id="new-wa-title" placeholder="Group Title (e.g. Warangal TS Police SI Batch)" style="flex:2; min-width:200px; margin:0;">
          <input type="text" id="new-wa-jid" placeholder="Group JID / Channel JID (…@newsletter) / Invite link" style="flex:2; min-width:200px; margin:0;">
          <select id="new-wa-category" style="width:160px; margin:0;">
            <option value="AUTO">🤖 Auto Category</option>
            <option value="GENERAL">🌐 General Group</option>
            <option value="TET_DSC">👩‍🏫 TS & AP TET / DSC</option>
            <option value="AP_BTECH">AP B.Tech</option>
            <option value="AP_DEGREE">AP Degree</option>
            <option value="AP_DIPLOMA">AP Diploma</option>
            <option value="AP_INTER">AP Intermediate</option>
            <option value="AP_10TH">AP 10th Class</option>
            <option value="TS_BTECH">TS B.Tech</option>
            <option value="TS_DEGREE">TS Degree</option>
            <option value="TS_DIPLOMA">TS Diploma</option>
            <option value="TS_INTER">TS Intermediate</option>
            <option value="TS_10TH">TS 10th Class</option>
            <option value="ITI_ALL">TS & AP ITI</option>
            <option value="OPEN_UNIV">Open Universities</option>
            <option value="POLICE">POLICE</option>
            <option value="SSC">SSC / Central</option>
            <option value="RAILWAY">RAILWAY</option>
            <option value="BANKING">BANKING</option>
            <option value="TSPSC">TSPSC / TS Districts</option>
            <option value="APPSC">APPSC / AP Districts</option>
          </select>
          <select id="new-wa-grouptype" style="width:160px; margin:0;">
            <option value="EXAM_SPECIFIC">🎯 Specific Exam Group</option>
            <option value="GENERAL">🌐 General Group</option>
          </select>
          <select id="new-wa-shift" style="width:130px; margin:0;">
            <option value="ALL_DAY">All-Day</option>
            <option value="MORNING">Morning Shift</option>
            <option value="EVENING">Evening Shift</option>
          </select>
          <button class="btn btn-accent" style="white-space:nowrap;" onclick="addNewWAGroup()">➕ Connect Group</button>
        </div>

        <!-- In-Tab Direct Excel / CSV File Uploader & Quick Paste Card -->
        <div style="margin-top:16px; background:#070d1e; border:1px solid #38bdf8; border-radius:10px; padding:16px;">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:10px;">
            <div>
              <h4 style="color:#38bdf8; font-size:14px; display:flex; align-items:center; gap:6px;">
                📊 Excel & CSV File Direct Uploader / Bulk Paste (50+ to 150+ Groups)
              </h4>
              <p style="font-size:12px; color:var(--text-muted); margin-top:2px;">
                మీ దగ్గర ఉన్న <b>.xlsx, .xls, లేదా .csv</b> ఫైల్‌ను నేరుగా బ్రౌజ్ చేసి అప్‌లోడ్ చేయండి, లేదా క్రింద ఉన్న బాక్స్‌లో నేరుగా కాపీ-పేస్ట్ చేయండి!
              </p>
            </div>
            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
              <a href="/api/excel/template_xlsx" class="btn btn-outline" style="font-size:12px; padding:6px 14px; text-decoration:none; color:#34d399; border-color:#34d399;">📥 Sample Excel (.xlsx + Auto-Schedule)</a>
              <input type="file" id="wa-excel-file-input" accept=".csv, .xlsx, .xls, .txt, .tsv" style="display:none;" onchange="handleExcelFileUpload(event)">
              <button class="btn btn-accent" style="font-size:12px; padding:6px 14px;" onclick="document.getElementById('wa-excel-file-input').click()">📁 Choose Excel / CSV File</button>
              <button class="btn btn-purple" style="font-size:12px; padding:6px 14px;" onclick="importInTabExcel()">📥 Import Pasted Rows</button>
            </div>
          </div>
          <textarea id="wa-direct-excel-paste" rows="4" placeholder="Or directly paste rows from Excel / Google Sheets here (Columns: Group Name | Link or JID | Category | Shift | Group Type)..." style="margin-bottom:8px; font-size:12px;"></textarea>
          <div id="wa-excel-status-log" style="font-size:11px; color:#10b981; font-weight:600;"></div>
        </div>
      </div>

      <div id="wa-log-box" class="log-box" style="margin-top:16px;">WhatsApp Interleaved Dispatcher ready.</div>
    </div>
  </div>

  <!-- TAB 2: COLLEGE ON-SPOT EXAMS & QR -->
  <div id="tab-campus" class="tab-pane">
    <div class="panel-card">
      <h2>🏫 College On-Spot Exam Launcher & Dynamic QR Generator</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
        ఏ కాలేజీకి వెళ్లినా సరే, అక్కడికక్కడే 1 నిమిషంలో కాలేజ్ పేరుతో ప్రత్యేక ఆన్-స్పాట్ టెస్ట్ లాంచ్ చేయవచ్చు! విద్యార్థులు స్కాన్ చేసి నేరుగా పేరు, మొబైల్ ఇచ్చి టెస్ట్ రాస్తారు. టెస్ట్ ముగియగానే పూర్తి మార్కుల రిపోర్ట్ ప్రిన్సిపాల్ / HOD కోసం రెడీ అవుతుంది.
      </p>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <div style="background:#0f172a; padding:18px; border-radius:10px; border:1px solid var(--border);">
          <h3 style="font-size:15px; margin-bottom:12px; color:#38bdf8;">➕ Launch New College Exam Event</h3>
          <label>College Name (e.g. SR Engineering College or Kakatiya Univ): <span style="color:var(--text-muted); font-size:11px;">— ekkuva colleges kosam comma tho separate cheyyandi (Inter-College War!)</span></label>
          <input type="text" id="campus-college-name" placeholder="Enter College Name">

          <label>District:</label>
          <input type="text" id="campus-district" placeholder="e.g. Warangal, Visakhapatnam, Hyderabad, Guntur">

          <label>⏰ Auto-Start Time (optional — ఖాళీగా వదిలేస్తే మీరే 🚀 Start నొక్కాలి):</label>
          <input type="datetime-local" id="campus-start-at">

          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
            <div>
              <label>Number of Questions:</label>
              <select id="campus-nq">
                <option value="5">5 Questions (Fast 5-Min Test)</option>
                <option value="10" selected>10 Questions (Standard 10-Min Test)</option>
                <option value="15">15 Questions (15-Min Test)</option>
                <option value="20">20 Questions (Grand Challenge)</option>
              </select>
            </div>
            <div>
              <label>Difficulty Level:</label>
              <select id="campus-level">
                <option value="easy">Easy (Engaging GK/Tech/Science)</option>
                <option value="medium">Medium (Competitive Level)</option>
                <option value="hard">Hard (Advanced / GATE)</option>
              </select>
            </div>
          </div>

          <label style="margin-top:6px;">⚠️ Negative Marking (real-exam feel, optional):</label>
          <select id="campus-neg">
            <option value="0" selected>No negative marking (friendly)</option>
            <option value="1">−1 point per wrong answer</option>
            <option value="2">−2 points per wrong answer</option>
            <option value="5">−5 points per wrong answer (strict)</option>
          </select>

          <label style="margin-top:6px;">Select Subjects to Include in Exam:</label>
          <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; font-size:12px; margin-bottom:12px; background:#050811; padding:10px; border-radius:8px; border:1px solid var(--border);">
            <label><input type="checkbox" id="subj-reasoning" checked> 🧩 Reasoning & Logic Puzzles</label>
            <label><input type="checkbox" id="subj-quant" checked> 🔢 Quantitative Aptitude / Maths</label>
            <label><input type="checkbox" id="subj-science" checked> 🔬 General Science & Tech</label>
            <label><input type="checkbox" id="subj-english" checked> 📖 General English & Vocabulary</label>
            <label><input type="checkbox" id="subj-ca" checked> 🗞️ Current Affairs & GK</label>
            <label><input type="checkbox" id="subj-coding"> 💻 Coding & Computer Science</label>
          </div>

          <button class="btn btn-accent" style="margin-top:4px;" onclick="createCampusEvent()">🚀 Generate College Exam Link & QR Code</button>
        </div>

        <div>
          <h3 style="font-size:15px; margin-bottom:12px;">📱 Active College Exam Link & Poster</h3>
          <div id="campus-active-card" style="background:#050811; border:1px solid var(--border); border-radius:8px; padding:14px; font-size:13px; line-height:1.6; min-height:180px;">
            Create or select a college event to view its live student registration link, QR Code and principal scorecard.
          </div>
        </div>
      </div>

      <div style="margin-top:24px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <h3>🏫 Active College Exam Sessions</h3>
          <button class="btn btn-outline" onclick="loadCampusEvents()">🔄 Refresh Sessions</button>
        </div>
        <table id="table-campus">
          <thead>
            <tr>
              <th>Event Code</th>
              <th>College Name</th>
              <th>District</th>
              <th>Questions</th>
              <th>Participants</th>
              <th>Status</th>
              <th>Action & Principal Report</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      <div class="panel-card" style="margin-top:16px;">
        <h3 style="font-size:14px; color:#38bdf8;">🌐 Portal Live Exams (quiz.studentup.in) — అందరి students kosam public live exams</h3>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; align-items:center;">
          <input type="text" id="pex-title" placeholder="Exam title e.g. Sunday Mega Test" style="flex:2; min-width:160px;">
          <select id="pex-goal" style="flex:1; min-width:130px;"></select>
          <input type="datetime-local" id="pex-start" style="flex:1; min-width:170px;">
          <select id="pex-dur"><option value="20">20 min</option><option value="30" selected>30 min</option><option value="45">45 min</option><option value="60">60 min</option></select>
          <select id="pex-nq"><option value="15">15 Qs</option><option value="20" selected>20 Qs</option><option value="30">30 Qs</option><option value="50">50 Qs</option></select>
          <select id="pex-neg" title="Negative marking (real exam pattern)"><option value="0">No negative</option><option value="0.25">−0.25 / wrong</option><option value="0.5">−0.5 / wrong</option><option value="1">−1 / wrong</option></select>
          <button class="btn btn-accent" onclick="createPortalExam()">➕ Schedule Live Exam</button>
          <button class="btn btn-outline" onclick="loadPortalExams()">🔄 Refresh</button>
        </div>
        <div id="pex-msg" style="font-size:12px; margin-top:8px;"></div>
        <div id="pex-list" style="font-size:12.5px; margin-top:8px; color:var(--text-muted);">Loading… (🏆 Weekly Grand Test prati Sunday 10 AM automatic ga create avthundi)</div>
      </div>

      <div class="panel-card" style="margin-top:16px;">
        <h3 style="font-size:14px; color:#38bdf8;">📊 Portal Analytics — students · funnel · goals · PYQ gaps</h3>
        <div id="pt-analytics" style="font-size:12.5px; margin-top:8px; color:var(--text-muted);">Loading…</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
          <button class="btn btn-outline" onclick="loadPortalAnalytics()">🔄 Refresh Analytics</button>
        </div>
        <h3 style="font-size:13px; margin-top:16px;">👥 Students Search</h3>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;">
          <input id="pt-q" type="text" placeholder="Name / district / phone…" style="flex:1; min-width:170px;">
          <button class="btn btn-outline" onclick="searchAdminStudents()">🔍 Search</button>
        </div>
        <div id="pt-students" style="font-size:12.5px; margin-top:8px; color:var(--text-muted);">Student search cheyyandi.</div>
        <h3 style="font-size:13px; margin-top:16px;">🚩 Question Flags (student reports)</h3>
        <div id="pt-flags" style="font-size:12.5px; margin-top:8px; color:var(--text-muted);">Loading…</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
          <button class="btn btn-outline" onclick="loadAdminFlags()">🔄 Refresh Flags</button>
        </div>
      </div>

      <div class="panel-card" style="margin-top:16px;">
        <h3 style="font-size:14px; color:#facc15;">📜 PYQ Harvest &amp; Import Center — real previous-year questions penchane engine</h3>
        <div id="pyq-status" style="font-size:12.5px; color:var(--text-muted); white-space:pre-line; margin-top:8px;">Loading…</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
          <button class="btn btn-accent" onclick="runPyqHarvest(false)">🌾 Run Harvest (Official Papers Download)</button>
          <button class="btn btn-outline" onclick="runPyqHarvest(true)">🧪 Dry Run</button>
          <button class="btn btn-outline" onclick="loadPyqStatus()">🔄 Status</button>
          <button class="btn btn-outline" onclick="downloadPyqTemplate()">📥 CSV Template</button>
        </div>
        <div id="pyq-msg" style="font-size:12px; margin-top:8px;"></div>
        <details style="margin-top:10px;">
          <summary style="cursor:pointer; font-size:13px; font-weight:700;">➕ Official Paper URL add cheyyandi (board site PDF/index link)</summary>
          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;">
            <select id="pyq-channel" style="min-width:110px;"><option>CURRENT</option><option>APPSC</option><option>TSPSC</option><option>SSC</option><option>BANKING</option><option>RAILWAY</option><option>POLICE</option><option>DEFENCE</option></select>
            <input id="pyq-exam" placeholder="Exam e.g. TSPSC Group-2" style="flex:1; min-width:140px;">
            <input id="pyq-year" placeholder="Year" style="width:80px;">
            <input id="pyq-paper" placeholder="Paper-1" style="width:90px;">
            <input id="pyq-url" placeholder="https://official-site…/paper.pdf" style="flex:2; min-width:220px;">
            <button class="btn btn-outline" onclick="addPyqPaper()">➕ Add Paper</button>
          </div>
          <div class="muted" style="font-size:11px; margin-top:6px;">Add chesina papers ni 🌾 Harvest download chesi, questions ga marchi, "📜 Exam Year" label tho bank loki vesthundi.</div>
        </details>
        <details style="margin-top:10px;">
          <summary style="cursor:pointer; font-size:13px; font-weight:700;">📥 CSV Import — mee deggara unna PYQ banks (Excel → CSV) direct ga add cheyyandi</summary>
          <div class="muted" style="font-size:11px; margin-top:6px;">Columns: question, option1, option2, option3, option4, answer (1-4 / A-D), explanation, exam, year, channel, topic · Duplicates automatic skip avthayi · Import avvagane Live Exams/Mocks lo use avthayi.</div>
          <textarea id="pyq-csv" rows="5" placeholder="CSV rows ikkada paste cheyyandi…" style="width:100%; margin-top:8px; background:#050811; color:#e2e8f0; border:1px solid var(--border); border-radius:8px; padding:10px;"></textarea>
          <div style="display:flex; gap:8px; margin-top:8px; align-items:center;">
            <input type="file" id="pyq-file" accept=".csv" onchange="readPyqFile(event)">
            <button class="btn btn-accent" onclick="importPyqCsv()">📥 Import PYQs</button>
            <span id="pyq-import-msg" style="font-size:12px;"></span>
          </div>
        </details>
        <details style="margin-top:10px;" open>
          <summary style="cursor:pointer; font-size:13px; font-weight:700;">📄 Paper Factory Drafts (370X) — official papers, owner approve tharuvatha ne bank</summary>
          <div class="muted" style="font-size:11px; margin-top:6px;">Server meeda paper file (PDF/TXT) path ichi draft cheyyandi — leda <code>python3 scripts/paper_factory.py make &lt;file&gt;</code>. Draft review: parsed/fresh counts + translation pending honest ga chupisthundi. ✅ Approve = bank loki (scraped_bank), ❌ Reject = draft close.</div>
          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;">
            <input id="pf-path" placeholder="data/pdf_inbox/TSPSC 2023 Paper-I.pdf" style="flex:2; min-width:220px;">
            <button class="btn btn-accent" onclick="makePaperDraft()">📄 Draft Cheyyandi</button>
            <button class="btn btn-outline" onclick="loadPaperDrafts()">🔄 Drafts</button>
          </div>
          <div id="pf-list" style="font-size:12px; margin-top:8px; white-space:pre-line;"></div>
          <div id="pf-msg" style="font-size:12px; margin-top:6px;"></div>
        </details>
      </div>

      <div class="panel-card" style="margin-top:16px;">
        <h3 style="font-size:14px; color:#38bdf8;">🌉 WordPress Bridge — studentup.in (blog) ↔ mana platform (quiz)</h3>
        <p class="muted" style="font-size:12px; margin-top:6px;">Smart rule: <b>Blog ki WordPress master</b> (publish chesthe automatic mana <a href="/blog" target="_blank">/blog</a> lo kanipisthundi) · <b>Quiz ki mana bank master</b> (ikkada prepare chesina daily quiz ni WP format lo export chestham). Sync details: <code>docs/BRIDGE_PLAN.md</code> + WP snippet: <code>integrations/wordpress/</code>.</p>
        <div id="wp-status" style="font-size:12.5px; margin-top:8px; color:var(--text-muted);">Status inka check cheyyaledu.</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
          <button class="btn btn-outline" onclick="wpStatus()">🔍 WordPress Connection Test</button>
          <button class="btn btn-accent" onclick="wpExportQuiz()">📤 Today's Quiz → WP Format Export</button>
          <a class="btn btn-outline" href="/blog" target="_blank" style="text-decoration:none;">📰 /blog Chudu</a>
        </div>
        <div id="wp-msg" style="font-size:12px; margin-top:8px;"></div>
      </div>

      <div class="panel-card" style="margin-top:16px;">
        <h3 style="font-size:14px; color:#38bdf8;">🚦 Publish Center — Daily Draft → Approve → LIVE (310X)</h3>
        <p class="muted" style="font-size:12px; margin-top:6px;">Roju draft automatic ga ready avthundi (Daily Quiz + Live Exams + Sunday Weekly Grand). <b>Meeru Approve chesthene</b> WordPress push &amp; Go-Live avthayi — approve lekunda students ki emi velladu.</p>
        <div id="pub-status" style="font-size:12.5px; margin-top:8px; color:var(--text-muted); white-space:pre-line;">Draft inka load cheyyaledu.</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
          <button class="btn btn-outline" onclick="pubLoad()">🔄 Draft Refresh</button>
          <button class="btn btn-accent" onclick="pubApprove()">✅ Approve</button>
          <button class="btn btn-outline" onclick="pubPushWp()">🌐 Push to WordPress</button>
          <button class="btn btn-accent" onclick="pubGoLive()">🚀 Go Live</button>
          <button class="btn btn-outline" onclick="pubReject()">❌ Reject</button>
        </div>
        <div id="pub-msg" style="font-size:12px; margin-top:8px;"></div>
      </div>

      <div class="panel-card" style="margin-top:16px;">
        <h3 style="font-size:14px; color:#38bdf8;">📢 Exam Updates / Notices — students ki portal lo + public site lo kanipisthayi</h3>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
          <input id="ntc-title" placeholder="Notice title e.g. SSC CGL 2026 Notification Out!" style="flex:2; min-width:200px;">
          <input id="ntc-link" placeholder="Official link (optional)" style="flex:1; min-width:180px;">
        </div>
        <textarea id="ntc-body" rows="2" placeholder="Details… (dates, eligibility, apply dates)" style="width:100%; margin-top:8px; background:#050811; color:#e2e8f0; border:1px solid var(--border); border-radius:8px; padding:10px;"></textarea>
        <div style="display:flex; gap:8px; margin-top:8px;">
          <button class="btn btn-accent" onclick="postNotice()">📢 Post Notice</button>
          <button class="btn btn-outline" onclick="loadNotices()">🔄 Refresh</button>
          <span id="ntc-msg" style="font-size:12px;"></span>
        </div>
        <div id="ntc-list" style="font-size:12.5px; margin-top:8px; color:var(--text-muted);">Loading…</div>
      </div>

      <div class="panel-card" style="margin-top:16px;">
        <h3 style="font-size:14px; color:#10b981;">📩 Personal Coach — okko student ki valla report personal ga</h3>
        <p class="muted" style="font-size:12px; margin-top:6px;">Telegram students andari ki valla <b>points, streak, accuracy, weak topics, revision due</b> personal DM ga velthundi (okkokariki valla report matrame). Web (portal) students ki report portal lone untundi + valla deggara WhatsApp share button undi.</p>
        <div style="display:flex; gap:8px; margin-top:10px; align-items:center; flex-wrap:wrap;">
          <button class="btn btn-accent" onclick="sendPersonalReports()">📩 Personal Reports Pampu</button>
          <button class="btn btn-outline" onclick="reportStatus()">🔄 Status</button>
          <span id="rep-msg" style="font-size:12px;"></span>
        </div>
      </div>

      <div class="panel-card" style="margin-top:16px;">
        <h3 style="font-size:14px; color:#facc15;">🏆 College League — అన్ని exams kalipi Inter-College Standings</h3>
        <div id="campus-league-box" style="font-size:12px; margin-top:8px; color:var(--text-muted);">League data loading…</div>
      </div>
      </div>
    </div>
  </div>

  <!-- TAB: 🚀 EASY SETUP WIZARD -->
  <div id="tab-setup-wizard" class="tab-pane active">
    <div class="panel-card">
      <h2>🏠 Home · Easy Setup Wizard — 5 steps lo full system ready!</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:12px;">
        Telegram + WhatsApp rendu, step-by-step. Prathi step status automatic ga check avuthundi —
        pending unna chota button nokkithe saraina tab ki theeskellthundi. Anni ✅ aithe meeru emi cheyakkarledu, system ye nadusthundi!
      </p>
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
        <button class="btn btn-accent" onclick="switchTab('tab-campus')">🏫 New College Exam</button>
        <button class="btn btn-primary" onclick="switchTab('tab-bulk-broadcast')">🚀 Bulk Broadcast</button>
        <button class="btn btn-outline" onclick="switchTab('tab-wa-dispatch')">🛡️ WhatsApp Schedules</button>
        <button class="btn btn-outline" onclick="switchTab('tab-members')">📋 Members</button>
        <button class="btn btn-outline" onclick="switchTab('tab-dynamic-channels')">📢 Telegram Channels</button>
      </div>
      <div style="background:#0b1329; border:1px solid #22304d; border-radius:10px; height:14px; overflow:hidden; margin-bottom:14px;">
        <div id="wiz-progress" style="height:100%; width:0%; background:linear-gradient(90deg,#10b981,#38bdf8); transition:width .4s;"></div>
      </div>
      <div id="wiz-steps" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:12px;"></div>
      <details class="adv">
        <summary>🖥️ Advanced — server commands &amp; production (developers kosam)</summary>
        <div style="font-size:12.5px; margin-top:8px;">
        <b style="color:#38bdf8;">🖥️ Server meeda motham stack okka command tho:</b>
        <pre style="background:#0b1329; padding:10px; border-radius:8px; margin-top:8px; overflow:auto;">bash start_all.sh        # Dashboard + Bridge + Scheduler (collector 8x/day) + Bot</pre>
        <span style="color:var(--text-muted);">Production (systemd) kosam: <code>deploy/*.service</code> · Status: <code>python3 -m core.vision</code></span>
        <button class="btn btn-outline" style="margin-left:10px; padding:4px 10px; font-size:11px;" onclick="loadSetupWizard()">🔄 Refresh Status</button>
        </div>
      </details>
      <div id="wiz-actions" style="margin-top:12px; font-size:12.5px;"></div>
      <div style="margin-top:16px; border-top:1px solid var(--border); padding-top:14px;">
        <h3 style="font-size:14px; color:#a78bfa;">✨ Smart Day Planner — eeroju dispatch plan ready ga</h3>
        <p style="font-size:12px; color:var(--text-muted); margin:4px 0 8px;">Students eppudu active ga untaro + ekkada weak ga unnaro chusi system ye plan chesthundi. Nachithe okka click lo apply — anthe!</p>
        <div id="planner-box" style="font-size:12px; color:var(--text-muted);">"✨ Plan Chudu" nokkithe eeroju plan kanipisthundi.</div>
        <div style="display:flex; gap:8px; margin-top:8px; flex-wrap:wrap;">
          <button class="btn btn-purple" style="font-size:12px;" onclick="loadPlanner()">✨ Plan Chudu</button>
          <button class="btn btn-accent" style="font-size:12px;" onclick="applyPlanner()">✅ Select Chesinavi Apply Chey</button>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB 3: EXCEL / SHEET IMPORTER & MANAGER -->
  <div id="tab-member-queue" class="tab-pane"><div class="panel-card"><h2>👥 Consent-first Member Queue</h2><p style="color:var(--text-muted);font-size:13px;margin-bottom:16px">Upload opted-in members, review the queue, and send compliant group invites in controlled daily batches.</p><div class="grid-stats"><div class="stat-card"><div class="label">READY</div><div class="val" id="mq-ready">0</div></div><div class="stat-card"><div class="label">COMPLETED</div><div class="val" id="mq-done">0</div></div><div class="stat-card"><div class="label">PENDING CONSENT</div><div class="val" id="mq-pending">0</div></div><div class="stat-card"><div class="label">INVALID / FAILED</div><div class="val" id="mq-failed">0</div></div></div><label>CSV file (Name, Phone, Consent)</label><input type="file" id="mq-file" accept=".csv" onchange="importMemberQueue(event)"><label>Admin alert numbers</label><input id="mq-alerts" placeholder="9394483300, 7981009598"><label>Daily batch limit (maximum 20)</label><input id="mq-limit" type="number" min="1" max="20" value="20"><button class="btn btn-accent" onclick="saveMemberQueueSettings()">Save Queue Settings</button><div id="mq-log" class="log-box">Queue ready. Only OPTED_IN records are eligible.</div></div></div>

  <div id="tab-excel-import" class="tab-pane">
    <div class="panel-card">
      <h2>📊 Advanced Multi-Sheet Excel & Google Sheets Importer (100+ to 250+ Groups & Channels)</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
        ఒకే Excel వర్క్‌బుక్ లోని వేర్వేరు షీట్లను (Multi-Sheet: ఉదా: <i>Police_SI, TET_DSC, TSPSC_APPSC, BTech_Campus, General_Aptitude</i>) అప్‌లోడ్ చేసి, ఏ షీట్ కావాలో టిక్ చేసుకుని (Selective Multiple Sheets) ఒక్క క్లిక్‌తో డేటాబేస్‌లోకి ఇంపోర్ట్ చేసుకోవచ్చు!
      </p>

      <div style="background:#0f172a; padding:12px; border-radius:8px; margin-bottom:14px; font-size:12px; color:var(--text-muted); border-left:4px solid #38bdf8;">
        💡 <b>Excel Columns (Tab / Comma separated / .xlsx):</b><br>
        <code>Group Name | Link or JID | Category | Shift | Group Type | Daily Times | Polls Per Slot | Days (0=Always) | Subjects</code><br>
        <span style="color:#a7f3d0; font-size:11px;">మొదటి 2 columns చాలు — మిగతావన్నీ optional! ⏰ <b>Daily Times</b> (ఉదా: <code>08:00+20:30</code>) నింపితే ఆ group కి <b>ఆటోమేటిక్ డైలీ schedule</b> create అవుతుంది — ఎన్నిసార్లు (times), ఎన్ని polls (<b>Polls Per Slot</b>), ఎన్ని రోజులు (<b>Days</b>: 0 = Always-On), ఏ subjects (<code>MATHS+GK</code>) అన్నీ Excel లోనే!
        Invite link ఇస్తే bridge connect అయినప్పుడు <b>auto-join</b> కూడా అవుతుంది. 🛡️ Sends అన్నీ anti-ban engine తోనే.</span>
      </div>

      <!-- File Browse Upload with Multi-Sheet Inspector -->
      <div style="background:rgba(30,41,59,0.7); border:1px solid #334155; border-radius:10px; padding:16px; margin-bottom:16px;">
        <h4 style="margin-bottom:8px; font-size:14px; color:#38bdf8;">📁 Step 1: Upload Excel File (.xlsx, .xls, .csv, .tsv)</h4>
        <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
          <input type="file" id="excel-tab-file-input" accept=".csv, .xlsx, .xls, .txt, .tsv" style="display:none;" onchange="handleMainExcelFileUpload(event)">
          <button class="btn btn-accent" onclick="document.getElementById('excel-tab-file-input').click()">📂 Choose Excel / CSV File</button>
          <span id="selected-file-label" style="font-size:13px; color:var(--text-muted);">No file selected yet</span>
          <a href="/api/excel/template_xlsx" class="btn btn-outline" style="text-decoration:none; color:#34d399; border-color:#34d399; margin-left:auto;">📥 Sample Excel (.xlsx, Multi-Sheet + Auto-Schedule)</a>
        </div>

        <!-- Multi-Sheet Selection Checkbox Panel (Appears when .xlsx uploaded) -->
        <div id="multisheet-panel" style="display:none; margin-top:16px; padding:14px; background:#0b1120; border:1px solid #3b82f6; border-radius:8px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <b style="color:#60a5fa; font-size:13px;">📑 Detected Multiple Sheets in Workbook (Select sheets to import):</b>
            <div>
              <button class="btn btn-outline" style="padding:3px 8px; font-size:11px;" onclick="selectAllSheets(true)">Select All</button>
              <button class="btn btn-outline" style="padding:3px 8px; font-size:11px;" onclick="selectAllSheets(false)">Deselect All</button>
            </div>
          </div>
          <div id="multisheet-checkboxes" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:10px;"></div>
          <div style="margin-top:12px;">
            <button class="btn btn-accent" onclick="importSelectedExcelSheets()">📥 Import Selected Sheets Only</button>
          </div>
        </div>
      </div>

      <h4 style="margin-bottom:6px; font-size:13px; color:var(--text-muted);">లేదా డైరెక్ట్‌గా Google Sheets / Excel Rows ఇక్కడ పేస్ట్ చేయండి:</h4>
      <textarea id="excel-paste-text" rows="7" placeholder="Paste your Excel / Google Sheet rows here...
Example:
Warangal TS Police SI Batch	120363012345678990@g.us	POLICE	EVENING	EXAM_SPECIFIC
Hyderabad Aspirants Daily Club	120363012345678999@g.us	GENERAL	ALL_DAY	GENERAL
AP B.Tech Guntur Campus	120363012345678991@g.us	AP_BTECH	MORNING	EXAM_SPECIFIC
Telangana SSC Science Channel	@ts_science_ssc	TS_10TH	ALL_DAY	EXAM_SPECIFIC"></textarea>

      <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-top:10px;">
        <button class="btn btn-accent" onclick="importExcelSheet()">📥 Import Pasted Rows</button>
        <button class="btn btn-purple" onclick="exportExcelSheet()">📤 Export All Groups</button>
        <button class="btn btn-outline" onclick="downloadGroupsCSV()">⬇️ Download CSV</button>
        <button class="btn btn-outline" onclick="document.getElementById('excel-paste-text').value=''">Clear Box</button>
      </div>

      <div id="excel-import-log" class="log-box" style="margin-top:16px;">Importer ready. Upload .xlsx file or paste rows.</div>

      <!-- ✍️ MANUAL SETUP — Excel lekunda, form thone okka target full setup -->
      <div style="background:rgba(16,24,40,0.9); border:1px solid #fbbf24; border-radius:10px; padding:16px; margin-top:18px;">
        <h4 style="margin-bottom:4px; font-size:14px; color:#fbbf24;">✍️ Manual Setup — Excel lekunda, ikkade add cheyyandi (1 minute!)</h4>
        <p style="font-size:12px; color:var(--text-muted); margin-bottom:10px;">Okka WhatsApp group / Telegram channel ni form tho add chesi — <b>exam, timings, polls, days, subjects</b> anni okkasare set cheyyandi. Times iste auto-schedule kuda create avuthundi. (Excel import tho behavior okkate: validation + duplicate check untundi)</p>
        <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px;">
          <div><label>📱 Platform</label>
            <select id="ms-platform" onchange="msPlatformChanged()">
              <option value="wa">🟢 WhatsApp Group</option>
              <option value="tg-channel">📢 Telegram Channel</option>
              <option value="tg-group">💬 Telegram Group</option>
            </select></div>
          <div><label>🏷️ Name</label><input type="text" id="ms-name" placeholder="Warangal SI Batch 1"></div>
          <div><label id="ms-link-label">🔗 Invite Link or JID</label><input type="text" id="ms-link" placeholder="https://chat.whatsapp.com/... లేదా 1203...@g.us లేదా Channel JID: 1203...@newsletter"></div>
          <div><label>🎯 Exam</label>
            <select id="ms-exam" onchange="msExamChanged()"></select>
            <input type="text" id="ms-exam-custom" placeholder="Custom exam name (e.g. TS Police SI 2027)" style="display:none; margin-top:6px;"></div>
          <div><label id="ms-shift-label">⏰ Shift</label>
            <select id="ms-shift"><option value="ALL_DAY">ALL_DAY</option><option value="MORNING">MORNING</option><option value="EVENING">EVENING</option></select></div>
          <div><label>🗂️ Group Type</label>
            <select id="ms-type"><option value="EXAM_SPECIFIC">EXAM_SPECIFIC</option><option value="GENERAL">GENERAL</option></select></div>
          <div><label>⏱️ Daily Times (+ tho)</label><input type="text" id="ms-times" placeholder="08:00+20:30 (ఖాళీ = no schedule)"></div>
          <div><label>📊 Polls / slot</label><input type="number" id="ms-count" min="1" max="20" value="5"></div>
          <div><label>📅 Days (0 = ♾️ Always)</label><input type="number" id="ms-days" min="0" max="3650" value="0"></div>
        </div>
        <label style="margin-top:10px; display:block;">📚 Subjects (ఏదీ select చేయకపోతే = ALL) — custom subject kuda type cheyyandi:</label>
        <div id="ms-subjects" style="display:flex; gap:10px; flex-wrap:wrap; margin-top:4px; font-size:12px;"></div>
        <input type="text" id="ms-subj-custom" placeholder="Custom subjects: HISTORY+GEOGRAPHY+TELUGU (+ tho kalapandi)" style="margin-top:6px;">
        <div style="display:flex; gap:10px; margin-top:12px; flex-wrap:wrap;">
          <button class="btn btn-accent" onclick="manualAddTarget()">➕ Add Target (+ Schedule)</button>
        </div>
        <div id="ms-result" style="font-size:12px; margin-top:8px;"></div>
      </div>
    </div>
  </div>

  <!-- TAB: BULK BROADCAST & ATTACHMENTS (GROUPS & CHANNELS) -->
  <div id="tab-bulk-broadcast" class="tab-pane">

    <!-- 🧭 MISSION HOME: ఒక్క చూపులో అంతా అర్థమయ్యే setup guide -->
    <div class="panel-card" id="setup-guide-card" style="border:1px solid #10b981;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <h2 style="font-size:15px;">🧭 Setup Guide — ఏం అయింది, ఏం మిగిలింది</h2>
        <span id="sg-progress-label" style="font-size:12px; font-weight:800; color:#10b981;"></span>
      </div>
      <div style="background:#0b1220; border-radius:10px; height:10px; margin:8px 0 12px; overflow:hidden;">
        <div id="sg-progress-bar" style="height:100%; width:0%; background:linear-gradient(90deg,#10b981,#38bdf8); transition:width 0.6s;"></div>
      </div>
      <div id="sg-steps" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px;"></div>
    </div>

    <!-- 📆 TODAY'S TIMELINE: ఈరోజు ఏ టైంకి ఏం వెళ్తుంది -->
    <div class="panel-card" id="today-timeline-card" style="border:1px solid #38bdf8;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
        <h2 style="font-size:15px;">📆 ఈరోజు Timeline — Auto Sends</h2>
        <span id="tl-next-chip" style="font-size:12px; font-weight:800; color:#fbbf24;"></span>
      </div>
      <div id="tl-list" style="display:flex; flex-direction:column; gap:4px;"></div>
    </div>

    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
        <h2>🚀 Bulk Message & Live Dispatcher (WhatsApp Groups + Telegram Channels)</h2>
        <div style="display:flex; gap:8px; align-items:center;">
          <span style="background:rgba(59,130,246,0.2); color:#60a5fa; border:1px solid #3b82f6; border-radius:20px; padding:3px 12px; font-size:12px; font-weight:700;">Simultaneous Multi-Target Gateway</span>
          <button class="btn btn-purple" style="padding:5px 12px; font-size:12px;" onclick="switchTab('tab-bundles')">📦 Manage & Create Bundles</button>
        </div>
      </div>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">
        ఒకేసారి అన్ని WhatsApp గ్రూపులకు మరియు Telegram ఛానెళ్లకు అధికారిక నోటిఫికేషన్లు, మెటీరియల్స్, స్టడీ PDFలు, పోస్టర్లు లేదా ప్రైవేట్ లింక్‌లను బల్క్‌గా డిస్పాచ్ చేయండి!
      </p>

      <!-- Real-time conflict warning banner for Bulk Dispatch -->
      <div id="bulk-conflict-alert" style="display:none; background:#7f1d1d; border:1px solid #ef4444; color:#fecaca; padding:10px 14px; border-radius:8px; font-size:12px; margin-bottom:14px;">
        ⚠️ <b>Schedule / Bundle Conflict Detected:</b> <span id="bulk-conflict-msg"></span>
      </div>

      <!-- Quick Bundle Preset Loader -->
      <div style="background:#0b1329; border:1px solid #38bdf8; border-radius:8px; padding:12px; margin-bottom:16px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:14px;">⚡</span>
          <b style="color:#38bdf8; font-size:13px;">Quick-Load Custom Bundle:</b>
          <select id="bulk-bundle-selector" style="margin:0; padding:6px 10px; font-size:12px; background:#0f172a; border:1px solid #38bdf8; color:white; border-radius:6px; min-width:240px;" onchange="applySelectedBundle(this.value)">
            <option value="">-- Choose a Saved Group Bundle --</option>
          </select>
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="loadBulkTargets()">🔄 Reload Targets</button>
          <button class="btn btn-purple" style="padding:4px 10px; font-size:11px;" onclick="switchTab('tab-excel-import')">📊 Upload Groups Excel / CSV</button>
        </div>
      </div>

      <!-- ➕ QUICK ADD NEW GROUPS: paste invite links → bot auto-joins & registers -->
      <div style="background:#0b1329; border:1px solid #10b981; border-radius:10px; padding:12px; margin-bottom:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; margin-bottom:8px;">
          <h4 style="font-size:13px; color:#10b981; margin:0;">➕ Quick Add New Groups (Invite Links paste చేస్తే చాలు — bot దే auto-join అవుతుంది!)</h4>
          <span style="font-size:10px; color:var(--text-muted);">Formats: link only · Name | link · Name | link | CATEGORY</span>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start;">
          <textarea id="quick-add-links" rows="2" placeholder="https://chat.whatsapp.com/XXXXXXXX
Warangal Police SI Batch | https://chat.whatsapp.com/YYYYYYYY | POLICE" style="flex:1; min-width:250px; margin:0; font-size:12px;"></textarea>
          <button class="btn btn-accent" style="padding:10px 16px; font-size:13px; font-weight:700; white-space:nowrap;" onclick="quickAddGroups()">➕ Add & Auto-Join</button>
        </div>
        <div id="quick-add-result" style="font-size:12px; margin-top:6px;"></div>
      </div>

      <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:18px; margin-bottom:18px;">
        <!-- Left Column: Message & Attachment Composer -->
        <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:16px;">
          <h3 style="font-size:14px; color:#38bdf8; margin-bottom:10px;">✍️ 1. Message & Media Composer</h3>
          
          <label style="font-size:12px; color:var(--text-muted); display:block; margin-bottom:4px;">Broadcasting Message / Caption:</label>
          <textarea id="bulk-broadcast-msg" rows="6" placeholder="Type your broadcast message or alert here...
e.g.
📢 Mega Grand Mock Test Live Now!
హాల్ టికెట్ & పూర్తి సిలబస్ కోసం క్రింది లింక్ ఓపెన్ చేయండి.
All candidates must join today before 9:00 PM!"></textarea>

          <label style="font-size:12px; color:var(--text-muted); display:block; margin-top:10px; margin-bottom:4px;">📎 File Attachment (PDF, Images, Posters):</label>
          <div style="display:flex; gap:8px; align-items:center; margin-bottom:8px;">
            <input type="file" id="bulk-attachment-file" style="display:none;" onchange="handleBulkAttachmentSelect(event)">
            <button class="btn btn-outline" style="padding:6px 12px; font-size:12px;" onclick="document.getElementById('bulk-attachment-file').click()">📁 Choose File</button>
            <span id="bulk-file-name" style="font-size:12px; color:#a7f3d0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:220px;">No file selected</span>
            <button id="bulk-clear-file-btn" class="btn btn-outline" style="display:none; padding:3px 6px; font-size:10px; color:#ef4444;" onclick="clearBulkAttachment()">✕</button>
          </div>

          <label style="font-size:12px; color:var(--text-muted); display:block; margin-top:8px; margin-bottom:4px;">లేదా Direct Attachment / Image / Video URL:</label>
          <input type="text" id="bulk-attachment-url" placeholder="https://example.com/materials/test_schedule.pdf">

          <div style="margin-top:16px; display:flex; flex-direction:column; gap:8px;">
            <button class="btn btn-accent" style="width:100%; padding:12px; font-size:14px; font-weight:800;" onclick="sendBulkBroadcast()">🚀 Send Bulk Message to Selected Targets</button>
          </div>

          <!-- 🎯 TOP-LEVEL EXAM POLL BUILDER: subjects + count + difficulty-free smart pick -->
          <div style="margin-top:14px; background:#0b1329; border:1px solid #8b5cf6; border-radius:10px; padding:12px;">
            <h4 style="font-size:13px; color:#a78bfa; margin-bottom:8px;">🎯 Exam Poll Builder (Subject-Wise)</h4>
            <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:8px;">
              <span style="font-size:11px; color:var(--text-muted);">Polls/group:</span>
              <select id="poll-count-select" style="margin:0; padding:4px 8px; font-size:12px; width:70px;">
                <option value="3">3</option>
                <option value="5" selected>5</option>
                <option value="10">10</option>
                <option value="15">15</option>
              </select>
              <span style="font-size:11px; color:var(--text-muted);">Subjects (ఏవీ టిక్ చేయకపోతే = All):</span>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; font-size:12px; margin-bottom:10px;">
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="MATHS"> 🔢 Maths / Aptitude</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="REASONING"> 🧩 Reasoning</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="GK"> 📚 GK / History / Polity</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="CURRENT"> 🗞️ Current Affairs</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="ENGLISH"> 📖 English</label>
              <label style="cursor:pointer;"><input type="checkbox" class="poll-subj" value="SCIENCE"> 🔬 Science & Tech</label>
            </div>
            <button class="btn btn-purple" style="width:100%; padding:10px; font-size:13px; font-weight:700;" onclick="sendBulkQuizPollsToTargets()">🎯 Send Exam Polls to Selected Targets</button>
            <div style="font-size:10px; color:var(--text-muted); margin-top:6px;">💬 WhatsApp: anti-ban gap engine · 📢 Telegram: instant (official Bot API — no ban risk, no gaps)</div>
          </div>
        </div>

        <!-- Right Column: Select Targets (Channels + Groups) with search filters -->
        <div style="background:#0f172a; border:1px solid #1e293b; border-radius:10px; padding:16px; max-height:520px; display:flex; flex-direction:column;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; flex-wrap:wrap; gap:6px;">
            <h3 style="font-size:14px; color:#a7f3d0; margin:0;">🎯 2. Select Delivery Targets</h3>
            <span id="bulk-selected-count-badge" style="font-size:11px; font-weight:700; color:#38bdf8;">0 selected</span>
          </div>

          <!-- Target Filter Search Box -->
          <div style="display:flex; gap:6px; margin-bottom:8px;">
            <input type="text" id="bulk-target-search" placeholder="🔍 Search groups & channels..." style="margin:0; padding:5px 8px; font-size:12px;" onkeyup="filterBulkTargetList()">
            <select id="bulk-cat-filter" style="margin:0; padding:5px 8px; font-size:11px; width:130px;" onchange="filterBulkTargetList()">
              <option value="ALL">All Categories</option>
              <option value="POLICE">POLICE</option>
              <option value="TSPSC">TSPSC</option>
              <option value="APPSC">APPSC</option>
              <option value="SSC">SSC</option>
              <option value="TET_DSC">TET / DSC</option>
              <option value="TS_BTECH">TS B.Tech</option>
              <option value="AP_BTECH">AP B.Tech</option>
              <option value="GENERAL">GENERAL</option>
            </select>
          </div>
          
          <div style="display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap;">
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="toggleAllBulkTargets(true)">Select All</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="toggleAllBulkTargets(false)">Clear All</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="selectBulkChannelsOnly()">Channels Only</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="selectBulkWAGroupsOnly()">WhatsApp Only</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px; border-color:#10b981; color:#10b981;" onclick="selectVisibleBulkTargets(true)">✅ Select Visible</button>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px; border-color:#f59e0b; color:#f59e0b;" onclick="selectVisibleBulkTargets(false)">✖ Unselect Visible</button>
          </div>

          <div style="overflow-y:auto; flex:1; padding-right:6px;">
            <div style="font-size:12px; font-weight:700; color:#38bdf8; margin-bottom:6px; border-bottom:1px solid #1e293b; padding-bottom:4px;">
              📢 Telegram Channels (<span id="bulk-channels-count">0</span>):
            </div>
            <div id="bulk-channels-list" style="margin-bottom:14px; display:flex; flex-direction:column; gap:4px;"></div>

            <div style="font-size:12px; font-weight:700; color:#10b981; margin-bottom:6px; border-bottom:1px solid #1e293b; padding-bottom:4px;">
              💬 WhatsApp Groups (<span id="bulk-groups-count">0</span>):
            </div>
            <div id="bulk-groups-list" style="display:flex; flex-direction:column; gap:4px;"></div>
          </div>
        </div>
      </div>

      <div id="bulk-broadcast-log" class="log-box">Ready. Compose your message, choose targets, and hit Send!</div>
    </div>
  </div>

  <div id="tab-bundles" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
        <h2>📦 Channel & WhatsApp Group Bundles (Custom Saved Clusters)</h2>
        <button class="btn btn-outline" style="padding:6px 12px; font-size:12px;" onclick="switchTab('tab-bulk-broadcast')">🚀 Open Bulk Dispatcher</button>
      </div>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
        మీకు నచ్చిన WhatsApp గ్రూపులను మరియు Telegram ఛానెళ్లను కలిపి ఒకే <b>Custom Bundle (కట్ట)</b> గా పేరు పెట్టి సేవ్ చేసుకోండి. భవిష్యత్తులో ఆ పేరును ఎంచుకోగానే అందరూ ఆటోమేటిక్‌గా సెలెక్ట్ అవుతారు!
      </p>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <!-- Left: Active Bundles List -->
        <div>
          <h3 style="font-size:15px; margin-bottom:10px;">📋 Saved Bundles</h3>
          <table id="table-bundles">
            <thead>
              <tr>
                <th>Bundle Name</th>
                <th>Category</th>
                <th>Target Groups & Channels</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>

        <!-- Right: Interactive Bundle Creator with Searchable Checkbox List -->
        <div style="background:#0f172a; padding:16px; border-radius:10px; border:1px solid var(--border); display:flex; flex-direction:column;">
          <h3 style="font-size:15px; margin-bottom:10px; color:#ec4899;">➕ Create / Edit Custom Bundle</h3>
          
          <label style="font-size:12px; color:var(--text-muted);">Bundle Name / Title:</label>
          <input type="text" id="bundle-name" placeholder="e.g. Warangal All Degree & B.Tech Cluster" style="margin-bottom:8px;">

          <div style="display:flex; gap:10px; margin-bottom:8px;">
            <div style="flex:1;">
              <label style="font-size:12px; color:var(--text-muted);">Default Exam Syllabus:</label>
              <select id="bundle-category" style="margin:0;">
                <option value="GENERAL">🌐 General Exam Prep</option>
                <option value="POLICE">👮 Police (SI/Constable)</option>
                <option value="TSPSC">🏛️ TSPSC State</option>
                <option value="APPSC">🏛️ APPSC State</option>
                <option value="SSC">🏛️ Central / SSC</option>
                <option value="RAILWAY">🚆 Railway RRB</option>
                <option value="BANKING">🏦 Banking</option>
                <option value="TET_DSC">👩‍🏫 TET / DSC</option>
                <option value="TS_BTECH">TS B.Tech</option>
                <option value="AP_BTECH">AP B.Tech</option>
                <option value="TS_DEGREE">TS Degree</option>
                <option value="AP_DEGREE">AP Degree</option>
                <option value="TS_INTER">TS Intermediate</option>
                <option value="AP_INTER">AP Intermediate</option>
                <option value="TS_10TH">TS 10th Class</option>
                <option value="AP_10TH">AP 10th Class</option>
                <option value="ITI_ALL">TS & AP ITI</option>
                <option value="OPEN_UNIV">Open Universities</option>
              </select>
            </div>
          </div>

          <label style="font-size:12px; color:#38bdf8; font-weight:700; margin-top:6px; margin-bottom:4px;">
            Select WhatsApp Groups & Channels for this Bundle:
          </label>
          
          <div style="display:flex; gap:6px; margin-bottom:6px;">
            <input type="text" id="bundle-member-search" placeholder="🔍 Filter groups to add..." style="margin:0; padding:4px 8px; font-size:11px;" onkeyup="filterBundleCreatorList()">
            <button class="btn btn-outline" style="padding:3px 6px; font-size:10px;" onclick="toggleBundleCreatorItems(true)">Check All</button>
            <button class="btn btn-outline" style="padding:3px 6px; font-size:10px;" onclick="toggleBundleCreatorItems(false)">Uncheck</button>
          </div>

          <div id="bundle-creator-members" style="height:220px; overflow-y:auto; background:#070d1e; border:1px solid #1e293b; border-radius:6px; padding:8px; margin-bottom:12px; display:flex; flex-direction:column; gap:4px;">
            <div style="color:var(--text-muted); font-size:11px; text-align:center; padding:10px;">Loading groups and channels...</div>
          </div>

          <button class="btn btn-pink" style="padding:10px; font-weight:800;" onclick="saveNewBundle()">💾 Save Custom Bundle</button>
        </div>
      </div>
    </div>
  </div>

  <!-- TAB 4: TELEGRAM CHANNELS & POLL COUNTS -->
  <div id="tab-dynamic-channels" class="tab-pane">
    <div class="panel-card">
      <h2>📢 Telegram Channels & Real-Time Question Counts</h2>
      <p style="color:var(--text-muted); font-size:13px; margin-bottom:16px;">
        ప్రతి ఛానల్‌లో ఎన్ని ప్రశ్నలు సిద్ధంగా ఉన్నాయో లైవ్‌గా చూడండి. కొత్త ఛానల్ యాడ్ చేసినప్పుడు AI ఆటోమేటిక్‌గా సిలబస్ అర్థం చేసుకుని క్వశ్చన్స్ బిల్డ్ చేస్తుంది.
      </p>

      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
        <div style="background:#0f172a; padding:18px; border-radius:10px; border:1px solid var(--border);">
          <h3 style="font-size:15px; margin-bottom:12px;">➕ Register Telegram Channel <u>or Group</u></h3>

          <!-- 🔍 one-click: bot ని add చేసిన groups/channels auto-register -->
          <div style="background:#0b1329; border:1px solid #10b981; border-radius:8px; padding:10px; margin-bottom:12px;">
            <div style="font-size:12px; color:#a7f3d0; margin-bottom:6px;">💡 <b>Easy way:</b> మీ Telegram <b>group</b> లో bot ని add చేయండి (member/admin గా) → ఈ button నొక్కండి — అన్నీ ఆటోమేటిక్‌గా register అవుతాయి!</div>
            <button class="btn btn-accent" style="font-size:12px; padding:6px 14px;" onclick="detectNewTelegramChats()">🔍 Auto-Detect Bot Groups & Channels</button>
            <div id="tg-detect-result" style="font-size:12px; margin-top:6px;"></div>
          </div>

          <label>Type:</label>
          <select id="new-ch-type">
            <option value="channel">📢 Channel (broadcast)</option>
            <option value="group">💬 Group / Supergroup (bot must be member)</option>
          </select>

          <label>Channel / Group / Exam Name:</label>
          <input type="text" id="new-ch-name" placeholder="e.g. TS Police Sub Inspector 2026">

          <label>Exam Category (or Auto-Detect):</label>
          <select id="new-ch-base">
            <option value="AUTO">🤖 Auto-Detect (AP B.Tech, AP Degree, TS, ITI, Police, etc.)</option>
            <option value="TET_DSC">👩‍🏫 TS & AP TET / DSC (Teachers, SGT, School Assistant)</option>
            <option value="AP_BTECH">AP B.Tech (JNTUK, JNTUA, Engineering & Placements)</option>
            <option value="AP_DEGREE">AP Degree (AU, SVU, ANU B.Com, B.Sc, B.A)</option>
            <option value="AP_DIPLOMA">AP Diploma & POLYCET / ECET (SBTET)</option>
            <option value="AP_INTER">AP Intermediate (BIEAP MPC/BiPC & EAPCET)</option>
            <option value="AP_10TH">AP 10th Class Board (BSEAP SSC)</option>
            <option value="TS_BTECH">TS B.Tech (Engineering / Coding / CRT Placements)</option>
            <option value="TS_DEGREE">TS Degree (B.Com, B.Sc, B.A, ICET)</option>
            <option value="TS_DIPLOMA">TS Diploma & POLYCET / ECET</option>
            <option value="TS_INTER">TS Intermediate (MPC/BiPC/CEC)</option>
            <option value="TS_10TH">TS 10th Class Board (SSC)</option>
            <option value="ITI_ALL">TS & AP ITI (Electrician / Fitter / NCVT / Apprentice)</option>
            <option value="OPEN_UNIV">Open Universities (BRAOU / IGNOU / Distance Education)</option>
            <option value="POLICE">Police Exams (SI / Constable / APSP / TSSP)</option>
            <option value="SSC">SSC Exams (CGL / CHSL / MTS / GD)</option>
            <option value="RAILWAY">Railway RRB (NTPC / Group D / ALP)</option>
            <option value="BANKING">Banking (IBPS PO / SBI Clerk / RRB)</option>
            <option value="TSPSC">TSPSC / TS Districts</option>
            <option value="APPSC">APPSC / AP Districts</option>
            <option value="DEFENCE">Defence (NDA, CDS, AFCAT)</option>
            <option value="CURRENT">Current Affairs & Daily GK</option>
          </select>

          <label>Telegram Chat ID or @username (groups కి usually -100... id):</label>
          <input type="text" id="new-ch-chatid" placeholder="@MyChannel or -100123456789 (group id)">

          <button class="btn btn-accent" onclick="createNewChannel()">⚡ Register & Auto-Synthesize Polls</button>
        </div>

        <div>
          <h3 style="font-size:15px; margin-bottom:12px;">📢 Instant Telegram Poll Broadcaster</h3>
          <label>Choose Channel to Post Poll:</label>
          <select id="post-poll-channel"></select>

          <div style="display:flex; gap:10px; margin-top:8px;">
            <button class="btn btn-accent" onclick="sendChannelPoll(1)">📢 Post 1 Exam-Specific Poll</button>
            <button class="btn btn-outline" onclick="sendChannelPoll(5)">📢 Post 5 Round Polls</button>
          </div>
          <div id="tg-poll-log" class="log-box" style="margin-top:14px;">Select channel and dispatch.</div>
        </div>
      </div>

      <div style="margin-top:24px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:12px;">
          <div>
            <h3 style="margin-bottom:4px;">Active Channels & Real-Time Question Counts</h3>
            <span style="font-size:12px; color:var(--text-muted);">Select specific channels or search by exam to dispatch customized quiz rounds instantly</span>
          </div>
          <div style="display:flex; gap:8px; align-items:center;">
            <input type="text" id="ch-search-box" placeholder="🔍 Search channels..." onkeyup="filterTGChannels()" style="width:170px; margin:0; padding:6px 10px; font-size:12px;">
            <button class="btn btn-accent" style="font-size:12px; padding:6px 12px;" onclick="dispatchSelectedChannels()">🚀 Post Quiz to Selected</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="selectAllChannels(true)">Select All</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="selectAllChannels(false)">Clear</button>
            <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="loadChannels()">🔄 Refresh</button>
          </div>
        </div>
        <table id="table-channels">
          <thead>
            <tr>
              <th style="width:30px;"><input type="checkbox" id="ch-select-all" onchange="selectAllChannels(this.checked)"></th>
              <th>Channel Key</th>
              <th>Channel Title</th>
              <th>Syllabus Category</th>
              <th>Available Polls Count</th>
              <th>Chat Target</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>

      <!-- 🤖 TELEGRAM AUTO-PILOT: daily hands-free poll posting -->
      <div style="background:#0b1329; border:1px solid #a78bfa; border-radius:10px; padding:16px; margin-top:16px;">
        <h3 style="font-size:15px; margin-bottom:4px;">🤖 Telegram Auto-Pilot — రోజూ ఆటోమేటిక్ Polls (Zero Effort)</h3>
        <p style="color:var(--text-muted); font-size:12px; margin-bottom:10px;">
          పై table లో channels/groups select చేసి, times పెట్టి ON చేయండి — ప్రతి రోజు ఆ time కి ఆటోమేటిక్‌గా polls post అవుతాయి (instant, no gaps — official Bot API).
        </p>
        <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:flex-end;">
          <div>
            <label style="font-size:11px;">Daily Times (comma sep):</label>
            <input type="text" id="tg-ap-times" placeholder="08:00, 13:00, 20:30" style="width:180px; margin:0; padding:7px 10px; font-size:13px;">
          </div>
          <div>
            <label style="font-size:11px;">Polls per slot:</label>
            <select id="tg-ap-count" style="margin:0; padding:7px 10px; width:90px;">
              <option value="1">1</option><option value="3">3</option><option value="5" selected>5</option><option value="10">10</option>
            </select>
          </div>
          <button class="btn btn-accent" onclick="createTgAutopilot()">🤖 Start Auto-Pilot (Selected Targets)</button>
          <button class="btn btn-outline" style="border-color:#fbbf24; color:#fbbf24;" onclick="oneClickDailyPlan()" title="08:00 + 13:00 + 20:30 slots, all targets">🚀 1-Click Daily Plan</button>
        </div>
        <div style="margin-top:8px; font-size:12px; color:#94a3b8;">
          Subjects (optional):
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="MATHS"> ➗ Maths</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="REASONING"> 🧠 Reasoning</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="GK"> 🌍 GK</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="CURRENT"> 📰 Current</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="ENGLISH"> 🔤 English</label>
          <label style="display:inline; font-size:12px;"><input type="checkbox" class="tg-ap-subj" value="SCIENCE"> 🔬 Science</label>
          <input type="text" id="tg-ap-subj-custom" placeholder="Custom: HISTORY+GEOGRAPHY" style="width:190px; margin:0; padding:6px 8px; font-size:12px;">
        </div>
        <div id="tg-ap-result" style="font-size:12px; margin-top:8px;"></div>
        <div id="tg-ap-jobs" style="font-size:12px; margin-top:10px;"></div>
      </div>

      <!-- 🔍 QUESTION FINDER: search whole bank, preview, hand-pick & send -->
      <div style="background:#0b1329; border:1px solid #38bdf8; border-radius:10px; padding:16px; margin-top:16px;">
        <h3 style="font-size:15px; margin-bottom:4px;">🔍 Question Finder — ఏ Question అయినా వెతికి, నచ్చింది పంపండి</h3>
        <p style="color:var(--text-muted); font-size:12px; margin-bottom:10px;">
          Topic, పదం, లేదా channel పేరుతో search చేయండి (ఉదా: "blood relation", "percentage", "constitution"). నచ్చిన question పక్కన 📤 నొక్కితే — పైన select చేసిన channel కి instant గా వెళ్తుంది.
        </p>
        <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
          <input type="text" id="qf-search" placeholder="🔍 e.g. blood relation, GDP, article 21..." style="flex:1; min-width:220px; margin:0; padding:8px 12px; font-size:13px;" onkeyup="qfDebounced()">
          <span style="font-size:11px; color:#94a3b8;">Send target: <b style="color:#38bdf8;">పైన "Choose Channel" select</b></span>
        </div>
        <div id="qf-results" style="margin-top:10px; max-height:300px; overflow-y:auto; font-size:12px;"></div>
      </div>
    </div>
  </div>

  <!-- TAB 5: FAST ACTIONS & DISTRICT WAR -->
  <div id="tab-control" class="tab-pane">
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">
      <div class="panel-card">
        <h2>⚔️ District War Instant Controller</h2>
        <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
          Lobby status, countdown and manual launch trigger for all TS & AP districts.
        </p>
        <div style="display:flex; gap:10px; margin-bottom:16px;">
          <button class="btn btn-accent" onclick="triggerWar('now', 5)">⚔️ Launch War Now (5 min Lobby)</button>
          <button class="btn btn-outline" onclick="triggerWar('status')">🔍 Check Status</button>
        </div>
        <div id="war-result" class="log-box">War controller ready.</div>
      </div>

      <div class="panel-card">
        <h2>📊 Google Sheet Sync & CRM</h2>
        <p style="color:var(--text-muted); font-size:13px; margin-bottom:14px;">
          Push all registered members, colleges, test results and daily analytics directly to Google Sheet.
        </p>
        <div style="display:flex; gap:10px; margin-bottom:16px;">
          <button class="btn" onclick="syncSheet('sync')">📤 Push All Members to Sheet</button>
          <button class="btn btn-outline" onclick="syncSheet('flush')">📦 Flush Queue</button>
        </div>
        <div id="sheet-result" class="log-box">Google Sheet CRM ready.</div>
      </div>
    </div>
  </div>

  <!-- TAB 6: SQUADS & ARENA -->
  <div id="tab-squads" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px;">
        <div>
          <h2>👥 Registered Squads, War Battle Room & Instant Join QR</h2>
          <p style="color:var(--text-muted); font-size:13px; margin-top:2px;">
            Generate new Squads with dynamic Telegram one-tap Join Links & scannable QR Codes directly from the Dashboard.
          </p>
        </div>
        <button class="btn btn-outline" onclick="loadSquads()">🔄 Refresh Squads</button>
      </div>

      <!-- Quick Create & Quick Join Bar -->
      <div style="display:grid; grid-template-columns: 1.5fr 1fr; gap:16px; margin-bottom:18px;">
        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:16px;">
          <h3 style="font-size:14px; margin-bottom:10px; color:#38bdf8;">➕ Quick Create New Squad</h3>
          <div style="display:flex; gap:10px; flex-wrap:wrap;">
            <input type="text" id="new-squad-name" placeholder="Squad Name (e.g. Warangal Tigers or JNTUK CSE Warriors)" style="flex:2; min-width:180px; margin:0;">
            <input type="text" id="new-squad-leader" placeholder="Leader Name / Telegram ID (e.g. Charan or 999123)" style="flex:1.2; min-width:150px; margin:0;">
            <button class="btn btn-accent" style="white-space:nowrap;" onclick="createDashboardSquad()">🚀 Create Squad & Generate QR</button>
          </div>
        </div>

        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:16px;">
          <h3 style="font-size:14px; margin-bottom:10px; color:#10b981;">🤝 Quick Add Student to Squad</h3>
          <div style="display:flex; gap:8px;">
            <input type="text" id="join-squad-code" placeholder="Squad Code (e.g. DJLC)" style="width:120px; margin:0; text-transform:uppercase;">
            <input type="text" id="join-squad-uid" placeholder="Student Mobile / TG ID" style="flex:1; margin:0;">
            <button class="btn btn-accent" style="white-space:nowrap;" onclick="addStudentToSquad()">➕ Join Member</button>
          </div>
          <div id="join-squad-log" style="font-size:11px; margin-top:6px; font-weight:600;"></div>
        </div>
      </div>

      <!-- Active Squads Table with Interactive Modal / QR Popup -->
      <table id="table-squads">
        <thead>
          <tr>
            <th>Squad Code</th>
            <th>Squad Name</th>
            <th>Leader</th>
            <th>Members Count</th>
            <th>Active Members</th>
            <th>One-Tap Join Link & Interactive Scannable QR</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>

      <!-- Dynamic Squad Modal Card -->
      <div id="squad-active-modal" style="display:none; margin-top:16px; background:#070d1e; border:1px solid #38bdf8; border-radius:10px; padding:18px;"></div>
    </div>
  </div>

  <!-- TAB 7: MEMBERS DIRECTORY -->
  <div id="tab-members" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; margin-bottom:14px;">
        <div>
          <h2>📋 Registered Student Members & Instant Registration</h2>
          <p style="color:var(--text-muted); font-size:13px; margin-top:2px;">All registered aspirants with accurate points, streaks, district and exam target.</p>
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn btn-outline" onclick="loadMembers()">🔄 Refresh Directory</button>
        </div>
      </div>

      <!-- Quick Add / Register Student Form -->
      <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:14px; margin-bottom:16px;">
        <h3 style="font-size:14px; margin-bottom:10px; color:#38bdf8;">➕ Quick Register New Student & Award Initial Points</h3>
        <div style="display:flex; gap:10px; flex-wrap:wrap;">
          <input type="text" id="reg-student-uid" placeholder="Telegram ID / Mobile (e.g. 9848012345)" style="flex:1; min-width:160px; margin:0;">
          <input type="text" id="reg-student-name" placeholder="Student Full Name (e.g. Charan Reddy)" style="flex:1.5; min-width:180px; margin:0;">
          <select id="reg-student-dist" style="flex:1; min-width:140px; margin:0;">
            <option value="Warangal">Warangal</option>
            <option value="Hyderabad">Hyderabad</option>
            <option value="Karimnagar">Karimnagar</option>
            <option value="Guntur">Guntur</option>
            <option value="Visakhapatnam">Visakhapatnam</option>
            <option value="Vijayawada">Vijayawada</option>
            <option value="Khammam">Khammam</option>
            <option value="Nalgonda">Nalgonda</option>
            <option value="Tirupati">Tirupati</option>
          </select>
          <select id="reg-student-exam" style="flex:1; min-width:130px; margin:0;">
            <option value="POLICE">POLICE SI/PC</option>
            <option value="TET_DSC">TET / DSC</option>
            <option value="TSPSC">TSPSC Group 1-4</option>
            <option value="APPSC">APPSC Group 1-4</option>
            <option value="SSC">SSC / Railway</option>
            <option value="TS_BTECH">B.Tech / Engineering</option>
          </select>
          <input type="number" id="reg-student-pts" placeholder="Bonus Points (e.g. 50)" value="50" style="width:100px; margin:0;">
          <button class="btn btn-accent" style="white-space:nowrap;" onclick="quickRegisterStudent()">✅ Register Student</button>
        </div>
        <div id="reg-student-log" style="font-size:12px; margin-top:8px; font-weight:600;"></div>
      </div>

      <table id="table-members">
        <thead>
          <tr>
            <th>TG ID</th>
            <th>Name</th>
            <th>District</th>
            <th>Target Exam</th>
            <th>Points</th>
            <th>Streak</th>
            <th>College</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </div>

  <!-- TAB: 📊 BROADCAST HISTORY & ANALYTICS -->
  <div id="tab-growth" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <h2>📈 Growth & Revenue — Business Pulse</h2>
        <button class="btn btn-outline" style="padding:4px 12px; font-size:11px;" onclick="loadPulse()">🔄 Refresh</button>
      </div>
      <p style="color:var(--text-muted); font-size:12px;">Real member data nunchi funnel, referral engine, partner economy — planner matram meeru set chese what-if (price × conversion).</p>
      <div class="grid-stats" id="pulse-cards"></div>
      <h3 style="font-size:13px; margin-top:16px;">🔻 Funnel</h3>
      <div id="pulse-funnel" style="font-size:12px;"></div>
      <h3 style="font-size:13px; margin-top:16px;">🏆 Top Referrers (📣 /invite loop)</h3>
      <div id="pulse-referrers" style="font-size:12px;"></div>
      <h3 style="font-size:13px; margin-top:16px;">🏪 Partner Economy (points → local offers)</h3>
      <div id="pulse-economy" style="font-size:12px;"></div>
      <h3 style="font-size:13px; margin-top:16px;">💰 Monetization Planner <span style="color:var(--text-muted); font-weight:normal;">(what-if — real ga charge chese mundu mee assumptions)</span></h3>
      <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:end; font-size:12px;">
        <label>Plan name<br><input id="pulse-plan-name" style="width:150px;"></label>
        <label>Price ₹/month<br><input id="pulse-price" type="number" min="0" max="100000" style="width:110px;" oninput="pulseRecompute()"></label>
        <label>Conversion %<br><input id="pulse-conv" type="number" min="0" max="100" step="0.5" style="width:90px;" oninput="pulseRecompute()"></label>
        <button class="btn btn-accent" style="padding:6px 14px; font-size:12px;" onclick="savePulseSettings()">💾 Save assumptions</button>
      </div>
      <div id="pulse-proj" style="font-size:13px; margin-top:10px;"></div>
    </div>
  </div>

  <div id="tab-proops" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
        <h2>🏢 Pro Ops — System Health, Metrics, Flags, Audit</h2>
        <span style="font-size:11px; color:var(--text-muted);">auto-refresh 30s · <button class="btn btn-outline" style="padding:3px 10px; font-size:11px;" onclick="loadProOps()">🔄 Refresh</button></span>
      </div>
      <div id="proops-health" style="font-size:12px; margin-top:10px;">Loading...</div>
      <h3 style="font-size:13px; margin-top:16px;">📊 Live Metrics <span style="color:var(--text-muted); font-weight:normal;">(real events — dry runs count avvavu)</span></h3>
      <div class="grid-stats" id="proops-metrics"></div>
      <div style="font-size:12px; margin-top:8px;">🕐 Last 24h — student answers (hourly)</div>
      <div id="proops-chart" style="display:flex; align-items:end; gap:2px; height:74px; margin-top:6px; background:rgba(255,255,255,0.03); border-radius:8px; padding:8px;"></div>
      <h3 style="font-size:13px; margin-top:16px;">🚦 Feature Flags <span style="color:var(--text-muted); font-weight:normal;">(kill switches — restart akkarledu, ventane apply avuthundi)</span></h3>
      <div id="proops-flags" style="font-size:12px;"></div>
      <h3 style="font-size:13px; margin-top:16px;">🧾 Audit Trail <span style="color:var(--text-muted); font-weight:normal;">(evaru, eppudu, em chesaru)</span></h3>
      <div id="proops-audit" style="font-size:12px;"></div>
    </div>
  </div>

  <div id="tab-conductor" class="tab-pane">
    <div class="panel-card">
      <h2>🎓 Exam Conductor — oka screen lo exam schedule cheyyandi, migatha motham automatic</h2>
      <p style="color:var(--text-muted); font-size:12px;">Time ki bot automatic ga start chesthundi (Grand Test / District War / Campus Exam). Bot server lo run avuthunte matrame scheduled launch jaruguthundi — ippude kavali ante Launch Now undi.</p>
      <div id="conductor-daily" style="font-size:12px; margin:10px 0; padding:8px 10px; background:rgba(56,189,248,0.08); border-radius:8px;">📌 Daily fixed polls status loading...</div>
      <div id="conductor-advisor" style="font-size:12px; margin:10px 0; padding:8px 10px; background:rgba(167,139,250,0.08); border-radius:8px;">🧠 Smart Slot Advisor loading...</div>
      <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; font-size:12px;">
        <label>Exam peru (title)<br><input id="cd-title" placeholder="Sunday Grand Test — SSC" style="width:100%;"></label>
        <label>Type<br><select id="cd-kind" style="width:100%;" onchange="cdKindHint()">
          <option value="grand">📝 Grand Test (channel mock)</option>
          <option value="war">⚔️ District War</option>
          <option value="campus">🏫 Campus Exam (join code)</option></select></label>
        <label>Channel (Grand ki)<br><select id="cd-channel" style="width:100%;"></select></label>
        <label>Date + Time<br><input id="cd-when" type="datetime-local" style="width:100%;"></label>
        <label>Duration (minutes)<br><input id="cd-duration" type="number" value="90" min="5" max="600" style="width:100%;"></label>
        <label>Questions (Grand/Campus)<br><input id="cd-nq" type="number" value="25" min="0" max="200" style="width:100%;"></label>
        <label>War lobby (minutes)<br><input id="cd-lobby" type="number" value="5" min="1" max="60" style="width:100%;"></label>
        <label>Campus / College peru<br><input id="cd-campus" placeholder="ABC Degree College" style="width:100%;"></label>
        <label>District<br><input id="cd-district" placeholder="Warangal" style="width:100%;"></label>
      </div>
      <div id="cd-hint" style="font-size:12px; color:var(--text-muted); margin-top:8px;"></div>
      <div style="margin-top:12px; display:flex; gap:10px; flex-wrap:wrap;">
        <button class="btn btn-accent" style="padding:8px 18px; font-size:13px;" onclick="createConductorEvent()">📅 Schedule Exam</button>
        <button class="btn btn-outline" style="padding:8px 14px; font-size:12px;" onclick="loadConductor()">🔄 Refresh</button>
      </div>
      <h3 style="font-size:13px; margin-top:18px;">🗓️ Mee Exams</h3>
      <div id="conductor-events" style="font-size:12px;">Loading...</div>
    </div>
  </div>

  <div id="tab-history" class="tab-pane">
    <div class="panel-card">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div>
          <h2>📊 Broadcast History & Analytics</h2>
          <p style="color:var(--text-muted); font-size:13px;">ప్రతి poll dispatch (Telegram instant / WhatsApp anti-ban / Auto-Pilot) ఇక్కడ record అవుతుంది.</p>
        </div>
        <div style="display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="downloadBackup()">💾 Full Backup (.zip)</button>
          <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="exportHistoryCSV()">📥 Export CSV</button>
          <button class="btn btn-outline" style="font-size:12px; padding:6px 12px;" onclick="loadHistory()">🔄 Refresh</button>
        </div>
      </div>

      <!-- 🩺 MISSION CONTROL: whole system health at a glance -->
      <div style="background:#0b1329; border:1px solid #38bdf8; border-radius:10px; padding:14px; margin-top:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <h3 style="font-size:14px;">🩺 Mission Control — System Health</h3>
          <span id="health-uptime" style="font-size:11px; color:#64748b;"></span>
        </div>
        <div id="health-badges" style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; font-size:12px;"></div>
        <div id="health-bank" style="margin-top:10px; font-size:12px;"></div>
      </div>

      <!-- 🧠 ITEM INTELLIGENCE OPS -->
      <div style="background:#0b1329; border:1px solid #f472b6; border-radius:10px; padding:14px; margin-top:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <h3 style="font-size:14px; margin:0;">🧠 Item Intelligence — Question Quality (Real Answers)</h3>
          <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="loadItemIntel()">🔄 Refresh</button>
        </div>
        <div id="brain-overview" style="font-size:12.5px; margin-bottom:8px; padding:8px 10px; background:rgba(56,189,248,0.07); border-radius:8px;"></div>
        <div id="item-intel-body" style="font-size:12px; margin-top:9px; color:var(--text-muted);">Loading...</div>
      </div>

      <div class="grid-stats" style="margin-top:14px;">
        <div class="stat-card">
          <div class="label">Today's Polls Sent</div>
          <div class="val" id="hist-today" style="color:#38bdf8;">...</div>
          <div class="desc"><span id="hist-today-ev">...</span> dispatch events</div>
        </div>
        <div class="stat-card">
          <div class="label">Last 7 Days Polls</div>
          <div class="val" id="hist-week" style="color:#34d399;">...</div>
          <div class="desc"><span id="hist-week-ev">...</span> dispatch events</div>
        </div>
        <div class="stat-card">
          <div class="label">📢 Telegram vs 💚 WhatsApp (7d)</div>
          <div class="val" id="hist-split" style="color:#a78bfa; font-size:20px;">...</div>
          <div class="desc">polls by platform</div>
        </div>
        <div class="stat-card">
          <div class="label">🏆 Top Target (7d)</div>
          <div class="val" id="hist-top" style="color:#fbbf24; font-size:16px;">...</div>
          <div class="desc">most polls received</div>
        </div>
      </div>

      <div style="display:grid; grid-template-columns: 2fr 1fr; gap:16px; margin-top:16px;" class="hist-grid">
        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:14px;">
          <h3 style="font-size:14px; margin-bottom:8px;">🕒 Recent Dispatches</h3>
          <div id="hist-table-wrap" style="max-height:420px; overflow-y:auto;">
            <table id="table-history">
              <thead><tr><th>Time</th><th>Platform</th><th>Target</th><th>Polls</th><th>Subjects</th><th>Mode</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </div>
        <div style="background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:14px;">
          <h3 style="font-size:14px; margin-bottom:8px;">🏆 Top Targets (7 days)</h3>
          <div id="hist-top-list" style="font-size:12px;"></div>
        </div>
      </div>
    </div>
  </div>

  <script>
    async function loadPlanner() {
      const box = document.getElementById('planner-box'); if (!box) return;
      box.innerHTML = '<div style="color:var(--text-muted); font-size:12px;">✨ Plan tayaravthundi… (students active hours + weak topics chusthunnanu)</div>';
      try {
        const r = await fetch('/api/planner/today'); const d = await r.json();
        window._plannerItems = d.items || [];
        box.innerHTML = (d.items || []).map((it, i) => `<label style="display:flex; gap:8px; align-items:flex-start; background:#050811; border:1px solid var(--border); border-radius:9px; padding:9px 11px; margin:6px 0; cursor:pointer;">
          <input type="checkbox" class="planner-chk" data-i="${i}" checked style="width:auto; margin:3px 0 0;">
          <span style="font-size:12px;"><b style="color:#facc15;">${it.time}</b> · ${it.mode === 'wa' ? '📱' : '✈️'} <b>${it.name}</b> · ${it.count} polls<br><span style="color:var(--text-muted);">${it.reason}</span></span></label>`).join('') + `<div style="font-size:11px; color:var(--text-muted); margin-top:6px;">${d.note || ''}</div>`;
      } catch (e) { box.innerHTML = '<div style="color:#f87171; font-size:12px;">❌ Plan load avvaledu</div>'; }
    }

    async function applyPlanner() {
      const items = [...document.querySelectorAll('.planner-chk:checked')].map(c => window._plannerItems[+c.dataset.i]).filter(Boolean);
      if (!items.length) return alert('Kanisam okka slot select cheyyandi!');
      if (!confirm(`✨ ${items.length} daily jobs create cheyyala? Prathi roju ee times lo automatic ga polls velthayi.`)) return;
      const box = document.getElementById('planner-box');
      try {
        const r = await fetch('/api/planner/apply', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({items})});
        const d = await r.json();
        box.innerHTML = `<div style="color:#10b981; font-size:13px;">✅ ${d.message || 'Plan applied!'} Jobs ni 📢 Telegram Channels tab lo chudachu / off cheyyachu.</div>`;
      } catch (e) { alert('❌ ' + e); }
    }

    // ---------- ⌨️ Command Palette ----------
    let cmdkSel = 0, cmdkList = [], cmdkEventsCache = null, cmdkMembersCache = null;
    function cmdkBaseItems() {
      const items = [];
      document.querySelectorAll('.tabs .tab-btn').forEach(b => {
        const m = (b.getAttribute('onclick') || '').match(/switchTab\('([^']+)'\)/);
        if (m) items.push({label: b.textContent.trim(), hint: 'Tab', run: () => switchTab(m[1])});
      });
      items.push({label: '🏫➕ New College Exam (fresh form)', hint: 'Action', run: () => { switchTab('tab-campus'); setTimeout(() => document.getElementById('campus-college-name')?.focus(), 60); }});
      items.push({label: '✨ Smart Day Planner chudu', hint: 'Action', run: () => { switchTab('tab-setup-wizard'); loadPlanner(); }});
      items.push({label: '🔄 Setup status refresh chey', hint: 'Action', run: () => { switchTab('tab-setup-wizard'); loadSetupWizard(); }});
      return items;
    }
    async function cmdkDynamic() {
      const out = [];
      try {
        if (!cmdkEventsCache) { const r = await fetch('/api/campus/list'); const d = await r.json(); cmdkEventsCache = d.events || []; }
        cmdkEventsCache.slice(0, 30).forEach(e => {
          out.push({label: `📊 Marks — ${e.name} (${e.code})`, hint: `${e.players_count} students · ${e.state}`, run: () => { switchTab('tab-campus'); viewCampusReport(e.code); }});
          if (e.state === 'question' || e.state === 'gap') out.push({label: `🔴 Live Control — ${e.name}`, hint: 'Exam LIVE', run: () => { switchTab('tab-campus'); watchCampusLive(e.code); }});
        });
      } catch (e) {}
      try {
        if (!cmdkMembersCache) { const r = await fetch('/api/members'); const d = await r.json(); cmdkMembersCache = d.members || []; }
        cmdkMembersCache.slice(0, 200).forEach(m => out.push({label: `👤 ${m.name} — ${m.points} pts`, hint: ((m.district || '') + ' ' + (m.college || '')).trim() || 'Member', run: () => switchTab('tab-members')}));
      } catch (e) {}
      return out;
    }
    async function openCmdk() {
      const ov = document.getElementById('cmdk-overlay'); if (!ov) return;
      ov.style.display = 'block';
      const inp = document.getElementById('cmdk-input'); inp.value = '';
      window._cmdkAll = [...cmdkBaseItems(), ...(await cmdkDynamic())];
      cmdkSel = 0; renderCmdk('');
      setTimeout(() => inp.focus(), 30);
    }
    function closeCmdk() { const ov = document.getElementById('cmdk-overlay'); if (ov) ov.style.display = 'none'; }
    function renderCmdk(q) {
      q = (q || '').toLowerCase();
      cmdkList = (window._cmdkAll || []).filter(it => !q || it.label.toLowerCase().includes(q) || (it.hint || '').toLowerCase().includes(q)).slice(0, 12);
      if (cmdkSel >= cmdkList.length) cmdkSel = 0;
      document.getElementById('cmdk-list').innerHTML = cmdkList.map((it, i) => `<div onclick="cmdkRun(${i})" style="padding:9px 12px; border-radius:9px; cursor:pointer; display:flex; justify-content:space-between; gap:10px; ${i === cmdkSel ? 'background:linear-gradient(90deg,#2563eb,#0ea5e9); color:#fff;' : ''}"><span style="font-size:13px; font-weight:600;">${it.label}</span><span style="font-size:10.5px; opacity:.75;">${it.hint || ''}</span></div>`).join('') || '<div style="padding:12px; font-size:12px; color:var(--text-muted);">Emi dorakaledu — verega type cheyyandi.</div>';
    }
    function cmdkRun(i) { const it = cmdkList[i]; closeCmdk(); if (it) it.run(); }
    document.addEventListener('keydown', (e) => {
      const ov = document.getElementById('cmdk-overlay');
      const open = ov && ov.style.display !== 'none';
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); open ? closeCmdk() : openCmdk(); return; }
      if (!open) return;
      if (e.key === 'Escape') closeCmdk();
      else if (e.key === 'ArrowDown') { e.preventDefault(); cmdkSel = Math.min(cmdkSel + 1, cmdkList.length - 1); renderCmdk(document.getElementById('cmdk-input').value); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); cmdkSel = Math.max(cmdkSel - 1, 0); renderCmdk(document.getElementById('cmdk-input').value); }
      else if (e.key === 'Enter') { e.preventDefault(); cmdkRun(cmdkSel); }
    });

    async function loadSafetyStack() {
      const box = document.getElementById('wa-safety-stack'); if (!box) return;
      try {
        const r = await fetch('/api/whatsapp/safety'); const d = await r.json();
        box.innerHTML = '<div style="font-weight:800; color:#e2e8f0; margin-bottom:6px;">🛡️ WhatsApp Safety Stack' + (d.quiet ? ' <span style="color:#facc15;">· 🌙 QUIET NOW (sends defer)</span>' : '') + (d.running ? ' <span style="color:#f87171;">· 🔴 BROADCASTING</span>' : '') + '</div>' +
          (d.layers || []).map(l => `<div style="display:flex; gap:8px; padding:5px 9px; background:#050811; border:1px solid var(--border); border-radius:8px; margin:4px 0;"><span>${l.icon}</span><span style="flex:1;"><b style="color:#e2e8f0;">${l.name}</b><br><span style="color:var(--text-muted); font-size:11px;">${l.detail}</span></span><span>${l.ok ? '✅' : '⏸️'}</span></div>`).join('') +
          `<div style="display:flex; gap:6px; margin-top:8px; flex-wrap:wrap;"><button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="runPreflight()">🔍 Preflight Check</button><button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="runWaPreview()">👀 Broadcast Preview</button><button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="loadSafetyStack()">🔄 Refresh</button><button class="btn" style="padding:4px 10px; font-size:11px; background:#dc2626;" onclick="emergencyStopWA()">🚨 Emergency Stop</button></div>`;
      } catch (e) { box.innerHTML = '<span style="color:#f87171;">Safety status load avvaledu</span>'; }
    }

    async function runPreflight() {
      const box = document.getElementById('wa-safety-detail'); if (!box) return;
      box.innerHTML = '🔍 Checking…';
      try {
        const r = await fetch('/api/whatsapp/preflight'); const d = await r.json(); const pf = d.preflight || {};
        box.innerHTML = `<b style="color:${pf.ok ? '#10b981' : '#f87171'};">${pf.ok ? '✅ Preflight PASSED — broadcast safe ga start cheyyachu' : '❌ Blockers: ' + (pf.blockers || []).join(', ')}</b>` + (pf.checks || []).map(c => `<div style="padding:3px 0; color:var(--text-muted);">${c.ok ? '✅' : '❌'} ${c.name} — ${c.detail}</div>`).join('');
      } catch (e) { box.innerHTML = '❌ ' + e; }
    }

    async function emergencyStopWA() {
      if (!confirm('🚨 Run avthunna WhatsApp broadcast ni IPPude aapeyyala? (mid-send kuda aaguthundi)')) return;
      try {
        const r = await fetch('/api/whatsapp/stop_pipeline', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
        const d = await r.json();
        alert(d.message || 'Stop signal sent');
        loadSafetyStack();
      } catch (e) { alert('❌ ' + e); }
    }

    function filterNav(q) {
      q = (q || '').toLowerCase().trim();
      document.querySelectorAll('.tabs .tab-btn').forEach(b => {
        b.style.display = (!q || b.textContent.toLowerCase().includes(q)) ? '' : 'none';
      });
      document.querySelectorAll('.tabs .nav-group').forEach(g => {
        let n = g.nextElementSibling, any = false;
        while (n && !n.classList.contains('nav-group')) {
          if (n.classList.contains('tab-btn') && n.style.display !== 'none') any = true;
          n = n.nextElementSibling;
        }
        g.style.display = any ? '' : 'none';
      });
    }
    document.addEventListener('DOMContentLoaded', () => { try { loadSetupWizard(); } catch (e) {} });

    function switchTab(id, btnElem) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

      if (btnElem) {
        btnElem.classList.add('active');
      } else {
        const matchingBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => {
          const onclickAttr = b.getAttribute('onclick') || '';
          return onclickAttr.includes("'" + id + "'") || onclickAttr.includes('"' + id + '"');
        });
        if (matchingBtn) matchingBtn.classList.add('active');
      }

      const targetPane = document.getElementById(id);
      if (targetPane) targetPane.classList.add('active');

      if (id === 'tab-wa-dispatch') { loadWAGroups(); loadSafetyStack(); }
      if (id === 'tab-campus') loadCampusEvents();
      if (id === 'tab-dynamic-channels') { loadChannels(); loadTgAutopilotJobs(); }
      if (id === 'tab-history') { loadHistory(); loadHealth(); loadItemIntel(); }
      if (id === 'tab-growth') loadPulse();
      if (id === 'tab-proops') loadProOps();
      if (id === 'tab-conductor') loadConductor();
      if (id === 'tab-excel-import') loadSetupOptions();
      if (id === 'tab-setup-wizard') loadSetupWizard();
      if (id === 'tab-bundles') loadBundles();
      if (id === 'tab-bulk-broadcast') { loadBulkTargets(); renderMissionHome(); }
      if (id === 'tab-squads') loadSquads();
      if (id === 'tab-members') loadMembers();
    }

    async function fetchStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('stat-polls-count').innerText = (data.total_questions || '0') + ' Polls';
        document.getElementById('stat-wa-count').innerText = data.wa_groups_count || '0';
        document.getElementById('stat-tg-count').innerText = data.channels_count || '0';
        document.getElementById('stat-bundle-count').innerText = data.bundles_count || '0';
        document.getElementById('stat-points').innerText = data.total_points.toLocaleString();
      } catch (e) {
        console.error(e);
      }
    }

    async function pollPipelineStatus() {
      try {
        const res = await fetch('/api/whatsapp/pipeline_status');
        const d = await res.json();
        const statText = document.getElementById('pipeline-status-text');
        const progText = document.getElementById('pipeline-progress-text');
        const bar = document.getElementById('pipeline-progress-bar');
        const logBox = document.getElementById('wa-log-box');
        const paceText = document.getElementById('pipeline-pacing-text');
        if (paceText && d.pacing) {
          const modeIcon = {HEALTHY: '🟢', CAUTIOUS: '⚠️', CRAWL: '🚨'}[d.pacing.mode] || '🧠';
          paceText.innerHTML = '🧠 <b>Adaptive Anti-Ban:</b> ×' + d.pacing.multiplier +
            ' · ' + modeIcon + ' ' + d.pacing.mode +
            ' · fatigue ×' + d.pacing.fatigue +
            ' · fails ' + d.pacing.consecutive_fails +
            (d.pacing.crawl_until ? ' · 🚨 crawl active' : '');
        }

        if (d.running) {
          statText.innerHTML = '🟢 <b>RUNNING:</b> ' + (d.current_group ? ('Posting in ' + d.current_group) : 'Rotating pairs...');
          const pct = d.total > 0 ? Math.round((d.progress / d.total) * 100) : 0;
          bar.style.width = pct + '%';
          progText.innerText = d.progress + ' / ' + d.total + ' Groups (' + pct + '%)';
        } else {
          statText.innerText = 'Status: Idle';
        }
        if (d.logs && d.logs.length > 0) {
          logBox.innerText = d.logs.join('\\n');
          logBox.scrollTop = logBox.scrollHeight;
        }
      } catch (e) {
        console.error(e);
      }
    }

    function setPlannerCategory(category, button) { const select=document.getElementById('wa-target-category'); if(select) select.value=category; document.querySelectorAll('.exam-pill').forEach(x=>x.classList.remove('active')); if(button) button.classList.add('active'); const table=document.getElementById('table-wa-groups'); if(table) table.scrollIntoView({behavior:'smooth',block:'center'}); }
    function updatePlannerSelectionCount(){ const n=document.querySelectorAll('#table-wa-groups input[type=checkbox]:checked').length; const el=document.getElementById('planner-selected-count'); if(el) el.textContent=n+' group'+(n===1?'':'s')+' selected'; }

    async function loadMemberQueue(){ try { const d=await (await fetch('/api/member_queue/status')).json(); ['ready','done','pending','failed'].forEach(k=>{const e=document.getElementById('mq-'+k); if(e)e.textContent=d[k==='done'?'completed':k]||0;}); } catch(e){} }
    async function importMemberQueue(ev){ const f=ev.target.files[0]; if(!f)return; const text=await f.text(); const r=await fetch('/api/member_queue/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,default_consent:'PENDING'})}); const d=await r.json(); document.getElementById('mq-log').textContent=d.ok?'Imported '+d.added+' records. Only OPTED_IN records can enter the invite queue.':'Import failed: '+d.error; loadMemberQueue(); }
    async function saveMemberQueueSettings(){ const alerts=(document.getElementById('mq-alerts').value||'').split(',').map(x=>x.trim()).filter(Boolean); const limit=Math.min(20,Math.max(1,Number(document.getElementById('mq-limit').value)||20)); const r=await fetch('/api/member_queue/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alerts,batch_limit:limit})}); document.getElementById('mq-log').textContent='Queue settings saved. Daily limit: '+limit; loadMemberQueue(); }
    async function loadWASession() {
      try {
        const res = await fetch('/api/whatsapp/session');
        const s = await res.json();
        const badge = document.getElementById('wa-session-status-badge');
        const desc = document.getElementById('wa-session-desc');
        const nameEl = document.getElementById('wa-device-name');
        const phoneEl = document.getElementById('wa-device-phone');
        const countEl = document.getElementById('wa-dialogs-count');

        if (nameEl) nameEl.innerText = s.device_name || 'Dispatch Node #1';
        if (phoneEl) phoneEl.innerText = s.phone || '';
        if (countEl) countEl.innerText = (s.scanned_dialogs_count || s.bridge_groups_count || 0) + ' Groups';

        // 🪪 Big neat "which number is logged in" badge
        const numBadge = document.getElementById('wa-login-number-badge');
        const sinceEl = document.getElementById('wa-connected-since');
        if (numBadge) {
          if (s.status === 'connected' && s.phone) {
            numBadge.innerText = '✅ ' + s.phone;
            numBadge.style.color = '#10b981';
            numBadge.style.border = '2px solid #10b981';
            numBadge.style.background = 'rgba(16,185,129,0.08)';
            numBadge.title = 'This WhatsApp number is linked & sending';
            if (sinceEl) sinceEl.innerText = s.connected_at ? ('· 🔗 Linked since ' + s.connected_at) : '';
          } else if (s.status === 'qr_ready' || s.status === 'code_ready' || s.status === 'connecting') {
            numBadge.innerText = '⏳ LINKING...';
            numBadge.style.color = '#f59e0b';
            numBadge.style.border = '2px dashed #f59e0b';
            numBadge.style.background = 'rgba(245,158,11,0.08)';
            if (sinceEl) sinceEl.innerText = '';
          } else {
            numBadge.innerText = '📵 NOT LINKED';
            numBadge.style.color = '#64748b';
            numBadge.style.border = '2px dashed #334155';
            numBadge.style.background = '#0b1329';
            if (sinceEl) sinceEl.innerText = '';
          }
        }

        if (badge) {
          if (s.status === 'connected') {
            badge.style.background = '#10b981';
            badge.style.color = '#050811';
            badge.innerText = '● REAL WHATSAPP CONNECTED';
          } else if (s.status === 'qr_ready') {
            badge.style.background = '#f59e0b';
            badge.style.color = '#050811';
            badge.innerText = '📷 QR CODE READY — SCAN NOW';
          } else if (s.status === 'code_ready') {
            badge.style.background = '#38bdf8';
            badge.style.color = '#050811';
            badge.innerText = '🔢 PAIRING CODE: ' + s.pairing_code;
          } else if (s.status === 'connecting') {
            badge.style.background = '#6366f1';
            badge.style.color = '#fff';
            badge.innerText = '⏳ CONNECTING TO WHATSAPP...';
          } else if (s.status === 'bridge_offline') {
            badge.style.background = '#ef4444';
            badge.style.color = '#fff';
            badge.innerText = '⚠️ BRIDGE OFFLINE (run: node gateway/wa_bridge.js)';
          } else {
            badge.style.background = '#ef4444';
            badge.style.color = '#fff';
            badge.innerText = '○ NOT LINKED — SCAN QR TO LOGIN';
          }
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function syncWADialogs() {
      const box = document.getElementById('wa-login-dialog');
      box.style.display = 'block';
      box.innerHTML = '<div style="color:#38bdf8;">🔄 Scanning active WhatsApp account for all joined groups & channels...</div>';
      try {
        const res = await fetch('/api/whatsapp/sync_dialogs', {method: 'POST'});
        const d = await res.json();
        if (d.ok === false) {
          box.innerHTML = `<div style="color:#ef4444; font-weight:700;">❌ ${d.error || 'Sync failed — connect WhatsApp first (Scan QR Login).'}</div>`;
          return;
        }
        box.innerHTML = `<div style="color:#10b981; font-weight:700;">✅ Synced ${d.dialogs_count || 0} REAL joined groups from your WhatsApp! (${d.added || 0} new, ${d.updated || 0} updated)</div>`;
        loadWASession();
        loadWAGroups();
        fetchStats();
        await loadBulkTargets();
        setTimeout(() => { box.style.display = 'none'; }, 5000);
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ Failed to sync: ' + e + '</div>';
      }
    }

    let waLoginPoller = null;

    function stopWALoginPoller() {
      if (waLoginPoller) { clearInterval(waLoginPoller); waLoginPoller = null; }
    }

    function closeWALoginDialog() {
      stopWALoginPoller();
      const box = document.getElementById('wa-login-dialog');
      if (box) box.style.display = 'none';
    }

    // Poll the REAL session status every 2.5s until the phone actually links.
    function startWALoginPoller(mode) {
      stopWALoginPoller();
      waLoginPoller = setInterval(async () => {
        try {
          const res = await fetch('/api/whatsapp/session');
          const s = await res.json();
          loadWASession();
          const box = document.getElementById('wa-login-dialog');
          if (!box) return;
          if (s.status === 'connected') {
            stopWALoginPoller();
            box.innerHTML = `<div style="color:#10b981; font-weight:700;">🎉 REAL WhatsApp Linked Successfully! Device: ${s.device_name || ''} ${s.phone || ''}<br><span style="font-size:12px; color:#cbd5e1;">Auto-syncing your joined groups now...</span></div>`;
            loadWAGroups();
            fetchStats();
            try { await fetch('/api/whatsapp/sync_dialogs', {method: 'POST'}); } catch (_) {}
            loadWAGroups();
            setTimeout(() => { box.style.display = 'none'; }, 5000);
          } else if (mode === 'qr' && s.status === 'qr_ready' && s.qr_data) {
            const img = document.getElementById('wa-live-qr-img');
            if (img && img.src !== s.qr_data) img.src = s.qr_data;  // QR auto-refreshes every ~60s
            else if (!img) showQRLoginModal();  // QR arrived after "not ready" screen
          } else if (mode === 'code' && s.status === 'code_ready' && s.pairing_code) {
            const codeEl = document.getElementById('wa-live-pairing-code');
            if (codeEl && codeEl.innerText !== s.pairing_code) codeEl.innerText = s.pairing_code;
          } else if (s.status === 'offline' && s.last_error) {
            stopWALoginPoller();
            box.innerHTML = `<div style="color:#ef4444; font-weight:700;">❌ Could not reach WhatsApp servers from this machine.</div>
              <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">Detail: ${s.last_error}<br>
              Check the server's internet access / firewall (web.whatsapp.com must be reachable), then retry.</div>
              <button class="btn btn-accent" style="font-size:11px; padding:5px 10px; margin-top:8px;" onclick="showQRLoginModal()">🔄 Retry QR Login</button>`;
          }
        } catch (e) { /* keep polling */ }
      }, 2500);
    }

    async function showQRLoginModal() {
      const box = document.getElementById('wa-login-dialog');
      box.style.display = 'block';
      box.innerHTML = '<div style="color:#38bdf8;">🔐 Opening REAL WhatsApp Web session & generating live QR... (takes ~5-10s)</div>';
      try {
        const res = await fetch('/api/whatsapp/request_qr', {method: 'POST'});
        const d = await res.json();
        const s = d.session || d || {};
        if (s.status === 'bridge_offline') {
          box.innerHTML = `<div style="color:#ef4444; font-weight:700;">⚠️ WhatsApp Bridge is not running!</div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">Start it in a terminal, then try again:<br>
            <code style="color:#facc15;">cd gateway && npm install && node wa_bridge.js</code></div>`;
          return;
        }
        if (s.status === 'connected') {
          box.innerHTML = '<div style="color:#10b981; font-weight:700;">✅ Already connected to a REAL WhatsApp session!</div>';
          loadWASession();
          setTimeout(() => { box.style.display = 'none'; }, 3000);
          return;
        }
        if (!s.qr_data) {
          if (s.status === 'offline' && s.last_error) {
            box.innerHTML = `<div style="color:#ef4444; font-weight:700;">❌ Could not reach WhatsApp servers from this machine.</div>
              <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">Detail: ${s.last_error}<br>
              This server's network must allow <b>web.whatsapp.com</b>. Run the bridge on your own PC / VPS with open internet, then retry.</div>
              <button class="btn btn-accent" style="font-size:11px; padding:5px 10px; margin-top:8px;" onclick="showQRLoginModal()">🔄 Retry QR Login</button>`;
            return;
          }
          box.innerHTML = '<div style="color:#f59e0b;">⏳ QR not ready yet (' + (s.status || 'connecting') + '). Waiting for WhatsApp servers...</div>';
          startWALoginPoller('qr');
          return;
        }
        box.innerHTML = `
          <div style="display:flex; gap:20px; align-items:center; flex-wrap:wrap;">
            <img id="wa-live-qr-img" src="${s.qr_data}" style="width:200px; height:200px; border-radius:8px; border:2px solid #10b981; background:white; padding:4px;">
            <div>
              <h4 style="color:#10b981; margin-bottom:6px;">📱 Scan with WhatsApp — this is a REAL login QR</h4>
              <p style="font-size:12px; color:#cbd5e1; margin-bottom:8px;">1. Open WhatsApp on your phone<br>2. Tap Menu / Settings &gt; <b>Linked Devices</b><br>3. Tap <b>Link a Device</b> and scan this code.<br><span style="color:#f59e0b;">QR auto-refreshes; connection is detected automatically — no button needed.</span></p>
              <div id="wa-qr-wait-status" style="font-size:12px; color:#38bdf8; margin-bottom:8px;">⏳ Waiting for your phone to scan...</div>
              <button class="btn btn-outline" style="font-size:11px; padding:5px 10px;" onclick="closeWALoginDialog()">Close</button>
            </div>
          </div>
        `;
        startWALoginPoller('qr');
        loadWASession();
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ QR Request failed: ' + e + '</div>';
      }
    }

    async function showCodeLoginModal() {
      const phone = prompt('Enter WhatsApp Phone Number with Country Code (e.g. +91 9876543210):');
      if (!phone) return;
      const box = document.getElementById('wa-login-dialog');
      box.style.display = 'block';
      box.innerHTML = '<div style="color:#38bdf8;">Requesting 8-digit Pairing Code from WhatsApp...</div>';
      try {
        const res = await fetch('/api/whatsapp/request_code', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({phone})
        });
        const d = await res.json();
        const s = d.session || d || {};
        if (s.status === 'bridge_offline') {
          box.innerHTML = `<div style="color:#ef4444; font-weight:700;">⚠️ WhatsApp Bridge is not running!</div>
            <div style="font-size:12px; color:#cbd5e1; margin-top:6px;">Start it in a terminal, then try again:<br>
            <code style="color:#facc15;">cd gateway && npm install && node wa_bridge.js</code></div>`;
          return;
        }
        if (!s.pairing_code) {
          box.innerHTML = '<div style="color:#f59e0b;">⏳ Requesting real pairing code from WhatsApp servers... keep this open.</div>';
          startWALoginPoller('code');
          return;
        }
        box.innerHTML = `
          <div style="background:#0b1329; border:1px solid #38bdf8; padding:16px; border-radius:8px;">
            <h4 style="color:#38bdf8; margin-bottom:6px;">🔢 REAL WhatsApp Pairing Code</h4>
            <div id="wa-live-pairing-code" style="font-size:24px; font-weight:800; letter-spacing:4px; color:#facc15; margin:10px 0;">${s.pairing_code}</div>
            <p style="font-size:12px; color:#cbd5e1; margin-bottom:10px;">On your phone: WhatsApp &gt; <b>Linked Devices</b> &gt; <b>Link a Device</b> &gt; <b>Link with phone number instead</b> — then type this code. Connection is detected automatically.</p>
            <button class="btn btn-outline" style="font-size:11px; padding:5px 10px;" onclick="closeWALoginDialog()">Close</button>
          </div>
        `;
        startWALoginPoller('code');
        loadWASession();
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ Pairing code request failed: ' + e + '</div>';
      }
    }

    // ---------- ⏱️ GLOBAL SMART GAP ENGINE (saved in browser, applies everywhere) ----------
    function applyGapPreset(val) {
      if (val === 'custom') return;
      const [mn, mx] = val.split(',').map(Number);
      document.getElementById('gap-min').value = mn;
      document.getElementById('gap-max').value = mx;
      saveGapSettings();
    }

    function getGapMin() {
      const v = parseInt(document.getElementById('gap-min')?.value || '40', 10);
      return isNaN(v) || v < 3 ? 3 : v;
    }

    function getGapMax() {
      const mn = getGapMin();
      const v = parseInt(document.getElementById('gap-max')?.value || '60', 10);
      return isNaN(v) || v <= mn ? mn + 5 : v;
    }

    function gapLabel() {
      const mn = getGapMin(), mx = getGapMax();
      const fmt = s => s >= 60 ? (s / 60).toFixed(s % 60 ? 1 : 0) + ' min' : s + 's';
      return `${fmt(mn)}–${fmt(mx)}`;
    }

    function saveGapSettings() {
      try {
        localStorage.setItem('su_gap', JSON.stringify({
          min: getGapMin(), max: getGapMax(),
          preset: document.getElementById('global-gap-preset')?.value || '60,80'
        }));
      } catch (e) {}
    }

    function loadGapSettings() {
      try {
        const s = JSON.parse(localStorage.getItem('su_gap') || 'null');
        if (!s) return;
        const presetEl = document.getElementById('global-gap-preset');
        if (presetEl && s.preset) presetEl.value = s.preset;
        if (s.min) document.getElementById('gap-min').value = s.min;
        if (s.max) document.getElementById('gap-max').value = s.max;
      } catch (e) {}
    }

    async function dashLogout() {
      if (!confirm('Lock the dashboard? మళ్ళీ open చేయాలంటే password అడుగుతుంది.')) return;
      try { await fetch('/api/auth/logout', {method:'POST'}); } catch (e) {}
      location.href = '/';
    }

    // ================= 📊 BROADCAST HISTORY & ANALYTICS =================
    async function loadHistory() {
      try {
        const r = await fetch('/api/history');
        const d = await r.json();
        const s = d.summary || {};
        document.getElementById('hist-today').innerText = s.today_polls ?? 0;
        document.getElementById('hist-today-ev').innerText = s.today_events ?? 0;
        document.getElementById('hist-week').innerText = s.week_polls ?? 0;
        document.getElementById('hist-week-ev').innerText = s.week_events ?? 0;
        const bk = s.by_kind || {};
        document.getElementById('hist-split').innerText = (bk.telegram || 0) + ' / ' + (bk.whatsapp || 0);
        const tops = s.top_targets || [];
        document.getElementById('hist-top').innerText = tops.length ? tops[0].target : '—';
        document.getElementById('hist-top-list').innerHTML = tops.length
          ? tops.map((t, i) => `<div style="display:flex; justify-content:space-between; padding:5px 6px; border-radius:6px; background:${i===0?'rgba(251,191,36,0.08)':'transparent'};"><span>${i+1}. ${t.target}</span><b style="color:#38bdf8;">${t.count}</b></div>`).join('')
          : '<span style="color:#64748b;">No dispatches yet — ఏదైనా poll పంపండి!</span>';
        const tbody = document.querySelector('#table-history tbody');
        tbody.innerHTML = '';
        (d.history || []).forEach(e => {
          const tr = document.createElement('tr');
          const kindBadge = e.kind === 'telegram' ? '📢 Telegram' : (e.kind === 'whatsapp' ? '💚 WhatsApp' : '🤖 ' + e.kind);
          tr.innerHTML = `
            <td style="font-family:monospace; font-size:11px;">${e.ts}</td>
            <td>${kindBadge}</td>
            <td>${e.target}</td>
            <td style="color:#38bdf8; font-weight:700;">${e.count}</td>
            <td style="font-size:11px;">${(e.subjects||[]).join(', ') || 'ALL'}</td>
            <td style="font-size:11px;">${e.dry ? '<span style="color:#f59e0b;">DRY-RUN</span>' : '<span style="color:#34d399;">LIVE</span>'}${e.note ? ' · ' + e.note : ''}</td>
          `;
          tbody.appendChild(tr);
        });
        if (!(d.history || []).length) {
          tbody.innerHTML = '<tr><td colspan="6" style="color:#64748b;">ఇంకా dispatches లేవు.</td></tr>';
        }
      } catch (e) { console.error('history load:', e); }
    }

    // ====== 📡 HEADER LIVE STATUS STRIP (ప్రతి tab లో కనిపిస్తుంది) ======
    // 🧭 MISSION HOME — ఏం అయింది / ఏం మిగిలింది + ఈరోజు timeline
    async function renderMissionHome() {
      try {
        const [hr, sr, gr] = await Promise.all([
          fetch('/api/health'), fetch('/api/whatsapp/schedules'), fetch('/api/whatsapp/groups')
        ]);
        const h = await hr.json(), s = await sr.json(), g = await gr.json();
        const groups = (g.groups || []).length;
        const jobs = (s.jobs || []).filter(j => j.enabled !== false);
        const steps = [
          {done: !!h.whatsapp_connected, icon: '💚', t: 'WhatsApp Connect', hint: 'QR scan ఒక్కసారే — తర్వాత never-disconnect engine చూసుకుంటుంది', tab: 'tab-wa-dispatch'},
          {done: !!h.telegram_live, icon: '📢', t: 'Telegram Bot Token', hint: 'env/.env లో BOT_TOKEN పెడితే TG LIVE అవుతుంది', tab: 'tab-dynamic-channels'},
          {done: groups > 0, icon: '👥', t: 'Groups Add (' + groups + ' ఉన్నాయి)', hint: 'Excel upload లేదా Quick-Add తో groups పెట్టండి', tab: 'tab-excel-import'},
          {done: jobs.length > 0, icon: '⏰', t: 'Daily Schedule (' + jobs.length + ' slots)', hint: 'Builder లో time + ఎన్ని రోజులో set చేయండి', tab: 'tab-wa-dispatch'},
          {done: (h.total_fresh || 0) >= 50, icon: '📦', t: 'Question Stock (' + (h.total_fresh || 0) + ' fresh)', hint: 'తక్కువైనా పర్లేదు — system auto top-up చేస్తుంది', tab: 'tab-control'}
        ];
        const done = steps.filter(x => x.done).length;
        document.getElementById('sg-progress-bar').style.width = Math.round(done / steps.length * 100) + '%';
        document.getElementById('sg-progress-label').textContent = done === steps.length
          ? '🎉 5/5 — అంతా READY, Full Auto-Pilot!' : done + '/' + steps.length + ' steps complete';
        document.getElementById('sg-steps').innerHTML = steps.map(x => `
          <div style="display:flex; align-items:center; gap:8px; background:${x.done ? 'rgba(16,185,129,0.08)' : 'rgba(251,191,36,0.07)'}; border:1px solid ${x.done ? '#10b981' : '#fbbf24'}; border-radius:10px; padding:8px 10px;">
            <span style="font-size:18px;">${x.done ? '✅' : x.icon}</span>
            <div style="flex:1;">
              <div style="font-size:12px; font-weight:800;">${x.t}</div>
              <div style="font-size:10px; color:var(--text-muted);">${x.hint}</div>
            </div>
            ${x.done ? '' : `<button class="btn btn-outline" style="padding:3px 8px; font-size:10px; white-space:nowrap;" onclick="switchTab('${x.tab}')">👉 ఇక్కడ</button>`}
          </div>`).join('');

        // 📆 today's timeline
        const today = new Date().toISOString().slice(0, 10);
        const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
        const items = jobs
          .filter(j => !(j.start_date && j.start_date > today))
          .map(j => {
            const p = (j.time || '00:00').split(':');
            const m = parseInt(p[0]) * 60 + parseInt(p[1]);
            return Object.assign({}, j, {_m: m, _done: (j.last_run || '').startsWith(today)});
          })
          .sort((a, b) => a._m - b._m);
        const next = items.find(x => !x._done && x._m >= nowMin);
        const tl = document.getElementById('tl-list');
        const chip = document.getElementById('tl-next-chip');
        if (items.length === 0) {
          tl.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:8px;">ఈరోజు scheduled sends లేవు — పైన Setup Guide లో ⏰ step తో ఒక slot పెట్టండి!</div>';
          chip.textContent = '';
        } else {
          tl.innerHTML = items.map(j => {
            const isNext = next && j.id === next.id;
            const state = j._done ? '✅ Sent' : (j._m < nowMin ? '🕒 ఈరోజు దాటింది' : (isNext ? '⏭️ NEXT' : '🕒 Upcoming'));
            const modeIc = j.mode === 'tg' ? '📢 TG' : (j.mode === 'both' ? '📢+💚' : '💚 WA');
            return `<div style="display:flex; align-items:center; gap:10px; padding:6px 10px; border-radius:8px; ${isNext ? 'background:rgba(251,191,36,0.1); border:1px solid #fbbf24;' : 'border-bottom:1px solid rgba(255,255,255,0.05);'}">
              <span style="font-family:monospace; font-weight:800; color:#38bdf8; font-size:14px;">${j.time}</span>
              <span style="font-size:12px; flex:1;">${j.label || 'Quiz Drill'} <span style="color:var(--text-muted);">· ${modeIc} · ${j.questions_count || 5} Qs</span></span>
              <span style="font-size:11px; font-weight:700;">${state}</span>
            </div>`;
          }).join('');
          if (next) {
            let dm = next._m - nowMin; if (dm < 0) dm += 1440;
            chip.textContent = '⏭️ Next: ' + next.time + ' (ఇంకో ' + (dm >= 60 ? Math.floor(dm / 60) + 'h ' + (dm % 60) + 'm' : dm + 'm') + ' లో)';
          } else {
            chip.textContent = items.some(x => x._done) ? '✅ ఈరోజు slots అన్నీ పూర్తి — రేపు మళ్ళీ auto!' : '';
          }
        }
      } catch (e) { /* silent */ }
    }
    setInterval(renderMissionHome, 60000);

    async function refreshStatusStrip() {
      try {
        const r = await fetch('/api/health');
        const d = await r.json();
        const chip = (txt, on) =>
          `<span style="font-size:10px; font-weight:800; padding:3px 9px; border-radius:12px; border:1px solid ${on ? '#34d399' : '#f59e0b'}; color:${on ? '#34d399' : '#f59e0b'}; background:${on ? 'rgba(52,211,153,0.08)' : 'rgba(245,158,11,0.07)'};">${txt}</span>`;
        document.getElementById('live-status-strip').innerHTML =
          chip(d.telegram_live ? '📢 TG LIVE' : '📢 TG DRY', d.telegram_live) +
          chip(d.whatsapp_connected ? '💚 WA ON' : '💚 WA OFF', d.whatsapp_connected) +
          chip('🤖 ' + (d.autopilot_slots + d.wa_slots) + ' SLOTS', (d.autopilot_slots + d.wa_slots) > 0) +
          chip('📦 ' + d.total_fresh + ' FRESH', d.total_fresh > 50) +
          chip(d.ip_lock_on ? '🛡️ IP LOCK' : '🔑 PW ONLY', d.ip_lock_on);
      } catch (e) {}
    }
    setInterval(refreshStatusStrip, 60000);

    // ================= 🩺 MISSION CONTROL (SYSTEM HEALTH) =================
    async function loadHealth() {
      try {
        const r = await fetch('/api/health');
        const d = await r.json();
        document.getElementById('health-uptime').innerText = 'server uptime: ' + d.uptime_min + ' min';
        const b = (ok, onTxt, offTxt, offColor) =>
          `<span style="padding:4px 10px; border-radius:14px; font-weight:800; background:${ok ? 'rgba(52,211,153,0.12)' : 'rgba(245,158,11,0.10)'}; color:${ok ? '#34d399' : (offColor || '#f59e0b')}; border:1px solid ${ok ? '#34d399' : (offColor || '#f59e0b')};">${ok ? onTxt : offTxt}</span>`;
        document.getElementById('health-badges').innerHTML =
          b(d.telegram_live, '📢 Telegram: LIVE', '📢 Telegram: DRY-RUN (BOT_TOKEN set చేయండి)') +
          b(d.whatsapp_connected, '💚 WhatsApp: CONNECTED', '💚 WhatsApp: NOT LINKED (QR scan)') +
          b(d.scheduler_running, '⏰ Scheduler: RUNNING', '⏰ Scheduler: OFF', '#f87171') +
          b(d.autopilot_slots > 0, '🤖 Auto-Pilot: ' + d.autopilot_slots + ' slot(s) ON', '🤖 Auto-Pilot: no slots') +
          b(d.ip_lock_on, '🛡️ IP Lock: ON', '🛡️ IP Lock: OFF (password only)') +
          b(true, '📊 7-Day Polls: ' + d.week_polls, '') +
          b(!!(d.last_backup && d.last_backup.exists), '🗄️ Auto-Backup: ' + ((d.last_backup||{}).file || ''), '🗄️ Auto-Backup: pending (daily)');
        const low = d.low_stock || [];
        let bankHtml = `<b style="color:#38bdf8;">🧮 Question Bank:</b> ${d.total_fresh} fresh / ${d.total_questions} total`;
        if (low.length) {
          bankHtml += ` · <span style="color:#f59e0b;">⚠️ Low stock (${low.length}):</span> ` +
            low.map(r => `${r.channel} (${r.unused})`).join(', ') +
            ` <button class="btn btn-accent" style="font-size:11px; padding:3px 10px; margin-left:6px;" onclick="runBankTopup()">⚡ Auto Top-Up Now</button>`;
        } else {
          bankHtml += ' · <span style="color:#34d399;">✅ అన్ని channels కి fresh stock బాగుంది</span>';
        }
        bankHtml += '<span id="topup-result" style="margin-left:8px;"></span>';
        document.getElementById('health-bank').innerHTML = bankHtml;
      } catch (e) { console.error('health:', e); }
    }

    async function runBankTopup() {
      const el = document.getElementById('topup-result');
      el.innerHTML = '<span style="color:#fbbf24;">⚡ Generating fresh questions...</span>';
      try {
        const r = await fetch('/api/bank/topup', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
        const d = await r.json();
        el.innerHTML = d.ok ? '<span style="color:#34d399;">✅ ' + d.message + '</span>'
                            : '<span style="color:#f87171;">❌ ' + (d.error || 'failed') + '</span>';
        if (d.ok) { fetchStats(); setTimeout(loadHealth, 1200); }
      } catch (e) { el.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>'; }
    }

    function downloadBackup() {
      window.location.href = '/api/backup';
    }

    async function exportHistoryCSV() {
      try {
        const r = await fetch('/api/history');
        const d = await r.json();
        const rows = [['Time','Platform','Target','Polls','Subjects','Mode','Note']];
        (d.history || []).forEach(e => rows.push([
          e.ts, e.kind, e.target, e.count, (e.subjects||[]).join('+') || 'ALL', e.dry ? 'DRY-RUN' : 'LIVE', e.note || ''
        ]));
        const csv = rows.map(r2 => r2.map(c => '"' + String(c).replace(/"/g, '""') + '"').join(',')).join('\\n');
        const blob = new Blob(['\\ufeff' + csv], {type: 'text/csv;charset=utf-8'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'broadcast_history.csv';
        a.click();
        URL.revokeObjectURL(a.href);
      } catch (e) { alert('Export failed: ' + e); }
    }

    // ================= 🔍 QUESTION FINDER =================
    let _qfTimer = null;
    function qfDebounced() {
      clearTimeout(_qfTimer);
      _qfTimer = setTimeout(searchQuestions, 350);
    }

    async function searchQuestions() {
      const term = document.getElementById('qf-search').value.trim();
      const box = document.getElementById('qf-results');
      if (!term) { box.innerHTML = ''; return; }
      box.innerHTML = '<span style="color:#fbbf24;">Searching...</span>';
      try {
        const r = await fetch('/api/questions/search?q=' + encodeURIComponent(term) + '&limit=30');
        const d = await r.json();
        if (!d.results || !d.results.length) {
          box.innerHTML = '<span style="color:#64748b;">"' + term + '" కి matches లేవు — వేరే పదం try చేయండి.</span>';
          return;
        }
        box.innerHTML = d.results.map(q => `
          <div style="display:flex; align-items:center; gap:8px; padding:7px 9px; border-radius:6px; background:#050811; margin-bottom:5px; flex-wrap:wrap;">
            <span style="flex:1; min-width:200px;">${esc(q.q_en || '(Telugu-only question)')}</span>
            <span class="category-tag" style="font-size:10px;">${esc(q.channel)}</span>
            <span style="font-size:10px; color:#94a3b8;">${esc(q.topic)}</span>
            <span style="font-size:10px; color:${q.fresh ? '#34d399' : '#f59e0b'};">${q.fresh ? '✨ FRESH' : '♻️ sent before'}</span>
            <button class="btn btn-accent" style="font-size:10px; padding:3px 10px;" onclick="sendPickedQuestion('${q.id}')">📤 Send</button>
          </div>`).join('');
      } catch (e) { box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>'; }
    }

    async function sendPickedQuestion(qid) {
      const ch = document.getElementById('post-poll-channel').value;
      if (!ch) return alert('పైన "Choose Channel to Post Poll" select చేయండి');
      try {
        const r = await fetch('/api/questions/send', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({qid, channel: ch})
        });
        const d = await r.json();
        alert(d.ok ? '✅ ' + d.message : '❌ ' + (d.error || 'failed'));
      } catch (e) { alert('❌ ' + e); }
    }

    // ================= 🤖 TELEGRAM AUTO-PILOT =================
    async function oneClickDailyPlan() {
      // 🚀 zero-thinking setup: select ALL targets + 3 classic daily slots
      let channels = getSelectedChannelKeys();
      if (!channels.length) { selectAllChannels(true); channels = getSelectedChannelKeys(); }
      if (!channels.length) return alert('ముందు కనీసం ఒక channel/group register చేయండి');
      if (!confirm('🚀 Daily Plan: 08:00 + 13:00 + 20:30 కి ' + channels.length + ' target(s) × 5 polls auto-post అవుతాయి. OK?')) return;
      const box = document.getElementById('tg-ap-result');
      box.innerHTML = '<span style="color:#fbbf24;">Creating daily plan...</span>';
      try {
        const r = await fetch('/api/telegram/schedule', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({times: '08:00, 13:00, 20:30', channels, count: 5, subjects: []})
        });
        const d = await r.json();
        box.innerHTML = d.ok ? '<span style="color:#34d399;">✅ ' + d.message + '</span>'
                             : '<span style="color:#f87171;">❌ ' + (d.error || 'Failed') + '</span>';
        if (d.ok) loadTgAutopilotJobs();
      } catch (e) { box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>'; }
    }

    async function createTgAutopilot() {
      const box = document.getElementById('tg-ap-result');
      const times = document.getElementById('tg-ap-times').value.trim();
      const count = document.getElementById('tg-ap-count').value;
      const channels = getSelectedChannelKeys();
      const subjects = Array.from(document.querySelectorAll('.tg-ap-subj:checked')).map(c => c.value);
      (document.getElementById('tg-ap-subj-custom').value || '').toUpperCase().split(/[^A-Z0-9]+/).filter(Boolean).forEach(s => subjects.push(s));
      if (!times) return alert('Times ఇవ్వండి — ఉదా: 08:00, 20:30');
      if (!channels.length) return alert('పై table లో కనీసం ఒక channel/group select చేయండి (checkbox)');
      box.innerHTML = '<span style="color:#fbbf24;">Creating auto-pilot slots...</span>';
      try {
        const r = await fetch('/api/telegram/schedule', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({times, channels, count: parseInt(count), subjects})
        });
        const d = await r.json();
        box.innerHTML = d.ok ? '<span style="color:#34d399;">✅ ' + d.message + '</span>'
                             : '<span style="color:#f87171;">❌ ' + (d.error || 'Failed') + '</span>';
        if (d.ok) { document.getElementById('tg-ap-times').value = ''; loadTgAutopilotJobs(); }
      } catch (e) { box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>'; }
    }

    async function loadTgAutopilotJobs() {
      const wrap = document.getElementById('tg-ap-jobs');
      if (!wrap) return;
      try {
        const r = await fetch('/api/whatsapp/schedules');
        const d = await r.json();
        const jobs = (d.jobs || d.schedules || []).filter(j => j.mode === 'tg');
        if (!jobs.length) { wrap.innerHTML = '<span style="color:#64748b;">No Telegram auto-pilot slots yet.</span>'; return; }
        wrap.innerHTML = '<div style="font-weight:800; color:#a78bfa; margin-bottom:6px;">🤖 Active Auto-Pilot Slots:</div>' + jobs.map(j => `
          <div style="display:flex; align-items:center; gap:8px; padding:6px 8px; border-radius:6px; background:#050811; margin-bottom:5px; flex-wrap:wrap;">
            <b style="color:#38bdf8;">${j.time}</b>
            <span style="flex:1;">${j.label}</span>
            <span style="font-size:11px; color:${j.enabled ? '#34d399' : '#f59e0b'};">${j.enabled ? '● ON' : '○ PAUSED'}</span>
            <span style="font-size:11px; color:#64748b;">runs: ${j.total_dispatches || 0}${j.last_run ? ' · last: ' + j.last_run : ''}</span>
            <button class="btn btn-outline" style="font-size:10px; padding:2px 8px; color:#fbbf24; border-color:#fbbf24;" onclick="editScheduleJob('${j.id}')">✏️ Edit</button>
            <button class="btn btn-outline" style="font-size:10px; padding:2px 8px;" onclick="toggleTgApJob('${j.id}')">${j.enabled ? '⏸ Pause' : '▶ Resume'}</button>
            <button class="btn btn-outline" style="font-size:10px; padding:2px 8px; border-color:#ef4444; color:#ef4444;" onclick="deleteTgApJob('${j.id}')">🗑</button>
          </div>`).join('');
      } catch (e) { wrap.innerHTML = ''; }
    }

    async function toggleTgApJob(id) {
      await fetch('/api/whatsapp/toggle_schedule', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: id})});
      loadTgAutopilotJobs();
    }

    async function deleteTgApJob(id) {
      if (!confirm('ఈ Auto-Pilot slot ని delete చేయాలా?')) return;
      await fetch('/api/whatsapp/delete_schedule', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: id})});
      loadTgAutopilotJobs();
    }

    function toggleIpLockPanel() {
      const p = document.getElementById('ip-lock-panel');
      const show = p.style.display === 'none';
      p.style.display = show ? 'block' : 'none';
      if (show) loadIpLock();
    }

    async function loadIpLock() {
      try {
        const r = await fetch('/api/security');
        const d = await r.json();
        document.getElementById('ip-lock-myip').innerText = d.your_ip || '?';
        document.getElementById('ip-allow-list').value = (d.allowed_ips || []).join('\\n');
        const st = document.getElementById('ip-lock-status');
        if (d.ip_lock_enabled) {
          st.innerText = '🛡️ IP LOCK: ON';
          st.style.color = '#34d399';
        } else {
          st.innerText = '🔓 IP LOCK: OFF';
          st.style.color = '#f59e0b';
        }
        const la = document.getElementById('login-audit');
        const rec = d.recent_logins || [];
        if (la) {
          la.innerHTML = rec.length
            ? '<b style="color:#94a3b8;">🔐 Recent login attempts:</b> ' +
              rec.map(a => `<span style="margin-left:8px; color:${a.ok ? '#34d399' : '#f87171'};">${a.ok ? '✅' : '❌'} ${a.ip} <span style="color:#64748b;">(${a.ts})</span></span>`).join('')
            : '';
        }
      } catch (e) {
        document.getElementById('ip-lock-result').innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>';
      }
    }

    function addMyIpToList() {
      const my = document.getElementById('ip-lock-myip').innerText;
      if (!my || my === '?' || my === '...') return alert('Current IP ఇంకా load అవ్వలేదు');
      const ta = document.getElementById('ip-allow-list');
      const lines = ta.value.split('\\n').map(s => s.trim()).filter(Boolean);
      if (lines.indexOf(my) === -1) lines.push(my);
      ta.value = lines.join('\\n');
    }

    async function saveIpLock(enable) {
      const box = document.getElementById('ip-lock-result');
      const lines = document.getElementById('ip-allow-list').value.split('\\n').map(s => s.trim()).filter(Boolean);
      if (enable && lines.length === 0) return alert('కనీసం ఒక IP ఇవ్వండి — లేదా "Add My Current IP" నొక్కండి');
      if (enable && !confirm('🛡️ IP Lock ON చేయాలా? List లో లేని IP ల నుంచి dashboard open అవ్వదు (మీ current IP safety కోసం auto-add అవుతుంది).')) return;
      box.innerHTML = '<span style="color:#fbbf24;">Saving...</span>';
      try {
        const r = await fetch('/api/security/update', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ip_lock_enabled: enable, allowed_ips: lines})
        });
        const d = await r.json();
        if (!d.ok) { box.innerHTML = '<span style="color:#f87171;">❌ ' + (d.error || 'Failed') + '</span>'; return; }
        box.innerHTML = '<span style="color:#34d399;">✅ ' + (d.message || 'Saved') + (d.note ? ' · ⚠️ ' + d.note : '') + '</span>';
        loadIpLock();
      } catch (e) {
        box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>';
      }
    }

    async function changeDashPassword() {
      const oldP = prompt('ప్రస్తుత (current) password:');
      if (oldP === null) return;
      const newP = prompt('కొత్త (new) password (min 6 chars):');
      if (!newP) return;
      try {
        const r = await fetch('/api/auth/change_password', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({old: oldP, new: newP})
        });
        const d = await r.json();
        alert(d.ok ? '✅ Password changed! మిగతా devices అన్నీ logout అయ్యాయి.' : '❌ ' + (d.error || 'Failed'));
      } catch (e) { alert('❌ ' + e); }
    }

    async function logoutWASession() {
      if (!confirm('Unlink this WhatsApp device and wipe the saved session?')) return;
      const box = document.getElementById('wa-login-dialog');
      box.style.display = 'block';
      box.innerHTML = '<div style="color:#f59e0b;">🚪 Unlinking device from WhatsApp...</div>';
      try {
        await fetch('/api/whatsapp/logout', {method: 'POST'});
        box.innerHTML = '<div style="color:#10b981;">✅ Device unlinked. Use Scan QR Login to connect again.</div>';
        loadWASession();
        setTimeout(() => { box.style.display = 'none'; }, 4000);
      } catch (e) {
        box.innerHTML = '<div style="color:#ef4444;">❌ Logout failed: ' + e + '</div>';
      }
    }

    async function confirmWALogin(devName) {
      try {
        await fetch('/api/whatsapp/confirm_login', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({device_name: devName || 'Primary WhatsApp Phone'})
        });
        const box = document.getElementById('wa-login-dialog');
        box.innerHTML = '<div style="color:#10b981; font-weight:700;">🎉 WhatsApp Connected Successfully & Saved to Disk!</div>';
        loadWASession();
        loadWAGroups();
        fetchStats();
        setTimeout(() => { box.style.display = 'none'; }, 2500);
      } catch (e) {
        alert('Failed: ' + e);
      }
    }

    const ALL_EXAM_CATEGORIES = [
      {code: 'GENERAL', label: '🌐 General (Aptitude/GK)'},
      {code: 'POLICE', label: '👮 Police (SI / Constable)'},
      {code: 'TSPSC', label: '🏛️ TSPSC State & Districts'},
      {code: 'APPSC', label: '🏛️ APPSC State & Districts'},
      {code: 'SSC', label: '🏛️ SSC (CGL / CHSL / MTS)'},
      {code: 'RAILWAY', label: '🚆 Railway RRB'},
      {code: 'BANKING', label: '🏦 Banking (IBPS/SBI)'},
      {code: 'TET_DSC', label: '👩‍🏫 TET / DSC'},
      {code: 'TS_BTECH', label: '💻 TS B.Tech (Engineering)'},
      {code: 'AP_BTECH', label: '💻 AP B.Tech (Engineering)'},
      {code: 'TS_DEGREE', label: '🎓 TS Degree'},
      {code: 'AP_DEGREE', label: '🎓 AP Degree'},
      {code: 'TS_DIPLOMA', label: '⚙️ TS Diploma & POLYCET'},
      {code: 'AP_DIPLOMA', label: '⚙️ AP Diploma & POLYCET'},
      {code: 'TS_INTER', label: '📘 TS Intermediate'},
      {code: 'AP_INTER', label: '📘 AP Intermediate'},
      {code: 'TS_10TH', label: '🎒 TS 10th Class'},
      {code: 'AP_10TH', label: '🎒 AP 10th Class'},
      {code: 'ITI_ALL', label: '🔧 ITI Trade'},
      {code: 'OPEN_UNIV', label: '🏛️ Open University'}
    ];

    async function updateGroupExamCategory(gid, newCat) {
      try {
        const res = await fetch('/api/whatsapp/update_group', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id: gid, updates: {category: newCat}})
        });
        const d = await res.json();
        if (d.ok) {
          const pill = document.getElementById('save-indicator-' + gid);
          if (pill) {
            pill.style.display = 'inline';
            setTimeout(() => { pill.style.display = 'none'; }, 2000);
          }
        }
      } catch (e) {
        alert('Failed to update category: ' + e);
      }
    }

    async function loadHallOfFame() {
      try {
        const d = await (await fetch('/api/whatsapp/hall-of-fame')).json();
        const el = document.getElementById('wa-hof');
        if (!el) return;
        const rows = (d.champions || []).slice(0, 10);
        if (!rows.length) return;
        const medals = ['🥇', '🥈', '🥉'];
        el.innerHTML = rows.map((c, i) => '<div style="padding:3px 0;">' + (medals[i] || ((i + 1) + '.')) +
          ' <b>@' + c.phone + '</b> — ' + c.correct + '✓ · ' + c.quizzes + ' quizzes' +
          (c.group ? ' · <span style="color:var(--text-muted);">' + c.group + '</span>' : '') + '</div>').join('');
      } catch (e) { /* hall of fame optional */ }
    }
    function waHealthBadge(jid) {
      const h = (window._waHealth || {})[jid];
      if (!h || (h.sent + h.failed) === 0) return '';
      if (h.status === 'paused') return ` <span style="background:#dc2626; color:white; padding:2px 7px; border-radius:12px; font-size:10px; font-weight:700;" title="Varusa failures — auto-paused">🔴 PAUSED</span> <button class="btn btn-outline" style="padding:1px 6px; font-size:10px;" onclick="resetGroupHealth('${jid}')">Reset</button>`;
      const col = h.status === 'good' ? '#059669' : '#d97706';
      return ` <span style="background:${col}; color:white; padding:2px 7px; border-radius:12px; font-size:10px; font-weight:700;" title="Delivery success ${h.rate}% (${h.sent} sent, ${h.failed} failed)">📶 ${h.rate}%</span>`;
    }
    async function resetGroupHealth(jid) {
      try { await fetch('/api/whatsapp/group_health_reset', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({jid})}); } catch (e) {}
      loadWAGroups();
    }
    async function runWaPreview() {
      const box = document.getElementById('wa-safety-detail'); if (!box) return;
      box.innerHTML = '👀 Preview tayaravthundi…';
      try {
        const r = await fetch('/api/whatsapp/preview?count=2'); const d = await r.json();
        const esc = (t) => String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');  // 🧼 290X quote-safe
        box.innerHTML = `<b style="color:#38bdf8;">👀 Broadcast Preview</b> <span style="color:var(--text-muted);">${d.groups_total} groups ki ilane velthundi (sample ${d.samples.length} groups · emi send avvadhu)</span>` +
          (d.samples || []).map(s => `<div style="background:#050811; border:1px solid var(--border); border-radius:8px; padding:9px 11px; margin-top:7px;"><b>${esc(s.group)}</b> <span style="color:#64748b;">· ${s.style}</span>${s.messages.map(t => `<pre style="white-space:pre-wrap; font-size:11px; color:#cbd5e1; margin:6px 0; font-family:inherit;">${esc(t)}</pre>`).join('')}</div>`).join('');
      } catch (e) { box.innerHTML = '❌ ' + e; }
    }

    async function loadWAGroups() {
      loadHallOfFame();
      try { const hr = await fetch('/api/whatsapp/group_health'); const hd = await hr.json(); window._waHealth = hd.health || {}; } catch (e) { window._waHealth = {}; }
      const res = await fetch('/api/whatsapp/groups');
      const d = await res.json();
      const tbody = document.querySelector('#table-wa-groups tbody');
      tbody.innerHTML = '';
      (d.groups || []).forEach(g => {
        const tr = document.createElement('tr');
        const gType = g.group_type || 'EXAM_SPECIFIC';
        const typeBadge = gType === 'GENERAL'
          ? '<span style="background:#0284c7; color:white; padding:2px 7px; border-radius:12px; font-size:10px; font-weight:700;">🌐 GENERAL</span>'
          : '<span style="background:#059669; color:white; padding:2px 7px; border-radius:12px; font-size:10px; font-weight:700;">🎯 EXAM-SPECIFIC</span>';

        const catOpts = ALL_EXAM_CATEGORIES.map(c => 
          `<option value="${c.code}" ${g.category === c.code ? 'selected' : ''}>${c.label}</option>`
        ).join('');

        tr.innerHTML = `
          <td><input type="checkbox" class="wa-group-select-checkbox" data-gid="${g.id}" onchange="updatePlannerSelectionCount()"></td>
          <td>${g.id}</td>
          <td>${(g.jid || '').endsWith('@newsletter') ? '📣 <span style="background:#7c3aed; color:white; padding:2px 7px; border-radius:12px; font-size:10px; font-weight:700;">CHANNEL</span> ' : ''}<b>${esc(g.name)}</b>${waHealthBadge(g.jid)}</td>
          <td>
            <div style="display:flex; align-items:center; gap:6px;">
              <select style="margin:0; padding:4px 8px; font-size:11px; background:#0f172a; border:1px solid #38bdf8; color:#f8fafc; border-radius:6px; font-weight:600;" onchange="updateGroupExamCategory('${g.id}', this.value)">
                ${catOpts}
              </select>
              <span id="save-indicator-${g.id}" style="display:none; color:#10b981; font-size:11px; font-weight:700;">✓ Saved</span>
            </div>
          </td>
          <td>${typeBadge}</td>
          <td><span class="shift-tag">${g.shift || 'ALL_DAY'}</span></td>
          <td style="font-family:monospace; font-size:12px;">${g.jid}</td>
          <td><span class="status-pill ${g.active ? 'open' : 'closed'}">${g.active ? 'Active' : 'Paused'}</span></td>
          <td><button class="btn btn-outline" style="padding:4px 8px; font-size:11px;" onclick="deleteWAGroup('${g.id}')">Delete</button></td>
        `;
        tbody.appendChild(tr);
      });
      if (d.gateway_url) document.getElementById('wa-gateway-input').value = d.gateway_url;
    }

    function filterWAGroups() {
      const q = (document.getElementById('wa-search-box').value || '').toLowerCase();
      const rows = document.querySelectorAll('#table-wa-groups tbody tr');
      rows.forEach(r => {
        const text = r.innerText.toLowerCase();
        r.style.display = text.includes(q) ? '' : 'none';
      });
    }

    async function downloadGroupsCSV() {
      const res = await fetch('/api/whatsapp/groups'); const d = await res.json();
      const rows = [['Group Name','WhatsApp JID / Link','Exam','Shift','Group Type','Active','Members','Real Synced']];
      (d.groups || []).filter(g => g.admin_verified === true).forEach(g => rows.push([g.name || '', g.jid || '', g.category || 'GENERAL', g.shift || 'ALL_DAY', g.group_type || 'EXAM_SPECIFIC', g.active ? 'YES' : 'NO', g.participants || 0, g.real ? 'YES' : 'NO']));
      const csv = rows.map(r => r.map(v => '"' + String(v).replaceAll('"','""') + '"').join(',')).join('\\r\\n');
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], {type:'text/csv;charset=utf-8'})); a.download = 'studentup-whatsapp-groups-' + new Date().toISOString().slice(0,10) + '.csv'; a.click(); URL.revokeObjectURL(a.href);
    }

    async function exportExcelSheet() {
      const res = await fetch('/api/whatsapp/groups');
      const d = await res.json();
      const groups = d.groups || [];
      const lines = ['Group Name\\tLink or JID\\tCategory\\tShift\\tGroup Type'];
      groups.filter(g => g.admin_verified === true).forEach(g => {
        lines.push(`${g.name}\\t${g.jid}\\t${g.category || 'GENERAL'}\\t${g.shift || 'ALL_DAY'}\\t${g.group_type || 'EXAM_SPECIFIC'}`);
      });
      document.getElementById('excel-paste-text').value = lines.join('\\n');
      document.getElementById('excel-import-log').innerText = `📋 Exported ${groups.length} groups to text box! You can copy/edit them directly and click Save.`;
    }

    async function addNewWAGroup() {
      const name = document.getElementById('new-wa-title').value.trim();
      const jid = document.getElementById('new-wa-jid').value.trim();
      const category = document.getElementById('new-wa-category').value;
      const gType = document.getElementById('new-wa-grouptype').value;
      const shift = document.getElementById('new-wa-shift').value;
      if (!name || !jid) return alert('Enter group name and JID / Link');
      await fetch('/api/whatsapp/add_group', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, jid, category, shift, group_type: gType})
      });
      document.getElementById('new-wa-title').value = '';
      document.getElementById('new-wa-jid').value = '';
      loadWAGroups();
      fetchStats();
    }

    function selectAllGroups(checked) {
      const cbs = document.querySelectorAll('.wa-group-select-checkbox');
      cbs.forEach(cb => cb.checked = checked);
      const master = document.getElementById('wa-select-all');
      if (master) master.checked = checked;
      updatePlannerSelectionCount();
    }

    function getSelectedGroupIds() {
      const cbs = document.querySelectorAll('.wa-group-select-checkbox:checked');
      return Array.from(cbs).map(cb => cb.getAttribute('data-gid'));
    }

    async function dispatchSelectedGroups() {
      const gids = getSelectedGroupIds();
      if (!gids || gids.length === 0) {
        return alert('Please select at least 1 WhatsApp group using the checkboxes to dispatch!');
      }
      if (!confirm(`Run 5-poll anti-ban broadcast on ${gids.length} selected group(s)?\\n(${gapLabel()} gaps between polls, batch rest after every 5 groups)`)) return;

      const gw = document.getElementById('wa-gateway-input').value;
      const res = await fetch('/api/whatsapp/start_pipeline', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          target_group_ids: gids,
          is_question: true,
          gateway: gw,
          delay_min: getGapMin(),
          delay_max: getGapMax(),
          questions_count: 5
        })
      });
      const d = await res.json();
      if (!d.ok) alert(d.message);
      else alert(`🚀 Broadcast started for ${gids.length} selected groups!`);
    }

    async function deleteWAGroup(id) {
      if (!confirm('Remove this group?')) return;
      await fetch('/api/whatsapp/remove_group', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id})
      });
      loadWAGroups();
      fetchStats();
    }

    async function startInterleaved(isQuestion) {
      const cat = document.getElementById('wa-target-category').value;
      const shift = document.getElementById('wa-target-shift').value;
      const msg = document.getElementById('wa-broadcast-msg').value;
      const att = document.getElementById('wa-attachment-url').value;
      const gw = document.getElementById('wa-gateway-input').value;

      const res = await fetch('/api/whatsapp/start_pipeline', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          category: cat,
          shift: shift,
          is_question: isQuestion,
          custom_msg: msg,
          attachment: att,
          gateway: gw,
          delay_min: getGapMin(),
          delay_max: getGapMax(),
          questions_count: 5
        })
      });
      const d = await res.json();
      if (!d.ok) alert(d.message);
    }

    async function stopInterleaved() {
      await fetch('/api/whatsapp/stop_pipeline', {method: 'POST'});
    }

    function toggleContinuousMode(isContinuous) {
      const durContainer = document.getElementById('sched-duration-container');
      if (durContainer) {
        durContainer.style.display = isContinuous ? 'none' : 'block';
      }
    }

    async function checkSchedulerConflictLive() {
      const timeVal = (document.getElementById('clock-slot-time').value || '').trim();
      const extraTimes = (document.getElementById('clock-extra-times').value || '')
        .split(',')
        .map(t => t.trim())
        .filter(t => t.length > 0);
      const allTimes = [timeVal, ...extraTimes];
      const gids = getSelectedGroupIds();

      const alertBox = document.getElementById('sched-conflict-alert');
      const msgBox = document.getElementById('sched-conflict-msg');
      if (!alertBox || !msgBox) return;

      if (gids.length === 0 || allTimes.length === 0) {
        alertBox.style.display = 'none';
        return;
      }

      for (const t of allTimes) {
        try {
          const res = await fetch('/api/whatsapp/check_conflicts', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({target_group_ids: gids, time: t})
          });
          const d = await res.json();
          if (d.has_conflicts) {
            const conflictMsgs = d.conflicts.map(c => c.message).join('; ');
            msgBox.innerHTML = `Group collision detected for <b>${t}</b>: ${conflictMsgs}`;
            alertBox.style.display = 'block';
            return;
          }
        } catch (e) {
          console.error(e);
        }
      }
      alertBox.style.display = 'none';
    }

    async function addClockSlot() {
      const timeVal = (document.getElementById('clock-slot-time').value || '').trim();
      const extraTimesRaw = (document.getElementById('clock-extra-times').value || '').trim();
      const label = (document.getElementById('clock-slot-label').value || '').trim();
      const cat = document.getElementById('clock-slot-cat').value;
      const isAuto = document.getElementById('sched-auto-continuous').checked;
      const daysDur = isAuto ? 0 : parseInt(document.getElementById('sched-days-duration').value || '7');
      const gids = getSelectedGroupIds();

      if (!timeVal) return alert('Please select a clock time first!');

      const extraTimes = extraTimesRaw ? extraTimesRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
      const allTimes = [timeVal, ...extraTimes];

      // Collision Check before submitting
      try {
        for (const t of allTimes) {
          const cRes = await fetch('/api/whatsapp/check_conflicts', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({target_group_ids: gids, time: t})
          });
          const cData = await cRes.json();
          if (cData.has_conflicts) {
            const warn = cData.conflicts.map(c => c.message).join('\\n');
            const proceed = confirm(`⚠️ Group Conflict Warning for ${t}:\\n${warn}\\n\\nDo you still want to proceed and save this schedule?`);
            if (!proceed) return;
          }
        }
      } catch (e) {
        console.error('Conflict check error:', e);
      }

      try {
        const res = await fetch('/api/whatsapp/schedule_quiz', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            time: timeVal,
            times: allTimes,
            label: label || (timeVal + ' Daily ' + cat + ' Drill'),
            category: cat,
            target_group_ids: gids,
            is_question: true,
            auto_mode: isAuto,
            days_duration: daysDur
          })
        });
        const d = await res.json();
        if (d.ok) {
          alert(`⏰ Successfully scheduled ${allTimes.length} daily recurring slot(s): ${allTimes.join(', ')}!\\nMode: ${isAuto ? 'Auto Continuous (Always-On)' : daysDur + ' Days'}`);
          document.getElementById('clock-slot-label').value = '';
          document.getElementById('clock-extra-times').value = '';
          const alertBox = document.getElementById('sched-conflict-alert');
          if (alertBox) alertBox.style.display = 'none';
          loadSchedules();
        }
      } catch (e) {
        alert('Failed to schedule: ' + e);
      }
    }

    // 🛠️ ADVANCED VISUAL SCHEDULE BUILDER
    let sbSelectedDays = 0;
    function toggleScheduleBuilder() {
      const el = document.getElementById('schedule-builder');
      el.style.display = el.style.display === 'none' ? 'block' : 'none';
      if (el.style.display === 'block') el.scrollIntoView({behavior: 'smooth', block: 'center'});
    }
    function durLabel(d) {
      if (d === 0) return '♾️ Life-Long — ఎప్పటికీ ఆగదు';
      if (d === 30) return '1 నెల (30 రోజులు) తర్వాత auto-stop';
      if (d === 60) return '2 నెలలు (60 రోజులు) తర్వాత auto-stop';
      if (d === 90) return '3 నెలలు (90 రోజులు) తర్వాత auto-stop';
      return d + ' రోజుల తర్వాత auto-stop';
    }
    // 🔁 From-To window లో రోజుకి N సార్లు — evenly spread times auto-compute
    function computeSlotTimes() {
      const fromT = document.getElementById('sb-time').value || '10:00';
      const toT = document.getElementById('sb-time-to').value;
      const n = Math.max(1, Math.min(parseInt(document.getElementById('sb-times-per-day').value) || 1, 12));
      if (!toT || n <= 1) return [fromT];
      const toMin = s => { const p = s.split(':'); return parseInt(p[0]) * 60 + parseInt(p[1]); };
      const f = toMin(fromT), t = toMin(toT);
      const span = t >= f ? (t - f) : (t + 1440 - f);  // overnight window కూడా support
      const step = span / (n - 1);
      const out = [];
      for (let i = 0; i < n; i++) {
        const m = Math.round(f + step * i) % 1440;
        out.push(String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'));
      }
      return Array.from(new Set(out));
    }
    function updateTimesPreview() {
      const times = computeSlotTimes();
      document.getElementById('sb-times-preview').textContent =
        '⏰ ' + times.length + ' slot' + (times.length > 1 ? 's రోజూ' : '') + ': ' + times.join(' · ');
    }
    function datesPicked() {
      const from = document.getElementById('sb-date-from').value;
      const to = document.getElementById('sb-date-to').value;
      const note = document.getElementById('sb-dur-note');
      if (to) {
        document.querySelectorAll('.sb-chip').forEach(b => { b.style.background = ''; b.style.color = ''; b.style.borderColor = ''; });
        document.getElementById('sb-custom-days').value = '';
        note.textContent = '✅ ' + (from ? from + ' నుంచి ' : 'ఈరోజు నుంచి ') + to + ' వరకు — ఆ తర్వాత auto-stop';
      } else if (from) {
        note.textContent = '✅ ' + from + ' నుంచి start — duration: ' + durLabel(sbSelectedDays);
      }
    }
    function selectDurChip(days, btn) {
      sbSelectedDays = days;
      document.getElementById('sb-date-to').value = '';
      document.getElementById('sb-custom-days').value = '';
      document.querySelectorAll('.sb-chip').forEach(b => { b.style.background = ''; b.style.color = ''; b.style.borderColor = ''; });
      if (btn) { btn.style.background = '#fbbf24'; btn.style.color = '#050811'; btn.style.borderColor = '#fbbf24'; }
      document.getElementById('sb-dur-note').textContent = '✅ ' + durLabel(days) + ' selected';
    }
    function customDurTyped() {
      const v = parseInt(document.getElementById('sb-custom-days').value);
      if (!isNaN(v) && v > 0) {
        sbSelectedDays = v;
        document.querySelectorAll('.sb-chip').forEach(b => { b.style.background = ''; b.style.color = ''; b.style.borderColor = ''; });
        document.getElementById('sb-dur-note').textContent = '✅ Custom: ' + durLabel(v) + ' selected';
      }
    }
    async function createScheduleFromBuilder() {
      const timeVal = document.getElementById('sb-time').value;
      if (!timeVal) return alert('⏰ From Time select చేయండి');
      const times = computeSlotTimes();
      const qCount = parseInt(document.getElementById('sb-count').value) || 5;
      const label = document.getElementById('sb-label').value.trim();
      const subjects = Array.from(document.querySelectorAll('.sb-subj:checked')).map(c => c.value);
      (document.getElementById('sb-subj-custom').value || '').toUpperCase().split(/[^A-Z0-9]+/).filter(Boolean).forEach(s => subjects.push(s));
      const weekdays = Array.from(document.querySelectorAll('.sb-weekday:checked')).map(c => Number(c.value));
      const cat = document.getElementById('wa-target-category').value;
      const gids = getSelectedGroupIds();
      const dateFrom = document.getElementById('sb-date-from').value;
      const dateTo = document.getElementById('sb-date-to').value;
      if (dateTo && dateFrom && dateTo < dateFrom) return alert('❌ To Date, From Date కంటే ముందు ఉండకూడదు!');
      const days = dateTo ? 0 : sbSelectedDays;

      try {
        const res = await fetch('/api/whatsapp/schedule_quiz', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            times: times,
            label: label || 'Daily Scheduled Drill',
            category: cat,
            target_group_ids: gids,
            is_question: true,
            questions_count: qCount,
            days_duration: days,
            auto_mode: !dateTo && days === 0,
            end_date: dateTo || '',
            start_date: dateFrom || '',
            subjects: subjects,
            weekdays: weekdays,
            answer_delay_minutes: parseInt(document.getElementById('sb-answer-delay').value || '5')
          })
        });
        const d = await res.json();
        if (d.ok) {
          const durTxt = dateTo ? ((dateFrom || 'ఈరోజు') + ' → ' + dateTo) : durLabel(days);
          alert('✅ ' + times.length + ' schedule(s) created!\\n⏰ ' + times.join(' · ') + '\\n📊 ' + qCount + ' questions ఒక్కో slot కి\\n📅 ' + durTxt);
          toggleScheduleBuilder();
          loadSchedules();
        }
      } catch (e) {
        alert('Failed to schedule: ' + e);
      }
    }

    async function toggleScheduleJob(id) {
      try {
        await fetch('/api/whatsapp/toggle_schedule', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id})
        });
        loadSchedules();
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    // ✏️ EDIT any schedule any time — duration presets: 0=Life-Long, 30=1 Month, 60=2 Months...
    async function editScheduleJob(id) {
      try {
        const res = await fetch('/api/whatsapp/schedules');
        const d = await res.json();
        const j = (d.jobs || []).find(x => x.id === id);
        if (!j) return alert('Job దొరకలేదు');
        const time = prompt('⏰ Time (HH:MM, 24hr):', j.time); if (time === null) return;
        const count = prompt('📊 ఒక్కో slot కి ఎన్ని questions? (1-20):', j.questions_count || 5); if (count === null) return;
        const days = prompt('📅 ఎన్ని రోజులు నడవాలి?\\n  0 = ♾️ LIFE-LONG (ఎప్పటికీ)\\n  2 = 2 రోజులు\\n  7 = 1 వారం\\n  15 = 15 రోజులు\\n  30 = 1 నెల\\n  60 = 2 నెలలు\\n  90 = 3 నెలలు\\n  (ఏ సంఖ్య అయినా పెట్టొచ్చు — 1 నుంచి 3650 వరకు)', j.days_duration || 0); if (days === null) return;
        const sdate = prompt('⏳ From Date — ఎప్పటి నుంచి start? (YYYY-MM-DD)\\nఖాళీ = వెంటనే/ఈరోజే:', j.start_date || ''); if (sdate === null) return;
        const edate = prompt('🏁 To Date — exact last day? (YYYY-MM-DD)\\nఖాళీ = పైన ఇచ్చిన days నుంచే లెక్క:', ''); if (edate === null) return;
        const subj = prompt('📚 Subjects (+ తో కలపండి): MATHS+REASONING+GK+CURRENT+ENGLISH+SCIENCE\\nఖాళీగా వదిలేస్తే = ALL subjects:', (j.subjects || []).join('+')); if (subj === null) return;
        const updates = {
          id: id,
          time: time.trim(),
          questions_count: parseInt(count) || 5,
          days_duration: parseInt(days) || 0,
          start_date: sdate.trim(),
          subjects: subj.trim() ? subj.trim().toUpperCase().split(/[^A-Z]+/).filter(Boolean) : []
        };
        if (edate.trim()) updates.end_date = edate.trim();
        const r = await fetch('/api/whatsapp/update_schedule', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(updates)
        });
        const dd = await r.json();
        const durMsg = updates.end_date ? ('📅 ' + (updates.start_date || 'ఈరోజు') + ' → ' + updates.end_date)
          : (updates.days_duration === 0 ? '♾️ Life-Long mode' : '📅 ' + updates.days_duration + ' రోజులు (auto-stop: ' + (dd.job.end_date || '') + ')');
        alert(dd.ok ? '✅ Schedule updated! ' + durMsg + (updates.start_date ? ' · ⏳ Starts ' + updates.start_date : '') : '❌ ' + (dd.error || 'failed'));
        loadSchedules();
        loadTgAutopilotJobs();
      } catch (e) { alert('❌ ' + e); }
    }

    async function loadSchedules() {
      try {
        const res = await fetch('/api/whatsapp/schedules');
        const d = await res.json();
        const listEl = document.getElementById('wa-schedules-list');
        if (!listEl) return;

        const jobs = d.jobs || [];
        if (jobs.length === 0) {
          listEl.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:10px;">No daily recurring slots configured yet. Click "Add New Daily Quiz Slot" above!</div>';
          return;
        }

        listEl.innerHTML = jobs.map(j => {
          const isEn = j.enabled !== false;
          const statusBadge = isEn 
            ? '<span style="background:#10b981; color:#050811; font-weight:800; font-size:10px; padding:2px 6px; border-radius:10px;">● ACTIVE</span>'
            : '<span style="background:#64748b; color:white; font-weight:800; font-size:10px; padding:2px 6px; border-radius:10px;">○ PAUSED</span>';

          const modeBadge = j.auto_mode || (!j.days_duration && !j.end_date)
            ? '<span style="background:#0284c7; color:white; font-size:10px; font-weight:700; padding:1px 6px; border-radius:8px;">♾️ LIFE-LONG</span>'
            : `<span style="background:#d97706; color:white; font-size:10px; font-weight:700; padding:1px 6px; border-radius:8px;">📅 ${j.days_duration}d → ${j.end_date || ''}</span>`;
          const today = new Date().toISOString().slice(0, 10);
          const startBadge = (j.start_date && j.start_date > today)
            ? `<span style="background:#7c3aed; color:white; font-size:10px; font-weight:700; padding:1px 6px; border-radius:8px;">⏳ Starts ${j.start_date}</span>` : '';

          const targetLabel = (j.target_group_ids && j.target_group_ids.length > 0)
            ? `${j.target_group_ids.length} Selected Groups`
            : `All ${j.category || 'General'} Groups`;
          const subjLabel = (j.subjects && j.subjects.length) ? j.subjects.join('+') : 'ALL subjects';

          return `
            <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.06); flex-wrap:wrap; gap:8px;">
              <div>
                <div style="display:flex; align-items:center; gap:8px;">
                  <span style="font-size:15px; font-weight:800; color:#38bdf8; font-family:monospace;">${j.time}</span>
                  <b>${j.label || 'Daily Exam Drill'}</b>
                  ${statusBadge}
                  ${modeBadge}
                  ${startBadge}
                </div>
                <div style="font-size:11px; color:var(--text-muted); margin-top:3px;">
                  Category: <span class="category-tag">${j.category || 'ALL'}</span> · Target: <b>${targetLabel}</b> · <b>${j.questions_count || 5}</b> polls/slot · 📚 ${subjLabel} · Dispatches: <b>${j.total_dispatches || 0} times</b>
                </div>
              </div>
              <div style="display:flex; gap:6px;">
                <button class="btn btn-outline" style="padding:3px 8px; font-size:11px; color:#fbbf24; border-color:#fbbf24;" onclick="editScheduleJob('${j.id}')">✏️ Edit</button>
                <button class="btn btn-outline" style="padding:3px 8px; font-size:11px;" onclick="toggleScheduleJob('${j.id}')">${isEn ? '⏸ Pause' : '▶ Enable'}</button>
                <button class="btn btn-outline" style="padding:3px 8px; font-size:11px; color:#ef4444;" onclick="deleteScheduleJob('${j.id}')">🗑 Delete</button>
              </div>
            </div>
          `;
        }).join('');
        try { renderMissionHome(); } catch (e2) {}
      } catch (e) {
        console.error(e);
      }
    }

    async function deleteScheduleJob(id) {
      if (!confirm('Cancel this scheduled quiz?')) return;
      try {
        await fetch('/api/whatsapp/delete_schedule', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id})
        });
        loadSchedules();
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    let uploadedExcelBase64 = '';
    let uploadedExcelSheets = [];
    let bulkAttachmentBase64 = '';
    let bulkAttachmentFileName = '';

    function handleMainExcelFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;
      document.getElementById('selected-file-label').innerText = file.name + ' (' + Math.round(file.size / 1024) + ' KB)';
      
      const isXlsx = file.name.toLowerCase().endsWith('.xlsx') || file.name.toLowerCase().endsWith('.xls');
      if (isXlsx) {
        const reader = new FileReader();
        reader.onload = async function(e) {
          const arrayBuffer = e.target.result;
          const bytes = new Uint8Array(arrayBuffer);
          let binary = '';
          for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
          }
          uploadedExcelBase64 = btoa(binary);
          await inspectUploadedExcel(uploadedExcelBase64, file.name);
        };
        reader.readAsArrayBuffer(file);
      } else {
        const reader = new FileReader();
        reader.onload = async function(e) {
          const text = e.target.result;
          document.getElementById('excel-paste-text').value = text;
          await importExcelSheet();
        };
        reader.readAsText(file);
      }
    }

    async function inspectUploadedExcel(b64, fname) {
      const log = document.getElementById('excel-import-log');
      log.innerText = 'Inspecting workbook sheets in ' + fname + '...';
      try {
        const res = await fetch('/api/excel/inspect', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({file_b64: b64, filename: fname})
        });
        const d = await res.json();
        if (!d.ok) {
          log.innerText = '❌ Failed to inspect excel: ' + (d.error || 'Unknown error');
          return;
        }
        uploadedExcelSheets = d.sheets || [];
        const panel = document.getElementById('multisheet-panel');
        const container = document.getElementById('multisheet-checkboxes');
        container.innerHTML = '';
        
        uploadedExcelSheets.forEach(s => {
          const div = document.createElement('div');
          div.style = 'display:flex; align-items:center; gap:8px; background:#1e293b; padding:8px 12px; border-radius:6px;';
          div.innerHTML = `
            <input type="checkbox" class="excel-sheet-check" id="sheet-chk-${s.name}" value="${s.name}" checked>
            <label for="sheet-chk-${s.name}" style="font-size:12px; font-weight:600; cursor:pointer;">
              📄 ${s.name} <span style="color:#a7f3d0; font-size:11px;">(${s.rows_count} rows)</span>
            </label>
          `;
          container.appendChild(div);
        });
        panel.style.display = 'block';
        log.innerText = `✅ Found ${uploadedExcelSheets.length} sheet(s) in workbook! Select the sheets you want to import below.`;
      } catch (e) {
        log.innerText = '❌ Error reading sheets: ' + e;
      }
    }

    function selectAllSheets(val) {
      document.querySelectorAll('.excel-sheet-check').forEach(c => c.checked = val);
    }

    async function importSelectedExcelSheets() {
      const selected = Array.from(document.querySelectorAll('.excel-sheet-check:checked')).map(c => c.value);
      if (selected.length === 0) return alert('Please select at least one sheet to import!');
      const log = document.getElementById('excel-import-log');
      log.innerText = `Importing ${selected.length} sheet(s) into database...`;

      try {
        const res = await fetch('/api/excel/import_selected', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({file_b64: uploadedExcelBase64, sheets: selected})
        });
        const d = await res.json();
        if (d.ok) {
          const schedCount = (d.schedules_created || []).length;
          const schedMsg = schedCount
            ? ` · ⏰ <b style="color:#a78bfa;">${schedCount} daily auto-schedule(s) created</b> (Daily Times column నుంచి — ఇక రోజూ ఆటోమేటిక్‌గా వెళ్తాయి!)`
            : '';
          log.innerHTML = `<span style="color:#10b981; font-weight:700;">✅ Success! Imported ${d.imported_groups_count} WhatsApp Groups and ${d.imported_channels_count} Telegram Channels across ${d.sheets_processed.length} sheets!${schedMsg}</span>`;
          fetchStats();
          loadWAGroups();
          loadChannels();
          await loadBulkTargets();
          toggleAllBulkTargets(true);  // auto-select everything incl. newly imported
        } else {
          log.innerText = '❌ Import failed: ' + (d.error || 'Unknown error');
        }
      } catch (e) {
        log.innerText = '❌ Request failed: ' + e;
      }
    }

    function handleBulkAttachmentSelect(event) {
      const file = event.target.files[0];
      if (!file) return;
      bulkAttachmentFileName = file.name;
      document.getElementById('bulk-file-name').innerText = file.name;
      document.getElementById('bulk-clear-file-btn').style.display = 'inline-block';

      const reader = new FileReader();
      reader.onload = function(e) {
        const arrayBuffer = e.target.result;
        const bytes = new Uint8Array(arrayBuffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        bulkAttachmentBase64 = btoa(binary);
      };
      reader.readAsArrayBuffer(file);
    }

    function clearBulkAttachment() {
      bulkAttachmentBase64 = '';
      bulkAttachmentFileName = '';
      document.getElementById('bulk-attachment-file').value = '';
      document.getElementById('bulk-file-name').innerText = 'No file selected';
      document.getElementById('bulk-clear-file-btn').style.display = 'none';
    }

    let cachedBulkChannels = [];
    let cachedBulkGroups = [];
    let cachedBundles = [];

    async function quickAddGroups() {
      const txt = document.getElementById('quick-add-links').value.trim();
      const out = document.getElementById('quick-add-result');
      if (!txt) return alert('WhatsApp invite links paste చేయండి (ఒక్కో line కి ఒకటి)!');
      out.innerHTML = '<span style="color:#38bdf8;">⏳ Adding groups... (bridge connected అయితే bot auto-join అవుతుంది, కొన్ని సెకన్లు పడుతుంది)</span>';
      try {
        const res = await fetch('/api/whatsapp/quick_add', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({text: txt})
        });
        const d = await res.json();
        if (!d.ok && d.error) { out.innerHTML = '<span style="color:#ef4444;">❌ ' + d.error + '</span>'; return; }
        let html = `<span style="color:#10b981; font-weight:700;">✅ ${d.added.length} group(s) added` +
                   (d.joined ? ` · 🤝 ${d.joined} auto-joined via invite link!` : '') + '</span>';
        d.added.forEach(g => {
          html += `<div style="color:#a7f3d0;">&nbsp;&nbsp;💬 ${g.name} <span style="color:#64748b;">[${g.category}]${g.joined ? ' · ✓JOINED' : ''}${g.participants ? ' · 👥 ' + g.participants : ''}</span></div>`;
        });
        (d.failed || []).forEach(f => {
          html += `<div style="color:#f87171;">&nbsp;&nbsp;⚠️ ${f.line.slice(0, 60)} → ${f.error}</div>`;
        });
        out.innerHTML = html;
        if (d.added.length) {
          document.getElementById('quick-add-links').value = '';
          loadWAGroups();
          fetchStats();
          await loadBulkTargets();  // new groups auto-selected by the sticky engine
        }
      } catch (e) {
        out.innerHTML = '<span style="color:#ef4444;">❌ ' + e + '</span>';
      }
    }

    async function loadBulkTargets() {
      try {
        const [chRes, waRes, bRes] = await Promise.all([
          fetch('/api/channels'),
          fetch('/api/whatsapp/groups'),
          fetch('/api/bundles')
        ]);
        const chData = await chRes.json();
        const waData = await waRes.json();
        const bData = await bRes.json();

        cachedBulkChannels = Object.entries(chData.channels || {});
        cachedBulkGroups = waData.groups || [];
        cachedBundles = bData.bundles || [];

        // Populate Bundle Presets Dropdown
        const bSel = document.getElementById('bulk-bundle-selector');
        if (bSel) {
          bSel.innerHTML = '<option value="">-- Choose a Saved Group Bundle --</option>' +
            cachedBundles.map(b => `<option value="${b.id}">${b.name} (${(b.target_groups||[]).length} Groups, ${(b.target_channels||[]).length} Channels)</option>`).join('');
        }

        renderBulkTargetsList();
        populateBundleCreatorMembers();
      } catch (e) {
        console.error('Error loading bulk targets:', e);
      }
    }

    // ------- STICKY SELECTION ENGINE: search/filter చేసినా selection పోదు -------
    let bulkSelCh = null;   // Set of selected Telegram channel keys
    let bulkSelWa = null;   // Set of selected WhatsApp group ids

    function initBulkSelection() {
      if (bulkSelCh !== null && bulkSelWa !== null) { autoSelectNewBulkItems(); return; }
      // restore last selection from this browser; default = everything selected
      try {
        const saved = JSON.parse(localStorage.getItem('su_bulk_sel') || 'null');
        if (saved && Array.isArray(saved.ch) && Array.isArray(saved.wa)) {
          bulkSelCh = new Set(saved.ch);
          bulkSelWa = new Set(saved.wa);
          autoSelectNewBulkItems();
          return;
        }
      } catch (e) {}
      bulkSelCh = new Set(cachedBulkChannels.map(([k]) => k));
      bulkSelWa = new Set(cachedBulkGroups.map(g => g.id));
      persistBulkSelection();
    }

    // Any group/channel seen for the FIRST time (new sync/import) is auto-selected
    function autoSelectNewBulkItems() {
      let known = {ch: [], wa: []};
      try { known = JSON.parse(localStorage.getItem('su_bulk_known') || '{"ch":[],"wa":[]}'); } catch (e) {}
      const knownCh = new Set(known.ch || []), knownWa = new Set(known.wa || []);
      let changed = false;
      cachedBulkChannels.forEach(([k]) => { if (!knownCh.has(k)) { bulkSelCh.add(k); knownCh.add(k); changed = true; } });
      cachedBulkGroups.forEach(g => { if (!knownWa.has(g.id)) { bulkSelWa.add(g.id); knownWa.add(g.id); changed = true; } });
      if (changed) {
        try { localStorage.setItem('su_bulk_known', JSON.stringify({ch: [...knownCh], wa: [...knownWa]})); } catch (e) {}
        persistBulkSelection();
      }
    }

    function persistBulkSelection() {
      try {
        localStorage.setItem('su_bulk_sel', JSON.stringify({ch: [...bulkSelCh], wa: [...bulkSelWa]}));
      } catch (e) {}
    }

    function toggleBulkSel(kind, key, on) {
      const set = kind === 'ch' ? bulkSelCh : bulkSelWa;
      if (on) set.add(key); else set.delete(key);
      persistBulkSelection();
      updateBulkSelectedBadge();
      checkBulkConflictsLive();
    }

    function getVisibleBulkItems() {
      const q = (document.getElementById('bulk-target-search')?.value || '').toLowerCase();
      const cat = document.getElementById('bulk-cat-filter')?.value || 'ALL';
      const ch = cachedBulkChannels.filter(([key, c]) => {
        const nameMatch = c.name.toLowerCase().includes(q) || key.toLowerCase().includes(q);
        const catMatch = cat === 'ALL' || (c.exam_type && c.exam_type.toUpperCase().includes(cat)) || (c.name.toUpperCase().includes(cat));
        return nameMatch && catMatch;
      });
      const wa = cachedBulkGroups.filter(g => {
        const nameMatch = g.name.toLowerCase().includes(q) || (g.jid || '').toLowerCase().includes(q);
        const catMatch = cat === 'ALL' || (g.category && g.category.toUpperCase() === cat.toUpperCase());
        return nameMatch && catMatch;
      });
      return {ch, wa};
    }

    function renderBulkTargetsList() {
      const chList = document.getElementById('bulk-channels-list');
      const waList = document.getElementById('bulk-groups-list');
      if (!chList || !waList) return;
      initBulkSelection();

      const vis = getVisibleBulkItems();
      chList.innerHTML = '';
      waList.innerHTML = '';

      vis.ch.forEach(([key, ch]) => {
        const sel = bulkSelCh.has(key);
        const div = document.createElement('div');
        div.className = 'bulk-target-item';
        div.style = `display:flex; align-items:center; gap:8px; font-size:12px; padding:5px 8px; border-radius:6px; cursor:pointer; border:1px solid ${sel ? 'rgba(56,189,248,0.4)' : 'transparent'}; background:${sel ? 'rgba(56,189,248,0.08)' : 'transparent'};`;
        div.innerHTML = `
          <input type="checkbox" class="bulk-target-ch" value="${key}" ${sel ? 'checked' : ''} style="pointer-events:none;">
          <span style="flex:1;">${ch.chat_type === 'group' ? '💬' : '📢'} <b>${ch.name}</b> ${ch.chat_type === 'group' ? '<span style="color:#6ee7b7; font-size:9px; font-weight:800;">TG GROUP</span>' : ''} <span style="color:#64748b;">(${ch.chat_id || key})</span></span>
        `;
        div.onclick = () => {
          const cb = div.querySelector('input');
          cb.checked = !cb.checked;
          toggleBulkSel('ch', key, cb.checked);
          div.style.background = cb.checked ? 'rgba(56,189,248,0.08)' : 'transparent';
          div.style.border = cb.checked ? '1px solid rgba(56,189,248,0.4)' : '1px solid transparent';
        };
        chList.appendChild(div);
      });
      document.getElementById('bulk-channels-count').innerText = vis.ch.length;

      vis.wa.forEach(g => {
        const sel = bulkSelWa.has(g.id);
        const div = document.createElement('div');
        div.className = 'bulk-target-item';
        div.style = `display:flex; align-items:center; gap:8px; font-size:12px; padding:5px 8px; border-radius:6px; cursor:pointer; border:1px solid ${sel ? 'rgba(16,185,129,0.4)' : 'transparent'}; background:${sel ? 'rgba(16,185,129,0.08)' : 'transparent'};`;
        const members = g.participants ? ` <span style="color:#64748b; font-size:10px;">👥 ${g.participants}</span>` : '';
        const realTag = g.real ? ' <span style="color:#10b981; font-size:9px; font-weight:800;" title="Synced from real WhatsApp">✓REAL</span>' : '';
        div.innerHTML = `
          <input type="checkbox" class="bulk-target-wa" value="${g.id}" ${sel ? 'checked' : ''} style="pointer-events:none;">
          <span style="flex:1;">💬 <b>${esc(g.name)}</b> <span style="color:#10b981; font-size:10px; font-weight:700;">[${esc(g.category || 'GENERAL')}]</span>${members}${realTag}</span>
        `;
        div.onclick = () => {
          const cb = div.querySelector('input');
          cb.checked = !cb.checked;
          toggleBulkSel('wa', g.id, cb.checked);
          div.style.background = cb.checked ? 'rgba(16,185,129,0.08)' : 'transparent';
          div.style.border = cb.checked ? '1px solid rgba(16,185,129,0.4)' : '1px solid transparent';
        };
        waList.appendChild(div);
      });
      document.getElementById('bulk-groups-count').innerText = vis.wa.length;
      updateBulkSelectedBadge();
    }

    function filterBulkTargetList() {
      renderBulkTargetsList();
    }

    function updateBulkSelectedBadge() {
      initBulkSelection();
      // prune ids that no longer exist
      const chKeys = new Set(cachedBulkChannels.map(([k]) => k));
      const waIds = new Set(cachedBulkGroups.map(g => g.id));
      bulkSelCh.forEach(k => { if (!chKeys.has(k)) bulkSelCh.delete(k); });
      bulkSelWa.forEach(k => { if (!waIds.has(k)) bulkSelWa.delete(k); });
      const badge = document.getElementById('bulk-selected-count-badge');
      if (badge) badge.innerText = `✅ ${bulkSelCh.size + bulkSelWa.size} selected (${bulkSelCh.size} Ch, ${bulkSelWa.size} Grp)`;
    }

    function selectVisibleBulkTargets(on) {
      const vis = getVisibleBulkItems();
      vis.ch.forEach(([key]) => { if (on) bulkSelCh.add(key); else bulkSelCh.delete(key); });
      vis.wa.forEach(g => { if (on) bulkSelWa.add(g.id); else bulkSelWa.delete(g.id); });
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive();
    }

    function applySelectedBundle(bundleId) {
      if (!bundleId) return;
      const b = cachedBundles.find(x => x.id === bundleId);
      if (!b) return;

      initBulkSelection();
      bulkSelWa = new Set(b.target_groups || []);
      bulkSelCh = new Set(b.target_channels || []);
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive(bundleId);
    }

    async function checkBulkConflictsLive(activeBundleId = '') {
      const waGids = (initBulkSelection(), [...bulkSelWa]);
      const chKeys = (initBulkSelection(), [...bulkSelCh]);
      const alertBox = document.getElementById('bulk-conflict-alert');
      const msgBox = document.getElementById('bulk-conflict-msg');
      if (!alertBox || !msgBox) return;

      if (waGids.length === 0 && chKeys.length === 0) {
        alertBox.style.display = 'none';
        return;
      }

      try {
        const res = await fetch('/api/whatsapp/check_conflicts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            target_group_ids: waGids,
            target_channel_keys: chKeys,
            bundle_id: activeBundleId
          })
        });
        const d = await res.json();
        if (d.has_conflicts) {
          const warnText = d.conflicts.map(c => `${c.message} (${(c.conflicting_groups||[]).length} items)`).join('; ');
          msgBox.innerHTML = warnText;
          alertBox.style.display = 'block';
        } else {
          alertBox.style.display = 'none';
        }
      } catch (e) {
        console.error(e);
      }
    }

    function toggleAllBulkTargets(val) {
      initBulkSelection();
      bulkSelCh = val ? new Set(cachedBulkChannels.map(([k]) => k)) : new Set();
      bulkSelWa = val ? new Set(cachedBulkGroups.map(g => g.id)) : new Set();
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive();
    }

    function selectBulkChannelsOnly() {
      initBulkSelection();
      bulkSelCh = new Set(cachedBulkChannels.map(([k]) => k));
      bulkSelWa = new Set();
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive();
    }

    function selectBulkWAGroupsOnly() {
      initBulkSelection();
      bulkSelCh = new Set();
      bulkSelWa = new Set(cachedBulkGroups.map(g => g.id));
      persistBulkSelection();
      renderBulkTargetsList();
      checkBulkConflictsLive();
    }

    async function sendBulkQuizPollsToTargets() {
      const chKeys = (initBulkSelection(), [...bulkSelCh]);
      const waGids = (initBulkSelection(), [...bulkSelWa]);
      const pollCount = parseInt(document.getElementById('poll-count-select')?.value || '5', 10);
      const pollSubjects = Array.from(document.querySelectorAll('.poll-subj:checked')).map(c => c.value);

      if (chKeys.length === 0 && waGids.length === 0) {
        return alert('Please select at least one Telegram Channel or WhatsApp Group target!');
      }

      // Check collision before quiz dispatch
      try {
        const cRes = await fetch('/api/whatsapp/check_conflicts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({target_group_ids: waGids, target_channel_keys: chKeys})
        });
        const cData = await cRes.json();
        if (cData.has_conflicts) {
          const warn = cData.conflicts.map(c => c.message).join('\\n');
          const cont = confirm(`⚠️ Targets Conflict Notice:\\n${warn}\\n\\nDo you want to proceed anyway?`);
          if (!cont) return;
        }
      } catch (e) {
        console.error(e);
      }

      const subjLabel = pollSubjects.length ? pollSubjects.join(', ') : 'All Subjects';
      if (!confirm(`🚀 Launch ${pollCount}-poll quiz dispatch?\n• Subjects: ${subjLabel}\n• ${chKeys.length} Telegram Channels (instant) + ${waGids.length} WhatsApp Groups (${gapLabel()} gaps)`)) return;

      const log = document.getElementById('bulk-broadcast-log');
      log.innerText = `Starting live quiz rounds on selected targets...`;

      // 1. Dispatch Telegram Channels
      if (chKeys.length > 0) {
        for (const k of chKeys) {
          try {
            await fetch('/api/post_poll', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({channel: k, count: pollCount, subjects: pollSubjects})
            });
          } catch (e) {
            console.error('Channel post error:', e);
          }
        }
      }

      // 2. Dispatch WhatsApp Groups via Anti-Ban Engine
      if (waGids.length > 0) {
        try {
          const gw = document.getElementById('wa-gateway-input')?.value || '';
          await fetch('/api/whatsapp/start_pipeline', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              target_group_ids: waGids,
              is_question: true,
              gateway: gw,
              delay_min: getGapMin(),
              delay_max: getGapMax(),
              questions_count: pollCount,
              subjects: pollSubjects
            })
          });
        } catch (e) {
          console.error('WhatsApp dispatch error:', e);
        }
      }

      log.innerText = `✅ ${pollCount}-Poll Exam Rounds (${subjLabel}) → ${chKeys.length} Channels (instant) + ${waGids.length} WhatsApp Groups (anti-ban queue)!`;
      alert(`✅ Exam Polls launched! ${chKeys.length} Channels + ${waGids.length} Groups · Subjects: ${subjLabel}`);
    }

    async function sendBulkBroadcast() {
      const msg = document.getElementById('bulk-broadcast-msg').value.trim();
      const attUrl = document.getElementById('bulk-attachment-url').value.trim();
      const log = document.getElementById('bulk-broadcast-log');

      if (!msg && !attUrl && !bulkAttachmentBase64) {
        return alert('Please write a message or attach a file/URL to broadcast!');
      }

      const chKeys = (initBulkSelection(), [...bulkSelCh]);
      const waGids = (initBulkSelection(), [...bulkSelWa]);

      if (chKeys.length === 0 && waGids.length === 0) {
        return alert('Please select at least one Channel or WhatsApp Group target!');
      }

      // Check collision before dispatching
      try {
        const cRes = await fetch('/api/whatsapp/check_conflicts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({target_group_ids: waGids, target_channel_keys: chKeys})
        });
        const cData = await cRes.json();
        if (cData.has_conflicts) {
          const warn = cData.conflicts.map(c => c.message).join('\\n');
          const cont = confirm(`⚠️ Targets Conflict Notice:\\n${warn}\\n\\nDo you want to proceed with dispatch anyway?`);
          if (!cont) return;
        }
      } catch (e) {
        console.error(e);
      }

      if (!confirm(`Confirm dispatch to ${chKeys.length} Telegram Channels and ${waGids.length} WhatsApp Groups?`)) return;

      log.innerText = `Dispatching across ${chKeys.length} channels and ${waGids.length} groups...`;

      try {
        const res = await fetch('/api/broadcast/dispatch', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            message: msg,
            attachment_url: attUrl,
            attachment_data_b64: bulkAttachmentBase64,
            attachment_filename: bulkAttachmentFileName,
            target_channel_keys: chKeys,
            target_group_ids: waGids
          })
        });
        const d = await res.json();
        let logTxt = `✅ Broadcast Launched!\\n• Telegram Channels Dispatched: ${d.telegram_dispatched}\\n• WhatsApp Groups Queued: ${d.whatsapp_dispatched}`;
        if (d.whatsapp_note) logTxt += `\\nℹ️ ${d.whatsapp_note}`;
        if (d.errors && d.errors.length > 0) {
          logTxt += `\\n⚠️ Notes/Errors (${d.errors.length}):\\n` + d.errors.slice(0, 5).join('\\n');
        }
        log.innerText = logTxt;
        alert(`Dispatched successfully to ${d.telegram_dispatched} Channels and ${d.whatsapp_dispatched} WhatsApp Groups!`);
      } catch (e) {
        log.innerText = '❌ Broadcast failed: ' + e;
      }
    }

    async function importExcelSheet() {
      const raw = document.getElementById('excel-paste-text').value.trim();
      const log = document.getElementById('excel-import-log');
      if (!raw) return alert('Paste your Excel or Google Sheet lines first');
      log.innerText = 'Importing rows into database...';
      const res = await fetch('/api/excel/import', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({raw_text: raw})
      });
      const d = await res.json();
      const sc = (d.schedules_created || []).length;
      log.innerText = '✅ Success! Imported ' + d.imported_groups_count + ' WhatsApp Groups and ' + d.imported_channels_count + ' Telegram Channels.' +
        (sc ? ' ⏰ ' + sc + ' daily auto-schedule(s) created!' : '');
      fetchStats();
      loadWAGroups();
    }

    function handleExcelFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async function(e) {
        const text = e.target.result;
        document.getElementById('wa-direct-excel-paste').value = text;
        await importInTabExcel();
      };
      reader.readAsText(file);
    }

    function handleMainExcelFileUpload(event) {
      const file = event.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = async function(e) {
        const text = e.target.result;
        document.getElementById('excel-paste-text').value = text;
        await importExcelSheet();
      };
      reader.readAsText(file);
    }

    async function importInTabExcel() {
      const raw = document.getElementById('wa-direct-excel-paste').value.trim();
      const statusEl = document.getElementById('wa-excel-status-log');
      if (!raw) return alert('Paste your Excel / CSV rows or choose a file first!');
      statusEl.style.color = '#38bdf8';
      statusEl.innerText = 'Importing rows into WhatsApp database...';

      try {
        const res = await fetch('/api/excel/import', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({raw_text: raw})
        });
        const d = await res.json();
        statusEl.style.color = '#10b981';
        statusEl.innerText = `✅ Successfully imported ${d.imported_groups_count || 0} WhatsApp Groups!`;
        document.getElementById('wa-direct-excel-paste').value = '';
        fetchStats();
        loadWAGroups();
        await loadBulkTargets();
      } catch (e) {
        statusEl.style.color = '#ef4444';
        statusEl.innerText = '❌ Import failed: ' + e;
      }
    }

    async function createCampusEvent() {
      const college = document.getElementById('campus-college-name').value.trim();
      const district = document.getElementById('campus-district').value.trim();
      if (!college) return alert('College name ఎంటర్ చేయండి!');
      if (!district) return alert('District ఎంటర్ చేయండి!');
      const nq = parseInt(document.getElementById('campus-nq').value || '10', 10);
      const startAt = document.getElementById('campus-start-at')?.value || '';
      const neg = parseInt(document.getElementById('campus-neg')?.value || '0', 10);
      const level = document.getElementById('campus-level').value || 'easy';
      const subjects = [];
      if (document.getElementById('subj-reasoning')?.checked) subjects.push('reasoning');
      if (document.getElementById('subj-quant')?.checked) subjects.push('quant');
      if (document.getElementById('subj-science')?.checked) subjects.push('science');
      if (document.getElementById('subj-english')?.checked) subjects.push('english');
      if (document.getElementById('subj-ca')?.checked) subjects.push('ca');
      if (document.getElementById('subj-coding')?.checked) subjects.push('coding');
      if (subjects.length === 0) return alert('కనీసం ఒక subject select చేయండి!');

      const card = document.getElementById('campus-active-card');
      card.innerHTML = '<div style="color:#38bdf8;">⏳ Generating exam, link & QR...</div>';
      try {
        const res = await fetch('/api/campus/create', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({college, district, n_q: nq, level, subjects, start_at: startAt, neg})
        });
        const d = await res.json();
        if (!d.ok) { card.innerHTML = '<div style="color:#ef4444;">❌ ' + (d.error || 'Failed') + '</div>'; return; }
        card.innerHTML = `
          <div style="display:flex; gap:16px; align-items:center; flex-wrap:wrap;">
            <img src="${d.web_qr || d.qr}" onerror="this.outerHTML='<div style=\"color:#facc15; font-size:12px;\">⚠️ QR unavailable — use the join link.</div>'" style="width:150px; height:150px; border-radius:8px; background:white; padding:5px; border:2px solid #10b981;">
            <div style="flex:1; min-width:200px;">
              <div style="font-size:14px; font-weight:800; color:#10b981;">✅ ${d.college} — Exam Ready!</div>
              <div style="margin:6px 0; font-size:12px;">Code: <b style="color:#facc15;">${d.code}</b>${d.colleges && d.colleges.length > 1 ? ` · 🏫 ${d.colleges.join(' vs ')}` : ''}</div>
              <div style="font-size:11px; word-break:break-all; color:#10b981;">🌐 ${d.web_link || d.link}</div>
              <div style="font-size:11px; word-break:break-all; color:#38bdf8;">🤖 ${d.link}</div>
              <div style="display:flex; gap:6px; margin-top:8px; flex-wrap:wrap;">
                <button class="btn btn-accent" style="padding:4px 10px; font-size:11px;" onclick="navigator.clipboard.writeText('${d.web_link || d.link}').then(()=>alert('✅ Web Link copied!'))">🌐 Copy Web Link</button>
                <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="navigator.clipboard.writeText('${d.link}').then(()=>alert('✅ Telegram Link copied!'))">🤖 Telegram Link</button>
                <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="navigator.clipboard.writeText(decodeURIComponent('${encodeURIComponent(d.poster || d.link)}')).then(()=>alert('✅ Poster copied — WhatsApp groups lo paste cheyyandi!'))">📢 Copy WhatsApp Poster</button>
                ${d.start_at ? `<span style="font-size:11px; color:#facc15;">⏰ Auto-start: ${d.start_at.replace('T', ' ')}</span>` : ''}
                ${d.neg ? `<span style="font-size:11px; color:#f87171;">⚠️ Negative marking: −${d.neg} pt / wrong answer</span>` : ''}
                <a href="${d.web_qr || d.qr}&dl=1" class="btn btn-outline" style="padding:4px 10px; font-size:11px; text-decoration:none;">📥 Download Web QR</a>
                <button class="btn btn-primary" style="padding:4px 10px; font-size:11px;" onclick="startCampusExam('${d.code}')">🚀 Start Exam</button>
                <button class="btn btn-accent" style="padding:4px 10px; font-size:11px;" onclick="viewCampusReport('${d.code}')">📊 Marks</button>
                <a href="https://wa.me/?text=${encodeURIComponent('🏫 ' + d.college + ' Exam — browser lone rayachu, app akkarledu! Join: ' + (d.web_link || d.link))}" target="_blank" class="btn btn-purple" style="padding:4px 10px; font-size:11px; text-decoration:none;">📲 Share on WhatsApp</a>
              </div>
              ${d.bot_warning ? `<div style="margin-top:8px; color:#facc15; font-size:11px;">⚠️ ${d.bot_warning}</div>` : ''}
              <div style="margin-top:8px; font-size:11px; color:var(--text-muted); line-height:1.7;">
                <b style="color:#e2e8f0;">Next steps:</b> 1️⃣ QR/link ni WhatsApp group lo share cheyyandi →
                2️⃣ Students scan chesi <b style="color:#10b981;">browser lone peru + mobile</b> istharu (Telegram app akkarledu!) — Telegram unna vallu 🤖 Telegram Link kuda vadachu, rendu okkate exam →
                3️⃣ Hall ready ayyaka mee <b>🚀 Start Exam</b> →
                4️⃣ Exam ayyaka <b>📊 Marks</b> lo అందరి results + Excel download.
              </div>
            </div>
          </div>`;
        loadCampusEvents();
      } catch (e) {
        card.innerHTML = '<div style="color:#ef4444;">❌ ' + e + '</div>';
      }
    }

    async function startCampusExam(code) {
      if (!confirm('🚀 ' + code + ' exam ippude start cheyyala? Join ayyi registration complete chesina students andhariki bot lo questions vastayi.')) return;
      const card = document.getElementById('campus-active-card');
      try {
        const res = await fetch('/api/campus/start', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code})});
        const d = await res.json();
        if (d.ok) {
          card.innerHTML = '<div style="color:#10b981; font-size:13px;">🚀 <b>Exam LIVE!</b> ' + (d.info?.players ?? '') + ' students ki ' + (d.info?.questions ?? '') + ' questions vellthunnayi. Control Room open avthundi…</div>';
          watchCampusLive(code);
        } else {
          card.innerHTML = '<div style="color:#facc15; font-size:13px;">⏸️ Start avvaledu: ' + (d.message || 'unknown') + '<br><span style="color:var(--text-muted);">కనీసం 2 students QR scan chesi registration complete cheyyali.</span></div>';
        }
        loadCampusEvents();
      } catch (e) { card.innerHTML = '<div style="color:#ef4444;">❌ ' + e + '</div>'; }
    }

    let campusLiveTimer = null;
    let campusLiveCode = '';
    function stopCampusLive() { if (campusLiveTimer) { clearInterval(campusLiveTimer); campusLiveTimer = null; } }
    async function watchCampusLive(code) {
      stopCampusLive(); campusLiveCode = code;
      const card = document.getElementById('campus-active-card');
      const render = async () => {
        try {
          const res = await fetch('/api/campus/live?code=' + encodeURIComponent(code));
          const d = await res.json();
          if (!d.ok) { card.innerHTML = '<div style="color:#ef4444;">❌ Live data ledu</div>'; stopCampusLive(); return; }
          const L = d.live;
          if (L.state === 'done') { stopCampusLive(); viewCampusReport(code); return; }
          const pct = L.n_q ? Math.round(100 * (L.qi - (L.state === 'question' ? 1 : 0)) / L.n_q) : 0;
          const rows = (L.players || []).map((pl, i) => `<tr><td style="padding:2px 8px;">${['🥇','🥈','🥉'][i] || (i + 1)}</td><td style="padding:2px 8px;"><b>${pl.name}</b></td><td style="padding:2px 8px; color:#64748b;">${pl.college || ''}</td><td style="padding:2px 8px; color:#38bdf8;"><b>${pl.pts}</b> pts</td><td style="padding:2px 8px;">${pl.correct} ✅</td></tr>`).join('');
          card.innerHTML = `
            <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; align-items:center;">
              <div style="font-size:14px; font-weight:800; color:#f87171;">🔴 LIVE — ${L.name}</div>
              <div style="font-size:11px; color:var(--text-muted);">${L.shuffle ? '🔀 Anti-copy shuffle ON · ' : ''}👥 ${L.joined} students</div>
            </div>
            <div style="margin:8px 0; font-size:12px;">Question <b style="color:#facc15;">${L.qi}/${L.n_q}</b> · Answered now: <b style="color:#10b981;">${L.answered_now}/${L.joined}</b>${L.ends_in != null && L.state === 'question' ? ` · ⏱ ${L.ends_in}s left` : ''}</div>
            <div style="background:#1e293b; border-radius:99px; height:10px; overflow:hidden;"><div style="width:${pct}%; height:100%; background:linear-gradient(90deg,#10b981,#38bdf8);"></div></div>
            ${rows ? `<table style="width:100%; font-size:12px; border-collapse:collapse; margin-top:8px;"><tbody>${rows}</tbody></table>` : '<div style="font-size:12px; color:#64748b; margin-top:8px;">Answers vastunnayi…</div>'}
            <div style="display:flex; gap:6px; margin-top:10px; flex-wrap:wrap;">
              <button class="btn btn-accent" style="padding:4px 10px; font-size:11px;" onclick="controlCampus('${code}', 'next')">⏭ Next Question</button>
              <button class="btn btn-primary" style="padding:4px 10px; font-size:11px; background:#dc2626;" onclick="if(confirm('Exam ippude aapeyyala? Results ventane vellipothayi.')) controlCampus('${code}', 'finish')">🏁 Finish Exam Now</button>
              <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="stopCampusLive()">⏸ Stop Watching</button>
            </div>`;
        } catch (e) { /* next tick retries */ }
      };
      render();
      campusLiveTimer = setInterval(render, 5000);
    }

    async function controlCampus(code, action) {
      try {
        const res = await fetch('/api/campus/control', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code, action})});
        const d = await res.json();
        if (!d.ok) alert('❌ ' + (d.message || 'control failed'));
        if (action === 'finish') { stopCampusLive(); setTimeout(() => viewCampusReport(code), 1200); loadCampusEvents(); }
      } catch (e) { alert('❌ ' + e); }
    }

    async function loadCampusLeague() {
      const box = document.getElementById('campus-league-box');
      if (!box) return;
      try {
        const res = await fetch('/api/campus/league');
        const d = await res.json();
        const rows = d.league || [];
        if (!rows.length) { box.innerHTML = 'Inka okka exam kuda complete avvaledu — first exam ayyaka league ikkada kanipisthundi.'; return; }
        box.innerHTML = '<table style="width:100%; font-size:12px; border-collapse:collapse;"><thead><tr style="color:#64748b;"><th style="text-align:left; padding:3px 8px;">#</th><th style="text-align:left; padding:3px 8px;">College</th><th style="text-align:left; padding:3px 8px;">🏆 Wins</th><th style="text-align:left; padding:3px 8px;">Exams</th><th style="text-align:left; padding:3px 8px;">Students</th><th style="text-align:left; padding:3px 8px;">Avg Accuracy</th></tr></thead><tbody>' +
          rows.map((r, i) => `<tr><td style="padding:3px 8px;">${['🥇','🥈','🥉'][i] || (i + 1)}</td><td style="padding:3px 8px;"><b style="color:#e2e8f0;">${r.college}</b></td><td style="padding:3px 8px; color:#facc15;"><b>${r.wins}</b></td><td style="padding:3px 8px;">${r.events}</td><td style="padding:3px 8px;">${r.students}</td><td style="padding:3px 8px; color:#38bdf8;">${r.avg_acc}%</td></tr>`).join('') + '</tbody></table>';
      } catch (e) { box.innerHTML = 'League load avvaledu.'; }
    }

    async function viewCampusReport(code) {
      stopCampusLive();
      const card = document.getElementById('campus-active-card');
      card.innerHTML = '<div style="color:#38bdf8;">⏳ Loading report for ' + code + '...</div>';
      try {
        const res = await fetch('/api/campus/report?code=' + encodeURIComponent(code));
        const d = await res.json();
        const rep = d.report;
        if (!rep) { card.innerHTML = '<div style="color:#ef4444;">❌ Report not found for ' + code + '</div>'; return; }
        const players = rep.players || rep.top_players || [];
        let rows = players.slice(0, 50).map((pl, i) =>
          `<tr><td style="padding:3px 8px;">${['🥇','🥈','🥉'][i] || (i + 1)}</td><td style="padding:3px 8px;"><b>${pl.name || pl.user || '—'}</b>${pl.college ? ' <span style="color:#64748b;">· ' + pl.college + '</span>' : ''}</td><td style="padding:3px 8px; color:#38bdf8;"><b>${pl.score ?? pl.points ?? 0}/${pl.total ?? rep.n_q ?? ''}</b></td><td style="padding:3px 8px; color:#a78bfa;">${pl.pts ?? ''} pts</td></tr>`).join('');
        card.innerHTML = `
          <div style="font-size:14px; font-weight:800; color:#38bdf8;">📋 ${rep.name || code} — Principal Report</div>
          <div style="font-size:12px; color:var(--text-muted); margin:6px 0;">District: ${rep.district || '—'} · Joined: <b style="color:#10b981;">${rep.players_count ?? players.length}</b> · Answered: <b style="color:#10b981;">${rep.answered ?? players.length}</b> · Class Average: <b style="color:#facc15;">${rep.average_pct ?? 0}%</b> · Status: ${rep.state || '—'} &nbsp; <a href="/api/campus/excel?code=${code}" class="btn btn-outline" style="padding:2px 8px; font-size:11px; text-decoration:none;">⬇ Excel Marks Sheet</a> <button class="btn btn-outline" style="padding:2px 8px; font-size:11px;" onclick="retestCampus('${code}')">🔁 Retest (same settings)</button> <a href="/api/campus/poster?code=${code}" class="btn btn-outline" style="padding:2px 8px; font-size:11px; text-decoration:none;">🖼️ Result Poster</a>${rep.neg ? ` · <span style="color:#f87171;">⚠️ −${rep.neg}/wrong</span>` : ''}</div>
          ${rows ? `<table style="width:100%; font-size:12px; border-collapse:collapse; margin-top:6px;"><thead><tr style="color:#64748b;"><th style="text-align:left; padding:3px 8px;">#</th><th style="text-align:left; padding:3px 8px;">Student</th><th style="text-align:left; padding:3px 8px;">Score</th></tr></thead><tbody>${rows}</tbody></table>` : '<div style="font-size:12px; color:#64748b; margin-top:8px;">ఇంకా students join అవ్వలేదు — QR scan చేయగానే ఇక్కడ కనిపిస్తారు.</div>'}
          ${(rep.topic_stats && rep.topic_stats.length) ? `<div style="margin-top:10px; font-size:12px;"><b style="color:#38bdf8;">📚 Topic Performance:</b>${rep.topic_stats.map(t => `<div style="margin:4px 0;">${t.topic} — <b style="color:${t.pct >= 60 ? '#10b981' : (t.pct >= 40 ? '#facc15' : '#f87171')};">${t.pct}%</b> <span style="color:#64748b;">(${t.correct}/${t.answered})</span><div style="background:#1e293b; border-radius:99px; height:6px;"><div style="width:${t.pct}%; height:100%; border-radius:99px; background:${t.pct >= 60 ? '#10b981' : (t.pct >= 40 ? '#facc15' : '#f87171')};"></div></div></div>`).join('')}</div>` : ''}
          ${(rep.question_stats && rep.question_stats.length) ? `<div style="margin-top:8px; font-size:12px;"><b style="color:#f87171;">❌ Students ki kashtamaina questions:</b>${rep.question_stats.slice(0, 3).map(s => `<div style="color:var(--text-muted); margin:2px 0;">· ${s.pct}% correct — ${s.q}</div>`).join('')}</div>` : ''}`;
      } catch (e) {
        card.innerHTML = '<div style="color:#ef4444;">❌ ' + e + '</div>';
      }
    }

    async function retestCampus(code) {
      if (!confirm('🔁 ' + code + ' settings tho kottha exam create cheyyala? (Same college, questions, level — students progress compare avthundi)')) return;
      try {
        const res = await fetch('/api/campus/retest', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({code})});
        const d = await res.json();
        if (!d.ok) return alert('❌ ' + (d.message || 'retest failed'));
        const card = document.getElementById('campus-active-card');
        card.innerHTML = `<div style="display:flex; gap:16px; align-items:center; flex-wrap:wrap;">
          <img src="${d.qr}" style="width:130px; height:130px; border-radius:8px; background:white; padding:5px; border:2px solid #10b981;">
          <div style="flex:1; min-width:200px;">
            <div style="font-size:14px; font-weight:800; color:#10b981;">🔁 Retest Ready! New Code: ${d.code}</div>
            <div style="font-size:11px; word-break:break-all; color:#38bdf8; margin:6px 0;">${d.link}</div>
            <div style="display:flex; gap:6px; flex-wrap:wrap;">
              <a href="${d.qr}&dl=1" class="btn btn-outline" style="padding:4px 10px; font-size:11px; text-decoration:none;">📥 Download QR</a>
              <button class="btn btn-accent" style="padding:4px 10px; font-size:11px;" onclick="navigator.clipboard.writeText('${d.link}').then(()=>alert('✅ Link copied!'))">📋 Copy Link</button>
              <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="navigator.clipboard.writeText(window.location.origin + '/exam/${d.code}').then(()=>alert('✅ Web Link copied!'))">🌐 Copy Web Link</button>
              <button class="btn btn-primary" style="padding:4px 10px; font-size:11px;" onclick="startCampusExam('${d.code}')">🚀 Start Exam</button>
            </div>
            <div style="font-size:11px; color:var(--text-muted); margin-top:6px;">QR scan cheyyamani students ki cheppandi — hall ready ayyaka 🚀 Start nokkandi.</div>
          </div></div>`;
        loadCampusEvents();
      } catch (e) { alert('❌ ' + e); }
    }

    async function loadCampusEvents() {
      const res = await fetch('/api/campus/list');
      const d = await res.json();
      const tbody = document.querySelector('#table-campus tbody');
      tbody.innerHTML = '';
      (d.events || []).forEach(e => {
        const tr = document.createElement('tr');
        const link = 'https://t.me/' + (d.bot || 'StudentUpBot') + '?start=c' + e.code.replace('CE-', '') + '-1';
        tr.innerHTML = `
          <td><b>${e.code}</b></td>
          <td><b>${e.name}</b></td>
          <td>${e.district}</td>
          <td>${e.n_q} Qs (${e.level})</td>
          <td style="color:#38bdf8; font-weight:700;">${e.players_count} Students</td>
          <td><span class="status-pill ${e.state === 'open' ? 'open' : 'closed'}">${e.state}</span></td>
          <td>
            <a href="${link}" target="_blank" class="btn btn-outline" style="padding:3px 7px; font-size:11px; text-decoration:none;">🔗 Link</a>
            <a href="/exam/${e.code}" target="_blank" class="btn btn-outline" style="padding:3px 7px; font-size:11px; margin-left:4px; text-decoration:none;">🌐 Web Exam</a>
            <button class="btn btn-accent" style="padding:3px 7px; font-size:11px; margin-left:4px;" onclick="viewCampusReport('${e.code}')">📋 Report</button>
            <a href="/api/campus/qr?code=${e.code}&dl=1" class="btn btn-outline" style="padding:3px 7px; font-size:11px; margin-left:4px; text-decoration:none;">📥 QR</a>
            ${e.state === 'open' ? `<button class="btn btn-primary" style="padding:3px 7px; font-size:11px; margin-left:4px;" onclick="startCampusExam('${e.code}')">🚀 Start</button>` : ''}
            ${(e.state === 'question' || e.state === 'gap') ? `<button class="btn btn-primary" style="padding:3px 7px; font-size:11px; margin-left:4px; background:#dc2626;" onclick="watchCampusLive('${e.code}')">🔴 Live</button>` : ''}
            ${e.state === 'done' ? `<button class="btn btn-outline" style="padding:3px 7px; font-size:11px; margin-left:4px;" onclick="retestCampus('${e.code}')">🔁 Retest</button>` : ''}
          </td>
        `;
        tbody.appendChild(tr);
      });
      loadCampusLeague();
      loadPortalExams();
      loadPortalAnalytics();
      loadAdminFlags();
      loadPyqStatus();
      loadNotices();
    }



    async function makePaperDraft() {
      const msg = document.getElementById('pf-msg');
      const path = document.getElementById('pf-path').value.trim();
      if (!path) { msg.textContent = '⚠️ Paper file path ivvandi.'; return; }
      try {
        const d = await (await fetch('/api/papers/make', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({path})})).json();
        msg.textContent = d.ok ? ('📄 Draft ready: ' + d.draft_id + ' · parsed ' + d.parsed + ' · fresh ' + d.fresh + ' · dup ' + d.duplicates + ' · 📝 translation pending ' + (d.needs_translation || 0)) : ('❌ ' + (d.error || 'failed'));
        loadPaperDrafts();
      } catch (e) { msg.textContent = '❌ ' + e; }
    }
    async function loadPaperDrafts() {
      const box = document.getElementById('pf-list');
      try {
        const d = await fetch('/api/papers/drafts').then(r => r.json());
        const rows = (d.drafts || []).map(x => {
          const m = x.meta || {};
          const acts = x.status === 'draft' ? ' <button class="btn btn-accent" onclick="paperDraftAct(\'approve\',\'' + x.id + '\')">✅ Approve→Bank</button>' + (x.needs_translation ? ' <button class="btn btn-outline" onclick="paperDraftAct(\'translate\',\'' + x.id + '\')">🌐 Translate</button>' : '') + ' <button class="btn btn-outline" onclick="paperDraftAct(\'reject\',\'' + x.id + '\')">❌ Reject</button>' : '';
          return '📄 ' + x.id + ' · ' + (m.exam || '?') + ' ' + (m.year || '') + ' ' + (m.paper || '') + ' · status: ' + x.status + ' · fresh ' + x.fresh + '/' + x.parsed + (x.needs_translation ? ' · 📝 TE pending ' + x.needs_translation : '') + acts;
        });
        box.textContent = rows.length ? rows.join('\n') : 'Drafts levu — paina path ichi draft cheyyandi.';
      } catch (e) { box.textContent = '❌ ' + e; }
    }
    async function paperDraftAct(act, id) {
      const msg = document.getElementById('pf-msg');
      const url = act === 'approve' ? '/api/papers/approve' : (act === 'translate' ? '/api/papers/translate' : '/api/papers/reject');
      try {
        const d = await (await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({draft_id: id})})).json();
        msg.textContent = d.ok ? ('✅ ' + act + ' done · added ' + (d.added ?? '—') + ' · translated ' + (d.translated ?? '—') + ' · pending ' + (d.still_pending ?? d.translation_pending ?? 0)) : ('❌ ' + (d.error || 'failed'));
        loadPaperDrafts();
      } catch (e) { msg.textContent = '❌ ' + e; }
    }
    async function loadPyqStatus() {
      try {
        const d = await fetch('/api/pyq/status').then(r => r.json());
        const _bc = Object.entries(d.by_channel || {}).map(([c, v]) => c + ': ' + v.pyq + ' PYQ').join(' · ');
        document.getElementById('pyq-status').textContent = (_bc ? '📊 Exam-wise PYQ: ' + _bc + '\n' : '') +
          '🏦 Bank: ' + d.bank.total + ' questions · 📜 Real PYQ: ' + d.bank.pyq + ' · ✍️ Curated: ' + d.bank.curated +
          ' · 🌐 Scraped: ' + d.bank.scraped + ' · 🤖 Generated: ' + d.bank.generated + '\n' + (d.text || '') +
          (d.running ? '\n⏳ Harvest running…' : '') + (d.last ? '\nLast run: ' + d.last : '');
      } catch (e) { /* tab not ready */ }
    }
    async function runPyqHarvest(dry) {
      const msg = document.getElementById('pyq-msg');
      try {
        const r = await fetch('/api/pyq/harvest', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({dry})});
        const d = await r.json();
        msg.textContent = d.ok ? ('🌾 Harvest start ayindi' + (dry ? ' (dry run)' : '') + ' — Status refresh chesthu undandi…') : ('❌ ' + d.error);
        setTimeout(loadPyqStatus, 3000);
      } catch (e) { msg.textContent = '❌ ' + e; }
    }
    async function addPyqPaper() {
      const msg = document.getElementById('pyq-msg');
      const body = {channel: document.getElementById('pyq-channel').value,
        exam: document.getElementById('pyq-exam').value.trim(),
        year: parseInt(document.getElementById('pyq-year').value || '0'),
        paper: document.getElementById('pyq-paper').value.trim(),
        url: document.getElementById('pyq-url').value.trim()};
      if (!body.exam || !body.url) { msg.textContent = '⚠️ Exam + URL ivvandi.'; return; }
      const d = await (await fetch('/api/pyq/add_paper', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})).json();
      msg.textContent = d.ok ? '✅ Paper add ayindi — 🌾 Harvest run cheyyandi.' : ('❌ ' + d.error);
      loadPyqStatus();
    }
    function downloadPyqTemplate() {
      const csv = 'question,option1,option2,option3,option4,answer,explanation,exam,year,channel,topic\n"The Finance Commission is constituted under which Article?","Article 280","Article 263","Article 312","Article 368",1,"Article 280 provides for a Finance Commission.","UPSC CSE Prelims",2023,CURRENT,polity\n';
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([csv], {type: 'text/csv'}));
      a.download = 'pyq_import_template.csv'; a.click();
    }
    function readPyqFile(ev) {
      const f = ev.target.files[0]; if (!f) return;
      f.text().then(t => { document.getElementById('pyq-csv').value = t; });
    }
    async function importPyqCsv() {
      const msg = document.getElementById('pyq-import-msg');
      const csv = document.getElementById('pyq-csv').value.trim();
      if (!csv) { msg.textContent = '⚠️ CSV paste cheyyandi / file select cheyyandi.'; return; }
      const d = await (await fetch('/api/pyq/import', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({csv})})).json();
      msg.textContent = '✅ Added ' + (d.added || 0) + ' PYQs · ⏭️ duplicates ' + (d.skipped_dup || 0) + ' · 🌐 Telugu kosam pending ' + (d.pending_translation || 0) +
        ((d.errors || []).length ? ' · ⚠️ ' + d.errors.slice(0, 3).join(' | ') : '');
      loadPyqStatus();
    }
    async function loadNotices() {
      try {
        const d = await fetch('/api/portal/admin/notices').then(r => r.json());
        document.getElementById('ntc-list').innerHTML = (d.notices || []).map(n =>
          '<div style="padding:7px 10px; background:#050811; border:1px solid var(--border); border-radius:8px; margin-top:6px;">📢 <b style="color:#e2e8f0;">' + n.title + '</b> <span style="color:var(--text-muted);">' + n.date + '</span><br>' + n.body + '</div>').join('') || 'Notices levu.';
      } catch (e) { /* tab not ready */ }
    }
    async function postNotice() {
      const msg = document.getElementById('ntc-msg');
      const body = {title: document.getElementById('ntc-title').value.trim(),
        body: document.getElementById('ntc-body').value.trim(),
        link: document.getElementById('ntc-link').value.trim()};
      if (!body.title) { msg.textContent = '⚠️ Title ivvandi.'; return; }
      const d = await (await fetch('/api/portal/admin/notices/create', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})).json();
      msg.textContent = d.ok ? '✅ Notice post ayindi — Portal + /updates lo live!' : '❌ Failed';
      if (d.ok) { document.getElementById('ntc-title').value = ''; document.getElementById('ntc-body').value = ''; loadNotices(); }
    }

    async function sendPersonalReports() {
      const msg = document.getElementById('rep-msg');
      if (!confirm('Telegram students andari ki personal report DM cheyyala? (okkokariki valla report matrame velthundi)')) return;
      const d = await (await fetch('/api/portal/admin/send_reports', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})).json();
      msg.textContent = d.ok ? '📩 Sending start ayindi — Status chudandi…' : ('❌ ' + d.error);
      setTimeout(reportStatus, 4000);
    }
    async function reportStatus() {
      const msg = document.getElementById('rep-msg');
      const d = await (await fetch('/api/portal/admin/reports/status')).json();
      msg.textContent = d.running ? ('⏳ Sending… ' + d.sent + '/' + d.total + ' (fail ' + d.failed + ')')
        : ('✅ Last: sent ' + d.sent + ' · fail ' + d.failed + ' · total ' + d.total + (d.last ? ' · ' + d.last : ''));
    }

    async function announceWinners(id) {
      const d = await (await fetch('/api/portal/admin/announce', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({exam_id: id})})).json();
      if (!d.ok) { alert('❌ ' + d.error); return; }
      try { await navigator.clipboard.writeText(d.text); } catch (e) {}
      alert((d.sent_to_admin ? '📩 Telegram admin ki vellindi + ' : '') + '📋 Announcement text copy ayindi — WhatsApp groups lo paste cheyyandi!\n\n' + d.text);
    }

    async function wpStatus() {
      const el = document.getElementById('wp-status');
      el.textContent = '⏳ Checking…';
      try {
        const d = await fetch('/api/wp/status').then(r => r.json());
        el.textContent = d.ok ? ('✅ Connected: ' + d.name + ' (' + d.url + ') · cached posts: ' + d.posts_cached)
          : ('❌ ' + d.error + ' · Base: ' + (d.base || ''));
      } catch (e) { el.textContent = '❌ ' + e; }
    }
    async function wpExportQuiz() {
      const msg = document.getElementById('wp-msg');
      try {
        const d = await fetch('/api/wp/export').then(r => r.json());
        const blob = new Blob([JSON.stringify(d, null, 2)], {type: 'application/json'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'studentup_daily_quiz_' + d.date + '.json'; a.click();
        msg.textContent = '📤 ' + d.date + ' quiz export ayindi (' + d.questions.length + ' questions, WP quiz.php format) — WP snippet dwara sync avthundi.';
      } catch (e) { msg.textContent = '❌ ' + e; }
    }

    // 🚦 310X Publish Center
    async function pubLoad() {
      const el = document.getElementById('pub-status');
      el.textContent = '⏳ Draft load avthundi…';
      try {
        const d = await fetch('/api/publish/today').then(r => r.json());
        const dr = d.draft || {};
        const st = {draft: '📝 DRAFT (approve kosam wait)', approved: '✅ APPROVED (push/live ready)', live: '🚀 LIVE', rejected: '❌ REJECTED'}[dr.status] || dr.status;
        const lines = ['Status: ' + st,
          '🎯 Daily Quiz: ' + ((dr.quiz || {}).count || 0) + ' questions (PYQ ' + ((dr.quiz || {}).pyq || 0) + ')',
          '🏆 Live Exams today: ' + ((dr.exams_today || []).length
            ? dr.exams_today.map(e => e.title + ' @ ' + String(e.starts_at || '').replace('T', ' ')).join(' · ')
            : 'levu'),
          '👑 Weekly Grand: ' + (dr.weekly_grand ? (dr.weekly_grand.n_q + 'Q @ ' + dr.weekly_grand.time) : '— (Sunday matrame)'),
          '🌐 WordPress: ' + (d.wp_creds ? 'creds ready' : 'creds set ledu (.env lo WP_APP_PASSWORD)') + ((dr.wp || {}).pushed ? ' · pushed ✅ (' + dr.wp.stored + ' stored)' : '')];
        el.textContent = lines.join('\n');
      } catch (e) { el.textContent = '❌ ' + e; }
    }
    async function pubAct(path, body) {
      const msg = document.getElementById('pub-msg');
      try {
        const d = await (await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})})).json();
        msg.textContent = d.ok ? ('✅ ' + (d.message || 'Done')) : ('❌ ' + (d.error || d.message || 'fail ayindi'));
        pubLoad();
      } catch (e) { msg.textContent = '❌ ' + e; }
    }
    function pubApprove() { pubAct('/api/publish/approve', {}); }
    function pubReject() { if (confirm('Ee draft reject cheyyala? Kotta draft rebuild avthundi.')) pubAct('/api/publish/reject', {}); }
    function pubPushWp() { pubAct('/api/publish/push_wp', {}); }
    async function pubGoLive() {
      if (!confirm('🚀 Go Live cheyyala? Quiz + exams students ki open avthayi.')) return;
      const msg = document.getElementById('pub-msg');
      try {
        const d = await (await fetch('/api/publish/go_live', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'})).json();
        msg.textContent = d.ok ? ('✅ ' + d.message + (d.sent_to_admin ? ' · 📩 Admin ki Telegram vellindi' : '')) : ('❌ ' + (d.error || d.message || 'fail ayindi'));
        if (d.ok && d.announcement) {
          try { await navigator.clipboard.writeText(d.announcement); msg.textContent += ' · 📋 Announcement copy ayindi — WhatsApp groups lo paste cheyyandi!'; } catch (e) {}
        }
        pubLoad();
      } catch (e) { msg.textContent = '❌ ' + e; }
    }

    async function createPortalExam() {
      const msg = document.getElementById('pex-msg');
      const body = {
        title: document.getElementById('pex-title').value.trim(),
        goal: document.getElementById('pex-goal').value,
        starts_at: document.getElementById('pex-start').value,
        duration_min: parseInt(document.getElementById('pex-dur').value),
        n_q: parseInt(document.getElementById('pex-nq').value),
        neg: parseFloat(document.getElementById('pex-neg').value || '0')
      };
      if (!body.title || !body.starts_at) { msg.textContent = '⚠️ Title + Start time ivvandi.'; return; }
      try {
        const r = await fetch('/api/portal/admin/exams/create', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        const d = await r.json();
        msg.textContent = d.ok ? ('✅ Scheduled: ' + d.title + ' · ' + d.n_q + ' Qs · ' + d.starts_at.replace('T', ' ')) : ('❌ ' + d.error);
        if (d.ok) loadPortalExams();
      } catch (e) { msg.textContent = '❌ ' + e; }
    }

    async function loadPortalExams() {
      try {
        const d = await fetch('/api/portal/admin/exams').then(r => r.json());
        const sel = document.getElementById('pex-goal');
        if (sel && !sel.options.length) Object.entries(d.goals || {}).forEach(([k, v]) => {
          const o = document.createElement('option'); o.value = k; o.textContent = v; sel.appendChild(o);
        });
        const box = document.getElementById('pex-list');
        box.innerHTML = (d.exams || []).map(e =>
          '<div style="padding:7px 10px; background:#050811; border:1px solid var(--border); border-radius:8px; margin-top:6px;">' +
          '<b style="color:#e2e8f0;">' + e.title + '</b> · ' + e.id + ' · ' + e.n_q + ' Qs · 👥 ' + e.joined +
          ' · <span style="color:' + (e.status === 'live' ? '#10b981' : (e.status === 'done' ? '#94a3b8' : '#facc15')) + ';">' +
          (e.status === 'live' ? '🔴 LIVE' : e.status) + '</span> · ⏰ ' + (e.starts_at || '').replace('T', ' ').slice(0, 16) +
          (e.winners && e.winners.length ? ' · 🏆 ' + e.winners.map(w => w.name + ' (' + w.correct + '/' + w.total + ')').join(', ') : '') +
          (e.status === 'done' && e.winners && e.winners.length ? ' <button class="btn btn-outline" style="padding:2px 8px; font-size:11px;" onclick="announceWinners(\'' + e.id + '\')">📣 Announce</button>' : '') +
          '</div>').join('') || 'Inka exams levu — paina schedule cheyyandi.';
      } catch (e) { /* tab not ready */ }
    }

    async function sendBotBroadcast() {
      const text = (document.getElementById('bb-text') || {}).value || '';
      const goal = (document.getElementById('bb-goal') || {}).value || '';
      if (!text.trim()) { alert('Message type cheyyandi'); return; }
      const d = await (await fetch('/api/portal/admin/bot_broadcast', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text, goal})})).json();
      alert(d.ok ? ('📣 Queued! Bot next tick lo ~' + (d.targets || 0) + ' linked students ki vasthundi.') : (d.error || 'Failed'));
      if (d.ok) document.getElementById('bb-text').value = '';
    }

    async function loadPortalAnalytics() {
      const box = document.getElementById('pt-analytics');
      if (!box) return;
      try {
        const d = await fetch('/api/portal/admin/analytics').then(r => r.json());
        if (!d.ok) { box.textContent = 'Analytics load avvaledu.'; return; }
        const f = d.funnel || {};
        const bar = (label, v, total) => {
          const pct = total ? Math.round(100 * v / total) : 0;
          return '<div style="margin-top:5px;">' + label + ': <b style="color:#e2e8f0;">' + v + '</b> <span>(' + pct + '%)</span>' +
            '<div style="height:7px; background:rgba(255,255,255,0.08); border-radius:4px;"><div style="height:7px; width:' + pct + '%; background:linear-gradient(90deg,#38bdf8,#34d399); border-radius:4px;"></div></div></div>';
        };
        const chips = (obj) => Object.entries(obj || {}).map(([k, v]) =>
          '<span style="display:inline-block; background:#050811; border:1px solid var(--border); border-radius:999px; padding:2px 9px; margin:2px 3px 0 0;">' + k + ': <b style="color:#e2e8f0;">' + v + '</b></span>').join('') || '<span>—</span>';
        box.innerHTML =
          '<div>👥 Students: <b style="color:#e2e8f0;">' + (d.students || 0) + '</b> · ✍️ Attempts: <b style="color:#e2e8f0;">' + (d.attempts_total || 0) + '</b> (today ' + (d.attempts_today || 0) + ') · 📜 Paper attempts: <b style="color:#e2e8f0;">' + (d.papers_attempts || 0) + '</b> · 🟢 Active today: <b style="color:#e2e8f0;">' + (d.active_today || 0) + '</b> · 🔐 Live sessions: <b style="color:#e2e8f0;">' + (d.sessions_live || 0) + '</b></div>' +
          '<h4 style="font-size:12px; margin-top:12px; color:#e2e8f0;">🔻 Portal Funnel (attempt rate ' + (f.attempt_rate || 0) + '%)</h4>' +
          bar('Registered', f.registered || 0, f.registered || 0) +
          bar('Attempted (≥1 test)', f.attempted || 0, f.registered || 0) +
          bar('Active today', f.active_today || 0, f.registered || 0) +
          ((d.retention) ? '<h4 style="font-size:12px; margin-top:12px; color:#e2e8f0;">🔁 Retention</h4><div>🆕 Last 7d registered: <b style="color:#e2e8f0;">' + (d.retention.new_7d || 0) + '</b> · 🟢 Active 7d: <b style="color:#e2e8f0;">' + (d.retention.active_7d || 0) + '</b> (' + (d.retention.active_7d_pct || 0) + '% of students)</div>' : '') +
          ((d.churn) ? '<div style="margin-top:5px;">⚠️ At-risk (7d+ inactive): <b style="color:#facc15;">' + (d.churn.at_risk_7d || 0) + '</b> · 💌 Win-back sent: <b style="color:#e2e8f0;">' + (d.churn.winback_sent || 0) + '</b> · 🏆 Result blasts: <b style="color:#e2e8f0;">' + (d.churn.result_blasts || 0) + '</b> <span>(bot auto)</span></div>' : '') +
          ((d.churn250) ? '<div style="margin-top:3px;">📉 Churn cohorts: 🟢 Active <b style="color:#4ade80;">' + (d.churn250.active || 0) + '</b> · 🟡 Cooling <b style="color:#facc15;">' + (d.churn250.cooling || 0) + '</b> · 🟠 At-risk <b style="color:#fb923c;">' + (d.churn250.at_risk || 0) + '</b> · 🔴 Critical <b style="color:#f87171;">' + (d.churn250.critical || 0) + '</b> <span class="muted">(' + (d.churn250.critical_pct || 0) + '% critical)</span></div>' : '') +
          ((d.bot) ? '<h4 style="font-size:12px; margin-top:12px; color:#e2e8f0;">🤖 Bot Funnel (120X)</h4><div>🔗 Linked: <b style="color:#e2e8f0;">' + (d.bot.linked || 0) + '</b> (' + (d.bot.link_pct || 0) + '% of students) · 🪪 Link claims: <b style="color:#e2e8f0;">' + (d.bot.claims || 0) + '</b> · 🔐 WebApp logins: <b style="color:#e2e8f0;">' + (d.bot.logins || 0) + '</b> · 📬 Bot msgs sent: <b style="color:#e2e8f0;">' + (d.bot.msgs || 0) + '</b></div>' +
          '<div style="margin-top:8px;"><div class="muted" style="font-size:11.5px;">📣 Bot Broadcast (linked students ki Telegram):</div>' +
          '<textarea id="bb-text" rows="2" style="width:100%; margin-top:4px;" placeholder="Ee roju 7 PM ki Grand Mock LIVE! Ready ga undandi 🔥"></textarea>' +
          '<div style="display:flex; gap:6px; margin-top:5px;"><select id="bb-goal" style="flex:1;"><option value="">All goals</option></select>' +
          '<button class="btn btn-outline" onclick="sendBotBroadcast()">📣 Queue Broadcast</button></div></div>' : '') +
          '<h4 style="font-size:12px; margin-top:12px; color:#e2e8f0;">🎯 Students by Goal</h4><div>' + chips(d.goals) + '</div>' +
          '<h4 style="font-size:12px; margin-top:12px; color:#e2e8f0;">🧪 Attempts by Kind</h4><div>' + chips(d.attempt_kinds) + '</div>' +
          ((d.pyq_gaps || []).length ? '<h4 style="font-size:12px; margin-top:12px; color:#e2e8f0;">📜 PYQ Coverage Gaps (target 50/channel)</h4>' +
            (d.pyq_gaps || []).map(g => '<div style="margin-top:3px;">' + (g.channel || g.exam || '?') + ': <b style="color:#facc15;">' + (g.gap != null ? g.gap + ' to go' : '') + '</b> <span>(' + (g.pyq || 0) + ' PYQ now)</span></div>').join('') : '') +
          ((d.harvest_targets230 || []).length ? '<h4 style="font-size:12px; margin-top:12px; color:#e2e8f0;">🚜 Exam Harvest Targets — reasoning/aptitude focus (weight × need)</h4>' +
            (d.harvest_targets230 || []).map(g => '<div style="margin-top:3px;">' + esc(g.channel + ' · ' + g.subject) + ': <b style="color:#facc15;">' + g.cmd + '</b> <span class="muted">(need ' + g.need + ')</span></div>').join('') +
            '<button class="btn-alt" style="width:auto; margin-top:6px;" onclick="runHarvest230()">🚜 Run #1 Harvest (production)</button> <span class="muted">sandbox lo dry-run matrame</span>' : '') +
          '<div style="margin-top:10px;"><b style="font-size:12px;">📚 Materials Vault — add item</b><br>' +
          '<input id="mat-title" placeholder="Title (eg Reasoning Tricks PDF)" style="width:220px;"> ' +
          '<input id="mat-file" placeholder="file name (data/materials/) or https link" style="width:240px;"> ' +
          '<input id="mat-goal" placeholder="goal: railway/ssc/banking/all" style="width:170px;"> ' +
          '<input id="mat-cost" placeholder="points" style="width:70px;"> ' +
          '<button class="btn-alt" style="width:auto;" onclick="addMaterial230()">➕ Add Material</button></div>' +
          ((d.bank_gaps210 || []).length ? '<h4 style="font-size:12px; margin-top:12px; color:#e2e8f0;">🎯 Bank-Gap Harvest Priorities (exam weight × need)</h4>' +
            (d.bank_gaps210 || []).map(g => '<div style="margin-top:3px;">' + esc(g.channel + ' · ' + g.subject) + ' <span class="muted">(goal ' + esc(g.goal) + ', weight ' + Math.round((g.weight || 0) * 100) + '%)</span>: <b style="color:#facc15;">need ' + g.need + '</b> <span class="muted">(' + g.bank_q + ' bank now · priority ' + g.priority + ')</span></div>').join('') : '');
        const bbg = document.getElementById('bb-goal');
        if (bbg) Object.keys(d.goals || {}).forEach(g => { const o = document.createElement('option'); o.value = g; o.textContent = g; bbg.appendChild(o); });
      } catch (e) { box.textContent = '❌ ' + e; }
    }

    // 🎓 450X: ee rendu functions PORTAL page lo matrame unde — admin
    // Portal-Analytics buttons (Run Harvest / Add Material) click
    // cheste ReferenceError vachedi. Ippudu admin page lone, admin
    // fetch style (146 direct fetch calls) tho define chesam.
    async function addMaterial230() {
      const body = { title: (document.getElementById('mat-title') || {}).value || '',
                     file: (document.getElementById('mat-file') || {}).value || '',
                     goal: (document.getElementById('mat-goal') || {}).value || 'all',
                     cost: parseInt((document.getElementById('mat-cost') || {}).value || '0', 10) || 0 };
      try {
        const r = await fetch('/api/admin/materials_add', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        const d = await r.json();
        alert(d.ok ? '✅ Material added: ' + ((d.item || {}).title || body.title) : ('❌ ' + (d.error || 'failed')));
      } catch (e) { alert('❌ ' + e); }
    }
    async function runHarvest230() {
      if (!confirm('Top harvest target run cheyyala? (production lo real PYQ download avthundi)')) return;
      try {
        const r = await fetch('/api/admin/harvest_run', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'});
        const d = await r.json();
        alert((d && d.message) || (d && d.error) || 'done');
      } catch (e) { alert('❌ ' + e); }
    }

    async function searchAdminStudents() {
      const box = document.getElementById('pt-students');
      const q = (document.getElementById('pt-q') || {}).value || '';
      try {
        const d = await fetch('/api/portal/admin/students?q=' + encodeURIComponent(q)).then(r => r.json());
        const rows = d.students || [];
        box.innerHTML = rows.length ? rows.map(s =>
          '<div style="padding:6px 9px; background:#050811; border:1px solid var(--border); border-radius:8px; margin-top:5px;">' +
          '<b style="color:#e2e8f0;">' + (s.name || '') + '</b> · ' + (s.district || '') + ' · 🎯 ' + (s.goal || '') +
          ' · ⭐ ' + (s.points || 0) + ' pts' +
          (s.mobile ? ' · 📱 ' + s.mobile : '') + '</div>').join('')
          : 'Students dorakaledu.';
      } catch (e) { box.textContent = '❌ ' + e; }
    }

    async function loadAdminFlags() {
      const box = document.getElementById('pt-flags');
      if (!box) return;
      try {
        const d = await fetch('/api/portal/admin/flags').then(r => r.json());
        const rows = d.flags || [];
        box.innerHTML = rows.length ? rows.map(f =>
          '<div style="padding:6px 9px; background:#050811; border:1px solid var(--border); border-radius:8px; margin-top:5px;">' +
          '🚩 <b style="color:#e2e8f0;">' + (f.qid || '') + '</b>' +
          (f.question ? ' · ' + f.question : '') +
          (f.topic ? ' · 🏷️ ' + f.topic : '') +
          (f.reason ? ' · ' + f.reason : '') + (f.date ? ' · ' + f.date : '') + '</div>').join('')
          : '🚩 Flags levu — bank clean!';
      } catch (e) { box.textContent = '❌ ' + e; }
    }

    async function loadBundles() {
      const res = await fetch('/api/bundles');
      const d = await res.json();
      cachedBundles = d.bundles || [];
      const tbody = document.querySelector('#table-bundles tbody');
      if (tbody) {
        tbody.innerHTML = '';
        cachedBundles.forEach(b => {
          const tr = document.createElement('tr');
          const groupCount = (b.target_groups || []).length;
          const chanCount = (b.target_channels || []).length;
          tr.innerHTML = `
            <td><b>${b.name}</b></td>
            <td><span class="category-tag">${b.category}</span></td>
            <td>
              <span style="color:#10b981; font-weight:700;">${groupCount} Groups</span> · 
              <span style="color:#38bdf8; font-weight:700;">${chanCount} Channels</span>
            </td>
            <td>
              <button class="btn btn-purple" style="padding:4px 8px; font-size:11px;" onclick="loadBundleToBulkDispatcher('${b.id}')">🚀 Select in Dispatcher</button>
              <button class="btn btn-outline" style="padding:4px 8px; font-size:11px; margin-left:4px; color:#ef4444;" onclick="deleteBundle('${b.id}')">Delete</button>
            </td>
          `;
          tbody.appendChild(tr);
        });
      }

      // Update bundle dropdown in bulk broadcast tab
      const bSel = document.getElementById('bulk-bundle-selector');
      if (bSel) {
        bSel.innerHTML = '<option value="">-- Choose a Saved Group Bundle --</option>' +
          cachedBundles.map(b => `<option value="${b.id}">${b.name} (${(b.target_groups||[]).length} Groups, ${(b.target_channels||[]).length} Channels)</option>`).join('');
      }

      populateBundleCreatorMembers();
    }

    function populateBundleCreatorMembers() {
      const cont = document.getElementById('bundle-creator-members');
      if (!cont) return;

      const q = (document.getElementById('bundle-member-search')?.value || '').toLowerCase();
      cont.innerHTML = '';

      if (cachedBulkGroups.length === 0 && cachedBulkChannels.length === 0) {
        cont.innerHTML = '<div style="color:var(--text-muted); font-size:11px; text-align:center; padding:10px;">No groups or channels loaded yet.</div>';
        return;
      }

      // Channels section
      cachedBulkChannels.forEach(([key, ch]) => {
        if (q && !ch.name.toLowerCase().includes(q) && !key.toLowerCase().includes(q)) return;
        const div = document.createElement('div');
        div.className = 'bundle-creator-item';
        div.style = 'display:flex; align-items:center; gap:6px; font-size:11px;';
        div.innerHTML = `
          <input type="checkbox" class="bundle-new-ch" value="${key}">
          <span>📢 <b>${ch.name}</b> <span style="color:#64748b;">(TG Channel)</span></span>
        `;
        cont.appendChild(div);
      });

      // Groups section
      cachedBulkGroups.forEach(g => {
        if (q && !g.name.toLowerCase().includes(q) && !(g.jid||'').toLowerCase().includes(q)) return;
        const div = document.createElement('div');
        div.className = 'bundle-creator-item';
        div.style = 'display:flex; align-items:center; gap:6px; font-size:11px;';
        div.innerHTML = `
          <input type="checkbox" class="bundle-new-wa" value="${g.id}">
          <span>💬 <b>${g.name}</b> <span style="color:#10b981; font-weight:700;">[${g.category || 'GENERAL'}]</span></span>
        `;
        cont.appendChild(div);
      });
    }

    function filterBundleCreatorList() {
      populateBundleCreatorMembers();
    }

    function toggleBundleCreatorItems(val) {
      document.querySelectorAll('.bundle-new-ch, .bundle-new-wa').forEach(c => c.checked = val);
    }

    function loadBundleToBulkDispatcher(bid) {
      switchTab('tab-bulk-broadcast');
      const bSel = document.getElementById('bulk-bundle-selector');
      if (bSel) {
        bSel.value = bid;
        applySelectedBundle(bid);
      }
    }

    async function saveNewBundle() {
      const name = document.getElementById('bundle-name').value.trim();
      const cat = document.getElementById('bundle-category').value;
      if (!name) return alert('Enter bundle title');

      const waGids = Array.from(document.querySelectorAll('.bundle-new-wa:checked')).map(c => c.value);
      const chKeys = Array.from(document.querySelectorAll('.bundle-new-ch:checked')).map(c => c.value);

      if (waGids.length === 0 && chKeys.length === 0) {
        return alert('Please select at least one WhatsApp Group or Telegram Channel to include in this bundle!');
      }

      // Conflict warning before bundle creation
      try {
        const cRes = await fetch('/api/whatsapp/check_conflicts', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({target_group_ids: waGids, target_channel_keys: chKeys})
        });
        const cData = await cRes.json();
        if (cData.has_conflicts) {
          const warn = cData.conflicts.map(c => c.message).join('\\n');
          const ok = confirm(`⚠️ Bundle Overlap Notice:\\n${warn}\\n\\nDo you want to save this bundle anyway?`);
          if (!ok) return;
        }
      } catch (e) {
        console.error(e);
      }

      await fetch('/api/bundles/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          name: name,
          category: cat,
          group_ids: waGids,
          channel_keys: chKeys
        })
      });

      alert(`✅ Bundle '${name}' created successfully with ${waGids.length} groups and ${chKeys.length} channels!`);
      document.getElementById('bundle-name').value = '';
      toggleBundleCreatorItems(false);
      loadBundles();
      fetchStats();
    }

    async function deleteBundle(bid) {
      if (!confirm('Delete this bundle?')) return;
      await fetch('/api/bundles/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: bid})
      });
      loadBundles();
      fetchStats();
    }

    async function dispatchBundle(bid, isQuestion) {
      alert('Launching round across bundle: ' + bid);
      switchTab('tab-wa-dispatch');
      startInterleaved(isQuestion);
    }

    function filterTGChannels() {
      const q = (document.getElementById('ch-search-box').value || '').toLowerCase();
      const rows = document.querySelectorAll('#table-channels tbody tr');
      rows.forEach(r => {
        const text = r.innerText.toLowerCase();
        r.style.display = text.includes(q) ? '' : 'none';
      });
    }

    async function loadChannels() {
      const res = await fetch('/api/channels');
      const d = await res.json();
      const tbody = document.querySelector('#table-channels tbody');
      const select = document.getElementById('post-poll-channel');
      tbody.innerHTML = '';
      select.innerHTML = '';
      const counts = d.question_counts || {};

      for (const [key, ch] of Object.entries(d.channels || {})) {
        const count = counts[ch.base_exam || key] || counts[key] || 0;
        const tr = document.createElement('tr');
        const typeBadge = ch.chat_type === 'group'
          ? '<span style="background:#064e3b; color:#6ee7b7; font-size:10px; padding:1px 6px; border-radius:8px; margin-left:4px;">💬 GROUP</span>'
          : '<span style="background:#1e3a5f; color:#7dd3fc; font-size:10px; padding:1px 6px; border-radius:8px; margin-left:4px;">📢 CHANNEL</span>';
        tr.innerHTML = `
          <td><input type="checkbox" class="tg-ch-select-checkbox" data-chkey="${key}"></td>
          <td><b>${key}</b></td>
          <td>${ch.emoji || '🎯'} ${ch.name} ${typeBadge}</td>
          <td><span class="category-tag">${ch.base_exam || key}</span></td>
          <td style="color:#38bdf8; font-weight:700;">${count} Questions</td>
          <td style="font-family:monospace;">${ch.chat_id || ch.username || '—'}</td>
          <td>
            <button class="btn btn-outline" style="padding:3px 7px; font-size:11px;" onclick="quickPostChannel('${key}')">⚡ Post Quiz</button>
          </td>
        `;
        tbody.appendChild(tr);

        const opt = document.createElement('option');
        opt.value = key;
        opt.innerText = (ch.chat_type === 'group' ? '💬 ' : '📢 ') + (ch.emoji || '🎯') + ' ' + ch.name + ' (' + count + ' polls)';
        select.appendChild(opt);
      }
    }

    function selectAllChannels(checked) {
      const cbs = document.querySelectorAll('.tg-ch-select-checkbox');
      cbs.forEach(cb => cb.checked = checked);
      const master = document.getElementById('ch-select-all');
      if (master) master.checked = checked;
    }

    function getSelectedChannelKeys() {
      const cbs = document.querySelectorAll('.tg-ch-select-checkbox:checked');
      return Array.from(cbs).map(cb => cb.getAttribute('data-chkey'));
    }

    async function quickPostChannel(key) {
      const log = document.getElementById('tg-poll-log');
      log.innerText = 'Posting 1 poll to ' + key + '...';
      const res = await fetch('/api/post_poll', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({channel: key, count: 1})
      });
      const d = await res.json();
      log.innerText = d.message || 'Poll dispatched!';
      loadChannels();
      fetchStats();
    }

    async function dispatchSelectedChannels() {
      const keys = getSelectedChannelKeys();
      if (!keys || keys.length === 0) {
        return alert('Please select at least 1 channel using the checkboxes!');
      }
      if (!confirm(`Post exam quiz polls to ${keys.length} selected channel(s)?`)) return;

      const log = document.getElementById('tg-poll-log');
      log.innerText = `Dispatching polls across ${keys.length} channels...`;
      let okCount = 0;
      for (const k of keys) {
        const res = await fetch('/api/post_poll', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({channel: k, count: 1})
        });
        const d = await res.json();
        if (d.ok) okCount++;
      }
      log.innerText = `✅ Successfully posted polls across ${okCount} / ${keys.length} channels!`;
      alert(`✅ Successfully posted polls across ${okCount} channels!`);
      loadChannels();
      fetchStats();
    }

    async function createNewChannel() {
      const name = document.getElementById('new-ch-name').value.trim();
      const base = document.getElementById('new-ch-base').value;
      const chatid = document.getElementById('new-ch-chatid').value.trim();
      const chtype = (document.getElementById('new-ch-type') || {value:'channel'}).value;
      if (!name) return alert('Enter channel or exam name');

      const res = await fetch('/api/channels/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, exam_type: base, chat_id: chatid, chat_type: chtype})
      });
      const d = await res.json();
      alert(d.message || ((chtype === 'group' ? 'Group' : 'Channel') + ' registered: ' + d.channel.name));
      document.getElementById('new-ch-name').value = '';
      document.getElementById('new-ch-chatid').value = '';
      loadChannels();
      fetchStats();
    }

    async function detectNewTelegramChats() {
      const box = document.getElementById('tg-detect-result');
      box.innerHTML = '<span style="color:#fbbf24;">🔍 Scanning Telegram for groups/channels where bot was added...</span>';
      try {
        const res = await fetch('/api/channels/detect_new', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: '{}'
        });
        const d = await res.json();
        if (!d.ok) {
          box.innerHTML = '<span style="color:#f87171;">❌ ' + (d.error || 'Detection failed') + '</span>';
          return;
        }
        if (!d.added || d.added.length === 0) {
          box.innerHTML = '<span style="color:#94a3b8;">Scanned ' + (d.scanned || 0) + ' chat(s) — కొత్తవి ఏమీ లేవు. ' + (d.note || '') + '</span>';
          return;
        }
        box.innerHTML = '<span style="color:#34d399;">✅ ' + d.added.length + ' కొత్త target(s) registered: ' +
          d.added.map(function(a){ return (a.chat_type === 'group' ? '💬 ' : '📢 ') + a.name; }).join(', ') + '</span>';
        loadChannels();
        fetchStats();
      } catch (e) {
        box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>';
      }
    }

    async function sendChannelPoll(count) {
      const ch = document.getElementById('post-poll-channel').value;
      const log = document.getElementById('tg-poll-log');
      log.innerText = 'Generating and posting ' + count + ' poll(s) for ' + ch + '...';
      const res = await fetch('/api/post_poll', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({channel: ch, count: count || 1})
      });
      const d = await res.json();
      log.innerText = d.message || JSON.stringify(d);
    }

    async function triggerWar(act, mins) {
      const box = document.getElementById('war-result');
      box.innerText = 'Triggering War ' + act + '...';
      const res = await fetch('/api/war', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({act, mins: mins || 5})
      });
      const d = await res.json();
      box.innerText = d.message || JSON.stringify(d);
    }

    async function syncSheet(act) {
      const box = document.getElementById('sheet-result');
      box.innerText = 'Syncing Google Sheet...';
      const res = await fetch('/api/sheet', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({act})
      });
      const d = await res.json();
      box.innerText = d.message || JSON.stringify(d);
    }

    async function loadSquads() {
      const res = await fetch('/api/squads');
      const d = await res.json();
      const tbody = document.querySelector('#table-squads tbody');
      tbody.innerHTML = '';
      if (!d.squads || Object.keys(d.squads).length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:16px;">No squads created yet. Click "Create Squad" above!</td></tr>';
        return;
      }
      for (const [code, s] of Object.entries(d.squads)) {
        const tr = document.createElement('tr');
        const link = 'https://t.me/' + (d.bot || 'StudentUpBot') + '?start=sq_' + code;
        const qrUrl = 'https://api.qrserver.com/v1/create-qr-code/?size=600x600&data=' + encodeURIComponent(link);
        const memCount = (s.members || []).length;
        const membersList = (s.members || []).join(', ') || s.leader;

        tr.innerHTML = `
          <td><b style="color:#38bdf8; font-size:14px;">SQ-${code}</b></td>
          <td><b>${s.name}</b></td>
          <td>${s.leader}</td>
          <td><span style="font-weight:700; color:${memCount >= 5 ? '#10b981' : '#f59e0b'};">${memCount} / 10 Members</span></td>
          <td style="font-size:11px; color:var(--text-muted); max-width:200px; overflow:hidden; text-overflow:ellipsis;">${membersList}</td>
          <td>
            <a href="${link}" target="_blank" class="btn btn-outline" style="padding:3px 8px; font-size:11px; text-decoration:none;">🔗 Join Link</a>
            <button class="btn btn-accent" style="padding:3px 8px; font-size:11px; margin-left:4px;" onclick="viewSquadModal('${code}', '${s.name.replace(/'/g, "\'")}', '${link}', '${qrUrl}', '${s.leader}')">📱 View Scannable QR</button>
          </td>
        `;
        tbody.appendChild(tr);
      }
    }

    function viewSquadModal(code, name, link, qr, leader) {
      const modal = document.getElementById('squad-active-modal');
      modal.style.display = 'block';
      modal.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
          <div>
            <h3 style="color:#38bdf8; font-size:16px;">👥 Squad: ${name} (Code: SQ-${code})</h3>
            <div style="font-size:12px; color:var(--text-muted); margin-top:2px;">Leader: <b>${leader}</b> · Live One-Tap Telegram Join Link & Projector QR Code</div>
          </div>
          <button class="btn btn-outline" style="padding:4px 10px; font-size:11px;" onclick="document.getElementById('squad-active-modal').style.display='none'">✕ Close</button>
        </div>
        <div style="display:flex; gap:20px; align-items:center; flex-wrap:wrap; background:#050811; padding:16px; border-radius:8px; border:1px solid rgba(255,255,255,0.06);">
          <img src="${qr}" style="width:160px; height:160px; border-radius:8px; border:2px solid #38bdf8; background:white; padding:4px;">
          <div>
            <div style="font-size:13px; margin-bottom:8px;"><b>One-Tap Student Link:</b> <a href="${link}" target="_blank" style="color:#10b981;">${link}</a></div>
            <div style="font-size:12px; color:var(--text-muted); line-height:1.6; max-width:400px;">
              ఈ QR కోడ్ లేదా లింక్‌ను వాట్సాప్ గ్రూపులలో లేదా కాలేజీ ప్రొజెక్టర్‌పై షేర్ చేయండి. విద్యార్థులు ఒక్క ట్యాప్‌తో మీ స్క్వాడ్‌లో చేరవచ్చు!
            </div>
          </div>
        </div>
      `;
      modal.scrollIntoView({behavior: 'smooth'});
    }

    async function addStudentToSquad() {
      const code = (document.getElementById('join-squad-code').value || '').trim().toUpperCase();
      const uid = (document.getElementById('join-squad-uid').value || '').trim();
      const log = document.getElementById('join-squad-log');
      if (!code || !uid) return alert('Enter Squad Code and Student Mobile / Telegram ID');

      try {
        const res = await fetch('/api/squads/join', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({code, uid})
        });
        const d = await res.json();
        if (d.ok) {
          log.style.color = '#10b981';
          log.innerText = `✅ Added ${uid} to Squad SQ-${code}!`;
          document.getElementById('join-squad-uid').value = '';
          loadSquads();
        } else {
          log.style.color = '#ef4444';
          log.innerText = '❌ Failed: ' + (d.message || 'Error');
        }
      } catch (e) {
        log.style.color = '#ef4444';
        log.innerText = '❌ Error: ' + e;
      }
    }

    async function loadMembers() {
      const res = await fetch('/api/members');
      const d = await res.json();
      const tbody = document.querySelector('#table-members tbody');
      tbody.innerHTML = '';
      if (!d.members || d.members.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted); padding:16px;">No registered members yet. Use the Quick Register box above!</td></tr>';
        return;
      }
      for (const m of d.members.slice(0, 100)) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td style="font-family:monospace;">${m.uid}</td>
          <td><b>${esc(m.name)}</b>${m.weak_topic ? `<br><span style="font-size:11px; color:#f87171;">🎯 Weak: ${esc(m.weak_topic)}</span> <span style="font-size:11px; color:#64748b;">· ${m.accuracy}% acc</span>` : ''}</td>
          <td>${esc(m.district || '—')}</td>
          <td><span class="category-tag">${esc(m.exam || '—')}</span></td>
          <td style="color:var(--warning); font-weight:800; font-size:14px;">🏆 ${m.points}</td>
          <td>🔥 ${m.streak || 1}d</td>
          <td>${m.college || '—'}</td>
          <td>
            <button class="btn btn-outline" style="padding:2px 7px; font-size:11px;" onclick="addStudentPoints('${m.uid}', 10)">+10 Pts</button>
            <button class="btn btn-outline" style="padding:2px 7px; font-size:11px;" onclick="addStudentPoints('${m.uid}', 50)">+50 Pts</button>
          </td>
        `;
        tbody.appendChild(tr);
      }
    }

    async function quickRegisterStudent() {
      const uid = document.getElementById('reg-student-uid').value.trim();
      const name = document.getElementById('reg-student-name').value.trim();
      const dist = document.getElementById('reg-student-dist').value;
      const exam = document.getElementById('reg-student-exam').value;
      const pts = parseInt(document.getElementById('reg-student-pts').value) || 50;
      const log = document.getElementById('reg-student-log');

      if (!uid || !name) return alert('Enter Telegram ID / Mobile and Student Name');

      try {
        const res = await fetch('/api/members/register', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({uid, name, district: dist, exam, points: pts})
        });
        const d = await res.json();
        if (d.ok) {
          log.style.color = '#10b981';
          log.innerText = `✅ Registered ${name}! Awarded ${pts} initial points.`;
          document.getElementById('reg-student-uid').value = '';
          document.getElementById('reg-student-name').value = '';
          loadMembers();
          fetchStats();
        }
      } catch (e) {
        log.style.color = '#ef4444';
        log.innerText = '❌ Failed: ' + e;
      }
    }

    async function addStudentPoints(uid, pts) {
      try {
        const res = await fetch('/api/members/add_points', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({uid, points: pts})
        });
        const d = await res.json();
        if (d.ok) {
          loadMembers();
          fetchStats();
        }
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    async function createDashboardSquad() {
      const name = document.getElementById('new-squad-name').value.trim();
      const leader = document.getElementById('new-squad-leader').value.trim();
      if (!name) return alert('Enter Squad Name');
      try {
        const res = await fetch('/api/squads/create', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name, leader: leader || 'Admin'})
        });
        const d = await res.json();
        if (d.ok) {
          alert('🎉 Squad Created! Code: SQ-' + d.code);
          document.getElementById('new-squad-name').value = '';
          document.getElementById('new-squad-leader').value = '';
          loadSquads();
        } else {
          alert('Failed to create squad: ' + (d.message || 'Unknown error'));
        }
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    function _splitSubjects(txt) {
      return (txt || '').toUpperCase().split(/[^A-Z0-9]+/).filter(Boolean);
    }
    async function loadSetupOptions() {
      const sel = document.getElementById('ms-exam');
      if (!sel || sel.options.length) { /* already filled */ }
      try {
        const r = await fetch('/api/setup/options');
        const d = await r.json();
        if (sel && !sel.options.length) {
          sel.innerHTML = '<option value="AUTO">🤖 AUTO (name nunchi detect)</option>' +
            (d.exams || []).map(e => '<option value="' + e + '">' + e + '</option>').join('') +
            '<option value="CUSTOM">✏️ Custom exam (type cheyyandi)...</option>';
        }
        // Schedule Builder category dropdown loki kuda live exams add cheyyandi
        const wsel = document.getElementById('wa-target-category');
        if (wsel) {
          const have = Array.from(wsel.options).map(o => o.value);
          (d.exams || []).forEach(e => {
            if (!have.includes(e)) {
              const o = document.createElement('option'); o.value = e; o.textContent = '🎯 ' + e; wsel.appendChild(o);
            }
          });
        }
        const box = document.getElementById('ms-subjects');
        if (box && !box.children.length) {
          const icons = {MATHS:'🔢', REASONING:'🧠', GK:'🌍', CURRENT:'📰', ENGLISH:'🔤', SCIENCE:'🔬'};
          box.innerHTML = (d.subjects || []).map(s =>
            '<label style="display:flex; align-items:center; gap:4px;"><input type="checkbox" class="ms-subj" value="' + s + '">' +
            (icons[s] || '📚') + ' ' + s + '</label>').join('');
        }
      } catch (e) { /* form works with defaults too */ }
    }
    function msExamChanged() {
      const v = document.getElementById('ms-exam').value;
      document.getElementById('ms-exam-custom').style.display = (v === 'CUSTOM') ? 'block' : 'none';
    }
    function msPlatformChanged() {
      const v = document.getElementById('ms-platform').value;
      const ll = document.getElementById('ms-link-label');
      const sl = document.getElementById('ms-shift-label');
      if (v === 'wa') {
        ll.textContent = '🔗 Invite Link or JID';
        document.getElementById('ms-link').placeholder = 'https://chat.whatsapp.com/... లేదా 1203...@g.us లేదా Channel JID: 1203...@newsletter';
        sl.textContent = '⏰ Shift';
      } else {
        ll.textContent = '🔗 @username / t.me link / -100 ID';
        document.getElementById('ms-link').placeholder = '@YourChannel or https://t.me/YourChannel or -1001234567890';
        sl.textContent = '⏰ Shift (TG ki వర్తించదు)';
      }
    }
    async function manualAddTarget() {
      const box = document.getElementById('ms-result');
      const plat = document.getElementById('ms-platform').value;
      const name = document.getElementById('ms-name').value.trim();
      const link = document.getElementById('ms-link').value.trim();
      let exam = document.getElementById('ms-exam').value || 'AUTO';
      if (exam === 'CUSTOM') exam = document.getElementById('ms-exam-custom').value.trim();
      const subjects = Array.from(document.querySelectorAll('.ms-subj:checked')).map(c => c.value)
        .concat(_splitSubjects(document.getElementById('ms-subj-custom').value));
      if (!name || !link) { box.innerHTML = '<span style="color:#f87171;">❌ Name mariyu Link rendu ivvandi</span>'; return; }
      box.innerHTML = '<span style="color:#fbbf24;">Adding...</span>';
      try {
        const r = await fetch('/api/setup/manual_add', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            platform: plat === 'wa' ? 'wa' : 'tg',
            type: plat === 'tg-group' ? 'group' : (plat === 'tg-channel' ? 'channel' : document.getElementById('ms-type').value),
            name, link, exam,
            shift: document.getElementById('ms-shift').value,
            times: document.getElementById('ms-times').value.trim(),
            count: parseInt(document.getElementById('ms-count').value) || 5,
            days: parseInt(document.getElementById('ms-days').value) || 0,
            subjects
          })
        });
        const d = await r.json();
        let html = d.ok
          ? '<span style="color:#34d399;">' + d.message + '</span>'
          : '<span style="color:#f87171;">' + (d.message || 'Failed') + '</span>';
        (d.errors || []).forEach(e => { html += '<br><span style="color:#f87171;">❌ ' + e.reason + '</span>'; });
        (d.skipped_duplicates || []).forEach(e => { html += '<br><span style="color:#fbbf24;">⏭️ Duplicate: ' + e.name + '</span>'; });
        box.innerHTML = html;
        if (d.ok) {
          document.getElementById('ms-name').value = '';
          document.getElementById('ms-link').value = '';
          if (typeof loadWAGroups === 'function') loadWAGroups();
          if (typeof loadChannels === 'function') loadChannels();
          if (typeof loadSchedules === 'function') loadSchedules();
          if (typeof fetchStats === 'function') fetchStats();
        }
      } catch (e) { box.innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>'; }
    }

    async function loadVision() {
      try {
        const r = await fetch('/api/vision');
        const d = await r.json();
        const sc = document.getElementById('vision-score');
        if (!sc) return;
        sc.innerText = d.score + '/100';
        sc.style.color = d.score >= 75 ? '#34d399' : (d.score >= 50 ? '#fbbf24' : '#f87171');
        document.getElementById('vision-grade').innerText = '(' + d.grade + ')';
        const c = d.pillars.content, rc = d.pillars.reach, e = d.pillars.engagement, cov = d.pillars.coverage;
        const cell = (icon, title, lines) =>
          '<div style="background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:10px;">' +
          '<div style="font-weight:800; margin-bottom:4px;">' + icon + ' ' + title + '</div>' + lines + '</div>';
        document.getElementById('vision-pillars').innerHTML =
          cell('📚', 'Content', 'Bank <b>' + c.bank_questions + '</b> · PYQ <b>' + c.pyq_questions + '</b> (' + c.pyq_share_pct + '%)<br>Weakest stock: ' + c.min_channel + ' = ' + c.min_unused + '<br>Sources live ' + c.sources_live + '/' + c.sources_total + ' · Papers ' + c.pyq_papers) +
          cell('📡', 'Reach', rc.telegram_channels + ' TG channels · ' + rc.whatsapp_groups + ' WA groups<br>' + rc.members_registered + ' members · ' + rc.districts + ' districts') +
          cell('🎯', 'Engagement', 'Last 7d LIVE polls: <b>' + e.week_polls_sent + '</b> (dry ' + e.week_dry_polls + ')<br>' + e.students_with_points + ' students with points (' + e.total_points + ' pts)') +
          cell('🗓️', 'Coverage', cov.active_schedules + ' schedules (WA ' + cov.wa_jobs + ' · TG ' + cov.tg_jobs + ' · both ' + cov.both_jobs + ')<br>Autopilot leni channels: ' + cov.channels_without_autopilot.length);
        document.getElementById('vision-actions').innerHTML = (d.actions || []).length
          ? '<b style="color:#fbbf24;">👉 Next actions:</b><br>' + d.actions.map(a => '• ' + a).join('<br>')
          : '<span style="color:#34d399;">✅ Anni pillars healthy!</span>';
        document.getElementById('vision-next').innerText = '⏭️ Next collections today: ' + ((d.next_collections_today || []).join(', ') || '—');
      } catch (e) { /* vision card is best-effort */ }
    }

    async function loadSetupWizard() {
      const wrap = document.getElementById('wiz-steps');
      if (!wrap) return;
      wrap.innerHTML = '<div style="color:var(--text-muted); font-size:12px;">Checking...</div>';
      const get = async (u) => { try { const r = await fetch(u); return await r.json(); } catch (e) { return {}; } };
      const [health, bridges, chans, scheds, vision, retry, waGroups] = await Promise.all([
        get('/api/health'), get('/api/whatsapp/bridges'), get('/api/channels'),
        get('/api/whatsapp/schedules'), get('/api/vision'),
        get('/api/whatsapp/retry_queue'), get('/api/whatsapp/groups')]);
      const bList = bridges.bridges || [];
      const waConnected = bList.some(b => b.connected);
      const chCount = Object.keys(chans.channels || {}).length;
      const jobs = (scheds.jobs || []).filter(j => j.enabled !== false);
      const waJobs = jobs.filter(j => (j.mode || 'wa') !== 'tg').length;
      const tgJobs = jobs.filter(j => j.mode === 'tg').length;
      const waActive = (waGroups.groups || []).filter(g => g.active !== false).length;
      const card = (ok, warn, icon, title, detail, btnTab, btnTxt) => {
        const st = ok ? ['✅', '#34d399', 'READY'] : (warn ? ['⚠️', '#fbbf24', 'PARTIAL'] : ['⭕', '#f87171', 'PENDING']);
        return '<div style="background:#0b1329; border:1px solid ' + st[1] + '55; border-radius:10px; padding:13px;">' +
          '<div style="display:flex; justify-content:space-between; align-items:center;"><b style="font-size:13px;">' + icon + ' ' + title + '</b>' +
          '<span style="font-size:10px; font-weight:800; color:' + st[1] + ';">' + st[0] + ' ' + st[2] + '</span></div>' +
          '<div style="font-size:12px; color:var(--text-muted); margin:7px 0; min-height:32px;">' + detail + '</div>' +
          '<button class="btn btn-outline" style="padding:5px 11px; font-size:11.5px;" onclick="switchTab(\'' + btnTab + '\')">' + btnTxt + '</button></div>';
      };
      const steps = [
        card(!!health.telegram_live, chCount > 0, '🤖', '1. Telegram Bot',
          health.telegram_live ? 'Bot token LIVE · ' + chCount + ' channels/groups registered' : 'BOT_TOKEN set cheyyandi (env/.env) — tarvata bot ni channels lo admin cheyyandi',
          'tab-dynamic-channels', '📢 Channels Tab'),
        card(waConnected, bList.some(b => b.online), '💚', '2. WhatsApp Bridge',
          waConnected ? 'Connected: ' + (bList.filter(b => b.connected).map(b => b.phone || b.session || 'number').join(', ')) + ' · Pool: ' + bList.length + ' number(s)' + ((retry.count || 0) ? ' · 🔁 ' + retry.count + ' retry pending' : '') : (bList.some(b => b.online) ? 'Bridge run avuthondi kani WhatsApp link ledu — QR scan cheyyandi' : 'Bridge offline — start_all.sh lo automatic ga start avuthundi'),
          'tab-wa-dispatch', '🛡️ WhatsApp Tab (QR)'),
        card((chCount > 0 && waActive > 0), (chCount > 0 || waActive > 0), '🎯', '3. Targets (Groups/Channels)',
          chCount + ' Telegram targets · ' + waActive + ' WhatsApp groups active — Excel leda Manual form tho add cheyyandi',
          'tab-excel-import', '📊 Excel / Manual Setup'),
        card(jobs.length > 0, false, '🗓️', '4. Timings & Schedules',
          jobs.length ? jobs.length + ' active schedule(s) — WA ' + waJobs + ' · TG ' + tgJobs + ' · anni automatic ga post avuthaayi' : 'Inka okka schedule kuda ledu — timings set cheste roju automatic posts!',
          'tab-wa-dispatch', '⏰ Schedule Builder'),
        card((vision.score || 0) >= 50, (vision.score || 0) >= 25, '🎯', '5. Vision Health',
          'Vision Score: <b>' + (vision.score ?? '…') + '/100 (' + (vision.grade || '-') + ')</b>' + ((vision.actions || []).length ? '<br>Next: ' + vision.actions[0] : '<br>Anni pillars healthy!'),
          'tab-bulk-broadcast', '🏠 Home (Vision Card)'),
      ];
      const done = steps.filter(s => s.includes('READY')).length;
      document.getElementById('wiz-progress').style.width = (done * 20) + '%';
      wrap.innerHTML = steps.join('');
      document.getElementById('wiz-actions').innerHTML = (vision.actions || []).length
        ? '<b style="color:#fbbf24;">👉 System cheppe next actions:</b><br>' + vision.actions.map(a => '• ' + a).join('<br>')
        : '<span style="color:#34d399;">🎉 Anni steps ready — system full automatic ga nadusthundi!</span>';
    }

    async function loadItemIntel() {
      const box = document.getElementById('item-intel-body');
      if (!box) return;
      try {
        const r = await fetch('/api/item_intel');
        const d = await r.json();
        const row = (q, color, btn) =>
          '<div style="display:flex; justify-content:space-between; align-items:center; gap:8px; padding:5px 8px; background:rgba(255,255,255,0.03); border-radius:6px; margin-top:5px;">' +
          '<span><b style="color:' + color + ';">' + q.qid + '</b> <span style="color:var(--text-muted);">[' + (q.channel || '') + '/' + (q.topic || '') + '] ' +
          q.correct + '/' + q.attempts + ' correct (' + Math.round((q.rate || 0) * 100) + '%)</span></span>' + btn + '</div>';
        let html = 'Tracked: <b>' + d.tracked_questions + '</b> questions · 🚫 quarantined: <b style="color:#f87171;">' + d.suspect_count + '</b> · 😴 too-easy: <b>' + d.too_easy_count + '</b>';
        (d.suspect_key || []).forEach(q => {
          html += row(q, '#f87171;', '<button class="btn btn-outline" style="padding:3px 9px; font-size:11px;" onclick="resetItemStats(\'' + q.qid + '\')">🔓 Key fix chesa → Reset</button>');
        });
        (d.too_easy || []).slice(0, 5).forEach(q => { html += row(q, '#fbbf24', ''); });
        if (!d.suspect_count && !d.too_easy_count) html += '<div style="margin-top:6px; color:#34d399;">✅ Quality issues levu — answers vache koddi ikkada kanipisthayi.</div>';
        box.innerHTML = html;
      } catch (e) { box.innerHTML = '❌ ' + e; }
      loadBrain();
    }
    async function loadBrain() {
      const box = document.getElementById('brain-overview');
      if (!box) return;
      try {
        const r = await fetch('/api/brain/overview');
        const d = await r.json();
        const bands = Object.entries(d.bands || {}).map(([k, v]) => k + ': ' + v).join(' · ');
        box.innerHTML = '<b>🧠 Student Brain 3.0</b> — 👥 ' + (d.students || 0) + ' students tracked · ✍️ ' + (d.answers || 0) +
          ' answers · Avg ability θ ' + (d.avg_theta || 0) + (bands ? '<br><span style="color:var(--text-muted);">' + bands + '</span>' : '') +
          '<br><span style="color:var(--text-muted);">Ability (Elo) + Exam Readiness + level-wise Smart Practice — portal & bot rendu vaipu live.</span>';
      } catch (e) { box.innerHTML = ''; }
    }
    async function resetItemStats(qid) {
      if (!confirm(qid + ' stats reset cheyyala? (key fix ayyindi anukunte matrame)')) return;
      try {
        const r = await fetch('/api/item_intel/reset', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({qid})});
        const d = await r.json();
        alert(d.message || 'done');
        loadItemIntel();
      } catch (e) { alert('❌ ' + e); }
    }

    let _pulseBase = 0;
    function _inr(n) { return '₹' + Number(n || 0).toLocaleString('en-IN'); }
    function pulseRecompute() {
      const price = parseFloat(document.getElementById('pulse-price').value) || 0;
      const conv = parseFloat(document.getElementById('pulse-conv').value) || 0;
      const paying = Math.round(_pulseBase * conv / 100);
      const mrr = paying * price;
      document.getElementById('pulse-proj').innerHTML =
        'Base: <b>' + _pulseBase + '</b> members × ' + conv + '% → <b>' + paying + ' paying</b> → ' +
        '<b style="color:#34d399;">' + _inr(mrr) + '/month</b> · ' + _inr(mrr * 12) + '/year ' +
        '<span style="color:var(--text-muted);">(projection matrame — real billing start ayyaka actuals ikkada)</span>';
    }
    async function loadPulse() {
      try {
        const r = await fetch('/api/pulse');
        const d = await r.json();
        const f = d.funnel, e = d.economy, p = d.planner;
        _pulseBase = p.base_members;
        const card = (label, val, sub) => '<div class="stat-card"><div class="label">' + label + '</div><div class="val">' + val + '</div><div style="font-size:11px; color:var(--text-muted);">' + (sub || '') + '</div></div>';
        document.getElementById('pulse-cards').innerHTML =
          card('GROWTH SCORE', d.growth_score + '/100', 'activation+activity+referrals') +
          card('REGISTERED', f.registered, f.activated + ' activated (' + f.activation_pct + '%)') +
          card('ACTIVE 7D', f.active_7d, f.active_today + ' today') +
          card('REFERRAL JOINS', f.referred_members, f.total_referral_activated + ' activated · ' + f.referrers + ' referrers');
        const bar = (label, v, total) => {
          const pct = total ? Math.round(100 * v / total) : 0;
          return '<div style="margin-top:5px;">' + label + ': <b>' + v + '</b> <span style="color:var(--text-muted);">(' + pct + '%)</span>' +
            '<div style="height:7px; background:rgba(255,255,255,0.08); border-radius:4px;"><div style="height:7px; width:' + pct + '%; background:linear-gradient(90deg,#38bdf8,#34d399); border-radius:4px;"></div></div></div>';
        };
        document.getElementById('pulse-funnel').innerHTML =
          bar('Registered', f.registered, f.registered) + bar('Activated (≥1 answer)', f.activated, f.registered) +
          bar('Active last 7 days', f.active_7d, f.registered) + bar('Came via referral', f.referred_members, f.registered);
        document.getElementById('pulse-referrers').innerHTML = (f.top_referrers.length ? f.top_referrers.map(x =>
          '<div style="padding:4px 8px; background:rgba(255,255,255,0.03); border-radius:6px; margin-top:4px;">' +
          (x.tier ? x.tier + ' ' : '') + '<b>' + x.name + '</b> <span style="color:var(--text-muted);">' + (x.district || '') +
          ' · ' + x.referrals + ' friends · ' + x.activated + ' activated</span></div>').join('')
          : '<span style="color:var(--text-muted);">Inka referrers leru — students /invite vadithe ikkada kanipistharu.</span>');
        document.getElementById('pulse-economy').innerHTML =
          '🏪 ' + e.partners + ' partners · 🎁 ' + e.offers + ' offers · ✅ ' + e.vouchers_used + ' redeemed · ⏳ ' +
          e.vouchers_held + ' pending at shops (' + e.points_held_at_shops + ' pts) · 🪙 ' + e.points_in_circulation +
          ' pts circulation · 🎟 ' + e.points_redeemed + ' pts redeemed all-time';
        document.getElementById('pulse-plan-name').value = p.plan_name || '';
        document.getElementById('pulse-price').value = p.price_inr;
        document.getElementById('pulse-conv').value = p.conversion_pct;
        pulseRecompute();
      } catch (e) {
        document.getElementById('pulse-cards').innerHTML = '<div style="color:#f87171; font-size:12px;">❌ ' + e + '</div>';
      }
    }
    async function savePulseSettings() {
      try {
        const body = {plan_name: document.getElementById('pulse-plan-name').value,
                      price_inr: parseInt(document.getElementById('pulse-price').value) || 0,
                      conversion_pct: parseFloat(document.getElementById('pulse-conv').value) || 0};
        const r = await fetch('/api/pulse/settings', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        const d = await r.json();
        if (d && d.planner) { alert('✅ Planner assumptions save ayyayi — base: ' + d.planner.base_members + ' members'); loadPulse(); }
        else alert('❌ save avvaledu');
      } catch (e) { alert('❌ ' + e); }
    }

    async function loadProOps() {
      const dot = s => s === 'ok' ? '🟢' : (s === 'warn' ? '🟡' : '🔴');
      try {
        const [h, m, f, a] = await Promise.all([
          fetch('/api/health/full').then(r => r.json()),
          fetch('/api/metrics').then(r => r.json()),
          fetch('/api/flags').then(r => r.json()),
          fetch('/api/audit').then(r => r.json())]);
        document.getElementById('proops-health').innerHTML =
          '<div style="margin-bottom:8px;">Overall: <b>' + dot(h.overall) + ' ' + String(h.overall || '').toUpperCase() + '</b>' +
          ' · uptime ' + (h.uptime_min || 0) + ' min · Python ' + (h.system ? h.system.python : '?') + ' · ' + (h.generated_at || '') + '</div>' +
          (h.checks || []).map(c => '<div style="padding:4px 8px; background:rgba(255,255,255,0.03); border-radius:6px; margin-top:4px;">' +
            dot(c.status) + ' <b>' + c.name + '</b> <span style="color:var(--text-muted);">' + c.detail + '</span></div>').join('');
        if (h.golive) {
          document.getElementById('proops-health').innerHTML +=
            '<div style="margin-top:12px; margin-bottom:4px;">🚀 Subdomain Go-Live: <b>' + String(h.golive.overall || '').toUpperCase() + '</b> <span style="color:var(--text-muted);">(docs/SUBDOMAIN_GO_LIVE.md)</span></div>' +
            (h.golive.checks || []).map(c => '<div style="padding:4px 8px; background:rgba(255,255,255,0.03); border-radius:6px; margin-top:4px;">' +
              dot(c.status) + ' <b>' + c.name + '</b> <span style="color:var(--text-muted);">' + c.detail + '</span></div>').join('');
        }
        const c = m.counters || {}, d = m.delivery || {};
        const card = (label, val, sub) => '<div class="stat-card"><div class="label">' + label + '</div><div class="val">' + val + '</div><div style="font-size:11px; color:var(--text-muted);">' + (sub || '') + '</div></div>';
        document.getElementById('proops-metrics').innerHTML =
          card('WA DELIVERY', (d.success_pct === null || d.success_pct === undefined) ? '—' : d.success_pct + '%', d.sent + ' sent · ' + d.failed + ' failed') +
          card('ANSWERS TODAY', (m.today || {}).answers || 0, ((m.today || {}).answers_correct || 0) + ' correct today') +
          card('ANSWERS (ALL-TIME)', c.answers || 0, 'metrics start: ' + String(m.started_at || '').slice(0, 10)) +
          card('RETRIES QUEUED (LIFETIME)', c.wa_retry_enqueued || 0, 'failed sends auto-retry count');
        const s = (m.hourly_series || {}).answers || {values: [], labels: []};
        const mx = Math.max(1, ...s.values);
        document.getElementById('proops-chart').innerHTML = s.values.map((v, i) =>
          '<div title="' + (s.labels[i] || '') + ': ' + v + '" style="flex:1; min-height:2px; height:' + Math.max(3, Math.round(58 * v / mx)) +
          'px; background:linear-gradient(180deg,#38bdf8,#2563eb); border-radius:2px;"></div>').join('') ||
          '<span style="color:var(--text-muted);">Inka data ledu</span>';
        document.getElementById('proops-flags').innerHTML = (f.flags || []).map(x =>
          '<div style="display:flex; justify-content:space-between; align-items:center; gap:10px; padding:6px 8px; background:rgba(255,255,255,0.03); border-radius:6px; margin-top:5px;">' +
          '<span><b>' + x.label + '</b>' + (x.overridden ? ' <span style="color:#fbbf24;">(override)</span>' : '') +
          '<br><span style="color:var(--text-muted);">' + x.desc + '</span></span>' +
          '<label style="display:flex; align-items:center; gap:6px; white-space:nowrap;">' +
          '<input type="checkbox" ' + (x.enabled ? 'checked' : '') + ' onchange="toggleFlag(\'' + x.name + '\', this.checked)"> ' +
          (x.enabled ? 'ON' : 'OFF') + '</label></div>').join('');
        document.getElementById('proops-audit').innerHTML = (a.entries || []).length ? (a.entries || []).map(e =>
          '<div style="padding:4px 8px; background:rgba(255,255,255,0.03); border-radius:6px; margin-top:4px;">' +
          '<span style="color:var(--text-muted);">' + e.ts + '</span> <b>' + e.action + '</b> ' +
          '<span style="color:var(--text-muted);">' + (e.detail || '') + '</span></div>').join('')
          : '<span style="color:var(--text-muted);">Inka audit entries levu — dashboard actions ikkada record avuthayi.</span>';
      } catch (e) {
        document.getElementById('proops-health').innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>';
      }
    }
    async function toggleFlag(name, enabled) {
      try {
        const r = await fetch('/api/flags', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name, enabled})});
        const d = await r.json();
        if (!d.ok) alert('❌ Flag update avvaledu');
        loadProOps();
      } catch (e) { alert('❌ ' + e); }
    }
    setInterval(() => {
      const pane = document.getElementById('tab-proops');
      if (pane && pane.classList.contains('active')) loadProOps();
    }, 30000);

    function applySmartHour(h) {
      const el = document.getElementById('cd-when');
      const d = new Date();
      d.setDate(d.getDate() + 1);
      d.setHours(h, 0, 0, 0);
      const p2 = n => String(n).padStart(2, '0');
      el.value = d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate()) + 'T' + p2(d.getHours()) + ':00';
      el.scrollIntoView({behavior: 'smooth', block: 'center'});
    }
    async function scheduleSmartHour(h) {
      const ch = document.getElementById('cd-channel').value || 'CURRENT';
      const p2 = n => String(n).padStart(2, '0');
      const time = p2(h) + ':00';
      if (!confirm('🔁 Daily schedule: prathi roju ' + time + ' ki ' + ch + ' channel/group ki automatic ga 5 polls vellala?')) return;
      try {
        const r = await fetch('/api/telegram/schedule', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({times: [time], channels: [ch], count: 5})});
        const d = await r.json();
        alert(d.ok ? ('✅ ' + d.message + '\nSchedules tab lo job kanipistundi — akkada off/edit cheyyochu.') : ('❌ ' + (d.error || 'failed')));
      } catch (e) { alert('❌ ' + e); }
    }
    function cdKindHint() {
      const k = document.getElementById('cd-kind').value;
      const hints = {
        grand: '📝 Channel lo full mock — sections, negative marking, results settle anni engine chesthundi.',
        war: '⚔️ Lobby open avuthundi, districts madhya live war — bot tick start chesthundi. WAR_TIME daily war ki idhi additional.',
        campus: '🏫 Join code ippude create avuthundi — code students tho share cheyyandi, time ki exam start avuthundi (kammi 2 registered students kavali).'
      };
      document.getElementById('cd-hint').textContent = hints[k] || '';
      document.getElementById('cd-duration').value = k === 'war' ? 30 : (k === 'campus' ? 60 : 90);
      document.getElementById('cd-nq').value = k === 'campus' ? 20 : 25;
    }
    async function loadConductor() {
      try {
        const d = await fetch('/api/conductor').then(r => r.json());
        const sel = document.getElementById('cd-channel');
        if (sel && !sel.options.length) (d.channels || []).forEach(c => {
          const o = document.createElement('option'); o.value = c; o.textContent = c; sel.appendChild(o);
        });
        const h = await fetch('/api/health').then(r => r.json()).catch(() => ({}));
        document.getElementById('conductor-daily').innerHTML =
          '📌 <b>Daily Fixed Polls:</b> Telegram Auto-Pilot slots <b>' + (h.autopilot_slots ?? '?') + '</b> · WhatsApp slots <b>' +
          (h.wa_slots ?? '?') + '</b> · ee week polls <b>' + (h.week_polls ?? '?') + '</b> — timings marchali ante ' +
          '<a href="#" onclick="switchTab(\'tab-setup-wizard\'); return false;">🚀 Setup Wizard</a> / ' +
          '<a href="#" onclick="switchTab(\'tab-dynamic-channels\'); return false;">📢 Telegram tab</a> chudandi.';
        try {
          const mm = await fetch('/api/metrics').then(r => r.json());
          const prof = mm.hour_profile || {};
          const rows = Object.entries(prof).map(([h, v]) => ({h: parseInt(h), v})).filter(x => x.v > 0).sort((a, b) => b.v - a.v);
          const tot = rows.reduce((s, x) => s + x.v, 0);
          const adv = document.getElementById('conductor-advisor');
          if (tot < 50) {
            adv.innerHTML = '🧠 <b>Smart Slot Advisor:</b> students eppudu ekkuva answer chestharo nerchukuntundi — ippatiki ' + tot + ' answers matrame. 50+ ayyaka best times suggest chesthundi.';
          } else {
            const mx = rows[0].v;
            adv.innerHTML = '🧠 <b>Smart Slot Advisor</b> — students ekkuva answer chesina hours (14 days, ' + tot + ' answers):' +
              rows.slice(0, 3).map(x => '<div style="margin-top:5px;">🕐 <b>' + String(x.h).padStart(2, '0') + ':00</b> — ' + x.v + ' answers ' +
                '<button class="btn btn-outline" style="padding:2px 9px; font-size:11px;" onclick="applySmartHour(' + x.h + ')">ee time ki exam schedule chey</button> ' +
                '<button class="btn btn-outline" style="padding:2px 9px; font-size:11px;" onclick="scheduleSmartHour(' + x.h + ')">🔁 daily schedule</button>' +
                '<div style="height:6px; background:rgba(255,255,255,0.08); border-radius:3px; margin-top:3px;"><div style="height:6px; width:' + Math.round(100 * x.v / mx) + '%; background:linear-gradient(90deg,#a78bfa,#38bdf8); border-radius:3px;"></div></div></div>').join('');
          }
        } catch (e) { /* advisor optional */ }
        const chip = s => ({scheduled: '🔵', live: '🔴 LIVE', done: '✅ done', failed: '❌ failed', cancelled: '⚪ cancelled'}[s] || s);
        document.getElementById('conductor-events').innerHTML = (d.events || []).length ? (d.events || []).map(e =>
          '<div style="display:flex; justify-content:space-between; align-items:center; gap:8px; padding:6px 8px; background:rgba(255,255,255,0.03); border-radius:6px; margin-top:5px; flex-wrap:wrap;">' +
          '<span><b>' + e.title + '</b> <span style="color:var(--text-muted);">' + (d.kinds[e.kind] ? d.kinds[e.kind].label : e.kind) +
          ' · ' + String(e.starts_at).replace('T', ' ') + (e.starts_in_min !== null && e.status === 'scheduled' ? ' · ⏳ ' + e.starts_in_min + ' min lo' : '') +
          (e.engine_ref ? ' · code <b>' + e.engine_ref + '</b>' : '') + (e.error ? ' · <span style="color:#f87171;">' + e.error + '</span>' : '') +
          (e.note ? '<br><span style="color:var(--text-muted);">' + e.note + '</span>' : '') + '</span></span>' +
          '<span style="display:flex; gap:6px; align-items:center;">' + chip(e.status) +
          (e.status === 'scheduled' || e.status === 'failed' ? '<button class="btn btn-accent" style="padding:3px 10px; font-size:11px;" onclick="launchConductorEvent(\'' + e.id + '\')">🚀 Launch Now</button>' : '') +
          (e.status === 'scheduled' || e.status === 'live' ? '<button class="btn btn-outline" style="padding:3px 10px; font-size:11px;" onclick="cancelConductorEvent(\'' + e.id + '\')">✖ Cancel</button>' : '') +
          (e.status === 'done' || e.status === 'live' ? '<button class="btn btn-outline" style="padding:3px 10px; font-size:11px;" onclick="conductorResult(\'' + e.id + '\')">📊 Result</button>' : '') +
          '</span></div>').join('')
          : '<span style="color:var(--text-muted);">Inka exams levu — paina form tho first exam schedule cheyyandi!</span>';
        cdKindHint();
      } catch (e) {
        document.getElementById('conductor-events').innerHTML = '<span style="color:#f87171;">❌ ' + e + '</span>';
      }
    }
    async function createConductorEvent() {
      const when = document.getElementById('cd-when').value;
      if (!when) { alert('❌ Date + Time select cheyyandi'); return; }
      const body = {
        title: document.getElementById('cd-title').value,
        kind: document.getElementById('cd-kind').value,
        channel: document.getElementById('cd-channel').value || 'CURRENT',
        starts_at: when,
        duration_min: parseInt(document.getElementById('cd-duration').value) || 0,
        n_questions: parseInt(document.getElementById('cd-nq').value) || 0,
        lobby_min: parseInt(document.getElementById('cd-lobby').value) || 5,
        campus_name: document.getElementById('cd-campus').value,
        district: document.getElementById('cd-district').value
      };
      try {
        const r = await fetch('/api/conductor/create', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        const d = await r.json();
        alert(d.ok ? ('✅ ' + (d.message || 'scheduled')) : ('❌ ' + (d.error || 'failed')));
        if (d.ok) loadConductor();
      } catch (e) { alert('❌ ' + e); }
    }
    async function launchConductorEvent(id) {
      if (!confirm('Ippude launch cheyyala? Real channels/groups ki posts vellochu.')) return;
      try {
        const r = await fetch('/api/conductor/launch', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id})});
        const d = await r.json();
        alert((d.ok ? '✅ ' : '❌ ') + (d.message || ''));
        loadConductor();
      } catch (e) { alert('❌ ' + e); }
    }
    async function cancelConductorEvent(id) {
      try {
        await fetch('/api/conductor/cancel', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id})});
        loadConductor();
      } catch (e) { alert('❌ ' + e); }
    }
    async function conductorResult(id) {
      try {
        const r = await fetch('/api/conductor/result', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id})});
        const d = await r.json();
        alert(d.ok ? d.text : ('❌ ' + (d.error || '')));
      } catch (e) { alert('❌ ' + e); }
    }

    fetchStats();
    loadVision();
    loadSetupOptions();
    loadWASession();
    loadMemberQueue();
    loadWAGroups();
    loadSchedules();
    loadChannels();
    loadBundles();
    loadGapSettings();
    loadBulkTargets();
    refreshStatusStrip();
    renderMissionHome();
    setInterval(fetchStats, 10000);
    setInterval(loadVision, 60000);
    setInterval(pollPipelineStatus, 1500);
    setInterval(loadWASession, 10000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # 🚀 keep-alive — anni responses Content-Length disciplined
    # ---------------- 🔒 access lock helpers ----------------
    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie", "") or ""
        for part in raw.split(";"):
            k, _, v = part.strip().partition("=")
            if k == "su_auth":
                return v.strip()
        return ""

    def _authed(self) -> bool:
        tok = self._cookie_token()
        return bool(tok) and tok in _load_auth().get("tokens", [])

    # ---------------- 🛡️ RATE LIMIT (public API anti-spam) ----------------
    _RL = {}

    def _rate_ok(self, key, limit=12, window=600):
        """Simple sliding-window limiter (per key, e.g. register/IP)."""
        now = time.time()
        hits = [t for t in self._RL.get(key, []) if now - t < window]
        if len(hits) >= limit:
            self._RL[key] = hits
            return False
        hits.append(now)
        self._RL[key] = hits
        return True

    # ---------------- 🛡️ IP ALLOWLIST (2nd security layer) ----------------
    def _client_ip(self) -> str:
        """Real visitor IP. Behind the preview proxy the trusted proxy APPENDS
        the real client IP to X-Forwarded-For — so take the LAST entry
        (first entries can be spoofed by the client)."""
        xff = (self.headers.get("X-Forwarded-For", "") or "").strip()
        if xff:
            return xff.split(",")[-1].strip()
        return self.client_address[0]

    def _ip_allowed(self) -> bool:
        if os.environ.get("DISABLE_IP_LOCK") == "1":
            return True  # emergency override: restart server with DISABLE_IP_LOCK=1
        sec = _load_auth()
        if not sec.get("ip_lock_enabled"):
            return True
        allowed = [str(a).strip() for a in (sec.get("allowed_ips") or []) if str(a).strip()]
        if not allowed:
            return True
        # sandbox-local failsafe: direct loopback requests (no proxy header) always pass
        xff = (self.headers.get("X-Forwarded-For", "") or "").strip()
        if not xff and self.client_address[0] in ("127.0.0.1", "::1", "localhost"):
            return True
        ip = self._client_ip()
        import ipaddress
        try:
            ipobj = ipaddress.ip_address(ip)
        except ValueError:
            ipobj = None
        for e in allowed:
            if e == ip:
                return True
            if (e.endswith(".") or e.endswith(":")) and ip.startswith(e):
                return True  # prefix rule e.g. "49.37." matches whole mobile range
            if "/" in e and ipobj is not None:
                try:
                    if ipobj in ipaddress.ip_network(e, strict=False):
                        return True
                except ValueError:
                    pass
        return False

    def _deny_ip(self, is_api: bool):
        ip = self._client_ip()
        if is_api:
            self._send_json({"ok": False, "error": f"access denied — your IP {ip} is not in the allowlist"}, code=403)
            return
        body = ("<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
                "<title>403 — Access Denied</title></head>"
                "<body style='background:#0b1220; color:#e2e8f0; font-family:sans-serif; display:flex; align-items:center; justify-content:center; height:100vh; margin:0;'>"
                "<div style='text-align:center; max-width:420px; padding:24px;'>"
                "<div style='font-size:52px;'>🛡️</div>"
                "<h2 style='color:#f87171;'>Access Denied</h2>"
                f"<p style='color:#94a3b8;'>Your IP <b style='color:#fbbf24;'>{ip}</b> is not in the admin allowlist.</p>"
                "<p style='color:#64748b; font-size:13px;'>ఈ dashboard కొన్ని IP addresses కి మాత్రమే open అవుతుంది. Admin ని సంప్రదించండి.</p>"
                "</div></body></html>").encode("utf-8")
        self.send_response(403)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


    def _deny(self, is_api: bool):
        if is_api:
            self._send_json({"ok": False, "error": "unauthorized — login required"}, code=401)
        else:
            body = LOGIN_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _issue_login_cookie(self):
        auth = _load_auth()
        tok = _secrets.token_hex(24)
        auth.setdefault("tokens", []).append(tok)
        auth["tokens"] = auth["tokens"][-25:]  # keep last 25 sessions
        _save_auth(auth)
        body = json.dumps({"ok": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        _secure = "; Secure" if (self.headers.get("X-Forwarded-Proto") == "https"
                                 or _public_base(self).startswith("https://")) else ""
        self.send_header("Set-Cookie", f"su_auth={tok}; Path=/; Max-Age=2592000; HttpOnly; SameSite=Lax{_secure}")
        self.end_headers()
        self.wfile.write(body)

    def _gz(self, body):
        """🚀 gzip — mobile students ki bandwidth save (pedda pages/JSON)."""
        try:
            if len(body) > 800 and "gzip" in (self.headers.get("Accept-Encoding") or ""):
                import gzip as _gzip
                return _gzip.compress(body, compresslevel=6), "gzip"
        except Exception:
            pass
        return body, None

    def _sec_headers(self):
        # 🛡️ 240X SECURITY HEADERS (baseline): MIME-sniff block,
        # clickjacking (same-origin framing matrame — preview /
        # Telegram webview direct navigation ki effect ledu),
        # referrer hygiene. HSTS production-https venaka enable.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")

    def _send_text(self, body_text, code=200, ctype="text/plain; charset=utf-8"):
        body, enc = self._gz(body_text.encode("utf-8"))
        self.send_response(code)
        self._sec_headers()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data, code=200):
        try:
            raw = json.dumps(data, ensure_ascii=False)
        except Exception:
            raw = '{"ok": false, "error": "serialization failed"}'
            code = 500
        body, enc = self._gz(raw.encode("utf-8"))
        self.send_response(code)
        self._sec_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        # 🔒 280X (F7): allowlist CORS — echo only trusted origins.
        _co280 = _cors_origin(self.headers.get("Origin", ""))
        if _co280:
            self.send_header("Access-Control-Allow-Origin", _co280)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, etag=False):
        # ⚡ 100X: static-ish pages (portal/public) ki ETag — repeat
        # visits lo 304 (body download ae undadu, instant load).
        if etag:
            import hashlib as _hl
            tag = '"' + _hl.sha1(html.encode("utf-8")).hexdigest()[:20] + '"'
            if (self.headers.get("If-None-Match") or "") == tag:
                self.send_response(304)
                self.send_header("ETag", tag)
                self.send_header("Cache-Control", "public, max-age=60")
                self.end_headers()
                return
            body, enc = self._gz(html.encode("utf-8"))
            self.send_response(200)
            self._sec_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("ETag", tag)
            self.send_header("Cache-Control", "public, max-age=60")
            if enc:
                self.send_header("Content-Encoding", enc)
                self.send_header("Vary", "Accept-Encoding")
            self.end_headers()
            self.wfile.write(body)
            return
        body, enc = self._gz(html.encode("utf-8"))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        # 🔒 280X (F7): preflight answered ONLY for allowlisted origins.
        _co280 = _cors_origin(self.headers.get("Origin", ""))
        self.send_response(204 if _co280 else 403)
        if _co280:
            self.send_header("Access-Control-Allow-Origin", _co280)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        try:
            self._do_GET()
        except Exception as e:
            # 🛡️ Endpoint crash aina browser ki JSON error padali —
            # empty reply ("anni errors") raakudadhu.
            print(f"   [dashboard] GET {self.path} error: {e}")
            try:
                self._send_json({"ok": False,
                                 "error": f"server error: {e}"}, code=500)
            except Exception:
                pass

    def _do_GET(self):
        p = urllib.parse.urlparse(self.path)

        # 🛡️ IP allowlist — checked BEFORE everything (even the login page)
        if not self._ip_allowed():
            self._deny_ip(is_api=p.path.startswith("/api/"))
            return

        # 🔒 Access lock: everything requires login except the login page itself
        if p.path == "/login":
            self._deny(is_api=False)
            return

        # 📱 PWA assets — login అవసరం లేదు (browser install కోసం), IP lock apply అవుతుంది
        if p.path == "/sw.js":
            self._send_text(
                "const C='studentup-v5';"
                "self.addEventListener('install',e=>{self.skipWaiting();"
                "e.waitUntil(caches.open(C).then(c=>c.addAll(['/portal','/','/icon.svg','/manifest.json'])))});"
                "self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});"
                "self.addEventListener('fetch',e=>{const u=new URL(e.request.url);"
                "if(e.request.method!=='GET'||u.pathname.startsWith('/api/'))return;"
                "e.respondWith(fetch(e.request).then(r=>{const cp=r.clone();"
                "caches.open(C).then(c=>c.put(e.request,cp));return r;})"
                ".catch(()=>caches.match(e.request)))})",
                ctype="application/javascript; charset=utf-8")
            return

        if p.path == "/manifest.json":
            body = json.dumps({
                "name": "StudentUp — Daily Quiz, Mock Tests & Live Exams",
                "short_name": "StudentUp",
                "description": "Free quiz practice, PYQs, college exams and leaderboards for AP & Telangana students.",
                "start_url": "/portal",
                "scope": "/",
                "display": "standalone",
                "background_color": "#050811",
                "theme_color": "#0b1329",
                "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}],
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if p.path == "/icon.svg":
            body = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                    '<rect width="100" height="100" rx="20" fill="#0b1220"/>'
                    '<text x="50" y="62" font-size="52" text-anchor="middle">🚀</text>'
                    '<text x="50" y="92" font-size="14" text-anchor="middle" fill="#38bdf8" '
                    'font-family="sans-serif" font-weight="bold">StudentUp</text></svg>').encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # 🌐 Student Web Exam — login akkarledu (students browser lone exam)
        if p.path.startswith("/exam/"):
            self._send_html(WEB_EXAM_HTML)
            return
        if p.path == "/api/exam/info":
            query = urllib.parse.parse_qs(p.query)
            code = query.get("code", [""])[0]
            d = campus._load(); e = d["events"].get(code)
            if not e:
                self._send_json({"ok": False, "error": "Exam not found"})
            else:
                self._send_json({"ok": True, "exam": e.get("name", ""),
                                 "n_q": e.get("n_q", 0),
                                 "colleges": e.get("colleges", []),
                                 "state": e.get("state", "open"),
                                 "joined": len(e.get("players", {}))})
            return
        if p.path == "/api/exam/state":
            query = urllib.parse.parse_qs(p.query)
            code = query.get("code", [""])[0]
            tok = query.get("token", [""])[0]
            snap = campus.web_state(code, tok)
            if snap is None:
                self._send_json({"ok": False, "error": "session expired — link malli open cheyyandi"})
            else:
                if (snap["state"] in ("question", "gap")
                        or (snap["state"] == "open" and snap.get("start_at"))):
                    try:
                        campus.tick(Telegram(), Members())
                    except Exception:
                        pass
                    snap = campus.web_state(code, tok) or snap
                self._send_json({"ok": True, **snap})
            return
        # 🌍 Public Website + AdSense kit — login akkarledu
        if p.path == "/" and not self._authed():
            _host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").split(":")[0]
            if _host.split(".")[0].lower() in ("quiz", "exam", "app", "portal"):
                self._send_html(PORTAL_HTML, etag=True)   # 🌐 subdomain = student portal
            else:
                self._send_html(public_page(self, "home"), etag=True)
            return
        if p.path == "/portal":
            self._send_html(PORTAL_HTML, etag=True)
            return
        if p.path == "/api/blog/posts":
            self._send_json({"ok": True, "posts": _fetch_wp_posts(12),
                             "site": _wp_base()})
            return
        if p.path == "/api/portal/meta":
            from core import districts as _D
            self._send_json({"ok": True,
                             "districts": ([{"name": x[0], "state": "AP"} for x in _D.AP_DISTRICTS]
                                           + [{"name": x[0], "state": "TG"} for x in _D.TS_DISTRICTS]),
                             "goals": {k: v["label"] for k, v in portal.GOALS.items()},
                             "topics": portal.topics_list()})
            return
        if p.path == "/api/portal/report":
            query = urllib.parse.parse_qs(p.query)
            rp = portal.my_report(Members(), query.get("token", [""])[0])
            self._send_json({"ok": rp is not None, **(rp or {"error": "session expired"})})
            return
        if p.path == "/api/portal/state":
            query = urllib.parse.parse_qs(p.query)
            st = portal.state(Members(), query.get("token", [""])[0])
            self._send_json({"ok": bool(st), **(st or {"error": "session expired"})})
            return

        if p.path == "/api/portal/state_hub":
            # 🗺️ 330X: TS & AP exam hub (public honest counts).
            self._send_json({"ok": True, **portal.state_hub()})
            return

        if p.path == "/api/portal/paper/catalog":
            self._send_json({"ok": True, "papers": portal.paper_catalog()})
            return
        if p.path == "/api/portal/syllabus":
            query = urllib.parse.parse_qs(p.query)
            sy = portal.my_syllabus(Members(), query.get("token", [""])[0])
            self._send_json({"ok": sy is not None, **(sy or {"error": "session expired"})})
            return
        if p.path == "/api/portal/syllabus2":
            query = urllib.parse.parse_qs(p.query)
            sy = portal.syllabus_plan(Members(), query.get("token", [""])[0])
            self._send_json({"ok": sy is not None, **(sy or {"error": "syllabus ready ledu"})})
            return
        if p.path == "/api/portal/district":
            query = urllib.parse.parse_qs(p.query)
            dd = portal.district_deep(Members(), query.get("token", [""])[0])
            self._send_json({"ok": dd is not None, **(dd or {"error": "session expired"})})
            return
        if p.path == "/api/portal/revision":
            query = urllib.parse.parse_qs(p.query)
            rp = portal.revision_planner(Members(), query.get("token", [""])[0])
            self._send_json({"ok": rp is not None, **(rp or {"error": "session expired"})})
            return
        if p.path == "/api/portal/rank2":
            query = urllib.parse.parse_qs(p.query)
            rk = portal.rank_predict(Members(), query.get("token", [""])[0])
            self._send_json({"ok": rk is not None, **(rk or {"error": "session expired"})})
            return
        if p.path == "/api/portal/materials":
            query = urllib.parse.parse_qs(p.query)
            mc = portal.materials_catalog(Members(), query.get("token", [""])[0])
            self._send_json({"ok": mc is not None, **(mc or {"error": "session expired"})})
            return
        if p.path == "/api/portal/st270":
            # 🔐 270X: portable shared-host bundle for one Stateless token.
            # (student-carried HMAC state; zero server student storage)
            # Signed claims verify locally; dashboard cookie
            # not required because the student token itself proves.
            query = urllib.parse.parse_qs(p.query)
            _tok270 = query.get("token", [""])[0]
            try:
                from core import stateless_client as _sl270
                _view270 = _sl270.public_view(_tok270)
            except Exception:
                _view270 = None
            if not _view270:
                self._send_json({"ok": False,
                                 "error": "invalid/expired token"},
                                code=401)
                return
            self._send_json({"ok": True, "stateless": True,
                             **_view270})
            return
        if p.path == "/api/portal/materials_suggest":
            query = urllib.parse.parse_qs(p.query)
            ms = portal.materials_suggest(Members(), query.get("token", [""])[0])
            self._send_json({"ok": ms is not None, **(ms or {"error": "session expired"})})
            return
        if p.path == "/api/portal/material_file":
            query = urllib.parse.parse_qs(p.query)
            data, fname = portal.materials_file(Members(), query.get("token", [""])[0], query.get("id", [""])[0])
            if not data:
                self._send_json({"ok": False, "error": "file ready ledu / unlock cheyyaledu"}, code=404)
                return
            ctype = "application/pdf" if fname.lower().endswith(".pdf") else "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition", "attachment; filename=" + fname)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if p.path == "/api/portal/score_intel":
            query = urllib.parse.parse_qs(p.query)
            si = portal.score_intelligence(Members(), query.get("token", [""])[0])
            self._send_json({"ok": si is not None, **(si or {"error": "session expired"})})
            return
        if p.path == "/api/portal/coach":
            query = urllib.parse.parse_qs(p.query)
            co = portal.coach_today(Members(), query.get("token", [""])[0])
            self._send_json({"ok": co is not None, **(co or {"error": "session expired"})})
            return
        if p.path == "/api/portal/percentile":
            query = urllib.parse.parse_qs(p.query)
            pc = portal.goal_percentile(Members(), query.get("token", [""])[0])
            self._send_json({"ok": pc is not None, **(pc or {"error": "session expired"})})
            return
        if p.path == "/api/portal/bookmarks":
            query = urllib.parse.parse_qs(p.query)
            bm = portal.my_bookmarks(Members(), query.get("token", [""])[0])
            self._send_json({"ok": True, "bookmarks": bm})
            return
        if p.path == "/api/portal/archive":
            query = urllib.parse.parse_qs(p.query)
            ar = portal.my_archive(Members(), query.get("token", [""])[0])
            self._send_json({"ok": True, "archive": ar})
            return
        if p.path == "/api/portal/worksheet":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.worksheet_text(Members(), query.get("token", [""])[0])
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/daily_mix":
            self._send_json({"ok": True, **portal.daily_mix()})
            return
        if p.path == "/api/portal/pyq_trends":
            query = urllib.parse.parse_qs(p.query)
            self._send_json({"ok": True, **portal.pyq_trends(query.get("goal", [""])[0])})
            return
        if p.path == "/api/portal/challenge":
            query = urllib.parse.parse_qs(p.query)
            ch = portal.challenge_today(Members(), query.get("token", [""])[0])
            self._send_json({"ok": ch is not None, **(ch or {"error": "session expired"})})
            return
        if p.path == "/api/portal/sprint":
            query = urllib.parse.parse_qs(p.query)
            sp2 = portal.sprint_plan(Members(), query.get("token", [""])[0])
            self._send_json({"ok": sp2 is not None, **(sp2 or {"error": "session expired"})})
            return
        if p.path == "/api/portal/weekly_report":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.weekly_report_text(Members(), query.get("token", [""])[0])
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/mistakes":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.mistake_notebook(Members(), query.get("token", [""])[0])
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/notices":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.notices_for(Members(), query.get("token", [""])[0])
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/goal_hub":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.goal_hub(Members(), query.get("token", [""])[0],
                                       query.get("goal", [""])[0])
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/notes":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.topic_notes(Members(), query.get("token", [""])[0],
                                          query.get("topic", [""])[0])
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/bot_link":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.bot_link_state(Members(), query.get("token", [""])[0])
            if ok:
                info = {**info, "bot": _bot_username()}
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/series/certificate":
            query = urllib.parse.parse_qs(p.query)
            png = portal.series_certificate(Members(), query.get("token", [""])[0])
            if png:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.end_headers()
                self.wfile.write(png)
            else:
                self._send_json({"ok": False, "error": "Series 10 tests complete ayyaka certificate vasthundi"}, code=404)
            return
        if p.path == "/api/portal/study_plan":
            query = urllib.parse.parse_qs(p.query)
            sp = portal.study_plan(Members(), query.get("token", [""])[0])
            self._send_json({"ok": sp is not None, **(sp or {"error": "session expired"})})
            return
        if p.path == "/api/portal/next_topic":
            query = urllib.parse.parse_qs(p.query)
            nt = portal.next_topic(Members(), query.get("token", [""])[0])
            self._send_json({"ok": nt is not None, **(nt or {"error": "session expired"})})
            return
        if p.path == "/api/portal/memory":
            # 🧠 360X: FSRS-Lite memory deck (retention + due cards).
            query = urllib.parse.parse_qs(p.query)
            md = portal.memory_deck(Members(), query.get("token", [""])[0])
            self._send_json({"ok": md is not None, **(md or {"error": "session expired"})})
            return
        if p.path == "/api/portal/trend":
            query = urllib.parse.parse_qs(p.query)
            tr = portal.score_trend(Members(), query.get("token", [""])[0])
            ac = portal.activity_calendar(Members(), query.get("token", [""])[0])
            self._send_json({"ok": True, "trend": tr, "activity": ac})
            return
        if p.path == "/api/portal/forecast":
            query = urllib.parse.parse_qs(p.query)
            fc = portal.score_forecast(Members(), query.get("token", [""])[0])
            self._send_json({"ok": fc is not None, **(fc or {"error": "session expired"})})
            return
        if p.path == "/api/portal/attempt":
            query = urllib.parse.parse_qs(p.query)
            an = portal.attempt_analysis(Members(), query.get("token", [""])[0],
                                         query.get("run_id", [""])[0])
            self._send_json({"ok": an is not None, **(an or {"error": "attempt dorakaledu"})})
            return
        if p.path == "/api/portal/goal_board":
            query = urllib.parse.parse_qs(p.query)
            gb = portal.goal_board(Members(), query.get("goal", ["mixed"])[0])
            self._send_json({"ok": True, "board": gb})
            return
        if p.path == "/api/portal/revision_pack":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.revision_pack_text(Members(), query.get("token", [""])[0])
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/sections":
            query = urllib.parse.parse_qs(p.query)
            ss = portal.section_stock(Members(), query.get("token", [""])[0])
            self._send_json({"ok": ss is not None, **(ss or {"error": "session expired"})})
            return
        if p.path == "/api/portal/patterns":
            query = urllib.parse.parse_qs(p.query)
            pt = portal.mistake_patterns(Members(), query.get("token", [""])[0])
            self._send_json({"ok": pt is not None, **(pt or {"error": "session expired"})})
            return
        if p.path == "/api/portal/retention":
            query = urllib.parse.parse_qs(p.query)
            rt = portal.retention_report(Members(), query.get("token", [""])[0])
            wg = portal.weekly_goal(Members(), query.get("token", [""])[0])
            self._send_json({"ok": rt is not None, "retention": rt, "weekly_goal": wg})
            return
        if p.path == "/api/portal/records":
            query = urllib.parse.parse_qs(p.query)
            rc = portal.my_records(Members(), query.get("token", [""])[0])
            sr = portal.test_series(Members(), query.get("token", [""])[0])
            self._send_json({"ok": rc is not None, "records": rc, "series": sr})
            return
        if p.path == "/api/portal/rival":
            query = urllib.parse.parse_qs(p.query)
            rv = portal.rival_status(Members(), query.get("token", [""])[0])
            self._send_json({"ok": rv is not None, **(rv or {"error": "session expired"})})
            return
        if p.path == "/api/portal/daily_review":
            query = urllib.parse.parse_qs(p.query)
            dr2 = portal.daily_review(Members(), query.get("token", [""])[0])
            self._send_json({"ok": dr2 is not None, **(dr2 or {"error": "session expired"})})
            return
        if p.path == "/api/portal/resume":
            query = urllib.parse.parse_qs(p.query)
            rs = portal.resume_latest(Members(), query.get("token", [""])[0])
            self._send_json({"ok": rs is not None, **(rs or {"error": "session expired"})})
            return
        if p.path == "/api/portal/mydata":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.my_data_export(Members(), query.get("token", [""])[0])
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/district_rank":
            query = urllib.parse.parse_qs(p.query)
            dr = portal.district_goal_rank(Members(), query.get("token", [""])[0])
            self._send_json({"ok": dr is not None, **(dr or {"error": "session expired"})})
            return
        if p.path == "/api/portal/exam":
            query = urllib.parse.parse_qs(p.query)
            ex = portal.exam_questions(Members(), query.get("token", [""])[0],
                                       query.get("id", [""])[0])
            self._send_json({"ok": ex is not None, **(ex or {"error": "session expired"})})
            return
        if p.path == "/api/portal/exam/certificate":
            query = urllib.parse.parse_qs(p.query)
            png = portal.exam_certificate(Members(), query.get("token", [""])[0],
                                          query.get("id", [""])[0])
            if png:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Disposition",
                                 'attachment; filename="studentup-certificate.png"')
                self.send_header("Content-Length", str(len(png)))
                self.end_headers()
                self.wfile.write(png)
            else:
                self._send_json({"ok": False, "error": "Certificate kevalam Top-3 winners ke!"}, code=403)
            return
        if p.path == "/api/portal/exam/scorecard":
            query = urllib.parse.parse_qs(p.query)
            png = portal.exam_scorecard(Members(), query.get("token", [""])[0],
                                         query.get("id", [""])[0])
            if png:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Disposition",
                                 'attachment; filename="studentup-scorecard.png"')
                self.send_header("Content-Length", str(len(png)))
                self.end_headers()
                self.wfile.write(png)
            else:
                self._send_json({"ok": False, "error": "Score card exam ayyaka vastundi!"}, code=403)
            return
        if p.path == "/api/portal/exam/result":
            query = urllib.parse.parse_qs(p.query)
            ex = portal.exam_result(Members(), query.get("token", [""])[0],
                                    query.get("id", [""])[0])
            self._send_json({"ok": ex is not None, **(ex or {"error": "not found"})})
            return
        if p.path == "/api/portal/key":
            query = urllib.parse.parse_qs(p.query)
            ok, info = portal.key_paper(Members(), query.get("token", [""])[0],
                                        query.get("kind", [""])[0],
                                        query.get("ref", [""])[0])
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/quiz":
            query = urllib.parse.parse_qs(p.query)
            qq = portal.daily_questions(Members(), query.get("token", [""])[0])
            if qq is None:
                self._send_json({"ok": False, "error": "session expired"})
            else:
                self._send_json({"ok": True, **qq})
            return
        if p.path in PUBLIC_PAGE_PATHS:
            self._send_html(public_page(self, PUBLIC_PAGE_PATHS[p.path]), etag=True)
            return
        if p.path == "/ads.txt":
            body_txt = ads_txt_content()
            if body_txt:
                self._send_text(body_txt)
            else:
                self._send_text("# AdSense not configured\n", code=404)
            return
        if p.path == "/robots.txt":
            self._send_text(robots_txt(self))
            return
        if p.path == "/sitemap.xml":
            self._send_text(sitemap_xml(self), ctype="application/xml; charset=utf-8")
            return
        if not self._authed():
            self._deny(is_api=p.path.startswith("/api/"))
            return

        if p.path in ("/", "/index.html", "/dashboard"):
            self._send_html(HTML_PAGE)
            return

        if p.path == "/api/history":
            from core import broadcast_log
            self._send_json({
                "ok": True,
                "summary": broadcast_log.get_summary(),
                "history": broadcast_log.get_history(limit=80),
            })
            return

        if p.path == "/api/health":
            # 🩺 MISSION CONTROL: whole-system health in one call
            from core.telegram import Telegram
            from core import broadcast_log
            jobs = whatsapp_pipeline.get_scheduled_jobs()
            enabled_jobs = [j for j in jobs if j.get("enabled")]
            bank = Bank()
            stats = bank.stats()
            # only channels that actually have questions, sorted by fresh stock
            stock = sorted(
                [{"channel": ch, **st} for ch, st in stats.items() if st.get("total", 0) > 0],
                key=lambda r: r["unused"],
            )
            low = [r for r in stock if r["unused"] < 15]
            up_min = int((time.time() - _START_TS) // 60)
            sec = _load_auth()
            self._send_json({
                "ok": True,
                "telegram_live": bool(Telegram().token),
                "whatsapp_connected": whatsapp_pipeline.bridge_is_connected(),
                "scheduler_running": bool(getattr(whatsapp_pipeline, "_SCHEDULER_RUNNING", False)),
                "autopilot_slots": len([j for j in enabled_jobs if j.get("mode") == "tg"]),
                "wa_slots": len([j for j in enabled_jobs if j.get("mode", "wa") != "tg"]),
                "total_fresh": sum(r["unused"] for r in stock),
                "total_questions": sum(r["total"] for r in stock),
                "low_stock": low[:10],
                "stock": stock,
                "ip_lock_on": bool(sec.get("ip_lock_enabled")),
                "uptime_min": up_min,
                "week_polls": broadcast_log.get_summary().get("week_polls", 0),
                "last_backup": __import__("core.backup", fromlist=["backup"]).last_backup_info(),
            })
            return

        if p.path == "/api/questions/search":
            # 🔍 QUESTION FINDER: live search across the whole bank
            qs = urllib.parse.parse_qs(p.query)
            term = (qs.get("q", [""])[0] or "").strip().lower()
            limit = min(int(qs.get("limit", ["30"])[0] or 30), 100)
            bank = Bank()
            results = []
            for q in bank.questions:
                if term:
                    hay = " ".join([
                        str(q.get("q_en", "")), str(q.get("q_te", "")),
                        str(q.get("topic", "")), str(q.get("channel", "")),
                        str(q.get("id", "")),
                    ]).lower()
                    if term not in hay:
                        continue
                ch = q.get("channel", "CURRENT")
                results.append({
                    "id": q.get("id"),
                    "channel": ch,
                    "topic": q.get("topic", ""),
                    "q_en": str(q.get("q_en", ""))[:160],
                    "options": len(q.get("options_en", []) or []),
                    "fresh": q.get("id") not in set(bank.used.get(ch, [])),
                })
                if len(results) >= limit:
                    break
            self._send_json({"ok": True, "count": len(results), "results": results})
            return

        if p.path == "/api/backup":
            # 💾 ONE-CLICK FULL BACKUP: every data json/csv zipped & downloaded
            import io, zipfile
            buf = io.BytesIO()
            added = 0
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(config.DATA.glob("*")):
                    if f.is_file() and f.suffix.lower() in (".json", ".csv", ".xlsx") and f.stat().st_size < 8_000_000:
                        try:
                            z.write(f, f"studentup_backup/{f.name}")
                            added += 1
                        except Exception:
                            pass
            data = buf.getvalue()
            fname = "studentup_backup_" + datetime.now().strftime("%Y%m%d_%H%M") + ".zip"
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if p.path == "/api/security":
            sec = _load_auth()
            self._send_json({
                "ok": True,
                "ip_lock_enabled": bool(sec.get("ip_lock_enabled")),
                "allowed_ips": sec.get("allowed_ips", []),
                "your_ip": self._client_ip(),
                "recent_logins": _recent_logins(8),
            })
            return

        if p.path == "/api/stats":
            mb = Members()
            st_war = districtwar.lobby_status()
            reg = [m for m in mb.members.values() if m.get("registered")]
            tot_pts = sum(m.get("points", 0) for m in mb.members.values())
            wa = whatsapp_pipeline.load_wa_registry()
            all_ch = channel_router.get_all_channels()
            bundles = bundle_manager.load_bundles().get("bundles", [])
            bank = Bank()

            self._send_json({
                "total_members": len(mb.members),
                "registered_members": len(reg),
                "total_points": tot_pts,
                "war_status": st_war,
                "wa_groups_count": len(wa.get("groups", [])),
                "channels_count": len(all_ch),
                "bundles_count": len(bundles),
                "total_questions": len(bank.questions)
            })
            return

        if p.path == "/api/whatsapp/groups":
            self._send_json(whatsapp_pipeline.load_wa_registry())
            return

        if p.path == "/api/whatsapp/retry_queue":
            from core.store import load_json as _load_json
            _rq = _load_json(whatsapp_pipeline.WA_RETRY_FILE, {"items": []})
            _items = _rq.get("items", []) if isinstance(_rq, dict) else []
            self._send_json({"count": len(_items), "items": _items[-20:]})
            return

        if p.path == "/api/whatsapp/bridges":
            self._send_json({"bridges": whatsapp_pipeline.bridges_status(),
                             "pool_size": len(whatsapp_pipeline._bridge_urls())})
            return

        if p.path == "/api/whatsapp/session":
            self._send_json(whatsapp_pipeline.get_session_info())
            return

        if p.path == "/api/whatsapp/schedules":
            self._send_json({"jobs": whatsapp_pipeline.get_scheduled_jobs()})
            return

        if p.path == "/api/whatsapp/hall-of-fame":
            self._send_json({"ok": True,
                             "champions": whatsapp_pipeline.wa_hall_of_fame(20)})
            return

        if p.path == "/api/conductor":
            from core import conductor as _cd
            from core import config as _cfg
            self._send_json({"ok": True, "events": _cd.list_events(),
                             "channels": list(getattr(_cfg, "PUBLIC_CHANNELS", [])),
                             "kinds": _cd.KINDS})
            return

        if p.path == "/api/metrics":
            from core import metrics as _mx
            self._send_json(_mx.snapshot())
            return

        if p.path == "/api/health/full":
            from core import health as _hl
            rep = _hl.full_report()
            rep["uptime_min"] = int((time.time() - _START_TS) // 60)
            try:
                _pa = portal.portal_analytics(Members())
                rep["portal"] = {"students": _pa.get("students"),
                                 "attempts": _pa.get("attempts_total"),
                                 "active_today": _pa.get("active_today")}
            except Exception:
                rep["portal"] = {}
            try:
                rep["golive"] = _golive_checks()
            except Exception:
                rep["golive"] = {}
            self._send_json(rep)
            return

        if p.path == "/api/health/golive":
            self._send_json({"ok": True, **_golive_checks()})
            return
        if p.path == "/api/flags":
            from core import flags as _fl
            self._send_json({"ok": True, "flags": _fl.all_flags()})
            return

        if p.path == "/api/audit":
            from core import auditlog as _al
            self._send_json({"ok": True, "entries": _al.recent(30)})
            return

        if p.path == "/api/pulse":
            from core import pulse as _pl
            self._send_json(_pl.report())
            return

        if p.path == "/api/item_intel":
            from core import item_intel as _ii
            self._send_json({"ok": True, **_ii.report()})
            return

        if p.path == "/api/brain/overview":
            from core import brain as _br
            self._send_json({"ok": True, **_br.overview()})
            return

        if p.path == "/api/portal/exam/integrity":
            from core import integrity as _ig
            _iq = urllib.parse.parse_qs(p.query)
            self._send_json({"ok": True, **_ig.report_for_exam(
                (_iq.get("id") or [""])[0])})
            return

        if p.path == "/api/syllabus":
            query = urllib.parse.parse_qs(p.query)
            uid = (query.get("uid", [""])[0] or "").strip()
            if not uid:
                self._send_json({"ok": False, "error": "uid kavali (?uid=<telegram id>)"})
                return
            from core import syllabus as _syllabus
            mb = Members()
            mem = mb.members.get(str(uid), {})
            from core.question_bank import Bank as _Bank
            ch = (mem.get("follow") or ["CURRENT"])[0] if mem.get("follow") else "CURRENT"
            self._send_json({"ok": True, "uid": uid,
                             "plan": _syllabus.plan(mem, _Bank(), ch)})
            return

        if p.path == "/api/vision":
            from core import vision as _vision
            self._send_json(_vision.vision_report())
            return

        if p.path == "/api/setup/options":
            # 🎛️ Manual Setup form data: exams mariyu subjects rendu
            # live registry nunche (hardcode kaadu).
            exams = set()
            for _k, _v in channel_router.get_all_channels().items():
                if _v.get("base_exam"):
                    exams.add(str(_v["base_exam"]).upper())
                exams.add(str(_k).upper())
            try:
                for _g in whatsapp_pipeline.load_wa_registry().get("groups", []):
                    if _g.get("category"):
                        exams.add(str(_g["category"]).upper())
            except Exception:
                pass
            self._send_json({
                "exams": sorted(exams),
                "subjects": sorted(whatsapp_pipeline.SUBJECT_TOPIC_MAP.keys()),
                "shifts": ["ALL_DAY", "MORNING", "EVENING"],
                "group_types": ["EXAM_SPECIFIC", "GENERAL"],
            })
            return

        if p.path == "/api/whatsapp/pipeline_status":
            self._send_json(whatsapp_pipeline.get_broadcast_status())
            return

        if p.path == "/api/channels":
            bank = Bank()
            counts = {}
            for q in bank.questions:
                c = q.get("channel", "UNKNOWN")
                counts[c] = counts.get(c, 0) + 1

            self._send_json({
                "channels": channel_router.get_all_channels(),
                "question_counts": counts
            })
            return

        if p.path == "/api/whatsapp/group_health":
            self._send_json({"ok": True, "health": whatsapp_pipeline.group_health()})
            return

        if p.path == "/api/whatsapp/preview":
            query = urllib.parse.parse_qs(p.query)
            try:
                cnt = max(1, min(int(query.get("count", ["2"])[0]), 5))
            except Exception:
                cnt = 2
            self._send_json(whatsapp_pipeline.preview_broadcast(
                target_category=query.get("category", ["ALL"])[0], questions_per_group=cnt))
            return

        if p.path == "/api/whatsapp/safety":
            self._send_json({"ok": True, **whatsapp_pipeline.safety_stack()})
            return

        if p.path == "/api/whatsapp/preflight":
            reg = whatsapp_pipeline.load_wa_registry()
            grps = [g for g in reg.get("groups", []) if g.get("active")]
            pf = whatsapp_pipeline.preflight_whatsapp(groups=grps, category="ALL", questions_per_group=5)
            self._send_json({"ok": pf["ok"], "preflight": pf})
            return

        if p.path == "/api/wp/status":
            try:
                req = urllib.request.Request(_wp_base() + "/wp-json/",
                                             headers={"User-Agent": "StudentUp-Bridge/1.0"})
                with urllib.request.urlopen(req, timeout=6) as r:
                    info = json.loads(r.read().decode("utf-8", "ignore"))
                self._send_json({"ok": True, "name": info.get("name", ""),
                                 "url": info.get("url", _wp_base()),
                                 "posts_cached": len(_WP_CACHE["posts"])})
            except Exception as ex:
                self._send_json({"ok": False, "error": f"WP reach avvaledu: {ex}",
                                 "base": _wp_base()})
            return

        if p.path == "/api/wp/export":
            self._send_json({"ok": True, **_wp_quiz_export()})
            return

        if p.path == "/api/publish/today":
            # 🚦 310X: today's approve-to-live draft manifest.
            from core import publish_queue, wp_push
            self._send_json({"ok": True,
                             "draft": publish_queue.get_or_build_today(),
                             "wp_creds": wp_push.creds_ready(),
                             "wp_url": wp_push.push_url()})
            return

        if p.path == "/api/papers/drafts":
            from core import paperfactory
            self._send_json({"ok": True,
                             "drafts": paperfactory.list_drafts()})
            return

        if p.path == "/api/pyq/status":
            import collections as _c
            try:
                _bank = json.loads(config.BANK_JSON.read_text(encoding="utf-8"))
                _src = _c.Counter(q.get("source") or "" for q in _bank.get("questions", []))
            except Exception:
                _src = {}
            self._send_json({"ok": True, "text": pyq.status_text(),
                             "by_channel": pyq.by_channel(),
                             "running": _PYQ_JOB["running"], "last": _PYQ_JOB["last"],
                             "bank": {"total": sum(_src.values()),
                                      "pyq": _src.get("pyq", 0), "curated": _src.get("curated", 0),
                                      "scraped": _src.get("scraped", 0),
                                      "generated": _src.get("offline-gen", 0) + _src.get("llm-gen", 0)}})
            return

        if p.path == "/api/portal/admin/reports/status":
            self._send_json({"ok": True, **_REPORT_JOB})
            return

        if p.path == "/api/portal/admin/notices":
            self._send_json({"ok": True, "notices": portal.list_notices(10)})
            return

        if p.path == "/api/portal/admin/analytics":
            self._send_json({"ok": True, **portal.portal_analytics(Members())})
            return
        if p.path == "/api/portal/admin/students":
            query = urllib.parse.parse_qs(p.query)
            self._send_json({"ok": True, "students": portal.admin_students(
                Members(), query.get("q", [""])[0])})
            return
        if p.path == "/api/portal/admin/flags":
            self._send_json({"ok": True, "flags": portal.question_flags()})
            return
        if p.path == "/api/bank/quality":
            from core.question_bank import bank_quality
            self._send_json({"ok": True, **bank_quality()})
            return
        if p.path == "/api/portal/admin/exams":
            self._send_json({"ok": True, "exams": portal.admin_list(),
                             "goals": {k: v["label"] for k, v in portal.GOALS.items()}})
            return

        if p.path == "/api/campus/list":
            d = campus._load()
            events = []
            for c, e in d.get("events", {}).items():
                events.append({
                    "code": c,
                    "name": e.get("name", ""),
                    "district": e.get("district", ""),
                    "colleges": e.get("colleges", []),
                    "n_q": e.get("n_q", 10),
                    "level": e.get("level", "easy"),
                    "state": e.get("state", "open"),
                    "players_count": len(e.get("players", {}))
                })
            self._send_json({
                "bot": _bot_username(),
                "events": events
            })
            return

        if p.path == "/api/campus/report":
            query = urllib.parse.parse_qs(p.query)
            code = query.get("code", [""])[0]
            rep = campus.report_dict(code)
            if rep is None:
                self._send_json({"ok": False, "error": "Event not found", "report": None})
            else:
                self._send_json({"ok": True, "report": rep})
            return

        if p.path == "/api/campus/poster":
            query = urllib.parse.parse_qs(p.query)
            code = query.get("code", [""])[0]
            data = campus.poster_png(code)
            if not data:
                self._send_json({"ok": False, "error": "Poster unavailable (no finishers yet or Pillow missing)."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Disposition", f'attachment; filename="campus-{code}-poster.png"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if p.path == "/api/campus/qr":
            query = urllib.parse.parse_qs(p.query)
            code = query.get("code", [""])[0]
            if query.get("web", [""])[0] == "1":
                data = campus.qr_png(code, _bot_username(),
                                     link=f"{_public_base(self)}/exam/{code}")
            else:
                data = campus.qr_png(code, _bot_username())
            if not data:
                self._send_json({"ok": False, "error": "QR unavailable (qrcode package missing or event not found). Use the join link instead."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            if query.get("dl", [""])[0] == "1":
                self.send_header("Content-Disposition", f'attachment; filename="campus-{code}-qr.png"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if p.path == "/api/campus/excel":
            query = urllib.parse.parse_qs(p.query)
            code = query.get("code", [""])[0]
            fname, data = campus.export_excel_bytes(code)
            if not data:
                self._send_json({"ok": False, "error": "No marks data for this event yet."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.ms-excel")
            self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if p.path == "/api/campus/live":
            query = urllib.parse.parse_qs(p.query)
            snap = campus.live_snapshot(query.get("code", [""])[0])
            if snap is None:
                self._send_json({"ok": False, "error": "Event not found"})
            else:
                self._send_json({"ok": True, "live": snap})
            return

        if p.path == "/api/campus/league":
            self._send_json({"ok": True, "league": campus.league_table()})
            return

        if p.path == "/api/planner/today":
            self._send_json({"ok": True, **planner.today_plan()})
            return

        if p.path == "/api/bundles":
            self._send_json(bundle_manager.load_bundles())
            return

        if p.path == "/api/squads":
            sq_data = hooks._sq()
            self._send_json({
                "bot": config.BOT_USERNAME or "StudentUpBot",
                "squads": sq_data.get("squads", {})
            })
            return

        if p.path == "/api/excel/template_xlsx":
            # 📥 BEST sample workbook: Instructions + 3 sheets + auto-schedule columns
            data = bundle_manager.build_groups_template_xlsx()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="studentup_groups_template.xlsx"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if p.path == "/api/excel/template":
            tmpl_path = config.DATA / "sample_whatsapp_groups_template.csv"
            if not tmpl_path.exists():
                sample_data = (
                    "Group Name,Link or JID,Category,Shift,Group Type\n"
                    "Warangal TS Police SI & Constable Batch,https://chat.whatsapp.com/sample_police_warangal,POLICE,MORNING,EXAM_SPECIFIC\n"
                    "Guntur AP DSC SGT Aspirants 2026,https://chat.whatsapp.com/sample_dsc_guntur,TET_DSC,ALL_DAY,EXAM_SPECIFIC\n"
                    "Telangana Group 1 2 3 State Service Hub,https://chat.whatsapp.com/sample_tspsc_state,TSPSC,ALL_DAY,EXAM_SPECIFIC\n"
                    "Andhra Pradesh APPSC Group 2 & 4 Warriors,https://chat.whatsapp.com/sample_appsc_state,APPSC,ALL_DAY,EXAM_SPECIFIC\n"
                    "TS 10th Class SSC Board 2026 Toppers,https://chat.whatsapp.com/sample_ts_10th,TS_10TH,ALL_DAY,EXAM_SPECIFIC\n"
                    "AP 10th Class BSEAP Board Exam Prep,https://chat.whatsapp.com/sample_ap_10th,AP_10TH,ALL_DAY,EXAM_SPECIFIC\n"
                    "TS Intermediate MPC & BiPC Study Circle,https://chat.whatsapp.com/sample_ts_inter,TS_INTER,MORNING,EXAM_SPECIFIC\n"
                    "AP Intermediate BIEAP & EAPCET Network,https://chat.whatsapp.com/sample_ap_inter,AP_INTER,MORNING,EXAM_SPECIFIC\n"
                    "TS Diploma SBTET & POLYCET Circle,https://chat.whatsapp.com/sample_ts_diploma,TS_DIPLOMA,ALL_DAY,EXAM_SPECIFIC\n"
                    "AP Diploma SBTET Polytechnic & ECET Hub,https://chat.whatsapp.com/sample_ap_diploma,AP_DIPLOMA,ALL_DAY,EXAM_SPECIFIC\n"
                    "TS Degree Colleges (B.Com/B.Sc/B.A) Forum,https://chat.whatsapp.com/sample_ts_degree,TS_DEGREE,EVENING,EXAM_SPECIFIC\n"
                    "AP Degree Colleges AU & SVU Students Union,https://chat.whatsapp.com/sample_ap_degree,AP_DEGREE,EVENING,EXAM_SPECIFIC\n"
                    "TS B.Tech Engineering & Placement Hub,https://chat.whatsapp.com/sample_ts_btech,TS_BTECH,EVENING,EXAM_SPECIFIC\n"
                    "AP B.Tech JNTUK & JNTUA Placements,https://chat.whatsapp.com/sample_ap_btech,AP_BTECH,EVENING,EXAM_SPECIFIC\n"
                    "TS & AP ITI Electrician & Fitter Forum,https://chat.whatsapp.com/sample_iti_students,ITI_ALL,ALL_DAY,EXAM_SPECIFIC\n"
                    "Dr BR Ambedkar Open University BRAOU Network,https://chat.whatsapp.com/sample_braou_univ,OPEN_UNIV,ALL_DAY,EXAM_SPECIFIC\n"
                    "SSC CGL / CHSL / MTS Central Exam Prep,https://chat.whatsapp.com/sample_ssc_central,SSC,MORNING,EXAM_SPECIFIC\n"
                    "Railway RRB NTPC & Group D Warriors,https://chat.whatsapp.com/sample_rrb_railway,RAILWAY,MORNING,EXAM_SPECIFIC\n"
                    "State Bank SBI PO & IBPS Clerk Circle,https://chat.whatsapp.com/sample_banking_sbi,BANKING,MORNING,EXAM_SPECIFIC\n"
                    "Telangana & AP General Study Circle,https://chat.whatsapp.com/sample_general_circle,CURRENT,ALL_DAY,GENERAL\n"
                )
                tmpl_path.write_text(sample_data, encoding="utf-8")
            
            content = tmpl_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="studentup_sample_whatsapp_groups.csv"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if p.path == "/api/member_queue/status":
            self._send_json(member_queue.snapshot())
            return

        if p.path == "/api/members":
            mb = Members()
            arr = []
            for uid, m in sorted(mb.members.items(), key=lambda kv: -kv[1].get("points", 0)):
                arr.append({
                    "uid": uid,
                    "name": m.get("name") or "Player",
                    "district": m.get("district", ""),
                    "exam": m.get("exam", ""),
                    "points": m.get("points", 0),
                    "streak": m.get("streak", 0),
                    "college": m.get("college", ""),
                    "accuracy": (round(100 * m.get("correct", 0) / m["total"]) if m.get("total") else 0),
                    "weak_topic": (mb.weak_topics(uid) or [""])[0]
                })
            self._send_json({"members": arr})
            return

        # unknown route -> JSON 404 (browser ki empty page padakudadhu)
        if p.path.startswith("/api/"):
            self._send_json({"ok": False,
                             "error": f"unknown endpoint: {p.path}"}, code=404)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        try:
            self._do_POST()
        except Exception as e:
            print(f"   [dashboard] POST {self.path} error: {e}")
            try:
                self._send_json({"ok": False,
                                 "error": f"server error: {e}"}, code=500)
            except Exception:
                pass

    def _do_POST(self):
        p = urllib.parse.urlparse(self.path)

        # 🛡️ IP allowlist — checked BEFORE everything (even login attempts)
        if not self._ip_allowed():
            self._deny_ip(is_api=True)
            return

        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except Exception:
            length = 0
        if length > 5_000_000:      # 🛡️ 240X: payload cap (DoS hygiene)
            self._send_json({"ok": False, "error": "payload too large"}, code=413)
            return
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        # 🔒 Access lock
        if p.path == "/api/auth/login":
            pw = str(body.get("password", ""))
            if pw and hmac.compare_digest(pw, _dash_password()):
                _log_login_attempt(self._client_ip(), True)
                self._issue_login_cookie()
            else:
                _log_login_attempt(self._client_ip(), False)
                time.sleep(1.2)  # slow brute-force attempts
                self._send_json({"ok": False, "error": "wrong password"}, code=401)
            return
        # 🌐 Student Web Exam APIs — login akkarledu
        # 🎓 Student Portal APIs — login akkarledu
        if p.path == "/api/portal/exam/join":
            ok, info = portal.exam_join(Members(), body.get("token", ""), body.get("exam_id", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/exam/answer":
            try:
                ok, info = portal.exam_answer(
                    Members(), body.get("token", ""), body.get("exam_id", ""),
                    int(body.get("idx") or 0),
                    int(body.get("choice") if body.get("choice") is not None else -1))
            except Exception as ex:
                ok, info = False, str(ex)
            self._send_json({"ok": ok, **(info if ok and isinstance(info, dict) else {"error": info})})
            return
        if p.path == "/api/portal/paper/start":
            ok, info = portal.paper_start(Members(), body.get("token", ""),
                                          body.get("exam", ""),
                                          body.get("year", ""),
                                          body.get("paper", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/paper/catalog":
            self._send_json({"ok": True, "papers": portal.paper_catalog()})
            return
        if p.path == "/api/portal/practice/start":
            ok, info = portal.practice_start(Members(), body.get("token", ""),
                                             body.get("mode", "smart"),
                                             body.get("topic", ""),
                                             body.get("goal", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/practice/answer":
            try:
                ok, info = portal.practice_answer(
                    Members(), body.get("token", ""), body.get("run_id", ""),
                    int(body.get("idx") or 0),
                    int(body.get("choice") if body.get("choice") is not None else -1))
            except Exception as ex:
                ok, info = False, str(ex)
            self._send_json({"ok": ok, **(info if ok and isinstance(info, dict) else {"error": info})})
            return
        if p.path == "/api/portal/challenge/answer":
            try:
                ok, info = portal.challenge_answer(
                    Members(), body.get("token", ""),
                    int(body.get("choice") if body.get("choice") is not None else -1))
            except Exception as ex:
                ok, info = False, str(ex)
            self._send_json({"ok": ok, **(info if ok and isinstance(info, dict) else {"error": info})})
            return
        if p.path == "/api/portal/search":
            ok, info = portal.search_practice(Members(), body.get("token", ""),
                                              body.get("q", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/flag":
            ok, info = portal.flag_question(Members(), body.get("token", ""),
                                            body.get("qid", ""), body.get("reason", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/goal2":
            ok, info = portal.set_goal2(Members(), body.get("token", ""),
                                        body.get("goal", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/focus":
            ok, info = portal.log_study(Members(), body.get("token", ""),
                                        body.get("minutes", 0))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/exam/remind":
            ok, info = portal.set_exam_reminder(
                Members(), body.get("token", ""), body.get("exam_id", ""),
                bool(body.get("on", True)))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/tg_link":
            ok, info = portal.tg_link_code(Members(), body.get("token", ""))
            if ok:
                info = {**info, "bot": _bot_username()}
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/tg_auth":
            ok, info = portal.tg_auth(Members(), body.get("init_data", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/lang":
            ok, info = portal.set_lang(Members(), body.get("token", ""),
                                       body.get("lang", "both"))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/rival/set":
            ok, info = portal.set_rival(Members(), body.get("token", ""),
                                        body.get("ref", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/goal":
            ok, info = portal.set_goal(Members(), body.get("token", ""),
                                       body.get("goal", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/register":
            if not self._rate_ok("reg:" + self._client_ip(), 12, 600):
                self._send_json({"ok": False, "error": "Chala sarlu try chesaru — koncham aagi malli try cheyyandi."}, code=429)
                return
            ok, info = portal.register_student(
                Members(), body.get("name", ""), body.get("phone", ""),
                body.get("district", ""), body.get("goal", "mixed"),
                body.get("ref", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/answer":
            try:
                ok, info = portal.daily_answer(
                    Members(), body.get("token", ""),
                    int(body.get("idx") or 0),
                    int(body.get("choice") if body.get("choice") is not None else -1),
                    body.get("sec"))
            except Exception as ex:
                ok, info = False, str(ex)
            self._send_json({"ok": ok, **(info if ok and isinstance(info, dict) else {"error": info})})
            return
        if p.path == "/api/portal/mock/start":
            ok, info = portal.mock_start(Members(), body.get("token", ""), body.get("goal", "mixed"),
                                         neg=float(body.get("neg") or 0),
                                         kind=str(body.get("kind") or "mock"))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/materials_unlock":
            uok, umsg = portal.materials_unlock(Members(), str(body.get("token") or ""), str(body.get("id") or ""))
            self._send_json({"ok": uok, "message": umsg})
            return
        if p.path == "/api/admin/harvest_run":
            if not self._authed():
                self._send_json({"ok": False, "error": "admin login kavali"}, code=401)
                return
            # 🚜 230X: run top bank-gap harvest target. Production =
            # real PYQ harvest; SANDBOX/CI env forces dry (no downloads).
            _dry = bool(os.environ.get("STUDYUP_SANDBOX") or os.environ.get("CI"))
            res = portal.run_harvest_job(dry=_dry, limit_jobs=1)
            _t = (res or [{}])[0]
            self._send_json({"ok": True, "dry": _dry, "job": _t,
                             "message": ("🚜 Harvest target: " + str(_t.get("channel", "?")) +
                                         " · " + str(_t.get("subject", "")) +
                                         (" (DRY — sandbox)" if _dry else " — production run started"))})
            return
        if p.path == "/api/admin/materials_add":
            if not self._authed():
                self._send_json({"ok": False, "error": "admin login kavali"}, code=401)
                return
            item = portal.materials_add(Members(), str(body.get("title") or ""),
                                        str(body.get("file") or ""),
                                        str(body.get("goal") or "all"),
                                        str(body.get("topic") or ""),
                                        str(body.get("subject") or ""),
                                        int(body.get("cost") or 0))
            self._send_json({"ok": True, "item": item})
            return
        if p.path == "/api/portal/bookmark":
            ok, info = portal.bookmark_toggle(Members(), body.get("token", ""),
                                              body.get("qid", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/mock/submit":
            ok, info = portal.mock_submit(Members(), body.get("token", ""),
                                          body.get("run_id", ""), body.get("answers") or {},
                                          body.get("times") or {})
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/exam/join":
            ok, info = campus.web_join(
                Members(), (body.get("code") or "").strip(),
                body.get("name", ""), body.get("phone", ""), body.get("college_idx", 1))
            if ok:
                self._send_json({"ok": True, **info})
            else:
                self._send_json({"ok": False, "error": info})
            return
        if p.path == "/api/exam/answer":
            try:
                ok, info = campus.web_answer(
                    (body.get("code") or "").strip(), body.get("token", ""),
                    int(body.get("position") or 0),
                    int(body.get("choice") if body.get("choice") is not None else -1))
            except Exception as ex:
                ok, info = False, str(ex)
            if ok:
                self._send_json({"ok": True, **info})
            else:
                self._send_json({"ok": False, "error": info})
            return
        if p.path == "/api/portal/st270/register":
            if not self._rate_ok("sl270-reg:" + self._client_ip(), 12, 600):
                self._send_json({"ok": False, "error": "Chala sarlu try chesaru — koncham aagi malli try cheyyandi."}, code=429)
                return
            try:
                from core import stateless_client as _sl270
                _tok270, _err270 = _sl270.register_student(
                    body.get("name", ""), body.get("phone", ""),
                    body.get("district", ""), body.get("goal", "mixed"))
            except Exception as _ex270:
                _tok270, _err270 = None, str(_ex270)
            self._send_json({"ok": bool(_tok270), "stateless": True,
                             "token": _tok270, "stoken": _tok270,
                             **({"error": _err270} if _err270 else {})})
            return
        if p.path == "/api/portal/st270/answer":
            try:
                from core import stateless_client as _sl270
                _nt270, _res270 = _sl270.record_answer(
                    body.get("stoken") or body.get("token", ""),
                    body.get("qid", ""),
                    body.get("choice", -1),
                    idx=int(body.get("idx") or body.get("i") or 0)
                    )
            except Exception as _ex270:
                _nt270, _res270 = None, {"ok": False, "error": str(_ex270)}
            self._send_json({**(_res270 or {}), "stateless": True,
                             "token": _nt270, "stoken": _nt270})
            return
        if p.path == "/api/portal/st270/claims":
            # 🧾 270X: verify a server-signed claim (verify-only; claims
            # are ISSUED server-side after contests — never from here).
            try:
                from core import stateless_client as _sl270
                _v270 = _sl270.verify_claim(
                    str(body.get("claim") or ""),
                    want_kind=(str(body.get("kind") or "") or None))
            except Exception:
                _v270 = None
            self._send_json({"ok": _v270 is not None, "stateless": True,
                             "claim": _v270})
            return
        if p.path == "/api/portal/st270/attempt/start":
            try:
                from core import stateless_client as _sl270
                _at270, _info270 = _sl270.start_attempt(
                    body.get("stoken") or body.get("token", ""))
            except Exception as _ex270:
                _at270, _info270 = None, str(_ex270)
            if not _at270:
                self._send_json({"ok": False,
                                 "error": _info270 or "invalid token"},
                                code=401)
                return
            self._send_json({"ok": True, "stateless": True,
                             "attempt_token": _at270, "atoken": _at270,
                             **(_info270 or {})})
            return
        if p.path == "/api/portal/st270/attempt/submit":
            try:
                from core import stateless_client as _sl270
                _nt270, _res270 = _sl270.submit_attempt(
                    body.get("stoken") or body.get("token", ""),
                    body.get("atoken") or body.get("attempt_token", ""),
                    body.get("answers") or {})
            except Exception as _ex270:
                _nt270, _res270 = None, {"ok": False,
                                         "error": str(_ex270)}
            self._send_json({**(_res270 or {}), "stateless": True,
                             "token": _nt270, "stoken": _nt270})
            return
        if not self._authed():
            self._send_json({"ok": False, "error": "unauthorized — login required"}, code=401)
            return

        if p.path == "/api/auth/logout":
            auth = _load_auth()
            tok = self._cookie_token()
            auth["tokens"] = [t for t in auth.get("tokens", []) if t != tok]
            _save_auth(auth)
            self._send_json({"ok": True, "message": "logged out"})
            return

        if p.path == "/api/auth/change_password":
            old = str(body.get("old", ""))
            new = str(body.get("new", "")).strip()
            if old != _dash_password():
                self._send_json({"ok": False, "error": "current password is wrong"})
                return
            if len(new) < 6:
                self._send_json({"ok": False, "error": "new password must be at least 6 characters"})
                return
            auth = _load_auth()
            auth["password"] = new
            auth["tokens"] = [self._cookie_token()]  # kick every other session
            _save_auth(auth)
            self._send_json({"ok": True, "message": "password changed — other sessions logged out"})
            return

        if p.path == "/api/security/update":
            enabled = bool(body.get("ip_lock_enabled"))
            raw_ips = body.get("allowed_ips", [])
            if isinstance(raw_ips, str):
                raw_ips = raw_ips.replace(",", " ").split()
            ips, bad = [], []
            import ipaddress
            for e in raw_ips:
                e = str(e).strip()
                if not e:
                    continue
                valid = False
                try:
                    ipaddress.ip_address(e)
                    valid = True
                except ValueError:
                    if "/" in e:
                        try:
                            ipaddress.ip_network(e, strict=False)
                            valid = True
                        except ValueError:
                            pass
                    elif e.endswith(".") or e.endswith(":"):
                        valid = True  # prefix rule like "49.37."
                if valid:
                    if e not in ips:
                        ips.append(e)
                else:
                    bad.append(e)
            if bad:
                self._send_json({"ok": False, "error": "Invalid entries: " + ", ".join(bad) + " — valid formats: 49.37.12.34 | 49.37. | 49.37.0.0/16"})
                return

            note = ""
            my_ip = self._client_ip()
            if enabled and ips:
                # 🚨 LOCKOUT GUARD: never let the admin lock THEMSELVES out.
                xff = (self.headers.get("X-Forwarded-For", "") or "").strip()
                is_local = (not xff) and self.client_address[0] in ("127.0.0.1", "::1")
                if not is_local:
                    try:
                        ipobj = ipaddress.ip_address(my_ip)
                    except ValueError:
                        ipobj = None
                    matched = any(
                        e == my_ip
                        or ((e.endswith(".") or e.endswith(":")) and my_ip.startswith(e))
                        or ("/" in e and ipobj is not None and ipobj in ipaddress.ip_network(e, strict=False))
                        for e in ips
                    )
                    if not matched:
                        ips.append(my_ip)
                        note = f"మీ current IP {my_ip} list లో లేదు — lockout కాకుండా auto-add చేశాం."
            if enabled and not ips:
                enabled = False
                note = "Allowlist ఖాళీగా ఉంది — lock OFF చేశాం (ఖాళీ list తో అందరూ block అవుతారు)."

            auth = _load_auth()
            auth["ip_lock_enabled"] = enabled
            auth["allowed_ips"] = ips
            _save_auth(auth)
            self._send_json({"ok": True, "ip_lock_enabled": enabled, "allowed_ips": ips,
                             "your_ip": my_ip, "note": note,
                             "message": ("🛡️ IP Lock ON — only " + str(len(ips)) + " allowed IP rule(s)") if enabled else "🔓 IP Lock OFF — password-only protection"})
            return

        if p.path == "/api/member_queue/settings":
            self._send_json(member_queue.update_settings(body))
            return

        if p.path == "/api/member_queue/import":
            text = body.get("text", "")
            if not text.strip():
                self._send_json({"ok": False, "error": "CSV content is required"})
                return
            self._send_json(member_queue.import_csv(text, body.get("group_id", ""), body.get("default_consent", "PENDING")))
            return

        if p.path == "/api/members/register":
            uid = str(body.get("uid", "")).strip()
            name = body.get("name", "").strip()
            district = body.get("district", "Warangal").strip()
            exam = body.get("exam", "POLICE").strip()
            pts = int(body.get("points", 50))
            
            mb = Members()
            m = mb.register(uid, name=name, exam=exam, district=district)
            m["points"] = m.get("points", 0) + pts
            mb.kv.save()
            self._send_json({"ok": True, "uid": uid, "points": m["points"]})
            return

        if p.path == "/api/members/add_points":
            uid = str(body.get("uid", "")).strip()
            pts = int(body.get("points", 10))
            mb = Members()
            if uid in mb.members:
                mb.members[uid]["points"] = mb.members[uid].get("points", 0) + pts
                mb.kv.save()
                self._send_json({"ok": True, "uid": uid, "points": mb.members[uid]["points"]})
            else:
                self._send_json({"ok": False, "message": "User not found"})
            return

        if p.path == "/api/whatsapp/group_health_reset":
            ok = whatsapp_pipeline.group_health_reset((body.get("jid") or "").strip())
            self._send_json({"ok": ok, "message": "Group health reset — next broadcast nunchi malli try chesthundi" if ok else "group not found"})
            return

        if p.path == "/api/planner/apply":
            created = planner.apply_plan(body.get("items") or [])
            self._send_json({"ok": True, "created": len(created),
                             "message": f"✨ {len(created)} daily jobs create ayyayi — Smart Plan active!"})
            return

        if p.path == "/api/campus/retest":
            old = (body.get("code") or "").strip()
            new_code = campus.retest_event(old)
            if not new_code:
                self._send_json({"ok": False, "message": "event not found"})
            else:
                bot = _bot_username()
                self._send_json({"ok": True, "code": new_code, "retest_of": old,
                                 "link": campus.deep_link(new_code, bot),
                                 "qr": f"/api/campus/qr?code={new_code}"})
            return

        if p.path == "/api/campus/control":
            code = (body.get("code") or "").strip()
            action = (body.get("action") or "").strip()
            if action == "next":
                ok, msg = campus.advance_now(Telegram(), Members(), code)
            elif action == "finish":
                ok, msg = campus.finish_now(Telegram(), Members(), code)
            else:
                ok, msg = False, "unknown action"
            self._send_json({"ok": ok, "code": code, "message": msg})
            return

        if p.path == "/api/campus/start":
            code = (body.get("code") or "").strip()
            ok, info = campus.start(Bank(), Members(), Telegram(), code)
            if ok:
                self._send_json({"ok": True, "code": code, "info": info})
            else:
                self._send_json({"ok": False, "code": code, "message": str(info)})
            return

        if p.path == "/api/pyq/harvest":
            dry = bool(body.get("dry"))
            if _PYQ_JOB["running"]:
                self._send_json({"ok": False, "error": "Harvest already running undi — wait cheyyandi."})
                return

            def _run_pyq():
                _PYQ_JOB["running"] = True
                try:
                    st = pyq.harvest(dry=dry, limit=body.get("limit") or None)
                    _PYQ_JOB["last"] = str(st)
                except Exception as ex:
                    _PYQ_JOB["last"] = f"error: {ex}"
                _PYQ_JOB["running"] = False

            _threading.Thread(target=_run_pyq, daemon=True).start()
            self._send_json({"ok": True, "started": True, "dry": dry})
            return

        if p.path == "/api/papers/make":
            from core import paperfactory
            from core import config as _cfg
            raw = str(body.get("path", "")).strip()
            pth = Path(raw) if raw else None
            if pth is not None and not pth.is_absolute():
                pth = _cfg.ROOT / raw
            res = (paperfactory.make_draft(pth,
                                            str(body.get("title", "")))
                   if pth is not None else
                   {"ok": False, "error": "path ivvandi"})
            self._send_json(res)
            return

        if p.path == "/api/papers/translate":
            from core import paperfactory
            self._send_json(paperfactory.translate_draft(
                body.get("draft_id", "")))
            return

        if p.path == "/api/papers/approve":
            from core import paperfactory
            self._send_json(paperfactory.go_bank(body.get("draft_id", "")))
            return

        if p.path == "/api/papers/reject":
            from core import paperfactory
            self._send_json(paperfactory.reject_draft(
                body.get("draft_id", "")))
            return

        if p.path == "/api/pyq/add_paper":
            try:
                e = pyq.add_paper(body.get("channel", ""), body.get("exam", ""),
                                  int(body.get("year") or 0), body.get("paper", ""),
                                  body.get("url", ""))
                self._send_json({"ok": True, "entry": e})
            except Exception as ex:
                self._send_json({"ok": False, "error": str(ex)})
            return

        if p.path == "/api/pyq/import":
            res = pyq.import_csv(body.get("csv", ""), rebuild=True)
            self._send_json({"ok": res.get("added", 0) >= 0, **res})
            return

        if p.path == "/api/portal/admin/bot_broadcast":
            ok, info = portal.admin_bot_broadcast(
                Members(), body.get("text", ""), body.get("goal", ""))
            self._send_json({"ok": ok, **(info if ok else {"error": info})})
            return
        if p.path == "/api/portal/admin/announce":
            txt = portal.winners_text(body.get("exam_id", ""))
            if not txt:
                self._send_json({"ok": False, "error": "Winners inka leru (exam done avvagane vastundi)."})
                return
            sent = False
            if config.BOT_TOKEN and config.ADMIN_ID:
                try:
                    Telegram().send_message(str(config.ADMIN_ID), txt)
                    sent = True
                except Exception:
                    sent = False
            self._send_json({"ok": True, "text": txt, "sent_to_admin": sent})
            return

        # 🚦 310X: Approve-to-Live publish pipeline. Nothing reaches
        # students/WordPress until the owner approves today's draft.
        if p.path == "/api/publish/approve":
            from core import publish_queue
            draft = publish_queue.get_or_build_today()
            ok, msg = publish_queue.approve(draft["id"],
                                            str(body.get("by") or "owner"))
            self._send_json({"ok": ok, "message": msg,
                             "draft": publish_queue.get(draft["id"])})
            return
        if p.path == "/api/publish/reject":
            from core import publish_queue
            draft = publish_queue.get_or_build_today()
            ok, msg = publish_queue.reject(draft["id"],
                                           str(body.get("by") or "owner"),
                                           str(body.get("reason") or ""))
            self._send_json({"ok": ok, "message": msg})
            return
        if p.path == "/api/publish/push_wp":
            from core import publish_queue, wp_push
            draft = publish_queue.get_or_build_today()
            if draft.get("status") not in ("approved", "live"):
                self._send_json({"ok": False,
                                 "error": "Mundu draft Approve cheyyandi — "
                                          "approve lekunda WP push avvadu."})
                return
            res = wp_push.push_quiz(_wp_quiz_export())
            publish_queue.mark_wp_pushed(draft["id"], bool(res.get("ok")),
                                         res.get("stored", 0),
                                         res.get("error", ""))
            self._send_json({"ok": bool(res.get("ok")), **res,
                             "draft": publish_queue.get(draft["id"])})
            return
        if p.path == "/api/publish/go_live":
            from core import publish_queue
            draft = publish_queue.get_or_build_today()
            ok, msg = publish_queue.go_live(draft["id"],
                                            str(body.get("by") or "owner"))
            out = {"ok": ok, "message": msg,
                   "draft": publish_queue.get(draft["id"])}
            if ok:
                # 🚀 320X: go-live announcement — Telegram admin ki
                # auto-send + dashboard copy-to-WhatsApp text.
                ann = publish_queue.announcement_text(
                    out["draft"], _public_base(self) + "/portal")
                sent = False
                if config.BOT_TOKEN and config.ADMIN_ID:
                    try:
                        Telegram().send_message(str(config.ADMIN_ID), ann)
                        sent = True
                    except Exception:
                        sent = False
                out["announcement"] = ann
                out["sent_to_admin"] = sent
            self._send_json(out)
            return

        if p.path == "/api/portal/admin/send_reports":
            if _REPORT_JOB["running"]:
                self._send_json({"ok": False, "error": "Reports already send avthunnayi."})
                return
            if not config.BOT_TOKEN:
                self._send_json({"ok": False, "error": "BOT_TOKEN .env lo ledu — Telegram reports ki bot kavali."})
                return
            _portal_url = config.env("PORTAL_BASE_URL", "").strip() or (_public_base(self) + "/portal")

            def _run_reports():
                _REPORT_JOB.update({"running": True, "sent": 0, "failed": 0, "total": 0})
                try:
                    mb = Members()
                    tg = Telegram()
                    targets = [u for u, mm in (mb.members or {}).items()
                               if str(u).isdigit() and (mm.get("registered") or mm.get("name"))]
                    _REPORT_JOB["total"] = len(targets)
                    for u in targets:
                        try:
                            tg.send_message(str(u), portal.report_text(mb, u, _portal_url))
                            _REPORT_JOB["sent"] += 1
                        except Exception:
                            _REPORT_JOB["failed"] += 1
                        time.sleep(0.12)
                    _REPORT_JOB["last"] = datetime.now().isoformat(timespec="seconds")
                except Exception as ex:
                    _REPORT_JOB["last"] = f"error: {ex}"
                _REPORT_JOB["running"] = False

            _threading.Thread(target=_run_reports, daemon=True).start()
            self._send_json({"ok": True, "started": True})
            return

        if p.path == "/api/portal/admin/notices/create":
            n = portal.add_notice(body.get("title", ""), body.get("body", ""),
                                  body.get("link", ""), body.get("goal", ""))
            self._send_json({"ok": bool(n), "notice": n})
            return

        if p.path == "/api/portal/admin/exams/create":
            e = portal.create_exam(
                body.get("title", ""), body.get("goal", "mixed"),
                body.get("starts_at", ""), body.get("duration_min", 30),
                body.get("n_q", 20), neg=float(body.get("neg") or 0))
            if e:
                self._send_json({"ok": True, "id": e["id"], "title": e["title"],
                                 "n_q": len(e["qs"]), "starts_at": e["starts_at"]})
            else:
                self._send_json({"ok": False, "error": "Exam create avvaledu — time/questions check cheyyandi."})
            return

        if p.path == "/api/campus/create":
            college = body.get("college", "College").strip()
            district = body.get("district", "District").strip()
            nq = int(body.get("n_q", 10))
            lvl = body.get("level", "easy")
            subjs = body.get("subjects", ["reasoning", "quant", "science", "english", "ca"])
            start_at = (body.get("start_at") or "").strip()
            try:
                neg = max(0, min(int(body.get("neg", 0) or 0), 10))
            except Exception:
                neg = 0
            colleges = [c.strip() for c in college.split(",") if c.strip()][:12]
            if len(colleges) > 1:
                code = campus.new_event(
                    f"{colleges[0]} + {len(colleges) - 1} Colleges × StudentUp Challenge",
                    district, colleges, n_q=nq, level=lvl, created_by="dashboard",
                    mode="college", subjects=subjs, start_at=start_at, neg=neg, shuffle=True)
            else:
                code = campus.quick_event(college, district, n_q=nq, level=lvl, subjects=subjs, start_at=start_at, neg=neg)
            try:
                poster = campus.poster_text(code)
            except Exception:
                poster = ""

            bot = _bot_username()
            link = campus.deep_link(code, bot)
            qr = f"/api/campus/qr?code={code}"
            warn = ""
            if bot == "StudentUpBot" and not getattr(config, "BOT_USERNAME", ""):
                warn = "BOT_USERNAME is not set and the bot name could not be auto-detected — set BOT_USERNAME in .env, otherwise this QR may open the wrong bot."

            self._send_json({
                "ok": True,
                "code": code,
                "college": colleges[0] if colleges else college,
                "colleges": colleges,
                "bot": bot,
                "bot_warning": warn,
                "start_at": start_at,
                "neg": neg,
                "poster": poster,
                "link": link,
                "qr": qr,
                "web_link": f"{_public_base(self)}/exam/{code}",
                "web_qr": f"/api/campus/qr?code={code}&web=1"
            })
            return

        if p.path == "/api/squads/create":
            name = body.get("name", "Squad").strip()
            leader = body.get("leader", "Admin").strip()
            # Generate 4-letter squad code
            import random, string
            letters = string.ascii_uppercase
            sq_data = hooks._sq()
            code = "".join(random.choice(letters) for _ in range(4))
            while code in sq_data.get("squads", {}):
                code = "".join(random.choice(letters) for _ in range(4))

            sq_data.setdefault("squads", {})[code] = {
                "code": code,
                "name": name,
                "leader": leader,
                "members": [leader],
                "created": datetime.now().isoformat()
            }
            sq_data.setdefault("by_uid", {})[leader] = code
            hooks.save_json_atomic(hooks.SQUADS_PATH, sq_data)

            bot = getattr(config, "BOT_USERNAME", "") or "StudentUpBot"
            link = f"https://t.me/{bot}?start=sq_{code}"
            qr = f"https://api.qrserver.com/v1/create-qr-code/?size=600x600&data={link}"

            self._send_json({
                "ok": True,
                "code": code,
                "name": name,
                "link": link,
                "qr": qr
            })
            return

        if p.path == "/api/squads/join":
            code = body.get("code", "").strip().upper()
            uid = str(body.get("uid", "")).strip()
            sq_data = hooks._sq()
            
            clean_code = code.replace("SQ-", "").strip()
            if clean_code not in sq_data.get("squads", {}):
                self._send_json({"ok": False, "message": f"Squad SQ-{clean_code} not found"})
                return

            sq = sq_data["squads"][clean_code]
            if uid not in sq.get("members", []):
                sq.setdefault("members", []).append(uid)
                sq_data.setdefault("by_uid", {})[uid] = clean_code
                hooks.save_json_atomic(hooks.SQUADS_PATH, sq_data)

            self._send_json({
                "ok": True,
                "code": clean_code,
                "name": sq["name"],
                "members_count": len(sq["members"]),
                "members": sq["members"]
            })
            return

        if p.path == "/api/excel/inspect":
            b64 = body.get("file_b64", "")
            fname = body.get("filename", "workbook.xlsx")
            if not b64:
                self._send_json({"ok": False, "error": "No file data received"})
                return
            try:
                raw_bytes = base64.b64decode(b64)
                sheets_info = bundle_manager.inspect_xlsx_sheets_bytes(raw_bytes)
                self._send_json({"ok": True, "filename": fname, "sheets": sheets_info})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if p.path == "/api/excel/import_selected":
            b64 = body.get("file_b64", "")
            sel_sheets = body.get("sheets", [])
            if not b64 or not sel_sheets:
                self._send_json({"ok": False, "error": "Missing file or selected sheets"})
                return
            try:
                raw_bytes = base64.b64decode(b64)
                res = bundle_manager.import_from_multisheet_excel(raw_bytes, sel_sheets)
                self._send_json(res)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if p.path == "/api/broadcast/dispatch":
            msg = body.get("message", "")
            att_url = body.get("attachment_url", "")
            att_b64 = body.get("attachment_data_b64", "")
            att_fname = body.get("attachment_filename", "")
            ch_keys = body.get("target_channel_keys", [])
            g_ids = body.get("target_group_ids", [])
            gw = body.get("gateway_url", "")

            res = bundle_manager.dispatch_bulk_broadcast(
                message=msg,
                attachment_url=att_url,
                attachment_data_b64=att_b64,
                attachment_filename=att_fname,
                target_group_ids=g_ids,
                target_channel_keys=ch_keys,
                gateway_url=gw
            )
            self._send_json(res)
            return

        if p.path == "/api/excel/import":
            raw_text = body.get("raw_text", "")
            res = bundle_manager.import_from_csv_or_excel_text(raw_text)
            self._send_json(res)
            return

        if p.path == "/api/bundles/create":
            name = body.get("name", "Cluster Bundle")
            cat = body.get("category", "POLICE")
            gids = body.get("group_ids", [])
            ch_keys = body.get("channel_keys", [])
            b = bundle_manager.create_bundle(name, cat, gids, ch_keys)
            self._send_json({"ok": True, "bundle": b})
            return

        if p.path == "/api/bundles/delete":
            bid = body.get("id")
            ok = bundle_manager.delete_bundle(bid)
            self._send_json({"ok": ok})
            return

        if p.path == "/api/whatsapp/request_qr":
            info = whatsapp_pipeline.request_login_qr()
            self._send_json({"ok": True, "session": info})
            return

        if p.path == "/api/whatsapp/request_code":
            phone = body.get("phone", "")
            info = whatsapp_pipeline.request_pairing_code(phone)
            self._send_json({"ok": True, "session": info})
            return

        if p.path == "/api/whatsapp/confirm_login":
            dev = body.get("device_name", "Primary WhatsApp Phone")
            info = whatsapp_pipeline.confirm_session_connected(dev)
            self._send_json({"ok": True, "session": info})
            return

        if p.path == "/api/whatsapp/sync_dialogs":
            res = whatsapp_pipeline.sync_dialogs_from_session()
            self._send_json(res)
            return

        if p.path == "/api/whatsapp/quick_add":
            raw = body.get("text", "")
            if not raw.strip():
                self._send_json({"ok": False, "error": "no links given"})
                return
            res = whatsapp_pipeline.quick_add_groups(raw)
            self._send_json(res)
            return

        if p.path == "/api/whatsapp/logout":
            res = whatsapp_pipeline.logout_session()
            self._send_json({"ok": True, "session": res})
            return

        if p.path == "/api/whatsapp/schedule_quiz":
            time_val = body.get("time", "09:00")
            gids = body.get("target_group_ids", [])
            cat = body.get("category", "ALL")
            is_q = body.get("is_question", True)
            label = body.get("label", "").strip()
            q_count = int(body.get("questions_count", 1))
            days_dur = int(body.get("days_duration", 0))
            auto_mode = bool(body.get("auto_mode", True))
            end_date = body.get("end_date", "")

            # Support multiple times in one schedule call if times array passed
            times = body.get("times") or [time_val]
            created_jobs = []
            for t_item in times:
                t_str = str(t_item).strip()
                if not t_str:
                    continue
                job = whatsapp_pipeline.add_scheduled_job(
                    t_str,
                    target_group_ids=gids,
                    category=cat,
                    is_question=is_q,
                    label=label or f"{t_str} Daily {cat} Drill",
                    questions_count=q_count,
                    days_duration=days_dur,
                    auto_mode=auto_mode,
                    end_date=end_date,
                    start_date=str(body.get("start_date", "")).strip(),
                    subjects=[str(s).upper() for s in (body.get("subjects") or []) if s],
                    weekdays=body.get("weekdays") or [],
                    answer_delay_minutes=int(body.get("answer_delay_minutes", 5)),
                )
                created_jobs.append(job)

            self._send_json({"ok": True, "jobs": created_jobs, "job": created_jobs[0] if created_jobs else None})
            return

        if p.path == "/api/whatsapp/check_conflicts" or p.path == "/api/bundles/check_conflicts":
            gids = body.get("target_group_ids", [])
            ch_keys = body.get("target_channel_keys", [])
            time_val = body.get("time", "")
            bid = body.get("bundle_id", "")
            conflicts = bundle_manager.check_conflicts(gids, ch_keys, time_str=time_val, current_bundle_id=bid)
            self._send_json({"ok": True, "conflicts": conflicts, "has_conflicts": len(conflicts) > 0})
            return

        if p.path == "/api/whatsapp/toggle_schedule":
            jid = body.get("id")
            updated = whatsapp_pipeline.toggle_scheduled_job(jid)
            self._send_json({"ok": bool(updated), "job": updated})
            return

        if p.path == "/api/whatsapp/update_schedule":
            jid = body.get("id")
            updates = {k: v for k, v in body.items() if k != "id"}
            job = whatsapp_pipeline.update_scheduled_job(jid, updates)
            self._send_json({"ok": bool(job), "job": job,
                             "message": "✏️ Schedule updated!" if job else "job not found"})
            return

        if p.path == "/api/whatsapp/delete_schedule":
            jid = body.get("id")
            ok = whatsapp_pipeline.delete_scheduled_job(jid)
            self._send_json({"ok": ok})
            return

        if p.path == "/api/conductor/create":
            from core import conductor as _cd
            try:
                ev = _cd.create_event(
                    title=body.get("title", ""), kind=body.get("kind", "grand"),
                    starts_at=body.get("starts_at", ""),
                    channel=body.get("channel", "CURRENT"),
                    duration_min=body.get("duration_min"),
                    n_questions=body.get("n_questions"),
                    lobby_min=body.get("lobby_min", 5),
                    campus_name=body.get("campus_name", ""),
                    district=body.get("district", ""))
                try:
                    from core import auditlog as _al
                    _al.log("conductor.create", f"{ev['kind']} {ev['title']} @ {ev['starts_at']}")
                except Exception:
                    pass
                self._send_json({"ok": True, "event": ev,
                                 "message": f"✅ {ev['title']} schedule ayyindi — {ev['starts_at']} ki automatic ga start avuthundi (bot run avuthunte)"})
            except ValueError as e:
                self._send_json({"ok": False, "error": str(e)})
            return

        if p.path == "/api/conductor/cancel":
            from core import conductor as _cd
            ok = _cd.cancel_event(str(body.get("id", "")))
            try:
                from core import auditlog as _al
                _al.log("conductor.cancel", f"{body.get('id')} ok={ok}")
            except Exception:
                pass
            self._send_json({"ok": ok})
            return

        if p.path == "/api/conductor/launch":
            from core import conductor as _cd
            ev = _cd.get_event(str(body.get("id", "")))
            if not ev:
                self._send_json({"ok": False, "error": "event dorakaledu"})
                return
            if ev.get("status") not in ("scheduled", "failed"):
                self._send_json({"ok": False, "error": f"status {ev.get('status')} — launch cheyyalenu"})
                return
            from core.engine import Engine as _Engine
            ok, msg = _cd.launch_event(
                ev, bank=Bank(), members=Members(), tg=Telegram(),
                engine_factory=lambda: _Engine(dry=False))
            if not ok and ev.get("status") == "scheduled":
                _cd._update(ev["id"], status="failed", error=str(msg)[:200])
            try:
                from core import auditlog as _al
                _al.log("conductor.launch", f"{ev['id']} {ev['kind']} ok={ok}")
            except Exception:
                pass
            self._send_json({"ok": ok, "message": msg})
            return

        if p.path == "/api/conductor/result":
            from core import conductor as _cd
            ev = _cd.get_event(str(body.get("id", "")))
            if not ev:
                self._send_json({"ok": False, "error": "event dorakaledu"})
                return
            self._send_json({"ok": True, "text": _cd.result_text(ev, members=Members())})
            return

        if p.path == "/api/flags":
            from core import flags as _fl
            ok = _fl.set_flag(str(body.get("name", "")), bool(body.get("enabled")))
            try:
                from core import auditlog as _al
                _al.log("flag.toggle", f"{body.get('name')} -> {bool(body.get('enabled'))} (ok={ok})")
            except Exception:
                pass
            self._send_json({"ok": ok, "flags": _fl.all_flags()})
            return

        if p.path == "/api/pulse/settings":
            from core import pulse as _pl
            _pl.save_settings(price_inr=body.get("price_inr"),
                              conversion_pct=body.get("conversion_pct"),
                              plan_name=body.get("plan_name"))
            try:
                from core import auditlog as _al
                _al.log("pulse.settings", f"price={body.get('price_inr')} conv={body.get('conversion_pct')}")
            except Exception:
                pass
            self._send_json(_pl.report())
            return

        if p.path == "/api/item_intel/reset":
            from core import item_intel as _ii
            qid = str(body.get("qid", "")).strip()
            removed = _ii.reset(qid) if qid else False
            try:
                from core import auditlog as _al
                _al.log("item_intel.reset", f"qid={qid} removed={removed}")
            except Exception:
                pass
            self._send_json({"ok": removed, "qid": qid,
                             "message": ("✅ Stats reset — question malli nerchukuntundi (quarantine lift ayyindi)"
                                         if removed else "qid dorakaledu")})
            return

        if p.path == "/api/setup/manual_add":
            # ✍️ MANUAL SETUP — Excel lekunda, okka form tho target + exam
            # + timings + subjects + days. Excel import_rows_list ne reuse
            # chestundi (validation/dedupe/auto-schedule rendu chotla okkate).
            platform = str(body.get("platform", "wa")).lower()
            m_name = str(body.get("name", "")).strip()
            m_link = str(body.get("link", "")).strip()
            m_exam = str(body.get("exam", "")).strip() or "AUTO"
            m_times = body.get("times", "")
            if isinstance(m_times, list):
                m_times = "+".join(str(x).strip() for x in m_times if str(x).strip())
            m_times = str(m_times).replace(",", "+").replace(" ", "+")
            m_count = str(body.get("count", 5))
            m_days = str(body.get("days", 0))
            m_subjects = "+".join(str(s).strip().upper()
                                  for s in (body.get("subjects") or []) if str(s).strip())
            if not m_name or not m_link:
                self._send_json({"ok": False, "error": "Name mariyu Link/JID rendu kavali"})
                return
            if platform == "tg":
                rows = [[m_name, m_link, m_exam, str(body.get("type", "channel")),
                         m_times, m_count, m_days, m_subjects]]
                res = bundle_manager.import_rows_list(rows, kind="tg")
                sched = bundle_manager.create_tg_schedules_for_imports(
                    res.pop("tg_schedules_wanted", []), "✍️ Manual")
                res.pop("schedules_wanted", None)
            else:
                rows = [[m_name, m_link, m_exam, str(body.get("shift", "ALL_DAY")),
                         str(body.get("type", "EXAM_SPECIFIC")),
                         m_times, m_count, m_days, m_subjects]]
                res = bundle_manager.import_rows_list(rows, kind="wa")
                sched = bundle_manager.create_schedules_for_imports(
                    res.pop("schedules_wanted", []), "✍️ Manual")
                res.pop("tg_schedules_wanted", None)
            added = res.get("imported_groups_count", 0) + res.get("imported_channels_count", 0)
            try:
                from core import auditlog as _al
                _al.log("setup.manual_add", f"{platform} {m_name} added={added} schedules={len(sched)}")
            except Exception:
                pass
            self._send_json({
                "ok": added > 0,
                "added_groups": res.get("imported_groups_count", 0),
                "added_channels": res.get("imported_channels_count", 0),
                "schedules_created": len(sched),
                "skipped_duplicates": res.get("skipped_duplicates", []),
                "errors": res.get("errors", []),
                "message": (f"✅ {m_name} add ayyindi + {len(sched)} schedule(s)!"
                            if added else "❌ Add avvaledu — kindha errors chudandi"),
            })
            return

        if p.path == "/api/whatsapp/add_group":
            name = body.get("name", "").strip()
            jid = body.get("jid", "").strip()
            cat = body.get("category", "AUTO")
            shift = body.get("shift", "ALL_DAY")
            g_type = body.get("group_type", "EXAM_SPECIFIC")
            new_g = whatsapp_pipeline.add_group(name, jid, cat, shift, group_type=g_type)
            self._send_json({"ok": True, "group": new_g})
            return

        if p.path == "/api/whatsapp/update_group":
            gid = body.get("id")
            updates = body.get("updates", {})
            updated = whatsapp_pipeline.update_group(gid, updates)
            self._send_json({"ok": bool(updated), "group": updated})
            return

        if p.path == "/api/whatsapp/remove_group":
            gid = body.get("id")
            ok = whatsapp_pipeline.remove_group(gid)
            self._send_json({"ok": ok})
            return

        if p.path == "/api/whatsapp/start_pipeline":
            cat = body.get("category", "ALL")
            shift = body.get("shift", "ALL")
            target_gids = body.get("target_group_ids", None)
            is_q = body.get("is_question", True)
            msg = body.get("custom_msg", "")
            att = body.get("attachment", "")
            gw = body.get("gateway", "").strip()
            delay_min = int(body.get("delay_min", 60))
            delay_max = int(body.get("delay_max", 80))
            q_count = int(body.get("questions_count", 5))
            subjects = body.get("subjects", None)

            if gw:
                reg = whatsapp_pipeline.load_wa_registry()
                reg["gateway_url"] = gw
                whatsapp_pipeline.save_wa_registry(reg)

            res = whatsapp_pipeline.start_interleaved_broadcast(
                target_category=cat,
                shift_filter=shift,
                target_group_ids=target_gids,
                is_question=is_q,
                questions_per_group=q_count,
                custom_message=msg,
                attachment_url=att,
                two_phase_answer=True,
                delay_min=delay_min,
                delay_max=delay_max,
                subjects=subjects
            )
            self._send_json(res)
            return

        if p.path == "/api/whatsapp/stop_pipeline":
            res = whatsapp_pipeline.stop_broadcast()
            self._send_json(res)
            return

        if p.path == "/api/questions/send":
            # 🔍→📤 send ONE hand-picked question to any channel/group instantly
            qid = str(body.get("qid", "")).strip()
            ch = str(body.get("channel", "")).strip()
            if not qid or not ch:
                self._send_json({"ok": False, "error": "qid మరియు channel రెండూ కావాలి"})
                return
            from core.engine import Engine
            from core.telegram import Telegram
            from core import broadcast_log
            bank = Bank()
            q = next((x for x in bank.questions if x.get("id") == qid), None)
            if not q:
                self._send_json({"ok": False, "error": f"question {qid} కనపడలేదు"})
                return
            dry = not bool(Telegram().token)
            eng = Engine(dry=dry)
            send_key = ch if ch in config.CHANNELS else "CURRENT"
            # channel/group post → 👍 reaction text-poll style (flag ON);
            # native quiz poll only when the owner kills the flag in Pro Ops
            ok = eng._send_channel_question(send_key, q)
            if ok and not dry:
                try:
                    bank.mark_posted(q.get("channel", "CURRENT"), [q])
                except Exception:
                    pass
            all_ch = channel_router.get_all_channels()
            label = all_ch.get(ch, {}).get("name", ch)
            broadcast_log.log_event("telegram", "🎯 " + label, 1 if ok else 0,
                                    dry=dry, note="hand-picked: " + qid)
            self._send_json({
                "ok": bool(ok),
                "message": (f"🎯 Hand-picked question '{qid}' → {label} " +
                            ("[Live]" if not dry else "[Dry-Run — BOT_TOKEN set చేయండి]")) if ok else "send failed",
            })
            return

        if p.path == "/api/bank/topup":
            # ⚡ AUTO TOP-UP: refill thin channels with freshly generated questions
            try:
                from core.generator import top_up
                added, errs = top_up(per_channel_min=25)
                self._send_json({
                    "ok": True,
                    "added": len(added or []),
                    "rejected": len(errs or []),
                    "message": f"⚡ {len(added or [])} కొత్త fresh questions add అయ్యాయి! ({len(errs or [])} rejected by quality gate)",
                })
            except Exception as e:
                self._send_json({"ok": False, "error": f"top-up failed: {e}"})
            return

        if p.path == "/api/telegram/schedule":
            # 🤖 Telegram Auto-Pilot: daily auto-posts to chosen channels/groups
            times = body.get("times", [])
            if isinstance(times, str):
                times = [t.strip() for t in times.replace(",", " ").split() if t.strip()]
            channels = body.get("channels", [])
            count = max(1, min(int(body.get("count", 1) or 1), 20))
            subjects = body.get("subjects", []) or []
            if not times:
                self._send_json({"ok": False, "error": "కనీసం ఒక time ఇవ్వండి (ఉదా: 08:00)"})
                return
            if not channels:
                self._send_json({"ok": False, "error": "టేబుల్‌లో కనీసం ఒక channel/group select చేయండి"})
                return
            created = []
            for t in times:
                job = whatsapp_pipeline.add_scheduled_job(
                    t,
                    label=f"🤖 TG Auto-Pilot {t} · {len(channels)} target(s)" + (f" · {'+'.join(subjects)}" if subjects else ""),
                    questions_count=count,
                    telegram_channels=channels,
                    subjects=subjects,
                    mode="tg",
                )
                created.append({"id": job["id"], "time": job["time"]})
            self._send_json({
                "ok": True,
                "created": created,
                "message": f"🤖 Auto-Pilot ON: {len(created)} daily slot(s) × {len(channels)} Telegram target(s) × {count} poll(s) — posts are instant, no gaps.",
            })
            return

        if p.path == "/api/channels/detect_new":
            res = channel_router.detect_new_bot_chats()
            self._send_json(res)
            return

        if p.path == "/api/channels/register":
            name = body.get("name", "").strip()
            exam_t = body.get("exam_type", "")
            chat_id = body.get("chat_id", "")
            chat_type = body.get("chat_type", "channel")
            info = channel_router.register_channel(name, chat_id=chat_id, exam_type=exam_t, chat_type=chat_type)

            try:
                from core import dynamic_generator
                dynamic_generator.synthesize_quiz(info["key"], name, count=5)
            except Exception as e:
                print(f"Auto-synthesizer note: {e}")

            self._send_json({"ok": True, "channel": info, "message": f"Channel registered & 5 syllabus questions synthesized!"})
            return

        if p.path == "/api/post_poll":
            # 🚀 Shared dispatcher: correct chat targeting (custom groups get
            # their OWN chat), no-repeat rotation, history logging — Telegram
            # sends stay instant (official Bot API, no gaps).
            from core import poll_dispatch
            ch = body.get("channel", "CURRENT")
            count = int(body.get("count", 1))
            subjects = body.get("subjects", None)
            res = poll_dispatch.post_channel_polls(ch, count=count, subjects=subjects, source="dashboard")
            self._send_json({
                "ok": res.get("ok", False),
                "sent_count": res.get("sent", 0),
                "message": res.get("message", ""),
            })
            return

        if p.path == "/api/squads/create":
            name = body.get("name", "Dashboard Squad").strip()
            leader = body.get("leader", "Admin").strip()
            sq_data = hooks._sq()
            alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
            code = "".join(random.choice(alphabet) for _ in range(4))
            while code in sq_data.get("squads", {}):
                code = "".join(random.choice(alphabet) for _ in range(4))
            
            sq_data.setdefault("squads", {})[code] = {
                "code": code,
                "name": name,
                "leader": leader,
                "members": [leader],
                "created": datetime.now().isoformat()
            }
            hooks.save_json_atomic(hooks.SQUADS_PATH, sq_data)
            bot = getattr(config, "BOT_USERNAME", "") or "StudentUpBot"
            squad_link = f"https://t.me/{bot}?start=sq_{code}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=600x600&data={squad_link}"
            self._send_json({"ok": True, "code": code, "name": name, "link": squad_link, "qr": qr_url})
            return

        if p.path == "/api/war":
            act = body.get("act", "status")
            mins = int(body.get("mins", 5))
            mb = Members()
            tg = Telegram()
            bank = Bank()
            if act == "now":
                ok, txt = districtwar.manual_launch(mb, tg, bank=bank, minutes=mins)
                self._send_json({"ok": ok, "message": txt})
            else:
                txt = districtwar.owner_status(mb)
                self._send_json({"ok": True, "message": txt})
            return

        if p.path == "/api/sheet":
            act = body.get("act", "sync")
            mb = Members()
            if act == "sync":
                n = mb.sync_sheet_all()
                self._send_json({"ok": True, "message": f"Successfully synced {n} members to Google Sheet!"})
            else:
                q = crm.flush_queue()
                self._send_json({"ok": True, "message": f"Flushed {q} queued items to Google Sheet."})
            return

        # unknown route -> JSON 404 (browser ki empty page padakudadhu)
        if p.path.startswith("/api/"):
            self._send_json({"ok": False,
                             "error": f"unknown endpoint: {p.path}"}, code=404)
        else:
            self.send_response(404)
            self.end_headers()


def start_server(port=PORT):
    class _Srv(ThreadingHTTPServer):
        daemon_threads = True
        request_queue_size = 256  # 🚀 10k students burst ki pedda queue

    srv = _Srv(("0.0.0.0", port), DashboardHandler)
    print(f"🚀 StudentUp Control Dashboard running at http://0.0.0.0:{port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")


if __name__ == "__main__":
    start_server()
