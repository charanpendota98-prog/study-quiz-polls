#!/usr/bin/env python3
"""
STUDENTUP — PERSONAL/JOBS NEWS ENGINE (private channel, every 30 min)
1) Refresh RSS feeds (2-tier ACTION+CONTEXT filter, other-state hard block, dedup).
2) Post up to 5 jobs items WITH links + source to the private jobs channel.
Falls back to curated jobs when live feeds are unreachable (never silent).
Usage:
  python3 personal_news.py --dry
  python3 personal_news.py            # refresh feeds + post
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import config
from core.engine import Engine
from core.feeds import aggregate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-refresh", action="store_true",
                    help="Use existing aggregated file only")
    args = ap.parse_args()

    print(f"PERSONAL NEWS ENGINE — dry={args.dry} | private jobs channel")
    if not args.no_refresh:
        print("Refreshing jobs feeds…")
        try:
            aggregate(dry=args.dry)
        except Exception as e:
            print(f"feed refresh note: {e}")
    eng = Engine(dry=args.dry)
    n = eng.jobs()
    print(f"Posted {n} job items")


if __name__ == "__main__":
    main()
