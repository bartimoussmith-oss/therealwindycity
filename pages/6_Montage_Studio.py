"""
6_Montage_Studio.py — User Montage Studio: transcription-driven multi-meeting stitch with watermark

Allows users to:
- Search transcriptions (pipeline/corpus/*.txt, corpus_clean, captions VTT, RAG vectordb_sample)
- Pull up videos via transcriptions (timestamped clips)
- Stitch together own montages from multi meetings
- Export MP4 + SRT + POST kit and share directly to social media
- Mandatory watermark: THE REAL WINDY CITY — therealwindycity.com burned into every frame

Local server copy principle: every source clip has external_url + local_path

This page is additive — does not touch twins.
"""
import streamlit as st
import json, re
from pathlib import Path
from datetime import datetime
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Montage Studio — Build Your Own Reel", layout="wide")

# Try imports
try:
    from engine import corpus_search
except Exception:
    corpus_search = None

try:
    from engine.city_registry import recent_meetings, list_cities
except Exception:
    recent_meetings = list_cities = None

try:
    from engine.montage_builder import MontageBuilder
except Exception as e:
    MontageBuilder = None
    st.warning(f"MontageBuilder import failed: {e} — will export project JSON only (render in Colab/server with ffmpeg)")

st.title("🎬 Montage Studio — Build Your Own Reel (Watermarked)")
st.caption("Search transcriptions → pull up videos via timestamps → stitch multi-meeting montages → export + share to social with THE REAL WINDY CITY watermark — every frame tells viewers where it came from.")

# Session state for montage basket
if "montage_clips" not in st.session_state:
    st.session_state.montage_clips = []
if "montage_title" not in st.session_state:
    st.session_state.montage_title = "THE REAL WINDY CITY — My Montage"

# Sidebar: instructions
with st.sidebar:
    st.header("How to Build")
    st.markdown("""
1. **Search** transcriptions (minutes, captions) below
2. **Add** clips to basket — each clip has timestamp, date, clip_id, external_url + local_path
3. **Arrange** order, set start/end
4. **Build** project → preview cards + watermark proof
5. **Render** (if ffmpeg on server) or export JSON for Colab render
6. **Export** MP4 + SRT + POST kit — watermark mandatory
7. **Share** to social via buttons — watermark ensures platform attribution
    """)
    st.divider()
    st.write("**Watermark mandatory:**")
    st.code("THE REAL WINDY CITY — therealwindycity.com\n+ source clip_id/date burned into every frame", language="text")
    if st.button("Clear basket"):
        st.session_state.montage_clips = []
        st.toast("Basket cleared")

# Top: title
st.session_state.montage_title = st.text_input("Montage title", value=st.session_state.montage_title)

# Two columns: search + basket
col_search, col_basket = st.columns([2,1])

with col_search:
    st.subheader("🔎 Search Transcriptions — Pull Up Videos Via Words")

    # Load corpus for search
    CORPUS_DIR = ROOT / "pipeline/corpus"
    corpus = []
    if corpus_search and CORPUS_DIR.is_dir():
        files = sorted(CORPUS_DIR.glob("*.txt"))
        sig = (len(files), max((f.stat().st_mtime for f in files), default=0))
        corpus = corpus_search.load_corpus(CORPUS_DIR)
        st.caption(f"{len(corpus)} transcripts indexed (17 years) — verbatim, searchable")
    else:
        st.info("Corpus not loaded — using cityvideos.json + meetings.json for search")

    # Also RAG vectordb_sample search
    rag_query = None
    try:
        from rag.query import hybrid_search
        rag_available = True
    except Exception:
        rag_available = False

    query = st.text_input("Search every word (e.g. annexation, water, Miller, 15-1-402)", value="annexation", key="montage_search")

    hits = []
    if query and corpus_search and corpus:
        hits = corpus_search.search(corpus, query)[:50]
        st.write(f"**{len(hits)} transcript hits**")

    # Show hits with add button
    for i, h in enumerate(hits[:20]):
        with st.container(border=True):
            c1, c2 = st.columns([3,1])
            with c1:
                st.markdown(f"**{h.get('date')}** · `{h.get('file')}`")
                st.markdown(f"> …{h.get('snippet','')[:300]}…")
                # Try to parse clip_id
                clip_id = None
                m = re.match(r"(\d+)_", Path(h.get('file','')).name)
                if m:
                    clip_id = int(m.group(1))
                # YouTube lookup
                yt_id = None
                try:
                    cv = json.loads((ROOT / "pipeline/cityvideos.json").read_text())
                    yt_info = cv.get("meetings", {}).get(h.get('date'), {})
                    yt_id = yt_info.get("id") if isinstance(yt_info, dict) else yt_info
                except Exception:
                    pass
                st.caption(f"clip_id={clip_id} | YouTube={yt_id} | external: https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id={clip_id}" if clip_id else "")
            with c2:
                if st.button(f"Add to reel", key=f"add_hit_{i}"):
                    # Add 60 sec clip around hit
                    # If hit has context with timestamp? corpus_search doesn't have t_start, but we can default 0
                    new_clip = {
                        "clip_id": clip_id,
                        "date": h.get('date'),
                        "start": "00:00:00",
                        "end": "00:01:00",
                        "title": h.get('snippet','')[:80],
                        "source_text": h.get('snippet',''),
                        "external_url": f"https://cheyenne.granicus.com/AgendaViewer.php?view_id=2&clip_id={clip_id}" if clip_id else "",
                        "local_path": f"server_data/cheyenne/meetings/{clip_id}/video/meeting.mp4" if clip_id else "",
                        "youtube_id": yt_id,
                    }
                    st.session_state.montage_clips.append(new_clip)
                    st.toast(f"Added {h.get('date')} to basket")

    # Also show recent 6 months meetings as quick add
    st.divider()
    st.subheader("⚡ Quick Add — Recent 6 Months Real Meetings")
    if recent_meetings:
        recent = recent_meetings("cheyenne", months=6)[:15]
        for j, m in enumerate(recent):
            with st.container(border=True):
                c1, c2 = st.columns([3,1])
                with c1:
                    st.write(f"**{m.get('date')}** — {m.get('title')} | {m.get('source')}")
                    if m.get("youtube_url"):
                        st.caption(m["youtube_url"])
                with c2:
                    if st.button(f"Add", key=f"quick_add_{j}"):
                        new_clip = {
                            "clip_id": m.get("clip_id"),
                            "date": m.get("date"),
                            "start": "00:00:00",
                            "end": "00:01:00",
                            "title": m.get('title',''),
                            "source_text": "",
                            "external_url": m.get("external_url") or m.get("agenda_url") or m.get("youtube_url") or "",
                            "local_path": m.get("local_path") or "",
                            "youtube_id": m.get("youtube_id"),
                        }
                        st.session_state.montage_clips.append(new_clip)
                        st.toast(f"Added {m.get('date')}")

with col_basket:
    st.subheader(f"🧺 Basket — {len(st.session_state.montage_clips)} clips")
    if not st.session_state.montage_clips:
        st.info("Basket empty — search and add clips")
    else:
        # Editable list
        for idx, clip in enumerate(st.session_state.montage_clips):
            with st.expander(f"{idx+1}. {clip.get('date')} — {clip.get('title')[:50]}", expanded=(idx==0)):
                clip["start"] = st.text_input(f"Start (HH:MM:SS)", value=clip.get("start","00:00:00"), key=f"start_{idx}")
                clip["end"] = st.text_input(f"End (HH:MM:SS)", value=clip.get("end","00:01:00"), key=f"end_{idx}")
                clip["title"] = st.text_input(f"Title / caption", value=clip.get("title",""), key=f"title_{idx}")
                st.caption(f"clip_id={clip.get('clip_id')} | YouTube={clip.get('youtube_id')}")
                st.caption(f"External: {clip.get('external_url')}")
                st.caption(f"Local: {clip.get('local_path')}")
                if st.button(f"Remove", key=f"remove_{idx}"):
                    st.session_state.montage_clips.pop(idx)
                    st.rerun()

        st.divider()
        st.subheader("Build Montage")

        output_name = st.text_input("Output filename", value="my_montage.mp4")
        vertical = st.checkbox("Vertical 1080x1920 (for TikTok/Reels/Shorts)", value=True)
        watermark = st.checkbox("Watermark mandatory — THE REAL WINDY CITY", value=True, disabled=True, help="Mandatory for shared videos — every frame burned with platform attribution")

        if st.button("🔨 Build Project JSON + SRT + POST kit", type="primary", use_container_width=True):
            if MontageBuilder is None:
                st.error("MontageBuilder not available — exporting manual JSON")
                # Manual export
                project = {
                    "city": "cheyenne",
                    "output": output_name,
                    "title": st.session_state.montage_title,
                    "vertical": vertical,
                    "watermark": True,
                    "watermark_text": "THE REAL WINDY CITY — therealwindycity.com",
                    "clips": st.session_state.montage_clips,
                    "created_at": datetime.utcnow().isoformat(),
                }
                st.session_state.last_project = project
                st.success("Project JSON built (no ffmpeg) — download below, render in Colab/server")
            else:
                builder = MontageBuilder(city="cheyenne", root="server_data")
                for clip in st.session_state.montage_clips:
                    builder.add_clip(
                        clip_id=clip.get("clip_id"),
                        date=clip.get("date"),
                        start=clip.get("start"),
                        end=clip.get("end"),
                        title=clip.get("title"),
                        source_text=clip.get("source_text",""),
                        external_url=clip.get("external_url",""),
                        local_path=clip.get("local_path",""),
                        youtube_id=clip.get("youtube_id"),
                    )
                project = builder.build_project(output=output_name, title=st.session_state.montage_title, vertical=vertical, watermark=watermark)
                st.session_state.last_project = project
                st.success(f"Project built: {project['id']} — {len(project['segments'])} segments, {project['total_duration']}s")

        # Show last project
        if "last_project" in st.session_state:
            proj = st.session_state.last_project
            st.json(proj)

            # Download buttons
            proj_dir = Path(f"server_data/cheyenne/montages/{proj['id']}") if "id" in proj else None
            if proj_dir and (proj_dir / "project.json").exists():
                st.download_button("Download project.json", data=(proj_dir / "project.json").read_bytes(), file_name="project.json")
                srt_file = proj_dir / f"{Path(proj['output']).stem}.srt"
                if srt_file.exists():
                    st.download_button("Download .srt captions", data=srt_file.read_bytes(), file_name=srt_file.name)
                post_file = proj_dir / f"POST_{Path(proj['output']).stem}.txt"
                if post_file.exists():
                    st.download_button("Download POST kit (social caption)", data=post_file.read_bytes(), file_name=post_file.name)
                    st.text_area("POST kit preview", post_file.read_text()[:1000], height=200)

            # Render button if ffmpeg available
            if MontageBuilder and st.button("🎬 Render MP4 with Watermark (requires ffmpeg + local videos)", use_container_width=True):
                try:
                    builder = MontageBuilder(city="cheyenne", root="server_data")
                    for clip in st.session_state.montage_clips:
                        builder.add_clip(
                            clip_id=clip.get("clip_id"),
                            date=clip.get("date"),
                            start=clip.get("start"),
                            end=clip.get("end"),
                            title=clip.get("title"),
                            source_text=clip.get("source_text",""),
                            external_url=clip.get("external_url",""),
                            local_path=clip.get("local_path",""),
                            youtube_id=clip.get("youtube_id"),
                        )
                    # Need to rebuild project if not already
                    if "id" not in proj:
                        proj = builder.build_project(output=output_name, title=st.session_state.montage_title, vertical=vertical, watermark=True)
                    result = builder.render(proj, watermark=True, vertical=vertical)
                    st.json(result)
                    if result.get("status") == "rendered":
                        out_path = Path(result["output"])
                        if out_path.exists():
                            st.success(f"Rendered {out_path} — watermark burned into every frame")
                            st.video(str(out_path))
                            st.download_button("Download watermarked MP4", data=out_path.read_bytes(), file_name=out_path.name, mime="video/mp4")
                except Exception as e:
                    st.error(f"Render failed: {e} — export project JSON and render in Colab/server with ffmpeg")
                    st.code(f"python -c \"from engine.montage_builder import MontageBuilder; b=MontageBuilder(); ...; b.render(...)\"", language="bash")

st.divider()
st.header("📤 Share Directly to Social Media — Watermarked")

st.write("Every exported video has mandatory watermark so viewers know platform: **THE REAL WINDY CITY — therealwindycity.com** + source clip_id/date burned into every frame via ffmpeg drawtext. Logo overlay optional.")

col_s1, col_s2, col_s3, col_s4 = st.columns(4)

# Build share text from last project
share_text = st.session_state.montage_title
if "last_project" in st.session_state:
    proj = st.session_state.last_project
    share_text = proj.get("title", share_text) + f" — {len(proj.get('source_clips',[]))} meetings, every panel sourced. THE REAL WINDY CITY therealwindycity.com"

with col_s1:
    # Twitter/X
    twitter_url = f"https://twitter.com/intent/tweet?text={share_text[:200]}"
    st.link_button("𝕏 Share to X/Twitter", twitter_url, use_container_width=True)

with col_s2:
    # Facebook
    fb_url = f"https://www.facebook.com/sharer/sharer.php?u=https://therealwindycity.com"
    st.link_button("📘 Share to Facebook", fb_url, use_container_width=True)

with col_s3:
    # Reddit
    reddit_url = f"https://www.reddit.com/submit?title={share_text[:100]}&url=https://therealwindycity.com"
    st.link_button("👽 Share to Reddit", reddit_url, use_container_width=True)

with col_s4:
    # Download for TikTok/Reels/Shorts (vertical)
    st.write("**For TikTok / Reels / Shorts:**")
    st.caption("Download vertical MP4 1080x1920 + SRT + POST kit, upload to app — watermark already burned in")

st.divider()
st.write("**How watermark works (technical):**")
st.code("""
# ffmpeg filter (from engine/montage_builder.py + tools/watermark.py):
-vf "
scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,
drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='THE REAL WINDY CITY — therealwindycity.com':fontcolor=white:fontsize=24:x=w-text_w-20:y=h-text_h-20:box=1:boxcolor=black@0.6:boxborderw=6,
drawtext=fontfile=...:text='clip 1103 2026-06-22 01:22:10-01:25:00':fontcolor=0xFFD166:fontsize=18:x=20:y=20:box=1:boxcolor=black@0.6
"
# Optional logo overlay:
[0:v][1:v]overlay=W-w-20:H-h-20

Every frame → platform attribution guaranteed.
""", language="bash")

st.write("**Local server storage for montages:** `server_data/<city>/montages/<id>/` {project.json, rendered.mp4 (watermarked), .srt, POST_*.txt, manifest.json with watermark_proof + external_urls + local_paths}")
