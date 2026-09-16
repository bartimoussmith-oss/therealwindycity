#!/bin/bash
# After finish_all: fill the Jan 12 – Apr 12 2026 gap (13 council + special meetings), OCR any new scans, extract, RAG top-up, verify.
set -o pipefail; cd "$(dirname "$0")"; export PIP_CACHE_DIR=~/.pipcache TMPDIR=~/.pipcache; LOG=data/finish2.log
while pgrep -f finish_all.sh >/dev/null; do sleep 30; done
echo "== $(date) crawl 2026 gap" | tee -a $LOG
python3 civicwatch.py crawl --since 2026-01-01 --until 2026-04-12 --kinds council 2>&1 | grep -v "attach fail" | tee -a $LOG
echo "== $(date) ocr new" | tee -a $LOG;      python3 ocr.py 2>&1 | tail -5 | tee -a $LOG
echo "== $(date) extract" | tee -a $LOG;      python3 civicwatch.py extract 2>&1 | head -2 | tee -a $LOG
echo "== $(date) rag top-up" | tee -a $LOG;   python3 rag.py build --repo ~/twc 2>&1 | tail -2 | tee -a $LOG
python3 rag.py verify 2>&1 | tee -a $LOG; python3 rag.py stats 2>&1 | tee -a $LOG
echo "== $(date) FINISH2 DONE" | tee -a $LOG
