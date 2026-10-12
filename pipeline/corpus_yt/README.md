# Verbatim YouTube corpus (`corpus_yt/`)

Machine-mirrored verbatim meeting transcripts. **Do not edit by hand** — this
directory is overwritten by `pipeline/sync_yt_corpus.py` (runs every civic
cycle, ~6h, plus on-demand via workflow dispatch).

- **Upstream:** `therealwindycity/The-Real-Windy-City-`
  (`cheyenne-2026-transcripts/meetings.json` + per-meeting `.md`, public, no auth)
- **Coverage:** city council, committee of the whole, finance, public services,
  work sessions, planning commission, board of adjustment, historic
  preservation, urban renewal — 2026, one `.txt` per meeting
- **Format:** `MEETING: … | DATE: … | YT_ID: …` header, `SOURCE:` /
  `VIDEO:` lines, then `[HH:MM:SS]` verbatim paragraphs
- **Manifest:** `_manifest.json` records the sync time, upstream base, and a
  sha256 per file (unchanged files are left untouched so quiet runs commit
  nothing)

Consumed by `engine/corpus_search.load_corpus()` alongside
`pipeline/corpus/*.txt` (Granicus minutes). Documents from this directory carry
`"source": "verbatim-yt"`.
