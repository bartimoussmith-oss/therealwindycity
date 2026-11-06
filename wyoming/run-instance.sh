#!/usr/bin/env bash
# Per-instance runner: initialize storage and keep selftests out of live data.
set -euo pipefail
usage() { echo "usage: $0 <instance-slug> <command> [args...]" >&2; }
slug="${1:-}"
if [[ ! "$slug" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then usage; exit 2; fi
shift
if [ "$#" -eq 0 ]; then usage; exit 2; fi
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
inst="$root/wyoming/instances/$slug"
if [ ! -f "$inst/ecosystem.json" ] || [ -L "$inst" ]; then
  echo "unknown or symlinked instance '$slug'" >&2
  exit 2
fi
export ENGINE_CONFIG_DIR="$inst/config"
export ENGINE_DATA_DIR="${ENGINE_DATA_DIR:-$root/data/wyoming/$slug}"
export ENGINE_PUBLIC_DIR="${ENGINE_PUBLIC_DIR:-$root/public/wyoming/$slug}"
if [ -f "$inst/env.sh" ]; then . "$inst/env.sh"; fi
if [ "$1" = selftest ]; then
  scratch="$(mktemp -d)"
  trap 'rm -rf -- "$scratch"' EXIT
  export ENGINE_DATA_DIR="$scratch/data"
  export ENGINE_PUBLIC_DIR="$scratch/public"
  python3 "$root/run.py" "$@"
  exit 0
fi
help_only=false
for arg in "$@"; do
  if [ "$arg" = --help ] || [ "$arg" = -h ]; then help_only=true; fi
done
if [ "$help_only" = false ]; then
  case "$1" in
    crawl|work|search|digest|request)
      python3 "$root/run.py" init >/dev/null
      ;;
  esac
fi
exec python3 "$root/run.py" "$@"
