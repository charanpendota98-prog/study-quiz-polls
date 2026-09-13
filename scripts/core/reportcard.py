"""
WEEKLY REPORT CARD — every student's shareable PNG (WhatsApp-status size) + text twin.

Why: the student is not the only audience — parents, friends, classmates, college see it. A student who
posts "District rank #12 · 84% accuracy · 6-day streak · 3 weak topics fixed" brings 3 more students.

  • Sunday 20:30  → every member active this week gets card (PNG if Pillow, else text) with:
      week answers/accuracy · 7-day activity bars · district rank & state rank · streak · points earned
      · strongest topic · topic to fix · college (if any) · badges · share CTA with referral link.
  • /card any time (own card); after every campus test the campus result already carries the player line.
  • Text twin is always sent as the caption so it works on every phone.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config

BARS = "▁▂▃▄▅▆▇█"


def _now():
    return datetime.now(config.IST)


def week_days(now=None):
    now = now or _now()
    return [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]


def week_stats(m, now=None):
    dl = m.get("daylog") or {}
    days = week_days(now)
    per = [dl.get(d, [0, 0]) for d in days]
    ans = sum(p[0] for p in per); cor = sum(p[1] for p in per)
    mx = max([p[0] for p in per] + [1])
    bars = "".join(BARS[min(7, int(7 * p[0] / mx))] if p[0] else "·" for p in per)
    active_days = sum(1 for p in per if p[0])
    return {"answers": ans, "correct": cor, "acc": round(100 * cor / ans) if ans else 0, "bars": bars,
            "active_days": active_days, "days": days}


def ranks(members, uid):
    """(district_rank, district_n, state_rank, state_n) by points among registered."""
    m = members.members.get(str(uid), {})
    d, st = m.get("district"), m.get("state_code")
    pts = m.get("points", 0)
    dn = dr = sn = sr = 0
    for u, o in members.members.items():
        if not o.get("registered"):
            continue
        if d and o.get("district") == d:
            dn += 1
            if o.get("points", 0) > pts:
                dr += 1
        if st and o.get("state_code") == st:
            sn += 1
            if o.get("points", 0) > pts:
                sr += 1
    return (dr + 1 if d else 0, dn, sr + 1 if st else 0, sn)


def topics(m):
    rows = [(t, v) for t, v in (m.get("topics") or {}).items() if v.get("total", 0) >= 3]
    if not rows:
        return "", ""
    rows.sort(key=lambda kv: kv[1]["correct"] / kv[1]["total"])
    weak = rows[0]; strong = rows[-1]
    fmt = lambda kv: f"{kv[0].title()} {round(100 * kv[1]['correct'] / kv[1]['total'])}%"
    return fmt(strong), (fmt(weak) if weak is not strong else "")


def text_card(members, uid, now=None):
    m = members.members.get(str(uid), {})
    w = week_stats(m, now)
    dr, dn, sr, sn = ranks(members, uid)
    strong, weak = topics(m)
    bot = getattr(config, "BOT_USERNAME", "StudentUpBot")
    lines = [f"📇 {m.get('name', 'Student')[:22]} — WEEKLY REPORT CARD",
             f"📍 {m.get('district', '')}" + (f" · 🏫 {m['college'][:18]}" if m.get("college") else ""),
             "",
             f"📝 {w['answers']} Q this week · 🎯 {w['acc']}% accuracy · {w['active_days']}/7 days",
             f"📊 {w['bars']}  (Mon→Sun)",
             f"🔥 Streak {m.get('streak', 0)} days · ⭐ {m.get('points', 0)} pts"]
    if dr:
        lines.append(f"🏆 District rank #{dr}/{dn}" + (f" · State #{sr}/{sn}" if sr else ""))
    if strong:
        lines.append(f"💪 Strong: {strong}" + (f" · 🎯 Fix next: {weak}" if weak else ""))
    b = m.get("badges") or []
    if b:
        lines.append("🏅 " + " ".join(x.title() for x in b[:5]))
    lines += ["", f"👉 Friends కి పంపండి: t.me/{bot}?start=r{uid} (ఇద్దరికీ points)"]
    return "\n".join(lines)


def png_card(members, uid, now=None):
    """PNG via rankcard's renderer (None when Pillow missing)."""
    try:
        from . import rankcard, districts as D
    except Exception:
        return None
    if not rankcard.available():
        return None
    m = members.members.get(str(uid), {})
    w = week_stats(m, now)
    dr, dn, sr, sn = ranks(members, uid)
    strong, weak = topics(m)
    score = f"{w['acc']}% · {w['answers']} Q · {w['active_days']}/7 days"
    extra = (f"District #{dr}/{dn}" if dr else "") + (f" · Streak {m.get('streak', 0)}🔥" if m.get("streak") else "")
    try:
        dte = D.telugu_name(m.get("district", "")) if hasattr(D, "telugu_name") else ""
    except Exception:
        dte = ""
    return rankcard.render({"name": m.get("name", ""), "district": m.get("district", ""), "district_te": dte, "points": m.get("points", 0)},
                           title="WEEKLY REPORT CARD", subtitle_te="వారపు రిపోర్ట్ కార్డ్", exam=(m.get("exam") or "") + (f" · {strong}" if strong else ""),
                           rank=0, score=score, extra=extra, when=now)


def send_card(tg, members, uid, now=None):
    txt = text_card(members, uid, now)
    png = png_card(members, uid, now)
    if png and hasattr(tg, "send_photo"):
        try:
            tg.send_photo(uid, png, caption=txt[:1000], filename="report_card.png")
            return "png"
        except Exception:
            pass
    tg.send_message(uid, txt)
    return "text"


def weekly_send(tg, members, now=None, dry=False):
    """Sunday 20:30 — everyone who answered ≥5 Q this week."""
    now = now or _now()
    n = {"png": 0, "text": 0}
    for uid, m in members.members.items():
        if not m.get("registered") or m.get("dm_blocked"):
            continue
        if week_stats(m, now)["answers"] < 5:
            continue
        if dry:
            n["text"] += 1; continue
        try:
            n[send_card(tg, members, uid, now)] += 1
        except Exception:
            pass
    return n
