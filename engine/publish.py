"""Module 5 (public edition): render the ledger as a static, fully self-contained
site — The Real Windy City Ledger. Zero external assets: survives sandboxed
viewers, emails, and GitHub Pages unchanged. Voice: Cheyenne public-comment
bare-knuckle. Substrate: nothing that isn't in the DB with a source URL, or in
config/facts.json with a linked citation.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import shutil
from pathlib import Path

from . import db

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

_CSS = """
:root{--ink:#22303c;--paper:#f7f2e7;--rust:#b4432f;--gold:#d9a441;--sage:#5c7a4f;
--faded:#6d7b86;--card:#fffdf7;--rule:#d8cfbc}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);
font-family:Georgia,'Times New Roman',serif;line-height:1.55}
.wrap{max-width:1060px;margin:0 auto;padding:0 20px}
.mast{border-bottom:6px double var(--ink);padding:28px 0 18px;background:
repeating-linear-gradient(180deg,var(--paper) 0 6px,#f1ead9 6px 7px)}
.mast h1{font-size:clamp(34px,6vw,64px);letter-spacing:.02em;margin:0;
font-family:'Courier New',Courier,monospace;font-weight:700}
.kick{font-size:15px;color:var(--faded);margin:6px 0 0}
.tag{display:inline-block;margin-top:10px;background:var(--ink);color:var(--paper);
padding:6px 14px;font-family:'Courier New',monospace;font-size:14px;letter-spacing:.06em}
.wind{display:flex;gap:10px;align-items:center;margin-top:14px;color:var(--rust);
font-family:'Courier New',monospace;font-size:13px}
.strip{display:flex;flex-wrap:wrap;gap:14px;margin:26px 0}
.stat{flex:1 1 150px;background:var(--card);border:1px solid var(--rule);
border-top:4px solid var(--rust);padding:14px 16px}
.stat b{display:block;font-family:'Courier New',monospace;font-size:34px;line-height:1}
.stat span{font-size:12.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--faded)}
h2{font-family:'Courier New',monospace;font-size:20px;letter-spacing:.05em;margin:34px 0 4px;
border-bottom:2px solid var(--ink);padding-bottom:6px;text-transform:uppercase}
h2:before{content:'≫ ';color:var(--rust)}
.rule{font-size:12.5px;color:var(--faded);margin:0 0 14px}
.qotw{background:var(--card);border:1px solid var(--rule);border-left:6px solid var(--gold);
padding:16px 18px} .qotw h3{margin:0 0 6px;font-size:20px}
.watch{font-family:'Courier New',monospace;font-size:13px;color:var(--rust);margin-top:8px}
table{width:100%;border-collapse:collapse;font-size:14.5px;background:var(--card)}
th{font-family:'Courier New',monospace;text-transform:uppercase;font-size:11.5px;
letter-spacing:.08em;text-align:left;border-bottom:2px solid var(--ink);padding:8px}
td{border-bottom:1px solid var(--rule);padding:8px;vertical-align:top}
tr:hover td{background:#f3ecdc}
.t{font-family:'Courier New',monospace;font-size:12px;color:var(--faded);white-space:nowrap}
.qu{color:#3d4a56;font-style:italic}
a{color:var(--rust)} .term{font-family:'Courier New',monospace;font-size:12px;
color:var(--sage);white-space:nowrap}
.empty{border:1px dashed var(--faded);padding:16px;text-align:center;color:var(--faded);
font-family:'Courier New',monospace;font-size:13px}
.tl{list-style:none;margin:0;padding:0}
.tl li{display:flex;gap:14px;padding:10px 0;border-bottom:1px solid var(--rule)}
.tl time{flex:0 0 96px;font-family:'Courier New',monospace;font-size:12.5px;color:var(--rust)}
.draft{background:var(--card);border:1px solid var(--rule);padding:14px 16px;margin:10px 0}
footer{margin:44px 0 26px;border-top:6px double var(--ink);padding-top:16px;
font-size:12.5px;color:var(--faded)}
.method li{margin:4px 0}
.mono{font-family:'Courier New',monospace}
"""

_WINDSOCK = """<svg width="44" height="34" viewBox="0 0 44 34" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
<rect x="4" y="2" width="2.4" height="30" fill="#22303c"/>
<polygon points="7,4 30,7 30,13 7,16" fill="#b4432f"/>
<polygon points="7,4 14,5.2 14,14.8 7,16" fill="#d9a441"/>
<path d="M30 8 q9 1 12 3 M30 11 q9 0 12 1" stroke="#6d7b86" stroke-width="1.4" fill="none" stroke-linecap="round"/>
</svg>"""


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def build() -> str:
    facts = json.loads((ROOT / "config" / "facts.json").read_text())
    site = facts["site"]
    conn = db.connect()
    st = {
        "docs": conn.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"],
        "alerts": conn.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"],
        "edits": conn.execute("SELECT COUNT(*) c FROM versions WHERE seq>1").fetchone()["c"],
        "drafts": conn.execute("SELECT COUNT(*) c FROM requests WHERE status='draft'").fetchone()["c"],
    }
    alerts = conn.execute(
        "SELECT a.term, a.snippet, a.created_at, d.url, d.title FROM alerts a"
        " JOIN documents d ON d.id=a.document_id ORDER BY a.id DESC LIMIT 60").fetchall()
    edits = conn.execute(
        "SELECT v.captured_at, v.seq, v.change_summary, d.url, d.title FROM versions v"
        " JOIN documents d ON d.id=v.document_id WHERE v.seq>1 ORDER BY v.id DESC").fetchall()
    reqs = conn.execute("SELECT * FROM requests ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()

    drafts_dir = PUBLIC / "drafts"
    PUBLIC.mkdir(exist_ok=True)
    drafts_dir.mkdir(exist_ok=True)
    draft_links = []
    for r in reqs:
        fn = f"draft-{r['id']:04d}-{r['kind']}.md"
        (drafts_dir / fn).write_text(r["body"])
        draft_links.append(
            f"<div class='draft'><b class='mono'>DRAFT #{r['id']:04d} — {_esc(r['kind'].upper())}</b> · "
            f"{_esc(r['subject'])} · <a href='drafts/{fn}'>read the letter</a><br>"
            f"<span class='t'>filed {_esc(r['created_at'])} · a human reads and sends it. the machine does not mail letters.</span></div>")

    today = _dt.date.today()
    elec = _dt.date.fromisoformat(site["election_day"])
    pet = _dt.date.fromisoformat(site["petition_file_date"])
    days_to_elec = max(0, (elec - today).days)
    days_since_pet = max(0, (today - pet).days)

    stats_html = "".join([
        f"<div class='stat'><b>{st['docs']}</b><span>documents fingerprinted</span></div>",
        f"<div class='stat'><b>{st['alerts']}</b><span>watchlist hits, quoted</span></div>",
        f"<div class='stat'><b>{st['edits']}</b><span>silent edits caught</span></div>",
        f"<div class='stat'><b>{st['drafts']}</b><span>drafts awaiting a human</span></div>",
        f"<div class='stat'><b>{days_to_elec}</b><span>days to the Nov. 3 election</span></div>",
    ])

    edits_html = "".join(
        f"<tr><td class='t'>{_esc(r['captured_at'][:10])}</td><td><a href='{_esc(r['url'])}'>"
        f"{_esc(r['title'])}</a></td><td class='mono'>seq {r['seq']} — {_esc(r['change_summary'])}</td></tr>"
        for r in edits) or ("<div class='empty'>None yet. A quiet ledger is a true report. "
                            "If a published page changes by one hash, this table fills itself.</div>")
    if edits:
        edits_html = "<table><tr><th>When</th><th>Document</th><th>Change</th></tr>" + edits_html + "</table>"

    alerts_html = ("<table><tr><th>When</th><th>Flag</th><th>What the record says (verbatim)</th>"
                   "<th>Source</th></tr>" + "".join(
        f"<tr><td class='t'>{_esc(r['created_at'][:10])}</td>"
        f"<td class='term'>{_esc(r['term'])}</td>"
        f"<td class='qu'>{_esc(r['snippet'])}</td>"
        f"<td><a href='{_esc(r['url'])}'>source</a></td></tr>"
        for r in alerts) + "</table>") if alerts else \
        "<div class='empty'>The traps are set. Nothing has tripped them today.</div>"

    tl_html = "".join(
        f"<li><time>{_esc(e['date'])}</time><span>{_esc(e['label'])}"
        + (f" <a href='{_esc(e['url'])}'>[record]</a>" if e.get("url") else "")
        + "</span></li>"
        for e in facts["timeline"])

    q = facts["question_of_the_week"]
    generated = db.utcnow()

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(site['title'])}</title><style>{_CSS}</style></head><body><div class="wrap">
<header class="mast">
  <h1>{_esc(site['title'])}</h1>
  <p class="kick">{_esc(site['kicker'])}</p>
  <span class="tag">{_esc(site['tagline'])}</span>
  <div class="wind">{_WINDSOCK}<span>ledger generated {_esc(generated)} UTC · every entry links its record ·
  day {days_since_pet} since the petition was filed · clerk certification: pending</span></div>
</header>

<div class="strip">{stats_html}</div>

<h2>The question of the week</h2>
<p class="rule">One page. One fight. Read it and you're ahead of half the room.</p>
<div class="qotw"><h3>{_esc(q['headline'])}</h3><p>{_esc(q['body'])}</p>
<p class="watch">WATCH FOR: {_esc(q['watch_for'])}</p></div>

<h2>Silent-edit wire</h2>
<p class="rule">SHA-256 fingerprints of every published page, re-checked on schedule. Same words, same hash. New words, new hash — and a public diff.</p>
{edits_html}

<h2>Fresh from the traps</h2>
<p class="rule">Watchlist hits from the latest crawl. The quote is verbatim; the link is the record; the timestamp is the fetch.</p>
{alerts_html}

<h2>The record so far</h2>
<p class="rule">The 2026 chronology, each entry pinned to published reporting. Click [record]. Check the work.</p>
<ul class="tl">{tl_html}</ul>

<h2>Do the paperwork</h2>
<p class="rule">Wyoming Public Records Act drafts (W.S. §§ 16-4-201 to 16-4-205) and public comments, generated by the engine, sent by you.</p>
{''.join(draft_links)}

<footer>
  <p><b>Method.</b> This site is generated from a local ledger of public pages and
  documents fetched politely (robots.txt honored, 3-second minimum between requests,
  no logins, no paywall circumvention). Claims without a linked record do not get printed.</p>
  <ul class="method">
    <li>AI summaries here are extractive and method-labeled, or absent. The record is the text.</li>
    <li><b>No affiliation:</b> {_esc(site['voice_note'])}</li>
    <li>Engine: Civic Transparency Engine v0.1 · source + data export: civic-engine-export.tar.gz</li>
  </ul>
</footer>
</div></body></html>"""

    out = PUBLIC / "index.html"
    out.write_text(page)
    return str(out)
