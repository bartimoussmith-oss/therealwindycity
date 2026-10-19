#!/usr/bin/env python3
"""headless_transcript_harvester.py — Termux-friendly transcript puller.

Pulls YouTube auto-caption transcripts for every meeting already indexed
in this repo's pipeline/cityvideos.json (260 known date -> video-ID
mappings) and writes them as shard markdown files into output/, where
the Drive sync daemon (drive_sync_control.sh) picks them up and pushes
them to Google Drive automatically within ~30 seconds.

Why this instead of scraping the live YouTube channel page:
  - pipeline/cityvideos.json is this repo's own already-verified index.
    Re-discovering video IDs by scraping the channel each run is slower
    and more likely to trip YouTube's bot checks on bulk requests.
  - --sub-langs en.*,en (NOT "all") is the flag already proven to work
    against this exact channel in tools/colab_media_backfill.py. "all"
    can pull dozens of auto-translated caption tracks you don't want.
  - A short sleep between requests to stay polite / avoid rate limits.

Resumable: re-run any time. It records progress after every single video
(not just every shard), so Ctrl-C loses at most one in-flight video. To
retry a specific meeting later (e.g. captions weren't ready yet), delete
its entry from output/transcripts/.harvest_state.json.

Requires (installed automatically if missing, except ffmpeg):
  pkg install -y ffmpeg     # Termux native package, not pip-installable
  pip install yt-dlp webvtt-py   # done automatically by this script
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CITYVIDEOS_URL = (
    "https://raw.githubusercontent.com/bartimoussmith-oss/therealwindycity/"
    "arena/ee3b8c9e-therealwindycity/pipeline/cityvideos.json"
)
CITYVIDEOS_LOCAL = Path("pipeline/cityvideos.json")
OUTPUT_DIR = Path("output/transcripts")
SHARD_DIR = Path("output")
STATE_FILE = OUTPUT_DIR / ".harvest_state.json"
SHARD_SIZE = 100
REQUEST_SLEEP_SECONDS = 1.5


def ensure_deps() -> None:
    import importlib

    try:
        importlib.import_module("webvtt")
    except ImportError:
        print("[*] Installing webvtt-py...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "webvtt-py"], check=True)

    rc = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    if rc.returncode != 0:
        print("[*] Installing yt-dlp...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"], check=True)

    ff = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    if ff.returncode != 0:
        print("[!] ffmpeg not found. Run:  pkg install -y ffmpeg", flush=True)
        sys.exit(1)


def load_meetings() -> list:
    if not CITYVIDEOS_LOCAL.exists():
        print(f"[*] Fetching meeting index from repo -> {CITYVIDEOS_LOCAL}", flush=True)
        CITYVIDEOS_LOCAL.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(CITYVIDEOS_URL, CITYVIDEOS_LOCAL)
    data = json.loads(CITYVIDEOS_LOCAL.read_text())
    out = []
    for date, m in sorted(data.get("meetings", {}).items()):
        if not m:
            continue
        vid = m.get("id") if isinstance(m, dict) else m
        title = m.get("title", date) if isinstance(m, dict) else date
        if vid:
            out.append({"date": date, "id": vid, "title": title})
    return out


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1))


def fetch_transcript(video_id: str, date: str):
    out_tpl = str(OUTPUT_DIR / f"{date}_{video_id}")
    cmd = [
        "yt-dlp", "--skip-download", "--write-auto-subs",
        "--sub-langs", "en.*,en", "--convert-subs", "vtt",
        "-o", out_tpl, f"https://www.youtube.com/watch?v={video_id}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    vtt_files = sorted(OUTPUT_DIR.glob(f"{date}_{video_id}*.vtt"))
    if not vtt_files:
        return None, result.stderr.strip()[-500:]

    import webvtt
    cleaned = []
    try:
        for caption in webvtt.read(str(vtt_files[0])):
            text = caption.text.strip().replace("\n", " ")
            if not cleaned or cleaned[-1] != text:
                cleaned.append(text)
    finally:
        for f in vtt_files:
            f.unlink(missing_ok=True)
    return " ".join(cleaned), None


def next_free_shard_number() -> int:
    existing = sorted(SHARD_DIR.glob("Cheyenne_Omni_Corpus_Shard_*.md"))
    nums = [
        int(p.stem.rsplit("_", 1)[-1])
        for p in existing
        if p.stem.rsplit("_", 1)[-1].isdigit()
    ]
    return (max(nums) + 1) if nums else 1


def main() -> None:
    ensure_deps()
    meetings = load_meetings()
    state = load_state()
    todo = [m for m in meetings if m["id"] not in state]
    print(f"[*] {len(meetings)} indexed meetings total, {len(todo)} left to harvest", flush=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shard_content = ""
    shard_count = 0
    shard_num = next_free_shard_number()

    for i, m in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {m['date']} - {m['title']}", flush=True)
        transcript, err = fetch_transcript(m["id"], m["date"])
        state[m["id"]] = {"date": m["date"], "has_transcript": bool(transcript)}

        if transcript:
            shard_content += (
                f"\n\n## RECORDING_TITLE: {m['title']}\n"
                f"## MEETING_DATE: {m['date']}\n"
                f"## SOURCE_URL: https://www.youtube.com/watch?v={m['id']}\n"
                f"## TRANSCRIPT:\n{transcript}\n" + ("-" * 50) + "\n"
            )
            shard_count += 1
        else:
            print(f"    [!] no transcript ({err or 'none available'})", flush=True)

        if shard_count >= SHARD_SIZE or i == len(todo):
            if shard_content.strip():
                shard_path = SHARD_DIR / f"Cheyenne_Omni_Corpus_Shard_{shard_num}.md"
                shard_path.write_text(
                    f"# CHEYENNE OMNI VIDEO CORPUS - SHARD {shard_num}\n" + shard_content,
                    encoding="utf-8",
                )
                print(f"[+] wrote {shard_path.name} ({shard_count} transcripts)", flush=True)
                shard_num += 1
                shard_count = 0
                shard_content = ""

        save_state(state)
        time.sleep(REQUEST_SLEEP_SECONDS)

    print("\n=== HARVEST COMPLETE ===", flush=True)
    have = sum(1 for v in state.values() if v.get("has_transcript"))
    print(f"{have}/{len(state)} meetings have a transcript", flush=True)


if __name__ == "__main__":
    main()
