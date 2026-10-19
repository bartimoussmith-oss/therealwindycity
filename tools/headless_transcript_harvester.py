#!/usr/bin/env python3
"""headless_transcript_harvester.py — Termux-friendly transcript puller.

Pulls YouTube auto-caption transcripts for EVERY video on the City of
Cheyenne's YouTube channel (@TheCityofCheyenne) and writes them as shard
markdown files into output/, where the Drive sync daemon picks them up
and pushes them to Google Drive automatically within ~30 seconds.

Two video sources are merged:
  1. pipeline/cityvideos.json — this repo's own pre-verified index of
     260 council meetings (date + title are exact for these).
  2. A live scan of the channel's /videos AND /streams tabs via
     yt-dlp --flat-playlist, so anything NOT already indexed (PSAs,
     announcements, specials, newer uploads, livestream VODs filed
     under "streams" instead of "videos") is still picked up. Dates
     for this group are approximate (from yt-dlp's "x months ago"
     parsing) since getting exact dates needs a full per-video request.

Resumable: re-run any time. Progress is recorded after every single
video (not just every shard), so Ctrl-C loses at most one in-flight
video. To retry a specific video later (e.g. captions weren't ready
yet), delete its entry from output/transcripts/.harvest_state.json.

Requires (installed/updated automatically, except ffmpeg):
  pkg install -y ffmpeg     # Termux native package, not pip-installable
  pip install -U yt-dlp webvtt-py   # done automatically by this script
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CHANNEL_HANDLE = "@TheCityofCheyenne"
CHANNEL_BASE = f"https://www.youtube.com/{CHANNEL_HANDLE}"
CHANNEL_TABS = ["videos", "streams"]

CITYVIDEOS_URL = (
    "https://raw.githubusercontent.com/bartimoussmith-oss/therealwindycity/"
    "arena/ee3b8c9e-therealwindycity/pipeline/cityvideos.json"
)
CITYVIDEOS_LOCAL = Path("pipeline/cityvideos.json")
OUTPUT_DIR = Path("output/transcripts")
SHARD_DIR = Path("output")
STATE_FILE = OUTPUT_DIR / ".harvest_state.json"
LOG_FILE = OUTPUT_DIR / "harvest_errors.log"
SHARD_SIZE = 100
REQUEST_SLEEP_SECONDS = 2.0

# Known bot-check / rate-limit phrases so a run tells you plainly what's
# actually blocking it instead of silently reporting "no transcript".
BOT_CHECK_MARKERS = (
    "sign in to confirm",
    "not a bot",
    "confirm you're not a bot",
    "http error 429",
    "too many requests",
)


def log_error(text: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\n" + ("-" * 40) + "\n")


def ensure_deps() -> None:
    import importlib

    try:
        importlib.import_module("webvtt")
    except ImportError:
        print("[*] Installing webvtt-py...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "webvtt-py"], check=True)

    print("[*] Making sure yt-dlp is up to date (YouTube breaks old versions often)...", flush=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"], check=False)
    rc = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    if rc.returncode != 0:
        print("[!] yt-dlp still not runnable after install attempt.", flush=True)
        sys.exit(1)
    print(f"    yt-dlp version: {rc.stdout.strip()}", flush=True)

    ff = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    if ff.returncode != 0:
        print("[!] ffmpeg not found. Run:  pkg install -y ffmpeg", flush=True)
        sys.exit(1)


def load_known_meetings() -> dict:
    """pipeline/cityvideos.json -> {video_id: {date, title}} (exact dates)."""
    if not CITYVIDEOS_LOCAL.exists():
        print(f"[*] Fetching meeting index from repo -> {CITYVIDEOS_LOCAL}", flush=True)
        CITYVIDEOS_LOCAL.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(CITYVIDEOS_URL, CITYVIDEOS_LOCAL)
        except Exception as e:
            print(f"[!] Could not fetch cityvideos.json ({e}); continuing with channel scan only.", flush=True)
            return {}
    data = json.loads(CITYVIDEOS_LOCAL.read_text())
    out = {}
    for date, m in data.get("meetings", {}).items():
        if not m:
            continue
        vid = m.get("id") if isinstance(m, dict) else m
        title = m.get("title", date) if isinstance(m, dict) else date
        if vid:
            out[vid] = {"date": date, "title": title}
    return out


def discover_channel_videos() -> dict:
    """Scan the channel's /videos and /streams tabs -> {video_id: {date, title}}."""
    found = {}
    for tab in CHANNEL_TABS:
        url = f"{CHANNEL_BASE}/{tab}"
        print(f"[*] Scanning channel tab: {url}", flush=True)
        cmd = [
            "yt-dlp", "--flat-playlist", "--dump-json",
            "--extractor-args", "youtubetab:approximate_date",
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if result.returncode != 0:
            err = result.stderr.strip()
            print(f"[!] Channel scan FAILED for /{tab} (exit {result.returncode})", flush=True)
            print(f"    {err[-400:]}", flush=True)
            log_error(f"channel scan /{tab} failed:\n{err}")
            lowered = err.lower()
            if any(marker in lowered for marker in BOT_CHECK_MARKERS):
                print("    >>> This looks like YouTube bot-detection blocking yt-dlp entirely.", flush=True)
                print("    >>> Every video will fail the same way until this is resolved", flush=True)
                print("    >>> (commonly needs --cookies-from-browser or a newer yt-dlp).", flush=True)
            continue
        count = 0
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid = data.get("id")
            if not vid or vid in found:
                continue
            title = data.get("title") or vid
            upload_date = data.get("upload_date")  # YYYYMMDD if present
            if upload_date and re.fullmatch(r"\d{8}", upload_date):
                date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            else:
                date = f"unknown-{vid}"
            found[vid] = {"date": date, "title": title}
            count += 1
        print(f"    +{count} videos found on /{tab}", flush=True)
    return found


def build_target_list() -> list:
    known = load_known_meetings()
    discovered = discover_channel_videos()
    merged = dict(discovered)
    merged.update(known)  # known index wins on exact date/title where ids overlap
    targets = [{"id": vid, "date": v["date"], "title": v["title"]} for vid, v in merged.items()]
    targets.sort(key=lambda m: m["date"])
    print(f"[*] {len(known)} from the known meeting index, {len(discovered)} from live channel scan, "
          f"{len(targets)} unique videos total", flush=True)
    return targets


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
        "--retries", "3", "--fragment-retries", "3",
        "--extractor-args", "youtube:player_client=default,android",
        "-o", out_tpl, f"https://www.youtube.com/watch?v={video_id}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    vtt_files = sorted(OUTPUT_DIR.glob(f"{date}_{video_id}*.vtt"))
    if not vtt_files:
        err = (result.stderr or result.stdout or "").strip()
        if err:
            log_error(f"{date} {video_id}:\n{err}")
        return None, err[-500:]

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
    targets = build_target_list()
    state = load_state()
    todo = [m for m in targets if m["id"] not in state]
    print(f"[*] {len(targets)} videos total, {len(todo)} left to harvest", flush=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shard_content = ""
    shard_count = 0
    shard_num = next_free_shard_number()
    consecutive_failures = 0
    bot_check_warned = False

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
            consecutive_failures = 0
        else:
            print(f"    [!] no transcript ({err or 'none available'})", flush=True)
            consecutive_failures += 1
            if err and any(marker in err.lower() for marker in BOT_CHECK_MARKERS) and not bot_check_warned:
                bot_check_warned = True
                print("\n    >>> This failure looks like YouTube bot-detection, not a caption/format", flush=True)
                print("    >>> issue. If this keeps happening, stop the run and report back — the fix", flush=True)
                print(f"    >>> is different (cookies/newer yt-dlp), not something to keep retrying.\n", flush=True)
            if consecutive_failures >= 10:
                print(f"\n[!] {consecutive_failures} failures in a row — stopping early.", flush=True)
                print(f"[!] Full error details are in {LOG_FILE}", flush=True)
                save_state(state)
                break

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

    print("\n=== HARVEST COMPLETE (or stopped early) ===", flush=True)
    have = sum(1 for v in state.values() if v.get("has_transcript"))
    print(f"{have}/{len(state)} videos have a transcript so far", flush=True)
    if LOG_FILE.exists():
        print(f"Full per-video error log: {LOG_FILE}", flush=True)


if __name__ == "__main__":
    main()
