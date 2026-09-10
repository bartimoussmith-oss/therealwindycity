# Cheyenne, WY — City Government Video Archive → YouTube

Turn the City of Cheyenne's public meeting videos into a searchable, organized
YouTube channel. Everything below is already researched and scripted — you just
run the steps on your own computer.

> **Repo integration:** this wing lives alongside the watchdog engine. Its
> `catalog_granicus.csv` uses the same **clip_id** keys as
> `pipeline/corpus/{clip}_{date}.txt` and `pipeline/docs/<clip>/`, and the
> `rag/` package reads these catalogs for citations and transcript alignment.
> All paths below are relative to this folder.

> **Heads-up on copyright:** you asked to treat these as public domain. The
> practical case is strong (recordings of public meetings, posted as public
> records, with the city itself offering public MP4 downloads), but "public
> record" and "public domain" are not the same thing in law. Read
> `docs/LEGAL_NOTES.md` before you publish. (Not legal advice.)

## What I found

| Source | Coverage | Count | Download from |
|---|---|---|---|
| **Granicus** (`cheyenne.granicus.com`, view 2) | City Council / Governing Body, May 2008 – Aug 2026 | **481 entries, 474 with MP4** | Home internet only (Granicus blocks cloud/VPN IPs with HTTP 403) |
| **Internet Archive** (`cochwy-*` collection) | Council, Finance, Public Services, Planning, work sessions, PSAs, 2012–2026 | **773 items** | Anywhere |
| City's official YouTube (`@TheCityofCheyenne`) | Recent livestreams (Planning, Council) | — | Reference only — don't re-upload these verbatim without adding value |

Merged plan: **`upload_plan.csv`** — 1,254 rows: **1,226 to upload**, 21 exact
same-date duplicates skipped (Granicus wins), 7 agenda-only entries with no
video, plus 127 "possible duplicate" flags for your review (archive.org dates
are often the upload date, 1–3 days after the meeting).

## Project layout

```
cheyenne-archive/
├── README.md                    ← you are here
├── catalog_granicus.csv/json    ← all 481 Granicus entries (clip, date, MP4, agenda, minutes)
├── catalog_archiveorg.csv/json  ← all 773 archive.org items
├── upload_plan.csv/json         ← merged YouTube plan: titles, descriptions, tags, playlists
├── requirements.txt
├── client_secrets.json          ← YOU add this (YouTube API setup, step 3)
├── upload_state.json            ← created by the uploader (resume tracking)
├── videos/granicus/             ← Granicus MP4s land here
├── videos/archiveorg/           ← archive.org MP4s (+ .vtt captions) land here
├── samples/                     ← one verified sample download (proof the pipeline works)
├── scripts/
│   ├── scrape_granicus.py       ← rebuild the Granicus catalog (re-run for new meetings)
│   ├── scrape_archiveorg.py     ← rebuild the archive.org catalog
│   ├── download_granicus.py     ← download Granicus MP4s (run on HOME internet)
│   ├── download_archiveorg.py   ← download archive.org videos + captions
│   ├── build_upload_plan.py     ← rebuild upload_plan.csv after re-scraping
│   └── upload_youtube.py        ← bulk upload to YouTube with resume + playlists
└── docs/
    ├── YOUTUBE_CHANNEL_SETUP.md ← create channel, verify, API keys, quota
    ├── METADATA_TEMPLATES.md    ← About text, descriptions, tags, playlists
    └── LEGAL_NOTES.md           ← public-domain analysis, policies, risks
```

## The workflow (5 phases)

### Phase 1 — Create the channel (1 day)
Follow `docs/YOUTUBE_CHANNEL_SETUP.md`:
1. Google account → new YouTube channel with a clearly **unofficial** name
   (e.g. "Cheyenne Council Archive" — never impersonate the city).
2. **Phone-verify** the account (mandatory: council meetings are hours long and
   unverified accounts cap at 15 minutes).
3. Branding + About text from `docs/METADATA_TEMPLATES.md`.
4. Google Cloud project → enable YouTube Data API v3 → download
   `client_secrets.json` into this folder.

### Phase 2 — Review the plan (1–2 hours)
Open `upload_plan.csv` in Excel/Sheets:
- Delete rows (or set `action=skip`) for anything you don't want — e.g. trim
  the 226 "City Hall Extras & PSAs" if you only want meetings.
- Review the 127 `Possible duplicate` notes; flip confirmed ones to
  `action=duplicate-skip`.
- Titles/descriptions are pre-written; tweak the templates in
  `scripts/build_upload_plan.py` and re-run if you want different wording.

### Phase 3 — Download (days, unattended)
```bash
pip install -r requirements.txt
# Smoke test (newest 3 council meetings):
python scripts/download_granicus.py --limit 3
# Then the full back catalog (run on HOME internet, resume-safe):
python scripts/download_granicus.py
# Committees/Planning/extras from archive.org (works anywhere):
python scripts/download_archiveorg.py
```
- **Storage:** council MP4s run ~0.3–1.5 GB each. Budget **~500 GB–1 TB** for
  everything (external USB drive is fine). Start with one committee to calibrate.
- Re-running is safe: finished files are skipped, partial files resume.

### Phase 3b — Download every agenda + supporting document + minutes
```bash
# Test on one new + one old meeting:
python scripts/download_granicus_docs.py --only 1126 31
# Then everything (~20–40 GB total, several hrs unattended, resume-safe):
python scripts/download_granicus_docs.py
```
- Saves per-meeting folders under `documents/` — `agenda.html`, one PDF per
  agenda item's Supporting Document (descriptive filenames), and `minutes.pdf`
  — plus `documents_manifest.csv` indexing every file with page counts.
- **Unlike the videos, documents download fine from ANY network** (home, work,
  or cloud server) — only the video hosts are CloudFront-restricted.
- What to expect: recent meetings average ~20 supporting PDFs (~25 MB);
  older meetings also have per-item PDFs. Minutes are fetched for every clip
  (the archive table under-reports them — verified).

### Phase 4 — Upload (weeks; quota-limited)
```bash
# Test with one video, unlisted:
python scripts/upload_youtube.py --only-date 2026-08-24 --max 1
# Then daily batches (default API quota ≈ 6 videos/day):
python scripts/upload_youtube.py --max 6 --newest-first
```
- Uploads default to **unlisted** so you can review, then flip to public in
  YouTube Studio (bulk-select → Edit → Public).
- The uploader auto-creates playlists, files each video, attaches captions when
  present, and records every `videoId` in `upload_state.json` so runs resume.
- 1,226 videos ÷ 6/day ≈ **200 days via API**. Speed-ups: request a quota
  extension (free, slow), and/or hand-upload batches in YouTube Studio
  (community-observed ~10–50/day on newer channels). See the setup doc.
- Recommended order: **newest-first** so the channel is useful on day one,
  oldest-first if you prefer a clean chronological backfill.

### Phase 5 — Maintain (15 min/month)
New meetings appear on Granicus after each council session:
```bash
python scripts/scrape_granicus.py
python scripts/build_upload_plan.py
python scripts/download_granicus.py --from-date $(date -d '30 days ago' +%F)  # Linux
python scripts/upload_youtube.py --max 6
```
(Windows PowerShell: replace `$(...)` with the literal date, e.g. `--from-date 2026-08-15`.)

## Tips that will save you pain

- **Don't name the channel like the city.** "City of Cheyenne" / the city seal
  as your avatar risks an impersonation takedown. Use an "Archive (Unofficial)"
  style name and say so in the About page. Details in `LEGAL_NOTES.md`.
- **Monetization:** YouTube's reused-content rules mean a mirror archive will
  almost certainly be ineligible for the Partner Program. Run it as a civic
  project, not a revenue play.
- **Don't upload the city's recent YouTube livestreams verbatim** if they're
  already public on the official channel — prioritize the Granicus back catalog
  (2008–~2022), which is *not* on YouTube. That's your unique value.
- **Captions:** Granicus caption files are empty; archive.org items include
  auto-generated `.vtt`/`.srt` which the scripts download and attach. YouTube
  will also auto-caption everything.

## Quick verification

- `samples/sample_fifth_penny_tax.mp4` (12 MB) was downloaded from archive.org
  during research and verified as a valid MP4 — the pipeline works.
- Granicus MP4/HLS URLs return HTTP 403 from datacenter IPs (verified during
  research); they are expected to work from your home connection, which is why
  the download step runs on your machine.
