# -*- coding: utf-8 -*-
"""🤖 390X: BOT PAPER FACTORY — owner sends an official paper to
the Telegram bot, gets a reviewable DRAFT back with inline
buttons. The bot is a *remote control* for core.paperfactory:
nothing here bypasses the 370X/380X trust gates (draft-first,
translation-pending never banks, signature dedupe).

Kept pure (no Telegram imports) so the whole flow is unit
testable; bot.py only downloads bytes and renders buttons.
Callback data is 'pf:{act}:{draft_id}' — draft ids are capped
by paperfactory at ~54 chars, so callbacks stay under
Telegram's 64-byte limit.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import config

_ACTIONS = ("bank", "tr", "rej")


def is_paper_file(filename: str) -> bool:
    return str(filename or "").lower().endswith((".pdf", ".txt"))


def save_incoming(filename: str, data: bytes) -> Path:
    """Save an uploaded paper into data/pdf_inbox/ (basename only —
    no path traversal; a name clash gets a -2/-3 suffix so an
    earlier paper is never silently overwritten)."""
    name = Path(str(filename or "paper.pdf")).name or "paper.pdf"
    name = re.sub(r"[^\w.\- ]+", "_", name).strip() or "paper.pdf"
    inbox = config.DATA / "pdf_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / name
    n = 2
    while dest.exists():
        dest = inbox / f"{Path(name).stem}-{n}{Path(name).suffix}"
        n += 1
    dest.write_bytes(data or b"")
    return dest


def buttons_for(draft_res: dict) -> list | None:
    """Inline buttons for a fresh draft (None when drafting failed
    — the message then carries the honest error instead)."""
    if not draft_res.get("ok"):
        return None
    did = draft_res["draft_id"]
    row = [("✅ Bank loki", f"pf:bank:{did}")]
    if draft_res.get("needs_translation"):
        row.append(("🌐 Translate", f"pf:tr:{did}"))
    row.append(("❌ Reject", f"pf:rej:{did}"))
    return [row]


def summary_text(draft_res: dict) -> str:
    if not draft_res.get("ok"):
        return ("⚠️ Paper draft avvaledu: "
                + str(draft_res.get("error") or "unknown error"))
    m = draft_res.get("meta") or {}
    lines = [
        "📄 *Paper Draft Ready*",
        f"🏷 {m.get('exam') or '?'} {m.get('year') or ''} "
        f"{m.get('paper') or ''} · extractor: {draft_res.get('extractor')}",
        f"📥 Parsed: {draft_res.get('parsed')} · 🆕 Fresh: "
        f"{draft_res.get('fresh')} · ♻️ Duplicates: "
        f"{draft_res.get('duplicates')}",
    ]
    if draft_res.get("needs_translation"):
        lines.append(
            f"📝 Telugu translation pending: "
            f"{draft_res['needs_translation']} — 🌐 Translate nokkandi, "
            "ledante Bank appudu ivi skip avthayi (fake Telugu bank avvadu).")
    lines.append("✅ Bank = ippude scraped bank loki · ❌ Reject = draft close")
    return "\n".join(lines)


def make_from_upload(filename: str, data: bytes) -> tuple:
    """bytes -> saved file -> draft. Returns (text, buttons)."""
    from . import paperfactory
    path = save_incoming(filename, data)
    res = paperfactory.make_draft(path)
    return summary_text(res), buttons_for(res)


def handle_action(action: str, draft_id: str, llm=None,
                  by: str = "bot") -> str:
    """Inline-button dispatch. Always returns owner-readable text;
    the paperfactory gates decide what is actually allowed."""
    from . import paperfactory
    if action not in _ACTIONS or not draft_id:
        return "⚠️ Invalid paper action."
    if action == "tr":
        r = paperfactory.translate_draft(draft_id, llm=llm)
        if not r.get("ok"):
            return "⚠️ " + str(r.get("error") or "translate failed")
        return (f"🌐 Translate: {r['translated']} ready · "
                f"📝 inka pending: {r['still_pending']}"
                + (" — ✅ Bank nokkocchu." if not r["still_pending"]
                   else " (LLM/translator inka konni park chesindi)."))
    if action == "bank":
        r = paperfactory.go_bank(draft_id, by=by)
        if not r.get("ok"):
            return "⚠️ " + str(r.get("error") or "bank failed")
        msg = (f"✅ Bank loki {r['added']} questions vellayi "
               f"(dup: {r['duplicates']}, scraped total: "
               f"{r['total_in_scraped']}).")
        if r.get("translation_pending"):
            msg += (f"\n📝 {r['translation_pending']} translation "
                    "pending — draft open e undi, 🌐 Translate tharuvatha "
                    "malli Bank nokkandi.")
        return msg
    r = paperfactory.reject_draft(draft_id, by=by)
    if not r.get("ok"):
        return "⚠️ " + str(r.get("error") or "reject failed")
    return "🗑 Draft rejected — bank loki emi vellaledu."


def list_text() -> str:
    """Staff /papers overview: every draft + its gate status."""
    from . import paperfactory
    drafts = paperfactory.list_drafts()
    if not drafts:
        return ("📄 Paper drafts levu. Official paper PDF ni "
                "ikada pampandi — draft ga vasthundi.")
    lines = ["📄 *Paper Drafts*"]
    for d in drafts:
        m = d.get("meta") or {}
        lines.append(
            f"• {d['id']} — {m.get('exam') or '?'} {m.get('year') or ''} "
            f"· {d.get('status')} · fresh {d.get('fresh')}/"
            f"{d.get('parsed')}"
            + (f" · 📝 TE pending {d['needs_translation']}"
               if d.get("needs_translation") else ""))
    return "\n".join(lines)
