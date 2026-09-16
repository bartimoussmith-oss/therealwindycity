#!/bin/bash
# Serial (1 GB RAM box): wait for RAG build → OCR remaining scanned docs → re-extract → RAG top-up with OCR pages → verify.
# Every stage is idempotent/resumable: rag.py skips existing chunk ids; ocr.py skips docs with ocr=1.
set -o pipefail; cd "$(dirname "$0")"
export PIP_CACHE_DIR=~/.pipcache TMPDIR=~/.pipcache
LOG=data/finish_all.log
while pgrep -f "rag.py build" >/dev/null; do sleep 30; done
echo "== $(date) rag stage-1 finished; ocr" | tee -a $LOG
python3 ocr.py 2>&1 | tee -a $LOG
echo "== $(date) extract" | tee -a $LOG
python3 civicwatch.py extract 2>&1 | tail -3 | tee -a $LOG
echo "== $(date) rag top-up (OCR pages + anything new)" | tee -a $LOG
python3 rag.py build --repo ~/twc 2>&1 | tail -3 | tee -a $LOG
python3 rag.py verify 2>&1 | tee -a $LOG
python3 rag.py stats 2>&1 | tee -a $LOG
echo "== $(date) FINISH ALL DONE" | tee -a $LOG
