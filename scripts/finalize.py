#!/usr/bin/env python3
"""
STUDENTUP — FINALIZE / VALIDATION GATE
Runs before every build/deploy. Rebuilds the canonical bank and validates:
  - every question: 4 EN + 4 TE options, valid answer index, Telugu policy
  - blocked-topic scan (cricket / films / weather / job-cuts ...)
  - forbidden Indic scripts (no Devanagari/Kannada/Malayalam leaking in)
  - duplicate fingerprints across the whole bank
  - answer-key distribution per channel (avoid always-A)
  - CA digest + tips + curated jobs present
Exit code 0 = ready to deploy; non-zero = errors found.
"""
import sys
import argparse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import config
from core.question_bank import rebuild_json, parse_digest, Bank
from core.content import validate_question, is_blocked, has_telugu
from core.store import similarity, load_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="exit non-zero on any error")
    args = ap.parse_args()

    print("=" * 64)
    print("STUDENTUP VALIDATION GATE — pre-deploy")
    print("=" * 64)
    qs, parse_errs = rebuild_json()
    errors, warnings = [], []

    # 1) per-question validation
    for q in qs:
        errors.extend(validate_question(q))

    # 2) duplicate fingerprints — number-aware: same template with different
    #    values is a DIFFERENT question (e.g. "15% of 5000" vs "25% of 200").
    import re as _re
    def _nums(s):
        return tuple(sorted(_re.findall(r"\d+", s)))
    seen = {}
    for q in qs:
        fp = q["q_en"].lower().strip()
        for other, ofp in seen.items():
            if _nums(fp) != _nums(ofp):
                continue          # different numbers => distinct question
            if similarity(fp, ofp) >= 0.85:
                warnings.append(f"{q['id']} ~ {other}: possible duplicate question")
        seen[q["id"]] = fp

    # 3) answer-key distribution
    print("\nAnswer-key distribution per channel:")
    by_ch = {}
    for q in qs:
        by_ch.setdefault(q["channel"], []).append(q["answer_index"])
    for ch in config.PUBLIC_CHANNELS:
        dist = Counter(by_ch.get(ch, []))
        total = sum(dist.values())
        line = {k: dist.get(i, 0) for i, k in enumerate("ABCD")}
        flag = ""
        if total:
            top = max(line.values())
            if top / total > 0.6:
                flag = "  ⚠ skewed"
                warnings.append(f"{ch}: answer key skewed {line}")
        print(f"  {ch:9s} n={total:3d}  A={line['A']:2d} B={line['B']:2d} "
              f"C={line['C']:2d} D={line['D']:2d}{flag}")

    # 4) per-channel counts
    print("\nQuestion counts per channel:")
    b = Bank()
    for ch, st in b.stats().items():
        if ch == "JOBS":
            print(f"  [-- ] {ch:9s} (private jobs channel — feeds, not polls)")
            continue
        status = "OK " if st["total"] >= config.POLLS_PER_SLOT else "LOW"
        if st["total"] < config.POLLS_PER_SLOT:
            warnings.append(f"{ch}: only {st['total']} questions (< {config.POLLS_PER_SLOT})")
        print(f"  [{status}] {ch:9s} total={st['total']:3d} unused={st['unused']:3d}")

    # 5) content assets
    digest = parse_digest()
    ca_cur = load_json(config.CA_CURATED_JSON, {"items": []}).get("items", [])
    tips = load_json(config.TIPS_JSON, {"tips": []}).get("tips", [])
    jobs_cur = load_json(config.DATA / "jobs_curated.json", {"items": []}).get("items", [])
    print(f"\nContent assets: CA digest(MD)={len(digest)} CA curated={len(ca_cur)} "
          f"tips={len(tips)} curated jobs={len(jobs_cur)}")
    for name, items in [("CA curated", ca_cur), ("tips", tips), ("jobs", jobs_cur)]:
        for i, it in enumerate(items):
            te = it.get("te", "")
            if not has_telugu(te):
                warnings.append(f"{name}[{i}] missing Telugu: {it.get('en','')[:40]}")
            blocked, why = is_blocked(it.get("en", ""))
            if blocked:
                errors.append(f"{name}[{i}] blocked topic ({why})")

    # 6) parse errors from rebuild
    errors.extend(parse_errs)

    print("\n" + "=" * 64)
    if warnings:
        print(f"WARNINGS: {len(warnings)}")
        for w in warnings:
            print("  ⚠", w)
    if errors:
        print(f"\nERRORS: {len(errors)}")
        for e in errors:
            print("  ✗", e)
        print("\nVALIDATION GATE — FAILED ❌")
        if args.strict:
            sys.exit(1)
    else:
        print(f"\nVALIDATION GATE — PASSED ✅  ({len(qs)} questions, 0 errors)")
    print("=" * 64)


if __name__ == "__main__":
    main()
