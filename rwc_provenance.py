"""Provenance for the Streamlit record: every number carries its origin.

`data/out/provenance-ledger.json` is written by `python3 -m provenance ledger`.
Each row in it knows one datum, the public page it came from, the literal clicks
to fetch it, and the second in the film where that fetch is on screen.

Two functions are all the views need:

    from rwc_provenance import show, source_link

    source_link(datum_id)        # a one-line "where this came from" caption
    show("News coverage", families=["news", "engine"])   # the full block

The block is an expander, closed by default, so it never gets in the way of the
record itself — but it is on every page that prints a number, and it names the
data family rather than hiding behind a generic "sources" link.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "data" / "out" / "provenance-ledger.json"

FAMILY_TITLE = {
    "inventory": "The inventory itself",
    "engine": "The document ledger",
    "meeting_calendar": "Meeting calendar & meeting days",
    "agenda_documents": "Agenda packets",
    "supporting_documents": "Supporting documents",
    "minutes_and_notes": "Minutes & meeting notes",
    "transcripts": "Transcripts & caption tracks",
    "meeting_video": "The meeting tapes",
    "drive_corpus": "The processed meetings database",
    "news": "News coverage",
    "arrests": "Arrest reports (de-identified)",
    "scanner": "Scanner audio transcripts",
    "open_data": "Open-data & records probes",
    "film": "The provenance film",
}


@st.cache_data(show_spinner=False)
def _load(path_str: str, mtime: float) -> dict | None:
    try:
        return json.loads(Path(path_str).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def ledger() -> dict | None:
    if not LEDGER.exists():
        return None
    return _load(str(LEDGER), LEDGER.stat().st_mtime)


def datum(datum_id: str) -> dict | None:
    led = ledger()
    if not led:
        return None
    for d in led.get("data", []):
        if d.get("id") == datum_id:
            return d
    return None


def _clip(d: dict) -> None:
    cue = d.get("cue") or {}
    src = cue.get("src")
    if not src:
        return
    clip = ROOT / src
    if not clip.exists():
        st.caption(f"Film cue (not on this checkout): `{src}`")
        return
    start = cue.get("start") or 0.0
    b0 = cue.get("beat_start")
    beat_at = max(0.0, (b0 - start)) if b0 is not None else 0.0
    beat = cue.get("beat")
    st.caption(
        f"🎞 The fetch, on film — {Path(src).name}, cut from "
        f"{_tc(start)}–{_tc(cue.get('end') or 0)} of `video/provenance-manual-run.mp4`"
        + (f"; the {'“' + beat + '”'} beat at {_tc(beat_at)} is this datum." if beat else ".")
    )
    try:
        st.video(str(clip), start_time=int(beat_at))
    except TypeError:  # very old streamlit: no start_time
        st.video(str(clip))
    except Exception as exc:  # never let provenance break a view
        st.caption(f"(clip unavailable: {exc})")


def _tc(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def show(title: str, families: list[str] | None = None, ids: list[str] | None = None,
         expanded: bool = False) -> None:
    """One provenance block: links, clip, and the click-path, for the numbers above."""
    led = ledger()
    if not led:
        st.caption("Provenance ledger not built yet — run `python3 -m provenance ledger`.")
        return

    if ids:
        rows = [d for d in led["data"] if d.get("id") in ids]
    else:
        wanted = set(families or [])
        rows = [d for d in led["data"] if not wanted or d.get("ledger") in wanted]
    if not rows:
        return

    groups: dict[str, list[dict]] = {}
    for d in rows:
        groups.setdefault(d.get("ledger", ""), []).append(d)

    with st.expander(f"🔗 Provenance — where the numbers in “{title}” come from", expanded=expanded):
        st.caption(
            "Each figure below is linked to the public page it came from. The clip shows a person "
            "collecting that kind of record by hand on the real site — the clicks are written out so "
            "you can do it yourself."
        )
        for key, items in groups.items():
            st.markdown(f"**{FAMILY_TITLE.get(key, key.replace('_', ' ').title())}**")
            _clip(items[0])
            st.markdown(f"How to get it yourself: {items[0].get('how', '')}")
            first_how = items[0].get("how", "")
            for d in items:
                val = d.get("value")
                shown = f"{val:,}" if isinstance(val, int) and not isinstance(val, bool) else str(val)
                origin = d.get("origin") or {}
                line = (
                    f"- **{d.get('item', '')}** — `{shown}` · "
                    f"[{origin.get('host', 'source')}]({origin.get('url', '')})"
                    + (f" · {d['note']}" if d.get("note") else "")
                )
                if d.get("how") and d["how"] != first_how:
                    line += f"\n    ↳ *how:* {d['how']}"
                st.markdown(line)
            ev = [e for e in items[0].get("evidence", []) if e]
            if ev:
                st.caption("in this repo: " + ", ".join(f"`{e}`" for e in ev[:3]))
        st.caption(
            f"Full cue sheet: {led['totals']['data']:,} datums mapped to the film — "
            "`data/out/PROVENANCE-LEDGER.md` · on the public site, `/provenance/`."
        )


def source_link(datum_id: str, label: str | None = None) -> str:
    """A markdown one-liner: the origin link for a single datum, plus its cue."""
    d = datum(datum_id)
    if not d:
        return ""
    origin = d.get("origin") or {}
    cue = d.get("cue") or {}
    parts = [f"[{label or origin.get('host', 'source')}]({origin.get('url', '')})"]
    if cue.get("src"):
        start = cue.get("start") or 0
        b0 = cue.get("beat_start") or start
        parts.append(f"on film {_tc(b0)} ({cue.get('beat') or 'cue'} beat)")
    return " · ".join(parts)


def film_block(expanded: bool = False) -> None:
    """The two films themselves, with an honest description of what each shows."""
    led = ledger()
    with st.expander("🎬 The provenance films — everything at once, then one thing at a time",
                     expanded=expanded):
        st.markdown(
            "**The time-lapse** is the whole collection: every file in this record, in capture order, "
            "at roughly 560 files a second. It is not a diagram of the archive — it is the archive."
        )
        tl = ROOT / "video" / "provenance-timelapse.mp4"
        if tl.exists():
            st.video(str(tl))
        st.markdown(
            "**The chapter film** is the how-to: one chapter per kind of record, showing the real "
            "origin page, the actual clicks, the download, and the file landing in this archive. "
            "Every number on this site carries a cue into it."
        )
        master = ROOT / "video" / "provenance-manual-run.mp4"
        if master.exists():
            st.video(str(master))
        if led:
            sched = led["film"]["schedule"]
            st.caption("Chapter cues — " + " · ".join(
                f"{_tc(start)} {key.replace('_', ' ')}" for key, start, dur in sched["chapters"]))


# --------------------------------------------------------------------------
# the master guide, inside the app
# --------------------------------------------------------------------------

def guide(out=None) -> Path | None:
    """Write data/out/PROVENANCE-GUIDE.md from what is in the checkout right now."""
    try:
        from provenance import guide as guide_mod

        return guide_mod.write(ROOT)
    except Exception as exc:
        st.caption(f"(guide could not be generated: {exc})")
        return None


def compare_mod_facts() -> dict:
    """The comparison's numbers, read from the checkout."""
    from provenance import compare as compare_mod

    return compare_mod.facts(ROOT)


def comparison(out=None) -> Path | None:
    """Write data/out/GRANICUS-VS-THIS-ARCHIVE.md from what is in the checkout right now."""
    try:
        from provenance import compare as compare_mod

        return compare_mod.write(ROOT)
    except Exception as exc:
        st.caption(f"(comparison could not be generated: {exc})")
        return None


def show_guide() -> None:
    """The master page: what everything is, the films, and how to check a number."""
    led = ledger()
    path = ROOT / "data" / "out" / "PROVENANCE-GUIDE.md"
    if not path.exists():
        path = guide()
    if path is None or not path.exists():
        st.warning("The guide has not been generated yet — run `python3 -m provenance guide`.")
        return

    st.subheader("🧭 The provenance guide")
    st.caption(
        "Everything in this archive, the films that show how each part was collected, and how to "
        "check any number in it yourself. Generated from the checkout, not typed by hand."
    )

    if led:
        sched = led["film"]["schedule"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Datums with a source", f"{led['totals']['with_link']:,}")
        c2.metric("With a film cue", f"{led['totals']['with_cue']:,}")
        c3.metric("Chapters", len(sched["chapters"]))
        c4.metric("Showcase length", f"{int(sched['timelapse'] + sched['timelapse_seconds']) // 60}:"
                                     f"{int(sched['timelapse'] + sched['timelapse_seconds']) % 60:02d}")

    film_block(expanded=True)

    tabs = st.tabs(["📄 The guide", "⚖️ City archive vs this", "💾 Rebuild it",
                    "🚦 How to check a number"])
    with tabs[0]:
        st.markdown(path.read_text(encoding="utf-8"))
        st.download_button("Download the guide (Markdown)", path.read_text(encoding="utf-8"),
                           file_name="PROVENANCE-GUIDE.md", mime="text/markdown")
    with tabs[1]:
        cmp_path = ROOT / "data" / "out" / "GRANICUS-VS-THIS-ARCHIVE.md"
        if not cmp_path.exists():
            cmp_path = comparison()
        if cmp_path is None or not cmp_path.exists():
            st.warning("The comparison has not been generated yet — "
                       "run `python3 -m provenance compare`.")
        else:
            try:
                cf = compare_mod_facts()
            except Exception:
                cf = {}
            if cf:
                k1, k2, k3 = st.columns(3)
                k1.metric("Meetings on the city's portal", f"{cf['council_clips']:,}",
                          help="Council and governing-body clips in the crawled clip list. "
                               "The portal lists no committee, board or county meeting.")
                k2.metric("Meetings in this archive", f"{cf['live'].get('meetings', 0):,}",
                          help=f"Across {cf['live'].get('body_slugs', 0)} bodies, "
                               f"{cf['meeting_first']} → {cf['meeting_last']}.")
                k3.metric("Portal rows newer than this catalog", "yes" if cf["catalog_lag"] else "no",
                          help=f"Portal newest: {cf.get('portal_newest') or '—'}; "
                               f"clip catalog ends {cf['clip_last']}.")
            st.markdown(cmp_path.read_text(encoding="utf-8"))
            st.download_button("Download the comparison (Markdown)",
                               cmp_path.read_text(encoding="utf-8"),
                               file_name="GRANICUS-VS-THIS-ARCHIVE.md", mime="text/markdown")
            if st.button("Rebuild the comparison now from this checkout",
                         key="prov_compare_build"):
                p = comparison()
                if p:
                    st.success(f"Wrote {p.relative_to(ROOT)}")
    with tabs[2]:
        st.markdown(
            "Every artefact on this page is generated from the checkout. In order:\n\n"
            "```bash\n"
            "python3 -m provenance detect                    # classify every file, write the inventory\n"
            "python3 -m provenance timelapse                 # the 20-second time-lapse\n"
            "python3 -m provenance video                     # the chapter film (~8 min)\n"
            "python3 -m provenance ledger --clips --showcase # cues, per-chapter clips, showcase\n"
            "python3 -m provenance guide                     # this page\n"
            "python3 -m provenance compare                   # portal vs this archive\n"
            "python3 tools/render_ai_record.py --src ai-record --out _site\n"
            "python3 tools/check_provenance.py --site _site\n"
            "```"
        )
        if st.button("Rebuild the guide now from this checkout", key="prov_guide_build"):
            p = guide()
            if p:
                st.success(f"Wrote {p.relative_to(ROOT)}")
    with tabs[3]:
        st.markdown(
            "1. **Pick a number on any page.** Every page with a figure has a 🔗 Provenance "
            "expander underneath it, on this app and on the public site.\n"
            "2. **Open the origin link.** It should be the page that number actually came from — "
            "the city's minutes page, Granicus, the news feed.\n"
            "3. **Play the clip.** It shows a person doing that fetch: the URL typed, the row "
            "clicked, the download. Each row names the beat, so you can skip to the moment.\n"
            "4. **Do it yourself once.** Follow the printed click-path and download one file. If it "
            "matches, the number is checkable; if it does not, that is a bug worth filing.\n"
            "5. **Or run the checks.** `python3 tools/check_provenance.py --site _site` fails if any "
            "figure lost its link or cue; `python3 tools/provenance_site_audit.py` rebuilds the whole "
            "record and crawls every page."
        )
