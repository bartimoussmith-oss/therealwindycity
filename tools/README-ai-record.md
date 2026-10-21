# AI-readable record: how it is built

**Live site (after merge to `main`):** https://bartimoussmith-oss.github.io/therealwindycity/
(also `/llms.txt`, `/sitemap.xml`, `/robots.txt`, and an `.md` twin of every page)

## The problem it solves

Online AI assistants (Google AI Mode, ChatGPT search, Perplexity, Claude, and others) could not
analyze the archive:
- **Agendas, packets, and minutes are PDFs.** They sit in six GitHub repos, and web fetchers and
  search snippets don't open PDFs. Some files are scans with no text; some are web pages saved under a `.pdf` name.
- **The Civic Cheyenne search index samples only a few passages per meeting,** and its pages render in JavaScript.
- **Nothing told a crawler where things are.**

The fix is a static, JavaScript-free mirror:
- One page per meeting. Every document is plain text with page markers, a quality label, and links back to the original file.
- Transcripts carry timestamps that link to the video. The minutes text is inlined on each meeting page.
- Year, body, keyword, statute, and ordinance indexes, plus verified topic pages.
- `llms.txt`, a sitemap, and a robots.txt that welcomes AI crawlers.

## Pipeline

| Step | Script | Output |
|---|---|---|
| 1. Extract | `tools/ai_record_extract.py` | `<sha>.json` per file (PDF text per page, HTML text) + `tree_<repo>.json` |
| 2. OCR (incremental) | `tools/ai_record_ocr.py` | `ai-record-ocr/<sha>.json`: OCR text for image-only pages, **committed** so each run continues the backlog |
| 2b. Caption database | `tools/ai_record_drive.py` | Normalizes `drive-import/master_meetings_database.json.gz` (720 caption transcripts from Google Drive). Each one is attached to its meeting, or gets its own page plus an entry in `indexes/caption-transcripts` |
| 3. Build | `tools/build_ai_record.py` | `ai-record/`: Markdown pages, indexes, topic pages (from `tools/ai_record_static/`) |
| 4. Render | `tools/render_ai_record.py` | `_site/`: HTML + `.md` twins, robots.txt, sitemap.xml, llms.txt |
| 5. Publish | `.github/workflows/ai-record-pages.yml` | GitHub Pages (deploys from `main` only) |

The meeting grouping comes from Civic Cheyenne's own `scripts/build-data.mjs`, so meeting IDs
match the interactive site. Generated output (`ai-record/`, `_site/`) is **not committed**; the
workflow rebuilds it on every change and daily.

## Run it locally

```bash
pip install pymupdf beautifulsoup4 markdown            # + rapidocr-onnxruntime opencv-python-headless wordninja for OCR
git clone --depth 1 https://github.com/therealwindycity/TheReelWindyCity /tmp/fe && (cd /tmp/fe && node scripts/build-data.mjs)
git clone --depth 1 https://github.com/therealwindycity/The-Real-Windy-City- /tmp/tr
python3 tools/ai_record_extract.py --text /tmp/text --trees /tmp/trees          # ~10 min, ~7 GB transient
python3 tools/ai_record_ocr.py --text /tmp/text --cache ai-record-ocr --minutes 30   # optional
python3 tools/build_ai_record.py --meetings /tmp/fe/src/data/meetings.json --text /tmp/text \
  --ocr ai-record-ocr --transcripts /tmp/tr --minutes pipeline/corpus --trees /tmp/trees --drive-db drive-import/master_meetings_database.json.gz --out ai-record
python3 tools/render_ai_record.py --src ai-record --out _site --extra public/index.html=ledger.html
python3 -m http.server -d _site 8080
```

## Editing the hand-written pages

Edit `tools/ai_record_static/` (home page, `llms.txt`, `topics/*`). These placeholders are filled in at build time:
- `{{m:<meeting-id>}}`: a link to the meeting page.
- `{{yt:<meeting-id>@HH:MM:SS}}`: a link to that moment in the transcript plus the YouTube video.
- `{{stat:meetings}}`, `{{stat:documents}}`, `{{stat:pages}}`, `{{stat:transcripts}}`, `{{stat:minutes}}`, `{{stat:years}}`: snapshot counts.

**Rule for topic pages:** only state what the transcript or minutes show, with a timestamp or meeting link.

## Snapshot freshness and publication verification

The homepage now adds a server-rendered **Archive status and coverage** panel,
with `indexes/status.json` carrying the same snapshot metadata. This does not
require JavaScript. Latest indexed date means the maximum date in the meeting
catalog, including posted meetings; it is not evidence of continuous coverage,
a completed meeting, or a verified outcome. Collection-check and verified-outcome
metadata remain null until a provenance-backed implementation records them.
Build timestamps are explicitly separate. Counts describe generated holdings,
not the universe of city records or a whole-corpus OCR backlog.

`status.json` records the build SHA and workflow run ID (local builds use
`local-unversioned`). This metadata is intentionally time-dependent, unlike the
record text. The Pages workflow runs unit tests, checks the rendered artifact,
and after deployment fetches the public site to compare both SHA and run ID.
It also checks the status panel, catalog count consistency, llms.txt, corrections,
data quality, and a sample meeting page. A successful upload alone is no longer
a successful verification. Public checks retry six times for CDN propagation,
then fail visibly rather than claim publication. This is a smoke check, not a
browser rendering test, an exhaustive link audit, or an official-source audit.
The stale-upcoming safeguard detects explicit ISO dates near an “upcoming” label;
it does not interpret all natural-language date formats.

```bash
python3 -m unittest discover -s tools -p 'test_ai_record_status.py' -v
python3 tools/check_ai_record.py --site _site
# Compare a published build to the expected action revision and run:
python3 tools/check_ai_record.py --url https://bartimoussmith-oss.github.io/therealwindycity/ \
  --revision <expected-commit-sha> --run <expected-run-id> --attempts 6
```

### Separate deployments (not interchangeable)

| Address | Project / control boundary |
|---|---|
| https://bartimoussmith-oss.github.io/therealwindycity/ | This repository's plain-text mirror; this workflow verifies it |
| https://therealwindycity.github.io/The-Real-Windy-City-/ | Separate archive repository and Pages workflow |
| https://therealwindycity.github.io/TheReelWindyCity/ | Separate Civic Cheyenne repository and Pages workflow |
| https://therealwindycity.streamlit.app/ | Streamlit app; Pages success does not verify its application health |

Changes here do not fix or redeploy the other repositories. In particular, the
Civic Cheyenne “upcoming” cards and the alternate archive's city-sync/deployment
coupling need fixes in their owning repositories. No live-health claims are
stored in this directory table; inspect each service independently.
