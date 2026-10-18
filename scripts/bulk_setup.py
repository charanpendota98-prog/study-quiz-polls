#!/usr/bin/env python3
"""
STUDENTUP — BULK SETUP CLI (Excel/CSV tho groups & channels easy setup)

    python3 scripts/bulk_setup.py sample [--out samples/StudentUp_Bulk_Setup_Template.xlsx]
    python3 scripts/bulk_setup.py import FILE.xlsx [--dry-run] [--sheets Police_SI_Groups,📢 Telegram_Channels]
    python3 scripts/bulk_setup.py import FILE.csv  [--dry-run]

- sample  : dashboard lo vunde ade advanced template ni file ga isthundi
            (Instructions + WhatsApp sheets + 📢 Telegram_Channels sheet).
- import  : WhatsApp groups (invite link/JID) + Telegram channels/groups
            register chestundi, Daily Times unte auto-schedules kuda.
- --dry-run: emi write cheyadu — kevalam validation report (errors,
            duplicates) matrame chupistundi. Mundhu idhi run cheyandi!
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import bundle_manager  # noqa: E402


def _print_report(res: dict, dry: bool):
    mode = "DRY-RUN (emí write cheyaleedu)" if dry else "LIVE IMPORT"
    print(f"\n===== {mode} =====")
    if res.get("sheets_processed"):
        print(f"Sheets: {', '.join(res['sheets_processed'])}")
        for sname, s in (res.get("per_sheet") or {}).items():
            _sched = s['schedules'] or s.get('schedules_would_create', 0)
            _lbl = "schedule(s) avuthaayi (dry)" if dry and s.get('schedules_would_create') else "schedule(s)"
            print(f"  · {sname}: +{s['groups']} WA group(s), +{s['channels']} TG channel(s), "
                  f"{_sched} {_lbl}, {s['skipped_duplicates']} duplicate skip, "
                  f"{s['errors']} error(s)")
    print(f"WhatsApp groups added : {res.get('imported_groups_count', 0)}")
    print(f"Telegram channels add : {res.get('imported_channels_count', 0)}")
    print(f"Schedules created     : {len(res.get('schedules_created') or [])} WA + "
          f"{len(res.get('tg_schedules_created') or [])} TG")
    if res.get("skipped_duplicates_count"):
        print(f"Duplicates skipped    : {res['skipped_duplicates_count']} (already register ayinavi)")
    errs = res.get("errors") or []
    if errs:
        print(f"\n❌ Errors ({len(errs)}):")
        for e in errs:
            where = f"{e.get('sheet', '')} row {e.get('row')}".strip()
            print(f"  - [{where}] {e.get('name', '')}: {e.get('reason')}")
    if not dry and (res.get('imported_groups_count') or res.get('imported_channels_count')):
        print("\n✅ Ayipoyindi! Dashboard → WhatsApp/Telegram tabs lo chudandi, "
              "schedules auto ga run avuthaayi.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="StudentUp bulk setup (Excel/CSV)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample", help="sample Excel template file generate chey")
    s.add_argument("--out", default="samples/StudentUp_Bulk_Setup_Template.xlsx")

    i = sub.add_parser("import", help="Excel/CSV nunchi groups+channels import chey")
    i.add_argument("file")
    i.add_argument("--dry-run", action="store_true", help="validation matrame, emi write cheyadu")
    i.add_argument("--sheets", default="", help="comma-separated sheet names (Excel only)")

    a = ap.parse_args(argv)

    if a.cmd == "sample":
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(bundle_manager.build_groups_template_xlsx())
        print(f"✅ Sample template: {out} ({out.stat().st_size} bytes)")
        print("   Sheets: 📖 Instructions | ✍️ My_Groups | 📢 Telegram_Channels | "
              "Police_SI_Groups | TET_DSC_Groups | Banking_Groups")
        print("   Excel/LibreOffice lo open chesi mee rows nimpandi, tarvata:")
        print(f"   python3 scripts/bulk_setup.py import {out} --dry-run   # mundu check")
        print(f"   python3 scripts/bulk_setup.py import {out}             # final import")
        return 0

    fp = Path(a.file)
    if not fp.exists():
        print(f"❌ File ledu: {fp}")
        return 2
    sheets = [s.strip() for s in a.sheets.split(",") if s.strip()] or None
    if fp.suffix.lower() in (".xlsx", ".xlsm"):
        res = bundle_manager.import_from_multisheet_excel(
            fp.read_bytes(), sheets, dry_run=a.dry_run)
    else:
        res = bundle_manager.import_from_csv_or_excel_text(
            fp.read_text(encoding="utf-8", errors="replace"), dry_run=a.dry_run)
    _print_report(res, a.dry_run)
    if res.get("errors") and not res.get("imported_groups_count") \
            and not res.get("imported_channels_count"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
