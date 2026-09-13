# Montage Studio — Transcription-Driven Multi-Meeting Stitch with Watermark

## Goal
Allow users to pull up videos via transcriptions and then stitch together their own montages from multi meetings that they can export and share directly to social media. Watermark mandatory with The Real Windy City so viewers know platform.

## UI — pages/6_Montage_Studio.py

### Search transcriptions → pull up videos
- Input: plain-English query (e.g. "annexation", "water", "Miller", "15-1-402")
- Backend: `engine/corpus_search.py` over `pipeline/corpus/*.txt` (17 years, 472 meetings) + `pipeline/corpus_clean/*.clean.txt` (cleaned transcripts with `[HH:MM:SS-HH:MM:SS]`) + `pipeline/captions/*.vtt` (YouTube auto-captions) + RAG `rag/vectordb_sample/` hybrid search
- Hit: {date, file, snippet, clip_id, t_start, source_url, youtube_id, external_url, local_path}
- Add to basket: creates clip around timestamp (default 60 sec window: t_start-5 to t_start+55) with title = snippet, source_text = snippet

### Quick Add — Recent 6 months real
- Uses `engine/city_registry.py` `recent_meetings("cheyenne", months=6)` → 22 meetings from `pipeline/meetings.json` (479) + `cityvideos.json` (260)
- Each meeting has external_url (Granicus agenda, MP4 `archive-video.granicus.com`, YouTube) + local_path `server_data/cheyenne/...`
- Add button → basket

### Basket — multi-meeting montage
- Session state `st.session_state.montage_clips` list of {clip_id, date, start, end, title, source_text, external_url, local_path, youtube_id}
- Editable per clip: start/end HH:MM:SS, title/caption, remove
- Order = basket order (drag not yet, but can remove/re-add to reorder)
- Build Project: `MontageBuilder.build_project(output, title, vertical, watermark)` → `server_data/cheyenne/montages/<id>/project.json + .srt + POST_*.txt + manifest.json`

### Render — watermark mandatory
- `engine/montage_builder.py` `render(project, watermark=True, vertical=True)`
- Checks ffmpeg, cuts each clip from local file if exists (priority: local file → YouTube via yt-dlp → Granicus MP4) or placeholder card if no video
- Watermark filter:
  ```
  scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,
  drawtext=fontfile=...:text='THE REAL WINDY CITY — therealwindycity.com':fontcolor=white:fontsize=24:x=w-text_w-20:y=h-text_h-20:box=1:boxcolor=black@0.6:boxborderw=6,
  drawtext=fontfile=...:text='clip 1103 2026-06-22 01:22:10-01:25:00':fontcolor=0xFFD166:fontsize=18:x=20:y=20:box=1:boxcolor=black@0.6
  ```
- Optional logo PNG overlay `[0:v][1:v]overlay=W-w-20:H-h-20`
- Concat via `ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4`
- Output: `server_data/cheyenne/montages/<id>/my_montage.mp4` watermarked, every frame burned

### Export — share to social
- Download buttons: project.json, .srt captions, POST kit (title + bullet list of clips + sources + hashtags)
- Share buttons: X/Twitter intent, Facebook sharer, Reddit submit — share_text includes title + "THE REAL WINDY CITY therealwindycity.com"
- For TikTok/Reels/Shorts: vertical 1080x1920 MP4 + SRT upload — watermark already burned

### Local server copy principle
- Every source clip has external_url preserved + local_path served — no dependency
- Montage manifest: `server_data/<city>/montages/<id>/manifest.json` {watermark_proof, clips, external_urls, local_paths}
- RAG vectordb: `server_data/<city>/vectordb/` primary, R2 backup egress free

## Engine — engine/montage_builder.py

- `MontageBuilder(city, root)` — root default `server_data`
- `add_clip(clip_id, date, start, end, title, source_text, external_url, local_path, youtube_id)`
- `add_from_transcript_hit(hit)` — 60 sec window around t_start
- `build_project(output, title, vertical, watermark)` → project JSON + SRT + POST + manifest
- `render(project, watermark, vertical, logo_path)` → ffmpeg cut + watermark + concat

## Watermark utility — tools/watermark.py

- `watermark_video(input, output, text, source_label, logo_path, vertical)` — standalone
- `python tools/watermark.py input.mp4 output.mp4 --text "THE REAL WINDY CITY" --source "clip 1103 2026-06-22"`

## Storage

```
server_data/
  cheyenne/
    meetings/1103/
      agenda.html (local) + external_url
      minutes.pdf
      docs/*.pdf
      video/meeting.mp4
      captions.vtt
    montages/20260913_011500/
      project.json
      my_montage.mp4 (watermarked)
      my_montage.srt
      POST_my_montage.txt
      manifest.json {watermark_proof, external_urls, local_paths}
      work/ (temp parts)
    vectordb/
      chroma.sqlite3
      chunks.jsonl
```

## How to use on your server

```bash
# Install ffmpeg
sudo apt install ffmpeg

# Pull videos (Colab) then sync to server
python tools/server_sync.py --city cheyenne --to server_data/

# Build RAG vectordb on server
pip install -r rag/requirements-rag.txt
python rag/build_vector_db.py --all --persist server_data/cheyenne/vectordb

# Run Streamlit — Montage Studio page appears in sidebar
streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0

# Or render montage from CLI (without UI)
python -c "
from engine.montage_builder import MontageBuilder
b=MontageBuilder(city='cheyenne')
b.add_clip(clip_id=1103, date='2026-06-22', start='01:22:10', end='01:25:00', title='Miller DDA', external_url='https://cheyenne.granicus.com/...', local_path='server_data/cheyenne/meetings/1103/video/meeting.mp4', youtube_id='RjSGlhh4q9s')
b.add_clip(clip_id=1093, date='2026-04-27', start='02:10:00', end='02:13:30', title='DDA budget')
proj=b.build_project(output='my_reel.mp4', title='My Montage')
print(b.render(proj))
"
```

## Why watermark mandatory

Every shared video must tell viewers platform: THE REAL WINDY CITY — therealwindycity.com burned into every frame + source clip_id/date top-left. So even if video is re-uploaded to TikTok/Reels/Shorts/X/Facebook/Reddit, attribution stays. No way to export without watermark — checkbox disabled checked, filter always applied in render.

## Future

- Drag to reorder basket
- Waveform preview + transcript timeline
- Auto-captions burned (SRT → drawtext or subtitles filter)
- Direct upload to YouTube/TikTok API via OAuth (requires secrets)
- Logo PNG overlay from `assets/logo.png` (add your logo)
- Horizontal 1920x1080 option for YouTube, vertical 1080x1920 for Reels/Shorts (toggle already in UI)
