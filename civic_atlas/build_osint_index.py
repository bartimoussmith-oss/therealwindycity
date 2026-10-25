"""Build a compact, read-only lexical index for the static OSINT Atlas page."""
import argparse
import json
from pathlib import Path
from .server import Corpus


def build(root: Path) -> list[dict]:
    corpus = Corpus(root)
    # No full documents are shipped. The browser receives title/provenance,
    # searchable normalized tokens, and a short excerpt only.
    return [{
        "id": r["id"], "title": r["title"], "date": r["date"],
        "kind": r["kind"], "path": r["path"],
        "terms": " ".join(sorted(r["terms"])),
        "excerpt": " ".join(r["text"].split())[:360],
    } for r in corpus.records]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(build(args.root), ensure_ascii=False, separators=(",", ":")))
    print(f"Wrote {args.out} ({args.out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
