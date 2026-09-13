"""
MESSAGE STUDIO — send YOUR message to registered students individually via the bot, the easy way.

  /msg                      → audience buttons (All · District · Exam · College · Inactive 7d · Active 7d ·
                              Campus students · Has phone · Top 100) → tap → "now type your message"
  next message (text OR photo with caption) → personalised PREVIEW (as the first student would see it)
                              with buttons: ✅ Send now · ⏰ Send at 6 PM · ⏰ Tomorrow 9 AM · ✏️ Edit · ❌ Cancel
  send                      → 20 msgs/sec-safe pacing, blocked users auto-marked, buttons row optional,
                              delivery report to you (sent / blocked / skipped) + saved in history.
  /msg history              → last 10 campaigns with delivery numbers
  /msg templates            → 6 ready Telugu templates (exam alert, offer, event, motivation, job, festival)

Placeholders (auto-filled per student): {name} {district} {points} {exam} {college} {rank} {streak} {first}
Optional button line at the end of your message:  [Open quiz](/quiz)  or  [Apply](https://…)
Quiet hours: nothing goes out 22:00–07:00 (queued to 07:05) unless you tap "Send anyway".
State: data/campaigns.json
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

PATH = config.DATA / "campaigns.json"
PER_SEC = 18
QUIET = (22, 7)

AUDIENCES = [
    ("all", "👥 All registered", {}),
    ("active7", "🔥 Active last 7 days", {"active": "7"}),
    ("inactive7", "😴 Silent 7+ days", {"inactive": "7"}),
    ("campus", "🎓 Campus students", {"campus": "yes"}),
    ("phone", "📱 Has phone number", {"mobile": "yes"}),
    ("top100", "🏆 Top 100 by points", {"top": "100"}),
    ("district", "📍 Pick district…", None),
    ("exam", "📚 Pick exam…", None),
    ("college", "🏫 Pick college…", None),
]

TEMPLATES = {
    "exam": "📢 {name} గారు, {exam} exam update!\n\n<మీ update ఇక్కడ>\n\nరోజూ practice: /quiz · మీ points: {points} ⭐",
    "offer": "🎁 {name}, {district} లో మీ కోసం కొత్త offer!\n\n<offer details>\n\nమీ దగ్గర {points} points ఉన్నాయి → /offers లో claim చేయండి",
    "event": "🎓 {name} గారు, {college} లో StudentUp event!\n\n📅 <date> · ⏰ <time>\n\nRegister link వచ్చాక ఇక్కడే వస్తుంది. Friends కి చెప్పండి 👇",
    "motivate": "💪 {name}, {streak} రోజుల streak! {district} లో మీ rank #{rank}.\n\nఈరోజు 10 Q ఆడితే top 10 లోకి రావొచ్చు → /quiz",
    "job": "💼 {name} గారు, కొత్త notification!\n\n<post · vacancies · last date>\n\nApply help కావాలంటే మా centre కి రండి — points తో discount ✅",
    "festival": "🎉 {name} గారికి, మీ కుటుంబానికి <పండుగ> శుభాకాంక్షలు!\n\nఈరోజు special: double points on /quiz 🎁\n— StudentUp టీం",
}


def _now():
    return datetime.now(config.IST)


def _load():
    d = load_json(PATH, {}) or {}
    d.setdefault("history", []); d.setdefault("scheduled", []); d.setdefault("drafts", {})
    return d


def _save(d):
    save_json_atomic(PATH, d)


# ================================================================== audience
def audience_buttons():
    rows, row = [], []
    for key, label, _ in AUDIENCES:
        row.append((label, f"msg:aud:{key}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([("📜 History", "msg:history:-"), ("📝 Templates", "msg:templates:-")])
    return rows


def pick_buttons(members, kind):
    """Second-level picker: districts / exams / colleges with counts (top 12)."""
    cnt = {}
    for m in members.members.values():
        if not m.get("registered") or m.get("dm_blocked"):
            continue
        v = m.get({"district": "district", "exam": "exam", "college": "college"}[kind]) or ""
        if v:
            cnt[v] = cnt.get(v, 0) + 1
    top = sorted(cnt.items(), key=lambda kv: -kv[1])[:12]
    rows, row = [], []
    for v, n in top:
        row.append((f"{v[:16]} ({n})", f"msg:set:{kind}={v[:40]}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([("⬅️ Back", "msg:home:-")])
    return rows or [[("⬅️ Back", "msg:home:-")]]


def select(members, seg):
    from . import crm
    base = crm.select(members.members, {k: v for k, v in seg.items() if k in ("district", "state", "exam", "qual", "minpoints", "active", "mobile")})
    out = []
    now = _now()
    for uid in base:
        m = members.members[uid]
        if seg.get("inactive"):
            cutoff = (now - timedelta(days=int(seg["inactive"]))).strftime("%Y-%m-%d")
            if (m.get("last_active") or "") >= cutoff:
                continue
        if seg.get("campus") == "yes" and not m.get("college"):
            continue
        if seg.get("college") and (m.get("college") or "").lower() != seg["college"].lower():
            continue
        out.append(uid)
    if seg.get("top", "").isdigit():
        out.sort(key=lambda u: -members.members[u].get("points", 0))
        out = out[:int(seg["top"])]
    return out


def seg_label(seg):
    if not seg:
        return "All registered"
    names = {"active": "active ≤{v}d", "inactive": "silent ≥{v}d", "campus": "campus students", "mobile": "has phone",
             "top": "top {v}", "district": "📍 {v}", "exam": "📚 {v}", "college": "🏫 {v}"}
    return " · ".join(names.get(k, k + "={v}").format(v=v) for k, v in seg.items())


# ================================================================== personalise
_BTN_RE = re.compile(r"^\[([^\]]{1,30})\]\((/[a-z_]+|https?://\S+)\)\s*$", re.M)


def split_buttons(text):
    """Trailing lines like [Label](/quiz) or [Label](https://…) become inline buttons."""
    btns = []
    for m in _BTN_RE.finditer(text):
        lbl, target = m.group(1), m.group(2)
        btns.append((lbl, f"url:{target}" if target.startswith("http") else f"cmd:{target}"))
    body = _BTN_RE.sub("", text).rstrip()
    return body, ([btns] if btns else None)


def personalise(text, members, uid):
    m = members.members.get(str(uid), {})
    name = (m.get("name") or "Student").strip()
    first = name.split()[0] if name else "Student"
    rank = ""
    try:
        from .reportcard import ranks
        rank = ranks(members, uid)[0] or ""
    except Exception:
        pass
    vals = {"name": name, "first": first, "district": m.get("district") or "మీ జిల్లా", "points": m.get("points", 0),
            "exam": m.get("exam") or "", "college": m.get("college") or "మీ college", "rank": rank, "streak": m.get("streak", 0)}
    out = text
    for k, v in vals.items():
        out = out.replace("{" + k + "}", str(v))
    return out


# ================================================================== drafts
def start_draft(admin, seg):
    d = _load()
    d["drafts"][str(admin)] = {"seg": seg, "text": "", "photo": "", "created": _now().isoformat()}
    _save(d)


def get_draft(admin):
    return _load()["drafts"].get(str(admin))


def set_content(admin, text="", photo=""):
    d = _load(); dr = d["drafts"].get(str(admin))
    if not dr:
        return None
    dr["text"] = text; dr["photo"] = photo
    _save(d)
    return dr


def clear_draft(admin):
    d = _load(); d["drafts"].pop(str(admin), None); _save(d)


def preview(members, admin):
    dr = get_draft(admin)
    if not dr or not dr.get("text"):
        return None, None, 0
    targets = select(members, dr["seg"])
    sample = targets[0] if targets else None
    body, btns = split_buttons(dr["text"])
    shown = personalise(body, members, sample) if sample else body
    q = in_quiet()
    head = (f"👀 PREVIEW · {len(targets)} students · {seg_label(dr['seg'])}" + (" · 📷 photo" if dr.get("photo") else "") +
            (f"\n(as {members.members[sample].get('name', '')[:16]} would see it)" if sample else "") +
            ("\n🌙 Quiet hours now — 'Send now' will queue to 07:05" if q else "") + "\n" + "─" * 22 + "\n")
    rows = [[("✅ Send now", "msg:send:now"), ("⏰ Today 6 PM", "msg:send:18")],
            [("⏰ Tomorrow 9 AM", "msg:send:tom9"), ("✏️ Edit text", "msg:edit:-")],
            [("🔁 Change audience", "msg:home:-"), ("❌ Cancel", "msg:cancel:-")]]
    return head + shown + ("\n\n[buttons: " + ", ".join(b[0] for b in btns[0]) + "]" if btns else ""), rows, len(targets)


def in_quiet(now=None):
    h = (now or _now()).hour
    return h >= QUIET[0] or h < QUIET[1]


# ================================================================== send / schedule
def schedule(admin, when):
    dr = get_draft(admin)
    if not dr or not dr.get("text"):
        return None
    d = _load()
    job = {"id": f"C{int(time.time())}", "by": str(admin), "seg": dr["seg"], "text": dr["text"], "photo": dr.get("photo", ""),
           "at": when.isoformat(), "state": "scheduled"}
    d["scheduled"].append(job); d["drafts"].pop(str(admin), None); _save(d)
    return job


def when_for(code, now=None):
    now = now or _now()
    if code == "now":
        if in_quiet(now):
            t = now.replace(hour=7, minute=5, second=0, microsecond=0)
            return t if t > now else t + timedelta(days=1)
        return now
    if code == "18":
        t = now.replace(hour=18, minute=0, second=0, microsecond=0)
        return t if t > now else t + timedelta(days=1)
    if code == "tom9":
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return now


def run_job(tg, members, job, dry=False):
    targets = select(members, job["seg"])
    body, btns = split_buttons(job["text"])
    rep = {"sent": 0, "blocked": 0, "failed": 0, "total": len(targets)}
    t0 = time.time(); n = 0
    for uid in targets:
        txt = personalise(body, members, uid)
        if dry:
            rep["sent"] += 1; continue
        try:
            if job.get("photo") and hasattr(tg, "_call"):
                payload = {"chat_id": uid, "photo": job["photo"], "caption": txt[:1000]}
                if btns:
                    payload["reply_markup"] = tg.markup(btns) if hasattr(tg, "markup") else None
                tg._call("sendPhoto", payload)
            else:
                tg.send_message(uid, txt, buttons=btns)
            rep["sent"] += 1
        except Exception as e:
            if "block" in str(e).lower() or "deactivated" in str(e).lower() or "not found" in str(e).lower():
                members.members[uid]["dm_blocked"] = True; rep["blocked"] += 1
            else:
                rep["failed"] += 1
        n += 1
        if n % PER_SEC == 0:
            el = time.time() - t0
            if el < n / PER_SEC:
                time.sleep(n / PER_SEC - el)
    try:
        members.kv.save()
    except Exception:
        pass
    job.update(state="done", report=rep, done=_now().isoformat())
    d = _load()
    d["scheduled"] = [j for j in d["scheduled"] if j["id"] != job["id"]]
    d["history"] = (d["history"] + [job])[-50:]
    _save(d)
    return rep


def run_due(tg, members, now=None, dry=False):
    now = now or _now()
    d = _load()
    due = [j for j in d["scheduled"] if datetime.fromisoformat(j["at"]) <= now]
    out = []
    for j in due:
        rep = run_job(tg, members, j, dry)
        out.append((j, rep))
        if j.get("by") and not dry:
            try:
                tg.send_message(j["by"], report_text(j))
            except Exception:
                pass
    return out


def report_text(job):
    r = job.get("report", {})
    return (f"📣 Delivered · {seg_label(job['seg'])}\n✅ {r.get('sent', 0)} sent · 🚫 {r.get('blocked', 0)} blocked · ⚠️ {r.get('failed', 0)} failed "
            f"(of {r.get('total', 0)})\n🕒 {job.get('done', '')[:16].replace('T', ' ')}\n\n" + job["text"][:120])


def history_text():
    d = _load()
    lines = ["📜 LAST CAMPAIGNS"]
    for j in reversed(d["history"][-10:]):
        r = j.get("report", {})
        lines.append(f"• {j.get('done', '')[:10]} {seg_label(j['seg'])[:24]} — ✅{r.get('sent', 0)} 🚫{r.get('blocked', 0)} · {j['text'][:40]!r}")
    for j in d["scheduled"]:
        lines.append(f"⏰ {j['at'][:16].replace('T', ' ')} {seg_label(j['seg'])[:24]} · {j['text'][:40]!r}  (cancel: /msg cancel {j['id']})")
    return "\n".join(lines) if len(lines) > 1 else "No campaigns yet."


def cancel_scheduled(job_id):
    d = _load(); before = len(d["scheduled"])
    d["scheduled"] = [j for j in d["scheduled"] if j["id"] != job_id]; _save(d)
    return before - len(d["scheduled"])


def templates_text():
    return "📝 TEMPLATES — copy, edit the <…> parts, send as your message:\n\n" + "\n\n".join(f"#{k}\n{v}" for k, v in TEMPLATES.items()) + \
           "\n\nPlaceholders: {name} {first} {district} {points} {exam} {college} {rank} {streak}\nButton line: [Open quiz](/quiz)"
