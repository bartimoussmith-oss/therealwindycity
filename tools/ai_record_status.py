"""Snapshot metadata. Never infer collection freshness or outcomes from meeting dates."""
import datetime as dt
import os
import re


def snapshot_status(catalog, stats):
    dates = [m.get("date", "") for m in catalog]
    dates = [d for d in dates if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)]
    return {
        "schema_version": 1,
        "build_revision": os.environ.get("GITHUB_SHA", "local-unversioned"),
        "build_run": os.environ.get("GITHUB_RUN_ID"),
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "collection_checked_at": None,
        "latest_indexed_meeting": max(dates, default=None),
        "latest_verified_outcome": None,
        "counts": stats,
        "limitations": [
            "Build time is not a collection-check timestamp.",
            "The latest indexed date does not establish complete coverage through that date.",
            "Counts describe this generated snapshot, not all official city records.",
            "Missing or scanned documents may lack usable text; captions are not verified quotations.",
        ],
    }


def status_panel(status):
    latest = status["latest_indexed_meeting"] or "Not recorded"
    return f"""## Archive status and coverage

| Measure | This snapshot |
|---|---|
| Collection last checked against official sources | Not recorded |
| Latest meeting date in the index | {latest} |
| Latest independently verified outcome | Not recorded in snapshot metadata |

**Scope clarification:** “full record” and “every archived” below describe the
material indexed by this mirror, not a completeness guarantee for official records.
Transcripts are machine captions, not independently verified verbatim quotations.
An indexed date may refer to a posted meeting rather than a completed meeting.
Build and deployment times are not collection timestamps.

Counts below describe generated holdings; they are not an overall OCR-pending count.
A recent indexed date does not prove continuous coverage or a verified decision.
Check important quotations, votes, deadlines, and legal interpretations against
original records. See [data quality](topics/data-quality.md),
[corrections](topics/corrections.md), and the
[machine-readable snapshot status](indexes/status.json).

"""
