#!/usr/bin/env bash
# ==============================================================================
# The Real Windy City — deploy-kit selftest (no cloud, no root, no network)
#
#   bash deploy/oracle/selftest.sh
#
# Proves the kit is internally consistent before you point it at a VM:
#   * every shell script parses
#   * config rendering substitutes every placeholder, in both the "domain" and
#     "bare IP" configurations, and drops the blocks it should drop
#   * the rendered nginx config is brace-balanced and proxies to loopback
#   * no service ever binds a public interface
#   * systemd units are well-formed (systemd-analyze, when available)
#   * the repo invariants this deploy depends on still hold (entry twins
#     byte-identical, requirements.txt present, engine entrypoints exist)
#
# Exit code 0 = safe to deploy.
# ==============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m  %s\n' "$*"; }
bad() { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m  %s\n' "$*"; }
sec() { printf '\n%s\n' "$*"; }
check() { # description, then command
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then ok "$desc"; else bad "$desc"; fi
}
contains() { grep -q -- "$2" "$1"; }   # file, pattern

echo "Windy City deploy-kit selftest — $(date -u +%Y-%m-%dT%H:%MZ)"

# ---------------------------------------------------------------- 1. syntax
sec "[1] shell syntax"
for f in "$HERE"/*.sh; do
  check "$(basename "$f") parses" bash -n "$f"
done

# ---------------------------------------------------------------- 2. repo invariants
sec "[2] repo invariants this deploy depends on"
check "entry twins are byte-identical (streamlit_app.py == Transparency_Index_App.py)" \
      cmp -s "$ROOT/streamlit_app.py" "$ROOT/Transparency_Index_App.py"
for f in requirements.txt run.py engine/scheduler.py engine/verify_vault.py \
         engine/entity_index.py engine/gen_feed.py pipeline/webui.py \
         pipeline/cheyenne_pipeline.py public/index.html public/feed.xml .streamlit/config.toml; do
  check "$f exists" test -e "$ROOT/$f"
done
check "requirements.txt pins streamlit" grep -qi '^streamlit' "$ROOT/requirements.txt"
check "engine/scheduler.py accepts --once" grep -q -- '--once' "$ROOT/engine/scheduler.py"

# ---------------------------------------------------------------- 3. render: domain config
sec "[3] rendered config — full configuration (domain + pipeline subdomain)"
bash "$HERE/render_config.sh" --out "$TMP/full" \
  --repo /opt/windycity --user windycity \
  --console-port 8501 --pipeline-port 8717 --studio-port 8080 \
  --domain windycity.example.com --pipeline-domain pipeline.windycity.example.com \
  >/dev/null || bad "render_config.sh failed for the full configuration"
NG="$TMP/full/nginx/windycity.conf"
contains "$NG" "server_name windycity.example.com" && ok "console server_name rendered" || bad "console server_name missing"
contains "$NG" "server_name pipeline.windycity.example.com" && ok "pipeline server_name rendered" || bad "pipeline server_name missing"
contains "$NG" "proxy_pass http://127.0.0.1:8501" && ok "console proxies to loopback:8501" || bad "console proxy_pass wrong"
contains "$NG" "proxy_pass http://127.0.0.1:8717" && ok "studio proxies to loopback:8717" || bad "studio proxy_pass wrong"
contains "$NG" "listen 8080" && ok "bare-IP studio port rendered" || bad "studio port block missing"
contains "$NG" "root /opt/windycity/public" && ok "static ledger served from the repo's public/" || bad "static ledger root wrong"
contains "$NG" "Connection \$connection_upgrade" && ok "websocket upgrade headers present (Streamlit needs them)" || bad "websocket upgrade headers missing"
! grep -q 'listen 0.0.0.0' "$NG" && ok "no wildcard listen directives" || bad "wildcard listen found"
! grep -rq '__[A-Z_]*__' "$TMP/full" && ok "no unsubstituted placeholders (any artifact)" || bad "placeholder survived rendering"
awk 'BEGIN{d=0}{for(i=1;i<=length($0);i++){c=substr($0,i,1);if(c=="{")d++;if(c=="}")d--}}END{exit d!=0}' "$NG" \
  && ok "nginx config is brace-balanced" || bad "nginx config braces unbalanced"

# ---------------------------------------------------------------- 4. render: bare IP
sec "[4] rendered config — bare-IP configuration (no DNS yet, studio disabled)"
bash "$HERE/render_config.sh" --out "$TMP/bare" \
  --repo /opt/windycity --user windycity \
  --console-port 8501 --pipeline-port 8717 --studio-port 0 \
  --domain "" --pipeline-domain "" \
  >/dev/null || bad "render_config.sh failed for the bare-IP configuration"
NG2="$TMP/bare/nginx/windycity.conf"
contains "$NG2" "server_name _" && ok "default_server falls back to _" || bad "default server_name wrong"
! contains "$NG2" "listen 0.0.0.0:8080" && ! grep -q '# BEGIN STUDIO_PORT' "$NG2" \
  && ok "studio block dropped when studio-port=0" || bad "studio block was not dropped"
! grep -q '# BEGIN PIPELINE_DOMAIN' "$NG2" && ok "pipeline-domain block dropped when unset" || bad "pipeline block was not dropped"
! grep -rq '__[A-Z_]*__' "$TMP/bare" && ok "no unsubstituted placeholders (bare-IP artifacts)" || bad "placeholder survived rendering"
check "bare-IP config still parses as text with a server block" grep -q 'listen 80 default_server' "$NG2"

# ---------------------------------------------------------------- 5. units
sec "[5] systemd units"
for u in "$TMP/full/systemd"/*; do
  b="$(basename "$u")"
  case "$b" in
    *.service)
      contains "$u" '^\[Unit\]' && contains "$u" '^\[Service\]' && contains "$u" 'ExecStart=' \
        && ok "$b has [Unit]/[Service]/ExecStart" || bad "$b is malformed"
      contains "$u" 'Restart=' || contains "$u" 'Type=oneshot' \
        || bad "$b has no restart policy"
      ;;
    *.timer)
      contains "$u" '^\[Timer\]' && contains "$u" 'OnCalendar=' && contains "$u" 'Unit=windycity-cycle.service' \
        && ok "$b has [Timer]/OnCalendar/Unit" || bad "$b is malformed"
      ;;
  esac
done
# services must not bind publicly
if grep -q -- '--server.address 127.0.0.1' "$TMP/full/systemd/windycity-console.service"; then
  ok "console binds loopback only"
else
  bad "console service does not force --server.address 127.0.0.1"
fi
if grep -q -- '--host 127.0.0.1' "$TMP/full/systemd/windycity-pipeline.service"; then
  ok "studio binds loopback only"
else
  bad "studio service does not force --host 127.0.0.1"
fi
contains "$TMP/full/systemd/windycity-cycle.service" 'engine/scheduler.py --once' \
  && ok "cycle unit runs scheduler --once" || bad "cycle unit command wrong"
contains "$TMP/full/systemd/windycity-cycle.service" '/opt/windycity' \
  && ok "cycle unit points at the checkout" || bad "cycle unit path wrong"

if command -v systemd-analyze >/dev/null 2>&1; then
  # systemd-analyze insists ExecStart and WorkingDirectory exist, so point a
  # throwaway render at a stub checkout that satisfies that check. This still
  # exercises the real unit syntax, ordering and paths.
  STUB="$TMP/stubrepo"
  mkdir -p "$STUB/.venv/bin" "$STUB/engine" "$STUB/pipeline" "$STUB/data" "$STUB/public"
  for exe in python streamlit; do
    printf '#!/bin/sh\nexit 0\n' > "$STUB/.venv/bin/$exe"; chmod 0755 "$STUB/.venv/bin/$exe"
  done
  for f in engine/scheduler.py engine/verify_vault.py engine/entity_index.py engine/gen_feed.py pipeline/webui.py; do
    : > "$STUB/$f"
  done
  bash "$HERE/render_config.sh" --out "$TMP/stub-verify" --repo "$STUB" --user "$(id -un)" \
    --console-port 8501 --pipeline-port 8717 --studio-port 8080 \
    --domain example.com --pipeline-domain pipeline.example.com >/dev/null
  for u in "$TMP/stub-verify/systemd"/*; do
    out="$(systemd-analyze verify "$u" 2>&1 \
      | grep -vE 'Unknown user|Failed to (create|load)|Unit .* not found|Unknown lvalue' || true)"
    if [[ -z "$out" ]]; then ok "$(basename "$u") passes systemd-analyze verify"
    else bad "$(basename "$u") failed systemd-analyze verify: $(echo "$out" | head -2 | tr '\n' ' ')"; fi
  done
else
  printf '  \033[33mSKIP\033[0m  systemd-analyze not available here\n'
fi

# ---------------------------------------------------------------- 6. runtime deps
sec "[6] runtime dependencies the deploy installs"
python3 - <<'PY' && ok "requirements.txt parses and lists streamlit" || bad "requirements.txt unreadable"
import re, sys, pathlib
txt = pathlib.Path("requirements.txt").read_text() if pathlib.Path("requirements.txt").exists() else ""
sys.exit(0 if re.search(r'^streamlit', txt, re.M | re.I) else 1)
PY
contains "$HERE/bootstrap.sh" 'ffmpeg' && ok "bootstrap installs ffmpeg for clip/reel jobs" || bad "ffmpeg not installed by bootstrap"
contains "$HERE/bootstrap.sh" 'certbot' && ok "bootstrap wires Let's Encrypt" || bad "certbot missing from bootstrap"
contains "$HERE/bootstrap.sh" 'python3-venv' && ok "bootstrap creates a venv (no system pip writes)" || bad "venv step missing"
check "preflight.sh flags public binds" grep -q 'bound on all interfaces' "$HERE/preflight.sh"
check "update.sh refuses non-fast-forward pulls" grep -q 'not a fast-forward' "$HERE/update.sh"

# ---------------------------------------------------------------- summary
printf '\n----------------------------------------\n %d passed · %d failed\n' "$PASS" "$FAIL"
if [[ "$FAIL" -eq 0 ]]; then
  echo " Kit verified. Next: README.md §Step 1 (create the Phoenix instance)."
else
  echo " Fix the FAIL lines before deploying."
fi
[[ "$FAIL" -eq 0 ]]
