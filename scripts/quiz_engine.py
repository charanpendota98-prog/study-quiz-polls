#!/usr/bin/env python3
"""
STUDENTUP — QUIZ ENGINE (functional CLI)
Slots: quiz | morning | tip | evening | jobs | reminder | leaderboard
Examples:
    python3 quiz_engine.py quiz --dry              # 10 polls x 7 channels (no post)
    python3 quiz_engine.py quiz --channel BANKING  # one channel only
    python3 quiz_engine.py evening --dry           # CA digest
    python3 quiz_engine.py morning --dry
    python3 quiz_engine.py tip --dry
    python3 quiz_engine.py jobs --dry
    python3 quiz_engine.py leaderboard
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core.engine import Engine
from core import config


def main():
    ap = argparse.ArgumentParser(description="StudentUp quiz engine")
    ap.add_argument("slot", choices=["quiz", "morning", "tip", "coach", "collect",
                                     "evening", "reminder", "jobs", "leaderboard",
                                     # back-compat aliases
                                     "digest", "personal"])
    ap.add_argument("--dry", action="store_true", help="Dry run — NO Telegram posts")
    ap.add_argument("--channel", help="Run for one channel key only (e.g. TSPSC)")
    ap.add_argument("--count", type=int, default=config.POLLS_PER_SLOT)
    ap.add_argument("--in", dest="in_min", type=int, default=10,
                    help="Reminder: minutes until slot")
    args = ap.parse_args()

    if args.dry:
        config.DRY = True

    eng = Engine(dry=args.dry)
    channels = [args.channel] if args.channel else None

    print(f"QUIZ ENGINE — slot={args.slot} dry={args.dry} "
          f"channels={channels or 'ALL 7 public'}")

    if args.slot in ("quiz",):
        eng.run_quiz_slot(channels=channels)
    elif args.slot == "morning":
        eng.morning()
    elif args.slot == "tip":
        eng.tip()
    elif args.slot == "coach":
        eng.coach_broadcast()
    elif args.slot == "collect":
        eng.collect_exam_content()
    elif args.slot in ("evening", "digest"):
        eng.digest()
    elif args.slot in ("jobs", "personal"):
        eng.jobs()
    elif args.slot == "reminder":
        eng.reminder(args.in_min)
    elif args.slot == "leaderboard":
        eng.weekly_leaderboard()


if __name__ == "__main__":
    main()
