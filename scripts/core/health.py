"""
Deep Health — subsystem-by-subsystem status for the Pro Ops dashboard.

Shallow /api/health already answers "is the dashboard up"; this answers
"will today's rounds actually flow" — bank depth, collector, PYQ factory,
WhatsApp bridges, retry queue, scheduler, tokens, disk, writability,
backup. Each check is independent and guarded: one broken subsystem
never hides the others. Statuses: ok / warn / fail (honest — an offline
bridge in a sandbox is warn with the reason, never fake-ok).

CLI:  python3 -m core.health
"""
from __future__ import annotations

import platform
import shutil
import sys
from datetime import datetime

from . import config
from .store import load_json


def _ck(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": str(detail)[:160]}


def full_report() -> dict:
    checks = []
    dd = config.DATA

    # 📚 question bank
    try:
        bank = load_json(dd / "question_bank.json", {})
        qs = bank if isinstance(bank, list) else bank.get("questions", []) or []
        checks.append(_ck("📚 Question bank",
                          "ok" if len(qs) >= 100 else ("warn" if qs else "fail"),
                          f"{len(qs)} questions in bank"))
    except Exception as e:
        checks.append(_ck("📚 Question bank", "fail", e))

    # 🌐 collector sources
    try:
        reg = load_json(dd / "collector_sources.json", {})
        srcs = reg.get("sources", []) if isinstance(reg, dict) else []
        live = sum(1 for s in srcs if s.get("enabled"))
        checks.append(_ck("🌐 Collector sources",
                          "ok" if live >= 10 else "warn",
                          f"{live}/{len(srcs)} sources live"))
    except Exception as e:
        checks.append(_ck("🌐 Collector sources", "warn", e))

    # 📜 PYQ factory
    try:
        papers = load_json(dd / "pyq_papers.json", {}).get("papers", [])
        st = load_json(dd / "pyq_state.json", {})
        done = sum(1 for pp in papers
                   if st.get(pp.get("url") or pp.get("index"), {}).get("status") == "done")
        checks.append(_ck("📜 PYQ factory", "ok",
                          f"{done}/{len(papers)} papers harvested "
                          f"({len(papers) - done} pending — 02:15/13:45 runs drain)"))
    except Exception as e:
        checks.append(_ck("📜 PYQ factory", "warn", e))

    # 📱 WhatsApp bridges (multi-number pool)
    try:
        from . import whatsapp_pipeline as _wp
        bs = _wp.bridges_status()
        conn = sum(1 for b in bs if b.get("connected"))
        checks.append(_ck("📱 WhatsApp bridges",
                          "ok" if conn else "warn",
                          f"{conn}/{len(bs)} number(s) connected"
                          + ("" if conn else " — bridge offline / QR pending")))
    except Exception as e:
        checks.append(_ck("📱 WhatsApp bridges", "warn", f"status unavailable: {e}"))

    # 🔁 retry queue
    try:
        q = load_json(dd / "wa_retry_queue.json", [])
        n = len(q) if isinstance(q, list) else len(q.get("items", []))
        checks.append(_ck("🔁 WA retry queue", "warn" if n > 50 else "ok",
                          f"{n} pending retries"))
    except Exception as e:
        checks.append(_ck("🔁 WA retry queue", "warn", e))

    # 🗓️ scheduler (in this process?)
    try:
        from . import whatsapp_pipeline as _wp
        running = bool(getattr(_wp, "_SCHEDULER_RUNNING", False))
        checks.append(_ck("🗓️ WA scheduler", "ok" if running else "warn",
                          "running" if running else
                          "not in this process (server lo watch.py separate ga run avuthundi)"))
    except Exception as e:
        checks.append(_ck("🗓️ WA scheduler", "warn", e))

    # ✈️ Telegram token
    try:
        from .telegram import Telegram
        has = bool(Telegram().token)
        checks.append(_ck("✈️ Telegram bot", "ok" if has else "warn",
                          "token configured" if has else "BOT_TOKEN missing in env"))
    except Exception as e:
        checks.append(_ck("✈️ Telegram bot", "warn", e))

    # 👥 members store
    try:
        md = load_json(dd / "members.json", {})
        ms = md.get("members", {}) if isinstance(md, dict) else {}
        reg = sum(1 for m in ms.values() if isinstance(m, dict) and m.get("registered"))
        checks.append(_ck("👥 Members", "ok", f"{reg} registered"))
    except Exception as e:
        checks.append(_ck("👥 Members", "warn", e))

    # 💾 disk + writability
    try:
        free = shutil.disk_usage(str(dd)).free / (1024 ** 3)
        checks.append(_ck("💾 Disk", "fail" if free < 0.2 else ("warn" if free < 1 else "ok"),
                          f"{free:.1f} GB free"))
    except Exception as e:
        checks.append(_ck("💾 Disk", "warn", e))
    try:
        probe = dd / ".health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(_ck("✍️ Data writable", "ok", "read/write OK"))
    except Exception as e:
        checks.append(_ck("✍️ Data writable", "fail", e))

    # 🗄️ backup freshness
    try:
        from . import backup as _bk
        info = _bk.last_backup_info()
        checks.append(_ck("🗄️ Last backup", "ok" if info else "warn",
                          str(info)[:120] if info else "backup info unavailable"))
    except Exception as e:
        checks.append(_ck("🗄️ Last backup", "warn", e))

    overall = ("fail" if any(c["status"] == "fail" for c in checks)
               else "warn" if any(c["status"] == "warn" for c in checks) else "ok")
    return {
        "ok": overall != "fail",
        "overall": overall,
        "generated_at": datetime.now(config.IST).strftime("%Y-%m-%d %H:%M:%S"),
        "checks": checks,
        "system": {"python": sys.version.split()[0], "platform": platform.platform(),
                   "data_dir": str(dd)},
    }


if __name__ == "__main__":
    rep = full_report()
    icon = {"ok": "🟢", "warn": "🟡", "fail": "🔴"}
    print(f"🩺 DEEP HEALTH — overall {rep['overall'].upper()} · {rep['generated_at']}")
    for c in rep["checks"]:
        print(f"  {icon[c['status']]} {c['name']}: {c['detail']}")
