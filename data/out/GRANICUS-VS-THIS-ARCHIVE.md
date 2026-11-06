# The city's own archive, and this one — what differs

*Two collections of the same meetings, built for different jobs. Captured 2026-11-04; every figure below is read from a file in this repository.*

The city's portal: <https://cheyenne.granicus.com/ViewPublisher.php?view_id=2>  ·  this archive: <https://bartimoussmith-oss.github.io/therealwindycity/>

## The short answer

The portal is the record of authority: it is where the City Clerk publishes the video, the agenda viewer and the minutes viewer, and it is what an official citation points at. This archive is a reader for that record — the same meetings, plus the documents, transcripts and indexes the portal does not print, and it links back to the portal from every page. It is not a replacement, and it does not re-host any meeting video.

Concretely, the gap runs in both directions:

- **Meetings.** The portal lists 479 council/governing-body clips. This archive carries 1,043 meetings across 9 bodies — every one of those clips, plus the committees, boards and county commission the portal does not list at all.
- **Documents.** The portal serves agendas and minutes as viewer pages; this archive carries 4,686 documents as plain text (57,448 pages).
- **Transcripts.** The portal's captions are searchable inside its player only. Here they are 649 readable transcripts (6,733,904 words).
- **Video.** 474 MP4s and 474 MP3s live on the portal's own server. This archive links to them and hosts none of them.

## Side by side

| | City of Cheyenne portal (Granicus) | This archive |
|---|---|---|
| **what it is** | The city's record of authority. The thing the City Clerk publishes, and the file an official citation points at. | A reader for that record: the same meetings, plus the documents and transcripts the portal does not print, with the portal's link on every page. |
| **bodies covered** | City Council and governing-body sessions only — on every view we read (2, 4, 5, 6, 7). | 9 bodies: council, three committees, work sessions, planning commission, board of adjustment, historic preservation board, urban renewal, and the Laramie County commissioners. |
| **meetings** | 479 council and governing-body clips in the crawled clip list (2 of its 481 rows are vendor training or ceremonies), 2008-05-27 → 2026-08-24. Council only: no committee, board, or county meeting is listed. | 1,043 meetings, 2008–2026, one page each, across 9 bodies. The 479 council clips the portal carries are all here, keyed by clip_id; the rest of the meetings are the bodies the portal never lists. |
| **video** | 474 MP4 files on archive-video.granicus.com, 474 MP3 audio tracks, plus an ASX stream that needs Windows Media Player. | No video of its own. Every meeting page links out to the portal's own player and MP4 — it never re-hosts the footage. |
| **documents** | Agenda and Minutes as viewer pages behind a clip_id, plus the attachments the portal serves inside those viewers. | 4,686 documents as plain text (57,448 pages), each at a predictable URL, no PDF reader and no viewer needed. |
| **transcripts** | Searchable captions inside its own player. No transcript to read, copy, or cite. | 649 caption transcripts as text (6,733,904 words), plus timestamped 2026 transcripts, plus Record of Proceedings text for 463 meetings. |
| **finding things** | A form: name/description, agenda items, attachments, notes, motions/votes, captions; all-words / exact phrase / any-words; a date range. No index pages, no article URLs. | Indexes by year, body, keyword, Wyoming statute and ordinance number, plus a machine index of every meeting at indexes/meetings.json. |
| **stability** | Session URLs: clip_id, doc_id, and viewer pages. The page itself is script-driven. | Static files on GitHub Pages. No JavaScript, no login, no session. Every page also exists as Markdown at the same path. |
| **provenance** | Not applicable — it is the source. | 121 figures, each with the public page it came from, the literal clicks to fetch it, and a film cue showing that fetch; a time-lapse of every file; and two checkers that fail the build if a link or a cue goes missing. |
| **freshness** | The newest row on the portal when this was captured: 2026-10-26. | Meetings are captured from the portal; the clip catalog in this checkout runs to 2026-08-24, so anything posted after that date is linked from the meeting page but not yet counted here. |

## What only the portal has

These are real advantages. If any of them is what you need, use the portal.

- **Authority.** It is the city's own publication. A citation to a meeting should point there, or at the city's own PDF, not at this mirror.
- **The footage itself.** Every council meeting's MP4 and MP3 are served from `archive-video.granicus.com`. This archive only links.
- **Legacy formats.** The ASX / Windows Media Player stream is still how the older rows are offered; the portal keeps that working.
- **The official viewers.** `AgendaViewer.php` and `MinutesViewer.php` with a `doc_id` are the city's own rendering of the agenda and the minutes, including the attachments exactly as posted.
- **Subscriptions and search.** RSS feeds for agendas, minutes, podcast and video podcast; email updates; and a search form that reaches motions, votes, notes and captions.
- **Posting first.** The city posts here first. This archive picks the meeting up afterwards.
- **The newest meetings.** At capture the portal's newest row was **2026-10-26**; the clip catalog in this checkout ends at **2026-08-24**, so the most recent postings are linked from the meeting page but are not yet counted in this archive's own totals.

## What only this archive has

Each of these is checkable on the live site, and each figure has a row in `data/out/PROVENANCE-LEDGER.md` with the page it came from and a film cue.

- **The other eight bodies.** The portal lists City Council. This archive carries Planning Commission, Board of Adjustment, Historic Preservation Board, Urban Renewal Authority, Finance Committee, Public Services Committee, Work Session / Committee of the Whole as a separate index, Laramie County Board of County Commissioners as well, with a page for each meeting.
- **Document text.** 4,686 agendas, packets, supporting documents and minutes as plain text — 57,448 pages — searchable, quotable, and readable without a PDF plugin.
- **Transcripts as text.** 649 caption transcripts (6,733,904 words) plus timestamped 2026 transcripts and 463 official Records of Proceedings as text.
- **Indexes.** By year, by body, by keyword, by Wyoming statute, by ordinance number, and a machine index (`indexes/meetings.json`) that lists every meeting with its URLs.
- **Stable, script-free pages.** No JavaScript, no login, no session, no player. Every page is also a Markdown file at the same path, which is what makes the whole archive readable by a machine as well as a person.
- **Provenance on every figure.** 121 numbers, each with the public page it came from, the clicks to reproduce it, and a film cue of that fetch happening.
- **The films.** A 20-second time-lapse of all 7,466 files, and an 11-chapter film of the fetching, one chapter per kind of record.
- **Material the portal never had.** Local news coverage, the county arrest reports, scanner audio transcripts, open-data pulls, and the OCR of planning documents — 4,636 captured files from 13 public sites.

## Where this archive is behind, or could be wrong

- **It is a mirror, not the record.** If the two disagree, the portal and the city's own PDF are right.
- **Captions are machine-made.** Names and numbers in caption transcripts can be misheard; the site says so on every transcript page, and each one links to the video.
- **OCR is imperfect.** Some scanned packet pages have partial or no text; the site's data-quality page lists them. The inventory assigns every one of its 7,466 files to a family (0 unaccounted for), but a file being counted is not the same as its text being complete.
- **No audio, no video of its own.** If the portal's MP4 or MP3 disappears, this archive can only say where it used to be.
- **The clip catalog lags.** It ends at 2026-08-24; the portal was publishing through 2026-10-26.

## Check any of it

Every claim above resolves to one of these pages:

- <https://bartimoussmith-oss.github.io/therealwindycity/years/2026.html>
- <https://bartimoussmith-oss.github.io/therealwindycity/meetings/2025/city-council-2025-02-24.html>
- <https://bartimoussmith-oss.github.io/therealwindycity/indexes/meetings.json>
- <https://cheyenne.granicus.com/ViewPublisher.php?view_id=2> — the portal side

- view_id=2 — *City of Cheyenne Streaming Media Archive*: City Council / governing-body meetings only, most recent first (5 columns)
- view_id=4 — *Redesign View*: City Council / governing-body meetings only, most recent first (5 columns)
- view_id=5 — *Civicplus View*: City Council / governing-body meetings only, most recent first (3 columns)
- view_id=6 — *OpenCities View*: City Council / governing-body meetings only, most recent first (3 columns)
- view_id=7 — *Training*: Vendor training recordings, not public meetings (3 columns)

## How this page is built

```
python3 -m provenance compare     # writes this file
```

The portal side is read from `data/granicus-portal-snapshot-2026-11-04.json`, which records what each view page showed on the capture date, and from `youtube-archive/catalog_granicus.json`, this repo's own crawl of the portal's clip list. The archive side is read from `pipeline/meetings.json`, `data/out/provenance-inventory.json` and the live site's published statement of scope. If a source is missing, this page says so rather than guessing.

*Not an official city website. Silent films, captions only.*
