"""The Real Windy City — HOME.

Multipage layout (2026-09-17 split): every feature lives on its own page under
pages/, sharing one view library (rwc_views.py). This home page shows a live
preview card for each feature — a real, current item pulled from the same
data the page uses (latest alert, newest silent edit, top search hit, a hero,
a vault row, the newest tape…) — with a button that jumps to the full page.

Transparency_Index_App.py stays a byte-identical twin of this file so either
entrypoint boots on Streamlit Cloud.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="The Real Windy City — Heroes of the Public Record",
                   page_icon="🌬️", layout="wide")

import rwc_views as V  # noqa: E402

FEATURES = json.loads((ROOT / "pages" / "_features.json").read_text())
PAGE_OF = {f["key"]: f for f in FEATURES}


# --------------------------------------------------------------------- previews
def _first(rows):
    return rows[0] if rows else None


def _prev_front_page():
    p = ROOT / "public" / "index.html"
    if p.exists():
        import streamlit.components.v1 as components
        components.html(p.read_text(), height=420, scrolling=True)
    else:
        st.info("public/index.html not built yet — civic-cycle builds it.")


def _prev_mission_board():
    a = _first(V._engine_q("SELECT a.created_at, a.term, a.snippet, d.title FROM alerts a "
                           "JOIN documents d ON d.id=a.document_id ORDER BY a.id DESC LIMIT 1"))
    e = _first(V._engine_q("SELECT v.captured_at, v.change_summary, d.title FROM versions v "
                           "JOIN documents d ON d.id=v.document_id WHERE v.seq>1 ORDER BY v.id DESC LIMIT 1"))
    if a:
        st.markdown(f"🚩 **Latest alert** · {a['created_at'][:10]} · “{a['term']}” in *{a['title']}*")
        st.markdown(f"> {a['snippet'][:300]}")
    else:
        st.info("No alerts in the engine ledger yet.")
    if e:
        st.warning(f"⚠️ **Newest silent edit** · {e['captured_at'][:10]} · {e['title']} — {e['change_summary']}")
    else:
        st.success("No silent edits caught — a quiet ledger is a true report.")


def _prev_evidence_vault():
    q = "annexation"
    if V.db is not None and V.ENGINE_DB.exists():
        try:
            conn = V.db.connect(); hits = V.db.search(conn, q); conn.close()
            st.caption(f"🔎 live query **“{q}”** → {len(hits)} document(s)")
            for r in hits[:3]:
                st.markdown(f"**doc #{r['doc_id']}** · `{r['source']}` · {r['title']}")
                if r.get("snip"):
                    st.markdown(f"> {r['snip'][:220]}")
        except Exception as ex:
            st.info(f"Engine search unavailable: {ex}")
    else:
        st.info("Engine not present in this checkout.")
    n_md = len([p for p in ROOT.glob("*.md") if p.name not in V.SKIP])
    st.caption(f"🗄 {n_md} dossiers in the longboxes · 📜 transcript corpus under pipeline/corpus")


def _prev_case_files():
    ver = V._vault_ver(); rows = ver.get("rows", {})
    found = [r for r in rows.values() if r.get("status") == "found-in-record"]
    st.metric("Vault rows verified vs corpus", f"{len(found)} / {len(rows) or 22}")
    r = _first(V._legacy_q(V.VAULT_QUERIES["public_comment_battles"]))
    if r:
        st.markdown("⚔️ **Top battle record:**")
        st.json({k: (str(v)[:120] if v is not None else None) for k, v in list(r.items())[:6]}, expanded=False)


def _prev_roster():
    st.markdown("🦸 Every hero on the roster earned the panel **on the record** — "
                "mic'd, minuted, or published. Open the page for the full roster and the "
                "*Know the enemy — FORCES, not faces* file.")


def _prev_guide():
    st.markdown("🧭 Six questions → a brief built for *you*: who you are, what touches you, "
                "how deep, and how you like your evidence. Open the page to start the wizard.")


def _prev_tapes(reel=False):
    manifest = ROOT / "pipeline" / "cityvideos.json"
    renders = sorted((ROOT / "pipeline" / "renders").glob("*.mp4")) if (ROOT / "pipeline" / "renders").exists() else []
    if renders:
        newest = max(renders, key=lambda p: p.stat().st_mtime)
        st.markdown(f"🎬 **Newest tape:** `{newest.name}`")
        st.video(str(newest))
    elif manifest.exists():
        try:
            m = json.loads(manifest.read_text())
            item = m[0] if isinstance(m, list) else next(iter(m.values()))
            st.json(item, expanded=False)
        except Exception:
            st.info("Tape manifest present; open the page.")
    else:
        st.info("Renders live on the archive; open the page for the full theater.")


def _prev_miller():
    idx = ROOT / "pipeline" / "miller_interventions.json"
    if idx.exists():
        try:
            data = json.loads(idx.read_text())
            items = data if isinstance(data, list) else data.get("items", [])
            st.markdown(f"🎬 **{len(items)} Miller interventions** cued, on loop.")
            if items:
                it = items[0]
                st.json({k: it[k] for k in list(it)[:5]}, expanded=False)
        except Exception:
            st.info("Miller index present; open the page.")
    else:
        st.info("Miller index not built in this checkout.")


def _prev_signals():
    drafts = _first(V._engine_q("SELECT COUNT(*) n FROM requests WHERE status='draft'"))
    st.metric("PRA drafts waiting", (drafts or {}).get("n", 0))
    st.markdown(f"💡 Tips come in via the [GitHub issue template]({V._TIP}); letters only go out with your signature.")


def _prev_join():
    st.markdown("✋ **New heroes wanted.** Every power on this roster started as one citizen, "
                "one mic, three minutes.")


def _prev_index():
    ents = sorted((ROOT / "Entity_Database").glob("*.json")) if (ROOT / "Entity_Database").exists() else []
    st.metric("Entity dossiers indexed", len(ents))
    if ents:
        try:
            e = json.loads(ents[0].read_text())
            st.json({k: e[k] for k in list(e)[:5]}, expanded=False)
        except Exception:
            pass


PREVIEW = {
    "◈ Ledger HQ": _prev_front_page,
    "📡 Mission Board": _prev_mission_board,
    "🔎 Evidence Vault": _prev_evidence_vault,
    "🦸 Hero Roster": _prev_roster,
    "🧭 Choose Your Mission": _prev_guide,
    "🔥 Origin Tapes": lambda: _prev_tapes(reel=True),
    "🎬 The Tapes": _prev_tapes,
    "✉️ Signals & Paperwork": _prev_signals,
    "🗃 Case Files": _prev_case_files,
    "✋ Join the Roster": _prev_join,
    "__INDEX__": _prev_index,
}
EXTRA = [  # the two pre-existing standalone pages
    dict(page="16a_Miller_Tapes", key="🎬 Miller Tapes", icon="🎬", blurb="Every intervention, on loop", prev=_prev_miller),
    dict(page="16b_Screening_Room", key="🎞 Screening Room", icon="🎞", blurb="Montage theater", prev=_prev_tapes),
]

# --------------------------------------------------------------------- render
V.render_ledger_header()
st.markdown("### 📖 Chapters — live previews. Click through for the full page.")

cards = [dict(f, prev=PREVIEW[f["key"]]) for f in FEATURES] + EXTRA
cols = st.columns(2)
for i, f in enumerate(cards):
    title = "🏛 Transparency Index" if f["key"] == "__INDEX__" else f["key"]
    with cols[i % 2]:
        with st.container(border=True):
            st.markdown(f"#### {title}")
            st.caption(f["blurb"])
            try:
                f["prev"]()
            except Exception as ex:  # a broken preview must never take the home page down
                st.info(f"preview unavailable: {ex}")
            st.page_link(f"pages/{f['page']}.py", label=f"{f['icon']} Open {title} →")

V.footer()
