# The provenance guide

*One page for everything in this archive: what it holds, the films that show how it was fetched, and how to check any number in it yourself.*

Generated **2026-11-04T14:03:09Z** from this checkout by `python3 -m provenance guide`. Nothing on this page is typed in by hand — every number is read from the artefacts beside it, and anything missing is reported as missing.

## The collection, in five numbers

| | |
|---|---|
| **7,466** | files in the collection, each one assigned to a family |
| **24** | kinds of record — meetings, packets, minutes, transcripts, tape, news, arrests, scanner, open data |
| **4,636** | of those files captured from a public site rather than derived |
| **13** | public sites the repo's own files point at |
| **0** | files unaccounted for |

By hand, the same set is roughly **9 d 14 h 35 m** of work at the conservative rates stated per family in `provenance/inventory.py`. That figure is an estimate and is labelled as one wherever it appears.

## What is here

| thing | what it is | size / length | file |
|---|---|---|---|
| **The time-lapse** | Every file this archive holds, one cell each, in capture order — the size of the collection at a glance. | 20.0s · 10.5 MB | `video/provenance-timelapse.mp4` |
| **The chapter film (master)** | One chapter per kind of record: the real public page, the clicks a person makes, the download, and the file landing in this archive. | 221.6s · 8.3 MB | `video/provenance-manual-run.mp4` |
| **The showcase (one file, everything)** | The time-lapse, then every chapter back to back. This is the copy the site serves, so every cue is a timestamp into a single file. | 241.6s · 18.8 MB | `video/provenance-showcase.mp4` |
| **The per-chapter cues** | Each chapter cut out of the master film, ~14 seconds each, with a poster frame. These are what sit inline on the pages next to the numbers they explain. | 11 clips · 9.8 MB | `video/clips/` |
| **The ledger — one row per datum** | Every figure this project prints, with the public page it came from, the literal clicks to fetch it, the film cue where that fetch is on screen, and the files here it was counted from. | 26.1 KB | `data/out/PROVENANCE-LEDGER.md` |
| **The inventory — what is actually here** | Every file in the checkout assigned to a data family, with its origin host, unit count, size, and a conservative estimate of what the same work costs by hand. | 18.1 KB | `data/out/PROVENANCE-INVENTORY.md` |
| **The record, with provenance on every page** | The public record itself: ~7,000 plain-text pages. Every page that states a number now carries a section underneath it with the origin link, the cue clip, and the click-path for that number. | — | `https://bartimoussmith-oss.github.io/therealwindycity/` |
| **The app, with the same block** | The Streamlit record. Every view that prints a number carries the same provenance block in a collapsed expander, and both films in the footer. | — | `rwc_provenance.py` |
| **The checks** | Two scripts that make the claim testable rather than asserted: one fails the build if a datum loses its link or cue; the other rebuilds the record from scratch and crawls every rendered page. | — | `tools/check_provenance.py` |

## How to use this

### 1. Watch the time-lapse first

It is 20.0s and it shows the size of the thing: 7,466 files in 24 families. You are not meant to read every cell — you are meant to see how many there are.

### 2. Then watch one chapter

Pick the kind of record you actually care about — meeting nights, agenda packets, minutes, transcripts, the tape, the news, the arrest reports, the scanner, open data. Each chapter is ~15 seconds: the real page, the click, the download. Start with chapter 1 at 0:25 in the chapter film.

### 3. Then read the ledger row for a number you already believe

The ledger has 121 rows. Find one you can check quickly — a meeting count, a file count — and follow its origin link. If the number is not on the page the ledger points at, that is a bug and the ledger is wrong.

### 4. Then do it yourself, once

Open the origin URL, follow the click-path in the ledger row, and download one file. It should take you two minutes and it should be exactly what the chapter showed. That is the whole test: everything here is re-fetchable by hand.

### 5. Then run the checks

`python3 tools/check_provenance.py --site _site` and `python3 tools/provenance_site_audit.py` — the first proves every datum still carries a link and a cue, the second rebuilds the record and crawls every page. If either fails, do not trust the page that changed.

## Each piece, in detail

### The time-lapse

Every file this archive holds, one cell each, in capture order — the size of the collection at a glance.

- each file arriving on a wall of cells, ~566/second
- the “just arrived” column naming files as they land
- a bar filling with what the pile is made of: which families, in what proportion

**Why you would open it:** Start here if you want to know how much material there is before asking how it was got.

**Where it comes from:** data/out/provenance-timelapse-frames.json — one row per file  
**Rebuild:** `python3 -m provenance timelapse`

### The chapter film (master)

One chapter per kind of record: the real public page, the clicks a person makes, the download, and the file landing in this archive.

- the scanner classifying the checkout (intro + detect)
- eleven chapters, one per data family, each with its real origin URL
- the collection panel: how many units, where they go, what it costs by hand
- the source-site table at the end, and the rebuild commands

**Why you would open it:** This is the how-to. Find the chapter for the kind of record you want and watch that chapter; the rest you can skip.

**Where it comes from:** provenance/story.py → data/out/provenance-storyboard.json  
**Rebuild:** `python3 -m provenance video`

### The showcase (one file, everything)

The time-lapse, then every chapter back to back. This is the copy the site serves, so every cue is a timestamp into a single file.

- the time-lapse (everything at once)
- then the chapter film (one thing at a time)

**Why you would open it:** Send this to somebody who has ten minutes and no context. It is the whole claim in one file, in the right order.

**Where it comes from:** ffmpeg concat of the two films above, stream-copied (no re-encode)  
**Rebuild:** `python3 -m provenance ledger --showcase`

### The per-chapter cues

Each chapter cut out of the master film, ~14 seconds each, with a poster frame. These are what sit inline on the pages next to the numbers they explain.

- one family's fetch, start to finish, with no setup

**Why you would open it:** Open the one for the number you are checking. The row underneath it tells you the second inside the clip where that exact figure appears.

**Where it comes from:** video/provenance-manual-run.mp4, cut with -c:v copy  
**Rebuild:** `python3 -m provenance ledger --clips`

### The ledger — one row per datum

Every figure this project prints, with the public page it came from, the literal clicks to fetch it, the film cue where that fetch is on screen, and the files here it was counted from.

- 121 rows, each: datum · page · value · origin URL · film cue · which beat
- the film timeline, scene by scene

**Why you would open it:** This is the citation table. If a page states a number, search the ledger for it and you get the source and the footage.

**Where it comes from:** provenance/ledger.py — reads the inventory, the film schedule and data/engine.db  
**Rebuild:** `python3 -m provenance ledger`

### The inventory — what is actually here

Every file in the checkout assigned to a data family, with its origin host, unit count, size, and a conservative estimate of what the same work costs by hand.

- 24 families, 7466 files, 0 unaccounted for
- the source hosts found in the repo's own files, with counts
- per-family seconds and actions per unit, stated so they can be argued with

**Why you would open it:** Read this if you want to know what the archive contains and roughly what it took — and to check that nothing is unaccounted for.

**Where it comes from:** provenance/inventory.py (the family definitions are the interesting part)  
**Rebuild:** `python3 -m provenance detect`

### The record, with provenance on every page

The public record itself: ~7,000 plain-text pages. Every page that states a number now carries a section underneath it with the origin link, the cue clip, and the click-path for that number.

- “Where the numbers on this page come from” on every content page
- 3 inline clips per page, and a cue link on every other row
- a standalone /provenance/ cue sheet, and /provenance/master.html — this guide

**Why you would open it:** Read a meeting page, then scroll to the bottom: the numbers in it are sourced there, not in a footer.

**Where it comes from:** tools/render_ai_record.py + provenance/site.py  
**Rebuild:** `python3 tools/render_ai_record.py`

### The app, with the same block

The Streamlit record. Every view that prints a number carries the same provenance block in a collapsed expander, and both films in the footer.

- 🔗 Provenance expander on every page that states a number
- the chapter clip, opened at the beat for that datum
- the two films, on every page, via the footer

**Why you would open it:** Use it the same way as the site: read the view, then open the expander under it.

**Where it comes from:** rwc_provenance.py, wired through rwc_views.py and pages/*  
**Rebuild:** `(no build — reads data/out/provenance-ledger.json at run time)`

### The checks

Two scripts that make the claim testable rather than asserted: one fails the build if a datum loses its link or cue; the other rebuilds the record from scratch and crawls every rendered page.

- check_provenance.py: every datum linked, cued, clip on disk, present on the cue sheet
- provenance_site_audit.py: build → render → crawl every internal link and <video>

**Why you would open it:** Run them before you trust a number, and in CI so nobody ships one that lost its citation.

**Where it comes from:** tools/check_provenance.py, tools/provenance_site_audit.py  
**Rebuild:** `python3 tools/check_provenance.py --site _site`

## The chapter map

Each chapter is one data family, in the chapter film. The cue column is where that chapter starts in `video/provenance-manual-run.mp4`; the clip is the same footage cut out and served beside the numbers on the pages.

| # | chapter | cue in the film | clip | datums it explains |
|---|---|---|---|---|
| 1 | meeting calendar | 0:25–0:40 | `video/clips/01-meeting-calendar-meeting-days.mp4` | 4 |
| 2 | agenda documents | 0:40–0:54 | `video/clips/02-agenda-packets.mp4` | 3 |
| 3 | supporting documents | 0:54–1:09 | `video/clips/03-supporting-documents.mp4` | 3 |
| 4 | minutes and notes | 1:09–1:23 | `video/clips/04-minutes-meeting-notes.mp4` | 4 |
| 5 | transcripts | 1:23–1:38 | `video/clips/05-transcripts-caption-tracks.mp4` | 3 |
| 6 | meeting video | 1:38–1:53 | `video/clips/06-meeting-tape.mp4` | 3 |
| 7 | drive corpus | 1:53–2:07 | `video/clips/07-processed-meetings-database.mp4` | 3 |
| 8 | news | 2:07–2:22 | `video/clips/08-news-coverage.mp4` | 4 |
| 9 | arrests | 2:22–2:36 | `video/clips/09-arrest-reports-de-identified.mp4` | 4 |
| 10 | scanner | 2:36–2:51 | `video/clips/10-scanner-audio-transcripts.mp4` | 4 |
| 11 | open data | 2:51–3:06 | `video/clips/11-open-data-records-probes.mp4` | 4 |

The film opens with a 10s title and a 15s scanner sequence, ends at 3:42, and the showcase version puts the time-lapse (20s) in front of it for 4:02 total.

## Reading a ledger row

Every datum looks like this:

```
| `news.units` | The Daily Ledger, Front Page | 513 | capcity.news | 2:07 | panel @ 2:20 |
```

and means: *513 article / digest items are counted on the Daily Ledger and Front Page pages; the public start of that data is capcity.news; the footage is chapter 8 at 2:07 in the chapter film; and the exact moment the collection panel shows the count is 2:20, which is 13 seconds into that chapter's clip.*

The beats are the same choreography in every chapter:

| beat | what is on screen |
|---|---|
| `type` | the origin URL being typed into the address bar |
| `load` | the real page loading |
| `pick` | the meeting / document row being clicked |
| `item` | the item page with its download control |
| `download` | the download click |
| `collect` | a second row, a second file |
| `save` | the file landing in the archive folder |
| `panel` | the collection panel: units, destination, cost by hand |

## If you only have two minutes

1. Watch `video/provenance-timelapse.mp4` — the whole collection, 20 seconds.
2. Open the chapter for a record you care about, from the cue sheet.
3. Find that number in `data/out/PROVENANCE-LEDGER.md` and click its origin link.

If those three line up, the rest of this page is detail.

## How this differs from the city's own portal

The City of Cheyenne publishes the same council meetings on its own Granicus portal, and that portal is the record of authority. This archive is a reader for it. The two differ in both directions — the portal has the footage and the official viewers; this archive has the other eight bodies, the document text, the transcripts and the provenance. The full comparison, figure by figure, is a generated page:

- on the site: `/provenance/granicus.html`
- in the repo: `data/out/GRANICUS-VS-THIS-ARCHIVE.md` (`python3 -m provenance compare`)

## Rebuild everything, in order

```bash
python3 -m provenance detect                    # classify every file, write the inventory
python3 -m provenance timelapse                 # render the 20-second time-lapse
python3 -m provenance video                     # render the chapter film (~8 min)
python3 -m provenance ledger --clips --showcase # cues, per-chapter clips, showcase
python3 -m provenance guide                     # this page
python3 -m provenance compare                   # portal vs this archive
python3 tools/render_ai_record.py --src ai-record --out _site   # the site, with provenance
python3 tools/check_provenance.py --site _site  # prove every datum still carries its source
```

---

*Silent films, captions only. Names are withheld in arrest material; charges are quoted verbatim. Not an official city website.*
