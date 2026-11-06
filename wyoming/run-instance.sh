#!/usr/bin/env bash
# Run any Wyoming instance of the Civic Transparency Engine.
# Usage: wyoming/run-instance.sh <slug> <run.py command> [args...]
#   wyoming/run-instance.sh casper selftest
#   wyoming/run-instance.sh natrona-county init
#   wyoming/run-instance.sh laramie request pra "records description" "2026-01-01 to present"
set -euo pipefail
slug="${1:-}"
if [ -z "$slug" ]; then echo "usage: $0 <instance-slug> <command...>  (see wyoming/registry.json)" >&2; exit 2; fi
shift || true
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
inst="$root/wyoming/instances/$slug"
if [ ! -d "$inst" ]; then echo "unknown instance '$slug' — see wyoming/registry.json" >&2; exit 2; fi
export ENGINE_CONFIG_DIR="$inst/config"
export ENGINE_DATA_DIR="${ENGINE_DATA_DIR:-$root/data/wyoming/$slug}"
export ENGINE_PUBLIC_DIR="${ENGINE_PUBLIC_DIR:-$root/public/wyoming/$slug}"
if [ -f "$inst/env.sh" ]; then . "$inst/env.sh"; fi
exec python3 "$root/run.py" "$@"
