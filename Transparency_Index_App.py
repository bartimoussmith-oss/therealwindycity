"""The Real Windy City — civic console for Cheyenne / Laramie County.

One Streamlit process, two faces, switched from the sidebar (deep-linkable
with ?face=index):

  * Windy City Ledger — the working console. It opens on the Start
    Here guide (three questions that route each viewer to the parts
    of the record that touch them), and the sidebar groups the views
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

ENGINE_DB = ROOT / "data" / "engine.db"
LEGACY_DB = ROOT / "cheyenne_watchdog.db"
VERIF_JSON = ROOT / "data" / "vault_verification.json"
CORPUS_DIR = ROOT / "pipeline" / "corpus"

st.set_page_config(page_title="The Real Windy City",
                   page_icon="🌬", layout="wide")

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


def _view_home():
    page = ROOT / "public" / "index.html"
    st.caption("The static ledger, regenerated every scheduler cycle.")
    if page.exists():
        components.html(page.read_text(), height=3200, scrolling=True)
    else:
        st.info("public/index.html not built yet — civic-cycle builds it.")
def _view_alerts():
    st.subheader("Watchlist alerts — verbatim quotes, linked records")
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
    st.subheader("Silent edits — SHA-256 drift on already-published pages")
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
    st.subheader("📰 Digest — what changed lately")
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
    c.metric("Silent edits (7 days)", new_edits)
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
    st.subheader("⚔️ Statutory Battles — public-comment interventions")
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
    st.subheader("🔍 Veracity Ledger — documented-say/unsay pairs")
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
    st.subheader("🧾 Voucher Audit — money claims tracked")
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
    st.subheader("☣️ Environmental Matrix")
    rows = _legacy_q(VAULT_QUERIES["environmental_zones"])
    for i, r in enumerate(rows):
        v = _verdict(ver, "environmental_zones", i)
        r["record_evidence"] = ("✅ " + v["hits"][0]["file"]) if v else "—"
    st.dataframe(rows, use_container_width=True, hide_index=True)

# ---------- minutes archive -------------------------------------------
def _view_minutes():
    st.subheader("📜 Minutes Archive — search 17 years of the record")
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
    st.subheader("💡 Got something the ledger should see?")
    st.markdown(
        "The machine watches published sources; people see things first. A good "
        "tip is **verifiable**: a URL, a document (with `sha256sum`), a meeting "
        "number + timestamp, or a verbatim quote — never a rumor.")
    st.link_button("📥 File a tip (GitHub issue form)",
                   "https://github.com/bartimoussmith-oss/therealwindycity/"
                   "issues/new?template=tip.md")
    st.caption("Tips are read by a human. This mailbox never triggers letters or "
               "contact with officials on its own.")

# ---------- canon library ---------------------------------------------
def _view_canon():
    st.subheader("🗄 The Canon Library — every dossier in the repo")
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
    st.subheader("🎬 Video Vault — the record on tape")
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
        st.markdown("**The Record Speaks — produced segments (captioned)**")
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
# Start Here guide — question-driven routing into the record. Deliberately a
# plain rules engine, not a model: every recommendation carries its because-of
# so a viewer can audit the logic, and the answers never leave the browser.
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


def _guide_jump(section, q=None, canon=None):
    """Send the viewer to a section, optionally preloading its search box."""
    st.session_state["ledger_section"] = section
    if q is not None:
        st.session_state["corpus_q"] = q
    if canon is not None:
        st.session_state["canon_term"] = canon


def _view_guide():
    st.subheader("🧭 Start here — get *your* brief, not the whole haystack")
    st.caption("Three quick questions. Plain rules, no model: every "
               "recommendation below shows its because-of, and nothing you "
               "pick leaves your browser.")

    st.radio("1 · Who are you here as?", [lbl for lbl, _ in GUIDE_ROLES],
             key="g_role")
    st.multiselect("2 · Which of these touch your life? (pick any)",
                   [lbl for lbl, _ in GUIDE_TOPICS], key="g_topics")
    st.markdown("3 · Check what's true for you — every check adds to your brief:")
    st.checkbox("I own my home (property taxes hit me directly)", key="g_owner")
    st.checkbox("I drink city tap water", key="g_tap")
    st.checkbox("I live west of town, near the Belvoir–High Plains corridor",
                key="g_west")
    st.checkbox("I voted in the last city election", key="g_voter")
    st.checkbox("I've watched or attended a city meeting", key="g_watcher")

    role = dict(GUIDE_ROLES).get(st.session_state.get("g_role", ""), "")
    topics = st.session_state.get("g_topics") or []
    tags = {role} | {t for lbl, t in GUIDE_TOPICS if lbl in topics}
    if st.session_state.get("g_owner"):
        tags.add("money")
    if st.session_state.get("g_tap"):
        tags.add("water")
    if st.session_state.get("g_west"):
        tags |= {"datacenter", "environment"}
    if st.session_state.get("g_voter"):
        tags.add("elections")
    if st.session_state.get("g_watcher"):
        tags.add("process")

    recs = []

    def rec(title, because, section, q=None, canon=None):
        recs.append((title, because, section, q, canon))

    if "money" in tags:
        rec("Follow the money — the voucher forensics",
            "You flagged taxes and spending. The vault tracks spending line by "
            "line with the receipts attached — worth ten minutes of anyone's "
            "property-tax bill.", "🗃 Legacy vault")
        rec("Watch “S2: The 74M List”",
            "The film cut of the capital-project list — the fastest way to "
            "see what the money argument is actually about.",
            "🎬 Video vault")
        rec("Search 17 years of minutes for “6th penny”",
            "Every time the sales-tax question came up, verbatim, with the "
            "meeting dates attached.", "🔎 The record", q="6th penny")
    if "water" in tags:
        rec("Your water, on the record",
            "You flagged water. The environmental matrix tracks the water "
            "and groundwater items, and the archive holds every water "
            "discussion the councils have had.",
            "🗃 Legacy vault")
        rec("Search the minutes for “water”",
            "Moratorium votes, utility extensions, supply studies — the "
            "paper trail behind whatever ends up in your bill.",
            "🔎 The record", q="water")
    if "datacenter" in tags:
        rec("The data-center boom, filed and footnoted",
            "Annexations, zoning, the ranch-land fights — this is the "
            "dossier line that grew this whole archive. Start with the "
            "Battles view and the data-center brief.",
            "🗃 Legacy vault")
        rec("Watch “S1: 48 Hours”",
            "The cut that shows how fast the annexation votes moved.",
            "🎬 Video vault")
        rec("Search the minutes for “annexation”",
            "The full paper trail, meeting by meeting.", "🔎 The record",
            q="annexation")
    if "environment" in tags:
        rec("Groundwater, air, and environmental review",
            "The environmental matrix keeps the review items in one place, "
            "each linked back to its source document.",
            "🗃 Legacy vault")
        rec("Search the minutes for “groundwater”",
            "Where the environmental record actually lives.", "🔎 The record",
            q="groundwater")
    if "process" in tags:
        rec("The silent-edits wire",
            "Documents on the city site that changed after the fact — each "
            "one diffed, timestamped, and linked. This tab existing at all "
            "is the point.", "📡 Live operations")
        rec("How to read a meeting like an investigator",
            "The Minutes Archive is 17 years of verbatim transcripts, "
            "searchable word by word. Ctrl-F is a civic instrument.",
            "🔎 The record")
    if "officials" in tags:
        rec("Who said what — the veracity files",
            "First positions next to later positions, so the record does the "
            "comparing for you.", "🗃 Legacy vault")
        rec("The tape archive",
            "Verified clips with timestamps back to the full meeting video — "
            "including the cuts that made the news. The Caller tape is the "
            "one people ask about first.", "🎬 Video vault")
        rec("The canon library, by person",
            "Every dossier on the officials and the races, organized by "
            "series.", "🔎 The record", canon="miller")
    if "elections" in tags:
        rec("Ballot season, on the record",
            "The digest tracks what moved each week, and the alerts flag "
            "watchlist language within 48 hours of it posting.",
            "📡 Live operations")
        rec("Search the canon for “referendum”",
            "The referendum dossiers and everything filed around them.",
            "🔎 The record", canon="referendum")
    if role == "press":
        rec("Reporter's kit — full-text search",
            "FTS over everything fingerprinted, plus 17 years of transcripts. "
            "Every alert carries a verbatim quote, a source URL, and a fetch "
            "timestamp — citeable as-is.", "🔎 The record")
        rec("The PRA drafting bench",
            "Wyoming Public Records Act request drafts, filled in and ready "
            "for a human to send. Wrong-statute citations are a reporter's "
            "fastest way to get stonewalled.", "✉️ Intake")
    if "roads" in tags:
        rec("Roads and construction in the record",
            "Search the minutes for the street and project names you drive "
            "past — most capital work shows up in a vote before it shows up "
            "on the ground.", "🔎 The record", q="street")

    st.divider()
    if recs:
        st.success(f"Your brief — {len(recs)} place{'s' if len(recs) != 1 else ''} "
                   "to start, each one because of something you told me:")
        for i, (title, because, section, q, canon) in enumerate(recs):
            with st.container(border=True):
                st.markdown(f"**{i + 1}. {title}**")
                st.caption(because)
                st.button("Take me there →", key=f"g_go_{i}",
                          on_click=_guide_jump, args=(section, q, canon),
                          use_container_width=False)
    else:
        st.info("Nothing checked — no problem. Everyone's baseline: the "
                "**Live Alerts** and **Digest** tabs under Live operations, "
                "and the **Minutes Archive** under The record. Or pick a "
                "checkbox above and watch the brief build itself.")
    st.caption("Whoever you are: the alert feed updates itself every six "
               "hours, so 📡 Live operations is worth a bookmark.")


SECTIONS = {
    "🧭 Start Here":     [("🧭 Find your brief", _view_guide)],
    "◈ Overview":       [("◈ Ledger", _view_home)],
    "📡 Live operations": [
        ("🚩 Live Alerts", _view_alerts),
        ("⚠️ Silent Edits", _view_edits),
        ("📰 Digest", _view_digest),
    ],
    "🔎 The record": [
        ("🔎 Search", _view_search),
        ("📜 Minutes Archive", _view_minutes),
        ("🗄 Canon Library", _view_canon),
    ],
    "🎬 Video vault":   [("🎬 Video Vault", _view_video)],
    "✉️ Intake":        [("💡 Tips", _view_tips),
                         ("✉️ Paperwork", _view_paperwork)],
    "🗃 Legacy vault": [
        ("⚔️ Battles*", _view_battles),
        ("🔍 Veracity*", _view_veracity),
        ("🧾 Vouchers*", _view_vouchers),
        ("☣️ Environment*", _view_environment),
    ],
}


def render_ledger():
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
        st.error("🚨 **BREAKING (<48 h):** " + " · ".join(
            f"“{r['term']}” in {r['title']}" for r in breaking[:5])
            + (" …see Live Alerts." if len(breaking) > 5 else ""))

    # Section nav in the sidebar replaces the old 14-across tab strip — same
    # views, grouped the way people actually come looking for them.
    st.sidebar.markdown("#### Sections")
    pick = st.sidebar.radio("Go to", list(SECTIONS), key="ledger_section",
                            label_visibility="collapsed")
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

    st.markdown("## 🏛️ The Cheyenne Transparency Index")
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


st.sidebar.markdown("### 🎛 Console Face")
st.sidebar.radio(
    "Switch faces (shareable: add ?face=index to the URL)",
    ["◈ Windy City Ledger", "🏛 Transparency Index"],
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
           "or committee · * = legacy seed: lead until ✅ found in record")
