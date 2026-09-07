#!/usr/bin/env python3
"""
montage_miller.py — "THE CALLER: every cut microphone is an exhibit"
=====================================================================
The complete minuted record of Charles Miller's points of order, mic cuts,
interruptions, and rulings against him — plus the city's own record of what
happened to his arguments (they adopted them, unattributed).

Sources, strictly separated on every card:
  [MINUTES]  = city clerk's minutes (corpus, verbatim extracts)
  [VERBATIM] = Miller's own on-the-record words (user-supplied transcript indexes,
               authoritative per canon)
Run:  python3 montage_miller.py   -> renders/THE_CALLER.mp4 (+.srt)
"""
import subprocess, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cheyenne_pipeline import find_font, wrap_text  # noqa: E402

FONT = find_font() or "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
WORK = ROOT / "renders" / "caller_work"
OUT = ROOT / "renders" / "THE_CALLER.mp4"
W, H = 1080, 1920
GOLD, DIM, RED, WHITE = "0xFFD166", "0x8fa3b8", "0xFF6B6B", "white"

BEATS = [
    {"h": "THE CALLER", "n": "ONE RESIDENT", "b": "Remote. On Zoom. County resident, speaking his real name into the record. This is the city's own count of what happened next.", "s": "City minutes \u00b7 spring\u2013summer 2026 \u00b7 this record", "d": 7, "c": GOLD},
    {"h": "MARCH 9", "n": "FIRST CUT", "b": "\u201cThe second I began exposing a mathematically false financial report, a point of order cut my mic.\u201d", "s": "Miller, verbatim \u00b7 Mar 9, 2026 GB (supplied transcript record)", "d": 8, "c": WHITE},
    {"h": "MARCH 9", "n": "RULED AGAINST", "b": "During Miller's comments, Mr. Wolfe raised a point of order that comments were off subject. Mayor Collins responded that comments weren't germane.", "s": "City minutes \u00b7 Mar 9, 2026 (clip 1071)", "d": 9, "c": WHITE},
    {"h": "MARCH 9", "n": "HIS ANSWER", "b": "\u201cBy freezing this ordinance at third reading rather than dismissing it, you preserved your own poisoned paperwork\u2026 You have started a 240-day countdown. Adhere to the Wyoming Food Freedom Act.\u201d", "s": "Miller, verbatim \u00b7 Mar 9, 2026", "d": 9, "c": WHITE},
    {"h": "APRIL 27", "n": "CUT #1", "b": "During comments made by Charles Miller, Dr. Aldrich and Mr. White raised points of order that comments were off subject. \u2014 the clerk's own hand", "s": "City minutes \u00b7 Apr 27, 2026 (clip 1093)", "d": 8, "c": RED},
    {"h": "APRIL 27", "n": "CUT #2", "b": "Regarding the postponement: Mr. Moody and Mr. White raised points of order that comments were off subject. Ruled not germane to the postponement.", "s": "City minutes \u00b7 Apr 27, 2026", "d": 8, "c": RED},
    {"h": "APRIL 27", "n": "CUT #3", "b": "Again on the postponement: Mr. Moody and Mr. Laybourn raised points of order that comments were off subject.", "s": "City minutes \u00b7 Apr 27, 2026", "d": 8, "c": RED},
    {"h": "APRIL 27", "n": "CUT #4", "b": "\u201cMultiple points of order were raised that comments were off subject.\u201d The clerk stopped counting.", "s": "City minutes \u00b7 Apr 27, 2026", "d": 8, "c": RED},
    {"h": "JUNE 22", "n": "OVER HIM", "b": "During Mr. Miller's comments, Mr. Wolfe raised a point of order. Then, during Mr. Wolfe's comments, Dr. Aldrich raised a point of order \u2014 on Wolfe. They fought over his testimony.", "s": "City minutes \u00b7 Jun 22, 2026 (clip 1103)", "d": 9, "c": WHITE},
    {"h": "THE RULES,", "n": "APPLIED SELECTIVELY", "b": "\u201cSelectively enforced time limits against my testimony while allowing other speakers to return to the microphone multiple times. Ignored my raised hand in the online queue while granting in-room speakers a second turn on the same motion.\u201d", "s": "Miller, verbatim \u00b7 late-June committee record", "d": 10, "c": WHITE},
    {"h": "THE ATTORNEY", "n": "\u201cLEGALLY MEANINGLESS\u201d", "b": "His formal constructive notices to the city \u2014 dismissed by the city attorney, on the record, as \u201clegally meaningless.\u201d", "s": "Miller, verbatim \u00b7 late-June committee record", "d": 8, "c": WHITE},
    {"h": "AUGUST 21", "n": "THEY ADOPTED IT", "b": "The Food Freedom alignment he demanded on March 9 was delivered as city policy \u2014 with credit assigned elsewhere: \u201cfour or five of us asked you guys to work on this.\u201d He was in the room. On Zoom. Uncredited.", "s": "UDC work session \u00b7 Aug 21, 2026 (attendance on record)", "d": 10, "c": GOLD},
    {"h": "THE EXHIBITS", "n": "\u201cEVERY CUT MIC\nIS AN EXHIBIT\u201d", "b": "\u201cEvery cut microphone is an exhibit. Every bypassed hand is an exhibit.\u201d", "s": "Miller, verbatim \u00b7 late-June committee record", "d": 8, "c": GOLD},
    {"h": "THE RECORD", "n": "CLOSED", "b": "\u201cThe administrative record is now closed \u2014 and it is closed against you guys.\u201d The caller keeps watching. Verify every word: cheyenne.granicus.com.", "s": "Miller, verbatim + city minutes \u00b7 the public record", "d": 9, "c": WHITE},
]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return r


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    parts, metas = [], []
    total = len(BEATS)
    for i, b in enumerate(BEATS, 1):
        tag = f"{i:02d}"
        (WORK / f"h{tag}.txt").write_text(wrap_text(b["h"], 18))
        (WORK / f"n{tag}.txt").write_text(b["n"])
        (WORK / f"b{tag}.txt").write_text(wrap_text(b["b"], 29))
        (WORK / f"s{tag}.txt").write_text(b["s"])

        def dt(tf, size, col, y, t0):
            return (f"drawtext=fontfile={FONT}:textfile={tf}:fontcolor={col}:fontsize={size}:"
                    f"x=(w-text_w)/2:y={y}:alpha='clip((t-{t0})/0.6,0,1)':line_spacing=16")
        vf = (f"color=0x0d1117:size={W}x{H}:rate=30,format=yuv420p,"
              + dt(str(WORK / f"h{tag}.txt"), 74, WHITE, "h*0.14", 0.2)
              + "," + dt(str(WORK / f"n{tag}.txt"), 66, b["c"], "h*0.38", 1.2)
              + "," + dt(str(WORK / f"b{tag}.txt"), 43, WHITE, "h*0.58", 0.9)
              + "," + dt(str(WORK / f"s{tag}.txt"), 28, DIM, "h*0.87", 0.4)
              + f",drawbox=x=0:y='ih-10':w='iw*{i}/{total}':h=10:color=0x4da3ff@0.85:t=fill")
        out = WORK / f"card_{tag}.mp4"
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", vf,
             "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(b["d"]),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-c:a", "aac", "-b:a", "128k", str(out)])
        parts.append(out)
        metas.append((b["h"] + " \u2014 " + b["n"].replace("\n", " "), b["d"]))
        print(f"    [{i}/{total}] {b['h']}")
    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(OUT)])
    t0, blocks = 0.0, []
    for i, (txt, d) in enumerate(metas, 1):
        def f(t):
            h, rem = divmod(int(t), 3600); m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d},000"
        blocks.append(f"{i}\n{f(t0)} --> {f(t0+d)}\n{txt}\n")
        t0 += d
    OUT.with_suffix(".srt").write_text("\n".join(blocks))
    print(f"[+] THE CALLER -> {OUT} ({OUT.stat().st_size/1e6:.1f} MB, {t0:.0f}s, 1080x1920)")


if __name__ == "__main__":
    main()
