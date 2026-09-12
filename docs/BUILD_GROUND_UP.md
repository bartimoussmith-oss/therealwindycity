# THE REAL WINDY CITY — Ground-Up Build Blueprint
### Every meeting, every board, every code, every law, every case — wired together with RAG + a Granicus-like viewer + guerrilla-free scaling

**Date:** 2026-09-12  
**Goal (user verbatim, consolidated):**  
> All cities history be it from way back machine or internet archive org or granicus or city of Cheyenne etc. Every single meeting every meeting type every board every municipal agencies documents. Entire municipal code and any other applicable law codes state statutes agencies involved in municipal oversight etc. as well as federal laws and case law for Wyoming compiled. Each and every video and meeting built from ground up with multiple layers attached to it via RAG vector and whatever else necessary for database to be built and everything tied together and accessible via a language model or old fashioned human sorting etc. Each and every meeting in my database to contain all supporting documents. Own interface to match similarly to that of the granicus live meeting view where they pull up the documents alongside the ordinance etc. and additional toppings.

**Non-negotiables from prior turns:**
- Do not exclude anything — staff training, etc.
- Additive-only repo, twins stay identical, no file >50MB in git.
- Free guerrilla bootstrap that is better than paid, string together as many free services as needed. Scale to every city in WY, then other states.
- AI built-in, host videos + RAG DBs + docs with room for growth, super cheap, able to run code from it.
- Domain `therealwindycity.com` is **available** — $12-13/yr at Porkbun / Cloudflare Registrar. Streamlit Cloud does NOT support custom domain natively — use Cloudflare Pages front door + proxy or registrar redirect.

---

## 0. TL;DR Architecture — The Free Stack That Beats Paid

```
GitHub (source of truth, unlimited public repos, Actions free 2000 min/mo)
  ├─ pipeline/corpus/         17yr minutes (already 400+ files)
  ├─ pipeline/cityvideos.json 260 YouTube meetings (Finance/PSC/Council/Work Session/Board of Adjustment/Historic Preservation/URA/DDA...)
  ├─ tools/granicus_document_pull.py  v3 — ALL views (2,4,5,6,7 training), ALL meetings, MP4s, RSS, recursive links
  ├─ tools/cheyenne_boards_pull.py    NEW — 26 boards/commissions from cheyennecity.org/Boards-Commissions
  ├─ tools/wayback_pull.py            NEW — CDX API for cheyennecity.org/* + granicus + municode snapshots
  ├─ tools/municode_pull.py           NEW — Cheyenne Municipal Code + UDC
  ├─ tools/wy_statutes_pull.py        NEW — wyoleg.gov Title 01-42 + Constitution PDFs
  ├─ tools/courtlistener_pull.py      NEW — WY Supreme Court 1980-present bulk + API
  ├─ tools/unified_meeting_builder.py NEW — merges everything into one meeting JSON
  └─ engine/llm_router.py             NEW — free-tier LLM fallback chain

Cloudflare Free (the glue for scale)
  ├─ DNS + proxy for therealwindycity.com + *.therealwindycity.com (one subdomain per city)
  ├─ Pages: static Granicus-like viewer (React/Vite) — free unlimited bandwidth
  ├─ R2: 10 GB free, egress ALWAYS free ($0.015/GB after) — store PDFs, docs, captions, chunks.jsonl
  ├─ Workers: API gateway (free 100k req/day)
  ├─ Vectorize: 5M vectors free — or keep Chroma local + sync to R2
  ├─ Workers AI: 10k neurons/day ≈ 1300 LLM responses/day free (Llama 3.1 8B, etc)

Streamlit Cloud Free
  ├─ Unlimited apps — one per city: cheyenne.therealwindycity.com → Streamlit via Cloudflare proxy
  └─ Keeps existing https://therealwindycity.streamlit.app alive

Data
  ├─ Turso (libSQL) free 9GB + 500 DBs — relational ledger (meetings, docs, versions, alerts)
  ├─ Chroma (already in rag/) local + persisted to R2 — vector DB, no torch, ONNX embeddings
  └─ GitHub Releases: audio/video assets (2GB/asset cap) — 130GB total stays out of git

AI Router (free tier string)
  Groq ~1000 req/day (Llama 3.3 70B fast) → Gemini Flash ~1500/day → Cloudflare Workers AI 10k neurons/day
  → OpenRouter free models → Ollama local → extractive fallback (engine/analyze.py already has llm_fn hook)

Video Trick
  Don't host 130GB — index & embed existing YouTube + Granicus MP4s. For offline archive, push to Internet Archive (archive.org) — free unlimited public storage for public records.
```

**Why this beats paid:** R2 egress free (AWS charges), Cloudflare Pages bandwidth free (Vercel/Netlify charge), GitHub Actions free compute, Streamlit free apps, Turso free DB, Chroma free local embeddings. Paid fallback if ever needed: Contabo Storage VPS 6 vCPU/18GB/1TB ~€13/mo or Hetzner CAX11 ~€5.99/mo + R2.

---

## 1. Complete Source Inventory — What Exists

### 1A. Granicus — Cheyenne (verified live via fetch_page)
- **Base:** `https://cheyenne.granicus.com`
- **Views live (probe 1..100):** 
  - `2` Archives (classic) — 479 meetings mapped, 472 MP4s
  - `4` Redesign
  - `5` CivicPlus
  - `6` OpenCities — back to **2008-05-27 clip 24**
  - `7` Training — 8 staff training recordings (LiveManager, Minutes Training, Peak)
  - Dead: 1,3,8-15 (page not found)
- **ID shapes:**
  - `clip_id=N` archived meetings (e.g. 1103 Jun 22/23 2026)
  - `event_id=N` upcoming (e.g. 1441 Sep 14 2026)
  - `doc_id=UUID` 2008-era Uploaded File minutes (e.g. 41f85f2d-633b-4b1f-82c6-7830d7b903e1 → July 28 2008)
  - `meta_id=N` supporting docs + MediaPlayer markers
  - MP4: `https://archive-video.granicus.com/cheyenne/cheyenne_<uuid>.mp4`
  - ASX: `ASX.php?view_id=2&clip_id=N&sn=cheyenne.granicus.com`
  - Minutes: `MinutesViewer.php?view_id=2&clip_id=N` → 302 → `DocumentViewer.php?file=cheyenne_<hash>.pdf&view=1`
  - Agenda: `AgendaViewer.php?view_id=2&clip_id=N` → 302 → `GeneratedAgendaViewer.php`
- **RSS:** `ViewPublisherRSS.php?view_id=N&mode=agendas|minutes|podcast|vpodcast` — surfaces meetings HTML listing omits
- **Robots:** `User-agent: * / Disallow: /` but allows Googlebot crawl-delay 10. Position as single-owner throttled public-records pull (same as hand-opening). Existing puller already respects DELAY=1.5s.
- **Status:** `tools/granicus_document_pull.py` v3 does full sweep, recursive in-doc hyperlink following (PDF embedded links + URLs in text), raw href inventory, MP4 catalogue + optional download, manifest.json with sha256. **Sandbox egress blocked** — must run in Colab. Colab cell:
  ```python
  !git clone --depth 1 https://github.com/bartimoussmith-oss/therealwindycity.git
  %cd therealwindycity
  exec(open('tools/granicus_document_pull.py').read())
  ```
  OUT_ROOT default `/content/drive/MyDrive/TheRealWindyCity/cheyenne` — confirm user's Drive path.

### 1B. City of Cheyenne Website — cheyennecity.org
- **Boards / Commissions (26, verified 2026-09-12):**
  Active Transportation Advisory Committee, Affordable Housing Task Force, Board of Adjustment, Building Code Board of Appeals, Cheyenne Housing Authority Board, Cheyenne-Laramie Co. Economic Development JPB, Cheyenne Passenger Rail Commission, City/County Health Board, Community Action of Laramie County, Community Technology Advisory Council, Contractor Licensing Board, Downtown Development Authority, Fire Civil Service Commission, Friends of the Botanic Gardens, Greenway Advisory Committee, Historic Preservation Board, Housing and Community Dev Advisory Council, Innovation and Entrepreneur Advisory Council, International Fire Code Board of Appeals, Mayor's Council for People with Disabilities, Mayor's Youth Council, MPO Citizen's Advisory Committee, Planning Commission, Police Civil Service Commission, Public Transit Advisory Board, Tourism Promotion Joint Powers Board, Urban Renewal Authority.
- **Plus:** City Council (Council, Finance Committee, Public Services Committee, Committee of the Whole, Work Sessions), BOPU Board (separate domain cheyennebopu.org), Laramie County Commissioners (laramiecountywy.gov — disabled in sources.json pending path verification).
- **File pattern discovered:** COTW files `wscow-2026/cow-MM-DD-YY-{agenda,minutes}.pdf` — guessable, fetchable. City Minutes-and-Agendas page posts direct DocumentViewer minute PDFs for every GB meeting 2025-26.
- **What to pull:** Each board has its own agendas/minutes page — need `tools/cheyenne_boards_pull.py` that enumerates `cheyennecity.org/Your-Government/Boards-Commissions/<Board>` and scrapes linked PDFs + linked Granicus clips.
- **Wayback for history:** Many older board minutes deleted — CDX API recovers them.

### 1C. YouTube — City Channel (already indexed)
- `pipeline/cityvideos.json` = 260 meetings (Finance, PSC, Council, Work Session, Board of Adjustment, Historic Preservation, URA, etc.) with YouTube IDs.
- Example: 2026-03-09 `19tQtLA8klo` Miller cut, 2026-04-27 `y9vnXtjZpR0` nine Miller recognitions, 2026-06-22 `RjSGlhh4q9s` Wolfe POO.
- Existing `tools/colab_media_backfill.py` — captions → `pipeline/captions/` (in git, searchable), audio → GitHub Releases, video 480p → Releases. Resumable batch commits of 10.
- Auto-captions are machine transcripts — good for search/jump, not quotable like clerk record. Cleaned transcripts in `pipeline/corpus_clean/` via `rag/clean_transcripts.py` (42k lines deduped, glossary corrections logged).

### 1D. Wayback Machine + Internet Archive
- **CDX API:** `https://web.archive.org/cdx/search/cdx?url=cheyennecity.org/*&output=json&fl=timestamp,original,mimetype,statuscode&filter=statuscode:200&collapse=digest`
- **Raw fetch:** `https://web.archive.org/web/{timestamp}id_/{original}` — `id_` suffix strips toolbar, essential for binaries.
- **Use cases:**
  - Recover deleted agendas/minutes (city site deletes old files, Granicus view 5/6 may still have them but not linked)
  - Recover old cheyennecity.org redesigns (board pages changed CMS)
  - Recover Municode old versions (Municode has Previous Versions UI)
  - Recover cheyenne.granicus.com old ViewPublisher listings (pre-2012)
- **Tool:** `tools/wayback_pull.py` — query CDX for each host, dedupe by digest, download raw, store in `granicus_pull/wayback/<host>/` with manifest.
- **Bulk tips:** `wayback-machine-downloader` Ruby gem `gem install wayback_machine_downloader; wayback_machine_downloader https://cheyennecity.org --from 2008 --to 2026` or CDX + wget loop with `sleep 1` to avoid throttle.
- **Internet Archive Search:** `https://archive.org/search?query=cheyenne+city+council` — may have citizen uploads of meetings.

### 1E. Municipal Code + UDC
- **Cheyenne City Code:** Municode library `https://library.municode.com/wy/cheyenne/codes/code_of_ordinances`
  - Supplement 73, updated Jun 25 2026, codified through Ord 4662 Mar 23 2026
  - Municode is JS-heavy — HTML fetch returns "Loading..." — need headless browser or CivicPlus API reverse.
  - Structure: Title 1 General Provisions, Title 2 Admin/Personnel, Title 3 Revenue/Finance, Title 5 Business Licenses, Title 6 Animals, Title 8 Health/Safety, Title 9 Public Peace/Welfare, Title 10 Vehicles/Traffic, Title 12 Streets/Sidewalks, Title 13 Public Services, Title 15 Buildings/Construction, plus UDC (Unified Development Code) separate.
  - Previous Versions available via Municode UI — need to scrape all supplements to get history.
  - **Alternative:** City Clerk page `cheyennecity.org/Your-Government/Departments/City-Clerk/City-CodeUDC` links to Municode but also may have PDF of UDC.
- **UDC:** Unified Development Code — the zoning bible. Need full text + amendment history.
- **Tool:** `tools/municode_pull.py` — use Playwright/Selenium to render Municode, walk TOC, save each Title/Chapter as HTML + extracted text + PDF print. Also pull Previous Versions. Store in `cities/cheyenne/code/municode/<title>/`.
- **Free fallback:** If Municode blocks, use Wayback CDX for `library.municode.com/wy/cheyenne/*` — often has older snapshots.

### 1F. Wyoming State Statutes
- **Source:** `https://www.wyoleg.gov/stateStatutes/StatutesDownload` — verified live, lists PDFs for Constitution + Titles 1-42 + 99.
- **Downloadable now (2026 Budget Session, effective Jul 1 2026):**
  - `title97.pdf` Constitution
  - `title01.pdf` Civil Procedure ... `title15.pdf` Cities and Towns (CRITICAL), `title16.pdf` City/County/State/Local Powers, `title34.pdf` Property, etc. Full list 43 files.
- **Tool:** `tools/wy_statutes_pull.py` — download all PDFs, pdfplumber to text, chunk by section (e.g. `15-1-402` annexation compliance hearing, `15-1-407` city-owned land annexation, `15-1-505/506` PC vote thresholds, `16-4-201..205` PRA, `16-4-405(a)(vii)` exec session). Build `cities/cheyenne/law/wy_statutes/<title>.txt` + structured JSON `statutes.json` with section index.
- **Storage:** ~50-100 MB total, fits in R2 free.

### 1G. Federal Laws
- **Sources:**
  - eCFR `https://www.ecfr.gov` — bulk via API `https://www.ecfr.gov/api/versioner/v1/full/...`
  - US Code via `https://uscode.house.gov/download/download.shtml` + govinfo `https://www.govinfo.gov/bulkdata`
  - For municipal relevance: 42 USC 1983 (civil rights), 5 USC 552 FOIA, Fair Housing, etc.
- **Tool:** reuse `wy_statutes_pull.py` with `--federal` flag — pull relevant titles, or at minimum link via API rather than bulk store (keep free tier small).
- **Initial scope:** Keep federal as API-linked, not full bulk — full US Code is huge. Focus on sections cited in Cheyenne minutes (Title VI, FTA 5339, etc. already in PULL doc).

### 1H. Case Law — Wyoming
- **Wyoming Supreme Court:**
  - Official: `https://www.courts.state.wy.us/opinions/` + `https://www.wyocourts.gov/` — opinions 2006-present free, searchable
  - FindLaw: `https://caselaw.findlaw.com/court/wy-supreme-court` — 1980-present
  - CourtListener bulk: `https://www.courtlistener.com/help/api/bulk-data/` — CSV dumps of courts, dockets, opinion clusters, opinions (largest file), citations map. Generated quarterly. Example: `aws s3 sync s3://com-courtlistener-storage/bulk/ --no-sign-request` — but note embeddings 2TB incurs $200 AWS fee.
  - CourtListener API: `https://www.courtlistener.com/api/rest/v4/` — `Authorization: Token <token>`, free account 5/min, 50/hour, 125/day as of May 2026 (higher behind membership). Official Python SDK `courtlistener-api-client`.
- **What matters for Cheyenne:** Annexation cases (e.g. contiguity, 15-1-402 compliance, enclave annexation), zoning, DDA, BOPU water, referendum, municipal home rule (Title 15). Need to filter by `court=wy` + citation to Title 15.
- **Tool:** `tools/courtlistener_pull.py` — two modes: bulk CSV import (for full archive) + API search `q=Cheyenne annexation` + `court=wy`. Save to `cities/cheyenne/law/case_law/<citation>/opinion.txt` + metadata JSON with citations.
- **Free tier:** Use bulk CSV (free, no rate limit) for historical, API for recent. Store text in R2, embeddings in Vectorize/Chroma.

### 1I. Oversight Agencies
- Wyoming Ethics Commission, Wyoming Public Service Commission, Wyoming Dept of Environmental Quality (for BOPU, water), Wyoming State Auditor, Laramie County Clerk, etc.
- Their meeting minutes often not in Granicus — separate sites. Add to `config/sources.json` as new sources, reuse engine/ingest.py polite harvester (already honors robots.txt, 3s delay).

---

## 2. Unified Data Model — One Meeting, All Layers

**Central object:** `cities/<city_slug>/meetings/<clip_id>.json` (or `<event_id>.json`)

```json
{
  "city": "cheyenne",
  "state": "wy",
  "clip_id": 1103,
  "event_id": null,
  "date": "2026-06-22",
  "body": "City Council",
  "title": "City Council - 06-22-26",
  "views": [2,4,5,6],
  "sources": {
    "granicus": {
      "agenda_url": "https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1103",
      "agenda_html": "cities/cheyenne/meetings/1103/agenda.html",
      "agenda_txt": "cities/cheyenne/meetings/1103/agenda.txt",
      "minutes_url": "https://cheyenne.granicus.com/DocumentViewer.php?file=cheyenne_964bdd57...pdf",
      "minutes_pdf": "cities/cheyenne/meetings/1103/minutes.pdf",
      "minutes_txt": "cities/cheyenne/meetings/1103/minutes.txt",
      "mp4_url": "https://archive-video.granicus.com/cheyenne/cheyenne_09f1fb45....mp4",
      "mp4_local": "cities/cheyenne/meetings/1103/video/meeting.mp4",
      "asx_url": "https://cheyenne.granicus.com/ASX.php?view_id=2&clip_id=1103&...",
      "media_markers": [{"meta_id": 148913, "title": "1. CALL TO ORDER", "t": 0}],
      "supporting_docs": [
        {"meta_id": 148918, "title": "Staff Report", "url": ".../MetaViewer.php?...", "file": "cities/cheyenne/meetings/1103/docs/staff_report.pdf", "sha256": "..."}
      ],
      "rss": ["https://cheyenne.granicus.com/ViewPublisherRSS.php?view_id=2&mode=agendas"]
    },
    "youtube": {
      "id": "RjSGlhh4q9s",
      "url": "https://www.youtube.com/watch?v=RjSGlhh4q9s",
      "captions_vtt": "cities/cheyenne/meetings/1103/captions.vtt",
      "captions_clean": "cities/cheyenne/meetings/1103/captions_clean.txt",
      "audio_m4a": "https://github.com/.../releases/download/media-2026/2026-06-22_meeting.m4a"
    },
    "city_site": {
      "agenda_pdf": "https://www.cheyennecity.org/.../cow-06-22-26-agenda.pdf",
      "minutes_pdf": "https://www.cheyennecity.org/.../cow-06-22-26-minutes.pdf"
    },
    "wayback": [
      {"timestamp": "20260623...", "original": "https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id=1103", "file": "wayback/..."}
    ]
  },
  "agenda_items": [
    {
      "no": "18",
      "title": "Annexation Ordinance PUDC-26-37 (Cox Ranch)",
      "ordinance_no": "4687?",
      "sponsor": "Dr. Emmons",
      "documents": [".../docs/staff_report.pdf", ".../docs/annex_map.pdf"],
      "video_start": 3600,
      "video_end": 5400,
      "municipal_code_refs": ["1.16.050", "15.??"],
      "wy_statute_refs": ["15-1-402", "15-1-407"],
      "case_law_refs": ["..."],
      "transcript_snippet": "...",
      "toppings": {
        "ordinance_history": [{"date": "2026-04-13", "action": "introduced", "clip_id": 1091}, ...],
        "entity_mentions": ["AVI Professional Corp", "Cox Ranch LLC", "Gay Woodhouse"],
        "contention_score": 0.92,
        "pra_draft": "cities/cheyenne/meetings/1103/pra/18.md"
      }
    }
  ],
  "law_layers": {
    "municipal_code": ["Title 1 Ch 1.16", "Title 15 Buildings"],
    "udc": ["Sec 2.1.3 BP Business Park"],
    "wy_statutes": ["15-1-402", "15-1-407", "15-1-505", "15-1-506", "16-4-201"],
    "federal": ["42 USC 1983"],
    "case_law": [{"cite": "2026 WY 15", "title": "Smith v. City of Cheyenne", "url": "..."}]
  },
  "embeddings": {
    "chunks": 45,
    "vectordb": "rag/vectordb/cheyenne_1103"
  }
}
```

**Why this matches Granicus live view:**
- Granicus MediaPlayer has left video + center agenda list that jumps video + right document pane that shows staff report / ordinance alongside. Our JSON has `agenda_items[].video_start`, `documents`, and `municipal_code_refs` — frontend can render same three-pane layout.
- Additional toppings: ordinance history (already built `engine/ordinance_index.py` → `pipeline/ordinance_history.json` 153 ordinances / 309 mentions), contention reel scores, entity dossiers, PRA drafts, watchlist alerts, case law citations, transcript search.

---

## 3. RAG — Multi-Layer Vectors

**Existing:** `rag/build_vector_db.py` chunks cleaned transcripts + minutes + supporting docs with metadata `clip_id, date, body, source_type, source_file, source_url, item_ref, page, t_start, t_end`. Hybrid retrieval in `rag/query.py` — vector (Chroma, n_fetch=k*10) + keyword (word-boundary for short terms, substring for long, crude stemming) + RRF fusion + keyword-star promotion + stable tiebreak. Sample DB `rag/vectordb_sample` 1687 chunks.

**Ground-up upgrade — 6 layers:**

1. **Verbatim layer:** minutes text (`pipeline/corpus/*.txt`), agenda HTML text, supporting docs PDF text. Source_type `minutes|agenda|supporting_doc`. Already done.
2. **Transcript layer:** YouTube auto-captions VTT → cleaned `corpus_clean/*.clean.txt` with timestamps `[HH:MM:SS-HH:MM:SS]`. Source_type `transcript_clean`. Chunk 3 segments per chunk to preserve context. Includes `t_start, t_end` for video jump.
3. **Legal layer — municipal code:** Municode titles chunked by section (e.g. Title 1 Chapter 1.16 Section 1.16.050). Metadata `source_type=municipal_code`, `item_ref=1.16.050`, `source_url=municode URL`. Tag `[Cheyenne Municipal Code | Title 1 | 1.16.050]`.
4. **Legal layer — WY statutes:** Title 15, 16, etc. Chunk by statute section (e.g. `15-1-402`). Metadata `source_type=wy_statute`, `item_ref=15-1-402`. Tag `[WY Statute | Title 15 | 15-1-402]`.
5. **Legal layer — case law:** CourtListener opinions chunked, metadata `source_type=case_law`, `cite=2026 WY 15`, `court=wy`. Tag `[WY Supreme Court | 2026 WY 15]`.
6. **Entity layer:** People, orgs, ordinances, resolutions from `engine/entity_index.py` + `rag/glossary.json` (31k entries). Metadata `source_type=entity`.

**All layers in one Chroma collection** `cheyenne_meetings` with filterable metadata — query can restrict `where={"source_type": "wy_statute"}` or `where={"clip_id": "1103"}` or hybrid across layers: "Show me every meeting where 15-1-402 was cited and what case law says about it" → vector search across meeting chunks + statute chunks + case law chunks, then RRF fusion.

**Storage:** `chunks.jsonl` portable manifest next to persist dir — already written by `build_vector_db.py`. Sync to R2 for free backup. For scale, Cloudflare Vectorize supports 5M vectors free — migrate by uploading chunks.jsonl.

**Embeddings:** Chroma default ONNX `all-MiniLM-L6-v2` — no torch, no API key, works offline after first model download. For better legal retrieval, optional `BAAI/bge-small-en-v1.5` (still ONNX). Pin in `rag/requirements-rag.txt`.

---

## 4. Interface — Granicus-Like Viewer + Toppings

**Granicus MediaPlayer anatomy (to match):**
- Left: video player (Granicus uses Windows Media / MP4). Ours: HTML5 video with `archive-video.granicus.com` MP4 + YouTube embed fallback.
- Center: agenda outline — each item clickable, jumps video to `meta_id` timestamp. We have `media_meta_ids` from agenda parsing.
- Right: document viewer — shows supporting doc PDF / staff report alongside ordinance. We have `MetaViewer.php?meta_id=N` docs.
- Bottom: captions / transcript.

**Our toppings (beyond Granicus):**
- Ordinance history column (already in contention reel context pane) — per mention tape jumps across every body
- Entity dossiers — click "AVI Professional Corp" → all meetings, docs, votes where it appears (from `engine/entity_index.py`)
- Contention score — 17-min autoplay looping reel of 9 most contentious moments (already built `pipeline/build_reel.py`)
- Watchlist alerts — verbatim quote + source URL + fetch timestamp (engine/analyze.py)
- PRA draft generator — Wyoming PRA W.S. 16-4-201..205, drafts for human to send (engine/records.py)
- Case law pane — "This annexation cites 15-1-402 — here are 3 WY Supreme Court opinions interpreting it"
- Municipal code pane — "This rezoning AG→BP references UDC Sec 2.1.3 — here is full text"
- Transcript search + jump — `pipeline/corpus/` 17yr minutes searchable, captions VTT searchable
- Video vault — 260 YouTube meetings with captions + audio releases (already `pages/1_Screening_Room.py`)

**Tech for viewer:**
- Option A (Streamlit, fastest): Extend `streamlit_app.py` twins with custom component — `st.video` + `st.columns(3)` + `st.pdf_viewer`? Streamlit lacks PDF side-by-side sync — use `streamlit-pdf-viewer` community component.
- Option B (Cloudflare Pages, scales): React + Vite + `react-pdf` + `hls.js` for MP4 + `youtube-player` + Chroma client. Free hosting, custom domain `cheyenne.therealwindycity.com`. Streamlit app proxies to it or embeds via iframe.
- **Recommendation:** Build both — Streamlit for quick iteration, Pages for production custom domain. Pages app reads same `cities/cheyenne/meetings/*.json` from R2.

---

## 5. Tools — What to Build (all additive, all <50MB)

| Tool | Input | Output | Free infra |
|------|-------|--------|------------|
| `tools/granicus_document_pull.py` v3 (done) | view_id 1..100 auto-discover, RSS, clip/event/doc_id | `granicus_pull/<id>/agenda.html/.txt, docs/*.pdf, video/*.mp4, manifest.json` | Colab + Drive |
| `tools/cheyenne_boards_pull.py` | `cheyennecity.org/Boards-Commissions` list 26 boards, each board page | `cities/cheyenne/boards/<board>/minutes/*.pdf`, `agendas/`, `manifest.json` | GitHub Actions + R2 |
| `tools/wayback_pull.py` | CDX API `cheyennecity.org/*`, `cheyenne.granicus.com/*`, `library.municode.com/wy/cheyenne/*` | `wayback/<host>/<timestamp>_<url>.html`, deduped by digest | GitHub Actions, sleep 1 between fetches |
| `tools/municode_pull.py` | Municode Cheyenne TOC, Supplement 73 | `cities/cheyenne/code/municode/<title>/<chapter>.html/.txt`, `previous_versions/` | Playwright in Actions, or Wayback fallback |
| `tools/wy_statutes_pull.py` | `wyoleg.gov/statutes/compress/title*.pdf` (43 files) | `cities/cheyenne/law/wy_statutes/<title>.txt`, `statutes.json` index by section | Actions, pdfplumber |
| `tools/courtlistener_pull.py` | CourtListener bulk CSV + API `court=wy` | `cities/cheyenne/law/case_law/<cite>/opinion.txt`, `metadata.json` | Actions, bulk S3 sync |
| `tools/unified_meeting_builder.py` | All above + cityvideos.json + corpus/ | `cities/cheyenne/meetings/<clip_id>.json` unified model | Actions, local |
| `engine/llm_router.py` | Prompt | Response via Groq→Gemini→CF Workers AI→OpenRouter→Ollama→extractive | Free tier chain, key via GitHub Secrets |
| `cities/<slug>/seed-city` | Template | New city folder with config.yaml, sources.json, boards list | CLI |

**Example CDX queries for wayback_pull.py:**
```bash
# All cheyennecity.org captures 2008-2026
curl "https://web.archive.org/cdx/search/cdx?url=cheyennecity.org/*&output=json&fl=timestamp,original,mimetype,statuscode,digest&filter=statuscode:200&collapse=digest&from=20080101&to=20261231"
# Raw fetch
curl "https://web.archive.org/web/20260623120000id_/https://cheyennecity.org/Your-Government/City-Council/Minutes-and-Agendas"
```

**Example wy_statutes_pull.py:**
```python
import urllib.request, pathlib, subprocess
BASE="https://wyoleg.gov/statutes/compress"
for title in ["title97"]+[f"title{i:02d}" for i in range(1,43)]+["title99"]:
  url=f"{BASE}/{title}.pdf"
  data=urllib.request.urlopen(url).read()
  pathlib.Path(f"cities/cheyenne/law/wy_statutes/{title}.pdf").write_bytes(data)
# then pdfplumber to text, regex r"\d+-\d+-\d+" for sections
```

**Example courtlistener_pull.py:**
```python
# bulk
# aws s3 sync s3://com-courtlistener-storage/bulk/ ./bulk --no-sign-request --exclude "*" --include "*opinion*"
# api
import requests
r=requests.get("https://www.courtlistener.com/api/rest/v4/search/?q=Cheyenne+annexation&type=o&court=wy",
  headers={"Authorization": "Token YOUR_TOKEN"})
```

---

## 6. Free Guerrilla Stack — Cost Breakdown

| Component | Free tier | Paid fallback |
|-----------|-----------|---------------|
| Domain therealwindycity.com | $12/yr Porkbun/Cloudflare Registrar | - |
| DNS + proxy | Cloudflare free unlimited | - |
| Static frontend | Cloudflare Pages free unlimited bandwidth | - |
| Docs / PDFs / chunks | R2 10GB free, egress free | $0.015/GB after |
| API gateway | Workers free 100k req/day | $5/mo for 10M |
| Vectors | Chroma local + R2, or Vectorize 5M vectors free | - |
| LLM | Groq 1k/day + Gemini 1.5k/day + CF Workers AI 10k neurons/day ≈ 1300/day | OpenRouter $0 |
| Relational | Turso 9GB free, 500 DBs | - |
| Compute | GitHub Actions 2000 min/mo free (public repo) | - |
| Video/audio | YouTube embed (free) + GitHub Releases (free) + Internet Archive (free unlimited public) | - |
| Apps | Streamlit Cloud free unlimited apps (one per city) | - |
| CI | GitHub Actions civic-cycle every 6h + meeting-watch hourly | - |

**Storage estimate Cheyenne full:**
- Minutes text: 472 meetings * ~20KB = ~10 MB (already in pipeline/corpus/)
- Supporting docs PDFs: 479 meetings * ~5 docs * ~2MB = ~4.8 GB
- Captions VTT: 260 * ~100KB = 26 MB (in git)
- Audio m4a 64kbps: 260 * 2h * 28MB/h ≈ 14.5 GB → GitHub Releases
- Video 480p: 260 * 2h * 400MB/h ≈ 208 GB → Internet Archive + Releases (not in git)
- Municipal code: ~50 MB text
- WY statutes: ~100 MB PDFs → ~20 MB text
- Case law WY: ~10k opinions * ~20KB = 200 MB text
- Vectors: 10k chunks * 384 dim * 4 bytes ≈ 15 MB + metadata
- **Total text + docs (no video): ~5-6 GB fits R2 free 10GB.** Video via embed trick stays free.

---

## 7. City Factory — Scale to Every City in WY, Then States

**Structure:**
```
cities/
  cheyenne/
    config.yaml      # city name, state, granicus domain, municode slug, youtube channel, boards list
    sources.json     # mirrors config/sources.json but city-specific
    boards/          # per-board minutes/agendas
    code/municode/   # municipal code
    law/wy_statutes/ # statutes (shared across WY cities, symlink)
    law/case_law/    # case law (shared)
    meetings/        # unified meeting JSONs
  laramie/
    config.yaml      # granicus: laramie.granicus.com, municode: laramie, etc.
  casper/
  ...
```

**Seed script:** `tools/seed-city.py <slug> <state> --granicus <domain> --municode <slug> --youtube <channel>`
- Copies template from `cities/_template/`
- Generates `config.yaml` with discovered views (probe 1..100)
- Creates GitHub Action workflow `civic-cycle-<slug>.yml`
- Creates Streamlit app stub `cities/<slug>/app.py` that loads meetings from R2
- Creates Cloudflare Pages subdomain `<slug>.therealwindycity.com`

**Wyoming cities list (23):** Cheyenne, Casper, Laramie, Gillette, Rock Springs, Sheridan, Green River, Evanston, Riverton, Jackson, Cody, Rawlins, Lander, Torrington, Powell, Douglas, Worland, Buffalo, Wheatland, Newcastle, Thermopolis, Kemmerer, Lyman.

**Other states:** Same factory, but statutes source changes (e.g. `legislature.state.*`, Municode slug differs, Granicus domain `*.granicus.com`). Law layers become state-specific.

**Engine LLM router (`engine/llm_router.py`):**
```python
class LLMRouter:
  def __init__(self, groq_key=None, gemini_key=None, cf_account=None):
    self.chain = [self.groq, self.gemini, self.cf_workers_ai, self.openrouter, self.ollama, self.extractive]
  def complete(self, prompt: str) -> dict:
    for fn in self.chain:
      try:
        text = fn(prompt)
        return {"method": "llm", "provider": fn.__name__, "text": text}
      except Exception as e:
        continue
    return {"method": "extractive-offline", "text": extractive_summary(prompt)}
```
Wire into `engine/analyze.py` via `Summarizer(llm_fn=LLMRouter().complete)`.

---

## 8. Implementation Roadmap — 6 Phases

**Phase 0 — Done:**
- Granicus full-archive puller v3 (all views incl training, RSS, recursive links, MP4 catalogue)
- 17yr minutes corpus + 260 YouTube index + captions backfill cell
- RAG sample DB + hybrid query + glossary
- Contention reel + ordinance index + entity index

**Phase 1 — Ground-up inventory (this doc + tools stubs):**
- Create `docs/BUILD_GROUND_UP.md` (this file)
- Stub tools: `cheyenne_boards_pull.py`, `wayback_pull.py`, `municode_pull.py`, `wy_statutes_pull.py`, `courtlistener_pull.py`, `unified_meeting_builder.py`
- Verify live via fetch_page for each source

**Phase 2 — Pull everything (Colab + Actions):**
- Run granicus pull full sweep (MAX_CLIPS=0) → Drive → R2 sync
- Run boards pull → 26 boards minutes/agendas
- Run wayback pull → CDX for 2008-2026
- Run municode pull → municipal code + UDC + previous versions
- Run wy_statutes pull → 43 PDFs → text + index
- Run courtlistener pull → bulk CSV + API recent

**Phase 3 — Unified meeting builder:**
- Merge Granicus + YouTube + city site + Wayback into `cities/cheyenne/meetings/<id>.json`
- Extract agenda items, ordinance refs (regex `Ord\.? No\.? \d+`, `PUDC-\d+-\d+`), statute refs (`\d+-\d+-\d+`), case cites
- Attach law layers

**Phase 4 — RAG 6-layer:**
- Extend `build_vector_db.py` to ingest code/statutes/case law + entity layer
- Build full `rag/vectordb/` + `chunks.jsonl` → R2
- Eval with `rag/eval_queries.md` battery (e.g. "What does 15-1-402 require for annexation?" should return statute + meeting + case law)

**Phase 5 — Granicus-like viewer:**
- Streamlit: 3-column layout (video + agenda jumps + doc viewer) + toppings tabs (ordinance history, case law, entities, PRA draft)
- Cloudflare Pages: React viewer reading from R2 JSON, custom domain `cheyenne.therealwindycity.com`
- Deploy via GitHub Actions → Pages

**Phase 6 — City factory + scale:**
- `tools/seed-city.py` template + `cities/_template/`
- `engine/llm_router.py` + wire to Summarizer
- `SCALE-ARCHITECTURE.md` (short version of this doc for README)
- Repeat for Laramie, Casper, etc.

---

## 9. Legal + Politeness

- Public documents only; no impersonation; verbatim quotes + source URL + fetch timestamp on alerts (existing invariant)
- Honor robots.txt where possible — Granicus `Disallow: /` for `*` but allows Googlebot — position as single-owner throttled public-records research (same files citizen opens by hand), DELAY 1.5s, custom UA `TheRealWindyCity/1.0 (+civic-archive)`
- Wayback CDX sleep 1 between fetches
- Municode: use browser rendering, not aggressive scrape — respect ToS, fallback to Wayback
- CourtListener bulk is explicitly for bulk reuse (Free Law Project nonprofit)
- WY statutes PDFs are public domain (state law)
- Video: embed existing YouTube/Granicus MP4s — don't re-host 130GB unless Internet Archive (public record archiving allowed)

---

## 10. Immediate Next Actions for Owner

1. **Confirm Drive path:** Is `/content/drive/MyDrive/TheRealWindyCity/cheyenne` correct? Or existing folder different? Adjust OUT_ROOT.
2. **Run Granicus full sweep smoke test:** Set `MAX_CLIPS=3` in Colab, verify manifest, then `MAX_CLIPS=0` full.
3. **Buy domain:** Porkbun or Cloudflare Registrar `therealwindycity.com` $12/yr, WHOIS privacy ON, auto-renew ON. Set Cloudflare DNS.
4. **Create Cloudflare account + R2 bucket `therealwindycity` + Pages project.**
5. **Create Turso account + DB `cheyenne` + token → GitHub repo secret `TURSO_TOKEN`.**
6. **Get free LLM keys:** Groq (groq.com), Gemini (aistudio.google.com), Cloudflare Workers AI (dash.cloudflare.com) → GitHub secrets `GROQ_API_KEY`, `GEMINI_API_KEY`, `CF_AI_TOKEN`.
7. **Merge PR #6** (Granicus puller v3) → main so Colab can clone latest.
8. **Run boards + statutes + case law pulls** (tools stubs provided next).

---

## Appendix A: Cheyenne Boards (26) — Pull Targets

From `cheyennecity.org/Your-Government/Boards-Commissions`:
Active Transportation Advisory Committee, Affordable Housing Task Force, Board of Adjustment, Building Code Board of Appeals, Cheyenne Housing Authority Board, Cheyenne-Laramie Co. Economic Development JPB, Cheyenne Passenger Rail Commission, City/County Health Board, Community Action of Laramie County, Community Technology Advisory Council, Contractor Licensing Board, Downtown Development Authority, Fire Civil Service Commission, Friends of the Botanic Gardens, Greenway Advisory Committee, Historic Preservation Board, Housing and Community Dev Advisory Council, Innovation and Entrepreneur Advisory Council, International Fire Code Board of Appeals, Mayor's Council for People with Disabilities, Mayor's Youth Council, MPO Citizen's Advisory Committee, Planning Commission, Police Civil Service Commission, Public Transit Advisory Board, Tourism Promotion Joint Powers Board, Urban Renewal Authority.

Each has page `cheyennecity.org/Your-Government/Boards-Commissions/<Slug>` with minutes/agendas PDFs — pattern similar to Council but not in Granicus. Need separate scraper.

Plus: Finance Committee, Public Services Committee, Committee of the Whole, Work Sessions (in cityvideos.json), BOPU (cheyennebopu.org), Laramie County Commissioners.

## Appendix B: WY Statutes Titles — Download List

From `wyoleg.gov/stateStatutes/StatutesDownload` (Jul 1 2026):
Constitution (title97.pdf), Title 01 Civil Procedure, 02 Wills, 03 Guardian, 04 Fiduciaries, 05 Courts, 06 Crimes, 07 Criminal Procedure, 08 General Provisions, 09 Administration of Government, 10 Aeronautics, 11 Agriculture, 12 Alcoholic Beverages, 13 Banks, 14 Children, 15 Cities and Towns (key), 16 City/County/State/Local Powers (key, includes PRA 16-4-201), 17 Corps, 18 Counties, 19 Defense, 20 Domestic Relations, 21 Education, 22 Elections, 23 Game/Fish, 24 Highways, 25 Institutions, 26 Insurance, 27 Labor, 28 Legislature, 29 Liens, 30 Mines/Minerals, 31 Motor Vehicles, 32 Notaries, 33 Professions, 34 Property, 34.1 UCC, 35 Public Health/Safety, 36 Public Land, 37 Public Utilities, 38 Sureties, 39 Taxation, 40 Trade/Commerce, 41 Water, 42 Welfare, 99 Water Projects.

Critical for Cheyenne: Title 15 (15-1-402 compliance hearing, 15-1-407 city-owned annexation, 15-1-505/506 PC vote), Title 16 (16-4-201 PRA, 16-4-405 exec session), Title 34 (property), Title 35 (health/safety).

## Appendix C: CourtListener Endpoints

- Bulk: `https://com-courtlistener-storage.s3.amazonaws.com/bulk/...` via `aws s3 sync s3://com-courtlistener-storage/bulk/ --no-sign-request`
- API search: `https://www.courtlistener.com/api/rest/v4/search/?q=&type=o&court=wy&order_by=score+desc`
- Opinions: `/api/rest/v4/opinions/?cluster__docket__court=wy`
- Courts: `/api/rest/v4/courts/` — `wy` = Wyoming Supreme Court
- Python SDK: `pip install courtlistener-api-client`, `export COURTLISTENER_API_TOKEN=...`

## Appendix D: Wayback CDX Examples

```
# Cheyenne city site all captures
https://web.archive.org/cdx/search/cdx?url=cheyennecity.org/*&output=text&fl=timestamp,original,mimetype,statuscode,digest&filter=statuscode:200&collapse=digest

# Granicus
https://web.archive.org/cdx/search/cdx?url=cheyenne.granicus.com/*&output=text&fl=timestamp,original,mimetype,statuscode,digest&filter=statuscode:200&collapse=digest

# Municode Cheyenne
https://web.archive.org/cdx/search/cdx?url=library.municode.com/wy/cheyenne/*&output=text&fl=timestamp,original,mimetype,statuscode,digest&filter=statuscode:200&collapse=digest
```

Raw fetch: `https://web.archive.org/web/20200101120000id_/https://cheyennecity.org/...`

---

**End of blueprint — next files are tool stubs implementing each pull.**
