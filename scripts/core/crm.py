#!/usr/bin/env python3
"""
STUDENTUP CRM — the member base as a reusable asset.

Every registered player (name, district, state, mobile, exam, Telegram id,
points, activity) is:
  1. mirrored to a Google Sheet in real time (Apps Script web-app endpoint,
     no Google API keys/libraries needed) — this is your permanent database
     for future channels, courses, alerts, prizes, anything;
  2. exportable as CSV / Excel-friendly file from the bot (/export, admin);
  3. reachable by segment (/broadcast district=Warangal exam=TSPSC …) so you
     can DM a targeted group about a new channel, job alert, event, etc.

Google Sheet setup (one time, 2 minutes):
  • Create a Sheet → Extensions → Apps Script → paste docs/sheet_webapp.gs
  • Deploy → Web app → Execute as: Me, Access: Anyone → copy URL
  • .env:  SHEET_WEBAPP_URL=https://script.google.com/macros/s/…/exec
           SHEET_SECRET=any-long-random-string  (same value inside the script)
Pure standard library.
"""
from __future__ import annotations

import csv
import io
import json
import re
import urllib.request
from datetime import datetime

from . import config

SHEET_URL = getattr(config, "SHEET_WEBAPP_URL", "") or ""
SHEET_SECRET = getattr(config, "SHEET_SECRET", "") or ""

COLUMNS = ["tg_id", "name", "username", "mobile", "state", "district", "qualification", "mandal", "exam", "lang",
           "registered_at", "source", "points", "correct", "total", "accuracy", "streak", "best_streak", "level",
           "last_active", "follow", "college", "branch", "year", "campus_event", "tests", "best_pct", "last_pct",
           "referred_by", "referrals", "verified_channels", "coach_streak", "badges", "ambassador", "dm_blocked"]

QUEUE = config.DATA / "sheet_queue.json"      # offline queue: failed pushes are retried, never lost
QUEUE_CAP = 2000
MEMBERS_XLSX = config.DATA / "members.xlsx"

def export_xlsx_bytes(members: dict, only_registered=True) -> bytes:
    """Generates clean native Excel (.xlsx) file bytes from members dictionary using zipfile & OpenXML."""
    import zipfile, xml.etree.ElementTree as ET, io
    rows_data = []
    for uid, m in sorted(members.items(), key=lambda kv: -(kv[1].get("points", 0) or 0)):
        if only_registered and not m.get("registered"):
            continue
        row_dict = member_row(uid, m)
        rows_data.append([str(row_dict.get(col, "")) for col in COLUMNS])
    
    # Simple sheetData XML
    sheet_rows_xml = []
    # Header row (1)
    header_cells = ''.join(f'<c t="inlineStr"><is><t>{c}</t></is></c>' for c in COLUMNS)
    sheet_rows_xml.append(f'<row r="1">{header_cells}</row>')
    
    for r_idx, r in enumerate(rows_data, 2):
        cells_xml = []
        for val in r:
            clean_val = str(val).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            cells_xml.append(f'<c t="inlineStr"><is><t>{clean_val}</t></is></c>')
        joined_cells = "".join(cells_xml)
        sheet_rows_xml.append(f'<row r="{r_idx}">{joined_cells}</row>')
        
    sheet_data = ''.join(sheet_rows_xml)
    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{sheet_data}</sheetData>'
        '</worksheet>'
    )
    
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Registered_Students" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )
    
    wb_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types_xml)
        zf.writestr('_rels/.rels', rels_xml)
        zf.writestr('xl/workbook.xml', workbook_xml)
        zf.writestr('xl/_rels/workbook.xml.rels', wb_rels_xml)
        zf.writestr('xl/worksheets/sheet1.xml', worksheet_xml)
    return out_buf.getvalue()

MEMBERS_CSV = config.DATA / "members.csv"     # Local auto-sync CSV mirror for instant Excel & offline access


def member_row(uid, m: dict) -> dict:
    from .members import level_for
    total = m.get("total", 0) or 0
    acc = round(100 * (m.get("correct", 0) or 0) / total, 1) if total else 0.0
    tests = m.get("tests") or []
    return {
        "tg_id": str(uid), "name": m.get("name", ""), "username": m.get("username", ""),
        "mobile": m.get("mobile", ""), "state": m.get("state", ""),
        "district": m.get("district", ""), "mandal": m.get("mandal", ""), "qualification": m.get("qualification", ""),
        "exam": m.get("exam", ""), "lang": m.get("lang", ""),
        "registered_at": m.get("registered_at", ""), "source": m.get("source", ""),
        "points": m.get("points", 0), "correct": m.get("correct", 0), "total": total,
        "accuracy": acc, "streak": m.get("streak", 0), "best_streak": m.get("best_streak", 0),
        "level": level_for(m.get("points", 0)).get("title_en", ""),
        "last_active": m.get("last_active", ""),
        "follow": ",".join(m.get("follow") or []),
        "college": m.get("college", ""), "branch": m.get("branch", ""), "year": m.get("year", ""),
        "campus_event": m.get("campus_event", ""),
        "tests": len(tests), "best_pct": max((t.get("pct", 0) for t in tests), default=""),
        "last_pct": tests[-1].get("pct", "") if tests else "",
        "referred_by": m.get("referred_by", ""), "referrals": m.get("referrals", 0),
        "verified_channels": len(m.get("joined_channels") or []),
        "coach_streak": m.get("coach_streak", 0), "badges": ",".join(m.get("badges") or []),
        "ambassador": bool(m.get("ambassador")), "dm_blocked": bool(m.get("dm_blocked")),
    }


def sheet_enabled() -> bool:
    return bool(SHEET_URL and SHEET_URL.startswith("http"))


def sync_local_csv(members: dict) -> int:
    """Automatically write/update all registered members to both members.csv and members.xlsx Excel sheet."""
    try:
        csv_bytes = export_csv(members, only_registered=True)
        MEMBERS_CSV.write_bytes(csv_bytes)
        xlsx_bytes = export_xlsx_bytes(members, only_registered=True)
        MEMBERS_XLSX.write_bytes(xlsx_bytes)
        return sum(1 for m in members.values() if m.get("registered"))
    except Exception as e:
        print(f"   [crm] sync_local_csv note: {e}")
        return 0


def push_member(uid, m: dict, post=None, members_dict=None) -> bool:
    """Upsert one member row into Google Sheet and sync local CSV mirror."""
    if members_dict is not None:
        sync_local_csv(members_dict)
    elif m.get("registered"):
        try:
            # Quick append/update to local CSV
            from .store import load_json
            data = load_json(config.DATA / "members.json", {})
            mems = data.get("members", {})
            if mems:
                sync_local_csv(mems)
        except Exception:
            pass

    if not sheet_enabled():
        return False
    return _post({"action": "upsert", "row": member_row(uid, m)}, post)


def push_all(members: dict, post=None) -> int:
    sync_local_csv(members)
    if not sheet_enabled():
        return 0
    rows = [member_row(uid, m) for uid, m in members.items() if m.get("registered")]
    ok = 0
    for i in range(0, len(rows), 200):
        if _post({"action": "bulk", "rows": rows[i:i + 200]}, post):
            ok += len(rows[i:i + 200])
    return ok


def push_round_top(round_id, channel, rows, post=None) -> bool:
    """Append round toppers to the 'rounds' tab — history of who wins where."""
    if not sheet_enabled() or not rows:
        return False
    return _post({"action": "round", "rows": [
        {"round_id": round_id, "channel": channel, "rank": i + 1, "tg_id": r["uid"],
         "name": r["name"], "district": r["district"], "correct": r["correct"],
         "total": r["total"], "points": r["points"]} for i, r in enumerate(rows)]}, post)


def push_campus(code, event_name, district, rows, members=None, post=None) -> bool:
    """Append a campus event's full result to the 'campus' tab (one row per student, with phone/branch)."""
    if not sheet_enabled() or not rows:
        return False
    mm = members or {}
    out = []
    for r in rows:
        m = mm.get(str(r["uid"]), {})
        tot = r.get("total", 0) or 0
        out.append({"event": f"{code} {event_name}"[:60], "college": r.get("college", ""), "district": district, "rank": r.get("rank", ""),
                    "tg_id": r["uid"], "name": r.get("name", ""), "phone": m.get("mobile", ""), "branch": m.get("branch", ""), "year": m.get("year", ""),
                    "correct": r.get("correct", 0), "total": tot, "pct": round(100 * r.get("correct", 0) / tot) if tot else "", "points": r.get("pts", 0)})
    return _post({"action": "campus", "rows": out}, post)


def push_colleges(members: dict, post=None) -> int:
    """One row per college: students, phones, tests, avg last %, improved count, ambassador, last event."""
    if not sheet_enabled():
        return 0
    cols = {}
    for uid, m in members.items():
        c = m.get("college")
        if not c or not m.get("registered"):
            continue
        r = cols.setdefault(c, {"college": c, "district": m.get("district", ""), "students": 0, "with_phone": 0, "tests": 0,
                                "_pcts": [], "improved": 0, "ambassador": "", "last_event": ""})
        r["students"] += 1
        r["with_phone"] += 1 if m.get("mobile") else 0
        ts = m.get("tests") or []
        if ts:
            r["tests"] = max(r["tests"], len(ts)); r["_pcts"].append(ts[-1].get("pct", 0))
            r["last_event"] = max(r["last_event"], ts[-1].get("date", ""))
            if len(ts) >= 2 and ts[-1].get("pct", 0) > ts[0].get("pct", 0):
                r["improved"] += 1
        if m.get("ambassador"):
            r["ambassador"] = m.get("name", "")
    rows = []
    for r in cols.values():
        p = r.pop("_pcts")
        r["avg_last_pct"] = round(sum(p) / len(p)) if p else ""
        rows.append(r)
    ok = 0
    for i in range(0, len(rows), 200):
        if _post({"action": "colleges", "rows": rows[i:i + 200]}, post):
            ok += len(rows[i:i + 200])
    return ok


def push_partners(post=None) -> int:
    if not sheet_enabled():
        return 0
    try:
        from . import partners as P
        d = P._load()
    except Exception:
        return 0
    rows = []
    for pid, p in d.get("partners", {}).items():
        offers = [o for o in d.get("offers", {}).values() if o.get("partner") == pid]
        vs = [v for v in d.get("vouchers", {}).values() if any(v.get("offer") == o["id"] for o in offers)]
        rows.append({"partner_id": pid, "name": p.get("name", ""), "type": p.get("category", ""), "district": p.get("district", ""),
                     "mandal": p.get("mandal", ""), "status": "active" if p.get("active") else "paused", "offers": len(offers),
                     "vouchers_issued": len(vs), "redeemed": sum(1 for v in vs if v.get("status") == "used"),
                     "pending": sum(1 for v in vs if v.get("status") == "held"), "plan": p.get("plan", "")})
    ok = 0
    for i in range(0, len(rows), 200):
        if _post({"action": "partners", "rows": rows[i:i + 200]}, post):
            ok += len(rows[i:i + 200])
    return ok


def push_campaign(job: dict, post=None) -> bool:
    if not sheet_enabled():
        return False
    r = job.get("report", {})
    try:
        from .messenger import seg_label
        aud = seg_label(job.get("seg", {}))
    except Exception:
        aud = str(job.get("seg", {}))
    return _post({"action": "campaign", "row": {"by": job.get("by", ""), "audience": aud, "total": r.get("total", 0), "sent": r.get("sent", 0),
                                                  "blocked": r.get("blocked", 0), "failed": r.get("failed", 0), "text": (job.get("text") or "")[:200]}}, post)


def push_request(req_id: str, r: dict, status: str = "", event_code: str = "", post=None) -> bool:
    """Record student campuswar request in Google Sheet 'requests' tab."""
    if not sheet_enabled():
        return False
    row = {
        "req_id": req_id,
        "tg_id": r.get("uid", ""),
        "name": r.get("name", ""),
        "college": r.get("college", ""),
        "district": r.get("district", ""),
        "status": status or r.get("status", "pending"),
        "event_code": event_code or r.get("event", ""),
        "created_at": r.get("ts", "")
    }
    return _post({"action": "request", "row": row}, post)


def push_daily(members: dict, extra: dict | None = None, post=None) -> bool:
    """One snapshot row per day (computed by the bot, so it works even if the Sheet trigger is never set)."""
    if not sheet_enabled():
        return False
    today = datetime.now(config.IST).strftime("%Y-%m-%d")
    reg = [m for m in members.values() if m.get("registered")]
    row = {"date": today, "members": len(reg), "with_mobile": sum(1 for m in reg if m.get("mobile")),
           "active_today": sum(1 for m in reg if m.get("last_active") == today),
           "new_today": sum(1 for m in reg if (m.get("registered_at") or "")[:10] == today),
           "ts_members": sum(1 for m in reg if m.get("state") == "Telangana"),
           "ap_members": sum(1 for m in reg if m.get("state") == "Andhra Pradesh"),
           "answers_today": sum((m.get("daylog") or {}).get(today, [0, 0])[0] for m in reg),
           "colleges": len({m.get("college") for m in reg if m.get("college")})}
    row.update(extra or {})
    return _post({"action": "daily", "row": row}, post)


def nightly_sync(members: dict, post=None) -> dict:
    """23:30 — full resync of everything + flush the offline queue. Returns counts."""
    out = {"queue_flushed": flush_queue(post)}
    if not sheet_enabled():
        return out
    out["members"] = push_all(members, post)
    out["colleges"] = push_colleges(members, post)
    out["partners"] = push_partners(post)
    out["daily"] = push_daily(members, post=post)
    return out


def ping(post=None) -> dict:
    """Health check → {'ok': bool, 'members': n, 'version': v}."""
    if not sheet_enabled():
        return {"ok": False, "error": "SHEET_WEBAPP_URL not set"}
    try:
        data = json.dumps({"action": "ping", "secret": SHEET_SECRET}).encode("utf-8")
        req = urllib.request.Request(SHEET_URL, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode("utf-8", "ignore") or "{}")
        if not body.get("ok"):
            return {"ok": False, "error": body.get("error", "unknown")}
        with urllib.request.urlopen(SHEET_URL, timeout=15) as r:
            info = json.loads(r.read().decode("utf-8", "ignore") or "{}")
        return {"ok": True, "members": info.get("members", 0), "version": info.get("version", 1)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _send(payload: dict, post=None) -> bool:
    if post:
        return bool(post(SHEET_URL, payload))
    data = json.dumps(payload, default=str).encode("utf-8")
    req = urllib.request.Request(SHEET_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read(400).decode("utf-8", "ignore")
    try:
        return bool(json.loads(body).get("ok"))
    except Exception:
        return '"ok":true' in body.replace(" ", "")


def _post(payload: dict, post=None) -> bool:
    if not sheet_enabled():
        return False
    payload["secret"] = SHEET_SECRET
    payload["ts"] = datetime.now(config.IST).isoformat(timespec="seconds")
    try:
        if _send(payload, post):
            return True
        raise RuntimeError("sheet returned not ok")
    except Exception as e:
        print(f"   [crm] sheet push failed: {e} → queued")
        _enqueue(payload)
        return False


def _enqueue(payload):
    from .store import load_json, save_json_atomic
    q = load_json(QUEUE, {"items": []})
    items = q.get("items", [])
    items.append({k: v for k, v in payload.items() if k != "secret"})
    save_json_atomic(QUEUE, {"items": items[-QUEUE_CAP:]})


def queue_size() -> int:
    from .store import load_json
    return len(load_json(QUEUE, {"items": []}).get("items", []))


def flush_queue(post=None, limit=300) -> int:
    """Retry queued pushes (called nightly and from /sheet). Stops at first failure to keep order."""
    from .store import load_json, save_json_atomic
    if not sheet_enabled():
        return 0
    q = load_json(QUEUE, {"items": []})
    items = q.get("items", [])
    if not items:
        return 0
    done = 0
    while items and done < limit:
        p = dict(items[0]); p["secret"] = SHEET_SECRET
        try:
            if not _send(p, post):
                break
        except Exception:
            break
        items.pop(0); done += 1
    save_json_atomic(QUEUE, {"items": items})
    return done


def sheet_status_text(members: dict) -> str:
    pg = ping()
    lines = ["📊 GOOGLE SHEET"]
    if pg.get("ok"):
        lines.append(f"✅ connected · v{pg.get('version', 1)} · {pg.get('members', 0)} rows in Sheet · {sum(1 for m in members.values() if m.get('registered'))} registered in bot")
    else:
        lines.append(f"⚠️ {pg.get('error')}" + ("" if sheet_enabled() else "\nSetup: docs/sheet_webapp.gs (3 min) → .env SHEET_WEBAPP_URL + SHEET_SECRET"))
    qs = queue_size()
    lines.append(f"📦 offline queue: {qs} pending" if qs else "📦 offline queue: empty")
    lines.append("\nTabs: members · rounds · campus · colleges · partners · campaigns · daily · 📊 Dashboard")
    lines.append("Auto: live upserts · 23:30 full resync · every event/round/campaign appended")
    return "\n".join(lines)


def sheet_buttons():
    return [[("🔁 Sync all now", "sheet:sync"), ("📦 Flush queue", "sheet:flush")],
            [("🏫 Colleges tab", "sheet:colleges"), ("🏪 Partners tab", "sheet:partners")],
            [("📅 Daily snapshot", "sheet:daily"), ("📤 CSV export", "sheet:csv")],
            [("🔄 Status", "sheet:status")]]


# ----------------------------------------------------------------------- CSV
def export_csv(members: dict, only_registered=True) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    for uid, m in sorted(members.items(), key=lambda kv: -(kv[1].get("points", 0) or 0)):
        if only_registered and not m.get("registered"):
            continue
        w.writerow(member_row(uid, m))
    # UTF-8 BOM so Excel opens Telugu names correctly
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


# ------------------------------------------------------------------ segments
_FILTER_RE = re.compile(r"(\w+)\s*=\s*([^\s]+)")


def parse_segment(text: str) -> dict:
    """'district=Warangal exam=TSPSC state=TS active=7' -> dict."""
    return {k.lower(): v for k, v in _FILTER_RE.findall(text or "")}


def select(members: dict, seg: dict) -> list:
    from . import districts as D
    from datetime import timedelta
    out = []
    want_d = seg.get("district")
    if want_d:
        _, canon = D.match_any_district(want_d)
        want_d = canon or want_d
    want_state = seg.get("state", "").upper()
    want_state = {"TS": "Telangana", "AP": "Andhra Pradesh"}.get(want_state, seg.get("state", ""))
    active_days = int(seg["active"]) if seg.get("active", "").isdigit() else None
    cutoff = ((datetime.now(config.IST) - timedelta(days=active_days)).strftime("%Y-%m-%d")
              if active_days else None)
    for uid, m in members.items():
        if not m.get("registered") or m.get("dm_blocked"):
            continue
        if want_d and (m.get("district") or "").lower() != want_d.lower():
            continue
        if want_state and (m.get("state") or "").lower() != want_state.lower():
            continue
        if seg.get("exam") and seg["exam"].lower() not in (m.get("exam") or "").lower():
            continue
        if seg.get("qual") and (m.get("qualification") or "").lower() != seg["qual"].lower():
            continue
        if seg.get("minpoints", "").isdigit() and (m.get("points", 0) or 0) < int(seg["minpoints"]):
            continue
        if cutoff and (m.get("last_active") or "") < cutoff:
            continue
        if seg.get("mobile") == "yes" and not m.get("mobile"):
            continue
        out.append(uid)
    return out


def segment_summary(members: dict) -> str:
    regs = {u: m for u, m in members.items() if m.get("registered")}
    by = lambda k: sorted(
        {}.items() if not regs else
        _count(regs, k).items(), key=lambda kv: -kv[1])
    lines = [f"🗂 *StudentUp CRM* — {len(regs)} registered",
             f"📱 with mobile: {sum(1 for m in regs.values() if m.get('mobile'))}",
             "", "*State*"]
    lines += [f"  {k or '—'}: {v}" for k, v in by("state")[:4]]
    lines += ["", "*Top districts*"]
    lines += [f"  {k or '—'}: {v}" for k, v in by("district")[:10]]
    lines += ["", "*Qualification*"]
    lines += [f"  {k or '—'}: {v}" for k, v in by("qualification")[:6]]
    lines += ["", "*Exam target*"]
    lines += [f"  {k or '—'}: {v}" for k, v in by("exam")[:9]]
    lines += ["", "Sheet sync: " + ("✅ on" if sheet_enabled() else "⚠️ off (set SHEET_WEBAPP_URL)"),
              "Export: /export · Segment DM: /broadcast district=Warangal exam=TSPSC <message>"]
    return "\n".join(lines)


def _count(d: dict, key: str) -> dict:
    c = {}
    for m in d.values():
        k = m.get(key) or ""
        c[k] = c.get(k, 0) + 1
    return c
