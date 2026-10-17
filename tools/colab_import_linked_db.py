#!/usr/bin/env python3
"""colab_import_linked_db.py — get `master_meetings_database_linked.json` into GitHub.

The Drive file is ~143 MB. GitHub rejects any blob over 100 MB, and this repo
keeps committed files under ~50 MB, so the database ships gzipped (measured
ratio on this data is ~3.2x, so expect ~40–48 MB). The Drive connector also
caps transfers at 100 MB, which is why the bytes have to be compressed on the
machine that already has them — Colab, where the file sits in mounted Drive.

Run it as a cell in the notebook that has the Drive file, or on any machine
with a local copy:

    # Colab (the file is at /content/drive/...)
    !python3 tools/colab_import_linked_db.py --push

    # local checkout
    python3 tools/colab_import_linked_db.py \
        --src ~/WindyCityMeetings/processed_database/master_meetings_database_linked.json \
        --repo . --push

What it does, in order:
  1. reads the JSON and profiles it (record count, keys, what "linked" adds
     over the older master_meetings_database.json, date range, categories);
  2. writes a deterministic gzip (mtime=0, no embedded filename) so re-running
     on the same input produces a byte-identical file and the same SHA-256;
  3. records both checksums, sizes and the profile in
     drive-import/manifest.json (machine-readable; no prose to drift);
  4. commits those two files and pushes to a data branch, printing the PR link.

Nothing is rewritten or reworded: the .json.gz is the source bytes, compressed.

Exit codes: 0 ok · 2 bad args/input · 3 too large after compression · 4 git/push
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_SRC = ("/content/drive/MyDrive/WindyCityMeetings/processed_database/"
               "master_meetings_database_linked.json")
GZ_NAME = "master_meetings_database_linked.json.gz"
DEST_DIR = "drive-import"
MANIFEST = "manifest.json"
# repo rule: committed files stay under ~50 MB (GitHub's hard cap is 100 MB)
MAX_MB = 50.0
REPO_URL = "https://github.com/bartimoussmith-oss/therealwindycity.git"
DATA_BRANCH = "data/meetings-db-linked"


# --------------------------------------------------------------------- helpers
def human(n: float) -> str:
    return f"{n / 1e6:.1f} MB"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def compress(src: Path, dst: Path) -> None:
    """gzip at level 9 with mtime=0 and no filename -> reproducible bytes."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    with src.open("rb") as fi, tmp.open("wb") as raw:
        # GzipFile(filename="") omits the original name; mtime=0 pins the header
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                           compresslevel=9, mtime=0) as fo:
            shutil.copyfileobj(fi, fo, length=1 << 20)
    tmp.replace(dst)


def profile(records: list) -> dict:
    """Describe the data without copying it: counts, keys, span, categories."""
    if not isinstance(records, list):
        raise SystemExit("input JSON is not a list of meeting records")

    top_keys: dict[str, int] = {}
    turn_keys: dict[str, int] = {}
    categories: dict[str, int] = {}
    dates = []
    total_chars = 0
    no_turns = 0

    for r in records:
        if not isinstance(r, dict):
            continue
        for k in r:
            top_keys[k] = top_keys.get(k, 0) + 1
        cat = str(r.get("category") or "").strip() or "(none)"
        categories[cat] = categories.get(cat, 0) + 1
        d = str(r.get("date") or "")
        if len(d) == 10 and d[4] == "-":
            dates.append(d)
        turns = r.get("turns") or []
        if not turns:
            no_turns += 1
        for t in turns:
            if isinstance(t, dict):
                for k in t:
                    turn_keys[k] = turn_keys.get(k, 0) + 1
                total_chars += len(str(t.get("text") or ""))

    return {
        "records": len(records),
        "records_without_turns": no_turns,
        "top_level_fields": dict(sorted(top_keys.items(), key=lambda kv: -kv[1])),
        "turn_fields": dict(sorted(turn_keys.items(), key=lambda kv: -kv[1])),
        "dates": {"min": min(dates) if dates else None,
                  "max": max(dates) if dates else None,
                  "dated": len(dates)},
        "categories": dict(sorted(categories.items(), key=lambda kv: -kv[1])),
        "turn_text_chars": total_chars,
    }


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, check=check)


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=cwd, check=check)


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=DEFAULT_SRC, help=f"source JSON (default: {DEFAULT_SRC})")
    ap.add_argument("--repo", default=".", help="local checkout to write into (default: .)")
    ap.add_argument("--branch", default=DATA_BRANCH, help=f"branch to push (default: {DATA_BRANCH})")
    ap.add_argument("--push", action="store_true", help="commit and push (default: build only)")
    ap.add_argument("--to-main", action="store_true",
                    help="push to main instead of a data branch (owner's usual Colab flow)")
    ap.add_argument("--allow-over", action="store_true",
                    help=f"continue even if the gzip exceeds {MAX_MB:.0f} MB")
    ap.add_argument("--dry-run", action="store_true", help="profile only; write nothing")
    args = ap.parse_args()

    src = Path(args.src).expanduser().resolve()
    repo = Path(args.repo).expanduser().resolve()

    # ---------------------------------------------------------------- input
    if not src.is_file():
        print(f"[!] source not found: {src}", file=sys.stderr)
        print("    In Colab, mount Drive first:", file=sys.stderr)
        print("      from google.colab import drive; drive.mount('/content/drive')", file=sys.stderr)
        return 2
    raw_bytes = src.stat().st_size
    print(f"[1/5] source: {src}  ({human(raw_bytes)})")

    try:
        with src.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[!] not valid JSON: {e}", file=sys.stderr)
        return 2

    prof = profile(data)
    print(f"       records: {prof['records']}  "
          f"({prof['dates']['dated']} dated, {prof['dates']['min']} → {prof['dates']['max']})")
    print(f"       turn fields: {', '.join(prof['turn_fields']) or '(none)'}")
    extra = [k for k in prof["top_level_fields"]
             if k not in {"id", "title", "filename", "date", "category", "turns", "raw_text_length"}]
    if extra:
        print(f"       fields the linked export adds: {', '.join(extra)}")
    print(f"       categories: " + ", ".join(f"{k} ({v})" for k, v in
                                            list(prof["categories"].items())[:6]) +
          (" …" if len(prof["categories"]) > 6 else ""))
    if args.dry_run:
        print("[dry-run] stopping before writing anything")
        return 0

    # ---------------------------------------------------------------- compress
    dest_dir = repo / DEST_DIR
    dest = dest_dir / GZ_NAME
    with tempfile.TemporaryDirectory() as td:
        tmp_gz = Path(td) / GZ_NAME
        print(f"[2/5] compressing (level 9, reproducible header)…")
        compress(src, tmp_gz)
        gz_bytes = tmp_gz.stat().st_size
        print(f"       {human(raw_bytes)} → {human(gz_bytes)} "
              f"({raw_bytes / gz_bytes:.2f}x)")
        if gz_bytes > MAX_MB * 1e6 and not args.allow_over:
            print(f"[!] {human(gz_bytes)} is over the repo's ~{MAX_MB:.0f} MB rule.", file=sys.stderr)
            print("    Options: --allow-over (still under GitHub's 100 MB cap), or ship it as a",
                  file=sys.stderr)
            print("    Release asset instead of a blob (see deploy notes / README).", file=sys.stderr)
            return 3
        if gz_bytes > 100e6:
            print("[!] over GitHub's 100 MB hard blob limit — a normal commit will be rejected.",
                  file=sys.stderr)
            print("    Use a Release asset: gh release create <tag> <file>", file=sys.stderr)
            return 3
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_gz), dest)

    # ---------------------------------------------------------------- manifest
    manifest_path = dest_dir / MANIFEST
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            manifest = {}
    imports = manifest.setdefault("imports", {})
    imports[GZ_NAME] = {
        "source_path": str(src),
        "imported_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "raw_bytes": raw_bytes,
        "gzip_bytes": dest.stat().st_size,
        "sha256_raw": sha256_file(src),
        "sha256_gzip": sha256_file(dest),
        "profile": prof,
        "notes": ("Deterministic gzip (mtime=0, no embedded filename): re-importing the same "
                  "source reproduces the same bytes and sha256_gzip."),
    }
    manifest["generated_by"] = "tools/colab_import_linked_db.py"
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"[3/5] manifest: {manifest_path.relative_to(repo)} "
          f"(sha256 gz {imports[GZ_NAME]['sha256_gzip'][:16]}…)")

    # ---------------------------------------------------------------- git
    if not (repo / ".git").exists():
        print(f"[!] {repo} is not a git checkout — clone it first:", file=sys.stderr)
        print(f"    git clone {REPO_URL} {repo}", file=sys.stderr)
        return 4

    branch = "main" if args.to_main else args.branch
    status = git(repo, "status", "--porcelain", "--", str(dest.relative_to(repo)),
                 str(manifest_path.relative_to(repo)), check=False)
    changed = bool(status.stdout.strip())
    print(f"[4/5] git: branch {branch} — "
          f"{'2 files to add/update' if changed else 'nothing changed (already imported)'}")
    if not args.push:
        print("[5/5] built only (pass --push to commit and push)")
        print(f"      wrote {dest} ({human(dest.stat().st_size)}) and {manifest_path.name}")
        return 0
    if not changed:
        print("[5/5] already up to date — nothing to push")
        return 0

    current = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if current != branch:
        exists = git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
        if exists.returncode == 0:
            git(repo, "checkout", branch)
        else:
            git(repo, "checkout", "-b", branch)

    git(repo, "add", str(dest.relative_to(repo)), str(manifest_path.relative_to(repo)))
    msg = (f"data: import {GZ_NAME} ({prof['records']} meetings, "
           f"{human(dest.stat().st_size)} gzipped)")
    ident = ["-c", "user.name=bartimoussmith-oss",
             "-c", "user.email=bartimoussmith-oss@users.noreply.github.com"]
    git(repo, *ident, "commit", "-m", msg)
    print(f"[5/5] committed: {msg}")

    pushed = git(repo, "push", "-u", "origin", branch, check=False)
    if pushed.returncode != 0:
        print("[!] push failed — most often a missing or expired credential.", file=sys.stderr)
        print("    Colab: store a fine-grained PAT with Contents:write as GH_PAT in Secrets,",
              file=sys.stderr)
        print("    then re-run with the remote set to:",
              file=sys.stderr)
        print(f"      git remote set-url origin https://<token>@github.com/"
              f"bartimoussmith-oss/therealwindycity.git", file=sys.stderr)
        print(pushed.stderr.strip()[-800:], file=sys.stderr)
        return 4

    print(pushed.stderr.strip()[-400:] if pushed.stderr.strip() else "")
    if branch != "main":
        print(f"\nOpen the PR:\n  https://github.com/bartimoussmith-oss/"
              f"therealwindycity/compare/main...{branch}?expand=1")
    return 0


if __name__ == "__main__":
    sys.exit(main())
