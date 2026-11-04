# notebooklm_controller

Auto-running third-party controller for **NotebookLM** over the **full City of Cheyenne**
meeting archive — **2008-05-27 → 2026-08-24 (~563 meetings, ~20 years)**, oldest video/meeting
first. One notebook per meeting, a full suite of studio artifacts per meeting, historical
context woven from every earlier meeting, and NotebookLM/Gemini watermark scrubbing on every
artifact.

## What it does (mission)

1. **Inventory** the entire Cheyenne meeting archive, oldest → newest:
   - `pipeline/meetings.json` — 479 Granicus meetings (2008-05-27 → 2026-08-24) with
     agenda/minutes/MP4 URLs per meeting.
   - `pipeline/corpus_yt/` — 85 verbatim YouTube transcripts (2026, channel `@TheCityofCheyenne`),
     matched to meetings by date + body to attach YouTube video IDs.
   - `pipeline/notebooklm/cheyenne_minutes_YYYY.md` — yearly minutes aggregates (2008+),
     split per-meeting on the `MEETING: ... | DATE: ... | CLIP_ID:` header.
   Result: a unified queue of ~563 meetings, deduplicated by date + body, sorted strictly
   oldest → newest.

   **Manifest refresh:** `controller.py refresh` re-syncs all connected repos and public
   sources (upstream YouTube-transcript repo, Granicus meeting index, Granicus catalog
   mirror) then rebuilds the queue, bringing the manifest current to 2026-11-04 when
   network is available.

2. **One NotebookLM notebook per meeting** — sources: the YouTube video, its verbatim
   transcript, the Granicus agenda/minutes, and every supporting document linked inside
   the agenda. Notebook spec written to `state/nb-<date>-<clip_id>.json` for every meeting.

3. **Context chaining — each notebook carries its predecessors' sources.** Before a
   meeting's notebook is built, the controller converts the prior meetings' studio
   packages (`06_studio_package.md`) into optimal plain-text sources and adds them into
   this notebook's source list (newest limited to 6, sorted oldest → newest). So every
   notebook reads the *actual prior record* (verbatim quotes, decisions, ordinances,
   projects, officials), not just a reference. The `04_historical_context.md` section
   additionally lists entity-shared prior meetings with verbatim snippets and artifact
   links. By the final meeting, artifacts reference meetings all the way back to 2008 —
   the archive is read as one continuous record.

4. **Studio artifacts per meeting** (7 files + a `sources/` folder in
   `artifacts/<date>-<body>-<clip_id>/`):
   - `00_manifest.json` — provenance, per-artifact SHA-256, watermark-scan audit, notebook spec
   - `01_meeting_brief.md` — who/what/when, motions, votes, outcomes, supporting documents
   - `02_transcript_notes.md` — verbatim quotes with timestamps, decision-dense passages
   - `03_agenda_trace.md` — agenda items → supporting documents → disposition
   - `04_historical_context.md` — preceding meetings sharing the same ordinances, statutes,
     projects, or officials, auto-woven from the entity index
   - `05_audio_overview.txt` — NotebookLM-style two-host studio script
   - `06_studio_package.md` — the combined single-file deliverable
   - `sources/` — local copies of the harvested agenda page and every linked supporting
     document (staff reports, packet pages, PDFs), populated when network allows

5. **Watermark scrub** — every artifact is scanned for NotebookLM / Gemini branding strings
   ("Made with NotebookLM", "powered by Gemini", etc.) and they are removed before writing;
   the pre-scan audit is recorded in `00_manifest.json`. Optional OpenCV/ffmpeg slide/video
   frame redaction is declared and opt-in (no DRM bypass).

## Files

```
notebooklm_controller/
  controller.py        orchestrator: run / status / report / inventory
  archive_inventory.py unified archive inventory, oldest -> newest (563 meetings)
  notebooklm_adapter.py  live driver via notebooklm-py (unofficial client) + simulation mode
  artifact_builder.py  studio-artifact generator (stdlib only)
  history_weaver.py    entity index + historical-context weaving
  watermark_scrubber.py watermark detection/removal (text + optional frames)
  artifacts/           generated studio artifacts, one dir per meeting (3941 files,
                       plus a sources/ subfolder per meeting when docs are harvested)
  state/               checkpoint, entity index, queue, last report, notebook specs
  runs/                per-run logs + reports
  logs/                run logs
```

## Run it

```bash
# 1) Inspect the queue (oldest -> newest, 563 meetings)
python3 notebooklm_controller/controller.py inventory

# 2) Test a few meetings first
python3 notebooklm_controller/controller.py run --limit 6

# 3) Process the full archive (resume-safe via checkpoint)
python3 notebooklm_controller/controller.py run

# 4) Resume later — checkpoint skips completed meetings automatically
python3 notebooklm_controller/controller.py run

# 5) Live NotebookLM (your machine, your Google account, network to google.com)
pip install "notebooklm-py[browser]"
notebooklm login                     # one-time Google sign-in
NOTEBOOKLM_LIVE=1 python3 notebooklm_controller/controller.py run
```

## NotebookLM reality check

NotebookLM has **no official public API**. Live control uses the maintained unofficial
client **notebooklm-py** (teng-lin/notebooklm-py on PyPI), which reverse-engineers
Google's internal endpoints. It requires your own Google account and network access to
google.com — run `notebooklm login` once, then `NOTEBOOKLM_LIVE=1`.

This repo runs in **simulation mode by default**: it writes the complete notebook spec
for every meeting and generates the full studio artifact suite locally from the verified
corpus, so nothing depends on Google's UI, credentials, or network. To create real
notebooks inside notebooklm.google.com, run Option 5 on your hardware.

## Watermark / legal notice

NotebookLM does **not** watermark user-uploaded sources; it brands some Google-generated
outputs (e.g. Audio Overviews). This scrubber only touches artifacts you produced or
records you hold redistribution rights for (here: public City of Cheyenne meeting records).
Do **not** use it to circumvent DRM or strip copyright management information from
third-party copyrighted video/slides. Frame scrubbing requires ffmpeg + OpenCV and is
disabled by default.

## Where the archive comes from

- `pipeline/meetings.json` — Granicus agenda/minutes/MP4 index (479 meetings, 2008–2026)
- `pipeline/corpus_yt/` — mirrors `therealwindycity/The-Real-Windy-City-`
  (cheyenne-2026-transcripts), public, no auth
- `pipeline/notebooklm/cheyenne_minutes_YYYY.md` — yearly minutes aggregates (2008–2026)
- City of Cheyenne YouTube channel: `@TheCityofCheyenne`; Granicus: `cheyenne.granicus.com`
