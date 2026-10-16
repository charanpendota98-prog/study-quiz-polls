#!/usr/bin/env python3
"""
STUDENTUP — ADVANCED WHATSAPP ANTI-BAN PIPELINE & CONCURRENT DISPATCH ENGINE
Engineered specifically for 100+ to 150+ WhatsApp Groups:
  1. Interleaved & Dual-Paced Round-Robin Scheduling:
     - Aspirants in Group A take 40-70 seconds to read and answer Question 1.
     - While Group A is thinking, the engine rotates smoothly into Group B, Group C with 20-30s natural jitter gaps.
     - Supports 2-by-2 interleaved batch pairing (post 2 groups, pause, post next 2 groups).
  2. Multi-Tier Timing & Shift Filters:
     - Morning Shift (07:00 AM - 12:00 PM): Current Affairs, General Studies, English.
     - Evening Shift (05:00 PM - 10:00 PM): Aptitude, Reasoning, Practice Tests.
     - All-Day / Custom shifts.
  3. Advanced Two-Phase Poll Delivery:
     - Phase 1: Question + Options (Poll) posted first with countdown.
     - Phase 2: Official Answer Key + Detailed Bilingual Explanation released after student contemplation window (e.g. 60-90s).
  4. Undetectable Anti-Ban Architecture:
     - Micro zero-width invisible character jitter (\u200B, \u200C, \u200D, \uFEFF) makes every message hash 100% distinct.
     - Randomized human delay curves (18s to 32s) between groups.
     - Extended safety rest after every paired cycle.
  5. Background Non-Blocking Task Runner:
     - Broadcast runs in a detached thread so the Web Dashboard never times out or freezes.
     - Live progress streaming, live active queues, and abort controls.
"""
import os
import time
import random
import json
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from core import config
from core.store import load_json, save_json_atomic
from core.question_bank import Bank
from core import channel_router

WA_CONFIG_FILE = config.DATA / "whatsapp_groups.json"
WA_SESSION_FILE = config.DATA / "whatsapp_session.json"
WA_SCHEDULES_FILE = config.DATA / "whatsapp_schedules.json"
ZERO_WIDTH_CHARS = ["\u200B", "\u200C", "\u200D", "\uFEFF"]

# ---------------------------------------------------------------------
# REAL WHATSAPP BRIDGE (gateway/wa_bridge.js — Baileys WhatsApp Web)
# The Node bridge holds the actual WhatsApp Web session. All login /
# group-sync / send operations go through it. If the bridge is not
# running, the dashboard clearly reports it instead of faking success.
# ---------------------------------------------------------------------
WA_BRIDGE_URL = os.environ.get("WA_BRIDGE_URL", "http://127.0.0.1:3900").rstrip("/")


def _bridge_call(path: str, payload: dict = None, method: str = None, timeout: int = 40, base_url: str = None):
    """Call the Node WhatsApp bridge. Returns dict or None if bridge is down."""
    url = f"{(base_url or WA_BRIDGE_URL).rstrip('/')}{path}"
    try:
        if payload is not None or (method or "").upper() == "POST":
            data = json.dumps(payload or {}).encode("utf-8")
            _hdrs = {"Content-Type": "application/json"}
            if os.environ.get("WA_BRIDGE_TOKEN"):
                _hdrs["x-bridge-token"] = os.environ["WA_BRIDGE_TOKEN"]
            req = urllib.request.Request(url, data=data, headers=_hdrs)
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception:
        return None


def bridge_is_connected() -> bool:
    st = _bridge_call("/status", timeout=5)
    return bool(st and st.get("connected"))

HEADERS = [
    "🎯 *Daily Exam Quiz Challenge*",
    "🔥 *Target Practice Quiz*",
    "🏆 *Official PYQ Daily Challenge*",
    "📚 *Exam Preparation Test Poll*",
    "⚡ *Quick Knowledge Test*",
    "📝 *Daily Syllabus Drill*"
]

BULLETS = [
    ("A", "B", "C", "D", "E"),
    ("1", "2", "3", "4", "5"),
    ("🔹 A", "🔹 B", "🔹 C", "🔹 D", "🔹 E"),
]

# In-memory execution state
EXEC_STATE = {
    "running": False,
    "task_id": None,
    "progress": 0,
    "total": 0,
    "current_group": "",
    "current_stage": "",
    "logs": [],
    "stop_requested": False
}

DEFAULT_SESSION = {
    "status": "bridge_offline",
    "phone": "",
    "device_name": "StudentUp Dispatch Node #1",
    "connected_at": "",
    "qr_data": "",
    "pairing_code": "",
    "scanned_dialogs_count": 0,
    "auto_reconnect": True,
    "heartbeat_interval_sec": 30,
    "last_sync": "",
    "last_heartbeat": ""
}


def load_session() -> dict:
    if WA_SESSION_FILE.exists():
        try:
            return load_json(WA_SESSION_FILE, DEFAULT_SESSION)
        except Exception:
            pass
    save_session(DEFAULT_SESSION)
    return dict(DEFAULT_SESSION)


def save_session(sess: dict):
    save_json_atomic(WA_SESSION_FILE, sess)


def load_schedules() -> list:
    if WA_SCHEDULES_FILE.exists():
        try:
            d = load_json(WA_SCHEDULES_FILE, {"jobs": []})
            return d.get("jobs", [])
        except Exception:
            pass
    return []


def save_schedules(jobs: list):
    save_json_atomic(WA_SCHEDULES_FILE, {"jobs": jobs})


def _session_from_bridge(st: dict) -> dict:
    """Map the Node bridge /status payload onto the session dict the dashboard expects."""
    sess = load_session()
    sess["status"] = st.get("status", "offline")
    sess["phone"] = st.get("phone") or sess.get("phone") or ""
    sess["device_name"] = st.get("device_name") or "StudentUp Dispatch Node #1"
    sess["qr_data"] = st.get("qr_data") or ""
    sess["pairing_code"] = st.get("pairing_code") or ""
    sess["connected_at"] = st.get("connected_at") or sess.get("connected_at") or ""
    sess["bridge_groups_count"] = st.get("groups_count", 0)
    sess["has_saved_session"] = bool(st.get("has_saved_session"))
    sess["last_error"] = st.get("last_error") or ""
    sess["last_heartbeat"] = datetime.now().strftime("%H:%M:%S")
    save_session(sess)
    return sess


def get_session_info() -> dict:
    """REAL session status straight from the Baileys bridge (never faked)."""
    st = _bridge_call("/status", timeout=6)
    if st is None:
        sess = load_session()
        sess["status"] = "bridge_offline"
        sess["message"] = (
            "WhatsApp bridge is not running. Start it with: cd gateway && npm install && node wa_bridge.js"
        )
        save_session(sess)
        return sess
    return _session_from_bridge(st)


def request_login_qr() -> dict:
    """Ask the bridge to open a REAL WhatsApp Web session and return the real QR."""
    st = _bridge_call("/login/qr", payload={}, timeout=45)
    if st is None:
        sess = load_session()
        sess["status"] = "bridge_offline"
        sess["qr_data"] = ""
        sess["message"] = (
            "WhatsApp bridge is offline — start it first: cd gateway && npm install && node wa_bridge.js"
        )
        save_session(sess)
        return sess
    return _session_from_bridge(st)


def request_pairing_code(phone_number: str) -> dict:
    """Request a REAL 8-character WhatsApp pairing code for the given number."""
    st = _bridge_call("/login/code", payload={"phone": phone_number.strip()}, timeout=45)
    if st is None:
        sess = load_session()
        sess["status"] = "bridge_offline"
        sess["pairing_code"] = ""
        sess["message"] = (
            "WhatsApp bridge is offline — start it first: cd gateway && npm install && node wa_bridge.js"
        )
        save_session(sess)
        return sess
    return _session_from_bridge(st)


def confirm_session_connected(device_name: str = "Primary WhatsApp Phone") -> dict:
    """Connection is confirmed by the bridge itself — this just re-checks live status."""
    return get_session_info()


def logout_session() -> dict:
    st = _bridge_call("/logout", payload={}, timeout=20)
    sess = load_session()
    sess["status"] = "offline" if st else "bridge_offline"
    sess["qr_data"] = ""
    sess["pairing_code"] = ""
    save_session(sess)
    return sess


def sync_dialogs_from_session() -> dict:
    """Pull the REAL list of joined WhatsApp groups from the live session and
    merge them into the local registry (upsert by JID, auto exam-category)."""
    st = _bridge_call("/groups?fresh=1", timeout=45)
    if st is None:
        return {
            "ok": False,
            "error": "WhatsApp bridge is offline. Start it: cd gateway && node wa_bridge.js",
            "dialogs_count": 0,
        }
    if not st.get("ok"):
        return {
            "ok": False,
            "error": st.get("error", "WhatsApp not connected — scan the QR first."),
            "dialogs_count": 0,
        }

    real_groups = st.get("groups", [])
    d = load_wa_registry()
    existing = {g.get("jid"): g for g in d.get("groups", [])}
    added, updated = 0, 0
    for rg in real_groups:
        jid = rg.get("jid")
        # Never add non-admin groups to the managed/exportable registry.
        if not jid or not rg.get("is_admin", False):
            continue
        if jid in existing:
            existing[jid]["name"] = rg.get("name", existing[jid].get("name"))
            existing[jid]["participants"] = rg.get("participants", 0)
            existing[jid]["real"] = True
            existing[jid]["admin_verified"] = True
            updated += 1
        else:
            d.setdefault("groups", []).append({
                "id": f"G_{len(d.get('groups', [])) + 1}_{int(time.time()) % 1000}",
                "name": rg.get("name", jid),
                "jid": jid,
                "category": channel_router.detect_exam_base(rg.get("name", "")),
                "shift": "ALL_DAY",
                "active": True,
                "participants": rg.get("participants", 0),
                "real": True,
                "admin_verified": True,
            })
            added += 1
    save_wa_registry(d)

    sess = load_session()
    sess["scanned_dialogs_count"] = len(real_groups)
    sess["last_sync"] = datetime.now().strftime("%H:%M:%S")
    save_session(sess)
    return {
        "ok": True,
        "dialogs_count": len(real_groups),
        "added": added,
        "updated": updated,
        "groups": d.get("groups", []),
        "last_sync": sess["last_sync"],
    }


def add_scheduled_job(
    time_str: str,
    target_group_ids: list = None,
    category: str = "ALL",
    is_question: bool = True,
    label: str = "",
    questions_count: int = 1,
    enabled: bool = True,
    days_duration: int = 0,
    auto_mode: bool = True,
    end_date: str = "",
    start_date: str = "",
    telegram_channels: list = None,
    subjects: list = None,
    mode: str = "wa",
    weekdays: list = None,
    answer_delay_minutes: int = 5,
) -> dict:
    import uuid
    jobs = load_schedules()
    job_id = f"job_{uuid.uuid4().hex[:6]}"
    clean_time = time_str.strip()
    if len(clean_time) == 4 and clean_time[1] == ':':
        clean_time = "0" + clean_time  # format 9:00 -> 09:00

    auto_label = label.strip() if label else f"{clean_time} Daily {category} Drill"
    # 📅 exact TO-date given directly → honor it (and switch off life-long mode)
    calculated_end_date = (end_date or "").strip()
    start_clean = (start_date or "").strip()
    today_str = datetime.now().strftime("%Y-%m-%d")
    if start_clean and start_clean <= today_str:
        start_clean = ""  # starting today/past = starts immediately
    if calculated_end_date:
        auto_mode = False
        base = datetime.strptime(start_clean, "%Y-%m-%d") if start_clean else datetime.now()
        try:
            days_duration = max((datetime.strptime(calculated_end_date, "%Y-%m-%d") - base).days, 1)
        except Exception:
            pass
    elif days_duration > 0:
        base = datetime.strptime(start_clean, "%Y-%m-%d") if start_clean else datetime.now()
        calculated_end_date = (base + timedelta(days=int(days_duration))).strftime("%Y-%m-%d")

    if auto_mode or (days_duration == 0 and not calculated_end_date):
        mode_label = "♾️ Life-Long"
    else:
        mode_label = f"→ {calculated_end_date}" if calculated_end_date else f"{days_duration} Days Limited"
    if start_clean:
        mode_label = f"⏳ Starts {start_clean} {mode_label}"
    job = {
        "id": job_id,
        "time": clean_time,
        "label": auto_label,
        "target_group_ids": target_group_ids or [],
        "category": category or "ALL",
        "is_question": is_question,
        "questions_count": questions_count or 1,
        "telegram_channels": telegram_channels or [],
        "subjects": subjects or [],
        "weekdays": [int(d) for d in (weekdays or []) if str(d).isdigit() and 0 <= int(d) <= 6],
        "answer_delay_minutes": max(0, min(60, int(answer_delay_minutes or 5))),
        "mode": mode if mode in ("wa", "tg", "both") else "wa",
        "enabled": enabled,
        "auto_mode": bool(auto_mode),
        "days_duration": int(days_duration) if days_duration else 0,
        "end_date": calculated_end_date,
        "start_date": start_clean,
        "status": f"Active ({mode_label})",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_run": None,
        "total_dispatches": 0
    }
    jobs.append(job)
    save_schedules(jobs)
    return job


def get_scheduled_jobs() -> list:
    return load_schedules()


def toggle_scheduled_job(job_id: str) -> dict:
    jobs = load_schedules()
    target = None
    for j in jobs:
        if j.get("id") == job_id:
            j["enabled"] = not j.get("enabled", True)
            j["status"] = "Active (Always-On)" if j["enabled"] else "Paused"
            target = j
            break
    if target:
        save_schedules(jobs)
    return target


def update_scheduled_job(job_id: str, updates: dict) -> dict:
    """✏️ EDIT an existing schedule any time — time, polls count, duration
    (0 = LIFE-LONG, 30 = 1 month, 60 = 2 months...), subjects, targets."""
    jobs = load_schedules()
    target = None
    for j in jobs:
        if j.get("id") != job_id:
            continue
        if "time" in updates and str(updates["time"]).strip():
            t = str(updates["time"]).strip()
            if len(t) == 4 and t[1] == ":":
                t = "0" + t
            j["time"] = t
        if "label" in updates and str(updates["label"]).strip():
            j["label"] = str(updates["label"]).strip()
        if "questions_count" in updates:
            j["questions_count"] = max(1, min(int(updates["questions_count"] or 1), 20))
        if "subjects" in updates:
            j["subjects"] = [str(s).upper() for s in (updates["subjects"] or []) if s]
        if "category" in updates and updates["category"]:
            j["category"] = str(updates["category"])
        if "target_group_ids" in updates and isinstance(updates["target_group_ids"], list):
            j["target_group_ids"] = updates["target_group_ids"]
        if "telegram_channels" in updates and isinstance(updates["telegram_channels"], list):
            j["telegram_channels"] = updates["telegram_channels"]
        if "start_date" in updates:
            sd = str(updates["start_date"] or "").strip()
            today_s = datetime.now().strftime("%Y-%m-%d")
            j["start_date"] = "" if (not sd or sd <= today_s) else sd
        if "end_date" in updates and str(updates["end_date"] or "").strip():
            ed = str(updates["end_date"]).strip()
            j["end_date"] = ed
            j["auto_mode"] = False
            try:
                base = datetime.strptime(j.get("start_date") or datetime.now().strftime("%Y-%m-%d"), "%Y-%m-%d")
                j["days_duration"] = max((datetime.strptime(ed, "%Y-%m-%d") - base).days, 1)
            except Exception:
                pass
            j["status"] = f"Active (→ {ed})" if j.get("enabled", True) else "Paused"
        elif "days_duration" in updates:
            days = max(0, int(updates["days_duration"] or 0))
            j["days_duration"] = days
            j["auto_mode"] = (days == 0)
            if days == 0:
                j["end_date"] = ""
                j["status"] = "Active (♾️ Life-Long)" if j.get("enabled", True) else "Paused"
            else:
                try:
                    base = datetime.strptime(j["start_date"], "%Y-%m-%d") if j.get("start_date") else datetime.now()
                except Exception:
                    base = datetime.now()
                j["end_date"] = (base + timedelta(days=days)).strftime("%Y-%m-%d")
                j["status"] = f"Active ({days} Days → {j['end_date']})" if j.get("enabled", True) else "Paused"
        target = j
        break
    if target:
        save_schedules(jobs)
    return target


def delete_scheduled_job(job_id: str) -> bool:
    jobs = load_schedules()
    before = len(jobs)
    jobs = [j for j in jobs if j.get("id") != job_id]
    save_schedules(jobs)
    return len(jobs) < before


def load_wa_registry() -> dict:
    default_cfg = {
        "groups": [
            {
                "id": "G_POLICE_TS_1",
                "name": "Telangana TS Police Constable & SI Hub",
                "jid": "120363012345678901@g.us",
                "category": "POLICE",
                "shift": "ALL_DAY",
                "active": True
            },
            {
                "id": "G_POLICE_AP_1",
                "name": "AP Police Civil & AR Aspirants 2026",
                "jid": "120363012345678902@g.us",
                "category": "POLICE",
                "shift": "EVENING",
                "active": True
            },
            {
                "id": "G_CENTRAL_SSC_1",
                "name": "SSC CGL / CHSL / MTS Central Exam Prep",
                "jid": "120363012345678903@g.us",
                "category": "SSC",
                "shift": "MORNING",
                "active": True
            },
            {
                "id": "G_RAILWAY_RRB_1",
                "name": "Railway RRB NTPC & Group D Warriors",
                "jid": "120363012345678904@g.us",
                "category": "RAILWAY",
                "shift": "ALL_DAY",
                "active": True
            },
            {
                "id": "G_BANKING_SBI_1",
                "name": "IBPS PO / SBI Clerk Banking Aspirants",
                "jid": "120363012345678905@g.us",
                "category": "BANKING",
                "shift": "MORNING",
                "active": True
            },
            {
                "id": "G_TSPSC_GRP2_1",
                "name": "TSPSC Group 2, 3 & 4 Mission 2026",
                "jid": "120363012345678906@g.us",
                "category": "TSPSC",
                "shift": "EVENING",
                "active": True
            }
        ],
        "gateway_url": "",
        "gateway_token": "",
        "anti_ban": {
            "enabled": True,
            "min_gap_sec": 20,
            "max_gap_sec": 30,
            "batch_pair_size": 2,
            "pair_pause_sec": 35,
            "answer_delay_sec": 45,
            "invisible_hash_jitter": True
        },
        "logs": []
    }
    if WA_CONFIG_FILE.exists():
        try:
            loaded = load_json(WA_CONFIG_FILE, {})
            if "groups" in loaded and loaded["groups"]:
                # Ensure shift and category keys exist
                for g in loaded["groups"]:
                    g.setdefault("shift", "ALL_DAY")
                    g.setdefault("category", channel_router.detect_exam_base(g.get("name", "")))
                loaded.setdefault("anti_ban", default_cfg["anti_ban"])
                return loaded
        except Exception:
            pass
    save_json_atomic(WA_CONFIG_FILE, default_cfg)
    return default_cfg


def save_wa_registry(d: dict):
    save_json_atomic(WA_CONFIG_FILE, d)


def add_group(name: str, jid: str, category: str = "AUTO", shift: str = "ALL_DAY", group_type: str = "EXAM_SPECIFIC") -> dict:
    d = load_wa_registry()
    if category == "AUTO" or not category:
        category = channel_router.detect_exam_base(name)
    gid = f"G_{len(d.get('groups', [])) + 1}_{int(time.time()) % 1000}"
    new_g = {
        "id": gid,
        "name": name.strip(),
        "jid": jid.strip(),
        "category": category,
        "group_type": group_type or "EXAM_SPECIFIC",
        "shift": shift or "ALL_DAY",
        "active": True,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    d.setdefault("groups", []).append(new_g)
    save_wa_registry(d)
    return new_g


def update_group(gid: str, updates: dict) -> dict:
    d = load_wa_registry()
    target = None
    for g in d.get("groups", []):
        if g.get("id") == gid:
            g.update(updates)
            target = g
            break
    if target:
        save_wa_registry(d)
    return target


def remove_group(gid: str) -> bool:
    d = load_wa_registry()
    before = len(d.get("groups", []))
    d["groups"] = [g for g in d.get("groups", []) if g.get("id") != gid]
    save_wa_registry(d)
    return len(d["groups"]) < before


# =====================================================================
# ➕ QUICK ADD NEW GROUPS — paste invite links, bot auto-joins via bridge
# Accepted line formats:
#   https://chat.whatsapp.com/XXXXX
#   Group Name | https://chat.whatsapp.com/XXXXX
#   Group Name | https://chat.whatsapp.com/XXXXX | CATEGORY
# =====================================================================
def quick_add_groups(raw_text: str) -> dict:
    results = {"ok": True, "added": [], "joined": 0, "failed": [], "total_lines": 0}
    connected = bridge_is_connected()
    d = load_wa_registry()
    existing_jids = {g.get("jid") for g in d.get("groups", [])}

    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        results["total_lines"] += 1
        parts = [p.strip() for p in line.split("|")]
        name_hint, link, category = "", "", "AUTO"
        for p in parts:
            if "chat.whatsapp.com" in p or p.endswith("@g.us"):
                link = p
            elif p.upper() in ("POLICE", "TSPSC", "APPSC", "SSC", "RAILWAY", "BANKING",
                               "TET_DSC", "GENERAL", "CURRENT", "DEFENCE"):
                category = p.upper()
            elif p:
                name_hint = p
        if not link:
            results["failed"].append({"line": line, "error": "no WhatsApp link/JID found"})
            continue

        jid, name, participants, joined = link, name_hint or link, 0, False
        # If the bridge is live and it's an invite link → bot JOINS the group itself
        if connected and "chat.whatsapp.com" in link:
            jr = _bridge_call("/join", payload={"link": link}, timeout=45)
            if jr and jr.get("ok"):
                jid = jr.get("jid", link)
                name = name_hint or jr.get("name", link)
                participants = jr.get("participants", 0)
                joined = bool(jr.get("joined"))
            elif jr:
                results["failed"].append({"line": line, "error": jr.get("error", "join failed")})
                continue

        if jid in existing_jids:
            results["failed"].append({"line": line, "error": f"already added ({name})"})
            continue

        if category == "AUTO":
            category = channel_router.detect_exam_base(name)
        new_g = {
            "id": f"G_{len(d.get('groups', [])) + 1}_{int(time.time() * 1000) % 10000}",
            "name": name,
            "jid": jid,
            "category": category,
            "shift": "ALL_DAY",
            "active": True,
            "participants": participants,
            "real": joined,
        }
        d.setdefault("groups", []).append(new_g)
        existing_jids.add(jid)
        results["added"].append({"name": name, "jid": jid, "category": category, "joined": joined, "participants": participants})
        if joined:
            results["joined"] += 1

    save_wa_registry(d)
    return results


# =====================================================================
# 🎯 SUBJECT-WISE POLL SELECTION — top-level exam/subject targeting
# =====================================================================
SUBJECT_TOPIC_MAP = {
    "MATHS": ["interest", "average", "percentage", "ratio", "time-work", "number series",
              "profit", "partnership", "mensuration", "algebra", "speed", "train", "boat",
              "mixture", "lcm", "hcf", "fraction", "age"],
    "REASONING": ["coding", "symbol", "calendar", "ranking", "clock", "analogy",
                  "blood relation", "direction", "series", "syllogism", "puzzle",
                  "odd one", "seating", "venn"],
    "GK": ["gk", "history", "geography", "polity", "economy", "constitution",
           "telangana", "andhra", "india", "static", "award", "sports", "culture"],
    "CURRENT": ["current", "affairs", "news", "2025", "2026"],
    "ENGLISH": ["english", "vocabulary", "grammar", "synonym", "antonym", "idiom",
                "spelling", "sentence"],
    "SCIENCE": ["science", "physics", "chemistry", "biology", "tech", "computer"],
}


def pick_subject_questions(bank, category: str, n: int, subjects: list = None):
    """PYQ-quality pick, filtered to the admin-chosen subjects.
    Falls back gracefully: subject-filtered → category pool → CURRENT."""
    subjects = [s.upper() for s in (subjects or []) if s and s.upper() != "ALL"]
    if not subjects:
        return bank.pick(category, n)

    keywords = []
    for s in subjects:
        keywords.extend(SUBJECT_TOPIC_MAP.get(s, [s.lower()]))

    def _matches(q):
        topic = (q.get("topic") or "").lower()
        return any(k in topic for k in keywords)

    # Current Affairs is its own channel too
    pools = []
    try:
        pool = [q for q in bank.questions if q.get("channel") == category and _matches(q)]
        pools.append(pool)
        if "CURRENT" in subjects:
            pools.append([q for q in bank.questions if q.get("channel") == "CURRENT"])
        # widen across all channels if the category pool is thin
        if sum(len(p) for p in pools) < n:
            pools.append([q for q in bank.questions if _matches(q)])
    except Exception:
        return bank.pick(category, n)

    merged, seen = [], set()
    for pool in pools:
        random.shuffle(pool)
        for q in pool:
            qid = q.get("id") or id(q)
            if qid not in seen:
                seen.add(qid)
                merged.append(q)

    if len(merged) < n:
        for q in (bank.pick(category, n) or []):
            qid = q.get("id") or id(q)
            if qid not in seen:
                seen.add(qid)
                merged.append(q)

    # 🔁 NO-REPEAT SMART ROTATION: never-posted questions FIRST; already-sent
    # ones are used only as a fallback when the fresh pool runs dry.
    try:
        fresh, posted = [], []
        for q in merged:
            qch = q.get("channel", "CURRENT")
            if q.get("id") in set(bank.used.get(qch, [])):
                posted.append(q)
            else:
                fresh.append(q)
        merged = fresh + posted
    except Exception:
        pass

    return merged[:n] if merged else bank.pick(category, n)


def apply_stealth_jitter(text: str) -> str:
    """Inject zero-width invisible markers so each dispatch has a unique SHA-256 hash."""
    words = text.split(" ")
    out = []
    for w in words:
        out.append(w)
        if random.random() < 0.35:
            out.append(random.choice(ZERO_WIDTH_CHARS))
    return " ".join(out)


def build_question_only_post(
    q: dict,
    group_name: str,
    category: str,
    q_index: int = 1,
    total_q: int = 1,
    english_first: bool = True
) -> str:
    """
    Format bilingual poll question & dual English / Telugu options.
    If english_first is True:
      - Line 1: English question
      - Line 2: Telugu question
      - Options: English / Telugu
    If english_first is False (rotates every 5 groups):
      - Line 1: Telugu question
      - Line 2: English question
      - Options: Telugu / English
    """
    q_te = (q.get("q_te") or "").strip()
    q_en = (q.get("q_en") or "").strip()

    header = random.choice(HEADERS)
    lines = [f"{header} — *{category}*", f"📍 *Q {q_index}/{total_q}*"]
    if q.get("source") == "pyq" and q.get("exam"):
        lines.append(f"📜 *{q['exam']}*" + (f" · {q['year']}" if q.get("year") else "")
                     + (f" · {q['paper']}" if q.get("paper") else ""))
    lines.append("")

    if english_first:
        if q_en:
            lines.append(f"❓ *{q_en}*")
        if q_te and q_te != q_en:
            lines.append(f"   {q_te}")
        elif not q_en and q_te:
            lines.append(f"❓ *{q_te}*")
    else:
        if q_te:
            lines.append(f"❓ *{q_te}*")
        if q_en and q_en != q_te:
            lines.append(f"   {q_en}")
        elif not q_te and q_en:
            lines.append(f"❓ *{q_en}*")

    lines.append("")
    opts_en = q.get("options_en", [])
    opts_te = q.get("options_te", [])
    bullet_style = random.choice(BULLETS)

    max_len = max(len(opts_en), len(opts_te))
    for i in range(max_len):
        b = bullet_style[i] if i < len(bullet_style) else f"{i+1}"
        o_en = (opts_en[i] if i < len(opts_en) else "").strip()
        o_te = (opts_te[i] if i < len(opts_te) else "").strip()

        if o_en and o_te and o_en.lower() != o_te.lower():
            if english_first:
                lines.append(f"  *{b}*. {o_en} / {o_te}")
            else:
                lines.append(f"  *{b}*. {o_te} / {o_en}")
        elif o_en:
            lines.append(f"  *{b}*. {o_en}")
        elif o_te:
            lines.append(f"  *{b}*. {o_te}")

    lines.append("")
    lines.append("⏳ *ఆలోచించి సమాధానం ఇవ్వండి... Key & Explanation 60 సెకన్లలో క్రింద పోస్ట్ చేయబడుతుంది!*")
    bot_name = getattr(config, "BOT_USERNAME", "") or "StudentUpBot"
    lines.append(f"📲 లైవ్ ర్యాంక్ కోసం: t.me/{bot_name}")
    return apply_stealth_jitter("\n".join(lines))


def build_native_poll_payload(
    q: dict,
    category: str,
    q_index: int = 1,
    total_q: int = 1,
    english_first: bool = True
) -> dict:
    """Build a REAL tappable WhatsApp poll (sent by the Baileys bridge).
    WhatsApp limits: poll name ≤ 255 chars, ≤ 12 options, option ≤ 100 chars."""
    q_en = (q.get("q_en") or "").strip()
    q_te = (q.get("q_te") or "").strip()

    parts = [f"🎯 Q {q_index}/{total_q} • {category}"]
    if q.get("source") == "pyq" and q.get("exam"):
        parts.append(f"📜 {q['exam']}" + (f" · {q['year']}" if q.get("year") else "")
                     + (f" · {q['paper']}" if q.get("paper") else ""))
    primary, secondary = (q_en, q_te) if english_first else (q_te, q_en)
    if primary:
        parts.append(primary)
    if secondary and secondary != primary:
        parts.append(secondary)
    name = "\n".join(parts)[:250]

    opts_en = q.get("options_en", []) or []
    opts_te = q.get("options_te", []) or []
    options = []
    for i in range(max(len(opts_en), len(opts_te))):
        o_en = (opts_en[i] if i < len(opts_en) else "").strip()
        o_te = (opts_te[i] if i < len(opts_te) else "").strip()
        if o_en and o_te and o_en.lower() != o_te.lower():
            combined = f"{o_en} / {o_te}" if english_first else f"{o_te} / {o_en}"
        else:
            combined = o_en or o_te
        if combined:
            options.append(combined[:95])
    # WhatsApp rejects duplicate poll options — de-duplicate while keeping order
    seen, unique = set(), []
    for o in options:
        key = o.lower()
        if key not in seen:
            seen.add(key)
            unique.append(o)
    if len(unique) < 2:
        return None
    return {"name": name, "options": unique[:12]}


def build_answer_key_post(
    q: dict,
    category: str,
    q_index: int = 1,
    english_first: bool = True
) -> str:
    ans_idx = int(q.get("answer_index", 0))
    ans_letter = ["A", "B", "C", "D", "E"][ans_idx] if ans_idx < 5 else str(ans_idx + 1)
    expl_te = (q.get("explanation_te") or "").strip()
    expl_en = (q.get("explanation_en") or "").strip()

    lines = [
        f"✅ *OFFICIAL ANSWER KEY & EXPLANATION (Q {q_index})*",
        "",
        f"🏆 *Correct Option*: *Option {ans_letter}*",
    ]

    if english_first:
        if expl_en:
            lines.append(f"💡 *Explanation*: {expl_en}")
        if expl_te and expl_te != expl_en:
            lines.append(f"📖 *వివరణ*: {expl_te}")
    else:
        if expl_te:
            lines.append(f"📖 *వివరణ*: {expl_te}")
        if expl_en and expl_en != expl_te:
            lines.append(f"💡 *Explanation*: {expl_en}")

    lines.append("")
    lines.append("— StudentUp Daily Verified Exam PYQ")
    return apply_stealth_jitter("\n".join(lines))


def _dispatch_raw(gateway_url: str, jid: str, text: str, attachment: str = "", poll: dict = None, bridge_url: str = None, mentions: list = None):
    """Send for real through the Baileys bridge. Order of preference:
    1. Local bridge (gateway/wa_bridge.js) — text, media URL and native polls.
    2. Legacy external gateway webhook (if gateway_url configured).
    3. Otherwise honestly report that nothing was sent (no fake OK)."""
    payload = {"jid": jid, "text": text}
    if attachment:
        payload["attachment"] = attachment
    if poll:
        payload["poll"] = poll

    if mentions:
        payload["mentions"] = list(mentions)
    res = _bridge_call("/send", payload=payload, timeout=60, base_url=bridge_url)
    if res is not None:
        if res.get("ok"):
            if poll and res.get("poll_id"):
                _LAST_WA_POLL[str(jid)] = res["poll_id"]   # 🏆 vote tracking
            return True, f"✅ REAL SEND via WhatsApp Web ({'+'.join(res.get('sent', []))})"
        return False, f"Bridge error: {res.get('error', 'unknown')}"

    # Bridge not running — fall back to legacy external webhook gateway
    if gateway_url:
        try:
            legacy = {"recipient": jid, "message": text}
            if attachment:
                legacy["attachment"] = attachment
            req_data = json.dumps(legacy).encode("utf-8")
            req = urllib.request.Request(gateway_url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as r:
                return True, f"HTTP {r.status} (external gateway)"
        except Exception as e:
            return False, str(e)

    return False, "NOT SENT — WhatsApp bridge offline (start: cd gateway && node wa_bridge.js)"


_BROADCAST_LOCK = threading.Lock()   # 🔒 oka broadcast at a time (busy = honest)


def _log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    formatted = f"[{ts}] {msg}"
    EXEC_STATE["logs"].append(formatted)
    if len(EXEC_STATE["logs"]) > 200:
        EXEC_STATE["logs"].pop(0)


def start_interleaved_broadcast(
    target_category: str = "ALL",
    shift_filter: str = "ALL",
    target_group_ids: list = None,
    is_question: bool = True,
    questions_per_group: int = 5,
    custom_message: str = "",
    attachment_url: str = "",
    two_phase_answer: bool = True,
    delay_min: int = 60,
    delay_max: int = 80,
    subjects: list = None
) -> dict:
    """
    Launch asynchronous non-blocking broadcast worker with Advanced Anti-Ban Engine:
    - 40-60 seconds random jitter gap between individual polls in a group.
    - 5 polls completed per group before rotating to the next group.
    - After every batch of 5 groups completed, applies 60-90 seconds cooldown rest.
    - Language alternation: English First for groups 1-5, Telugu First for groups 6-10, and rotates.
    - Options formatted dual bilingual: English / Telugu (or Telugu / English).
    """
    global EXEC_STATE
    # ⏱️ OWNER RULE: WhatsApp gaps eppudu 60-80s floor — kindaki vellakudadhu
    delay_min = max(60, int(delay_min or 60))
    delay_max = max(delay_min, int(delay_max or 80))
    if not _BROADCAST_LOCK.acquire(blocking=False):
        return {"ok": False, "busy": True,
                "message": "Another broadcast is already running — will retry when free."}
    if EXEC_STATE["running"]:
        _BROADCAST_LOCK.release()
        return {"ok": False, "busy": True,
                "message": "Another broadcast process is currently running."}

    reg = load_wa_registry()
    groups = [g for g in reg.get("groups", []) if g.get("active")]

    # If specific group IDs are selected, prioritize them directly!
    if target_group_ids and len(target_group_ids) > 0:
        target_set = set(target_group_ids)
        groups = [g for g in groups if g.get("id") in target_set or g.get("jid") in target_set]
    else:
        # Apply Category filter
        if target_category != "ALL":
            groups = [g for g in groups if g.get("category", "").upper() == target_category.upper()]

        # Apply Shift filter (MORNING, EVENING, ALL_DAY)
        if shift_filter != "ALL":
            groups = [g for g in groups if g.get("shift", "ALL_DAY") in (shift_filter, "ALL_DAY")]

    if not groups:
        if _BROADCAST_LOCK.locked():
            try:
                _BROADCAST_LOCK.release()
            except RuntimeError:
                pass
        return {"ok": False, "message": f"No active groups found for the selected filter."}

    total_polls_to_send = len(groups) * (questions_per_group or 1)

    # 📊 record in broadcast history (analytics tab)
    try:
        from core import broadcast_log
        broadcast_log.log_event(
            "whatsapp",
            f"{len(groups)} group(s) · {target_category}",
            total_polls_to_send,
            subjects=subjects,
            dry=not bridge_is_connected(),
            note="interleaved anti-ban",
        )
    except Exception:
        pass

    EXEC_STATE["running"] = True
    EXEC_STATE["task_id"] = f"task_{int(time.time())}"
    EXEC_STATE["progress"] = 0
    EXEC_STATE["total"] = total_polls_to_send
    EXEC_STATE["logs"] = []
    EXEC_STATE["stop_requested"] = False

    def _worker():
        global EXEC_STATE
        try:
            _log(f"🛡️ Advanced Anti-Ban Dispatcher Started.")
            _log(f"   Target: {len(groups)} groups | Exam: {target_category} | {questions_per_group} polls/group")
            _log(f"   Anti-Ban Timing: {delay_min}-{delay_max}s random jitter between polls; 60-90s rest after every 5 groups.")
            _log(f"   Language Rotation: Alternate English/Telugu header & bilingual dual options every 5 groups.")

            bank = Bank()
            gw = reg.get("gateway_url", "").strip()

            # REAL MODE: when the Baileys bridge is connected we are posting to
            # real WhatsApp groups → honour the FULL anti-ban delays. In
            # simulation/test mode (bridge offline) delays are capped short.
            real_mode = bridge_is_connected()
            if real_mode:
                _log("🟢 REAL WhatsApp Web session detected — full anti-ban timing engaged, native polls ON.")
            else:
                _log("⚪ Bridge offline — DRY-RUN mode (nothing actually sent, delays shortened).")

            pacing_begin_broadcast()

            _log(f"⏱️ Anti-Ban Timing: {delay_min}-{delay_max}s between polls (adaptive pacing ON)")

            def _anti_ban_sleep(seconds: float, media: bool = False):
                pacing_sleep(0 if media else seconds, media=media,
                             real_mode=real_mode)

            media_sleep_fn=lambda: _anti_ban_sleep(0, media=True)

            completed_groups_count = 0

            for grp_idx, grp in enumerate(groups):
                if EXEC_STATE["stop_requested"]:
                    _log("🛑 Broadcast stopped by admin.")
                    break
                if in_wa_quiet():
                    # 🌙 Quiet hours (22:00–07:00) vachayi — mid-send graceful stop
                    quiet_until = wa_quiet_until()
                    _log(f"🌙 Quiet hours (22:00–07:00) vachayi — mid-send graceful stop. Next send after {quiet_until:%d %b %H:%M}")
                    break

                cat = grp.get("category", "CURRENT")
                g_type = grp.get("group_type", "EXAM_SPECIFIC")
                _grp_sent = _grp_failed = 0
                EXEC_STATE["current_group"] = grp["name"]

                # Language rotation: First 5 groups English first, next 5 groups Telugu first
                batch_number = grp_idx // 5
                english_first = (batch_number % 2 == 0)
                lang_label = "🇬🇧 English First" if english_first else "🇮🇳 Telugu First"

                _log(f"📢 [{grp_idx + 1}/{len(groups)}] Group '{grp['name']}' [{cat}] | Style: {lang_label}")

                # Select question pool for this group
                if g_type == "GENERAL" or cat.upper() in ("GENERAL", "AUTO", ""):
                    gen_pool = ["TSPSC", "SSC", "BANKING", "CURRENT", "POLICE"]
                    chosen_cat = random.choice(gen_pool)
                    pool_label = f"Universal Aptitude/GK ({chosen_cat})"
                    qs = pick_subject_questions(bank, chosen_cat, questions_per_group or 5, subjects)
                else:
                    chosen_cat = cat
                    pool_label = cat
                    qs = pick_subject_questions(bank, cat, questions_per_group or 5, subjects)

                if not qs:
                    qs = bank.pick("CURRENT", questions_per_group or 5) or bank.pick("TSPSC", questions_per_group or 5)

                q_count = len(qs) if is_question else 1

                for q_idx in range(q_count):
                    if EXEC_STATE["stop_requested"]:
                        break
                    # 🔀 anti-fingerprint: group+question+day parity
                    english_first = wa_english_first(grp_idx, q_idx)
                    if in_wa_quiet():
                        quiet_until = wa_quiet_until()
                        _log(f"🌙 Quiet hours (22:00–07:00) vachayi — mid-send graceful stop. Next send after {quiet_until:%d %b %H:%M}")
                        EXEC_STATE["stop_requested"] = True
                        break

                    EXEC_STATE["current_stage"] = f"Posting Poll {q_idx + 1}/{q_count}"

                    poll_payload = None
                    if is_question and qs:
                        q = qs[q_idx]
                        txt = build_question_only_post(
                            q, grp["name"], chosen_cat,
                            q_index=q_idx + 1,
                            total_q=q_count,
                            english_first=english_first
                        )
                        # Native tappable WhatsApp poll (real vote counts, anti-ban friendly: 1 message)
                        poll_payload = build_native_poll_payload(
                            q, chosen_cat,
                            q_index=q_idx + 1, total_q=q_count,
                            english_first=english_first
                        )
                    else:
                        txt = apply_stealth_jitter(custom_message)

                    _log(f"   📤 Poll {q_idx + 1}/{q_count} -> Dispatched: {pool_label}")
                    if is_question and qs and not attachment_url:
                        # 📲 Smart delivery: channel=emoji text-poll, group=native poll
                        res = deliver_whatsapp_question(
                            bridge_for_group(grp), grp["jid"], q,
                            grp.get("category", "CURRENT"),
                            q_index=q_idx + 1, total_q=q_count,
                            english_first=english_first,
                            answer_delay_sec=random.uniform(delay_min, delay_max),
                            sleep_fn=_anti_ban_sleep)
                        _send_ok = isinstance(res, dict) and \
                            res.get("status") in ("sent", "dry")
                        pacing_note_result(_send_ok, res)
                        if _send_ok:
                            _grp_sent += 1
                        else:
                            _grp_failed += 1
                        EXEC_STATE["progress"] += 1
                        continue
                    _send_ok, res = _dispatch_raw(gw, grp["jid"], txt, attachment=attachment_url, poll=poll_payload)
                    pacing_note_result(_send_ok, res)
                    if not _send_ok and poll_payload:
                        # Poll rejected (e.g. announcement-only community) → retry as plain text
                        _send_ok, res = _dispatch_raw(gw, grp["jid"], txt, attachment=attachment_url)
                        pacing_note_result(_send_ok, res)
                    if attachment_url:
                        media_sleep_fn()  # 📎 extra breathing room after media sends
                    _log(f"      -> Gateway Status: {res}")

                    EXEC_STATE["progress"] += 1

                    # If more polls remaining for this group, wait 40-60s random gap
                    if q_idx < q_count - 1 and not EXEC_STATE["stop_requested"]:
                        poll_gap = random.uniform(delay_min, delay_max)
                        _log(f"   ⏳ Natural Human Anti-Ban Gap: waiting {poll_gap:.1f}s before next poll...")
                        _anti_ban_sleep(poll_gap)

                # 🩺 per-group delivery health (dashboard Group Health panel)
                _h = group_health_record(grp["jid"], sent=_grp_sent,
                                         failed=_grp_failed,
                                         name=grp.get("name", ""))
                _log(f"🩺 Group health: {grp.get('name')} — {_h.get('status', 'weak')} ({_h.get('rate', 0)}% · sent {_grp_sent} · failed {_grp_failed})")

                completed_groups_count += 1

                # If this group finished, check if 5 groups completed: apply 60-90s batch cooldown
                if not EXEC_STATE["stop_requested"] and grp_idx < len(groups) - 1:
                    if completed_groups_count % 5 == 0:
                        # Batch rest scales with the admin-chosen gap (longer gaps → longer rests)
                        batch_cooldown = random.uniform(max(60, delay_max), max(90, delay_max * 1.5))
                        _log(f"☕ 5 Groups Completed! Anti-Ban Cooldown: pausing {batch_cooldown:.1f}s before next batch...")
                        _anti_ban_sleep(batch_cooldown if real_mode else 3.0)
                    else:
                        # Inter-group safety pause
                        group_pause = random.uniform(5, 12)
                        _log(f"   🔄 Group completed. Switching to next group in {group_pause:.1f}s...")
                        _anti_ban_sleep(group_pause if real_mode else 1.0)

            _log(f"🎉 Anti-Ban Dispatch Successfully Completed across {completed_groups_count} groups ({EXEC_STATE['progress']} polls)!")
        except Exception as ex:
            _log(f"❌ Error during broadcast: {ex}")
        finally:
            EXEC_STATE["running"] = False
            EXEC_STATE["current_group"] = ""
            EXEC_STATE["current_stage"] = "Idle"
            try:
                _BROADCAST_LOCK.release()
            except RuntimeError:
                pass

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    return {"ok": True, "message": f"Anti-Ban broadcast started for {len(groups)} groups with 5 polls rotation."}


def stop_broadcast() -> dict:
    global EXEC_STATE
    if not EXEC_STATE["running"]:
        return {"ok": False, "message": "No broadcast running."}
    EXEC_STATE["stop_requested"] = True
    return {"ok": True, "message": "Stop signal sent to broadcast pipeline."}


def get_broadcast_status() -> dict:
    st = dict(EXEC_STATE)
    snap = pacing_snapshot()
    st["pacing"] = {
        "multiplier": snap["risk_multiplier"],
        "fatigue": snap["fatigue"],
        "mode": snap["mode"],
        "consecutive_fails": snap["consecutive_fails"],
        "crawl_until": snap["crawl_until"] or None,
    }
    return st


# =====================================================================
# BACKGROUND AUTONOMOUS SCHEDULER & HEARTBEAT ENGINE
# Runs 24x7 in a persistent detached daemon thread:
# 1. Checks every 20 seconds against current server time (HH:MM).
# 2. Automatically launches interleaved quiz rounds for scheduled jobs.
# 3. Maintains active keepalive heartbeat for linked WhatsApp session.
# =====================================================================
_SCHEDULER_RUNNING = False
_LAST_TRIGGERED_MIN = {}
_PENDING_WA = {}          # 🔁 busy-aina WA jobs — next tick retry
_LAST_BACKUP_DAY = [""]  # 🗄️ daily auto-backup gate
_LAST_GUARDIAN_CHECK = [0.0]  # 🐶 connection guardian gate (every 2 min)


def _connection_guardian():
    """🐶 Dashboard-side guardian: if the bridge has a saved WhatsApp session
    but is sitting disconnected, kick it back alive automatically.
    Combined with the bridge's own watchdog + backoff reconnect, one scan = forever connected."""
    import time as _t
    if _t.time() - _LAST_GUARDIAN_CHECK[0] < 120:
        return
    _LAST_GUARDIAN_CHECK[0] = _t.time()
    st = _bridge_call("/status", timeout=6)
    if not st:
        return  # bridge process down — systemd/start_all.sh will restart it
    if st.get("has_saved_session") and not st.get("connected") and \
            st.get("status") not in ("connecting", "qr_ready", "code_ready"):
        _log("🐶 Guardian: WhatsApp session saved but disconnected — auto-reviving...")
        _bridge_call("/reconnect", payload={}, timeout=10)


def start_scheduler_daemon():
    global _SCHEDULER_RUNNING
    if _SCHEDULER_RUNNING:
        return
    _SCHEDULER_RUNNING = True

    def _loop():
        while True:
            try:
                now_str = datetime.now().strftime("%H:%M")
                sess = load_session()
                sess["last_heartbeat"] = datetime.now().strftime("%H:%M:%S")
                save_session(sess)

                # 🐶 keep WhatsApp link alive forever (checks every 2 min)
                try:
                    _connection_guardian()
                except Exception:
                    pass

                today_str = datetime.now().strftime("%Y-%m-%d")

                # 🗄️ once-a-day automatic full backup (keeps last 7)
                if _LAST_BACKUP_DAY[0] != today_str:
                    _LAST_BACKUP_DAY[0] = today_str
                    try:
                        from core import backup
                        res = backup.make_backup()
                        if res.get("created"):
                            _log(f"🗄️ Daily auto-backup saved: {res.get('file')} ({res.get('files')} files)")
                    except Exception:
                        pass

                # 🔁 pending WA retries (busy valla aagipoyina jobs)
                if _PENDING_WA and not _BROADCAST_LOCK.locked():
                    for _pjid, _pj in list(_PENDING_WA.items()):
                        _PENDING_WA.pop(_pjid, None)
                        _log(f"🔁 Pending retry: relaunching '{_pj.get('label', _pjid)}'")
                        _r = start_interleaved_broadcast(
                            target_category=_pj.get("category", "ALL"),
                            target_group_ids=_pj.get("target_group_ids", []),
                            is_question=_pj.get("is_question", True),
                            questions_per_group=_pj.get("questions_count", 5),
                            two_phase_answer=True, delay_min=60, delay_max=80,
                            subjects=_pj.get("subjects") or None)
                        if _r.get("busy"):
                            _PENDING_WA[_pjid] = _pj
                        break

                jobs = load_schedules()
                for j in jobs:
                    if not j.get("enabled", True):
                        continue
                    # ⏳ FROM-date: not started yet → wait silently
                    if j.get("start_date") and today_str < j["start_date"]:
                        continue
                    # Check end_date expiration if auto_mode is false and end_date set
                    end_d = j.get("end_date")
                    if end_d and not j.get("auto_mode", True) and today_str > end_d:
                        j["enabled"] = False
                        j["status"] = "Completed (Period Ended)"
                        save_schedules(jobs)
                        continue

                    job_time = j.get("time", "").strip()
                    jid = j.get("id")
                    if _slot_due(job_time, today_str, datetime.now(), j.get("last_run", "")) and _LAST_TRIGGERED_MIN.get(jid) != now_str:
                        if not _weekday_ok(j):
                            continue    # ee weekday job kadhu — silent skip
                        _LAST_TRIGGERED_MIN[jid] = now_str
                        j["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        j["total_dispatches"] = j.get("total_dispatches", 0) + 1
                        save_schedules(jobs)
                        _log(f"⏰ Auto-Scheduler Triggered: Launching '{j.get('label', jid)}' ({job_time})!")
                        jmode = j.get("mode", "wa")
                        jsubjects = j.get("subjects") or None

                        # 📢 TELEGRAM AUTO-PILOT — instant posts, no gaps (official Bot API)
                        if jmode in ("tg", "both") and j.get("telegram_channels"):
                            try:
                                from core import poll_dispatch
                                for _chk in j.get("telegram_channels", []):
                                    poll_dispatch.post_channel_polls(
                                        _chk,
                                        count=j.get("questions_count", 1),
                                        subjects=jsubjects,
                                        source="scheduler",
                                    )
                            except Exception as _e:
                                _log(f"   [auto-pilot] telegram leg note: {_e}")

                        # 🛡️ WHATSAPP leg — anti-ban interleaved with smart gaps
                        _gate = pacing_gate() if jmode in ("wa", "both") else {"allowed": True}
                        if jmode in ("wa", "both") and not _gate.get("allowed", True):
                            _PENDING_WA[jid] = {**j, "crawl_until": _gate.get("crawl_until")}
                            _log(f"🚦 Pacing CRAWL — '{j.get('label', jid)}' defer (crawl_until {_gate.get('crawl_until')})")
                        elif jmode in ("wa", "both"):
                            res = start_interleaved_broadcast(
                                target_category=j.get("category", "ALL"),
                                target_group_ids=j.get("target_group_ids", []),
                                is_question=j.get("is_question", True),
                                questions_per_group=j.get("questions_count", 5),
                                two_phase_answer=True,
                                delay_min=60,
                                delay_max=80,
                                subjects=jsubjects,
                            )
                            if res.get("busy"):
                                # 🔁 busy = malli try — set chesina time miss avvakudadhu
                                _PENDING_WA[jid] = dict(j)
                                _log("⏳ Broadcast busy — job pending, will retry next tick.")
            except Exception:
                pass
            time.sleep(20)

    th = threading.Thread(target=_loop, daemon=True)
    th.start()


# Auto-start daemon on module import
start_scheduler_daemon()


# =====================================================================
# 🚀 SCALE PACK — Adaptive Anti-Ban pacing · WA winners · bridge pool
# · retry queue (Reliability + Scale rounds; tests ni spec ga rebuild)
# =====================================================================
_PACE = {"mult": 1.0, "fails": 0, "crawl_until": 0.0, "begin": None}
_LAST_WA_POLL = {}
WA_HOF_FILE = config.DATA / "wa_hall_of_fame.json"
WA_RETRY_FILE = config.DATA / "wa_retry_queue.json"


def reset_pacing_state():
    _PACE.update({"mult": 1.0, "fails": 0, "crawl_until": 0.0, "begin": None})


def pacing_begin_broadcast(now=None):
    _PACE["begin"] = time.time() if now is None else float(now)


def _pace_fatigue(now):
    if _PACE.get("begin") is None:
        return 1.0
    hrs = max(0.0, (float(now) - _PACE["begin"]) / 3600.0)
    return min(1.35, 1.0 + 0.12 * hrs)          # +12%/hour, cap +35%


def pacing_snapshot(now=None):
    now = time.time() if now is None else float(now)
    crawling = now < _PACE["crawl_until"]
    mode = "CRAWL" if crawling else ("CAUTIOUS" if _PACE["mult"] > 1.0 else "NORMAL")
    return {"risk_multiplier": round(_PACE["mult"], 2), "mode": mode,
            "consecutive_fails": _PACE["fails"],
            "crawl_until": _PACE["crawl_until"], "fatigue": _pace_fatigue(now)}


def pacing_note_result(ok, msg="", now=None):
    """Send result batti risk adjust: fail +0.45 (cap x2.5), ban signal
    → 30-min CRAWL (x3.0), success −0.15 relax (floor x1.0 — eppudu
    base gap kanna speed avadu, owner rule)."""
    now = time.time() if now is None else float(now)
    if _PACE["crawl_until"] and now > _PACE["crawl_until"]:
        _PACE["crawl_until"] = 0.0
        _PACE["mult"] = min(_PACE["mult"], 2.35)   # crawl tarvatha cautious ceiling
    if ok:
        _PACE["fails"] = 0
        if now >= _PACE["crawl_until"]:
            _PACE["mult"] = max(1.0, _PACE["mult"] - 0.15)
    else:
        _PACE["fails"] += 1
        m = str(msg or "").lower()
        if any(k in m for k in ("block", "forbidden", "403", "ban",
                                "suspend", "spam", "restrict")):
            _PACE["mult"] = 3.0
            _PACE["crawl_until"] = now + 1800
        else:
            _PACE["mult"] = min(2.5, _PACE["mult"] + 0.45)
    return pacing_snapshot(now)


def pacing_gate(now=None):
    """🚦 Send cheyyacha leda: CRAWL lo wait, migithavi allow."""
    now = time.time() if now is None else float(now)
    snap = pacing_snapshot(now)
    crawl_until = _PACE["crawl_until"] or 0.0
    allowed = now >= crawl_until
    return {"allowed": allowed, "mode": snap["mode"],
            "multiplier": snap["risk_multiplier"], "fatigue": snap["fatigue"],
            "wait_seconds": 0.0 if allowed else round(crawl_until - now, 1),
            "crawl_until": crawl_until or None,
            "consecutive_fails": snap["consecutive_fails"]}


def pacing_plan(base_gap, media=False, now=None, rng=None):
    now = time.time() if now is None else float(now)
    rng = rng or random
    snap = pacing_snapshot(now)
    sleep = float(base_gap) * snap["risk_multiplier"] * snap["fatigue"]
    media_extra = float(rng.uniform(2, 5)) if media else 0.0
    interruption = float(rng.uniform(120, 300)) if rng.random() < 0.04 else 0.0
    return {"sleep_seconds": sleep + media_extra + interruption,
            "media_extra_seconds": media_extra,
            "interruption_seconds": interruption,
            "risk_multiplier": snap["risk_multiplier"], "mode": snap["mode"],
            "fatigue": snap["fatigue"]}


def pacing_sleep(base_gap, real_mode=True, media=False, sleep_fn=None,
                 rng=None, now=None):
    """Dry/test mode lo garijalo 2s — tests fast ga untayi."""
    plan = pacing_plan(base_gap, media=media, now=now, rng=rng)
    planned = plan["sleep_seconds"]
    actual = planned if real_mode else min(planned, 2.0)
    (sleep_fn or time.sleep)(actual)
    plan["planned_seconds"] = planned
    plan["slept_seconds"] = actual
    return plan


def _js_weekday(dt):
    """JS getDay() convention: Sunday=0 … Saturday=6."""
    return (dt.weekday() + 1) % 7


def _weekday_ok(job, dt):
    days = (job or {}).get("weekdays")
    if not days:
        return True
    return _js_weekday(dt) in [int(x) for x in days]


def is_wa_channel(jid) -> bool:
    return bool(jid) and str(jid).strip().endswith("@newsletter")


def _phone_of(jid) -> str:
    return str(jid or "").split("@")[0].split(":")[0]


def tally_wa_round(polls, results):
    """Bridge poll-results → per-voter correct count + standings."""
    per = {}
    for p in polls or []:
        res = (results or {}).get(p.get("poll_id")) or {}
        for jid, ch in (res.get("voters") or {}).items():
            s = per.setdefault(str(jid), {"correct": 0, "answered": 0})
            s["answered"] += 1
            if ch == p.get("correct"):
                s["correct"] += 1
    standings = sorted(((j, s["correct"]) for j, s in per.items()),
                       key=lambda x: -x[1])
    return {"players": len(per), "standings": standings,
            "total": len(polls or []), "scores": per}


def render_wa_winners(title, polls, tally) -> str:
    letters = "ABCDE"
    key = " ".join(f"{i + 1}.{letters[int(p.get('correct', 0))]}"
                   for i, p in enumerate(polls or []))
    total = tally.get("total") or len(polls or [])
    standings = tally.get("standings") or []
    shown = standings[:5]
    lines = [f"✅ *Answer Key — {title}*", f"*{key}*", "",
             "🎉 *Congrats Top Scorers!*"]
    distinct = sorted({sc for _j, sc in standings}, reverse=True)

    def _medal(score):
        rank = distinct.index(score) + 1 if score in distinct else 9
        return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "🏅")

    for jid, sc in shown:
        lines.append(f"{_medal(sc)} @{_phone_of(jid)} — {sc}/{total}")
    rest = standings[5:]
    if shown and rest:
        tail = sum(1 for _j, sc in rest if sc == shown[-1][1] and sc > 0)
        if tail:
            lines.append(f"🤝 మరో {tail} మంది కూడా {shown[-1][1]}/{total} score!")
    tot_correct = sum(sc for _j, sc in standings)
    denom = max(1, tally.get("players", 0) * max(1, total))
    lines.append(f"👥 {tally.get('players', 0)} players · 🎯 {round(100 * tot_correct / denom)}% sariyina answers")
    lines.append("📤 *Share with friends!*")
    return "\n".join(lines)


def _hof_add(jids):
    try:
        data = load_json(WA_HOF_FILE, {})
        for jid in jids:
            ph = _phone_of(jid)
            row = data.setdefault(ph, {"phone": ph, "quizzes": 0})
            row["quizzes"] = int(row.get("quizzes", 0)) + 1
        save_json_atomic(WA_HOF_FILE, data)
    except Exception:
        pass


def wa_hall_of_fame(limit=10):
    try:
        data = load_json(WA_HOF_FILE, {})
    except Exception:
        data = {}
    rows = sorted(data.values(), key=lambda r: -int(r.get("quizzes", 0)))
    return rows[: int(limit or 10)]


def send_wa_winners(gateway_url, group, polls, title, sleep_fn=None):
    """🏆 Group ki winners (top-5 @mentions + key). Channel ki eppudu
    pampamu (mentions avavu — owner rule). Votes bridge /poll-results
    nunchi; bridge lekapothe honest ga skip."""
    jid = (group or {}).get("jid", "")
    if is_wa_channel(jid):
        return {"sent": False, "skipped": "channel"}
    results = {}
    for p in polls or []:
        res = _bridge_call(f"/poll-results?poll={p.get('poll_id')}", timeout=20)
        if res:
            results[p.get("poll_id")] = res
    tally = tally_wa_round(polls, results)
    if not tally["players"]:
        return {"sent": False, "skipped": "no_votes"}
    msg = render_wa_winners(title, polls, tally)
    mentions = [j for j, _sc in tally["standings"][:5]]
    # 🏆 Winners Certificate (English PNG) — render fail aithe text only
    cert_path = ""
    try:
        from core import certcard
        total = max(1, tally.get("total") or len(polls or []))
        _rows = [{"rank": i + 1, "name": f"@{_phone_of(j)}",
                  "score": f"{sc}/{total}",
                  "pct": int(round(100 * sc / total))}
                 for i, (j, sc) in enumerate(tally["standings"][:5])]
        _png = certcard.render_certificate(
            f"{title} — Winners", (group or {}).get("name", ""), _rows,
            footer="StudentUp · Daily Quiz Winners")
        if _png:
            _cf = config.DATA / "wa_winners_cert.png"
            _cf.write_bytes(_png)
            cert_path = str(_cf)
    except Exception:
        cert_path = ""
    ok, _info = _dispatch_raw(gateway_url, jid, msg, attachment=cert_path,
                              mentions=mentions)
    if ok:
        _hof_add(mentions)
    return {"sent": bool(ok), "certificate": bool(cert_path),
            "players": tally["players"]}


def deliver_whatsapp_question(gateway_url, jid, q, category, q_index=1,
                              total_q=1, english_first=True,
                              two_phase_answer=True, answer_delay_sec=45,
                              sleep_fn=None, collect=None):
    """📲 Okka question deliver: Channel (@newsletter) ki 👍❤️😂😮 emoji
    TEXT poll; Group ki native tappable poll. Phase-2 lo answer key.
    Vote tracking kosam poll_id capture (collect list unte)."""
    from core.content import build_reaction_text
    sleep_fn = sleep_fn or time.sleep
    out = {"sent_poll": False, "sent_key": False}
    if is_wa_channel(jid):
        text = build_reaction_text(q, {"name": category, "emoji": "🎯"},
                                   telugu_first=not english_first,
                                   position=f"Q {q_index}/{total_q}")
        ok, _info = _dispatch_raw(gateway_url, jid, text)
        out["sent_poll"] = bool(ok)
    else:
        payload = build_native_poll_payload(q, category, q_index, total_q,
                                            english_first)
        if payload is None:
            return out
        text = build_question_only_post(q, "", category, q_index, total_q,
                                        english_first)
        if two_phase_answer:
            text += (f"\n\n🔑 *Answer Key* {int(answer_delay_sec)} seconds "
                     "tarvatha vasthundi — mee answer vote cheyyandi!")
        ok, _info = _dispatch_raw(gateway_url, jid, text, poll=payload)
        if not ok:
            # native poll reject (announcement-only group etc) → text question
            ok, _info = _dispatch_raw(gateway_url, jid, text)
        out["sent_poll"] = bool(ok)
        if collect is not None and _LAST_WA_POLL.get(str(jid)):
            collect.append({"poll_id": _LAST_WA_POLL[str(jid)],
                            "qid": q.get("id"),
                            "correct": int(q.get("answer_index", 0))})
    if two_phase_answer and out["sent_poll"]:
        sleep_fn(answer_delay_sec or 0)
        key = build_answer_key_post(q, category, q_index, english_first)
        ok2, _i2 = _dispatch_raw(gateway_url, jid, key)
        out["sent_key"] = bool(ok2)
    return out


def _bridge_urls():
    raw = os.environ.get("WA_BRIDGE_URLS", "").strip()
    if raw:
        urls = [u.strip().rstrip("/") for u in raw.split(",") if u.strip()]
        if urls:
            return urls
    return [WA_BRIDGE_URL]


def bridge_for_group(group):
    urls = _bridge_urls()
    try:
        idx = int((group or {}).get("bridge") or 0)
    except Exception:
        idx = 0
    return urls[idx] if 0 <= idx < len(urls) else urls[0]


def bridges_status():
    out = []
    for url in _bridge_urls():
        res = _bridge_call("/status", base_url=url, timeout=10)
        row = {"url": url, "online": bool(res), "connected": False,
               "phone": "", "session": "", "groups_count": 0}
        if res:
            row.update({"connected": bool(res.get("connected")),
                        "phone": res.get("phone", ""),
                        "session": res.get("session", ""),
                        "groups_count": res.get("groups_count", 0)})
        out.append(row)
    return out


def enqueue_retry(jid, q, category, **kw):
    try:
        from core import flags as _fl
        if not _fl.enabled("wa_retry_queue"):
            return {"ok": False, "disabled": True}   # kill-switch OFF
    except Exception:
        pass
    try:
        data = load_json(WA_RETRY_FILE, {"items": []})
    except Exception:
        data = {"items": []}
    data.setdefault("items", []).append(
        {"jid": jid, "q": q, "category": category, "attempts": 0,
         "next_at": time.time()})
    save_json_atomic(WA_RETRY_FILE, data)
    try:
        from core import metrics as _mx
        _mx.incr("wa_retry_enqueued")
    except Exception:
        pass
    return {"ok": True, "queued": len(data.get("items", []))}


def process_retry_queue(now=None):
    """🔁 Due retries deliver; CRAWL lo attempts burn cheyyakunda defer.
    Backoff = 300s × attempts × risk multiplier (brain scales the wait)."""
    now = time.time() if now is None else float(now)
    try:
        data = load_json(WA_RETRY_FILE, {"items": []})
    except Exception:
        data = {"items": []}
    items = list(data.get("items") or [])
    gate = pacing_gate(now)
    tried = sent = deferred = dropped = 0
    keep = []
    for it in items:
        if float(it.get("next_at") or 0) > now:
            keep.append(it)
            continue
        if not gate["allowed"]:
            it["next_at"] = max(float(it.get("next_at") or 0),
                                 (_PACE["crawl_until"] or now) + 1.0)
            deferred += 1
            keep.append(it)
            continue
        tried += 1
        res = deliver_whatsapp_question(
            "", it.get("jid"), it.get("q") or {}, it.get("category") or "",
            english_first=it.get("english_first", True),
            answer_delay_sec=0, sleep_fn=lambda *_a: None)
        if (res or {}).get("sent_poll") or (res or {}).get("status") in ("sent", "dry"):
            pacing_note_result(True, "", now=now)
            sent += 1
            continue
        pacing_note_result(False, (res or {}).get("status", ""), now=now)
        it["attempts"] = int(it.get("attempts") or 0) + 1
        if it["attempts"] >= 3:
            dropped += 1
            continue
        mult = pacing_snapshot(now)["risk_multiplier"]
        it["next_at"] = now + 300 * it["attempts"] * mult
        keep.append(it)
    data["items"] = keep
    try:
        save_json_atomic(WA_RETRY_FILE, data)
    except Exception:
        pass
    return {"tried": tried, "sent": sent, "deferred": deferred,
            "dropped": dropped, "pending": len(keep)}


# =====================================================================
# 🛡️ FULL SAFETY STACK — quiet hours, blast guard, caps, preflight
# =====================================================================
BLAST_GUARD_FILE = config.DATA / "wa_blast_guard.json"
GROUP_HEALTH_FILE = config.DATA / "wa_group_health.json"
WA_WARMUP_CAP = 10            # brand-new group: roju ki 10 polls max
WA_DAILY_CAP = 40             # mature group daily cap
WA_QUIET_START = 22
WA_QUIET_END = 7
_BLAST_WINDOW = 45 * 60       # duplicate blast guard window (seconds)


def in_wa_quiet(now=None, start=WA_QUIET_START, end=WA_QUIET_END):
    """🌙 Quiet window lo unna? (default 22:00–07:00, overnight wrap)."""
    now = now or datetime.now()
    h = now.hour
    if start == end:
        return False
    if start < end:
        return start <= h < end
    return h >= start or h < end


def wa_quiet_until(now=None, start=WA_QUIET_START, end=WA_QUIET_END):
    """Quiet eppudu avuthundi (next end-of-quiet datetime)."""
    now = now or datetime.now()
    base = now + timedelta(days=1) if now.hour >= start else now
    return base.replace(hour=end, minute=0, second=0, microsecond=0)


def wa_english_first(grp_idx, q_idx, day_ordinal=None):
    """🔀 Anti-fingerprint: group/question/day parity tho English↔Telugu
    first alternate — anni groups okela kanipinchavu (dorakakunda)."""
    if day_ordinal is None:
        day_ordinal = datetime.now().toordinal()
    return (int(grp_idx) + int(q_idx) + int(day_ordinal)) % 2 == 0


def _slot_due(job_time, today_str, now_dt, last_run, window_min=30):
    """⏰ Slot due aa? Set time nunchi 30-min catch-up window — okka
    missed tick valla schedule miss avakudadhu (owner rule)."""
    try:
        hh, mm = (job_time or "").strip().split(":")
        slot = now_dt.replace(hour=int(hh), minute=int(mm), second=0,
                              microsecond=0)
    except Exception:
        return False
    if last_run and str(last_run).startswith(f"{today_str} {job_time}"):
        return False
    return slot <= now_dt <= slot + timedelta(minutes=window_min)


# ---------------- duplicate blast guard ----------------
def _blast_load():
    try:
        d = load_json(BLAST_GUARD_FILE, {})
    except Exception:
        d = {}
    return d if isinstance(d, dict) else {}


def _blast_save(d):
    try:
        save_json_atomic(BLAST_GUARD_FILE, d)
    except Exception:
        pass


def blast_signature(jids, category="ALL", questions_per_group=5):
    import hashlib
    raw = "|".join(sorted(str(j) for j in (jids or [])))
    return hashlib.sha256(
        f"{raw}|{category}|{questions_per_group}".encode()).hexdigest()[:16]


def blast_pair_recent(jid, qid, now_ts=None, window=_BLAST_WINDOW):
    now_ts = time.time() if now_ts is None else float(now_ts)
    ts = (_blast_load().get("pairs") or {}).get(f"{jid}|{qid}")
    return bool(ts and now_ts - float(ts) < window)


def blast_record(jid, qid, now_ts=None):
    now_ts = time.time() if now_ts is None else float(now_ts)
    d = _blast_load()
    pairs = d.setdefault("pairs", {})
    pairs[f"{jid}|{qid}"] = now_ts
    if len(pairs) > 4000:                      # prune oldest
        for k in sorted(pairs, key=lambda k: pairs[k])[:1000]:
            pairs.pop(k, None)
    sent = d.setdefault("sent", {})
    day = datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d")
    rec = sent.get(jid) or {"day": day, "count": 0, "first": now_ts}
    if rec.get("day") != day:
        rec = {"day": day, "count": 0, "first": rec.get("first", now_ts)}
    rec["count"] = int(rec.get("count") or 0) + 1
    sent[jid] = rec
    _blast_save(d)


def blast_record_blast(sig, jids, now_ts=None):
    now_ts = time.time() if now_ts is None else float(now_ts)
    d = _blast_load()
    d.setdefault("blasts", {})[sig] = {"ts": now_ts,
                                       "jids": [str(j) for j in (jids or [])]}
    _blast_save(d)


def blast_recent(sig, now_ts=None, window=_BLAST_WINDOW):
    now_ts = time.time() if now_ts is None else float(now_ts)
    rec = (_blast_load().get("blasts") or {}).get(sig) or {}
    return bool(rec.get("ts") and now_ts - float(rec["ts"]) < window)


def wa_sent_today(jid, now_ts=None):
    now_ts = time.time() if now_ts is None else float(now_ts)
    rec = (_blast_load().get("sent") or {}).get(jid) or {}
    day = datetime.fromtimestamp(now_ts).strftime("%Y-%m-%d")
    return int(rec.get("count") or 0) if rec.get("day") == day else 0


def wa_group_daily_cap(jid, now_ts=None):
    """Spam guard: warm-up (kottha) group ki chinna cap, mature ki full."""
    now_ts = time.time() if now_ts is None else float(now_ts)
    rec = (_blast_load().get("sent") or {}).get(jid) or {}
    first = float(rec.get("first") or 0)
    warm = (not first) or (now_ts - first < 3 * 86400)
    return (WA_WARMUP_CAP, True) if warm else (WA_DAILY_CAP, False)


# ---------------- group health ----------------
def _health_load():
    try:
        d = load_json(GROUP_HEALTH_FILE, {})
    except Exception:
        d = {}
    return d if isinstance(d, dict) else {}


def _health_status(rec):
    if int(rec.get("consec_fail") or 0) >= 5:
        return "paused"
    sent, failed = int(rec.get("sent") or 0), int(rec.get("failed") or 0)
    if sent + failed >= 5 and sent / max(1, sent + failed) >= 0.7:
        return "good"
    return "weak"


def group_health():
    out = {}
    for jid, rec in _health_load().items():
        sent, failed = int(rec.get("sent") or 0), int(rec.get("failed") or 0)
        out[jid] = dict(rec, rate=int(round(100 * sent / max(1, sent + failed))),
                        status=_health_status(rec))
    return out


def group_health_record(jid, sent=0, failed=0, name=""):
    d = _health_load()
    rec = d.get(jid) or {"sent": 0, "failed": 0, "consec_fail": 0, "name": name}
    rec["sent"] = int(rec.get("sent") or 0) + int(sent or 0)
    rec["failed"] = int(rec.get("failed") or 0) + int(failed or 0)
    rec["consec_fail"] = 0 if sent else int(rec.get("consec_fail") or 0) + int(failed or 0)
    if name:
        rec["name"] = name
    rec["last"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    d[jid] = rec
    try:
        save_json_atomic(GROUP_HEALTH_FILE, d)
    except Exception:
        pass
    return group_health().get(jid, {})


def group_health_reset(jid):
    d = _health_load()
    if jid not in d:
        return False
    name = (d.get(jid) or {}).get("name", "")
    d[jid] = {"sent": 0, "failed": 0, "consec_fail": 0, "name": name}
    try:
        save_json_atomic(GROUP_HEALTH_FILE, d)
    except Exception:
        pass
    return True


# ---------------- preflight + safety stack + preview ----------------
def preflight_whatsapp(groups=None, category="ALL", questions_per_group=5,
                       now=None):
    """🔍 Broadcast mundu 9 checks. Bridge lekapothe DRY — blockers levu
    (em send avadhu kabatti); real connected unte strict."""
    now = now or datetime.now()
    if groups is None:
        reg = load_wa_registry()
        groups = [g for g in reg.get("groups", []) if g.get("active")]
    checks = []

    def add(name, ok, block, detail):
        checks.append({"name": name, "ok": bool(ok), "block": bool(block),
                       "detail": detail})

    bridge = _bridge_call("/status", timeout=5)
    add("Bridge reachable", bool(bridge), False,
        "connected" if bridge else "bridge offline — DRY MODE (em send avadhu)")
    connected = bool(bridge) and (bridge.get("connected")
                                   or bridge.get("status") == "connected")
    add("WhatsApp session", connected, False,
        "session connected" if connected else "session ledu — DRY MODE")
    real = connected
    quiet = in_wa_quiet(now)
    add("Quiet hours (22:00–07:00)", not quiet, bool(quiet and real),
        "quiet window lo unnam — sends defer" if quiet else "quiet hours kadhu")
    jids = [g.get("jid") for g in groups if g.get("jid")]
    sig = blast_signature(jids, category, questions_per_group)
    dup = blast_recent(sig)
    add("Duplicate Blast Guard (45m)", not dup, bool(dup and real),
        "same blast 45-min lopa ayindi" if dup else "fresh blast")
    add("Groups selected", len(groups) > 0, len(groups) == 0,
        f"{len(groups)} active groups")
    busy = bool(EXEC_STATE.get("running")) or _BROADCAST_LOCK.locked()
    add("Broadcast lock free", not busy, busy,
        "inkoka broadcast running" if busy else "lock free")
    gate = pacing_gate()
    add("Adaptive pacing gate", gate["allowed"], bool(not gate["allowed"] and real),
        f"mode {gate['mode']} ×{gate['multiplier']}")
    over = [j for j in jids if wa_sent_today(j) >= wa_group_daily_cap(j)[0]]
    add("Daily caps", not over, False,
        f"cap datina groups: {len(over)}" if over else "caps OK")
    try:
        bank = Bank()
        total = sum(v.get("total", 0) for v in bank.stats().values())
    except Exception:
        total = 0
    add("Questions available", total > 0, False, f"{total} questions bank lo")
    blockers = [c["name"] for c in checks if c["block"]]
    return {"ok": not blockers, "blockers": blockers, "checks": checks,
            "dry": not real}


def safety_stack(now=None):
    """🛡️ 7-layer safety stack snapshot (dashboard card)."""
    now = now or datetime.now()
    snap = pacing_snapshot()
    gate = pacing_gate()
    layers = [
        {"icon": "🌙", "name": "Quiet Hours 22:00–07:00",
         "detail": "Rathri quiet lo sends defer; mid-send kuda graceful stop",
         "ok": not in_wa_quiet(now)},
        {"icon": "🛡️", "name": "Duplicate Blast Guard (45m)",
         "detail": "Same group+question / same blast 45-min lopa repeat avadhu",
         "ok": True},
        {"icon": "🧠", "name": "Adaptive Anti-Ban Pacing",
         "detail": f"×{snap['risk_multiplier']} · {snap['mode']} · fatigue {snap['fatigue']}",
         "ok": gate["allowed"]},
        {"icon": "🌡️", "name": "Warm-up Daily Caps",
         "detail": f"kottha group {WA_WARMUP_CAP}/day → mature {WA_DAILY_CAP}/day (spam guard)",
         "ok": True},
        {"icon": "🔒", "name": "One-Broadcast Lock + 60–80s Gaps",
         "detail": "Oka broadcast run avthunte inkoti start avadhu; poll gaps 60–80s floor",
         "ok": not _BROADCAST_LOCK.locked()},
        {"icon": "🔁", "name": "Smart Retry Queue",
         "detail": "Failed sends risk-scaled backoff tho retry; CRAWL lo attempts burn avavu",
         "ok": True},
        {"icon": "🔀", "name": "Language Alternation",
         "detail": "Group/question/day batti English-first ↔ Telugu-first (anti-fingerprint)",
         "ok": True},
    ]
    return {"layers": layers, "pacing": snap, "gate": gate,
            "quiet": in_wa_quiet(now),
            "quiet_until": wa_quiet_until(now).strftime("%Y-%m-%d %H:%M"),
            "running": bool(EXEC_STATE.get("running"))}


def preview_broadcast(questions_per_group=2, target_category="ALL",
                      target_group_ids=None):
    """👀 Ey messages velthayo chupisthundi — EM SEND CHEYYADHU."""
    reg = load_wa_registry()
    groups = [g for g in reg.get("groups", []) if g.get("active")]
    if target_group_ids:
        ids = set(target_group_ids)
        groups = [g for g in groups
                  if g.get("id") in ids or g.get("jid") in ids]
    elif target_category != "ALL":
        groups = [g for g in groups
                  if g.get("category", "").upper() == target_category.upper()]
    bank = Bank()
    samples = []
    for grp in groups[:12]:
        cat = grp.get("category", "CURRENT")
        pool_cat = cat if cat.upper() not in ("GENERAL", "AUTO", "") else "SSC"
        qs = pick_subject_questions(bank, pool_cat, questions_per_group or 2, None)
        msgs = [build_question_only_post(q, grp.get("name", ""), pool_cat,
                                         q_index=i + 1,
                                         total_q=len(qs) or 1,
                                         english_first=wa_english_first(0, i))
                for i, q in enumerate(qs)]
        samples.append({"group": grp.get("name", ""), "jid": grp.get("jid"),
                        "category": cat, "messages": msgs})
    return {"ok": bool(samples), "groups_total": len(groups),
            "samples": samples,
            "note": "👁️ Preview only — nothing was sent (Preview mode)."}
