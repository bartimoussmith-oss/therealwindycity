# CivicWatch — deterministic Cheyenne records pipeline

Granicus (view_id=5) → raw PDFs → pypdf text (+ RapidOCR for scans) → SQLite + FTS5 → regex fact extraction → rule-engine briefs → deterministic vector RAG.
**Zero-generative.** Every emitted fact/chunk is a verbatim span with `doc id + page`. Verify the span before quoting it.

**Everything is committed. Nothing needs regenerating.** Extracted text, OCR text, the SQLite DB, the embedding model, and the vector index are on `main`. **Raw PDFs (2.9 GB) are on branch `archive/raw-pdfs`** — see `data/raw/README.md` for the one-line fetch. Kept off `main` only because Streamlit Cloud can't clone >1 GB.

## Corpus (see `data/rag/manifest.json` and `python3 rag.py stats` for exact final counts)
- Meetings: every City Council (regular + special) meeting **Jan 13, 2025 → Sep 22, 2026**, plus Sep 21 PSC and Sep 22 Finance packets.
- ~1,400 attachments · ~18k pages · raw PDFs ≈ 3 GB in `data/raw/<date>_<clip>/`.
- Scanned attachments (0 extractable words) are OCR'd with RapidOCR @150dpi; `docs.ocr=1` marks them. OCR text is machine-read — verify against the PDF before quoting.
- `data/civic.db` — meetings / docs / pages / pages_fts / facts. `data/text/<docid>.txt` — page-delimited (`\f`) text per doc.

## Fast path: finish on Colab
Open `colab_finish.ipynb` in Colab (T4), add `GH_TOKEN` secret, Run all. ~20–30 min: OCR on GPU, embeddings on CPU (bit-identical), pushes `data/rag/` + updated `civic.db` back here. If `vectors.f16.npy.part*` files exist: `cat vectors.f16.npy.part* > vectors.f16.npy`.

## Commands
```
python3 civicwatch.py crawl --since 2025-01-01 [--until 2025-12-31] [--kinds council,psc,finance]
python3 civicwatch.py extract                    # rebuild facts table
python3 civicwatch.py search "holding zone"      # phrase FTS w/ provenance (doc id + page)
python3 civicwatch.py brief --event 1443         # rule-engine red-team brief → brief.md
python3 civicwatch.py votes [--date] [--grep RX] # roll-call parser over minutes; dissent tally
python3 civicwatch.py diff --event 1443          # same file across meetings: IDENTICAL vs changed packet (SHA-1)
python3 civicwatch.py graph                      # applicant/agent/owner/preparer ↔ item force graph → graph.html
python3 civicwatch.py watch                      # new meetings + new/substitute attachments vs DB
python3 ocr.py [--dpi 150] [--limit N]           # OCR docs with <20 words; writes pages back into civic.db
python3 rag.py query "Cox annexation contiguity" [-k 10] [--hybrid]   # semantic (+FTS) search over EVERYTHING
python3 rag.py build --repo ..                   # incremental; only new chunk ids are embedded
python3 rag.py verify                            # re-embeds 200 chunks, asserts bit-exact equality with stored vectors
python3 rag.py stats
./run_all.sh / finish_all.sh / finish2.sh        # the exact build order used (refetch → crawl → ocr → extract → rag)
```

## Vector RAG (`data/rag/`) — deterministic by construction
- Model: `models/minilm-l6-onnx/` (all-MiniLM-L6-v2 exported to ONNX, **committed**, SHA-1 in manifest). CPU only, onnxruntime, fixed 256-token padding, sequential execution → identical bytes on every machine.
- Chunking: 900 chars / 150 overlap, sentence-bounded, never crosses a page. Chunk id = `sha1(source|page|offset|text)` → rebuilding never duplicates, adding docs never reorders existing rows.
- Storage: `vectors.f16.npy` (row-aligned with `chunks.sqlite.chunks.row`), `chunks.sqlite` (text + provenance + FTS5 for hybrid), `manifest.json` (model sha, chunk params, vector sha1, count).
- Coverage: every page in `civic.db` **plus every text file in this repository** (`*.md *.txt *.py *.json *.csv *.html *.yaml *.sh` — uploads/, pipeline/, youtube-archive/, rag/, Entity_Database/, miller-*.md, …). Kind column = `civic` or `repo`.
- Search is exact cosine over numpy (no ANN, no randomness). `--hybrid` unions FTS5 phrase hits before ranking.

## Outputs in this folder
- `briefs/brief_<date>_<id>.md` — rule-engine brief per meeting
- `votes_all.txt` — every parsed motion/dissent/speaker line, Jan 2025–Sep 2026; `votes_all_2026.txt` — Apr–Sep 2026 subset
- `graph.html` — open locally; drag/zoom
- `data/run_all.log`, `data/finish_all.log`, `data/finish2.log`, `data/rag_build.log` — build provenance

## Rules (brief engine)
HIGH: PC_DENIED_STAFF_APPROVE · PC_UNANIMOUS_DENY · STAFF_DENY · CRITERIA_FAIL
MED: NOTICE_LATE_RECEIPT · LOW_CONTIGUITY(<35%) · HOLDING_ZONE · VERBAL_USE_ONLY · LANDOWNER_DETERMINES · STALE_REPORT · GF_RESERVES
LOW: FLOOD · NO_PUBLIC_COMMENT_HIGH_VIEWS · BIG_MONEY · CONSENT_NONROUTINE · YEAR_MIX

## Known limits
- Minutes parser keys on Council minutes phrasing ("Voting "yes" – all members…"); committee minutes differ.
- `acreage` regex occasionally concatenates legal-description numbers (e.g. "1,9197.76"); treat as pointer, not figure.
- `year_mismatch` is noisy by design (any doc citing a different year) — it is a pointer to stale reports, not a finding.
- OCR pages: ~5 s/page on 2 cores; capped at 60 pages/doc (`ocr.py --max-pages`).
- Box has 1 GB RAM: embedder runs at batch 32 with ORT arena disabled. That is why `rag.py` streams the corpus instead of loading it.

## Findings the tools surfaced (Sept 21 PSC packet)
- **Cox Item 7 packet is byte-identical (SHA-1) to April 27 doc517.** Five months, one substitute ordinance, private settlement — zero change to the voting record. Items 8/9/10 and 22 likewise identical to earlier packets (`diff --event 1443`).
- Cox contiguity: **5.26%** (staff: "seemingly small % is due to the size of the annexation").
- Item 13 Campstool: PC denial vs staff approval. Item 16/22/23 Orchard Hills & Hitching Post: staff denial + criteria failures.
- Dissent tally Jan 2025–Sep 2026: Moody 42 · Laybourn 12 · Aldrich 11 · Rinne 6 · Segrave 4 · Esquibel 2 · Wolfe 2 · Emmons 1 · Roybal 1.
