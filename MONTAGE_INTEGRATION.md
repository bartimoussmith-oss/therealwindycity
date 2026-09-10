# Montage / Screening Room — repo integration

Everything below was built in the Sept session. Your repo (synced 9/5) already has the
render scripts, the staged tapes, all renders *except* one, the post kits, and the
updated canon. This drop adds the four things it's missing.

## What's in this drop

| File in this drop | Goes to (repo path) | What it is |
|---|---|---|
| `pages/1_Screening_Room.py` | `pages/1_Screening_Room.py` | **New** — Streamlit page: plays every montage inside therealwindycity.streamlit.app, with post kits, captions, and provenance tabs. Zero new pip deps. |
| `THE_CALLER_TAPE.mp4` | `pipeline/renders/THE_CALLER_TAPE.mp4` | The 13:51 master (720×1280, 22 MB) — was missing from the repo because of workspace size caps on the build side. |
| `cityvideos.json` | `pipeline/cityvideos.json` | Date→YouTube-ID map of the city's meeting archive, 260 meetings, rebuilt from the city channel listing + the three verified war nights (Mar 9 / Apr 27 / Jun 22) with tape timestamps. |
| `corpus/extra/mar9.txt` `apr27.txt` `jun22.txt` | `pipeline/corpus/extra/` | The archive's own auto-captions, converted to timestamped searchable text (16,035 / 11,602 / 15,153 lines). This is what makes every future mic-cut findable without downloading video. |
| `miller-canon-index.md` | `miller-canon-index.md` | **Replaces** your 9/5 copy — identical through §53, plus new §54 logging this integration (page, rebuilt video map, transcripts). |
| `MONTAGE_INTEGRATION.md` | (this file — keep or discard) | — |

## Commit it

From the repo root after copying the files in:

```bash
git add pages/1_Screening_Room.py pipeline/renders/THE_CALLER_TAPE.mp4 \
        pipeline/cityvideos.json pipeline/corpus/extra/
git commit -m "Screening Room page + THE CALLER tape master + archive video map + caption transcripts"
git push
```

No `requirements.txt` change needed — the page is stdlib + streamlit only.
The 22 MB mp4 is fine as a direct commit (GitHub's per-file limit is 100 MB).

## After you push

Streamlit Cloud redeploys on push. The sidebar gains **"Screening Room"** under the
main console. THE CALLER: TAPE EDITION plays first; the other seven videos (already in
the repo) are in the playlist. If a file is missing the page says so instead of
breaking — nothing 500s.

## Already in your repo (don't re-add)

`pipeline/montage.py · montage_miller.py · montage_voices.py · montage_caller_tape.py ·
stories.py · screening_room.py · webui.py · cheyenne_pipeline.py` · the nine staged
tapes in `pipeline/videos/` · `THE_CALLER.mp4`, `THE_RECORD_SPEAKS_VOICES.mp4`, S1–S5,
all `.srt`/`.vtt`, post kits, `index.html` · `miller-canon-index.md` (§52/§53 present —
byte-identical to the build-side canon).

## Re-rendering or extending (local, not on Streamlit Cloud)

The cloud app only *serves* video; rendering needs ffmpeg locally.

```bash
cd pipeline
python3 montage_caller_tape.py    # rebuilds THE_CALLER_TAPE.mp4 from pipeline/videos/
```

To pull a new tape window from a meeting video (never the full file):

```bash
yt-dlp --download-sections "*HH:MM:SS-HH:MM:SS" --force-keyframes-at-cuts \
  -f "bv*[height<=480]+ba/b[height<=480]/best" --merge-output-format mp4 \
  "https://www.youtube.com/watch?v=<ID from cityvideos.json>"
```

Find the moment first in `corpus/extra/*.txt` (or pull captions for any meeting with
`yt-dlp --write-auto-subs --skip-download`). Standing rules baked into the scripts:
officials' voices are never synthesized — real tape only; every card carries its source
on screen; `[MINUTES]` vs `[VERBATIM]` labels stay separate.

## Optional repo hygiene (not required)

- `engine/__pycache__/` and `.sudo_as_admin_successful` are committed; a `.gitignore`
  with `__pycache__/ *.pyc .sudo_as_admin_successful` keeps future syncs clean.
