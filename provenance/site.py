"""The provenance block that sits under every page of the public site.

Each page of the record states numbers: how many meetings, how many documents,
how many transcripts, how many arrests. This module answers, for the numbers on
*that* page, three things in a row you can check:

1. the public page the number came from, as a link;
2. the same thing fetched by hand, as an embedded clip of the walkthrough;
3. the literal clicks, in words, so a reader can do it themselves tomorrow.

Plain HTML, no JavaScript. The clips are ordinary files served from the same
site, so the page works with scripts blocked, in a text browser, and in the
Internet Archive ten years from now (they will not all survive — the link and
the words will).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

# Which family's numbers appear on which pages of the generated site.
SITE_MATCH: dict[str, tuple[str, ...]] = {
    "meeting_calendar": ("index.html", "years/", "bodies/", "meetings/", "topics/"),
    "agenda_documents": ("meetings/", "documents/"),
    "supporting_documents": ("meetings/", "documents/"),
    "minutes_and_notes": ("meetings/", "documents/", "years/"),
    "transcripts": ("meetings/", "transcripts/", "documents/", "indexes/"),
    "meeting_video": ("meetings/",),
    "drive_corpus": ("transcripts/", "meetings/"),
    "news": ("news/", "index.html"),
    "arrests": ("arrests", "index.html"),
    "scanner": ("scanner/", "index.html"),
    "open_data": ("open-data/", "index.html"),
    "inventory": ("index.html",),
    "engine_keywords": ("indexes/",),
    "engine": ("index.html", "documents/"),
    "film": ("index.html", "provenance/"),
}

# shown at the top of the block, in this order
ORDER = [
    "inventory", "engine", "meeting_calendar", "agenda_documents", "supporting_documents",
    "minutes_and_notes", "transcripts", "meeting_video", "drive_corpus", "news", "arrests",
    "scanner", "open_data", "film",
]

_FAMILY_TITLE = {
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

CSS = """
.prov{margin:44px 0 0;border-top:2px solid #cfd6e4;padding-top:18px}
.prov h2{font:600 20px/1.3 system-ui,sans-serif;margin:0 0 6px}
.prov p.lede{font:15px/1.55 system-ui,sans-serif;color:#333;margin:0 0 18px;max-width:70ch}
.prov .item{border:1px solid #dde3ec;border-radius:8px;padding:14px 16px;margin:0 0 14px;background:#fbfcfe}
.prov .item h3{font:600 16px/1.35 system-ui,sans-serif;margin:0 0 4px}
.prov .val{font:700 22px/1.2 ui-monospace,monospace;color:#0b3a6f}
.prov .how{font:14px/1.5 system-ui,sans-serif;color:#333;margin:8px 0 10px}
.prov .how b{color:#111}
.prov a.src{font:14px/1.4 ui-monospace,monospace;word-break:break-all}
.prov video{width:100%;max-width:640px;border-radius:6px;background:#0a0f1a;display:block;margin:10px 0 6px}
.prov .cue{font:12px/1.4 ui-monospace,monospace;color:#555}
.prov .ev{font:12px/1.5 ui-monospace,monospace;color:#555;margin-top:6px}
.prov .ev code{background:#eef2f8;padding:1px 4px;border-radius:3px}
.prov table.provt{border-collapse:collapse;margin:8px 0 4px;width:100%;max-width:820px}
.prov table.provt td{border-bottom:1px solid #e8ecf3;padding:6px 10px 6px 0;font:14px/1.45 system-ui,sans-serif;vertical-align:top}
.prov table.provt td.num{font:600 16px/1.4 ui-monospace,monospace;color:#0b3a6f;white-space:nowrap;width:1%}
.prov table.provt td .note{font:12px/1.4 system-ui,sans-serif;color:#666;margin-top:2px}
.prov table.provt td .how{font:12px/1.4 system-ui,sans-serif;color:#444;margin-top:2px}
.prov table.provt td.lnk{font:13px/1.4 ui-monospace,monospace;white-space:nowrap;width:1%}
"""


def load(root: Path) -> dict | None:
    p = root / "data" / "out" / "provenance-ledger.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _matches(ledger_key: str, rel: str) -> bool:
    for pre in SITE_MATCH.get(ledger_key, ()):
        if pre.endswith(".html"):
            if rel == pre:
                return True
        elif rel.startswith(pre):
            return True
    return False


def _clip_html(d: dict, root_rel: str) -> str:
    cue = d.get("cue") or {}
    src = cue.get("src")
    master = (cue.get("master") or {})
    if not src:
        return ""
    clip = f"{root_rel}{src}"
    poster = src.rsplit(".", 1)[0] + ".jpg"
    start = cue.get("start", 0)
    end = cue.get("end", 0)
    local_start = max(0.0, start - (master.get("start") or start))
    local_end = local_start + (end - start)
    frag = f"#t={local_start:.1f},{local_end:.1f}"
    chapter = cue.get("chapter", "overview")
    if chapter == "overview":
        what = ("the time-lapse and the chapter film as one 4-minute file — this datum is a "
                "collection-wide total, so every chapter contributes to it")
    else:
        what = (f"chapter “{_FAMILY_TITLE.get(chapter, chapter.replace('_', ' '))}” of the chapter film "
                f"({_tc(start)}–{_tc(end)} there), cut whole so you see the page open, the click and "
                "the file land")
    cap = (
        f'<div class="cue">{html.escape(str(src).rsplit("/", 1)[-1])} · {html.escape(what)} · '
        f'each row below opens the exact beat · '
        f'<a href="{root_rel}provenance/index.html">all cues</a></div>'
    )
    return (
        f'<video controls preload="metadata" playsinline poster="{html.escape(root_rel + poster)}" '
        f'src="{html.escape(clip)}{frag}"></video>{cap}'
    )


def _tc(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"


EMBED_MAX = 3  # clips on a content page; every row still carries its own cue link


def _beat_window(cue: dict) -> tuple[float, float]:
    """Where this datum sits inside its clip, as an offset from the clip's start."""
    start = cue.get("start") or 0.0
    b0 = cue.get("beat_start")
    b1 = cue.get("beat_end")
    if b0 is None or b1 is None:
        return 0.0, max(1.0, (cue.get("end") or start) - start)
    return max(0.0, b0 - start), max(0.0, b1 - start)


def _cue_link(d: dict, root_rel: str) -> str:
    cue = d.get("cue") or {}
    src = cue.get("src")
    if not src:
        return "—"
    a, b = _beat_window(cue)
    label = _tc(a)
    beat = cue.get("beat")
    tip = (f"watch this datum being collected ({beat} beat, {_tc(a)} into the clip)"
           if beat else "watch the cue")
    return (
        f'<a href="{root_rel}{html.escape(src)}#t={a:.1f},{max(a + 0.8, b - 0.1):.1f}" '
        f'title="{html.escape(tip)}">{label}</a>'
    )


def block(rel: str, ledger: dict, root_rel: str = "") -> str:
    """The provenance section for one site page (empty string if none applies)."""
    rows = [d for d in ledger.get("data", []) if _matches(d.get("ledger", ""), rel)]
    if not rows:
        return ""
    groups: dict[str, list[dict]] = {}
    for d in rows:
        groups.setdefault(d.get("ledger", ""), []).append(d)
    keys = sorted(groups, key=lambda k: (ORDER.index(k) if k in ORDER else 99, k))
    max_groups = 4 if rel in ("index.html",) else 6
    hidden = keys[max_groups:]
    keys = keys[:max_groups]

    def pretty(k: str) -> str:
        return _FAMILY_TITLE.get(k, k.replace("_", " ").title())

    # the whole ledger, as one line, for the pages that cannot show every family
    total_rows = len(rows)
    in_page = sum(min(6, len(groups[k])) for k in keys)

    out = [
        '<section class="prov">',
        "<h2>Where the numbers on this page come from</h2>",
        '<p class="lede">Every figure on this page is linked to the public page it came from, and the '
        "cue beside each one opens the film at the moment a person collects that kind of record by hand "
        "— the real site, the real clicks, the download. The click-path is written out so you can go and "
        "get it yourself; nothing here needs this site, or us, to check. "
        f'<a href="{root_rel}provenance/index.html">The full cue sheet</a> maps all '
        f"{ledger['totals']['data']:,} figures in this record to a second in the film.</p>",
    ]
    for n, key in enumerate(keys):
        items = groups[key]
        title = _FAMILY_TITLE.get(key, key.replace("_", " ").title())
        out.append('<div class="item">')
        out.append(f"<h3>{html.escape(title)}</h3>")
        if n < EMBED_MAX:
            out.append(_clip_html(items[0], root_rel))
        out.append(
            f'<div class="how"><b>How to get it yourself:</b> {html.escape(items[0].get("how", ""))}</div>'
        )
        out.append('<table class="provt"><thead><tr><th>datum</th><th>value</th><th>origin</th>'
                   "<th>cue</th></tr></thead><tbody>")
        first_how = items[0].get("how", "")
        rows_sorted = sorted(items, key=lambda x: x["id"])
        shown_rows = rows_sorted[:6]
        for d in shown_rows:
            val = d.get("value")
            val_html = (f"{val:,}" if isinstance(val, int) and not isinstance(val, bool)
                        else html.escape(str(val)))
            extra = ""
            if d.get("how") and d["how"] != first_how:
                extra = f'<div class="how">{html.escape(d["how"])}</div>'
            elif d.get("note"):
                extra = f'<div class="note">{html.escape(d["note"])}</div>'
            out.append(
                "<tr>"
                f'<td class="what">{html.escape(d.get("item", ""))}{extra}</td>'
                f'<td class="num">{val_html}</td>'
                f'<td class="lnk"><a href="{html.escape(d["origin"]["url"])}" rel="nofollow noopener">'
                f'{html.escape(d["origin"]["host"])}</a></td>'
                f'<td class="lnk">{_cue_link(d, root_rel)}</td>'
                "</tr>"
            )
        out.append("</tbody></table>")
        if len(rows_sorted) > len(shown_rows):
            out.append(
                f'<div class="note">+ {len(rows_sorted) - len(shown_rows)} more '
                f'{html.escape(title.lower())} figures — '
                f'<a href="{root_rel}provenance/index.html">the full cue sheet</a></div>'
            )
        ev = [e for e in items[0].get("evidence", []) if e]
        if ev:
            out.append(
                '<div class="ev">in this repo: '
                + ", ".join(f"<code>{html.escape(e)}</code>" for e in ev[:3])
                + "</div>"
            )
        out.append("</div>")
    if hidden:
        out.append(
            f'<p class="lede">Also on this page, each with its own link and cue: '
            + ", ".join(html.escape(pretty(k)) for k in hidden)
            + f'. Every figure in this record is listed in '
            f'<a href="{root_rel}provenance/index.html">the full cue sheet</a>.</p>'
        )
    if total_rows > in_page:
        out.append(
            f'<p class="lede"><b>{total_rows - in_page} more figures apply to this page</b> — the '
            "complete list, with an origin link and a film cue for each one, is the "
            f'<a href="{root_rel}provenance/index.html">cue sheet</a> '
            f'({ledger["totals"]["data"]:,} figures across the whole record).</p>'
        )
    out.append("</section>")
    return "\n".join(out)


def page(ledger: dict, root_rel: str, ctx: dict | None = None) -> str:
    """The standalone /provenance/ page: the films, then every cue, then every datum."""
    ctx = ctx or {}
    here = ctx.get("rel", "provenance/index.html")
    siblings = ctx.get("pages") or {}
    sched = ledger["film"]["schedule"]
    totals = ledger["totals"]
    out = [
        "<h1>Provenance: every number on this site, and the film of how it was collected</h1>",
        f"<p><em>{totals['data']:,} figures across this record. Each one is linked to the public page it "
        "came from and carries a cue into the film that shows a person fetching it by hand.</em></p>",
        "<h2>Everything at once</h2>",
        "<p>The time-lapse is the whole collection — every file this record is built from, in capture "
        "order, at roughly 560 files a second. It is not a diagram of the archive; it is the archive.</p>",
        f'<video controls preload="metadata" width="100%" poster="{root_rel}video/provenance-timelapse-poster.jpg" '
        f'src="{root_rel}video/provenance-timelapse.mp4"></video>',
        f"<p><small>20 seconds · {ledger['film']['timelapse']}</small></p>",
        "<h2>One thing at a time</h2>",
        "<p>One chapter per kind of record: the real origin page, the actual clicks, the download, and the "
        "file landing in this archive. The master film is "
        f'<a href="{root_rel}video/provenance-manual-run.mp4">here</a> ({_tc(sched["total"])}); the copy '
        "below is the same footage with the time-lapse in front.</p>",
        f'<video controls preload="metadata" width="100%" '
        f'src="{root_rel}video/provenance-showcase.mp4"></video>',
        f"<p><small>{_tc(sched['timelapse'] + sched['timelapse_seconds'])} · "
        f"{ledger['film']['showcase']}</small></p>",
        "<h2>The cue sheet</h2>",
        "<p>Every datum, in the order it appears in the film. Open a cue and you are watching that number "
        "being collected. The page column links to the pages of this record that print it.</p>",
        "<table><thead><tr><th>chapter cue</th><th>beat</th><th>datum</th><th>value</th>"
        "<th>origin</th><th>on these pages</th></tr></thead><tbody>",
    ]
    rows = [d for d in ledger.get("data", []) if d.get("cue")]
    rows.sort(key=lambda d: (d["cue"].get("start") or 0, d["id"]))
    for d in rows:
        cue = d["cue"]
        val = d.get("value")
        val = f"{val:,}" if isinstance(val, int) and not isinstance(val, bool) else html.escape(str(val))
        a, b = _beat_window(cue)
        pages = _pages_for(d, here, root_rel, siblings)
        out.append(
            f'<tr data-datum="{html.escape(d["id"])}">'
            f'<td><a href="{root_rel}{html.escape(cue["src"])}#t={a:.1f},{max(a + 0.8, b - 0.1):.1f}" '
            f'title="{html.escape(cue.get("beat") or "cue")} beat">{_tc(cue.get("start") or 0)}</a></td>'
            f'<td>{_tc(a)}<div class="note">{html.escape(cue.get("beat") or "")}</div></td>'
            f'<td>{html.escape(d.get("item", ""))}<div class="note">{html.escape(d.get("how", ""))}</div></td>'
            f"<td>{val}</td>"
            f'<td><a href="{html.escape(d["origin"]["url"])}" rel="nofollow noopener">'
            f'{html.escape(d["origin"]["host"])}</a></td>'
            f"<td>{pages}</td>"
            "</tr>"
        )
    out += [
        "</tbody></table>",
        f"<p><em>Built {html.escape(ledger.get('generated_at', ''))} from the repository itself by "
        "<code>python3 -m provenance ledger</code>. This cue sheet is also served as "
        f'<a href="{root_rel}provenance/ledger.md">Markdown</a> and '
        f'<a href="{root_rel}provenance/ledger.json">JSON</a>.</em></p>',
    ]
    return "\n".join(out)


def _pages_for(d: dict, here: str, root_rel: str, siblings: dict[str, str]) -> str:
    """The pages of this site that print this datum, as links."""
    led = d.get("ledger", "")
    if led in ("inventory", "film"):
        target = "index.html"
        return f'<a href="{root_rel}{target}">home</a>'
    hits = []
    for rel, href in siblings.items():
        if _matches(led, href):
            hits.append((rel, href))
    # a family matches directory prefixes, so link the first page in each directory
    seen = set()
    links = []
    for rel, href in hits:
        top = href.split("/")[0]
        if top in seen:
            continue
        seen.add(top)
        in_this_dir = "" if href.startswith("provenance/") else ""
        links.append(f'<a href="{root_rel}{href}">{html.escape(top or "home")}</a>')
        if len(links) >= 3:
            break
    if not links:
        return "—"
    return " · ".join(links)
