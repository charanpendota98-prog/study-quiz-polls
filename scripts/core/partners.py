"""
LOCAL PARTNER MARKETPLACE — district merchants × students × your channels.

Business loop
  1. A shop / coaching institute / restaurant / salon / mall in a district
     becomes a PARTNER (admin adds them with /partner add …, or they apply via
     /partner apply and admin approves).
  2. The partner gives an OFFER for StudentUp members ("₹100 off Group-2 test
     series", "20 % off on exam day", "free coffee with any meal") and pays you
     for the ad slot (you handle money outside the bot).
  3. Bot posts the partner's AD CARD in the hub/JOBS channel on schedule (3 slots
     a day, rotated, district-tagged) and DMs it only to members of that district
     (opt-out respected) — targeted, so an Adilabad salon never spams Guntur.
  4. Students REDEEM the offer with points (/offers → district offers → tap):
     one-time code PT-XXXXXX; the merchant verifies it at the counter with
     /pverify PT-XXXXXX (merchant's own Telegram id is authorised per partner) —
     you never have to be present.  Exam-day offers unlock only on the exam
     window you set (e.g. TSPSC Group-2 15–17 Oct) for members whose target exam
     matches — "exam రాసి వచ్చి claim చేయండి".
  5. Partner analytics for YOUR sales pitch: impressions (posts+DMs), redemptions,
     unique students, districts — /partner stats <id>.

Referral upgrade (smart tiers, anti-abuse)
  base +20 … but referee must REGISTER and play 3 rounds within 7 days for the
  referrer to get the extra +30 ("activated referral"), +50 more at 5 activated,
  +100 at 10, and a monthly "Top Recruiter" spotlight. Self/duplicate/blocked
  referrals earn nothing (already enforced in members.add_referral).

State: data/partners.json  {partners:{id:{…}}, offers:{id:{…}}, vouchers:{code:{…}},
                            ads:{queue:[…], log:[…]}, applications:[…]}
Every public function is guarded — a bad partner record can never crash the bot.
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "partners.json"
AD_SLOTS = [t.strip() for t in (getattr(config, "AD_SLOTS", "") or "10:30,15:30,20:45").split(",") if t.strip()]
AD_CHANNELS = getattr(config, "AD_CHANNELS", None) or getattr(config, "CHAMPION_CHANNELS", ["CURRENT"])
VOUCHER_DAYS = 30
CATEGORIES = {"coaching": "🎓 Coaching / Institute", "books": "📚 Books / Stationery", "food": "🍽 Restaurant / Café",
              "salon": "💇 Salon / Beauty", "shop": "🛍 Shop / Mall", "hostel": "🏠 Hostel / PG", "tech": "💻 Internet / Xerox",
              "health": "🩺 Health / Gym", "other": "🏪 Other"}
REF_ACTIVATE_ROUNDS, REF_ACTIVATE_DAYS = 3, 7
REF_BASE, REF_ACTIVATED, REF_MILESTONES = 20, 30, {5: 50, 10: 100, 25: 300}
REF_MENTOR_PTS, REF_MENTOR_DAYS, REF_MENTOR_CAP = 2, 30, 60     # passive: +2/round the friend plays (30 days, max 60)
REF_WEEKLY_TOP = 100                                          # Monday Top Recruiter prize
EXAM_CHECKIN_PTS = 25                                         # "నేను exam రాశాను" bonus


def _now():
    return datetime.now(config.IST)


def _load():
    return load_json(PATH, {"partners": {}, "offers": {}, "vouchers": {}, "ads": {"queue": [], "log": []},
                            "applications": [], "counter": 0})


def _save(d):
    save_json_atomic(PATH, d)


def _code(prefix, existing):
    alphabet = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
    while True:
        c = prefix + "-" + "".join(random.choice(alphabet) for _ in range(6))
        if c not in existing:
            return c


# ================================================================= partners
def add_partner(name, district, category, contact="", merchant_uid="", address="", note=""):
    d = _load()
    d["counter"] += 1
    pid = f"P{d['counter']:03d}"
    d["partners"][pid] = {"id": pid, "name": name.strip()[:40], "district": district, "category": category if category in CATEGORIES else "other",
                          "contact": contact, "merchant_uids": [str(merchant_uid)] if merchant_uid else [], "address": address,
                          "note": note, "active": True, "created": _now().isoformat(), "impressions": 0, "dm_impressions": 0}
    _save(d)
    return pid


def set_opening(pid, days=7):
    """Grand-opening package: 2× ad priority for `days`, card shows 🎉 NEW OPENING."""
    d = _load()
    p = d["partners"].get(pid)
    if not p:
        return False
    p["opening_until"] = (_now() + timedelta(days=int(days))).isoformat()
    _save(d)
    return True


def _is_opening(p, now=None):
    try:
        return bool(p.get("opening_until")) and datetime.fromisoformat(p["opening_until"]) >= (now or _now())
    except Exception:
        return False


def set_merchant(pid, uid):
    d = _load()
    p = d["partners"].get(pid)
    if not p:
        return False
    if str(uid) not in p["merchant_uids"]:
        p["merchant_uids"].append(str(uid))
    _save(d)
    return True


def add_offer(pid, title_te, title_en, pts, *, kind="discount", value="", exam="", exam_from="", exam_to="",
              per_member=1, total=0, expires_days=60, cta="", flash_hours=0):
    """kind: discount | freebie | examday (needs exam + window) | flash (stock + hours)."""
    d = _load()
    if pid not in d["partners"]:
        return None
    oid = _code("OF", d["offers"])
    d["offers"][oid] = {"id": oid, "partner": pid, "title_te": title_te[:80], "title_en": title_en[:80], "pts": int(pts),
                        "kind": kind, "value": value, "exam": exam.upper(), "exam_from": exam_from, "exam_to": exam_to,
                        "per_member": int(per_member), "total": int(total), "used": 0, "cta": cta,
                        "expires": (_now() + timedelta(days=int(expires_days))).isoformat(), "active": True,
                        "created": _now().isoformat(), "redemptions": 0}
    if flash_hours:
        d["offers"][oid]["kind"] = "flash"
        d["offers"][oid]["expires"] = (_now() + timedelta(hours=int(flash_hours))).isoformat()
    _save(d)
    return oid


def apply_partner(uid, text):
    """Merchant self-application via /partner apply <business · district · category · phone>."""
    d = _load()
    d["applications"].append({"uid": str(uid), "text": text[:300], "ts": _now().isoformat()})
    d["applications"] = d["applications"][-200:]
    _save(d)
    return ("✅ Application received — StudentUp team మీకు call చేస్తుంది.\n"
            "మీ ad మా channels + ఆ జిల్లా students DM లో వెళ్తుంది; students points తో మీ offer claim చేస్తారు.")


# ================================================================ eligibility
def _exam_ok(o, member, now):
    if o.get("kind") != "examday":
        return True, ""
    ex = (member.get("exam") or "").upper()
    if o.get("exam") and o["exam"] not in ex and ex not in o["exam"]:
        return False, f"ఈ offer {o['exam']} exam రాసేవాళ్ళకి"
    try:
        if o.get("exam_from") and now.date() < datetime.fromisoformat(o["exam_from"]).date():
            return False, f"Exam day ({o['exam_from'][:10]}) నుంచి unlock అవుతుంది"
        if o.get("exam_to") and now.date() > datetime.fromisoformat(o["exam_to"]).date():
            return False, "Exam window ముగిసింది"
    except Exception:
        pass
    if o.get("exam") and not exam_checked_in(member, o["exam"], o.get("exam_from", ""), o.get("exam_to", "")):
        return False, "exam రాశాక /examdone tap చేయండి → unlock"
    return True, ""


def exam_checked_in(member, exam, frm="", to=""):
    """True if member pressed 'నేను exam రాశాను' for this exam inside the window."""
    ci = (member.get("exam_checkins") or {}).get(exam.upper())
    if not ci:
        return False
    try:
        day = ci[:10]
        return (not frm or day >= frm[:10]) and (not to or day <= to[:10])
    except Exception:
        return False


def exam_checkin(members, uid, exam, now=None):
    """Student taps 'నేను exam రాశాను' → unlocks that exam's exam-day offers + bonus (once per exam per day)."""
    now = now or _now()
    m = members._get(str(uid))
    ci = m.setdefault("exam_checkins", {})
    today = now.date().isoformat()
    if (ci.get(exam.upper()) or "")[:10] == today:
        return False, "✅ ఇప్పటికే check-in అయ్యారు — /offers చూడండి"
    ci[exam.upper()] = now.isoformat()
    m["points"] = m.get("points", 0) + EXAM_CHECKIN_PTS
    m["exam_warrior"] = m.get("exam_warrior", 0) + 1
    members.kv.save()
    return True, (f"🏅 Exam Warrior! {exam.upper()} రాసినందుకు +{EXAM_CHECKIN_PTS} pts.\n"
                  f"మీ జిల్లా exam-day offers ఇప్పుడు unlock → /offers 🍽🎓")


def examday_prompts(members, now=None):
    """For every exam-day offer whose window includes today: (uid, exam, offers[]) for
    matching-exam members of that district who haven't checked in yet. Engine DMs them
    with a 'నేను exam రాశాను' button — the loop that turns exam halls into footfall."""
    now = now or _now()
    d = _load()
    today = now.date().isoformat()
    live = {}
    for o in d["offers"].values():
        p = d["partners"].get(o["partner"])
        if o.get("kind") != "examday" or not (o.get("active") and p and p.get("active")) or not o.get("exam"):
            continue
        if (o.get("exam_from") or today)[:10] <= today <= (o.get("exam_to") or today)[:10]:
            live.setdefault((o["exam"], p["district"]), []).append((o, p))
    out = []
    for uid, m in members.members.items():
        if not m.get("registered") or m.get("dm_blocked"):
            continue
        ex = (m.get("exam") or "").upper()
        for (exam, dist), offs in live.items():
            if dist not in (m.get("district"), "ALL"):
                continue
            if exam not in ex and ex not in exam:
                continue
            if exam_checked_in(m, exam, offs[0][0].get("exam_from", ""), offs[0][0].get("exam_to", "")):
                continue
            out.append((uid, exam, offs))
    return out


def examday_prompt_text(exam, offs):
    lines = [f"📝 ఈ రోజు {exam} exam రాశారా? All the best 💪", "",
             "రాశాక క్రింద tap చేయండి → +%d pts + మీ జిల్లా exam-day offers unlock:" % EXAM_CHECKIN_PTS]
    for o, p in offs[:5]:
        lines.append(f"• {CATEGORIES.get(p['category'], '🏪').split()[0]} {p['name']} — {o['title_te']} ({o['pts']} pts)")
    return "\n".join(lines)


def offers_for(members, uid, now=None, category=""):
    """Offers visible to this member: their district (+ 'ALL'), active, not exhausted."""
    now = now or _now()
    d = _load()
    m = members.members.get(str(uid)) or {}
    dist = m.get("district", "")
    out = []
    for o in d["offers"].values():
        if not o.get("active"):
            continue
        p = d["partners"].get(o["partner"])
        if not p or not p.get("active"):
            continue
        if p["district"] not in (dist, "ALL"):
            continue
        if category and p.get("category") != category:
            continue
        try:
            if datetime.fromisoformat(o["expires"]) < now:
                continue
        except Exception:
            pass
        if o.get("total") and o["used"] >= o["total"]:
            continue
        mine = sum(1 for v in d["vouchers"].values() if v["uid"] == str(uid) and v["offer"] == o["id"] and v["status"] in ("held", "used"))
        if mine >= o.get("per_member", 1):
            continue
        ok, why = _exam_ok(o, m, now)
        out.append((o, p, ok, why))
    out.sort(key=lambda x: (not x[2], x[0].get("kind") != "flash", x[0]["pts"]))
    return out


def _flash_tag(o, now=None):
    if o.get("kind") != "flash":
        return ""
    now = now or _now()
    try:
        left = datetime.fromisoformat(o["expires"]) - now
        hrs = max(0, int(left.total_seconds() // 3600)); mins = max(0, int(left.total_seconds() % 3600 // 60))
    except Exception:
        hrs, mins = 0, 0
    stock = f" · {o['total'] - o['used']} left" if o.get("total") else ""
    return f" ⚡ {hrs}h{mins:02d}m{stock}"


def render_offers(members, uid, rewards_balance, category=""):
    m = members.members.get(str(uid)) or {}
    rows = offers_for(members, uid, category=category)
    dist = m.get("district", "")
    if not rows:
        return (f"🏪 {dist or 'మీ జిల్లా'} లో partner offers ఇంకా లేవు.\n"
                "మీకు తెలిసిన shop / coaching / restaurant వాళ్ళకి చెప్పండి → bot లో /partner apply\n"
                "(వాళ్ళ ad మా channels లో + మీకు discount)")
    lines = [f"🏪 {dist} — Partner offers · మీ balance {rewards_balance} pts", ""]
    for o, p, ok, why in rows[:12]:
        cat = CATEGORIES.get(p["category"], "🏪").split()[0]
        lock = "✅" if ok and o["pts"] <= rewards_balance else "🔒"
        lines.append(f"{lock} {cat} {p['name']} — {o['title_te']} · {o['pts']} pts{_flash_tag(o)}" + (f"\n     ⏳ {why}" if why else ""))
    lines += ["", "Tap చేయడానికి buttons 👇 · filter: /offers food · coaching · shop · salon",
              "Exam-day offers: exam రాశాక /examdone → unlock"]
    return "\n".join(lines)


def offer_buttons(members, uid, rewards_balance, category=""):
    rows = []
    for o, p, ok, why in offers_for(members, uid, category=category)[:8]:
        can = ok and o["pts"] <= rewards_balance
        label = f"{'✅' if can else '🔒'} {p['name'][:14]} · {o['title_te'][:18]} · {o['pts']}"
        rows.append([(label, f"poffer:{o['id']}" if can else f"plocked:{o['pts'] if not ok else 0}")])
    return rows


# ================================================================ redeem/verify
def redeem(members, uid, oid, rewards_mod):
    """Hold points (through rewards ledger semantics) and issue PT- code."""
    try:
        d = _load()
        o = d["offers"].get(oid)
        m = members.members.get(str(uid)) or {}
        if not o or not m.get("registered"):
            return False, "Offer not found.", None
        p = d["partners"][o["partner"]]
        visible = {x[0]["id"]: (x[2], x[3]) for x in offers_for(members, uid)}
        if oid not in visible:
            return False, "ఈ offer మీ జిల్లాలో లేదు / already claim చేశారు.", None
        ok, why = visible[oid]
        if not ok:
            return False, f"⏳ {why}", None
        bal = rewards_mod.balance(members, uid)
        # partner vouchers also count as holds: reuse rewards ledger for the hold
        held_here = sum(v["pts"] for v in d["vouchers"].values() if v["uid"] == str(uid) and v["status"] == "held")
        if o["pts"] > bal["available"] - held_here:
            return False, f"ఇంకా {o['pts'] - (bal['available'] - held_here)} pts కావాలి — /quiz, /war ఆడండి!", None
        code = _code("PT", d["vouchers"])
        now = _now()
        exp = min(datetime.fromisoformat(o["expires"]), now + timedelta(days=VOUCHER_DAYS))
        if o.get("kind") == "examday" and o.get("exam_to"):
            try:
                exp = min(exp, datetime.fromisoformat(o["exam_to"]) + timedelta(days=3))
            except Exception:
                pass
        d["vouchers"][code] = {"code": code, "uid": str(uid), "name": m.get("name", ""), "district": m.get("district", ""),
                               "phone": m.get("phone", ""), "offer": oid, "partner": p["id"], "pts": o["pts"], "status": "held",
                               "created": now.isoformat(), "expires": exp.isoformat()}
        o["used"] += 1
        _save(d)
        text = "\n".join([
            f"🎟 {p['name']} — VOUCHER",
            f"Code: `{code}`",
            f"🎁 {o['title_te']}",
            f"   {o['title_en']}",
            f"⭐ {o['pts']} pts held · valid till {exp.strftime('%d %b')}",
            f"📍 {p['district']}" + (f" · {p['address']}" if p.get("address") else "") + (f" · 📞 {p['contact']}" if p.get("contact") else ""),
            (f"ℹ️ {o['cta']}" if o.get("cta") else ""),
            "",
            "Counter లో ఈ code చూపించండి — shop verify చేశాకే points deduct. Cancel: /pcancel " + code,
        ])
        merchant_msg = (f"🎟 StudentUp voucher {code}\n{m.get('name', '')} · {m.get('district', '')}\n{o['title_en']}\n"
                        f"At counter reply: /pverify {code}")
        return True, text, (p.get("merchant_uids", []), merchant_msg)
    except Exception as e:
        print(f"   [partners] redeem {e}")
        return False, "Redeem failed — try again.", None


def held_points(uid):
    d = _load()
    return sum(v["pts"] for v in d["vouchers"].values() if v["uid"] == str(uid) and v["status"] == "held")


def cancel(uid, code):
    d = _load()
    v = d["vouchers"].get(code.upper().strip())
    if not v or v["uid"] != str(uid):
        return "Voucher not found."
    if v["status"] != "held":
        return f"Already {v['status']}."
    v["status"] = "cancelled"; v["closed"] = _now().isoformat()
    o = d["offers"].get(v["offer"])
    if o:
        o["used"] = max(0, o["used"] - 1)
    _save(d)
    return f"✅ {code} cancelled — {v['pts']} pts released."


def verify(members, code, by_uid, staff_ids):
    """Merchant (authorised per partner) or staff marks USED → points burn."""
    try:
        d = _load()
        v = d["vouchers"].get(code.upper().strip())
        if not v:
            return f"❌ {code}: not found"
        p = d["partners"].get(v["partner"], {})
        if str(by_uid) not in p.get("merchant_uids", []) and str(by_uid) not in staff_ids:
            return "🔒 ఈ voucher verify చేయడానికి ఈ shop merchant / StudentUp staff మాత్రమే."
        if v["status"] == "used":
            return f"⚠️ {code}: already USED {v.get('closed', '')[:16]} — do NOT honour again"
        if v["status"] != "held":
            return f"❌ {code}: {v['status']}"
        if datetime.fromisoformat(v["expires"]) < _now():
            v["status"] = "expired"; _save(d)
            return f"❌ {code}: expired"
        m = members._get(v["uid"])
        m["points"] = max(0, m.get("points", 0) - v["pts"])
        m["points_redeemed"] = m.get("points_redeemed", 0) + v["pts"]
        m["partner_redemptions"] = m.get("partner_redemptions", 0) + 1
        members.kv.save()
        v["status"] = "used"; v["closed"] = _now().isoformat(); v["by"] = str(by_uid)
        o = d["offers"].get(v["offer"])
        if o:
            o["redemptions"] = o.get("redemptions", 0) + 1
        _save(d)
        return (f"✅ VERIFIED {code}\n👤 {v['name']} · {v['district']}\n🎁 {(o or {}).get('title_en', '')}\n"
                f"⭐ {v['pts']} pts deducted. Thank you for supporting students 🙏")
    except Exception as e:
        return f"verify error: {e}"


def expire_stale(now=None):
    now = now or _now()
    d = _load()
    n = 0
    for v in d["vouchers"].values():
        if v["status"] == "held" and datetime.fromisoformat(v["expires"]) < now:
            v["status"] = "expired"; v["closed"] = now.isoformat(); n += 1
            o = d["offers"].get(v["offer"])
            if o:
                o["used"] = max(0, o["used"] - 1)
    if n:
        _save(d)
    return n


# ==================================================================== ads
def ad_card(p, o, cfg=None):
    from . import districts as D
    head = f"{cfg['emoji']} " if cfg else ""
    cat = CATEGORIES.get(p["category"], "🏪")
    lines = [f"{head}🤝 StudentUp Partner — {p['district']} ({D.telugu_name(p['district'])})"]
    if _is_opening(p):
        lines.append(f"🎉 NEW OPENING in {p['district']}! Students కి launch offer 👇")
    lines += [f"{cat}: {p['name']}", "",
             f"🎁 {o['title_te']}", f"   {o['title_en']}",
             f"⭐ Claim with {o['pts']} points → bot లో /offers"]
    if o.get("kind") == "flash":
        lines.append(f"⚡ FLASH DEAL —{_flash_tag(o)} · first come first served")
    if o.get("kind") == "examday":
        lines.append(f"📅 {o['exam']} exam day special ({o.get('exam_from', '')[:10]} → {o.get('exam_to', '')[:10]}) — exam రాసి వచ్చి claim చేయండి")
    if p.get("address"):
        lines.append(f"📍 {p['address']}")
    if p.get("contact"):
        lines.append(f"📞 {p['contact']}")
    if o.get("cta"):
        lines.append(f"ℹ️ {o['cta']}")
    lines += ["", "మీ business కి కూడా students కావాలా? → bot లో /partner apply"]
    return "\n".join(lines)


def next_ad(now=None):
    """Round-robin over active offers (least recently shown first)."""
    now = now or _now()
    d = _load()
    cands = []
    for o in d["offers"].values():
        p = d["partners"].get(o["partner"])
        if not (o.get("active") and p and p.get("active")):
            continue
        try:
            if datetime.fromisoformat(o["expires"]) < now:
                continue
        except Exception:
            pass
        # flash first; then openings get shown as if they were shown half as recently (≈2× frequency)
        ls = o.get("last_shown", "")
        if _is_opening(p, now) and ls:
            try:
                ls = (datetime.fromisoformat(ls) - (now - datetime.fromisoformat(ls))).isoformat()
            except Exception:
                pass
        cands.append(((o.get("kind") != "flash", ls), o, p))
    if not cands:
        return None, None
    cands.sort(key=lambda x: x[0])
    _, o, p = cands[0]
    o["last_shown"] = now.isoformat()
    p["impressions"] = p.get("impressions", 0) + 1
    d["ads"]["log"].append({"ts": now.isoformat(), "offer": o["id"], "partner": p["id"]})
    d["ads"]["log"] = d["ads"]["log"][-1000:]
    _save(d)
    return o, p


def district_targets(members, district, limit=500):
    """Members of that district who have not opted out of partner DMs."""
    out = []
    for uid, m in members.members.items():
        if m.get("registered") and not m.get("dm_blocked") and not m.get("no_ads") and m.get("district") == district:
            out.append(uid)
    return out[:limit]


def mark_dm_impressions(pid, n):
    d = _load()
    p = d["partners"].get(pid)
    if p:
        p["dm_impressions"] = p.get("dm_impressions", 0) + n
        _save(d)


# ================================================================ analytics
def partner_stats(pid):
    d = _load()
    p = d["partners"].get(pid)
    if not p:
        return "Partner not found."
    offers = [o for o in d["offers"].values() if o["partner"] == pid]
    vs = [v for v in d["vouchers"].values() if v["partner"] == pid]
    used = [v for v in vs if v["status"] == "used"]
    uniq = len({v["uid"] for v in vs})
    lines = [f"📈 {p['name']} ({p['id']}) · {p['district']} · {CATEGORIES.get(p['category'], '')}",
             f"📣 Channel posts: {p.get('impressions', 0)} · DM reach: {p.get('dm_impressions', 0)}",
             f"🎟 Vouchers: {len(vs)} issued · {len(used)} redeemed · {uniq} unique students",
             f"⭐ Points value redeemed: {sum(v['pts'] for v in used)}", ""]
    for o in offers:
        lines.append(f"• {o['id']} {o['title_en'][:40]} — {o['pts']} pts · {o.get('redemptions', 0)} redeemed · "
                     f"{'active' if o.get('active') else 'off'} · till {o['expires'][:10]}")
    return "\n".join(lines)


def partners_of_merchant(uid):
    d = _load()
    return [p for p in d["partners"].values() if str(uid) in p.get("merchant_uids", [])]


def merchant_dashboard(uid):
    """/mystats for a merchant: their partners' stats + pending vouchers list."""
    ps = partners_of_merchant(uid)
    if not ps:
        return "🔒 మీరు ఏ partner కి merchant కాదు. Business owner? → /partner apply"
    d = _load()
    out = []
    for p in ps:
        out.append(partner_stats(p["id"]))
        held = [v for v in d["vouchers"].values() if v["partner"] == p["id"] and v["status"] == "held"]
        if held:
            out.append(f"🎟 Pending vouchers ({len(held)}) — counter లో /pverify CODE:")
            out += [f"  {v['code']} · {v['name']} · {v['created'][:10]}" for v in held[-10:]]
    out.append("\n📅 ప్రతి సోమవారం report automatic గా వస్తుంది.")
    return "\n".join(out)


def weekly_merchant_reports():
    """(merchant_uid, text) for every active partner — Monday DM."""
    d = _load()
    out = []
    for p in d["partners"].values():
        if not p.get("active"):
            continue
        txt = "📊 StudentUp weekly partner report\n" + partner_stats(p["id"]) + "\n\nకొత్త offer / flash deal కావాలంటే StudentUp team కి చెప్పండి 🙏"
        for mu in p.get("merchant_uids", []):
            out.append((mu, txt))
    return out


def list_partners():
    d = _load()
    if not d["partners"]:
        return "No partners yet. /partner add <name> | <district> | <category> | <phone> | <merchant_uid>"
    lines = ["🤝 Partners:"]
    for p in d["partners"].values():
        n_off = sum(1 for o in d["offers"].values() if o["partner"] == p["id"] and o.get("active"))
        lines.append(f"{p['id']} {p['name']} · {p['district']} · {p['category']} · {n_off} offers · {'✅' if p['active'] else '⛔'}")
    if d["applications"]:
        lines += ["", f"📥 {len(d['applications'])} applications pending:"]
        for a in d["applications"][-5:]:
            lines.append(f"  {a['uid']}: {a['text'][:60]}")
    return "\n".join(lines)


def toggle_partner(pid, active):
    d = _load()
    p = d["partners"].get(pid)
    if not p:
        return False
    p["active"] = bool(active); _save(d)
    return True


# ============================================================ smart referral
def on_round_played(members, uid):
    """Call after a member finishes a round: activates the referral once they
    have played REF_ACTIVATE_ROUNDS within REF_ACTIVATE_DAYS of registering."""
    try:
        m = members.members.get(str(uid)) or {}
        ref = m.get("referred_by")
        if not ref:
            return None
        m["_ref_rounds"] = m.get("_ref_rounds", 0) + 1
        try:
            reg = datetime.fromisoformat(m.get("registered_at") or "")
            age = (_now() - reg).days
        except Exception:
            age = 0
        fresh = age <= REF_ACTIVATE_DAYS
        # passive mentor share: every round the friend plays in first 30 days → +2 to the referrer (cap 60)
        if age <= REF_MENTOR_DAYS and m.get("_mentor_paid", 0) < REF_MENTOR_CAP:
            r = members._get(ref)
            r["points"] = r.get("points", 0) + REF_MENTOR_PTS
            r["mentor_points"] = r.get("mentor_points", 0) + REF_MENTOR_PTS
            m["_mentor_paid"] = m.get("_mentor_paid", 0) + REF_MENTOR_PTS
        if m.get("_ref_activated"):
            members.kv.save()
            return None
        if m["_ref_rounds"] >= REF_ACTIVATE_ROUNDS and fresh:
            m["_ref_activated"] = True
            r = members._get(ref)
            r["points"] = r.get("points", 0) + REF_ACTIVATED
            r["ref_activated"] = r.get("ref_activated", 0) + 1
            r["ref_week"] = r.get("ref_week", 0) + 1
            bonus = REF_ACTIVATED
            ms = REF_MILESTONES.get(r["ref_activated"])
            if ms:
                r["points"] += ms
                bonus += ms
            members.kv.save()
            return {"referrer": ref, "bonus": bonus, "activated": r["ref_activated"],
                    "name": m.get("name", "friend")}
        members.kv.save()
        return None
    except Exception as e:
        print(f"   [referral] {e}")
        return None


def weekly_top_recruiters(members, top=5):
    """Monday: rank by activated referrals this week, prize the winner, reset counters.
    Returns (text or None, winner_uid or None)."""
    from . import districts as D
    rows = []
    for uid, m in members.members.items():
        if m.get("ref_week", 0) > 0:
            rows.append((m["ref_week"], m.get("ref_activated", 0), m.get("name") or m.get("username") or "?", m.get("district", ""), uid))
    if not rows:
        return None, None
    rows.sort(reverse=True)
    win = rows[0]
    w = members._get(win[4])
    w["points"] = w.get("points", 0) + REF_WEEKLY_TOP
    w["top_recruiter_wins"] = w.get("top_recruiter_wins", 0) + 1
    for uid, m in members.members.items():
        if m.get("ref_week"):
            m["ref_week"] = 0
    members.kv.save()
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    lines = ["🏆 TOP RECRUITERS of the week", ""]
    for i, (wk, tot, name, dist, _) in enumerate(rows[:top]):
        lines.append(f"{medals[i]} {name} · {D.telugu_name(dist) if dist else ''} — {wk} active friends this week (total {tot})")
    lines += ["", f"🎁 {win[2]} కి +{REF_WEEKLY_TOP} pts! మీరూ friends ని తీసుకురండి → bot లో /invite"]
    return "\n".join(lines), win[4]


def referral_explainer(uid, link):
    return "\n".join([
        "🎁 Smart Referral — friends ని తీసుకురండి, ఎక్కువ సంపాదించండి",
        f"• Friend register అయితే: +{REF_BASE} pts",
        f"• ఆ friend 7 రోజుల్లో 3 rounds ఆడితే: ఇంకా +{REF_ACTIVATED} (activated)",
        f"• Mentor share: friend ఆడిన ప్రతి round కి +{REF_MENTOR_PTS} (30 రోజులు, max {REF_MENTOR_CAP}/friend)",
        f"• 5 activated → +{REF_MILESTONES[5]} · 10 → +{REF_MILESTONES[10]} · 25 → +{REF_MILESTONES[25]} 🥇 Ambassador",
        f"• ప్రతి సోమవారం Top Recruiter → channel spotlight + {REF_WEEKLY_TOP} pts",
        "",
        "Points తో: application discounts · study materials · మీ జిల్లా shops/coaching/restaurant offers (/offers)",
        "", f"మీ link: {link}",
    ])
