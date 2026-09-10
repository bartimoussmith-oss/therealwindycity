# RAG eval battery (sample DB)

Sample DB: `rag/vectordb_sample/` — 1687 chunks across clips 1071 (2026-03-09),
1093 (2026-04-27), 1103 (2026-06-23; meeting held 2026-06-22), 1124
(minutes-only). Run with `python3 rag/query.py "<query>" --k N`.

## Queries + ground truths

| # | Query | Ground truth |
|---|---|---|
| Q1 | Which council members were present at the March 9 2026 meeting? | 1071 minutes roll call ("Present were:"); all members present, no Absent line |
| Q2 | PRCA rodeo hall of fame Project Blue Moon funding | 1071 transcript @~624s ($800k sales-tax discussion) + agenda item 22 (PRCA resolution) |
| Q3 | Who voted no on the ordinance second reading? | AMBIGUOUS by design (no date). Best single-chunk answer: 1071 transcript — ordinance approved on second reading as amended, Laybourn + Wolfe voting no (`1071:tx:00133`; minutes mirror: `1071:min:00375`) |
| Q3b | …at the April 27 meeting? | Date-scoped variant: all top hits must be clip 1093 |
| Q4 | Harmony Valley annexation zoning map amendment | 1071 supporting-doc staff report (rezoning pages) |
| Q5 | Via West postponement second reading Holland Hart | 1093 transcript @1765s (postponement testimony) |
| Q6 | Mayor Collins not available tonight (`--where clip 1103`) | 1103 transcript opening @108s (clip filter must hold) |

## What each query stresses

- Q1: date tags + keyword side (vector rank is weak here by nature).
- Q2: transcript-vs-agenda consensus; ASR fix visible (`Laramie County`).
- Q3: ambiguous multi-meeting question; stemming (`voted`→`vot`) recall.
- Q4: supporting-doc retrieval (PDF pages, not minutes/transcript).
- Q5: keyword-star promotion (vector side misses entirely).
- Q6: metadata filtering + exact-phrase opening retrieval.
