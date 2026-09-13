# Granicus-Like Viewer Spec — With Toppings

## What Granicus MediaPlayer Does (to clone)
- URL: `MediaPlayer.php?view_id=2&clip_id=1103&meta_id=148913`
- Left: video player (MP4 from archive-video.granicus.com)
- Center: agenda outline — each item is a link with meta_id, jumps video to timestamp (Granicus stores timestamps in player JS)
- Right: document pane — shows MetaViewer doc (staff report, ordinance text) alongside video
- Bottom: captions (none served by Granicus, but we have YouTube VTT)

## Our Viewer — 3-Pane + Toppings

### Layout (React + Vite, also Streamlit fallback)
```
+-------------------------------------------------------------+
| Header: Cheyenne City Council - Jun 22, 2026 [clip 1103]    |
+--------------+-----------------+----------------------------+
| Video        | Agenda Outline  | Document Viewer            |
| - MP4        | - 1. CALL ORDER | - Staff Report PDF         |
| - YouTube    | - 18. Annex     | - Ordinance text           |
|   embed      |   PUDC-26-37    | - Supporting docs tabs     |
| - Jump on    |   [02:14:30]    |                            |
|   agenda     | - 19. AG/P Zone | Toppings Tabs:             |
|   click      | - 20. AG->BP    | [Code] [Statutes] [Cases]  |
|              |                 | [Entities] [History] [PRA] |
+--------------+-----------------+----------------------------+
| Transcript Search | Captions VTT with timestamps (click to jump) |
+-------------------------------------------------------------+
| RAG Chat: "What did council say about 15-1-402?"           |
+-------------------------------------------------------------+
```

### Data Source
- `cities/cheyenne/meetings/1103.json` unified
- `granicus_pull/1103/agenda.html` + `agenda.txt`
- `granicus_pull/1103/docs/*.pdf`
- `pipeline/captions/2026-06-22.vtt`
- `rag/vectordb/` or Cloudflare Vectorize for chat

### Features
1. **Video sync:** Click agenda item → `video.currentTime = agenda_items[i].video_start`
2. **Doc sync:** Agenda item has `documents: [staff_report.pdf, annex_map.pdf]` — show in right pane, tabs if multiple
3. **Code pane:** If item references `1.16.050` or `PUDC-26-37`, fetch `cities/cheyenne/code/municode/...` text
4. **Statute pane:** If `15-1-402`, fetch `cities/cheyenne/law/wy_statutes/sections/15-1-402.txt`
5. **Case law pane:** If statute cited, query `wy_cases.jsonl` for opinions citing it
6. **Ordinance history:** `pipeline/ordinance_history.json` — show all readings of same ordinance across meetings, with tape jumps
7. **Entity dossiers:** Click "AVI Professional Corp" → modal with all meetings/docs where it appears (from `engine/entity_index.py`)
8. **Contention:** Show contention_score, highlight most contentious moments (from reel)
9. **PRA draft:** Button "Draft PRA for missing doc" → uses `engine/records.py` Wyoming PRA template
10. **Transcript search:** Input box filters `pipeline/corpus/*.txt` + captions VTT, highlights timestamp, click to jump video

### Tech Stack (free)
- **Cloudflare Pages:** Vite + React + react-pdf + hls.js + youtube-player
- **R2:** Serve JSON + PDFs via Workers API (CORS)
- **Workers:** `/api/meeting/1103`, `/api/search?q=`, `/api/rag?q=`
- **Vectorize or Chroma:** RAG chat endpoint `/api/chat` uses llm_router
- **Streamlit fallback:** `pages/3_Meeting_Viewer.py` with `st.video`, `st.columns`, `st.pdf_viewer` (community component)

### Implementation Steps
1. Create `frontend/` Vite app (outside git or in `frontend/` ignored for video assets)
2. Worker API reads from R2 `cities/cheyenne/meetings/*.json`
3. PDF viewer uses `react-pdf` with R2 URLs
4. Video player: `<video src={mp4_url} controls>` + YouTube iframe fallback
5. Agenda list: map `agenda_items` to clickable divs, onClick set video time
6. Toppings tabs: fetch code/statute/case law from R2 on demand
7. RAG chat: input → Vectorize query → llm_router → answer with citations (verbatim quote + source URL + timestamp)

### Why Better Than Granicus
- Granicus shows only agenda + docs for that meeting. Ours shows ordinance history across 17 years, entity mentions, case law, statutes, contention, transcript search, and AI chat — all tied to same video timestamp.
- Granicus has no RAG, no entity dossiers, no PRA drafts, no cross-meeting search.

### Mock API
```
GET /api/meetings -> index.json (sorted by date)
GET /api/meeting/1103 -> 1103.json
GET /api/meeting/1103/docs/staff_report.pdf -> R2
GET /api/search?q=annexation -> FTS5 + vector hybrid
GET /api/rag?q=What does 15-1-402 require? -> {answer, citations: [{clip_id, t_start, text, source_url}]}
GET /api/ordinance/4687 -> history.json filtered
GET /api/entity/AVI%20Professional%20Corp -> entity_index.json filtered
```
