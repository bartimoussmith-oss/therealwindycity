# Cheyenne Omni Knowledge Base

Auto-generated, AI-readable corpus matching City of Cheyenne YouTube meeting
transcripts to the agenda/ordinance/resolution documents for that same
meeting. Built by `tools/build_omni_knowledge_base.py` — re-run it any time
more shard files are harvested; it fully rebuilds from source each time.

## Files

- **meetings.jsonl** — the primary artifact. One JSON object per line, one
  line per harvested meeting. Load with `pandas.read_json(path, lines=True)`
  or stream line-by-line in any language. Fields per record:
  - `youtube_id`, `date` (YYYY-MM-DD), `kind` (meeting type, best-effort),
    `title`, `video_url`, `transcript` (full auto-caption text),
    `transcript_chars`, `source_shard`
  - `documents`: list of agenda/ordinance/resolution documents matched to
    this meeting, each with `title`, `source_url`, `harvested_at`,
    `content` (full extracted text), `content_chars`, `match_confidence`,
    `date_source`
  - `document_count`: convenience count of `documents`
- **unmatched_documents.json** — documents that could not be tied to any
  harvested transcript yet, with the reason (no date could be extracted
  from the text/filename, or a date was found but no transcript for that
  date has been harvested yet). Re-check this after harvesting more videos.
- **unmatched_transcripts.json** — transcripts with zero matched documents.
- **manifest.json** — build stats and provenance.

## Matching method (and its honest limits)

Most of these documents come from Granicus `DocumentViewer.php` URLs with
opaque hashed filenames (`cheyenne_<md5>.pdf`) — only a small minority carry
a date in the filename. So the match key is **the date stated inside the
document's own text** (agendas/ordinances open with a line like
"... June 23, 2023 ..."), extracted with a regex over the first ~4000
characters. Every document and every match records how its date was
obtained (`content_date`, `filename_date`, or `unknown`) and the resulting
`match_confidence` (`date+kind`, `date-only`, or `date-only (ambiguous,
attached to all)` when multiple distinct meetings share the same date and
the document's meeting type couldn't be determined) — this is a heuristic
match, not an authoritative ID join, and is surfaced as such rather than
asserted as certain.

## Also feeds the site's existing search engine

Every transcript is additionally written to `pipeline/corpus_omni/` in the
same header convention as `pipeline/corpus_yt/` (see
`engine/corpus_search.py`), tagged as source `"omni-auto-captions"`, so it's
full-text searchable alongside the official clerk minutes (`pipeline/corpus/`)
and the curated verbatim mirror (`pipeline/corpus_yt/`) without any separate
tooling.

## Regenerating

```
python3 tools/build_omni_knowledge_base.py \
    --input-dir output \
    --out-dir pipeline/omni_knowledge_base \
    --corpus-omni-dir pipeline/corpus_omni
```

Defaults match the paths above, so a bare `python3 tools/build_omni_knowledge_base.py`
run from the repo root works once `output/Cheyenne_Omni_Corpus_Shard_*.md` and
`output/Cheyenne_Municipal_Shard_*.md` are present (e.g. synced down from the
Drive folder, or run directly on the harvesting device).

## Scope note

This snapshot covers only what has been harvested so far — a fraction of
the ~888 videos on the channel and an even smaller slice of the city's full
agenda/ordinance history. It grows every time the harvester and the
document scraper produce more shard files; nothing about the schema needs
to change as that happens.
