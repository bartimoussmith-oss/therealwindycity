# Data quality: what to trust and how much

*An honest account of where the text in this record came from and where it can be wrong.*

[Home](../README.md)

## Text status labels

Every document page carries one of these labels:

| Label | Meaning | How much to trust it |
|---|---|---|
| **full text** | The PDF has a text layer, and every page was extracted. | Wording is exact. Table columns may run together. |
| **full text (N pages via machine OCR)** | Some pages were scans and were read by OCR software. | Mostly right, but numbers, names, and spacing may be wrong. Check the PDF before quoting. |
| **partial text** | Some pages are scans with no text and no OCR yet. | Text pages are exact. Missing pages are marked in place. |
| **image-only scan: no text layer** | The whole PDF is pictures of pages. | Open the original. OCR is being added a batch at a time. |
| **agenda saved as an HTML web page** | The archive captured the Granicus agenda web page under a `.pdf` name. | The agenda text is real and recovered. Layout is lost. |
| **capture failed** | The archived file is an error page, the city homepage, or empty. | No content. Use the official link on the meeting page. |

Snapshot totals:
- {{stat:documents}} archived document entries, {{stat:pages}} PDF pages.
- About 23% of PDF pages have no text layer. They are concentrated in 2014–2017 and in large payables and voucher reports.
- About 35 files are failed captures.

## Transcripts (2026)

- These are auto-generated YouTube captions, de-duplicated and grouped by timestamp. **The wording is not edited.**
- Each `[HH:MM:SS]` links to that second of the official video. Use it to check quotes.
- Speaker names are not labeled. Speakers usually identify themselves ("for the record, Charles Miller"), or the chair names them ("Mr. Miller, you can go ahead").
- **A missing hit does not prove something was never said.** Captions often mishear names and numbers. Search for the variants below too.

### Caption alias table (what captions write → what was said)

| Captions often write | Actual name or term |
|---|---|
| Crave, Secret, Segraves | Mr. Segrave (council member) |
| Escoel, Esabel, ESL, Esquivel | Mr. Esquibel (council member) |
| Evans, Emmens, Ern | Dr. Emmons (council member) |
| Aldridge | Dr. Aldrich (council member) |
| Renie, Rainey | Dr. Rinne (council member) |
| Wolf | Mr. Wolfe (council member) |
| Leborn, Lebornne | Mr. Laybourn (council member) |
| Adura, Ardura, A Dura | Ardurra Group, Inc. |
| Gley | Greeley |
| Waltershide | Walterschied |
| 16443 | W.S. 16-4-403 (Wyoming Public Meetings Act) |
| 1149102 | W.S. 11-49-102 |
| Oil versus State | probably *O'Boyle v. State* (Wyoming Supreme Court) |
| Tanga | Topanga |
| agurism | agritourism |
| hypers scale | hyperscale |

## Records of Proceedings (minutes)

- **Where they come from:** the official minutes for City Council meetings, 2008 to August 2026, taken from the city's Granicus MinutesViewer text (`pipeline/corpus`).
- **What they're good for:** the authoritative source for motions, votes, ordinance numbers `(#NNNN)`, and lists of public commenters.

## Known gaps

- Granicus (cheyenne.granicus.com) blocks automated collection in its robots.txt. Some meetings have official links but no archived files.
- Meetings after the latest archive snapshot have only official links and transcripts.
- Some agenda-packet files are named by packet date rather than meeting date, so they can sit one or two days off the meeting they belong to.
