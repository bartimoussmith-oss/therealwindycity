#!/usr/bin/env bash
# Drain the Granicus transcription queue on a Colab GPU session, from a Chromebook.
#
# The browser notebook (tools/colab_transcribe_granicus.py) works, but it dies with the
# tab and you have to babysit it. This runs the same script headlessly on a Colab runtime
# from the Linux terminal, in resumable chunks, and (usually) cleans up after itself.
#
#   bash tools/colab_cli_drain.sh                    # T4, 3 chunks, 1.5 h each
#   bash tools/colab_cli_drain.sh --gpu A100 --chunks 6 --hours 2
#   bash tools/colab_cli_drain.sh --model large-v3 --year 2026
#   bash tools/colab_cli_drain.sh --keep             # leave the VM running for inspection
#   bash tools/colab_cli_drain.sh --watch            # stay attached, use `colab stop` yourself
#
# WHY IT LOOKS LIKE THIS
#   * `colab run` tears down the VM when the script exits, which would throw away the
#     ~4 minutes of model download and warm-up. So: one long-lived session, a few
#     `colab exec` calls into it, then `colab stop`.
#   * State lives in Google Drive, not the VM, so a lost session resumes where it stopped.
#   * Every chunk is time-boxed. Colab kills kernels without warning; a chunk that ends
#     cleanly cannot lose more than the clip in flight.
#   * The VM is billable while it exists. This script stops it on every exit path it
#     controls, including Ctrl-C. It cannot help if your Chromebook sleeps or the
#     network drops — then `colab sessions` and `colab stop -s <name>` are on you.
#
# Needs: the Colab CLI (tools/chromebook_colab_setup.sh) and a Chromebook with Linux on.
# Run this from a clone of the repo, because it uploads the neighbouring .py file.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO_DIR/tools/colab_transcribe_granicus.py"

GPU="T4"
SESS="windycity"
CHUNKS=3
MAX_CLIPS=12
MAX_MINUTES=240
WALL_HOURS=1.5
MODEL="small.en"
YEAR=""
KEEP=""
WATCH=""

while [ $# -gt 0 ]; do
  case "$1" in
    --gpu) GPU="$2"; shift 2 ;;
    --session) SESS="$2"; shift 2 ;;
    --chunks) CHUNKS="$2"; shift 2 ;;
    --max-clips) MAX_CLIPS="$2"; shift 2 ;;
    --max-minutes) MAX_MINUTES="$2"; shift 2 ;;
    --hours) WALL_HOURS="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    --year) YEAR="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    --watch) WATCH=1; shift ;;
    -h|--help) sed -n '2,30p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
note() { printf '  \033[2m%s\033[0m\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

command -v colab >/dev/null 2>&1 || { echo "colab CLI not found — run tools/chromebook_colab_setup.sh first" >&2; exit 1; }
[ -f "$SCRIPT" ] || { echo "missing $SCRIPT — run this from the repo" >&2; exit 1; }

cleanup() {
  local code=$?
  if [ -z "${KEEP}" ]; then
    say "Releasing the VM (colab stop -s $SESS)"
    colab stop -s "$SESS" >/dev/null 2>&1 && note "stopped" || note "already gone"
  else
    warn "--keep set: session '$SESS' is still running and still billable."
    note "  colab stop -s $SESS     when you are done"
  fi
  exit $code
}
trap cleanup EXIT INT TERM

# --------------------------------------------------------------------------
say "Colab usage before we start"
colab usage || warn "could not read compute-unit balance"
# --------------------------------------------------------------------------

say "Allocating a $GPU runtime as '$SESS'"
colab new -s "$SESS" --gpu "$GPU"
colab status -s "$SESS"

say "Installing faster-whisper on the runtime"
colab install -s "$SESS" faster-whisper==1.2.1 av==18.1.0

say "Uploading the transcriber and the clip catalog"
colab upload -s "$SESS" "$SCRIPT" /content/colab_transcribe_granicus.py
CATALOG="$REPO_DIR/youtube-archive/catalog_granicus.json"
if [ -f "$CATALOG" ]; then
  colab upload -s "$SESS" "$CATALOG" /content/catalog_granicus.json
  note "using the repo's catalog (already includes the Oct 2026 clips)"
else
  note "no local catalog — the script will read the portal itself"
fi

say "Mounting Google Drive on the runtime"
note "first time: approve the Drive prompt in the browser, transcripts land in"
note "  MyDrive/granicus-transcripts/"
colab drivemount -s "$SESS" /content/drive

# the per-chunk config, written on the VM so each exec is one line
cat >/tmp/drain_config.py <<PY
CONFIG.update({
    "use_drive": True,
    "drive_subdir": "granicus-transcripts",
    "model": "$MODEL",
    "max_clips": "$MAX_CLIPS",
    "max_minutes": "$MAX_MINUTES",
    "max_hours": "$WALL_HOURS",
    "years": ("$YEAR",) if "$YEAR" else None,
})
PY
colab upload -s "$SESS" /tmp/drain_config.py /content/drain_config.py
colab exec -s "$SESS" -c "
import sys, json, pathlib
sys.argv = ['x', '--self-test']
src = pathlib.Path('/content/colab_transcribe_granicus.py').read_text()
ns = {'__name__': 'not_main'}
exec(compile(src, 'colab_transcribe_granicus.py', 'exec'), ns)
assert ns['self_test']() == 0, 'parser self-test failed — the portal markup may have moved'
print('self-test ok')
"

if [ -n "${WATCH}" ]; then
  say "Attaching. Ctrl-] then q to detach; the VM keeps running and keeps billing."
  note "when you are finished: colab stop -s $SESS"
  colab console -s "$SESS"
  exit 0
fi

# --------------------------------------------------------------------------
say "$CHUNKS chunks × up to $WALL_HOURS h"
note "model $MODEL · $MAX_CLIPS clips / $MAX_MINUTES stated minutes per chunk${YEAR:+ · year $YEAR}"

# Apply the config once, in the kernel, so every later exec sees it without re-running.
colab exec -s "$SESS" -c "
import pathlib
exec(compile(pathlib.Path('/content/colab_transcribe_granicus.py').read_text(),
             'colab_transcribe_granicus.py', 'exec'), globals())
exec(pathlib.Path('/content/drain_config.py').read_text())
CONFIG['_applied'] = True
print('config applied:', {k: CONFIG[k] for k in ('model', 'max_clips', 'max_minutes', 'years')})
"

for i in $(seq 1 "$CHUNKS"); do
  say "Chunk $i of $CHUNKS"
  # run() re-reads CONFIG from the module globals; install() and load_model() are no-ops
  # after the first chunk, so only the first pays for the model download.
  colab exec -s "$SESS" -c "
import pathlib
exec(compile(pathlib.Path('/content/colab_transcribe_granicus.py').read_text(),
             'colab_transcribe_granicus.py', 'exec'), globals())
exec(pathlib.Path('/content/drain_config.py').read_text())
run(CONFIG)
"
done

say "Exporting the session log"
colab log -s "$SESS" -o "/tmp/colab-session-$(date +%Y%m%d-%H%M).md" || warn "log export failed"
note "logs are on this Chromebook in /tmp"

say "Done. What is left?"
colab exec -s "$SESS" -c "
import pathlib, json
src = pathlib.Path('/content/colab_transcribe_granicus.py').read_text()
ns = {'__name__': 'not_main'}
exec(compile(src, 'colab_transcribe_granicus.py', 'exec'), ns)
items = ns['load_manifest'](ns['out_dir'](ns['CONFIG']))
done = sum(i.get('duration_audio_seconds') or 0 for i in items.values()) / 3600
print(f'{len(items):,} transcripts · {done:,.1f} h of 792.5 h · {max(0, 792.5-done):,.1f} h left')
"
