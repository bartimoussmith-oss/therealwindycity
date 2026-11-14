"""Fireflies-style meeting intelligence — the ledger's console front end.

Reads the generated fireflies/ledger/ + fireflies/briefs/ outputs (build with
`python3 -m fireflies build`). Extractive & pattern-based only: every claim
shown carries a verbatim quote and a source locator. Search runs over the
read-only corpus via fireflies.search.
"""
import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

st.set_page_config(page_title="Meeting Intelligence", layout="wide")
st.title("Meeting Intelligence")
st.caption(
    "Fireflies-style briefs over 17+ years of meeting transcripts, agenda items and "
    "supporting documents. Extractive & pattern-based only — nothing is paraphrased "
    "into new claims; every line carries a verbatim quote and a source locator. "
    "Verify: `python3 -m fireflies verify`.")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fireflies"
LEDGER = OUT / "ledger" / "meetings.jsonl"
TRACKER = OUT / "ledger" / "agenda_tracker.csv"
TOPICS = OUT / "ledger" / "topics.json"


@st.cache_data(show_spinner=False)
def load_ledger():
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.open(encoding="utf-8") if line.strip()]


@st.cache_data(show_spinner=False)
def load_topics():
    if not TOPICS.exists():
        return {"entities": []}
    return json.loads(TOPICS.read_text(encoding="utf-8"))


@st.cache_resource(show_spinner=False)
def load_meetings():
    from fireflies.sources import load_meetings as _load
    return _load(ROOT)


ledger = load_ledger()
if not ledger:
    st.warning("No ledger found. Run `python3 -m fireflies build` first.")
    st.stop()

view = st.sidebar.radio("View", ["Meeting briefs", "Agenda tracker", "Search", "Topics"])
bodies = sorted({r["body"] for r in ledger})
years = sorted({(r["date"] or "")[:4] for r in ledger if r["date"]}, reverse=True)


def ts_link(url: str, ts: str) -> str:
    if not url or not ts or ":" not in ts:
        return ""
    try:
        h, m, s = (int(x) for x in ts.split(":"))
    except ValueError:
        return ""
    if "youtube.com" in url or "youtu.be" in url:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}t={h * 3600 + m * 60 + s}"
    return ""


if view == "Meeting briefs":
    b = st.sidebar.selectbox("Body", ["(all)"] + bodies)
    y = st.sidebar.selectbox("Year", ["(all)"] + years)
    rows = [r for r in ledger
            if (b == "(all)" or r["body"] == b)
            and (y == "(all)" or (r["date"] or "").startswith(y))]
    rows.sort(key=lambda r: (r["date"] or "9999"), reverse=True)
    if not rows:
        st.stop()
    labels = {f"{r['date'] or 'undated'} · {r['body_label']} · {r['meeting_id']}": r
              for r in rows}
    pick = st.selectbox("Meeting", list(labels))
    rec = labels[pick]

    st.subheader(f"{rec['body_label']} — {rec['date'] or 'undated'}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Agenda items", rec["stats"]["items"])
    c2.metric("Actions/decisions", rec["stats"]["actions"])
    c3.metric("Words of record", f"{rec['stats']['words']:,}")
    c4.metric("Caption segments", rec["stats"]["segments"])
    if rec["flags"]:
        st.caption("Flags: " + " · ".join(sorted(set(rec["flags"]))))
    links = [f"[{k}]({v})" for k, v in rec["urls"].items() if v]
    if links:
        st.markdown("Record links: " + " · ".join(links))

    if rec.get("attendance", {}).get("quote"):
        st.markdown("**Attendance (verbatim)**")
        st.code(rec["attendance"]["quote"], language=None)

    if rec["overview"]["sentences"]:
        st.markdown(f"**Overview** — extractive, method `{rec['overview']['method']}`")
        for s in rec["overview"]["sentences"]:
            loc = s["locator"]
            tag = f"¶{loc['para']}" if loc.get("para") else f"@{loc.get('char', 0)}"
            st.markdown(f"- {s['sentence']} *({tag})*")

    if rec["outline"]:
        st.markdown("**Outline**")
        yurl = rec["urls"].get("youtube", "")
        for i, o in enumerate(rec["outline"], 1):
            link = ts_link(yurl, o.get("start", "")) or o.get("deep_link", "")
            span = f"{o['start']}–{o['end']}" if o.get("end") else (o.get("start") or "")
            jump = f" [▶]({link})" if link else ""
            st.markdown(f"{i}. **{o['title'][:130]}** — {span} *({o['method']} / "
                        f"{o['confidence']})*{jump}")

    if rec["items"]:
        st.markdown("**Agenda items & supporting documents**")
        for it in rec["items"]:
            with st.expander(f"{it['item_id']} · {it['title'][:120]}"):
                meta = [f"kind: {it['kind']}"]
                if it["reading"]:
                    meta.append(f"reading: {it['reading']}")
                if it["number"]:
                    meta.append(f"no.: {it['number']}")
                if it["title_guess"]:
                    meta.append("title derived from speech cue")
                st.caption(" · ".join(meta))
                for q in it["quotes"]:
                    loc = q["locator"]
                    tag = loc.get("ts") or (f"¶{loc['para']}" if loc.get("para")
                                            else loc.get("ref", ""))
                    st.markdown(f"- *(`{q['method']}`)* “{q['quote']}” *({tag})*")
                if it["expected_action"]:
                    st.markdown(f"- expected ACTION (agenda): {it['expected_action']}")
                for d in it["docs"]:
                    ref = d.get("url") or d.get("ref") or ""
                    st.markdown(f"- supporting doc ({d.get('kind', '?')}): "
                                f"{d.get('title', '')} — {ref}")

    if rec["actions"]:
        st.markdown("**Decisions & actions** (verbatim, pattern-tagged)")
        for a in rec["actions"]:
            loc = a["locator"]
            tag = loc.get("ts") or (f"¶{loc['para']}" if loc.get("para") else loc.get("ref", ""))
            who = f" · {a['who']}" if a["who"] else ""
            item = f" · {a['item_id']}" if a["item_id"] else ""
            st.markdown(f"- **{a['type']}**{who}{item}: “{a['quote']}” *({tag})*")

    if rec["entities"]:
        st.markdown("**Entities**")
        st.markdown(" · ".join(
            f"`{e['type']}` **{e['value']}** ×{e['count']}" for e in rec["entities"][:25]))
    if rec["keywords"]:
        st.markdown("**Keywords (extractive):** " + ", ".join(
            f"{k['term']} ({k['count']})" for k in rec["keywords"]))

elif view == "Agenda tracker":
    import csv
    b = st.sidebar.selectbox("Body", ["(all)"] + bodies)
    y = st.sidebar.selectbox("Year", ["(all)"] + years)
    q = st.sidebar.text_input("Filter title/quotes")
    if TRACKER.exists():
        with TRACKER.open(encoding="utf-8") as fh:
            trows = list(csv.DictReader(fh))
        keep = [r for r in trows
                if (b == "(all)" or r["body"] == b)
                and (y == "(all)" or (r["date"] or "").startswith(y))
                and (not q or q.lower() in (r["title"] + r["outcome_quotes"]).lower())]
        st.caption(f"{len(keep):,} agenda items (of {len(trows):,}). "
                   "One row per item: docs, chapter, expected action, outcome quotes.")
        st.dataframe(keep, width="stretch", height=500)
        st.download_button("Download tracker CSV",
                           TRACKER.read_bytes(), file_name="agenda_tracker.csv")
    else:
        st.warning("agenda_tracker.csv missing — run `python3 -m fireflies build`.")

elif view == "Search":
    from fireflies.search import search as run_search
    query = st.text_input("Search every transcript, minutes and packet text "
                          "(whitespace-flexible phrase match)")
    b = st.sidebar.selectbox("Body", ["(all)"] + bodies)
    y = st.sidebar.selectbox("Year", ["(all)"] + years)
    if query:
        hits = run_search(query, load_meetings(),
                          body=None if b == "(all)" else b,
                          year=None if y == "(all)" else y,
                          max_hits=50)
        st.caption(f"{len(hits)} hits")
        for h in hits:
            loc = h["locator"]
            tag = loc.get("ts") or (f"¶{loc['para']}" if loc.get("para") else loc["ref"])
            st.markdown(f"**[{h['date'] or 'undated'}] {h['body']}** — `{tag}` · "
                        f"{h['meeting_id']}")
            s, e = h["match_start"], h["match_end"]
            sn = h["snippet"]
            st.markdown(f"> {sn[:s]}**`{sn[s:e]}`**{sn[e:]}")

else:  # Topics
    topics = load_topics()
    ents = topics.get("entities", [])
    y = st.sidebar.selectbox("Year", ["(all)"] + years)
    if y != "(all)":
        ents = [e for e in ents if any(m["date"].startswith(y) for m in e["meetings"])]
    st.caption(f"{len(ents):,} tracked entities (ordinances, resolutions, statute "
               "cites) across the corpus — first/last seen, mentions, meetings.")
    import pandas as pd
    df = pd.DataFrame([{
        "type": e["type"], "value": e["value"], "mentions": e["mentions"],
        "meetings": len(e["meetings"]),
        "first_seen": e["first_seen"], "last_seen": e["last_seen"],
    } for e in ents[:400]])
    st.dataframe(df, width="stretch", height=400)
    top = ents[:25]
    if top:
        st.bar_chart(pd.DataFrame(
            [{"entity": f"{e['value']}", "mentions": e["mentions"]} for e in top]
        ).set_index("entity"))
    with st.expander("Timeline detail (top 25)"):
        for e in top:
            st.markdown(f"**{e['type']} {e['value']}** — {e['first_seen']} → "
                        f"{e['last_seen']} · {e['mentions']} mentions in "
                        f"{len(e['meetings'])} meetings")
            for m in e["meetings"][:8]:
                ex = (m.get("example") or {}).get("quote", "")
                st.markdown(f"- [{m['date']}] {m['body']} ×{m['count']}"
                            + (f" — “{ex[:150]}”" if ex else ""))
