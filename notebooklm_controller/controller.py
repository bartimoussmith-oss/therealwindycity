#!/usr/bin/env python3
"""
notebooklm_controller/controller.py — Auto-running NotebookLM controller for the
FULL City of Cheyenne meeting archive (2008 -> present, ~479 meetings).

Mission (oldest -> newest):
  1. Inventory every meeting from pipeline/meetings.json (Granicus backbone,
     2008-05-27 -> 2026-08-24), matched with verbatim YouTube transcripts from
     pipeline/corpus_yt/ (2026) and per-meeting minutes text split from
     pipeline/notebooklm/cheyenne_minutes_*.md (2008+).
  2. Per meeting: define one NotebookLM notebook — video + verbatim transcript
     + agenda/supporting documents.
  3. Generate studio artifacts per meeting:
       01 meeting brief · 02 transcript notes · 03 agenda trace ·
       04 historical context · 05 audio overview · 06 studio package
  4. Weave history: each artifact summarizes what earlier meetings said about
     the same ordinances, projects, and people.
  5. Scrub every artifact for NotebookLM / Gemini watermarks before it hits
     disk; record the audit trail in 00_manifest.json.

Usage:
  python3 controller.py run              # process whole queue, oldest -> newest
  python3 controller.py run --since 2010-01-01   # start at a date
  python3 controller.py run --limit 12           # process N meetings (test)
  python3 controller.py status             # queue + checkpoint state
  python3 controller.py report             # last-run report
  python3 controller.py inventory          # print the meeting queue

Live NotebookLM (needs your machine + Google account):
  NOTEBOOKLM_LIVE=1 python3 controller.py run   # uses notebooklm-py client

Everything produced lands under notebooklm_controller/. Nothing is sent to
Google unless NOTEBOOKLM_LIVE=1 and you've run `notebooklm login`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = ROOT / "notebooklm_controller"
ARTIFACTS = CONTROLLER_DIR / "artifacts"
STATE = CONTROLLER_DIR / "state"
RUNS = CONTROLLER_DIR / "runs"
LOGS = CONTROLLER_DIR / "logs"
CHECKPOINT = STATE / "checkpoint.json"

import os  # noqa: E402

from archive_inventory import build_queue  # noqa: E402
from notebooklm_adapter import NotebookLMAdapter  # noqa: E402
from artifact_builder import build_artifacts  # noqa: E402
from history_weaver import extract_entities, find_prior_context, register_meeting  # noqa: E402
from watermark_scrubber import scrub_text  # noqa: E402
from doc_harvester import harvest_for_meeting  # noqa: E402
from manifest_refresh import rebuild_queue, refresh_corpus_yt, refresh_granicus_catalog, refresh_meetings_index  # noqa: E402

LIVE = bool(int(os.environ.get("NOTEBOOKLM_LIVE", "0")))


def _log(run_id: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{ts} {msg}"
    print(line)
    LOGS.mkdir(parents=True, exist_ok=True)
    with (LOGS / f"{run_id}.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_checkpoint() -> dict:
    try:
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "completed": [], "failed": [], "last_run": None}


def save_checkpoint(cp: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(cp, indent=1), encoding="utf-8")


def load_meeting_transcript(meeting: dict) -> str | None:
    """Return VERBATIM transcript text only — never minutes.

    Returns None when no verbatim transcript is available (2008-2025 meetings).
    Callers must check meeting['has_verbatim_transcript'] before treating this
    as verbatim.
    """
    if meeting.get("has_verbatim_transcript") and meeting.get("transcript_text"):
        return meeting["transcript_text"]
    path = meeting.get("transcript_path")
    if path and Path(path).exists() and meeting.get("has_verbatim_transcript"):
        return Path(path).read_text(encoding="utf-8", errors="replace")
    return None


def load_meeting_minutes(meeting: dict) -> str | None:
    """Return SUMMARIZED minutes text only — never verbatim transcript.

    Minutes are a different source type with different evidentiary status.
    Callers must not treat this as verbatim or attach timestamps to it.
    """
    if meeting.get("minutes_text"):
        return meeting["minutes_text"]
    path = meeting.get("minutes_path")
    if path and Path(path).exists():
        return Path(path).read_text(encoding="utf-8", errors="replace")
    return None


def process_meeting(meeting: dict, adapter: NotebookLMAdapter,
                    run_id: str) -> dict:
    date = meeting["date"]
    body = meeting["body"]
    clip_id = meeting["clip_id"]

    # Load verbatim transcript (None if not available — 2008-2025).
    transcript = load_meeting_transcript(meeting)

    # Load minutes separately — NEVER substituted for transcript.
    minutes = load_meeting_minutes(meeting)

    meeting_with_text = dict(meeting)
    meeting_with_text["transcript_text"] = transcript
    meeting_with_text["minutes_text"] = minutes

    # Historical context from everything processed before this meeting.
    # For entity extraction, prefer verbatim transcript; fall back to minutes
    # only for entity matching (clearly flagged as minutes-derived).
    # Reload index each meeting so cross-meeting context within this run accumulates.
    import history_weaver as hw
    index = hw.load_index()
    text_for_entities = transcript if transcript else (minutes or "")
    entities = extract_entities(text_for_entities)
    prior = find_prior_context(entities, date, index)

    # Context sources: prior meetings' studio packages converted to optimal
    # plain-text sources and added into THIS notebook so the model reads the
    # actual prior record, not just a reference. Oldest -> newest.
    context_sources = hw.context_sources_for(date, index, limit=6,
                                             artifacts_root=ARTIFACTS)

    # --- Harvest the agenda page + every linked supporting document ---
    # Done before artifact build so supporting_docs flows into the notebook
    # spec and the agenda-trace artifact. When the host is unreachable, keep
    # the legacy Granicus catalog entries already on the meeting record.
    out_dir = ARTIFACTS / f"{date}-{body}-{clip_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    harvested = None
    try:
        harvested = harvest_for_meeting(meeting_with_text, ARTIFACTS)
    except Exception as exc:  # never let doc harvest kill a meeting
        print(f"[controller] doc harvest failed {date}-{body}-{clip_id}: {exc}")
    if harvested:  # non-empty = we actually got the agenda page
        meeting_with_text["supporting_docs"] = harvested
    # else: leave the inventory's legacy supporting_docs in place

    # Studio artifacts.
    artifacts = build_artifacts(meeting_with_text, prior, scrub_text)

    written: dict[str, str] = {}
    for fname, (content, scan) in artifacts.items():
        dest = out_dir / fname
        dest.write_text(content, encoding="utf-8")
        written[fname] = str(dest)

    # Notebook spec (what the live adapter creates in NotebookLM).
    # Pass both transcript and minutes as SEPARATE sources — never substituted.
    notebook_spec = adapter.notebook_for_meeting(
        meeting, [f for f in artifacts if f != "00_manifest.json"],
        context_sources=context_sources)
    spec_path = adapter.write_spec(notebook_spec)
    _log(run_id, f"notebook spec -> {spec_path}")

    # Register this meeting in the entity index for later meetings.
    snippet = ""
    notes = artifacts.get("02_transcript_notes.md", ("", {}))[0]
    for line in notes.splitlines():
        s = line.strip()
        if s.startswith("> ["):
            snippet = s.lstrip("> ").strip()[:220]
            break
    if not snippet:
        brief = artifacts.get("01_meeting_brief.md", ("", {}))[0]
        for line in brief.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("**") and not s.startswith("---"):
                snippet = s[:220]
                break
    register_meeting(date, body, clip_id, entities, snippet,
                     f"artifacts/{date}-{body}-{clip_id}/06_studio_package.md")

    return {
        "date": date,
        "body": body,
        "clip_id": clip_id,
        "video_id": meeting.get("youtube_id"),
        "artifacts": written,
        "notebook_spec": str(spec_path),
        "prior_meetings": [p["date"] for p in prior],
        "watermark_scans": {fname: scan for fname, (_, scan) in artifacts.items()},
    }


def cmd_run(since: str | None, limit: int | None) -> int:
    run_id = datetime.now(timezone.utc).strftime("run-%Y%m%d-%H%M%S")
    RUNS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)

    _log(run_id, f"controller starting — live={LIVE}, since={since}, limit={limit}")

    queue = build_queue(live=LIVE)
    (STATE / "queue.json").write_text(json.dumps(queue, indent=1), encoding="utf-8")

    if since:
        queue = [m for m in queue if m["date"] >= since]
    if limit is not None:
        queue = queue[:limit]

    cp = load_checkpoint()
    done = set(cp.get("completed", []))
    queue = [m for m in queue
             if f"{m['date']}-{m['body']}-{m['clip_id']}" not in done]
    _log(run_id, f"queue: {len(queue)} meetings to process (skipping {len(done)} completed)")

    adapter = NotebookLMAdapter(run_id, live=LIVE)

    results = []
    failures = []
    for i, meeting in enumerate(queue, 1):
        key = f"{meeting['date']}-{meeting['body']}-{meeting['clip_id']}"
        _log(run_id, f"[{i}/{len(queue)}] {key} — {meeting.get('youtube_id') or 'no-yt'}")
        try:
            result = process_meeting(meeting, adapter, run_id)
            results.append(result)
            cp.setdefault("completed", []).append(key)
            save_checkpoint(cp)
        except Exception as exc:  # keep the batch alive
            _log(run_id, f"FAIL {key}: {exc}")
            failures.append({"key": key, "error": str(exc)})
            cp.setdefault("failed", []).append({"key": key, "error": str(exc),
                                                "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            save_checkpoint(cp)

    cp["last_run"] = {
        "run_id": run_id,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "processed": len(results),
        "failures": len(failures),
        "live": LIVE,
    }
    save_checkpoint(cp)

    report = {
        "run_id": run_id,
        "at": cp["last_run"]["at"],
        "queue_total": len(build_queue(live=LIVE)),
        "processed": len(results),
        "failures": len(failures),
        "live": LIVE,
        "artifacts_root": str(ARTIFACTS),
        "results": results,
        "failures": failures,
    }
    (RUNS / f"{run_id}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (STATE / "last_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

    _log(run_id, f"done — processed {len(results)}, failures {len(failures)}")
    print(json.dumps({"run_id": run_id, "processed": len(results),
                      "failures": len(failures), "report": f"runs/{run_id}.json"},
                     indent=1))
    return 0 if not failures else 1


def cmd_status() -> int:
    cp = load_checkpoint()
    queue = build_queue(live=LIVE)
    done = set(cp.get("completed", []))
    remaining = [m for m in queue
                 if f"{m['date']}-{m['body']}-{m['clip_id']}" not in done]
    print(json.dumps({
        "live": LIVE,
        "queue_total": len(queue),
        "completed": len(done),
        "remaining": len(remaining),
        "failed": len(cp.get("failed", [])),
        "next_oldest": remaining[0] if remaining else None,
        "last_run": cp.get("last_run"),
        "checkpoint": str(CHECKPOINT),
    }, indent=1))
    return 0


def cmd_report() -> int:
    path = STATE / "last_report.json"
    if not path.exists():
        print("no report yet — run `controller.py run` first")
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def cmd_inventory() -> int:
    queue = build_queue(live=LIVE)
    for m in queue:
        yt = m.get("youtube_id") or "no-yt"
        print(f"{m['date']}  {m['body']:32s}  clip={m['clip_id']:>4s}  yt={yt}")
    print(f"--- {len(queue)} meetings (oldest -> newest)")
    return 0


def cmd_refresh(argv=None) -> int:
    """Refresh the manifest from all connected repos / public sources, then
    rebuild the controller queue so meetings through 2026-11-04 are included."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Refresh the Cheyenne meeting manifest to current data")
    parser.add_argument("--queue-only", action="store_true",
                        help="rebuild the queue from existing files only")
    # argv is passed in by main(); when None, default to empty so we don't
    # re-read sys.argv (which still contains the "refresh" token).
    if argv is None:
        argv = []
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="NotebookLM controller — full Cheyenne meeting archive")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="process the queue oldest -> newest")
    p_run.add_argument("--since", default=None, help="ISO date, process meetings on/after this date")
    p_run.add_argument("--limit", type=int, default=None, help="max meetings to process")

    sub.add_parser("status", help="show queue/checkpoint state")
    sub.add_parser("report", help="print the last run report")
    sub.add_parser("inventory", help="print the meeting queue oldest -> newest")
    p_refresh = sub.add_parser("refresh", help="refresh manifest from public sources, then rebuild queue")
    p_refresh.add_argument("--queue-only", action="store_true",
                           help="rebuild the queue from existing files only")

    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args.since, args.limit)
    if args.command == "status":
        return cmd_status()
    if args.command == "report":
        return cmd_report()
    if args.command == "inventory":
        return cmd_inventory()
    if args.command == "refresh":
        return cmd_refresh(["--queue-only"] if args.queue_only else [])
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
