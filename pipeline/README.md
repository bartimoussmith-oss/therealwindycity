# Cheyenne Municipal Records & Video Pipeline

`cheyenne_pipeline.py` — one tool for the whole post-meeting workflow: index every
city meeting, pull every agenda/minutes/supporting document, download meeting
video, cut timestamped clips, and stitch reels with your commentary.

## Setup (once)
```bash
python3 -m pip install requests yt-dlp curl_cffi   # curl_cffi = last-resort stream fetch
# ffmpeg + fonts:
sudo apt install ffmpeg fonts-dejavu-core          # Debian/Ubuntu (brew equivalent on Mac)
```

## Commands
```bash
python3 cheyenne_pipeline.py index                 # build meetings.json (479 meetings: agendas, minutes, MP4s)
python3 cheyenne_pipeline.py list --search "2026-08"   # find meetings; clip ids
python3 cheyenne_pipeline.py docs 1091             # agenda + minutes + EVERY supporting doc (packet pages)
python3 cheyenne_pipeline.py docs --all --since 2026-01-01 --max-docs 40   # bulk pull
python3 cheyenne_pipeline.py video 1091            # full meeting video -> videos/
python3 cheyenne_pipeline.py video 1091 --seconds 30   # quick partial grab
python3 cheyenne_pipeline.py clip 1091 --start 01:22:10 --end 01:25:00 --name miller_turn
python3 cheyenne_pipeline.py clip videos/1091_2026-04-13.mp4 --start 12:34 --end 15:00
python3 cheyenne_pipeline.py grab <any-youtube-or-facebook-url>   # yt-dlp path (city livestreams etc.)
python3 cheyenne_pipeline.py captions 1091         # WebVTT track (server populates none so far)
python3 cheyenne_pipeline.py example               # writes project_example.json
python3 cheyenne_pipeline.py project my_reel.json  # render the reel -> renders/
```

## Project JSON — stitch meeting clips + commentary
```json
{
  "output": "mlk_reel.mp4",
  "segments": [
    {"type": "title", "text": "MLK Park, by the numbers", "duration": 4},
    {"type": "clip", "meeting": 1091, "start": "00:04:10", "end": "00:06:30"},
    {"type": "file", "path": "commentary/my_take.mp4"},
    {"type": "clip", "meeting": 1103, "start": "01:22:00", "end": "01:25:00",
     "overlay_audio": "commentary/voiceover.mp3", "duck": true},
    {"type": "title", "text": "19,795 bookings. 16 park arrests.", "duration": 4}
  ]
}
```
- `type: clip` — a timestamped piece of any indexed meeting (auto-downloads the video if needed). Use your "Sync to video time" numbers directly.
- `type: file` — your own commentary video/audio (any format ffmpeg reads).
- `overlay_audio` + `duck: true` — your voice-over on top of meeting audio, meeting audio auto-ducks while you speak.
- `type: title` — full-screen title card.
All segments are normalized to 1280x720/30fps/AAC and concatenated, so mixed sources always stitch.

## Where things land
```
pipeline/meetings.json   the index (clip_id -> dates, agenda/minutes/MP4 URLs)
pipeline/docs/<clip_id>/ agenda.html, minutes.html, meta_NN.html (staff reports & packets)
pipeline/videos/         full meeting MP4s  (multi-GB for long meetings — watch disk)
pipeline/clips/          cut segments
pipeline/renders/        final reels
```

## Notes & gotchas (verified live 2026-08-28)
- **Index works everywhere**: 479 meetings, 472 direct-MP4 links, 479 agendas, 473 minutes.
- **Docs work everywhere**: Granicus renders agendas/minutes/packets as HTML pages, not PDFs — they're saved as `.html` (open in any browser, or grep them). Real PDFs (DocumentViewer / city-site) download as PDFs when linked.
- **Video streams** (`archive-stream.granicus.com`) reject non-browser clients on some networks (this build sandbox got 403; home/office networks typically fine). Fallback chain: HLS w/ headers -> direct MP4 -> chrome-impersonated segment downloader (curl_cffi) -> yt-dlp. If all fail from your network: open the player in your browser, F12 -> Network -> copy the `playlist.m3u8` URL, then:
  `python3 cheyenne_pipeline.py video 1091 --url "<m3u8-url>"`
- Meeting IDs: `list` shows them; e.g. 1126=Aug 24 2026, 1124=Aug 10, 1122=Jul 27, 1120=Jul 13 (7h43m), 1103=Jun 22/23, 1093=Apr 27, 1091=Apr 13, 1071=Mar 9 (5h52m).
- The tool rate-limits itself (0.4s between doc fetches). Source is public records; keep it polite.

## On-the-fly segments — NO full-meeting downloads (2026-08-28)
`clip` and `project` now cut from the **stream** when the full video isn't local: they fetch
only the HLS segments covering your window (a 3-minute turn ≈ ~30 small segment files,
tens of MB — never the multi-GB meeting file). Segments are cached in
`videos/.segcache/<clip_id>/` and shared between overlapping clips.

```bash
# one clip, no full download:
python3 cheyenne_pipeline.py clip 1091 --start 01:22:10 --end 01:25:00 --name miller_turn

# batch from a JSON spec (use your "Sync to video time" indexes verbatim):
cat > turns.json << '[
  {"meeting": 1071, "start": "00:04:10", "end": "00:07:00", "name": "mar9_miller"},
  {"meeting": 1103, "start": "01:22:00", "end": "01:25:00", "name": "jun22_miller"},
  {"meeting": 1093, "start": "02:10:00", "end": "02:13:30", "name": "apr27_dda"}
]
python3 cheyenne_pipeline.py segments turns.json          # skips clips that already exist
python3 cheyenne_pipeline.py segments turns.json --force  # re-cut everything

# spec entries also accept a raw playlist URL and normalization:
{"url": "https://archive-stream.granicus.com/.../playlist.m3u8", "start": "...", "end": "...", "normalize": true}
```
`project` reels do the same: a `{"type":"clip","meeting":1091,...}` segment streams just its
window (normalized to 720p/30fps for the stitch automatically). Priority order is always:
local full video → windowed stream. If both fail on your network, copy the m3u8 URL from a
browser (F12 → Network) and pass it as `"url"` in the spec.

## Browser UI (2026-08-28)
```bash
python3 webui.py                 # → http://localhost:8717
python3 webui.py --port 9000     # custom port; --host 127.0.0.1 to keep it local-only
```
Tabs: **Meetings** (search the 479-meeting index; per-meeting buttons for docs / full video / captions / prefill-clip),
**Clips** (cut by timestamp — stream-local, no full downloads; batch-paste a turns JSON; play & download results inline),
**Render reel** (edit the project JSON, render, play/download), **Files** (videos + every pulled document, browsable),
**Job log** (live streaming logs of every job). Long jobs run in a background worker; the page polls their status.
Everything the CLI does is exposed as JSON endpoints too (`/api/meetings`, `/api/docs`, `/api/clip`, `/api/segments`,
`/api/project`, `/api/status`, `/file/<kind>/<name>`).

## Transcript search + NotebookLM → social answer reel (2026-08-28)
The question-to-video chain:
```bash
python3 cheyenne_pipeline.py corpus                 # all minutes -> corpus/*.txt + notebooklm/cheyenne_minutes_YYYY.md
python3 cheyenne_pipeline.py search "municipal building"   # local search with snippets
python3 cheyenne_pipeline.py nbprompt               # prints/writes notebooklm/PROMPT.txt
```
1. Upload `notebooklm/*.md` (one file per year, plus your own sync transcripts) to a NotebookLM notebook.
2. Paste PROMPT.txt with your question → NotebookLM replies strict JSON (hook, segments with clip_ids + verbatim quotes).
3. Save as `answer.json`; fill any null start/end timestamps (from your sync-to-video indexes or the player).
4. `python3 cheyenne_pipeline.py answer answer.json` → **renders/{hook}.mp4**: vertical 1080×1920, blurred-fill
   background, burned captions + source labels, hook & CTA cards, segments capped at 45s — plus a drafted
   POST.txt caption with quotes and hashtags. Segments can also use "file" or "url" instead of "meeting".
The browser UI gains a transcript-search card on the Meetings tab (`/api/search`) and a corpus-build button.

## THE 10x UPGRADE — full archive, one-command answers, bulk creation (2026-08-28/29)

### The whole archive, searchable (done: 472 transcripts)
`python3 cheyenne_pipeline.py corpus` built **corpus/ = every minutes PDF in the city archive
(472 meetings, Nov 2012 → Aug 2026, ~10 MB of text)** + notebooklm/cheyenne_minutes_YYYY.md bundles.
Search anything across 14 years: `python3 cheyenne_pipeline.py search "15-1-402"`.

### ASK — question in, reel-spec out (NotebookLM now OPTIONAL)
```bash
python3 cheyenne_pipeline.py ask "What has the council spent on the Municipal Building"
python3 cheyenne_pipeline.py ask --batch questions.txt      # one question per line -> one spec each
python3 cheyenne_pipeline.py ask "..." --auto               # also renders reels when timestamps exist
```
Finds the strongest verbatim sentences across all 472 transcripts, builds asks/ask_NNN.json
(hook, narration, segments w/ clip_ids + quotes). **If you drop your sync-to-video transcripts in
corpus/extra/{clip_id}_*.txt (lines like `01:22:10 Miller - DDA remarks`), timestamps fill in
automatically** and `--auto` renders with zero manual steps.

### VERIFY — the publication gate
```bash
python3 cheyenne_pipeline.py verify "quote to check"
```
EXACT / PARTIAL / NOT FOUND against every transcript. Nothing goes out unverified.

### BULK RENDER
```bash
python3 cheyenne_pipeline.py answer asks/          # renders EVERY ready spec in the folder
```
Each reel now also writes a matching .srt (captions file for YouTube/FB upload).

### AUTOPILOT — the meeting watch
```bash
python3 cheyenne_pipeline.py autopass              # re-index; auto-pull minutes+docs for new meetings
```
Run it daily (cron: `0 8 * * * cd /path/pipeline && python3 cheyenne_pipeline.py autopass >> watch.log`).
This is the Sept 8/9/14 agenda watch, automated.

### Turn-list importer
Paste a sync-to-video transcript (`00:04:10 | description` lines) → every line becomes a clip spec
with end-times inferred from the next timestamp. CLI: `parse_turns`; browser: Clips tab.

### Browser UI — new "Ask & Verify" tab
Ask box (find quotes / find + render), quote verifier, "Render ALL ready asks", "Check for NEW meetings"
button (autopass), turn-list importer on Clips tab, commentary upload button on Render tab.

## THE RECORD SPEAKS — proven-record montage (2026-08-29)
`python3 montage.py` → `renders/THE_RECORD_SPEAKS.mp4` (91s, 1080×1920, silent by design —
add music in-app when posting) + `.srt` + `renders/POST_THE_RECORD_SPEAKS.txt` (caption kit).
12 kinetic cards, every claim sourced on screen; built ONLY from verified record
(canon §35–§36 quarantines enforced — no DOJ claims, no Fountain/Windy City quotes).
Edit the BEATS list at the top of montage.py to update facts and re-render.
**Footage version:** fill timestamps in `montage_with_footage.json` (real clip_ids included),
then `python3 cheyenne_pipeline.py answer montage_with_footage.json` on a network where the
city streams play — same montage, with the actual council chambers footage under each card.

## VOICES EDITION — their real words, played from the tape (2026-08-29)
`python3 montage_voices.py` → `renders/THE_RECORD_SPEAKS_VOICES.mp4` — the montage with
**actual meeting audio/video**: Nemecek's "lipstick on a pig" testimony (Jan 14 COTW, real tape at
00:46:20–00:48:20) and the chair's "$22 million... you would remove" amendment recap (00:27:50–00:29:10),
vertical 1080×1920, captions + source labels burned over the real footage.

**How the tape was cracked (works from anywhere):**
- COTW + work-session videos live on the **city's YouTube channel** (GB meetings stay on Granicus).
  `pipeline/cityvideos.json` = date→video map scraped from the city site (80+ videos).
- `youtube-transcript-api` pulls **auto-captions = searchable timestamps** (Jan 14 COTW and Aug 21 2026
  transcripts already saved to `corpus/extra/`).
- yt-dlp downloads exact sections (`--download-sections`) — on datacenter networks add deno +
  `--remote-components ejs:github` (the script handles the plain path first, then the fallback).

**Extend it:** add entries to `SEGMENTS` in montage_voices.py — `{"yt": "<id>", "from": ..., "to": ...,
"caption": ..., "label": ...}` (auto-downloads at home) or `{"file": "videos/xxx.mp4", ...}` for staged
tapes. Find any quote's timestamp by grepping `corpus/extra/yt_*.txt`.
