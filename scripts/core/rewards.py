"""
Points Wallet + Redemption at the StudentUp Internet Centre.

Points earned in quizzes become REAL discounts on services the centre already
does for students (application filing, document upload, print/scan, photo,
exam-form filling, hall-ticket download, etc.).

Flow
----
  /wallet        → balance, value in ₹, what they can redeem now, next unlock
  /redeem        → list of offers as buttons
  tap offer      → holds the points, creates a one-time CODE (e.g. SU-7K4Q2M),
                   sends the member a voucher (code + what + validity + centre
                   details) and notifies the admin
  centre staff   → member shows the code; staff (admin in Telegram) sends
                   /verify SU-7K4Q2M  → bot confirms member name/district/offer,
                   marks it USED (points now finally deducted) — or /cancel CODE
                   to release the hold.
  expiry         → unused vouchers auto-expire after VOUCHER_DAYS and the
                   points return to the member.

Design rules
  * points are HELD at redemption and BURNED only at /verify → no double spend,
    cancel is free.
  * every voucher has a unique code; admin verification is the only way to
    mark USED → staff at the counter is the source of truth.
  * catalogue lives in data/rewards_catalog.json (edit prices/offers freely,
    hot-reloaded); ledger in data/wallet_ledger.json.
  * nothing here raises into bot/engine — all public functions are guarded.
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

CATALOG_PATH = config.DATA / "rewards_catalog.json"
LEDGER_PATH = config.DATA / "wallet_ledger.json"
VOUCHER_DAYS = int(getattr(config, "VOUCHER_DAYS", 30) or 30)
POINT_VALUE_PAISE = int(getattr(config, "POINT_VALUE_PAISE", 10) or 10)   # 100 pts = ₹10

DEFAULT_CATALOG = {
    "centre": {
        "name": "StudentUp Internet Centre",
        "address": "(set in data/rewards_catalog.json)",
        "phone": "",
        "hours": "9 AM – 9 PM",
        "note": "Applications call చేసి documents పంపితే మేమే file చేసి పెడతాం — voucher code చెప్పండి చాలు.",
    },
    # Two categories only: exam APPLICATION discounts (redeemed at the centre)
    # and STUDY MATERIALS (delivered as files by the bot, or collected at the centre).
    "offers": [
        # ---- 📝 Applications (type=application → counter /verify) ----
        {"id": "app20", "cat": "application", "pts": 150, "rupees": 20,
         "title_en": "₹20 OFF any exam application filing",
         "title_te": "ఏ exam application filing పైనైనా ₹20 తగ్గింపు"},
        {"id": "app50", "cat": "application", "pts": 350, "rupees": 50,
         "title_en": "₹50 OFF any exam application filing",
         "title_te": "ఏ exam application filing పైనైనా ₹50 తగ్గింపు"},
        {"id": "appfree", "cat": "application", "pts": 700,
         "title_en": "1 exam application filing FREE (exam fee extra)",
         "title_te": "ఒక exam application filing పూర్తిగా ఫ్రీ (exam fee వేరు)"},
        {"id": "app3", "cat": "application", "pts": 1500,
         "title_en": "3 application filings FREE + priority handling for 1 month",
         "title_te": "3 application filings ఫ్రీ + నెల రోజులు priority service"},
        # ---- 📚 Study materials (type=material → bot sends file / centre hands over) ----
        {"id": "mat_ca", "cat": "material", "pts": 100, "file": "monthly_current_affairs_te.pdf",
         "title_en": "Monthly Current Affairs PDF (Telugu + English)",
         "title_te": "నెల Current Affairs PDF (తెలుగు + English)"},
        {"id": "mat_pyq", "cat": "material", "pts": 200, "file": "pyq_pack_{exam}.pdf",
         "title_en": "Previous-year questions pack for YOUR exam (topic-wise, with keys)",
         "title_te": "మీ exam PYQ pack (topic-wise, keys తో)"},
        {"id": "mat_missed", "cat": "material", "pts": 250, "file": "most_missed_{exam}.pdf",
         "title_en": "Most-missed 100 questions + explanations (from our rounds)",
         "title_te": "ఎక్కువ మంది తప్పు చేసిన 100 ప్రశ్నలు + వివరణలు"},
        {"id": "mat_print", "cat": "material", "pts": 500, "at_centre": True,
         "title_en": "Printed material set for your exam — collect at the centre",
         "title_te": "మీ exam printed material set — centre లో తీసుకోండి"},
    ],
}


# ------------------------------------------------------------------ storage
def catalog() -> dict:
    c = load_json(CATALOG_PATH, None)
    if not c:
        save_json_atomic(CATALOG_PATH, DEFAULT_CATALOG)
        c = DEFAULT_CATALOG
    return c


def _ledger() -> dict:
    return load_json(LEDGER_PATH, {"vouchers": {}, "counter": 0})


def _save(led):
    save_json_atomic(LEDGER_PATH, led)


def _code(led) -> str:
    alphabet = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
    while True:
        c = "SU-" + "".join(random.choice(alphabet) for _ in range(6))
        if c not in led["vouchers"]:
            return c


# ------------------------------------------------------------------ balance
def held_points(led, uid) -> int:
    return sum(v["pts"] for v in led["vouchers"].values()
               if v["uid"] == str(uid) and v["status"] == "held")


def balance(members, uid) -> dict:
    m = members.members.get(str(uid)) or {}
    led = _ledger()
    pts = int(m.get("points", 0))
    held = held_points(led, uid)
    return {"points": pts, "held": held, "available": max(0, pts - held),
            "rupees": (max(0, pts - held) * POINT_VALUE_PAISE) // 100,
            "redeemed": m.get("points_redeemed", 0)}


def render_wallet(members, uid) -> str:
    try:
        m = members.members.get(str(uid)) or {}
        if not m.get("registered"):
            return "👛 Wallet కోసం ముందు register అవ్వండి — /start"
        b = balance(members, uid)
        cat = catalog()
        offers = sorted(cat["offers"], key=lambda o: o["pts"])
        can = [o for o in offers if o["pts"] <= b["available"]]
        nxt = next((o for o in offers if o["pts"] > b["available"]), None)
        lines = [f"👛 {m.get('name', 'Player')} — Points Wallet",
                 f"⭐ Balance: {b['available']} pts" + (f" (+{b['held']} held in vouchers)" if b['held'] else ""),
                 f"💰 Value: ≈ ₹{b['rupees']} at {cat['centre']['name']}",
                 f"🎟 Redeemed so far: {b['redeemed']} pts", ""]
        if can:
            lines.append("✅ మీరు ఇప్పుడు తీసుకోగలిగేవి / You can redeem now:")
            for o in [x for x in can if x.get("cat") == "application"][-2:]:
                lines.append(f"  📝 {o['title_te']} — {o['pts']} pts")
            for o in [x for x in can if x.get("cat") == "material"][-2:]:
                lines.append(f"  📚 {o['title_te']} — {o['pts']} pts")
        if nxt:
            need = nxt["pts"] - b["available"]
            lines.append(f"🔓 Next unlock: {nxt['title_te']} — ఇంకా {need} pts (≈ {max(1, -(-need // 10))} correct answers)")
        led = _ledger()
        mine = [v for v in led["vouchers"].values() if v["uid"] == str(uid) and v["status"] == "held"]
        if mine:
            lines.append("")
            lines.append("🎟 Active vouchers:")
            for v in mine:
                lines.append(f"  {v['code']} — {v['title_te']} · valid till {v['expires'][:10]}")
        lines += ["", "/redeem — offers · points ఎలా వస్తాయి: ✅ +10 · podium +30/20/10 · Grand Test ×2 · War/Battle wins · referral +20",
                  f"📍 {cat['centre']['name']} · {cat['centre']['address']}" +
                  (f" · 📞 {cat['centre']['phone']}" if cat['centre'].get('phone') else "")]
        return "\n".join(lines)
    except Exception as e:
        print(f"   [wallet] {e}")
        return "👛 Wallet temporarily unavailable — try again shortly."


# ---------------------------------------------------------------- redeeming
def offer_buttons(members, uid):
    """Inline keyboard rows: affordable offers first (✅), others greyed with lock."""
    b = balance(members, uid)
    rows = []
    for o in sorted(catalog()["offers"], key=lambda x: x["pts"]):
        ok = o["pts"] <= b["available"]
        icon = "📝" if o.get("cat") == "application" else "📚"
        label = f"{'✅' if ok else '🔒'}{icon} {o['title_te'][:26]} · {o['pts']}"
        rows.append([(label, f"redeem:{o['id']}" if ok else f"locked:{o['pts']}")])
    return rows


def redeem(members, uid, offer_id: str, when=None):
    """Create a HELD voucher. Returns (ok, text_for_member, admin_text)."""
    try:
        m = members.members.get(str(uid)) or {}
        if not m.get("registered"):
            return False, "ముందు register అవ్వండి — /start", None
        cat = catalog()
        o = next((x for x in cat["offers"] if x["id"] == offer_id), None)
        if not o:
            return False, "Offer not found.", None
        b = balance(members, uid)
        if o["pts"] > b["available"]:
            return False, f"ఇంకా {o['pts'] - b['available']} pts కావాలి. /quiz ఆడండి!", None
        led = _ledger()
        now = when or datetime.now(config.IST)
        code = _code(led)
        led["counter"] += 1
        v = {"code": code, "uid": str(uid), "name": m.get("name", ""), "district": m.get("district", ""),
             "phone": m.get("phone", ""), "offer": o["id"], "title_te": o["title_te"], "title_en": o["title_en"],
             "pts": o["pts"], "status": "held", "created": now.isoformat(),
             "expires": (now + timedelta(days=VOUCHER_DAYS)).isoformat()}
        led["vouchers"][code] = v
        _save(led)
        c = cat["centre"]
        text = "\n".join([
            "🎟 VOUCHER CREATED — వోచర్ సిద్ధం",
            f"Code: `{code}`",
            f"🎁 {o['title_te']}",
            f"   {o['title_en']}",
            f"⭐ {o['pts']} pts held · valid till {v['expires'][:10]}",
            "",
            f"📍 {c['name']} · {c['address']}" + (f" · 📞 {c['phone']}" if c.get("phone") else ""),
            f"🕘 {c.get('hours', '')}",
            f"ℹ️ {c.get('note', '')}",
            "",
            "Counter లో ఈ code చెప్పండి (లేదా call/WhatsApp లో పంపండి). Staff verify చేశాకే points deduct అవుతాయి.",
            "Cancel చేయాలంటే: /cancel " + code,
        ])
        admin = (f"🎟 New voucher {code}\n{v['name']} · {v['district']} · {v['phone'] or 'no phone'}\n"
                 f"{o['title_en']} · {o['pts']} pts\nVerify at counter: /verify {code}")
        return True, text, admin
    except Exception as e:
        print(f"   [redeem] {e}")
        return False, "Redeem failed — try again.", None


MATERIALS_DIR = config.DATA / "materials"


def material_file(offer: dict, member: dict):
    """Resolve the PDF for a material offer ({exam} → member's exam). Returns
    (path or None, filename)."""
    name = (offer.get("file") or "").format(exam=(member.get("exam") or "general").lower().replace(" ", "_"))
    if not name:
        return None, ""
    p = MATERIALS_DIR / name
    if not p.exists():                       # generic fallback
        g = MATERIALS_DIR / name.replace(f"_{(member.get('exam') or 'general').lower()}", "_general")
        p = g if g.exists() else None
    return p, name


def deliver_material(members, uid, code: str):
    """For material vouchers: burn points now and return (file_path|None, note).
    If the file is missing, voucher stays HELD for collection at the centre."""
    led = _ledger()
    v = led["vouchers"].get(code)
    if not v or v["uid"] != str(uid) or v["status"] != "held":
        return None, ""
    cat = catalog()
    o = next((x for x in cat["offers"] if x["id"] == v["offer"]), {})
    m = members._get(uid)
    if o.get("at_centre"):
        return None, "📚 ఈ material centre లో ఇస్తాం — code చెప్పి తీసుకోండి. Staff verify చేశాకే points deduct."
    path, fname = material_file(o, m)
    if not path:
        return None, ("📚 ఈ file ఇంకా upload అవ్వలేదు — voucher active గా ఉంది, ready అయిన వెంటనే bot పంపుతుంది "
                      "(లేదా centre లో తీసుకోండి).")
    m["points"] = max(0, m.get("points", 0) - v["pts"])
    m["points_redeemed"] = m.get("points_redeemed", 0) + v["pts"]
    m["redemptions"] = m.get("redemptions", 0) + 1
    members.kv.save()
    v["status"] = "used"; v["closed"] = datetime.now(config.IST).isoformat(); v["staff"] = "bot"
    _save(led)
    return path, f"📚 {o.get('title_te', '')}\n⭐ {v['pts']} pts deducted · balance {m['points']}. All the best! 📖"


def cancel(members, uid, code: str) -> str:
    led = _ledger()
    v = led["vouchers"].get(code.upper().strip())
    if not v or v["uid"] != str(uid):
        return "Voucher not found."
    if v["status"] != "held":
        return f"Voucher already {v['status']}."
    v["status"] = "cancelled"
    v["closed"] = datetime.now(config.IST).isoformat()
    _save(led)
    return f"✅ {code} cancelled — {v['pts']} pts released back to your wallet."


def verify(members, code: str, staff_uid=None) -> str:
    """ADMIN/STAFF: mark voucher USED and burn the points. Idempotent."""
    try:
        led = _ledger()
        v = led["vouchers"].get(code.upper().strip())
        if not v:
            return f"❌ {code}: not found"
        if v["status"] == "used":
            return f"⚠️ {code}: already USED on {v.get('closed', '')[:16]} — do NOT honour again"
        if v["status"] != "held":
            return f"❌ {code}: {v['status']}"
        if datetime.fromisoformat(v["expires"]) < datetime.now(config.IST):
            v["status"] = "expired"; _save(led)
            return f"❌ {code}: expired on {v['expires'][:10]}"
        m = members._get(v["uid"])
        m["points"] = max(0, m.get("points", 0) - v["pts"])
        m["points_redeemed"] = m.get("points_redeemed", 0) + v["pts"]
        m["redemptions"] = m.get("redemptions", 0) + 1
        members.kv.save()
        v["status"] = "used"; v["closed"] = datetime.now(config.IST).isoformat()
        v["staff"] = str(staff_uid or "")
        _save(led)
        return (f"✅ VERIFIED {code}\n👤 {v['name']} · {v['district']} · {v['phone'] or '—'}\n"
                f"🎁 {v['title_en']}\n⭐ {v['pts']} pts deducted · balance now {m['points']}")
    except Exception as e:
        return f"verify error: {e}"


def expire_stale(members, now=None) -> int:
    """Daily: release points of expired vouchers (they were only held)."""
    now = now or datetime.now(config.IST)
    led = _ledger()
    n = 0
    for v in led["vouchers"].values():
        if v["status"] == "held" and datetime.fromisoformat(v["expires"]) < now:
            v["status"] = "expired"; v["closed"] = now.isoformat(); n += 1
    if n:
        _save(led)
    return n


def member_voucher_note(members, uid, code) -> str | None:
    led = _ledger()
    v = led["vouchers"].get(code)
    if not v or v["uid"] != str(uid):
        return None
    return (f"✅ Voucher {code} used — {v['title_te']}. Thank you! 🙏\n"
            f"⭐ {v['pts']} pts deducted. మళ్ళీ points సంపాదించండి → /quiz")


def admin_summary() -> str:
    led = _ledger()
    vs = list(led["vouchers"].values())
    if not vs:
        return "🎟 No vouchers yet."
    by = {}
    for v in vs:
        by[v["status"]] = by.get(v["status"], 0) + 1
    used_pts = sum(v["pts"] for v in vs if v["status"] == "used")
    top = {}
    for v in vs:
        if v["status"] == "used":
            top[v["title_en"]] = top.get(v["title_en"], 0) + 1
    lines = ["🎟 Rewards summary", " · ".join(f"{k} {n}" for k, n in by.items()),
             f"⭐ Points burned: {used_pts} (≈ ₹{used_pts * POINT_VALUE_PAISE // 100} value given)"]
    if top:
        lines.append("Top offers: " + " · ".join(f"{t} ×{n}" for t, n in sorted(top.items(), key=lambda kv: -kv[1])[:3]))
    return "\n".join(lines)


# ------------------------------------------------- channel promo (occasional)
def promo_text(cfg=None) -> str:
    cat = catalog()
    apps = sorted([o for o in cat["offers"] if o.get("cat") == "application"], key=lambda o: o["pts"])[:2]
    mats = sorted([o for o in cat["offers"] if o.get("cat") == "material"], key=lambda o: o["pts"])[:2]
    head = f"{cfg['emoji']} " if cfg else ""
    lines = [f"{head}👛 మీ quiz points = application discounts + study materials",
             "ప్రతి ✅ answer = points. Points తో:", ""]
    for o in apps:
        lines.append(f"  📝 {o['title_te']} — {o['pts']} pts")
    for o in mats:
        lines.append(f"  📚 {o['title_te']} — {o['pts']} pts")
    lines += ["", "Applications కోసం call చేసి documents పంపండి — మేమే file చేస్తాం, code చెబితే discount 🎟",
              "Bot లో /wallet → balance · /redeem → voucher"]
    return "\n".join(lines)
