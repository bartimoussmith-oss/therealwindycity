#!/data/data/com.termux/files/usr/bin/bash
# drive_sync_control.sh start|stop|status|sync|ensure
#
# Single control point for the Drive sync: this is what the home-screen
# widget icons AND the persistent notification's buttons call.
#
#   start  - turn syncing on (instant, no process restart needed)
#   stop   - turn syncing off (daemon keeps running, just idles)
#   status - report current state + refresh the notification
#   sync   - push output/ right now, regardless of on/off
#   ensure - used by the boot script: makes sure the daemon process
#            exists and the notification is showing, WITHOUT changing
#            whatever on/off state you last set
set -u

PROJECT_DIR="${PROJECT_DIR:-$HOME/therealwindycity}"
cd "$PROJECT_DIR" 2>/dev/null || cd "$HOME"
PROJECT_DIR="$(pwd)"

STATE_DIR="$HOME/.config/drive_sync"
STATE_FILE="$STATE_DIR/state"
LAST_SYNC_FILE="$STATE_DIR/last_sync"
mkdir -p "$STATE_DIR"

CONTROL="$PROJECT_DIR/tools/drive_sync_control.sh"
SUPERVISOR="$PROJECT_DIR/tools/drive_sync_supervisor.sh"

toast() { command -v termux-toast >/dev/null 2>&1 && termux-toast -s "$1" || echo "$1"; }

ensure_supervisor_running() {
  if ! pgrep -f drive_sync_supervisor.sh >/dev/null 2>&1; then
    command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock
    nohup bash "$SUPERVISOR" >> "$HOME/drive_sync.log" 2>&1 &
    disown
  fi
}

last_sync_text() {
  if [ -f "$LAST_SYNC_FILE" ]; then
    echo "last sync: $(cat "$LAST_SYNC_FILE")"
  else
    echo "no syncs yet"
  fi
}

notify() {
  command -v termux-notification >/dev/null 2>&1 || return 0
  local state="$1"
  local info
  info="$(last_sync_text)"
  if [ "$state" = "on" ]; then
    termux-notification \
      --id drive_sync \
      --title "Drive Sync: RUNNING" \
      --content "$info" \
      --ongoing --alert-once \
      --button1 "Stop" --button1-action "bash '$CONTROL' stop" \
      --button2 "Sync now" --button2-action "bash '$CONTROL' sync"
  else
    termux-notification \
      --id drive_sync \
      --title "Drive Sync: STOPPED" \
      --content "$info" \
      --ongoing --alert-once \
      --button1 "Start" --button1-action "bash '$CONTROL' start"
  fi
}

cmd="${1:-status}"
case "$cmd" in
  start)
    echo "on" > "$STATE_FILE"
    ensure_supervisor_running
    notify "on"
    toast "Drive Sync: ON"
    ;;
  stop)
    echo "off" > "$STATE_FILE"
    notify "off"
    toast "Drive Sync: OFF"
    ;;
  sync)
    mkdir -p output
    rclone copy output/ gdrive: --update -q
    date -u +%FT%TZ > "$LAST_SYNC_FILE"
    notify "$(cat "$STATE_FILE" 2>/dev/null || echo on)"
    toast "Drive Sync: pushed now"
    ;;
  ensure)
    [ -f "$STATE_FILE" ] || echo "on" > "$STATE_FILE"
    ensure_supervisor_running
    notify "$(cat "$STATE_FILE")"
    ;;
  status|*)
    state="$(cat "$STATE_FILE" 2>/dev/null || echo "on (default)")"
    running="not running"
    pgrep -f drive_sync_supervisor.sh >/dev/null 2>&1 && running="running"
    info="$(last_sync_text)"
    echo "state=$state supervisor=$running $info"
    notify "$state"
    toast "Drive Sync: $state ($running) - $info"
    ;;
esac
