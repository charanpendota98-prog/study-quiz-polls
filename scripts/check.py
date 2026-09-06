#!/usr/bin/env python3
"""
STUDENTUP — HEALTH CHECK
Verifies: env keys, bank health, content assets, LLM keys, feed reachability,
and (if BOT_TOKEN set) Telegram connectivity via getMe + getChat per channel.
Usage:  python3 check.py
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import config
from core.question_bank import Bank
from core.llm import LLM
from core.store import load_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--feeds", action="store_true", help="also probe RSS feed reachability")
    ap.add_argument("--sources", action="store_true",
                    help="show central source registry + health summary")
    args = ap.parse_args()

    ok = True
    print("=" * 64)
    print("STUDENTUP HEALTH CHECK")
    print("=" * 64)

    # env
    print("\n[1] Environment")
    print("  BOT_TOKEN set:", "YES" if config.BOT_TOKEN else "NO (dry-run only)")
    print("  ADMIN_ID    :", config.ADMIN_ID or "not set")
    llm = LLM()
    print("  LLM keys    : Groq=%d DeepSeek=%d OpenAI=%d Gemini=%d" % (
        len(llm.groq), len(llm.deepseek), len(llm.openai), len(llm.gemini)))

    # bank
    print("\n[2] Question bank")
    b = Bank()
    total = 0
    for ch, st in b.stats().items():
        total += st["total"]
        mark = "OK " if st["total"] >= config.POLLS_PER_SLOT else "LOW"
        if st["total"] < config.POLLS_PER_SLOT and ch != "JOBS":
            ok = False
        print(f"  [{mark}] {ch:9s} total={st['total']:3d} unused={st['unused']:3d}")
    print(f"  TOTAL questions: {total}")

    # assets
    print("\n[3] Content assets")
    for name, path, key in [
        ("PYQ bank", config.BANK_PYQ_JSON, "questions"),
        ("CA curated", config.CA_CURATED_JSON, "items"),
        ("Study tips", config.TIPS_JSON, "tips"),
        ("Jobs curated", config.DATA / "jobs_curated.json", "items"),
        ("Canonical bank", config.BANK_JSON, "questions"),
    ]:
        data = load_json(path, None)
        n = len(data.get(key, [])) if data else 0
        status = "OK" if n else "MISSING"
        if not n:
            ok = False
        print(f"  [{status}] {name:15s} {n}")

    # members
    print("\n[3b] Members & points")
    try:
        from core.members import Members
        mb = Members()
        reg = mb.count()
        print(f"  Registered members: {reg}")
        top = mb.top(3)
        for i, (uid, m) in enumerate(top):
            print(f"    {i+1}. {m.get('name','?')} — ⭐{m.get('points',0)}")
    except Exception as e:
        print("  members note:", e)

    # telegram
    if config.BOT_TOKEN:
        print("\n[4] Telegram connectivity")
        from core.telegram import Telegram, TelegramError
        tg = Telegram(dry=False)
        try:
            me = tg._call("getMe", {})
            uname = me.get("result", {}).get("username", "?")
            print(f"  Bot: @{uname} — authenticated OK")
            for ch in config.CHANNELS:
                chat = config.channel_chat_id(ch)
                try:
                    r = tg._call("getChat", {"chat_id": chat})
                    title = r.get("result", {}).get("title", "?")
                    print(f"    ✓ {ch:9s} {chat} -> {title[:40]}")
                except TelegramError as e:
                    print(f"    ✗ {ch:9s} {chat} -> {str(e)[:60]}")
        except TelegramError as e:
            print("  getMe failed:", e)
            ok = False
    else:
        print("\n[4] Telegram: skipped (no BOT_TOKEN — dry-run mode)")

    # feeds
    if args.feeds:
        print("\n[5] Feed reachability")
        from core.feeds import load_feed_sources, fetch_feed
        for scope, feeds in load_feed_sources().items():
            for name, url in feeds:
                entries = fetch_feed(name, url, timeout=10)
                status = f"{len(entries)} entries" if entries else "DEAD/empty"
                print(f"  [{status:12s}] {name}")

    # central source registry + health
    if args.sources:
        print("\n[6] Central source registry (deep-quiz scraping)")
        from core import collector
        reg = collector.load_registry()
        srcs = reg.get("sources", [])
        en = [s for s in srcs if s.get("enabled")]
        cand = [s for s in srcs if not s.get("enabled") and s.get("auto_enable_if_live")]
        print(f"  Total: {len(srcs)} | enabled: {len(en)} | "
              f"candidates (auto-audit): {len(cand)}")
        h = collector.health_summary()
        print(f"  Health: ok={h['ok']} paused={h['paused']} failing={h['failing']}")
        for s in en:
            a = s.get("audit", {})
            print(f"    ✓ {s['name'][:38]:38s} {s.get('type','?'):6s} "
                  f"{a.get('status','?')}")
        print("  (full detail: python3 audit_sources.py)")

    print("\n" + "=" * 64)
    print("HEALTH:", "ALL CORE CHECKS PASS ✅" if ok else "ISSUES FOUND ⚠️ (see above)")
    print("=" * 64)


if __name__ == "__main__":
    main()
