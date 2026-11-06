"""Drawing primitives for the provenance film.

Everything is drawn with Pillow at 1920×1080 (or a scaled multiple). Widgets are
plain functions that take a `Draw` object, so scenes can compose them freely.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .util import (
    clamp,
    darken,
    ease,
    ease_out,
    ellipsize,
    font,
    hexc,
    lighten,
    mix,
    ramp,
    timecode,
    wrap,
)

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------

INK = hexc("#0a0f1a")
DESK_TOP = hexc("#0d1626")
DESK_BOTTOM = hexc("#070b13")
PANEL = hexc("#101a2b")
PANEL_HI = hexc("#16233a")
STROKE = hexc("#22334d")
TEXT = hexc("#e9eff8")
TEXT_DIM = hexc("#94a5bd")
TEXT_FAINT = hexc("#5d6f8a")
WHITE = (255, 255, 255)
GREEN = hexc("#3ddc97")
RED = hexc("#ff4d5e")
AMBER = hexc("#ffc857")

W, H = 1920, 1080

MENUBAR_H = 30
RAIL_Y = 1062


# --------------------------------------------------------------------------
# Backgrounds
# --------------------------------------------------------------------------


def make_desktop(w: int = W, h: int = H) -> Image.Image:
    """Cached wallpaper: vertical gradient + faint blueprint grid + vignette."""
    img = Image.new("RGB", (w, h), DESK_TOP)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=mix(DESK_TOP, DESK_BOTTOM, t))

    grid = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grid)
    step = 48
    for x in range(0, w, step):
        gd.line([(x, 0), (x, h)], fill=(70, 110, 160, 14))
    for y in range(0, h, step):
        gd.line([(0, y), (w, y)], fill=(70, 110, 160, 14))
    img = Image.alpha_composite(img.convert("RGBA"), grid)

    # vignette
    vig = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([-w * 0.25, -h * 0.4, w * 1.25, h * 1.4], fill=90)
    vig = vig.filter(__import__("PIL.ImageFilter", fromlist=["ImageFilter"]).GaussianBlur(160))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    dark.putalpha(vig.point(lambda v: 255 - v))
    img = Image.alpha_composite(img, dark)
    return img.convert("RGB")


def overlay(size: tuple[int, int], colour: tuple, alpha: int) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle([0, 0, size[0], size[1]], fill=(*colour[:3], alpha))
    return layer


# --------------------------------------------------------------------------
# Menubar / HUD
# --------------------------------------------------------------------------


def menubar(d: ImageDraw.ImageDraw, elapsed: float, right: str = "", rec: bool = True,
            pulse_t: float | None = None, dim: bool = False):
    """A screen-recorder style strip: REC + elapsed time on the left, context right."""
    d.rectangle([0, 0, W, MENUBAR_H], fill=hexc("#070c15"))
    d.line([(0, MENUBAR_H), (W, MENUBAR_H)], fill=hexc("#1b2740"))
    t = elapsed if pulse_t is None else pulse_t

    if rec:
        pulse = 0.55 + 0.45 * math.sin(t * 4.0)
        d.ellipse([16, 10, 26, 20], fill=RED if pulse > 0.6 else hexc("#7a2733"))
    d.text((36, 7), "REC", font=font(15, "mono-bold"), fill=hexc("#cfd9e8") if not dim else hexc("#5b6b85"))
    d.text((78, 7), timecode(elapsed), font=font(15, "mono"), fill=hexc("#93a4bd") if not dim else hexc("#4a5a72"))
    d.text((196, 7), "simulated screen capture  ·  2026-11-04  ·  Cheyenne, WY", font=font(14),
           fill=hexc("#4a5a72") if dim else TEXT_FAINT)
    if right:
        d.text((W - 20, 7), ellipsize(right, font(15, "mono"), 900), font=font(15, "mono"),
               fill=TEXT_DIM, anchor="ra")


def chapter_rail(d: ImageDraw.ImageDraw, chapters: list[tuple[str, float]], current: int, t: float, total: float):
    d.rectangle([0, RAIL_Y - 6, W, H], fill=hexc("#070c15"))
    n = len(chapters)
    gap = 6
    x = 96
    avail = W - 192 - gap * (n - 1)
    weights = [max(0.6, dur) for _, dur in chapters]
    scale = avail / sum(weights)
    for i, ((name, dur), wgt) in enumerate(zip(chapters, weights)):
        w = wgt * scale
        done = i < current
        active = i == current
        colour = hexc("#2a3d59")
        if done:
            colour = hexc("#3d5a80")
        if active:
            colour = hexc("#6ea8ff")
        d.rounded_rectangle([x, RAIL_Y, x + w, RAIL_Y + 5], radius=2, fill=colour)
        if active:
            d.text((x, RAIL_Y + 12), ellipsize(name, font(13, "mono"), w), font=font(13, "mono"), fill=hexc("#9fc0ff"))
        x += w + gap


# --------------------------------------------------------------------------
# Window chrome
# --------------------------------------------------------------------------


@dataclass
class Rect:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def w(self) -> int:
        return self.x1 - self.x0

    @property
    def h(self) -> int:
        return self.y1 - self.y0

    def inset(self, n: int) -> "Rect":
        return Rect(self.x0 + n, self.y0 + n, self.x1 - n, self.y1 - n)

    def as_list(self) -> list[int]:
        return [self.x0, self.y0, self.x1, self.y1]


BROWSER = Rect(96, 72, 1292, 892)
PANEL_BOX = Rect(1320, 72, 1824, 892)
CAPTION_BOX = Rect(96, 914, 1824, 1042)


def shadow_panel(img: Image.Image, box: Rect, radius: int = 14, fill=PANEL, stroke=STROKE, alpha: int = 22):
    sh = Image.new("RGBA", (box.w + 60, box.h + 60), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([30, 30, box.w + 30, box.h + 30], radius=radius, fill=(0, 0, 0, 200))
    sh = sh.filter(__import__("PIL.ImageFilter", fromlist=["ImageFilter"]).GaussianBlur(alpha))
    img.alpha_composite(sh, (box.x0 - 30, box.y0 - 30))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box.as_list(), radius=radius, fill=(*fill[:3], 255), outline=(*stroke[:3], 255))


def browser(img: Image.Image, box: Rect, url: str, site: str, accent: tuple, load: float = 1.0, tab: str = ""):
    """Chrome around a page area. Returns the page Rect."""
    shadow_panel(img, box, radius=16)
    d = ImageDraw.Draw(img)

    strip_h = 42
    d.rounded_rectangle([box.x0, box.y0, box.x1, box.y0 + strip_h + 12], radius=16, fill=(*hexc("#0c1422")[:3], 255))
    d.rectangle([box.x0, box.y0 + strip_h, box.x1, box.y0 + strip_h + 12], fill=(*hexc("#0c1422")[:3], 255))
    d.line([(box.x0, box.y0 + strip_h), (box.x1, box.y0 + strip_h)], fill=STROKE)

    # traffic lights
    for i, col in enumerate([hexc("#ff5f57"), hexc("#febc2e"), hexc("#28c840")]):
        cx = box.x0 + 22 + i * 20
        d.ellipse([cx - 6, box.y0 + 14, cx + 6, box.y0 + 26], fill=col)
    # tab
    tab_x = box.x0 + 92
    d.rounded_rectangle([tab_x, box.y0 + 6, tab_x + 300, box.y0 + strip_h], radius=8, fill=(*PANEL_HI[:3], 255))
    d.ellipse([tab_x + 12, box.y0 + 16, tab_x + 28, box.y0 + 32], fill=accent)
    d.text((tab_x + 36, box.y0 + 15), ellipsize(tab or site, font(15), 240), font=font(15), fill=TEXT)

    # address bar
    bar = Rect(box.x0 + 16, box.y0 + strip_h + 6, box.x1 - 16, box.y0 + strip_h + 40)
    d.rounded_rectangle(bar.as_list(), radius=9, fill=(*hexc("#0a1220")[:3], 255), outline=(*hexc("#1d2d45")[:3], 255))
    d.text((bar.x0 + 14, bar.y0 + 8), "https://", font=font(15, "mono"), fill=TEXT_FAINT)
    shown = ellipsize(url, font(15, "mono"), bar.w - 90)
    d.text((bar.x0 + 78, bar.y0 + 8), shown, font=font(15, "mono"), fill=hexc("#cfe0f5"))

    # load bar
    if load < 1.0:
        lw = int((box.w - 2) * clamp(load))
        d.rectangle([box.x0 + 1, box.y0 + strip_h + 41, box.x0 + 1 + lw, box.y0 + strip_h + 43], fill=(*accent[:3], 255))

    page = Rect(box.x0 + 1, box.y0 + strip_h + 44, box.x1 - 1, box.y1 - 1)
    d.rectangle(page.as_list(), fill=(*hexc("#f7f9fc")[:3], 255))
    return page


# --------------------------------------------------------------------------
# Page renderers (the fake-but-faithful public sites)
# --------------------------------------------------------------------------


def _text(d, xy, s, size=16, fill=TEXT, weight="sans", anchor="la"):
    d.text(xy, s, font=font(size, weight), fill=fill, anchor=anchor)


def page_list(img, page: Rect, accent, heading, crumbs, rows, hover=None, pressed=None, scroll=0.0,
              chips=("Body", "Year", "Type"), sub=""):
    d = ImageDraw.Draw(img)
    d.rectangle(page.as_list(), fill=(*hexc("#ffffff")[:3], 255))
    # site header
    d.rectangle([page.x0, page.y0, page.x1, page.y0 + 54], fill=(*hexc("#0f2743")[:3], 255))
    d.rounded_rectangle([page.x0 + 20, page.y0 + 14, page.x0 + 46, page.y0 + 40], radius=6, fill=accent)
    _text(d, (page.x0 + 57, page.y0 + 17), "CITY OF CHEYENNE", 16, WHITE, "sans-bold")
    nav = ["Your Government", "Services", "News", "Records"]
    x = page.x0 + 260
    for item in nav:
        _text(d, (x, page.y0 + 18), item, 14, hexc("#c8d6e8"))
        x += font(14).getlength(item) + 26

    # breadcrumb
    d.text((page.x0 + 28, page.y0 + 74), crumbs, font=font(14, "mono"), fill=hexc("#7a8ba3"))

    # heading
    d.text((page.x0 + 28, page.y0 + 96), heading, font=font(30, "sans-bold"), fill=hexc("#12233a"))
    if sub:
        d.text((page.x0 + 28, page.y0 + 136), sub, font=font(15), fill=hexc("#5c6b80"))

    # chips
    cx = page.x0 + 28
    for c in chips:
        w = font(14).getlength(c) + 40
        d.rounded_rectangle([cx, page.y0 + 168, cx + w, page.y0 + 196], radius=14,
                            fill=hexc("#eef3f9"), outline=hexc("#cfdceb"))
        d.text((cx + 16, page.y0 + 173), c, font=font(14), fill=hexc("#3b5069"))
        d.text((cx + w - 22, page.y0 + 171), "▾", font=font(13), fill=hexc("#7a8ba3"))
        cx += w + 10

    # table header
    ty = page.y0 + 212
    d.rectangle([page.x0 + 20, ty, page.x1 - 20, ty + 34], fill=hexc("#e9eff6"))
    for label, lx in (("DATE", page.x0 + 36), ("BODY", page.x0 + 196), ("DOCUMENTS", page.x0 + 448)):
        d.text((lx, ty + 9), label, font=font(13, "mono-bold"), fill=hexc("#5a6d85"))

    row_h = 62
    visible_h = page.y1 - (ty + 40) - 16
    rows_area = Rect(page.x0 + 20, ty + 38, page.x1 - 20, ty + 38 + visible_h)
    clip = img.crop(rows_area.as_list())

    layer = Image.new("RGBA", (rows_area.w, rows_area.h), (255, 255, 255, 0))
    ld = ImageDraw.Draw(layer)
    for i, row in enumerate(rows):
        ry = int(i * row_h - scroll * row_h)
        if ry < -row_h or ry > rows_area.h:
            continue
        hot = hover == i
        fill = (0, 0, 0, 0)
        if hot:
            fill = (233, 241, 252, 255)
        if pressed == i:
            fill = (219, 232, 249, 255)
        if fill[3]:
            ld.rectangle([0, ry, rows_area.w, ry + row_h], fill=fill)
        ld.line([(0, ry + row_h), (rows_area.w, ry + row_h)], fill=(226, 233, 242, 255))
        if hot:
            ld.rectangle([0, ry + 10, 4, ry + row_h - 10], fill=(*accent[:3], 255))

        date = row.get("date", "")
        body = row.get("body", "")
        docs = row.get("docs", [])
        ld.text((16, ry + 12), date, font=font(16, "sans-bold"), fill=(18, 35, 58, 255))
        ld.text((16, ry + 34), row.get("meta", ""), font=font(12, "mono"), fill=(122, 139, 163, 255))
        ld.text((176, ry + 20), body, font=font(15), fill=(40, 60, 86, 255))
        dx = 428
        for j, doc in enumerate(docs):
            label = doc.get("label", "")
            w = font(13).getlength(label) + 22
            primary = j == 0 or doc.get("primary")
            pill_fill = (accent[0], accent[1], accent[2], 36) if primary else (238, 243, 249, 255)
            ld.rounded_rectangle([dx, ry + 19, dx + w, ry + 44], radius=12, fill=pill_fill,
                                 outline=(accent[0], accent[1], accent[2], 120) if primary else (207, 220, 235, 255))
            ld.text((dx + 11, ry + 24), label, font=font(13), fill=(18, 35, 58, 255))
            dx += w + 8
    img.paste(layer, (rows_area.x0, rows_area.y0), layer)

    # scrollbar
    track = Rect(page.x1 - 12, rows_area.y0, page.x1 - 6, rows_area.y1)
    d.rounded_rectangle(track.as_list(), radius=3, fill=hexc("#eef3f9"))
    frac = clamp(scroll / max(1, len(rows) - 4))
    thumb_h = max(40, int(track.h * min(1.0, 6 / max(6, len(rows)))))
    thumb_y = int(track.y0 + (track.h - thumb_h) * frac)
    d.rounded_rectangle([track.x0, thumb_y, track.x1, thumb_y + thumb_h], radius=3, fill=hexc("#b9c8da"))
    return d


def page_doc(img, page: Rect, accent, title, meta, pages=12, download_hover=False, download_pressed=False,
             attachments=None, highlight=False, sheet_label="AGENDA PACKET", viewer_label="GRANICUS  ·  AGENDA VIEWER",
             button_label="Download PDF"):
    d = ImageDraw.Draw(img)
    d.rectangle(page.as_list(), fill=(*hexc("#eef2f7")[:3], 255))
    # viewer toolbar
    d.rectangle([page.x0, page.y0, page.x1, page.y0 + 52], fill=(*hexc("#0f2743")[:3], 255))
    _text(d, (page.x0 + 22, page.y0 + 16), viewer_label, 15, hexc("#dce8f7"), "mono-bold")
    _text(d, (page.x1 - 22, page.y0 + 17), "view_id=2", 14, hexc("#93a9c4"), "mono", anchor="ra")

    # title block
    d.text((page.x0 + 34, page.y0 + 74), title, font=font(26, "sans-bold"), fill=hexc("#12233a"))
    d.text((page.x0 + 34, page.y0 + 110), meta, font=font(15, "mono"), fill=hexc("#5c6b80"))

    # pdf sheet
    sheet = Rect(page.x0 + 34, page.y0 + 146, page.x0 + 660, page.y1 - 26)
    d.rounded_rectangle(sheet.as_list(), radius=4, fill=(255, 255, 255, 255), outline=hexc("#d3dde9"))
    # faux page text lines
    y = sheet.y0 + 34
    widths = [0.62, 0.9, 0.86, 0.74, 0.92, 0.55, 0.88, 0.8, 0.68, 0.94, 0.72, 0.6, 0.9, 0.78]
    for i in range(18):
        wfrac = widths[i % len(widths)]
        yy = y + i * 22
        if yy > sheet.y1 - 30:
            break
        d.rounded_rectangle([sheet.x0 + 30, yy, sheet.x0 + 30 + int((sheet.w - 60) * wfrac), yy + 7],
                            radius=3, fill=hexc("#e3e8ef"))
    d.text((sheet.x0 + 30, sheet.y0 + 12), sheet_label, font=font(13, "mono-bold"), fill=hexc("#8ea0b6"))
    d.text((sheet.x1 - 30, sheet.y0 + 12), "p. 1 / " + str(pages), font=font(13, "mono"), fill=hexc("#8ea0b6"), anchor="ra")

    # right rail: download + attachments
    rail = Rect(sheet.x1 + 26, sheet.y0, page.x1 - 26, sheet.y1)
    d.text((rail.x0, rail.y0), "FILES IN THIS ITEM", font=font(13, "mono-bold"), fill=hexc("#5c6b80"))
    items = attachments or []
    iy = rail.y0 + 30
    for i, item in enumerate(items):
        h = 46
        hot = highlight and i == 0
        d.rounded_rectangle([rail.x0, iy, rail.x1, iy + h], radius=8,
                            fill=hexc("#ffffff") if not hot else hexc("#e8f1fd"),
                            outline=hexc("#cfdceb") if not hot else accent)
        d.rectangle([rail.x0 + 12, iy + 12, rail.x0 + 24, iy + 34], fill=hexc("#dbe4ef"))
        d.text((rail.x0 + 34, iy + 9), ellipsize(item["name"], font(14), rail.w - 60), font=font(14), fill=hexc("#22344d"))
        d.text((rail.x0 + 34, iy + 26), item.get("meta", ""), font=font(12, "mono"), fill=hexc("#7a8ba3"))
        iy += h + 8

    # download button
    bw = max(210, int(font(16, "sans-bold").getlength("⤓  " + button_label)) + 44)
    bh = 46
    bx0, by0 = rail.x0, rail.y1 - bh - 6
    fill = hexc("#1f6feb") if not download_hover else hexc("#2a7ff5")
    if download_pressed:
        fill = hexc("#1857bd")
    d.rounded_rectangle([bx0, by0, bx0 + bw, by0 + bh], radius=10, fill=fill)
    d.text((bx0 + 22, by0 + 13), "⤓  " + button_label, font=font(16, "sans-bold"), fill=WHITE)
    return Rect(bx0, by0, bx0 + bw, by0 + bh)


def page_video(img, page: Rect, accent, title, meta, tstamp, caption_lines, hover_play=False):
    d = ImageDraw.Draw(img)
    d.rectangle(page.as_list(), fill=(*hexc("#0b0f16")[:3], 255))
    # player
    player = Rect(page.x0 + 34, page.y0 + 34, page.x1 - 34, page.y0 + 34 + 400)
    d.rectangle(player.as_list(), fill=(*hexc("#05080d")[:3], 255))
    # fake dais silhouette
    for i in range(7):
        bx = player.x0 + 60 + i * 92
        d.rounded_rectangle([bx, player.y1 - 150, bx + 66, player.y1 - 40], radius=6, fill=hexc("#131a24"))
        d.ellipse([bx + 18, player.y1 - 196, bx + 48, player.y1 - 166], fill=hexc("#1b2431"))
    d.rectangle([player.x0, player.y1 - 34, player.x1, player.y1], fill=hexc("#0a0f17"))
    d.rounded_rectangle([player.x0 + 22, player.y1 - 22, player.x1 - 110, player.y1 - 12], radius=5, fill=hexc("#24303f"))
    prog = 0.34
    d.rounded_rectangle([player.x0 + 22, player.y1 - 22, player.x0 + 22 + int((player.w - 132) * prog), player.y1 - 12],
                        radius=5, fill=accent)
    d.ellipse([player.x0 + 16 + int((player.w - 132) * prog), player.y1 - 26,
               player.x0 + 28 + int((player.w - 132) * prog), player.y1 - 8], fill=WHITE)
    d.text((player.x1 - 96, player.y1 - 26), f"{tstamp} / 3:12:44", font=font(13, "mono"), fill=hexc("#b6c4d6"))
    # big play triangle if hovered
    if hover_play:
        d.ellipse([player.x0 + player.w // 2 - 34, player.y0 + player.h // 2 - 34,
                   player.x0 + player.w // 2 + 34, player.y0 + player.h // 2 + 34], fill=(255, 255, 255, 235))
        d.polygon([(player.x0 + player.w // 2 - 10, player.y0 + player.h // 2 - 18),
                   (player.x0 + player.w // 2 - 10, player.y0 + player.h // 2 + 18),
                   (player.x0 + player.w // 2 + 20, player.y0 + player.h // 2)], fill=hexc("#0b0f16"))

    d.text((page.x0 + 34, player.y1 + 22), title, font=font(24, "sans-bold"), fill=TEXT)
    d.text((page.x0 + 34, player.y1 + 56), meta, font=font(14, "mono"), fill=TEXT_DIM)
    # caption lines under
    cy = player.y1 + 92
    for line in caption_lines[:3]:
        d.text((page.x0 + 34, cy), line, font=font(15), fill=hexc("#c7d4e6"))
        cy += 24
    return d


def page_table(img, page: Rect, accent, title, subtitle, columns, rows, status_col=None, banner=None):
    d = ImageDraw.Draw(img)
    d.rectangle(page.as_list(), fill=(*hexc("#0f1725")[:3], 255))
    d.rectangle([page.x0, page.y0, page.x1, page.y0 + 50], fill=(*hexc("#0a111d")[:3], 255))
    _text(d, (page.x0 + 22, page.y0 + 15), title, 16, TEXT, "mono-bold")
    _text(d, (page.x1 - 22, page.y0 + 15), "api/v1 — read only", 13, TEXT_FAINT, "mono", anchor="ra")
    d.text((page.x0 + 22, page.y0 + 68), subtitle, font=font(14), fill=TEXT_DIM)
    if banner:
        by = page.y0 + 94
        d.rounded_rectangle([page.x0 + 22, by, page.x1 - 22, by + 40], radius=8,
                            fill=(*hexc("#3a1d22")[:3], 255), outline=hexc("#7b2f3a"))
        d.text((page.x0 + 36, by + 11), banner, font=font(14, "mono"), fill=hexc("#ffb3bd"))
        ty = by + 56
    else:
        ty = page.y0 + 120
    col_x = [page.x0 + 22]
    widths = [220, 190, 260, 220]
    for w in widths:
        col_x.append(col_x[-1] + w)
    d.rectangle([page.x0 + 16, ty, page.x1 - 16, ty + 32], fill=hexc("#16202f"))
    for i, c in enumerate(columns):
        d.text((col_x[i] + 6, ty + 9), c.upper(), font=font(12, "mono-bold"), fill=hexc("#7f93ad"))
    ry = ty + 34
    for row in rows:
        d.line([(page.x0 + 16, ry + 40), (page.x1 - 16, ry + 40)], fill=hexc("#1b2738"))
        for i, cell in enumerate(row[: len(columns)]):
            colour = TEXT if i == 0 else hexc("#a9bacd")
            if status_col is not None and i == status_col:
                colour = hexc("#ff8a95") if "403" in str(cell) or "block" in str(cell).lower() else GREEN
            d.text((col_x[i] + 6, ry + 11), ellipsize(str(cell), font(14, "mono"), widths[i] - 16), font=font(14, "mono"), fill=colour)
        ry += 40
    return d


def page_audio(img, page: Rect, accent, title, meta, lines, t):
    d = ImageDraw.Draw(img)
    d.rectangle(page.as_list(), fill=(*hexc("#0b1119")[:3], 255))
    d.text((page.x0 + 30, page.y0 + 28), title, font=font(24, "sans-bold"), fill=TEXT)
    d.text((page.x0 + 30, page.y0 + 62), meta, font=font(14, "mono"), fill=TEXT_DIM)
    # waveform
    wx0, wy0, wx1, wy1 = page.x0 + 30, page.y0 + 108, page.x1 - 30, page.y0 + 258
    d.rounded_rectangle([wx0, wy0, wx1, wy1], radius=10, fill=hexc("#0f1a26"), outline=hexc("#1d2c3d"))
    mid = (wy0 + wy1) / 2
    bars = 84
    for i in range(bars):
        x = wx0 + 12 + i * (wx1 - wx0 - 24) / bars
        amp = (0.35 + 0.65 * abs(math.sin(i * 0.7) * math.cos(i * 0.23))) * (wy1 - wy0) * 0.42
        played = i / bars < 0.42
        d.line([(x, mid - amp), (x, mid + amp)], fill=accent if played else hexc("#2b3d52"), width=2)
    d.line([(wx0 + 12 + 0.42 * (wx1 - wx0 - 24), wy0 + 8), (wx0 + 12 + 0.42 * (wx1 - wx0 - 24), wy1 - 8)],
           fill=hexc("#ff6b7a"), width=2)
    # transcript lines
    ty = wy1 + 28
    for i, line in enumerate(lines):
        alpha = 255 if line.get("done") else 120
        colour = hexc("#cfdcee") if line.get("done") else hexc("#5d6f8a")
        d.text((page.x0 + 30, ty), line["ts"], font=font(13, "mono"), fill=hexc("#6d8099"))
        d.text((page.x0 + 96, ty), ellipsize(line["text"], font(15), page.w - 150), font=font(15), fill=colour)
        ty += 26
    return d


def page_files(img, page: Rect, accent, heading, crumbs, rows, hover=None):
    d = ImageDraw.Draw(img)
    d.rectangle(page.as_list(), fill=(*hexc("#ffffff")[:3], 255))
    d.rectangle([page.x0, page.y0, page.x1, page.y0 + 54], fill=(*hexc("#0f2743")[:3], 255))
    _text(d, (page.x0 + 22, page.y0 + 16), "Google Drive", 16, WHITE, "sans-bold")
    _text(d, (page.x0 + 22, page.y0 + 72), crumbs, 14, hexc("#7a8ba3"), "mono")
    d.text((page.x0 + 22, page.y0 + 100), heading, font=font(26, "sans-bold"), fill=hexc("#12233a"))
    ty = page.y0 + 150
    d.rectangle([page.x0 + 16, ty, page.x1 - 16, ty + 30], fill=hexc("#eef3f9"))
    for label, lx in (("NAME", page.x0 + 30), ("OWNER", page.x0 + 520), ("SIZE", page.x1 - 240), ("MODIFIED", page.x1 - 140)):
        d.text((lx, ty + 8), label, font=font(12, "mono-bold"), fill=hexc("#5a6d85"))
    ry = ty + 34
    for i, row in enumerate(rows):
        if hover == i:
            d.rectangle([page.x0 + 16, ry, page.x1 - 16, ry + 40], fill=hexc("#e9f1fb"))
        d.rectangle([page.x0 + 26, ry + 12, page.x0 + 40, ry + 28], fill=hexc("#c9d8ea"))
        d.text((page.x0 + 50, ry + 9), ellipsize(row["name"], font(15), 430), font=font(15), fill=hexc("#22344d"))
        d.text((page.x0 + 520, ry + 11), row.get("owner", "me"), font=font(13), fill=hexc("#6b7d93"))
        d.text((page.x1 - 240, ry + 11), row.get("size", ""), font=font(13, "mono"), fill=hexc("#6b7d93"))
        d.text((page.x1 - 140, ry + 11), row.get("when", ""), font=font(13, "mono"), fill=hexc("#6b7d93"))
        ry += 40
    return d


# --------------------------------------------------------------------------
# Collection panel (right rail)
# --------------------------------------------------------------------------


def collection_panel(img: Image.Image, box: Rect, accent, family_title, dest, units, unit_label,
                     site, url, chips: list[str], est_text: str, meter: float, pulse: float = 0.0,
                     note: str = ""):
    shadow_panel(img, box, radius=16)
    d = ImageDraw.Draw(img)
    pad = 24
    x = box.x0 + pad
    inner_w = box.w - pad * 2
    y = box.y0 + 20

    d.ellipse([x, y + 4, x + 10, y + 14], fill=accent)
    d.text((x + 18, y), "COLLECTION", font=font(15, "mono-bold"), fill=hexc("#b9c9dd"))
    d.text((x, y + 30), ellipsize(family_title, font(21, "sans-bold"), inner_w),
           font=font(21, "sans-bold"), fill=TEXT)

    # destination folder
    fy = y + 66
    d.text((x, fy), "SAVED TO", font=font(12, "mono-bold"), fill=TEXT_FAINT)
    d.rounded_rectangle([x, fy + 18, x + inner_w, fy + 52], radius=8,
                        fill=(*hexc("#0b1424")[:3], 255), outline=hexc("#26374f"))
    d.text((x + 12, fy + 27), ellipsize(dest, font(14, "mono"), inner_w - 24),
           font=font(14, "mono"), fill=accent)

    # origin
    sy = fy + 70
    d.text((x, sy), "SOURCE", font=font(12, "mono-bold"), fill=TEXT_FAINT)
    d.text((x, sy + 16), ellipsize(site, font(15, "sans-bold"), inner_w), font=font(15, "sans-bold"),
           fill=hexc("#dfe8f5"))
    d.text((x, sy + 38), ellipsize(url.replace("https://", ""), font(12, "mono"), inner_w),
           font=font(12, "mono"), fill=hexc("#6d8099"))

    # counter
    cy = sy + 66
    d.text((x, cy), "ITEMS IN THIS DATA TYPE", font=font(12, "mono-bold"), fill=TEXT_FAINT)
    d.text((x, cy + 22), f"{units:,}", font=font(40, "sans-bold"), fill=TEXT)
    d.text((x, cy + 70), ellipsize(unit_label + "s", font(14), inner_w), font=font(14), fill=TEXT_DIM)

    # chips of captured items
    chy = cy + 96
    d.text((x, chy), "IN THIS RUN", font=font(12, "mono-bold"), fill=TEXT_FAINT)
    chy += 20
    for i, chip in enumerate(chips):
        appear = clamp(pulse - i * 0.35)
        h = 30
        d.rounded_rectangle([x, chy, x + inner_w, chy + h], radius=7,
                            fill=(*hexc("#0d1828")[:3], 255), outline=(*hexc("#26374f")[:3], 255))
        d.text((x + 10, chy + 6), "⤓", font=font(14), fill=accent)
        d.text((x + 30, chy + 7), ellipsize(chip, font(13, "mono"), inner_w - 44),
               font=font(13, "mono"), fill=hexc("#c8d6e8"))
        chy += h + 6

    # manual effort meter
    my = box.y1 - 84
    d.line([(x, my - 14), (box.x1 - pad, my - 14)], fill=hexc("#1e2c42"))
    d.text((x, my), "IF A HUMAN DID THIS BY HAND", font=font(12, "mono-bold"), fill=TEXT_FAINT)
    d.rounded_rectangle([x, my + 22, box.x1 - pad, my + 30], radius=4, fill=hexc("#16233a"))
    d.rounded_rectangle([x, my + 22, x + int((box.x1 - pad - x) * clamp(meter)), my + 30],
                        radius=4, fill=accent)
    d.text((x, my + 38), est_text, font=font(15, "sans-bold"), fill=hexc("#dfe8f5"))
    if note:
        d.text((x, my + 60), ellipsize(note, font(12), inner_w), font=font(12), fill=TEXT_FAINT)


# --------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------


def caption_bar(img: Image.Image, box: Rect, accent, label: str, text: str, progress: float,
                alpha: float = 1.0, footer: str = ""):
    """Two-line caption block under the window, typed on left to right."""
    if alpha <= 0:
        return
    layer = Image.new("RGBA", (box.w, box.h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0, 0, box.w, box.h], radius=12, fill=(9, 15, 26, int(232 * alpha)))
    d.rounded_rectangle([0, 0, 6, box.h], radius=3, fill=(*accent[:3], int(255 * alpha)))
    d.text((24, 14), label, font=font(13, "mono-bold"), fill=(*hexc("#7f93ad")[:3], int(255 * alpha)))

    fnt = font(25)
    lines = wrap(text, fnt, box.w - 300, max_lines=2)
    shown = text[: int(len(text) * clamp(progress * 1.08))]
    y = 42
    remaining = len(shown)
    for i, line in enumerate(lines):
        if remaining <= 0:
            break
        part = line[:remaining]
        d.text((24, y), part, font=fnt, fill=(*hexc("#e9eff8")[:3], int(255 * alpha)))
        remaining -= len(line) + 1
        y += 34

    if footer:
        d.text((box.x1 - box.x0 - 24, 44), footer, font=font(13, "mono"),
               fill=(*hexc("#5d6f8a")[:3], int(255 * alpha)), anchor="ra")
    img.alpha_composite(layer, (box.x0, box.y0))


# --------------------------------------------------------------------------
# Cursor
# --------------------------------------------------------------------------


def cursor(img: Image.Image, x: float, y: float, pressed: float = 0.0, scale: float = 1.0):
    """Arrow cursor + click ripple. Drawn on its own layer for clean edges."""
    size = 64
    layer = Image.new("RGBA", (size * 3, size * 3), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = size, size

    pts = [(0, 0), (0, 26), (7, 20), (12, 31), (19, 28), (14, 18), (23, 18)]
    pts = [(cx + px * scale, cy + py * scale) for px, py in pts]
    d.polygon(pts, fill=(255, 255, 255, 255), outline=(10, 16, 26, 255))
    d.line(pts + [pts[0]], fill=(10, 16, 26, 255), width=max(1, int(2 * scale)))

    if pressed > 0:
        r = 10 + 26 * (1 - pressed)
        a = int(160 * pressed)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(110, 170, 255, a), width=3)
        d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(110, 170, 255, int(50 * pressed)))

    img.alpha_composite(layer, (int(x - size), int(y - size)))


# --------------------------------------------------------------------------
# Small components
# --------------------------------------------------------------------------


def chapter_card(img: Image.Image, accent, index: int, total: int, title: str, lines: list[str],
                 stats: list[tuple[str, str]], progress: float):
    """Full-bleed card at the head of a chapter: fades in, holds, slides away."""
    if progress >= 1.0:
        return
    fade_in = clamp(progress / 0.12)
    fade_out = 1 - clamp((progress - 0.74) / 0.26)
    alpha = fade_in * fade_out
    if alpha <= 0.01:
        return
    slide = int(46 * clamp((progress - 0.7) / 0.3))

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([0, 0, W, H], fill=(6, 10, 18, int(240 * alpha)))

    d.rectangle([96, 292 - slide, 106, 600 - slide], fill=(*accent[:3], int(255 * alpha)))
    d.text((136, 292 - slide), f"DATA TYPE {index:02d} / {total:02d}", font=font(17, "mono-bold"),
           fill=(*accent[:3], int(255 * alpha)))
    d.text((136, 324 - slide), title, font=font(62, "sans-bold"), fill=(*hexc("#f2f6fc")[:3], int(255 * alpha)))
    y = 420 - slide
    for line in lines:
        d.text((138, y), line, font=font(24), fill=(*hexc("#9fb0c8")[:3], int(255 * alpha)))
        y += 36

    sx = 138
    sy = y + 30
    for label, value in stats:
        d.text((sx, sy), label.upper(), font=font(12, "mono-bold"), fill=(*hexc("#5d6f8a")[:3], int(255 * alpha)))
        d.text((sx, sy + 18), value, font=font(23, "sans-bold"), fill=(*hexc("#e9eff8")[:3], int(255 * alpha)))
        sx += max(230, font(23, "sans-bold").getlength(value) + 80)

    # right-hand chain: public page → document → this repo
    cx = W - 520
    cy = 560
    steps = [("public page", accent), ("document", mix(accent, (255, 255, 255, 255)[:3], 0.35)), ("this repo", hexc("#e9eff8"))]
    for i, (label, colour) in enumerate(steps):
        by = cy + i * 96
        d.rounded_rectangle([cx, by, cx + 330, by + 52], radius=10,
                            fill=(15, 24, 39, int(220 * alpha)), outline=(*colour[:3], int(180 * alpha)))
        d.ellipse([cx + 16, by + 21, cx + 26, by + 31], fill=(*colour[:3], int(255 * alpha)))
        d.text((cx + 38, by + 15), label, font=font(18, "mono"), fill=(*hexc("#e9eff8")[:3], int(255 * alpha)))
        if i < 2:
            d.line([(cx + 40, by + 52), (cx + 40, by + 96 - 14)], fill=(*hexc("#3a4d68")[:3], int(255 * alpha)), width=2)
            d.text((cx + 52, by + 62), "click · download · rename", font=font(12, "mono"),
                   fill=(*hexc("#5d6f8a")[:3], int(255 * alpha)))
    img.alpha_composite(layer, (0, 0))
