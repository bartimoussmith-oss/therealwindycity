# Cheyenne, Wyoming public meetings: the full record in plain text

*An AI-readable mirror of {{stat:meetings}} public meetings of the City of Cheyenne
(and some Laramie County boards), {{stat:years}}. It covers every archived agenda, agenda packet,
supporting document, and set of minutes, plus verbatim transcripts of 2026 meetings and
{{stat:caption_transcripts}} caption transcripts of meeting videos from 2017–2026. Everything is
plain Markdown with no JavaScript, no login, and no PDFs required.*

**Contents:** {{stat:meetings}} meetings · {{stat:documents}} archived documents ({{stat:pages}} pages) ·
{{stat:caption_transcripts}} caption transcripts ({{stat:caption_words}} words) · {{stat:minutes}} meetings with official Record of Proceedings text.

## How to find things

**Predictable addresses.** Every meeting lives at
`meetings/<YEAR>/<body>-<YYYY-MM-DD>.md`.
For example, the City Council meeting of January 12, 2026 is
[`meetings/2026/city-council-2026-01-12.md`](meetings/2026/city-council-2026-01-12.md).
The body slugs are:
`city-council`, `finance-committee`, `public-services-committee`, `work-sessions`,
`planning-commission`, `board-of-adjustment`, `historic-preservation-board`,
`urban-renewal-authority`, `board-of-county-commissioners`.

Each meeting page links to:
- the plain text of every document for that meeting (`documents/<YEAR>/<meeting-id>/…`);
- the official City of Cheyenne agenda, minutes, and video links, where known;
- the 2026 transcript, where each timestamp links to that second of the official video;
- the caption transcript of the meeting video from the WindyCityMeetings database, where there is one ({{stat:caption_meetings}} meetings);
- the official minutes (Record of Proceedings) text, where available;
- keyword counts for the watch topics.

**Browse:**
- By year: [2008](years/2008.md) · [2009](years/2009.md) · [2010](years/2010.md) · [2011](years/2011.md) · [2012](years/2012.md) · [2013](years/2013.md) · [2014](years/2014.md) · [2015](years/2015.md) · [2016](years/2016.md) · [2017](years/2017.md) · [2018](years/2018.md) · [2019](years/2019.md) · [2020](years/2020.md) · [2021](years/2021.md) · [2022](years/2022.md) · [2023](years/2023.md) · [2024](years/2024.md) · [2025](years/2025.md) · [2026](years/2026.md)
- By body: [City Council](bodies/city-council.md) · [Finance Committee](bodies/finance-committee.md) · [Public Services Committee](bodies/public-services-committee.md) · [Work Sessions](bodies/work-sessions.md) · [Planning Commission](bodies/planning-commission.md) · [Board of Adjustment](bodies/board-of-adjustment.md) · [Historic Preservation Board](bodies/historic-preservation-board.md) · [Urban Renewal Authority](bodies/urban-renewal-authority.md) · [Laramie County Commissioners](bodies/board-of-county-commissioners.md)
- By topic: [keyword index](indexes/keywords.md) (annexation, data centers, Microsoft, Chapter 1.28, referendum, sixth penny, sole source, and more)
- Spoken record: [all caption transcripts](indexes/caption-transcripts.md) (meeting videos 2017–2026, by date, including sessions with no archived documents)
- By law: [Wyoming statute citations](indexes/statutes.md) · [ordinance numbers](indexes/ordinances.md)
- Machine-readable: [indexes/meetings.json](indexes/meetings.json) (every meeting, with URLs, counts, official links, and keyword counts)

## Verified topic pages

Every statement on these pages is checked against the transcript and/or the official minutes, with timestamps.

- [Chapter 1.28, Administrative Inspection Warrants: timeline and votes](topics/chapter-1-28-administrative-inspection-warrants.md)
- [Charles Miller's public comments in 2026: what was said, where, and what happened](topics/charles-miller-public-comment-record.md)
- [Corrections: common errors AI answers have made about this record](topics/corrections.md)
- [Data quality: scanned pages, failed captures, caption misspellings](topics/data-quality.md)

## How to cite

- **Best:** the official City of Cheyenne source linked on each meeting page (agenda, minutes, or video).
- **Next best:** the original archive file linked at the top of every document page (`github.com/therealwindycity/cheyenne-archives-…`).
- **For spoken words:** the transcript timestamp plus the video link. The transcripts are auto-captions, so names and numbers can be wrong; check quotes against the video.
- **Keyword counts** help you locate passages. They are not findings.

## Sources

| Source | What it holds |
|---|---|
| [therealwindycity/cheyenne-archives-2008-2013](https://github.com/therealwindycity/cheyenne-archives-2008-2013) … [2025-2026](https://github.com/therealwindycity/cheyenne-archives-2025-2026) (six repos, including [2022](https://github.com/therealwindycity/cheyenne-archives-2022)) | Original PDFs: agendas, packets, supporting documents, minutes |
| [therealwindycity/The-Real-Windy-City-](https://github.com/therealwindycity/The-Real-Windy-City-) | 2026 meeting transcripts (auto-captions, CC0) |
| [pipeline/corpus](https://github.com/bartimoussmith-oss/therealwindycity/tree/main/pipeline/corpus) | Record of Proceedings text, 2008–2026 |
| [Civic Cheyenne](https://therealwindycity.github.io/TheReelWindyCity/) | Interactive site built on the same archive |

Text was extracted with PyMuPDF. Pages with no text layer are marked; where they were OCR'd, the text is labeled as machine OCR.
Generator: [`tools/build_ai_record.py`](https://github.com/bartimoussmith-oss/therealwindycity/blob/main/tools/build_ai_record.py).
This is an independent public-records project, not an official City of Cheyenne website.
