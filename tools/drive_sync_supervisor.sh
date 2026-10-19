#!/data/data/com.termux/files/usr/bin/bash
# drive_sync_supervisor.sh — keeps drive_sync_daemon.py alive forever.
# If the python process ever crashes (OOM kill, exception, etc.) this
# relaunches it after a short pause instead of leaving sync dead until
# someone notices. This is the ONE process that should run continuously;
# start/stop just flip a flag the daemon checks, they don't kill this.
PROJECT_DIR="${PROJECT_DIR:-$HOME/therealwindycity}"
cd "$PROJECT_DIR" 2>/dev/null || cd "$HOME"

LOG="$HOME/drive_sync.log"
echo "$(date -u +%FT%TZ) supervisor started" >> "$LOG"

while true; do
  python3 tools/drive_sync_daemon.py >> "$LOG" 2>&1
  echo "$(date -u +%FT%TZ) daemon exited, restarting in 5s" >> "$LOG"
  sleep 5
done
