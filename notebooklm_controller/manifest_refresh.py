#!/usr/bin/env python3
"""
manifest_refresh.py — Bring the Cheyenne meeting manifest current to today
(2026-11-04) by re-syncing every connected repo and public source.

Public sources re-synced (network required; fails gracefully offline):

  1. pipeline/corpus_yt/              — verbatim YouTube transcripts (2026+)
     via pipeline/sync_yt_corpus.py from therealwindycity/The-Real-Windy-City-
     (cheyenne-2026-transcripts). Captures any new YouTube meetings since the
     last sync.
  2. pipeline/meetings.json           — Granicus meeting index (agendas,
     minutes, MP4 URLs) via pipeline/cheyenne_pipeline.py index. Captures new
     Granicus meetings (e.g. late-Aug through Nov 2026).
  3. youtube-archive/catalog_granicus.json — Granicus catalog mirror via
     youtube-archive/scripts/scrape_granicus.py.

After re-syncing, rebuilds the controller queue so new meetings (through
2026-11-04) are included in the oldest->newest run.

Usage:
  python3 notebooklm_controller/manifest_refresh.py   # refresh all sources
  python3 notebooklm_controller/manifest_refresh.py --queue-only   # rebuild queue from existing files

When network is unavailable (this sandbox), each step reports what it would
do and fails gracefully; the existing manifest is left intact.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINE = ROOT / "pipeline"
SYNC_YT = PIPELINE / "sync_yt_corpus.py"
CHEYENNE_PIPELINE = PIPELINE / "cheyenne_pipeline.py"
SCRAPE_GRANICUS = ROOT / "youtube-archive" / "scripts" / "scrape_granicus.py"


def _run(cmd: list[str], label: str) -> bool:
    print(f"[refresh] {label} ...")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.stdout:
            for line in proc.stdout.splitlines()[-8:]:
                print(f"      {line}")
        if proc.returncode != 0:
            print(f"[refresh] {label} exited {proc.returncode}")
            if proc.stderr:
                for line in proc.stderr.splitlines()[-5:]:
                    print(f"      ! {line}")
            return False
        print(f"[refresh] {label} OK")
        return True
    except subprocess.TimeoutExpired:
        print(f"[refresh] {label} timed out")
        return False
    except FileNotFoundError:
        print(f"[refresh] {label}: script not found ({cmd[0]})")
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[refresh] {label}: {e}")
        return False


def refresh_corpus_yt() -> bool:
    """Re-sync verbatim YouTube transcripts from upstream GitHub."""
    env = dict(os.environ)
    # Point at the official upstream; override for testing via YT_CORPUS_BASE.
    return _run([sys.executable, str(SYNC_YT)], "sync corpus_yt (YouTube transcripts)")


def refresh_meetings_index() -> bool:
    """Re-index Granicus meetings (agendas/minutes/MP4s) into meetings.json."""
    return _run([sys.executable, str(CHEYENNE_PIPELINE), "index"],
                "re-index meetings.json (Granicus)")


def refresh_granicus_catalog() -> bool:
    """Re-scrape the Granicus catalog mirror."""
    if not SCRAPE_GRANICUS.exists():
        print(f"[refresh] granicus catalog script missing: {SCRAPE_GRANICUS}")
        return False
    return _run([sys.executable, str(SCRAPE_GRANICUS)],
                "re-scrape granicus catalog")


def rebuild_queue() -> dict:
    """Rebuild the controller queue from the (possibly refreshed) source files.

    Returns the queue so callers can report date range / count.
    """
    from archive_inventory import build_queue
    queue = build_queue(live=False)
    state_dir = ROOT / "notebooklm_controller" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "queue.json").write_text(json.dumps(queue, indent=1),
                                          encoding="utf-8")
    return queue


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Refresh the Cheyenne meeting manifest to current data")
    parser.add_argument("--queue-only", action="store_true",
                        help="rebuild the queue from existing files only")
    args = parser.parse_args(argv)

    if args.queue_only:
        queue = rebuild_queue()
    else:
        ok = True
        ok &= refresh_corpus_yt()
        ok &= refresh_meetings_index()
        ok &= refresh_granicus_catalog()
        queue = rebuild_queue()
        print(f"[refresh] network-dependent steps complete (ok={ok})")

    if queue:
        dates = [m["date"] for m in queue if m.get("date")]
        print(f"[refresh] queue: {len(queue)} meetings, "
              f"{min(dates)} -> {max(dates)}" if dates else "queue empty")
    else:
        print("[refresh] queue empty")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
