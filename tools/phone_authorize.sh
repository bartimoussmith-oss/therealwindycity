#!/data/data/com.termux/files/usr/bin/bash
# phone_authorize.sh — run this on your PHONE's Termux.
#
# It installs rclone (if needed) and runs the one Google OAuth step that
# needs a real, reachable browser. That's the ONLY manual action in this
# whole process: tapping "Allow" when the browser opens.
#
# When it's done, it prints one line of JSON starting with { and ending
# with }. Copy that WHOLE line (long-press to select, or share it to
# yourself) and paste it into setup_drive_sync.sh on the Chromebook.
set -e

echo "=== Installing rclone on this phone (if needed) ==="
command -v rclone >/dev/null 2>&1 || pkg install -y rclone

echo
echo "=== A browser will open now. Log in as your Google account and tap Allow. ==="
echo "=== When you're back here, copy the ENTIRE { ... } JSON line it prints. ==="
echo

rclone authorize "drive"

echo
echo "=== Copy the { ... } block printed above. That's everything you need from this phone. ==="
