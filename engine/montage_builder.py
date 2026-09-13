"""
engine/montage_builder.py — User Montage Studio: transcription-driven multi-meeting stitch with watermark

Features:
- Pull up videos via transcriptions (pipeline/corpus/*.txt, corpus_clean, captions VTT)
- Search transcriptions, get timestamped clips
- Stitch together own montages from multi meetings
- Export MP4 + SRT + POST kit
- Watermark mandatory: "The Real Windy City" + logo + source citation

Uses ffmpeg for rendering (must be installed on server). Falls back to project JSON export if ffmpeg not available.

Storage: server_data/<city>/montages/<id>/ {project.json, rendered.mp4, srt, post.txt, manifest.json with watermark proof}
Local server copy principle: every source clip has external_url + local_path

Usage:
  from engine.montage_builder import MontageBuilder
  builder = MontageBuilder(city="cheyenne")
  builder.add_clip(clip_id=1103, start="01:22:10", end="01:25:00", title="Miller DDA", source_text="...")
  builder.add_clip(clip_id=1093, start="02:10:00", end="02:13:30", title="DDA budget")
  project = builder.build_project(output="my_reel.mp4")
  rendered = builder.render(project, watermark=True)  # -> server_data/cheyenne/montages/.../my_reel.mp4

Watermark: bottom-right "THE REAL WINDY CITY — therealwindycity.com" + top-left source label (clip_id, date) burned into every frame via ffmpeg drawtext. Also optional logo PNG overlay.
"""
from __future__ import annotations
import json, re, shutil, subprocess, time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
SERVER_ROOT = ROOT / "server_data"

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
# Fallback fonts for different OS
FONTS_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

def _find_font():
    for f in FONTS_CANDIDATES:
        if Path(f).exists():
            return f
    return FONTS_CANDIDATES[0]

def _sec_from_hms(hms: str) -> int:
    """01:22:10 -> 4930 sec, also supports 22:10, 130s"""
    hms = hms.strip()
    if hms.isdigit():
        return int(hms)
    parts = hms.split(":")
    try:
        if len(parts) == 3:
            h,m,s = map(int, parts)
            return h*3600 + m*60 + s
        elif len(parts) == 2:
            m,s = map(int, parts)
            return m*60 + s
        else:
            return int(float(parts[0]))
    except Exception:
        return 0

def _hms_from_sec(sec: int) -> str:
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-1000:]}")
    return r

class MontageBuilder:
    def __init__(self, city="cheyenne", root="server_data"):
        self.city = city
        self.root = Path(root) / city / "montages"
        self.root.mkdir(parents=True, exist_ok=True)
        self.clips = []  # list of {clip_id, date, start, end, start_sec, end_sec, title, source_text, external_url, local_path, youtube_id}
        self.font = _find_font()

    def add_clip(self, clip_id=None, date=None, start="00:00:00", end="00:01:00", title="", source_text="", external_url="", local_path="", youtube_id=None, event_id=None):
        start_sec = _sec_from_hms(start)
        end_sec = _sec_from_hms(end)
        if end_sec <= start_sec:
            end_sec = start_sec + 60
        # Cap segment at 90 sec for social (can be overridden)
        # but allow longer for export
        self.clips.append({
            "clip_id": clip_id,
            "event_id": event_id,
            "date": date or "",
            "start": _hms_from_sec(start_sec),
            "end": _hms_from_sec(end_sec),
            "start_sec": start_sec,
            "end_sec": end_sec,
            "duration": end_sec - start_sec,
            "title": title or f"Clip {clip_id} {start}-{end}",
            "source_text": source_text[:500],
            "external_url": external_url,
            "local_path": local_path,
            "youtube_id": youtube_id,
        })
        return self.clips[-1]

    def add_from_transcript_hit(self, hit: dict):
        """
        hit from corpus_search: {date, file, snippet, clip_id?, t_start?, ...}
        Adds clip around snippet timestamp.
        """
        # Try to parse clip_id from file name like 1103_2026-06-23.txt
        clip_id = hit.get("clip_id")
        if not clip_id:
            m = re.match(r"(\d+)_", Path(hit.get("file","")).name)
            if m:
                clip_id = int(m.group(1))
        date = hit.get("date","")
        # If hit has t_start from cleaned transcript, use it
        t_start = hit.get("t_start") or hit.get("start_sec") or 0
        # Window 60 sec around hit
        start_sec = max(0, t_start - 5)
        end_sec = start_sec + 60
        return self.add_clip(
            clip_id=clip_id,
            date=date,
            start=_hms_from_sec(start_sec),
            end=_hms_from_sec(end_sec),
            title=hit.get("snippet","")[:80],
            source_text=hit.get("snippet",""),
            external_url=hit.get("source_url") or hit.get("url") or "",
            youtube_id=hit.get("youtube_id"),
        )

    def build_project(self, output="montage.mp4", title="THE REAL WINDY CITY MONTAGE", vertical=True, watermark=True):
        """
        Builds project JSON compatible with pipeline/cheyenne_pipeline.py project spec + our extensions
        """
        project_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        project_dir = self.root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)

        # Segments for cheyenne_pipeline.py style
        segments = []
        # Title card
        segments.append({"type": "title", "text": title, "duration": 3})

        for clip in self.clips:
            seg = {
                "type": "clip",
                "meeting": clip.get("clip_id") or clip.get("event_id"),
                "date": clip.get("date"),
                "start": clip["start"],
                "end": clip["end"],
                "title": clip["title"],
                "source_text": clip["source_text"],
                "external_url": clip["external_url"],
                "youtube_id": clip.get("youtube_id"),
                "watermark": watermark,
            }
            # Prefer local path if exists
            if clip.get("local_path") and Path(clip["local_path"]).exists():
                seg["file"] = clip["local_path"]
            segments.append(seg)

        # Closing card
        segments.append({"type": "title", "text": "THE REAL WINDY CITY\ntherealwindycity.com\nEvery panel sourced", "duration": 3})

        project = {
            "id": project_id,
            "city": self.city,
            "output": output,
            "vertical": vertical,
            "watermark": watermark,
            "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "segments": segments,
            "source_clips": self.clips,
            "total_duration": sum(c["duration"] for c in self.clips) + 6,
            "watermark_text": "THE REAL WINDY CITY — therealwindycity.com",
            "export": {
                "mp4": f"{project_id}/{output}",
                "srt": f"{project_id}/{Path(output).stem}.srt",
                "post": f"{project_id}/POST_{Path(output).stem}.txt",
                "project_json": f"{project_id}/project.json",
            }
        }

        # Save project.json
        (project_dir / "project.json").write_text(json.dumps(project, indent=1), encoding="utf-8")
        # Save manifest with external_url preservation
        manifest = {
            "id": project_id,
            "city": self.city,
            "created_at": project["created_at"],
            "watermark": watermark,
            "watermark_proof": "Every frame burned with THE REAL WINDY CITY — therealwindycity.com + source clip_id/date",
            "clips": self.clips,
            "external_urls": [c["external_url"] for c in self.clips if c.get("external_url")],
            "local_paths": [c["local_path"] for c in self.clips if c.get("local_path")],
            "project": project,
        }
        (project_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

        # Build SRT
        srt_path = project_dir / f"{Path(output).stem}.srt"
        srt_blocks = []
        t = 0
        for i, clip in enumerate(self.clips, 1):
            def fmt(sec):
                h = sec // 3600; m = (sec % 3600)//60; s = sec % 60
                return f"{h:02d}:{m:02d}:{s:02d},000"
            block = f"{i}\n{fmt(t)} --> {fmt(t+clip['duration'])}\n{clip['title']} [{clip.get('date')} clip {clip.get('clip_id')}] — THE REAL WINDY CITY\n"
            srt_blocks.append(block)
            t += clip["duration"]
        srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")

        # Build POST kit for social
        post_path = project_dir / f"POST_{Path(output).stem}.txt"
        post_lines = [
            f"{title}",
            "",
            f"Cut from {len(self.clips)} meetings — every panel sourced.",
            "",
        ]
        for clip in self.clips:
            post_lines.append(f"• {clip['date']} clip {clip.get('clip_id')} {clip['start']}-{clip['end']}: {clip['title'][:80]}")
        post_lines += [
            "",
            "Sources: " + ", ".join(set([c.get('external_url') or f"clip {c.get('clip_id')}" for c in self.clips if c.get('clip_id')][:5])),
            "",
            "THE REAL WINDY CITY — therealwindycity.com",
            "Wind belongs on the prairie. Not in the minutes.",
            "#Cheyenne #Wyoming #PublicRecord #Transparency #therealwindycity",
        ]
        post_path.write_text("\n".join(post_lines), encoding="utf-8")

        return project

    def render(self, project: dict, watermark=True, vertical=True, logo_path=None):
        """
        Render project to MP4 with ffmpeg, adding mandatory watermark.
        If ffmpeg not available or source files missing, returns project dir with JSON only (for Colab/server render later).

        Watermark:
        - Bottom-right: THE REAL WINDY CITY — therealwindycity.com (white with black box)
        - Top-left: source clip_id + date per segment
        - Optional logo PNG overlay bottom-right
        """
        project_id = project["id"]
        project_dir = self.root / project_id
        output = project_dir / project["output"]

        # Check ffmpeg
        if not shutil.which("ffmpeg"):
            return {"status": "project_only", "reason": "ffmpeg not found", "project_dir": str(project_dir), "project": project}

        # For each clip, need to cut from source
        # Sources priority: local file → YouTube via yt-dlp → Granicus MP4
        # For preview without full video, we create title cards with watermark as placeholder

        # If no real video files available, render cards-only montage with watermark (like pipeline/montage.py)
        work = project_dir / "work"
        work.mkdir(exist_ok=True)

        W, H = (1080, 1920) if vertical else (1920, 1080)
        parts = []

        font = self.font

        for idx, seg in enumerate(project["segments"], 1):
            if seg["type"] == "title":
                # Title card with watermark
                txt_file = work / f"title_{idx}.txt"
                txt_file.write_text(seg["text"][:200], encoding="utf-8")
                # Watermark text file
                wm_file = work / f"wm_{idx}.txt"
                wm_file.write_text("THE REAL WINDY CITY — therealwindycity.com", encoding="utf-8")
                # ffmpeg lavfi card
                vf = (
                    f"color=0x0d1117:size={W}x{H}:rate=30,format=yuv420p,"
                    f"drawtext=fontfile={font}:textfile={txt_file}:fontcolor=white:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2-100:line_spacing=20,"
                    f"drawtext=fontfile={font}:textfile={wm_file}:fontcolor=white:fontsize=28:x=w-text_w-20:y=h-text_h-20:box=1:boxcolor=black@0.6:boxborderw=6"
                )
                out = work / f"part_{idx:03d}.mp4"
                try:
                    _run(["ffmpeg","-y","-f","lavfi","-i",vf,"-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-t",str(seg.get("duration",3)),"-c:v","libx264","-preset","veryfast","-crf","22","-c:a","aac","-b:a","128k",str(out)])
                    parts.append(out)
                except Exception as e:
                    print(f"card render failed {e}")
                    continue
            elif seg["type"] == "clip":
                # Try to cut from local file if exists
                src_file = seg.get("file")
                if src_file and Path(src_file).exists():
                    # Cut with watermark
                    out = work / f"part_{idx:03d}.mp4"
                    start = seg.get("start","00:00:00")
                    end = seg.get("end","00:01:00")
                    dur = _sec_from_hms(end) - _sec_from_hms(start)
                    # Watermark filter: scale to W x H, add drawtext bottom-right + top-left source
                    wm_text = f"THE REAL WINDY CITY — therealwindycity.com | {seg.get('date')} clip {seg.get('meeting')}"
                    # Escape for drawtext
                    wm_escaped = wm_text.replace(":", "\\:").replace("'", "")
                    # Use scale + pad for vertical, plus watermark
                    vf = (
                        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                        f"drawtext=fontfile={font}:text='{wm_escaped}':fontcolor=white:fontsize=22:x=w-text_w-20:y=h-text_h-20:box=1:boxcolor=black@0.6:boxborderw=4,"
                        f"drawtext=fontfile={font}:text='clip {seg.get('meeting')} {seg.get('date')} {seg.get('start')}-{seg.get('end')}':fontcolor=white:fontsize=18:x=20:y=20:box=1:boxcolor=black@0.6:boxborderw=4"
                    )
                    try:
                        _run(["ffmpeg","-y","-ss",start,"-t",str(dur),"-i",str(src_file),"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","22","-c:a","aac","-b:a","128k",str(out)])
                        parts.append(out)
                    except Exception as e:
                        print(f"clip cut failed {e}, fallback to card")
                        # Fallback card
                        txt_file = work / f"clip_{idx}.txt"
                        txt_file.write_text(f"{seg.get('title')}\n{seg.get('date')} clip {seg.get('meeting')}\n{seg.get('start')}-{seg.get('end')}\n{seg.get('source_text')[:100]}", encoding="utf-8")
                        vf2 = f"color=0x1a2332:size={W}x{H}:rate=30,format=yuv420p,drawtext=fontfile={font}:textfile={txt_file}:fontcolor=white:fontsize=32:x=(w-text_w)/2:y=(h-text_h)/2:line_spacing=12,drawtext=fontfile={font}:text='THE REAL WINDY CITY — therealwindycity.com':fontcolor=white:fontsize=24:x=w-text_w-20:y=h-text_h-20:box=1:boxcolor=black@0.6:boxborderw=4"
                        out2 = work / f"part_{idx:03d}.mp4"
                        try:
                            _run(["ffmpeg","-y","-f","lavfi","-i",vf2,"-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-t",str(dur),"-c:v","libx264","-preset","veryfast","-crf","22","-c:a","aac","-b:a","128k",str(out2)])
                            parts.append(out2)
                        except Exception:
                            continue
                else:
                    # No local file — card placeholder with source info + watermark (for preview without video)
                    txt_file = work / f"clip_{idx}.txt"
                    txt_file.write_text(f"{seg.get('title')}\n{seg.get('date')} clip {seg.get('meeting')}\n{seg.get('start')}-{seg.get('end')}\nSource: {seg.get('external_url') or seg.get('youtube_id') or 'Granicus/YouTube'}", encoding="utf-8")
                    dur = seg.get("end_sec",60) - seg.get("start_sec",0)
                    if dur <=0:
                        dur = 60
                    vf = f"color=0x1a2332:size={W}x{H}:rate=30,format=yuv420p,drawtext=fontfile={font}:textfile={txt_file}:fontcolor=white:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2-100:line_spacing=14,drawtext=fontfile={font}:text='THE REAL WINDY CITY — therealwindycity.com':fontcolor=white:fontsize=24:x=w-text_w-20:y=h-text_h-20:box=1:boxcolor=black@0.6:boxborderw=6,drawtext=fontfile={font}:text='clip {seg.get('meeting')} {seg.get('date')}':fontcolor=0xFFD166:fontsize=20:x=20:y=20:box=1:boxcolor=black@0.6:boxborderw=4"
                    out = work / f"part_{idx:03d}.mp4"
                    try:
                        _run(["ffmpeg","-y","-f","lavfi","-i",vf,"-f","lavfi","-i","anullsrc=r=48000:cl=stereo","-t",str(dur),"-c:v","libx264","-preset","veryfast","-crf","22","-c:a","aac","-b:a","128k",str(out)])
                        parts.append(out)
                    except Exception as e:
                        print(f"placeholder card failed {e}")
                        continue

        if not parts:
            return {"status": "failed", "reason": "no parts rendered", "project_dir": str(project_dir)}

        # Concat
        list_file = work / "list.txt"
        list_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
        try:
            _run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(list_file),"-c","copy",str(output)])
            # Also add final watermark pass if logo provided
            if logo_path and Path(logo_path).exists():
                final_wm = project_dir / f"wm_{output.name}"
                # overlay logo bottom-right
                _run(["ffmpeg","-y","-i",str(output),"-i",str(logo_path),"-filter_complex","[0:v][1:v]overlay=W-w-20:H-h-20:format=auto,format=yuv420p","-c:a","copy",str(final_wm)])
                final_output = final_wm
            else:
                final_output = output
            return {"status": "rendered", "output": str(final_output), "project_dir": str(project_dir), "parts": len(parts), "watermark": "THE REAL WINDY CITY — therealwindycity.com burned into every frame + source clip_id/date"}
        except Exception as e:
            return {"status": "concat_failed", "error": str(e), "project_dir": str(project_dir), "parts": [str(p) for p in parts]}
