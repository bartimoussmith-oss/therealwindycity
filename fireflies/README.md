# `fireflies/` — Fireflies-style meeting intelligence

A local mirror of the fireflies.ai loop for this repo's meeting corpus —
**transcripts, agenda items and supporting documents in; intelligence out**:

| Fireflies feature | Here | Method tag |
|---|---|---|
| Meeting summary | `## Overview` in each brief — extractive sentence selection, every sentence a verbatim quote with a locator | `extractive-freq-v1` |
| Outline / chapters with jump-to-moment | `## Outline` — agenda items aligned to `[HH:MM:SS]` caption spans (YouTube `&t=` deep links) or Granicus `MediaPlayer.php?meta_id=` per-item links | `anchor-alignment-v1`, `granicus-mediaplayer-link-v1`, `minutes-paragraph-span-v1` |
| Action items & decisions | `## Decisions & actions` — motions, seconds, outcomes, vote tallies, directives to staff, scheduling, appointments — each a verbatim sentence, pattern-tagged, with speaker and locator | `verbatim-pattern-v1` |
| Agenda item ↔ supporting docs tracker | `## Agenda items & supporting documents` + `ledger/agenda_tracker.csv` (one row per item: expected ACTION line, docs, chapter, outcome quotes) | `granicus-agenda-html-v1`, `minutes-item-patterns-v1`, `speech-item-cues-v1` |
| Search across meetings | `python3 -m fireflies search` + the console page — whitespace-flexible phrase search over every source text with timestamp/paragraph locators | — |
| Topic / entity tracking | `ledger/topics.json` + `python3 -m fireflies topics` — ordinances, resolutions and statute cites followed across the whole corpus with first/last seen and example quotes | — |

## The integrity contract

This repo's rule is **"if it isn't quotable, it isn't asserted."** The
analyzer only *selects and categorizes sentences from the record* — it never
generates text. Every derived field is method-tagged, and

```bash
python3 -m fireflies verify
```

re-opens every source file and checks **every stored quote is a verbatim
substring** (whitespace- and entity-tolerant). The full corpus run checks
~84,000 quotes. Titles derived from spoken cues are labelled `title_guess`
and always ship alongside their verbatim cue sentence. ASR turns are counted,
never attributed (no diarization is claimed).

All corpora are **read-only inputs**; this package writes only under
`fireflies/briefs/` and `fireflies/ledger/` (or an explicit `--out`).

## Sources ingested (merged per meeting by date + body)

| Source | What | Coverage |
|---|---|---|
| `pipeline/corpus/*.txt` | Granicus minutes prose (`RECORD OF PROCEEDINGS`) | 473 meetings, 2008–2026 |
| `pipeline/corpus_yt/*.txt` | timestamped YouTube caption transcripts (`[HH:MM:SS]`, `>>` turns) | 85 meetings, 2026 |
| `drive-import/master_meetings_database_linked.json.gz` | markdown transcripts (2004–2026; date conflicts with filenames are flagged, both values kept) | 720 records |
| `uploads/*.md` | uploaded markdown transcripts (deduped against the master DB by content hash) | 2025–2026 |
| `pipeline/meetings.json` | clip_id → agenda/minutes/MP4 URLs | 479 meetings |
| `pipeline/docs/<clip_id>/` | agenda + minutes + packet HTML (Granicus anchors carry per-item video deep links and MetaViewer supporting-doc links) | sample (clip 1124) |

## CLI

```bash
python3 -m fireflies build                 # full corpus -> briefs/ + ledger/
python3 -m fireflies build --limit 25      # quick partial run
python3 -m fireflies brief 2026-08-10      # print one meeting brief
python3 -m fireflies search "water rates"  # phrase search, timestamped snippets
python3 -m fireflies topics                # entity timelines (top ordinances…)
python3 -m fireflies topics "Ordinance 4687"   # one term across every meeting
python3 -m fireflies tracker --year 2026   # flat agenda-item tracker view
python3 -m fireflies verify                # quote verifier (exit 2 on any failure)
```

Console page: `pages/30_Meeting_Intelligence.py` (meeting briefs, agenda
tracker, search, topics) — run `streamlit run Transparency_Index_App.py` and
open **Meeting Intelligence**.

## Layout

```
fireflies/
  sources.py     read-only corpus loaders + meeting merge (date/body keyed)
  textutil.py    sentence/quote utilities, OCR-de-join for matching, locators
  agenda.py      agenda items from agenda HTML / minutes prose / speech cues
  actions.py     motions·votes·directives extraction (verbatim + pattern tag)
  outline.py     chapter alignment: anchors -> caption time spans
  summarize.py   extractive overview, keywords, entities (method-tagged)
  topics.py      cross-meeting entity & term timelines
  search.py      corpus-wide phrase search with locators
  build.py       orchestration + quote verifier
  render.py      markdown briefs + INDEX
  __main__.py    CLI
  test_fireflies.py   27 offline tests incl. full e2e on a synthetic corpus
  briefs/<meeting_id>.md    generated Fireflies-style briefs
  ledger/meetings.jsonl     full derived ledger (one JSON per meeting)
  ledger/agenda_tracker.csv one row per agenda item
  ledger/topics.json        entity timelines
  ledger/INDEX.md           corpus index
```

Regenerate everything after corpus changes: `python3 -m fireflies build && python3 -m fireflies verify`.
