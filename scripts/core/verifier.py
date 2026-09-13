#!/usr/bin/env python3
"""
STUDENTUP — QUESTION VERIFIER (API-key powered, consensus, quarantine)
=====================================================================
Every scraped / PDF / generated question is checked with the LLM keys
BEFORE it may be posted as a poll:

  1. Structural gate (offline, always): 4 distinct options, key in range,
     Telugu present, no answer leak in the stem, numbers preserved EN↔TE.
  2. Answer audit (LLM): the model solves the question blind (it is NOT
     shown our key), returns its answer + confidence. Second provider is
     asked when the first disagrees with our key (consensus).
  3. Translation audit (LLM): Telugu must be a faithful exam-paper
     translation — same meaning, same numbers, options same order.

Outcomes (data/verify_state.json, keyed by question id):
   ok          → postable, badge "✅ verified"
   fixed       → our key was wrong; 2 providers agreed on another option
                 with high confidence → answer_index corrected in the bank
   quarantine  → unclear/contradictory → NEVER posted, listed in /verify
   pending     → no key available yet → PYQ/curated post as before,
                 scraped waits (STRICT mode) or posts (LENIENT mode)

CLI:
  python3 -m core.verifier run [--limit N] [--only CH] [--dry]
  python3 -m core.verifier status
  python3 -m core.verifier requeue ID
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime

from . import config
from .store import load_json, save_json_atomic

STATE_FILE = config.DATA / "verify_state.json"
_TE = re.compile(r"[\u0C00-\u0C7F]")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")

STRICT_SOURCES = {"scraped", "llm-gen", "offline-gen"}   # must be verified when a key exists
TRUSTED_SOURCES = {"pyq", "curated"}                     # verified opportunistically

_SOLVE_SYS = (
    "You are a strict examiner for Indian competitive exams (TSPSC, APPSC, SSC, RRB, "
    "IBPS, Police, NDA). Solve the multiple-choice question yourself. Do not guess the "
    "setter's intent; use facts and calculation. Output ONLY JSON: "
    '{"answer_index": 0-3, "confidence": 0.0-1.0, "reason": "<=25 words", '
    '"flags": ["ambiguous"|"outdated"|"multiple_correct"|"no_correct"|"bad_options" ...]}'
)
_TX_SYS = (
    "You audit Telugu translations of exam MCQs. Compare the English and Telugu question "
    "and options. Output ONLY JSON: "
    '{"faithful": true|false, "issues": ["..."], "fixed_q_te": str|null, '
    '"fixed_options_te": [4 str]|null}. Mark faithful=false if meaning changes, a number/'
    "year/unit differs, option order differs, Devanagari appears, or the Telugu is not "
    "natural exam-paper Telugu. Only supply fixes when you are certain."
)


def _state():
    return load_json(STATE_FILE, {"questions": {}, "runs": []})


def _parse(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None


# ------------------------------------------------------------ offline gate
def structural_issues(q: dict) -> list:
    issues = []
    opts = q.get("options_en") or []
    if len(opts) != 4:
        issues.append("options!=4")
    if len({(o or "").strip().lower() for o in opts}) != len(opts):
        issues.append("duplicate_options")
    ai = q.get("answer_index")
    if not isinstance(ai, int) or not 0 <= ai < 4:
        issues.append("bad_answer_index")
    qe = (q.get("q_en") or "").strip()
    if len(qe) < 12:
        issues.append("stem_too_short")
    qt = (q.get("q_te") or "").lstrip("⤷").strip()
    if not _TE.search(qt):
        issues.append("no_telugu")
    if re.search(r"[\u0900-\u097F]", qt + " ".join(q.get("options_te") or [])):
        issues.append("devanagari_in_telugu")
    if isinstance(ai, int) and 0 <= ai < len(opts):
        ans = (opts[ai] or "").strip().lower()
        if len(ans) > 3 and re.search(r"\b" + re.escape(ans) + r"\b", qe.lower()):
            issues.append("answer_leak_in_stem")
    if _TE.search(qt) and sorted(_NUM.findall(qe)) != sorted(_NUM.findall(qt)) and \
            _NUM.findall(qe) and qt != qe:
        # Telugu digits are normalised by translator; a mismatch means a lost number
        issues.append("numbers_differ_en_te")
    if re.search(r"\b(all|none) of the above\b", " ".join(opts), re.I) and \
            (q.get("source") in ("offline-gen", "llm-gen")):
        issues.append("weak_generated_options")
    return issues


# ------------------------------------------------------------ LLM audits
def _solve(llm, q, provider_skip=None):
    payload = {"question": q.get("q_en"), "options": q.get("options_en")}
    out = llm.chat(_SOLVE_SYS, json.dumps(payload, ensure_ascii=False))
    d = _parse(out) or {}
    try:
        ai = int(d.get("answer_index"))
        conf = float(d.get("confidence", 0))
    except Exception:
        return None
    if not 0 <= ai < 4:
        return None
    return {"answer_index": ai, "confidence": max(0.0, min(1.0, conf)),
            "reason": str(d.get("reason", ""))[:160],
            "flags": [str(f) for f in (d.get("flags") or [])][:6]}


def _audit_translation(llm, q):
    payload = {"q_en": q.get("q_en"), "options_en": q.get("options_en"),
               "q_te": (q.get("q_te") or "").lstrip("⤷").strip(),
               "options_te": q.get("options_te")}
    d = _parse(llm.chat(_TX_SYS, json.dumps(payload, ensure_ascii=False))) or {}
    return d


def verify_question(q: dict, llm=None, second_llm=None) -> dict:
    """Return verdict dict: status ok|fixed|quarantine|pending, details, patch."""
    issues = structural_issues(q)
    if issues:
        return {"status": "quarantine", "why": issues, "patch": {}}
    if llm is None or not getattr(llm, "available", lambda: False)():
        return {"status": "pending", "why": ["no_api_key"], "patch": {}}

    ours = q["answer_index"]
    v1 = _solve(llm, q)
    if v1 is None:
        return {"status": "pending", "why": ["llm_no_answer"], "patch": {}}
    hard_flags = {"multiple_correct", "no_correct", "bad_options"} & set(v1["flags"])
    if hard_flags:
        return {"status": "quarantine", "why": sorted(hard_flags) + [v1["reason"]], "patch": {}}

    patch = {}
    if v1["answer_index"] == ours:
        answer_status = "ok"
    else:
        # disagreement → ask again (second provider if given, else same chain)
        v2 = _solve(second_llm or llm, q)
        if v2 and v2["answer_index"] == v1["answer_index"] and \
                min(v1["confidence"], v2["confidence"]) >= 0.85 and \
                q.get("source") not in TRUSTED_SOURCES:
            answer_status = "fixed"
            patch["answer_index"] = v1["answer_index"]
        elif v2 and v2["answer_index"] == ours and v2["confidence"] >= 0.7:
            answer_status = "ok"        # first model slipped; ours confirmed
        else:
            return {"status": "quarantine",
                    "why": [f"key_disagree ours={ours} llm={v1['answer_index']}",
                            v1["reason"]], "patch": {}}

    tx = _audit_translation(llm, q)
    if tx and tx.get("faithful") is False:
        fq, fo = tx.get("fixed_q_te"), tx.get("fixed_options_te")
        if fq and _TE.search(fq) and isinstance(fo, list) and len(fo) == 4:
            patch["q_te"], patch["options_te"] = fq, fo
        else:
            return {"status": "quarantine",
                    "why": ["telugu_unfaithful"] + [str(i) for i in (tx.get("issues") or [])][:3],
                    "patch": patch}
    return {"status": answer_status, "why": [v1["reason"]] if v1.get("reason") else [],
            "patch": patch}


# ------------------------------------------------------------ batch runner
def _bank_files():
    from . import question_bank as qb  # noqa
    return [config.DATA / "scraped_bank.json", config.BANK_EXTRA_JSON,
            config.CURATED_EXTRA_JSON, config.DATA / "pyq_bank.json",
            config.DATA / "pyq_bank_2.json", config.DATA / "pyq_bank_3.json",
            config.DATA / "pyq_bank_4_ssc.json"]


def _apply_patch(qid, patch, dry):
    if not patch or dry:
        return False
    for f in _bank_files():
        d = load_json(f, None)
        if not d:
            continue
        hit = False
        for q in d.get("questions", []):
            if q.get("id") == qid:
                q.update(patch)
                q["verified_patch"] = sorted(patch)
                hit = True
        if hit:
            save_json_atomic(f, d)
            return True
    return False


def run(limit=120, only=None, dry=False, llm=None, include_trusted=True):
    from .question_bank import load_bank, rebuild_json
    if llm is None:
        try:
            from .llm import LLM
            c = LLM()
            llm = c if c.available() else None
        except Exception:
            llm = None
    st = _state()
    done = st["questions"]
    todo = []
    for q in load_bank():
        if only and q.get("channel") != only:
            continue
        rec = done.get(q["id"])
        if rec and rec["status"] in ("ok", "fixed", "quarantine"):
            continue
        if q.get("source") in TRUSTED_SOURCES and not include_trusted:
            continue
        todo.append(q)
    # strict sources first, newest first
    todo.sort(key=lambda q: (q.get("key_confidence") != "crowd",      # crowd keys first: they can't post until verified
                             q.get("source") in TRUSTED_SOURCES,
                             -(len(q.get("collected_on") or ""))))
    stats = {"checked": 0, "ok": 0, "fixed": 0, "quarantine": 0, "pending": 0,
             "llm": bool(llm)}
    patched = False
    for q in todo[:limit]:
        v = verify_question(q, llm)
        stats["checked"] += 1
        stats[v["status"]] += 1
        if v["status"] == "pending" and not llm:
            # offline: only structural results are meaningful; don't spam state
            continue
        done[q["id"]] = {"status": v["status"], "why": v["why"][:4],
                         "on": datetime.now(config.IST).strftime("%Y-%m-%d"),
                         "source": q.get("source"), "channel": q.get("channel")}
        if v["patch"]:
            patched |= _apply_patch(q["id"], v["patch"], dry)
        if not llm:
            break
    if not dry:
        st["runs"] = (st.get("runs") or [])[-30:] + [
            {"on": datetime.now(config.IST).isoformat(timespec="minutes"), **stats}]
        save_json_atomic(STATE_FILE, st)
        if patched:
            rebuild_json()
    print(f"[verify] {stats}")
    return stats


def status_of(qid: str) -> str:
    return (_state()["questions"].get(qid) or {}).get("status", "pending")


def postable(q: dict, strict: bool | None = None) -> bool:
    """Gate used by the bank. strict=None → config VERIFY_STRICT (default True
    once any API key is configured, else lenient)."""
    s = status_of(q.get("id", ""))
    if s in ("ok", "fixed"):
        return True
    if s == "quarantine":
        return False
    if q.get("key_confidence") == "crowd":
        return False                 # crowd-sourced key is never posted unverified
    if strict is None:
        strict = _strict_default()
    src = q.get("source", "pyq")
    if src in TRUSTED_SOURCES:
        return True
    if structural_issues(q):
        return False
    return not strict


def _strict_default() -> bool:
    v = getattr(config, "VERIFY_STRICT", "auto")
    if isinstance(v, bool):
        return v
    try:
        from .llm import LLM
        return LLM().available()
    except Exception:
        return False


def status_text() -> str:
    st = _state()
    qs = st["questions"]
    from collections import Counter
    c = Counter(r["status"] for r in qs.values())
    lines = [f"🔎 Verify: ✅ ok {c.get('ok', 0)} · 🛠 fixed {c.get('fixed', 0)} · "
             f"⛔ quarantine {c.get('quarantine', 0)} · ⏳ pending {c.get('pending', 0)}"]
    per = Counter((r.get("channel"), r["status"]) for r in qs.values())
    for ch in config.CHANNELS:
        ok = per.get((ch, "ok"), 0) + per.get((ch, "fixed"), 0)
        bad = per.get((ch, "quarantine"), 0)
        if ok or bad:
            lines.append(f"  {ch}: ✅{ok} ⛔{bad}")
    if st.get("runs"):
        r = st["runs"][-1]
        lines.append(f"last run {r['on']}: checked {r['checked']} (llm={'yes' if r.get('llm') else 'no'})")
    bad = [(k, v) for k, v in qs.items() if v["status"] == "quarantine"][-5:]
    for k, v in bad:
        lines.append(f"  ⛔ {k}: {', '.join(v['why'][:2])[:80]}")
    return "\n".join(lines)


def requeue(qid):
    st = _state()
    st["questions"].pop(qid, None)
    save_json_atomic(STATE_FILE, st)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "status", "requeue"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--limit", type=int, default=120)
    ap.add_argument("--only")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.cmd == "run":
        run(limit=a.limit, only=a.only, dry=a.dry)
    elif a.cmd == "status":
        print(status_text())
    else:
        requeue(a.arg); print("requeued", a.arg)
