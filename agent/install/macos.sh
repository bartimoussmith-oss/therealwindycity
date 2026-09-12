#!/usr/bin/env bash
# windycity-agent — macOS installer.
set -e
echo "== windycity-agent :: macOS install =="
command -v python3 >/dev/null 2>&1 || { echo "install Python 3.9+ (brew install python, or python.org)"; exit 1; }
REPO="${WY_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/wyagent" <<EOF
#!/usr/bin/env bash
export WY_REPO="\${WY_REPO:-$REPO}"
exec python3 "\$WY_REPO/agent/selfrun.py" "\$@"
EOF
chmod +x "$HOME/.local/bin/wyagent"

if [ "${WY_LAUNCHD:-0}" = "1" ]; then
  PLIST="$HOME/Library/LaunchAgents/com.windycity.agent.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.windycity.agent</string>
  <key>ProgramArguments</key><array>
    <string>$HOME/.local/bin/wyagent</string><string>serve</string><string>--port</string><string>8765</string>
  </array>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>EnvironmentVariables</key><dict><key>WY_REPO</key><string>$REPO</string></dict>
  <key>StandardOutPath</key><string>/tmp/wyagent.log</string>
  <key>StandardErrorPath</key><string>/tmp/wyagent.err</string>
</dict></plist>
EOF
  echo "plist written to $PLIST — load with:  launchctl load $PLIST"
fi
echo; echo "Installed.  Then:"; echo "  wyagent doctor && wyagent serve"
