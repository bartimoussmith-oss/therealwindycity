#!/bin/bash
# Full rebuild: refetch 2026 raw PDFs, extend crawl to 2025, OCR scanned docs, re-extract.
set -o pipefail; cd "$(dirname "$0")"
export PIP_CACHE_DIR=~/.pipcache TMPDIR=~/.pipcache
echo "== $(date) refetch existing docs"
python3 - <<'PY'
import civicwatch as cw
from pathlib import Path
c=cw.db(); n=0
for did,url,path in c.execute("select id,url,path from docs").fetchall():
    p=Path(path)
    if p.exists() and p.stat().st_size>0: continue
    p.parent.mkdir(parents=True,exist_ok=True)
    try: cw.save(url,p); n+=1
    except Exception as e: print("fail",did,e)
    if n%50==0: print("refetched",n,flush=True)
print("refetched total",n)
PY
echo "== $(date) crawl 2025"
python3 civicwatch.py crawl --since 2025-01-01 --until 2025-12-31 --kinds council
echo "== $(date) ocr"
python3 ocr.py
echo "== $(date) extract"
python3 civicwatch.py extract
echo "== $(date) ALL DONE"
