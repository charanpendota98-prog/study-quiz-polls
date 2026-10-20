#!/usr/bin/env python3
"""
STUDENTUP — 📄 PAPER FACTORY CLI (370X)

Official previous-paper / board PDF (or .txt) → validated,
provenance-tagged DRAFT. NOTHING goes live from here: drafts
wait in data/paper_drafts.json until the owner approves
(dashboard Paper Factory card or `approve` below), which merges
them into data/scraped_bank.json (signature-deduped). Questions
still needing Telugu translation are NEVER banked — they stay
flagged in the draft.

Usage:
  python3 scripts/paper_factory.py make <file.pdf|file.txt> [--title "TSPSC Group-II 2023 Paper-I.pdf"]
  python3 scripts/paper_factory.py list
  python3 scripts/paper_factory.py translate <draft_id>
  python3 scripts/paper_factory.py approve <draft_id>
  python3 scripts/paper_factory.py reject <draft_id>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("file")
    mk.add_argument("--title", default="")
    sub.add_parser("list")
    tr = sub.add_parser("translate")
    tr.add_argument("draft_id")
    ap2 = sub.add_parser("approve")
    ap2.add_argument("draft_id")
    rj = sub.add_parser("reject")
    rj.add_argument("draft_id")
    args = ap.parse_args()

    from core import paperfactory
    if args.cmd == "make":
        res = paperfactory.make_draft(args.file, args.title)
    elif args.cmd == "list":
        res = {"ok": True, "drafts": paperfactory.list_drafts()}
    elif args.cmd == "translate":
        res = paperfactory.translate_draft(args.draft_id)
    elif args.cmd == "approve":
        res = paperfactory.go_bank(args.draft_id)
    else:
        res = paperfactory.reject_draft(args.draft_id)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
