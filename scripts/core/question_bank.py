#!/usr/bin/env python3
"""
STUDENTUP — QUESTION BANK
- Parses the human-maintained quiz_bank_advanced.md into canonical JSON.
- Loads JSON (primary) + AI/offline generated extras; validates every question.
- Rotates questions per channel (no repeat until bank exhausted), balances answer key.
- Rebuild script: `python3 -m core.question_bank --rebuild` from scripts/.
"""
from __future__ import annotations

import re
import random
from pathlib import Path

from . import config
from .store import load_json, save_json_atomic
from .content import validate_question, has_telugu
import re as _re

# Channel name in the "• Channel:" line -> our channel key
_CHANNEL_HINT = {
    "TSPSC": "TSPSC", "APPSC": "APPSC", "Banking": "BANKING", "Railway": "RAILWAY",
    "Police": "POLICE", "Defence": "DEFENCE", "Current Affairs": "CURRENT",
}

# Quiz questions may ONLY come from exam-paper-aligned sources — never from
# news feeds/articles (those feed the CA digest, never the quiz polls).
#   scraped  = collected from exam-prep websites/apps by core.collector
ALLOWED_QUIZ_SOURCES = {"pyq", "curated", "llm-gen", "offline-gen", "scraped", ""}

_OPT_SPLIT = re.compile(r"\s+([A-D])\)\s+")


def _split_options(line: str):
    """'A) x  B) y  C) z  D) w' -> ['x','y','z','w']"""
    # Find A) marker start
    m = re.search(r"A\)\s+", line)
    if not m:
        # fallback: split on double-space runs
        parts = [p.strip() for p in re.split(r"\s{2,}", line) if p.strip()]
        parts = [re.sub(r"^[A-D][\)\.]\s*", "", p) for p in parts]
        return parts[:4]
    start = m.start()
    body = line[start:]
    # insert a delimiter before B) C) D)
    body = re.sub(r"\s+(?=[B-D]\)\s+)", "\x00", body)
    parts = [p.strip() for p in body.split("\x00") if p.strip()]
    out = []
    for p in parts:
        p = re.sub(r"^[A-D]\)\s*", "", p).strip()
        out.append(p)
    return out[:4]


def parse_markdown(md_path: Path = config.BANK_MD):
    """Parse quiz questions (Q## blocks) from the markdown bank."""
    text = md_path.read_text(encoding="utf-8")
    # Split into blocks starting at "Q## ["
    blocks = re.split(r"\n(?=Q\d{2}\s*\[)", text)
    questions = []
    for block in blocks:
        if not re.match(r"Q\d{2}\s*\[", block.strip()):
            continue
        lines = [l.rstrip() for l in block.splitlines() if l.strip()]
        q = {"id": "", "channel": "", "topic": "", "q_en": "", "q_te": "",
             "options_en": [], "options_te": [], "answer_index": None,
             "explanation_en": "", "note": "", "source": "curated", "bank": "md"}
        # header
        hdr = lines[0]
        mid = re.match(r"Q(\d+)\s*\[([^\]]+)\]", hdr)
        if mid:
            num = int(mid.group(1))
            tag = mid.group(2)
            q["id"] = f"Q{num:02d}"
            ch_topic = tag.split("—")
            ch_hint = ch_topic[0].strip().upper()
            q["channel"] = next((v for k, v in _CHANNEL_HINT.items() if k in tag),
                                ch_hint if ch_hint in config.CHANNELS else "")
            q["topic"] = ch_topic[1].strip().title() if len(ch_topic) > 1 else tag
        for ln in lines[1:]:
            if ln.startswith("EN:"):
                q["q_en"] = ln[3:].strip()
            elif ln.startswith("TE:"):
                q["q_te"] = ln[3:].strip()
            elif ln.startswith("Options EN:"):
                q["options_en"] = _split_options(ln[len("Options EN:"):])
            elif ln.startswith("Options TE:"):
                q["options_te"] = _split_options(ln[len("Options TE:"):])
            elif ln.startswith("Correct:"):
                cm = re.search(r"\((\d)\)", ln)
                if cm:
                    q["answer_index"] = int(cm.group(1))
                after = ln.split("→", 1)
                q["explanation_en"] = after[1].strip() if len(after) > 1 else ""
            elif ln.startswith("Note:"):
                q["note"] = ln[5:].strip()
        if q["q_en"] and q["options_en"] and q["answer_index"] is not None:
            questions.append(q)
    return questions


def parse_digest(md_path: Path = config.BANK_MD):
    """Parse the D## CA digest items (non-poll)."""
    text = md_path.read_text(encoding="utf-8")
    items = []
    for m in re.finditer(r"(D\d{2})\s*\[[^\]]*\]\s*\nEN:\s*(.+?)\nTE:\s*(⤷?.+?)(?:\nSource:|$)",
                         text, re.S):
        items.append({"id": m.group(1), "en": m.group(2).strip(),
                      "te": m.group(3).strip().lstrip("⤷").strip()})
    return items


def rebuild_json():
    """Parse MD + PYQ + curated extras + generated extras -> validated bank."""
    questions = parse_markdown()
    # Authentic previous-year questions (highest priority) — all PYQ volumes
    for _pyq_name in ("pyq_bank.json", "pyq_bank_2.json", "pyq_bank_3.json"):
        _pyq = load_json(config.DATA / _pyq_name, {"questions": []})
        questions.extend(_pyq.get("questions", []))
    # Hand-curated bilingual GK/CA extras
    curated = load_json(config.CURATED_EXTRA_JSON, {"questions": []})
    questions.extend(curated.get("questions", []))
    # AI / offline generated extras
    extra = load_json(config.BANK_EXTRA_JSON, {"questions": []})
    questions.extend(extra.get("questions", []))
    # Scraped from exam-prep websites/apps by core.collector (exam-only)
    scraped = load_json(config.DATA / "scraped_bank.json", {"questions": []})
    questions.extend(scraped.get("questions", []))
    # Validate
    valid, errors = [], []
    seen_ids = set()
    for q in questions:
        if q["id"] in seen_ids:
            errors.append(f"{q['id']}: duplicate id")
            continue
        seen_ids.add(q["id"])
        errs = validate_question(q)
        if errs:
            errors.extend(errs)
        else:
            valid.append(q)
    save_json_atomic(config.BANK_JSON, {
        "version": "3.0", "count": len(valid), "questions": valid,
        "errors": errors,
    })
    digest = parse_digest()
    save_json_atomic(config.DATA / "ca_digest_curated.json",
                     {"items": digest})
    return valid, errors


def load_bank(force_rebuild=False):
    """Load canonical bank; rebuild from MD if missing or forced."""
    if force_rebuild or not config.BANK_JSON.exists():
        rebuild_json()
    data = load_json(config.BANK_JSON, {"questions": []})
    qs = data.get("questions", [])
    if not qs and config.BANK_MD.exists():
        qs, _ = rebuild_json()
    return qs


class Bank:
    """Per-channel question access with a PERMANENT no-repeat guarantee."""
    def __init__(self):
        self.questions = [q for q in load_bank()
                          if q.get("source", "pyq") in ALLOWED_QUIZ_SOURCES]
        # rotation history: channel -> list of posted ids (permanent, never reset)
        self.used = load_json(config.STORE_USED, {})
        # content signature set: qid -> signature (so the same question, even
        # regenerated, cannot be posted twice)
        self.shown_sigs = load_json(config.DATA / "shown_signatures.json",
                                    {"sigs": []})
        self._sig_set = set(self.shown_sigs.get("sigs", []))

    def by_channel(self, channel: str):
        return [q for q in self.questions if q.get("channel") == channel]

    def unused(self, channel: str):
        used = set(self.used.get(channel, []))
        sigs = self._sig_set
        out = []
        for q in self.by_channel(channel):
            if q["id"] in used:
                continue
            sig = q_signature(q)
            # never repeat a question with the same content signature
            if sig in sigs:
                continue
            out.append(q)
        return out

    def mark_posted(self, channel: str, questions):
        """Record these questions as permanently shown."""
        ids = self.used.setdefault(channel, [])
        for q in questions:
            ids.append(q["id"])
            self._sig_set.add(q_signature(q))
        self.shown_sigs["sigs"] = sorted(self._sig_set)
        save_json_atomic(config.STORE_USED, self.used)
        save_json_atomic(config.DATA / "shown_signatures.json", self.shown_sigs)

    def pick(self, channel: str, n: int = 10):
        """
        Pick n NEVER-SEEN questions for a round:
          - source priority: PYQ first, then curated, LLM, offline-generated
          - topic diversity + answer-key balance
        If fewer than n unseen questions remain, auto-generate fresh ones
        (top_up) so the channel NEVER repeats and NEVER runs dry.
        """
        pool = self.unused(channel)
        # Grow until we have at least n unseen. Signature-dedup rejects some
        # freshly generated questions, so top-up may need more than one pass;
        # loop (bounded) so a round is never short and never repeats.
        attempts = 0
        while len(pool) < n and attempts < 8:
            attempts += 1
            try:
                from .generator import top_up
                before = len(pool)
                # Ask for plenty — signature-dedup rejects near-collisions, so
                # the generator must over-produce to guarantee a full round.
                need_each = max(config.FILLER_TRIGGER_UNUSED, n * 6, 40)
                top_up(per_channel_min=need_each)
                self.__init__()
                pool = self.unused(channel)
                if len(pool) <= before:
                    break  # generator could not add distinct items; stop loop
            except Exception as e:
                print(f"   [bank] auto top-up note: {e}")
                break
        src_rank = {"pyq": 0, "curated": 1, "llm-gen": 2, "offline-gen": 3}
        pyqs = [q for q in pool if q.get("source") == "pyq"]
        rest = [q for q in pool if q.get("source") != "pyq"]
        ordered = pyqs[:max(1, n * 4 // 10)] + rest
        chosen, topics_used, keys_used = [], {}, [0, 0, 0, 0]
        candidates = ordered[:]
        while len(chosen) < n and candidates:
            def score(q):
                return (src_rank.get(q.get("source", "offline-gen"), 3) * 0
                        + topics_used.get(q.get("topic", ""), 0) * 2
                        + keys_used[q["answer_index"]] + random.random())
            candidates.sort(key=score)
            q = candidates.pop(0)
            chosen.append(q)
            topics_used[q.get("topic", "")] = topics_used.get(q.get("topic", ""), 0) + 1
            keys_used[q["answer_index"]] += 1
        self.mark_posted(channel, chosen)      # PERMANENT — never repeat
        return chosen

    def by_id(self, qid):
        for q in self.questions:
            if q["id"] == qid:
                return q
        return None

    def pick_adaptive(self, channel, weak_topics=None, review_qids=None):
        """
        One personalised question: due spaced-repetition card -> weak-topic
        fresh question -> normal balanced pick. Never repeats seen content.
        """
        # 1) spaced-repetition review (re-ask a previously missed question)
        if review_qids:
            for rqid in review_qids:
                q = self.by_id(rqid)
                if q:
                    return q
        pool = self.unused(channel) or self.by_channel(channel)
        # 2) weak topic (fresh, unseen)
        if weak_topics:
            for wt in weak_topics:
                for q in pool:
                    if wt in (q.get("topic", "") or "").lower():
                        self.mark_posted(channel, [q])
                        return q
        # 3) normal single pick (rotation + mark posted)
        qs = self.pick(channel, 1)
        if qs:
            return qs[0]
        return pool[0] if pool else None

    def stats(self):
        out = {}
        for ch in config.CHANNELS:
            allq = self.by_channel(ch)
            used = set(self.used.get(ch, []))
            out[ch] = {"total": len(allq), "unused": len(self.unused(ch)),
                       "posted": len(used)}
        return out


def q_signature(q: dict) -> str:
    """
    Content identity of a question — topic + its key numbers + answer.
    Two generated questions with the same topic, values and answer are the
    SAME question (even with different ids), so the no-repeat engine blocks it.
    """
    nums = ".".join(sorted(_re.findall(r"\d+", q.get("q_en", ""))))
    words = "".join(sorted(
        set(_re.findall(r"[a-z]{4,}", (q.get("q_en", "") or "").lower()))))[:40]
    # NOTE: answer_index is deliberately excluded — shuffling the 4 options
    # must not make the SAME question look new.
    return f"{q.get('channel','')}|{q.get('topic','')}|{nums}|{words}"


if __name__ == "__main__":
    import argparse, sys
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.rebuild:
        qs, errs = rebuild_json()
        print(f"Rebuilt bank: {len(qs)} valid questions, {len(errs)} errors")
        for e in errs:
            print("  ✗", e)
    if a.stats or True:
        b = Bank()
        for ch, s in b.stats().items():
            print(f"  {ch:9s} total={s['total']:3d} unused={s['unused']:3d}")
        d = parse_digest()
        print(f"  CA digest curated items: {len(d)}")
