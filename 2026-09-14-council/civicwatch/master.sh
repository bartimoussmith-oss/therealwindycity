#!/bin/bash
# Single serial chain for the 1 GB box. Every stage resumable. Log: data/master.log
set -o pipefail; cd "$(dirname "$0")"; export PIP_CACHE_DIR=~/.pipcache TMPDIR=~/.pipcache; LOG=data/master.log
say(){ echo "== $(date -u +%H:%M:%S) $*" | tee -a $LOG; }
say "crawl 2026 gap (Jan 12 – Apr 12)"; python3 civicwatch.py crawl --since 2026-01-01 --until 2026-04-12 --kinds council 2>&1 | grep -v "attach fail" | tee -a $LOG
say "ocr";      python3 ocr.py 2>&1 | tee -a $LOG
say "extract";  python3 civicwatch.py extract 2>&1 | head -2 | tee -a $LOG
say "rag build (civic + whole repo)"; python3 rag.py build --repo ~/twc 2>&1 | tee -a $LOG
say "verify";   python3 rag.py verify 2>&1 | tee -a $LOG; python3 rag.py stats 2>&1 | tee -a $LOG
say "MASTER DONE"
