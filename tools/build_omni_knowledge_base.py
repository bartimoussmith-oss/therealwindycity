#!/usr/bin/env python3
"""build_omni_knowledge_base.py — match harvested YouTube transcripts to
harvested agenda/ordinance documents and emit an AI-readable knowledge base.

Inputs (read from --input-dir, default: output/):
  Cheyenne_Omni_Corpus_Shard_*.md      verbatim YouTube transcripts, written
                                        by tools/headless_transcript_harvester.py.
                                        Each record: RECORDING_TITLE / MEETING_DATE
                                        / SOURCE_URL / TRANSCRIPT.
  Cheyenne_Municipal_Shard_*.md        agenda/ordinance/resolution documents
                                        scraped from cheyennecity.org. Each
                                        record: MUNICIPAL_RECORD / SOURCE_URL /
                                        HARVESTED_AT / CONTENT.

Why matching is hard: most of these document URLs are opaque Granicus
DocumentViewer hashes (cheyenne_<md5>.pdf) with no date in the filename —
only ~9% carry a filename date. So the match key comes from the date stated
INSIDE the document text itself (agendas/ordinances open with a line like
"... June 23, 2023 ..."), not the URL. That is inherently less certain than
an exact ID match, so every match is tagged with how it was made, and every
document assigns to the right meeting on text content, not wishful
thinking.

Outputs (written under --out-dir, default: pipeline/omni_knowledge_base/):
  meetings.jsonl             one JSON object per harvested meeting: full
                              transcript + every document matched to it.
                              This is the primary AI-readable artifact —
                              newline-delimited JSON, each line self
                              contained, ready for RAG ingestion / grep /
                              jq / pandas.read_json(lines=True).
  unmatched_documents.json   documents with no extractable date, or a date
                              that doesn't correspond to any harvested
                              transcript yet (grows smaller as more of the
                              888-video channel backlog gets transcribed).
  unmatched_transcripts.json transcripts with zero matched documents.
  manifest.json              build stats + how to regenerate.
  README.md                  schema documentation.

Also writes pipeline/corpus_omni/{date}-{kind-slug}-{yt_id}.txt per matched
or unmatched transcript, in the same header convention already used by
pipeline/corpus_yt/ (see engine/corpus_search.py), so the existing
full-text search engine picks these up as a third source
("omni-auto-captions") alongside the official minutes and the
upstream-mirrored verbatim archive.

Stdlib only. Safe to re-run: fully rebuilds from whatever shard files are
currently in --input-dir, nothing is deleted that isn't regenerated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Kept in sync by convention with engine/ordinance_index.py's BODY_KEYWORDS —
# duplicated here rather than imported so this script stays runnable
# standalone (e.g. inside a lightweight Termux checkout with no `engine`
# package on the path).
BODY_KEYWORDS = [
    ("Public Services Committee", "public services committee"),
    ("Finance Committee", "finance committee"),
    ("Planning Commission", "planning commission"),
    ("Board of Adjustment", "board of adjustment"),
    ("Urban Renewal Authority", "urban renewal"),
    ("Historic Preservation Board", "historic preservation"),
    ("Public Hearing", "public hearing"),
    ("Work Session", "work session"),
    ("Governing Body", "governing body"),
    ("City Council", "city council"),
]

MONTHS = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")
CONTENT_DATE_RE = re.compile(
    rf"\b({MONTHS})\s+(\d{{1,2}})\s*,\s*(\d{{4}})\b"
)
FILENAME_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{2})(?:-agenda)?\.pdf", re.IGNORECASE)
MONTH_NUM = {m: i + 1 for i, m in enumerate(
    "January February March April May June July August September "
    "October November December".split())}


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "unknown"


def infer_kind(text: str) -> str | None:
    lowered = text.lower()
    for label, needle in BODY_KEYWORDS:
        if needle in lowered:
            return label
    return None


def infer_doc_date(content: str, source_url: str) -> tuple[str | None, str]:
    """Returns (YYYY-MM-DD or None, how-we-got-it)."""
    m = CONTENT_DATE_RE.search(content[:4000])
    if m:
        month_name, day, year = m.groups()
        try:
            dt = datetime(int(year), MONTH_NUM[month_name], int(day))
            return dt.strftime("%Y-%m-%d"), "content_date"
        except ValueError:
            pass
    m = FILENAME_DATE_RE.search(source_url)
    if m:
        mm, dd, yy = m.groups()
        try:
            dt = datetime(2000 + int(yy), int(mm), int(dd))
            return dt.strftime("%Y-%m-%d"), "filename_date"
        except ValueError:
            pass
    return None, "unknown"


def parse_omni_shards(paths: list[Path]) -> list[dict]:
    records = []
    for p in paths:
        text = p.read_text(encoding="utf-8", errors="replace")
        for block in text.split("\n## RECORDING_TITLE:")[1:]:
            title = block.split("\n", 1)[0].strip()
            rest = block.split("\n", 1)[1] if "\n" in block else ""
            date_m = re.search(r"## MEETING_DATE:\s*(\S+)", rest)
            url_m = re.search(r"## SOURCE_URL:\s*(\S+)", rest)
            transcript_m = re.search(r"## TRANSCRIPT:\n(.*)", rest, re.DOTALL)
            date = date_m.group(1).strip() if date_m else "unknown"
            url = url_m.group(1).strip() if url_m else ""
            transcript = transcript_m.group(1).strip() if transcript_m else ""
            # yt-dlp/our harvester always writes a watch?v= URL
            yt_m = re.search(r"v=([A-Za-z0-9_-]{6,})", url)
            yt_id = yt_m.group(1) if yt_m else hashlib.sha1(title.encode()).hexdigest()[:11]
            # strip trailing shard separator junk
            transcript = re.split(r"\n-{10,}\n?$", transcript)[0].strip()
            kind = infer_kind(title) or "Unknown"
            records.append({
                "youtube_id": yt_id,
                "date": date,
                "kind": kind,
                "title": title,
                "video_url": url,
                "transcript": transcript,
                "transcript_chars": len(transcript),
                "source_shard": p.name,
            })
    return records


def parse_municipal_shards(paths: list[Path]) -> list[dict]:
    records = []
    for p in paths:
        text = p.read_text(encoding="utf-8", errors="replace")
        for block in text.split("\n## MUNICIPAL_RECORD:")[1:]:
            title = block.split("\n", 1)[0].strip()
            rest = block.split("\n", 1)[1] if "\n" in block else ""
            url_m = re.search(r"## SOURCE_URL:\s*(\S+)", rest)
            harvested_m = re.search(r"## HARVESTED_AT:\s*(\S+)", rest)
            content_m = re.search(r"## CONTENT:\n(.*)", rest, re.DOTALL)
            url = url_m.group(1).strip() if url_m else ""
            harvested_at = harvested_m.group(1).strip() if harvested_m else ""
            content = content_m.group(1).strip() if content_m else ""
            content = re.split(r"\n-{10,}\n?$", content)[0].strip()
            date, date_source = infer_doc_date(content, url)
            kind = infer_kind(content[:4000])
            records.append({
                "title": title,
                "source_url": url,
                "harvested_at": harvested_at,
                "content": content,
                "content_chars": len(content),
                "inferred_date": date,
                "date_source": date_source,
                "inferred_kind": kind,
                "source_shard": p.name,
            })
    return records


def build_corpus_omni_file(out_dir: Path, rec: dict) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    kind_slug = slugify(rec["kind"])
    name = f"{rec['date']}-{kind_slug}-{rec['youtube_id']}.txt"
    header = (
        f"MEETING: {rec['kind']} | DATE: {rec['date']} | YT_ID: {rec['youtube_id']}\n"
        f"SOURCE: auto-captions via tools/headless_transcript_harvester.py "
        f"(youtube.com/@TheCityofCheyenne)\n"
        f"VIDEO: {rec['video_url']}\n\n"
    )
    (out_dir / name).write_text(header + rec["transcript"] + "\n", encoding="utf-8")
    return name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input-dir", default=str(ROOT / "output"),
                     help="Directory containing the harvested shard .md files")
    ap.add_argument("--out-dir", default=str(ROOT / "pipeline" / "omni_knowledge_base"),
                     help="Where to write the knowledge base")
    ap.add_argument("--corpus-omni-dir", default=str(ROOT / "pipeline" / "corpus_omni"),
                     help="Where to write per-meeting .txt files for the search engine")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    out_dir = Path(args.out_dir)
    corpus_omni_dir = Path(args.corpus_omni_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    omni_paths = sorted(input_dir.glob("Cheyenne_Omni_Corpus_Shard_*.md"))
    municipal_paths = sorted(input_dir.glob("Cheyenne_Municipal_Shard_*.md"))
    if not omni_paths and not municipal_paths:
        print(f"[!] No shard files found in {input_dir}", file=sys.stderr)
        return 1

    print(f"[*] {len(omni_paths)} transcript shard(s), {len(municipal_paths)} document shard(s)")
    transcripts = parse_omni_shards(omni_paths)
    documents = parse_municipal_shards(municipal_paths)
    print(f"[*] parsed {len(transcripts)} transcripts, {len(documents)} documents")

    by_date: dict[str, list[dict]] = {}
    for t in transcripts:
        by_date.setdefault(t["date"], []).append(t)

    unmatched_documents = []
    matched_doc_count = 0
    for d in documents:
        date = d["inferred_date"]
        if not date or date not in by_date:
            unmatched_documents.append({
                "title": d["title"], "source_url": d["source_url"],
                "inferred_date": date, "date_source": d["date_source"],
                "reason": "no date extracted" if not date else "no transcript for that date (yet)",
            })
            continue
        candidates = by_date[date]
        if len(candidates) > 1 and d["inferred_kind"]:
            kind_matches = [t for t in candidates if t["kind"] == d["inferred_kind"]]
            targets = kind_matches or candidates
            confidence = "date+kind" if kind_matches else "date-only (multiple same-day meetings)"
        else:
            targets = candidates
            confidence = "date-only" if len(candidates) == 1 else "date-only (ambiguous, attached to all)"
        for t in targets:
            t.setdefault("documents", []).append({
                "title": d["title"], "source_url": d["source_url"],
                "harvested_at": d["harvested_at"], "content": d["content"],
                "content_chars": d["content_chars"],
                "match_confidence": confidence, "date_source": d["date_source"],
            })
        matched_doc_count += 1

    # GitHub rejects any single committed file over 100MB, so meetings.jsonl
    # is written as size-capped shards (meetings_part1.jsonl, _part2, ...)
    # instead of one monolithic file once the corpus grows large enough.
    MAX_SHARD_BYTES = 80 * 1024 * 1024  # 80MB safety margin under GitHub's 100MB hard limit
    unmatched_transcripts = []
    meetings_shard_names: list[str] = []
    shard_index = 1
    shard_bytes = 0
    shard_file = None

    def _open_next_shard():
        nonlocal shard_file, shard_index, shard_bytes
        if shard_file is not None:
            shard_file.close()
        name = f"meetings_part{shard_index}.jsonl"
        meetings_shard_names.append(name)
        shard_file = (out_dir / name).open("w", encoding="utf-8")
        shard_bytes = 0
        shard_index += 1

    _open_next_shard()
    for t in transcripts:
        docs = t.pop("documents", [])
        if not docs:
            unmatched_transcripts.append({
                "youtube_id": t["youtube_id"], "date": t["date"], "title": t["title"],
            })
        record = {**t, "documents": docs, "document_count": len(docs)}
        line = json.dumps(record, ensure_ascii=False) + "\n"
        line_bytes = len(line.encode("utf-8"))
        if shard_bytes + line_bytes > MAX_SHARD_BYTES and shard_bytes > 0:
            _open_next_shard()
        shard_file.write(line)
        shard_bytes += line_bytes
        build_corpus_omni_file(corpus_omni_dir, t)
    shard_file.close()

    # single-file name is kept only when everything fits in one shard, so
    # small corpora still get the simple meetings.jsonl path from before
    if len(meetings_shard_names) == 1:
        single = out_dir / meetings_shard_names[0]
        meetings_path = out_dir / "meetings.jsonl"
        single.rename(meetings_path)
        meetings_shard_names = ["meetings.jsonl"]

    (out_dir / "unmatched_documents.json").write_text(
        json.dumps(unmatched_documents, indent=1, ensure_ascii=False), encoding="utf-8")
    (out_dir / "unmatched_transcripts.json").write_text(
        json.dumps(unmatched_transcripts, indent=1, ensure_ascii=False), encoding="utf-8")

    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_dir": str(input_dir),
        "transcript_shards": [p.name for p in omni_paths],
        "document_shards": [p.name for p in municipal_paths],
        "meetings_files": meetings_shard_names,
        "total_transcripts": len(transcripts),
        "total_documents": len(documents),
        "documents_matched": matched_doc_count,
        "documents_unmatched": len(unmatched_documents),
        "transcripts_with_no_documents": len(unmatched_transcripts),
        "note": (
            "Snapshot build. Re-run this script whenever more "
            "Cheyenne_Omni_Corpus_Shard_*.md / Cheyenne_Municipal_Shard_*.md "
            "files land in --input-dir to extend it — matching recomputes "
            "from scratch each run, it does not need the old output."
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    readme = f"""# Cheyenne Omni Knowledge Base

Auto-generated, AI-readable corpus matching City of Cheyenne YouTube meeting
transcripts to the agenda/ordinance/resolution documents for that same
meeting. Built by `tools/build_omni_knowledge_base.py` — re-run it any time
more shard files are harvested; it fully rebuilds from source each time.

## Files

- **meetings.jsonl** (or **meetings_part1.jsonl, meetings_part2.jsonl, ...**
  once the corpus is large) — the primary artifact. One JSON object per
  line, one line per harvested meeting. GitHub rejects any single committed
  file over 100MB, so once the combined output would exceed that this
  script automatically splits it into size-capped `meetings_partN.jsonl`
  shards instead (see `manifest.json` → `meetings_files` for the exact list
  to load — concatenating their lines reconstructs the full dataset).
  Load with `pandas.read_json(path, lines=True)` per shard, or stream
  line-by-line in any language. Fields per record:
  - `youtube_id`, `date` (YYYY-MM-DD), `kind` (meeting type, best-effort),
    `title`, `video_url`, `transcript` (full auto-caption text),
    `transcript_chars`, `source_shard`
  - `documents`: list of agenda/ordinance/resolution documents matched to
    this meeting, each with `title`, `source_url`, `harvested_at`,
    `content` (full extracted text), `content_chars`, `match_confidence`,
    `date_source`
  - `document_count`: convenience count of `documents`
- **unmatched_documents.json** — documents that could not be tied to any
  harvested transcript yet, with the reason (no date could be extracted
  from the text/filename, or a date was found but no transcript for that
  date has been harvested yet). Re-check this after harvesting more videos.
- **unmatched_transcripts.json** — transcripts with zero matched documents.
- **manifest.json** — build stats and provenance.

## Matching method (and its honest limits)

Most of these documents come from Granicus `DocumentViewer.php` URLs with
opaque hashed filenames (`cheyenne_<md5>.pdf`) — only a small minority carry
a date in the filename. So the match key is **the date stated inside the
document's own text** (agendas/ordinances open with a line like
"... June 23, 2023 ..."), extracted with a regex over the first ~4000
characters. Every document and every match records how its date was
obtained (`content_date`, `filename_date`, or `unknown`) and the resulting
`match_confidence` (`date+kind`, `date-only`, or `date-only (ambiguous,
attached to all)` when multiple distinct meetings share the same date and
the document's meeting type couldn't be determined) — this is a heuristic
match, not an authoritative ID join, and is surfaced as such rather than
asserted as certain.

## Also feeds the site's existing search engine

Every transcript is additionally written to `pipeline/corpus_omni/` in the
same header convention as `pipeline/corpus_yt/` (see
`engine/corpus_search.py`), tagged as source `"omni-auto-captions"`, so it's
full-text searchable alongside the official clerk minutes (`pipeline/corpus/`)
and the curated verbatim mirror (`pipeline/corpus_yt/`) without any separate
tooling.

## Regenerating

```
python3 tools/build_omni_knowledge_base.py \\
    --input-dir output \\
    --out-dir pipeline/omni_knowledge_base \\
    --corpus-omni-dir pipeline/corpus_omni
```

Defaults match the paths above, so a bare `python3 tools/build_omni_knowledge_base.py`
run from the repo root works once `output/Cheyenne_Omni_Corpus_Shard_*.md` and
`output/Cheyenne_Municipal_Shard_*.md` are present (e.g. synced down from the
Drive folder, or run directly on the harvesting device).

## Scope note

This snapshot covers only what has been harvested so far — a fraction of
the ~888 videos on the channel and an even smaller slice of the city's full
agenda/ordinance history. It grows every time the harvester and the
document scraper produce more shard files; nothing about the schema needs
to change as that happens.
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    meetings_desc = ", ".join(meetings_shard_names)
    print(f"[+] wrote {out_dir}/[{meetings_desc}] ({len(transcripts)} meetings)")
    print(f"[+] {matched_doc_count}/{len(documents)} documents matched to a meeting")
    print(f"[+] {len(unmatched_documents)} documents unmatched, {len(unmatched_transcripts)} transcripts with no documents")
    print(f"[+] {len(transcripts)} per-meeting .txt files written to {corpus_omni_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
