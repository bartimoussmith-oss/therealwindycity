#!/usr/bin/env python3
"""Check the rendered artifact or exact published build; fails closed on mismatch."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import time
from urllib.request import urlopen


def validate(read, revision=None, run=None):
    home = read("index.html")
    status = json.loads(read("indexes/status.json"))
    catalog = json.loads(read("indexes/meetings.json"))
    assert "Archive status and coverage" in home, "missing rendered status panel"
    assert "Build and deployment times are not collection timestamps" in home
    assert "{{stat:" not in home, "unexpanded homepage placeholder"
    assert status["collection_checked_at"] is None, "collection checks need an explicit provenance implementation"
    assert status["latest_verified_outcome"] is None
    assert status["counts"]["meetings"] == catalog["count"] == len(catalog["meetings"])
    if revision:
        assert status["build_revision"] == revision, "published revision differs"
    if run:
        assert status["build_run"] == run, "published workflow run differs"
    # Catch an explicit dated 'upcoming' label in either date/label order.
    today = dt.datetime.now(dt.timezone.utc).date()
    text = re.sub(r"<[^>]+>", " ", home)
    for match in re.finditer(r"upcoming.{0,60}?(\d{4}-\d{2}-\d{2})|(\d{4}-\d{2}-\d{2}).{0,60}?upcoming", text, re.I):
        assert dt.date.fromisoformat(match.group(1) or match.group(2)) >= today, "past meeting labeled upcoming"
    for path in ("llms.txt", "topics/corrections.html", "topics/data-quality.html"):
        assert read(path).strip(), f"empty {path}"
    for meeting in catalog["meetings"][:1]:
        path = "meetings/" + meeting["date"][:4] + "/" + meeting["id"] + ".html"
        assert read(path).strip(), "missing sample meeting page"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--site", type=Path)
    source.add_argument("--url")
    parser.add_argument("--revision")
    parser.add_argument("--run")
    parser.add_argument("--attempts", type=int, default=1)
    args = parser.parse_args()
    def read(path):
        if args.site:
            return (args.site / path).read_text(encoding="utf-8")
        url = args.url.rstrip("/") + "/" + path + "?verify=" + (args.run or args.revision or "status")
        with urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8")
    for attempt in range(args.attempts):
        try:
            validate(read, args.revision, args.run)
            print("Snapshot and key pages verified")
            return
        except (AssertionError, OSError, ValueError, KeyError) as error:
            if attempt + 1 == args.attempts:
                raise SystemExit(f"Site verification failed: {error}")
            time.sleep(15)


if __name__ == "__main__":
    main()
