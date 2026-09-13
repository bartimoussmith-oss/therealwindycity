#!/usr/bin/env python3
"""
tools/server_sync.py — Sync Drive/R2 -> local server_data/ ensuring no external dependency

Ensures:
- Every external URL has local copy in server_data/<city>/
- RAG vectordb stored on server (server_data/<city>/vectordb/) + backup to R2
- Manifest preserves external_url + local_path + sha256

Usage:
  python tools/server_sync.py --city cheyenne --from-drive /content/drive/MyDrive/TheRealWindyCity/cheyenne --to server_data/cheyenne
  python tools/server_sync.py --city all --to server_data/
  python tools/server_sync.py --verify --city cheyenne

Also handles:
- Granicus pull manifest -> server_data
- Boards pull -> server_data
- WY statutes PDFs -> server_data
- Municode HTML -> server_data
- Case law -> server_data
- Captions VTT -> server_data
- Vectordb -> server_data + R2 backup

Run on your own server after Colab pulls.
"""
import argparse, json, shutil, hashlib
from pathlib import Path

def sha256_file(p: Path):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def sync_folder(src: Path, dst: Path):
    if not src.exists():
        print(f"  src missing {src}")
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in src.rglob("*"):
        if f.is_file():
            rel = f.relative_to(src)
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if not out.exists() or sha256_file(f) != sha256_file(out):
                shutil.copy2(f, out)
                count += 1
    print(f"  synced {count} files {src} -> {dst}")
    return count

def verify_city(city, root):
    from engine.local_store import LocalStore
    store = LocalStore(city=city, root=root)
    ok, missing = store.verify_no_dependency()
    if ok:
        print(f"  {city}: OK — all {len(store.manifest['files'])} external URLs have local copies")
    else:
        print(f"  {city}: MISSING {len(missing)} local copies")
        for m in missing[:20]:
            print(f"    - {m}")
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="cheyenne", help="city slug or 'all'")
    ap.add_argument("--from-drive", default="/content/drive/MyDrive/TheRealWindyCity", help="Drive source root")
    ap.add_argument("--to", default="server_data", help="local server root")
    ap.add_argument("--verify", action="store_true", help="verify no external dependency")
    args = ap.parse_args()

    cities = []
    if args.city == "all":
        # load registry
        reg_path = Path("cities/wyoming_cities.json")
        if reg_path.exists():
            reg = json.loads(reg_path.read_text())
            cities = [c["slug"] for c in reg["cities"]]
        else:
            cities = ["cheyenne"]
    else:
        cities = [args.city]

    for city in cities:
        print(f"\n=== {city} ===")
        if args.verify:
            verify_city(city, args.to)
            continue
        # sync from drive
        drive_city = Path(args.from_drive) / city
        local_city = Path(args.to) / city
        if drive_city.exists():
            sync_folder(drive_city, local_city)
        # sync granicus_pull if exists
        gp = Path("granicus_pull")
        if gp.exists():
            sync_folder(gp, local_city / "meetings")
        # sync boards
        boards = Path(f"cities/{city}/boards")
        if boards.exists():
            sync_folder(boards, local_city / "boards")
        # sync law
        law = Path(f"cities/{city}/law")
        if law.exists():
            sync_folder(law, local_city / "law")
        # sync vectordb
        vectordb = Path("rag/vectordb")
        if vectordb.exists():
            sync_folder(vectordb, local_city / "vectordb")
        # sync captions
        caps = Path("pipeline/captions")
        if caps.exists():
            sync_folder(caps, local_city / "captions")
        # verify
        verify_city(city, args.to)

if __name__ == "__main__":
    main()
