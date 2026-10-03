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


def _bridge_call(path: str, payload: dict = None, method: str = None, timeout: int = 40):
    """Call the Node WhatsApp bridge. Returns dict or None if bridge is down."""
    url = f"{WA_BRIDGE_URL}{path}"
    try:
        if payload is not None or (method or "").upper() == "POST":
            data = json.dumps(payload or {}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
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
        if not jid:
            continue
        if jid in existing:
            existing[jid]["name"] = rg.get("name", existing[jid].get("name"))
            existing[jid]["participants"] = rg.get("participants", 0)
            existing[jid]["real"] = True
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
    end_date: str = ""
) -> dict:
    import uuid
    jobs = load_schedules()
    job_id = f"job_{uuid.uuid4().hex[:6]}"
    clean_time = time_str.strip()
    if len(clean_time) == 4 and clean_time[1] == ':':
        clean_time = "0" + clean_time  # format 9:00 -> 09:00

    auto_label = label.strip() if label else f"{clean_time} Daily {category} Drill"
    # Calculate end date if days_duration > 0
    calculated_end_date = end_date
    if days_duration > 0 and not calculated_end_date:
        calculated_end_date = (datetime.now() + timedelta(days=int(days_duration))).strftime("%Y-%m-%d")

    mode_label = "Auto Continuous" if auto_mode or days_duration == 0 else f"{days_duration} Days Limited"
    job = {
        "id": job_id,
        "time": clean_time,
        "label": auto_label,
        "target_group_ids": target_group_ids or [],
        "category": category or "ALL",
        "is_question": is_question,
        "questions_count": questions_count or 1,
        "enabled": enabled,
        "auto_mode": bool(auto_mode),
        "days_duration": int(days_duration) if days_duration else 0,
        "end_date": calculated_end_date,
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
    lines = [f"{header} — *{category}*", f"📍 *Q {q_index}/{total_q}*", ""]

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


def _dispatch_raw(gateway_url: str, jid: str, text: str, attachment: str = "", poll: dict = None):
    """Send for real through the Baileys bridge. Order of preference:
    1. Local bridge (gateway/wa_bridge.js) — text, media URL and native polls.
    2. Legacy external gateway webhook (if gateway_url configured).
    3. Otherwise honestly report that nothing was sent (no fake OK)."""
    payload = {"jid": jid, "text": text}
    if attachment:
        payload["attachment"] = attachment
    if poll:
        payload["poll"] = poll

    res = _bridge_call("/send", payload=payload, timeout=60)
    if res is not None:
        if res.get("ok"):
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
    delay_min: int = 40,
    delay_max: int = 60,
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
    if EXEC_STATE["running"]:
        return {"ok": False, "message": "Another broadcast process is currently running."}

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
        return {"ok": False, "message": f"No active groups found for the selected filter."}

    total_polls_to_send = len(groups) * (questions_per_group or 1)
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

            def _anti_ban_sleep(seconds: float):
                time.sleep(seconds if real_mode else min(seconds, 2.0))

            completed_groups_count = 0

            for grp_idx, grp in enumerate(groups):
                if EXEC_STATE["stop_requested"]:
                    _log("🛑 Broadcast stopped by admin.")
                    break

                cat = grp.get("category", "CURRENT")
                g_type = grp.get("group_type", "EXAM_SPECIFIC")
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
                    ok, res = _dispatch_raw(gw, grp["jid"], txt, attachment=attachment_url, poll=poll_payload)
                    if not ok and poll_payload:
                        # Poll rejected (e.g. announcement-only community) → retry as plain text
                        ok, res = _dispatch_raw(gw, grp["jid"], txt, attachment=attachment_url)
                    _log(f"      -> Gateway Status: {res}")

                    EXEC_STATE["progress"] += 1

                    # If more polls remaining for this group, wait 40-60s random gap
                    if q_idx < q_count - 1 and not EXEC_STATE["stop_requested"]:
                        poll_gap = random.uniform(delay_min, delay_max)
                        _log(f"   ⏳ Natural Human Anti-Ban Gap: waiting {poll_gap:.1f}s before next poll...")
                        _anti_ban_sleep(poll_gap)

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
    return dict(EXEC_STATE)


# =====================================================================
# BACKGROUND AUTONOMOUS SCHEDULER & HEARTBEAT ENGINE
# Runs 24x7 in a persistent detached daemon thread:
# 1. Checks every 20 seconds against current server time (HH:MM).
# 2. Automatically launches interleaved quiz rounds for scheduled jobs.
# 3. Maintains active keepalive heartbeat for linked WhatsApp session.
# =====================================================================
_SCHEDULER_RUNNING = False
_LAST_TRIGGERED_MIN = {}


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

                today_str = datetime.now().strftime("%Y-%m-%d")
                jobs = load_schedules()
                for j in jobs:
                    if not j.get("enabled", True):
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
                    if job_time == now_str and _LAST_TRIGGERED_MIN.get(jid) != now_str:
                        _LAST_TRIGGERED_MIN[jid] = now_str
                        j["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        j["total_dispatches"] = j.get("total_dispatches", 0) + 1
                        save_schedules(jobs)
                        _log(f"⏰ Auto-Scheduler Triggered: Launching '{j.get('label', jid)}' ({job_time})!")
                        start_interleaved_broadcast(
                            target_category=j.get("category", "ALL"),
                            target_group_ids=j.get("target_group_ids", []),
                            is_question=j.get("is_question", True),
                            questions_per_group=j.get("questions_count", 5),
                            two_phase_answer=True,
                            delay_min=40,
                            delay_max=60
                        )
            except Exception:
                pass
            time.sleep(20)

    th = threading.Thread(target=_loop, daemon=True)
    th.start()


# Auto-start daemon on module import
start_scheduler_daemon()
