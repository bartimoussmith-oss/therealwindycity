#!/data/data/com.termux/files/usr/bin/bash
# setup_drive_sync_controls.sh — adds Start/Stop/Status control to an
# already-working Drive sync (run setup_drive_sync.sh first if you
# haven't already authenticated rclone).
#
# This installs:
#   - termux-api (for toasts + the persistent notification)
#   - the control/supervisor/daemon scripts (overwriting the plain
#     always-on daemon from before with the flag-aware version)
#   - a Termux:Boot script so sync resumes automatically after any
#     reboot, respecting whatever on/off state you last left it in
#   - three home-screen widget scripts in ~/.shortcuts/: Start, Stop,
#     Status (requires the Termux:Widget companion app — see chat)
#
# Then it starts everything and posts the first notification.
set -e

PROJECT_DIR="${PROJECT_DIR:-$HOME/therealwindycity}"
[ -d "$PROJECT_DIR/tools" ] || PROJECT_DIR="$HOME"
cd "$PROJECT_DIR"
mkdir -p tools output

BASE_URL="https://raw.githubusercontent.com/bartimoussmith-oss/therealwindycity/arena/ee3b8c9e-therealwindycity/tools"

echo "=== [1/5] Installing termux-api (toasts + notifications) ==="
command -v termux-toast >/dev/null 2>&1 || pkg install -y termux-api

echo
echo "=== [2/5] Fetching the control/supervisor/daemon scripts ==="
curl -fsSL -o tools/drive_sync_daemon.py "$BASE_URL/drive_sync_daemon.py"
curl -fsSL -o tools/drive_sync_supervisor.sh "$BASE_URL/drive_sync_supervisor.sh"
curl -fsSL -o tools/drive_sync_control.sh "$BASE_URL/drive_sync_control.sh"
chmod +x tools/drive_sync_supervisor.sh tools/drive_sync_control.sh

echo
echo "=== [3/5] Stopping any old plain daemon (the new supervisor replaces it) ==="
pkill -f drive_sync_daemon.py 2>/dev/null || true
pkill -f drive_sync_supervisor.sh 2>/dev/null || true
sleep 1

echo
echo "=== [4/5] Installing the Termux:Boot autostart script ==="
mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/autostart_drive_sync.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock
PROJECT_DIR="$PROJECT_DIR" bash "$PROJECT_DIR/tools/drive_sync_control.sh" ensure
EOF
chmod +x "$HOME/.termux/boot/autostart_drive_sync.sh"
echo "NOTE: this only fires automatically if the Termux:Boot app is installed"
echo "(same app store as your Termux) and opened at least once to grant its"
echo "permission. If you skip that, just run the 'ensure' command below by hand"
echo "after each reboot instead."

echo
echo "=== [5/5] Creating home-screen widget scripts in ~/.shortcuts/ ==="
mkdir -p "$HOME/.shortcuts"
printf '#!/data/data/com.termux/files/usr/bin/bash\nPROJECT_DIR="%s" bash "%s/tools/drive_sync_control.sh" start\n' "$PROJECT_DIR" "$PROJECT_DIR" > "$HOME/.shortcuts/Start Drive Sync"
printf '#!/data/data/com.termux/files/usr/bin/bash\nPROJECT_DIR="%s" bash "%s/tools/drive_sync_control.sh" stop\n' "$PROJECT_DIR" "$PROJECT_DIR" > "$HOME/.shortcuts/Stop Drive Sync"
printf '#!/data/data/com.termux/files/usr/bin/bash\nPROJECT_DIR="%s" bash "%s/tools/drive_sync_control.sh" status\n' "$PROJECT_DIR" "$PROJECT_DIR" > "$HOME/.shortcuts/Drive Sync Status"
chmod +x "$HOME/.shortcuts/Start Drive Sync" "$HOME/.shortcuts/Stop Drive Sync" "$HOME/.shortcuts/Drive Sync Status"

echo
echo "=== Starting it now ==="
bash tools/drive_sync_control.sh start

echo
echo "Done. Look at your notification shade for 'Drive Sync: RUNNING' with"
echo "Stop / Sync now buttons. To get home-screen icons too, install the"
echo "Termux:Widget app (same store as Termux) and add its widget to your"
echo "desktop, choosing 'Start Drive Sync', 'Stop Drive Sync', or"
echo "'Drive Sync Status' from the list."
