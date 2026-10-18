"""
🏅 Winners Certificate — premium gold/green PNG (WA groups + Telegram).

User korika: winners ki visual certificate. Rank circles (ties share the
same medal colour), peru/number, score + accuracy bars, players strip.
Telugu peru lu boxes ga rakunda repo-bundled Noto Sans Telugu font
(assets/fonts, OFL). Pillow lekapothe None — callers text fallback ki
velthayi (never crash, never fake an image).

    render_certificate(title, subtitle, rows, footer) -> PNG bytes | None
    rows: [{"rank": 1, "name": "…", "score": "3/5", "pct": 60}, …] (≤5)
"""
from __future__ import annotations

import io
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FONTS = ROOT / "assets" / "fonts"
W, H = 1200, 900
GOLD = (212, 175, 55)
GOLD_LIGHT = (240, 210, 110)
INK = (8, 32, 24)


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    cands = [
        FONTS / ("NotoSansTelugu_700Bold.ttf" if bold else "NotoSansTelugu_400Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu") / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
    ]
    for c in cands:
        try:
            if c.exists():
                return ImageFont.truetype(str(c), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _star(draw, cx, cy, r, color):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=color)


def _fit(draw, text, font, max_w):
    """Text ni max_w loki truncate (… tho)."""
    text = str(text or "")
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def render_certificate(title: str, subtitle: str, rows: list,
                       footer: str = "") -> bytes | None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    rows = (rows or [])[:5]
    img = Image.new("RGB", (W, H), (6, 40, 28))
    d = ImageDraw.Draw(img)
    # vertical green gradient
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(6 + 8 * t), int(40 + 30 * t), int(28 + 20 * t)))
    # double gold border
    d.rectangle([18, 18, W - 18, H - 18], outline=GOLD, width=6)
    d.rectangle([34, 34, W - 34, H - 34], outline=(150, 122, 40), width=2)
    for cx, cy in [(70, 70), (W - 70, 70), (70, H - 70), (W - 70, H - 70)]:
        _star(d, cx, cy, 16, GOLD)
    _star(d, W // 2, 108, 26, GOLD_LIGHT)

    def center(text, y, font, fill):
        w = d.textlength(text, font=font)
        d.text(((W - w) / 2, y), text, font=font, fill=fill)

    center("StudentUp", 128, _font(30, bold=True), GOLD_LIGHT)
    center(str(title or "WINNERS CERTIFICATE"), 168, _font(54, bold=True), GOLD)
    if subtitle:
        center(_fit(d, subtitle, _font(30), W - 200), 240, _font(30), (235, 245, 238))
    center("PRACTICE QUIZ · WINNERS", 286, _font(30, bold=True), (190, 220, 200))
    d.line([(W // 2 - 260, 336), (W // 2 + 260, 336)], fill=GOLD, width=3)

    medal_fill = {1: (212, 175, 55), 2: (196, 202, 210), 3: (205, 140, 90)}
    y = 372
    for r in rows:
        rank = int(r.get("rank", 0) or 0)
        fill = medal_fill.get(rank, (90, 120, 140))
        # rank circle
        d.ellipse([90, y, 150, y + 60], fill=fill, outline=(255, 255, 255), width=2)
        num = str(rank if rank else "•")
        nw = d.textlength(num, font=_font(30, bold=True))
        d.text((120 - nw / 2, y + 12), num, font=_font(30, bold=True), fill=INK)
        # name + score
        name = _fit(d, r.get("name", ""), _font(36, bold=True), 640)
        d.text((180, y + 2), name, font=_font(36, bold=True), fill=(255, 255, 255))
        score = str(r.get("score", ""))
        sw = d.textlength(score, font=_font(36, bold=True))
        d.text((W - 110 - sw, y + 2), score, font=_font(36, bold=True), fill=GOLD_LIGHT)
        # accuracy bar
        pct = max(0, min(100, int(r.get("pct", 0) or 0)))
        bx0, bx1, by = 180, W - 110, y + 48
        d.rounded_rectangle([bx0, by, bx1, by + 14], radius=7, fill=(20, 60, 46))
        col = (46, 204, 113) if pct >= 70 else ((241, 166, 50) if pct >= 40 else (231, 76, 60))
        if pct:
            d.rounded_rectangle([bx0, by, bx0 + (bx1 - bx0) * pct / 100, by + 14],
                                radius=7, fill=col)
        y += 88
    if footer:
        center(_fit(d, footer, _font(28), W - 160), H - 96, _font(28), (200, 225, 208))
    center("StudentUp · Practice Daily, Rank Daily", H - 58, _font(24), (150, 180, 162))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def rows_from_tally(standings: list, n_q: int, name_of) -> list:
    """Standings [(jid, correct, answered)] → certificate rows (tie ranks)."""
    rows, rank, prev = [], 0, None
    for pos, (jid, c, a) in enumerate((standings or [])[:5]):
        if c != prev:
            rank, prev = pos + 1, c
        rows.append({"rank": rank, "name": name_of(jid),
                     "score": f"{c}/{n_q}",
                     "pct": round(100 * c / n_q) if n_q else 0})
    return rows


if __name__ == "__main__":
    png = render_certificate(
        "WINNERS CERTIFICATE", "Demo Group · SSC",
        rows_from_tally([("919999999999@s.whatsapp.net", 3, 5),
                         ("918888888888@s.whatsapp.net", 2, 5),
                         ("917777777777@s.whatsapp.net", 2, 5)], 5,
                        lambda j: "@" + j.split("@")[0]),
        "Players: 7 · Accuracy: 43%")
    print("PNG bytes:", len(png) if png else None)
