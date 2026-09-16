"""
OWNER HQ — one screen to run the whole platform, with buttons.

/hq  →  📊 today (new members, active, rounds, answers, wars, redemptions)
        📈 growth 7d / 30d, top districts, top colleges, referral funnel
        🏪 partners: active, vouchers pending, top partner
        ⚠️ alerts: low question stock per channel, scraping sources failing, bot DM blocks,
                   events stuck open, members never verified join
        buttons: 🎓 Campus panel · 🏪 Partners · 📣 Post digest now · 🔔 Nudge join ·
                 📤 Export CSV · 🧾 Sheet sync · ⚔️ War status · 🔁 Refresh

Morning brief (08:00) = the same card DMed to STAFF_IDS, only when something changed
or an alert exists — so you never open a dashboard unless you want to.

College Manager: every college that ever ran an event is a CLUB
  /college            → list of clubs with members, active this week, leader
  /college <name>     → club card: members, activity, last event, leader, next actions
  leader = the student who topped the last event (auto) or set by /college lead <name> | <uid>
  next-day follow-up is automatic (campus drip); from the club card you can:
     🔁 Re-run event (creates a new /go with same college) · 📢 Message all members ·
     🏆 Post club board · 👑 Make top scorer the leader
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "hq.json"
LOW_STOCK = 60          # unused questions per channel below which we alert


def _now():
    return datetime.now(config.IST)


def _day(dt=None):
    return (dt or _now()).strftime("%Y-%m-%d")


# ================================================================== metrics
def metrics(members, bank=None):
    now = _now()
    today, y7, y30 = _day(), _day(now - timedelta(days=7)), _day(now - timedelta(days=30))
    ms = members.members
    reg = [m for m in ms.values() if m.get("registered")]
    out = {
        "members": len(reg),
        "new_today": sum(1 for m in reg if (m.get("registered_at") or "")[:10] == today),
        "new_7d": sum(1 for m in reg if (m.get("registered_at") or "")[:10] >= y7),
        "new_30d": sum(1 for m in reg if (m.get("registered_at") or "")[:10] >= y30),
        "active_today": sum(1 for m in reg if m.get("last_active") == today),
        "active_7d": sum(1 for m in reg if (m.get("last_active") or "") >= y7),
        "blocked": sum(1 for m in reg if m.get("dm_blocked")),
        "joined_hub": sum(1 for m in reg if (m.get("joined_channels") or {}).get("CURRENT")),
        "referrals": sum(m.get("referrals", 0) for m in reg),
        "ref_activated": sum(m.get("ref_activated", 0) for m in reg),
        "colleges": len({m.get("college") for m in reg if m.get("college")}),
        "campus_members": sum(1 for m in reg if m.get("college")),
    }
    # rounds today
    rounds = members.data.get("rounds", {}) if hasattr(members, "data") else {}
    tag = today.replace("-", "")
    r_today = [r for rid, r in rounds.items() if rid.startswith(tag)]
    out["rounds_today"] = len(r_today)
    out["answers_today"] = sum(e.get("total", 0) for r in r_today for ch in r.get("by_channel", {}).values() for e in ch.values())
    out["players_today"] = len({u for r in r_today for ch in r.get("by_channel", {}).values() for u in ch})
    # districts / colleges
    dist = {}
    for m in reg:
        if m.get("district"):
            dist[m["district"]] = dist.get(m["district"], 0) + 1
    out["top_districts"] = sorted(dist.items(), key=lambda x: -x[1])[:5]
    col = {}
    for m in reg:
        if m.get("college"):
            col[m["college"]] = col.get(m["college"], 0) + 1
    out["top_colleges"] = sorted(col.items(), key=lambda x: -x[1])[:5]
    # partners
    try:
        from . import partners as P
        d = P._load()
        out["partners"] = sum(1 for p in d["partners"].values() if p.get("active"))
        out["offers"] = sum(1 for o in d["offers"].values() if o.get("active"))
        vs = list(d["vouchers"].values())
        out["vouchers_held"] = sum(1 for v in vs if v["status"] == "held")
        out["vouchers_used_7d"] = sum(1 for v in vs if v["status"] == "used" and (v.get("closed") or "")[:10] >= y7)
        out["applications"] = len(d.get("applications", []))
    except Exception:
        out.update(partners=0, offers=0, vouchers_held=0, vouchers_used_7d=0, applications=0)
    # rewards (centre)
    try:
        from . import rewards as R
        led = R._ledger()
        out["centre_pending"] = sum(1 for v in led["vouchers"].values() if v["status"] == "held")
    except Exception:
        out["centre_pending"] = 0
    # question stock
    stock = {}
    if bank is not None:
        for ch in getattr(config, "PUBLIC_CHANNELS", []):
            try:
                stock[ch] = len(bank.unused(ch))
            except Exception:
                stock[ch] = -1
    out["stock"] = stock
    # war
    try:
        from . import districtwar as W
        d = W._load()
        live = d.get("live") or {}
        out["war"] = live.get("state", "none")
        out["war_fighters"] = sum(1 for f in live.get("fighters", {}).values() if f.get("answered"))
    except Exception:
        out["war"], out["war_fighters"] = "n/a", 0
    # campus
    try:
        from . import campus as C
        d = C._load()
        out["events_open"] = [e for e in d["events"].values() if e["state"] == "open"]
        out["events_done_7d"] = sum(1 for e in d["events"].values() if e["state"] == "done" and (e.get("finished") or "")[:10] >= y7)
    except Exception:
        out["events_open"], out["events_done_7d"] = [], 0
    # sources
    try:
        from .collector import health_summary
        h = health_summary()
        out["src_ok"], out["src_fail"], out["src_paused"] = h["ok"], h["failing"], h["paused"]
    except Exception:
        out["src_ok"] = out["src_fail"] = out["src_paused"] = 0
    return out


def alerts(mx):
    a = []
    for ch, n in mx.get("stock", {}).items():
        if 0 <= n < LOW_STOCK:
            a.append(f"📉 {ch}: only {n} unused questions — run collector / add sources")
    if mx.get("src_fail", 0) > 10:
        a.append(f"🌐 {mx['src_fail']} sources failing ({mx.get('src_paused', 0)} paused)")
    stale = [e for e in mx.get("events_open", []) if (_now() - datetime.fromisoformat(e["created"])).total_seconds() > 6 * 3600]
    for e in stale[:3]:
        a.append(f"🎓 {e['code']} {e['name'][:20]} open for {int((_now() - datetime.fromisoformat(e['created'])).total_seconds() // 3600)}h — start or close")
    if mx["members"] and mx["joined_hub"] / mx["members"] < 0.4:
        a.append(f"📢 only {round(100 * mx['joined_hub'] / mx['members'])}% verified channel join — nudge")
    if mx["blocked"] > 0.1 * max(mx["members"], 1):
        a.append(f"🚫 {mx['blocked']} members blocked the bot")
    if mx.get("vouchers_held", 0) + mx.get("centre_pending", 0) > 20:
        a.append(f"🎟 {mx['vouchers_held'] + mx['centre_pending']} vouchers waiting for verification")
    if mx.get("applications", 0):
        a.append(f"🤝 {mx['applications']} partner applications waiting — /partner")
    return a


def render(members, bank=None):
    mx = metrics(members, bank)
    al = alerts(mx)
    now = _now()
    lines = [f"🏢 STUDENTUP HQ · {now.strftime('%a %d %b %H:%M')}", "",
             f"👥 Members {mx['members']} (+{mx['new_today']} today · +{mx['new_7d']} 7d · +{mx['new_30d']} 30d)",
             f"🔥 Active: {mx['active_today']} today · {mx['active_7d']} this week · 🎯 {mx['players_today']} played {mx['rounds_today']} rounds ({mx['answers_today']} answers)",
             f"📢 Verified join {mx['joined_hub']}/{mx['members']} · 🚫 blocked {mx['blocked']}",
             f"🎁 Referrals {mx['referrals']} → activated {mx['ref_activated']}",
             f"🎓 Colleges {mx['colleges']} · campus members {mx['campus_members']} · events 7d {mx['events_done_7d']}" + (f" · OPEN: {', '.join(e['code'] for e in mx['events_open'])}" if mx['events_open'] else ""),
             f"🏪 Partners {mx['partners']} · offers {mx['offers']} · vouchers held {mx['vouchers_held']} · redeemed 7d {mx['vouchers_used_7d']} · centre pending {mx['centre_pending']}",
             f"⚔️ War: {mx['war']}" + (f" ({mx['war_fighters']} fighters)" if mx['war_fighters'] else ""),
             f"🌐 Sources ok {mx['src_ok']} · failing {mx['src_fail']} · paused {mx['src_paused']}"]
    if mx["stock"]:
        lines.append("📚 Stock: " + " · ".join(f"{ch[:4]} {n}" for ch, n in mx["stock"].items()))
    if mx["top_districts"]:
        lines.append("📍 " + " · ".join(f"{d} {n}" for d, n in mx["top_districts"]))
    if mx["top_colleges"]:
        lines.append("🏫 " + " · ".join(f"{c[:14]} {n}" for c, n in mx["top_colleges"]))
    try:
        from . import cup as CU
        live_cups = [c for c in CU._load()["cups"].values() if c["state"] == "live"]
        if live_cups:
            parts = []
            for c in live_cups[:3]:
                lb, dn, tt = CU.cup_progress(c)
                parts.append(f"{c['code']} {c['name'][:16]} ({lb} {dn}/{tt})")
            lines.append("🏆 Cups LIVE: " + " · ".join(parts))
    except Exception:
        pass
    try:
        from . import gate
        lines.append(gate.owner_line(members))
    except Exception:
        pass
    lines.append("")
    lines += (["⚠️ ALERTS:"] + [f"• {x}" for x in al]) if al else ["✅ No alerts"]
    return "\n".join(lines), mx, al


def buttons():
    return [[("🎓 Campus", "hq:campus"), ("🏪 Partners", "hq:partners"), ("🏫 Colleges", "hq:colleges")],
            [("📣 Offers digest now", "hq:digest"), ("🔔 Nudge join", "hq:nudge")],
            [("📤 Export CSV", "hq:export"), ("🧾 Sheet sync", "hq:sheet")],
            [("⚔️ War status", "hq:war"), ("🔁 Refresh", "hq:refresh")]]


def morning_brief(members, bank=None):
    """Return text only if there is news (new members/alerts) since yesterday's brief."""
    text, mx, al = render(members, bank)
    st = load_json(PATH, {})
    key = {"members": mx["members"], "alerts": len(al), "events": mx["events_done_7d"]}
    if st.get("last_key") == key and not al:
        return None
    st["last_key"] = key; st["last_sent"] = _now().isoformat()
    save_json_atomic(PATH, st)
    return "☀️ Morning brief\n\n" + text


# ============================================================ college manager
def clubs(members):
    """{college: {members, active7, district, leader, points}}"""
    y7 = _day(_now() - timedelta(days=7))
    out = {}
    lead = load_json(PATH, {}).get("leaders", {})
    for uid, m in members.members.items():
        col = m.get("college")
        if not col or not m.get("registered"):
            continue
        c = out.setdefault(col, {"college": col, "members": 0, "active7": 0, "district": m.get("district", ""), "points": 0,
                                  "top": ("", -1), "leader": lead.get(col)})
        c["members"] += 1
        c["points"] += m.get("points", 0)
        if (m.get("last_active") or "") >= y7:
            c["active7"] += 1
        if m.get("points", 0) > c["top"][1]:
            c["top"] = (uid, m.get("points", 0))
    return out


def set_leader(college, uid, members):
    st = load_json(PATH, {})
    st.setdefault("leaders", {})[college] = str(uid)
    save_json_atomic(PATH, st)
    m = members._get(str(uid))
    m["ambassador"] = college
    if "ambassador" not in m.setdefault("badges", []):
        m["badges"].append("ambassador")
    m["points"] = m.get("points", 0) + 50
    members.kv.save()


def club_list_text(members):
    cs = sorted(clubs(members).values(), key=lambda c: (-c["active7"], -c["members"]))
    if not cs:
        return "ఇంకా colleges లేవు — /go <College> | <district> తో మొదటి event."
    lines = ["🏫 COLLEGE CLUBS", ""]
    for c in cs[:20]:
        ldr = (members.members.get(c["leader"]) or {}).get("name", "—") if c["leader"] else "—"
        lines.append(f"• {c['college'][:24]} · {c['district']} — {c['members']}👥 · {c['active7']} active/7d · 👑 {ldr}")
    lines += ["", "Tap a college below for actions."]
    return "\n".join(lines)


def club_buttons(members):
    cs = sorted(clubs(members).values(), key=lambda c: (-c["active7"], -c["members"]))[:8]
    rows = [[(f"🏫 {c['college'][:28]}", f"club:show:{c['college'][:50]}")] for c in cs]
    rows.append([("⬅️ HQ", "hq:refresh")])
    return rows


def club_card(members, college):
    c = clubs(members).get(college)
    if not c:
        return "College not found.", None
    from . import campus as C
    d = C._load()
    evs = sorted((e for e in d["events"].values() if college in e["colleges"]), key=lambda e: e["created"], reverse=True)
    last = evs[0] if evs else None
    ldr = members.members.get(c["leader"]) if c["leader"] else None
    top = members.members.get(c["top"][0]) if c["top"][0] else None
    lines = [f"🏫 {college} · {c['district']}", "",
             f"👥 {c['members']} members · 🔥 {c['active7']} active this week ({round(100 * c['active7'] / max(c['members'], 1))}%) · ⭐ {c['points']} total pts",
             f"👑 Leader/Ambassador: {ldr.get('name') if ldr else '— (set with 👑 button)'}",
             f"🏆 Top scorer: {top.get('name') if top else '—'} ({c['top'][1]} pts)",
             f"🎓 Events: {len(evs)}" + (f" · last {last['code']} {last['created'][:10]} · {len(last['players'])} players" if last else ""), "",
             "Next actions 👇"]
    btns = [[("🔁 Re-run event", f"club:rerun:{college[:50]}"), ("📢 Message members", f"club:msg:{college[:50]}")],
            [("👑 Top scorer → leader", f"club:lead:{college[:50]}"), ("🏆 Post club board", f"club:board:{college[:50]}")],
            [("🧪 Retest in 10 min", f"club:retest:{college[:50]}"), ("📋 Roster + CSV", f"club:roster:{college[:50]}")],
            [("📈 Progress report", f"club:progress:{college[:50]}"), ("⬅️ Colleges", "hq:colleges")]]
    return "\n".join(lines), btns


def club_board(members, college, limit=10):
    rows = [(m.get("points", 0), m.get("name", ""), uid) for uid, m in members.members.items() if m.get("college") == college and m.get("registered")]
    if not rows:
        return ""
    rows.sort(reverse=True)
    lines = [f"🏫 {college} — CLUB BOARD (all-time points)", ""]
    for i, (p, n, u) in enumerate(rows[:limit], 1):
        lines.append(f"{'🥇🥈🥉'[i - 1] if i <= 3 else str(i) + '.'} {n[:20]} — {p} pts")
    lines += ["", f"{len(rows)} members · రోజూ /quiz ఆడితే పైకి · College League నెలకి ఒకసారి 🏆"]
    return "\n".join(lines)


def club_members(members, college):
    return [uid for uid, m in members.members.items() if m.get("college") == college and m.get("registered") and not m.get("dm_blocked")]
