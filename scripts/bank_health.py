#!/usr/bin/env python3
"""
STUDENTUP — BANK HEALTH CLI (280X)
Honest, deterministic health report for the question bank: totals,
per-group counts, PYQ share, duplicate stems, invalid questions,
missing explanations and — most importantly — correct-answer
POSITION bias (the "answer is usually B" disease).

Usage:
  python3 scripts/bank_health.py            # full report
  python3 scripts/bank_health.py --json     # machine-readable
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import bankhealth  # noqa: E402
from core.question_bank import load_bank  # noqa: E402


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()

    bank = load_bank()
    qs = bank.questions if hasattr(bank, "questions") else list(bank)
    rep = bankhealth.bank_health_report(qs)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
        return
    print("🏥 STUDENTUP BANK HEALTH (280X)")
    print(bankhealth.summarize(rep))
    print(f"groups: {rep['groups']}")
    print(f"positions (A/B/C/D): {rep['positions']}")
    for f in rep["bias_flags"]:
        print(f"  ⚠️ {f['scope']}: position {f['top_position']} = "
              f"{round(100 * f['top_share'])}% of {f['n']}")
    if rep["invalid"]:
        for qid, defects in list(rep["invalid"].items())[:15]:
            print(f"  ❌ {qid}: {', '.join(defects)}")
    print("note: live polls are position-balanced at send time "
          "(content.poll_safe) — this report measures the RAW bank.")


if __name__ == "__main__":
    main()
