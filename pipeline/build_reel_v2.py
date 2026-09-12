#!/usr/bin/env python3
"""CONTENTION REEL v2 — the same nine-clip, 16:25 evidence reel, captioned.

v1 was a bare concat with no burned graphics. v2 re-cuts all nine clips
from the cut_media/ segment pulls and burns landscape graphics on every
clip: karaoke word captions, speaker name tags, chapter slugs.

Clip DURATIONS ARE PINNED to v1 exactly (110/120/115/110/155/155/80/80/80)
so the app's REEL_CHAPTERS timestamps stay valid. Same output filename.
Run: python3 build_reel_v2.py  -> renders/CONTENTION_REEL.mp4 (+.srt)
"""
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cut_graphics import build_ass  # noqa: E402

WORK = ROOT / "renders" / "reel_v2_work"
MEDIA = ROOT / "cut_media"
CAPTIONS = ROOT / "cut_captions"  # all 23 video VTTs live here
OUT = ROOT / "renders" / "CONTENTION_REEL.mp4"


def t(hms):
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


MILLER = "CHARLES MILLER \u2014 Zoom caller"
DAIS = "THE DAIS"

# (pull, vid, pull_start, a, b, vtt_dir, tags, slug, srt_label)
CLIPS = [
    ("mar9_cut_src", "19tQtLA8klo", "04:29:30", "04:32:35", "04:34:25", CAPTIONS,
     [("04:32:35", "04:34:08", MILLER), ("04:34:08", "04:34:25", DAIS)],
     "1 \u00b7 THE CUT \u2014 MAR 9, 10:34 PM", "0:00 \u2014 The cut: three minutes in, gavel mid-sentence (Mar 9, 10:34 p.m.)"),
    ("mar9_return_src", "19tQtLA8klo", "05:47:00", "05:47:50", "05:49:50", CAPTIONS,
     [("05:47:50", "05:49:50", MILLER)],
     "2 \u00b7 MILLER \u2014 MAR 9, 11:48 PM", "1:50 \u2014 Miller: \u201cyou used a point of order to cut my microphone\u201d (Mar 9, 11:48 p.m.)"),
    ("apr27_first_src", "y9vnXtjZpR0", "02:17:00", "02:18:30", "02:20:25", CAPTIONS,
     [("02:18:30", "02:18:47", MILLER), ("02:18:47", "02:19:00", DAIS),
      ("02:19:00", "02:20:15", MILLER), ("02:20:15", "02:20:25", DAIS)],
     "3 \u00b7 FIRST TURN \u2014 APR 27", "3:50 \u2014 First turn, interrupted; \u201cyour time\u2019s up\u201d (Apr 27, 8:19 p.m.)"),
    ("apr27_nine_src", "y9vnXtjZpR0", "03:40:00", "03:41:30", "03:43:20", CAPTIONS,
     [("03:41:30", "03:42:15", MILLER), ("03:42:15", "03:43:20", DAIS)],
     "4 \u00b7 NINE PEOPLE YELLING \u2014 APR 27", "5:45 \u2014 \u201cNine people yelling point of order at me\u201d (Apr 27, ~10:40 p.m.)"),
    ("apr27_pileon_src", "y9vnXtjZpR0", "03:09:00", "03:09:45", "03:12:20", CAPTIONS,
     [("03:09:45", "03:10:30", DAIS), ("03:10:30", "03:11:50", MILLER), ("03:11:50", "03:12:20", DAIS)],
     "5 \u00b7 THE PILE-ON \u2014 APR 27", "7:35 \u2014 The pile-on: \u201cnot on the postponement\u201d \u2192 \u201cmotion and a second to call you out of order\u201d (Apr 27, 9:10 p.m.)"),
    ("apr27_hand_src", "y9vnXtjZpR0", "02:42:30", "02:43:25", "02:46:00", CAPTIONS,
     [("02:43:25", "02:44:25", DAIS), ("02:44:25", "02:44:30", "CITY CLERK"),
      ("02:44:30", "02:44:50", DAIS), ("02:44:50", "02:45:35", MILLER), ("02:45:35", "02:46:00", DAIS)],
     "6 \u00b7 THE BYPASSED HAND \u2014 APR 27", "10:10 \u2014 The bypassed hand: skipped \u2192 \u201cmoved on\u201d \u2192 apology \u2192 point of order anyway (Apr 27, 8:44 p.m.)"),
    ("apr27_1301_src", "y9vnXtjZpR0", "03:00:00", "03:01:10", "03:02:30", CAPTIONS,
     [("03:01:10", "03:01:46", MILLER), ("03:01:46", "03:02:30", DAIS)],
     "7 \u00b7 THE LAST ITEM \u2014 APR 27", "12:45 \u2014 \u201cI find you out of order, Mr. Miller\u201d mid-sentence (1:30 a.m.)"),
    ("moody_src", "tUTtHJp87Iw", "00:27:40", "00:27:50", "00:29:10", CAPTIONS,
     [("00:27:50", "00:28:20", DAIS), ("00:28:20", "00:29:10", "CHAIR SEGRAVE")],
     "8 \u00b7 \u2018REMOVE $22M\u2019 \u2014 JAN 14", "14:05 \u2014 \u201cRemove $22M from the consent agenda\u201d (Jan 14 COW)"),
    ("nemecek_src", "tUTtHJp87Iw", "00:46:50", "00:47:10", "00:48:30", CAPTIONS,
     [("00:47:10", "00:48:30", "VICKI NEMECEK \u2014 Public Works Director")],
     "9 \u00b7 \u2018LIPSTICK ON A PIG\u2019", "15:25 \u2014 \u201cLipstick on a pig\u201d \u2014 Public Works on the consent-agenda contract (finance committee)"),
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
    (ROOT / "renders").mkdir(parents=True, exist_ok=True)
    parts, metas = [], []
    for pull, vid, pstart, a, b, capdir, tags, slug, srt in CLIPS:
        asec, bsec = t(a), t(b)
        off = asec - t(pstart)
        assert off >= 0, f"{pull} range outside pull"
        praw = MEDIA / f"{pull}.mp4"
        pdur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(praw)]).stdout)
        assert bsec - t(pstart) <= pdur + 0.5, f"{pull} too short for {a}-{b}"
        ass = WORK / f"{pull}.ass"
        build_ass(capdir / f"{vid}.en.vtt", asec, bsec, ass,
                  tags=[(t(x) - asec, t(y) - asec, n) for x, y, n in tags],
                  exhibits=[(0, 6, slug)], landscape=True)
        ae = str(ass.resolve()).replace(":", "\\:").replace("'", "\\'")
        fin = WORK / f"fin_{pull}.mp4"
        run(["ffmpeg", "-y", "-ss", str(off), "-t", str(bsec - asec),
             "-i", str(MEDIA / f"{pull}.mp4"),
             "-vf", "scale=854:480:force_original_aspect_ratio=decrease,"
                    f"pad=854:480:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p,subtitles='{ae}'",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", str(fin)])
        d = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "csv=p=0", str(fin)]).stdout)
        parts.append(fin)
        metas.append((srt, d))
        print(f"    [{pull}] {d:.0f}s", flush=True)
    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(OUT)])
    t0, blocks = 0.0, []
    for i, (txt, dd) in enumerate(metas, 1):
        def f(t):
            h, rem = divmod(int(t), 3600)
            m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d},000"
        blocks.append(f"{i}\n{f(t0)} --> {f(t0+dd)}\n{txt}\n")
        t0 += dd
    OUT.with_suffix(".srt").write_text("\n".join(blocks))
    print(f"[+] CONTENTION REEL v2 -> {OUT} ({OUT.stat().st_size/1e6:.1f} MB, {t0:.0f}s)")


if __name__ == "__main__":
    main()
