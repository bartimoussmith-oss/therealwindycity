import csv, gzip, hashlib, json, re
from collections import defaultdict
from pathlib import Path

ROOT = Path("source")
CATALOG = Path("catalog/cheyenne-2026-transcripts/meetings.json")
OUT = Path("asr-reconciliation")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def records(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("meetings", "records", "items", "data"):
            if isinstance(obj.get(key), list):
                return obj[key]
        if obj and all(isinstance(v, dict) for v in obj.values()):
            return list(obj.values())
    raise ValueError("Unsupported master schema; refusing to claim zero coverage")

def video_id(row):
    value = str(row.get("youtube_id") or row.get("video_id") or "")
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    for key in ("url", "source_url", "video_url", "youtube_url"):
        match = re.search(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([A-Za-z0-9_-]{11})", str(row.get(key) or ""))
        if match:
            return match[1]
    return ""

def body(value):
    text = re.sub(r"[^a-z]+", " ", str(value).lower()).strip()
    for name in ("city council", "finance committee", "public services committee", "planning commission", "board of adjustment", "historic preservation board", "urban renewal authority", "work session"):
        if name in text:
            return name
    return ""

def identity(row):
    date = str(row.get("date") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return None
    name = body(row.get("body") or row.get("category") or row.get("title"))
    return (date, name) if name else None

def text_of(row):
    turns = row.get("turns") or []
    return "\n".join(str(t.get("text") or "") for t in turns if isinstance(t, dict)).strip() or str(row.get("raw_text") or row.get("text") or "").strip()

def reconcile(catalog, indexed):
    by_video, by_day = defaultdict(list), defaultdict(list)
    for row in indexed:
        if row["youtube_id"]:
            by_video[row["youtube_id"]].append(row)
        if row["date_body"]:
            by_day[tuple(row["date_body"])].append(row)
    output = []
    for entry in catalog:
        row = dict(entry)
        exact = by_video.get(video_id(entry), []) if video_id(entry) else []
        candidates = by_day.get(identity(entry), []) if identity(entry) else []
        row["master_exact_id_matches"] = [r["text_sha256"] for r in exact]
        row["master_date_body_candidates"] = sorted(set(r["text_sha256"] for r in candidates))
        if exact:
            row["reconciliation_status"] = "existing_text_exact_video_id"
        elif entry.get("file"):
            path = CATALOG.parent / entry["file"]
            row["reconciliation_status"] = "existing_catalog_text" if path.is_file() and path.stat().st_size else "broken_catalog_locator"
        elif candidates:
            row["reconciliation_status"] = "review_date_body_candidates"
        elif video_id(entry):
            row["reconciliation_status"] = "not_found_in_checked_inputs"
        else:
            row["reconciliation_status"] = "no_recording_id_in_catalog"
        row["new_asr_authorized"] = False
        output.append(row)
    return output

def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "texts").mkdir(exist_ok=True)
    inventory, inputs, failures = [], [], []
    paths = sorted((ROOT / "drive-import").glob("master_meetings_database*.json.gz"))
    if not paths:
        raise FileNotFoundError("Master gzip files absent; reconciliation blocked")
    for path in paths:
        try:
            with gzip.open(path, "rb") as handle:
                raw = handle.read(250_000_001)
            if len(raw) > 250_000_000:
                raise ValueError("Master exceeds configured decompressed-size limit")
            data = records(json.loads(raw))
            inputs.append({"path": str(path), "raw_sha256": sha(raw), "records": len(data)})
            for position, row in enumerate(data):
                if not isinstance(row, dict):
                    raise ValueError("Non-object master record")
                text = text_of(row)
                if not text:
                    continue
                digest = sha(text.encode("utf-8"))
                target = OUT / "texts" / (digest + ".txt")
                if not target.exists():
                    target.write_text(text, encoding="utf-8")
                inventory.append({"source": str(path), "position": position, "record_id": str(row.get("id") or ""), "title": str(row.get("title") or ""), "youtube_id": video_id(row), "date_body": identity(row), "text_sha256": digest, "characters": len(text)})
        except Exception as exc:
            failures.append({"path": str(path), "error": type(exc).__name__ + ": " + str(exc)})
    if not inventory:
        raise ValueError("No usable transcript text; do not interpret as an empty archive")
    catalog_bytes = CATALOG.read_bytes()
    catalog = records(json.loads(catalog_bytes))
    result = reconcile(catalog, inventory)
    counts = defaultdict(int)
    for row in result:
        counts[row["reconciliation_status"]] += 1
    summary = {"scope": "Checked-out public GitHub masters plus 2026 caption catalog only; live Drive and current Promethean runtime NOT checked", "source_commit": Path("source-commit.txt").read_text().strip(), "catalog_commit": Path("catalog-commit.txt").read_text().strip(), "inputs": inputs, "catalog_sha256": sha(catalog_bytes), "master_text_representations": len(inventory), "unique_exact_texts": len({r["text_sha256"] for r in inventory}), "catalog_entries": len(result), "status_counts": dict(counts), "failures": failures, "complete": not failures, "limitations": ["Exact text deduplication does not establish distinct meetings or source independence", "Date/body candidates are never auto-merged; multipart and same-day meetings require review", "Transcript text existence does not establish full audio coverage or correct attribution", "Missing here is not proof new ASR is needed", "Original archives and catalogs were not modified"]}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT / "reconciled_catalog.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with (OUT / "transcript_inventory.jsonl").open("w", encoding="utf-8") as handle:
        for row in inventory:
            handle.write(json.dumps(row) + "\n")
    with (OUT / "coverage.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "body", "youtube_id", "status", "exact_matches", "date_body_candidates"])
        for row in result:
            writer.writerow([row.get("date"), row.get("body"), row.get("youtube_id"), row["reconciliation_status"], len(row["master_exact_id_matches"]), len(row["master_date_body_candidates"])])
    manifest = []
    for path in sorted(OUT.rglob("*")):
        if path.is_file():
            manifest.append(sha(path.read_bytes()) + "  " + str(path.relative_to(OUT)))
    (OUT / "SHA256SUMS").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if failures:
        raise RuntimeError("Partial reconciliation: inspect failures in summary.json")

if __name__ == "__main__":
    main()
