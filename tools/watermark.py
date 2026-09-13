#!/usr/bin/env python3
"""
tools/watermark.py — Watermark utility for The Real Windy City montages

Ensures every exported video has mandatory watermark so viewers know platform.

Watermark:
- Text: "THE REAL WINDY CITY — therealwindycity.com" bottom-right, white with black box
- Source label: top-left "clip {clip_id} {date} {start}-{end}" 
- Optional logo PNG overlay

Usage:
  python tools/watermark.py input.mp4 output.mp4 --text "THE REAL WINDY CITY"
  python tools/watermark.py --logo assets/logo.png input.mp4 output.mp4

For montage studio: engine/montage_builder.py calls this via ffmpeg filters.

Font: tries DejaVu, Liberation, Helvetica
"""
import argparse, subprocess, shutil
from pathlib import Path

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

def find_font():
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return FONT_CANDIDATES[0]

def watermark_video(input_path, output_path, text="THE REAL WINDY CITY — therealwindycity.com", source_label="", logo_path=None, vertical=True):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found")
    font = find_font()
    W, H = (1080, 1920) if vertical else (1920, 1080)

    # Escape text for drawtext
    def esc(s): return s.replace(":", "\\:").replace("'", "").replace("%", "\\%")

    # Base filter: scale + crop + watermark text bottom-right + source top-left
    vf_parts = [
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
        f"drawtext=fontfile={font}:text='{esc(text)}':fontcolor=white:fontsize=24:x=w-text_w-20:y=h-text_h-20:box=1:boxcolor=black@0.6:boxborderw=6"
    ]
    if source_label:
        vf_parts.append(f"drawtext=fontfile={font}:text='{esc(source_label)}':fontcolor=0xFFD166:fontsize=18:x=20:y=20:box=1:boxcolor=black@0.6:boxborderw=4")

    vf = ",".join(vf_parts)

    if logo_path and Path(logo_path).exists():
        # Two inputs: video + logo
        cmd = ["ffmpeg","-y","-i",str(input_path),"-i",str(logo_path),"-filter_complex",f"[0:v]{vf}[base];[base][1:v]overlay=W-w-20:H-h-20:format=auto,format=yuv420p","-c:a","copy",str(output_path)]
    else:
        cmd = ["ffmpeg","-y","-i",str(input_path),"-vf",vf,"-c:a","copy",str(output_path)]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    return output_path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", help="input mp4")
    ap.add_argument("output", help="output mp4")
    ap.add_argument("--text", default="THE REAL WINDY CITY — therealwindycity.com")
    ap.add_argument("--source", default="", help="source label top-left e.g. 'clip 1103 2026-06-22'")
    ap.add_argument("--logo", default="", help="logo PNG path")
    ap.add_argument("--horizontal", action="store_true", help="render horizontal 1920x1080 not vertical 1080x1920")
    args = ap.parse_args()
    out = watermark_video(args.input, args.output, text=args.text, source_label=args.source, logo_path=args.logo or None, vertical=not args.horizontal)
    print(f"Watermarked -> {out}")

if __name__ == "__main__":
    main()
