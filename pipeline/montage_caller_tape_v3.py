#!/usr/bin/env python3
"""THE CALLER: TAPE EDITION v3 — director's cut.

v2's seven tape beats re-cut from fresh segment pulls, PLUS four
contradiction exhibits (S1-S4) cut into the same film, all with burned-in
graphics: karaoke word captions, speaker name tags, exhibit banners.

  S1 "NEVER ADMITTED" .... Cox maps: applicant admits (00:35) -> council
     postpones to Sept (02:41) -> Miller cites it -> "not accurate" (03:06)
     -> "never admitted... incorrect sir" (04:00). All Apr 27, one tape.
  S2 "CAN'T SAY DATA CENTERS" .. Apr 20 committee pitches data centers,
     gags citizens to "the annexation", Miller charges viewpoint
     discrimination on the record -> dismissed May 26 ("lost the council").
  S3 "LEGALLY MEANINGLESS" .... Mar 9 Food Freedom warning -> notices
     dismissed -> Aug 21 the city delivers it ("four or five of us asked").
  S4 "TOTALLY OFF BASE" ....... Jul 21 citizen calls the FCI contract
     premature (staff: no GMP yet) -> Miller relays it Jul 27 -> Wolf:
     "totally off base".

Needs: cut_media/*.mp4 segment pulls (see pull_list.txt — yt-dlp
--download-sections, android client) + caption VTTs (miller_captions for the
20 Miller videos, cut_captions for the rest). Renders
renders/THE_CALLER_TAPE.mp4 (+.srt), same filename as v2 so the app, reel
view, and post kits keep working. Run: python3 montage_caller_tape_v3.py
"""
import subprocess
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cheyenne_pipeline import _vtext_files, VF_BLUR, find_font, wrap_text  # noqa: E402
from cut_graphics import build_ass  # noqa: E402

FONT = find_font() or "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
WORK = ROOT / "renders" / "caller_tape_v3_work"
MEDIA = ROOT / "cut_media"
CAP_MILLER = Path("/home/user/miller/pipeline/miller_captions")
CAP_CUT = ROOT / "cut_captions"
OUT = ROOT / "renders" / "THE_CALLER_TAPE.mp4"
W, H = 1080, 1920
WHITE, GOLD, DIM, RED = "white", "0xFFD166", "0x8fa3b8", "0xFF6B6B"


def t(hms: str) -> float:
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


# pull file -> (video id, pull start in tape seconds, caption dir)
PULLS = {
    "mar9_cut_src": ("19tQtLA8klo", t("04:29:30"), CAP_MILLER),
    "mar9_return_src": ("19tQtLA8klo", t("05:47:00"), CAP_MILLER),
    "s3_demand": ("19tQtLA8klo", t("02:40:45"), CAP_MILLER),
    "apr27_first_src": ("y9vnXtjZpR0", t("02:17:00"), CAP_MILLER),
    "apr27_hand_src": ("y9vnXtjZpR0", t("02:42:30"), CAP_MILLER),
    "apr27_1301_src": ("y9vnXtjZpR0", t("03:00:00"), CAP_MILLER),
    "apr27_pileon_src": ("y9vnXtjZpR0", t("03:09:00"), CAP_MILLER),
    "apr27_nine_src": ("y9vnXtjZpR0", t("03:40:00"), CAP_MILLER),
    "s1_admit": ("y9vnXtjZpR0", t("00:34:30"), CAP_MILLER),
    "s1_cites": ("y9vnXtjZpR0", t("02:19:20"), CAP_MILLER),
    "s1_postpone": ("y9vnXtjZpR0", t("02:40:30"), CAP_MILLER),
    "s1_denial1": ("y9vnXtjZpR0", t("03:06:15"), CAP_MILLER),
    "s1_denial2": ("y9vnXtjZpR0", t("03:59:50"), CAP_MILLER),
    "s2_pitch": ("t17ft4xMMx4", t("01:16:45"), CAP_MILLER),
    "s2_gag": ("t17ft4xMMx4", t("01:28:30"), CAP_MILLER),
    "s2_charge": ("t17ft4xMMx4", t("02:03:50"), CAP_MILLER),
    "s2_dismiss": ("bGt1XMfaTTw", t("05:00:10"), CAP_MILLER),
    "s3_meaningless": ("RjSGlhh4q9s", t("05:27:15"), CAP_MILLER),
    "s3_delivered": ("kAPVTM1oJTo", t("00:56:50"), CAP_CUT),
    "s4_committee": ("Q3CI--6YUDY", t("00:46:50"), CAP_CUT),
    "s4_relay": ("S49bb5GfUro", t("00:51:00"), CAP_MILLER),
    "s4_offbase": ("S49bb5GfUro", t("00:56:10"), CAP_MILLER),
}

MILLER = "CHARLES MILLER \u2014 Zoom caller"
DAIS = "THE DAIS"


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


def seg(pull, a, b, label, tags, exhibits, srt):
    """Cut tape range [a,b] (HH:MM:SS) from a pull, dress it, burn graphics."""
    vid, pstart, capdir = PULLS[pull]
    asec, bsec = t(a), t(b)
    off = asec - pstart
    assert off >= 0 and bsec - pstart >= 0, f"{pull} range outside pull"
    raw = MEDIA / f"{pull}.mp4"
    assert raw.exists(), f"missing pull {raw} (see pull_list.txt)"
    pdur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "csv=p=0", str(raw)]).stdout)
    assert bsec - pstart <= pdur + 0.5, f"{pull} too short for {a}-{b}"
    vtt = capdir / f"{vid}.en.vtt"
    tag = f"{pull}_{a.replace(':', '')}"
    ass = WORK / f"{tag}.ass"
    build_ass(vtt, asec, bsec, ass,
              tags=[(x - asec, y - asec, n) for x, y, n in tags],
              exhibits=[(x - asec, y - asec, n) for x, y, n in exhibits])
    # single pass: trim -> vertical blur -> source label -> burn ASS
    _, srcf = _vtext_files(WORK, tag, "", label)
    ass_esc = str(ass.resolve()).replace(":", "\\:").replace("'", "\\'")
    vf = (f"{VF_BLUR},"
          f"drawtext=fontfile={FONT}:textfile={srcf}:fontcolor=white@0.85:fontsize=34:"
          f"x=(w-text_w)/2:y=h*0.92,"
          f"fps=30,format=yuv420p,subtitles='{ass_esc}'[vout]")
    fin = WORK / f"fin_{tag}.mp4"
    run(["ffmpeg", "-y", "-ss", str(off), "-t", str(bsec - asec), "-i", str(raw),
         "-filter_complex", vf, "-map", "[vout]", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "128k", str(fin)])
    print(f"    [{tag}] {bsec - asec:.0f}s", flush=True)
    d = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                   "-of", "csv=p=0", str(fin)]).stdout)
    return fin, d, srt


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    RENDER = ROOT / "renders"
    RENDER.mkdir(parents=True, exist_ok=True)
    parts, metas = [], []
    T = 9  # progress-bar chapters

    def add_card(*a, **k):
        srt = k.pop("srt", a[0])
        c, d = card(*a, **k)
        parts.append(c)
        metas.append((srt, d))

    def add_seg(*a):
        p, d, s = seg(*a)
        parts.append(p)
        metas.append((s, d))

    # ---- v2 film, re-cut -------------------------------------------------
    add_card("THE CALLER", "The actual tape. His voice, their gavels \u2014 every cut as it happened. Now with burned-in captions, name tags, and four new contradiction exhibits.", "City meeting videos \u00b7 Mar 9 & Apr 27, 2026", "REAL TAPE", 7, 1, T, srt="THE CALLER \u2014 director's cut")
    add_card("MARCH 9, 2026", "Four and a half hours in, the last speaker of the night is the Zoom caller. He testifies for three and a half minutes.", "Minutes 1071: 6:00 p.m. start \u00b7 archive 04:30", "10:30 PM", 6, 2, T, srt="Mar 9, 10:30 p.m. \u2014 three and a half minutes in")
    add_seg("mar9_cut_src", "04:32:56", "04:34:25", "The cut \u00b7 Mar 9, 2026 \u00b7 10:34 p.m.",
            [(t("04:32:56"), t("04:34:08"), MILLER), (t("04:34:08"), t("04:34:25"), DAIS)],
            [(t("04:34:05"), t("04:34:25"), "CUT MID-SENTENCE \u00b7 10:34 PM")],
            "MAR 9 \u2014 \u201cmaterially false financial data\u2026\u201d \u2192 \u201cpoint of order\u201d \u2192 \u201cYour time\u2019s up\u201d [10:34 p.m.]")
    add_card("APRIL 27, 2026", "One night. He is recognized nine times. Nearly every turn ends in a point of order, an \u201cout of order,\u201d or a cut.", "Apr 27, 2026 \u00b7 archive 00:26\u201304:04", "9 TURNS", 7, 3, T, color=RED, srt="Apr 27 \u2014 nine recognitions in one night")
    add_seg("apr27_first_src", "02:18:40", "02:20:25", "First turn, interrupted \u00b7 Apr 27, 2026",
            [(t("02:18:40"), t("02:18:47"), MILLER), (t("02:18:47"), t("02:19:00"), DAIS), (t("02:19:00"), t("02:20:15"), MILLER), (t("02:20:15"), t("02:20:25"), DAIS)], [],
            "APR 27, turn one \u2014 mid-testimony interruption + \u201cyour time\u2019s up\u201d [08:19 p.m.]")
    add_seg("apr27_hand_src", "02:44:20", "02:46:00", "The bypassed hand \u00b7 Apr 27, 2026",
            [(t("02:44:20"), t("02:44:29"), "CITY CLERK"), (t("02:44:29"), t("02:44:50"), DAIS), (t("02:44:50"), t("02:45:30"), MILLER), (t("02:45:30"), t("02:46:00"), DAIS)], [],
            "APR 27 \u2014 THE BYPASSED HAND: skipped hand \u2192 \u201cmoved on\u201d \u2192 \u201cviewpoint discrimination\u201d \u2192 apology \u2192 point of order anyway [08:44 p.m.]")
    add_seg("apr27_1301_src", "03:01:20", "03:02:15", "Ruled out of order mid-sentence \u00b7 Apr 27, 2026",
            [(t("03:01:20"), t("03:01:46"), MILLER), (t("03:01:46"), t("03:02:15"), DAIS)], [],
            "APR 27 \u2014 \u201cI find you out of order, Mr. Miller\u201d mid-sentence [09:01 p.m.]")
    add_seg("apr27_pileon_src", "03:10:10", "03:12:10", "The pile-on \u00b7 Apr 27, 2026",
            [(t("03:10:10"), t("03:10:30"), DAIS), (t("03:10:30"), t("03:11:50"), MILLER), (t("03:11:50"), t("03:12:10"), DAIS)], [],
            "APR 27 \u2014 the pile-on: \u201cnot on the postponement\u201d / \u201cyou cannot point of order a physical reality\u201d / \u201cmotion and a second to call you out of order\u201d [09:10 p.m.]")
    add_seg("apr27_nine_src", "03:41:50", "03:43:10", "Nine people yelling point of order \u00b7 Apr 27, 2026",
            [(t("03:41:50"), t("03:43:10"), DAIS)], [],
            "APR 27 \u2014 \u201cI\u2019ve got nine people yelling point of order at me\u201d [09:42 p.m.]")
    add_card("THE SAME NIGHT", "11:48 p.m. The meeting is ending. He asks to be heard one more time.", "Mar 9, 2026 \u00b7 archive 05:48", "MAR 9", 6, 4, T, srt="Mar 9, 11:48 p.m. \u2014 one more time")
    add_seg("mar9_return_src", "05:47:52", "05:49:50", "Miller, the same night \u00b7 Mar 9, 2026",
            [(t("05:47:52"), t("05:49:50"), MILLER)], [],
            "MAR 9, close \u2014 \u201cyou used a point of order to cut my microphone the second I began exposing a mathematically false financial report\u201d [11:48 p.m.]")
    add_card("THE COUNT", "The clerk\u2019s minutes that night record four interruption events. The tape records more. Every cut microphone is an exhibit. Every bypassed hand is an exhibit.", "Minutes: clips 1071, 1093 \u00b7 Tape + captions: city YouTube archive", "", 7, 5, T, srt="The minutes count four. The tape counts more.")

    # ---- NEW: the contradictions ----------------------------------------
    add_card("THE CONTRADICTIONS", "Four times they told him he was wrong \u2014 on the live mic. Four times the record itself disagreed. Claim, denial, proof.", "City meeting videos + captions \u00b7 all dates on screen", "4 EXHIBITS", 8, 6, T, color=RED, srt="THE CONTRADICTIONS \u2014 four exhibits")
    # S1
    add_card("EXHIBIT S1", "\u201cNEVER ADMITTED.\u201d The Cox Ranch map: the applicant admits the surveys aren\u2019t done \u2014 then the dais denies it twice, same night.", "Apr 27, 2026 \u00b7 one tape, start to finish", "S1", 7, 7, T, color=RED, srt="EXHIBIT S1 \u2014 \u201cnever admitted\u201d")
    add_seg("s1_admit", "00:34:44", "00:35:15", "The applicant admits \u00b7 Apr 27, 6:35 p.m.",
            [(t("00:34:44"), t("00:35:15"), "GAY WOODHOUSE \u2014 attorney for the Cox family")],
            [(t("00:34:52"), t("00:35:15"), "EXHIBIT S1-A \u00b7 SURVEYS STILL OUTSTANDING")],
            "S1-A \u2014 applicant\u2019s attorney: surveys still needed, can\u2019t be done by June [6:35 p.m.]")
    add_seg("s1_cites", "02:19:30", "02:19:52", "Miller cites the admission \u00b7 8:19 p.m.",
            [(t("02:19:30"), t("02:19:52"), MILLER)],
            [(t("02:19:34"), t("02:19:52"), "MILLER CITES IT \u2014 ON THE RECORD")],
            "S1-B \u2014 Miller: \u201cmaps are actually false\u2026 won\u2019t be surveyed until August\u201d [8:19 p.m.]")
    add_seg("s1_postpone", "02:41:04", "02:41:38", "The council concedes \u00b7 postponed to Sept 14",
            [(t("02:41:04"), t("02:41:38"), DAIS)],
            [(t("02:41:11"), t("02:41:38"), "POSTPONED TO SEPT 14 \u2014 TIME CONCEDED")],
            "S1-C \u2014 council postpones to Sept 14 at the family\u2019s request [8:41 p.m.]")
    add_seg("s1_denial1", "03:06:25", "03:07:05", "Denied, part one \u00b7 9:06 p.m.",
            [(t("03:06:25"), t("03:06:42"), MILLER), (t("03:06:42"), t("03:07:05"), DAIS)],
            [(t("03:06:42"), t("03:07:05"), "DENIED \u2014 \u201cNOT ACCURATE\u201d")],
            "S1-D \u2014 \u201cthat is not accurate\u2026 boundaries are in fact accurate\u201d [9:06 p.m.]")
    add_seg("s1_denial2", "04:00:20", "04:00:52", "Denied, part two \u00b7 10:00 p.m.",
            [(t("04:00:20"), t("04:00:30"), MILLER), (t("04:00:30"), t("04:00:52"), DAIS)],
            [(t("04:00:30"), t("04:00:52"), "\u201cNEVER ADMITTED\u2026 INCORRECT, SIR\u201d")],
            "S1-E \u2014 \u201cnever admitted\u2026 faulty boundaries\u2026 incorrect, sir\u201d [10:00 p.m.]")
    # S2
    add_card("EXHIBIT S2", "\u201cCAN\u2019T SAY DATA CENTERS.\u201d April 20: the committee lets the developer pitch data centers \u2014 then gags citizens to \u201cthe annexation.\u201d", "Public Services Committee \u00b7 Apr 20, 2026", "S2", 7, 7, T, color=RED, srt="EXHIBIT S2 \u2014 \u201ccan\u2019t say data centers\u201d")
    add_seg("s2_pitch", "01:16:55", "01:17:55", "The pitch \u00b7 data centers welcome",
            [(t("01:16:55"), t("01:17:55"), "APPLICANT\u2019S DATA-CENTER DEVELOPER")],
            [(t("01:17:01"), t("01:17:55"), "THE PITCH \u2014 UNINTERRUPTED")],
            "S2-A \u2014 developer pitches data-center bona fides, uninterrupted [1:17 p.m.]")
    add_seg("s2_gag", "01:28:40", "01:29:06", "The gag \u00b7 same hearing",
            [(t("01:28:40"), t("01:28:44"), "CITIZEN (TAXPAYER)"), (t("01:28:44"), t("01:29:06"), "COMMITTEE CHAIR")],
            [(t("01:28:44"), t("01:29:06"), "\u201cNOT ABOUT DATA CENTERS\u201d")],
            "S2-B \u2014 chair: \u201cnot about data centers\u2026 about the annexation\u201d [1:29 p.m.]")
    add_seg("s2_gag", "01:29:30", "01:29:48", "The chill, on mic",
            [(t("01:29:30"), t("01:29:48"), "CITIZEN PATRICIA MCCOY")],
            [(t("01:29:35"), t("01:29:48"), "\u201cSINCE I CAN\u2019T SAY DATA CENTERS\u201d")],
            "S2-C \u2014 citizen: \u201csince I can\u2019t say data centers, apparently\u201d")
    add_seg("s2_charge", "02:04:00", "02:04:08", "Second citizen, self-censoring",
            [(t("02:04:00"), t("02:04:08"), "CITIZEN MR. KETCHUM")], [],
            "S2-D \u2014 \u201cI guess I can\u2019t talk about that\u201d [2:04 p.m.]")
    add_seg("s2_charge", "02:05:40", "02:07:20", "The charge \u00b7 viewpoint discrimination",
            [(t("02:05:40"), t("02:07:20"), MILLER)],
            [(t("02:06:29"), t("02:07:20"), "VIEWPOINT DISCRIMINATION \u2014 ON RECORD")],
            "S2-E \u2014 Miller charges viewpoint discrimination, cites the First Amendment")
    add_seg("s2_dismiss", "05:00:30", "05:01:10", "Dismissed five weeks later \u00b7 May 26",
            [(t("05:00:30"), t("05:00:58"), MILLER), (t("05:00:58"), t("05:01:10"), DAIS)],
            [(t("05:00:58"), t("05:01:10"), "\u201cLOST THE COUNCIL\u201d \u2014 MAY 26")],
            "S2-F \u2014 May 26: \u201cyou\u2019ve lost the council\u2026 nothing to do with the moratorium\u201d")
    # S3
    add_card("EXHIBIT S3", "\u201cLEGALLY MEANINGLESS.\u201d March 9: he warns them the Food Freedom Act preempts their farm rules. His notices are dismissed \u2014 then the city delivers exactly what he demanded.", "Mar 9 \u2192 Jun 22 \u2192 Aug 21, 2026", "S3", 8, 8, T, color=RED, srt="EXHIBIT S3 \u2014 \u201clegally meaningless\u201d")
    add_seg("s3_demand", "02:41:10", "02:42:05", "The warning \u00b7 Mar 9",
            [(t("02:41:10"), t("02:42:05"), MILLER)],
            [(t("02:41:18"), t("02:42:05"), "PREEMPTED \u00b7 ULTRA VIRES \u00b7 ILLEGAL")],
            "S3-A \u2014 Miller: 25-customer cap violates the Food Freedom Act [8:41 p.m.]")
    add_seg("s3_meaningless", "05:27:25", "05:27:48", "The dismissal \u00b7 his words, Jun 22",
            [(t("05:27:25"), t("05:27:48"), MILLER)],
            [(t("05:27:32"), t("05:27:48"), "\u201cLEGALLY MEANINGLESS\u201d")],
            "S3-B \u2014 Miller: notices dismissed as \u201clegally meaningless\u201d [Jun 22]")
    add_seg("s3_delivered", "00:57:10", "00:57:55", "Delivered \u00b7 Aug 21 work session",
            [(t("00:57:10"), t("00:57:55"), DAIS)],
            [(t("00:57:23"), t("00:57:55"), "\u201cFOUR OR FIVE OF US ASKED\u201d")],
            "S3-C \u2014 Aug 21: city delivers the update \u2014 credit elsewhere [00:57]")
    # S4
    add_card("EXHIBIT S4", "\u201cTOTALLY OFF BASE.\u201d July 21: a citizen calls the $30,000 FCI contract premature \u2014 staff admits there\u2019s no guaranteed maximum price yet. Six days later Miller relays it and gets gavelled.", "Finance Committee Jul 21 \u2192 Council Jul 27", "S4", 8, 8, T, color=RED, srt="EXHIBIT S4 \u2014 \u201ctotally off base\u201d")
    add_seg("s4_committee", "00:46:58", "00:48:00", "Committee: no price yet \u00b7 Jul 21",
            [(t("00:46:58"), t("00:47:12"), "COUNCILMAN MOODY"), (t("00:47:12"), t("00:48:00"), "CITY STAFF")],
            [(t("00:47:51"), t("00:48:00"), "NO GUARANTEED MAXIMUM PRICE \u2014 YET")],
            "S4-A \u2014 Moody asks what happens; staff: GMP comes later [Jul 21]")
    add_seg("s4_committee", "00:50:45", "00:52:12", "Citizen: premature \u00b7 Jul 21",
            [(t("00:50:45"), t("00:52:12"), "CITIZEN MICHAEL WHITE")],
            [(t("00:51:44"), t("00:52:12"), "\u201cI STILL FEEL THIS PREMATURE\u201d")],
            "S4-B \u2014 citizen White: premature; who gets to bid? [Jul 21]")
    add_seg("s4_relay", "00:51:15", "00:52:00", "Miller relays it \u00b7 Jul 27",
            [(t("00:51:15"), t("00:52:00"), MILLER)],
            [(t("00:51:17"), t("00:52:00"), "MILLER RELAYS THE CITIZEN \u2014 6 DAYS LATER")],
            "S4-C \u2014 Miller relays the citizen\u2019s defect finding [Jul 27]")
    add_seg("s4_offbase", "00:56:15", "00:56:55", "Denied \u00b7 Jul 27",
            [(t("00:56:15"), t("00:56:55"), "COUNCILMAN WOLF")],
            [(t("00:56:20"), t("00:56:55"), "\u201cTOTALLY OFF BASE\u201d")],
            "S4-D \u2014 Wolf: \u201ctotally off base\u2026 denigrates this process\u201d")

    add_card("NO APOLOGY", "Four exhibits. Claim, denial, proof \u2014 all from the city\u2019s own microphones. No correction was ever entered. The caller keeps watching.", "Verify every word: cheyenne.granicus.com + city YouTube archive", "ON RECORD", 9, 9, T, srt="NO APOLOGY ON RECORD \u2014 verify everything")

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
    print(f"[+] THE CALLER TAPE v3 -> {OUT} ({OUT.stat().st_size/1e6:.1f} MB, {t0:.0f}s)")


if __name__ == "__main__":
    main()
