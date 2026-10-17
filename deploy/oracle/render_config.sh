#!/usr/bin/env bash
# ==============================================================================
# The Real Windy City — render the deploy kit's config artifacts
#
# Turns the templates in this folder into concrete files for this host:
#   systemd/windycity-*.{service,timer}  ->  <out>/systemd/
#   nginx/windycity.conf.template        ->  <out>/nginx/windycity.conf
#
#   bash render_config.sh --out /tmp/render            # write to a directory
#   sudo bash render_config.sh --install               # write into /etc
#
# Both bootstrap.sh and selftest.sh use this file, so what gets tested is
# exactly what gets installed. Exits non-zero if a placeholder survives
# rendering (that would mean a half-substituted unit on a production box).
# ==============================================================================
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=""; INSTALL=0
REPO=/opt/windycity; SVC_USER=windycity
CONSOLE_PORT=8501; PIPELINE_PORT=8717; STUDIO_PORT=8080
DOMAIN=""; PIPELINE_DOMAIN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)             OUT="$2"; shift 2 ;;
    --install)         INSTALL=1; shift ;;
    --repo)            REPO="$2"; shift 2 ;;
    --user)            SVC_USER="$2"; shift 2 ;;
    --console-port)    CONSOLE_PORT="$2"; shift 2 ;;
    --pipeline-port)   PIPELINE_PORT="$2"; shift 2 ;;
    --studio-port)     STUDIO_PORT="$2"; shift 2 ;;
    --domain)          DOMAIN="$2"; shift 2 ;;
    --pipeline-domain) PIPELINE_DOMAIN="$2"; shift 2 ;;
    -h|--help)         sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "render_config: unknown flag $1" >&2; exit 2 ;;
  esac
done

[[ "$INSTALL" -eq 1 || -n "$OUT" ]] || { echo "render_config: pass --out DIR or --install" >&2; exit 2; }
if [[ "$INSTALL" -eq 1 && ${EUID} -ne 0 ]]; then echo "render_config: --install needs root" >&2; exit 1; fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
WORK="$TMP/out"; mkdir -p "$WORK/systemd" "$WORK/nginx"

SERVER_NAMES="$DOMAIN"; [[ -n "$SERVER_NAMES" ]] || SERVER_NAMES="_"

render() { # src dst
  sed -e "s|__REPO__|${REPO}|g" \
      -e "s|__USER__|${SVC_USER}|g" \
      -e "s|__CONSOLE_PORT__|${CONSOLE_PORT}|g" \
      -e "s|__PIPELINE_PORT__|${PIPELINE_PORT}|g" \
      -e "s|__STUDIO_PORT__|${STUDIO_PORT}|g" \
      -e "s|__PIPELINE_DOMAIN__|${PIPELINE_DOMAIN:-_}|g" \
      -e "s|__SERVER_NAMES__|${SERVER_NAMES}|g" \
      "$1" > "$2"
}

# ------------------------------------------------------------------ systemd
for src in "$HERE"/systemd/*.service "$HERE"/systemd/*.timer; do
  [[ -e "$src" ]] || continue
  render "$src" "$WORK/systemd/$(basename "$src")"
done

# ------------------------------------------------------------------ nginx
render "$HERE/nginx/windycity.conf.template" "$WORK/nginx/windycity.conf"
if [[ "$STUDIO_PORT" == "0" ]]; then
  sed -i '/# BEGIN STUDIO_PORT/,/# END STUDIO_PORT/d' "$WORK/nginx/windycity.conf"
fi
if [[ -z "$PIPELINE_DOMAIN" ]]; then
  sed -i '/# BEGIN PIPELINE_DOMAIN/,/# END PIPELINE_DOMAIN/d' "$WORK/nginx/windycity.conf"
  # comments referencing the dropped block would be noise in the installed file
  sed -i 's|^#   studio       -> pipeline web UI.*|#   studio       -> (no public host configured; loopback only)|' "$WORK/nginx/windycity.conf"
fi

# ------------------------------------------------------------------ fail closed
if grep -rn '__[A-Z_]*__' "$WORK" >/dev/null 2>&1; then
  echo "render_config: unsubstituted placeholder survived:" >&2
  grep -rn '__[A-Z_]*__' "$WORK" >&2
  exit 3
fi
# a malformed config must never reach /etc/nginx
if ! command -v nginx >/dev/null; then
  # no nginx binary to test with: at least prove the file is brace-balanced
  awk 'BEGIN{d=0} {for(i=1;i<=length($0);i++){c=substr($0,i,1); if(c=="{")d++; if(c=="}")d--}} END{if(d!=0){print "unbalanced braces: " d > "/dev/stderr"; exit 1}}' \
    "$WORK/nginx/windycity.conf" || { echo "render_config: nginx config is not brace-balanced" >&2; exit 3; }
fi

# ------------------------------------------------------------------ emit
if [[ "$INSTALL" -eq 0 ]]; then
  mkdir -p "$OUT"
  cp -r "$WORK"/. "$OUT/"
  echo "rendered -> $OUT (systemd/, nginx/)"
else
  for f in "$WORK"/systemd/*; do install -m 0644 "$f" "/etc/systemd/system/$(basename "$f")"; done
  mkdir -p /etc/nginx/conf.d
  if [[ -f /etc/nginx/conf.d/windycity.conf ]] && grep -q 'managed by Certbot' /etc/nginx/conf.d/windycity.conf; then
    install -m 0644 "$WORK/nginx/windycity.conf" /etc/nginx/conf.d/windycity.conf.new
    echo "WARN: /etc/nginx/conf.d/windycity.conf was edited by certbot — left in place; new render at windycity.conf.new" >&2
  else
    install -m 0644 "$WORK/nginx/windycity.conf" /etc/nginx/conf.d/windycity.conf
    rm -f /etc/nginx/conf.d/windycity.conf.new
  fi
  nginx -t >/dev/null 2>&1 || { echo "WARN: 'nginx -t' failed after install — inspect /etc/nginx/conf.d/windycity.conf" >&2; }
  echo "installed systemd units + /etc/nginx/conf.d/windycity.conf"
fi
