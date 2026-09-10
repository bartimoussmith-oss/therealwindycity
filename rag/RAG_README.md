# Cheyenne Council RAG — pipeline guide

Question-answering over Cheyenne City Council meetings: minutes, cleaned
transcripts, agendas, and supporting documents, chunked with citations and
served through a hybrid vector + keyword retriever.

Provenance: Granicus (`cheyenne.granicus.com`) is the system of record for
video, minutes, agendas, and document links. `youtube-archive/` (sibling wing)
handles video download/upload; this wing handles text.

## Layout

| Path | What it is |
|---|---|
| `rag/text_extract.py` | PDF/HTML text extraction (stdlib + vendored parsers) |
| `rag/build_glossary.py` | Mines minutes + docs for people/ordinances/resolutions/phrases; merges `glossary_manual.json` (reviewed ASR confusions) → `glossary.json` |
| `rag/clean_transcripts.py` | Rolling-caption dedup + logged glossary corrections → `pipeline/corpus_clean/` |
| `rag/build_vector_db.py` | Chunks transcripts + minutes + docs with citations → Chroma DB |
| `rag/query.py` | Hybrid RRF retrieval CLI (vector + keyword + filters) |
| `rag/glossary_manual.json` | Hand-reviewed confusion pairs (source of truth for corrections) |
| `rag/glossary.json` | Built glossary (manual + mined candidates) |
| `rag/vectordb_sample/` | Committed 4-clip sample DB (1687 chunks, ~28 MB) — queryable as-is |
| `rag/eval_queries.md` | Eval battery definition + ground truths |
| `rag/eval_results_sample.md` | Captured sample-DB results + verdicts |
| `pipeline/corpus_clean/` | Sample cleaned transcripts + `.changes.json` logs + `cleaning_report.md` |

Only `rag/vectordb_sample/` is committed. Full-run DBs (`rag/vectordb/`,
`rag/text_cache/`) are gitignored build artifacts.

## Quick start (sample)

```bash
pip install -r rag/requirements-rag.txt
python3 rag/query.py "Which council members were present at the March 9 2026 meeting?" --k 3
python3 rag/query.py "Mayor Collins not available tonight" --where '{"clip_id": "1103"}' --k 2
```

## Reproduce the sample outputs

```bash
# 1. glossary (minutes for the 3 sample clips + sample docs)
python3 rag/build_glossary.py --clips 1071 1093 1103 \
    --docs-dir /tmp/sample_docs --max-pdf-mb 8

# 2. clean transcripts (extra/ rolling captions → corpus_clean/)
python3 rag/clean_transcripts.py

# 3. sample vector DB (1124 = minutes-only 4th clip)
python3 rag/build_vector_db.py --clips 1071 1093 1103 1124 \
    --persist rag/vectordb_sample --docs-dir /tmp/sample_docs --max-pages 5
```

Sample inputs: minutes live in `pipeline/corpus/{clip}_*.txt`; raw captions in
`extra/`; sample supporting docs (121 PDFs, 308 MB) were pulled from Granicus
per the upload-plan manifest and are NOT in git (full corpus docs are tens of
GB — see `youtube-archive/` bridge note).

## Full-corpus runs (owner machine)

```bash
python3 rag/build_glossary.py --all
python3 rag/clean_transcripts.py
python3 rag/build_vector_db.py --all --persist rag/vectordb
python3 rag/query.py "..." --persist rag/vectordb
```

## Retrieval design (what the eval taught us)

Chunks carry a date/topic tag (`[2026-03-09 March | City Council | minutes]`)
so date- and meeting-scoped queries match lexically. Retrieval is hybrid:

- **Vector side** (Chroma, `n_fetch = max(k*10, 50)`): conceptual matches.
- **Keyword side**: normalized terms; short terms (≤4 chars) use
  word-boundaries (`roll` must not match `enrolled`); longer terms use
  substring (robust to ASR fragments); crude stemming (`voted`→`vot`) for
  recall; stop words dropped.
- **Fusion**: reciprocal rank fusion, plus two corrections plain RRF needs:
  1. *Keyword-star promotion* — a chunk ranked keyword-#1 with ≥4 matched
     terms is pinned at #1 (otherwise two mediocre ranks outvote one
     excellent rank).
  2. *Stable tiebreak* — id-ascending pre-sort, because reverse sorts break
     ties toward later chunks and date tags make ties common.
- **Filters**: `--where '{"clip_id": "1103"}'` (also `date`, `source_type`).

Known limits (see eval): short factual queries lean on the keyword side
(vector ranks can be weak there); vote tallies occasionally split across chunk
boundaries — future work is minutes chunk overlap + stemmed phrase bonus.

## Transcript cleaning rules (hard-won)

Two-pass claiming (exact first, then fuzzy); single-token fuzzy ≥ 0.92;
multi-token needs every token-pair ≥ 0.60; `'s`-stripped comparison with a
no-op guard; surname-only variants for titled people; never fuzzy-map common
words (`Crave`→`Segrave`, `labour`, bare `Wolf`); street context for
`O'Neil Avenue`; `Jack O'Neal` is a person. Every correction is logged to
`.changes.json`; the report carries a miss-scan. 42,790 lines deduped,
130 corrections across the 3 sample transcripts, zero misses on rescan.
