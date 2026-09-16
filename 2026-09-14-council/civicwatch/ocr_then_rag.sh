#!/bin/bash
# Runs after master.sh's RAG build: OCR all scans, re-extract, incremental RAG top-up, verify.
set -o pipefail; cd "$(dirname "$0")"; export PIP_CACHE_DIR=~/.pipcache TMPDIR=~/.pipcache; LOG=data/master.log
say(){ echo "== $(date -u +%H:%M:%S) $*" | tee -a $LOG; }
while pgrep -f "master.sh" >/dev/null; do sleep 30; done
python3 -c "import sqlite3; c=sqlite3.connect('data/civic.db',timeout=120); c.execute('update docs set ocr=0 where ocr=-1'); c.commit()"
say "ocr (pass 2)"; python3 ocr.py 2>&1 | tee -a $LOG
say "extract";      python3 civicwatch.py extract 2>&1 | head -2 | tee -a $LOG
say "rag top-up";   python3 rag.py build --repo ~/twc 2>&1 | tail -3 | tee -a $LOG
say "verify";       python3 rag.py verify 2>&1 | tee -a $LOG; python3 rag.py stats 2>&1 | tee -a $LOG
say "OCR+RAG DONE"
