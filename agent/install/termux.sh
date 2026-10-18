#!/data/data/com.termux/files/usr/bin/bash
# windycity-agent — Android/Termux installer.
# No root, no packages beyond python + git, no pip installs required.
set -e
echo "== windycity-agent :: Termux install =="

command -v python >/dev/null 2>&1 || { echo "installing python…"; pkg install -y python; }
command -v git    >/dev/null 2>&1 || { echo "installing git…";    pkg install -y git; }
command -v curl   >/dev/null 2>&1 || pkg install -y curl

REPO="${WY_REPO:-$HOME/therealwindycity}"
if [ ! -d "$REPO/agent" ]; then
  echo
  echo "Repo not found at $REPO."
  echo "Either:  git clone https://github.com/bartimoussmith-oss/therealwindycity \"$REPO\""
  echo "or:      set WY_REPO=/path/to/checkout and re-run this script."
  echo "Note: a bare agent/ folder also works — the runtime needs nothing else."
fi

mkdir -p "$HOME/bin"
cat > "$HOME/bin/wyagent" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
export WY_REPO="\${WY_REPO:-$REPO}"
exec python3 "\$WY_REPO/agent/selfrun.py" "\$@"
EOF
chmod +x "$HOME/bin/wyagent"

# keep Android from freezing long runs
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true

cat >> "$HOME/.bashrc" <<'EOF'
# windycity-agent
export PATH="$HOME/bin:$PATH"
export WY_AGENT_HOME="${WY_AGENT_HOME:-$HOME/.windycity-agent}"
alias wy-agent-serve='wyagent serve --port 8765'
EOF

echo
echo "Installed.  Open a new Termux session (or: source ~/.bashrc), then:"
echo "  wyagent doctor                 # what works on this phone"
echo "  wyagent serve                  # console at http://<phone-ip>:8765"
echo "  wyagent run \"describe this repo\""
echo
echo "Phone-only, no API key? Use the paste bridge:"
echo "  wyagent run \"list the biggest files here\" --provider paste"
echo
if [ -d "$REPO/agent" ]; then
  cd "$REPO" && python3 -m agent doctor || true
fi
