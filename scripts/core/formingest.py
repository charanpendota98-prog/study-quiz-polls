#!/usr/bin/env python3
"""
STUDENTUP — GOOGLE FORM INGEST NORMALIZATION
Shared by the CSV importer (import_members.py) and the live webhook server
(webhook_server.py). Turns raw form fields (flexible keys, EN/TE headers,
district prefixes) into a clean member-info dict.
"""
from __future__ import annotations

import re


def find_field(fields: dict, keywords) -> str:
    """Case-insensitive substring match on column/field names."""
    for col, val in fields.items():
        low = (str(col) or "").lower()
        if any(k in low for k in keywords):
            return str(val if val is not None else "").strip()
    return ""


def norm_district(val: str):
    """'TS · Warangal' -> ('Warangal', 'Telangana'). ('', state) for 'Other'."""
    v = (val or "").strip()
    state = ""
    if re.match(r"^TS\b", v):
        state = "Telangana"
    elif re.match(r"^AP\b", v):
        state = "Andhra Pradesh"
    v = re.sub(r"^[AT][PS]\s*[·•\-]\s*", "", v)
    if "other" in v.lower() or "not listed" in v.lower():
        return "", state
    return v.strip(), state


def norm_exam(val: str) -> str:
    v = (val or "").lower()
    if "tspsc" in v:
        return "TSPSC"
    if "appsc" in v:
        return "APPSC"
    if "bank" in v or "ibps" in v or "sbi" in v:
        return "Banking"
    if "railway" in v or "rrb" in v or "alp" in v:
        return "Railway"
    if "police" in v or "constable" in v or re.search(r"\bsi\b", v):
        return "Police"
    if "defence" in v or "nda" in v or "cds" in v or "agniveer" in v or "army" in v:
        return "Defence"
    if "ssc" in v or "upsc" in v:
        return "SSC/UPSC"
    if "current" in v or "gk" in v or "general" in v:
        return "Current Affairs GK"
    return (val or "").strip()


def norm_lang(val: str) -> str:
    v = (val or "").lower()
    if "both" in v:
        return "Both (EN + TE)"
    if "telugu" in v:
        return "Telugu"
    if "english" in v:
        return "English"
    return (val or "").strip()


def norm_phone(val: str) -> str:
    digits = re.sub(r"\D", "", val or "")
    if len(digits) == 11 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return (val or "").strip()


def split_tg(val: str):
    """Return (@username-without-@, numeric-id)."""
    v = (val or "").strip().lstrip("@")
    if v.isdigit():
        return "", v
    return v.lower(), ""


def normalize_signup(fields: dict) -> dict:
    """Map any form response (CSV row or webhook JSON) to a member info dict."""
    name = find_field(fields, ["full name", "name", "పేరు"])
    phone = norm_phone(find_field(fields, ["mobile", "phone", "whatsapp", "మొబైల్"]))
    email = find_field(fields, ["email", "ఇమెయిల్", "e-mail"])
    tg = find_field(fields, ["telegram", "టెలిగ్రామ్"])
    state = find_field(fields, ["state", "రాష్ట్రం"])
    district_raw = find_field(fields, ["district", "జిల్లా"])
    district, dstate = norm_district(district_raw)
    if dstate and not state:
        state = dstate
    exam = norm_exam(find_field(fields, ["exam target", "preparing", "లక్ష్యం", "exam"]))
    lang = norm_lang(find_field(fields, ["language", "medium", "మాధ్యమం", "భాష"]))
    edu = find_field(fields, ["education level", "current education", "చదువు"])
    target_year = find_field(fields, ["target exam", "when is your target"])
    study = find_field(fields, ["how do you study", "study mode", "coaching", "self study"])
    hours = find_field(fields, ["hours", "గంటలు"])
    updates = find_field(fields, ["free daily", "updates", "అప్‌డేట్"])
    source = find_field(fields, ["how did you find", "source", "find studentup", "ఎలా తెలిసింది"])
    suggestion = find_field(fields, ["suggestion", "సూచన", "need most"])
    uname, tgid = split_tg(tg)
    return {
        "name": name, "username": uname, "tg_id": tgid, "phone": phone,
        "email": email, "state": state, "district": district, "exam": exam,
        "lang": lang, "education": edu, "target_year": target_year,
        "study_mode": study, "hours": hours, "updates": updates,
        "source": source, "suggestion": suggestion,
        "stage": target_year or edu,
        "coaching": study,
    }
