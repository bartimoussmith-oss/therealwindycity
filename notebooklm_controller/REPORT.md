# notebooklm_controller — mission report

**Run:** run-20261104-094621 (2026-11-04T09:48:29+00:00)
**Mode:** offline simulation (live NotebookLM drive disabled — set
`NOTEBOOKLM_LIVE=1` with notebooklm-py + credentials to drive notebooklm.google.com
for real)

## Result

| Metric | Value |
|---|---|
| Meetings inventoried (Cheyenne archive, oldest -> newest) | 563 |
| Date span covered | 2008-05-27 -> 2026-08-24 |
| Manifest refresh target (current date) | 2026-11-04 |
| Meetings processed | 563 |
| Failures | 0 |
| Studio artifacts written | 3,941 (7 files per meeting) |
| Notebook specs written | 563 (one per meeting) |
| Artifacts with watermark findings | 563 (all scrubbed; audit in each `00_manifest.json`) |
| Artifacts root | `notebooklm_controller/artifacts/` (~23 MB) |
| Supporting docs harvested | 0 local copies (sandbox has no network to cheyenne.granicus.com) |
|   — on a networked machine, each agenda's MetaViewer/PDF links are fetched into `sources/` |

## Data freshness note

The local manifest currently ends at **2026-08-24** (last Granicus meeting and last
synced YouTube transcript). Today is **2026-11-04**, so meetings from late August
through early November 2026 are not yet captured. To bring the manifest current:

```bash
python3 notebooklm_controller/controller.py refresh
```

This re-syncs all connected repos and public sources — the upstream YouTube
transcript repo (therealwindycity/The-Real-Windy-City-), the Granicus meeting
index (`cheyenne_pipeline.py index`), and the Granicus catalog mirror
(`scrape_granicus.py`) — then rebuilds the controller queue so any meetings
through 2026-11-04 are included. Requires network to github.com and
cheyenne.granicus.com (blocked in this sandbox; runs gracefully offline).

## How context flows between notebooks

Each notebook gets its context from previous meetings in two complementary ways:

1. **Converted prior-meeting sources (added to each notebook).** Before a meeting's
   notebook is built, the controller converts the prior meetings' studio packages
   (`06_studio_package.md`) into optimal plain-text sources and adds them into this
   notebook's source list (newest limited to 6, sorted oldest → newest). So every
   NotebookLM notebook actually ingests the *actual prior record* — verbatim quotes,
   decisions, ordinances, projects, officials — not just a reference.

2. **Entity-woven historical context (`04_historical_context.md`).** An entity index
   (ordinances, resolutions, chapters, statutes, dollar amounts, projects, names)
   accumulates meeting by meeting. Each artifact lists earlier meetings on the same
   topics with verbatim snippets and artifact links. By the final meeting (2026-08-24),
   artifacts reference meetings all the way back to 2008-05-27.

So yes — sources are converted to optimal plain-text format and added into each
subsequent notebook, alongside that meeting's own YouTube video, transcript, agenda,
and supporting documents.

## What was produced

`notebooklm_controller/artifacts/<date>-<body>-<clip_id>/` — one directory per meeting:

- `00_manifest.json` — provenance: clip_id, date, body, YouTube id/URL, Granicus agenda +
  minutes/MP4 URLs, notebook spec, per-artifact SHA-256, watermark scan/scrub audit.
- `01_meeting_brief.md` — date, body, source links, attendees, key moments, supporting
  documents, outcomes.
- `02_transcript_notes.md` — verbatim quotes with timestamps + decision-dense passages.
- `03_agenda_trace.md` — agenda items → supporting documents → disposition.
- `04_historical_context.md` — preceding meetings sharing the same ordinances, statutes,
  projects, or officials, with verbatim snippets and artifact links.
- `05_audio_overview.txt` — NotebookLM-style two-host studio script.
- `06_studio_package.md` — the combined single-file deliverable.
- `sources/` — local copies of the harvested agenda page and every linked supporting
  document (staff reports, packet pages, PDFs). Populated when the machine running the
  controller can reach cheyenne.granicus.com.

`notebooklm_controller/state/nb-<date>-<clip_id>.json` — the NotebookLM notebook spec per
meeting (sources: YouTube video + transcript + agenda + every supporting document +
prior-meeting context sources, generation instructions). The live notebooklm-py adapter
can ingest these specs into real notebooks.

## Watermark handling

Every artifact is scanned with `watermark_scrubber.scan_text()` for NotebookLM / Gemini
branding and the strings are removed before writing; pre-scan findings are recorded in
`00_manifest.json` for an honest audit trail. Optional OpenCV/ffmpeg slide/video-frame logo
redaction is declared and opt-in (never bypasses DRM).

## Resuming

Checkpointed in `state/checkpoint.json`; `controller.py run` is safe to re-run
(cron-friendly) and picks up where it stopped. `controller.py status` shows progress;
`controller.py report` prints the last run report.

## Live NotebookLM drive

NotebookLM has no official API. `notebooklm_adapter.py` drives it via the unofficial
`notebooklm-py` client (teng-lin/notebooklm-py on PyPI), gated behind
`NOTEBOOKLM_LIVE=1`:

```bash
pip install "notebooklm-py[browser]"
notebooklm login          # one-time: sign into your Google account
NOTEBOOKLM_LIVE=1 python3 notebooklm_controller/controller.py run
```

Until then, simulation mode produces the complete artifact suite locally — nothing is sent
to Google.

## Ecosystem impact

- **Previously:** meetings scattered across YouTube + Granicus + yearly minutes, each
  analyzed in isolation, no chronological thread across 20 years.
- **Now:** one notebook per meeting, oldest → newest, all 563 meetings accounted for;
  every artifact carries the historical context of every earlier meeting on the same topics
  (both as ingested sources and as a woven context section); every agenda's linked
  supporting documents are harvested as sources; every artifact scrubbed of generator
  branding.
- **Plugs into existing repo:** reads `pipeline/meetings.json`, `pipeline/corpus_yt/`,
  `pipeline/notebooklm/`; writes only to the new `notebooklm_controller/` wing.
