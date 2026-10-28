#!/usr/bin/env python3
"""Measure the repository's tracked mass, plan its partition, export bundles.

This tool exists because the working tree carries ~1.27 GB of tracked bytes,
of which ~596 MB is .mp4 video, while the repository's own recorded rule is
"videos stay out of git per repo rule (YouTube + Releases)". The mass is a
standing rule violation rather than a design choice, and it is paid for on
every Actions checkout.

What this tool DOES:
  * measure tracked bytes by class, directory and extension, from git's index;
  * detect duplicate content by SHA-256 across distinct tracked paths;
  * write a partition manifest declaring what belongs in git, in Releases,
    and in Git LFS, with measured bytes for each destination;
  * export release bundles (tar.gz) of the outbound classes, with a SHA-256
    and a byte count recorded per bundle, so an owner can upload them;
  * emit a .gitattributes LFS block covering future additions of those
    extensions, so the mass stops growing even before it is removed;
  * print the exact migration commands, with a before/after byte projection.

What this tool NEVER does:
  * rewrite history, force-push, delete tracked content, or run git rm.
    Already-tracked bytes are only reclaimed by history rewrite or by
    `git rm --cached` plus accepting that history stays large. Both are owner
    decisions, so both are printed and neither is executed. Deleting media
    that this agent did not create is forbidden by READ-FIRST.md.

Stdlib only. Reads the git index; never modifies it.

Example:
  python tools/repo_partition.py --out data/partition --export
  python tools/repo_partition.py --out data/partition --json-only
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Partition classes. Order matters: the first matching rule wins, so the more
# specific rules are listed before the catch-alls. A class is "resident" when
# its bytes should stay in git, and "outbound" when they belong in Releases or
# LFS. The classification is deliberately extension- and path-based only: it
# never opens a document to judge its importance, because a judgement about
# content value is an editorial decision, not a measurement.
CLASSES: tuple[tuple[str, str, frozenset[str], tuple[str, ...]], ...] = (
    # name, residency, extensions, path prefixes
    ("video", "outbound", frozenset({".mp4", ".webm", ".mov", ".mkv", ".avi"}), ()),
    ("audio", "outbound", frozenset({".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac"}), ()),
    ("ml-model", "outbound", frozenset({".onnx", ".pt", ".pth", ".safetensors", ".gguf", ".bin"}),
     ("models/",)),
    ("database", "outbound", frozenset({".db", ".sqlite", ".sqlite3"}), ()),
    ("archive-image", "outbound", frozenset({".zip", ".tar", ".gz", ".tgz", ".7z", ".rar"}), ()),
    ("render", "outbound", frozenset(), ("pipeline/renders/",)),
    ("pdf", "review", frozenset({".pdf"}), ()),
    ("document", "resident", frozenset({".md", ".txt", ".rst", ".vtt", ".srt"}), ()),
    ("structured-data", "review", frozenset({".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml"}), ()),
    ("web-asset", "review", frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css"}), ()),
    ("code", "resident",
     frozenset({".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".sh", ".html", ".ipynb"}), ()),
)

# Extensions that a future .gitattributes should route to LFS. Kept separate
# from CLASSES because the LFS decision is about what must never be committed
# again, which is narrower than what is currently heavy.
LFS_EXTENSIONS = (".mp4", ".webm", ".mov", ".mkv", ".mp3", ".wav", ".m4a",
                  ".onnx", ".pt", ".safetensors", ".db", ".sqlite3", ".zip", ".gz")

# Anything above this many bytes is reported individually even if its class is
# resident, because a large resident file is worth a human look.
LARGE_FILE_THRESHOLD = 5 * 1024 * 1024

# Duplicate reporting floor. The corpus legitimately contains thousands of tiny
# identical text artifacts (per-document silent-edit diff series share boilerplate
# heads), and listing them buries the duplicates that actually waste megabytes.
# Duplicates below this size are still counted in the totals, just not itemised.
DUPLICATE_REPORT_THRESHOLD = 256 * 1024


def run_git(args: list[str]) -> str:
    """Run a git command in the repository root and return stdout.

    Raises rather than returning an empty string on failure, because an empty
    index and a broken git invocation must not produce the same answer.
    """
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:400]}")
    return proc.stdout


def classify(path: str) -> tuple[str, str]:
    """Return (class_name, residency) for a tracked path."""
    lowered = path.lower()
    ext = os.path.splitext(lowered)[1]
    for name, residency, extensions, prefixes in CLASSES:
        if prefixes and any(path.startswith(p) for p in prefixes):
            return name, residency
        if ext in extensions:
            return name, residency
    return "other", "review"


def collect() -> list[dict]:
    """Read the git index and stat every tracked path.

    Uses `git ls-files -s` rather than `git ls-files` alone so that deleted
    but still-indexed entries are visible as missing instead of silently
    dropping out of the measurement.
    """
    out = run_git(["ls-files", "-s", "-z"])
    rows: list[dict] = []
    for entry in out.split("\0"):
        if not entry.strip():
            continue
        # format: <mode> <sha> <stage>\t<path>
        meta, _, path = entry.partition("\t")
        if not path:
            continue
        parts = meta.split()
        if len(parts) < 3:
            continue
        blob_sha = parts[1]
        abs_path = ROOT / path
        try:
            size = abs_path.stat().st_size
            present = True
        except OSError:
            size = 0
            present = False
        cls, residency = classify(path)
        rows.append({
            "path": path,
            "bytes": size,
            "present": present,
            "class": cls,
            "residency": residency,
            "blob_sha": blob_sha,
            "ext": os.path.splitext(path)[1].lower(),
            "top_dir": path.split("/", 1)[0] if "/" in path else ".",
        })
    return rows


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def find_duplicates(rows: list[dict]) -> dict:
    """Group tracked paths by content SHA-256, reporting only real duplicates.

    Two-pass: group by byte length first, then hash only the size-collisions.
    Hashing all 1.27 GB when a handful of sizes collide would be wasteful, and
    hashing nothing would miss duplicates that waste real space.
    """
    by_size: dict[int, list[dict]] = collections.defaultdict(list)
    for row in rows:
        if row["present"] and row["bytes"] > 0:
            by_size[row["bytes"]].append(row)

    groups: list[dict] = []
    for size, candidates in sorted(by_size.items(), key=lambda kv: -kv[0]):
        if len(candidates) < 2:
            continue
        by_hash: dict[str, list[dict]] = collections.defaultdict(list)
        for row in candidates:
            try:
                by_hash[sha256_of(ROOT / row["path"])].append(row)
            except OSError:
                continue
        for digest, members in by_hash.items():
            if len(members) < 2:
                continue
            groups.append({
                "sha256": digest,
                "bytes_each": size,
                "wasted_bytes": size * (len(members) - 1),
                "paths": sorted(m["path"] for m in members),
            })
    groups.sort(key=lambda g: -g["wasted_bytes"])
    # Split rather than filter: the totals must stay truthful about ALL duplicate
    # bytes, while the itemised list stays readable. Reporting only the large ones
    # and summing only the large ones would understate the finding.
    material = [g for g in groups if g["bytes_each"] >= DUPLICATE_REPORT_THRESHOLD]
    minor = [g for g in groups if g["bytes_each"] < DUPLICATE_REPORT_THRESHOLD]
    return {
        "material_groups": material,
        "minor_groups_count": len(minor),
        "minor_wasted_bytes": sum(g["wasted_bytes"] for g in minor),
        "all_groups_count": len(groups),
        "all_wasted_bytes": sum(g["wasted_bytes"] for g in groups),
    }


def summarize(rows: list[dict]) -> dict:
    total = sum(r["bytes"] for r in rows)
    by_class: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    by_dir: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    by_ext: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    by_residency: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    missing = 0
    for r in rows:
        if not r["present"]:
            missing += 1
        for table, key in ((by_class, r["class"]), (by_dir, r["top_dir"]),
                           (by_ext, r["ext"] or "(none)"), (by_residency, r["residency"])):
            table[key]["files"] += 1
            table[key]["bytes"] += r["bytes"]

    def ordered(table: dict) -> list[dict]:
        return [{"key": k, **v} for k, v in sorted(table.items(), key=lambda kv: -kv[1]["bytes"])]

    return {
        "measured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "repository_root": str(ROOT),
        "tracked_files": len(rows),
        "indexed_but_missing": missing,
        "tracked_bytes": total,
        "by_residency": ordered(by_residency),
        "by_class": ordered(by_class),
        "by_top_dir": ordered(by_dir)[:30],
        "by_extension": ordered(by_ext)[:30],
        "large_resident_files": sorted(
            ({"path": r["path"], "bytes": r["bytes"], "class": r["class"]}
             for r in rows if r["residency"] == "resident" and r["bytes"] >= LARGE_FILE_THRESHOLD),
            key=lambda d: -d["bytes"]),
    }


def build_manifest(summary: dict, duplicates: dict, rows: list[dict]) -> dict:
    """Declare the partition: what stays, what leaves, and what needs a human."""
    outbound = [r for r in rows if r["residency"] == "outbound"]
    review = [r for r in rows if r["residency"] == "review"]
    resident_bytes = sum(r["bytes"] for r in rows if r["residency"] == "resident")
    outbound_bytes = sum(r["bytes"] for r in outbound)
    review_bytes = sum(r["bytes"] for r in review)

    by_class_outbound: dict[str, dict] = collections.defaultdict(lambda: {"files": 0, "bytes": 0})
    for r in outbound:
        by_class_outbound[r["class"]]["files"] += 1
        by_class_outbound[r["class"]]["bytes"] += r["bytes"]

    return {
        "schema": "repo-partition-manifest-v1",
        "generated_by": "tools/repo_partition.py",
        "measured_at": summary["measured_at"],
        "totals": {
            "tracked_bytes": summary["tracked_bytes"],
            "tracked_files": summary["tracked_files"],
            "resident_bytes": resident_bytes,
            "outbound_bytes": outbound_bytes,
            "review_bytes": review_bytes,
            "projected_bytes_after_outbound_removed": resident_bytes + review_bytes,
        },
        "note": (
            "projected_bytes_after_outbound_removed describes the WORKING TREE and the "
            "index after an owner-approved migration. It is not a .git size reduction: "
            "already-committed blobs remain in history until history is rewritten, which "
            "READ-FIRST.md forbids an agent from doing. Stated plainly so the number is "
            "never read as a clone-size saving."),
        "outbound_by_class": sorted(
            ({"class": k, **v} for k, v in by_class_outbound.items()),
            key=lambda d: -d["bytes"]),
        "duplicate_content_groups": duplicates["material_groups"],
        "duplicate_report_floor_bytes": DUPLICATE_REPORT_THRESHOLD,
        "duplicate_groups_itemised": len(duplicates["material_groups"]),
        "duplicate_groups_total": duplicates["all_groups_count"],
        "duplicate_wasted_bytes_itemised": sum(
            d["wasted_bytes"] for d in duplicates["material_groups"]),
        "duplicate_wasted_bytes_total": duplicates["all_wasted_bytes"],
        "duplicate_minor_groups_suppressed": duplicates["minor_groups_count"],
        "duplicate_minor_wasted_bytes": duplicates["minor_wasted_bytes"],
        "lfs_extensions": list(LFS_EXTENSIONS),
        "review_required": {
            "files": len(review),
            "bytes": review_bytes,
            "why": (
                "pdf, structured-data and web-asset classes are marked 'review' because "
                "whether a 33 MB JSON or a 104 MB PDF corpus belongs in git depends on "
                "whether an Actions job reads it at build time. That is a dependency "
                "question this tool cannot answer from the index alone."),
        },
    }


def gitattributes_block() -> str:
    lines = ["# Generated by tools/repo_partition.py — route heavy media to LFS.",
             "# Prevents future growth; does not shrink what is already committed."]
    for ext in LFS_EXTENSIONS:
        lines.append(f"*{ext} filter=lfs diff=lfs merge=lfs -text")
    return "\n".join(lines) + "\n"


def export_bundles(rows: list[dict], out_dir: Path) -> list[dict]:
    """Write one tar.gz per outbound class and record its hash and byte count.

    Bundles are the owner's upload path to GitHub Releases. They are written to
    a gitignored output directory, never into the tracked tree.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    by_class: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        if r["residency"] == "outbound" and r["present"]:
            by_class[r["class"]].append(r)

    bundles = []
    for cls, members in sorted(by_class.items(), key=lambda kv: -sum(m["bytes"] for m in kv[1])):
        bundle_path = out_dir / f"{cls}-bundle.tar.gz"
        members.sort(key=lambda m: m["path"])
        with tarfile.open(bundle_path, "w:gz") as tar:
            for m in members:
                tar.add(ROOT / m["path"], arcname=m["path"])
        size = bundle_path.stat().st_size
        bundles.append({
            "class": cls,
            "bundle": str(bundle_path.relative_to(ROOT)),
            "bundle_bytes": size,
            "bundle_sha256": sha256_of(bundle_path),
            "member_files": len(members),
            "member_bytes": sum(m["bytes"] for m in members),
            "paths": [m["path"] for m in members],
        })
    return bundles


def migration_commands(manifest: dict) -> list[str]:
    """Print the exact owner-run migration. Never executed by this tool."""
    cmds = [
        "# 1. Upload the bundles to GitHub Releases (owner; needs a release target):",
        "gh release create media-partition-$(date -u +%Y%m%d) "
        "data/partition/bundles/*.tar.gz --title 'Media partition' "
        "--notes 'Exported by tools/repo_partition.py; see data/partition/manifest.json'",
        "",
        "# 2. Stop future growth (safe, additive, no history change):",
        "cp data/partition/gitattributes-lfs.txt .gitattributes   # merge, do not clobber",
        "git lfs install",
        "",
        "# 3. Untrack the outbound classes WITHOUT deleting the local files:",
        "git rm -r --cached video videos pipeline/renders 2026-09-14-council/civicwatch/models",
        "printf 'video/\\nvideos/\\npipeline/renders/\\n*.onnx\\n' >> .gitignore",
        "git add .gitattributes .gitignore && git commit -m 'partition: untrack media, route to LFS/Releases'",
        "",
        "# WARNING: step 3 removes the files from the NEXT commit onward. The 1.27 GB",
        "# stays in .git history forever. Reclaiming it requires history rewrite:",
        "#   git filter-repo --invert-paths --path video --path videos   # OWNER DECISION",
        "# READ-FIRST.md forbids an agent from doing this: 'Never force-push. Never",
        "# reset or rewrite history.' It also breaks every existing clone and every",
        "# permalink to a media file, including links already published in the app.",
    ]
    return cmds


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/partition", help="output directory (gitignored)")
    ap.add_argument("--export", action="store_true", help="also write tar.gz release bundles")
    ap.add_argument("--json-only", action="store_true", help="print the manifest and exit")
    ap.add_argument("--no-duplicates", action="store_true",
                    help="skip the SHA-256 duplicate scan (faster, less complete)")
    args = ap.parse_args(argv)

    out_dir = (ROOT / args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = collect()
    if not rows:
        print("no tracked files found — is this a git repository?", file=sys.stderr)
        return 2
    summary = summarize(rows)
    duplicates = ({"material_groups": [], "minor_groups_count": 0, "minor_wasted_bytes": 0,
                   "all_groups_count": 0, "all_wasted_bytes": 0}
                  if args.no_duplicates else find_duplicates(rows))
    manifest = build_manifest(summary, duplicates, rows)

    bundles = export_bundles(rows, out_dir / "bundles") if args.export else []
    manifest["bundles"] = bundles

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out_dir / "measurement.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out_dir / "gitattributes-lfs.txt").write_text(gitattributes_block(), encoding="utf-8")
    (out_dir / "MIGRATION.md").write_text(
        "# Media partition migration\n\n"
        "Generated by `tools/repo_partition.py`. Every command below is an OWNER action.\n"
        "Nothing here was executed by the tool that produced it.\n\n```\n"
        + "\n".join(migration_commands(manifest)) + "\n```\n", encoding="utf-8")

    if args.json_only:
        print(json.dumps(manifest, indent=2))
        return 0

    t = manifest["totals"]

    def mb(n: int) -> str:
        return f"{n / (1024 * 1024):,.1f} MiB"

    print(f"tracked files          {t['tracked_files']:,}")
    print(f"tracked bytes          {t['tracked_bytes']:,}  ({mb(t['tracked_bytes'])})")
    print(f"  resident (keep)      {t['resident_bytes']:,}  ({mb(t['resident_bytes'])})")
    print(f"  review  (human call) {t['review_bytes']:,}  ({mb(t['review_bytes'])})")
    print(f"  outbound (Releases)  {t['outbound_bytes']:,}  ({mb(t['outbound_bytes'])})")
    print(f"projected tree after   {t['projected_bytes_after_outbound_removed']:,} "
          f"({mb(t['projected_bytes_after_outbound_removed'])})  — .git history unchanged")
    print()
    print("outbound by class:")
    for c in manifest["outbound_by_class"]:
        print(f"  {c['class']:16s} {c['files']:5d} files  {mb(c['bytes']):>12s}")
    print()
    print(f"duplicate content: {manifest['duplicate_groups_total']} groups, "
          f"{mb(manifest['duplicate_wasted_bytes_total'])} wasted in total")
    print(f"  itemised (>={mb(DUPLICATE_REPORT_THRESHOLD)} each): "
          f"{manifest['duplicate_groups_itemised']} groups, "
          f"{mb(manifest['duplicate_wasted_bytes_itemised'])}")
    print(f"  suppressed as immaterial: {manifest['duplicate_minor_groups_suppressed']} groups, "
          f"{mb(manifest['duplicate_minor_wasted_bytes'])}")
    for d in manifest["duplicate_content_groups"][:12]:
        print(f"  {mb(d['bytes_each']):>10s} x{len(d['paths'])}  {d['paths'][0]}")
        for extra in d["paths"][1:]:
            print(f"  {'':>10s}      {extra}")
    if summary["indexed_but_missing"]:
        print(f"\nWARNING: {summary['indexed_but_missing']} files are in the git index but "
              f"missing from disk — they still count toward tracked bytes in history")
    if bundles:
        print(f"\nbundles written to {out_dir.relative_to(ROOT)}/bundles:")
        for b in bundles:
            print(f"  {b['class']:16s} {mb(b['bundle_bytes']):>12s}  {b['bundle']}")
    print(f"\nmanifest   {out_dir.relative_to(ROOT)}/manifest.json")
    print(f"migration  {out_dir.relative_to(ROOT)}/MIGRATION.md  (owner commands, not executed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
