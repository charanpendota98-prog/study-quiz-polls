"""
Audit Log — who did what, when (admin-action trail, company-style).

Append-only JSONL at data/audit_log.jsonl, auto-trimmed to the last
~1000 entries. Dashboard wires it into sensitive actions (flag toggles,
planner settings, item-intel resets, manual setup). Never raises —
auditing must never break the action it records.

CLI:  python3 -m core.auditlog
"""
from __future__ import annotations

import json
from datetime import datetime

from . import config

AUDIT_FILE = config.DATA / "audit_log.jsonl"
_MAX_BYTES = 512 * 1024        # trim when the file passes ~512 KB
_KEEP = 1000


def log(action: str, detail: str = "", actor: str = "dashboard"):
    try:
        entry = {
            "ts": datetime.now(config.IST).strftime("%Y-%m-%d %H:%M:%S"),
            "actor": str(actor)[:40],
            "action": str(action)[:80],
            "detail": str(detail)[:300],
        }
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        try:
            if AUDIT_FILE.stat().st_size > _MAX_BYTES:
                lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
                AUDIT_FILE.write_text("\n".join(lines[-_KEEP:]) + "\n",
                                      encoding="utf-8")
        except Exception:
            pass
    except Exception:
        pass


def recent(limit: int = 30) -> list:
    """Newest-first parsed entries; corrupt lines are skipped."""
    try:
        if not AUDIT_FILE.exists():
            return []
        lines = AUDIT_FILE.read_text(encoding="utf-8").splitlines()
        out = []
        for line in reversed(lines[-max(1, limit):]):
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


if __name__ == "__main__":
    for e in recent(10):
        print(f"{e.get('ts')}  [{e.get('actor')}] {e.get('action')}  {e.get('detail')}")
