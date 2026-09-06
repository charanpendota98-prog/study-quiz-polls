#!/usr/bin/env python3
"""
STUDENTUP — CHANNEL DETECTOR (stdlib only)
==========================================
Once you added the bot as ADMIN + POST MESSAGES in your channels, paste the
BOT_TOKEN in env/.env and run:

    python3 detect_channels.py            # probe + show titles & ids
    python3 detect_channels.py --write    # also write CHANNEL_* into env/.env

It checks every configured channel username + any CHANNEL_* already in env,
calls Telegram getChat, and prints:
    ✓ TSPSC  @StudentUpTSPSC  "StudentUp TSPSC Quiz"  -1001234567890

Numeric ids are best (usernames can be renamed). --write preserves comments
and never touches other env vars. If a channel is missing, it says so.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import config  # noqa: E402


def main():
    if not config.BOT_TOKEN:
        print("BOT_TOKEN not set — paste it in env/.env first.")
        print("(Get it from @BotFather. The bot must be ADMIN in each channel.)")
        return 1

    from core.telegram import Telegram, TelegramError
    tg = Telegram(dry=False)
    try:
        me = tg._call("getMe", {})
        bot = me.get("result", {}).get("username", "?")
        print(f"Authenticated as @{bot}\n")
    except TelegramError as e:
        print("getMe failed — check BOT_TOKEN, network:", e)
        return 1

    # Candidates: explicit env CHANNEL_* first, then config default usernames.
    targets = {}
    for key, cfg in config.CHANNELS.items():
        explicit = config.env(f"CHANNEL_{key}", "").strip()
        uname = cfg.get("username", "")
        candidates = [explicit] if explicit else []
        if uname:
            candidates.append("@" + uname.lstrip("@"))
        # de-dup, keep order
        seen = set()
        targets[key] = [c for c in candidates
                        if c and not (c in seen or seen.add(c))]

    results = {}
    for key, cands in targets.items():
        chat = config.channel_chat_id(key)
        chat = chat or (cands[0] if cands else "")
        if not chat:
            print(f"  - {key:8s} no target configured")
            continue
        try:
            r = tg._call("getChat", {"chat_id": chat})
            res = r.get("result", {})
            cid = res.get("id", chat)
            title = res.get("title") or res.get("username", "?")
            typ = res.get("type", "?")
            results[key] = str(cid)
            print(f"  ✓ {key:8s} {str(chat):28s} {typ:9s} "
                  f"\"{str(title)[:34]}\"  ->  {cid}")
        except TelegramError as e:
            print(f"  ✗ {key:8s} {str(chat):28s} not found/admin: {str(e)[:70]}")
        time.sleep(0.4)

    if "--write" in sys.argv and results:
        write_env(results)
        print("\nenv/.env updated with numeric ids (comments preserved).")
    return 0


def write_env(results: dict):
    """Idempotently set CHANNEL_<KEY>=<id> in env/.env, keeping comments."""
    path = config.ENV_FILE
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines() if text else []
    out, seen = [], set()
    for ln in lines:
        line = ln.strip()
        if "=" in line and not line.startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in {f"CHANNEL_{k}" for k in results}:
                seen.add(key)
                out.append(f"{key}={results[key.split('_', 1)[1]]}")
                continue
        out.append(ln)
    for key, val in results.items():
        var = f"CHANNEL_{key}"
        if var not in seen:
            out.append(f"{var}={val}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
