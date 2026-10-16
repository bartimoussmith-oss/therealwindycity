# Ecosystem access test — what can actually be read and analyzed (2026-10-16)

*Method: the live GitHub API (`gh`) plus a fresh clone of each repo, not web-search
snippets. Every number below was measured in this session. Reproduce it with
`tools/access_audit.py` (see the last section). Two things could not be tested:
`therealwindycity.streamlit.app` and `therealwindycity.github.io`. The test sandbox
could reach github.com but not those hosts, so the site was judged from its
source code and built data files.*

---

## 1. Bottom line

1. **The historical record is real, public, and mostly machine-readable.**
   - Seven archive repos hold **5,122 documents (6.97 GB)**. Of a random sample of 240:
     - **81%** extract as text right away.
     - **4%** are agendas saved as `.pdf` that are really HTML. The text is still recoverable.
     - **13%** are scanned images and need OCR.
     - **~2%** are dead (error pages or empty files).
   - The 2026 transcripts total **1.49 million words across 85 meetings**. They are plain text with timestamps, and 100% can be searched.
   - `pipeline/corpus/` holds **473 extracted minutes texts covering 2008–2026**.
2. **Earlier AI answers that said "I can't read the PDFs or transcripts" were wrong about
   the data.** The limit was in their tools, not in the archive. With a shell and the GitHub API,
   the full record can be pulled, searched, and checked.
3. **The weak link is the public website's search, not the archive.**
   - "Ask the record" indexes **493 items**, including only **3–5 evenly spaced samples per meeting** (the Jan 26, 2026 meeting is the one exception).
   - The **embedded text covers about 5%** of the transcript text, and **none** of the PDF text.
   - Key phrases that are verbatim in the transcripts get **zero hits** on the site: "35-7-1046", "Musco", "viewpoint discrimination", "Ardurra".
4. **Several earlier AI answers mixed real facts with invented or misattributed details.**
   Section 4 corrects them claim by claim.
5. **No one is copying it yet, as far as can be detected.**
   - Every therealwindycity repo has **0 forks and 0 stars**.
   - The only fork in the network is the project's own mirror.
   - GitHub code search found no outside repos using its distinctive strings.

---

## 2. What is in each layer (measured)

| Layer | Contents (measured) | Readable as text? |
|---|---|---|
| `cheyenne-archives-2008-2013` | 1,003 PDFs, 0.86 GB | Sample: 35/40 text, 3 scanned, 2 dead stubs |
| `cheyenne-archives-2014-2017` | 545 PDFs, 1.31 GB | **Worst era:** 23/40 text, **16/40 scanned**, 1 stub |
| `cheyenne-archives-2018-2021` | 834 PDFs, 1.12 GB | 34/40 text, 5 scanned, 1 HTML agenda |
| `cheyenne-archives-2022` | 634 PDFs, 1.27 GB. **The earlier AI answers left this repo out entirely.** | 31/40 text, 5 scanned, 4 HTML agendas |
| `cheyenne-archives-2023-2024` | 1,242 PDFs + 138 `.bin` (PDFs inside), 1.57 GB | 35/40 text, 2 scanned, 3 HTML agendas |
| `cheyenne-archives-2025-2026` | 677 PDFs + 49 `.bin`, 0.84 GB | 37/40 text, 3 HTML |
| `The-Real-Windy-City-` (transcripts) | 85 meeting files, Jan 5 – Sep 22, 2026, 8 bodies, 84 raw VTT caption files | **100%** plain text, timestamped, YouTube-linked |
| `pipeline/corpus/` (this repo) | 473 Record-of-Proceedings texts, 2008–2026 (15–28 per year) | **100%** text. The most useful historical layer. |
| `pipeline/corpus_yt/` (this repo) | 86 cleaned 2026 transcript texts | 100% text |
| `rag/vectordb_sample/` | 1,687 chunks from 4 meetings (clips 1071/1093/1103/1124) | Demo scale only |
| `data/engine.db` (watchdog) | 6 sources, **21 documents**, 14 full-text-indexed, 17 alerts, 1 PRA draft | Small. The watchdog went live on 2026-09-05. |
| `cheyenne_watchdog.db` | 22 hand-curated rows in 4 tables | Curated, not harvested |
| TheReelWindyCity site index | 493 vectors: 397 transcript windows, 91 meeting cards, 5 ordinances | Covers about 5% of transcript text and 0% of PDF text |

**What goes wrong in the archive files:**
- **Agendas that are really HTML.** Granicus agenda pages were saved under a `.pdf` name. Most hold the real agenda, so they parse fine as HTML.
- **Dead files.** About 35 are tiny error pages, for example `Annual Report Page 1.pdf` at 1,592 bytes.
- **The wrong page.** At least one `AgendaLink - Doc.pdf` is a snapshot of the city's homepage, not the agenda.
- **Scanned pages.** These are concentrated in 2014–2017 and include large payables and voucher reports with no text layer.

---

## 3. How well can the data be analyzed?

The ratings measure what analysis is actually possible with direct access, not just with web search.

| Layer | Rating | Why |
|---|---|---|
| Transcripts | **9/10** | Every word is searchable, with timestamps and video links. The main problem is auto-caption errors on names and statute numbers. For example, "W.S. 16-4-403" was transcribed as "statute 16443", and Ardurra as "Adura/Ardura". So **no hit does not prove the words weren't said.** |
| Minutes corpus 2008–2026 | **9/10** | This is the official record of votes, movers, and public commenters. It confirmed outcomes the transcripts only imply, such as the Feb 9 amendment votes. |
| Archive PDFs | **7/10** | About 85% is readable directly, and about 98% could be with OCR. File names carry the date and meeting body. The weak spots are scanned financial reports and mislabeled or dead files. |
| Watchdog engine | **4/10** | The design is sound, with fingerprinting and a robots.txt guard. But it has captured only 21 documents so far. Granicus blocks automated collection, which keeps the engine away from the main record. |
| RAG demo | **4/10** | The retrieval itself works (5/6 test questions pass), but the demo covers only 4 meetings. |
| Website search | **3/10** | It is fast, free, and cites its sources. But it misses most of the record (see Section 1, item 3). |

**A test of real historical analysis.** One script pass over the 2008–2026 minutes counted these terms per year:
- "Microsoft" appears 21 times in 2026 minutes, versus 0–8 in each earlier year.
- "Inspection warrant" first appears in December 2025.
- "Executive session" mentions rose from 0 per year (2018–2020) to 32–43 per year (2021–2023, 2026).

These are keyword counts. They show where to start reading, not conclusions.

---

## 4. Fact-check of the earlier AI answers

| Earlier claim | Verdict | Evidence |
|---|---|---|
| "I cannot access the transcripts or PDF contents" | **Wrong about the data** | All 85 transcripts and 240 sample PDFs were read in this session |
| Archive file counts 545 / 834 / 1,380 / 726 | Correct (those totals include README files) | Tree API |
| Covers 5 archive repos (2008–2013 count unknown) | **Incomplete** | 2008–2013 has 1,003 PDFs. The **2022 repo (634 PDFs) was never mentioned**. |
| Miller cited W.S. 35-7-1046 (district-court judge, pre-notice) | **Verified** | City Council 2026-01-12 [01:10:32]–[01:13:41]; also 2026-01-26 [00:33:43] |
| "Jan 26 was the exact session where Miller's key statutory objections were filed" | **Partly wrong** | The statute was first cited **Jan 12**. Jan 26 was a follow-up with a proposed amendment. |
| "You cannot check a statutory box claiming you are protecting residents who do not exist" | **Verified** | City Council 2026-04-13 [00:54:22], at the W.S. 15-1-402 hearing on 1,259.91 acres near Roundtop / Happy Jack Rd |
| "…1,200-acre blind experiment" | **Verified** | 2026-04-13 [00:55:54] |
| "Ghost project" | **Verified** | City Council 2026-06-22 [00:34:46] ("3500 acre ghost project") and later in the same meeting |
| First Amendment / "limited public forum" / "gag order" quote, attributed to a **Sep 9 Cox Ranch** meeting | **Quote verified, date and meeting wrong** | Public Services Committee **2026-04-20** [02:06:18]–[02:06:50]. The Sep 9 date comes from a Facebook repost. |
| "Study a study of your own failed design" ($186,500 Ardurra) | **Verified, wrong meeting** | Said at Finance Committee **2026-08-18** [00:11:01], not at Council. The contract is with Ardurra **Group, Inc.**, not "Ardurra Engineering." |
| $161,826 Musco mobile video trailer, sole source | **Verified** | Finance Committee 2026-04-21 [01:45:43]–[01:46:00] |
| "$130,000 Downtown PR campaign / sizzle reel" | **Two items merged** | $130,000 was the DDA *communications plan* (2026-04-13 [02:02:44]). "Sizzle reels" referred to the *Musco trailers* (2026-04-27 [02:20:06]). |
| "Financial footprint" strike formula | Phrase found once | Finance Committee 2026-04-21 [00:55:29]. "Signature formula" overstates one use. |
| `aipoison-2026-08-24-audit.md` is the "poison-pill preparation file" for objections | **Wrong** | It is a forensic audit of whether **city documents** resist AI extraction. Its verdict: effect confirmed, deliberate intent **unproven**, most likely platform artifacts. |
| `miller-tonight-speaking-roles.md` proves roles are "assigned in advance" | **Wrong framing** | It is an observer's *prediction* sheet ("Predicted public-comment turns"), not an assignment. |
| V-MAX-Colab-Protocol coordinates multi-resident comment "flooding" | **Made up** | It is a separate February 2026 Vite app ("promethean-v-max", "V-MAX OMEGA") with **zero** mentions of Cheyenne, council, civic, or comment. |
| "Daily validation across 23 counties / 99 municipalities" | **Overstated** | The catalog maps them, but Cheyenne is "the only ecosystem whose watcher is calibrated". The rest are left unfetched. |
| "~525 GB combined archive" | **Arithmetic error** | The figures quoted alongside it (221.9 GB video + 18.9 GB documents) add to about 241 GB |
| "GitHub repos contain no civic records" (from an earlier turn) | **Wrong** | See Section 2 |

---

## 5. Miller's statutory and procedural objections, with outcomes

Every item below was checked against the transcript, and against the official minutes where available.
"Outcome" is what the body did. It is not a claim that the objection caused the outcome.

| Date / body | Objection (verbatim anchor) | Authority invoked | Outcome on record |
|---|---|---|---|
| 2026-01-12 CC [01:10:32] | Ch. 1.28 "uses a municipal judge instead of a district court judge"; no pre-notice; "secret searches" | W.S. 35-7-1046; *City of Los Angeles v. Patel* (2015) | Passed on 2nd reading, 7–3 (Aldrich, Moody, Rinne no). The ordinance number is assigned at final passage (see Feb 9). 1st reading was 2025-12-22. |
| 2026-01-26 CC [00:33:43] | "My amendment forces this ordinance to comply with state law" | W.S. 35-7-1046 | 3rd reading postponed to Feb 9 (unanimous). Miller is listed among the commenters. |
| 2026-02-09 CC [02:42:03] | "Section 1.28.020 B3 contains a fatal defect… **The poison pill** threatens viability". Supported striking "determine, discover" [03:06:44]. | WY Const. privacy (McCoy cited a case captioned "Oil versus State", likely *O'Boyle v. State*); general-warrant doctrine | **Partly adopted.** Aldrich's amendment removing "determine, discover or" from 1.28.020(b)(3) **carried 6–4**. Patricia McCoy brought the strike sheet [02:18–02:19], and Miller backed it. The **municipal-judge provision stayed** (Feb 5 substitute, §1.28.010.A). Ord. **#4656 passed 7–3**. Miller later thanked the council for the warrant reporting requirement [04:21:04]. |
| 2026-04-13 CC [00:54:22] | Vacant land: "protecting residents who do not exist… arbitrary capricious act" | W.S. 15-1-402 annexation conditions | Hearing closed. Annexation and zoning ordinances advanced on 1st reading to PSC. |
| 2026-04-13 CC [02:02:44] | DDA $130,000 communications plan, $45,000 planters, $22M building remodel | Fiscal priority | Not adopted as a change (agenda proceeded) |
| 2026-04-20 PSC [02:06:18] | "Limited public forum… illegal to engage in viewpoint discrimination… gag order" | First Amendment; WY Public Meetings Act (captioned "16443", likely W.S. 16-4-403); procedural due process [03:09:03] | On the record. No ruling recorded on the objection. |
| 2026-04-21 FC [01:45:43] | $161,826 Musco Max 1710, sole source, drawing on the 5th-penny equipment fund and spot funds | Competitive bidding | **Approved unanimously** (moved by Moody, seconded by Wolf). A $50,000 Meta grant was noted. |
| 2026-04-27 CC [03:01:58] | Council's authority on item 12 is "directly tied to its adherence to due process in the first amendment" | 1st Amendment, due process | On the record |
| 2026-06-22 CC [00:34:46] | "Granting municipal jurisdiction to a 3500 acre ghost project" | Annexation statute (vacant-land construction) | Not checked in this pass |
| 2026-07-27 CC [00:45:50] | Transit cameras (~$133,000), "zero competitive bids" | Bidding law | Not checked in this pass |
| 2026-08-04 FC [00:10:56] | "Limited public forum, muzzling a taxpayer for making comparative arguments" | 1st Amendment | The chair challenged him as "rehashing" |
| 2026-08-18 FC [00:09:38]–[00:11:20] | $186,500 Ardurra review: "study a study of your own failed design" | Fiscal (1% sales-tax funds) | **FC split 1–1, no recommendation** [00:16:11]. **Council approved 2026-08-24** [00:40:53] (Moody, Rinne no). |

**Overall pattern:**
- The objections are dense and specific, and almost always on the record with a timestamp.
- One substantive change was adopted (the b(3) strike), and it was shared with other speakers.
- The headline jurisdiction objection (35-7-1046) was not adopted.
- Contested spending items mostly passed. Ardurra is the one where a committee split.

---

## 6. Is anyone copying it?

- **Forks and stars:** 0 on all nine therealwindycity repos. `bartimoussmith-oss/therealwindycity` has 1 fork, and that fork is `therealwindycity/therealwindycity`, the project's own mirror.
- **Code search:** `cheyenne-archives-2008-2013` and `"therealwindycity"` match only the project's own repos, plus unrelated expired-domain lists. Searches for `"calibrated doors"` and `"Ask the record"` return unrelated projects that just contain those words.
- **Limits:**
  - Private clones and downloads are invisible to anyone.
  - GitHub only shows traffic and clone counts to repo admins. Run `gh api repos/therealwindycity/TheReelWindyCity/traffic/clones` and `/traffic/popular/referrers` as the owner to see 14 days of clone counts and referring sites.
  - Copies are easier to spot if the site carries a visible attribution line or a code comment with a unique string, which can be searched for later.

---

## 7. Fixes that would raise the ratings

1. **Website search coverage.** Embed every transcript window, not 3–5 samples per meeting (`windowsFor()` in `scripts/embed-transcripts.mjs`). Also index the text of the minutes corpus.
   - About 85 meetings × ~100 windows is roughly 8,500 vectors, about 3.3 MB as int8. That is still fine for a static site.
   - Alternatively, ship a lexical index of the full text and keep the semantic search for a subset.
2. **OCR the 2014–2017 scans** with `pytesseract`, which is already in `requirements.txt`. Then commit the text next to each PDF.
3. **Rename the HTML "PDFs"** to `.html` (or add a `.txt` extraction next to each). Re-download or flag the ~35 dead stubs.
4. **Add a caption-alias table** for names and statutes (for example, "16443" → 16-4-403). `rag/glossary.json` already started one. This keeps exact-match searches from silently failing.
5. **Grow the watchdog.** Ask the City Clerk for bulk access to Granicus. The engine already drafts the PRA request.

---

## 8. Reproduce

```bash
pip install pypdf beautifulsoup4          # gh CLI must be authenticated
python3 tools/access_audit.py inventory
python3 tools/access_audit.py integrity --per-repo 40 --seed 42
python3 tools/access_audit.py coverage --phrase "35-7-1046" --phrase "Musco" --phrase "viewpoint discrimination"
```
Transcript checks: `git clone https://github.com/therealwindycity/The-Real-Windy-City-` and
grep `cheyenne-2026-transcripts/*/*.md`. The timestamps above match the `[HH:MM:SS]` markers in those files.
