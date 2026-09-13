"""
COLLEGE ROSTER + RETEST SERIES — "వాళ్ళ data collect అయినట్టు, మళ్ళీ మనం test పెట్టినట్టు".

Data captured per student (beyond name/phone/district): college, branch, year, roll (optional),
every test attempt (event code, date, score, rank, %). Stored in members (m["college"], m["branch"],
m["year"], m["roll"], m["tests"]=[{code, date, pts, correct, n, rank, of}]).

Flows
  • After join: one tap 📚 branch (B.Tech/Degree/Inter/PG/Diploma/Other) → one tap year (1/2/3/4/Final).
    Skippable; never asked twice. (+5 pts)
  • /retest <College> [| N] — RETEST series for the same students: everyone with m["college"]==College
    gets a scheduled exam in DM (default: in 10 min, or "| 18:30" today). No walk-in needed. Same engine
    (campus.new_event mode college) but players are auto-enrolled and pinged; poster not needed.
  • After ANY campus event finishes: attempts appended → improvement vs previous test computed →
    "📈 Most Improved" (top 3 by Δ%) DMed + added to channel result; principal PROGRESS report.
  • Weekly Monday 09:00: 🏆 College Toppers of the week → CHAMPION_CHANNELS (per college top 3 by week pts).
  • roster_csv(college) → CSV (name, phone, branch, year, roll, tests, best %, last %, Δ) for the college.
  • roster_text(college) → summary card for HQ/club.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from . import config

BRANCHES = ["B.Tech", "Degree", "Inter", "PG", "Diploma", "Other"]
YEARS = ["1st", "2nd", "3rd", "4th", "Final"]
PROFILE_PTS = 5
IMPROVE_PTS = {0: 40, 1: 25, 2: 15}


def _now():
    return datetime.now(config.IST)


# ================================================================== profile capture
def needs_profile(m):
    return bool(m.get("college")) and not m.get("branch") and not m.get("_prof_skipped")


def profile_prompt():
    return ("📚 ఒక్క tap: మీ course ఏది? (college leaderboard branch-wise కూడా చూపిస్తాం · +%d pts)" % PROFILE_PTS,
            [[(b, f"rp:b:{b}") for b in BRANCHES[:3]], [(b, f"rp:b:{b}") for b in BRANCHES[3:]], [("Skip", "rp:skip:-")]])


def year_prompt():
    return ("📅 ఏ year?", [[(y, f"rp:y:{y}") for y in YEARS[:3]], [(y, f"rp:y:{y}") for y in YEARS[3:]] + [("Skip", "rp:skip:-")]])


def handle_callback(members, uid, kind, val):
    """rp:b:<branch> | rp:y:<year> | rp:skip → (text, buttons|None)"""
    m = members._get(str(uid))
    if kind == "skip":
        m["_prof_skipped"] = True; members.kv.save()
        return "👍 OK. తర్వాత ఎప్పుడైనా: /profile", None
    if kind == "b" and val in BRANCHES:
        m["branch"] = val; members.kv.save()
        t, b = year_prompt()
        return f"✅ {val}\n{t}", b
    if kind == "y" and val in YEARS:
        m["year"] = val
        if not m.get("_prof_pts"):
            m["_prof_pts"] = True; m["points"] = m.get("points", 0) + PROFILE_PTS
        members.kv.save()
        return f"✅ {m.get('branch', '')} {val} year · +{PROFILE_PTS} pts 🎁\nమీ college board: /college", None
    return "…", None


# ================================================================== attempts
def record_event(members, e):
    """Called at campus finish: append attempts, compute improvement, return most-improved rows."""
    from .campus import ranking
    rows = ranking(e)
    n_q = len(e["questions"]) or e["n_q"]
    improved = []
    for u, p in rows:
        m = members._get(u)
        prev = (m.get("tests") or [])[-1] if m.get("tests") else None
        pct = round(100 * p["correct"] / max(n_q, 1))
        att = {"code": e["code"], "date": _now().strftime("%Y-%m-%d"), "pts": p["pts"], "correct": p["correct"], "n": n_q,
               "pct": pct, "rank": p.get("rank", 0), "of": len(rows), "college": p["college"]}
        m.setdefault("tests", []).append(att)
        m["tests"] = m["tests"][-50:]
        if prev:
            delta = pct - prev["pct"]
            att["delta"] = delta
            if delta > 0:
                improved.append((delta, pct, prev["pct"], u, p["name"], p["college"]))
    improved.sort(reverse=True)
    for i, row in enumerate(improved[:3]):
        m = members._get(row[3]); m["points"] = m.get("points", 0) + IMPROVE_PTS[i]
        m.setdefault("badges", [])
        if "improver" not in m["badges"]:
            m["badges"].append("improver")
    members.kv.save()
    return improved[:3]


def improved_text(improved):
    if not improved:
        return ""
    lines = ["", "📈 MOST IMPROVED (vs their last test)"]
    for i, (d, pct, prev, u, name, col) in enumerate(improved):
        lines.append(f"{['🥇', '🥈', '🥉'][i]} {name[:18]} · {col[:12]} — {prev}% → {pct}% (+{d}) 🎁+{IMPROVE_PTS[i]}")
    return "\n".join(lines)


def progress_report(members, college):
    """Principal-facing progress across all tests for this college."""
    studs = [(u, m) for u, m in members.members.items() if m.get("college") == college and m.get("tests")]
    if not studs:
        return ""
    codes = {}
    for u, m in studs:
        for t in m["tests"]:
            if t.get("college") == college:
                codes.setdefault(t["code"], []).append(t)
    lines = [f"🏛 {college} — PROGRESS REPORT", f"👥 {len(studs)} students · {len(codes)} tests", ""]
    for code, atts in sorted(codes.items(), key=lambda kv: kv[1][0]["date"]):
        avg = sum(a["pct"] for a in atts) / len(atts)
        lines.append(f"• {atts[0]['date']} {code}: {len(atts)} students · avg {avg:.0f}%")
    multi = [(m["tests"][-1]["pct"] - m["tests"][0]["pct"], m) for u, m in studs if len(m["tests"]) >= 2]
    if multi:
        up = sum(1 for d, _ in multi if d > 0)
        lines += ["", f"📈 {up}/{len(multi)} students improved since their first test · avg Δ {sum(d for d, _ in multi) / len(multi):+.0f}%"]
        multi.sort(key=lambda x: -x[0])
        lines.append("Top improvers: " + ", ".join(f"{m.get('name', '')[:12]} ({d:+d}%)" for d, m in multi[:5]))
    by_branch = {}
    for u, m in studs:
        by_branch.setdefault(m.get("branch") or "—", []).append(m["tests"][-1]["pct"])
    if len(by_branch) > 1:
        lines += ["", "Branch-wise (last test avg):"] + [f"  {b}: {sum(v) / len(v):.0f}% ({len(v)})" for b, v in sorted(by_branch.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))]
    weak = {}
    lines += ["", "Powered by StudentUp · next retest anytime — /retest"]
    return "\n".join(lines)


# ================================================================== retest
def schedule_retest(members, college, n_q=15, at=None, created_by="", mode="college"):
    """Create an event for an existing college and auto-enrol all its students. Returns (code, n_enrolled)."""
    from . import campus as C
    studs = [u for u, m in members.members.items() if m.get("college") == college and m.get("registered") and not m.get("dm_blocked")]
    if not studs:
        return None, 0
    district = next((m.get("district", "") for u, m in members.members.items() if m.get("college") == college and m.get("district")), "")
    code = C.new_event(f"{college[:26]} × Retest", district, [college], n_q, "easy", created_by, mode)
    d = C._load(); e = d["events"][code]
    e["retest"] = True
    e["auto_start"] = (at or (_now() + timedelta(minutes=10))).isoformat()
    for u in studs:
        m = members.members[u]
        e["players"][u] = {"college": college, "name": m.get("name", ""), "pts": 0, "correct": 0, "answered": 0,
                           "joined": _now().isoformat(), "first": None, "last": None, "bonus": True}
        d["by_uid"][u] = code
    C._save(d)
    return code, len(studs)


def retest_invite(e):
    t = datetime.fromisoformat(e["auto_start"]).strftime("%I:%M %p").lstrip("0")
    return (f"🔁 {e['name']}\n⏰ {t} కి ఇక్కడే exam start · {e['n_q']} Q · 30 sec/Q\n"
            f"📈 మీ last score ని beat చేయండి → Most Improved కి 🎁+40/25/15\n"
            f"📱 {t} కి phone ready గా ఉంచండి. ప్రశ్నలు వాటంతట అవే వస్తాయి.")


def ping_retest(tg, code):
    from . import campus as C
    e = C._load()["events"].get(code)
    if not e:
        return 0
    n = 0
    for u in e["players"]:
        try:
            tg.send_message(u, retest_invite(e)); n += 1
        except Exception:
            pass
    return n


def auto_start_due(bank, members, tg, now=None):
    """Start scheduled retests whose time has come (call from engine tick)."""
    from . import campus as C
    now = now or _now()
    d = C._load()
    started = []
    for e in d["events"].values():
        if e["state"] == "open" and e.get("auto_start") and now >= datetime.fromisoformat(e["auto_start"]):
            started.append(e["code"])
    for code in started:
        try:
            C.start(bank, members, tg, code, now)
        except Exception:
            pass
    return started


# ================================================================== roster views
def roster_csv(members, college):
    out = ["name,phone,branch,year,roll,district,tests,best_pct,last_pct,delta,points,uid"]
    for u, m in members.members.items():
        if m.get("college") != college:
            continue
        ts = m.get("tests") or []
        best = max((t["pct"] for t in ts), default="")
        last = ts[-1]["pct"] if ts else ""
        delta = (ts[-1]["pct"] - ts[0]["pct"]) if len(ts) >= 2 else ""
        out.append(",".join(str(x) for x in [m.get("name", ""), m.get("mobile", ""), m.get("branch", ""), m.get("year", ""), m.get("roll", ""),
                                             m.get("district", ""), len(ts), best, last, delta, m.get("points", 0), u]))
    return "\n".join(out)


def roster_text(members, college):
    studs = [m for m in members.members.values() if m.get("college") == college]
    if not studs:
        return f"🏫 {college}: no students yet"
    with_tests = [m for m in studs if m.get("tests")]
    by_b = {}
    for m in studs:
        by_b[m.get("branch") or "—"] = by_b.get(m.get("branch") or "—", 0) + 1
    lines = [f"🏫 {college} — ROSTER", f"👥 {len(studs)} students · 📱 phone {sum(1 for m in studs if m.get('mobile'))} · 📚 branch known {sum(1 for m in studs if m.get('branch'))}",
             "Branches: " + ", ".join(f"{b} {n}" for b, n in sorted(by_b.items(), key=lambda x: -x[1])),
             f"🧪 tested {len(with_tests)} · retests done {sum(1 for m in studs if len(m.get('tests') or []) >= 2)}"]
    if with_tests:
        best = max(with_tests, key=lambda m: m["tests"][-1]["pct"])
        lines.append(f"⭐ Last test top: {best.get('name', '')} {best['tests'][-1]['pct']}%")
    return "\n".join(lines)


def weekly_toppers(members, limit_colleges=8):
    """Monday post: per-college top 3 by this week's points (needs m['week_pts'] or falls back to points)."""
    by_col = {}
    for u, m in members.members.items():
        if not m.get("college") or not m.get("registered"):
            continue
        by_col.setdefault(m["college"], []).append((m.get("week_pts", m.get("points", 0)), m.get("name", ""), m.get("branch", "")))
    if not by_col:
        return ""
    cols = sorted(by_col.items(), key=lambda kv: -sum(p for p, _, _ in kv[1]))[:limit_colleges]
    lines = ["🏆 COLLEGE TOPPERS OF THE WEEK", ""]
    for col, rows in cols:
        rows.sort(reverse=True)
        lines.append(f"🏫 {col[:24]} ({len(rows)}👥)")
        for i, (p, n, b) in enumerate(rows[:3]):
            lines.append(f"  {['🥇', '🥈', '🥉'][i]} {n[:16]}{(' · ' + b) if b else ''} — {p} pts")
    lines += ["", "మీ college లేదా? Event కోసం organiser ని అడగండి · రోజూ /quiz ఆడితే మీ పేరు ఇక్కడ 🔥"]
    return "\n".join(lines)
