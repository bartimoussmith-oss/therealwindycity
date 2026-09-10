#!/usr/bin/env python3
"""Rebuild pipeline/renders/CONTENTION_REEL.mp4 from pipeline/videos/.

The reel is the site's front door: the most contentious verbatim moments
from official city-meeting video, concatenated into one looping file.
It's a derived artifact — rebuild it here rather than ever editing the
mp4 by hand. Requires ffmpeg (system PATH, or `pip install imageio-ffmpeg`).

Clip order is chronological by meeting; chapter timestamps in the app's
reel view must be updated if this order or the clip lengths change.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ORDER = ["mar9_cut", "mar9_return", "apr27_first", "apr27_nine",
         "apr27_pileon", "apr27_hand", "apr27_1301", "moody_swap",
         "nemecek_quote"]
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "pipeline" / "videos"
OUT = ROOT / "pipeline" / "renders" / "CONTENTION_REEL.mp4"


def ffmpeg() -> str:
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        sys.exit("ffmpeg not found: install it, or pip install imageio-ffmpeg")


def main() -> None:
    ff = ffmpeg()
    cmd: list[str] = [ff, "-y"]
    fc: list[str] = []
    for i, name in enumerate(ORDER):
        src = SRC / f"{name}.mp4"
        if not src.exists():
            sys.exit(f"missing {src}")
        cmd += ["-i", str(src)]
        # normalize: mixed 854x480@30 and 640x360@25 sources -> one format
        fc.append(
            f"[{i}:v]scale=854:480:force_original_aspect_ratio=decrease,"
            f"pad=854:480:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
            f"[v{i}];[{i}:a]aformat=sample_rates=48000:channel_layouts=mono"
            f"[a{i}];")
    cat = "".join(f"[v{i}][a{i}]" for i in range(len(ORDER)))
    fc.append(f"{cat}concat=n={len(ORDER)}:v=1:a=1[v][a]")
    cmd += ["-filter_complex", "".join(fc), "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-crf", "27", "-preset", "medium",
            "-c:a", "aac", "-b:a", "64k", "-ac", "1",
            "-movflags", "+faststart", str(OUT)]
    print(f"building {OUT.name} from {len(ORDER)} clips…")
    subprocess.run(cmd, check=True)
    print(f"done: {OUT.stat().st_size:,} bytes -> {OUT}")


if __name__ == "__main__":
    main()
