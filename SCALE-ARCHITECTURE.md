# SCALE ARCHITECTURE — Free Guerrilla Stack That Beats Paid

> Short version of `docs/BUILD_GROUND_UP.md` for README / onboarding.

## Goal
One domain `therealwindycity.com`, unlimited cities. Each city:
- Every meeting (Granicus, YouTube, city site, Wayback)
- Every board/commission (26 in Cheyenne)
- Every document (agendas, minutes, supporting docs, recursive links)
- Entire municipal code + UDC + WY statutes Title 1-42 + Constitution + federal relevant + WY case law 1980-present
- Every video with transcript layers
- RAG 6-layer vectors + Granicus-like 3-pane viewer + toppings (ordinance history, entity dossiers, contention reel, PRA drafts)

## Free Stack
- **GitHub** public repo: source of truth, Actions free 2000 min/mo, Releases for audio/video (2GB/asset), unlimited
- **Cloudflare Free**: DNS + proxy for `*.therealwindycity.com`, Pages (frontend free unlimited BW), R2 (10GB free, egress ALWAYS free), Workers (API 100k/day), Vectorize (5M vectors free), Workers AI (10k neurons/day ≈1300 LLM responses/day)
- **Streamlit Cloud Free**: unlimited apps, one per city, proxy via Cloudflare
- **Turso Free**: 9GB libSQL, 500 DBs
- **Chroma**: local ONNX embeddings, no torch, no key, sync chunks.jsonl to R2
- **AI Router**: Groq 1k/day → Gemini 1.5k/day → CF Workers AI 1.3k/day → OpenRouter free → Ollama local → extractive fallback (already in engine/analyze.py)
- **Video**: embed existing YouTube + Granicus MP4s; archive to Internet Archive (free unlimited public)

## City Factory
```
cities/
  cheyenne/config.yaml  # granicus domain, municode slug, youtube channel, boards list
  laramie/config.yaml
  casper/config.yaml
```
`python tools/seed-city.py <slug> <state> --granicus <domain> --municode <slug> --youtube <id>`

## Tools (all runnable in Colab — sandbox egress blocked)
- `tools/granicus_document_pull.py` v3 — ALL views (2,4,5,6,7 training), RSS, MP4, recursive in-doc links, manifest.json
- `tools/cheyenne_boards_pull.py` — 26 boards/commissions
- `tools/wayback_pull.py` — CDX API `cheyennecity.org/*`, `cheyenne.granicus.com/*`, `library.municode.com/wy/cheyenne/*`
- `tools/municode_pull.py` — Cheyenne Municipal Code + UDC (Playwright + Wayback fallback)
- `tools/wy_statutes_pull.py` — wyoleg.gov 43 PDFs → text + section index (15-1-402, 16-4-201, etc.)
- `tools/courtlistener_pull.py` — bulk CSV + API court=wy, queries like "Cheyenne annexation"
- `tools/unified_meeting_builder.py` — merges everything into `cities/<city>/meetings/<id>.json`
- `engine/llm_router.py` — free-tier fallback chain

## Meeting JSON (unified)
```json
{
  "clip_id": 1103, "date": "2026-06-22", "body": "City Council",
  "sources": {
    "granicus": {"agenda_url": "...", "minutes_pdf": "...", "mp4_url": "...", "documents": [...]},
    "youtube": {"id": "RjSGlhh4q9s", "captions_vtt": "..."}
  },
  "agenda_items": [{"no": "18", "title": "Annexation", "video_start": 3600, "documents": [...], "wy_statute_refs": ["15-1-402"]}],
  "law_layers": {"municipal_code": [...], "wy_statutes": ["15-1-402"], "case_law": [...]},
  "toppings": {"ordinance_history": [...], "entity_mentions": [...], "contention_score": 0.92}
}
```

## Viewer (Granicus-like)
- Left: video (MP4 + YouTube) with timestamp jumps
- Center: agenda outline clickable → jumps video
- Right: document viewer (staff report / ordinance) + tabs: Code, Statutes, Case Law, Entities, PRA draft
- Bottom: transcript search + captions

Streamlit for speed, Cloudflare Pages React for production custom domain.

## Costs
- Domain: $12/yr Porkbun/Cloudflare
- Everything else: $0 free tier for Cheyenne full (5-6GB text+docs, video via embed)
- Paid fallback if needed: Contabo Storage VPS 6 vCPU/18GB/1TB ~€13/mo or Hetzner CAX11 ~€5.99/mo + R2

## Roadmap
0. Done: Granicus v3 puller, 17yr corpus, 260 YouTube index, RAG sample, contention reel
1. This doc + tool stubs
2. Pull everything (Colab + Actions)
3. Unified meeting builder
4. RAG 6-layer + eval
5. Granicus-like viewer (Streamlit + Pages)
6. City factory + llm_router + scale to WY 23 cities then states

See `docs/BUILD_GROUND_UP.md` for full blueprint with CDX examples, board list, statutes list, CourtListener endpoints.
