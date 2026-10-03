"""
🗄️ Automatic Daily Backup Engine
Every day the scheduler daemon zips all data files into data/backups/ and
keeps the last 7 — so even if something gets corrupted or deleted, yesterday's
full state is one unzip away. Admin can also download a live zip any time
via the dashboard (💾 Full Backup button).
"""
from __future__ import annotations

import zipfile
from datetime import datetime

from core import config

BACKUP_DIR = config.DATA / "backups"
KEEP_LAST = 7


def make_backup() -> dict:
    """Create data/backups/auto_backup_YYYYMMDD.zip (idempotent per day)."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        dest = BACKUP_DIR / f"auto_backup_{stamp}.zip"
        if dest.exists():
            return {"ok": True, "file": dest.name, "created": False, "note": "today's backup already exists"}
        count = 0
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(config.DATA.glob("*")):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in (".json", ".csv", ".xlsx"):
                    continue
                if f.stat().st_size > 8_000_000:
                    continue
                try:
                    z.write(f, f.name)
                    count += 1
                except Exception:
                    pass
        _prune()
        return {"ok": True, "file": dest.name, "created": True, "files": count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _prune():
    """Keep only the newest KEEP_LAST auto-backups."""
    try:
        zips = sorted(BACKUP_DIR.glob("auto_backup_*.zip"))
        for old in zips[:-KEEP_LAST]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def last_backup_info() -> dict:
    try:
        zips = sorted(BACKUP_DIR.glob("auto_backup_*.zip"))
        if not zips:
            return {"exists": False}
        newest = zips[-1]
        return {
            "exists": True,
            "file": newest.name,
            "size_kb": newest.stat().st_size // 1024,
            "count": len(zips),
        }
    except Exception:
        return {"exists": False}
