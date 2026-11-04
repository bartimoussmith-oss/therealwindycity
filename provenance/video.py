"""Encode rendered frames with ffmpeg (bundled via imageio-ffmpeg, or system)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def ffmpeg_path() -> str:
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return exe
    except Exception:
        pass
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    raise RuntimeError(
        "ffmpeg not found. Install it (pip install imageio-ffmpeg) or put ffmpeg on PATH."
    )


def encode_frames(
    frames,
    out_path: Path,
    width: int,
    height: int,
    fps: int,
    total_frames: int,
    scale: float = 1.0,
    crf: int = 20,
    preset: str = "medium",
    progress: bool = True,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_path(),
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "-",
    ]
    vf = []
    if abs(scale - 1.0) > 1e-3:
        vf.append(f"scale={int(width * scale) // 2 * 2}:{int(height * scale) // 2 * 2}:flags=lanczos")
    vf.append("format=yuv420p")
    cmd += [
        "-vf", ",".join(vf),
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-movflags", "+faststart",
        "-an",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for i, frame in enumerate(frames):
            proc.stdin.write(frame.tobytes())
            if progress and (i % 120 == 0 or i == total_frames - 1):
                pct = 100.0 * (i + 1) / max(1, total_frames)
                sys.stderr.write(f"\r  rendering {i + 1:>5}/{total_frames} frames  {pct:5.1f}%")
                sys.stderr.flush()
    finally:
        if proc.stdin:
            proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "ignore") if proc.stderr else ""
        code = proc.wait()
    if progress:
        sys.stderr.write("\n")
    if code != 0:
        raise RuntimeError(f"ffmpeg failed ({code}):\n{err[-2000:]}")
    return out_path
