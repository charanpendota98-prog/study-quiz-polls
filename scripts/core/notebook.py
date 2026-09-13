"""
NotebookLM bridge — turn Google NotebookLM (or any AI notebook) into a PYQ factory
that feeds the SAME validated bank the channels post from.

Why: scraping/PDF text extraction breaks on scanned or oddly laid-out papers.
NotebookLM reads PDFs natively (OCR + layout) and can extract exact questions with the
official key. We give it a strict prompt; it returns a strict block format; the bot
imports the block → validate (4 options, answer, Telugu, no Hindi script, no answer
leak) → provenance stamp (exam · year · paper) → data/notebook_bank.json → rebuild →
posts with "📜 TSPSC Group-2 2024 · Paper-1" on every poll.

Owner flow (no syntax to remember):
  /notebook                → how-to + buttons
  /notebook prompt TSPSC   → copy-ready prompt for that exam (paste in NotebookLM)
  paste output / send .txt or .json to the bot → preview → ✅ Import
  /notebook status         → imported counts per exam

Block format NotebookLM must produce (also accepted: JSON list with the same keys):

  ### Q
  EXAM: TSPSC Group-2 | YEAR: 2024 | PAPER: Paper-1 | QNO: 17 | TOPIC: Indian Polity
  EN: Which article of the Constitution deals with ...?
  TE: రాజ్యాంగంలోని ఏ అధికరణ ... ?
  A) option 1 | ఎంపిక 1
  B) option 2 | ఎంపిక 2
  C) option 3 | ఎంపిక 3
  D) option 4 | ఎంపిక 4
  ANS: B
  EXP: one-line reason (EN) | ఒక లైన్ కారణం (TE)
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from . import config
from .store import load_json, save_json_atomic

BANK = config.DATA / "notebook_bank.json"
DRAFTS = config.DATA / "notebook_drafts.json"
MAX_PER_IMPORT = 200

_LETTER = {"A": 0, "B": 1, "C": 2, "D": 3, "1": 0, "2": 1, "3": 2, "4": 3}


def _now():
    return datetime.now(config.IST)


def _load():
    return load_json(BANK, {"version": "1.0", "count": 0, "questions": [], "imports": []})


# ------------------------------------------------------------------ prompt pack
def exam_names(channel: str) -> str:
    cfg = config.CHANNELS.get(channel, {})
    return cfg.get("audience") or channel


def prompt_for(channel: str, exam: str = "", year: str = "", paper: str = "") -> str:
    channel = channel.upper()
    bp = load_json(config.DATA / "exam_blueprints.json", {}).get("channels", {}).get(channel, {})
    subjects = ", ".join(f"{k} {int(v * 100)}%" for k, v in (bp.get("weights") or {}).items())
    exam = exam or bp.get("exam") or exam_names(channel)
    return f"""You are an exam-paper digitiser for {exam}. Sources in this notebook are OFFICIAL previous-year question papers and official final answer keys.

TASK: Extract EVERY multiple-choice question from the paper{(' "' + paper + '"') if paper else ''}{(' (' + str(year) + ')') if year else ''} EXACTLY as printed — do not paraphrase, simplify or invent. Use the official key for the answer. If the key marks a question deleted/ambiguous, skip it.

For each question output this block, nothing else (no numbering outside the block, no markdown tables):

### Q
EXAM: {exam} | YEAR: {year or '<year>'} | PAPER: {paper or '<paper name>'} | QNO: <question number> | TOPIC: <subject - topic>
EN: <question in English, exact>
TE: <same question in Telugu — exam-quality translation; keep every number, name, year identical>
A) <option 1 English> | <option 1 Telugu>
B) <option 2 English> | <option 2 Telugu>
C) <option 3 English> | <option 3 Telugu>
D) <option 4 English> | <option 4 Telugu>
ANS: <A/B/C/D from the official key>
EXP: <one line why, English> | <one line why, Telugu>

RULES
- Exactly 4 options. Keep the printed option order (do not reorder).
- Telugu must be Telugu script only — never Hindi/Devanagari, never transliteration in Latin letters.
- If the paper is in Telugu, EN must be a faithful English rendering.
- Numbers, units, years, names in TE must match EN exactly.
- Subject mix of this exam for your reference: {subjects or 'as per paper'}.
- Do a maximum of 50 questions per response; I will ask "continue from QNO <n>" for the rest.
Begin with QNO 1."""


def howto_text() -> str:
    return ("📓 NOTEBOOKLM → BANK\n"
            "1️⃣ notebooklm.google.com → New notebook → upload official paper PDF(s) + final key PDF (TSPSC/APPSC/SSC sites; /pyq papers list has 199 URLs).\n"
            "2️⃣ Bot లో /notebook prompt <TSPSC|APPSC|SSC|BANKING|RAILWAY|POLICE|DEFENCE|CURRENT> → prompt copy → NotebookLM chat లో paste.\n"
            "3️⃣ NotebookLM output మొత్తం copy చేసి ఇక్కడ paste చేయండి (or Save as .txt/.json → send file).\n"
            "4️⃣ Bot validate చేసి preview ఇస్తుంది → ✅ Import. ప్రతి poll మీద 📜 exam · year · paper stamp వస్తుంది.\n"
            "5️⃣ 'continue from QNO 51' అని NotebookLM ని అడిగి మిగతా batch పంపండి.\n\n"
            "✔ 4 options · answer · Telugu script · numbers match · no answer-leak · duplicate-free — fail అయినవి skip అవుతాయి (report వస్తుంది).\n"
            "/notebook status — imported counts")


# ------------------------------------------------------------------ parsing
def _split_pair(s: str):
    if "|" in s:
        en, te = s.split("|", 1)
        return en.strip(), te.strip()
    return s.strip(), ""


def parse_blocks(text: str) -> list[dict]:
    """### Q blocks → raw dicts. Tolerant: extra spaces, lowercase labels, missing EXP."""
    out = []
    parts = re.split(r"^\s*#{2,4}\s*Q\b.*$", text or "", flags=re.M | re.I)
    for chunk in parts:
        if not re.search(r"^\s*EN\s*:", chunk, re.M | re.I):
            continue
        d = {"options_en": [None] * 4, "options_te": [None] * 4}
        for ln in chunk.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            m = re.match(r"^([A-Da-d1-4])[\)\.]\s*(.+)$", ln)
            if m and _LETTER.get(m.group(1).upper()) is not None:
                en, te = _split_pair(m.group(2))
                i = _LETTER[m.group(1).upper()]
                d["options_en"][i] = en; d["options_te"][i] = te
                continue
            m = re.match(r"^([A-Za-z]+)\s*:\s*(.*)$", ln)
            if not m:
                continue
            key, val = m.group(1).upper(), m.group(2).strip()
            if key == "EXAM":
                for i, kv in enumerate(val.split("|")):
                    k, sep, v = kv.partition(":")
                    if i == 0 and not sep:
                        d["exam"] = k.strip()
                    elif sep:
                        d[k.strip().lower()] = v.strip()
            elif key == "EN":
                d["q_en"] = val
            elif key == "TE":
                d["q_te"] = val
            elif key == "ANS":
                d["answer_index"] = _LETTER.get(val.strip()[:1].upper())
            elif key == "EXP":
                d["explanation_en"], d["explanation_te"] = _split_pair(val)
        out.append(d)
    return out


def parse_json(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except Exception:
        return []
    if isinstance(data, dict):
        data = data.get("questions") or data.get("items") or []
    out = []
    for it in data if isinstance(data, list) else []:
        if not isinstance(it, dict):
            continue
        d = dict(it)
        if "answer_index" not in d and d.get("answer") is not None:
            d["answer_index"] = _LETTER.get(str(d["answer"]).strip()[:1].upper())
        for k in ("options_en", "options_te"):
            if isinstance(d.get(k), list):
                d[k] = [str(x) for x in d[k]] + [None] * (4 - len(d[k]))
        d.setdefault("options_te", [None] * 4)
        out.append(d)
    return out


def parse_any(text: str) -> list[dict]:
    t = (text or "").strip()
    if t.startswith("[") or t.startswith("{"):
        js = parse_json(t)
        if js:
            return js
    return parse_blocks(t)


# ------------------------------------------------------------------ validation
def _channel_for(exam: str, hint: str = "") -> str:
    if hint and hint.upper() in config.CHANNELS:
        return hint.upper()
    e = (exam or "").lower()
    for key, ch in (("tspsc", "TSPSC"), ("tgpsc", "TSPSC"), ("appsc", "APPSC"), ("police", "POLICE"), ("constable", "POLICE"),
                    (" si ", "POLICE"), ("ibps", "BANKING"), ("sbi", "BANKING"), ("bank", "BANKING"), ("rrb", "RAILWAY"),
                    ("railway", "RAILWAY"), ("ntpc", "RAILWAY"), ("nda", "DEFENCE"), ("cds", "DEFENCE"), ("agniveer", "DEFENCE"),
                    ("ssc", "SSC"), ("cgl", "SSC"), ("chsl", "SSC"), ("upsc", "CURRENT")):
        if key in " " + e + " ":
            return ch
    return ""


def build_question(raw: dict, idx: int, channel_hint: str = "", exam_hint: str = "", year_hint: str = "", paper_hint: str = "") -> tuple[dict | None, str]:
    """raw → canonical question or (None, reason)."""
    from .content import validate_question, has_telugu
    from .verifier import structural_issues
    exam = raw.get("exam") or exam_hint
    channel = _channel_for(exam, channel_hint)
    if not channel:
        return None, "exam→channel unknown"
    oe = [(o or "").strip() for o in (raw.get("options_en") or [])][:4]
    ot = [(o or "").strip() for o in (raw.get("options_te") or [])][:4]
    if len(oe) < 4 or any(not o for o in oe):
        return None, "options<4"
    q_en = (raw.get("q_en") or "").strip()
    q_te = (raw.get("q_te") or "").strip()
    if has_telugu(q_en) and not q_te:                       # Telugu-medium paper
        q_te = q_en
    if not has_telugu(q_te):
        return None, "no Telugu stem"
    if len(ot) < 4 or any(not o for o in ot):
        # numeric / name options may legitimately be identical in both languages
        ot = [t or e for t, e in zip(ot + [""] * 4, oe)]
    ai = raw.get("answer_index")
    if not isinstance(ai, int) or not 0 <= ai < 4:
        return None, "no answer"
    q = {"id": f"N{idx:04d}", "channel": channel, "topic": (raw.get("topic") or "exam practice")[:60],
         "q_en": q_en, "q_te": q_te if q_te.startswith("⤷") else "⤷ " + q_te, "options_en": oe, "options_te": ot,
         "answer_index": ai, "explanation_en": (raw.get("explanation_en") or "")[:300],
         "explanation_te": (raw.get("explanation_te") or "")[:300], "source": "pyq", "bank": "notebook",
         "exam": exam, "year": str(raw.get("year") or year_hint or ""), "paper": raw.get("paper") or paper_hint or "",
         "qno": str(raw.get("qno") or ""), "provenance": f"notebooklm :: {exam} {raw.get('year') or year_hint or ''} {raw.get('paper') or paper_hint or ''}".strip(),
         "collected_on": _now().strftime("%Y-%m-%d")}
    errs = validate_question(q)
    if errs:
        return None, errs[0].split(": ", 1)[-1][:60]
    iss = [i for i in structural_issues(q) if i not in ("weak_generated_options",)]
    if iss:
        return None, ",".join(iss)
    return q, ""


def _sig(q: dict) -> str:
    from .question_bank import q_signature
    return q_signature(q)


def preview(text: str, channel_hint: str = "", exam_hint: str = "", year_hint: str = "", paper_hint: str = "") -> dict:
    """Parse + validate without saving. → {ok:[q], rejected:[(qno, reason)], dupes:n}"""
    raws = parse_any(text)[:MAX_PER_IMPORT]
    bank = _load()
    existing = {_sig(q) for q in bank["questions"]}
    try:
        from .question_bank import load_bank
        existing |= {_sig(q) for q in load_bank()}
    except Exception:
        pass
    nxt = max([int(q["id"][1:]) for q in bank["questions"] if q.get("id", "").startswith("N")] + [0]) + 1
    ok, rej, dupes = [], [], 0
    for r in raws:
        q, why = build_question(r, nxt, channel_hint, exam_hint, year_hint, paper_hint)
        if not q:
            rej.append((str(r.get("qno") or (r.get("q_en") or "")[:30]), why)); continue
        s = _sig(q)
        if s in existing:
            dupes += 1; continue
        existing.add(s); ok.append(q); nxt += 1
    return {"ok": ok, "rejected": rej, "dupes": dupes, "parsed": len(raws)}


def preview_text(pv: dict) -> str:
    ok = pv["ok"]
    by = {}
    for q in ok:
        k = f"{q['channel']} · {q.get('exam', '')} {q.get('year', '')}".strip()
        by[k] = by.get(k, 0) + 1
    lines = [f"📓 NotebookLM import preview", f"parsed {pv['parsed']} · ✅ valid {len(ok)} · ♻️ already in bank {pv['dupes']} · ❌ rejected {len(pv['rejected'])}"]
    for k, n in by.items():
        lines.append(f"  • {k}: {n}")
    if ok:
        q = ok[0]
        lines.append(f"\nSample: {q['q_en'][:90]}\n{q['q_te'][:90]}\n✔ {q['options_en'][q['answer_index']][:40]}")
    if pv["rejected"]:
        lines.append("\nRejected (fix in NotebookLM or ignore):")
        for qno, why in pv["rejected"][:8]:
            lines.append(f"  ✗ Q{qno}: {why}")
        if len(pv["rejected"]) > 8:
            lines.append(f"  … +{len(pv['rejected']) - 8} more")
    if not ok:
        lines.append("\nఏమీ import కాలేదు — format check: /notebook")
    return "\n".join(lines)


# ------------------------------------------------------------------ drafts + commit
def save_draft(uid, text: str, hints: dict | None = None):
    d = load_json(DRAFTS, {})
    d[str(uid)] = {"text": text[:400000], "hints": hints or {}, "ts": _now().isoformat()}
    save_json_atomic(DRAFTS, d)


def get_draft(uid):
    return load_json(DRAFTS, {}).get(str(uid))


def clear_draft(uid):
    d = load_json(DRAFTS, {})
    if str(uid) in d:
        d.pop(str(uid)); save_json_atomic(DRAFTS, d)


def commit(uid, by: str = "") -> tuple[int, str]:
    dr = get_draft(uid)
    if not dr:
        return 0, "❌ No pending import. Paste NotebookLM output first."
    h = dr.get("hints", {})
    pv = preview(dr["text"], h.get("channel", ""), h.get("exam", ""), h.get("year", ""), h.get("paper", ""))
    if not pv["ok"]:
        return 0, "❌ Nothing valid to import."
    bank = _load()
    bank["questions"].extend(pv["ok"])
    bank["count"] = len(bank["questions"])
    bank["imports"].append({"ts": _now().isoformat(timespec="seconds"), "by": by or str(uid), "added": len(pv["ok"]),
                            "rejected": len(pv["rejected"]), "exams": sorted({q.get("exam", "") for q in pv["ok"]})})
    bank["imports"] = bank["imports"][-200:]
    save_json_atomic(BANK, bank)
    clear_draft(uid)
    try:
        from .question_bank import rebuild_json
        rebuild_json()
    except Exception as e:
        return len(pv["ok"]), f"✅ {len(pv['ok'])} imported (bank rebuild note: {e})"
    return len(pv["ok"]), f"✅ {len(pv['ok'])} questions imported → live bank. ప్రతి poll మీద 📜 {pv['ok'][0].get('exam', '')} stamp వస్తుంది."


def status_text() -> str:
    bank = _load()
    by = {}
    for q in bank["questions"]:
        k = q["channel"]
        by[k] = by.get(k, 0) + 1
    lines = [f"📓 NotebookLM bank: {bank['count']} questions"]
    lines.append(" · ".join(f"{k} {n}" for k, n in sorted(by.items())) or "empty — /notebook to start")
    ex = {}
    for q in bank["questions"]:
        k = f"{q.get('exam', '')} {q.get('year', '')}".strip()
        ex[k] = ex.get(k, 0) + 1
    for k, n in sorted(ex.items(), key=lambda kv: -kv[1])[:10]:
        lines.append(f"  📜 {k}: {n}")
    if bank["imports"]:
        last = bank["imports"][-1]
        lines.append(f"\nLast import: {last['ts'][:16]} · +{last['added']} · ✗{last['rejected']}")
    return "\n".join(lines)


def buttons():
    row = [(ch, f"nb:p:{ch}") for ch in ("TSPSC", "APPSC", "SSC", "BANKING")]
    row2 = [(ch, f"nb:p:{ch}") for ch in ("RAILWAY", "POLICE", "DEFENCE", "CURRENT")]
    return [row, row2, [("📊 Status", "nb:status"), ("❓ How-to", "nb:help")]]
