"""Drive sync loop.

Runs forever, checking every 30 seconds whether syncing is currently
"on" (controlled by drive_sync_control.sh via a tiny state file). When
on, it pushes:
  1. everything in ./output/ (whatever local scripts/tools drop there)
  2. matching browser-extension capture files sitting in your real
     Chromebook/Android Downloads folder, bridged into Termux via
     `termux-setup-storage` as ~/storage/downloads

to the configured rclone remote. When off, it just idles — so turning
sync back on is instant, with no process to relaunch.
"""
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path.home() / ".config" / "drive_sync"
STATE_FILE = STATE_DIR / "state"
LAST_SYNC_FILE = STATE_DIR / "last_sync"
REMOTE = "gdrive:"
SYNC_INTERVAL_SECONDS = 30

# Browser extension captures land in the shared OS Downloads folder, not
# in Termux's private filesystem. `termux-setup-storage` (run once) makes
# that folder visible here as ~/storage/downloads. If it hasn't been run
# yet, this path just won't exist and we skip that source gracefully.
DOWNLOADS_DIR = Path.home() / "storage" / "downloads"
DOWNLOADS_INCLUDE_PATTERNS = [
    "promethean_master_archive_*.json",
]


def is_on() -> bool:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        return STATE_FILE.read_text().strip() == "on"
    except FileNotFoundError:
        STATE_FILE.write_text("on")
        return True


def run_copy(cmd) -> bool:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        ts = datetime.now(timezone.utc).isoformat()
        print(f"[{ts}] sync error ({' '.join(cmd)}): {result.stderr.strip()}", flush=True)
        return False
    return True


def sync_once() -> None:
    ok = True

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = run_copy(["rclone", "copy", str(out_dir), REMOTE, "--update", "--quiet"]) and ok

    if DOWNLOADS_DIR.exists():
        for pattern in DOWNLOADS_INCLUDE_PATTERNS:
            ok = run_copy([
                "rclone", "copy", str(DOWNLOADS_DIR), REMOTE,
                "--include", pattern, "--update", "--quiet",
            ]) and ok
    else:
        print(
            f"[{datetime.now(timezone.utc).isoformat()}] "
            f"{DOWNLOADS_DIR} not found yet - run 'termux-setup-storage' once "
            "to pull in browser-extension captures automatically",
            flush=True,
        )

    if ok:
        ts = datetime.now(timezone.utc).isoformat()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LAST_SYNC_FILE.write_text(ts)
        print(f"[{ts}] sync pass complete (output/ + browser captures)", flush=True)


def main() -> None:
    print(f"=== drive sync daemon loop started ({SYNC_INTERVAL_SECONDS}s interval) ===", flush=True)
    while True:
        if is_on():
            sync_once()
        else:
            print(f"[{datetime.now(timezone.utc).isoformat()}] paused (stopped)", flush=True)
        time.sleep(SYNC_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
