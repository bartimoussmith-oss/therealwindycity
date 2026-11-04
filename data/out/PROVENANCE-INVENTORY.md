# Provenance inventory — what this archive consists of, and where it came from

Generated **2026-11-04T08:19:54Z** by `python3 -m provenance detect` from `/home/user/therealwindycity`.
Read-only: the scanner walks the checkout once and writes only this file and its JSON twin.

## Totals

- **7,430** files classified — **0** unaccounted for
- **1.5 GB** across the working tree
- **836.7 MB** of that is scraped or captured data
- **24** data families
- **13** distinct source hosts cited by the repo itself
- **≈ 9 days 14 h** of hand-work to assemble the same set manually (≈ 44,084 actions at conservative per-document rates)

Manual figures are estimates, not measurements: each family carries a stated `seconds_per_unit` and `actions_per_unit` in `inventory.py`. They exist to size the labour, not to score it.

## Data families

| # | family | class | files | units | size | origin | destination | by hand |
|---|--------|-------|-------|-------|------|--------|-------------|---------|
| 1 | **Meeting calendar & meeting days** | scraped | 7 | 479 meeting days | 8.5 MB | [City of Cheyenne — Minutes and Agendas](https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas) | `data/snapshots/ · 2026-09-14-council/meetings/` | 5 h 19 m |
| 2 | **Supporting documents** | scraped | 14 | 720 attachments | 45.4 MB | [Granicus — Agenda Supporting Documents](https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1126) | `artifacts/Cheyenne_Audit_raw/` | 12 h |
| 3 | **Agenda packets** | scraped | 40 | 720 agenda files | 99.3 MB | [Granicus — Cheyenne AgendaViewer](https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1126) | `artifacts/Cheyenne_Audit_raw/` | 9 h |
| 4 | **Minutes & meeting notes** | scraped | 230 | 720 meeting documents | 78.4 MB | [City of Cheyenne — Minutes and Agendas](https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas) | `uploads/` | 10 h |
| 5 | **Extracted document text** | scraped | 372 | 372 text extracts | 3.2 MB | [City of Cheyenne — Minutes and Agendas](https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas) | `data/text/` | 2 h 35 m |
| 6 | **Meeting tape** | scraped | 9 | 9 meeting recordings | 40.3 MB | [Granicus video archive + City YouTube](https://archive-video.granicus.com/cheyenne/) | `pipeline/videos/` | 27 min |
| 7 | **Transcripts & caption tracks** | scraped | 607 | 607 transcripts | 26.8 MB | [YouTube auto-captions (City of Cheyenne channel)](https://www.youtube.com/@CityofCheyenne) | `pipeline/corpus_yt/` | 15 h 10 m |
| 8 | **Meeting video catalogue** | scraped | 9 | 481 catalogued meetings | 4.5 MB | [Granicus video archive + City YouTube](https://archive-video.granicus.com/cheyenne/) | `youtube-archive/` | 4 h |
| 9 | **Processed meetings database** | scraped | 5 | 720 meeting records | 62.1 MB | [Google Drive — WindyCityMeetings](https://drive.google.com/drive/folders/WindyCityMeetings) | `drive-import/` | 1 day |
| 10 | **News coverage** | scraped | 1,153 | 513 article / digest items | 290.7 MB | [Cap City News + Wyoming Tribune Eagle](https://capcity.news/feed) | `data/out/` | 4 h 16 m |
| 11 | **Arrest reports (de-identified)** | scraped | 5 | 65 records | 4.1 MB | [Laramie County weekly arrest report (via Cap City News)](https://capcity.news/) | `data/arrests/` | 2 h 10 m |
| 12 | **Scanner audio transcripts** | scraped | 601 | 601 radio segments | 5.5 MB | [Broadcastify — Laramie County feed 47003](https://www.broadcastify.com/archives/feed/47003/) | `scanner-results/runs/` | 1 day 1 h |
| 13 | **Open-data & records probes** | scraped | 3 | 2 dataset probes | 33 KB | [Laramie County Sheriff Socrata + LETMSP](https://laramiecountywy-sheriff.data.socrata.com/) | `scanner-results/socrata/` | 8 min |
| 14 | **OCR of scanned documents** | derived | 1,081 | 1,081 scanned documents | 14.3 MB | [Six sibling archive repos (scanned planning documents)](https://github.com/therealwindycity) | `ai-record-ocr/` | 3 days 18 h |
| 15 | **Search / RAG index** | derived | 9 | 1,687 embedded chunks | 27.5 MB | — | `rag/` | — |
| 16 | **Civicwatch mirror** | scraped | 1,581 | 1,581 civic records | 167.8 MB | [YouTube auto-captions (City of Cheyenne channel)](https://www.youtube.com/@CityofCheyenne) | `2026-09-14-council/civicwatch/` | 1 day 2 h |
| 17 | **Analysis & dossiers written from the record** | derived | 138 | 138 documents | 10.8 MB | — | `repo root` | — |
| 18 | **Silent-edit diffs** | derived | 1,217 | 1,217 version diffs | 78.0 MB | — | `data/out/` | — |
| 19 | **Meeting structure & cut lists** | derived | 13 | 13 derived records | 1.8 MB | — | `pipeline/` | — |
| 20 | **Entity database** | derived | 63 | 63 document profiles | 27 KB | — | `Entity_Database/` | — |
| 21 | **Civic atlas (experimental site)** | generated | 24 | 24 page / assets | 117 KB | — | `civic_atlas/` | — |
| 22 | **Field agent tooling** | code | 20 | 20 files | 241 KB | — | `agent/` | — |
| 23 | **Repo metadata & local databases** | code | 23 | 23 files | 28.0 MB | — | `repo root` | — |
| 24 | **Edited reels cut from the tapes** | derived | 37 | 37 film cuts | 528.2 MB | — | `video/ · videos/` | — |
| 25 | **Provenance report & this film** | generated | 10 | 10 artifacts | 153 KB | — | `data/out/ · video/` | — |
| 26 | **Published site & feeds** | generated | 22 | 22 pages | 883 KB | — | `pages/ · public/` | — |
| 27 | **Pipelines, scrapers & console code** | code | 137 | 137 source files | 1.2 MB | — | `engine/ · tools/ · scripts/` | — |

## Where each family came from

### Meeting calendar & meeting days

- **Site:** City of Cheyenne — Minutes and Agendas
- **URL:** https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas
- **Evidence in repo:** config/sources.json → sources[0] (CONFIRMED live 2026-09-05)
- **Note:** Council, Finance, Public Services, Committee of the Whole, Work Sessions.
- **Counts:** 479 meeting nights indexed · 7 city pages captured
- **Samples:** `pipeline/docs/1124/2026-08-10_agenda.html`, `pipeline/docs/1124/2026-08-10_meta_01.html`, `pipeline/docs/1124/2026-08-10_meta_02.html`, `pipeline/docs/1124/2026-08-10_meta_03.html`

### Supporting documents

- **Site:** Granicus — Agenda Supporting Documents
- **URL:** https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1126
- **Evidence in repo:** artifacts/Cheyenne_Audit_raw/*Agenda_Supporting_Document*.pdf (MetaID/Attachment IDs)
- **Note:** Staff reports, plats, ordinances — the attachments behind each agenda item.
- **Counts:** 720 meetings carry attachments · 14 committed here
- **Samples:** `artifacts/Cheyenne_Audit_raw/01_Agenda_Supporting_Document_f333175a4b.pdf`, `artifacts/Cheyenne_Audit_raw/02_Agenda_Supporting_Documents_42ad5a83e5.pdf`, `artifacts/Cheyenne_Audit_raw/03_Agenda_Supporting_Document_a0bbae99c2.pdf`, `artifacts/Cheyenne_Audit_raw/04_Agenda_Supporting_Document_7135c27b3a.pdf`

### Agenda packets

- **Site:** Granicus — Cheyenne AgendaViewer
- **URL:** https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1126
- **Evidence in repo:** youtube-archive/catalog_granicus.csv → agenda_url column
- **Note:** The city links each packet PDF out to Granicus; robots.txt refuses bots.
- **Counts:** 720 agendas linked · 40 packet files committed here
- **Samples:** `2026-09-14-council/meetings/2026-09-14_council/pdf/150411.pdf`, `2026-09-14-council/meetings/2026-09-14_council/pdf/150413.pdf`, `2026-09-14-council/meetings/2026-09-14_council/pdf/150419.pdf`, `2026-09-14-council/meetings/2026-09-14_council/pdf/150421.pdf`

### Minutes & meeting notes

- **Site:** City of Cheyenne — Minutes and Agendas
- **URL:** https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas
- **Evidence in repo:** config/sources.json → sources[0] (CONFIRMED live 2026-09-05)
- **Note:** Council, Finance, Public Services, Committee of the Whole, Work Sessions.
- **Counts:** 720 minutes referenced · 230 saved as text here
- **Samples:** `2026-09-14-council/meetings/minutes/apr13.txt`, `2026-09-14-council/meetings/minutes/apr27.txt`, `2026-09-14-council/meetings/minutes/jul13.txt`, `2026-09-14-council/meetings/minutes/jun08.txt`

### Extracted document text

- **Site:** City of Cheyenne — Minutes and Agendas
- **URL:** https://www.cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas
- **Evidence in repo:** config/sources.json → sources[0] (CONFIRMED live 2026-09-05)
- **Note:** Council, Finance, Public Services, Committee of the Whole, Work Sessions.
- **Samples:** `2026-09-14-council/meetings/2026-09-14_council/txt/150411.txt`, `2026-09-14-council/meetings/2026-09-14_council/txt/150413.txt`, `2026-09-14-council/meetings/2026-09-14_council/txt/150419.txt`, `2026-09-14-council/meetings/2026-09-14_council/txt/150421.txt`

### Meeting tape

- **Site:** Granicus video archive + City YouTube
- **URL:** https://archive-video.granicus.com/cheyenne/
- **Evidence in repo:** youtube-archive/catalog_granicus.csv → mp4_url / player_url
- **Note:** Full tapes; clips are cut from these files, never re-enacted.
- **Samples:** `pipeline/videos/apr27_1301.mp4`, `pipeline/videos/apr27_first.mp4`, `pipeline/videos/apr27_hand.mp4`, `pipeline/videos/apr27_nine.mp4`

### Transcripts & caption tracks

- **Site:** YouTube auto-captions (City of Cheyenne channel)
- **URL:** https://www.youtube.com/@CityofCheyenne
- **Evidence in repo:** pipeline/cityvideos.json + pipeline/corpus_yt/*.txt
- **Note:** Caption tracks converted to timestamped text so moments are findable without video.
- **Counts:** 607 files · 106,487 lines
- **Samples:** `pipeline/corpus/1000_2025-02-10.txt`, `pipeline/corpus/1002_2025-02-24.txt`, `pipeline/corpus/1005_2025-02-25.txt`, `pipeline/corpus/1008_2025-03-11.txt`

### Meeting video catalogue

- **Site:** Granicus video archive + City YouTube
- **URL:** https://archive-video.granicus.com/cheyenne/
- **Evidence in repo:** youtube-archive/catalog_granicus.csv → mp4_url / player_url
- **Note:** Full tapes; clips are cut from these files, never re-enacted.
- **Counts:** 481 meetings catalogued
- **Samples:** `pipeline/cityvideos.json`, `youtube-archive/catalog_archiveorg.csv`, `youtube-archive/catalog_archiveorg.json`, `youtube-archive/catalog_granicus.csv`

### Processed meetings database

- **Site:** Google Drive — WindyCityMeetings
- **URL:** https://drive.google.com/drive/folders/WindyCityMeetings
- **Evidence in repo:** drive-import/manifest.json → source_path /content/drive/MyDrive/WindyCityMeetings/
- **Note:** 720 normalised meeting records with 39.9M characters of caption text.
- **Counts:** 720 meeting records · 39,881,789 chars of speech
- **Samples:** `drive-import/README.md`, `drive-import/manifest.json`, `drive-import/master_meetings_database.json.gz`, `drive-import/master_meetings_database_linked.json.gz`

### News coverage

- **Site:** Cap City News + Wyoming Tribune Eagle
- **URL:** https://capcity.news/feed
- **Evidence in repo:** config/sources.json → cap_city_news_rss, wte_local_rss
- **Note:** WordPress /feed for Cap City; TownNews search-RSS for the Tribune Eagle.
- **Counts:** 513 indexed documents
- **Samples:** `data/out/digest-2026-10-26.md`, `data/out/digest-2026-10-27.md`, `data/out/digest-2026-10-28.md`, `data/out/digest-2026-10-29.md`

### Arrest reports (de-identified)

- **Site:** Laramie County weekly arrest report (via Cap City News)
- **URL:** https://capcity.news/
- **Evidence in repo:** data/arrests/records.json → record.source_url / source_sha256
- **Note:** De-identified public tier; names sealed behind an issue request.
- **Counts:** 65 de-identified records
- **Samples:** `data/arrests/README.md`, `data/arrests/master_records.csv`, `data/arrests/master_records.json`, `data/arrests/records.csv`

### Scanner audio transcripts

- **Site:** Broadcastify — Laramie County feed 47003
- **URL:** https://www.broadcastify.com/archives/feed/47003/
- **Evidence in repo:** scanner-results/runs/*/transcript.json → source segments
- **Note:** Archived radio segments, transcribed locally with whisper; review required.
- **Samples:** `scanner-results/history/quality-sample/47003-1792597004/transcript.json`, `scanner-results/history/quality-sample/47003-1792597004/transcript.txt`, `scanner-results/history/recordings/47003-1776102602/transcript.json`, `scanner-results/history/recordings/47003-1776102602/transcript.txt`

### Open-data & records probes

- **Site:** Laramie County Sheriff Socrata + LETMSP
- **URL:** https://laramiecountywy-sheriff.data.socrata.com/
- **Evidence in repo:** scanner-results/socrata/datasets.json + network.json
- **Note:** Probed honestly: the API answered 403 and the dashboard needed a login.
- **Counts:** 2 datasets probed
- **Samples:** `scanner-results/socrata/connection.json`, `scanner-results/socrata/datasets.json`, `scanner-results/socrata/network.json`

### OCR of scanned documents

- **Site:** Six sibling archive repos (scanned planning documents)
- **URL:** https://github.com/therealwindycity
- **Evidence in repo:** ai-record-ocr/*.json keys are sha1 names from tools/ai_record_extract.py
- **Note:** Scans with no text layer — OCR'd page by page and committed incrementally.
- **Counts:** 1,081 scanned documents OCR'd
- **Samples:** `ai-record-ocr/002d0e1ea250b4b93bc50695a5ce9c63469cad46.json`, `ai-record-ocr/00705c30294d9fd89a7bb706b66d7fd40305855c.json`, `ai-record-ocr/0098d81e1833b29346f46a797a955ed99c40e4e3.json`, `ai-record-ocr/0133b729da72378f744ad505f7e68736acd3cb44.json`

### Search / RAG index

- No external URL appears in this family's files (derived or generated here).
- **Counts:** 1,687 embedded chunks
- **Samples:** `rag/glossary.json`, `rag/glossary_manual.json`, `rag/vectordb_sample/47971f7d-6028-4ce2-9b6a-84016bf4fb04/data_level0.bin`, `rag/vectordb_sample/47971f7d-6028-4ce2-9b6a-84016bf4fb04/header.bin`

### Civicwatch mirror

- **Site:** YouTube auto-captions (City of Cheyenne channel)
- **URL:** https://www.youtube.com/@CityofCheyenne
- **Evidence in repo:** pipeline/cityvideos.json + pipeline/corpus_yt/*.txt
- **Note:** Caption tracks converted to timestamped text so moments are findable without video.
- **Samples:** `2026-09-14-council/civicwatch/civicwatch.py`, `2026-09-14-council/civicwatch/colab_finish.ipynb`, `2026-09-14-council/civicwatch/data/civic.db`, `2026-09-14-council/civicwatch/data/master.log`

### Analysis & dossiers written from the record

- No external URL appears in this family's files (derived or generated here).
- **Samples:** `.github/ISSUE_TEMPLATE/arrest-name-request.md`, `.github/ISSUE_TEMPLATE/tip.md`, `2026-09-14-council/COX_HISTORY_COMPARISON.md`, `2026-09-14-council/DEBRIEF_2026-09-14.md`

### Silent-edit diffs

- No external URL appears in this family's files (derived or generated here).
- **Samples:** `data/out/silent-edit-doc1-seq2.diff.txt`, `data/out/silent-edit-doc1-seq3.diff.txt`, `data/out/silent-edit-doc1-seq4.diff.txt`, `data/out/silent-edit-doc1-seq5.diff.txt`

### Meeting structure & cut lists

- No external URL appears in this family's files (derived or generated here).
- **Samples:** `pipeline/asks/ask_001.json`, `pipeline/asks/ask_002.json`, `pipeline/media_manifest.json`, `pipeline/miller_interventions.json`

### Entity database

- No external URL appears in this family's files (derived or generated here).
- **Samples:** `Entity_Database/ACCESS-TEST-2026-10-16.json`, `Entity_Database/AGENTS.json`, `Entity_Database/CA-pull-kit-2026-08-24.json`, `Entity_Database/DEPLOYMENT-REPAIR-HANDOFF.json`

### Civic atlas (experimental site)

- No external URL appears in this family's files (derived or generated here).
- **Samples:** `civic_atlas/app.js`, `civic_atlas/build_osint_index.py`, `civic_atlas/index.html`, `civic_atlas/lens.js`

### Edited reels cut from the tapes

- No external URL appears in this family's files (derived or generated here).
- **Samples:** `pipeline/build_reel.py`, `pipeline/build_reel_v2.py`, `pipeline/renders/CONTENTION_REEL.mp4`, `pipeline/renders/S1_48_HOURS.mp4`

### Provenance report & this film

- No external URL appears in this family's files (derived or generated here).
- **Samples:** `provenance/__init__.py`, `provenance/__main__.py`, `provenance/art.py`, `provenance/cli.py`

### Published site & feeds

- No external URL appears in this family's files (derived or generated here).
- **Samples:** `locked-resource/index.html`, `pages/10_Front_Page.py`, `pages/11_Mission_Board.py`, `pages/12_Evidence_Vault.py`

## Source sites detected in the repo's own text

| site | host | references |
|------|------|------------|
| Cap City News | `capcity.news` | 12,184 |
| Granicus — Cheyenne | `cheyenne.granicus.com` | 7,915 |
| Wyoming Tribune Eagle | `www.wyomingnews.com` | 5,452 |
| Internet Archive | `archive.org` | 2,608 |
| Granicus video archive | `archive-video.granicus.com` | 1,420 |
| Granicus stream archive | `archive-stream.granicus.com` | 948 |
| Google Drive | `docs.google.com` | 673 |
| Broadcastify | `www.broadcastify.com` | 298 |
| OpenGov — Cheyenne | `cheyennewy.workflow.opengov.com` | 165 |
| WyoBiz | `wyobiz.wyo.gov` | 19 |
| City of Cheyenne | `www.cheyennecity.org` | 14 |
| PlanCheyenne | `www.plancheyenne.org` | 13 |
| Laramie County Sheriff — Socrata | `laramiecountywy-sheriff.data.socrata.com` | 1 |

## Sibling repositories this checkout depends on

- `github.com/therealwindycity/The-Real-Windy-City-` — mentioned 7×
- `github.com/therealwindycity/TheReelWindyCity` — mentioned 7×
- `github.com/therealwindycity/cheyenne-archives-2025-2026` — mentioned 3×
- `github.com/therealwindycity/cheyenne-archives-` — mentioned 2×
- `github.com/therealwindycity/cheyenne-archives-2008-2013` — mentioned 2×
- `github.com/therealwindycity/cheyenne-archives-2022` — mentioned 2×

## Ledger coverage

- `data/engine.db`: 332 documents · 1,549 versions · 1,319 alerts
- Unassigned files: **0**

## How this is measured

1. Walk the tree once, skipping `.git`, caches and build output.
2. Assign each file to exactly one family by path pattern (order matters; first match wins).
3. Count units from the family's own manifests where a file is not a unit (arrest records, meeting records, catalogue rows, dataset probes).
4. Credit a host as an origin only if a URL for it appears inside that family's files.
5. Anything left over is reported, never hidden.

Regenerate the film: `python3 -m provenance video`.

