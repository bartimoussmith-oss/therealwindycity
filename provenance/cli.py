"""Command line: detect → plan → video.

    python3 -m provenance detect     # classify every file, write the inventory
    python3 -m provenance plan       # write the storyboard JSON
    python3 -m provenance video      # render the film
    python3 -m provenance all        # all three
    python3 -m provenance timelapse  # every file, at speed
    python3 -m provenance ledger     # one row per datum: origin link + film cue
    python3 -m provenance guide      # the master page: what everything is, and how to use it

Nothing here touches the network: the film is derived from files already in the
checkout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

from . import inventory as inventory_mod
from . import guide as guide_mod
from . import ledger as ledger_mod
from . import story as story_mod
from .util import human_bytes, human_duration, human_int
from .video import encode_frames

REPO_ROOT = Path(__file__).resolve().parent.parent


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# detect
# --------------------------------------------------------------------------


def write_inventory(inv, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    js = out_dir / "provenance-inventory.json"
    js.write_text(json.dumps(inv.as_dict(), indent=1) + "\n", encoding="utf-8")

    md = out_dir / "PROVENANCE-INVENTORY.md"
    lines: list[str] = []
    totals = {
        "files": inv.total_files,
        "bytes": inv.total_bytes,
        "scraped": inv.scraped_files,
        "manual": inv.manual_seconds,
    }
    lines += [
        "# Provenance inventory — what this archive consists of, and where it came from",
        "",
        f"Generated **{inv.generated_at}** by `python3 -m provenance detect` from `{inv.root}`.",
        "Read-only: the scanner walks the checkout once and writes only this file and its JSON twin.",
        "",
        "## Totals",
        "",
        f"- **{totals['files']:,}** files classified — **{inv.unassigned['files']}** unaccounted for",
        f"- **{human_bytes(totals['bytes'])}** across the working tree",
        f"- **{human_bytes(inv.scraped_bytes)}** of that is scraped or captured data",
        f"- **{len([f for f in inv.data_families if f.units])}** data families",
        f"- **{len(inv.host_totals)}** distinct source hosts cited by the repo itself",
        f"- **≈ {human_duration(inv.manual_seconds)}** of hand-work to assemble the same set manually"
        f" (≈ {inv.manual_actions:,.0f} actions at conservative per-document rates)",
        "",
        "Manual figures are estimates, not measurements: each family carries a stated"
        " `seconds_per_unit` and `actions_per_unit` in `inventory.py`. They exist to size the"
        " labour, not to score it.",
        "",
        "## Data families",
        "",
        "| # | family | class | files | units | size | origin | destination | by hand |",
        "|---|--------|-------|-------|-------|------|--------|-------------|---------|",
    ]
    for i, fam in enumerate(inv.families, 1):
        if fam.files == 0:
            continue
        origin = "—"
        curated = None
        if fam.origin_key:
            from . import origins as origins_mod

            curated = origins_mod.curated(fam.origin_key)
        if curated:
            origin = f"[{curated['site']}]({curated['url']})"
        elif fam.host_hits:
            from . import origins as origins_mod

            name = origins_mod.display_host(fam.host_hits[0].host)[0]
            origin = name
        manual = human_duration(fam.manual_seconds) if fam.seconds_per_unit else "—"
        units = f"{human_int(fam.units)} {fam.unit}{'' if fam.units == 1 else 's'}"
        lines.append(
            f"| {i} | **{fam.title.replace('&amp;', '&')}** | {fam.data_class} | {fam.files:,} | {units} | "
            f"{human_bytes(fam.bytes)} | {origin} | `{fam.destination}` | {manual} |"
        )

    lines += ["", "## Where each family came from", ""]
    from . import origins as origins_mod

    seen: set[str] = set()
    for fam in inv.families:
        if fam.files == 0 or fam.data_class == "code":
            continue
        curated = origins_mod.curated(fam.origin_key) if fam.origin_key else None
        lines.append(f"### {fam.title.replace('&amp;', '&')}")
        lines.append("")
        if curated:
            lines += [
                f"- **Site:** {curated['site']}",
                f"- **URL:** {curated['url']}",
                f"- **Evidence in repo:** {curated['evidence']}",
                f"- **Note:** {curated['note']}",
            ]
            seen.add(curated["site"])
        elif fam.host_hits:
            lines.append("- **Hosts observed in this family's own files:** " + ", ".join(
                f"`{h.host}` ({h.count} refs)" for h in fam.host_hits[:5]
            ))
        else:
            lines.append("- No external URL appears in this family's files (derived or generated here).")
        if fam.unit_note:
            lines.append(f"- **Counts:** {fam.unit_note}")
        if fam.files:
            sample = ", ".join(f"`{s}`" for s in fam.samples[:4])
            lines.append(f"- **Samples:** {sample}")
        lines.append("")

    lines += [
        "## Source sites detected in the repo's own text",
        "",
        "| site | host | references |",
        "|------|------|------------|",
    ]
    for h in inv.host_totals:
        lines.append(f"| {h['name']} | `{h['host']}` | {h['count']:,} |")

    lines += ["", "## Sibling repositories this checkout depends on", ""]
    if inv.upstreams:
        for up in inv.upstreams:
            lines.append(f"- `github.com/therealwindycity/{up['repo']}` — mentioned {up['mentions']}×")
    else:
        lines.append("- none detected")

    lines += [
        "",
        "## Ledger coverage",
        "",
        f"- `data/engine.db`: {inv.engine_ledger['note'] or 'not present'}",
        f"- Unassigned files: **{inv.unassigned['files']}**"
        + (f" — {inv.unassigned['by_extension']}" if inv.unassigned["files"] else ""),
        "",
        "## How this is measured",
        "",
        "1. Walk the tree once, skipping `.git`, caches and build output.",
        "2. Assign each file to exactly one family by path pattern (order matters; first match wins).",
        "3. Count units from the family's own manifests where a file is not a unit"
        " (arrest records, meeting records, catalogue rows, dataset probes).",
        "4. Credit a host as an origin only if a URL for it appears inside that family's files.",
        "5. Anything left over is reported, never hidden.",
        "",
        "Regenerate the film: `python3 -m provenance video`.",
        "",
    ]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return js, md


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------


def write_plan(story, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "provenance-storyboard.json"
    plan = {
        "generated_at": story.generated_at,
        "totals": story.totals,
        "chapters": [
            {
                "index": ch.index,
                "key": ch.key,
                "title": ch.title,
                "site": ch.site,
                "url": ch.url,
                "page": ch.page,
                "destination": ch.dest,
                "units": ch.units,
                "unit": ch.unit_label,
                "manual_estimate": ch.manual_text,
                "captions": ch.captions,
                "on_screen_rows": ch.rows[:4],
                "attachments": ch.attachments,
                "duration_seconds": ch.duration,
            }
            for ch in story.chapters
        ],
        "montage": story.montage,
        "detect_lines": story.detect_lines,
        "source_hosts": story.hosts,
        "upstream_repos": story.upstreams,
    }
    path.write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# video
# --------------------------------------------------------------------------


def render_video(story, out_path: Path, fps: int = 30, scale: float = 1.0, preset: str = "medium",
                 crf: int = 20) -> Path:
    from .scenes import Film

    film = Film(story)
    total = int(round(film.duration * fps))
    print(
        f"  film: {film.duration:.1f}s · {total:,} frames · {fps} fps · "
        f"{len(story.chapters)} chapters · {len(story.montage)} montage families",
        file=sys.stderr,
    )

    def gen():
        for i in range(total):
            yield film.frame(i / fps)

    return encode_frames(gen(), out_path, 1920, 1080, fps, total, scale=scale, crf=crf, preset=preset)


def write_timelapse_frames(root: Path, inv, out_dir: Path) -> Path:
    """The file-by-file manifest the time-lapse is drawn from."""
    from .timelapse import snapshot

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "provenance-timelapse-frames.json"
    rows = snapshot(root, inv)
    path.write_text(
        json.dumps(
            {
                "generated_at": _now(),
                "files": len(rows),
                "note": "one row per file, in walk order; the time-lapse draws these in capture order",
                "order": "merged by family progress, see provenance/timelapse.py",
                "entries": rows,
            },
            indent=0,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def render_timelapse(root: Path, out_path: Path, fps: int = 30, scale: float = 1.0,
                     preset: str = "medium", crf: int = 20, generated_at: str | None = None) -> Path:
    from .timelapse import Timelapse, collect

    inv = inventory_mod.scan(root, generated_at=generated_at)
    entries = collect(root, inv)
    film = Timelapse(inv, entries)
    total = int(round(film.total * fps))
    print(
        f"  time-lapse: {film.total:.1f}s · {total:,} frames · {len(entries):,} files at "
        f"{film.rate:,.0f}/s",
        file=sys.stderr,
    )

    def gen():
        for i in range(total):
            yield film.frame(i / fps)

    return encode_frames(gen(), out_path, 1920, 1080, fps, total, scale=scale, crf=crf, preset=preset)


def preview(story, times: list[float], out_dir: Path) -> list[Path]:
    from .scenes import Film

    film = Film(story)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for t in times:
        p = out_dir / f"preview-{t:07.2f}.png"
        film.frame(t).save(p)
        paths.append(p)
    return paths


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="provenance", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO_ROOT), help="repo root to scan (default: this checkout)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("detect", help="classify every file and write the inventory")
    d.add_argument("--out", default="data/out")

    p = sub.add_parser("plan", help="write the storyboard JSON")
    p.add_argument("--out", default="data/out")

    v = sub.add_parser("video", help="render the film")
    v.add_argument("--out", default="video/provenance-manual-run.mp4")
    v.add_argument("--fps", type=int, default=30)
    v.add_argument("--scale", type=float, default=1.0)
    v.add_argument("--preset", default="medium")
    v.add_argument("--crf", type=int, default=20)
    v.add_argument("--preview", default="", help="comma-separated timestamps: write PNGs instead of video")
    v.add_argument("--preview-dir", default="data/out/preview")

    tl = sub.add_parser("timelapse", help="render the every-file time-lapse")
    tl.add_argument("--out", default="video/provenance-timelapse.mp4")
    tl.add_argument("--fps", type=int, default=30)
    tl.add_argument("--scale", type=float, default=1.0)
    tl.add_argument("--preset", default="medium")
    tl.add_argument("--crf", type=int, default=20)
    tl.add_argument("--preview", default="", help="comma-separated timestamps: write PNGs instead of video")
    tl.add_argument("--preview-dir", default="data/out/preview")

    gd = sub.add_parser("guide", help="write the master guide (data/out/PROVENANCE-GUIDE.md)")
    gd.add_argument("--out", default="data/out")

    lg = sub.add_parser("ledger", help="write the per-datum ledger and cut the film cues")
    lg.add_argument("--out", default="data/out")
    lg.add_argument("--clips", action="store_true", help="cut each chapter out of the master film")
    lg.add_argument("--showcase", action="store_true",
                    help="build video/provenance-showcase.mp4 (time-lapse, then every chapter)")
    lg.add_argument("--force", action="store_true", help="re-cut clips that already exist")

    a = sub.add_parser("all", help="detect + plan + video")
    a.add_argument("--fps", type=int, default=30)
    a.add_argument("--scale", type=float, default=1.0)
    a.add_argument("--preset", default="medium")
    a.add_argument("--crf", type=int, default=20)

    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    stamp = _now()

    if args.cmd in ("detect", "all"):
        print(f"scanning {root} …", file=sys.stderr)
        inv = inventory_mod.scan(root, generated_at=stamp)
        out_dir = root / (args.out if hasattr(args, "out") else "data/out")
        js, md = write_inventory(inv, out_dir)
        print(
            f"  {inv.total_files:,} files · {inv.unassigned['files']} unassigned · "
            f"{len(inv.data_families)} families · ≈{human_duration(inv.manual_seconds)} by hand",
            file=sys.stderr,
        )
        print(f"  wrote {js.relative_to(root)}", file=sys.stderr)
        print(f"  wrote {md.relative_to(root)}", file=sys.stderr)
        if args.cmd == "detect":
            return 0

    if args.cmd == "timelapse":
        out = root / args.out
        frames = write_timelapse_frames(root, inventory_mod.scan(root, generated_at=stamp),
                                        root / "data" / "out")
        print(f"  wrote {frames.relative_to(root)} · {frames.stat().st_size / 1e6:.1f} MB", file=sys.stderr)
        if args.preview:
            from .timelapse import Timelapse, collect

            inv = inventory_mod.scan(root, generated_at=stamp)
            film = Timelapse(inv, collect(root, inv))
            pdir = root / args.preview_dir
            pdir.mkdir(parents=True, exist_ok=True)
            for t in [float(x) for x in args.preview.split(",") if x.strip()]:
                p = pdir / f"timelapse-{t:07.2f}.png"
                film.frame(t).save(p)
                print(f"  {p.relative_to(root)}", file=sys.stderr)
            return 0
        print(f"rendering → {out.relative_to(root)}", file=sys.stderr)
        render_timelapse(root, out, fps=args.fps, scale=args.scale, preset=args.preset, crf=args.crf,
                         generated_at=stamp)
        print(f"  done: {out.relative_to(root)} · {human_bytes(out.stat().st_size)}", file=sys.stderr)
        return 0

    print("building storyboard …", file=sys.stderr)
    story = story_mod.build(root, generated_at=stamp)
    plan_path = write_plan(story, root / "data" / "out")
    print(f"  wrote {plan_path.relative_to(root)}", file=sys.stderr)

    if args.cmd == "plan":
        return 0

    if args.cmd == "guide":
        path = guide_mod.write(root)
        f = guide_mod.facts(root)
        print(f"  guide: {f['datums']:,} datums · {len(f['clips'])} clips · "
              f"{sum(1 for x in f['films'].values() if x['exists'])}/3 films present",
              file=sys.stderr)
        print(f"  wrote {path.relative_to(root)} · {human_bytes(path.stat().st_size)}", file=sys.stderr)
        return 0

    if args.cmd == "ledger":
        inv = inventory_mod.scan(root, generated_at=stamp)
        data = ledger_mod.build(root, inv=inv, story=story, generated_at=stamp)
        js, md = ledger_mod.write(root, data)
        print(
            f"  {data['totals']['data']:,} datums · {data['totals']['with_link']:,} with a public link · "
            f"{data['totals']['with_cue']:,} with a film cue",
            file=sys.stderr,
        )
        print(f"  wrote {js.relative_to(root)}", file=sys.stderr)
        print(f"  wrote {md.relative_to(root)}", file=sys.stderr)
        if args.clips:
            made = ledger_mod.cut_clips(root, data, force=args.force)
            for m in made:
                if not m.get("skipped"):
                    print(f"  cut {m['clip']} · {human_bytes(m['bytes'])}", file=sys.stderr)
            print(f"  chapter cues written under {ledger_mod.CLIP_DIR}", file=sys.stderr)
        if args.showcase:
            out = ledger_mod.build_showcase(root, data, force=args.force)
            print(f"  showcase → {out.relative_to(root)} · {human_bytes(out.stat().st_size)}",
                  file=sys.stderr)
        return 0

    if args.cmd == "video" and args.preview:
        times = [float(x) for x in args.preview.split(",") if x.strip()]
        paths = preview(story, times, root / args.preview_dir)
        for p in paths:
            print(f"  {p.relative_to(root)}", file=sys.stderr)
        return 0

    out = root / (args.out if args.cmd == "video" else "video/provenance-manual-run.mp4")
    fps = args.fps
    scale = args.scale
    preset = args.preset
    crf = args.crf
    print(f"rendering → {out.relative_to(root)}", file=sys.stderr)
    render_video(story, out, fps=fps, scale=scale, preset=preset, crf=crf)
    size = out.stat().st_size
    print(f"  done: {out.relative_to(root)} · {human_bytes(size)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
