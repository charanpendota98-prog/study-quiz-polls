"""
SOCIAL GROWTH ENGINE — turn every student into an Instagram follower / YouTube
subscriber, and turn every district's businesses into inbound partner leads.

A. Instagram / YouTube "code drop" (auto-DM loop)
   1. You post on Instagram: "Comment QUIZ → auto-DM లో secret code వస్తుంది".
   2. Instagram auto-DM (native or ManyChat) fires ONLY for followers → it sends the
      campaign code, e.g.  SU-MAY7  (you create it here: /social new …).
   3. Student types  /claim SU-MAY7  in the bot → +points, once per campaign.
      Because the code only reaches followers, the code itself is the proof —
      no screenshot review needed.  The same works for YouTube (pinned comment
      / community post / code spoken in the video: "video చివర్లో code").
   4. Fallback for students who can't get the DM: send the screenshot in the
      bot → staff sees it with ✅ / ❌ buttons (/social approve queue).
   5. Streak bonus: claim 5 campaigns → "Super Fan" +100; every campaign shows
      followers gained (claims), so you know which post worked.

B. Business lead engine ("every district's shops should contact US")
   • /scout  — students submit a business lead (name · type · phone). When the
     admin converts it to a partner, the scout earns SCOUT_PTS and a free voucher.
   • Grand-opening package: partner tagged "opening" → the ad card says
     "🎉 NEW OPENING", is shown twice a day for a week, and the first N students
     to redeem get a launch freebie.
   • /pitch <district> — one-tap sales sheet with the district's live numbers
     (members, active this week, top exams) that you forward to any business.
   • Weekly Monday "Partner with StudentUp" post in hub channels listing the
     districts with most members + how to apply → inbound applications.

State: data/social.json {campaigns:{code:{…}}, claims:{uid:[codes]}, pending:[…], leads:[…]}
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "social.json"
CLAIM_PTS_DEFAULT = 30
SUPERFAN_EVERY, SUPERFAN_PTS = 5, 100
SCREENSHOT_PTS = 20
SCOUT_PTS, SCOUT_CONVERT_PTS = 10, 150
PLATFORMS = {"ig": "📸 Instagram", "yt": "▶️ YouTube", "fb": "📘 Facebook", "x": "🐦 X"}
INSTAGRAM = getattr(config, "INSTAGRAM_HANDLE", "") or "studentup"
YOUTUBE = getattr(config, "YOUTUBE_HANDLE", "") or "@studentup"


def _now():
    return datetime.now(config.IST)


def _load():
    d = load_json(PATH, {}) or {}
    for k, v in (("campaigns", {}), ("claims", {}), ("pending", []), ("leads", []), ("stats", {})):
        d.setdefault(k, v)
    return d


def _save(d):
    save_json_atomic(PATH, d)


def _code(existing):
    while True:
        c = "SU-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if c not in existing:
            return c


# ==================================================================== campaigns
def new_campaign(platform, title, pts=CLAIM_PTS_DEFAULT, days=3, code="", cap=0):
    d = _load()
    code = (code or _code(d["campaigns"])).upper().strip()
    d["campaigns"][code] = {"code": code, "platform": platform if platform in PLATFORMS else "ig",
                            "title": title[:80], "pts": int(pts), "cap": int(cap), "claims": 0,
                            "created": _now().isoformat(),
                            "expires": (_now() + timedelta(days=int(days))).isoformat(), "active": True}
    _save(d)
    return code


def auto_dm_text(code):
    """Paste this into Instagram's auto-DM / ManyChat reply — it carries the code."""
    d = _load()
    c = d["campaigns"].get(code.upper())
    if not c:
        return "Campaign not found."
    return "\n".join([
        f"Thanks for following {INSTAGRAM} 🙌",
        f"మీ secret code: {code}",
        f"Telegram bot లో type చేయండి → /claim {code}  → +{c['pts']} points 🎁",
        f"Bot: t.me/{config.BOT_USERNAME or 'StudentUpBot'}",
        "Points తో మీ జిల్లా shops / coaching / restaurant offers claim చేయండి 🍽🎓",
    ])


def claim(members, uid, code):
    """/claim CODE → points once per campaign; Super-Fan bonus every 5 claims."""
    try:
        d = _load()
        code = code.upper().strip()
        c = d["campaigns"].get(code)
        if not c or not c.get("active"):
            return False, "❌ Code సరైనది కాదు / expired. Instagram లో మా latest post చూడండి 📸"
        if datetime.fromisoformat(c["expires"]) < _now():
            return False, "⏳ ఈ code expire అయింది — next post కి ready గా ఉండండి!"
        if c.get("cap") and c["claims"] >= c["cap"]:
            return False, "😮 ఈ code కి limit అయిపోయింది — next post లో fast గా claim చేయండి!"
        mine = d["claims"].setdefault(str(uid), [])
        if code in mine:
            return False, "✅ ఇప్పటికే claim చేశారు."
        m = members._get(str(uid))
        if not m.get("registered"):
            return False, "ముందు register అవ్వండి → /start"
        mine.append(code)
        c["claims"] += 1
        m["points"] = m.get("points", 0) + c["pts"]
        m["social_claims"] = m.get("social_claims", 0) + 1
        m.setdefault("follows", {})[c["platform"]] = True
        bonus = 0
        if m["social_claims"] % SUPERFAN_EVERY == 0:
            bonus = SUPERFAN_PTS
            m["points"] += bonus
            m["superfan"] = m.get("superfan", 0) + 1
        members.kv.save()
        _save(d)
        txt = f"🎉 {PLATFORMS[c['platform']]} code accepted → +{c['pts']} pts!"
        if bonus:
            txt += f"\n🌟 SUPER FAN — {m['social_claims']} campaigns claimed → +{bonus} bonus!"
        txt += f"\n\nమీ జిల్లా offers: /offers · Wallet: /wallet"
        return True, txt
    except Exception as e:
        print(f"   [social] claim {e}")
        return False, "Claim failed — try again."


def campaign_stats():
    d = _load()
    if not d["campaigns"]:
        return "No campaigns. /social new ig|<title>|<pts>|<days>  → code → paste in Instagram auto-DM"
    lines = ["📈 Social campaigns (claims = new followers verified):"]
    for c in sorted(d["campaigns"].values(), key=lambda x: x["created"], reverse=True)[:15]:
        st = "✅" if c["active"] and datetime.fromisoformat(c["expires"]) >= _now() else "⏹"
        lines.append(f"{st} {c['code']} {PLATFORMS[c['platform']].split()[0]} {c['title'][:30]} — {c['claims']} claims · {c['pts']} pts · till {c['expires'][:10]}")
    ig = sum(c["claims"] for c in d["campaigns"].values() if c["platform"] == "ig")
    yt = sum(c["claims"] for c in d["campaigns"].values() if c["platform"] == "yt")
    lines += ["", f"Verified: Instagram {ig} · YouTube {yt} · screenshots approved {d['stats'].get('shots_ok', 0)}"]
    return "\n".join(lines)


def follow_prompt():
    """Shown after a quiz / in welcome — the ask + how it pays."""
    return "\n".join([
        f"📸 Instagram {INSTAGRAM} follow అయ్యి, latest post కి 'QUIZ' అని comment చేయండి",
        "→ auto-DM లో secret code వస్తుంది → bot లో /claim CODE → points 🎁",
        f"▶️ YouTube {YOUTUBE} subscribe — video చివర్లో code చెబుతాం!",
        "DM రాలేదా? follow screenshot ఇక్కడే పంపండి → staff verify → +%d" % SCREENSHOT_PTS,
    ])


# ============================================================ screenshot fallback
def queue_screenshot(uid, name, file_id, platform="ig"):
    d = _load()
    if any(p["uid"] == str(uid) and p["platform"] == platform for p in d["pending"]):
        return "⏳ మీ screenshot already review లో ఉంది."
    if any(p["uid"] == str(uid) and p["platform"] == platform for p in d.get("approved", [])):
        return "✅ ఈ platform కి already verified."
    d["pending"].append({"uid": str(uid), "name": name, "file_id": file_id, "platform": platform, "ts": _now().isoformat()})
    d["pending"] = d["pending"][-500:]
    _save(d)
    return "📥 Screenshot received — staff verify చేశాక +%d pts వస్తాయి." % SCREENSHOT_PTS


def review_screenshot(members, uid, platform, ok):
    d = _load()
    d["pending"] = [p for p in d["pending"] if not (p["uid"] == str(uid) and p["platform"] == platform)]
    if ok:
        d.setdefault("approved", []).append({"uid": str(uid), "platform": platform, "ts": _now().isoformat()})
        d["stats"]["shots_ok"] = d["stats"].get("shots_ok", 0) + 1
        m = members._get(str(uid))
        m["points"] = m.get("points", 0) + SCREENSHOT_PTS
        m.setdefault("follows", {})[platform] = True
        members.kv.save()
    _save(d)
    return ok


def pending_screenshots():
    return list(_load()["pending"])


# ============================================================== business leads
def add_lead(uid, district, text):
    """/scout <business name> | <type> | <phone> | <area>  — student refers a business."""
    d = _load()
    f = [x.strip() for x in text.split("|")]
    if len(f) < 3:
        return None
    lead = {"id": f"L{len(d['leads']) + 1:04d}", "uid": str(uid), "district": district, "name": f[0][:60],
            "type": f[1][:20].lower(), "phone": f[2][:20], "area": (f[3] if len(f) > 3 else "")[:60],
            "ts": _now().isoformat(), "status": "new"}
    d["leads"].append(lead)
    d["leads"] = d["leads"][-2000:]
    _save(d)
    return lead


def convert_lead(members, lead_id, partner_id):
    """Admin converted the lead into a partner → scout gets SCOUT_CONVERT_PTS."""
    d = _load()
    for l in d["leads"]:
        if l["id"] == lead_id and l["status"] != "converted":
            l["status"] = "converted"; l["partner"] = partner_id
            m = members._get(l["uid"])
            m["points"] = m.get("points", 0) + SCOUT_CONVERT_PTS
            m["scout_wins"] = m.get("scout_wins", 0) + 1
            members.kv.save(); _save(d)
            return l
    return None


def leads_text(district=""):
    d = _load()
    ls = [l for l in d["leads"] if l["status"] == "new" and (not district or l["district"] == district)]
    if not ls:
        return "No new leads. Students add them with /scout <business> | <type> | <phone> | <area>"
    lines = [f"📋 Business leads ({len(ls)}) — call, then /partner add … and /social convert <LID> <PID>:"]
    for l in ls[-25:]:
        lines.append(f"{l['id']} · {l['district']} · {l['name']} ({l['type']}) 📞 {l['phone']} {l['area']} — scout {l['uid']}")
    return "\n".join(lines)


def district_pitch(members, district):
    """One-tap sales sheet you forward to a shop/coaching owner in that district."""
    from . import districts as D
    now = _now()
    tot = act = 0
    exams = {}
    for m in members.members.values():
        if not m.get("registered") or m.get("district") != district:
            continue
        tot += 1
        try:
            if (now - datetime.fromisoformat(m.get("last_active") or m.get("registered_at") or "")).days <= 7:
                act += 1
        except Exception:
            pass
        ex = (m.get("exam") or "GENERAL").upper()
        exams[ex] = exams.get(ex, 0) + 1
    top = ", ".join(f"{k} {v}" for k, v in sorted(exams.items(), key=lambda x: -x[1])[:4])
    return "\n".join([
        f"🤝 StudentUp × {district} ({D.telugu_name(district)}) — Partner proposal",
        "",
        f"👥 {tot} registered exam aspirants in {district} · {act} active this week",
        f"🎯 Preparing for: {top or '—'}",
        "",
        "మీకు ఏం వస్తుంది:",
        "• రోజూ మా Telegram channels + ఈ జిల్లా students DM లో మీ ad (photo/text)",
        "• Students points తో మీ offer claim → మీ shop కి వస్తారు (footfall guaranteed, ad మాత్రమే కాదు)",
        "• Exam-day special: exam centre నుంచి direct మీ shop కి (restaurant/xerox/coaching కి best)",
        "• ⚡ Flash deals: slow hours లో 2-3 గంటల offer → instant rush",
        "• 🎉 New opening? Launch package — వారం రోజులు 2× ads + first 50 students freebie",
        "• ప్రతి సోమవారం report: ఎంతమంది చూశారు, ఎంతమంది వచ్చారు",
        "",
        f"Start: Telegram bot t.me/{config.BOT_USERNAME or 'StudentUpBot'} → /partner apply",
    ])


def weekly_partner_call(members, top=6):
    """Monday hub post inviting businesses — shows the biggest districts."""
    counts = {}
    for m in members.members.values():
        if m.get("registered") and m.get("district"):
            counts[m["district"]] = counts.get(m["district"], 0) + 1
    if not counts:
        return None
    rows = sorted(counts.items(), key=lambda x: -x[1])[:top]
    lines = ["🏪 మీ జిల్లాలో business ఉందా? StudentUp partner అవ్వండి", "",
             "Shops · Malls · Coaching · Restaurants · Salons · Hostels · Xerox · Gym — కొత్త opening అయినా సరే 🎉", "",
             "📊 ఈ వారం aspirants:"]
    lines += [f"• {d} — {n} students" for d, n in rows]
    lines += ["", "మీ ad రోజూ students DM లో · students points తో మీ offer claim · weekly report",
              f"→ bot లో /partner apply  (students: shop వాళ్ళకి చెప్పండి → /scout → +{SCOUT_CONVERT_PTS} pts partner అయితే)"]
    return "\n".join(lines)


def partner_kit():
    """/social kit — the message you forward to any business owner: how to join, what to send, pricing slots."""
    bot = config.BOT_USERNAME or "StudentUpBot"
    return "\n".join([
        "🤝 StudentUp Partner Kit — 3 steps",
        "",
        "1️⃣ Telegram లో bot open: t.me/%s → /partner apply <shop పేరు> | <జిల్లా> | <type> | <phone>" % bot,
        "2️⃣ మాకు పంపండి (WhatsApp/Telegram): shop photo/poster 1, offer line (ఉదా: 'Students కి 20% off'),",
        "   points value (ఉదా: 100 pts), validity, mandal/area, counter person Telegram id",
        "3️⃣ మేము live చేస్తాం → మీకు /mystats + ప్రతి సోమవారం report",
        "",
        "📦 Packages:",
        "• 📍 District — ఆ జిల్లా students DM + channels (రోజూ 3 slots లో)",
        "• 🏠 Mandal — మీ mandal students కి top position (local shops కి best)",
        "• 🏛 State (TS లేదా AP) — రాష్ట్రం మొత్తం (chains, malls, online coaching)",
        "• 🌐 TS+AP — రెండు రాష్ట్రాలు",
        "• ⚡ Flash (2–4 గంటలు) · 📝 Exam-day · 🎉 Grand Opening (వారం 2× ads)",
        "",
        "Students points తో claim → మీ counter లో /pverify CODE → footfall guaranteed, ad మాత్రమే కాదు.",
    ])
