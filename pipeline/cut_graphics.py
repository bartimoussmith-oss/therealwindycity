#!/usr/bin/env python3
"""Graphics engine for the director's cut montages.

Builds .ass subtitle files that ffmpeg burns onto each segment:
  * karaoke word-highlight captions from the city's YouTube caption tracks
    (word times interpolated inside each cue — the standard auto-caption
    karaoke approach; text kept verbatim apart from ">>" markers)
  * speaker name tags ("CHARLES MILLER — Zoom caller") as timed chips
  * red EXHIBIT banners for the contradiction beats

Two layouts: vertical 1080x1920 (Caller tapes) and landscape 854x480 (reel).
Requires libass in ffmpeg (`-filters | grep subtitles`) + DejaVu fonts.
Stdlib only (ffmpeg does the burning).
"""
from __future__ import annotations

import html
import re
from pathlib import Path


def parse_vtt(path: str | Path) -> list[tuple[float, float, str]]:
    """Raw VTT -> [(start, end, text)] in tape seconds."""
    out = []
    for blk in re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8", errors="replace")):
        m = re.match(r"\s*(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*"
                     r"(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})[^\n]*\n([\s\S]*)", blk)
        if not m:
            continue
        s = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000
        e = int(m.group(5) or 0) * 3600 + int(m.group(6)) * 60 + int(m.group(7)) + int(m.group(8)) / 1000
        txt = html.unescape(re.sub(r"<[^>]+>", " ", m.group(9)))
        txt = re.sub(r"\s+", " ", txt).strip()
        if txt:
            out.append((s, e, txt))
    return out


def clean_caption(txt: str) -> str:
    txt = txt.replace(">>", " ")
    txt = re.sub(r"\s+", " ", txt).strip()
    if re.fullmatch(r"\[[^\]]*\]", txt):  # "[snorts]"-only cues
        return ""
    return txt


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(int(t), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}.{int((t - int(t)) * 100):02d}"


def _esc(txt: str) -> str:
    return txt.replace("{", "(").replace("}", ")")


def _wrap(words: list[str], width: int) -> list[str]:
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def caption_events(cues, a: float, b: float, width: int = 30, max_words: int = 12):
    """Cues overlapping tape range [a,b] -> ASS Dialogue lines (segment-relative)."""
    evs = []
    for s, e, txt in cues:
        if e <= a or s >= b:
            continue
        txt = clean_caption(txt)
        words = txt.split()
        if not words:
            continue
        s0, e0 = max(s, a) - a, min(e, b) - a
        if e0 - s0 < 0.2:
            continue
        # chunk long cues into sequential events so lines stay readable
        for c in range(0, len(words), max_words):
            chunk = words[c:c + max_words]
            f0 = c / len(words)
            f1 = (c + len(chunk)) / len(words)
            cs, ce = s0 + (e0 - s0) * f0, s0 + (e0 - s0) * f1
            k = max(8, int((ce - cs) * 100 / len(chunk)))  # centiseconds/word
            body = "".join(f"{{\\kf{k}}}{_esc(w)} " for w in chunk).rstrip()
            lines = _wrap(re.sub(r"\{\\kf\d+\}", "", body).split(), width)
            # re-attach karaoke tags in order after wrapping
            tagged = re.findall(r"\{\\kf\d+\}\S+", body)
            out, wi = [], 0
            for li, ln in enumerate(lines):
                parts = []
                for _ in ln.split():
                    parts.append(tagged[wi])
                    wi += 1
                out.append(" ".join(parts))
            evs.append((_ass_time(cs), _ass_time(ce), r"\N".join(out)))
    # de-overlap (VTT cues roll over each other)
    evs.sort(key=lambda e: e[0])
    fixed = []
    for i, (s, e, t) in enumerate(evs):
        if i + 1 < len(evs) and e > evs[i + 1][0]:
            e = evs[i + 1][0]
        if e > s:
            fixed.append((s, e, t))
    return [f"Dialogue: 0,{s},{e},cap,,0,0,0,,{t}" for s, e, t in fixed]


VERTICAL_STYLES = """Style: cap,DejaVu Sans,64,&H00FFFFFF,&H0091A0C0,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,40,40,660,1
Style: tag,DejaVu Sans,40,&H0066D1FF,&H000000FF,&H00000000,&HD0000000,-1,0,0,0,100,100,0,0,3,2,0,7,48,48,150,1
Style: exhibit,DejaVu Sans,44,&H00FFFFFF,&H000000FF,&H1A6B6BFF,&H1A6B6BFF,-1,0,0,0,100,100,0,0,3,2,0,8,40,40,48,1"""

LANDSCAPE_STYLES = """Style: cap,DejaVu Sans,30,&H00FFFFFF,&H0091A0C0,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,28,1
Style: tag,DejaVu Sans,21,&H0066D1FF,&H000000FF,&H00000000,&HD0000000,-1,0,0,0,100,100,0,0,3,1,0,7,16,16,14,1
Style: exhibit,DejaVu Sans,23,&H00FFFFFF,&H000000FF,&H1A6B6BFF,&H1A6B6BFF,-1,0,0,0,100,100,0,0,3,1,0,8,16,16,12,1"""

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{styles}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass(vtt_path: str | Path, a: float, b: float, out_path: str | Path,
              tags: list[tuple[float, float, str]] | None = None,
              exhibits: list[tuple[float, float, str]] | None = None,
              landscape: bool = False) -> Path:
    """Write a burned-graphics .ass for tape range [a,b]. Tag/exhibit times are
    SEGMENT-relative seconds; caption times come from the VTT (tape-absolute)."""
    cues = parse_vtt(vtt_path)
    w, h = (854, 480) if landscape else (1080, 1920)
    lines = [HEADER.format(w=w, h=h,
                           styles=LANDSCAPE_STYLES if landscape else VERTICAL_STYLES)]
    lines += caption_events(cues, a, b, width=34 if landscape else 26)
    for t0, t1, name in (tags or []):
        lines.append(f"Dialogue: 1,{_ass_time(t0)},{_ass_time(t1)},tag,,0,0,0,,{{\\an7}}{_esc(name)}")
    for t0, t1, label in (exhibits or []):
        lines.append(f"Dialogue: 2,{_ass_time(t0)},{_ass_time(t1)},exhibit,,0,0,0,,{{\\an8}}{_esc(label)}")
    out = Path(out_path)
    out.write_text("\n".join(lines) + "\n")
    return out
