#!/usr/bin/env python3
"""build_vector_db.py — chunk the aligned corpus and embed it into Chroma.

Sources (all aligned by clip_id + date):
  * pipeline/corpus_clean/*.clean.txt  — cleaned transcripts (time-stamped)
  * pipeline/corpus/{clip}_*.txt       — minutes text
  * pipeline/docs/<clip>/*             — repo supporting docs (PDF bytes, any ext)
  * --docs-dir documents/clip*_*       — youtube-archive docs layout (optional)
  * youtube-archive/upload_plan.csv    — source URLs for citations (optional)

Chunk metadata (every chunk): clip_id, date, body, source_type, source_file,
source_url, item_ref, page, t_start, t_end. Stable IDs ({clip}:{src}:{n}) so
re-runs upsert instead of duplicating.

Usage (repo root):
  pip install -r rag/requirements-rag.txt
  python rag/build_vector_db.py --clips 1124 1103 1093 1071 --persist rag/vectordb_sample
  python rag/build_vector_db.py --all --persist rag/vectordb   # full run (gitignored)

Also writes chunks.jsonl next to the persist dir (portable, git-friendly).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from text_extract import (MINUTES_HDR, agenda_items, cached_pdf_pages,
                          file_to_text, is_pdf)

ROOT = Path(__file__).resolve().parent.parent
RAG = ROOT / "rag"
CLEAN = ROOT / "pipeline" / "corpus_clean"
TEXT_CACHE = RAG / "text_cache"

SEGMENT = re.compile(r"\[(?P<t0>\d{2}:\d{2}:\d{2})-(?P<t1>\d{2}:\d{2}:\d{2})\]\s*(?P<text>.*)")


def to_sec(ts: str) -> int:
    h, m, s = (int(x) for x in ts.split(":"))
    return h * 3600 + m * 60 + s


def load_citations() -> dict[str, str]:
    """clip_id -> granicus player URL (for source_url metadata)."""
    out = {}
    for cand in [ROOT / "youtube-archive" / "catalog_granicus.csv",
                 ROOT / "youtube-archive" / "catalog_granicus.json"]:
        if cand.suffix == ".csv" and cand.exists():
            with open(cand, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r.get("clip_id"):
                        out[r["clip_id"]] = r.get("player_url", "")
            break
        if cand.suffix == ".json" and cand.exists():
            for r in json.loads(cand.read_text(encoding="utf-8")):
                out[str(r.get("clip_id"))] = r.get("player_url", "")
            break
    return out


def load_clip_dates() -> dict[str, str]:
    """clip_id -> date_iso (fills dates for repo-layout docs/<clip>/ files)."""
    out: dict[str, str] = {}
    for cand in [ROOT / "youtube-archive" / "catalog_granicus.csv",
                 ROOT / "youtube-archive" / "catalog_granicus.json",
                 ROOT / "pipeline" / "corpus"]:
        if cand.suffix == ".csv" and cand.exists():
            import csv as _csv
            with open(cand, newline="", encoding="utf-8") as f:
                for r in _csv.DictReader(f):
                    if r.get("clip_id") and r.get("date_iso"):
                        out[r["clip_id"]] = r["date_iso"]
            break
        if cand.suffix == ".json" and cand.exists():
            for r in json.loads(cand.read_text(encoding="utf-8")):
                out[str(r.get("clip_id"))] = r.get("date_iso", "")
            break
    return out


def clip_date_from_stem(stem: str) -> tuple[str, str]:
    m = re.match(r"(?P<clip>\d+)_(?P<date>\d{4}-\d{2}-\d{2})", stem)
    if m:
        return m.group("clip"), m.group("date")
    return "", ""


def chunk_text(text: str, target: int = 900, overlap: int = 120) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n{2,}|\n", text) if p.strip()]
    chunks, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 <= target + overlap:
            buf = (buf + "\n" + p).strip()
        else:
            if buf:
                chunks.append(buf)
            buf = p if len(p) <= target + overlap else p[:target]
            while len(p) > target + overlap:  # very long paragraph: hard split
                chunks.append(p[:target])
                p = p[target - overlap:]
            buf = p
    if buf:
        chunks.append(buf)
    return [c for c in chunks if len(c) >= 60]


def corpus_minutes_clips() -> set[str]:
    """Clip IDs whose minutes already live in pipeline/corpus/*.txt."""
    out = set()
    for fp in (ROOT / "pipeline" / "corpus").glob("*.txt"):
        m = MINUTES_HDR.search(fp.read_text(encoding="utf-8", errors="replace")[:600])
        out.add(m.group("clip") if m else fp.stem.split("_")[0])
    return out


_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def _tag(text: str, date: str, stype: str) -> str:
    """Prefix every chunk with date/body/type so date-constrained queries match."""
    month = ""
    try:
        month = _MONTHS[int(date.split("-")[1])] + " "
    except (ValueError, IndexError):
        pass
    return f"[{date} {month}| City Council | {stype}] {text}"


def iter_chunks(clips: set[str] | None, docs_dirs: list[Path], citations: dict,
                max_pages: int = 0, clip_dates: dict | None = None,
                minutes_clips: set[str] | None = None):
    """Yield (chunk_id, text, metadata)."""
    n = 0

    def want(clip: str) -> bool:
        return not clips or clip in clips

    # 1. cleaned transcripts (group ~3 segments per chunk)
    if CLEAN.is_dir():
        for fp in sorted(CLEAN.glob("*.clean.txt")):
            clip, cdate = clip_date_from_stem(fp.stem.replace(".clean", ""))
            if not clip or not want(clip):
                continue
            segs = [m.groupdict() for m in SEGMENT.finditer(
                fp.read_text(encoding="utf-8", errors="replace"))]
            for i in range(0, len(segs), 3):
                grp = segs[i:i + 3]
                text = " ".join(g["text"] for g in grp).strip()
                if len(text) < 60:
                    continue
                n += 1
                yield (f"{clip}:tx:{n:05d}", _tag(text, cdate, "transcript"),
                       {"clip_id": clip, "date": cdate, "body": "City Council",
                        "source_type": "transcript_clean", "source_file": fp.name,
                        "source_url": citations.get(clip, ""),
                        "t_start": to_sec(grp[0]["t0"]), "t_end": to_sec(grp[-1]["t1"]),
                        "item_ref": "", "page": 0})

    # 2. minutes
    for fp in sorted((ROOT / "pipeline" / "corpus").glob("*.txt")):
        text = fp.read_text(encoding="utf-8", errors="replace")
        m = MINUTES_HDR.search(text[:600])
        clip = m.group("clip") if m else fp.stem.split("_")[0]
        cdate = m.group("date") if m else ""
        if not want(clip):
            continue
        body = re.sub(r"^MEETING:.*$", "", text, count=1, flags=re.M).strip()
        for ch in chunk_text(body):
            n += 1
            yield (f"{clip}:min:{n:05d}", _tag(ch, cdate, "minutes"),
                   {"clip_id": clip, "date": cdate, "body": "City Council",
                    "source_type": "minutes", "source_file": fp.name,
                    "source_url": citations.get(clip, ""), "t_start": 0,
                    "t_end": 0, "item_ref": "", "page": 0})

    # 3. supporting docs (both layouts; magic-sniffed)
    for docs_root in docs_dirs:
        if not docs_root.is_dir():
            continue
        for fp in sorted(docs_root.rglob("*")):
            if not fp.is_file() or fp.stat().st_size < 200:
                continue
            # clip + date from parent dir ".../clipNNN_YYYY-MM-DD" or ".../<clip>/"
            clip, cdate = "", ""
            for part in fp.parts:
                m = re.match(r"clip(\d+)_(\d{4}-\d{2}-\d{2})", part)
                if m:
                    clip, cdate = m.group(1), m.group(2)
                    break
            if not clip:
                # repo layout pipeline/docs/<clip>/...
                try:
                    rel = fp.relative_to(docs_root).parts
                    if rel and rel[0].isdigit():
                        clip = rel[0]
                except ValueError:
                    pass
            if not clip or not want(clip):
                continue
            if not cdate and clip_dates:
                cdate = clip_dates.get(clip, "")
            name = fp.name.lower()
            if "minutes" in name and minutes_clips and clip in minutes_clips:
                continue  # corpus/*.txt already carries these minutes; avoid dup chunks
            try:
                if is_pdf(fp):
                    pages = cached_pdf_pages(fp, TEXT_CACHE)
                    if max_pages:
                        pages = pages[:max_pages]
                    for pi, page in enumerate(pages, 1):
                        for ch in chunk_text(page):
                            n += 1
                            yield (f"{clip}:doc:{n:05d}", _tag(ch, cdate, "doc"),
                                   {"clip_id": clip, "date": cdate, "body": "City Council",
                                    "source_type": "minutes" if "minutes" in name else "supporting_doc",
                                    "source_file": f"{fp.parent.name}/{fp.name}",
                                    "source_url": citations.get(clip, ""), "t_start": 0,
                                    "t_end": 0, "item_ref": fp.stem[:80], "page": pi})
                elif name.endswith((".html", ".htm")):
                    raw = fp.read_text(encoding="utf-8", errors="replace")
                    items = agenda_items(raw)
                    if items and "agenda" in name:
                        for it in items:
                            if len(it["title"]) < 20:
                                continue
                            n += 1
                            yield (f"{clip}:ag:{n:05d}",
                                   _tag(f"Agenda item {it['no']}: {it['title']}", cdate, "agenda"),
                                   {"clip_id": clip, "date": cdate, "body": "City Council",
                                    "source_type": "agenda", "source_file": fp.name,
                                    "source_url": citations.get(clip, ""), "t_start": 0,
                                    "t_end": 0, "item_ref": it["no"], "page": 0})
                    else:
                        for ch in chunk_text(file_to_text(fp)):
                            n += 1
                            yield (f"{clip}:doc:{n:05d}", _tag(ch, cdate, "doc"),
                                   {"clip_id": clip, "date": cdate, "body": "City Council",
                                    "source_type": "supporting_doc_html",
                                    "source_file": f"{fp.parent.name}/{fp.name}",
                                    "source_url": citations.get(clip, ""), "t_start": 0,
                                    "t_end": 0, "item_ref": fp.stem[:80], "page": 0})
            except Exception as e:  # noqa: BLE001 — one bad file must not kill the run
                print(f"  skip {fp}: {e}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--persist", default="rag/vectordb")
    ap.add_argument("--docs-dir", action="append", default=[],
                    help="extra docs root (repeatable); repo pipeline/docs always included")
    ap.add_argument("--max-pages", type=int, default=0,
                    help="index only the first N pages per PDF (0 = all). Sample runs: 5")
    ap.add_argument("--batch", type=int, default=100)
    args = ap.parse_args()
    if not args.clips and not args.all:
        ap.error("pass --clips ... or --all")

    import chromadb

    docs_dirs = [ROOT / "pipeline" / "docs"] + [Path(d) for d in args.docs_dir]
    citations = load_citations()
    clip_dates = load_clip_dates()
    persist = Path(args.persist)
    if not persist.is_absolute():
        persist = ROOT / persist
    persist.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(persist))
    col = client.get_or_create_collection(
        "cheyenne_meetings",
        metadata={"description": "Cheyenne council meetings: transcripts+minutes+agendas+docs"})

    clips = set(args.clips) if args.clips else None
    minutes_clips = corpus_minutes_clips()
    batch_ids, batch_docs, batch_meta = [], [], []
    total = 0
    chunks_jsonl = persist / "chunks.jsonl"
    with open(chunks_jsonl, "w", encoding="utf-8") as jf:
        def flush():
            if batch_ids:
                col.upsert(ids=batch_ids, documents=batch_docs, metadatas=batch_meta)
                batch_ids.clear(); batch_docs.clear(); batch_meta.clear()

        for cid, text, meta in iter_chunks(clips, docs_dirs, citations, args.max_pages,
                                           clip_dates, minutes_clips):
            batch_ids.append(cid); batch_docs.append(text); batch_meta.append(meta)
            jf.write(json.dumps({"id": cid, "text": text, "metadata": meta}) + "\n")
            total += 1
            if len(batch_ids) >= args.batch:
                flush()
                print(f"  embedded {total} chunks ...")
        flush()

    print(f"\ndone: {total} chunks -> {persist} (collection count: {col.count()})")
    print(f"chunk manifest: {chunks_jsonl}")


if __name__ == "__main__":
    main()
