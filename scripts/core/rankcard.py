"""
Shareable rank cards — a PNG "certificate" for Top-3 (and every player's
personal card on request) that people forward to WhatsApp status.

Rendering uses Pillow when installed (`pip install pillow`) and a Telugu-
capable font if one is found (Noto Sans Telugu / Gautami / Pothana). When
Pillow or a Telugu font is missing we degrade gracefully:
  * no Pillow           → return None (engine sends the text card only)
  * no Telugu font      → Telugu strings are skipped on the image; the
                          English lines still render, caption carries Telugu.
Nothing here can raise into the engine — every entry point is wrapped.
"""
from __future__ import annotations

import io
import os
from datetime import datetime

from . import config

W, H = 1080, 1350          # WhatsApp-status friendly (4:5)
BRAND = getattr(config, "BRAND_NAME", "StudentUp")
HANDLE = getattr(config, "BRAND_HANDLE", "t.me/StudentUpQuiz")

_FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts"),
              str(config.DATA / "fonts")]
_LATIN = ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "NotoSans-Bold.ttf", "NotoSans-Regular.ttf",
          "LiberationSans-Bold.ttf", "Arial.ttf")
_TELUGU = ("NotoSansTelugu-Bold.ttf", "NotoSansTelugu-Regular.ttf", "NotoSansTelugu[wdth,wght].ttf",
           "Pothana2000.ttf", "gautami.ttf", "Gautami.ttf")


def _find_font(names):
    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for n in names:
                if n in files:
                    return os.path.join(root, n)
    return None


def available() -> bool:
    if not getattr(config, "RANK_CARDS", True):
        return False
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


def _fonts():
    from PIL import ImageFont
    lat = _find_font(_LATIN)
    tel = _find_font(_TELUGU)

    def f(path, size):
        try:
            return ImageFont.truetype(path, size) if path else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()
    return {"h1": f(lat, 72), "h2": f(lat, 48), "body": f(lat, 40), "small": f(lat, 30),
            "te": f(tel, 40) if tel else None, "te_big": f(tel, 56) if tel else None}


_THEME = {  # rank -> (bg top, bg bottom, accent)
    1: ((28, 20, 60), (120, 80, 10), (255, 200, 60)),
    2: ((20, 30, 60), (90, 100, 120), (220, 225, 235)),
    3: ((30, 20, 40), (120, 70, 40), (230, 150, 90)),
    0: ((15, 35, 70), (10, 90, 110), (90, 220, 200)),
}


def _gradient(draw, top, bottom):
    for y in range(H):
        t = y / (H - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=c)


def _center(draw, y, text, font, fill):
    if not text or font is None:
        return
    try:
        w = draw.textlength(text, font=font)
    except Exception:
        w = len(text) * 20
    draw.text(((W - w) / 2, y), text, font=font, fill=fill)


def render(player: dict, *, title: str, subtitle_te: str = "", exam: str = "",
           rank: int = 0, score: str = "", extra: str = "", when=None) -> bytes | None:
    """player: {name, district, district_te, points}. Returns PNG bytes or None."""
    if not available():
        return None
    try:
        from PIL import Image, ImageDraw
        now = when or datetime.now(config.IST)
        top, bottom, accent = _THEME.get(rank if rank in (1, 2, 3) else 0)
        img = Image.new("RGB", (W, H), top)
        d = ImageDraw.Draw(img)
        _gradient(d, top, bottom)
        F = _fonts()
        # frame
        d.rounded_rectangle([40, 40, W - 40, H - 40], radius=40, outline=accent, width=6)
        _center(d, 90, BRAND.upper(), F["h2"], accent)
        _center(d, 150, title, F["small"], (235, 235, 245))
        if subtitle_te and F["te"]:
            _center(d, 195, subtitle_te, F["te"], (235, 235, 245))
        # medal / rank badge
        badge = {1: "1st", 2: "2nd", 3: "3rd"}.get(rank, f"#{rank}" if rank else "")
        if badge:
            d.ellipse([W / 2 - 130, 280, W / 2 + 130, 540], fill=accent)
            _center(d, 370, badge, F["h1"], top)
        # name + district
        _center(d, 590, (player.get("name") or "Player")[:26], F["h1"], (255, 255, 255))
        dist = player.get("district") or ""
        dte = player.get("district_te") or ""
        if dist:
            _center(d, 690, dist.upper(), F["h2"], accent)
        if dte and dte != dist and F["te_big"]:
            _center(d, 760, dte, F["te_big"], (240, 240, 240))
        if exam:
            _center(d, 850, exam, F["body"], (230, 230, 240))
        if score:
            d.rounded_rectangle([W / 2 - 300, 930, W / 2 + 300, 1040], radius=30, fill=(0, 0, 0))
            _center(d, 955, score, F["h2"], accent)
        if extra:
            _center(d, 1080, extra, F["body"], (235, 235, 245))
        _center(d, 1180, now.strftime("%d %b %Y"), F["small"], (200, 200, 210))
        _center(d, 1230, HANDLE, F["small"], accent)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception as e:
        print(f"   [rankcard] render note: {e}")
        return None


def top3_cards(rows, *, title, subtitle_te, exam, score_fmt, when=None):
    """rows: ranked list (dicts with name/district/correct/total/marks). Yields
    (rank, row, png_bytes) for the podium — skips silently if unavailable."""
    from . import districts as D
    out = []
    for i, r in enumerate(rows[:3], 1):
        player = {"name": r.get("name"), "district": r.get("district", ""),
                  "district_te": D.telugu_name(r.get("district", "")) if r.get("district") else "",
                  "points": r.get("points", 0)}
        png = render(player, title=title, subtitle_te=subtitle_te, exam=exam, rank=i,
                     score=score_fmt(r), extra=f"{r.get('correct', 0)} correct · {r.get('total', 0)} attempted",
                     when=when)
        if png:
            out.append((i, r, png))
    return out
