#!/data/data/com.termux/files/usr/bin/bash
# check_drive_sync.sh — tap-to-verify-and-fix for the Google Drive sync.
#
# Meant to be launched from a Termux:Widget home-screen icon (see setup
# notes in the repo chat). It does NOT just report status — it actively
# fixes what it can:
#   - holds a wake-lock so Android stops killing the background daemon
#   - confirms rclone can actually reach Google Drive
#   - restarts the sync daemon if it died
#   - pushes anything waiting in output/ immediately, instead of waiting
#     up to 60s for the daemon's own loop
#   - pops a toast + writes a log line so you get feedback without
#     needing to keep a terminal open
set -u

# Adjust this if your checkout lives somewhere else.
PROJECT_DIR="${PROJECT_DIR:-$HOME/therealwindycity}"
cd "$PROJECT_DIR" 2>/dev/null || cd "$HOME"

LOGFILE="$HOME/drive_sync_check.log"
toast() { command -v termux-toast >/dev/null 2>&1 && termux-toast -s "$1"; }

echo "=== Drive sync check: $(date -u +%FT%TZ) ===" | tee -a "$LOGFILE"

command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock

if ! command -v rclone >/dev/null 2>&1; then
  echo "FAIL: rclone is not installed" | tee -a "$LOGFILE"
  toast "Drive sync: rclone missing!"
  exit 1
fi

if rclone lsd gdrive: >/dev/null 2>&1; then
  echo "OK: Drive connection reachable" | tee -a "$LOGFILE"
else
  echo "FAIL: Drive connection failed - token likely needs refreshing" | tee -a "$LOGFILE"
  toast "Drive sync: connection FAILED"
  exit 1
fi

if pgrep -f drive_sync_daemon.py >/dev/null 2>&1; then
  echo "OK: daemon already running (PID $(pgrep -f drive_sync_daemon.py))" | tee -a "$LOGFILE"
else
  echo "FIXING: daemon was not running - restarting it" | tee -a "$LOGFILE"
  mkdir -p output
  nohup python3 tools/drive_sync_daemon.py > sync.log 2>&1 &
  disown
  sleep 1
  echo "  new PID: $(pgrep -f drive_sync_daemon.py || echo 'still not running - check sync.log')" | tee -a "$LOGFILE"
fi

mkdir -p output
rclone copy output/ gdrive: --update -q 2>>"$LOGFILE"

COUNT=$(rclone lsl gdrive: 2>/dev/null | wc -l)
echo "OK: $COUNT file(s) currently on Drive" | tee -a "$LOGFILE"
toast "Drive sync OK - $COUNT files, daemon PID $(pgrep -f drive_sync_daemon.py | head -1)"
echo "=== done ===" | tee -a "$LOGFILE"
