#!/usr/bin/env python3
"""
STUDENTUP — ZERO-DB JSON STORES + DEDUP ENGINE
- Atomic writes (temp -> rename) so a crash never corrupts a store.
- TTL pruning (ca 48h / jobs 12h / global 6h).
- Similarity: Jaccard on normalized tokens + char-3gram shingles, composite gate.
Pure standard library — 1GB-RAM friendly, no database.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple

from . import config

_STOP = {
    "a", "the", "of", "new", "update", "today", "latest", "is", "are", "was", "were",
    "has", "have", "had", "and", "or", "in", "on", "at", "to", "for", "with", "from",
    "by", "as", "an", "this", "that", "these", "those", "it", "its", "their", "they",
    "them", "we", "us", "our", "you", "your", "i", "me", "my", "he", "she", "him",
    "his", "her", "be", "been", "will", "would", "can", "could", "not", "no",
}


def load_json(path: Path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default if default is not None else {}


def save_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def now_iso() -> str:
    return datetime.now(config.IST).isoformat()


def prune_ttl(store: dict, ttl_hours: float) -> dict:
    """Drop entries older than ttl_hours. Entries are {value, ts} or carry 'ts'."""
    cutoff = datetime.now(config.IST) - timedelta(hours=ttl_hours)
    kept = {}
    for k, v in store.items():
        ts = v.get("ts") if isinstance(v, dict) else None
        if not ts:
            kept[k] = v
            continue
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=config.IST)
        except (ValueError, TypeError):
            kept[k] = v
            continue
        if dt >= cutoff:
            kept[k] = v
    return kept


# ---------------------------------------------------------------------------
# Similarity / fingerprinting
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w for w in text.split() if w not in _STOP and len(w) > 1]
    return " ".join(sorted(set(words)))


def _tokens(text: str) -> set:
    return set(normalize(text).split())


def _shingles(text: str, n: int = 3) -> set:
    t = re.sub(r"\s+", " ", text.lower()).strip()
    return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}


def similarity(a: str, b: str) -> float:
    """Composite similarity in [0,1]. High => near-duplicate."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        jac = 0.0
    else:
        jac = len(ta & tb) / len(ta | tb)
    sa, sb = _shingles(a), _shingles(b)
    shi = len(sa & sb) / len(sa | sb) if (sa and sb) else 0.0
    if jac >= 0.55 or shi >= 0.55:
        return max(jac, shi)
    if jac >= 0.45 and shi >= 0.30:
        return (jac + shi) / 2.0
    return max(jac, shi)


# ---------------------------------------------------------------------------
# SeenStore — one TTL-pruned dedup store
# ---------------------------------------------------------------------------
class SeenStore:
    def __init__(self, path: Path, ttl_hours: float):
        self.path = path
        self.ttl = ttl_hours
        self.data = prune_ttl(load_json(path, {}), ttl_hours)

    def is_dup(self, text: str, threshold: float = 0.55) -> bool:
        fp = normalize(text)
        for key in self.data:
            if normalize(key) == fp and fp:
                return True
            if similarity(text, key) >= threshold:
                return True
        return False

    def add(self, text: str, meta: Optional[dict] = None) -> None:
        entry = {"ts": now_iso(), "ttl": self.ttl}
        if meta:
            entry.update(meta)
        self.data[text[:300]] = entry
        self.data = prune_ttl(self.data, self.ttl)
        save_json_atomic(self.path, self.data)

    def save(self):
        save_json_atomic(self.path, self.data)


class Dedup:
    """Layered dedup across CA / jobs / global stores + in-batch collapse."""
    def __init__(self):
        self.ca = SeenStore(config.STORE_CA_SEEN, config.TTL_CA)
        self.jobs = SeenStore(config.STORE_JOBS_SEEN, config.TTL_JOBS)
        self.global_ = SeenStore(config.STORE_GLOBAL_SEEN, config.TTL_GLOBAL)

    def seen(self, text: str, scope: str = "ca", threshold: float = 0.55) -> bool:
        stores = [self.global_]
        stores.append(self.ca if scope == "ca" else self.jobs)
        return any(s.is_dup(text, threshold) for s in stores)

    def mark(self, text: str, scope: str = "ca", meta: Optional[dict] = None):
        (self.ca if scope == "ca" else self.jobs).add(text, meta)
        self.global_.add(text, meta)

    def batch_collapse(self, items, key=lambda x: x, threshold=0.62):
        """Within a single post, collapse near-duplicates (keep first)."""
        kept = []
        kept_text = []
        for it in items:
            t = key(it)
            if any(similarity(t, k) >= threshold for k in kept_text):
                continue
            kept.append(it)
            kept_text.append(t)
        return kept


# ---------------------------------------------------------------------------
# Generic JSON KV (leaderboard, stats, used-questions)
# ---------------------------------------------------------------------------
class KV:
    def __init__(self, path: Path, default=None):
        self.path = path
        self.data = load_json(path, default if default is not None else {})

    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, k, v):
        self.data[k] = v

    def save(self):
        save_json_atomic(self.path, self.data)
