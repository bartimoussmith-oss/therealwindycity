"""Small shared helpers: fonts, easing, colour, formatting, text layout.

No third-party dependency beyond Pillow. Everything here is deterministic so
that re-rendering the film produces byte-identical frames.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache

from PIL import ImageFont

# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------

_FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    os.path.expanduser("~/.fonts"),
]

_FAMILIES = {
    "sans": ["DejaVuSans.ttf", "DejaVuSans-ExtraLight.ttf"],
    "sans-bold": ["DejaVuSans-Bold.ttf"],
    "mono": ["DejaVuSansMono.ttf"],
    "mono-bold": ["DejaVuSansMono-Bold.ttf"],
    "serif": ["DejaVuSerif.ttf", "DejaVuSans.ttf"],
}


def _find_font(names: list[str]) -> str | None:
    for d in _FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    # matplotlib bundles DejaVu if the system copy is missing
    try:
        import matplotlib

        base = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
        for n in names:
            p = os.path.join(base, n)
            if os.path.exists(p):
                return p
    except Exception:
        pass
    return None


@lru_cache(maxsize=512)
def font(size: int, weight: str = "sans") -> ImageFont.FreeTypeFont:
    path = _find_font(_FAMILIES.get(weight, _FAMILIES["sans"]))
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default(size)  # Pillow >= 10 accepts a size here


# --------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------


def hexc(value: str, alpha: int | None = None) -> tuple:
    value = value.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    if alpha is None:
        return (r, g, b)
    return (r, g, b, alpha)


def mix(a: tuple, b: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    n = min(len(a), len(b))
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(n))


def lighten(c: tuple, t: float) -> tuple:
    return mix(c, (255, 255, 255, len(c) if len(c) == 4 else 3)[: len(c)], t)


def darken(c: tuple, t: float) -> tuple:
    return mix(c, (0, 0, 0, len(c) if len(c) == 4 else 3)[: len(c)], t)


# --------------------------------------------------------------------------
# Easing / timing
# --------------------------------------------------------------------------


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def ease(t: float) -> float:
    """Smooth in-out (cubic)."""
    t = clamp(t)
    return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2


def ease_out(t: float) -> float:
    t = clamp(t)
    return 1 - pow(1 - t, 3)


def ease_out_back(t: float, s: float = 1.70158) -> float:
    t = clamp(t)
    return 1 + (s + 1) * pow(t - 1, 3) + s * pow(t - 1, 2)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ramp(t: float, start: float, dur: float) -> float:
    """0..1 progress of an event that begins at `start` and lasts `dur`."""
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return clamp((t - start) / dur)


def deterministic_noise(seed: int, t: float) -> float:
    """Cheap smooth pseudo-noise in [-1, 1]; no RNG state, fully reproducible."""
    return (
        math.sin(t * 1.7 + seed * 12.9898) * 0.5
        + math.sin(t * 3.1 + seed * 78.233) * 0.3
        + math.sin(t * 7.3 + seed * 37.719) * 0.2
    )


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------


def human_bytes(n: int | float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def human_int(n: int | float) -> str:
    return f"{int(round(n)):,}"


def human_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} sec"
    minutes, s = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, m = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {m:02d} m" if m else f"{hours} h"
    days, h = divmod(hours, 24)
    day_word = "day" if days == 1 else "days"
    return f"{days} {day_word} {h} h" if h else f"{days} {day_word}"


def timecode(t: float) -> str:
    t = max(0.0, t)
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def ellipsize(text: str, fnt, max_w: float) -> str:
    if fnt.getlength(text) <= max_w:
        return text
    while text and fnt.getlength(text + "…") > max_w:
        text = text[:-1]
    return text + "…"


def wrap(text: str, fnt, max_w: float, max_lines: int = 99) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if fnt.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    elif cur:
        lines[-1] = ellipsize(lines[-1] + " " + cur, fnt, max_w)
    return lines
