# -*- coding: utf-8 -*-
"""📄 370X: PAPER FACTORY — one drop turns official paper PDFs
into a *reviewed* question draft, never straight into the bank.

Layers (best available wins; no hard dependency on heavy tools):
  1. Docling — IBM's MIT document AI (layout + tables) when the
     optional package is installed. On the free VM this is a
     night-batch job; live traffic never waits on it.
  2. Native fallback — collector.pdf_to_text (pdftotext ->
     pypdf) + collector.text_to_lines, which already repairs
     glued options + official numeric key rows.

Safety posture (Trust pillar):
  * Extracted papers are always SOURCE-TAGGED: paper provenance
    (exam/year parsed from the filename) travels with every
    question, so counts stay honest.
  * Output lands in data/paper_drafts.json as a DRAFT.
    Owner review (Approve-style) is required before go_bank()
    merges anything into data/scraped_bank.json.
  * Duplicate content (bank signature) is dropped at draft time
    and again at merge time (load_bank dedupes too).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config
from .store import load_json, now_iso, save_json_atomic

MAX_TEXT_CHARS = 2_000_000

_EXAM_HINTS = (
    ("tspsc", "TSPSC"), ("appsc", "APPSC"), ("ssc", "SSC"),
    ("rrb", "RAILWAY"), ("railway", "RAILWAY"), ("ibps", "BANKING"),
    ("sbi", "BANKING"), ("police", "POLICE"), ("nda", "DEFENCE"),
    ("cds", "DEFENCE"), ("inter", "INTER"), ("ssc board", "10TH"),
)


# -------------------------------------------------------------- provenance
def paper_meta(filename: str) -> dict:
    """Exam/year/paper provenance from a filename like
    'TSPSC Group-II 2023 Paper-I.pdf'. Honest: unknown stays ''."""
    name = str(filename or "")
    low = name.lower()
    exam = ""
    for key, label in _EXAM_HINTS:
        if key in low:
            exam = label
            break
    ym = re.search(r"(20[0-3][0-9]|19[9][0-9])", name)
    pm = re.search(r"paper[\s\-_]*([ivx0-9]+)", low)
    return {"exam": exam, "year": ym.group(1) if ym else "",
            "paper": ("Paper-" + pm.group(1).upper()) if pm else "",
            "file": Path(name).name}


# -------------------------------------------------------------- extraction
def extract_text(path) -> tuple:
    """(text, extractor_name). Docling first when installed,
    else the collector's proven native chain."""
    p = Path(path)
    if p.suffix.lower() == ".txt":
        return p.read_text(encoding="utf-8", errors="replace"), "txt"
    if p.suffix.lower() != ".pdf":
        return "", "unsupported"
    try:
        from docling.document_converter import DocumentConverter
        doc = DocumentConverter().convert(str(p)).document
        text = doc.export_to_markdown()
        if text and text.strip():
            return text[:MAX_TEXT_CHARS], "docling"
    except Exception:
        pass  # not installed / failed -> native fallback
    from . import collector
    return (collector.pdf_to_text(p) or "")[:MAX_TEXT_CHARS], "native"


def parse_questions(text: str, meta: dict, source_file: str = "") -> list:
    """Paper TEXT -> validated question dicts (bank-ready shape).

    Uses the collector's proven tolerant parser + normalizer with
    an official-paper provenance stamp; keeps only rows passing
    the bank validator. Nothing is written anywhere."""
    from . import collector
    from .question_bank import validate_question
    lines = collector.text_to_lines(text or "")
    raws = collector.parse_quiz_lines(lines, article_title=source_file,
                                      url="paper://")
    stamp = {"exam": meta.get("exam", ""),
             "year": meta.get("year", ""),
             "paper": meta.get("paper", "")}
    out = []
    for i, raw in enumerate(raws):
        q, needs_tx = collector.normalize_raw(
            raw, source_file or meta.get("file", ""), i + 1,
            stamp=stamp)
        pending = False
        if q is None and needs_tx:
            # 📝 No translator available: park it INSIDE the draft
            # (collector's scraped_pending.json has a separate
            # retry flow for web sources). The draft keeps the
            # parsed question flagged for owner/translator review;
            # ONLY the go_bank step gates it — drafts never serve
            # students directly.
            q = _untranslated_q(raw, stamp, source_file, i + 1)
            pending = True
        if not q:
            continue
        q["bank"] = "pyq"
        q["source"] = "pyq"
        if not q.get("id") or str(q["id"]).startswith("S"):
            q["id"] = (f"PAPER-{meta.get('exam') or 'EXAM'}-"
                       f"{meta.get('year') or 'NA'}-{i + 1:03d}")
        if pending:
            q["translation_pending"] = True
            out.append(q)          # draft-only; go_bank re-gates it
        elif not validate_question(q):
            out.append(q)
    return out


def _untranslated_q(raw, stamp, source_file, idx) -> dict:
    """EN-master fallback for papers when no translator/LLM is
    available. Mirrors normalize_raw's own non-worded fallback
    shape (q_te mirrors the stem) and flags needs_translation so
    drafts report the gap honestly instead of hiding it."""
    from . import collector
    q = {"id": "", "channel": collector.infer_channel(
             source_file, raw.get("q_en", "")),
         "topic": collector.infer_topic(source_file,
                                        raw.get("q_en", "")),
         "q_en": raw["q_en"], "q_te": raw["q_en"],
         "options_en": raw["options_en"],
         "options_te": [str(o) for o in raw["options_en"]],
         "answer_index": raw["answer_index"],
         "explanation_en": raw.get("explanation_en", ""),
         "explanation_te": raw.get("explanation_en", ""),
         "note": "", "source": "pyq", "bank": "pyq",
         "needs_translation": True,
         "provenance": f"{source_file} :: paper://"}
    q.update({k: v for k, v in (stamp or {}).items() if v})
    return q


def _esc(s: str) -> str:
    import html as _h
    return _h.escape(str(s or ""))


# -------------------------------------------------------------- draft store
def _drafts_path() -> Path:
    return config.DATA / "paper_drafts.json"


def _load_drafts() -> dict:
    d = load_json(_drafts_path(), {"drafts": {}})
    return d if isinstance(d, dict) else {"drafts": {}}


def _bank_signatures() -> set:
    """Signatures a new paper must not duplicate: the served bank
    PLUS scraped_bank.json (approved papers land there before the
    next bank rebuild folds them into question_bank.json)."""
    from .question_bank import load_bank, q_signature
    sigs = set()
    try:
        bank = load_bank()
        qs = bank.questions if hasattr(bank, "questions") else list(bank)
        sigs |= {q_signature(q) for q in qs}
    except Exception:
        pass
    try:
        scraped = load_json(config.DATA / "scraped_bank.json",
                            {"questions": []})
        sigs |= {q_signature(q)
                 for q in (scraped.get("questions") or [])}
    except Exception:
        pass
    return sigs


def make_draft(path, title: str = "") -> dict:
    """Full pipeline: file -> text -> validated draft manifest.
    Registers the draft in paper_drafts.json (status: draft).
    Never touches the bank."""
    p = Path(path)
    meta = paper_meta(title or p.name)
    text, extractor = extract_text(p)
    if not text.strip():
        return {"ok": False, "error": "PDF nunchi text raledu "
                "(scanned image PDF ayithe OCR kavali — 380X roadmap).",
                "extractor": extractor, "meta": meta}
    qs = parse_questions(text, meta, title or p.name)
    from .question_bank import q_signature
    bank_sigs = _bank_signatures()
    fresh, dup = [], 0
    for q in qs:
        if q_signature(q) in bank_sigs:
            dup += 1
        else:
            fresh.append(q)
    d = _load_drafts()
    did = "PD-" + re.sub(r"[^A-Za-z0-9]+", "-",
                         (title or p.stem))[:40].strip("-") + \
        "-" + now_iso()[:10]
    draft = {"id": did, "file": p.name, "title": title or p.stem,
             "meta": meta, "extractor": extractor,
             "status": "draft", "created": now_iso(),
             "parsed": len(qs), "duplicates": dup,
             "needs_translation":
                 sum(1 for q in fresh if q.get("translation_pending")),
             "questions": fresh}
    d.setdefault("drafts", {})[did] = draft
    save_json_atomic(_drafts_path(), d)
    return {"ok": True, "draft_id": did, "extractor": extractor,
            "parsed": len(qs), "fresh": len(fresh), "duplicates": dup,
            "needs_translation": draft["needs_translation"],
            "meta": meta}


def list_drafts() -> list:
    d = _load_drafts()
    return [{"id": k, "file": v.get("file"), "status": v.get("status"),
             "parsed": v.get("parsed", 0),
             "fresh": len(v.get("questions") or []),
             "meta": v.get("meta"), "created": v.get("created")}
            for k, v in (d.get("drafts") or {}).items()]


def go_bank(draft_id: str, by: str = "owner") -> dict:
    """Approve path: merge a draft into data/scraped_bank.json.
    Signature-deduped against the live bank again at merge time.
    Draft is kept with status 'banked' (auditable)."""
    d = _load_drafts()
    draft = (d.get("drafts") or {}).get(draft_id)
    if not draft:
        return {"ok": False, "error": "Draft dorakaledu."}
    if draft.get("status") == "banked":
        return {"ok": False, "error": "Ee draft already bank loki vellindi."}
    bank_file = config.DATA / "scraped_bank.json"
    cur = load_json(bank_file, {"questions": []})
    cur_qs = cur.get("questions") or []
    from .question_bank import q_signature
    sigs = _bank_signatures() | {q_signature(q) for q in cur_qs}
    added, dup, pending = 0, 0, 0
    for q in draft.get("questions") or []:
        if q.get("translation_pending"):
            pending += 1           # bank is strict: never bank
            continue                # untranslated questions
        if q_signature(q) in sigs:
            dup += 1
            continue
        sigs.add(q_signature(q))
        cur_qs.append(q)
        added += 1
    save_json_atomic(bank_file, {"questions": cur_qs})
    # Partial bank (some pending translation) stays 'draft' so the
    # owner can re-run after translation; full bank is terminal.
    draft["status"] = "draft" if pending else "banked"
    draft["banked_by"] = by
    draft["banked_at"] = now_iso()
    draft["banked_added"] = added
    save_json_atomic(_drafts_path(), d)
    return {"ok": True, "added": added, "duplicates": dup,
            "translation_pending": pending,
            "total_in_scraped": len(cur_qs)}


def reject_draft(draft_id: str, by: str = "owner") -> dict:
    d = _load_drafts()
    draft = (d.get("drafts") or {}).get(draft_id)
    if not draft:
        return {"ok": False, "error": "Draft dorakaledu."}
    if draft.get("status") == "banked":
        return {"ok": False, "error": "Banked draft reject avvadu."}
    if draft.get("status") == "rejected":
        return {"ok": False, "error": "Draft already rejected."}
    draft["status"] = "rejected"
    draft["rejected_by"] = by
    save_json_atomic(_drafts_path(), d)
    return {"ok": True, "draft_id": draft_id}
