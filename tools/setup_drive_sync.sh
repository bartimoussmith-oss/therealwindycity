#!/data/data/com.termux/files/usr/bin/bash
# setup_drive_sync.sh — one-shot Google Drive sync setup for Termux.
#
# What this does, in order, with NO other steps needed from you:
#   1. Installs/repairs rclone
#   2. Wipes any previous broken service-account config (that approach
#      cannot work on a personal Gmail account — see note at bottom)
#   3. Creates an OAuth remote named "gdrive" authenticated as YOUR
#      Google account, pointed at your Promethean_Telemetry_Sync folder
#   4. Verifies the connection
#   5. Writes a corrected sync daemon (fixes the capture_output typo)
#   6. Runs one manual test push so you SEE it work before trusting it
#   7. Launches the daemon in the background with a wake-lock so Android
#      doesn't kill it, and leaves it running after you close the script
#
# The ONLY thing you have to do by hand: when it prints a Google auth
# link, open it in Chrome and tap Allow. Google requires that human
# click for every OAuth app — no script, including this one, can skip it.
#
# Usage:
#   cd ~/therealwindycity   (or wherever this repo is checked out)
#   bash tools/setup_drive_sync.sh
set -e

DRIVE_FOLDER_ID="${DRIVE_FOLDER_ID:-15QE9muLTPuA2B4DVwEqDwfxWtM7kujfz}"
REMOTE_NAME="${REMOTE_NAME:-gdrive}"

echo "=== [1/7] Installing rclone ==="
if ! command -v rclone >/dev/null 2>&1; then
  pkg update -y
  pkg install -y rclone
fi
rclone version | head -1

echo
echo "=== [2/7] Removing any previous broken config ==="
mkdir -p "$HOME/.config/rclone"
# Only touch our own remote name, never nuke a whole working config file.
if [ -f "$HOME/.config/rclone/rclone.conf" ]; then
  rclone config delete "$REMOTE_NAME" >/dev/null 2>&1 || true
fi
rm -f "$HOME/gdrive-key.json"

echo
echo "=== [3/7] Creating OAuth remote '$REMOTE_NAME' (your real account) ==="
echo "    >>> A Google sign-in link will appear below. Open it in Chrome"
echo "    >>> and tap Allow. This script will continue automatically"
echo "    >>> the moment you finish — nothing else to type."
echo
rclone config create "$REMOTE_NAME" drive \
  scope drive \
  root_folder_id "$DRIVE_FOLDER_ID"

echo
echo "=== [4/7] Verifying the connection ==="
if rclone lsd "$REMOTE_NAME": ; then
  echo "OK: authenticated and folder reachable."
else
  echo "FAILED: rclone could not list the folder. Stopping here — do not"
  echo "proceed to the daemon until 'rclone lsd $REMOTE_NAME:' succeeds."
  exit 1
fi

echo
echo "=== [5/7] Writing the corrected sync daemon ==="
mkdir -p output
mkdir -p tools
cat > tools/drive_sync_daemon.py <<PYEOF
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone

REMOTE = "${REMOTE_NAME}:"

def sync_loop():
    print("=== DRIVE SYNC DAEMON ACTIVE (60s interval) ===", flush=True)
    local_watch_dir = Path("output")
    local_watch_dir.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            json_files = list(local_watch_dir.glob("**/*.json"))
            for file_path in json_files:
                if ".processing" in file_path.name:
                    continue
                cmd = ["rclone", "copy", str(file_path), REMOTE, "--update", "--quiet"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"[{datetime.now(timezone.utc).isoformat()}] synced -> {file_path.name}", flush=True)
                else:
                    print(f"[!] sync error for {file_path.name}: {result.stderr.strip()}", flush=True)
        except Exception as e:
            print(f"[!] daemon error: {e}", flush=True)
        time.sleep(60)

if __name__ == "__main__":
    sync_loop()
PYEOF
echo "Wrote tools/drive_sync_daemon.py"

echo
echo "=== [6/7] Test push before trusting the loop ==="
TESTFILE="output/setup_test_$(date -u +%Y%m%dT%H%M%SZ).json"
echo "{\"test\":\"setup_drive_sync.sh\",\"time\":\"$(date -u +%FT%TZ)\"}" > "$TESTFILE"
rclone copy output/ "$REMOTE_NAME": --update -v
echo "--- files currently on the remote ---"
rclone lsl "$REMOTE_NAME":

echo
echo "=== [7/7] Launching the background daemon ==="
pkill -f drive_sync_daemon.py 2>/dev/null || true
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true
nohup python3 tools/drive_sync_daemon.py > sync.log 2>&1 &
disown
sleep 1
echo "Daemon PID: $(pgrep -f drive_sync_daemon.py || echo 'NOT RUNNING - check sync.log')"
echo
echo "Done. Check status any time with:"
echo "  ps aux | grep drive_sync_daemon"
echo "  tail -f sync.log"
echo "  rclone lsl ${REMOTE_NAME}:"
echo
echo "NOTE: the old service-account approach (gdrive-key.json,"
echo "service_account_file=...) is removed on purpose. Service accounts"
echo "have zero storage quota on a personal (non-Workspace) Google Drive"
echo "and can never upload there, no matter how the JSON key is formatted."
