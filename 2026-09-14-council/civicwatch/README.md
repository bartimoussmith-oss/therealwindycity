# CivicWatch — deterministic Cheyenne records pipeline

Granicus (view_id=5) → PDFs → pypdf text → SQLite + FTS5 → regex fact extraction → rule-engine briefs.
**Zero-generative.** Every emitted fact is a verbatim span with `doc id + page`. Verify the span before quoting it.

## Corpus (as of 2026-09-15)
13 meetings (Apr 13 → Sep 22, 2026) · 460 real attachments · 6,438 pages · 1.5M words · 7,383 extracted facts.
Raw PDFs (~1.1 GB) are **not** committed — `crawl` re-fetches them. `data/civic.db` + `data/text/` are committed.

## Commands
```
python3 civicwatch.py crawl --since 2026-01-01 [--kinds council,psc,finance]
python3 civicwatch.py index                      # (crawl already indexes inline; this catches stragglers)
python3 civicwatch.py extract                    # rebuild facts table
python3 civicwatch.py search "holding zone"      # phrase FTS w/ provenance
python3 civicwatch.py brief --event 1443         # rule-engine red-team brief → brief.md
python3 civicwatch.py votes [--date] [--grep RX] # roll-call parser over minutes; dissent tally
python3 civicwatch.py diff --event 1443          # same PUDC file across meetings: IDENTICAL vs changed packet (SHA-1)
python3 civicwatch.py graph                      # applicant/agent/owner/preparer ↔ item force graph → graph.html
python3 civicwatch.py watch                      # new meetings + new/substitute attachments vs DB
```

## Outputs in this folder
- `briefs/brief_<date>_<id>.md` — one per meeting, all 13
- `votes_all_2026.txt` — every parsed motion/dissent/speaker line Apr–Sep 2026
- `graph.html` — open locally; drag/zoom
- `data/recrawl.log`

## Rules (brief engine)
HIGH: PC_DENIED_STAFF_APPROVE · PC_UNANIMOUS_DENY · STAFF_DENY · CRITERIA_FAIL
MED: NOTICE_LATE_RECEIPT · LOW_CONTIGUITY(<35%) · HOLDING_ZONE · VERBAL_USE_ONLY · LANDOWNER_DETERMINES · STALE_REPORT · GF_RESERVES
LOW: FLOOD · NO_PUBLIC_COMMENT_HIGH_VIEWS · BIG_MONEY · CONSENT_NONROUTINE · YEAR_MIX

## Known limits
- 53 attachments are scanned images (0 extractable words) — flagged `⚠` in briefs; OCR not yet wired (no tesseract in sandbox).
- Minutes parser keys on Council minutes phrasing ("Voting "yes" – all members…"); committee minutes differ.
- `acreage` regex occasionally concatenates legal-description numbers (e.g. "1,9197.76"); treat as pointer, not figure.

## Findings the tools surfaced (Sept 21 PSC packet)
- **Cox Item 7 packet is byte-identical (SHA-1) to April 27 doc517.** Five months, one substitute ordinance, private settlement — zero change to the voting record.
- Cox contiguity: **5.26%** (staff: "seemingly small % is due to the size of the annexation").
- Item 13 Campstool: PC denial vs staff approval. Item 16/22/23 Orchard Hills & Hitching Post: staff denial + criteria failures.
- Dissent tally Apr–Sep: Moody 28 · Laybourn 5 · Rinne 4 · Aldrich 4 · Wolfe 2 · Esquibel 1.
