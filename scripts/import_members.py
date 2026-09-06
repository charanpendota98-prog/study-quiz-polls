#!/usr/bin/env python3
"""
STUDENTUP — IMPORT GOOGLE-FORM REGISTRATIONS (CSV export)
Reads the CSV exported from the Google Form responses sheet and loads members
into data/members.json. Matches Telegram usernames/ids; grants +25 registration
bonus; holds username-only signups until they /start the bot.

Usage:
  python3 import_members.py path/to/responses.csv            # preview
  python3 import_members.py path/to/responses.csv --commit   # write
The same normalization powers the live webhook (webhook_server.py).
"""
import sys
import csv
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core.members import Members
from core.formingest import normalize_signup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_file")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    path = Path(args.csv_file)
    if not path.exists():
        print(f"CSV not found: {path}")
        sys.exit(1)

    with open(path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"Read {len(rows)} form responses from {path.name}")

    mb = Members()
    linked = pending = skipped = 0
    for i, row in enumerate(rows, 1):
        info = normalize_signup(row)
        if not (info["name"] or info["username"] or info["tg_id"]):
            skipped += 1
            continue
        if not args.commit:
            print(f"  [{i}] {(info['name'] or '?'):22s} | {(info['exam'] or '?'):10s} | "
                  f"📍 {info['district'] or info['state'] or '-':14s} | "
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
        print(f"\n✅ {linked} linked to Telegram accounts, {pending} held pending "
              f"(auto-link on /start), {skipped} skipped.")
        print(f"Total registered: {mb.count_form()}")
    else:
        print(f"\n(preview — re-run with --commit to save {len(rows)} rows)")


if __name__ == "__main__":
    main()
