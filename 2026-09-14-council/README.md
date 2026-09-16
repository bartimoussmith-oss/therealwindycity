# Cheyenne CivicWatch

Public-records pipeline + public-comment prep for Cheyenne City Council (Granicus view_id=5).

| Path | What |
|---|---|
| `RED_TEAM_and_SPEECHES_2026-09-14.md` | Full agenda red-team + three 3-minute speeches for Sept 14 |
| `DEBRIEF_2026-09-14.md` | Post-meeting scoreboard, admissions on the record, vote targets |
| `COX_HISTORY_COMPARISON.md` | Cox Ranch / data-center docket, Mar–Sep 2026, from official minutes |
| `meetings/2026-09-14_council/` | All 40 supporting PDFs + extracted text |
| `meetings/minutes/` | Council minutes text (Apr 13, Apr 27, May 11, May 26, Jun 8, Jul 13) |
| `civicwatch/civicwatch.py` | Deterministic crawler → SQLite FTS5 index → fact extractor → rule-based brief → entity graph |
| `civicwatch/data/civic.db` | Index of 13 meetings / ~700 attachments (raw PDFs are re-fetchable, not committed) |
| `civicwatch/data/text/` | Extracted page text per document |

## Pipeline
```
cd civicwatch
python3 civicwatch.py crawl --since 2026-01-01 --kinds council   # downloads agendas, minutes, attachments
python3 civicwatch.py index                                      # pypdf text → SQLite + FTS5
python3 civicwatch.py extract                                    # votes, notice dates, contiguity, PC votes, $$
python3 civicwatch.py search "holding zone"                      # provenance-cited full-text search
python3 civicwatch.py brief --event 1441                         # rule-engine red-team brief for one meeting
python3 civicwatch.py graph                                      # applicant/agent/owner ↔ item graph (graph.html)
python3 civicwatch.py watch                                      # diff live publisher vs DB; flags substitutes
```
Zero-generative: every emitted fact is a verbatim span with doc id + page.

## Key dates
- Sep 21 — Public Services Committee (Items 10–16, 22–25, Cox FLUM/USB)
- Sep 28 — Council: 2nd readings; Cox FLUM/USB amendment
- Oct 12 — 3rd readings Cox / Orchard Hills / Hitching Post; Item 23 PC overrule
