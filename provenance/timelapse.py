"""The time-lapse: every file in the collection, flying past at speed.

The chapter film is the how-to — one family at a time, the clicks, the
downloads. This is the other half of the same claim: *here is the whole pile*.
Thousands of files in the order they were captured, each one labelled with the
family it belongs to and the site it came from, fast enough to see the shape of
the archive and slow enough to read individual names as they pass.

Every frame counts files that are actually on disk at render time. Nothing is
animated from a made-up number.

    python3 -m provenance timelapse            # video/provenance-timelapse.mp4
    python3 -m provenance timelapse --preview 2,5,9,14
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from . import art
from . import inventory as inventory_mod
from . import origins
from .util import clamp, ease, ease_out, ellipsize, font, hexc, human_bytes, human_int, mix

W, H = art.W, art.H

# scene lengths, seconds
TL_TITLE = 3.6
TL_RUN = 13.2
TL_OUTRO = 3.2

# how many cells are on screen at once, and where the two columns sit
COLS, ROWS = 30, 21
GRID_LEFT, GRID_TOP, GRID_RIGHT, GRID_BOTTOM = 60, 172, 1372, 966
CELL_W = (GRID_RIGHT - GRID_LEFT) / COLS
CELL_H = (GRID_BOTTOM - GRID_TOP) / ROWS
PANEL_X = 1408


@dataclass
class Entry:
    rel: str
    family: str
    accent: str
    host: str
    size: int
    ext: str


def snapshot(root: Path, inv) -> list[dict]:
    """Every file the scanner assigned, as plain data — no drawing.

    Written to `data/out/provenance-timelapse-frames.json` so the time-lapse can be
    re-rendered later, or a different one made, without walking 1.5 GB again.
    """
    rows = []
    for base, dirs, files in os.walk(root.resolve()):
        dirs[:] = sorted(d for d in dirs if d not in inventory_mod.EXCLUDE_DIRS)
        for name in sorted(files):
            p = Path(base) / name
            rel = p.relative_to(root.resolve()).as_posix()
            if any(rel == ex or rel.startswith(ex + "/") for ex in inventory_mod.EXCLUDE_PATHS):
                continue
            fam = next((f for f in inv.families if f.match(rel)), None)
            if fam is None:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            rows.append({"rel": rel, "family": fam.key, "size": size,
                         "ext": p.suffix.lower().lstrip(".") or "—"})
    return rows


def collect(root: Path, inv) -> list[Entry]:
    """Walk the checkout in the same order `scan()` does, keeping every file."""
    root = root.resolve()
    fam_of = {}
    acc = {}
    for fam in inv.families:
        acc[fam.key] = fam.accent
    entries: list[Entry] = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in inventory_mod.EXCLUDE_DIRS)
        for name in sorted(files):
            p = Path(base) / name
            rel = p.relative_to(root).as_posix()
            if any(rel == ex or rel.startswith(ex + "/") for ex in inventory_mod.EXCLUDE_PATHS):
                continue
            fam = next((f for f in inv.families if f.match(rel)), None)
            if fam is None:
                continue
            if fam.key not in fam_of:
                hosts = [origins.host_of(u) for u in fam.samples[:5] if origins.host_of(u)]
                fam_of[fam.key] = fam
                acc[fam.key] = fam.accent
            try:
                size = p.stat().st_size
            except OSError:
                continue
            entries.append(
                Entry(rel=rel, family=fam.key, accent=acc[fam.key], host="", size=size,
                      ext=p.suffix.lower().lstrip(".") or "—")
            )
    return entries


class Timelapse:
    def __init__(self, inv, entries: list[Entry], seed: int = 7):
        self.inv = inv
        self.entries = self._order(entries, seed)
        self.desktop = art.make_desktop()
        self._tiles: dict[str, Image.Image] = {}
        self.total = TL_TITLE + TL_RUN + TL_OUTRO
        self.rate = len(self.entries) / TL_RUN
        self.host_of_family = {
            f.key: (origins.display_host(f.host_hits[0].host)[0] if f.host_hits else "this repo")
            for f in inv.families
        }

    @staticmethod
    def _order(entries: list[Entry], seed: int) -> list[Entry]:
        """Merge the families by *how far through each one we are*.

        A family with 1,581 files therefore contributes about fifty times as
        many cells per second as one with 24, and every family finishes at the
        same moment — which is what an archive assembled over years looks like
        when you speed it up.
        """
        buckets: dict[str, list[Entry]] = {}
        for e in entries:
            buckets.setdefault(e.family, []).append(e)
        keyed = []
        for key, items in buckets.items():
            n = len(items)
            for i, e in enumerate(items):
                keyed.append(((i + 0.5) / n, key, i, e))
        keyed.sort(key=lambda row: (row[0], row[1], row[2]))
        return [row[3] for row in keyed]

    # -- helpers ---------------------------------------------------------
    def _geom(self, t: float):
        """Grid reveal is diagonal, with a jitter so it reads as many hands."""
        return {}

    def frame(self, t: float) -> Image.Image:
        img = self.desktop.copy().convert("RGBA")
        d = ImageDraw.Draw(img)

        if t < TL_TITLE:
            self._title(img, d, t)
        elif t < TL_TITLE + TL_RUN:
            self._run(img, d, t - TL_TITLE)
        else:
            self._outro(img, d, t - TL_TITLE - TL_RUN)
        return img.convert("RGB")

    # -- title -----------------------------------------------------------
    def _title(self, img, d, t):
        art.menubar(d, t, "time-lapse · the whole collection at once", rec=True)
        a = ease(clamp(t / 0.7)) * (1 - ease(clamp((t - (TL_TITLE - 0.8)) / 0.8)))
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rectangle([0, 0, W, H], fill=(6, 10, 18, int(235 * a)))
        ld.text((150, 300), "TIME-LAPSE", font=font(20, "mono-bold"), fill=(*hexc("#6ea8ff")[:3], int(255 * a)))
        ld.text((150, 334), "Every file, in one pass", font=font(70, "sans-bold"),
                fill=(*art.TEXT[:3], int(255 * a)))
        ld.text((150, 452), "Each cell below is one file this repo holds — named, placed in its family,",
                font=font(25), fill=(*hexc("#9fb0c8")[:3], int(255 * a)))
        ld.text((150, 488), "and titled by the public site it came from. Watch the pile build.",
                font=font(25), fill=(*hexc("#9fb0c8")[:3], int(255 * a)))

        tot = self.inv
        stats = [
            (f"{tot.total_files:,}", "files"),
            (f"{len(tot.data_families)}", "families"),
            (f"{len(tot.host_totals)}", "source sites"),
            (human_bytes(tot.total_bytes), "on disk"),
        ]
        x = 150
        for i, (v, lab) in enumerate(stats):
            ap = clamp((t - 0.9 - i * 0.16) / 0.45)
            if ap <= 0:
                continue
            ld.text((x, 600), v, font=font(38, "sans-bold"), fill=(*art.TEXT[:3], int(255 * a * ap)))
            ld.text((x, 650), lab.upper(), font=font(12, "mono-bold"), fill=(*hexc("#5d6f8a")[:3], int(255 * a * ap)))
            x += font(38, "sans-bold").getlength(v) + 70
        img.alpha_composite(layer)

    # -- the run ---------------------------------------------------------
    def _run(self, img, d, t):
        art.menubar(d, t + TL_TITLE, f"{human_int(self.rate)} files / second  ·  the checkout, in capture order", rec=True)

        # progress across the whole run
        prog = clamp(t / TL_RUN)
        shown = int(len(self.entries) * ease(prog))
        fade_in = ease(clamp(t / 0.5))
        fade_out = 1 - ease(clamp((t - (TL_RUN - 0.6)) / 0.6))

        # header line: running totals
        d.text((80, 108), human_int(shown) + " files", font=font(30, "sans-bold"),
               fill=mix(hexc("#0e1726"), art.TEXT, fade_in))
        d.text((80 + font(30, "sans-bold").getlength(human_int(shown) + " files") + 20, 118),
               "of " + human_int(len(self.entries)), font=font(15, "mono"), fill=hexc("#7f93ad"))
        d.text((W - 80, 112), f"{t:04.1f}s / {TL_RUN:04.1f}s", font=font(15, "mono"),
               fill=hexc("#7f93ad"), anchor="ra")

        # the wall: newest lands bottom-right, oldest scrolls off the top
        start_idx = max(0, shown - COLS * ROWS)
        window = self.entries[start_idx:shown]
        for i, e in enumerate(window):
            x = GRID_LEFT + (i % COLS) * CELL_W
            y = GRID_TOP + (i // COLS) * CELL_H
            img.alpha_composite(self._tile(e), (int(x), int(y)))

        # shadow the older rows so the eye stays on what just landed
        veil = Image.new("RGBA", (int(GRID_RIGHT - GRID_LEFT) + 2, int(GRID_BOTTOM - GRID_TOP) + 2), (0, 0, 0, 0))
        vd = ImageDraw.Draw(veil)
        for r in range(ROWS):
            age = r / max(1, ROWS - 1)
            alpha = int(165 * (1 - age) ** 1.5)
            if alpha:
                vd.rectangle([0, int(r * CELL_H), veil.width, int((r + 1) * CELL_H)], fill=(9, 14, 24, alpha))
        if fade_out < 1:
            veil.putalpha(veil.getchannel("A").point(lambda v: v))
        img.alpha_composite(veil, (int(GRID_LEFT), int(GRID_TOP)))

        # what just arrived, spelled out in full down the right-hand column
        self._arrivals(img, d, window[-14:], fade_in, fade_out)

        # the family mix: cumulative, so the bar shows the archive accreting
        counts: dict[str, int] = {}
        for e in self.entries[:shown]:
            counts[e.family] = counts.get(e.family, 0) + 1
        self._mix(d, counts, shown, fade_out)

    def _mix(self, d, counts, shown, fade_out):
        """One stacked bar: what the pile is made of, so far."""
        a = fade_out
        y = H - 62
        d.text((60, y - 30), "WHAT THE PILE IS MADE OF", font=font(12, "mono-bold"),
               fill=(*hexc("#5d6f8a")[:3], int(255 * a)))
        total = max(1, sum(counts.values()))
        x = 60
        right = W - 60
        ordered = sorted(counts.items(), key=lambda kv: -kv[1])
        for key, n in ordered:
            fam = next((f for f in self.inv.families if f.key == key), None)
            if not fam:
                continue
            w = (right - 60) * n / total
            if w < 1:
                continue
            d.rectangle([x, y, x + w, y + 12], fill=(*hexc(fam.accent)[:3], int(255 * a)))
            x += w
        # call out the biggest three by name
        lx = 60
        for key, n in ordered[:3]:
            fam = next((f for f in self.inv.families if f.key == key), None)
            if not fam:
                continue
            d.rectangle([lx, y + 22, lx + 9, y + 31], fill=(*hexc(fam.accent)[:3], int(255 * a)))
            label = f"{fam.title.split('(')[0].strip()} — {human_int(n)}"
            d.text((lx + 15, y + 21), ellipsize(label, font(11), 380), font=font(11),
                   fill=(*art.TEXT[:3], int(235 * a)))
            lx += min(430, font(11).getlength(label) + 60)
        d.text((right, y - 30), f"{human_int(shown)} files · {len(counts)} families so far",
               font=font(12, "mono"), fill=(*hexc("#5d6f8a")[:3], int(255 * a)), anchor="ra")

    # -- one cell, drawn once and reused ---------------------------------
    def _tile(self, e: Entry) -> Image.Image:
        tile = self._tiles.get(e.rel)
        if tile is not None:
            return tile
        cw, chh = max(4, int(CELL_W) - 3), max(4, int(CELL_H) - 3)
        tile = Image.new("RGBA", (cw, chh), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        if e.ext in ("mp4", "mp3", "wav", "webm", "m4a"):
            fill, bar = hexc("#0b1626"), hexc("#ffc857")
        elif e.ext == "pdf":
            fill, bar = hexc("#101a2b"), hexc("#ff6b6b")
        elif e.ext in ("json", "csv", "db", "gz", "xml"):
            fill, bar = hexc("#0d1b1a"), hexc("#3ddc97")
        elif e.ext in ("md", "txt"):
            fill, bar = hexc("#0e1626"), hexc("#6ea8ff")
        elif e.ext in ("png", "jpg", "jpeg"):
            fill, bar = hexc("#151428"), hexc("#c792ea")
        else:
            fill, bar = hexc("#0f1524"), hexc(e.accent)
        tint = mix(hexc("#0b1220"), hexc(e.accent), 0.55)
        td.rounded_rectangle([0, 0, cw - 1, chh - 1], radius=2, fill=(*tint[:3], 255))
        td.rectangle([0, 0, cw - 1, 1], fill=bar)
        self._tiles[e.rel] = tile
        return tile

    # -- the arrivals column ---------------------------------------------
    def _arrivals(self, img, d, recent, fade_in, fade_out):
        x = PANEL_X
        top = GRID_TOP
        a = fade_in * fade_out
        d.text((x, top - 40), "JUST ARRIVED", font=font(13, "mono-bold"),
               fill=mix(hexc("#0e1726"), hexc("#7f93ad"), a))
        d.line([(x, top - 16), (W - 60, top - 16)], fill=(*hexc("#22334d")[:3], int(255 * a)))
        y = top + 6
        for k, e in enumerate(reversed(recent)):
            alpha = int(255 * a * (1.0 - k / 16.0) ** 0.7)
            if alpha <= 4:
                continue
            fam = next((f for f in self.inv.families if f.key == e.family), None)
            accent = hexc(fam.accent if fam else "#6ea8ff")
            d.rectangle([x, y + 5, x + 5, y + 25], fill=(*accent[:3], alpha))
            name = os.path.basename(e.rel)
            d.text((x + 14, y), ellipsize(name, font(14, "mono"), W - 60 - x - 14),
                   font=font(14, "mono"), fill=(*art.TEXT[:3], alpha))
            sub = f"{e.family.replace('_', ' ')} · {human_bytes(e.size)}"
            d.text((x + 14, y + 19), ellipsize(sub, font(11), W - 60 - x - 14),
                   font=font(11), fill=(*hexc("#6d8099")[:3], int(alpha * 0.9)))
            y += 48

    # -- outro -----------------------------------------------------------
    def _outro(self, img, d, t):
        art.menubar(d, t + TL_TITLE + TL_RUN, "done", rec=False)
        a = ease(clamp(t / 0.6))
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rectangle([0, 0, W, H], fill=(6, 10, 18, int(215 * a)))
        ld.text((150, 280), "ALL OF IT", font=font(20, "mono-bold"), fill=(*hexc("#6ea8ff")[:3], int(255 * a)))
        n = len(self.entries)
        ld.text((150, 314), f"{n:,} files in {self.total:.0f} seconds", font=font(64, "sans-bold"),
                fill=(*art.TEXT[:3], int(255 * a)))
        ld.text((150, 430), "The chapter film shows how each family is fetched by hand.",
                font=font(25), fill=(*hexc("#9fb0c8")[:3], int(255 * a)))
        ld.text((150, 466), "This is what all of those trips add up to.",
                font=font(25), fill=(*hexc("#9fb0c8")[:3], int(255 * a)))
        fam = self.inv
        line = (f"{human_bytes(fam.total_bytes)} · {len(fam.data_families)} families · "
                f"{len(fam.host_totals)} source sites · {fam.unassigned['files']} unaccounted for")
        ld.text((150, 540), line, font=font(18, "mono"), fill=(*hexc("#7f93ad")[:3], int(255 * a)))
        ld.text((150, H - 150), "rendered from the checkout — python3 -m provenance timelapse",
                font=font(15, "mono"), fill=(*hexc("#4e6079")[:3], int(255 * a)))
        img.alpha_composite(layer)
