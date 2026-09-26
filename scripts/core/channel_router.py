#!/usr/bin/env python3
"""
STUDENTUP — DYNAMIC CHANNEL & EXAM QUIZ ROUTER
Allows adding any new Telegram channel or exam category dynamically at runtime.
Automatically builds exam-aligned polls, subjects, blueprints and schedules.
"""
import re
from pathlib import Path
from core import config
from core.store import load_json, save_json_atomic

CUSTOM_CHANNELS_FILE = config.DATA / "custom_channels.json"

# Exam taxonomy keywords mapping exam titles to internal knowledge banks
TAXONOMY = {
    "AP_BTECH": ["AP BTECH", "AP B.TECH", "JNTU KAKINADA", "JNTUK", "JNTUA", "ANDHRA ENGINEERING", "JNTU ANANTAPUR"],
    "AP_DEGREE": ["AP DEGREE", "ANDHRA DEGREE", "ANDHRA UNIVERSITY", "SVU", "SRI VENKATESWARA", "ACHARYA NAGARJUNA DEGREE", "AP B.COM", "AP BSC"],
    "AP_DIPLOMA": ["AP DIPLOMA", "AP POLYCET", "AP SBTET", "AP POLYTECHNIC", "AP ECET"],
    "AP_INTER": ["AP INTER", "AP INTERMEDIATE", "BIEAP", "AP EAPCET", "ANDHRA INTER"],
    "AP_10TH": ["AP 10TH", "BSEAP", "AP SSC", "ANDHRA 10TH", "AP TENTH", "AP CLASS 10"],
    "ITI_ALL": ["ITI", "ELECTRICIAN", "FITTER", "MACHINIST", "NCVT", "SCVT", "DIESEL MECHANIC", "WELDER", "COPA", "WIREMAN"],
    "OPEN_UNIV": ["OPEN UNIVERSITY", "BRAOU", "AMBEDKAR OPEN", "DISTANCE", "DISTANCE EDUCATION", "ANUCDE", "SDLCE", "IGNOU", "OPEN DEGREE"],
    "TS_BTECH": ["BTECH", "B.TECH", "ENGINEERING", "GATE", "CSE", "ECE", "EEE", "MECHANICAL", "CIVIL", "CAMPUS PLACEMENT", "CRT", "SOFTWARE"],
    "TS_DEGREE": ["DEGREE", "B.COM", "BSC", "B.SC", "B.A", "BA", "ICET", "COMMERCE", "LIFE SCIENCES", "GENERAL DEGREE"],
    "TS_10TH": ["10TH", "SSC BOARD", "CLASS 10", "TENTH", "10TH CLASS", "SSC CLASS 10"],
    "TS_INTER": ["INTER", "INTERMEDIATE", "MPC", "BIPC", "CEC", "HEC", "11TH", "12TH", "IPE", "EAMCET"],
    "TS_DIPLOMA": ["DIPLOMA", "POLYCET", "POLYTECHNIC", "ECET", "SBTET", "C-20", "C-21"],
    "POLICE": ["POLICE", "SI", "SUB INSPECTOR", "SUB-INSPECTOR", "CONSTABLE", "TS POLICE", "AP POLICE", "TSSP", "APSP", "AR", "SAR", "CIVIL"],
    "BANKING": ["BANK", "BANKING", "IBPS", "SBI", "PO", "CLERK", "RBI", "NABARD", "CANARA", "HDFC", "FINANCE"],
    "SSC": ["SSC", "CGL", "CHSL", "MTS", "CPO", "GD", "STENO", "SELECTION POST", "CENTRAL"],
    "RAILWAY": ["RAILWAY", "RRB", "NTPC", "GROUP D", "ALP", "LOCO PILOT", "JE", "TC", "RPF"],
    "TSPSC": ["TSPSC", "TELANGANA GROUP", "TS GROUP 1", "TS GROUP 2", "TS GROUP 3", "TS GROUP 4", "VRO", "PANCHAYAT SECRETARY"],
    "APPSC": ["APPSC", "ANDHRA GROUP", "AP GROUP 1", "AP GROUP 2", "AP GROUP 3", "AP GROUP 4", "GRAMA SACHIVALAYAM", "WARD SECRETARY"],
    "TET_DSC": ["TET", "TS TET", "APTET", "AP TET", "DSC", "TS DSC", "AP DSC", "TRT", "TEACHER", "SGT", "SCHOOL ASSISTANT", "PEDAGOGY", "CHILD DEVELOPMENT", "BED", "DED", "B.ED", "D.ED"],
    "DEFENCE": ["DEFENCE", "ARMY", "NAVY", "AIR FORCE", "NDA", "CDS", "AFCAT", "AGNIVEER", "CAPF", "CISF", "CRPF", "BSF", "ITBP"],
    "CURRENT": ["CURRENT", "AFFAIRS", "GK", "DAILY NEWS", "GENERAL KNOWLEDGE", "GS", "GENERAL STUDIES"]
}


def load_custom_channels() -> dict:
    return load_json(CUSTOM_CHANNELS_FILE, {"channels": {}})


def save_custom_channels(d: dict):
    save_json_atomic(CUSTOM_CHANNELS_FILE, d)


def detect_exam_base(title_or_exam: str) -> str:
    """Detect matching exam category from arbitrary user input / title with longest-match precision."""
    s = title_or_exam.upper().strip()
    
    # Check exact word boundary matches sorted by keyword length (descending) for precision
    candidates = []
    for base_exam, keywords in TAXONOMY.items():
        for kw in keywords:
            # Word boundary search
            if re.search(r'\b' + re.escape(kw) + r'\b', s):
                candidates.append((len(kw), base_exam))
            elif kw in s and len(kw) >= 4:
                candidates.append((len(kw), base_exam))
                
    if candidates:
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    return "CURRENT"


def register_channel(name: str, chat_id: str = "", exam_type: str = "", username: str = "", description: str = "") -> dict:
    """
    Dynamically register a new Telegram channel and automatically configure:
      - Detected exam base (e.g. 'TS Police Sub Inspector' -> 'POLICE')
      - Target audience and syllabus subjects
      - Immediate availability in question generator and quiz engine
    """
    key = re.sub(r'[^A-Z0-9_]', '_', name.upper()).strip('_')
    if not key:
        key = f"CH_{len(load_custom_channels().get('channels', {})) + 1}"

    base_exam = detect_exam_base(exam_type or name)
    template = config.CHANNELS.get(base_exam, config.CHANNELS["CURRENT"])

    info = {
        "key": key,
        "name": name,
        "base_exam": base_exam,
        "emoji": template.get("emoji", "🎯"),
        "subject": f"{name} Exam Prep ({template.get('subject', 'General Studies')})",
        "public": True,
        "chat_id": chat_id,
        "username": username or name.replace(" ", ""),
        "audience": description or f"Aspirants targeting {name} & {base_exam}",
        "topics": list(template.get("topics", ["GK", "Reasoning", "Current Affairs"])),
        "ts_ap_weight": template.get("ts_ap_weight", 0.35)
    }

    data = load_custom_channels()
    data.setdefault("channels", {})[key] = info
    save_custom_channels(data)

    # Inject into live config dictionary
    config.CHANNELS[key] = info
    if key not in config.PUBLIC_CHANNELS:
        config.PUBLIC_CHANNELS.append(key)

    return info


def get_all_channels() -> dict:
    """Return unified dictionary of base channels + runtime custom channels."""
    out = dict(config.CHANNELS)
    cust = load_custom_channels().get("channels", {})
    out.update(cust)
    return out


# Auto-mount custom channels into runtime config upon module import
for _k, _v in load_custom_channels().get("channels", {}).items():
    config.CHANNELS[_k] = _v
    if _v.get("public") and _k not in config.PUBLIC_CHANNELS:
        config.PUBLIC_CHANNELS.append(_k)
