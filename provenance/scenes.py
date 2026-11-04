"""The film itself: timeline, choreography and per-frame drawing."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from . import art
from .art import (
    BROWSER,
    CAPTION_BOX,
    PANEL_BOX,
    RAIL_Y,
    Rect,
)
from .story import Chapter, Story
from .util import (
    clamp,
    ease,
    ease_out,
    ellipsize,
    font,
    hexc,
    human_bytes,
    human_duration,
    human_int,
    lerp,
    mix,
    ramp,
    wrap,
)

# scene durations (seconds)
INTRO = 10.0
DETECT = 15.0
CHAPTER = 14.6
MONTAGE = 9.0
FINALE = 19.0
ENDCARD = 8.0


def _accent(ch: Chapter) -> tuple:
    return hexc(ch.accent)


# --------------------------------------------------------------------------
# Choreography for one manual run
# --------------------------------------------------------------------------

T_TYPE_START = 3.35
T_LOAD_START = 5.05
T_ROW0_HOVER = 5.9
T_ROW0_CLICK = 6.5
T_ITEM = 6.62
T_DL_HOVER = 7.25
T_DL_CLICK = 7.75
T_BACK = 9.05
T_ROW1_HOVER = 9.35
T_ROW1_CLICK = 9.85
T_ITEM2 = 9.97
T_DL2_CLICK = 10.85
T_SAVE = 11.95
T_PANEL = 12.3


@dataclass
class RunState:
    url: str
    load: float
    phase: str
    hover_row: int | None
    press_row: int | None
    hover_dl: bool
    press_dl: bool
    typed_frac: float
    chips: list[tuple[str, float]]  # (label, launch time)
    saved: int
    caption_idx: int
    caption_progress: float
    cursor: tuple[float, float]
    click: float
    meter: float


def _panel_chip_top(ch) -> float:
    """Vertical centre of the first "IN THIS RUN" chip in the collection panel."""
    return PANEL_BOX.y0 + 357


def _bezier(p0, p1, p2, t):
    t = clamp(t)
    x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
    y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
    return x, y


def _cursor_at(t: float, keys: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """keys: (time, x, y). Returns (x, y, click_pulse)."""
    if t <= keys[0][0]:
        x, y = keys[0][1], keys[0][2]
    else:
        x, y = keys[-1][1], keys[-1][2]
        for (t0, x0, y0), (t1, x1, y1) in zip(keys, keys[1:]):
            if t0 <= t <= t1:
                f = ease((t - t0) / max(1e-6, t1 - t0))
                # small arc so paths are not ruler-straight
                mx = (x0 + x1) / 2 + (y1 - y0) * 0.06
                my = (y0 + y1) / 2 - (x1 - x0) * 0.04
                x, y = _bezier((x0, y0), (mx, my), (x1, y1), f)
                break
    jx = math.sin(t * 2.3) * 1.1 + math.sin(t * 5.7) * 0.5
    jy = math.cos(t * 1.9) * 1.0 + math.cos(t * 6.1) * 0.4
    return x + jx, y + jy, 0.0


def run_state(ch: Chapter, t: float, geom: dict) -> RunState:
    url = ch.url.replace("https://", "")
    typed_frac = clamp((t - T_TYPE_START) / 1.55)
    n_chars = int(len(url) * typed_frac)
    typed = url[:n_chars]
    load = ease(clamp((t - T_LOAD_START) / 0.55)) if t >= T_LOAD_START else 0.0

    phase = "index"
    if T_ITEM <= t < T_BACK:
        phase = "item"
    elif t >= T_ITEM2:
        phase = "item"

    hover_row = None
    press_row = None
    if T_ROW0_HOVER <= t < T_ROW0_CLICK:
        hover_row = 0
    elif T_ROW0_CLICK <= t < T_ROW0_CLICK + 0.18:
        hover_row, press_row = 0, 0
    elif T_ROW1_HOVER <= t < T_ROW1_CLICK:
        hover_row = 1
    elif T_ROW1_CLICK <= t < T_ROW1_CLICK + 0.18:
        hover_row, press_row = 1, 1

    hover_dl = T_DL_HOVER <= t < T_DL_CLICK + 0.2 or (t >= 10.45 and t < T_DL2_CLICK + 0.2)
    press_dl = (T_DL_CLICK <= t < T_DL_CLICK + 0.2) or (T_DL2_CLICK <= t < T_DL2_CLICK + 0.2)

    chips: list[tuple[str, float]] = []
    if t >= T_DL_CLICK:
        chips.append((geom["chip_label_1"], T_DL_CLICK))
    if t >= T_DL2_CLICK:
        chips.append((geom["chip_label_2"], T_DL2_CLICK))

    saved = sum(1 for _, t0 in chips if t >= t0 + 0.9)

    cap_bounds = [(0.9, 5.4), (5.4, 9.7), (9.7, 14.4)]
    caption_idx = 2
    caption_progress = 1.0
    for i, (a, b) in enumerate(cap_bounds):
        if t < b:
            caption_idx = i
            caption_progress = clamp((t - a) / (b - a))
            break

    click = 0.0
    for ct in (3.15, T_ROW0_CLICK, T_DL_CLICK, T_ROW1_CLICK, T_DL2_CLICK):
        if 0 <= t - ct < 0.4:
            click = 1 - (t - ct) / 0.4

    cursor = _cursor_at(t, geom["keys"])[:2] if t < T_PANEL else (
        geom["panel_point"][0] + math.sin(t * 2.0) * 2,
        geom["panel_point"][1] + math.cos(t * 1.7) * 2,
    )

    meter = clamp(0.25 + 0.75 * ease(clamp((t - T_SAVE) / 1.4)))
    return RunState(
        url=typed,
        load=load,
        phase=phase,
        hover_row=hover_row,
        press_row=press_row,
        hover_dl=hover_dl,
        press_dl=press_dl,
        typed_frac=typed_frac,
        chips=chips,
        saved=saved,
        caption_idx=caption_idx,
        caption_progress=caption_progress,
        cursor=cursor,
        click=click,
        meter=meter,
    )


# --------------------------------------------------------------------------
# Page drawing for one chapter
# --------------------------------------------------------------------------


def _draw_index(img, page: Rect, ch: Chapter):
    accent = _accent(ch)
    if ch.page == "list":
        return art.page_list(
            img, page, accent,
            heading="Minutes and Agendas" if "Minutes" in ch.site else "Agenda Center",
            crumbs="Home  ›  Your Government  ›  City Council  ›  Minutes & Agendas",
            rows=ch.rows or [{"date": "Aug 24, 2026", "body": "City Council", "docs": [{"label": "Agenda"}]}],
            chips=("All bodies", "2026", "Agendas & minutes"),
            sub="Council · Finance · Public Services · Committee of the Whole · Work Sessions",
            hover=None,
        )
    if ch.page == "video":
        tape = ch.tape
        art.page_video(
            img, page, accent,
            title=tape.get("title", "City Council"),
            meta=tape.get("meta", ""),
            tstamp=tape.get("tstamp", "00:00:00"),
            caption_lines=ch.caption_lines,
        )
        return None
    if ch.page == "table":
        table = ch.table
        art.page_table(
            img, page, accent,
            title=table.get("title", "datasets.json"),
            subtitle="public record · fetched by the engine, not by a person",
            columns=table.get("columns", ["A", "B", "C", "D"]),
            rows=table.get("rows", []),
            status_col=2,
            banner=table.get("banner"),
        )
        return None
    if ch.page == "audio":
        art.page_audio(
            img, page, accent,
            title="Feed 47003 — Laramie County public safety",
            meta="broadcastify.com/archives/feed/47003 · archived segments · transcribed locally",
            lines=[{"ts": l["ts"], "text": l["text"], "done": True} for l in ch.audio_lines],
            t=0.0,
        )
        return None
    if ch.page == "files":
        art.page_files(
            img, page, accent,
            heading="processed_database",
            crumbs="My Drive  ›  WindyCityMeetings  ›  processed_database",
            rows=ch.files,
        )
        return None
    return None


def _doc_button(page: Rect) -> Rect:
    rail_x0 = page.x0 + 34 + 660 + 26
    rail_x1 = page.x1 - 26
    return Rect(rail_x0, page.y0 + 146 + (page.y1 - 26 - (page.y0 + 146)) - 52, rail_x0 + 210,
                page.y0 + 146 + (page.y1 - 26 - (page.y0 + 146)) - 6)


def _draw_item(img, page: Rect, ch: Chapter, st: RunState):
    accent = _accent(ch)
    if ch.page in ("list", "doc"):
        doc = ch.doc or {"title": "Document", "meta": "", "pages": 12}
        btn = art.page_doc(
            img, page, accent,
            title=doc["title"], meta=doc["meta"], pages=doc.get("pages", 12),
            download_hover=st.hover_dl, download_pressed=st.press_dl,
            attachments=ch.attachments or [{"name": c, "meta": "saved from this page"} for c in ch.chips],
            highlight=st.hover_dl,
            sheet_label=ch.sheet_label,
            button_label=("Save page" if ch.key == "meeting_calendar"
                          else "Save minutes" if ch.key == "minutes_and_notes"
                          else "Download PDF" if "granicus" in ch.url or "agenda" in ch.key
                          else "Save item"),
            viewer_label=("OPEN CITIES CMS  ·  PAGE VIEW" if "cheyennecity" in ch.url
                          else "GRANICUS  ·  AGENDA VIEWER" if "granicus" in ch.url
                          else "BROWSER  ·  PAGE VIEW"),
        )
        return btn
    if ch.page == "video":
        art.page_video(
            img, page, accent,
            title=ch.tape.get("title", ""), meta=ch.tape.get("meta", ""),
            tstamp=ch.tape.get("tstamp", "00:00:00"), caption_lines=ch.caption_lines,
            hover_play=st.hover_dl,
        )
        return Rect(page.x1 - 220, page.y0 + 420, page.x1 - 40, page.y0 + 466)
    if ch.page == "table":
        table = ch.table
        art.page_table(
            img, page, accent,
            title=table.get("title", "datasets.json"),
            subtitle="public record · fetched by the engine, not by a person",
            columns=table.get("columns", ["A", "B", "C", "D"]),
            rows=table.get("rows", []),
            status_col=2,
            banner=table.get("banner"),
        )
        return Rect(page.x1 - 260, page.y0 + 300, page.x1 - 40, page.y0 + 344)
    if ch.page == "audio":
        art.page_audio(
            img, page, accent,
            title="Feed 47003 — Laramie County public safety",
            meta="broadcastify.com/archives/feed/47003 · archived segments · transcribed locally",
            lines=[{"ts": l["ts"], "text": l["text"], "done": True} for l in ch.audio_lines],
            t=1.0,
        )
        return Rect(page.x1 - 260, page.y0 + 108, page.x1 - 40, page.y0 + 254)
    if ch.page == "files":
        art.page_files(
            img, page, accent,
            heading="processed_database",
            crumbs="My Drive  ›  WindyCityMeetings  ›  processed_database",
            rows=ch.files, hover=0 if st.hover_dl else None,
        )
        return Rect(page.x0 + 520, page.y0 + 184, page.x1 - 40, page.y0 + 224)
    return None


# --------------------------------------------------------------------------
# Film
# --------------------------------------------------------------------------


@dataclass
class Film:
    story: Story
    desktop: Image.Image = field(init=False)
    schedule: list[tuple[str, float, float, object]] = field(default_factory=list)

    def __post_init__(self):
        self.desktop = art.make_desktop()
        t = 0.0
        self.schedule.append(("intro", t, INTRO, None))
        t += INTRO
        self.schedule.append(("detect", t, DETECT, None))
        t += DETECT
        for ch in self.story.chapters:
            self.schedule.append(("chapter", t, CHAPTER, ch))
            t += CHAPTER
        self.schedule.append(("montage", t, MONTAGE, None))
        t += MONTAGE
        self.schedule.append(("finale", t, FINALE, None))
        t += FINALE
        self.schedule.append(("endcard", t, ENDCARD, None))
        self.duration = t + ENDCARD

    # -- helpers ---------------------------------------------------------
    def _chapter_index(self, t: float) -> int:
        for i, (kind, start, dur, ch) in enumerate(self.schedule):
            if start <= t < start + dur:
                return i
        return len(self.schedule) - 1

    def _rail(self, d, t):
        chips = []
        for kind, start, dur, ch in self.schedule:
            if kind == "chapter":
                chips.append((f"{ch.index:02d} {ch.title}", dur))
            elif kind == "intro":
                chips.append(("intro", dur))
            elif kind == "detect":
                chips.append(("detect", dur))
            elif kind == "montage":
                chips.append(("also", dur))
            elif kind == "finale":
                chips.append(("collection", dur))
            elif kind == "endcard":
                chips.append(("end", dur))
        idx = 0
        for i, (kind, start, dur, ch) in enumerate(self.schedule):
            if t >= start:
                idx = i
        art.chapter_rail(d, chips, idx, t, self.duration)

    # -- frame -----------------------------------------------------------
    def frame(self, t: float) -> Image.Image:
        img = self.desktop.copy().convert("RGBA")
        d = ImageDraw.Draw(img)

        kind, start, dur, payload = self.schedule[self._chapter_index(t)]
        local = t - start
        total_scraped = self.story.totals["scraped_files"]

        if kind == "intro":
            self._intro(img, d, local, dur)
        elif kind == "detect":
            self._detect(img, d, local, dur)
        elif kind == "chapter":
            self._chapter(img, d, local, dur, payload, t)
        elif kind == "montage":
            self._montage(img, d, local, dur)
        elif kind == "finale":
            self._finale(img, d, local, dur)
        elif kind == "endcard":
            self._endcard(img, d, local, dur)

        self._rail(ImageDraw.Draw(img), t)
        return img.convert("RGB")

    # -- intro -----------------------------------------------------------
    def _intro(self, img, d, t, dur):
        art.menubar(d, t, "introduction", rec=False, dim=True)
        a = ease(clamp(t / 0.8)) * (1 - ease(clamp((t - (dur - 1.0)) / 1.0)))
        if a <= 0:
            return
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rectangle([0, 0, art.W, art.H], fill=(6, 10, 18, int(230 * a)))

        # scan line
        sy = int((t * 300) % (art.H + 200) - 100)
        ld.line([(0, sy), (art.W, sy)], fill=(90, 140, 220, 26))

        x = 150
        y = 300
        ld.text((x, y), "PROVENANCE", font=font(20, "mono-bold"), fill=(*hexc("#6ea8ff")[:3], int(255 * a)))
        ld.text((x, y + 34), "Where the record comes from", font=font(72, "sans-bold"), fill=(*art.TEXT[:3], int(255 * a)))

        sub = "Every dataset in this archive, traced back to the public page it came from —"
        sub2 = "and what a person would have had to click, download and file by hand."
        ld.text((x, y + 132), sub, font=font(26), fill=(*hexc("#9fb0c8")[:3], int(255 * a)))
        ld.text((x, y + 168), sub2, font=font(26), fill=(*hexc("#9fb0c8")[:3], int(255 * a)))

        tot = self.story.totals
        stats = [
            (f"{tot['files']:,}", "files classified"),
            (f"{tot['families']}", "data families"),
            (f"{tot['hosts']}", "source sites"),
            (f"{human_bytes(tot['bytes'])}", "on disk"),
            (f"{tot['years'][0]}–{tot['years'][1]}", "record range"),
        ]
        sx = x
        for i, (value, label) in enumerate(stats):
            appear = clamp((t - 1.4 - i * 0.18) / 0.5)
            if appear <= 0:
                continue
            ld.text((sx, y + 262), value, font=font(40, "sans-bold"), fill=(*art.TEXT[:3], int(255 * a * appear)))
            ld.text((sx, y + 312), label.upper(), font=font(12, "mono-bold"), fill=(*hexc("#5d6f8a")[:3], int(255 * a * appear)))
            sx += font(40, "sans-bold").getlength(value) + 64

        footer = "a film generated from the repository itself · no invented facts, no stock footage"
        ld.text((x, art.H - 150), footer, font=font(18, "mono"), fill=(*hexc("#4e6079")[:3], int(255 * a)))
        img.alpha_composite(layer)

    # -- detect ----------------------------------------------------------
    def _detect(self, img, d, t, dur):
        art.menubar(d, t, "detect · scanning the checkout", rec=True)
        box = Rect(150, 110, 1770, 900)
        art.shadow_panel(img, box, radius=12, fill=hexc("#070d16"), stroke=hexc("#1b2a40"))
        d = ImageDraw.Draw(img)

        d.text((box.x0 + 24, box.y0 + 18), "●  provenance detect --root .", font=font(16, "mono-bold"), fill=hexc("#7ee0b0"))
        d.text((box.x1 - 24, box.y0 + 18), "read-only · walks every file once", font=font(14, "mono"), fill=art.TEXT_FAINT, anchor="ra")
        d.line([(box.x0, box.y0 + 50), (box.x1, box.y0 + 50)], fill=hexc("#18263a"))

        lines = self.story.detect_lines
        lh = 27
        top = box.y0 + 72
        bottom = box.y1 - 132
        capacity = max(6, (bottom - top) // lh)
        reveal = clamp((t - 0.6) / 4.6)
        shown = int(len(lines) * reveal)
        scroll = max(0, shown - capacity)
        y = top
        for i, (key, line) in enumerate(lines[scroll:shown]):
            fade = clamp((shown - scroll - i) / 2.0)
            d.text((box.x0 + 26, y), ellipsize(line, font(16, "mono"), box.w - 60), font=font(16, "mono"),
                   fill=mix(hexc("#5d6f8a"), hexc("#d8e4f2"), fade))
            y += lh
            if y > bottom:
                break
        if scroll > 0:
            d.text((box.x1 - 26, box.y0 + 58), f"… {scroll} earlier families scrolled past",
                   font=font(12, "mono"), fill=hexc("#4a5a72"), anchor="ra")

        # summary at the bottom
        if shown >= len(lines):
            a = clamp((t - 7.0) / 0.6)
            tot = self.story.totals
            d.rectangle([box.x0, box.y1 - 118, box.x1, box.y1], fill=hexc("#0b1420"))
            d.line([(box.x0, box.y1 - 118), (box.x1, box.y1 - 118)], fill=hexc("#18263a"))
            d.text((box.x0 + 26, box.y1 - 98), "0", font=font(30, "sans-bold"), fill=mix(hexc("#0b1420"), hexc("#3ddc97"), a))
            d.text((box.x0 + 56, box.y1 - 92), "files unaccounted for", font=font(18, "mono"), fill=mix(hexc("#0b1420"), hexc("#9fb0c8"), a))
            words = f"{tot['files']:,} files · {tot['scraped_files']:,} scraped · {tot['families']} data families · {tot['hosts']} source sites"
            d.text((box.x1 - 26, box.y1 - 92), words, font=font(17, "mono"), fill=mix(hexc("#0b1420"), hexc("#e9eff8"), a), anchor="ra")

    # -- chapter ---------------------------------------------------------
    def _chapter(self, img, d, local, dur, ch: Chapter, t_global):
        accent = _accent(ch)
        geom = self._geom(ch)

        st = run_state(ch, local, geom)
        art.menubar(d, local, f"{ch.site}  ·  {ch.url.replace('https://','')}", rec=True)

        page = art.browser(img, BROWSER, st.url or "about:blank", ch.site, accent,
                           load=st.load, tab=ch.site)
        d = ImageDraw.Draw(img)

        if st.load < 1.0:
            # the previous page is still on screen while the next one loads
            _draw_index(img, page, ch)
            d = ImageDraw.Draw(img)
            veil = int(210 * (1 - st.load))
            d.rectangle(page.as_list(), fill=(255, 255, 255, veil))
            if st.load > 0.02:
                d.text((page.x0 + 40, page.y0 + 46), "Loading…", font=font(20),
                       fill=mix(hexc("#f2f5f9"), hexc("#8b9bb0"), st.load))
        else:
            if st.phase == "index":
                _draw_index(img, page, ch)
                d = ImageDraw.Draw(img)
                # hover row highlight redraw on top for list pages
                if ch.page == "list" and st.hover_row is not None:
                    art.page_list(
                        img, page, accent,
                        heading="Minutes and Agendas" if "Minutes" in ch.site else "Agenda Center",
                        crumbs="Home  ›  Your Government  ›  City Council  ›  Minutes & Agendas",
                        rows=ch.rows or [{"date": "Aug 24, 2026", "body": "City Council", "docs": [{"label": "Agenda"}]}],
                        chips=("All bodies", "2026", "Agendas & minutes"),
                        sub="Council · Finance · Public Services · Committee of the Whole · Work Sessions",
                        hover=st.hover_row, pressed=st.press_row,
                    )
            else:
                _draw_item(img, page, ch, st)
                d = ImageDraw.Draw(img)

            # page transition flash
            if 0.0 <= local - T_ITEM < 0.22 or 0.0 <= local - T_ITEM2 < 0.22:
                d.rectangle(page.as_list(), fill=(255, 255, 255, 90))

        # collection panel
        chips_labels = [c[0] for c in st.chips]
        art.collection_panel(
            img, PANEL_BOX, accent, ch.title, ch.dest, ch.units, ch.unit_label,
            ch.site, ch.url, chips_labels,
            ch.manual_text, st.meter, pulse=clamp((local - T_DL_CLICK) / 1.2),
            note=f"{human_int(ch.units)} {ch.unit_label}s in this family",
        )

        # flying chips
        for i, (label, launch) in enumerate(st.chips):
            f = clamp((local - launch - 0.05) / 0.62)
            if f <= 0:
                continue
            src = geom["chip_origin"]
            dst = self._chip_slots(ch)[min(i, len(self._chip_slots(ch)) - 1)]
            if f < 1:
                e = ease(f)
                x, y = _bezier(src, ((src[0] + dst[0]) / 2, src[1] - 140), dst, e)
                # the card shrinks into the panel chip and fades as it lands
                alpha = 1.0 - clamp((f - 0.72) / 0.28)
                if alpha <= 0.02:
                    continue
                self._chip_card(img, x - 165 + 40 * e, y - 16, label, accent, alpha)

        # captions
        cap = ch.captions[st.caption_idx]
        art.caption_bar(
            img, CAPTION_BOX, accent,
            f"WHAT A HUMAN HAS TO DO  ·  {ch.index:02d}  ·  {ch.title}",
            cap,
            clamp(st.caption_progress * 2.2),
            alpha=clamp((local - 0.4) / 0.4),
            footer=f"{ch.title}  ·  {ch.index:02d} / {len(self.story.chapters):02d}  ·  ≈ {ch.actions:,} actions",
        )

        # cursor
        cx, cy = st.cursor
        art.cursor(img, cx, cy, pressed=st.click)

        # chapter card overlay (first ~2.3s)
        if local < 2.35:
            prog = clamp(local / 2.35)
            art.chapter_card(
                img, accent, ch.index, len(self.story.chapters), ch.title,
                ch.intro_lines, ch.stats, prog,
            )
            # fade from black at the very start
            if local < 0.35:
                a = int(255 * (1 - local / 0.35))
                img.alpha_composite(art.overlay((art.W, art.H), (0, 0, 0), a))

    @staticmethod
    def _chip_slots(ch: Chapter) -> list[tuple[float, float]]:
        """Where a flying file card lands: the left edge of the matching panel chip."""
        x = PANEL_BOX.x0 + 24 + 36
        y = _panel_chip_top(ch)
        return [(x, y), (x, y + 36)]

    def _chip_card(self, img, x, y, label, accent, fade=1.0):
        fade = clamp(fade)
        w, h = 330, 32
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=8,
                            fill=(16, 26, 43, int(240 * fade)), outline=(*accent[:3], int(190 * fade)))
        d.text((10, 7), "⤓", font=font(15), fill=(*accent[:3], int(255 * fade)))
        d.text((30, 8), ellipsize(label, font(13, "mono"), w - 44), font=font(13, "mono"),
               fill=(*hexc("#d6e3f2")[:3], int(255 * fade)))
        img.alpha_composite(layer, (int(x), int(y)))

    def _geom(self, ch: Chapter) -> dict:
        page = Rect(BROWSER.x0 + 1, BROWSER.y0 + 42 + 44, BROWSER.x1 - 1, BROWSER.y1 - 1)
        rows_y0 = page.y0 + 212 + 38
        row0 = (page.x0 + 430, rows_y0 + 31)
        row1 = (page.x0 + 430, rows_y0 + 62 + 31)
        dl = _doc_button(page)
        dl_point = (dl.x0 + 100, dl.y0 + 22)
        if ch.page == "table":
            dl_point = (page.x1 - 150, page.y0 + 322)
        elif ch.page == "audio":
            dl_point = (page.x1 - 150, page.y0 + 180)
        elif ch.page == "files":
            dl_point = (page.x0 + 620, page.y0 + 204)
        elif ch.page == "video":
            dl_point = (page.x1 - 130, page.y0 + 444)

        keys = [
            (2.15, art.W + 60, 980),
            (3.0, 520, 137),
            (3.15, 520, 137),
            (3.9, 700, 190),
            (5.5, row0[0], row0[1]),
            (T_ROW0_CLICK, row0[0], row0[1]),
            (6.95, page.x0 + 700, page.y0 + 420),
            (T_DL_HOVER, dl_point[0], dl_point[1]),
            (T_DL_CLICK, dl_point[0], dl_point[1]),
            (8.55, page.x0 + 620, page.y0 + 500),
            (T_ROW1_HOVER, row1[0], row1[1]),
            (T_ROW1_CLICK, row1[0], row1[1]),
            (10.3, page.x0 + 700, page.y0 + 420),
            (T_DL2_CLICK, dl_point[0], dl_point[1]),
            (T_PANEL, PANEL_BOX.x0 + 180, PANEL_BOX.y0 + 300),
        ]
        return {
            "keys": keys,
            "chip_origin": dl_point,
            "panel_point": (PANEL_BOX.x0 + 220, PANEL_BOX.y0 + 360),
            "chip_label_1": (ch.chips[0] if ch.chips else "item_01"),
            "chip_label_2": (ch.chips[1] if len(ch.chips) > 1 else "item_02"),
        }

    # -- montage ---------------------------------------------------------
    def _montage(self, img, d, t, dur):
        art.menubar(d, t, "everything else in the collection", rec=False, dim=True)
        d.rectangle([110, 120, art.W - 110, art.H - 100], fill=(*hexc("#0a111d")[:3], 255),
                    outline=(*hexc("#1b2a40")[:3], 255))
        d.text((140, 150), "ALSO COLLECTED, ALSO TRACEABLE", font=font(16, "mono-bold"), fill=hexc("#6ea8ff"))
        items = self.story.montage
        cols, rows = 3, 4
        cw, chh = 520, 150
        x0, y0 = 140, 200
        for i, item in enumerate(items[: cols * rows]):
            appear = clamp((t - 0.35 - i * 0.13) / 0.5)
            if appear <= 0:
                continue
            cx = x0 + (i % cols) * (cw + 30)
            cy = y0 + (i // cols) * (chh + 22)
            a = ease(appear)
            layer = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            ld.rounded_rectangle([0, 0, cw - 1, chh - 1], radius=12,
                                 fill=(15, 24, 39, int(245 * a)), outline=(*hexc("#22334d")[:3], int(255 * a)))
            ld.text((20, 18), ellipsize(item["title"], font(20, "sans-bold"), cw - 40), font=font(20, "sans-bold"),
                    fill=(*art.TEXT[:3], int(255 * a)))
            ld.text((20, 52), f"{human_int(item['units'])} {item['unit']}s · {item['size']}",
                    font=font(15, "mono"), fill=(*hexc("#94a5bd")[:3], int(255 * a)))
            ld.text((20, 80), ellipsize(item["dest"], font(13, "mono"), cw - 40), font=font(13, "mono"),
                    fill=(*hexc("#5d6f8a")[:3], int(255 * a)))
            tag = item["class"].upper()
            tw = font(11, "mono-bold").getlength(tag) + 18
            ld.rounded_rectangle([20, 110, 20 + tw, 132], radius=9, fill=(*hexc("#152437")[:3], int(255 * a)))
            ld.text((29, 114), tag, font=font(11, "mono-bold"), fill=(*hexc("#7f93ad")[:3], int(255 * a)))
            img.alpha_composite(layer, (cx, cy))

    # -- finale ----------------------------------------------------------
    def _finale(self, img, d, t, dur):
        art.menubar(d, t, "one collection", rec=False, dim=True)
        accent = hexc("#6ea8ff")
        a = ease(clamp(t / 0.9))
        x = 130
        d.text((x, 150), "ONE COLLECTION", font=font(20, "mono-bold"), fill=mix(hexc("#0a0f1a"), accent, a))
        d.text((x, 184), "Assembled from public", font=font(46, "sans-bold"), fill=mix(hexc("#0a0f1a"), art.TEXT, a))
        d.text((x, 238), "pages, one at a time.", font=font(46, "sans-bold"), fill=mix(hexc("#0a0f1a"), art.TEXT, a))

        tot = self.story.totals
        stats = [
            (f"{tot['scraped_files']:,}", "scraped files"),
            (f"{human_bytes(tot['scraped_bytes'])}", "scraped bytes"),
            (f"{tot['hosts']}", "source sites"),
            (f"{tot['unassigned']}", "files unaccounted"),
        ]
        y = 330
        for i, (value, label) in enumerate(stats):
            app = clamp((t - 0.8 - i * 0.15) / 0.5)
            if app <= 0:
                continue
            d.text((x, y), value, font=font(36, "sans-bold"), fill=mix(hexc("#0a0f1a"), art.TEXT, app))
            d.text((x, y + 42), label.upper(), font=font(12, "mono-bold"), fill=mix(hexc("#0a0f1a"), hexc("#5d6f8a"), app))
            y += 88

        # hosts table (right)
        box = Rect(900, 150, art.W - 120, 748)
        app = clamp((t - 1.2) / 0.8)
        d.rounded_rectangle(box.as_list(), radius=14, fill=(*hexc("#0c1422")[:3], int(255 * app)),
                            outline=(*hexc("#22334d")[:3], int(255 * app)))
        d.text((box.x0 + 24, box.y0 + 20), "SOURCE SITES FOUND IN THE REPO ITSELF", font=font(13, "mono-bold"),
               fill=(*hexc("#7f93ad")[:3], int(255 * app)))
        hosts = [h for h in self.story.hosts if h["name"] not in {"GitHub", "this site"}][:11]
        hy = box.y0 + 56
        for i, h in enumerate(hosts):
            appear = clamp((t - 1.4 - i * 0.09) / 0.4)
            if appear <= 0:
                continue
            d.text((box.x0 + 24, hy), ellipsize(h["name"], font(17), 330), font=font(17),
                   fill=(*art.TEXT[:3], int(255 * appear)))
            d.text((box.x0 + 372, hy + 2), ellipsize(h["host"], font(13, "mono"), 330), font=font(13, "mono"),
                   fill=(*hexc("#6d8099")[:3], int(255 * appear)))
            d.text((box.x1 - 24, hy + 1), f"{h['count']:,}", font=font(15, "mono"), fill=(*hexc("#9fb0c8")[:3], int(255 * appear)), anchor="ra")
            hy += 32
            if hy > box.y1 - 30:
                break

        # contrast strip
        if t > 4.6:
            app2 = clamp((t - 4.6) / 0.8)
            bar = Rect(130, 800, art.W - 120, 900)
            d.rounded_rectangle(bar.as_list(), radius=12, fill=(*hexc("#101a2b")[:3], int(255 * app2)), outline=(*hexc("#22334d")[:3], int(255 * app2)))
            d.text((bar.x0 + 26, bar.y0 + 22), "IF A PERSON FETCHED IT BY HAND", font=font(13, "mono-bold"), fill=(*hexc("#7f93ad")[:3], int(255 * app2)))
            d.text((bar.x0 + 26, bar.y0 + 44), human_duration(tot["manual_seconds_scraped"]), font=font(30, "sans-bold"), fill=(*art.TEXT[:3], int(255 * app2)))
            d.text((bar.x0 + 380, bar.y0 + 22), f"≈ {tot['manual_actions_scraped']:,.0f} clicks, downloads and renames at published, conservative rates",
                   font=font(16), fill=(*hexc("#94a5bd")[:3], int(255 * app2)))
            d.text((bar.x0 + 380, bar.y0 + 48), "the engine runs the same sweep every six hours, and records what changed",
                   font=font(16), fill=(*hexc("#6d8099")[:3], int(255 * app2)))
            d.text((bar.x1 - 26, bar.y0 + 34), "civic-cycle · 6h", font=font(20, "mono-bold"), fill=(*accent[:3], int(255 * app2)), anchor="ra")

    # -- endcard ---------------------------------------------------------
    def _endcard(self, img, d, t, dur):
        art.menubar(d, t, "", rec=False, dim=True)
        d.rectangle([0, 0, art.W, art.H], fill=(*hexc("#060a12")[:3], 255))
        a = ease(clamp(t / 0.8))
        d.text((150, 260), "Every byte above is traceable to a public URL.", font=font(46, "sans-bold"),
               fill=mix(hexc("#060a12"), art.TEXT, a))
        d.text((150, 330), "Nothing in this film was staged: the dates, filenames, charges, dataset IDs and",
               font=font(22), fill=mix(hexc("#060a12"), hexc("#9fb0c8"), a))
        d.text((150, 364), "radio lines were read out of the repository at render time.",
               font=font(22), fill=mix(hexc("#060a12"), hexc("#9fb0c8"), a))

        lines = [
            ("inventory", "PROVENANCE-INVENTORY.md   ·   data/out/provenance-inventory.json"),
            ("rebuild the scan", "python3 -m provenance detect"),
            ("rebuild this film", "python3 -m provenance video"),
            ("the collector itself", "engine/scheduler.py --once   (civic-cycle, every 6 hours)"),
        ]
        y = 470
        for label, cmd in lines:
            app = clamp((t - 0.7 - (y - 470) / 900) / 0.5)
            if app <= 0:
                continue
            d.text((150, y), label.upper(), font=font(12, "mono-bold"), fill=(*hexc("#5d6f8a")[:3], int(255 * app)))
            d.text((150, y + 20), cmd, font=font(20, "mono"), fill=(*hexc("#d8e4f2")[:3], int(255 * app)))
            y += 78

        d.text((150, art.H - 120), "The Real Windy City — civic transparency engine · Cheyenne / Laramie County, Wyoming",
               font=font(15, "mono"), fill=hexc("#3f5169"))
