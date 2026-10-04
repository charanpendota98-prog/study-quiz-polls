"""Consent-first member invite queue. Never auto-adds contacts; prepares opted-in invites."""
import csv, io, json, re, uuid
from datetime import datetime
from pathlib import Path
from . import config

FILE = config.DATA / "member_invite_queue.json"

def _load():
    if FILE.exists():
        try: return json.loads(FILE.read_text(encoding="utf-8"))
        except Exception: pass
    return {"batch_limit": 20, "start_time": "09:00", "groups": {}, "alerts": [], "members": []}

def _save(d):
    FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

def normalize_phone(v):
    digits = re.sub(r"\D", "", str(v or ""))
    if digits.startswith("00"): digits = digits[2:]
    return digits if 10 <= len(digits) <= 15 else ""

def import_csv(text, group_id="", default_consent="PENDING"):
    d, seen, added, skipped = _load(), set(), 0, 0
    rows = list(csv.DictReader(io.StringIO(text)))
    for row in rows:
        phone = normalize_phone(row.get("phone") or row.get("Phone") or row.get("number") or row.get("Number"))
        if not phone or phone in seen: skipped += 1; continue
        seen.add(phone)
        consent = str(row.get("consent") or row.get("Consent") or default_consent).upper().strip()
        if consent not in ("OPTED_IN", "OPTED_OUT", "PENDING"): consent = "PENDING"
        d["members"] = [m for m in d["members"] if m.get("phone") != phone]
        d["members"].append({"id": "m_" + uuid.uuid4().hex[:8], "name": row.get("name") or row.get("Name") or "", "phone": phone, "group_id": group_id, "consent": consent, "status": "READY" if consent == "OPTED_IN" else "BLOCKED", "created_at": datetime.now().isoformat(), "last_error": ""})
        added += 1
    _save(d); return {"ok": True, "added": added, "skipped": skipped, "total": len(d["members"])}

def snapshot():
    d = _load(); ms = d["members"]
    return {"ok": True, "batch_limit": d["batch_limit"], "start_time": d["start_time"], "total": len(ms), "ready": sum(m["status"] == "READY" for m in ms), "pending_consent": sum(m["consent"] == "PENDING" for m in ms), "completed": sum(m["status"] == "INVITE_SENT" for m in ms), "failed": sum(m["status"] == "FAILED" for m in ms), "opted_out": sum(m["consent"] == "OPTED_OUT" for m in ms)}

def update_settings(body):
    d = _load(); d["batch_limit"] = max(1, min(20, int(body.get("batch_limit", 20)))); d["start_time"] = str(body.get("start_time", "09:00")); d["alerts"] = [normalize_phone(x) for x in body.get("alerts", []) if normalize_phone(x)]; _save(d); return snapshot()
