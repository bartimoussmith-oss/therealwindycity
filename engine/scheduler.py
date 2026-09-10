"""Daily operations loop: crawl -> work -> digest on an interval.

Run once:            python3 engine/scheduler.py --once
Run continuously:    python3 -u engine/scheduler.py --hours 6
Pod/VM cron instead: 15 */6 * * * cd civic-engine && python3 run.py crawl && python3 run.py work && python3 run.py digest --days 1
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import db, digest, ingest  # noqa: E402
from engine.extract import process_jobs  # noqa: E402


def cycle(conn) -> None:
    print(f"[scheduler] cycle start {db.utcnow()}", flush=True)
    try:
        from . import publish  # noqa: PLC0415
        n = ingest.crawl_all(conn)
        j = process_jobs(conn, kinds=("extract", "diff"))
        digest.build_digest(conn, days=1)
        site = publish.build()
        s = digest.stats(conn)
        print(f"[scheduler] done: {n} links, {j} jobs, "
              f"{s['documents']} docs, {s['silent_edits']} silent edits, "
              f"{s['alerts']} alerts; republished {site}", flush=True)
    except Exception:
        traceback.print_exc()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hours", type=float, default=24.0,
                    help="interval between cycles (default 24)")
    ap.add_argument("--once", action="store_true", help="run one cycle and exit")
    args = ap.parse_args()
    db.init_db()
    conn = db.connect()
    while True:
        cycle(conn)
        if args.once:
            break
        time.sleep(args.hours * 3600)


if __name__ == "__main__":
    main()
