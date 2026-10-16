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
  --ocr ai-record-ocr --transcripts /tmp/tr --minutes pipeline/corpus --trees /tmp/trees --out ai-record
python3 tools/render_ai_record.py --src ai-record --out _site --extra public/index.html=ledger.html
python3 -m http.server -d _site 8080
```

## Editing the hand-written pages

Edit `tools/ai_record_static/` (home page, `llms.txt`, `topics/*`). These placeholders are filled in at build time:
- `{{m:<meeting-id>}}`: a link to the meeting page.
- `{{yt:<meeting-id>@HH:MM:SS}}`: a link to that moment in the transcript plus the YouTube video.
- `{{stat:meetings}}`, `{{stat:documents}}`, `{{stat:pages}}`, `{{stat:transcripts}}`, `{{stat:minutes}}`, `{{stat:years}}`: snapshot counts.

**Rule for topic pages:** only state what the transcript or minutes show, with a timestamp or meeting link.
