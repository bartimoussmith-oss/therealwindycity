#!/usr/bin/env python3
"""
stories.py — FIVE stories, told like THE RECORD SPEAKS (vertical 1080x1920)
============================================================================
2 with REAL TAPE (city YouTube, staged in videos/):  48 HOURS / THE $74M LIST
3 card-driven from the proven record:                THE TWO TIES / THE 214 / ONE NIGHT IN APRIL
Every card sourced on screen. Nothing unverified (canon §35-§36 rules).
Run:  python3 stories.py          -> renders/S1..S5 + SRTs + POST_ALL_FIVE.txt
"""
import subprocess, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cheyenne_pipeline import vertical_segment, find_font, wrap_text  # noqa: E402

FONT = find_font() or "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
W, H = 1080, 1920
WHITE, ACCENT, DIM = "white", "0xFFD166", "0x8fa3b8"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-500:])
    return r


def card(head, body, src, num="", dur=7.0, idx=1, total=6, color=WHITE):
    tag = f"c{idx}_{abs(hash(head)) % 9999}"
    work = WORK
    hf = work / f"h{tag}.txt"; hf.write_text(wrap_text(head, 18))
    bf = work / f"b{tag}.txt"; bf.write_text(wrap_text(body, 30) if body else "")
    nf = work / f"n{tag}.txt"; nf.write_text(num)
    sf = work / f"s{tag}.txt"; sf.write_text(src)

    def dt(tf, size, col, y, t0):
        return (f"drawtext=fontfile={FONT}:textfile={tf}:fontcolor={col}:fontsize={size}:"
                f"x=(w-text_w)/2:y={y}:alpha='clip((t-{t0})/0.6,0,1)':line_spacing=18")
    vf = (f"color=0x0d1117:size={W}x{H}:rate=30,format=yuv420p,"
          + dt(hf, 76, color, "h*0.16", 0.2)
          + ("," + dt(nf, 92, ACCENT, "h*0.42", 1.3) if num else "")
          + ("," + dt(bf, 44, WHITE, "h*0.60", 0.9) if body else "")
          + "," + dt(sf, 29, DIM, "h*0.86", 0.4)
          + f",drawbox=x=0:y='ih-10':w='iw*{idx}/{total}':h=10:color=0x4da3ff@0.85:t=fill")
    out = work / f"card_{tag}.mp4"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", vf,
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(dur),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-c:a", "aac", "-b:a", "128k", str(out)])
    return out, dur


def tape(seg_file, trim_a, trim_b, caption, label):
    raw = ROOT / seg_file
    cut = WORK / f"cut_{abs(hash(seg_file)) % 9999}.mp4"
    run(["ffmpeg", "-y", "-ss", str(trim_a), "-t", str(trim_b - trim_a), "-i", str(raw),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-c:a", "aac", "-b:a", "128k", str(cut)])
    p = vertical_segment(cut, caption, label, WORK, f"t{abs(hash(label)) % 9999}")
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout)
    return p, d


def render(name, pieces, metas):
    WORK.mkdir(parents=True, exist_ok=True)
    lst = WORK / f"list_{name}.txt"
    lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in pieces))
    out = ROOT / "renders" / f"{name}.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    # SRT
    t0, blocks = 0.0, []
    for i, (txt, d) in enumerate(metas, 1):
        def f(t):
            h, rem = divmod(int(t), 3600); m, s = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s:02d},000"
        blocks.append(f"{i}\n{f(t0)} --> {f(t0+d)}\n{txt}\n")
        t0 += d
    out.with_suffix(".srt").write_text("\n".join(blocks))
    print(f"[+] {out.name}  ({out.stat().st_size/1e6:.1f} MB, {t0:.0f}s)")


WORK = ROOT / "renders" / "stories_work"
if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir(parents=True)

# ---------------- S1: 48 HOURS (real tape) ----------------
print("[*] Story 1: 48 HOURS")
pieces, metas = [], []
c, d = card("48 HOURS", "The city adopts a plan admitting what's missing. Two days later, it funds everything else.", "Consolidated Plan 2025-2027 (Res. 6507) + COTW minutes", "JAN 2026", 7, 1, 6); pieces += [c]; metas += [("48 HOURS - Jan 2026", d)]
c, d = card("JAN 12, 2026", "The council's own Consolidated Plan, adopted by resolution: \u201cThere are few resources available for persons with chronic mental illness.\u201d", "Res. #6507 \u00b7 Consolidated Plan 2025\u20132027", "\u201cFEW RESOURCES\u201d", 8, 2, 6); pieces += [c]; metas += [("JAN 12: few resources (Res. 6507)", d)]
p, d = tape("videos/nemecek_quote.mp4", 20, 100,
            "\u201cIt\u2019s lipstick on a pig\u2026 we\u2019ve been putting lipstick on it for five decades. And we\u2019re two decades past a major renovation.\u201d",
            "Vicki Nemecek \u00b7 Public Works Director \u00b7 Jan 14, 2026")
pieces += [p]; metas += [(f"Nemecek, on tape: \u201clipstick on a pig\u2026 five decades\u2026 two decades past a major renovation\u201d [COTW Jan 14, 2026, 00:47]", d)]
c, d = card("48 HOURS LATER", "The committee votes 8\u20131 to put a $22,000,000 Municipal Building remodel on the ballot.", "Committee of the Whole \u00b7 Jan 14, 2026", "8\u20131", 7, 4, 6); pieces += [c]; metas += [("48 hours later: 8-1 for the $22M remodel", d)]
c, d = card("AND FOR THE MISSING PART?", "Eleven projects. $74.25M. Not one dollar for treatment capacity.", "Sixth-penny ballot \u00b7 Aug 18, 2026 primary", "$0", 7, 5, 6, color="0xFF6B6B"); pieces += [c]; metas += [("Ballot: $0 for treatment", d)]
c, d = card("IT'S THE RECORD", "Their plan. Their words. Their votes. Verify it yourself.", "cheyenne.granicus.com \u00b7 cheyennecity.org", "", 6, 6, 6); pieces += [c]; metas += [("Verify: cheyenne.granicus.com", d)]
render("S1_48_HOURS", pieces, metas)

# ---------------- S2: THE $74 MILLION LIST (real tape) ----------------
print("[*] Story 2: THE $74 MILLION LIST")
pieces, metas = [], []
c, d = card("THE $74 MILLION LIST", "How a city builds a ballot. One January night, four amendments \u2014 all dead.", "Committee of the Whole \u00b7 Jan 14, 2026", "11 PROJECTS", 7, 1, 6); pieces += [c]; metas += [("The $74M list - COTW Jan 14, 2026", d)]
p, d = tape("videos/moody_swap.mp4", 5, 70,
            "\u201cIncrease the city street maintenance project from 9 million to 20 million \u2014 and number 10, you would remove $22 million.\u201d",
            "Chair Segrave, on Moody\u2019s amendment \u00b7 Jan 14, 2026")
pieces += [p]; metas += [(f"Segrave on tape: \u201c\u2026number 10, you would remove $22 million\u2026\u201d [COTW Jan 14, 2026, 00:28]", d)]
c, d = card("THE AMENDMENT WAR", "Swap the building for a fire station: 0\u20139. Half-fund it: 1\u20138. Kill street maintenance: 1\u20138. Swap downtown for Reed Ave: 4\u20135. The list survived it all.", "COTW minutes \u00b7 Jan 14, 2026", "0 FOR 4", 9, 3, 6); pieces += [c]; metas += [("Amendments: 0-9, 1-8, 1-8, 4-5 - list carried", d)]
c, d = card("WHAT MADE THE BALLOT", "$22M Municipal Building \u00b7 $10.47M Johnson Pool \u00b7 $4M downtown (two garage elevators) \u00b7 $9M streets \u00b7 $12M Fire Station #2 \u00b7 $3.7M police digital\u2026", "Sixth-penny ballot propositions", "$74.25M", 9, 4, 6); pieces += [c]; metas += [("The ballot itemization", d)]
c, d = card("WHAT DIDN'T", "Treatment capacity. Behavioral health. Crisis beds. The thing their own plan said was missing.", "Consolidated Plan 2025\u20132027 vs. ballot", "$0", 7, 5, 6, color="0xFF6B6B"); pieces += [c]; metas += [("$0 for the missing piece", d)]
c, d = card("AUG 18, 2026", "The voters were handed this list \u2014 and nothing else to choose from.", "Primary election \u00b7 Laramie County", "ONE BALLOT", 6, 6, 6); pieces += [c]; metas += [("Aug 18, 2026: the vote", d)]
render("S2_THE_74M_LIST", pieces, metas)

# ---------------- S3: THE TWO TIES (cards) ----------------
print("[*] Story 3: THE TWO TIES")
pieces, metas = [], []
B = [("ONE NIGHT. TWO TIES.", "March 9, 2026. The pocket-annexation war comes to a head \u2014 and the mayor's vote decides who wins.", "Council minutes \u00b7 Mar 9, 2026", "MAR 9", 7),
     ("THE ROOM", "47 speakers. Recesses at 9:00 and 11:05 p.m. Farmers, neighbors, a former legislator \u2014 against the annexation.", "Mar 9, 2026 minutes \u00b7 speaker roster", "47", 8),
     ("FIRST TIE", "Moody's substitute amendment to stop the pocket annexation: 5\u20135. Failed. The mayor voted no.", "Mar 9, 2026 roll call", "5\u20135", 8),
     ("SECOND TIE", "Aldrich's motion to carve out the farm parcels: 5\u20135. Failed. Same blocs. Same night.", "Mar 9, 2026 roll call", "5\u20135", 8),
     ("WHAT SURVIVED", "White's amendment \u2014 unanimous \u2014 set the real deadline: November 9. The only thing everyone agreed on.", "Mar 9, 2026 minutes", "UNANIMOUS", 7),
     ("THE ARITHMETIC", "Same five votes, both times, with the mayor. That's not a malfunction. That's the machine.", "Roll-call record \u00b7 Mar 9, 2026", "", 7)]
for i, (h, b, s, n, dd) in enumerate(B, 1):
    c, d = card(h, b, s, n, dd, i, len(B)); pieces += [c]; metas += [(h, d)]
render("S3_THE_TWO_TIES", pieces, metas)

# ---------------- S4: THE 214 (cards) ----------------
print("[*] Story 4: THE 214")
pieces, metas = [], []
B = [("THE 214", "Ten years of the published arrest blotter. 19,795 bookings. 9,268 people. This is what the data says.", "WTE arrest blotter \u00b7 Dec 2016\u2013Feb 2026", "10 YEARS", 7),
     ("MOST PEOPLE, ONCE", "65% of everyone arrested that decade was booked exactly once \u2014 and never again.", "Blotter tally", "65%", 7),
     ("THE CHRONIC CORE", "214 people. 3,191 bookings \u2014 16% of the entire decade \u2014 cycling back every 4 to 5 months.", "Blotter tally", "214", 8),
     ("THE PARK MYTH", "Arrests at any city park, in ten years: 16. MLK Park: exactly one \u2014 a 2022 warrant. Enforcement was never the lever.", "Blotter tally \u00b7 location field", "16", 8),
     ("THE WAVE", "Drug bookings: 123 in 2017 \u2192 667 in 2025. Fentanyl didn't appear until 2021.", "Blotter tally \u00b7 by year", "5.4\u00d7", 7),
     ("THE ANSWER THEY FUNDED", "$22M building remodel. $10.47M pool. $1M HVAC. $0 for treatment \u2014 for the 214 jail can't fix.", "Sixth-penny ballot \u00b7 Aug 18, 2026", "$0", 8)]
for i, (h, b, s, n, dd) in enumerate(B, 1):
    col = "0xFF6B6B" if h == "THE ANSWER THEY FUNDED" else WHITE
    c, d = card(h, b, s, n, dd, i, len(B), color=col); pieces += [c]; metas += [(h, d)]
render("S4_THE_214", pieces, metas)

# ---------------- S5: ONE NIGHT IN APRIL (cards) ----------------
print("[*] Story 5: ONE NIGHT IN APRIL")
pieces, metas = [], []
B = [("ONE NIGHT IN APRIL", "How you annex and rezone 1,259 acres before anyone can object.", "Council record \u00b7 April 2026", "APR 13", 7),
     ("APRIL 13", "Three instruments introduced the same night: annexation, A-G zoning, and A-G\u2192BP \u2014 purpose: \u201cto zone land BP for development.\u201d", "Council agenda \u00b7 Apr 13, 2026", "3 AT ONCE", 8),
     ("APRIL 27", "The war night: 35+ speakers, recess at 8:55, four hours long. The annexation is postponed.", "Council minutes \u00b7 Apr 27, 2026", "35+ VOICES", 8),
     ("ON CONSENT", "But that same night, the Future Land Use Map and the Urban Service Boundary move \u2014 on the consent agenda.", "Apr 27, 2026 \u00b7 [CA] items", "UNNOTICED", 8),
     ("THE FINDING", "The ordinance says \u201cpersons residing in the area.\u201d The staff's proof: \u201cfuture occupants.\u201d", "Ordinance text vs. staff report", "\u201cFUTURE\u201d", 8),
     ("THE NECK", "Contiguity by the staff's own figure: 5.26%. The approval recommendation page: 84 views, zero comments.", "PUDC-26-38 packet metrics", "5.26%", 7),
     ("SEPTEMBER 14", "It all comes back. Bring the parcel numbers.", "Council calendar \u00b7 return hearing", "THE RETURN", 6)]
for i, (h, b, s, n, dd) in enumerate(B, 1):
    c, d = card(h, b, s, n, dd, i, len(B)); pieces += [c]; metas += [(h, d)]
render("S5_ONE_NIGHT_IN_APRIL", pieces, metas)

print("\n[+] ALL FIVE RENDERED -> pipeline/renders/")
