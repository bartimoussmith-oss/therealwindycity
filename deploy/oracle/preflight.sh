#!/usr/bin/env bash
# ==============================================================================
# The Real Windy City — post-deploy verification (OCI)
#
#   sudo bash deploy/oracle/preflight.sh            # full report
#   sudo bash deploy/oracle/preflight.sh --quiet    # one line per check
#
# Exits non-zero if any HARD check fails. This is the "don't call it deployed
# until the URL answers" gate the repo's READ-FIRST asks for.
# ==============================================================================
set -uo pipefail

ENV_FILE=/etc/windycity/windycity.env
QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1

# shellcheck disable=SC1090
[[ -f "$ENV_FILE" ]] && { set -a; . "$ENV_FILE"; set +a; }
: "${WINDYCITY_USER:=windycity}"
: "${WINDYCITY_REPO:=/opt/windycity}"
: "${CONSOLE_PORT:=8501}"
: "${PIPELINE_PORT:=8717}"
: "${STUDIO_PORT:=8080}"
: "${DOMAIN:=}"

PASS=0; FAIL=0; WARN=0
ok()   { PASS=$((PASS+1)); printf '  \033[32mPASS\033[0m  %s\n' "$*"; }
bad()  { FAIL=$((FAIL+1)); printf '  \033[31mFAIL\033[0m  %s\n' "$*"; }
meh()  { WARN=$((WARN+1)); printf '  \033[33mWARN\033[0m  %s\n' "$*"; }
sec()  { [[ "$QUIET" -eq 1 ]] || printf '\n%s\n' "$*"; }

echo "Windy City preflight — $(date -u +%Y-%m-%dT%H:%MZ)  host: $(hostname)  ip: $(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo '?')"

# ---------------------------------------------------------------- services
sec "[1] services"
for svc in windycity-console windycity-pipeline; do
  if systemctl is-active --quiet "$svc"; then ok "$svc is active"
  else bad "$svc is not active ($(systemctl is-active "$svc" 2>&1)) — journalctl -u $svc -n 50"; fi
done
if systemctl list-timers --all 2>/dev/null | grep -q windycity-cycle.timer; then
  next="$(systemctl list-timers windycity-cycle.timer --no-pager 2>/dev/null | awk 'NR==2{print $1, $2, $3}')"
  ok "cycle timer scheduled (next: ${next:-unknown})"
else
  bad "windycity-cycle.timer not present — systemctl enable --now windycity-cycle.timer"
fi
if systemctl is-active --quiet nginx; then ok "nginx is active"; else bad "nginx is not active"; fi

# ---------------------------------------------------------------- sockets
sec "[2] sockets"
for p in "$CONSOLE_PORT" "$PIPELINE_PORT"; do
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$p\$"; then
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "^0\.0\.0\.0:$p$|^\[::\]:$p$"; then
      meh "port $p is bound on all interfaces — it should be 127.0.0.1 only (check the unit's --server.address / --host)"
    else
      ok "port $p listening on loopback only"
    fi
  else
    bad "nothing listening on port $p"
  fi
done
for p in "$STUDIO_PORT" 80 443; do
  [[ "$p" == "0" ]] && continue
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$p\$"; then ok "port $p open (nginx)"; else meh "port $p not listening (fine before TLS / if the studio block is disabled)"; fi
done

# ---------------------------------------------------------------- HTTP
sec "[3] HTTP surfaces"
code() { curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$1" 2>/dev/null || echo 000; }
HOSTHDR=(-H "Host: ${DOMAIN:-localhost}")
c="$(code http://127.0.0.1/)"
[[ "$c" == "200" ]] && ok "console via nginx -> 200" || bad "console via nginx returned $c"
c="$(code http://127.0.0.1/ledger/)"
[[ "$c" == "200" ]] && ok "static ledger -> 200" || bad "static ledger returned $c (is $WINDYCITY_REPO/public/index.html present?)"
c="$(code http://127.0.0.1/feed.xml)"
[[ "$c" == "200" ]] && ok "RSS feed -> 200" || bad "RSS feed returned $c"
if curl -fsS --max-time 20 http://127.0.0.1/feed.xml 2>/dev/null | head -c 400 | grep -q '<rss\|<feed'; then
  ok "feed.xml parses as RSS/Atom"
else
  meh "feed.xml did not look like RSS — regenerate with: python3 engine/gen_feed.py"
fi
if [[ "$STUDIO_PORT" != "0" ]]; then
  c="$(code "http://127.0.0.1:${STUDIO_PORT}/")"
  [[ "$c" == "200" ]] && ok "studio via nginx -> 200" || bad "studio returned $c"
fi
if [[ -n "$DOMAIN" ]]; then
  c="$(code "https://${DOMAIN}/")"
  [[ "$c" == "200" ]] && ok "https://${DOMAIN}/ -> 200" || meh "https://${DOMAIN}/ returned $c (DNS/TLS not live yet?)"
fi

# ---------------------------------------------------------------- data + app health
sec "[4] data and logs"
DB="$WINDYCITY_REPO/data/engine.db"
if [[ -f "$DB" ]]; then
  n="$(sudo -u "$WINDYCITY_USER" python3 - "$DB" <<'PY' 2>/dev/null || echo "?"
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
print(c.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
PY
)"
  [[ "$n" =~ ^[0-9]+$ ]] && ok "engine.db readable — $n documents tracked" || bad "engine.db present but unreadable as $WINDYCITY_USER"
else
  bad "no $DB — run: cd $WINDYCITY_REPO && sudo -u $WINDYCITY_USER .venv/bin/python run.py init"
fi
[[ -f "$WINDYCITY_REPO/public/index.html" ]] && ok "static ledger built (public/index.html)" \
  || meh "public/index.html missing — it appears after the first civic cycle"
last_cycle="$(journalctl -u windycity-cycle --no-pager -n 200 2>/dev/null | grep -c 'done:' || true)"
[[ "${last_cycle:-0}" -gt 0 ]] && ok "at least one civic cycle has completed" \
  || meh "no completed civic cycle in the journal yet — run: systemctl start windycity-cycle.service"
if journalctl -u windycity-console --no-pager -n 100 2>/dev/null | grep -qiE 'traceback|ModuleNotFoundError'; then
  bad "the console journal shows a Python error — journalctl -u windycity-console -n 80"
else
  ok "console journal clean"
fi
if command -v certbot >/dev/null && [[ -n "$DOMAIN" ]]; then
  days="$(certbot certificates 2>/dev/null | grep -m1 'VALID:' | grep -oE '[0-9]+ day' || true)"
  [[ -n "$days" ]] && ok "TLS certificate ${days} from expiry" || meh "no certificate found for $DOMAIN yet"
fi

# ---------------------------------------------------------------- summary
if [[ "$QUIET" -eq 1 ]]; then
  echo "preflight: $PASS pass / $WARN warn / $FAIL fail"
else
  cat <<EOF

----------------------------------------
 $PASS passed · $WARN warnings · $FAIL failures
EOF
  [[ "$FAIL" -eq 0 ]] && echo " All hard checks pass — the stack is live." \
                      || echo " Fix the FAIL lines above; re-run deploy/oracle/bootstrap.sh (idempotent) if needed."
fi
[[ "$FAIL" -eq 0 ]]
