# -*- coding: utf-8 -*-
"""🧼 290X: DISPLAY-TEXT SANITIZER (stored-XSS root fix).

Threat model: display names enter from Telegram profiles, bot chat
registration, the portal form and college creation — then get rendered
into leaderboards, winners walls, certificates and the admin
dashboard, several of which build HTML via string concatenation.
One student named `<img src=x onerror=...>` must never become markup
anywhere. Escaping at every render site is fragile (170+ sinks), so
290X cleans at WRITE time, once, at every entry point — and the
dashboard `esc()` was simultaneously upgraded to escape quotes as
defense-in-depth.

Rules for display names: strip HTML-significant characters
(< > & " ' ` / \\), control characters and zero-width/format
characters; collapse whitespace; cap length. Telugu/Unicode letters,
digits, spaces, dots and hyphens survive untouched — real names are
never mangled, only markup is.
"""
from __future__ import annotations

import re
import unicodedata

_BAD_CHARS = re.compile(r"[<>&\"'`/\\]")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_WS = re.compile(r"\s+")


def clean_display_name(value, max_len: int = 60) -> str:
    """A name safe to store once and render anywhere."""
    s = "" if value is None else str(value)
    s = unicodedata.normalize("NFKC", s)
    s = "".join(ch if unicodedata.category(ch) not in ("Cf", "Cc")
                else (" " if unicodedata.category(ch) == "Cc" else "")
                for ch in s)
    s = _BAD_CHARS.sub(" ", s)
    s = _CTRL.sub(" ", s)
    s = _WS.sub(" ", s).strip(" .")
    return s[:max_len].strip()


def contains_markup(value) -> bool:
    """True if the raw value carries HTML-significant characters
    (audit/monitoring helper — cleaning already happened upstream)."""
    return bool(_BAD_CHARS.search("" if value is None else str(value)))
