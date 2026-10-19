#!/usr/bin/env python3
"""
STUDENTUP — 🏥 BANK RESTORE (350X resilience tool)

The served question bank (data/question_bank.json) is GENERATED
state, rebuilt from canonical tracked sources:
  quiz_bank_advanced.md + pyq_bank*.json + curated extras
  + question_bank_extra.json (generated) + academic_bank.md.

If the generated JSON is lost/shrunk (fresh clone, new VM, disk
issue), this tool restores a healthy bank deterministically:

  1. rebuild_json()      — canonical sources → validated bank
  2. generator.top_up()  — offline top-up of thin channels
                           (signature-deduped, honest 'offline-gen'
                           source label; no fake PYQ claims)
  3. bank health report  — totals / grade / invalid / gaps

Idempotent: top_up only adds what is missing, so re-running is
safe. Run it once on every fresh deploy (VM/systemd step).

Usage:
  python3 scripts/bank_restore.py [--min 60] [--json]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min", type=int, default=60,
                    help="minimum unused questions per public channel")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from core import bankhealth, generator
    from core.question_bank import load_bank, rebuild_json

    qs, errors = rebuild_json()
    added, terrors = generator.top_up(per_channel_min=args.min,
                                      use_llm=False)
    if added:
        qs, errors = rebuild_json()
    bank = load_bank(force_rebuild=True)
    all_qs = bank.questions if hasattr(bank, "questions") else list(bank)
    rep = bankhealth.bank_health_report(all_qs)
    out = {"rebuilt": len(qs), "validation_errors": len(errors),
           "topped_up": len(added), "topup_errors": len(terrors),
           "total": rep["total"], "grade": rep["grade"],
           "pyq": rep["pyq"], "invalid": rep["invalid_count"]}
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print("🏥 BANK RESTORE (350X)")
        print(f"rebuilt: {out['rebuilt']} · topped up: {out['topped_up']} "
              f"· total served: {out['total']}")
        print(f"grade: {out['grade']} · PYQ: {rep['pyq']['count']} · "
              f"invalid: {out['invalid']}")
        print(bankhealth.summarize(rep))
    return 0 if out["invalid"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
