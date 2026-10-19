#!/data/data/com.termux/files/usr/bin/bash
# setup_drive_sync.sh — run this on the CHROMEBOOK's Termux.
#
# Before running this: on your PHONE's Termux, run phone_authorize.sh,
# tap Allow in the browser when it opens, and copy the { ... } JSON
# line it prints at the end. You'll paste that ONE line into this
# script when it asks — that is the ONLY manual step here.
#
# Everything else happens automatically:
#   1. Installs/repairs rclone
#   2. Wipes any previous broken service-account config
#   3. Builds the "gdrive" remote directly from the token you paste in
#      (no browser, no localhost callback, no ChromeOS/Termux network
#      sandboxing problem — the Chromebook never has to talk to Google's
#      OAuth server itself)
#   4. Verifies the connection
#   5. Writes a corrected sync daemon
#   6. Runs a real test push so you SEE it work
#   7. Launches the daemon in the background with a wake-lock
set -e

DRIVE_FOLDER_ID="${DRIVE_FOLDER_ID:-15QE9muLTPuA2B4DVwEqDwfxWtM7kujfz}"
REMOTE_NAME="${REMOTE_NAME:-gdrive}"

echo "=== [1/8] Installing rclone ==="
command -v rclone >/dev/null 2>&1 || { pkg update -y; pkg install -y rclone; }
rclone version | head -1

echo
echo "=== [2/8] Removing any previous broken config ==="
mkdir -p "$HOME/.config/rclone"
rclone config delete "$REMOTE_NAME" >/dev/null 2>&1 || true
rm -f "$HOME/gdrive-key.json"

echo
echo "=== [3/8] Paste the token from your phone ==="
if [ -z "$DRIVE_TOKEN" ]; then
  echo "Run phone_authorize.sh on your phone first if you haven't."
  echo "Paste the ENTIRE { ... } line it printed, then press Enter:"
  read -r DRIVE_TOKEN
fi

if [ -z "$DRIVE_TOKEN" ]; then
  echo "No token entered. Stopping — nothing else can run without it."
  exit 1
fi

echo
echo "=== [4/8] Creating the 'gdrive' remote from that token (no browser needed here) ==="
rclone config create --non-interactive "$REMOTE_NAME" drive \
  scope drive \
  root_folder_id "$DRIVE_FOLDER_ID" \
  token "$DRIVE_TOKEN"

echo
echo "=== [5/8] Verifying the connection ==="
if rclone lsd "$REMOTE_NAME": ; then
  echo "OK: authenticated and folder reachable."
else
  echo "FAILED: the token may be stale (they expire fast if unused) or mistyped."
  echo "Re-run phone_authorize.sh on your phone to get a fresh one, then re-run this script."
  exit 1
fi

echo
echo "=== [6/8] Writing the corrected sync daemon ==="
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
echo "=== [7/8] Test push before trusting the loop ==="
TESTFILE="output/setup_test_$(date -u +%Y%m%dT%H%M%SZ).json"
echo "{\"test\":\"setup_drive_sync.sh\",\"time\":\"$(date -u +%FT%TZ)\"}" > "$TESTFILE"
rclone copy output/ "$REMOTE_NAME": --update -v
echo "--- files currently on the remote ---"
rclone lsl "$REMOTE_NAME":

echo
echo "=== [8/8] Launching the background daemon ==="
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
