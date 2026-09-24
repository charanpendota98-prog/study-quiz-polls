#!/usr/bin/env python3
"""
STUDENTUP — EXCEL / CSV IMPORTER & BUNDLE MANAGER
Allows uploading/pasting Excel, CSV or Google Sheet rows containing 100+ to 150+ WhatsApp groups/channel links:
  - Format: Name, Link/JID, Category, Shift
  - Automatic category detection and auto-assignment.
  - Channel & WhatsApp Group Bundling: Group multiple channels into custom bundles
    (e.g. 'All Police Groups & Channels', 'TS Intermediate College Cluster', 'AP Engineering Placements').
  - One-click broadcast dispatch to an entire Bundle.
"""
import csv
import io
import json
import time
from pathlib import Path
from core import config
from core.store import load_json, save_json_atomic
from core import channel_router, whatsapp_pipeline

BUNDLES_FILE = config.DATA / "channel_bundles.json"


def load_bundles() -> dict:
    default = {
        "bundles": [
            {
                "id": "BUNDLE_POLICE",
                "name": "👮 Police Exam Mega Bundle (TS & AP)",
                "category": "POLICE",
                "target_groups": ["G_POLICE_TS_1", "G_POLICE_AP_1"],
                "target_channels": ["POLICE", "TS_POLICE_SI_2026_BATCH"]
            },
            {
                "id": "BUNDLE_CENTRAL",
                "name": "🏛️ Central Jobs & Railway Mega Bundle",
                "category": "SSC",
                "target_groups": ["G_CENTRAL_SSC_1", "G_RAILWAY_RRB_1"],
                "target_channels": ["SSC", "RAILWAY"]
            },
            {
                "id": "BUNDLE_TS_ACADEMIC",
                "name": "🎓 Telangana Academic Cluster (10th, Inter, Degree, B.Tech)",
                "category": "TS_BTECH",
                "target_groups": ["G_TSPSC_GRP2_1"],
                "target_channels": ["TS_10TH_CLASS_BOARD_EXAM_PREP", "TS_INTERMEDIATE__MPC_BIPC_CEC", "TS_DIPLOMA___POLYCET___ECET"]
            },
            {
                "id": "BUNDLE_AP_ACADEMIC",
                "name": "🌊 Andhra Pradesh Academic Cluster (B.Tech, Degree, Inter, 10th)",
                "category": "AP_BTECH",
                "target_groups": [],
                "target_channels": []
            }
        ]
    }
    if BUNDLES_FILE.exists():
        try:
            return load_json(BUNDLES_FILE, default)
        except Exception:
            pass
    save_json_atomic(BUNDLES_FILE, default)
    return default


def save_bundles(d: dict):
    save_json_atomic(BUNDLES_FILE, d)


def create_bundle(name: str, category: str, group_ids: list, channel_keys: list) -> dict:
    data = load_bundles()
    bid = f"BUNDLE_{int(time.time()) % 10000}_{len(data.get('bundles', [])) + 1}"
    bundle = {
        "id": bid,
        "name": name,
        "category": category,
        "target_groups": group_ids,
        "target_channels": channel_keys,
        "created_at": time.strftime("%Y-%m-%d %H:%M")
    }
    data.setdefault("bundles", []).append(bundle)
    save_bundles(data)
    return bundle


def delete_bundle(bundle_id: str) -> bool:
    data = load_bundles()
    before = len(data.get("bundles", []))
    data["bundles"] = [b for b in data.get("bundles", []) if b.get("id") != bundle_id]
    save_bundles(data)
    return len(data["bundles"]) < before


def import_from_csv_or_excel_text(raw_text: str) -> dict:
    """
    Parses comma-separated, tab-separated (direct Excel/Google Sheet paste) or pipe-separated lines.
    Expected Columns (Flexible order):
      Column 1: Name / Title
      Column 2: Link / JID / ChatID
      Column 3: Category (optional, auto-detected if blank)
      Column 4: Shift (optional: MORNING, EVENING, ALL_DAY)
    """
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    added_groups = []
    added_channels = []

    for line in lines:
        # Determine separator: tab (Excel paste) or comma or pipe
        if "\t" in line:
            parts = [p.strip() for p in line.split("\t")]
        elif "," in line:
            # Handle potential quoted commas via standard csv reader
            try:
                reader = csv.reader(io.StringIO(line))
                parts = [p.strip() for p in next(reader)]
            except Exception:
                parts = [p.strip() for p in line.split(",")]
        elif "|" in line:
            parts = [p.strip() for p in line.split("|")]
        else:
            parts = [line]

        if not parts or not parts[0]:
            continue

        name = parts[0]
        # Ignore header row if present
        if name.lower() in ("name", "title", "group name", "channel name", "group"):
            continue

        link_or_jid = parts[1] if len(parts) > 1 else ""
        category = parts[2] if len(parts) > 2 and parts[2] else channel_router.detect_exam_base(name)
        shift = parts[3].upper() if len(parts) > 3 and parts[3] in ("MORNING", "EVENING", "ALL_DAY") else "ALL_DAY"

        # Check if it is a Telegram channel (@ or t.me/ or channel ID)
        if link_or_jid.startswith("@") or "t.me/" in link_or_jid:
            ch_info = channel_router.register_channel(name, chat_id=link_or_jid, exam_type=category)
            added_channels.append(ch_info)
        else:
            # WhatsApp Group
            grp = whatsapp_pipeline.add_group(name, link_or_jid, category=category, shift=shift)
            added_groups.append(grp)

    return {
        "ok": True,
        "imported_groups_count": len(added_groups),
        "imported_channels_count": len(added_channels),
        "groups": added_groups,
        "channels": added_channels
    }
