"""
Channel Reaction Text-Polls — 👍 ❤️ 😂 😮 (owner-chosen answer style).

Telegram channel lo native quiz poll badulu, question + 4 options okka
TEXT message ga velthundi; students message ni long-press chesi emoji
tho react chestharu (👍=A ❤️=B 😂=C 😮=D). Window (default 45 min)
tarvata bot ✅ correct answer + 📊 vote % reveal chesthundi.

Data honest ga:
  * message_reaction (user unte) → per-user vote (change/remove support)
  * message_reaction_count (channel anonymous) → aggregate counts
  * reveal time lo bulk counts item_intel loki (record_many) + metrics
    loki velthayi — channel learning loop close avuthundi.
  * DM/member polls matram native quiz ge untayi (named scoring).

Store: data/reaction_polls.json (mtime-cached, lock, never raises).
Bot loop: apply_update(upd) prathi reaction update ki, tick(tg) prathi
cycle lo due reveals ki. CLI: python3 -m core.reaction_polls
"""
from __future__ import annotations

import threading
import time

from . import config
from .store import load_json, save_json_atomic

STORE_FILE = config.DATA / "reaction_polls.json"
REACTION_EMOJIS = ["👍", "❤️", "😂", "😮"]
_LOCK = threading.Lock()
_cache = {"mtime": None, "data": None}
_MAX_RECORDS = 500


def _norm(emoji: str) -> str:
    return (emoji or "").replace("\ufe0f", "")


_EMOJI_NORM = [_norm(e) for e in REACTION_EMOJIS]


def window_minutes() -> int:
    try:
        return max(1, int(getattr(config, "REACTION_WINDOW_MINUTES", 45) or 45))
    except Exception:
        return 45


def _load() -> dict:
    try:
        mt = STORE_FILE.stat().st_mtime
    except Exception:
        mt = None
    if _cache["data"] is None or _cache["mtime"] != mt:
        d = load_json(STORE_FILE, {})
        _cache["data"] = d if isinstance(d, dict) else {}
        _cache["mtime"] = mt
    return _cache["data"]


def _save(d: dict):
    # cap: reveal ayinavi mundu trim (oldest first by posted ts)
    if len(d) > _MAX_RECORDS:
        keys = sorted(d.keys(), key=lambda k: d[k].get("posted", 0))
        for k in keys:
            if len(d) <= _MAX_RECORDS:
                break
            if d[k].get("revealed"):
                d.pop(k, None)
    save_json_atomic(STORE_FILE, d)
    try:
        _cache["mtime"] = STORE_FILE.stat().st_mtime
    except Exception:
        _cache["mtime"] = None
    _cache["data"] = d


def _key(chat_id, message_id) -> str:
    return f"{chat_id}:{message_id}"


# ------------------------------------------------------------------ register
def register(chat_id, message_id, q: dict, channel: str, now_ts: float = None) -> str:
    """Post ayina reaction-poll message ni track chey. Returns store key."""
    now_ts = time.time() if now_ts is None else now_ts
    try:
        from .content import _option_contents, build_explanation
        tf = bool(getattr(config, "TELUGU_FIRST", True))
        opts = _option_contents(q, tf)
        expl = build_explanation(q, tf)
    except Exception:
        opts, expl = [str(o) for o in (q.get("options_en") or [])][:4], ""
    key = _key(chat_id, message_id)
    with _LOCK:
        d = _load()
        d[key] = {
            "chat": str(chat_id), "msg": int(message_id),
            "channel": channel, "qid": q.get("id", ""),
            "topic": q.get("topic", ""),
            "correct": int(q.get("answer_index", 0)),
            "options": opts, "expl": expl,
            "votes": {}, "counts": [0, 0, 0, 0],
            "posted": now_ts, "closes": now_ts + window_minutes() * 60,
            "revealed": False,
        }
        _save(d)
    return key


# ------------------------------------------------------------------ updates
def _emoji_index(reactions) -> int:
    """Reaction list lo mana 4 emojis lo first dhi index; lekapothe -1."""
    for r in reactions or []:
        e = _norm((r or {}).get("emoji", ""))
        if e in _EMOJI_NORM:
            return _EMOJI_NORM.index(e)
    return -1


def apply_update(upd: dict) -> bool:
    """message_reaction / message_reaction_count update ni apply chey.
    Mana poll kadhu / teliyakapothe False (emi cheyyadu)."""
    try:
        if "message_reaction_count" in upd:
            u = upd["message_reaction_count"] or {}
            key = _key((u.get("chat") or {}).get("id"), u.get("message_id"))
            with _LOCK:
                d = _load()
                rec = d.get(key)
                if not rec or rec.get("revealed"):
                    return False
                counts = [0, 0, 0, 0]
                for r in u.get("reactions") or []:
                    e = _norm(((r.get("type") or {}).get("emoji", "")))
                    if e in _EMOJI_NORM:
                        counts[_EMOJI_NORM.index(e)] = int(r.get("total_count", 0))
                rec["counts"] = counts
                _save(d)
            return True
        if "message_reaction" in upd:
            u = upd["message_reaction"] or {}
            key = _key((u.get("chat") or {}).get("id"), u.get("message_id"))
            user = u.get("user") or {}
            uid = user.get("id")
            if uid is None:
                return False        # anonymous → count update ne tally ki
            with _LOCK:
                d = _load()
                rec = d.get(key)
                if not rec or rec.get("revealed"):
                    return False
                idx = _emoji_index(u.get("new_reaction"))
                if idx < 0:
                    rec["votes"].pop(str(uid), None)      # reaction removed
                else:
                    rec["votes"][str(uid)] = idx          # vote / change
                _save(d)
            return True
    except Exception:
        pass
    return False


def tally(rec: dict):
    """(counts[4], total) — per-user votes unte ave, lekapothe aggregate."""
    votes = rec.get("votes") or {}
    if votes:
        counts = [0, 0, 0, 0]
        for idx in votes.values():
            if 0 <= int(idx) < 4:
                counts[int(idx)] += 1
        return counts, sum(counts)
    counts = [int(c) for c in (rec.get("counts") or [0, 0, 0, 0])][:4]
    return counts, sum(counts)


def reveal_text(rec: dict) -> str:
    counts, total = tally(rec)
    ci = int(rec.get("correct", 0))
    emoji = REACTION_EMOJIS[ci] if 0 <= ci < 4 else "✅"
    opt = (rec.get("options") or ["", "", "", ""])[ci] if ci < len(rec.get("options") or []) else ""
    pct = round(100.0 * counts[ci] / total) if total else 0
    lines = [f"✅ Correct answer: {emoji} {opt}",
             f"📊 {total} answers · {pct}% correct ga chepparu"]
    if total:
        dist = " · ".join(f"{REACTION_EMOJIS[i]} {c}" for i, c in enumerate(counts))
        lines.append(f"   {dist}")
    if rec.get("expl"):
        lines.append(rec["expl"])
    return "\n".join(lines)


def due(now_ts: float = None) -> list:
    now_ts = time.time() if now_ts is None else now_ts
    with _LOCK:
        return [dict(r) for r in _load().values()
                if not r.get("revealed") and float(r.get("closes", 0)) <= now_ts]


# ------------------------------------------------------------------ tick
def tick(tg, now_ts: float = None) -> dict:
    """Due polls ki reveal post + learning feed. Bot loop nunchi."""
    now_ts = time.time() if now_ts is None else now_ts
    out = {"revealed": 0, "answers": 0}
    for rec in due(now_ts):
        key = _key(rec["chat"], rec["msg"])
        counts, total = tally(rec)
        try:
            tg.send_message(rec["chat"], reveal_text(rec))
        except Exception:
            continue                    # send fail → next tick retry
        with _LOCK:
            d = _load()
            if key in d:
                d[key]["revealed"] = True
                d[key]["final_counts"] = counts
                _save(d)
        out["revealed"] += 1
        out["answers"] += total
        if total > 0:
            ci = int(rec.get("correct", 0))
            try:
                from . import item_intel
                item_intel.record_many(rec.get("qid", ""), counts[ci],
                                       total - counts[ci],
                                       topic=rec.get("topic", ""),
                                       channel=rec.get("channel", ""))
            except Exception:
                pass
            try:
                from . import metrics
                metrics.incr("answers", total)
                metrics.incr("answers_correct", counts[ci])
            except Exception:
                pass
    return out


def summary() -> dict:
    with _LOCK:
        d = _load()
    open_n = sum(1 for r in d.values() if not r.get("revealed"))
    return {"tracked": len(d), "open": open_n, "revealed": len(d) - open_n,
            "window_min": window_minutes()}


if __name__ == "__main__":
    print(f"👍 REACTION POLLS — {summary()}")
