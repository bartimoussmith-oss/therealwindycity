"""Read-only, allowlisted record index. No network or database writes."""
import hashlib
import re
from pathlib import Path
from urllib.parse import quote

ROOTS = ("pipeline/corpus", "pipeline/corpus_clean", "pipeline/corpus_yt", "ai-record-ocr")
RULES = (("Ordinance", r"\b(?:ordinance|ord\.?)[\s#:–-]*(?:no\.?\s*)?(\d{3,5})\b"),
         ("Resolution", r"\bresolution[\s#:–-]*(?:no\.?\s*)?(\d{2,4}[-–]\d{1,4})\b"),
         ("Parcel", r"\bparcel(?:\s+id)?[\s#:–-]*([\d-]{8,25})\b"))

def identifiers(text):
    found = {}
    for kind, pattern in RULES:
        for m in re.finditer(pattern, text, re.I):
            key = kind + " " + m[1].replace("–", "-")
            if key not in found:
                found[key] = {"offset": m.start(), "excerpt": text[max(0, m.start()-140):m.end()+240]}
    return found

def manifest(root):
    root = Path(root).resolve()
    files = []
    for folder in ROOTS:
        base = root / folder
        if not base.is_dir() or base.is_symlink():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_symlink() or not p.is_file() or p.suffix.lower() not in (".txt", ".md", ".vtt", ".srt"):
                continue
            if not p.resolve().is_relative_to(base.resolve()):
                continue
            relative = p.relative_to(root).as_posix()
            if any(x in relative.lower() for x in ("arrest", "keyring", "name_key", "access_ledger")):
                continue
            stat = p.stat()
            files.append((relative, stat.st_size, stat.st_mtime_ns))
    return tuple(files)

def build_index(root, inventory, revision="main", max_bytes=3_000_000):
    root = Path(root).resolve()
    records, skipped, seen = [], [], set()
    allowed = {entry[0] for entry in manifest(root)}
    for relative, size, _ in inventory:
        if relative not in allowed:
            skipped.append({"path": relative, "reason": "Outside source allowlist"})
            continue
        if size > max_bytes:
            skipped.append({"path": relative, "reason": "File exceeds 3 MB text limit"})
            continue
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            skipped.append({"path": relative, "reason": str(exc)})
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in seen:
            skipped.append({"path": relative, "reason": "Exact text duplicate"})
            continue
        seen.add(digest)
        date = re.search(r"20\d{2}-\d{2}-\d{2}", relative)
        records.append({"id": relative, "title": Path(relative).name, "text": text,
                        "date": date[0] if date else "", "sha256": digest,
                        "identifiers": identifiers(text),
                        "url": "https://github.com/bartimoussmith-oss/therealwindycity/blob/" + quote(revision, safe="") + "/" + quote(relative, safe="/")})
    return {"records": records, "discovered": len(inventory), "skipped": skipped,
            "revision": revision, "allowlist": ROOTS}

def related(records, focus):
    keys = set(focus["identifiers"])
    return [(record, sorted(keys.intersection(record["identifiers"])))
            for record in records if record["id"] != focus["id"] and keys.intersection(record["identifiers"])]
