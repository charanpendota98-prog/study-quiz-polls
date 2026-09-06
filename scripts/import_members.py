#!/usr/bin/env python3
"""
STUDENTUP — IMPORT GOOGLE-FORM REGISTRATIONS
Reads the CSV exported from the Google Form responses sheet and loads members
into data/members.json. Matches Telegram usernames/ids; grants +25 registration
bonus; holds username-only signups in form_pending until they /start the bot.

Usage:
  python3 import_members.py path/to/responses.csv            # preview
  python3 import_members.py path/to/responses.csv --commit   # actually write

CSV columns are matched flexibly (English header OR Telugu text in header).
"""
import sys
import csv
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core.members import Members
import re as _re


def _find(row, keywords):
    for col, val in row.items():
        low = (col or "").lower()
        if any(k in low for k in keywords):
            return (val or "").strip()
    return ""


def _norm_district(val):
    """'TS · Hyderabad' -> 'Hyderabad'; tags state via prefix."""
    v = (val or "").strip()
    state = ""
    if v.startswith("TS"):
        state = state or "Telangana"
    if v.startswith("AP"):
        state = state or "Andhra Pradesh"
    v = _re.sub(r"^[AT][PS]\s*·\s*", "", v)
    if "other" in v.lower() or "not listed" in v.lower():
        return "", state
    return v, state


def _norm_exam(val):
    """Map the form's descriptive exam labels to the bot's short targets."""
    v = (val or "").lower()
    if "tspsc" in v:
        return "TSPSC"
    if "appsc" in v:
        return "APPSC"
    if "bank" in v or "ibps" in v or "sbi" in v:
        return "Banking"
    if "railway" in v or "rrb" in v or "alp" in v:
        return "Railway"
    if "police" in v or "constable" in v or " si" in v:
        return "Police"
    if "defence" in v or "nda" in v or "cds" in v or "agniveer" in v:
        return "Defence"
    if "ssc" in v or "upsc" in v:
        return "SSC/UPSC"
    if "current" in v or "gk" in v:
        return "Current Affairs GK"
    return (val or "").strip()


def _norm_lang(val):
    v = (val or "").lower()
    if "both" in v:
        return "Both (EN + TE)"
    if "telugu" in v:
        return "Telugu"
    if "english" in v:
        return "English"
    return (val or "").strip()


def _norm_phone(val):
    digits = _re.sub(r"\D", "", val or "")
    if len(digits) == 11 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 10:
        return digits
    return (val or "").strip()  # keep as-is if unexpected


def _username(val):
    val = (val or "").strip()
    if val.isdigit():
        return "", val                      # numeric id
    return val.lstrip("@").lower(), ""      # @handle


def parse_row(row):
    name = _find(row, ["full name", "name", "పేరు"])
    phone = _norm_phone(_find(row, ["mobile", "phone", "whatsapp", "మొబైల్"]))
    # Email may be Google's auto-collected "Email Address" column
    email = _find(row, ["email", "ఇమెయిల్", "e-mail"])
    tg = _find(row, ["telegram", "టెలిగ్రామ్"])
    state = _find(row, ["state", "రాష్ట్రం"])
    district_raw = _find(row, ["district", "జిల్లా"])
    district, dstate = _norm_district(district_raw)
    if dstate and not state:
        state = dstate
    exam = _norm_exam(_find(row, ["exam target", "target", "లక్ష్యం", "preparing", "exam"]))
    lang = _norm_lang(_find(row, ["language", "medium", "మాధ్యమం", "భాష"]))
    stage = _find(row, ["target exam", "when is your target", "education level",
                        "current education", "stage", "preparation"])
    study = _find(row, ["how do you study", "study", "coaching", "self study"])
    source = _find(row, ["how did you find", "source", "find studentup"])
    uname, tgid = _username(tg)
    return {
        "name": name, "username": uname, "tg_id": tgid, "phone": phone,
        "email": email, "state": state, "district": district, "exam": exam,
        "lang": lang, "stage": stage, "coaching": study, "source": source,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file")
    ap.add_argument("--commit", action="store_true", help="Write to members.json")
    args = ap.parse_args()

    path = Path(args.csv_file)
    if not path.exists():
        print(f"CSV not found: {path}")
        sys.exit(1)

    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    print(f"Read {len(rows)} form responses from {path.name}")

    mb = Members()
    linked = pending = skipped = 0
    for i, row in enumerate(rows, 1):
        info = parse_row(row)
        if not info["name"] and not info["username"] and not info["tg_id"]:
            skipped += 1
            continue
        if not args.commit:
            print(f"  [{i}] {info['name'] or '?':24s} | {info['exam'][:22]:22s} | "
                  f"TG: {info['username'] or info['tg_id'] or '-'}")
            continue
        status, key = mb.import_form_signup(info)
        if status == "linked":
            linked += 1
        elif status == "pending":
            pending += 1
        else:
            skipped += 1

    if args.commit:
        mb.kv.save()
        print(f"\n✅ Imported: {linked} linked to Telegram accounts, "
              f"{pending} held pending (will auto-link on /start), {skipped} skipped.")
        print(f"Total registered now: {mb.count_form()}")
    else:
        print(f"\n(preview — re-run with --commit to save {len(rows)} rows)")


if __name__ == "__main__":
    main()
