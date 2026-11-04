#!/usr/bin/env python3
"""
notebooklm_adapter.py — Live driver for NotebookLM via the unofficial
``notebooklm-py`` client (teng-lin/notebooklm-py, PyPI), with a Playwright
browser-automation fallback.

NotebookLM has no official public API. ``notebooklm-py`` reverse-engineers
Google's internal batchexecute / Android gRPC endpoints to give full
programmatic control:

  * create one notebook per meeting
  * add sources: YouTube URL, verbatim transcript file, agenda/minutes URLs
  * generate Audio Overview, Briefing Doc, Study Guide, Quiz, Mind Map, etc.
  + download every generated artifact locally

Authentication is via your own Google account (headless cookie storage or
interactive sign-in). Credentials never touch this repo.

This adapter runs in SIMULATION mode by default (no network to Google, no
browser): it writes the notebook spec (`state/nb-<clip_id>.json`) for every
meeting so you can recreate the notebooks manually, or run live later with
``NOTEBOOKLM_LIVE=1`` on a machine that can reach google.com.

Install for live mode:
    pip install "notebooklm-py[browser]"
    notebooklm login          # first run: signs into your Google account
    NOTEBOOKLM_LIVE=1 python3 notebooklm_controller/controller.py run
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "notebooklm_controller" / "state"
RUNS = ROOT / "notebooklm_controller" / "runs"

NOTEBOOKLM_INSTRUCTIONS = (
    "You are analyzing a City of Cheyenne public meeting. Sources: the "
    "YouTube video, its verbatim transcript, and the agenda/supporting "
    "documents. Answer using ONLY the uploaded sources. Give verbatim quotes "
    "with timestamps, never invent meetings or quotes, and mark anything not "
    "in the sources as 'not on the record'."
)

ARTIFACT_KINDS = ("audio_overview", "briefing_doc", "study_guide", "quiz")


class NotebookLMAdapter:
    def __init__(self, run_id: str, live: bool = False, headless: bool = True):
        self.run_id = run_id
        self.live = live
        self.headless = headless
        self.log_dir = RUNS / run_id
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.invocation_log = self.log_dir / "notebooklm_invocations.jsonl"
        if self.live:
            self._check_live_deps()
            print("[notebooklm_adapter] LIVE mode — notebooklm-py client")
        else:
            print("[notebooklm_adapter] simulation mode — writing notebook "
                  "specs locally; no browser, no Google account involved")

    def _check_live_deps(self) -> None:
        try:
            import notebooklm  # type: ignore  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "--live requires notebooklm-py: pip install 'notebooklm-py[browser]' "
                "then run 'notebooklm login' once to authenticate your Google account"
            ) from exc

    # ------------------------------------------------------------------ spec
    def notebook_for_meeting(self, meeting: dict, artifact_kinds: tuple = ARTIFACT_KINDS,
                             context_sources: list | None = None) -> dict:
        sources = []
        if meeting.get("youtube_url"):
            sources.append({
                "kind": "youtube",
                "url": meeting["youtube_url"],
                "title": meeting["title"],
                "note": "NotebookLM ingests YouTube URLs natively as a source.",
            })

        # VERBATIM TRANSCRIPT — added ONLY when a verbatim transcript exists
        # (2026 meetings via corpus_yt). Never substituted with minutes.
        if meeting.get("has_verbatim_transcript") and meeting.get("transcript_path"):
            sources.append({
                "kind": "file",
                "path": meeting["transcript_path"],
                "title": f"Verbatim transcript — {meeting['title']}",
                "note": "Verbatim YouTube captions (machine mirror of YouTube captions). "
                        "Word-for-word record with timestamps.",
                "source_type": "verbatim_transcript",
            })

        # SUMMARIZED MINUTES — added as a SEPARATE source, never a substitute
        # for transcript. Available 2008-2026.
        if meeting.get("minutes_path"):
            sources.append({
                "kind": "file",
                "path": meeting["minutes_path"],
                "title": f"Summarized minutes — {meeting['title']}",
                "note": "Granicus summarized minutes — NOT verbatim, no timestamps. "
                        "Official record summary only.",
                "source_type": "summarized_minutes",
            })

        if meeting.get("agenda_url"):
            sources.append({
                "kind": "url",
                "url": meeting["agenda_url"],
                "title": f"Agenda — {meeting['title']}",
                "note": "Granicus agenda viewer page.",
            })
        if meeting.get("minutes_url"):
            sources.append({
                "kind": "url",
                "url": meeting["minutes_url"],
                "title": f"Minutes viewer — {meeting['title']}",
                "note": "Granicus minutes viewer page.",
            })

        # every supporting document harvested from the agenda page
        for d in meeting.get("supporting_docs", []):
            if not d.get("url"):
                continue  # skip malformed / empty entries
            if d.get("kind") == "agenda":
                continue  # already added above as agenda_url
            sources.append({
                "kind": d.get("kind", "url"),
                "url": d.get("url", ""),
                "title": f"{d.get('label', 'supporting document')} — {meeting['title']}",
                "note": (d.get("local") or "") + (" [saved locally]" if d.get("local") else " [fetch from Granicus]"),
                "local": d.get("local"),
                "fetched": d.get("fetched", False),
            })

        # prior-meeting context sources (converted studio packages) — this is how
        # each notebook carries forward the historical record into the next one.
        for cs in (context_sources or []):
            sources.append({
                "kind": "context_source",
                "url": None,
                "title": cs["title"],
                "content": cs.get("content"),   # inline text source
                "local": cs.get("local"),
                "note": cs["note"],
                "date": cs["date"],
                "body": cs["body"],
            })

        return {
            "notebook_id": f"nb-{meeting['date'].replace('-', '')}-{meeting['clip_id']}",
            "title": f"City of Cheyenne — {meeting['title']}",
            "date": meeting["date"],
            "body": meeting["body"],
            "clip_id": meeting["clip_id"],
            "instructions": NOTEBOOKLM_INSTRUCTIONS,
            "sources": sources,
            "generate": list(artifact_kinds),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "controller": "notebooklm_controller / notebooklm-py (unofficial client)",
        }

    def write_spec(self, notebook_spec: dict) -> Path:
        STATE.mkdir(parents=True, exist_ok=True)
        dest = STATE / f"{notebook_spec['notebook_id']}.json"
        dest.write_text(json.dumps(notebook_spec, indent=1), encoding="utf-8")
        self._log({"op": "write_spec", "notebook_id": notebook_spec["notebook_id"],
                   "path": str(dest)})
        return dest

    # ------------------------------------------------------------------ live
    def run_live(self, notebook_spec: dict) -> dict:
        """Create the notebook in NotebookLM, add sources, generate +
        download artifacts. Requires network + authenticated notebooklm-py."""
        import asyncio
        return asyncio.run(self._drive_live(notebook_spec))

    async def _drive_live(self, notebook_spec: dict) -> dict:
        from notebooklm import NotebookLMClient  # type: ignore

        results: dict[str, str] = {}
        async with NotebookLMClient.from_storage() as client:
            nb = await client.notebooks.create(notebook_spec["title"])
            nb_id = nb.id

            for src in notebook_spec["sources"]:
                if src["kind"] == "youtube":
                    await client.sources.add_url(nb_id, src["url"], wait=True)
                elif src["kind"] == "file":
                    await client.sources.add_file(nb_id, src["path"], wait=True)
                elif src["kind"] == "url":
                    await client.sources.add_url(nb_id, src["url"], wait=True)

            for kind in notebook_spec["generate"]:
                if kind == "audio_overview":
                    status = await client.artifacts.generate_audio(nb_id)
                elif kind == "briefing_doc":
                    status = await client.artifacts.generate_report(nb_id,
                                                                    format="briefing-doc")
                elif kind == "study_guide":
                    status = await client.artifacts.generate_report(nb_id,
                                                                    format="study-guide")
                elif kind == "quiz":
                    status = await client.artifacts.generate_quiz(nb_id)
                else:
                    continue
                await client.artifacts.wait_for_completion(nb_id, status.task_id)
                out = self.log_dir / f"{notebook_spec['notebook_id']}_{kind}"
                if kind == "audio_overview":
                    await client.artifacts.download_audio(nb_id, f"{out}.m4a")
                elif kind in ("briefing_doc", "study_guide"):
                    await client.artifacts.download_report(nb_id, f"{out}.md",
                                                           output_format="markdown")
                elif kind == "quiz":
                    await client.artifacts.download_quiz(nb_id, f"{out}.json")
                results[kind] = str(out)
        self._log({"op": "run_live", "notebook_id": notebook_spec["notebook_id"],
                   "artifacts": results})
        return results

    # ------------------------------------------------------------------ log
    def _log(self, entry: dict) -> None:
        entry["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.invocation_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
