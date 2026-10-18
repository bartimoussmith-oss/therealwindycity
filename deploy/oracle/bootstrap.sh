#!/usr/bin/env bash
# ==============================================================================
# The Real Windy City — Oracle Cloud (OCI) one-shot installer
#
#   sudo bash deploy/oracle/bootstrap.sh [--domain NAME] [--email ADDR]
#                                        [--pipeline-domain NAME] [--branch B]
#                                        [--repo DIR] [--no-studio-port] [--no-tls]
#
# Idempotent: safe to re-run; it upgrades in place (git pull, reinstall deps,
# reconcile nginx + systemd, restart). Nothing in here needs a credential, and
# nothing in here pushes to GitHub unless you uncomment that block in
# deploy/oracle/systemd/windycity-cycle.service.
#
# Tested target: Ubuntu 22.04/24.04 on OCI (us-phoenix-1), x86 or Ampere ARM.
# Oracle Linux 9 / RHEL-family is also handled (dnf + firewalld).
# ==============================================================================
set -Eeuo pipefail

ENV_FILE=/etc/windycity/windycity.env
TEMPLATES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_PREFIX="[bootstrap]"

log()  { printf '%s %s\n' "$LOG_PREFIX" "$*"; }
warn() { printf '%s WARN: %s\n' "$LOG_PREFIX" "$*" >&2; }
die()  { printf '%s FATAL: %s\n' "$LOG_PREFIX" "$*" >&2; exit 1; }
trap 'die "failed at line $LINENO — nothing was left half-installed on purpose; fix and re-run (idempotent)"' ERR

# ---------------------------------------------------------------- args
ARG_DOMAIN=""; ARG_EMAIL=""; ARG_PIPELINE_DOMAIN=""; ARG_BRANCH=""
ARG_REPO=""; STUDIO_PORT_SET=1; TLS=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)          ARG_DOMAIN="${2:-}"; shift 2 ;;
    --email)           ARG_EMAIL="${2:-}"; shift 2 ;;
    --pipeline-domain) ARG_PIPELINE_DOMAIN="${2:-}"; shift 2 ;;
    --branch)          ARG_BRANCH="${2:-}"; shift 2 ;;
    --repo)            ARG_REPO="${2:-}"; shift 2 ;;
    --no-studio-port)  STUDIO_PORT_SET=0; shift ;;
    --no-tls)          TLS=0; shift ;;
    -h|--help)         sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) die "unknown flag: $1" ;;
  esac
done

[[ ${EUID} -eq 0 ]] || die "run me with sudo (I install packages and write systemd units)"

# ---------------------------------------------------------------- OS facts
if [[ -r /etc/os-release ]]; then . /etc/os-release; else die "no /etc/os-release"; fi
OS_ID="${ID:-unknown}"; OS_VER="${VERSION_ID:-0}"
case "$OS_ID" in
  ubuntu|debian) PKG=apt ;;
  ol|rhel|rocky|almalinux|fedora|centos) PKG=dnf ;;
  *) die "unsupported distro '$OS_ID' — use Ubuntu 24.04 (preferred) or Oracle Linux 9" ;;
esac
ARCH="$(uname -m)"
log "host: ${OS_ID} ${OS_VER} / ${ARCH} / kernel $(uname -r)"

MEM_MB=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 ))
log "memory: ${MEM_MB} MiB"

# ---------------------------------------------------------------- config file
mkdir -p /etc/windycity
if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0644 "${TEMPLATES_DIR}/env.example" "$ENV_FILE"
  log "wrote default config -> $ENV_FILE"
fi
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

# CLI flags win over the file, and are persisted back so re-runs stay consistent
if [[ -n "$ARG_DOMAIN" ]];          then DOMAIN="$ARG_DOMAIN"; fi
if [[ -n "$ARG_PIPELINE_DOMAIN" ]]; then PIPELINE_DOMAIN="$ARG_PIPELINE_DOMAIN"; fi
if [[ -n "$ARG_EMAIL" ]];           then LE_EMAIL="$ARG_EMAIL"; fi
if [[ -n "$ARG_BRANCH" ]];          then WINDYCITY_BRANCH="$ARG_BRANCH"; fi
if [[ -n "$ARG_REPO" ]];            then WINDYCITY_REPO="$ARG_REPO"; fi
if [[ "$STUDIO_PORT_SET" -eq 0 ]];  then STUDIO_PORT=0; fi

: "${WINDYCITY_USER:=windycity}"
: "${WINDYCITY_REPO:=/opt/windycity}"
: "${WINDYCITY_REMOTE:=https://github.com/bartimoussmith-oss/therealwindycity.git}"
: "${WINDYCITY_BRANCH:=main}"
: "${CONSOLE_PORT:=8501}"
: "${PIPELINE_PORT:=8717}"
: "${STUDIO_PORT:=8080}"
: "${DOMAIN:=}"
: "${PIPELINE_DOMAIN:=}"
: "${LE_EMAIL:=}"
: "${SWAP_MB:=0}"

# A 1 GB x86 micro cannot run Streamlit without swap. Add it unless told otherwise.
if [[ "$SWAP_MB" == "0" && "$MEM_MB" -lt 2048 ]]; then SWAP_MB=2048; fi

# ---------------------------------------------------------------- packages
log "installing system packages ($PKG)…"
if [[ "$PKG" == "apt" ]]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends \
    git curl ca-certificates python3 python3-venv python3-pip \
    nginx ffmpeg fonts-dejavu-core rsync jq \
    certbot python3-certbot-nginx >/dev/null
  apt-get install -y -qq --no-install-recommends iptables-persistent >/dev/null 2>&1 || \
    warn "iptables-persistent unavailable — I will use ufw/rules.v4 fallback"
else
  dnf -y install git curl ca-certificates python3 python3-pip python3-virtualenv \
    nginx ffmpeg dejavu-sans-fonts rsync jq firewalld >/dev/null
  dnf -y install certbot python3-certbot-nginx >/dev/null 2>&1 || \
    warn "certbot-nginx not in repos — install it manually if you want TLS"
fi
command -v ffmpeg >/dev/null || warn "ffmpeg missing — clip/reel features in the studio will not work"
log "python: $(python3 --version 2>&1)"

# ---------------------------------------------------------------- swap
if [[ "$SWAP_MB" != "0" && ! -f /swapfile ]]; then
  log "creating ${SWAP_MB} MiB swapfile (small shapes need it)…"
  fallocate -l "${SWAP_MB}M" /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count="$SWAP_MB" status=none
  chmod 600 /swapfile; mkswap -q /swapfile >/dev/null; swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---------------------------------------------------------------- service user
if ! id -u "$WINDYCITY_USER" >/dev/null 2>&1; then
  log "creating service user '$WINDYCITY_USER'…"
  useradd --system --create-home --shell /bin/bash "$WINDYCITY_USER"
fi

# ---------------------------------------------------------------- repo checkout
# Clone as the service user so every file it needs to write (data/, public/,
# Entity_Database/, pipeline/corpus_yt/) is already owned correctly.
if [[ -d "$WINDYCITY_REPO/.git" ]]; then
  log "updating existing checkout in $WINDYCITY_REPO…"
  sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" remote set-url origin "$WINDYCITY_REMOTE"
  sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" fetch --quiet origin "$WINDYCITY_BRANCH"
  # never clobber local ledger changes: rebase only if the tree is clean
  if sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" diff --quiet && \
     sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" diff --cached --quiet; then
    sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" checkout --quiet "$WINDYCITY_BRANCH"
    sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" merge --ff-only --quiet "origin/$WINDYCITY_BRANCH"
    log "checkout at $(sudo -u "$WINDYCITY_USER" git -C "$WINDYCITY_REPO" rev-parse --short HEAD)"
  else
    warn "checkout has local modifications — leaving them alone (git status in $WINDYCITY_REPO)"
  fi
else
  log "cloning $WINDYCITY_REMOTE ($WINDYCITY_BRANCH) -> $WINDYCITY_REPO"
  mkdir -p "$(dirname "$WINDYCITY_REPO")"
  sudo -u "$WINDYCITY_USER" git clone --quiet --branch "$WINDYCITY_BRANCH" \
    "$WINDYCITY_REMOTE" "$WINDYCITY_REPO"
fi
chown -R "$WINDYCITY_USER:$WINDYCITY_USER" "$WINDYCITY_REPO"

# ---------------------------------------------------------------- virtualenv + deps
VENV="$WINDYCITY_REPO/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  log "creating virtualenv…"
  sudo -u "$WINDYCITY_USER" python3 -m venv "$VENV"
fi
log "installing python dependencies (a minute or two on a small shape)…"
sudo -u "$WINDYCITY_USER" "$VENV/bin/pip" install --quiet --upgrade pip setuptools wheel
sudo -u "$WINDYCITY_USER" "$VENV/bin/pip" install --quiet -r "$WINDYCITY_REPO/requirements.txt"
# optional bits the pipeline uses when they are importable
sudo -u "$WINDYCITY_USER" "$VENV/bin/pip" install --quiet yt-dlp curl_cffi >/dev/null 2>&1 || \
  warn "yt-dlp/curl_cffi install skipped (optional — only the last-resort video paths need them)"

# ---------------------------------------------------------------- engine init
# Cheap, idempotent: creates data/engine.db and syncs config/sources.json.
log "initialising the engine database…"
( cd "$WINDYCITY_REPO" && sudo -u "$WINDYCITY_USER" "$VENV/bin/python" -u run.py init ) \
  || warn "run.py init reported a problem — check $WINDYCITY_REPO/data before trusting the ledger"

# ---------------------------------------------------------------- systemd units
log "rendering and installing systemd units…"
bash "$TEMPLATES_DIR/render_config.sh" \
  --repo "$WINDYCITY_REPO" --user "$WINDYCITY_USER" \
  --console-port "$CONSOLE_PORT" --pipeline-port "$PIPELINE_PORT" \
  --studio-port "$STUDIO_PORT" --domain "$DOMAIN" \
  --pipeline-domain "$PIPELINE_DOMAIN" --install
systemctl daemon-reload
systemctl enable --now windycity-console.service  >/dev/null 2>&1 || warn "windycity-console failed to start — journalctl -u windycity-console"
systemctl enable --now windycity-pipeline.service >/dev/null 2>&1 || warn "windycity-pipeline failed to start — journalctl -u windycity-pipeline"
systemctl enable --now windycity-cycle.timer      >/dev/null 2>&1 || warn "windycity-cycle.timer failed to enable"

# ---------------------------------------------------------------- nginx
# the stock default site would shadow ours on :80
if [[ -e /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
  log "removed the stock nginx default site"
fi
nginx -t || die "nginx config test failed — see the message above"

# ---------------------------------------------------------------- firewall
log "opening the host firewall for 80/443${STUDIO_PORT:+/$STUDIO_PORT}…"
PORTS=(80 443)
if [[ "$STUDIO_PORT" != "0" ]]; then PORTS+=("$STUDIO_PORT"); fi
if systemctl is-active --quiet firewalld; then
  for p in "${PORTS[@]}"; do firewall-cmd --permanent --add-port="${p}/tcp" >/dev/null; done
  firewall-cmd --reload >/dev/null
elif command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q '^Status: active'; then
  for p in "${PORTS[@]}"; do ufw allow "${p}/tcp" >/dev/null; done
elif command -v iptables >/dev/null; then
  # OCI Ubuntu images ship a ruleset that is *fully populated* at boot
  # (ACCEPT lo/established/ssh, REJECT the rest). Persist additions so they
  # survive reboot.
  RULES=/etc/iptables/rules.v4
  mkdir -p /etc/iptables
  for p in "${PORTS[@]}"; do
    iptables -C INPUT -p tcp --dport "$p" -j ACCEPT 2>/dev/null || \
      iptables -I INPUT 5 -p tcp --dport "$p" -j ACCEPT || \
      warn "could not add an iptables rule for port $p — open it by hand"
  done
  if command -v netfilter-persistent >/dev/null; then
    netfilter-persistent save >/dev/null 2>&1 || warn "could not persist iptables rules"
  elif command -v iptables-save >/dev/null; then
    iptables-save > "$RULES" 2>/dev/null || warn "could not write $RULES"
    warn "install iptables-persistent so these rules survive reboot"
  fi
else
  warn "no firewalld/ufw/iptables found — confirm 80/443 are open in the OCI security list AND on the host"
fi

systemctl enable --now nginx >/dev/null 2>&1
systemctl reload nginx

# ---------------------------------------------------------------- TLS
if [[ "$TLS" -eq 1 && -n "$DOMAIN" ]]; then
  if ! getent hosts "$DOMAIN" >/dev/null; then
    warn "DNS for $DOMAIN does not resolve yet — skipping certbot. Point an A record at this host and re-run with --domain $DOMAIN"
  else
    MYIP="$(curl -fsS --max-time 5 https://api.ipify.org || echo '')"
    RESOLVED="$(getent hosts "$DOMAIN" | awk '{print $1; exit}')"
    if [[ -n "$MYIP" && "$RESOLVED" != "$MYIP" ]]; then
      warn "$DOMAIN resolves to $RESOLVED but this host is $MYIP — skipping certbot (DNS has not propagated)"
    else
      CERT_ARGS=(-d "$DOMAIN")
      if [[ -n "$PIPELINE_DOMAIN" ]]; then CERT_ARGS+=(-d "$PIPELINE_DOMAIN"); fi
      log "requesting a Let's Encrypt certificate for ${CERT_ARGS[*]}…"
      if [[ -n "$LE_EMAIL" ]]; then
        certbot --nginx --non-interactive --agree-tos --redirect -m "$LE_EMAIL" "${CERT_ARGS[@]}" \
          || warn "certbot failed — HTTP still works; re-run the bootstrap to retry"
      else
        certbot --nginx --non-interactive --agree-tos --register-unsafely-without-email --redirect "${CERT_ARGS[@]}" \
          || warn "certbot failed — HTTP still works; re-run with --email you@example.com to retry"
      fi
    fi
  fi
elif [[ "$TLS" -eq 1 && -z "$DOMAIN" ]]; then
  log "no --domain given: serving plain HTTP on the public IP (re-run with --domain + --email for HTTPS)"
fi

# ---------------------------------------------------------------- persist flags
write_kv() { # key value -> update or append in ENV_FILE (value may be empty)
  local k="$1" v="$2"
  if grep -q "^${k}=" "$ENV_FILE"; then
    sed -i "s|^${k}=.*|${k}=${v}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE"
  fi
}
write_kv DOMAIN "$DOMAIN"
write_kv PIPELINE_DOMAIN "$PIPELINE_DOMAIN"
write_kv LE_EMAIL "$LE_EMAIL"
write_kv STUDIO_PORT "$STUDIO_PORT"
write_kv WINDYCITY_REPO "$WINDYCITY_REPO"
chmod 0644 "$ENV_FILE"

# ---------------------------------------------------------------- summary
PUBIP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo '<public-ip>')"
if [[ -n "$DOMAIN" ]]; then
  CONSOLE_URL="https://${DOMAIN}   (also http://${PUBIP})"
else
  CONSOLE_URL="http://${PUBIP}"
fi
if [[ -n "$PIPELINE_DOMAIN" ]]; then
  STUDIO_URL="https://${PIPELINE_DOMAIN}"
elif [[ "$STUDIO_PORT" != "0" ]]; then
  STUDIO_URL="http://${PUBIP}:${STUDIO_PORT}"
else
  STUDIO_URL="disabled — reachable only on the box (127.0.0.1:${PIPELINE_PORT})"
fi

cat <<EOF

==============================================================================
 Deployed.
==============================================================================
 console      $CONSOLE_URL
 static ledger http://${DOMAIN:-$PUBIP}/ledger/
 rss feed     http://${DOMAIN:-$PUBIP}/feed.xml
 studio       $STUDIO_URL

 services     systemctl status windycity-console windycity-pipeline
 cycle timer  systemctl list-timers windycity-cycle.timer
 config       $ENV_FILE      (safe to edit, then re-run this script)
 verify       sudo bash ${TEMPLATES_DIR}/preflight.sh

 Reminder: the OCI security list must have ingress TCP 80 and 443 from 0.0.0.0/0
 (and $STUDIO_PORT if you want the studio on the bare IP). See deploy/oracle/README.md.
EOF
