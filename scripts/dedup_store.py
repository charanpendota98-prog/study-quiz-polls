#!/usr/bin/env python3
"""COMPATIBILITY WRAPPER — dedup now lives in core/store.py (SeenStore/Dedup).
This preserves the old CLI: prints the engine status and exposes helpers."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from core.store import Dedup, SeenStore, normalize, similarity  # noqa


if __name__ == "__main__":
    d = Dedup()
    print("DEDUP ENGINE — stores: ca (48h) | jobs (12h) | global (6h)")
    print("Atomic JSON writes | TTL-pruned | Jaccard + shingle3 similarity")
    print(f"  ca_seen entries:     {len(d.ca.data)}")
    print(f"  jobs_seen entries:   {len(d.jobs.data)}")
    print(f"  global_seen entries: {len(d.global_.data)}")
