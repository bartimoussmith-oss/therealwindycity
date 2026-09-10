"""The Real Windy City — civic console for Cheyenne / Laramie County.

One Streamlit process, two faces, switched from the sidebar (deep-linkable
with ?face=index):

  * Windy City Ledger — the working console. It opens on a looping reel
    of the most contentious moments spoken at the meetings (autoplay
    muted, sourced chapter by chapter), then the Start Here guide — an
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
# Start Here guide — an adaptive question wizard. Six stages: who → what →
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
    st.subheader("🧭 Start here — get *your* brief, not the whole haystack")
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
            "🗃 Legacy vault", m,
            nxt=("Then search the minutes for “voucher”", "🔎 The record",
                 "voucher", None))
        add("Watch “S2: The 74M List”",
            "The film cut of the capital-project list — the fastest way to "
            "see what the money argument is actually about.",
            "🎬 Video vault", ["taxes and spending"])
        add("Search 17 years of minutes for “6th penny”",
            "Every time the sales-tax question came up, verbatim, with "
            "meeting dates attached.", "🔎 The record",
            ["taxes and spending"], q="6th penny")
        if sub.get("money") == "m-voucher":
            add("The voucher tables, row by row",
                "You chose line items — the Vouchers view is the table "
                "itself, sources linked per row.", "🗃 Legacy vault",
                ["you chose voucher line items"])
        if sub.get("money") == "m-capital":
            add("The capital-projects paper trail",
                "You chose the capital list — here's every capital motion "
                "in the record.", "🔎 The record",
                ["you chose the capital list"], q="capital")
        if sub.get("money") == "m-pra":
            add("The PRA drafting bench",
                "You chose to pull the receipts yourself — these are "
                "filled-in Wyoming PRA drafts waiting for a human to send.",
                "✉️ Intake", ["you chose: pull the receipts yourself"])
    if "water" in tags:
        m = ["you flagged water"]
        if _gval("g_tap"):
            m.append("you drink the tap water")
        add("Your water, on the record",
            "The environmental matrix keeps the water and groundwater items "
            "in one place, each linked to its source document.",
            "🗃 Legacy vault", m)
        add("Search the minutes for “water”",
            "Moratorium votes, utility extensions, supply studies — the "
            "paper trail behind whatever ends up in your bill.",
            "🔎 The record", ["you flagged water"], q="water")
        if sub.get("water") == "w-supply":
            add("BOPU — the water utility's own record",
                "You chose supply — every mention of the Board of Public "
                "Utilities, verbatim.", "🔎 The record",
                ["you chose supply and drought capacity"], q="BOPU")
        if sub.get("water") == "w-ground":
            add("Groundwater, everywhere it appears",
                "You chose contamination risk — this is the aquifer paper "
                "trail.", "🔎 The record",
                ["you chose groundwater risk"], q="groundwater")
        if sub.get("water") == "w-bill":
            add("What goes into a water bill",
                "You chose cost — the rate and fee discussions, in the "
                "dossiers.", "🔎 The record",
                ["you chose what you're paying"], canon="water")
        if sub.get("water") == "w-hookups":
            add("Utility extensions — who gets hooked up",
                "You chose new-development hookups — every extension the "
                "council has voted on.", "🔎 The record",
                ["you chose development hookups"], q="utility extension")
    if "datacenter" in tags:
        m = ["you flagged the data-center boom"]
        if _gval("g_west"):
            m.append("you live near the corridor")
        add("The data-center boom, filed and footnoted",
            "Annexations, zoning, the ranch-land fights — the dossier line "
            "that grew this whole archive. Start with Battles and the "
            "data-center brief.", "🗃 Legacy vault", m)
        add("Watch “S1: 48 Hours”",
            "The cut that shows how fast the annexation votes moved.",
            "🎬 Video vault", ["data-center boom"])
        add("Search the minutes for “annexation”",
            "The full paper trail, meeting by meeting.", "🔎 The record",
            ["data-center boom"], q="annexation")
        if sub.get("datacenter") == "d-power":
            add("Power and water demand on the record",
                "You chose the power angle — every electric-capacity "
                "discussion, verbatim.", "🔎 The record",
                ["you chose power and water demand"], q="electric")
        if sub.get("datacenter") == "d-jobs":
            add("Jobs and abatement claims, checked",
                "You chose the jobs claims — see what was promised vs. what "
                "the record shows.", "🔎 The record",
                ["you chose jobs and abatement claims"], canon="abatement")
        if sub.get("datacenter") == "d-near":
            add("The Highlands corridors, in the dossiers",
                "You chose your street — the Highlands files are the "
                "closest to the ground.", "🔎 The record",
                ["you chose what it means for your street"],
                canon="highlands")
    if "environment" in tags:
        add("Groundwater, air, and environmental review",
            "The environmental matrix keeps the review items in one place, "
            "each linked back to its source document.", "🗃 Legacy vault",
            ["you flagged the environment"])
        add("Search the minutes for “groundwater”",
            "Where the environmental record actually lives.",
            "🔎 The record", ["you flagged the environment"], q="groundwater")
        if sub.get("environment") == "e-air":
            add("Air quality in the record",
                "You chose air — every air-quality discussion, verbatim.",
                "🔎 The record", ["you chose air quality"], q="air quality")
        if sub.get("environment") == "e-review":
            add("How environmental review actually happens",
                "You chose the review process — permits, hearings, and "
                "what triggers what.", "🔎 The record",
                ["you chose how review happens"], q="permit")
    if "process" in tags:
        m = ["you flagged how meetings run"]
        if _gval("g_watcher"):
            m.append("you've attended the meetings")
        add("The silent-edits wire",
            "Documents on the city site that changed after the fact — each "
            "one diffed, timestamped, and linked. This tab existing at all "
            "is the point.", "📡 Live operations", m)
        add("How to read a meeting like an investigator",
            "The Minutes Archive is 17 years of verbatim transcripts, "
            "searchable word by word. Ctrl-F is a civic instrument.",
            "🔎 The record", ["how meetings run"])
        if sub.get("process") == "p-agenda":
            add("Agenda changes, caught in the act",
                "You chose late-changing agendas — the edits wire plus the "
                "agenda history.", "🔎 The record",
                ["you chose late agendas"], q="agenda")
        if sub.get("process") == "p-closed":
            add("Executive sessions — every claimed exception",
                "You chose closed doors — each executive session with the "
                "statute cited.", "🔎 The record",
                ["you chose closed sessions"], q="executive session")
        if sub.get("process") == "p-comment":
            add("Public comment — how to get your three minutes",
                "You chose speaking up — the rules and the record of public "
                "comment, in one place.", "🔎 The record",
                ["you chose public comment"], q="public comment")
    if "officials" in tags:
        add("Who said what — the veracity files",
            "First positions next to later positions, so the record does "
            "the comparing for you.", "🗃 Legacy vault",
            ["you flagged officials"])
        add("The tape archive",
            "Verified clips with timestamps back to the full meeting video "
            "— including the cuts that made the news. The Caller tape is "
            "the one people ask about first.", "🎬 Video vault",
            ["you flagged officials"])
        add("The canon library, by person",
            "Every dossier on the officials and the races, organized by "
            "series.", "🔎 The record", ["you flagged officials"],
            canon="miller")
        if sub.get("officials") == "o-candidates":
            add("The Nov 3 candidate files",
                "You chose the candidates — the election-year dossiers.",
                "🔎 The record", ["you chose the candidates"], canon="2026")
    if "elections" in tags:
        m = ["you flagged elections"]
        if _gval("g_voter"):
            m.append("you voted last time")
        add("Ballot season, on the record",
            "The digest tracks what moved each week, and the alerts flag "
            "watchlist language within 48 hours of it posting.",
            "📡 Live operations", m)
        add("Search the canon for “referendum”",
            "The referendum dossiers and everything filed around them.",
            "🔎 The record", ["you flagged elections"], canon="referendum")
        if sub.get("elections") == "el-mech":
            add("How and where to vote",
                "You chose mechanics — the election-process files.",
                "🔎 The record", ["you chose how to vote"], canon="election")
    if "roads" in tags:
        add("Roads and construction in the record",
            "Search the minutes for the street and project names you drive "
            "past — most capital work shows up in a vote before it shows "
            "up on the ground.", "🔎 The record",
            ["you flagged roads"], q="street")
        if sub.get("roads") == "r-project":
            add("Find your specific project",
                "You chose a project near you — construction motions, "
                "verbatim.", "🔎 The record",
                ["you chose a specific project"], q="construction")
        if sub.get("roads") == "r-maint":
            add("Maintenance and potholes — the record",
                "You chose maintenance — what the city said it would fix.",
                "🔎 The record", ["you chose maintenance"], q="maintenance")
    if "press" in tags:
        add("Reporter's kit — full-text search",
            "FTS over everything fingerprinted, plus 17 years of "
            "transcripts. Every alert carries a verbatim quote, a source "
            "URL, and a fetch timestamp — citeable as-is.",
            "🔎 The record", ["you're a reporter or researcher"])
        add("The PRA drafting bench",
            "Wyoming Public Records Act request drafts, filled in and "
            "ready for a human to send. Wrong-statute citations are a "
            "reporter's fastest way to get stonewalled.", "✉️ Intake",
            ["you're a reporter or researcher"])
    if "observer" in tags:
        add("The story so far",
            "Not local? The digest is the catch-up: what moved, when, with "
            "links.", "📡 Live operations",
            ["you're following the story"])

    # format preference re-weights the ranking
    fmt = _gval("g_format") or ""
    boosts = {"🔔 Get updates": "📡 Live operations",
              "🎬 Watch the tape": "🎬 Video vault",
              "🔎 Search it myself": "🔎 The record",
              "📖 Read the record": "🗃 Legacy vault"}
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
                "**Live Alerts** and **Digest** views under Live operations, "
                "and the **Minutes Archive** under The record. Or go Back "
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
               "hours, so 📡 Live operations is worth a bookmark.")


# The front-door reel: contentious moments, in order, with links to the full
# source meeting. Timestamps are cumulative starts in CONTENTION_REEL.mp4 —
# keep in sync with pipeline/build_reel.py's ORDER.
REEL_CHAPTERS = [
    ("0:00", "The cut — a speaker cut mid-sentence (Mar 9)",
     "https://www.youtube.com/watch?v=19tQtLA8klo&t=16449s"),
    ("1:50", "The return — 73 minutes later (Mar 9)",
     "https://www.youtube.com/watch?v=19tQtLA8klo&t=20878s"),
    ("3:50", "First recognition of the night (Apr 27)",
     "https://www.youtube.com/watch?v=y9vnXtjZpR0"),
    ("5:45", "Nine recognitions of one councilmember (Apr 27)",
     "https://www.youtube.com/watch?v=y9vnXtjZpR0"),
    ("7:35", "The pile-on (Apr 27)",
     "https://www.youtube.com/watch?v=y9vnXtjZpR0"),
    ("10:10", "The bypassed hand (Apr 27)",
     "https://www.youtube.com/watch?v=y9vnXtjZpR0&t=9862s"),
    ("12:45", "1:30 AM — the last item (Apr 27)",
     "https://www.youtube.com/watch?v=y9vnXtjZpR0"),
    ("14:05", "The Moody swap", None),
    ("15:25", "The Nemecek quote", None),
]


def _view_reel():
    st.subheader("🔥 The Record Speaks — the most contentious moments, on loop")
    st.caption("Nine verbatim moments from official city-meeting video, "
               "seventeen minutes, playing on loop. Browsers start autoplay "
               "muted — click the 🔊 on the player for sound. Every moment "
               "is sourced below.")
    reel = ROOT / "pipeline" / "renders" / "CONTENTION_REEL.mp4"
    if reel.exists():
        st.video(str(reel), autoplay=True, muted=True, loop=True)
        st.markdown("**What you're watching — each moment links to the full "
                    "meeting tape:**")
        for ts, label, url in REEL_CHAPTERS:
            if url:
                st.markdown(f"- `{ts}` **{label}** — [full meeting]({url})")
            else:
                st.markdown(f"- `{ts}` **{label}** — in the Video vault")
    else:
        st.info("The reel isn't built in this checkout yet — run "
                "`pipeline/build_reel.py` (needs ffmpeg).")
    st.divider()
    col1, col2 = st.columns(2)
    col1.button("🧭 Start here — find what affects you",
                on_click=_guide_jump, args=("🧭 Start Here",),
                type="primary")
    col2.button("🎬 All segments & evidence clips",
                on_click=_guide_jump, args=("🎬 Video vault",))


SECTIONS = {
    "🔥 The Record Speaks": [("🔥 The Contention Reel", _view_reel)],
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
