#!/usr/bin/env python3
"""Add the reviewed static game to the existing archive without replacing it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"index.html", "history.js", "history.css", "historical-data.js",
            "transcript-data.js", "evolution.js", "evolution-data.js", "live.js"}


def validate(src):
    if not all((src / name).is_file() for name in REQUIRED):
        raise ValueError("Incomplete game runtime")
    files = {}
    for path in src.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlinks are not permitted")
        if not path.is_file():
            continue
        rel = path.relative_to(src).as_posix()
        if any(part.startswith(".") for part in path.relative_to(src).parts):
            raise ValueError("Hidden working files are not permitted")
        if rel not in REQUIRED and not (
            rel.startswith("fonts/") and path.suffix in {".woff2", ".ttf"}
            or rel.startswith("transcripts/") and path.suffix == ".json"
        ):
            raise ValueError("Unexpected runtime file: " + rel)
        files[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    raw = (src / "transcript-data.js").read_text()
    catalog = json.loads(raw.split("=", 1)[1].strip().removesuffix(";"))
    records = catalog["records"]
    if len(records) != 913 or catalog["stats"]["records"] != 913:
        raise ValueError("Unexpected approved corpus count")
    if not any(name.startswith("transcripts/") for name in files):
        raise ValueError("Missing transcript chunks")
    return {"records": len(records), "files": files}


def publish(src, out, revision):
    if not (out / "index.html").is_file():
        raise ValueError("Render the archive first; refusing a replacement site")
    manifest = validate(src)
    manifest["revision"] = revision
    target = out / "game"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(src, target)
    (target / "deployment.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def verify(url, revision):
    base = url.rstrip("/") + "/game/"
    with urlopen(base + "deployment.json?revision=" + revision, timeout=60) as response:
        manifest = json.load(response)
    if manifest["revision"] != revision or manifest["records"] != 913:
        raise ValueError("Published revision or corpus count mismatch")
    names = ["index.html", "history.js", "transcript-data.js"]
    names += [next(name for name in manifest["files"] if name.startswith("transcripts/"))]
    for name in names:
        with urlopen(base + name + "?revision=" + revision, timeout=60) as response:
            actual = hashlib.sha256(response.read()).hexdigest()
        if actual != manifest["files"][name]:
            raise ValueError("Published bytes differ: " + name)
    print("Verified published game revision, catalog and runtime/chunk fingerprints")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("_site"))
    parser.add_argument("--revision", default="local")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--verify-url")
    args = parser.parse_args()
    if args.verify_url:
        verify(args.verify_url, args.revision)
    elif args.check_only:
        print(json.dumps(validate(ROOT / "civic_game"), indent=2))
    else:
        result = publish(ROOT / "civic_game", args.out, args.revision)
        print(f"Added {result['records']} transcript records under game/; archive retained")


if __name__ == "__main__":
    main()
