#!/usr/bin/env python3
"""
STUDENTUP — FILLER GENERATION ENGINE (functional)
Auto top-up: if any channel's unused pool < threshold, generate new questions.
  Offline procedural generator always works (verified math, EN+TE).
  LLM generator (Groq->DeepSeek->OpenAI->Gemini) adds worded/reasoning/GK when keys exist.
Every generated question passes the validation gate before it enters the bank.
Usage:
  python3 filler_gen.py --dry            # show what would be generated
  python3 filler_gen.py                  # top-up banks now
  python3 filler_gen.py --min 30        # target unused pool size
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import config
from core.generator import top_up, generate_offline
from core.question_bank import Bank


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--min", type=int, default=config.FILLER_TRIGGER_UNUSED,
                    dest="min_pool")
    ap.add_argument("--demo", type=int, default=0)
    args = ap.parse_args()

    if args.demo:
        qs = generate_offline(args.demo)
        print(f"DEMO — {len(qs)} offline-generated, validated questions:")
        for q in qs:
            print(f"  [{q['channel']}/{q['topic']}] {q['q_en'][:70]}")
            print(f"      {q['options_en']} -> {q['answer_index']}")
        return

    print("FILLER ENGINE — model chain: offline (verified) + LLM when keys present")
    b = Bank()
    print("Before:", {k: v["unused"] for k, v in b.stats().items()})
    if args.dry:
        need = {k: max(0, args.min_pool - v["unused"]) for k, v in b.stats().items()}
        print("Would top-up (dry):", {k: n for k, n in need.items() if n})
        return
    added, errs = top_up(per_channel_min=args.min_pool)
    b = Bank()
    print(f"After: added {len(added)} questions, {len(errs)} rejected by gate")
    print("After :", {k: v["unused"] for k, v in b.stats().items()})


if __name__ == "__main__":
    main()
