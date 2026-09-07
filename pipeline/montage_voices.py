#!/usr/bin/env python3
"""
montage_voices.py — THE RECORD SPEAKS: VOICES edition
======================================================
The montage, but with THEIR ACTUAL WORDS PLAYING FROM THE TAPE.
Sources: city YouTube videos (cityvideos.json) — real footage, real audio.

At home (streams play there):  python3 montage_voices.py
It will yt-dlp any missing section automatically (needs deno + `--remote-components`
on some networks; plain yt-dlp usually suffices at home).

Segments (edit freely — add meetings/quotes; every entry = real tape):
  {"yt": "<video-id>", "from": "HH:MM:SS", "to": "HH:MM:SS",
   "caption": "burned quote", "label": "on-screen source", "trim": (in,out) optional}
"""
import subprocess, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cheyenne_pipeline import vertical_segment, find_font, wrap_text  # noqa: E402

WORK = ROOT / "renders" / "voices_work"
OUT = ROOT / "renders" / "THE_RECORD_SPEAKS_VOICES.mp4"
FONT = find_font() or "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 1080, 1920

COTW0114 = "tUTtHJp87Iw"  # Committee of the Whole - Jan 14, 2026 (city YouTube)

SEGMENTS = [
    {"file": "videos/nemecek_quote.mp4", "trim": (20, 100),
     "caption": "\u201cIt\u2019s lipstick on a pig. We\u2019ve got a pig, and we\u2019ve been putting "
                "lipstick on it for five decades. And we\u2019re two decades past a major renovation.\u201d",
     "label": "Vicki Nemecek \u00b7 Public Works Director \u00b7 COTW Jan 14, 2026"},
    {"file": "videos/moody_swap.mp4", "trim": (5, 70),
     "caption": "\u201cIncrease the city street maintenance project from 9 million to 20 million \u2014 "
                "and number 10, you would remove $22 million.\u201d",
     "label": "Chair Segrave, on Moody\u2019s amendment \u00b7 COTW Jan 14, 2026"},
]

HOOK = {"title": "THE RECORD SPEAKS", "sub": "their words \u00b7 on tape \u00b7 Jan 14, 2026", "dur": 5}
CTA = {"title": "\u201c$0 FOR TREATMENT\u201d",
       "sub": "the ballot they built 48 hours later \u00b7 verify: cheyenne.granicus.com", "dur": 7}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return r


def fetch_section(yt: str, a: str, b: str, name: str) -> Path:
    out = ROOT / "videos" / f"{name}.mp4"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={yt}"
    cmd = ["yt-dlp", "-f", "bv*[height<=480]+ba/b[height<=480]/best",
           "--download-sections", f"*{a}-{b}", "-o", str(out),
           "--force-keyframes-at-cuts", "--merge-output-format", "mp4", url]
    try:
        run(cmd)
    except RuntimeError:
        run(["yt-dlp", "--remote-components", "ejs:github", *cmd[1:]])
    return out


def card(title, sub, dur, tag):
    tf = WORK / f"t{tag}.txt"; tf.write_text(wrap_text(title, 16))
    sf = WORK / f"s{tag}.txt"; sf.write_text(sub)
    vf = (f"color=0x0d1117:size={W}x{H}:rate=30,format=yuv420p,"
          f"drawtext=fontfile={FONT}:textfile={tf}:fontcolor=0xFFD166:fontsize=96:"
          f"x=(w-text_w)/2:y=h*0.38:line_spacing=24,"
          f"drawtext=fontfile={FONT}:textfile={sf}:fontcolor=white:fontsize=40:"
          f"x=(w-text_w)/2:y=h*0.72:line_spacing=14")
    out = WORK / f"card_{tag}.mp4"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", vf,
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(dur),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-c:a", "aac", "-b:a", "128k", str(out)])
    return out


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    parts = [card(HOOK["title"], HOOK["sub"], HOOK["dur"], "hook")]
    for i, seg in enumerate(SEGMENTS, 1):
        if seg.get("file"):
            raw = ROOT / seg["file"]
            print(f"[*] section {i}/{len(SEGMENTS)}: {raw.name}")
        else:
            print(f"[*] section {i}/{len(SEGMENTS)}: {seg['yt']} {seg['from']}-{seg['to']}")
            raw = fetch_section(seg["yt"], seg["from"], seg["to"], f"yt_{seg['yt']}_{seg['from'].replace(':','')}")
        clip = raw
        if seg.get("trim"):
            a, b = seg["trim"]
            clip = WORK / f"cut_{i}.mp4"
            run(["ffmpeg", "-y", "-ss", str(a), "-t", str(b - a), "-i", str(raw),
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                 "-c:a", "aac", "-b:a", "128k", str(clip)])
        parts.append(vertical_segment(clip, seg["caption"], seg["label"], WORK, f"{i:02d}"))
        print(f"    [+] {seg['label'][:60]}")
    parts.append(card(CTA["title"], CTA["sub"], CTA["dur"], "cta"))
    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(OUT)])
    d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(OUT)], capture_output=True, text=True).stdout.strip()
    print(f"[+] VOICES MONTAGE -> {OUT} ({OUT.stat().st_size/1e6:.1f} MB, {float(d):.0f}s, REAL AUDIO)")


if __name__ == "__main__":
    main()
