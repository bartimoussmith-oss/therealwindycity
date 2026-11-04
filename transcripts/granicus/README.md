# The portal's meeting audio, transcribed

Whisper over the City of Cheyenne's own MP3s — the same audio the portal serves — one clip
at a time, committed here as text with second-level timestamps.

**Status:** the harness is in `tools/transcribe_granicus.py` and the job that runs it is
`.github/workflows/transcribe-granicus.yml`. Nothing has been transcribed from *this*
sandbox, because it cannot reach `archive-video.granicus.com` (TLS is cut) or download
Whisper weights (Hugging Face is unreachable). Run the workflow instead — that is what it
is for:

```bash
gh workflow run transcribe-granicus.yml --limit 6 --max_minutes 300
# or one meeting:  gh workflow run transcribe-granicus.yml --clip_id 1144
```

Each run transcribes the oldest clips that have no transcript yet, writes them here, and
commits. Re-running resumes; `--status` prints what is left.

**The size of the job:** `youtube-archive/catalog_granicus.json` lists 474 clips with
audio, 47,553 minutes (792.5 hours) in total. At roughly 6–10× realtime for
`small.en` int8 on four vCPUs, that is ~80–130 hours of compute — about 20 workflow runs
at the 5-hour job cap, or ~4 days if the 6-hourly schedule is switched on in the workflow.

## What lands here

| file | what it is |
|---|---|
| `<clip_id>-<date>-<slug>.md` | the transcript: a timestamped table, each time deep-linked into the official MP3 (`#t=3725`) |
| `<clip_id>-<date>-<slug>.txt` | the same, one line per segment |
| `manifest.json` | one row per finished clip — this is what makes a rerun resume |
| `INDEX.md` / `index.json` | every transcript, with words, length and the audio URL |

Every file states what it is: a machine transcription that can be wrong, not an official
transcript, to be checked against the linked video. Names and numbers are the parts most
likely to be wrong.

## Why not the existing captions

The archive already carries 649 caption tracks (6.7 M words) that were scraped from the
city's YouTube uploads, and 84 hand-timestamped 2026 transcripts. Those cover roughly 128
of the 470 council meeting dates. This job is for the rest — the meetings that only exist
as audio on the portal, back to 2008.

## Credit

Transcription runs on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) with
OpenAI's Whisper models. Model choice is `WHISPER_MODEL` (default `small.en`); the
scanner pipeline in this repo already uses `tiny.en`, so a run can match it exactly.
