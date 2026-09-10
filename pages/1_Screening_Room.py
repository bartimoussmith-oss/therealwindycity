"""Screening Room — the montage theater for The Real Windy City.

Drop-in Streamlit multipage: lives at  <repo>/pages/1_Screening_Room.py
and auto-appears in the app sidebar next to the main console.
Plays the verified-tape montages from pipeline/renders/ — zero new
pip dependencies (stdlib + streamlit only).

The videos are rendered offline (ffmpeg) from the city's own meeting
archive; this page only serves them. To rebuild a video see the
"How this was made" expander, or MONTAGE_INTEGRATION.md.
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]          # repo root
RENDERS = ROOT / "pipeline" / "renders"
CITYVIDEOS = ROOT / "pipeline" / "cityvideos.json"

# ---------------------------------------------------------------- playlist
# f: file in pipeline/renders/ · t: title · len: runtime · tape: real meeting
# audio on tape · kit: paste-ready post kit · srt: caption file
PLAYLIST = [
    dict(f="THE_CALLER_TAPE.mp4", t="THE CALLER: TAPE EDITION", len="13:51",
         tape=True, new=True, kit="POST_THE_CALLER_TAPE.txt", srt="THE_CALLER_TAPE.srt",
         d="Mar 9 & Apr 27, 2026 — his voice, their gavels, every mic cut as it happened."),
    dict(f="THE_CALLER.mp4", t="THE CALLER (cards edition)", len="1:59",
         tape=False, kit=None, srt="THE_CALLER.srt",
         d="The complete incident file — clerk's minutes vs. verbatim record, every card sourced."),
    dict(f="THE_RECORD_SPEAKS_VOICES.mp4", t="THE RECORD SPEAKS: VOICES", len="2:37",
         tape=True, kit="POST_THE_RECORD_SPEAKS.txt", srt="THE_RECORD_SPEAKS.srt",
         d="Nemecek and Moody in their own words, from the dais."),
    dict(f="S1_48_HOURS.mp4", t="S1 · 48 HOURS", len="1:55",
         tape=True, kit="POST_ALL_FIVE.txt", srt="S1_48_HOURS.srt",
         d="From \u201cfew resources\u201d to $0 in two days."),
    dict(f="S2_THE_74M_LIST.mp4", t="S2 · THE 74M LIST", len="1:43",
         tape=True, kit="POST_ALL_FIVE.txt", srt="S2_THE_74M_LIST.srt",
         d="\u201cRemove $22 million\u201d — the amendment war, 0–9."),
    dict(f="S3_THE_TWO_TIES.mp4", t="S3 · THE TWO TIES", len="0:45",
         tape=False, kit="POST_ALL_FIVE.txt", srt="S3_THE_TWO_TIES.srt",
         d="47 speakers, two 5–5 ties, one unanimous deadline."),
    dict(f="S4_THE_214.mp4", t="S4 · THE 214", len="0:52",
         tape=False, kit="POST_ALL_FIVE.txt", srt="S4_THE_214.srt",
         d="65% once-only · 214 people · 3,191 bookings · 16%."),
    dict(f="S5_ONE_NIGHT_IN_APRIL.mp4", t="S5 · ONE NIGHT IN APRIL", len="0:45",
         tape=False, kit="POST_ALL_FIVE.txt", srt="S5_ONE_NIGHT_IN_APRIL.srt",
         d="The Apr 13 trio, the Apr 27 war, and the Sept 14 return."),
]

# ---------------------------------------------------------------- helpers
@st.cache_data(show_spinner=False)
def _video_bytes(path_str: str) -> bytes:
    return Path(path_str).read_bytes()


@st.cache_data(show_spinner=False)
def _text(path_str: str) -> str:
    return Path(path_str).read_text(errors="replace")


def _label(i: int, it: dict) -> str:
    marks = []
    if it.get("new"):
        marks.append("NEW")
    if it.get("tape"):
        marks.append("REAL TAPE")
    tag = f"  [{' · '.join(marks)}]" if marks else ""
    return f"{it['t']}  ({it['len']}){tag}"


# ---------------------------------------------------------------- masthead
st.markdown(
    """<style>
    .sr-mast{border-bottom:6px double #22303c;padding:4px 0 10px;margin-bottom:6px}
    .sr-mast h2{font-family:'Courier New',monospace;font-size:1.7rem;margin:0;color:#22303c}
    .sr-kick{color:#6d7b86;margin:2px 0 0;font-size:.95rem}
    .sr-tag{display:inline-block;background:#22303c;color:#f7f2e7;padding:3px 10px;
    font-family:'Courier New',monospace;font-size:.78rem;margin-top:8px;letter-spacing:.06em}
    .sr-src{color:#6d7b86;font-size:.85rem}
    </style>
    <div class="sr-mast"><h2>SCREENING ROOM</h2>
    <p class="sr-kick">The city's own archive video, its own captions, its own clock —
    cut into vertical montages. Every claim sourced on screen.</p>
    <span class="sr-tag">The minutes count four. The tape counts more.</span></div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------- playlist
choices = [_label(i, it) for i, it in enumerate(PLAYLIST)]
pick = st.radio("Now screening", choices, label_visibility="collapsed")
it = PLAYLIST[choices.index(pick)]
mp4 = RENDERS / it["f"]

st.markdown(f"**{it['t']}** · *{it['len']}*"
            + (" · 🎙 **real meeting audio**" if it["tape"] else " · cards edition"))
st.caption(it["d"])

# ---------------------------------------------------------------- player
if mp4.exists():
    # narrow center column -> vertical (9:16) video reads tall, like a phone
    left, stage, right = st.columns([1, 1.05, 1])
    with stage:
        st.video(_video_bytes(str(mp4)))
    st.markdown(
        f'<p class="sr-src">Source: City of Cheyenne meeting archive (YouTube) · '
        f"minutes clips 1071 / 1093 · file: <code>{it['f']}</code></p>",
        unsafe_allow_html=True,
    )
else:
    st.warning(
        f"`{it['f']}` isn't in pipeline/renders/ yet. It is rendered offline with ffmpeg "
        f"(see the \u201cHow this was made\u201d expander below), then committed with the repo."
    )

# ------------------------------------------------------------- supporting
tabs = st.tabs(["Post kit", "Captions", "How this was made"])

with tabs[0]:
    if it.get("kit") and (RENDERS / it["kit"]).exists():
        st.code(_text(str(RENDERS / it["kit"])), language="text")
    else:
        st.write("—")

with tabs[1]:
    if (RENDERS / it["srt"]).exists():
        st.code(_text(str(RENDERS / it["srt"])), language="text")
    else:
        st.write("—")

with tabs[2]:
    st.markdown(
        "**Pipeline (all code in this repo, `pipeline/`):**\n"
        "1. `pipeline/cityvideos.json` maps every meeting date to the city's YouTube "
        "archive video (rebuilt from the channel listing, 260 meetings).\n"
        "2. `yt-dlp --write-auto-subs` pulls the archive's own captions → "
        "`pipeline/corpus/extra/mar9.txt · apr27.txt · jun22.txt` (timestamped, searchable).\n"
        "3. Every mic cut / point of order is located in the captions, then the exact "
        "window is streamed down with `--download-sections` — never the full meeting.\n"
        "4. `pipeline/montage_caller_tape.py` (and `stories.py`, `montage_voices.py`, "
        "`montage_miller.py`) render cards + tape into vertical video with ffmpeg.\n\n"
        "**Re-render THE CALLER: TAPE EDITION locally:**\n"
        "```bash\n"
        "cd pipeline\n"
        "python3 montage_caller_tape.py   # -> renders/THE_CALLER_TAPE.mp4 (1080x1920)\n"
        "ffmpeg -i renders/THE_CALLER_TAPE.mp4 -vf scale=720:1280 \\\n"
        "  -c:v libx264 -crf 24 -c:a aac -b:a 96k -movflags +faststart small.mp4\n"
        "```\n"
        "Rules baked in: officials' voices are never synthesized — real tape only; "
        "every card carries its source on screen; `[MINUTES]` and `[VERBATIM]` labels "
        "stay separate."
    )
    if CITYVIDEOS.exists():
        cv = json.loads(_text(str(CITYVIDEOS)))
        st.markdown(
            f"**Verified tape nights:** "
            + " · ".join(
                f"{d} — [{v['id']}](https://www.youtube.com/watch?v={v['id']})"
                for d, v in sorted(cv.get("verified_tape", {}).items())
            )
        )

st.caption("Every cut microphone is an exhibit. Every bypassed hand is an exhibit. "
           "· Rendered from public meeting video · no affiliation with any individual, "
           "candidate, or committee")
