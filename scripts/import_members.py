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


def _find(row, keywords):
    for col, val in row.items():
        low = (col or "").lower()
        if any(k in low for k in keywords):
            return (val or "").strip()
    return ""


def _username(val):
    val = (val or "").strip()
    if val.isdigit():
        return "", val                      # numeric id
    return val.lstrip("@").lower(), ""      # @handle


def parse_row(row):
    name = _find(row, ["name", "పేరు"])
    phone = _find(row, ["mobile", "phone", "whatsapp", "మొబైల్"])
    tg = _find(row, ["telegram", "టెలిగ్రామ్"])
    email = _find(row, ["email", "ఇమెయిల్"])
    state = _find(row, ["state", "రాష్ట్రం"])
    district = _find(row, ["district", "జిల్లా"])
    exam = _find(row, ["exam target", "target", "లక్ష్యం", "exam"])
    lang = _find(row, ["language", "medium", "మాధ్యమం", "భాష"])
    stage = _find(row, ["stage", "preparation", "stage"])
    coaching = _find(row, ["coaching", "self study"])
    uname, tgid = _username(tg)
    return {
        "name": name, "username": uname, "tg_id": tgid, "phone": phone,
        "email": email, "state": state, "district": district, "exam": exam,
        "lang": lang, "stage": stage, "coaching": coaching,
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
