#!/usr/bin/env python3
"""THE CALLER: TAPE EDITION v2 - corrected beat list, full Apr 27 record."""
import subprocess, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cheyenne_pipeline import vertical_segment, find_font, wrap_text
FONT = find_font() or "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
WORK = ROOT / "renders" / "caller_tape_work"
OUT = ROOT / "renders" / "THE_CALLER_TAPE.mp4"
W, H = 1080, 1920
WHITE, GOLD, DIM, RED = "white", "0xFFD166", "0x8fa3b8", "0xFF6B6B"

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return r

def card(head, body, src, num="", dur=7.0, idx=1, total=5, color=GOLD):
    tag = f"k{idx}_{abs(hash(head)) % 9999}"
    (WORK / f"h{tag}.txt").write_text(wrap_text(head, 18))
    (WORK / f"n{tag}.txt").write_text(num)
    (WORK / f"b{tag}.txt").write_text(wrap_text(body, 29))
    (WORK / f"s{tag}.txt").write_text(src)
    def dt(tf, size, col, y, t0):
        return (f"drawtext=fontfile={FONT}:textfile={tf}:fontcolor={col}:fontsize={size}:"
                f"x=(w-text_w)/2:y={y}:alpha='clip((t-{t0})/0.6,0,1)':line_spacing=16")
    vf = (f"color=0x0d1117:size={W}x{H}:rate=30,format=yuv420p,"
          + dt(str(WORK / f"h{tag}.txt"), 74, WHITE, "h*0.14", 0.2)
          + "," + dt(str(WORK / f"n{tag}.txt"), 64, color, "h*0.38", 1.2)
          + "," + dt(str(WORK / f"b{tag}.txt"), 43, WHITE, "h*0.58", 0.9)
          + "," + dt(str(WORK / f"s{tag}.txt"), 28, DIM, "h*0.87", 0.4)
          + f",drawbox=x=0:y='ih-10':w='iw*{idx}/{total}':h=10:color=0x4da3ff@0.85:t=fill")
    out = WORK / f"card_{tag}.mp4"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", vf, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-c:a", "aac", "-b:a", "128k", str(out)])
    return out, dur

def tape(fname, trim, caption, label):
    raw = ROOT / "videos" / fname
    cut = WORK / f"cut_{abs(hash(fname)) % 9999}.mp4"
    a, b = trim
    run(["ffmpeg", "-y", "-ss", str(a), "-t", str(b - a), "-i", str(raw),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-c:a", "aac", "-b:a", "128k", str(cut)])
    p = vertical_segment(cut, caption, label, WORK, f"t{abs(hash(label)) % 9999}")
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)
    return p, d

if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir(parents=True)
parts, metas = [], []
T = 5
c, d = card("THE CALLER", "The actual tape. His voice, their gavels \u2014 every cut as it happened.", "City meeting videos \u00b7 Mar 9 & Apr 27, 2026", "REAL TAPE", 6, 1, T); parts += [c]; metas += [("THE CALLER \u2014 real tape edition", d)]
c, d = card("MARCH 9, 2026", "Four and a half hours in, the last speaker of the night is the Zoom caller. He testifies for three and a half minutes.", "Minutes 1071: 6:00 p.m. start \u00b7 archive 04:30", "10:30 PM", 6, 2, T); parts += [c]; metas += [("Mar 9, 10:30 p.m. \u2014 three and a half minutes in", d)]
p, d = tape("mar9_cut.mp4", (0, 105),
            "\u201cIf you vote yes tonight, you are passing a resolution of compliance based on materially false financial data\u2026\u201d \u2014 \u201cA point of order, sir.\u201d \u2014 \u201cThank you, Mr. Miller. Your time\u2019s up.\u201d",
            "The cut \u00b7 Mar 9, 2026 \u00b7 10:34 p.m.")
parts += [p]; metas += [("MAR 9 \u2014 \u201cbased on materially false financial data\u2026\u201d \u2192 \u201cpoint of order\u201d \u2192 \u201cThank you, Mr. Miller. Your time\u2019s up.\u201d [10:34 p.m.]", d)]
c, d = card("APRIL 27, 2026", "One night. He is recognized nine times. Nearly every turn ends in a point of order, an \u201cout of order,\u201d or a cut.", "Apr 27, 2026 \u00b7 archive 00:26\u201304:04", "9 TURNS", 7, 3, T, color=RED); parts += [c]; metas += [("Apr 27 \u2014 nine recognitions in one night", d)]
p, d = tape("apr27_first.mp4", (0, 112),
            "The mayor breaks in mid-testimony \u2014 \u201cMr. Miller, Mr. Miller, in an extreme drought\u2014\u201d \u2014 then: \u201cMr. Miller, your time\u2019s up. Thank you.\u201d",
            "First turn, interrupted \u00b7 Apr 27, 2026")
parts += [p]; metas += [("APR 27, turn one \u2014 mid-testimony interruption + \u201cyour time\u2019s up\u201d [02:18\u201302:20]", d)]
p, d = tape("apr27_hand.mp4", (0, 155),
            "\u201cI\u2019m sorry I missed Mr. Miller\u2019s hand raised when you went by public comment.\u201d \u2014 \u201cWe\u2019ve kind of moved on from that.\u201d \u2014 Miller: \u201cThat is viewpoint discrimination.\u201d \u2014 \u201cI apologize. We missed you. I really do.\u201d \u2014 then a point of order.",
            "The bypassed hand \u00b7 Apr 27, 2026")
parts += [p]; metas += [("APR 27 \u2014 THE BYPASSED HAND: clerk catches the skipped hand \u2192 mayor \u201cmoved on\u201d \u2192 Miller: \u201cviewpoint discrimination\u201d \u2192 apology \u2192 point of order anyway [02:44\u201302:46]", d)]
p, d = tape("apr27_1301.mp4", (0, 80),
            "Miller: \u201cI\u2019m speaking now because the procedural integrity of this entire\u2014\u201d \u2014 \u201cI find you out of order, Mr. Miller.\u201d \u2014 \u201cPoint of order, Mr. Mayor. Why does this happen?\u201d",
            "Ruled out of order mid-sentence \u00b7 Apr 27, 2026")
parts += [p]; metas += [("APR 27 \u2014 \u201cI find you out of order, Mr. Miller\u201d mid-sentence [03:01\u201303:02]", d)]
p, d = tape("apr27_pileon.mp4", (5, 140),
            "\u201cMy whole council is saying point of order. Mr. Miller, you\u2019re not on the postponement.\u201d \u2014 Miller: \u201cThat was classic. You cannot point of order a physical reality.\u201d \u2014 \u201c\u2026a motion and a second to call you out of order.\u201d",
            "The pile-on \u00b7 Apr 27, 2026")
parts += [p]; metas += [("APR 27 \u2014 the pile-on: \u201cmy whole council is saying point of order\u201d / Miller: \u201cyou cannot point of order a physical reality\u201d / \u201cmotion and a second to call you out of order\u201d [03:10\u201303:12]", d)]
p, d = tape("apr27_nine.mp4", (0, 105),
            "\u201cPoint of order. Mr. Mayor.\u201d \u2014 \u201cMr. Miller, again \u2014 I\u2019ve got nine people yelling point of order at me. You\u2019re not following our procedures.\u201d",
            "Nine people yelling point of order \u00b7 Apr 27, 2026")
parts += [p]; metas += [("APR 27 \u2014 \u201cI\u2019ve got nine people yelling point of order at me\u201d [03:41\u201303:42]", d)]
c, d = card("THE SAME NIGHT", "11:48 p.m. The meeting is ending. He asks to be heard one more time.", "Mar 9, 2026 \u00b7 archive 05:48", "MAR 9", 6, 4, T); parts += [c]; metas += [("Mar 9, 11:48 p.m. \u2014 one more time", d)]
p, d = tape("mar9_return.mp4", (3, 110),
            "\u201cEarlier this evening, you used a point of order to cut my microphone \u2014 the second I began exposing a mathematically false financial report.\u201d",
            "Miller, the same night \u00b7 Mar 9, 2026")
parts += [p]; metas += [("MAR 9, close \u2014 \u201cyou used a point of order to cut my microphone the second I began exposing a mathematically false financial report\u201d [11:48 p.m.]", d)]
c, d = card("THE COUNT", "The clerk\u2019s minutes that night record four interruption events. The tape records more. Every cut microphone is an exhibit. Every bypassed hand is an exhibit.", "Minutes: clips 1071, 1093 \u00b7 Tape + captions: city YouTube archive", "", 7, 5, T); parts += [c]; metas += [("The minutes count four. The tape counts more.", d)]
lst = WORK / "list.txt"
lst.write_text("".join(f"file '{p_.resolve().as_posix()}'\n" for p_ in parts))
run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(OUT)])
t0, blocks = 0.0, []
for i, (txt, dd) in enumerate(metas, 1):
    def f(t):
        h, rem = divmod(int(t), 3600); m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d},000"
    blocks.append(f"{i}\n{f(t0)} --> {f(t0+dd)}\n{txt}\n"); t0 += dd
OUT.with_suffix(".srt").write_text("\n".join(blocks))
print(f"[+] THE CALLER TAPE v2 -> {OUT} ({OUT.stat().st_size/1e6:.1f} MB, {t0:.0f}s)")
