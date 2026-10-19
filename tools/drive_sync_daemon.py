"""Drive sync loop.

Runs forever, checking every 60 seconds whether syncing is currently
"on" (controlled by drive_sync_control.sh via a tiny state file). When
on, it pushes everything in output/ to the configured rclone remote.
When off, it just idles — so turning sync back on is instant, with no
process to relaunch.
"""
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone

STATE_DIR = Path.home() / ".config" / "drive_sync"
STATE_FILE = STATE_DIR / "state"
LAST_SYNC_FILE = STATE_DIR / "last_sync"
REMOTE = "gdrive:"


def is_on() -> bool:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        return STATE_FILE.read_text().strip() == "on"
    except FileNotFoundError:
        STATE_FILE.write_text("on")
        return True


def sync_once() -> None:
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["rclone", "copy", str(out_dir), REMOTE, "--update", "--quiet"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    ts = datetime.now(timezone.utc).isoformat()
    if result.returncode == 0:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LAST_SYNC_FILE.write_text(ts)
        print(f"[{ts}] synced output/ -> {REMOTE}", flush=True)
    else:
        print(f"[{ts}] sync error: {result.stderr.strip()}", flush=True)


def main() -> None:
    print("=== drive sync daemon loop started ===", flush=True)
    while True:
        if is_on():
            sync_once()
        else:
            print(f"[{datetime.now(timezone.utc).isoformat()}] paused (stopped)", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
