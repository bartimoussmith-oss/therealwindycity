# Tools — Ground-Up Pullers

All tools are designed to run in **Colab** (sandbox egress blocked for `curl`/`urllib` to external hosts, but Colab has full egress). They are resumable and write to Google Drive `MyDrive/TheRealWindyCity/` by default, fallback to local `cities/` etc.

## Existing
- `granicus_document_pull.py` v3 — **DONE** — full-archive sweep nothing excluded: views 2,4,5,6,7 training, RSS, clip/event/doc_id, MP4, ASX, MediaPlayer markers, supporting docs, recursive in-doc hyperlink following, raw href inventory, manifest.json with sha256. Selftest passes. Run in Colab:
  ```python
  !git clone --depth 1 https://github.com/bartimoussmith-oss/therealwindycity.git
  %cd therealwindycity
  exec(open('tools/granicus_document_pull.py').read())
  ```
  Config at top: OUT_ROOT, VIEW_IDS=None auto-discover, MAX_VIEW=100, SAVE_VIDEO=True (hundreds GB), MAX_CLIPS=0 no limit, DELAY=1.5.

- `colab_media_backfill.py` — YouTube 260 meetings: captions → `pipeline/captions/` (in git), audio → GitHub Releases, video 480p → Releases. MODE="captions"|"audio"|"full".

## New (this PR)
- `cheyenne_boards_pull.py` — 26 boards/commissions from `cheyennecity.org/Your-Government/Boards-Commissions` + Finance/PSC/COW. Saves agendas/minutes/docs per board.
- `wayback_pull.py` — CDX API for `cheyennecity.org/*`, `cheyenne.granicus.com/*`, `library.municode.com/wy/cheyenne/*`, `cheyennebopu.org/*`, `laramiecountywy.gov/*`. Dedupe by digest, raw fetch with `id_` suffix.
- `municode_pull.py` — Cheyenne Municipal Code + UDC from Municode. JS-heavy so tries Playwright headless, fallback to Wayback CDX. Saves HTML + txt + toc.json.
- `wy_statutes_pull.py` — Wyoming Statutes 43 PDFs from `wyoleg.gov/statutes/compress/title*.pdf` (Constitution + Title 01-42 + 99 + 34.1). Converts to text via pdfplumber/pypdf, builds section index regex `\d+-\d+-\d+`, per-section snippets.
- `courtlistener_pull.py` — Wyoming case law. Bulk mode via `aws s3 sync s3://com-courtlistener-storage/bulk/ --no-sign-request`, API mode via `courtlistener-api-client` with token, queries like "Cheyenne annexation", "15-1-402". Saves metadata.json + page.html + wy_cases.jsonl.
- `unified_meeting_builder.py` — Merges Granicus manifest + cityvideos.json + boards + wayback + law layers into `cities/cheyenne/meetings/<clip_id>.json` unified model (see `docs/BUILD_GROUND_UP.md`).
- `seed-city.py` — Factory to seed new city: `python tools/seed-city.py laramie wy --granicus laramie.granicus.com --municode laramie --youtube CHANNEL_ID` → creates `cities/<slug>/config.yaml` + README + workflow.

## Engine
- `engine/llm_router.py` — Free-tier chain Groq → Gemini → CF Workers AI → OpenRouter → Ollama → extractive fallback. Env secrets via GitHub Secrets or Colab userdata. Wire via `Summarizer(llm_fn=LLMRouter().complete_fn)`.

## Next Steps
1. Run granicus full sweep (MAX_CLIPS=3 smoke test, then 0)
2. Run boards pull
3. Run wy_statutes pull (43 PDFs)
4. Run courtlistener pull (need token)
5. Run wayback pull (CDX)
6. Run municode pull (needs Playwright or use Wayback)
7. Run unified builder → `cities/cheyenne/meetings/index.json`
8. Extend `rag/build_vector_db.py` to ingest law layers + build 6-layer vectors

All outputs <50MB stay in git (text, jsonl, captions). PDFs, audio, video → R2 + GitHub Releases + Internet Archive (out of git per repo rule).

See `docs/BUILD_GROUND_UP.md` for full blueprint, `SCALE-ARCHITECTURE.md` for short version, `docs/GRANICUS_VIEWER_SPEC.md` for viewer spec.
