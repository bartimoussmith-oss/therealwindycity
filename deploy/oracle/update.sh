#!/usr/bin/env bash
# ==============================================================================
# The Real Windy City — update / restart the OCI deployment
#
#   sudo bash deploy/oracle/update.sh              # git pull + deps + restart
#   sudo bash deploy/oracle/update.sh --no-pull    # restart only
#   sudo bash deploy/oracle/update.sh --no-deps    # skip pip install
#
# Fast path: the same bootstrap is idempotent, but this skips package installs
# and certbot, so it finishes in seconds on a small shape.
# ==============================================================================
set -Eeuo pipefail

ENV_FILE=/etc/windycity/windycity.env
DO_PULL=1; DO_DEPS=1
for a in "$@"; do
  case "$a" in
    --no-pull) DO_PULL=0 ;;
    --no-deps) DO_DEPS=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

[[ ${EUID} -eq 0 ]] || { echo "run me with sudo" >&2; exit 1; }
# shellcheck disable=SC1090
[[ -f "$ENV_FILE" ]] && { set -a; . "$ENV_FILE"; set +a; }
: "${WINDYCITY_USER:=windycity}"
: "${WINDYCITY_REPO:=/opt/windycity}"
: "${WINDYCITY_BRANCH:=main}"

if [[ "$DO_PULL" -eq 1 ]]; then
  echo "[update] git pull ($WINDYCITY_BRANCH)…"
  sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" fetch --quiet origin "$WINDYCITY_BRANCH"
  before="$(sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" rev-parse --short HEAD)"
  sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" merge --ff-only --quiet "origin/$WINDYCITY_BRANCH" \
    || { echo "[update] not a fast-forward — resolve manually in $WINDYCITY_REPO (local ledger changes?)" >&2; exit 1; }
  after="$(sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" rev-parse --short HEAD)"
  echo "[update] $before -> $after"
  if [[ "$DO_DEPS" -eq 1 && "$before" != "$after" ]] && \
     ! sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" diff --quiet "$before" "$after" -- requirements.txt; then
    echo "[update] requirements.txt changed — reinstalling…"
    sudo -u "$WINDYCITY_USER" "$WINDYCITY_REPO/.venv/bin/pip" install --quiet -r "$WINDYCITY_REPO/requirements.txt"
  fi
fi

echo "[update] restarting services…"
systemctl restart windycity-console.service windycity-pipeline.service
systemctl is-active --quiet windycity-console.service || { echo "[update] console did not come back — journalctl -u windycity-console" >&2; exit 1; }
systemctl is-active --quiet windycity-pipeline.service || { echo "[update] studio did not come back — journalctl -u windycity-pipeline" >&2; exit 1; }

if [[ -x "$WINDYCITY_REPO/deploy/oracle/preflight.sh" ]]; then
  echo "[update] preflight:"
  bash "$WINDYCITY_REPO/deploy/oracle/preflight.sh" --quiet || true
fi
echo "[update] done at $(date -u +%Y-%m-%dT%H:%MZ)"
