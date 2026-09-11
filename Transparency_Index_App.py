"""The Real Windy City — civic console for Cheyenne / Laramie County.

One Streamlit process, two faces, switched from the sidebar (deep-linkable
with ?face=index):

  * Ledger HQ — the working console. It opens on the Miller Tapes
    theater (every Charles Miller intervention autoplaying on loop —
    picture starts instantly, first click anywhere brings sound), then the
    contention reel, then the Choose Your Mission guide — an
    adaptive six-stage wizard that drills each
    viewer down into the parts of the record that touch them —
    and the sidebar groups the views
    into sections: live operations (alerts, silent edits, digest), the
    record (search, the 17-year minutes archive, the canon library), the
    video vault (produced segments, evidence clips, full city meetings),
    intake (tips and PRA paperwork), and the recovered vault tabs, which
    stay behind leads-not-facts banners until each row checks out against
    the transcript corpus.
  * Transparency Index — entity dossiers and a document viewer. Reads
    Entity_Database/*.json when the indexer has built them, and otherwise
    falls back to a heuristic index assembled live from the dossiers, so
    the face is never dark.

streamlit_app.py and Transparency_Index_App.py are kept as identical twins
on purpose: whichever one Streamlit Cloud points at, the app boots.

Skinned as HEROES OF THE PUBLIC RECORD (owner-directed comic-book
re-theme, 2026-09-11): presentation only — every query, widget, and
behavior is unchanged, and the twins are still byte-identical.
"""

# Contributors and agents: READ-FIRST.md at the repo root is the coordination
# file — read it and file a claim there before changing anything in here.

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from engine import db, corpus_search, verify_vault, entity_index
except Exception:  # engine tree absent -> engine tabs degrade, rest still works
    db = corpus_search = verify_vault = entity_index = None

try:
    from miller_theater import render_theater as _render_miller_theater
except Exception:  # theater module absent -> front-door view degrades, rest works
    _render_miller_theater = None

ENGINE_DB = ROOT / "data" / "engine.db"
LEGACY_DB = ROOT / "cheyenne_watchdog.db"
VERIF_JSON = ROOT / "data" / "vault_verification.json"
CORPUS_DIR = ROOT / "pipeline" / "corpus"

st.set_page_config(page_title="The Real Windy City — Heroes of the Public Record",
                   page_icon="🦸", layout="wide")

# =========================================================================
# data plumbing (shared)
# =========================================================================


def _engine_q(query, args=()):
    if db is None or not ENGINE_DB.exists():
        return []
    conn = db.connect()
    try:
        return [dict(r) for r in conn.execute(query, args).fetchall()]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _legacy_q(query):
    if not LEGACY_DB.exists():
        return []
    try:
        conn = sqlite3.connect(str(LEGACY_DB))
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(query).fetchall()]
        conn.close()
        return rows
    except sqlite3.OperationalError:
        return []


def _ago(ts: str | None) -> str:
    if not ts:
        return "never"
    try:
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        d = datetime.now(timezone.utc) - t
        h = d.total_seconds() // 3600
        return f"{t:%b %d %H:%M} UTC ({'just now' if h < 1 else f'{h}h ago' if h < 48 else f'{h//24}d ago'})"
    except Exception:
        return ts


@st.cache_data(ttl=3600, show_spinner=False)
def _verification(root_str: str, json_mtime: float):
    root = Path(root_str)
    if json_mtime and (root / "data" / "vault_verification.json").exists():
        try:
            return json.loads((root / "data" / "vault_verification.json")
                              .read_text())
        except Exception:
            pass
    if verify_vault is None:
        return {"rows": {}, "corpus_files": 0}
    return verify_vault.verify(root)


@st.cache_data(ttl=3600, show_spinner=False)
def _corpus(root_str: str, sig: tuple):
    if corpus_search is None:
        return []
    return corpus_search.load_corpus(Path(root_str))


@st.cache_data(ttl=3600, show_spinner=False)
def _auto_entities(root_str: str, sig: tuple):
    if entity_index is None:
        return {}
    return entity_index.build(Path(root_str))


# =========================================================================
# FACE 1 — Watchdog Ledger
# =========================================================================

SERIES = [
    (r"(?i)^miller[-_]", "◆ Canon"),
    (r"(?i)^(tonight|docket|highlands|agenda)", "▣ Meeting Packs"),
    (r"(?i)^(ca-pull|pull|connect|fb-reply|.*speech|municipal-building)", "▶ Actions"),
    (r"(?i)(aipoison|audit)", "◌ Field Notes"),
]
SKIP = {"README.md", "LEGAL.md", "PERSISTENCE.md", "DEPLOY.md"}

VAULT_BANNER = ("Recovered from the pre-Sept-7 vault. Rows carry positions, quotes "
                "and dollar figures **as the seed recorded them**. Each cycle now "
                "re-checks every claim against the transcript corpus: ✅ = found in "
                "the record with file + date; anything else remains a lead to verify "
                "before citing. (*) marks vault tabs.")

VAULT_QUERIES = {
    "public_comment_battles": ("SELECT meeting_date, forum, agenda_item, subject, "
                               "miller_position, statutory_hooks, council_response, "
                               "outcome_status FROM public_comment_battles "
                               "ORDER BY meeting_date DESC"),
    "veracity_contradictions": "SELECT * FROM veracity_contradictions",
    "voucher_forensics": ("SELECT check_date, vendor, amount, department, description, "
                          "miller_claim, audit_status FROM voucher_forensics "
                          "ORDER BY amount DESC"),
    "environmental_zones": "SELECT * FROM environmental_zones",
}


def _canon_series(name: str) -> str:
    for pat, label in SERIES:
        if re.search(pat, name):
            return label
    return "○ Other"


def _verdict(ver: dict, table: str, i: int):
    r = ver.get("rows", {}).get(f"{table}:{i}")
    if not r:
        return None
    return r if r.get("status") == "found-in-record" and r.get("hits") else None


def _vault_ver() -> dict:
    """One place that reads the vault-verification JSON (header + vault views)."""
    json_mtime = VERIF_JSON.stat().st_mtime if VERIF_JSON.exists() else 0.0
    return _verification(str(ROOT), json_mtime)


# =========================================================================
# HEROES OF THE PUBLIC RECORD — comic-universe skin (presentation only)
# =========================================================================
# Owner-directed re-theme (2026-09-11). This block adds a stylesheet, a
# cover masthead, the Hero Roster, and the Join-the-Roster intake. It
# changes NO query, widget, or behavior anywhere else in this file.
# Twins rule: edit streamlit_app.py, then copy it byte-for-byte over
# Transparency_Index_App.py — never let them diverge.

_COMIC_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Bangers&family=Comic+Neue:ital,wght@0,400;0,700;1,400&display=swap');
.stApp{background-color:#f4ecd8;
background-image:radial-gradient(#ddd2b8 1.2px,transparent 1.3px);
background-size:15px 15px}
.stApp h1,.stApp h2,.stApp h3{font-family:'Bangers',Impact,'Arial Black',sans-serif;
letter-spacing:.04em;text-transform:uppercase;color:#141414}
.stApp a{color:#b4432f !important;font-weight:700}
.rv-cover{background:#141414;color:#f4ecd8;border:4px solid #0a0a0a;
box-shadow:8px 8px 0 #b4432f;padding:22px 22px 16px;margin:6px 0 18px;
transform:rotate(-.4deg)}
.rv-kicker{font-family:'Comic Neue','Comic Sans MS',cursive;font-weight:700;
font-size:.85rem;letter-spacing:.35em;color:#ffd93b}
.rv-title{font-family:'Bangers',Impact,'Arial Black',sans-serif;
font-size:clamp(40px,6.5vw,76px);line-height:1;margin:6px 0 4px;color:#fff;
text-shadow:3px 3px 0 #b4432f,6px 6px 0 #0a0a0a}
.rv-issue{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.rv-issue span{background:#ffd93b;color:#141414;font-family:'Bangers',Impact,sans-serif;
font-size:1rem;letter-spacing:.08em;padding:2px 12px;border:2px solid #0a0a0a;
box-shadow:3px 3px 0 #000}
.rv-tagline{font-family:'Comic Neue','Comic Sans MS',cursive;font-style:italic;
font-size:1.05rem;color:#f4ecd8}
.rv-strip{margin-top:12px;background:#b4432f;color:#fff;font-weight:700;
font-size:.85rem;letter-spacing:.04em;padding:6px 12px;border:2px solid #0a0a0a}
.rv-hero{background:linear-gradient(135deg,#ffd93b 0%,#ffb52e 60%,#f08a1d 100%);
border:4px solid #0a0a0a;box-shadow:8px 8px 0 #0a0a0a;padding:20px;margin:14px 0}
.rv-hero h2{margin:0;font-size:clamp(30px,4.5vw,52px);color:#141414;
text-shadow:2px 2px 0 #fff}
.rv-hero .aka{font-family:'Comic Neue','Comic Sans MS',cursive;font-weight:700}
.rv-stats{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}
.rv-stats span{background:#141414;color:#ffd93b;font-family:'Bangers',Impact,sans-serif;
font-size:1.15rem;letter-spacing:.05em;padding:4px 14px;border:2px solid #0a0a0a;
box-shadow:3px 3px 0 rgba(0,0,0,.35)}
.rv-card{background:#fffdf7;border:3px solid #0a0a0a;box-shadow:6px 6px 0 #0a0a0a;
padding:14px 16px;margin:10px 0}
.rv-card h3{margin:0 0 6px;font-size:1.5rem}
.rv-card p{margin:6px 0;font-size:.95rem}
.rv-power{display:inline-block;background:#141414;color:#fff;font-weight:700;
font-size:.78rem;letter-spacing:.03em;padding:2px 10px;margin:2px 4px 2px 0;
border:2px solid #0a0a0a}
.rv-pow{display:inline-block;background:#e33e2b;color:#fff;
font-family:'Bangers',Impact,sans-serif;font-size:1.3rem;letter-spacing:.06em;
padding:14px 22px;margin:4px 12px 4px 0;transform:rotate(-6deg);
clip-path:polygon(50% 0%,61% 12%,75% 5%,79% 19%,94% 17%,93% 32%,107% 35%,100% 47%,110% 58%,97% 63%,100% 78%,86% 78%,83% 93%,70% 88%,61% 100%,53% 88%,39% 95%,36% 81%,21% 83%,22% 68%,8% 65%,14% 53%,4% 42%,17% 37%,14% 22%,28% 22%,32% 8%,44% 13%)}
.rv-oath{background:#141414;color:#ffd93b;border:3px solid #0a0a0a;
box-shadow:6px 6px 0 #b4432f;padding:14px 18px;margin:14px 0;text-align:center;
font-family:'Bangers',Impact,sans-serif;font-size:clamp(20px,3vw,30px);
letter-spacing:.08em}
.rv-src{font-size:.8rem;color:#5a6672}
div[data-testid="stMetric"]{background:#fffdf7;border:3px solid #0a0a0a;
box-shadow:5px 5px 0 #0a0a0a;padding:10px;transform:rotate(-.4deg)}
div[data-testid="stMetricValue"]{font-family:'Bangers',Impact,sans-serif}
div[data-testid="stButton"] button,div[data-testid="stLinkButton"] a{
font-family:'Bangers',Impact,'Arial Black',sans-serif !important;
font-size:1.1rem !important;letter-spacing:.05em !important;text-transform:uppercase;
background:#ffd93b !important;color:#141414 !important;
border:3px solid #0a0a0a !important;border-radius:0 !important;
box-shadow:4px 4px 0 #0a0a0a !important}
div[data-testid="stButton"] button:hover,div[data-testid="stLinkButton"] a:hover{
transform:translate(-1px,-1px);box-shadow:5px 5px 0 #0a0a0a !important}
button[data-testid="stTab"]{font-weight:800 !important;text-transform:uppercase;
letter-spacing:.03em}
button[data-testid="stTab"][aria-selected="true"]{color:#b4432f !important}
div[data-testid="stExpander"]{border:2px solid #0a0a0a;background:#fffdf7}
</style>"""


def _comic_boot():
    """Inject the comic stylesheet once per session (idempotent)."""
    if st.session_state.get("_comic_booted"):
        return
    st.session_state["_comic_booted"] = True
    st.markdown(_COMIC_CSS, unsafe_allow_html=True)


def _comic_masthead():
    """Cover banner. Static HTML — no widgets, no state, no queries."""
    st.markdown(
        """<div class="rv-cover">
<div class="rv-kicker">THE REAL WINDY CITY PRESENTS</div>
<div class="rv-title">HEROES OF THE PUBLIC RECORD</div>
<div class="rv-issue"><span>ISSUE #001</span><span>CHEYENNE · WYOMING</span>
<span>EVERY PANEL SOURCED</span></div>
<div class="rv-tagline">Wind belongs on the prairie. Not in the minutes.</div>
<div class="rv-strip">🦸 THE ROSTER IS REAL — mic'd, minuted, or published, every
one of them · NO SECRET IDENTITIES: the record is the superpower ·
<strong>NEW HEROES WANTED</strong> — your three minutes are waiting ↓</div>
</div>""",
        unsafe_allow_html=True,
    )


_GH = "https://github.com/bartimoussmith-oss/therealwindycity/blob/main/"
_TIP = ("https://github.com/bartimoussmith-oss/therealwindycity/"
        "issues/new?template=tip.md")


def _view_roster():
    st.subheader("🦸 Meet the Roster — heroes of the public record")
    st.markdown(
        "Every hero below earned their panel **on the record** — quoted from "
        "meeting tapes, minutes, or published reporting, with the canon linked "
        "under each card. Powers are metaphor. The record is not.")
    st.markdown(
        """<div class="rv-hero"><h2>CHARLES MILLER</h2>
<div class="aka">“THE PERMANENT RECORD” · a.k.a. THE ZOOM CALLER ·
HEADLINER — Legal / Record Wing</div>
<div class="rv-stats"><span>484 STATEMENTS</span><span>59 MEETINGS</span>
<span>132 INTERRUPTIONS SURVIVED</span><span>20 MONTHS</span>
<span>7H 44M LONGEST NIGHT</span></div>
<div><span class="rv-pow">POW!</span>
<span class="rv-power">🎙 THE LONG MIC</span>
<span class="rv-power">📜 VERBATIM RECALL</span>
<span class="rv-power">⚖ THE TOPANGA KEY</span>
<span class="rv-power">🎯 ADMISSION HUNTING</span>
<span class="rv-power">🌙 THE 1:41 A.M. CLOSER</span></div>
<p><b>Origin story:</b> the Farm Wars (late 2025) → the Highlands Circuit —
seven meetings, ≈68 documented turns → the July 13 finale, adjourned
1:41 a.m.: <i>“The trap is sprung. See you in district court.”</i>
The city's own lawyer confirmed the substance of his central doctrine as
Wyoming law on July 6 — disputing only its name.</p>
</div>""",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"[📖 Full dossier: `miller-dossier.md`]({_GH}miller-dossier.md) · "
        f"[🎙 The Zoom Caller]({_GH}miller-the-zoom-caller.md) · "
        f"[🗄 Canon index]({_GH}miller-canon-index.md)")
    left, right = st.columns(2)
    with left:
        st.markdown(
            """<div class="rv-card"><h3>📋 THE PETITIONERS</h3>
<p><b>Electoral Wing</b> — Madrid (referendum organizer; the Madrid
hold petition) · Huylar · Hasenauer · Chirro (Ward 1). Madrid speaks
the doctrine on the mic himself: <i>“arbitrary and capricious because
there's no plan at all.”</i></p>
<span class="rv-power">POWER: THE GROUND GAME</span></div>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            """<div class="rv-card"><h3>🎤 THE PUBLIC BODY</h3>
<p><b>Street Wing</b> — 20+ repeat mic-takers filling hours: Scigliano,
McAdams, Nicely, Leech, Kamargo, Tolman, Duncan… plus Don Taylor, who
read the national numbers into the record (833 groups · 49 states ·
300+ bills). Politics on the Plaza. The Capitol, 7/19.</p>
<span class="rv-power">POWER: BODIES IN THE ROOM</span></div>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            """<div class="rv-card"><h3>⚙ THE ENGINE</h3>
<p><b>Archive Wing</b> — fingerprints every published page, catches
silent edits by hash, and sweeps every six hours (hourly on meeting
nights). It never sleeps so the record never blinks.</p>
<span class="rv-power">POWER: NEVER SLEEPS</span></div>""",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            """<div class="rv-card"><h3>🗳 THE DISSENTING BLOC</h3>
<p><b>3 of 10</b> — Wolf · Moody · Laybourn. The moratorium (Moody the
lone yes, 8–1) · the $50M community-benefits push · the delay
amendments. Every one failed. Every one is <b>on the record</b>.</p>
<span class="rv-power">POWER: THE RECORDED NO</span></div>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            """<div class="rv-card"><h3>📡 THE SIGNAL</h3>
<p><b>Media Wing</b> — “The Real Windy City”: founded March 30, 2026,
<i>before</i> the Highlands petition existed. 91 followers, 16K-view
flagship reel, group-seeded reach — plus the Citizen Action Directory:
how to fight city hall for $0.00.</p>
<span class="rv-power">POWER: THE 16K REACH</span></div>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            """<div class="rv-card"><h3>📰 THE PRESS CORPS</h3>
<p><b>Fourth-Estate Allies</b> — the published reporting this ledger
stands on: Cap City News · Cowboy State Daily · Wyoming Tribune Eagle ·
and the legislators who answered on the record.</p>
<span class="rv-power">POWER: INK THAT STICKS</span></div>""",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"<p class='rv-src'>Roster mapped from the movement's own ecosystem map "
        f"(`miller-dossier.md` §10) + the published timeline. The Roster honors "
        f"on-the-record acts — mic, minutes, or ink. "
        f"[Read the map]({_GH}miller-dossier.md).</p>",
        unsafe_allow_html=True,
    )
    with st.expander("🦹 Know the enemy — FORCES, not faces"):
        st.markdown(
            "This book has no secret villains with names. People get **quoted**; "
            "**forces** get fought:")
        st.markdown(
            "- 🌫 **THE SILENT EDIT** — published pages that change with no "
            "changelog. (This ledger fingerprints every one.)\n"
            "- 🔨 **THE GAVEL** — 132 interruptions and counting. Every cut "
            "microphone is an exhibit.\n"
            "- 🌀 **THE MAZE** — portals citizens can't navigate. The archive "
            "exists to walk them through it.\n"
            "- ✅ **THE RUBBER STAMP** — 8–1s and 0–9s without findings. The "
            "Roster's answer is always the same: put it on the record.\n"
            "- ⬛ **THE REDACTION** — what they won't print, the Engine "
            "re-checks every six hours.")
    st.markdown('<div class="rv-oath">READ THE STATUTE · QUOTE THE RECORD '
                '· SIGN YOUR NAME</div>', unsafe_allow_html=True)
    st.button("✋ Join the Roster", key="roster_cta", on_click=_join_jump,
              use_container_width=True)


def _join_jump():
    """Sidebar + roster CTAs land here (runs pre-script, like _guide_jump)."""
    st.session_state["ledger_section"] = "✋ Join the Roster"


def _view_recruit():
    st.subheader("✋ Your Power Awaits — new heroes wanted")
    st.markdown(
        """<div class="rv-hero"><h2>EVERYBODY'S GOT IT IN THEM</h2>
<p>Courage is the only origin story that matters. Every power on the
Roster started the same way: <b>one citizen, one mic, three minutes.</b>
No cape required. No permission needed. The mic is public — and the
next panel is yours.</p>
</div>""",
        unsafe_allow_html=True,
    )
    st.markdown("### ⚡ Choose your power")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            """<div class="rv-card"><h3>🎙 TAKE THE MIC</h3>
<p>Three minutes at public comment moves text — 'verify' survived a
warrant ordinance because somebody showed up and said the words.</p></div>""",
            unsafe_allow_html=True,
        )
        st.link_button("📻 Remote-speaker kit",
                       f"{_GH}remote-speaker-kit-2026-08-24.md")
        st.link_button("🗒 Study a speaking file",
                       f"{_GH}MILLER-speaking-file-8-24-26.md")
    with c2:
        st.markdown(
            """<div class="rv-card"><h3>📨 SEND A SIGNAL</h3>
<p>See something first? A URL, a document hash, a meeting timestamp, a
verbatim quote — verifiable tips only. Never rumors.</p></div>""",
            unsafe_allow_html=True,
        )
        st.link_button("📥 File a tip (issue form)", _TIP)
        st.markdown(
            """<div class="rv-card"><h3>📜 FILE THE PAPERWORK</h3>
<p>Wyoming Public Records Act drafts — the machine drafts, <b>you</b>
sign and send. Open ✉️ Signals &amp; Paperwork → Paperwork Arsenal.</p>
</div>""",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """<div class="rv-card"><h3>🎬 CUT THE TAPE</h3>
<p>Watch the montages, share the reels, learn the exhibits. Open the
<b>Screening Room</b> page (sidebar, under the console).</p></div>""",
            unsafe_allow_html=True,
        )
        st.page_link("pages/1_Screening_Room.py", label="🎬 Open Screening Room")
        st.markdown(
            """<div class="rv-card"><h3>🗳 SHOW UP</h3>
<p>Meetings run Monday/Tuesday nights — the Engine sweeps hourly those
nights for a reason. And circle <b>November 3, 2026</b>.</p></div>""",
            unsafe_allow_html=True,
        )
    st.markdown("### 🗺 Your first mission (this week)")
    st.markdown(
        "1. **Watch one tape** — 🎬 The Tapes → Montage Theater (start with "
        "THE CALLER).\n"
        "2. **Read one fight** — 📰 The Daily Ledger, top alert, then the "
        "linked record.\n"
        "3. **Take one action** — send a signal, file a records request, or "
        "take the mic. Then tell the Roster how it went (same mailbox).")
    st.markdown('<div class="rv-oath">READ THE STATUTE · QUOTE THE RECORD '
                '· SIGN YOUR NAME</div>', unsafe_allow_html=True)
    st.caption("No affiliation with any individual, candidate, or committee — "
               "then, now, always. Powers are metaphor; the record is real.")



def _view_home():
    page = ROOT / "public" / "index.html"
    st.caption("📰 The front page — reprinted fresh every scheduler cycle.")
    if page.exists():
        components.html(page.read_text(), height=3200, scrolling=True)
    else:
        st.info("public/index.html not built yet — civic-cycle builds it.")
def _view_alerts():
    st.subheader("🚩 Action Alerts — tripwires with verbatim quotes + linked records")
    rows = _engine_q("SELECT a.created_at, a.term, a.snippet, d.url, d.title "
                     "FROM alerts a JOIN documents d ON d.id=a.document_id "
                     "ORDER BY a.id DESC LIMIT 300")
    if not rows:
        st.info("Engine ledger empty here — civic-cycle will fill it.")
    for r in rows:
        with st.expander(f"{r['created_at']} · {r['term']} · {r['title']}"):
            st.markdown(f"> {r['snippet']}")
            st.markdown(f"[source record]({r['url']})")
def _view_edits():
    st.subheader("⚠️ Shape-Shifters Caught — silent edits fingerprinted by SHA-256 drift")
    rows = _engine_q("SELECT v.captured_at, v.seq, v.change_summary, d.url, d.title "
                     "FROM versions v JOIN documents d ON d.id=v.document_id "
                     "WHERE v.seq>1 ORDER BY v.id DESC")
    if rows:
        for r in rows:
            st.warning(f"**{r['title']}** — seq {r['seq']} · {r['captured_at']} · "
                       f"{r['change_summary']} · [source]({r['url']})")
    else:
        st.success("None yet. A quiet ledger is a true report.")
def _view_search():
    if db is None or not ENGINE_DB.exists():
        st.info("Engine not present.")
    else:
        q = st.text_input("Plain-English query over every captured document",
                          "annexation")
        if q:
            conn = db.connect()
            hits = db.search(conn, q)
            conn.close()
            st.caption(f"{len(hits)} document(s) match")
            for r in hits:
                st.markdown(f"**doc #{r['doc_id']}** · `{r['source']}` · {r['title']}")
                if r.get("snip"):
                    st.markdown(f"> {r['snip']}")
def _view_paperwork():
    st.info("Drafts are review-and-send. The machine does not mail letters; "
            "you sign, you send.")
    for r in _engine_q("SELECT id, kind, subject, created_at, body FROM requests "
                       "ORDER BY id DESC LIMIT 50"):
        with st.expander(f"#{r['id']} [{r['kind']}] {r['subject']} · {r['created_at']}"):
            st.markdown(r["body"])

# ---------- digest ----------------------------------------------------
def _view_digest():
    st.subheader("📰 The Daily Ledger — what moved lately")
    week = (datetime.now(timezone.utc) - timedelta(days=7)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    new_alerts = _engine_q("SELECT COUNT(*) n FROM alerts WHERE created_at>=?",
                           (week,))[0]["n"]
    new_docs = _engine_q("SELECT COUNT(*) n FROM documents WHERE first_seen>=?",
                         (week,))[0]["n"]
    new_edits = _engine_q("SELECT COUNT(*) n FROM versions WHERE seq>1 AND "
                          "captured_at>=?", (week,))[0]["n"]
    a, b, c = st.columns(3)
    a.metric("New watchlist hits (7 days)", new_alerts)
    b.metric("New documents fingerprinted (7 days)", new_docs)
    c.metric("Shape-shifters (7 days)", new_edits)
    st.markdown("**Latest documents on the wire**")
    st.dataframe(_engine_q("SELECT title, source, last_checked, size_bytes "
                           "FROM documents ORDER BY last_checked DESC LIMIT 15"),
                 use_container_width=True, hide_index=True)
    for cand in ("public/digest.md", "public/digest.html"):
        fp = ROOT / cand
        if fp.exists():
            st.markdown("**Cycle digest (published)**")
            (st.markdown if cand.endswith(".md") else
             lambda t: components.html(t, height=600, scrolling=True))(
                fp.read_text(errors="replace"))

# ---------- recovered vault tabs (with verification bridge) ---------
def _view_battles():
    ver = _vault_ver()
    st.warning(VAULT_BANNER)
    st.subheader("⚔️ Battle Records — every statutory clash, blow by blow")
    rows = _legacy_q(VAULT_QUERIES["public_comment_battles"])
    for i, r in enumerate(rows):
        v = _verdict(ver, "public_comment_battles", i)
        r["record_evidence"] = ("✅ " + v["hits"][0]["file"] +
                                (f" ({v['hits'][0]['date']})"
                                 if v["hits"][0]["date"] else "")) if v else "—"
    st.dataframe(rows, use_container_width=True, hide_index=True)
    outcomes = {}
    for r in rows:
        outcomes[r["outcome_status"] or "unknown"] = outcomes.get(
            r["outcome_status"] or "unknown", 0) + 1
    if outcomes:
        st.caption("Outcomes")
        st.bar_chart(outcomes)
def _view_veracity():
    ver = _vault_ver()
    st.warning(VAULT_BANNER)
    st.subheader("🔍 The Lie Detector — documented say/unsay pairs")
    for i, r in enumerate(_legacy_q(VAULT_QUERIES["veracity_contradictions"])):
        with st.container(border=True):
            st.markdown(f"**{r['topic']}** — {r['contradiction_type']}")
            a, b = st.columns(2)
            a.error(f"First position ({r['speaker_denial']}, {r['date_denial']}):\n\n"
                    f"_{r['quote_denial']}_")
            b.info(f"Later record ({r['speaker_validation']}, "
                   f"{r['date_validation']}):\n\n_{r['quote_validation']}_")
            v = _verdict(ver, "veracity_contradictions", i)
            if v:
                h = v["hits"][0]
                st.success(f"✅ Found in the record: `{h['file']}`"
                           + (f" — meeting of {h['date']}" if h["date"] else ""))
                with st.expander("Matched context from the transcript"):
                    st.markdown(f"> …{h['context']}…")
            else:
                st.caption(f"Seed significance: {r['significance']} · "
                           f"not yet matched in the transcript corpus — a lead, "
                           f"not a fact.")
def _view_vouchers():
    ver = _vault_ver()
    st.warning(VAULT_BANNER)
    st.subheader("🧾 The Money Trail — every dollar claim, tracked")
    rows = _legacy_q(VAULT_QUERIES["voucher_forensics"])
    for i, r in enumerate(rows):
        v = _verdict(ver, "voucher_forensics", i)
        r["record_evidence"] = ("✅ " + v["hits"][0]["file"]) if v else "—"
    tot = sum(r["amount"] or 0 for r in rows)
    c1, c2 = st.columns(2)
    c1.metric("Vault-tracked spend", f"${tot:,.2f}")
    c2.metric("Rows matched to corpus this cycle",
              sum(1 for r in rows if r["record_evidence"] != "—"),
              delta="next: attach check-register URLs", delta_color="off")
    st.dataframe(rows, use_container_width=True, hide_index=True)
    by_dept = {}
    for r in rows:
        by_dept[r["department"] or "unknown"] = (
            by_dept.get(r["department"] or "unknown", 0) + (r["amount"] or 0))
    if by_dept:
        st.caption("Spend by department ($)")
        st.bar_chart(by_dept)
def _view_environment():
    ver = _vault_ver()
    st.warning(VAULT_BANNER)
    st.subheader("☣️ The Toxic Files — environmental evidence")
    rows = _legacy_q(VAULT_QUERIES["environmental_zones"])
    for i, r in enumerate(rows):
        v = _verdict(ver, "environmental_zones", i)
        r["record_evidence"] = ("✅ " + v["hits"][0]["file"]) if v else "—"
    st.dataframe(rows, use_container_width=True, hide_index=True)

# ---------- minutes archive -------------------------------------------
def _view_minutes():
    st.subheader("📜 17 Years of Tapes — search the whole minutes archive")
    if not CORPUS_DIR.is_dir():
        st.info("The transcript corpus (pipeline/corpus/) isn't in this "
                "checkout. It rides along automatically once the repo "
                "carrying it is deployed.")
    else:
        files = sorted(CORPUS_DIR.glob("*.txt"))
        sig = (len(files), max((f.stat().st_mtime for f in files), default=0))
        corpus = _corpus(str(ROOT), sig)
        dates = sorted({d["date"] for d in corpus if d["date"]})
        st.caption(f"{len(corpus)} transcripts indexed"
                   + (f" · {dates[0]} → {dates[-1]}" if dates else "")
                   + " · verbatim context, hand-verifiable with ctrl-F")
        q = st.text_input("Search every word (all terms must appear)",
                          "annexation", key="corpus_q")
        if q and corpus_search is not None:
            hits = corpus_search.search(corpus, q)
            st.caption(f"{len(hits)} transcript(s) match")
            for h in hits:
                with st.expander(f"{h['date'] or 'undated'} · {h['file']}"):
                    st.markdown(f"> …{h['snippet']}…")

# ---------- tips ------------------------------------------------------
def _view_tips():
    st.subheader("💡 Send a Signal — got something the Roster should see?")
    st.markdown(
        "The machine watches published sources; people see things first. A good "
        "tip is **verifiable**: a URL, a document (with `sha256sum`), a meeting "
        "number + timestamp, or a verbatim quote — never a rumor.")
    st.link_button("📥 Send a Signal — file a tip (GitHub issue form)",
                   "https://github.com/bartimoussmith-oss/therealwindycity/"
                   "issues/new?template=tip.md")
    st.caption("Tips are read by a human. This mailbox never triggers letters or "
               "contact with officials on its own.")

# ---------- canon library ---------------------------------------------
def _view_canon():
    st.subheader("🗄 The Longboxes — every dossier in the canon")
    st.caption("Root-level Markdown only. The uploads/ archive (~70 MB) stays "
               "out of the reader on purpose — use intake.py's reports for it.")
    docs = []
    for fp in sorted(ROOT.glob("*.md")):
        if fp.name in SKIP:
            continue
        raw = fp.read_text(errors="replace")
        words = len(raw.split())
        docs.append({"name": fp.name, "series": _canon_series(fp.name),
                     "words": words, "read_min": max(1, round(words / 200)),
                     "excerpt": " ".join(raw.split())[:220], "body": raw})
    st.caption(f"{len(docs)} documents · "
               + " · ".join(f"{s}: {sum(1 for d in docs if d['series']==s)}"
                            for s in dict.fromkeys(d['series'] for d in docs)))
    col_a, col_b = st.columns([1, 2])
    series_pick = col_a.selectbox("Series", ["All"] + sorted({d["series"] for d in docs}),
                                   key="canon_series")
    term = col_b.text_input("Search titles + excerpts", "", key="canon_term")
    view = [d for d in docs
            if (series_pick == "All" or d["series"] == series_pick)
            and (term.lower() in (d["name"] + d["excerpt"]).lower())]
    for d in view:
        with st.expander(f"{d['series']} · **{d['name']}** — {d['words']:,} words "
                         f"(~{d['read_min']} min)"):
            st.caption(d["excerpt"] + "…")
            if d["words"] > 4000:
                st.caption("Large file — rendering first section; open the repo file "
                           "for the full text.")
                st.markdown(d["body"][:15000])
            else:
                st.markdown(d["body"])
def _view_video():
    st.subheader("🎬 Montage Theater — the record on tape")
    st.caption("Produced segments and evidence clips cut from the City of "
               "Cheyenne's official meeting video (public record), plus "
               "every indexed city meeting on the city's YouTube channel.")
    REN = ROOT / "pipeline" / "renders"
    VID = ROOT / "pipeline" / "videos"
    try:
        cv = json.loads((ROOT / "pipeline" / "cityvideos.json").read_text())
    except Exception:
        cv = {}

    segs = sorted(REN.glob("*.mp4")) if REN.is_dir() else []
    if segs:
        st.markdown("**🔥 Origin Tapes — produced segments (captioned)**")
        seg = st.selectbox("Segment", segs,
                           format_func=lambda p: p.stem.replace("_", " "),
                           key="vv_seg")
        sub = seg.with_suffix(".vtt")
        st.video(str(seg), subtitles=str(sub) if sub.exists() else None)
        posts = {f.name: f for f in REN.glob("POST_*.txt")}
        stem = seg.stem
        post = posts.get("POST_ALL_FIVE.txt") if stem[:2] in (
            "S1", "S2", "S3", "S4", "S5") else None
        post = next((f for n, f in posts.items()
                     if n[5:-4] and n[5:-4] in stem), post)
        if post:
            with st.expander("Post copy for this segment"):
                st.caption(post.read_text(errors="replace")[:2000])
    else:
        st.info("No produced segments under pipeline/renders/ yet.")

    clips = sorted(VID.glob("*.mp4")) if VID.is_dir() else []
    if clips:
        st.markdown("**Evidence clips — verified tape**")
        clip = st.selectbox("Clip", clips,
                            format_func=lambda p: p.stem.replace("_", " "),
                            key="vv_clip")
        st.video(str(clip))
        TAPE = {"apr27": "2026-04-27", "mar9": "2026-03-09"}
        dkey = next((d for p, d in TAPE.items()
                     if clip.stem.startswith(p + "_")), None)
        info = (cv.get("verified_tape", {}).get(dkey) or {}) if dkey else {}
        ytid = info.get("id")
        if ytid:
            secs = 0
            if info.get("cut_at"):
                secs = sum(v * 60 ** i for i, v in enumerate(
                    reversed([int(x) for x in info["cut_at"].split(":")])))
            t = "&t=%ds" % secs if secs else ""
            st.markdown(
                f"Full meeting ({dkey}): [youtube.com/watch?v={ytid}{t}]"
                f"(https://www.youtube.com/watch?v={ytid}{t})"
                + (f" — {info['note']}" if info.get("note") else ""))
    else:
        st.info("No evidence clips under pipeline/videos/ yet.")

    meets = cv.get("meetings", {})
    if meets:
        st.markdown("**Full meetings — City of Cheyenne YouTube channel**")
        mdate = st.selectbox("Meeting date", sorted(meets, reverse=True),
                             key="vv_meet")
        minfo = meets.get(mdate) or {}
        ytid = minfo.get("id") if isinstance(minfo, dict) else minfo
        if ytid:
            st.video(f"https://www.youtube.com/watch?v={ytid}")
        st.caption("Live Granicus captions remain out of scope (no VTT "
                   "served); auto-captions are pullable via yt-dlp — see "
                   "pipeline/cityvideos.json.")
# Sidebar sections: label -> [(tab label, view function)]. Views render inside
# per-section sub-tabs; single-view sections skip the sub-tab strip entirely.
# ---------------------------------------------------------------------------
# Choose-Your-Mission guide — an adaptive question wizard. Six stages: who → what →
# specifics → drill-down → depth → brief. Deliberately a plain, auditable
# rules engine (no model, no tracking): every recommendation carries its
# because-of, the fired rules land in an audit panel, and answers live only
# in this browser session. The complexity is in the branching, not the
# burden — a viewer answers a handful of questions; the tree behind them is
# deep, because follow-ups only appear for the topics they picked.
# ---------------------------------------------------------------------------

GUIDE_ROLES = [
    ("I live inside Cheyenne city limits", "city"),
    ("I live in Laramie County, outside the city", "county"),
    ("I own or run a business here", "business"),
    ("I'm not local — I'm following the story", "observer"),
    ("I'm a reporter or researcher", "press"),
]

GUIDE_TOPICS = [
    ("My water bill and the city's water supply", "water"),
    ("My property taxes and how the city spends money", "money"),
    ("The data-center boom — annexations, ranch land, power", "datacenter"),
    ("Roads and construction where I live", "roads"),
    ("Groundwater, air, and environmental review", "environment"),
    ("How meetings run — agendas, minutes, edits, closed doors", "process"),
    ("What specific officials say and do", "officials"),
    ("Ballots and elections, including the Nov 3 contest", "elections"),
]

GUIDE_BOOLEANS = [
    ("g_owner", "I own my home (property taxes hit me directly)", "money"),
    ("g_tap", "I drink city tap water", "water"),
    ("g_west", "I live west of town, near the Belvoir–High Plains corridor", None),
    ("g_voter", "I voted in the last city election", "elections"),
    ("g_watcher", "I've watched or attended a city meeting", "process"),
]

# Per-topic follow-ups — rendered ONLY for topics the viewer picked.
GUIDE_FOLLOWUPS = {
    "water": ("What's the water concern, specifically?", [
        ("What I'm paying", "w-bill"),
        ("Supply and drought capacity", "w-supply"),
        ("Groundwater contamination risk", "w-ground"),
        ("Hookups for new development", "w-hookups"),
    ]),
    "money": ("How deep do you want to follow the money?", [
        ("Just the headlines", "m-head"),
        ("Voucher line items", "m-voucher"),
        ("The capital-projects list", "m-capital"),
        ("Pull the receipts myself (PRA)", "m-pra"),
    ]),
    "datacenter": ("Which angle on the data-center boom?", [
        ("Land and annexation votes", "d-land"),
        ("Power and water demand", "d-power"),
        ("Jobs and tax-abatement claims", "d-jobs"),
        ("What it means for my street", "d-near"),
    ]),
    "environment": ("Which environmental concern?", [
        ("Groundwater", "e-ground"),
        ("Air quality", "e-air"),
        ("How review actually happens", "e-review"),
    ]),
    "process": ("What bothers you about how meetings run?", [
        ("Agendas that change late", "p-agenda"),
        ("Documents edited after the fact", "p-edits"),
        ("Closed sessions and executive excuses", "p-closed"),
        ("Getting a word in (public comment)", "p-comment"),
    ]),
    "officials": ("Whose conduct are you tracking?", [
        ("Mayor and council overall", "o-council"),
        ("One specific official", "o-person"),
        ("The candidates on Nov 3", "o-candidates"),
    ]),
    "elections": ("Elections — what do you need?", [
        ("The referendum questions", "el-ref"),
        ("Council and mayoral races", "el-races"),
        ("How and where to vote", "el-mech"),
    ]),
    "roads": ("Roads — what kind of issue?", [
        ("A specific project near me", "r-project"),
        ("Maintenance and potholes", "r-maint"),
        ("The capital plan for streets", "r-capital"),
    ]),
}

GUIDE_DEPTH = [("⚡ Two minutes", 4), ("☕ One evening", 7), ("🦉 The full dive", 99)]
GUIDE_FORMAT = ["📖 Read the record", "🎬 Watch the tape",
                "🔎 Search it myself", "🔔 Get updates"]
GUIDE_STAGES = 6
_STAGE_NAMES = ["who you are", "what touches you", "a few specifics",
                "drill-down", "how deep", "your brief"]


def _guide_jump(section, q=None, canon=None):
    """Send the viewer to a section, optionally preloading its search box."""
    st.session_state["ledger_section"] = section
    if q is not None:
        st.session_state["corpus_q"] = q
    if canon is not None:
        st.session_state["canon_term"] = canon


def _gval(key, default=None):
    """Read a wizard answer. Streamlit prunes widget-key state once the
    widget stops rendering, so the Next/Back buttons snapshot every stage
    into w_-prefixed plain keys; live widget value wins when present."""
    s = st.session_state
    if key in s:
        return s[key]
    return s.get("w_" + key, default)


def _guide_snapshot():
    """Copy the current stage's live widget values into plain session keys."""
    s = st.session_state
    for k in ("g_role", "g_topics", "g_depth", "g_format"):
        if k in s:
            s["w_" + k] = s[k]
    for k, _lbl, _tag in GUIDE_BOOLEANS:
        if k in s:
            s["w_" + k] = s[k]
    for t in GUIDE_FOLLOWUPS:
        if f"f_{t}" in s:
            s["w_f_" + t] = s[f"f_{t}"]


def _guide_next():
    _guide_snapshot()
    st.session_state["g_step"] = min(GUIDE_STAGES,
                                     st.session_state.get("g_step", 1) + 1)


def _guide_back():
    _guide_snapshot()
    st.session_state["g_step"] = max(1, st.session_state.get("g_step", 1) - 1)


def _guide_restart():
    protected = ("ledger_section", "g_restart")
    for k in list(st.session_state):
        if (k.startswith(("g_", "f_", "w_")) and not k.endswith("_btn")
                and k not in protected):
            del st.session_state[k]


def _guide_answers():
    """(tags, sub-choices) from the session — single source of truth."""
    role = dict(GUIDE_ROLES).get(_gval("g_role", "") or "", "")
    topics = _gval("g_topics") or []
    tags = {role} | {t for lbl, t in GUIDE_TOPICS if lbl in topics}
    for key, _lbl, tag in GUIDE_BOOLEANS:
        if _gval(key) and tag:
            tags.add(tag)
    if _gval("g_west"):
        tags |= {"datacenter", "environment"}
    sub = {}
    for t, (_q, opts) in GUIDE_FOLLOWUPS.items():
        if t in tags:
            m = dict(opts).get(_gval(f"f_{t}", "") or "")
            if m:
                sub[t] = m
    return tags, sub


def _view_guide():
    st.subheader("🧭 Choose Your Mission — get *your* brief, not the whole haystack")
    st.caption("A short adaptive interview: who you are, what touches you, "
               "how deep you want to go. Plain rules under the hood — the "
               "audit panel shows every rule that fired. Nothing you pick "
               "leaves your browser.")
    step = st.session_state.get("g_step", 1)
    st.progress(step / GUIDE_STAGES)
    left, right = st.columns([3, 1])
    left.caption(f"Step {step} of {GUIDE_STAGES} · {_STAGE_NAMES[step - 1]}")
    if step < GUIDE_STAGES:
        right.button("Next →", key="g_next_btn", on_click=_guide_next,
                     type="primary")
    else:
        right.button("↺ Start over", key="g_restart", on_click=_guide_restart)
    if step > 1:
        st.button("← Back", key="g_back_btn", on_click=_guide_back)

    if step == 1:
        opts = [lbl for lbl, _ in GUIDE_ROLES]
        cur = _gval("g_role")
        st.radio("Who are you here as?", opts, key="g_role",
                 index=opts.index(cur) if cur in opts else 0)
    elif step == 2:
        opts = [lbl for lbl, _ in GUIDE_TOPICS]
        cur = _gval("g_topics") or []
        st.multiselect("Which of these touch your life? (pick any)", opts,
                       key="g_topics",
                       default=[o for o in cur if o in opts])
    elif step == 3:
        st.markdown("Check what's true for you — every check widens the net:")
        for key, lbl, _tag in GUIDE_BOOLEANS:
            st.checkbox(lbl, key=key, value=bool(_gval(key)))
    elif step == 4:
        tags, _ = _guide_answers()
        ups = [(t, q) for t, (q, _o) in GUIDE_FOLLOWUPS.items() if t in tags]
        if ups:
            st.markdown("Fine-tuning — one follow-up per topic you picked:")
            for t, question in ups:
                opts = [lbl for lbl, _ in GUIDE_FOLLOWUPS[t][1]]
                cur = _gval(f"f_{t}")
                st.radio(question, opts, key=f"f_{t}",
                         index=opts.index(cur) if cur in opts else 0)
        else:
            st.info("No topics picked — nothing to drill into. Go Back and "
                    "pick some, or Next for your baseline brief.")
    elif step == 5:
        dopts = [lbl for lbl, _ in GUIDE_DEPTH]
        dcur = _gval("g_depth")
        st.radio("How deep do you want to go right now?", dopts,
                 key="g_depth", index=dopts.index(dcur) if dcur in dopts else 1)
        fopts = GUIDE_FORMAT
        fcur = _gval("g_format")
        st.radio("And how do you like your evidence?", fopts, key="g_format",
                 index=fopts.index(fcur) if fcur in fopts else 0)
    else:
        _render_brief()


def _render_brief():
    tags, sub = _guide_answers()
    trace = []

    def T(why):
        trace.append(why)

    recs = []

    def add(title, because, section, match, q=None, canon=None, nxt=None):
        for m in match:
            T(f"“{title}” ← {m}")
        recs.append({"title": title, "because": because, "section": section,
                     "q": q, "canon": canon, "nxt": nxt,
                     "score": float(len(match))})

    if "money" in tags:
        m = ["you flagged taxes and spending"]
        if _gval("g_owner"):
            m.append("you own your home")
        add("Follow the money — the voucher forensics",
            "The vault tracks spending line by line with the receipts "
            "attached — worth ten minutes of anyone's property-tax bill.",
            "🗃 Case Files", m,
            nxt=("Then search the minutes for “voucher”", "🔎 Evidence Vault",
                 "voucher", None))
        add("Watch “S2: The 74M List”",
            "The film cut of the capital-project list — the fastest way to "
            "see what the money argument is actually about.",
            "🎬 The Tapes", ["taxes and spending"])
        add("Search 17 years of minutes for “6th penny”",
            "Every time the sales-tax question came up, verbatim, with "
            "meeting dates attached.", "🔎 Evidence Vault",
            ["taxes and spending"], q="6th penny")
        if sub.get("money") == "m-voucher":
            add("The voucher tables, row by row",
                "You chose line items — the Money Trail view is the table "
                "itself, sources linked per row.", "🗃 Case Files",
                ["you chose voucher line items"])
        if sub.get("money") == "m-capital":
            add("The capital-projects paper trail",
                "You chose the capital list — here's every capital motion "
                "in the record.", "🔎 Evidence Vault",
                ["you chose the capital list"], q="capital")
        if sub.get("money") == "m-pra":
            add("The PRA drafting bench",
                "You chose to pull the receipts yourself — these are "
                "filled-in Wyoming PRA drafts waiting for a human to send.",
                "✉️ Signals & Paperwork", ["you chose: pull the receipts yourself"])
    if "water" in tags:
        m = ["you flagged water"]
        if _gval("g_tap"):
            m.append("you drink the tap water")
        add("Your water, on the record",
            "The environmental matrix keeps the water and groundwater items "
            "in one place, each linked to its source document.",
            "🗃 Case Files", m)
        add("Search the minutes for “water”",
            "Moratorium votes, utility extensions, supply studies — the "
            "paper trail behind whatever ends up in your bill.",
            "🔎 Evidence Vault", ["you flagged water"], q="water")
        if sub.get("water") == "w-supply":
            add("BOPU — the water utility's own record",
                "You chose supply — every mention of the Board of Public "
                "Utilities, verbatim.", "🔎 Evidence Vault",
                ["you chose supply and drought capacity"], q="BOPU")
        if sub.get("water") == "w-ground":
            add("Groundwater, everywhere it appears",
                "You chose contamination risk — this is the aquifer paper "
                "trail.", "🔎 Evidence Vault",
                ["you chose groundwater risk"], q="groundwater")
        if sub.get("water") == "w-bill":
            add("What goes into a water bill",
                "You chose cost — the rate and fee discussions, in the "
                "dossiers.", "🔎 Evidence Vault",
                ["you chose what you're paying"], canon="water")
        if sub.get("water") == "w-hookups":
            add("Utility extensions — who gets hooked up",
                "You chose new-development hookups — every extension the "
                "council has voted on.", "🔎 Evidence Vault",
                ["you chose development hookups"], q="utility extension")
    if "datacenter" in tags:
        m = ["you flagged the data-center boom"]
        if _gval("g_west"):
            m.append("you live near the corridor")
        add("The data-center boom, filed and footnoted",
            "Annexations, zoning, the ranch-land fights — the dossier line "
            "that grew this whole archive. Start with Battle Records and the "
            "data-center brief.", "🗃 Case Files", m)
        add("Watch “S1: 48 Hours”",
            "The cut that shows how fast the annexation votes moved.",
            "🎬 The Tapes", ["data-center boom"])
        add("Search the minutes for “annexation”",
            "The full paper trail, meeting by meeting.", "🔎 Evidence Vault",
            ["data-center boom"], q="annexation")
        if sub.get("datacenter") == "d-power":
            add("Power and water demand on the record",
                "You chose the power angle — every electric-capacity "
                "discussion, verbatim.", "🔎 Evidence Vault",
                ["you chose power and water demand"], q="electric")
        if sub.get("datacenter") == "d-jobs":
            add("Jobs and abatement claims, checked",
                "You chose the jobs claims — see what was promised vs. what "
                "the record shows.", "🔎 Evidence Vault",
                ["you chose jobs and abatement claims"], canon="abatement")
        if sub.get("datacenter") == "d-near":
            add("The Highlands corridors, in the dossiers",
                "You chose your street — the Highlands files are the "
                "closest to the ground.", "🔎 Evidence Vault",
                ["you chose what it means for your street"],
                canon="highlands")
    if "environment" in tags:
        add("Groundwater, air, and environmental review",
            "The environmental matrix keeps the review items in one place, "
            "each linked back to its source document.", "🗃 Case Files",
            ["you flagged the environment"])
        add("Search the minutes for “groundwater”",
            "Where the environmental record actually lives.",
            "🔎 Evidence Vault", ["you flagged the environment"], q="groundwater")
        if sub.get("environment") == "e-air":
            add("Air quality in the record",
                "You chose air — every air-quality discussion, verbatim.",
                "🔎 Evidence Vault", ["you chose air quality"], q="air quality")
        if sub.get("environment") == "e-review":
            add("How environmental review actually happens",
                "You chose the review process — permits, hearings, and "
                "what triggers what.", "🔎 Evidence Vault",
                ["you chose how review happens"], q="permit")
    if "process" in tags:
        m = ["you flagged how meetings run"]
        if _gval("g_watcher"):
            m.append("you've attended the meetings")
        add("The silent-edits wire",
            "Documents on the city site that changed after the fact — each "
            "one diffed, timestamped, and linked. This tab existing at all "
            "is the point.", "📡 Mission Board", m)
        add("How to read a meeting like an investigator",
            "The tape archive holds 17 years of verbatim transcripts, "
            "searchable word by word. Ctrl-F is a civic instrument.",
            "🔎 Evidence Vault", ["how meetings run"])
        if sub.get("process") == "p-agenda":
            add("Agenda changes, caught in the act",
                "You chose late-changing agendas — the edits wire plus the "
                "agenda history.", "🔎 Evidence Vault",
                ["you chose late agendas"], q="agenda")
        if sub.get("process") == "p-closed":
            add("Executive sessions — every claimed exception",
                "You chose closed doors — each executive session with the "
                "statute cited.", "🔎 Evidence Vault",
                ["you chose closed sessions"], q="executive session")
        if sub.get("process") == "p-comment":
            add("Public comment — how to get your three minutes",
                "You chose speaking up — the rules and the record of public "
                "comment, in one place.", "🔎 Evidence Vault",
                ["you chose public comment"], q="public comment")
    if "officials" in tags:
        add("Who said what — the veracity files",
            "First positions next to later positions, so the record does "
            "the comparing for you.", "🗃 Case Files",
            ["you flagged officials"])
        add("The tape archive",
            "Verified clips with timestamps back to the full meeting video "
            "— including the cuts that made the news. The Caller tape is "
            "the one people ask about first.", "🎬 The Tapes",
            ["you flagged officials"])
        add("The canon library, by person",
            "Every dossier on the officials and the races, organized by "
            "series.", "🔎 Evidence Vault", ["you flagged officials"],
            canon="miller")
        if sub.get("officials") == "o-candidates":
            add("The Nov 3 candidate files",
                "You chose the candidates — the election-year dossiers.",
                "🔎 Evidence Vault", ["you chose the candidates"], canon="2026")
    if "elections" in tags:
        m = ["you flagged elections"]
        if _gval("g_voter"):
            m.append("you voted last time")
        add("Ballot season, on the record",
            "The digest tracks what moved each week, and the alerts flag "
            "watchlist language within 48 hours of it posting.",
            "📡 Mission Board", m)
        add("Search the canon for “referendum”",
            "The referendum dossiers and everything filed around them.",
            "🔎 Evidence Vault", ["you flagged elections"], canon="referendum")
        if sub.get("elections") == "el-mech":
            add("How and where to vote",
                "You chose mechanics — the election-process files.",
                "🔎 Evidence Vault", ["you chose how to vote"], canon="election")
    if "roads" in tags:
        add("Roads and construction in the record",
            "Search the minutes for the street and project names you drive "
            "past — most capital work shows up in a vote before it shows "
            "up on the ground.", "🔎 Evidence Vault",
            ["you flagged roads"], q="street")
        if sub.get("roads") == "r-project":
            add("Find your specific project",
                "You chose a project near you — construction motions, "
                "verbatim.", "🔎 Evidence Vault",
                ["you chose a specific project"], q="construction")
        if sub.get("roads") == "r-maint":
            add("Maintenance and potholes — the record",
                "You chose maintenance — what the city said it would fix.",
                "🔎 Evidence Vault", ["you chose maintenance"], q="maintenance")
    if "press" in tags:
        add("Reporter's kit — full-text search",
            "FTS over everything fingerprinted, plus 17 years of "
            "transcripts. Every alert carries a verbatim quote, a source "
            "URL, and a fetch timestamp — citeable as-is.",
            "🔎 Evidence Vault", ["you're a reporter or researcher"])
        add("The PRA drafting bench",
            "Wyoming Public Records Act request drafts, filled in and "
            "ready for a human to send. Wrong-statute citations are a "
            "reporter's fastest way to get stonewalled.", "✉️ Signals & Paperwork",
            ["you're a reporter or researcher"])
    if "observer" in tags:
        add("The story so far",
            "Not local? The digest is the catch-up: what moved, when, with "
            "links.", "📡 Mission Board",
            ["you're following the story"])

    # format preference re-weights the ranking
    fmt = _gval("g_format") or ""
    boosts = {"🔔 Get updates": "📡 Mission Board",
              "🎬 Watch the tape": "🎬 The Tapes",
              "🔎 Search it myself": "🔎 Evidence Vault",
              "📖 Read the record": "🗃 Case Files"}
    if fmt in boosts:
        for r in recs:
            if r["section"] == boosts[fmt]:
                r["score"] += 0.5
        T(f"format “{fmt}” → +0.5 to {boosts[fmt]} recommendations")

    depth = dict(GUIDE_DEPTH).get(_gval("g_depth") or "☕ One evening", 7)
    recs.sort(key=lambda r: -r["score"])

    archetypes = [
        ({"datacenter", "environment"}, "Corridor watcher",
         "you live where the boom meets the water table — the annexation "
         "and groundwater threads are yours"),
        ({"water", "money"}, "Bill-and-bill taxpayer",
         "the rate discussions and the spending votes are your beat"),
        ({"process"}, "Meeting-night regular",
         "you know how the gavel sounds — now see what changes after the "
         "minutes post"),
        ({"officials"}, "Accountability tracker",
         "you follow the people, not just the votes"),
        ({"elections"}, "Ballot-season voter",
         "you show up in November — this keeps the record between elections"),
        ({"business"}, "Main-street operator",
         "fees, rates, and the boom's ripple effects are your ledger"),
        ({"press"}, "Reporter on deadline",
         "verbatim quotes, timestamps, and a PRA bench — built for citing"),
    ]
    name, desc = "Curious citizen", "the baseline brief fits everyone"
    best = 0
    for need, n, d in archetypes:
        hit = len(need & tags)
        if hit > best:
            best, name, desc = hit, n, d

    st.divider()
    if recs:
        shown = recs[:depth]
        st.info(f"**Your profile: {name}.** "
                f"In plain words, {desc}.")
        st.success(f"Your brief — {len(shown)} place"
                   f"{'s' if len(shown) != 1 else ''} to start, ranked by "
                   f"how strongly your answers pointed at them:")
        for i, r in enumerate(shown):
            with st.container(border=True):
                st.markdown(f"**{i + 1}. {r['title']}**")
                st.caption(r["because"])
                n = max(0, min(5, int(r["score"])))
                st.caption("match " + "▰" * n + "▱" * (5 - n)
                           + f"  ·  {r['score']:.1f}")
                st.button("Take me there →", key=f"g_go_{i}",
                          on_click=_guide_jump,
                          args=(r["section"], r["q"], r["canon"]))
                if depth == 99 and r["nxt"]:
                    nt, ns, nq, nc = r["nxt"]
                    st.button(f"Then: {nt}", key=f"g_nx_{i}",
                              on_click=_guide_jump, args=(ns, nq, nc))
    else:
        st.info("Nothing answered — no problem. Everyone's baseline: the "
                "**Action Alerts** and **The Daily Ledger** views under Mission Board, "
                "and **17 Years of Tapes** under Evidence Vault. Or go Back "
                "and answer a question or two and watch the brief build.")
    with st.expander("🔍 Audit these recommendations — every rule that fired"):
        if trace:
            for line in trace:
                st.markdown(f"- {line}")
        else:
            st.markdown("- (no rules fired — you answered nothing)")
        st.caption("No model, no tracking: the rules above are the entire "
                   "decision, and your answers never left this browser tab.")
    st.caption("Whoever you are: the alert feed updates itself every six "
               "hours, so the 📡 Mission Board is worth a bookmark.")


# The front-door reel: contentious moments, in order, with links to the full
# source meeting. Timestamps are cumulative starts in CONTENTION_REEL.mp4 —
# keep in sync with pipeline/build_reel.py's ORDER.
REEL_MEETINGS = {
    "mar9": {"date": "2026-03-09", "body": "Governing Body — City Council",
             "file": "pipeline/corpus/extra/mar9.txt",
             "yt": "19tQtLA8klo", "tape": True},
    "apr27": {"date": "2026-04-27", "body": "Governing Body — City Council",
              "file": "pipeline/corpus/extra/apr27.txt",
              "yt": "y9vnXtjZpR0", "tape": True},
}

# (reel timestamp, label, meeting key, verified tape second -- None where
# the moment's exact tape time isn't verified yet)
REEL_CHAPTERS = [
    ("0:00", "The cut — a speaker cut mid-sentence", "mar9", 16449),
    ("1:50", "The return — 73 minutes later", "mar9", 20878),
    ("3:50", "First recognition of the night", "apr27", None),
    ("5:45", "Nine recognitions of one councilmember", "apr27", None),
    ("7:35", "The pile-on", "apr27", None),
    ("10:10", "The bypassed hand", "apr27", 9862),
    ("12:45", "1:30 AM — the last item", "apr27", None),
    ("14:05", "The Moody swap", None, None),
    ("15:25", "The Nemecek quote", None, None),
]

RAW_BASE = "https://raw.githubusercontent.com/bartimoussmith-oss/therealwindycity/main"


def _sec_to_hms(sec: int) -> str:
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def _yt_url(ytid: str, sec=None) -> str:
    base = f"https://www.youtube.com/watch?v={ytid}"
    return base + (f"&t={sec}s" if sec is not None else "")


@st.cache_data(show_spinner=False)
def _transcript_lines(rel: str):
    """Parse a full-tape transcript into [(second, text)] — the Granicus
    caption lines are video-relative, which is what makes time-jumps real."""
    out = []
    fp = ROOT / rel
    if not fp.exists():
        return out
    for line in fp.read_text(errors="replace").splitlines():
        m = re.match(r"^(\d{2}):(\d{2}):(\d{2})\s+(.*)$", line.strip())
        if m:
            h, mi, s, text = m.groups()
            out.append((int(h) * 3600 + int(mi) * 60 + int(s), text))
    return out


@st.cache_data(show_spinner=False)
def _ordinance_index():
    fp = ROOT / "pipeline" / "ordinance_history.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text()).get("ordinances", {})
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def _city_meetings():
    fp = ROOT / "pipeline" / "cityvideos.json"
    if not fp.exists():
        return {}
    try:
        data = json.loads(fp.read_text()).get("meetings", {})
        out = {}
        for date, minfo in data.items():
            ytid = minfo.get("id") if isinstance(minfo, dict) else minfo
            if ytid:
                out[date] = ytid
        return out
    except Exception:
        return {}


def _view_reel():
    st.subheader("🔥 Origin Tapes — the most contentious moments ever mic'd, on loop")
    st.caption("Nine verbatim moments from official city-meeting video, "
               "seventeen minutes, playing on loop. Browsers start autoplay "
               "muted — click the 🔊 on the player for sound. Below the "
               "player: the meeting, the ordinances being spoken about, and "
               "clickable captions — all three follow whichever moment you "
               "pick.")
    reel = ROOT / "pipeline" / "renders" / "CONTENTION_REEL.mp4"
    if reel.exists():
        st.video(str(reel), autoplay=True, muted=True, loop=True)
    else:
        st.info("The reel isn't built in this checkout yet — run "
                "`pipeline/build_reel.py` (needs ffmpeg).")
        return

    st.markdown("**What you're watching** — pick a moment; the context "
                "columns underneath track it:")
    labels = [f"`{ts}` {label}" for ts, label, _m, _s in REEL_CHAPTERS]
    pick = st.selectbox("Moment", labels, key="reel_ctx",
                        label_visibility="collapsed")
    ch = REEL_CHAPTERS[labels.index(pick)]
    meet = REEL_MEETINGS.get(ch[2])

    c1, c2, c3 = st.columns(3)

    # ---- column 1: the meeting ------------------------------------------
    with c1:
        st.markdown("**📺 The meeting**")
        if meet:
            st.markdown(f"**{meet['date']}**\n{meet['body']}")
            tape_at = ch[3]
            if tape_at is not None:
                st.markdown(f"[▶ Full tape at {_sec_to_hms(tape_at)}]"
                            f"({_yt_url(meet['yt'], tape_at)}) — the moment "
                            f"in context")
            else:
                st.markdown(f"[▶ Full meeting tape]({_yt_url(meet['yt'])})")
            st.markdown(f"[📜 Transcript source]({RAW_BASE}/{meet['file']})")
            st.caption("The in-app caption viewer with time-jumps is in the "
                       "right-hand column.")
        else:
            st.info("Source meeting pending verification — this clip "
                    "predates the verified-tape index. The Longboxes "
                    "holds the written record around it.")

    # ---- column 2: ordinances -------------------------------------------
    with c2:
        st.markdown("**⚖️ Ordinances in play**")
        ords = []
        if meet:
            idx = _ordinance_index()
            ords = [e for e in idx.values()
                    if any(m["date"] == meet["date"] for m in e["mentions"])]
            ords.sort(key=lambda e: -len(e["mentions"]))
        if ords:
            st.caption(f"{len(ords)} ordinance item"
                       f"{'s' if len(ords) != 1 else ''} spoken about in "
                       f"this meeting — open one for its full history:")
            for e in ords[:6]:
                label = (f"No. {e['number']}" if e.get("number")
                         else (e.get("title") or e["key"])[:56])
                with st.expander(f"{label} — {len(e['mentions'])} mention"
                                 f"{'s' if len(e['mentions']) != 1 else ''}"):
                    for m in e["mentions"]:
                        ytid = _city_meetings().get(m["date"])
                        jump = (f"[▶]({_yt_url(ytid)}) " if ytid else "")
                        st.markdown(f"- {jump}`{m['date']}` · {m['body']} · "
                                    f"{m['stage']}")
                    st.caption("Each ▶ opens that meeting's tape — the "
                               "player can't auto-queue a playlist, so it's "
                               "one click per leg.")
        else:
            st.caption("No ordinance mentions indexed for this meeting "
                       "yet — the index grows as transcripts are ingested "
                       "each cycle.")
        docs = _engine_q("SELECT title, url FROM documents "
                         "WHERE lower(title) LIKE '%agenda%' "
                         "OR lower(url) LIKE '%agenda%' "
                         "ORDER BY last_checked DESC LIMIT 5")
        if docs:
            st.markdown("**Agenda & fingerprinted documents**")
            for d in docs:
                st.markdown(f"- [{d['title'][:60]}]({d['url']})")
            st.caption("Plus everything the crawler has fingerprinted — "
                       "see the Ledger.")
        else:
            st.caption("Agenda documents appear here as the crawler "
                       "fingerprints them (it runs every 6 hours).")

    # ---- column 3: captions ---------------------------------------------
    with c3:
        st.markdown("**💬 Captions — click a line, the tape jumps**")
        if meet and meet.get("tape"):
            lines = _transcript_lines(meet["file"])
            anchor = ch[3]
            if anchor is not None:
                window = [l for l in lines
                          if anchor - 45 <= l[0] <= anchor + 150][:45]
                st.caption(f"Transcript around {_sec_to_hms(anchor)} — "
                           "what's being said in this moment:")
            else:
                window = lines[:45]
                st.caption("Exact tape time for this moment isn't verified "
                           "yet — showing the meeting open:")
            for sec, text in window:
                st.markdown(f"[`{_sec_to_hms(sec)}`]({_yt_url(meet['yt'], sec)})"
                            f" {text[:100]}")
            with st.expander("📜 Full transcript — every line is a jump link"):
                if lines:
                    max_min = int(lines[-1][0] // 60)
                    minute = st.number_input("Jump to minute", 0, max_min,
                                             key="reel_min")
                    around = [l for l in lines
                              if minute * 60 <= l[0] < minute * 60 + 240][:100]
                    for sec, text in around:
                        st.markdown(
                            f"[`{_sec_to_hms(sec)}`]"
                            f"({_yt_url(meet['yt'], sec)}) {text[:110]}")
                    st.caption("Word-level click needs custom JavaScript "
                               "this app deliberately doesn't ship — "
                               "timestamp-level is the honest version, and "
                               "each link lands on the exact second.")
        else:
            st.info("Caption-linked transcripts exist for the two verified "
                    "tape meetings (Mar 9 and Apr 27, 2026). Pick a moment "
                    "from one of those — or browse every meeting in the "
                    "The Tapes.")

    st.divider()
    col1, col2 = st.columns(2)
    col1.button("🧭 Choose your mission — find what affects you",
                on_click=_guide_jump, args=("🧭 Choose Your Mission",),
                type="primary")
    col2.button("🎬 All segments & evidence clips",
                on_click=_guide_jump, args=("🎬 The Tapes",))


@st.cache_data(show_spinner=False)
def _media_manifest():
    fp = ROOT / "pipeline" / "media_manifest.json"
    if not fp.exists():
        return {"meetings": {}}
    try:
        return json.loads(fp.read_text())
    except Exception:
        return {"meetings": {}}


@st.cache_data(show_spinner=False)
def _vtt_cues(rel: str):
    """Auto-caption VTT -> [(second, text)], rolling duplicates collapsed.
    Machine transcripts: search/jump-grade, not quotable like the clerk
    record — the view says so too."""
    fp = ROOT / rel
    if not fp.exists():
        return []
    ts = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,]\d{3}\s*-->")
    cues, last, pending, cur_sec = [], None, None, 0
    for line in fp.read_text(errors="replace").splitlines() + [""]:
        stripped = line.strip()
        m = ts.match(stripped)
        if m:
            if pending:
                text = " ".join(re.sub(r"<[^>]+>", "", " ".join(pending)).split())
                if text and text != last:
                    cues.append((cur_sec, text))
                    last = text
            h, mi, s = (m.group(1) or "0"), m.group(2), m.group(3)
            cur_sec = int(h) * 3600 + int(mi) * 60 + int(s)
            pending = []
            continue
        if not stripped or stripped == "WEBVTT" or stripped.startswith(("NOTE", "Kind:", "Language:")):
            if pending:
                text = " ".join(re.sub(r"<[^>]+>", "", " ".join(pending)).split())
                if text and text != last:
                    cues.append((cur_sec, text))
                    last = text
                pending = None
            continue
        if pending is not None and "-->" not in stripped:
            pending.append(stripped)
    return cues


def _view_media():
    st.subheader("📼 Every Tape, Every Line — recordings & captions for every indexed meeting")
    manifest = _media_manifest().get("meetings", {})
    n_caps = sum(1 for v in manifest.values() if v.get("captions"))
    n_aud = sum(1 for v in manifest.values() if v.get("audio"))
    st.caption(f"{len(manifest)} meetings in the media manifest · "
               f"{n_caps} captioned · {n_aud} with full audio · captions are "
               "machine transcripts (search/jump-grade); the clerk-written "
               "record stays the quotable one. Grows via the media backfill "
               "cell (tools/colab_media_backfill.py).")
    if not manifest:
        st.info("Nothing in the manifest yet — run the media backfill cell "
                "in Colab (MODE='captions' is the quick pass).")
        return
    date = st.selectbox("Meeting", sorted(manifest, reverse=True),
                        key="media_date")
    minfo = manifest.get(date) or {}
    ytid = minfo.get("yt")
    if not (date and ytid):
        st.info("No media indexed for this date yet.")
        return
    st.markdown(f"**{date}** — [tape on YouTube]"
                f"(https://www.youtube.com/watch?v={ytid})")
    if minfo.get("audio"):
        st.audio(minfo["audio"])
        st.caption("Full-meeting audio — streamed from the repo's GitHub "
                   "Release archive.")
    cues = _vtt_cues(minfo["captions"]) if minfo.get("captions") else []
    if cues:
        st.markdown("**Captions — every line jumps the tape:**")
        max_min = int(cues[-1][0] // 60)
        minute = st.number_input("Jump to minute", 0, max_min,
                                 min(60, max_min), key="media_min")
        window = [c for c in cues
                  if minute * 60 <= c[0] < minute * 60 + 300][:120]
        for sec, text in window:
            st.markdown(f"[`{_sec_to_hms(sec)}`]({_yt_url(ytid, sec)}) {text[:110]}")
        st.caption("Caption links open the tape at the exact second; the "
                   "audio player above runs off the same clock.")
    else:
        st.video(_yt_url(ytid))
        st.caption("No caption file yet — the backfill cell picks these up "
                   "per meeting.")


def _view_miller():
    if _render_miller_theater is None:
        st.info("The Miller Tapes aren't cued in this checkout yet — run "
                "`python3 pipeline/build_miller_index.py` (needs the caption "
                "tracks; see its docstring).")
        return
    _render_miller_theater(embed=True)


SECTIONS = {
    "🎬 Miller Tapes": [("🎬 Every Intervention, On Loop", _view_miller)],
    "🔥 Origin Tapes": [("🔥 The Contention Reel", _view_reel)],
    "🧭 Choose Your Mission":     [("🧭 Get Your Mission Brief", _view_guide)],
    "🦸 Hero Roster":   [("🦸 Meet the Roster", _view_roster)],
    "◈ Ledger HQ":       [("◈ Today's Front Page", _view_home)],
    "📡 Mission Board": [
        ("🚩 Action Alerts", _view_alerts),
        ("⚠️ Silent Edits Caught", _view_edits),
        ("📰 The Daily Ledger", _view_digest),
    ],
    "🔎 Evidence Vault": [
        ("🔎 Search the Evidence", _view_search),
        ("📜 17 Years of Tapes", _view_minutes),
        ("🗄 The Longboxes", _view_canon),
    ],
    "🎬 The Tapes":   [("🎬 Montage Theater", _view_video),
                       ("📼 Every Tape, Every Line", _view_media)],
    "✉️ Signals & Paperwork":        [("💡 Send a Signal", _view_tips),
                         ("✉️ Paperwork Arsenal", _view_paperwork)],
    "🗃 Case Files": [
        ("⚔️ Battle Records*", _view_battles),
        ("🔍 Lie Detector*", _view_veracity),
        ("🧾 Money Trail*", _view_vouchers),
        ("☣️ Toxic Files*", _view_environment),
    ],
    "✋ Join the Roster": [("✋ Your Power Awaits", _view_recruit)],
}


def render_ledger():
    _comic_boot()
    _comic_masthead()
    eng_stats = {r["k"]: r["v"] for r in _engine_q(
        "SELECT 'documents' k, COUNT(*) v FROM documents UNION ALL "
        "SELECT 'alerts', COUNT(*) FROM alerts UNION ALL "
        "SELECT 'silent_edits', COUNT(*) FROM versions WHERE seq>1 UNION ALL "
        "SELECT 'drafts', COUNT(*) FROM requests WHERE status='draft'")}
    for k in ("documents", "alerts", "silent_edits", "drafts"):
        eng_stats.setdefault(k, 0)

    # ---- freshness + breaking ------------------------------------------
    last = ([r["m"] for r in _engine_q("SELECT MAX(last_checked) m FROM documents")
             if r["m"]] or [None])[-1]
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    breaking = [r for r in _engine_q(
        "SELECT a.created_at, a.term, d.title FROM alerts a "
        "JOIN documents d ON d.id=a.document_id WHERE a.created_at >= ?",
        (cutoff,))]

    ver = _vault_ver()
    ver_rows = ver.get("rows", {})
    found_n = sum(1 for r in ver_rows.values()
                  if r.get("status") == "found-in-record")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Documents fingerprinted", eng_stats["documents"])
    c2.metric("Watchlist hits", eng_stats["alerts"])
    c3.metric("Silent edits caught", eng_stats["silent_edits"])
    c4.metric("Vault rows", len(ver_rows) or 22)
    c5.metric("Vault rows verified vs corpus", found_n,
              delta="auto-rechecked every cycle", delta_color="off")
    c6.metric("PRA drafts waiting", eng_stats["drafts"])
    st.caption(f"⏱ last crawl: **{_ago(last)}** · cycle runs every 6 h plus "
               f"hourly on Mon/Tue meeting nights · "
               f"RSS: `public/feed.xml` in the repo")

    if breaking:
        st.error("🚨 **ACTION ALERT (<48 h):** " + " · ".join(
            f"“{r['term']}” in {r['title']}" for r in breaking[:5])
            + (" …see Action Alerts." if len(breaking) > 5 else ""))

    # Section nav in the sidebar replaces the old 14-across tab strip — same
    # views, grouped the way people actually come looking for them.
    st.sidebar.markdown("#### 📖 Chapters")
    pick = st.sidebar.radio("Go to", list(SECTIONS), key="ledger_section",
                            label_visibility="collapsed")
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "🦸 **New heroes wanted.** Every power on this roster started as "
        "one citizen, one mic, three minutes.")
    st.sidebar.button("✋ Join the Roster", key="join_cta",
                      on_click=_join_jump, use_container_width=True)
    chosen = SECTIONS[pick]
    if len(chosen) == 1:
        chosen[0][1]()
    else:
        for (_, fn), tab in zip(chosen, st.tabs([lbl for lbl, _ in chosen])):
            with tab:
                fn()

# =========================================================================
# FACE 2 — Transparency Index (entity lineage; auto-indexing fallback)
# =========================================================================


def render_index():
    _comic_boot()
    _comic_masthead()
    try:
        import pandas as pd
        from bs4 import BeautifulSoup
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover - Cloud installs requirements.txt
        st.error(f"This face needs extra packages ({e}). They are in "
                 f"requirements.txt — Streamlit Cloud installs them automatically "
                 f"on redeploy. Locally: pip install pandas beautifulsoup4 pypdf")
        return

    st.markdown("""
        <style>
        .stMetric { background-color: #1e2130; padding: 15px; border-radius: 5px;
                    border: 1px solid #30363d; }
        .object-header { font-size: 28px; font-weight: bold; color: #e6edf3;
                         border-bottom: 1px solid #30363d; padding-bottom: 10px;
                         margin-bottom: 20px;}
        a { color: #58a6ff !important; text-decoration: none; font-weight: 500; }
        a:hover { text-decoration: underline; }
        </style>
        """, unsafe_allow_html=True)

    st.markdown("## 🏛️ The Forensic Files — Cheyenne Transparency Index")
    st.markdown("*An independent, document-backed forensic database of "
                "Cheyenne Municipal Operations.*")

    @st.cache_data(show_spinner=False)
    def load_index(root_str: str):
        index = {"Entities": {}, "Documents": {}}
        json_files = glob.glob(str(Path(root_str) / "Entity_Database" / "*.json"))
        for jf in json_files:
            try:
                with open(jf, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                fname = os.path.basename(jf).replace(".json", "")
                index["Documents"][fname] = data
                all_entities = (data.get("speakers_or_authors", [])
                                + data.get("policies_mentioned", [])
                                + data.get("locations_mentioned", []))
                for entity in set(all_entities):
                    if not entity or len(entity) < 4:
                        continue
                    index["Entities"].setdefault(entity, []).append(fname)
            except Exception:
                pass
        return index

    with st.spinner("Initializing Forensic Database..."):
        index = load_index(str(ROOT))

    auto = False
    if not index["Documents"]:
        md_sig = tuple(sorted(fp.name for fp in ROOT.glob("*.md")))
        docs_map = _auto_entities(str(ROOT), md_sig)
        if docs_map:
            auto = True
            index = {"Entities": {}, "Documents": docs_map}
            for fname, data in docs_map.items():
                for entity in set(data.get("speakers_or_authors", [])
                                  + data.get("policies_mentioned", [])
                                  + data.get("locations_mentioned", [])):
                    if entity and len(entity) >= 4:
                        index["Entities"].setdefault(entity, []).append(fname)
            st.success(f"Auto-indexed live from **{len(docs_map)} dossiers** "
                       f"(heuristic extraction — deterministic greps, no LLM. "
                       f"From the next civic cycle on, these are also committed "
                       f"as `Entity_Database/*.json`).")
        else:
            st.info("**No documents to index yet** — this face reads "
                    "`Entity_Database/*.json` and falls back to auto-indexing the "
                    "root dossier corpus. Both are empty in this checkout.",
                    icon="🏗️")

    def read_raw_document(fname):
        candidates = [ROOT / fname,
                      ROOT / (fname + ".md"),
                      ROOT / (fname + ".txt"),
                      ROOT / "Video_Transcripts" / fname,
                      ROOT / "Cheyenne_Extracted_Documents" / fname,
                      ROOT / "city of cheyenne gov files" / fname]
        target = next((p for p in candidates if p.exists()), None)
        if not target:
            return "Source file currently archived or unavailable."
        ext = str(target).lower().split('.')[-1]
        try:
            if ext in ['htm', 'html']:
                return BeautifulSoup(open(target, "r", encoding="utf-8",
                                          errors="ignore").read(),
                                     'html.parser').get_text(' ')
            elif ext == 'pdf':
                return "\n".join([p.extract_text() or ""
                                  for p in PdfReader(str(target)).pages])
            elif ext == 'txt':
                return open(target, "r", encoding="utf-8", errors="ignore").read()
            elif ext == 'md':
                return open(target, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            return "Error extracting raw text."
        return "Format unsupported."

    st.sidebar.markdown("### 🔍 Index Navigation")
    nav_mode = st.sidebar.radio("Select View:",
                                ["Global Dashboard", "Entity Dossier",
                                 "Document Viewer"])

    if nav_mode == "Global Dashboard":
        st.markdown("<div class='object-header'>System Overview</div>",
                    unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Indexed Municipal Records", len(index["Documents"]))
        c2.metric("Tracked Entities & Policies", len(index["Entities"]))
        c3.metric("Status", "AUTO-INDEXED" if auto else "ACTIVE - UNREDACTED")

        st.subheader("High-Frequency Targets (Recent)")
        df_entities = pd.DataFrame([{"Entity": k, "Record Count": len(v)}
                                    for k, v in index["Entities"].items()])
        if not df_entities.empty:
            st.dataframe(df_entities.sort_values("Record Count",
                                                 ascending=False).head(15),
                         use_container_width=True)

    elif nav_mode == "Entity Dossier":
        selected_entity = st.sidebar.selectbox(
            "Select Target Entity/Policy:",
            sorted(list(index["Entities"].keys())))
        if selected_entity:
            st.markdown(f"<div class='object-header'>Dossier: {selected_entity}</div>",
                        unsafe_allow_html=True)
            linked_docs = index["Entities"][selected_entity]
            st.info(f"Target identified in {len(linked_docs)} official records.")
            for doc in linked_docs:
                with st.expander(f"📄 View record: {doc}"):
                    raw_text = read_raw_document(doc)
                    highlighted = re.sub(rf"(?i)({re.escape(selected_entity)})",
                                         r"**:red[\1]**", raw_text)
                    st.markdown(highlighted[:3000]
                                + "...\n\n*[Text truncated for display]*")

    elif nav_mode == "Document Viewer":
        selected_doc = st.sidebar.selectbox(
            "Select Official Record:", sorted(list(index["Documents"].keys())))
        if selected_doc:
            st.markdown(f"<div class='object-header'>Record: {selected_doc}</div>",
                        unsafe_allow_html=True)
            t1, t2 = st.tabs(["Raw Source Text", "Extracted Metadata"])
            with t1:
                st.markdown(read_raw_document(selected_doc))
            with t2:
                st.json(index["Documents"][selected_doc])


# =========================================================================
# SHELL — masthead + face switch
# =========================================================================

st.markdown("""<style>
.block-container{padding-top:1.2rem}
.rwc-mast{border-bottom:6px double #22303c;padding:6px 0 12px;margin-bottom:10px}
.rwc-mast h1{font-family:'Courier New',monospace;font-size:2.4rem;margin:0;color:#22303c}
.rwc-kick{color:#6d7b86;margin:2px 0 0}
.rwc-tag{display:inline-block;background:#22303c;color:#f7f2e7;padding:4px 12px;
font-family:'Courier New',monospace;font-size:.85rem;margin-top:8px;letter-spacing:.06em}
</style>
<div class="rwc-mast"><h1>THE REAL WINDY CITY</h1>
<p class="rwc-kick">Cheyenne, Wyoming · public documents in, verifiable evidence out ·
one console, switchable faces: verified ledger + recovered vault + canon · entity index</p>
<span class="rwc-tag">Wind belongs on the prairie. Not in the minutes.</span></div>
""", unsafe_allow_html=True)


def _sync_face():
    st.query_params["face"] = ("index"
                               if st.session_state.face_pick.startswith("🏛")
                               else "ledger")


st.sidebar.markdown("### 🎛 Pick Your Title")
st.sidebar.radio(
    "Switch titles (shareable: add ?face=index to the URL)",
    ["◈ Ledger HQ", "🏛 Transparency Index — Forensic Files"],
    index=1 if st.query_params.get("face") == "index" else 0,
    key="face_pick", on_change=_sync_face,
)
st.sidebar.markdown("---")

if st.session_state.face_pick.startswith("🏛"):
    render_index()
else:
    render_ledger()

st.caption("Engine v0.1 + recovered vault (auto-verified against the transcript "
           "corpus every cycle) + entity index face · public documents only · "
           "robots.txt honored · no affiliation with any individual, candidate, "
           "or committee · * = legacy seed: lead until ✅ found in record · the Roster honors on-the-record acts only")
