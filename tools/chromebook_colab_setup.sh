#!/usr/bin/env bash
# Set up Google's Colab CLI inside a Chromebook's Linux container (Crostini).
#
# Run once, in the Chromebook's Terminal app. It installs uv, a Python 3.12
# interpreter (the CLI needs >=3.12; Crostini ships 3.11), and the CLI itself.
#
#   curl -fsSL https://raw.githubusercontent.com/bartimoussmith-oss/therealwindycity/<branch>/tools/chromebook_colab_setup.sh | bash
# or, from a clone:
#   bash tools/chromebook_colab_setup.sh
#
# Safe to re-run: every step checks first.

set -euo pipefail

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

# --------------------------------------------------------------------------
# 0. are we actually inside the Linux container?
# --------------------------------------------------------------------------
if [ ! -f /etc/os-release ]; then
  echo "This is meant to run inside the Chromebook's Linux terminal." >&2
  exit 1
fi
# shellcheck disable=SC1091
. /etc/os-release
if ! grep -qi 'cros\|debian\|ubuntu' <<<"${ID:-} ${ID_LIKE:-}"; then
  warn "not obviously ChromeOS/Crostini (ID=${ID:-?}); continuing anyway"
fi
if [ -d /mnt/chromeos ]; then
  ok "ChromeOS Linux container detected (${PRETTY_NAME:-Linux})"
else
  warn "no /mnt/chromeos — this may not be a Chromebook, but it will still work on Debian/Ubuntu"
fi

# --------------------------------------------------------------------------
# 1. base packages
# --------------------------------------------------------------------------
say "Installing base packages"
sudo apt-get update -qq
sudo apt-get install -y -qq --no-install-recommends \
  curl ca-certificates git python3 python3-venv build-essential libgomp1 unzip
ok "apt packages in place"

# --------------------------------------------------------------------------
# 2. uv (installs and pins Python versions without touching the system one)
# --------------------------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
  ok "uv already installed ($(uv --version))"
else
  say "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ok "uv installed"
fi
export PATH="$HOME/.local/bin:$PATH"
# make it stick for new shells
if ! grep -q 'local/bin' "$HOME/.profile" 2>/dev/null; then
  printf '\n# uv + colab cli\nexport PATH="$HOME/.local/bin:$PATH"\n' >>"$HOME/.profile"
fi

# --------------------------------------------------------------------------
# 3. Python 3.12+ — the Colab CLI requires it, Crostini's default is 3.11
# --------------------------------------------------------------------------
say "Installing Python 3.12"
uv python install 3.12
ok "python $(uv python find 3.12 | xargs -r basename)"

# --------------------------------------------------------------------------
# 4. the CLI
# --------------------------------------------------------------------------
say "Installing the Colab CLI"
if command -v colab >/dev/null 2>&1; then
  ok "colab already installed ($(colab version 2>/dev/null || echo '?')) — upgrading"
  uv tool upgrade google-colab-cli || uv tool install --python 3.12 --force google-colab-cli
else
  uv tool install --python 3.12 google-colab-cli
fi
hash -r

# --------------------------------------------------------------------------
# 5. check
# --------------------------------------------------------------------------
say "Checking the install"
if command -v colab >/dev/null 2>&1; then
  colab version
  ok "colab is on PATH at $(command -v colab)"
else
  warn "colab is not on PATH — open a new Terminal tab, or run: export PATH=\"\$HOME/.local/bin:\$PATH\""
  exit 1
fi

cat <<'NEXT'

Next, authenticate once. Two ways:

  colab new                       # copy-paste flow, no Google Cloud project needed
    → it prints a URL; open it in Chrome on this Chromebook,
      approve, paste the code back into the terminal

  # or, if you already use gcloud:
  sudo apt-get install -y google-cloud-cli
  gcloud auth application-default login
  colab new --auth adc

Known Crostini wrinkle: the CLI stores your token in the system keyring, and Crostini's
keyring can be locked, which looks like a hang. If it sits there, either unlock it
(Passwords and keys → login) or use --auth adc, which skips the keyring.

Then check what you have:

  colab new -s grab --gpu T4      # allocate a T4 (billable while it exists)
  colab status -s grab            # hardware + shape
  colab usage                     # compute units left
  colab stop -s grab              # ALWAYS do this — see tools/colab_cli_drain.sh

Wipe it all later with:
  uv tool uninstall google-colab-cli && rm -rf ~/.config/colab-cli
NEXT
