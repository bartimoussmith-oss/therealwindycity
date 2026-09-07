#!/usr/bin/env python3
"""
montage.py — "THE RECORD SPEAKS" vertical montage (1080x1920)
================================================================
Kinetic-typography montage of PROVEN contradictions from the city's own record.
Every card carries its source on screen. No unverified quotes (red-team rules:
redteam-2026-08-27-cox-corpus.md / -ada-timebomb.md / canon §35-§36 quarantine).

Re-run any time:  python3 montage.py            -> renders/THE_RECORD_SPEAKS.mp4
Edit the beats at the bottom to update facts. All text via textfile= (no escaping bugs).
"""
import subprocess, shutil, time, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "renders" / "montage_work"
OUT = ROOT / "renders" / "THE_RECORD_SPEAKS.mp4"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 1080, 1920
WHITE, ACCENT, DIM, RED = "white", "0xFFD166", "0x8fa3b8", "0xFF6B6B"


def wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur: lines.append(cur)
    return "\n".join(lines)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-600:])
    return r


def card(beat, idx, total):
    """Render one 1080x1920 card with staged reveals + progress bar."""
    D = beat.get("dur", 6.0)
    tag = f"{idx:02d}"
    head = WORK / f"h{tag}.txt"; head.write_text(wrap(beat["head"], 18))
    body = WORK / f"b{tag}.txt"; body.write_text(wrap(beat.get("body", ""), 30))
    numf = WORK / f"n{tag}.txt"; numf.write_text(beat.get("num", ""))
    srcf = WORK / f"s{tag}.txt"; srcf.write_text(beat["src"])

    def dt(tf, size, color, y, t0, style=""):
        a = f"alpha='clip((t-{t0})/0.6,0,1)'"
        return (f"drawtext=fontfile={FONT}:textfile={tf}:fontcolor={color}:fontsize={size}:"
                f"x=(w-text_w)/2:y={y}:{a}:line_spacing=18{':' + style if style else ''}")

    vf = (
        f"color=0x0d1117:size={W}x{H}:rate=30,format=yuv420p,"
        + dt(head, 78, beat.get("color", WHITE), "h*0.16", 0.2)
        + ("," + dt(numf, 92, ACCENT, "h*0.44", 1.4) if beat.get("num") else "")
        + ("," + dt(body, 46, WHITE, "h*0.60", 0.9) if beat.get("body") else "")
        + "," + dt(srcf, 30, DIM, "h*0.86", 0.4, "box=1:boxcolor=0x0d1117@0.0")
        + f",drawbox=x=0:y='ih-10':w='iw*{idx}/{total}':h=10:color=0x4da3ff@0.85:t=fill"
    )
    out = WORK / f"card_{tag}.mp4"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", vf,
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-t", str(D), "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-c:a", "aac", "-b:a", "128k", str(out)])
    print(f"    [{idx}/{total}] {beat['head'][:46]}")
    return out, D


BEATS = [
    {"head": "THEY SAID IT THEMSELVES", "body": "Every word in this video is from the City of Cheyenne's own record. Dates and documents on every card.", "src": "Sources: city minutes, resolutions & ballot — on file", "dur": 6},
    {"head": "JAN 12, 2026", "num": "\u201cFew resources\u201d", "body": "The council adopts its own Consolidated Plan: \u201cThere are few resources available for persons with chronic mental illness.\u201d", "src": "Res. #6507, Consolidated Plan 2025\u20132027 \u00b7 Jan 12, 2026", "dur": 7},
    {"head": "48 HOURS LATER", "num": "$22,000,000", "body": "Committee votes 8\u20131 to fund a full Municipal Building remodel on the sixth-penny ballot.", "src": "Committee of the Whole minutes \u00b7 Jan 14, 2026", "dur": 7},
    {"head": "THE BALLOT, itemized", "num": "$0 for treatment", "body": "$22M building remodel \u00b7 $10.47M pool \u00b7 $4M downtown (two garage elevators) \u00b7 $1M health-dept HVAC.\nEleven projects. Not one dollar for the thing their own plan said was missing.", "src": "Sixth-penny ballot propositions \u00b7 Aug 18, 2026 primary", "dur": 8},
    {"head": "THEIR OWN WORDS", "num": "\u201cLipstick on a pig\u201d", "body": "\u201cWe\u2019ve got a pig, and we\u2019ve been putting lipstick on it for five decades. And we\u2019re two decades past a major renovation.\u201d", "src": "Vicki Nemecek, Public Works Director \u00b7 COTW Jan 14, 2026", "dur": 8},
    {"head": "MEANWHILE, THE NUMBERS", "num": "214 people", "body": "3,191 bookings \u2014 16% of an entire decade \u2014 cycling through jail every 4\u20135 months. Jail can\u2019t treat what they have.", "src": "Published WTE arrest blotter, Dec 2016\u2013Feb 2026 (19,795 bookings)", "dur": 8},
    {"head": "APR 13, 2026", "num": "ONE NIGHT", "body": "1,259 acres annexed, zoned AG, and re-zoned BP \u2014 \u201cto zone land BP for development\u201d \u2014 all three introduced the same night.", "src": "City Council agenda & minutes \u00b7 Apr 13, 2026", "dur": 8},
    {"head": "APR 27, 2026", "num": "ON CONSENT", "body": "The annexation is postponed after a 4-hour war \u2014 but the Future Land Use + Urban Service Boundary change moves through on consent.", "src": "Council minutes \u00b7 Apr 27, 2026 (35+ speakers)", "dur": 8},
    {"head": "THE FINDING", "num": "\u201cFuture occupants\u201d", "body": "The ordinance says \u201cpersons residing in the area.\u201d The staff analysis supports it with \u201cfuture occupants.\u201d A finding proved by people who aren\u2019t there.", "src": "Annexation ordinance vs. staff report \u00b7 spring 2026", "dur": 8},
    {"head": "5.26%", "num": "A NECK", "body": "The staff report\u2019s own contiguity figure for the annexation. The approval recommendation page: 84 views, zero comments.", "src": "PUDC-26-38 staff report & packet metrics \u00b7 Apr 2026", "dur": 7},
    {"head": "MAR 9, 2026", "num": "5\u20135. TWICE.", "body": "The mayor\u2019s vote produced two deadlocked ties in one night \u2014 both times siding with the pro-annexation bloc. The reform amendments died.", "src": "Council minutes \u00b7 Mar 9, 2026 (47 speakers, past 11 p.m.)", "dur": 8},
    {"head": "THIS ISN\u2019T A CONSPIRACY", "num": "IT\u2019S THE RECORD", "body": "Every quote, vote, and dollar in this video is public record. Verify it yourself \u2014 then ask the city the same question.", "src": "cheyenne.granicus.com \u00b7 cheyennecity.org \u00b7 Laramie County election results", "dur": 8},
]


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    parts = []
    print("[*] Rendering cards ...")
    total = len(BEATS)
    for i, b in enumerate(BEATS, 1):
        parts.append(card(b, i, total)[0])
    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts))
    OUT.parent.mkdir(exist_ok=True)
    print("[*] Stitching ...")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(OUT)])
    # SRT
    t0, blocks = 0.0, []
    for i, b in enumerate(BEATS, 1):
        d = b.get("dur", 6.0)
        def f(t):
            h, rem = divmod(int(t), 3600); m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d},000"
        text = (b["head"] + (" \u2014 " + b["num"].strip("\u201c\u201d") if b.get("num") else "")
                + f" [{b['src']}]")
        blocks.append(f"{i}\n{f(t0)} --> {f(t0+d)}\n{text}\n")
        t0 += d
    OUT.with_suffix(".srt").write_text("\n".join(blocks))
    print(f"[+] MONTAGE -> {OUT} ({OUT.stat().st_size/1e6:.1f} MB, {t0:.0f}s, 1080x1920)")
    print(f"[+] Captions -> {OUT.with_suffix('.srt').name}")


if __name__ == "__main__":
    main()
