#!/usr/bin/env python3
"""
Seed a new city from template — guerrilla bootstrap scaling

Usage:
  python tools/seed-city.py laramie wy --granicus laramie.granicus.com --municode laramie --youtube CHANNEL_ID
  python tools/seed-city.py casper wy --granicus casper.granicus.com --municode casper

Creates:
  cities/<slug>/config.yaml
  cities/<slug>/README.md
  cities/<slug>/boards/
  cities/<slug>/meetings/
  cities/<slug>/code/
  cities/<slug>/law/
  .github/workflows/civic-cycle-<slug>.yml (copy from civic-cycle.yml)

Then you run the pullers with CITY=<slug> env.
"""
import sys, shutil, pathlib, yaml, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "cities/_template/config.yaml"

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    slug = sys.argv[1].lower()
    state = sys.argv[2].lower()
    args = sys.argv[3:]
    granicus = None
    municode = None
    youtube = None
    for i, a in enumerate(args):
        if a == "--granicus" and i+1 < len(args):
            granicus = args[i+1]
        if a == "--municode" and i+1 < len(args):
            municode = args[i+1]
        if a == "--youtube" and i+1 < len(args):
            youtube = args[i+1]

    dest = ROOT / "cities" / slug
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "boards").mkdir(exist_ok=True)
    (dest / "meetings").mkdir(exist_ok=True)
    (dest / "code").mkdir(exist_ok=True)
    (dest / "law").mkdir(exist_ok=True)

    # copy template
    if TEMPLATE.exists():
        cfg_text = TEMPLATE.read_text()
        cfg_text = cfg_text.replace("cheyenne", slug).replace("wy", state)
        if granicus:
            cfg_text = re.sub(r"domain:.*", f"domain: {granicus}", cfg_text)
        if municode:
            cfg_text = re.sub(r"slug:.*", f"slug: {municode}", cfg_text, count=1)
        if youtube:
            cfg_text = re.sub(r"channel_id:.*", f"channel_id: {youtube}", cfg_text)
        (dest / "config.yaml").write_text(cfg_text)
    else:
        (dest / "config.yaml").write_text(f"city: {slug}\nstate: {state}\ngranicus:\n  domain: {granicus or ''}\nmunicode:\n  slug: {municode or slug}\n")

    (dest / "README.md").write_text(f"# {slug.title()}, {state.upper()}\n\nSeeded via tools/seed-city.py\n\n- Granicus: {granicus}\n- Municode: {municode}\n- YouTube: {youtube}\n\nNext:\n1. Run `python tools/granicus_document_pull.py` with CITY={slug} (edit OUT_ROOT)\n2. Run `python tools/cheyenne_boards_pull.py` adapted for {slug}\n3. Run `python tools/unified_meeting_builder.py`\n")

    print(f"Seeded {dest}")
    print(f"  config: {dest/'config.yaml'}")
    # optionally copy workflow
    workflow_src = ROOT / ".github/workflows/civic-cycle.yml"
    if workflow_src.exists():
        wf_dest = ROOT / f".github/workflows/civic-cycle-{slug}.yml"
        if not wf_dest.exists():
            txt = workflow_src.read_text()
            txt = txt.replace("cheyenne", slug)
            wf_dest.write_text(txt)
            print(f"  workflow: {wf_dest}")

if __name__ == "__main__":
    main()
