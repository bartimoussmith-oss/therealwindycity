#!/usr/bin/env bash
# windycity-agent — Linux installer (Debian/Ubuntu/Fedora/Arch, Crostini, WSL, VPS).
# Stdlib-only runtime: no pip, no venv required. A venv is used only if you want extras.
set -e
echo "== windycity-agent :: Linux install =="

command -v python3 >/dev/null 2>&1 || {
  echo "python3 missing. Try one of:"
  echo "  sudo apt install python3        # debian/ubuntu/crostini"
  echo "  sudo dnf install python3        # fedora"
  echo "  sudo pacman -S python           # arch"
  exit 1
}
REPO="${WY_REPO:-$(cd "$(dirname "$0")/../.." && pwd)}"
mkdir -p "$HOME/.local/bin"

cat > "$HOME/.local/bin/wyagent" <<EOF
#!/usr/bin/env bash
export WY_REPO="\${WY_REPO:-$REPO}"
exec python3 "\$WY_REPO/agent/selfrun.py" "\$@"
EOF
chmod +x "$HOME/.local/bin/wyagent"

# optional user service so the console is always up
if [ "${WY_SERVICE:-0}" = "1" ]; then
  mkdir -p "$HOME/.config/systemd/user"
  cat > "$HOME/.config/systemd/user/wyagent.service" <<EOF
[Unit]
Description=windycity-agent local agent console
After=network-online.target

[Service]
Type=simple
Environment=WY_REPO=$REPO
ExecStart=$HOME/.local/bin/wyagent serve --port 8765
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload || true
  echo "service written — enable with:  systemctl --user enable --now wyagent"
fi

cat >> "$HOME/.bashrc" <<'EOF'
# windycity-agent
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH";; esac
export WY_AGENT_HOME="${WY_AGENT_HOME:-$HOME/.windycity-agent}"
EOF

echo
echo "Installed.  New shell (or: source ~/.bashrc), then:"
echo "  wyagent doctor"
echo "  wyagent serve            # http://<lan-ip>:8765"
echo "Remote access without port-forwarding:  curl -fsSL https://tailscale.com/install.sh | sh"
