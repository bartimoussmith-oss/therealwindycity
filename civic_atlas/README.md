# Civic Atlas + Dais Lens

A read-only web application for The Real Windy City, available both standalone and integrated into the existing Streamlit app. Existing players and source records are preserved.

## Run

From the repository root, with Python 3.10+:

```sh
python -m civic_atlas.server --port 8080
```

Open the server's port in your browser. No API keys, external packages, CDN assets, fonts, or AI service required. The server binds to `0.0.0.0` for the Arena preview. This is a local/read-only research tool, not a production-hardened public service; put a reverse proxy, TLS, access policy, and request limits in front of it before public hosting. The standalone server is not needed by the integrated Streamlit page. GitHub Pages does not run this Python server.

## Record map

- Select an archived source agenda, then click an item to search its wording.
- Search a topic or select a suggested thread. The first twelve of up to 24 ranked search results become graph nodes; all returned results appear as evidence cards.
- Click a node or card for the indexed text, repository path, and a GitHub source link. The GitHub link points to `main`; until this branch is merged, new files may not exist there. The text shown in the app comes from the local checkout, not a remote refresh.
- Explore a record's title to move to another thread; pan the graph by dragging the background, use zoom/reset buttons, and export lead metadata and excerpts as JSON.
- Paste an agenda or upload `.txt` / `.md`, then select an agenda line. Uploaded material remains in the browser; only the selected line is sent to the local search server. PDF/DOCX parsing is not implemented.

### Actual coverage and evidence limits

At implementation time: **720 meeting entries**, **345 repository Markdown documents**, and **one archived HTML agenda** (`pipeline/docs/1124/2026-08-10_agenda.html`). The linked meeting database's `agendas` arrays are empty in this checkout; they are not represented as complete agenda coverage. Meeting entries may contain duplicated/derivative captions and uncertain speaker attribution. They are not 720 independently verified meetings.

Indexes the meeting text in `public/master_meetings_database_linked.json`, local Markdown (excluding hidden directories, `agent`, `legacy`, and this application; size limit 1.5 MB per file), plus source agenda item titles from `pipeline/docs/**/*agenda.html`. Markdown research/advocacy is explicitly a **repository document**, not an official record. Archived HTML is parsed to inert text; scripts are never executed. Original agenda item links are retained in the catalog API.

**Connections mean lexical overlap, not proof of an institutional, financial, personal, legal, or causal relationship.** Ranking uses matching query terms plus an exact-phrase boost. There is no LLM inference, automated accusation, verified knowledge graph, cross-repository crawler, PDF OCR, duplicate-source independence check, or full historical-record coverage. Binary documents and other repositories are not indexed. No unseen attachment was processed. To expand coverage, add authorized source material and explicit provenance adapters rather than silently treating research as primary evidence. Restart to refresh the in-memory index.

## Dais Lens

1. Click **Pop on Dais Lens** from the app header to enable the floating panel on either view. Select an existing archived compilation, a local browser-supported video (MP4 recommended), or **Share any video tab**. Local and shared video pixels are not uploaded.
2. For a player on another site (YouTube, a city webcast, or another repository's video), open the video in its own tab, then use **Share any video tab** and explicitly select that tab/window in the browser's picker. You control playback in the original player; the lens crops the live captured frames. No direct cross-origin iframe pixel access is attempted.
3. Use **Pop out lens** (or the ↗ button in the floating panel) to move the same tiles into a separate resizable window. Place it beside the original video. This is a normal browser window, **not guaranteed always-on-top**. Allow pop-ups if blocked; the in-app floating panel is the fallback. Keep Civic Atlas open.
4. Use **Adjust crops** in the floating/pop-out view to show/hide crop controls. Closing the panel hides it but **does not stop capture**; use **Stop sharing** or the browser's own stop-sharing control.
5. Add up to twelve square seat views. Manually label them and use horizontal, vertical, and crop-width sliders to frame a visible person.
6. Play, pause, or seek with the master player. All canvases draw from that **single video element**, so independent players cannot drift.
7. Save seat labels/crops in this browser's local storage. Video files and playback position are not saved. Layouts are camera-angle-specific; reset crops when the shot changes.

### Sharing compatibility and permissions

Tab/window sharing uses `getDisplayMedia`, requires a secure context (HTTPS, or localhost for local development), explicit permission, and a supported desktop browser. Mobile and browser support varies. In an embedded preview, the outer iframe's permission policy may block sharing; open the preview as a top-level browser tab and try again. If denied or cancelled, the current source is kept. Switching to an archive/local video releases an existing screen capture; stopping capture clears the shared source. Audio is not captured to avoid feedback—listen in the original player. Capturing your entire screen can expose unrelated windows; prefer sharing just the meeting tab. Avoid sharing the Atlas tab itself (recursive mirror). Protected/DRM video can appear black; this tool cannot bypass those restrictions.

The app provides **real-time rendering during playback or user-authorized screen capture**, not an automatic connection to a live city meeting feed. You may share a live player yourself. Archive MP4s are edited montages. A full continuous view requires an authorized full-length source that actually shows the dais. If the broadcast cuts to the speaker, the other members' reactions are not available; enlarging cannot recover off-camera faces or missing detail. No face recognition, identity inference, tracking, emotion inference, or behavioral scoring. Seat labels are user-entered, not verified identities. Automatic camera tracking and direct live-stream ingestion are not shipped features. Shared-tab/window input is available, but it does not inject controls into every external site or modify existing Streamlit players.

## Laramie County OSINT Explorer workspaces

The running standalone server also serves three independent map workspaces (the existing Civic Atlas home and its interface are unchanged):

- `/osint-original.html` — original Gotham-style layout, with unsafe/fabricated sample graph claims removed and safer interaction handling.
- `/osint-atlas.html` — separate GIS + Civic Atlas page. Selecting a GIS feature lets you search its visible attribute text against the local Civic Atlas index; results are lexical leads only.
- `/osint.html` — upgraded standalone explorer with responsive layout, safer filter parsing, feature attribute inspection, and a source-bound attribute graph.

All three share the public County Parcels, Zoning, Subdivision, and Pipelines ArcGIS services; layer toggles; simple validated attribute filters; a Turf.js 500-foot map-click buffer; and a relationship/attribute graph that only shows attributes from the selected actual GIS feature. The graph does **not** invent owners, registered agents, permits, intersections, or corporate relationships. The buffer is a circle for spatial context only; the app does not claim that it intersects GIS features. The filter is restricted to a short field-name/equality/inequality/LIKE grammar and is never executed as arbitrary SQL. GIS/basemap layers rely on external CDN and public-service availability; the Atlas-connected search uses the preview server's local `/api/search` endpoint. These are read-only research aids, not official county services or a production-hosted public service.

Start the existing server with `python -m civic_atlas.server --port 8080`, then open the routes above on that server. When the `ai-record-pages` workflow deploys from `main`, the public URLs are `https://bartimoussmith-oss.github.io/therealwindycity/osint.html`, `https://bartimoussmith-oss.github.io/therealwindycity/osint-atlas.html`, and `https://bartimoussmith-oss.github.io/therealwindycity/osint-original.html`. GitHub Pages uses a generated, metadata-and-token-only lexical index (no full transcript text) for Atlas search; it is roughly 14 MB uncompressed and is generated during deployment, not committed. Arena's live preview is available while the server process is running. Public deployment is complete only after main-branch workflow verification succeeds.

## Verify

```sh
python -m unittest civic_atlas.test_server -v
node --check civic_atlas/app.js
```

Tests cover source extraction, search excerpts/provenance, empty queries, exclusion, deterministic IDs, real local-corpus API access, media-compatible byte ranges, invalid ranges, and denying private-file/path traversal requests. Eight additional DOM interaction tests cover floating/docked tiles, single-player reuse, shared-source lifecycle, switching sources, cancelled permission picker, pop-out restoration, pop-up blocking, and unsupported sharing. Run with jsdom installed separately (no application dependency):

```sh
npm install --prefix /tmp/atlas-js-tests jsdom@26 --no-audit --no-fund
NODE_PATH=/tmp/atlas-js-tests/node_modules node --test civic_atlas/test_lens.cjs
node --check civic_atlas/lens.js
```

These use mocked media/window APIs, not a real screen-capture permission grant. No visual browser rendering, actual cross-site/live capture, or production deployment verification was performed.

## Streamlit integration

Open **Civic Atlas** from the sidebar or the **Civic Atlas + Dais Lens** home card. `pages/25_Civic_Atlas.py` uses the same cached local source index and ranking engine, with native Streamlit topic/agenda/paste controls, a source graph, complete record inspection, and JSON export. The integrated graph displays twelve leads; the source selector covers all 24 returned leads. No second process, localhost browser call, API key, new requirement, or remote corpus fetch is needed.

Optional **Dais Lens** expanders now sit alongside the home video previews, Origin Tapes, The Tapes (produced segments, clips, full meetings), recording media fallback, Miller playlist, and Screening Room. Existing player behavior is unchanged until the user enables the lens. Cross-origin YouTube pixels cannot be read directly, so the user explicitly shares the playing tab/window or opens a local file. No automatic player interception is claimed.

The lens is embedded as self-contained HTML/CSS/JS. **Streamlit's iframe permission policy can block screen sharing** even when the standalone preview supports it. The enabled panel therefore includes **Download standalone Dais Lens**: open that single HTML file in a supported desktop browser, then choose the meeting tab/window in its share picker. Browser support for capture from local files varies; if unavailable, use a local video file or serve the standalone app over HTTPS/localhost. This download contains tool code and the selected source label/link, never video bytes or a records corpus. No scraping, DRM bypass, or permission bypass. Full visual rendering and actual browser capture are not verified by mocked tests.

Publication requires this branch's changes to reach the deployed `main` branch; the repo's existing Streamlit Cloud connection should then redeploy. A successful merge is not proof that Cloud completed deployment.

Additional checks:

```sh
python -m unittest civic_atlas.test_server civic_atlas.test_integration -v
# with Streamlit installed:
python -m unittest civic_atlas.test_streamlit -v
```

Six AppTest tests (with four video-page subcases) verify the home link, twin identity, native search/agenda/paste modes, enabled embedded panel/download, and existing video-page lens options. Four artifact tests verify embedded asset independence and script-safe source labels/graph data. An existing Python-3.11-incompatible escaped separator inside a Miller playlist f-string was changed to its identical literal middle-dot character so the module can import and be tested on 3.11; no transcript or playlist contents changed.
