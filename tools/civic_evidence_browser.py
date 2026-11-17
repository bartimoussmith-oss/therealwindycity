"""Bounded, read-only evidence candidates; no model, network or publication."""
import hashlib
import re
from pathlib import Path

RULES = {
    "Procurement language": r"\b(?:sole[ -]source|single[ -]source|competitive bidding|bid waiver)\b",
    "Notice language": r"\b(?:public notice|notice requirement|notice of hearing)\b",
    "Land-use language": r"\b(?:annexation|contiguity|rezoning|zoning change)\b",
    "Inspection language": r"\b(?:inspection warrant|administrative warrant|consent to inspect)\b",
}

def inspect_text(path, raw):
    text = raw.decode("utf-8", errors="replace")
    rows = []
    for label, pattern in RULES.items():
        match = re.search(pattern, text, flags=re.I)
        if match:
            start, end = max(0, match.start()-180), min(len(text), match.end()+320)
            rows.append({"path": path, "category": label, "matched_term": match.group(),
                         "start": start, "end": end, "quote": text[start:end],
                         "raw_sha256": hashlib.sha256(raw).hexdigest(),
                         "state": "keyword_candidate_unreviewed", "publication_allowed": False})
    return text, rows

def scan(root, limit=300, max_bytes=1000000):
    root = Path(root).resolve()
    corpus = root / "pipeline" / "corpus"
    result = {"files_discovered": 0, "files_scanned": 0, "files_skipped": 0,
              "limit": limit, "candidates": [], "errors": [], "truncated": False}
    if not corpus.is_dir():
        result["errors"].append("Repository corpus is unavailable")
        return result
    files = sorted(p for p in corpus.rglob("*") if p.suffix.lower() in {".txt", ".md"} and p.is_file())
    result["files_discovered"] = len(files)
    result["truncated"] = len(files) > limit
    for path in files[:limit]:
        rel = path.relative_to(root).as_posix()
        try:
            if not path.resolve().is_relative_to(corpus.resolve()) or path.stat().st_size > max_bytes:
                result["files_skipped"] += 1
                continue
            raw = path.read_bytes()
            if not raw.strip():
                result["files_skipped"] += 1
                continue
            _, rows = inspect_text(rel, raw)
            result["files_scanned"] += 1
            result["candidates"].extend(rows)
        except OSError:
            result["errors"].append("Could not read " + rel)
    return result
