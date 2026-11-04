#!/usr/bin/env python3
"""Detect every scraped dataset in this repo, then render the provenance film.

    python3 scripts/make_provenance_video.py                # detect + plan + video
    python3 scripts/make_provenance_video.py --detect-only
    python3 scripts/make_provenance_video.py --preview 8,40,95.5

Outputs:
    data/out/provenance-inventory.json      machine-readable inventory
    data/out/PROVENANCE-INVENTORY.md        the same, for humans
    data/out/provenance-storyboard.json     what the film will show
    video/provenance-manual-run.mp4         the film
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from provenance.cli import main as cli_main  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--detect-only", action="store_true", help="write the inventory and stop")
    ap.add_argument("--preview", default="", help="comma-separated timestamps → PNGs instead of a video")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--out", default="video/provenance-manual-run.mp4")
    args = ap.parse_args()

    if args.detect_only:
        return cli_main(["detect"])
    if args.preview:
        return cli_main(["video", "--preview", args.preview])
    return cli_main(["all", "--fps", str(args.fps), "--scale", str(args.scale)])


if __name__ == "__main__":
    raise SystemExit(main())
