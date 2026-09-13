"""
Job Radar 2.0 — personal job matching on top of the Jobs Desk (core/jobs.py).

* Every card posted to the private JOBS channel is also stored in data/jobs_board.json
  (60-day board) with a parsed minimum qualification + deadline.
* Students: /jobs → jobs that match THEIR qualification + state, newest first, with
  🔔 Track / ✅ Applied buttons.  Channel cards carry a "🔔 Track in bot" deep link
  (t.me/<bot>?start=job<id>).
* Tracking = deadline reminders (3 days + 1 day before, 09:00) + an apply checklist
  (documents by category) + the Internet-Centre cashback CTA.
* 19:00 daily Radar DM: new matching jobs of the last 24 h (max 5) — opt-out with /jobs off.
* Owner: /jobs stats → most tracked jobs, applied counts, radar reach.
Everything is stdlib, dry-safe, and failures never block the channel post.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import config
from .store import load_json, save_json_atomic

BOARD = config.DATA / "jobs_board.json"
KEEP_DAYS = 60
DIGEST_MAX = 5
APPLIED_PTS = 5
APPLIED_CAP_PER_DAY = 3

QUAL_LEVEL = {"SSC": 1, "INTER": 2, "ITI": 2, "UG": 3, "PG": 4, "OTHER": 2}
_QUAL_PATTERNS = [
    ("SSC", r"\b(10th|ssc|matric(ulation)?|tenth|8th|7th|5th)\b|పదో|పదవ"),
    ("INTER", r"\b(12th|10\s*\+\s*2|inter(mediate)?|hsc|plus two)\b|ఇంటర్"),
    ("ITI", r"\b(iti|diploma|polytechnic)\b|డిప్లొమా|ఐటీఐ"),
    ("UG", r"\b(degree|graduat(e|ion)|bachelor|b\.?\s?tech|b\.?e\b|b\.?sc|b\.?com|b\.?a\b|bba|bca|llb|mbbs|b\.?ed|any graduate)|డిగ్రీ|గ్రాడ్యుయేట్"),
    ("PG", r"\b(post\s*graduat(e|ion)|pg|m\.?\s?tech|m\.?e\b|m\.?sc|m\.?com|m\.?a\b|mba|mca|master|ph\.?d|llm|m\.?ed)\b|పీజీ"),
]

CHECKLIST = {
    "ts-ap": ["📷 Passport photo + signature (scan)", "🪪 Aadhaar", "📜 SSC memo (DOB proof)", "🎓 Qualification certificates",
              "🏷 Caste / EWS certificate (if any)", "🏠 Study / residence certificate (local status)", "💳 Fee payment (UPI/card)"],
    "central": ["📷 Photo + signature per size rules", "🪪 Aadhaar / ID", "📜 SSC memo", "🎓 Degree / Inter certificates",
                "🏷 Caste / EWS / PwD certificate", "📧 Working e-mail + mobile (OTP)", "💳 Fee payment"],
    "private-it": ["📄 Updated resume (PDF)", "🎓 Marks memos", "🪪 ID proof", "📧 Professional e-mail", "🔗 LinkedIn / GitHub (if IT)"],
    "walk-in": ["📄 2 resume copies", "📷 2 photos", "🎓 Original + xerox certificates", "🪪 Aadhaar", "🕘 Reach 30 min early"],
    "scholarship": ["🎓 Bonafide certificate", "💰 Income certificate", "🏷 Caste certificate", "🏦 Bank passbook (own name)",
                    "🪪 Aadhaar linked mobile", "📜 Previous year marks memo"],
}


def _now():
    return datetime.now(config.IST)


def _load():
    d = load_json(BOARD, {"jobs": {}, "seq": 0, "tracks": {}, "applied": {}, "digest_off": [], "digest_log": {}, "remind_log": {}})
    for k in ("jobs", "tracks", "applied", "digest_log", "remind_log"):
        d.setdefault(k, {})
    d.setdefault("digest_off", []); d.setdefault("seq", 0)
    return d


def _save(d):
    cutoff = (_now() - timedelta(days=KEEP_DAYS)).isoformat()
    d["jobs"] = {k: v for k, v in d["jobs"].items() if v.get("posted", "") >= cutoff}
    save_json_atomic(BOARD, d)


# ------------------------------------------------------------------ parsing
def min_qualification(text: str) -> str:
    """Lowest qualification mentioned in a qualification string → code ('' if none found)."""
    t = (text or "").lower()
    found = [code for code, pat in _QUAL_PATTERNS if re.search(pat, t, re.I)]
    if not found:
        return ""
    return min(found, key=lambda c: QUAL_LEVEL[c])


def eligible(member: dict, job: dict) -> bool:
    mq = member.get("qualification") or "OTHER"
    jq = job.get("min_qual") or ""
    if not jq:
        return True                      # unknown → show, card says "check qualification"
    return QUAL_LEVEL.get(mq, 2) >= QUAL_LEVEL[jq]


def state_ok(member: dict, job: dict) -> bool:
    if job.get("category") != "ts-ap":
        return True
    st = (member.get("state") or "")
    loc = (job.get("location") or "") + " " + (job.get("title") or "") + " " + (job.get("board") or "")
    if re.search(r"telangana|tspsc|tgpsc|hyderabad|తెలంగాణ", loc, re.I) and st == "Andhra Pradesh" \
            and not re.search(r"andhra|appsc|ap\b|ఆంధ్ర", loc, re.I):
        return False
    if re.search(r"andhra|appsc|amaravati|ఆంధ్ర", loc, re.I) and st == "Telangana" \
            and not re.search(r"telangana|tspsc|tgpsc|hyderabad|తెలంగాణ", loc, re.I):
        return False
    return True


# ------------------------------------------------------------------ board
def record(j, card: str) -> str:
    """Called by jobs.run after a channel post. Returns the short job id (J123)."""
    d = _load()
    key = j.key()
    for jid, v in d["jobs"].items():
        if v.get("key") == key:
            return jid
    d["seq"] += 1
    jid = f"J{d['seq']}"
    d["jobs"][jid] = {"id": jid, "key": key, "title": j.title, "title_te": j.title_te, "category": j.category, "board": j.board,
                      "qualification": j.qualification, "min_qual": min_qualification(j.qualification or j.title),
                      "last_date": j.last_date, "url": j.url, "apply_url": j.apply_url, "location": j.location,
                      "vacancies": j.vacancies, "posted": _now().isoformat(), "card": card[:1500], "tracks": 0, "applied": 0}
    _save(d)
    return jid


def deep_link(jid: str) -> str:
    u = getattr(config, "BOT_USERNAME", "") or ""
    return f"https://t.me/{u.lstrip('@')}?start=job{jid[1:]}" if u else ""


def channel_buttons(jid: str):
    dl = deep_link(jid)
    return [[("🔔 Track in bot · reminders", f"url:{dl}")]] if dl else None


def parse_start_arg(arg: str):
    m = re.fullmatch(r"job(\d+)", (arg or "").strip(), re.I)
    return f"J{m.group(1)}" if m else None


def _days_left(job, today=None):
    from .jobs import parse_date
    dt = parse_date(job.get("last_date", ""))
    if not dt:
        return None
    return (dt - (today or _now().date())).days


def open_jobs(d=None, today=None):
    d = d or _load()
    out = []
    for v in d["jobs"].values():
        dl = _days_left(v, today)
        if dl is not None and dl < 0:
            continue
        out.append(v)
    out.sort(key=lambda v: v.get("posted", ""), reverse=True)
    return out


def matches(member: dict, limit=8, d=None, since=None, today=None):
    out = []
    for v in open_jobs(d, today):
        if since and v.get("posted", "") < since:
            continue
        if eligible(member, v) and state_ok(member, v):
            out.append(v)
    # state jobs first, then closing-soon
    out.sort(key=lambda v: (0 if v.get("category") == "ts-ap" else 1, _days_left(v, today) if _days_left(v, today) is not None else 99))
    return out[:limit]


# ------------------------------------------------------------------ render
def _line(v, today=None):
    dl = _days_left(v, today)
    tag = "" if dl is None else (" · ⏳ TODAY" if dl == 0 else f" · ⏳ {dl}d")
    q = v.get("min_qual") or "check"
    title = (v.get("title_te") or v.get("title") or "")[:70]
    return f"{v['id']} · {title}\n     🎓 {q}{(' · ' + v['vacancies'] + ' posts') if v.get('vacancies') else ''}{tag}"


def radar_text(members, uid, today=None) -> str:
    m = members.members.get(str(uid), {})
    from .members import QUAL_LABEL
    ms = matches(m, today=today)
    q = QUAL_LABEL.get(m.get("qualification", ""), m.get("qualification") or "—")
    head = f"📡 JOB RADAR — {m.get('name', '')[:16]}\n🎓 {q} · 📍 {m.get('state', '') or 'TS/AP'}\n"
    if not ms:
        return head + "\nఇప్పుడు మీకు match అయ్యే open jobs లేవు. కొత్త job వస్తే 19:00 కి DM వస్తుంది 📡\n(change qualification: /profile)"
    d = _load()
    tracked = set(d["tracks"].get(str(uid), []))
    lines = [head, f"✅ మీకు eligible open jobs: {len(ms)}", ""]
    for v in ms:
        lines.append(("🔔 " if v["id"] in tracked else "▫️ ") + _line(v, today))
    lines.append("\n🔔 Track = last-date reminders + apply checklist\n💳 Application file చేయాలంటే మా Internet Centre → points cashback (/rewards)")
    lines.append("Radar DM off: /jobs off · on: /jobs on")
    return "\n".join(lines)


def radar_buttons(members, uid, today=None):
    m = members.members.get(str(uid), {})
    rows, row = [], []
    for v in matches(m, today=today)[:8]:
        row.append((f"🔔 {v['id']}", f"jr:t:{v['id']}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([("📋 My tracked", "jr:mine"), ("🔄 Refresh", "jr:refresh")])
    return rows


def job_card(jid: str, uid=None, today=None) -> tuple[str, list | None]:
    d = _load()
    v = d["jobs"].get(jid)
    if not v:
        return "❌ ఈ job ఇప్పుడు board లో లేదు (60 రోజులు మాత్రమే ఉంటుంది).", None
    txt = v.get("card") or v.get("title", "")
    dl = _days_left(v, today)
    if dl is not None:
        txt = ("⏳ ఈరోజే చివరి తేదీ!\n" if dl == 0 else (f"⏳ {dl} రోజులు మిగిలాయి\n" if dl <= 7 else "")) + txt
    tracked = uid is not None and jid in d["tracks"].get(str(uid), [])
    applied = uid is not None and jid in d["applied"].get(str(uid), [])
    btn = [[("🔕 Untrack" if tracked else "🔔 Track this job", f"jr:{'u' if tracked else 't'}:{jid}"),
            ("✅ Applied" if applied else "✅ I applied", f"jr:a:{jid}")],
           [("📋 Checklist", f"jr:c:{jid}"), ("📡 My radar", "jr:refresh")]]
    if v.get("apply_url") or v.get("url"):
        btn.insert(0, [("🌐 Open notification", f"url:{v.get('apply_url') or v.get('url')}")])
    return txt, btn


def checklist_text(jid: str) -> str:
    d = _load()
    v = d["jobs"].get(jid, {})
    items = CHECKLIST.get(v.get("category", ""), CHECKLIST["central"])
    lines = [f"📋 APPLY CHECKLIST — {jid}", (v.get("title_te") or v.get("title", ""))[:80], ""]
    lines += [f"☐ {it}" for it in items]
    if v.get("last_date"):
        lines.append(f"\n📅 Last date: {v['last_date']} — చివరి రోజు వరకు ఆగకండి (server slow అవుతుంది)")
    lines.append("\n💳 మా Internet Centre లో file చేస్తే → points cashback + loyalty bonus (/rewards)\n✅ Apply అయ్యాక 'I applied' నొక్కండి (+5 pts)")
    return "\n".join(lines)


# ------------------------------------------------------------------ actions
def track(uid, jid: str) -> str:
    d = _load()
    if jid not in d["jobs"]:
        return "❌ Job not found."
    lst = d["tracks"].setdefault(str(uid), [])
    if jid in lst:
        return f"🔔 {jid} already tracked. Reminders: 3 days + 1 day before last date, 09:00."
    lst.append(jid); d["jobs"][jid]["tracks"] = d["jobs"][jid].get("tracks", 0) + 1
    _save(d)
    v = d["jobs"][jid]
    return (f"🔔 Tracking {jid} — {(v.get('title_te') or v.get('title'))[:60]}\n"
            f"📅 Last date: {v.get('last_date') or 'notification చూడండి'} → reminders 3 రోజులు + 1 రోజు ముందు 09:00 కి.\n📋 Checklist button నొక్కండి.")


def untrack(uid, jid: str) -> str:
    d = _load()
    lst = d["tracks"].setdefault(str(uid), [])
    if jid in lst:
        lst.remove(jid); d["jobs"].get(jid, {}).__setitem__("tracks", max(0, d["jobs"].get(jid, {}).get("tracks", 1) - 1)); _save(d)
    return f"🔕 {jid} untracked."


def applied(members, uid, jid: str) -> str:
    d = _load()
    if jid not in d["jobs"]:
        return "❌ Job not found."
    lst = d["applied"].setdefault(str(uid), [])
    if jid in lst:
        return f"✅ {jid} already marked applied. All the best! 💪"
    lst.append(jid); d["jobs"][jid]["applied"] = d["jobs"][jid].get("applied", 0) + 1
    today = _now().strftime("%Y-%m-%d")
    m = members.members.get(str(uid))
    bonus = ""
    if m is not None:
        log = m.setdefault("applied_log", {})
        if log.get(today, 0) < APPLIED_CAP_PER_DAY:
            log[today] = log.get(today, 0) + 1
            m["points"] = m.get("points", 0) + APPLIED_PTS
            members.kv.save()
            bonus = f" +{APPLIED_PTS} pts 🎁"
    if jid in d["tracks"].get(str(uid), []):
        d["tracks"][str(uid)].remove(jid)
    _save(d)
    return f"✅ Applied noted for {jid}{bonus}\n📚 ఇప్పుడు prep: /quiz · exam date రాగానే countdown DM వస్తుంది."


def mine_text(uid, today=None) -> str:
    d = _load()
    tr = [d["jobs"][j] for j in d["tracks"].get(str(uid), []) if j in d["jobs"]]
    ap = [d["jobs"][j] for j in d["applied"].get(str(uid), []) if j in d["jobs"]]
    lines = ["📋 MY JOBS"]
    lines.append(f"\n🔔 Tracking ({len(tr)}):" if tr else "\n🔔 Tracking: none — /jobs లో 🔔 నొక్కండి")
    for v in tr:
        lines.append("  " + _line(v, today))
    if ap:
        lines.append(f"\n✅ Applied ({len(ap)}):")
        for v in ap[-10:]:
            lines.append(f"  {v['id']} · {(v.get('title_te') or v.get('title'))[:60]}")
    return "\n".join(lines)


def set_digest(uid, on: bool) -> str:
    d = _load()
    s = str(uid)
    if on and s in d["digest_off"]:
        d["digest_off"].remove(s)
    if not on and s not in d["digest_off"]:
        d["digest_off"].append(s)
    _save(d)
    return "📡 Job Radar DM ON — రోజూ 19:00 కి మీకు match అయ్యే కొత్త jobs." if on else "📡 Job Radar DM OFF. మళ్ళీ on: /jobs on"


# ------------------------------------------------------------------ scheduled
def daily_digest(members, tg, dry=False, today=None) -> int:
    """19:00 — new matching jobs (last 24 h) per member, max 5. Returns members messaged."""
    d = _load()
    day = (today or _now().date()).strftime("%Y-%m-%d")
    since = (_now() - timedelta(hours=26)).isoformat()
    sent = 0
    for uid, m in members.members.items():
        if not m.get("registered") or m.get("dm_blocked") or uid in d["digest_off"]:
            continue
        if d["digest_log"].get(uid) == day:
            continue
        new = matches(m, limit=DIGEST_MAX, d=d, since=since, today=today)
        if not new:
            continue
        txt = (f"📡 JOB RADAR · {m.get('name', '')[:14]}\n🎓 మీకు eligible కొత్త jobs ({len(new)}):\n\n" +
               "\n".join(_line(v, today) for v in new) +
               "\n\n🔔 Track చేయండి → reminders + checklist. Off: /jobs off")
        btn = [[(f"🔔 {v['id']}", f"jr:t:{v['id']}") for v in new[:3]], [("📡 Full radar", "jr:refresh")]]
        d["digest_log"][uid] = day
        if dry:
            sent += 1; continue
        try:
            tg.send_message(uid, txt, buttons=btn); sent += 1
            tg.polite_gap(True)
        except Exception as e:
            if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                m["dm_blocked"] = True
    if not dry:
        members.kv.save(); _save(d)
    return sent


def deadline_reminders(members, tg, dry=False, today=None) -> int:
    """09:00 — for tracked jobs closing in 3 days / 1 day / today (each once)."""
    d = _load()
    sent = 0
    for uid, jids in list(d["tracks"].items()):
        m = members.members.get(uid, {})
        if m.get("dm_blocked"):
            continue
        for jid in list(jids):
            v = d["jobs"].get(jid)
            if not v:
                continue
            dl = _days_left(v, today)
            if dl is None or dl not in (0, 1, 3):
                continue
            k = f"{uid}:{jid}:{dl}"
            if d["remind_log"].get(k):
                continue
            d["remind_log"][k] = 1
            when = "ఈరోజే చివరి తేదీ! ⚠️" if dl == 0 else f"{dl} రోజు{'లు' if dl > 1 else ''} మిగిలాయి"
            txt = (f"⏰ REMINDER — {jid}\n{(v.get('title_te') or v.get('title'))[:80]}\n📅 {v.get('last_date')} · {when}\n"
                   f"{'✅ Apply: ' + v['apply_url'] if v.get('apply_url') else '🔗 ' + v.get('url', '')}\n"
                   f"💳 Fast filing: మా Internet Centre → points cashback")
            btn = [[("✅ I applied", f"jr:a:{jid}"), ("📋 Checklist", f"jr:c:{jid}")]]
            if dry:
                sent += 1; continue
            try:
                tg.send_message(uid, txt, buttons=btn); sent += 1; tg.polite_gap(True)
            except Exception as e:
                if "blocked" in str(e).lower():
                    m["dm_blocked"] = True
    if not dry:
        d["remind_log"] = dict(list(d["remind_log"].items())[-5000:])
        _save(d)
    return sent


# ------------------------------------------------------------------ owner
def stats_text(members) -> str:
    d = _load()
    jobs = list(d["jobs"].values())
    opn = open_jobs(d)
    reg = [m for m in members.members.values() if m.get("registered")]
    by_q = {}
    for m in reg:
        by_q[m.get("qualification") or "?"] = by_q.get(m.get("qualification") or "?", 0) + 1
    top = sorted(jobs, key=lambda v: (-v.get("tracks", 0), -v.get("applied", 0)))[:5]
    lines = [f"📡 JOB RADAR — owner stats", f"Board: {len(jobs)} jobs (60d) · open {len(opn)} · tracked {sum(v.get('tracks', 0) for v in jobs)} · applied {sum(v.get('applied', 0) for v in jobs)}",
             f"Radar reach: {len(reg) - len(d['digest_off'])}/{len(reg)} members on · " + " ".join(f"{k}:{n}" for k, n in sorted(by_q.items())), ""]
    lines.append("🔥 Most tracked:")
    for v in top:
        lines.append(f"  {v['id']} 🔔{v.get('tracks', 0)} ✅{v.get('applied', 0)} · {(v.get('title_te') or v.get('title'))[:50]}")
    cats = {}
    for v in opn:
        cats[v.get("category", "?")] = cats.get(v.get("category", "?"), 0) + 1
    lines.append("\nOpen by type: " + " · ".join(f"{k} {n}" for k, n in cats.items()))
    return "\n".join(lines)
