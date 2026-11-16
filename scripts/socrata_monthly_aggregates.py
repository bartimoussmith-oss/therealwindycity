#!/usr/bin/env python3
"""Monthly aggregate totals from Laramie County Sheriff Socrata dataset 35sf-bu8v.

Only server-side aggregates are requested (COUNT grouped by month, incident
type, and agency). No row-level data is downloaded, and no personal fields
(names, dates of birth, addresses, incident numbers) are ever selected.

Usage:
    python3 scripts/socrata_monthly_aggregates.py --months 2026-10 2026-11 \
        --out reports/socrata-35sf-bu8v-2026-10-11.md
    python3 scripts/socrata_monthly_aggregates.py --fixture tests/fixtures/... (offline)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

HOST = "https://laramiecountywy-sheriff.data.socrata.com"
DATASET = "35sf-bu8v"
TIMESTAMP = "call_date_time"
# Only these aggregate-safe columns may be selected or grouped on.
ALLOWED_GROUP_FIELDS = {"incident_type", "agency"}


def month_bounds(ym: str) -> tuple[str, str]:
    start = dt.datetime.strptime(ym, "%Y-%m").replace(tzinfo=dt.timezone.utc)
    end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S")


def build_soql(ym: str, group_by: list[str]) -> dict:
    """Return query params for one month. Raises if a non-aggregate field is requested."""
    bad = set(group_by) - ALLOWED_GROUP_FIELDS
    if bad:
        raise ValueError(f"field(s) not permitted in aggregate output: {sorted(bad)}")
    lo, hi = month_bounds(ym)
    select = ", ".join(group_by + ["count(*) AS total"])
    return {
        "$select": select,
        "$where": f"{TIMESTAMP} >= '{lo}' AND {TIMESTAMP} < '{hi}'",
        "$group": ", ".join(group_by),
        "$order": "total DESC",
        "$limit": "5000",
    }


def fetch_live(ym: str, group_by: list[str]) -> list[dict]:
    import requests  # local import: fixture mode needs no network library

    params = build_soql(ym, group_by)
    r = requests.get(f"{HOST}/resource/{DATASET}.json", params=params, timeout=60,
                     headers={"User-Agent": "LaramieCivicAggregates/1.0"})
    r.raise_for_status()
    return r.json()


def summarize(rows_by_month: dict[str, list[dict]]) -> dict:
    summary = {}
    for ym, rows in rows_by_month.items():
        total = sum(int(r.get("total", 0)) for r in rows)
        by_type: dict[str, int] = {}
        for r in rows:
            t = r.get("incident_type") or "(unspecified)"
            by_type[t] = by_type.get(t, 0) + int(r.get("total", 0))
        summary[ym] = {"total": total,
                       "by_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1]))}
    months = list(summary)
    if len(months) == 2:
        a, b = summary[months[0]]["total"], summary[months[1]]["total"]
        change = None if a == 0 else round((b - a) / a * 100, 1)
        summary["_change"] = {"from": months[0], "to": months[1], "abs": b - a, "pct": change}
    return summary


def render(summary: dict, months: list[str], generated: str, source: str) -> str:
    lines = [
        "# Socrata aggregate compliance totals — dataset 35sf-bu8v",
        "",
        f"- Source: {source}",
        f"- Generated (UTC): {generated}",
        "- Method: server-side COUNT grouped by month and incident type. "
        "No row-level records were downloaded.",
        "- Excluded by design: incident numbers, names, dates of birth, addresses, "
        "and any other identifying field.",
        "",
        "## Monthly totals",
        "",
        "| Month | Total incidents |",
        "|---|---:|",
    ]
    for ym in months:
        lines.append(f"| {ym} | {summary[ym]['total']} |")
    ch = summary.get("_change")
    if ch:
        pct = "n/a" if ch["pct"] is None else f"{ch['pct']}%"
        lines += ["", f"Change {ch['from']} → {ch['to']}: {ch['abs']:+d} ({pct})."]
    for ym in months:
        lines += ["", f"## Breakdown by incident type — {ym}", "",
                  "| Incident type | Count |", "|---|---:|"]
        for t, n in summary[ym]["by_type"].items():
            lines.append(f"| {t} | {n} |")
        if not summary[ym]["by_type"]:
            lines.append("| (no rows) | 0 |")
    lines += ["", "_Counts are as published by the source at query time. Nothing has been inferred._", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", nargs="+", required=True, help="YYYY-MM values")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fixture", help="JSON file of {month: [rows]} for offline runs")
    args = ap.parse_args(argv)

    if args.fixture:
        data = json.loads(Path(args.fixture).read_text())
        rows = {m: data.get(m, []) for m in args.months}
        source = f"offline fixture {args.fixture} (NOT live data)"
    else:
        rows = {m: fetch_live(m, ["incident_type"]) for m in args.months}
        source = f"{HOST}/resource/{DATASET}.json"

    summary = summarize(rows)
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(render(summary, args.months, generated, source), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
