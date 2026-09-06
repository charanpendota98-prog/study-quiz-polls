#!/usr/bin/env python3
"""
STUDENTUP — SOURCE AUDIT CLI
Deep, content-gated audit of the central source registry
(data/collector_sources.json). Reads the registry + health store, checks every
source, prints a table, and (by default) updates the registry audit fields.

Usage:
  python3 audit_sources.py                 # full audit (writes registry audit info)
  python3 audit_sources.py --only-enabled  # skip archive/candidate sources
  python3 audit_sources.py --no-write      # check only, touch nothing
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from core import collector, auditor, config  # noqa: E402


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only-enabled", action="store_true",
                    help="skip archive / candidate sources")
    ap.add_argument("--no-write", action="store_true",
                    help="check only — do not update the registry")
    args = ap.parse_args()

    reg = collector.load_registry()
    srcs = reg.get("sources", [])
    print("=" * 78)
    print("STUDENTUP SOURCE AUDIT  —", config.now_ist().strftime("%Y-%m-%d %H:%M IST"))
    print("registry:", config.DATA / "collector_sources.json")
    print("=" * 78)
    print(f"registry: {len(srcs)} sources "
          f"({sum(1 for s in srcs if s.get('enabled'))} enabled, "
          f"{sum(1 for s in srcs if not s.get('enabled'))} disabled/archive)")

    summary = auditor.audit_all(update_registry=not args.no_write,
                                only_enabled=args.only_enabled)

    print("\n%-42s %-8s %-8s %-26s" % ("SOURCE", "STATUS", "ENTRIES", "NOTE"))
    print("-" * 78)
    for s in srcs:
        if args.only_enabled and not s.get("enabled", True):
            continue
        a = s.get("audit", {})
        note = (a.get("note") or "")[:26]
        state = a.get("status", "?")
        h = collector.health_summary()
        entry = ""
        print("%-42s %-8s %-8s %-26s" % (s["name"][:42], state,
                                         entry, note))
    hs = collector.health_summary()
    print("-" * 78)
    print(f"health: ok={hs['ok']} paused={hs['paused']} failing={hs['failing']}")
    print(f"audit : checked={summary['checked']} live={summary['live']} "
          f"warn={summary.get('warn', 0)} dead={summary['dead']} "
          f"changes={summary['enabled_changed']}")
    for scope, rows in summary.get("news", {}).items():
        ok = sum(1 for r in rows if r.get("ok"))
        print(f"news[{scope}]: {ok}/{len(rows)} feeds responding")
    print("=" * 78)


if __name__ == "__main__":
    main()
