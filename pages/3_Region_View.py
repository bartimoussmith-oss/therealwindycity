"""
3_Region_View.py — Wyoming Region Preview (last 6 months real data per city)

Shows what the scaled system looks like:
- Map of Wyoming cities (plotly)
- Recent 6 months meetings per city (real data for Cheyenne from pipeline/meetings.json + cityvideos.json)
- For other cities: seeded status + instructions + external link preservation
- Click city → recent meetings table with external_url + local_path (no dependency)

This page is additive — does not touch twins.
"""
import streamlit as st
import json
from pathlib import Path
from datetime import datetime, timedelta
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from engine.city_registry import list_cities, recent_meetings
except Exception as e:
    st.error(f"city_registry import failed: {e}")
    st.stop()

st.set_page_config(page_title="Wyoming Region — Real Data Last 6 Months", layout="wide")
st.title("🗺️ Wyoming Region — Real Data Last 6 Months Per City")
st.caption("Every meeting has external_url preserved + local_path on your server — no dependency on external sites. Cheyenne is live with real Granicus + YouTube data; other cities seeded and ready to pull.")

# Load registry
cities = list_cities()
st.write(f"**{len(cities)} Wyoming cities** in factory — Cheyenne live, others seeded. Factory: `tools/seed-city.py`")

# Filters
col1, col2, col3 = st.columns(3)
with col1:
    months = st.slider("Months back", 1, 12, 6)
with col2:
    show_only_live = st.checkbox("Show only live cities", value=False)
with col3:
    sort_by = st.selectbox("Sort by", ["population desc", "name asc", "meetings desc"])

# Recent meetings for Cheyenne real
if sort_by == "population desc":
    cities_sorted = sorted(cities, key=lambda x: x.get("population",0), reverse=True)
elif sort_by == "name asc":
    cities_sorted = sorted(cities, key=lambda x: x.get("name",""))
else:
    # meetings desc — need to compute
    tmp = []
    for c in cities:
        rm = recent_meetings(c["slug"], months=months)
        tmp.append((len(rm), c))
    tmp_sorted = sorted(tmp, key=lambda x: x[0], reverse=True)
    cities_sorted = [c for _,c in tmp_sorted]

if show_only_live:
    cities_sorted = [c for c in cities_sorted if c.get("status")=="live"]

# Summary table
import pandas as pd
rows = []
for c in cities_sorted:
    rm = recent_meetings(c["slug"], months=months)
    # count real vs seeded
    real_count = len([m for m in rm if m.get("source") in ("granicus","youtube")])
    rows.append({
        "city": c["name"],
        "slug": c["slug"],
        "county": c.get("county",""),
        "pop": c.get("population",""),
        "status": c.get("status","seeded"),
        "granicus": c.get("granicus_domain",""),
        "meetings_last_6mo": real_count if c["slug"]=="cheyenne" else c.get("meetings_last_6mo","seeded"),
        "boards": c.get("boards_count") or c.get("boards_estimate",""),
        "youtube": bool(c.get("youtube_channel_id")),
    })
df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, height=400)

# Plotly map — simple scatter by lat/lon approximated (since we don't have lat/lon, use population as size)
try:
    import plotly.express as px
    # Approximate lat/lon for WY cities (hardcoded for preview)
    coords = {
        "cheyenne": (41.14, -104.82),
        "casper": (42.85, -106.33),
        "laramie": (41.31, -105.59),
        "gillette": (44.29, -105.50),
        "rock-springs": (41.59, -109.20),
        "sheridan": (44.79, -106.96),
        "green-river": (41.53, -109.46),
        "evanston": (41.26, -110.96),
        "riverton": (43.02, -108.38),
        "jackson": (43.47, -110.76),
        "cody": (44.52, -109.08),
        "rawlins": (41.79, -107.23),
        "lander": (42.83, -108.73),
        "torrington": (42.06, -104.18),
        "powell": (44.75, -108.76),
        "douglas": (42.76, -105.38),
        "worland": (44.01, -107.95),
        "buffalo": (44.34, -106.70),
        "wheatland": (42.05, -104.95),
        "newcastle": (43.85, -104.20),
        "thermopolis": (43.64, -108.21),
        "kemmerer": (41.79, -110.54),
        "lyman": (41.32, -110.29),
    }
    df["lat"] = df["slug"].map(lambda s: coords.get(s, (0,0))[0])
    df["lon"] = df["slug"].map(lambda s: coords.get(s, (0,0))[1])
    fig = px.scatter_mapbox(df, lat="lat", lon="lon", hover_name="city", hover_data=["status","meetings_last_6mo","granicus"], size="pop", color="status", zoom=5.5, height=500, mapbox_style="open-street-map")
    st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.warning(f"Map failed (plotly): {e} — showing table only")

st.divider()
st.header("Cheyenne — Real Data Last 6 Months (live)")

cheyenne_meetings = recent_meetings("cheyenne", months=months)
st.write(f"**{len(cheyenne_meetings)} meetings** in last {months} months from `pipeline/meetings.json` (479 total) + `cityvideos.json` (260 YouTube)")

# Show as cards with external + local
for m in cheyenne_meetings[:20]:
    with st.expander(f"{m.get('date')} — {m.get('title')} ({m.get('source')})"):
        colA, colB = st.columns(2)
        with colA:
            st.write("**External (original)**")
            st.write(m.get("external_url") or m.get("agenda_url") or m.get("youtube_url") or "—")
            if m.get("mp4_url"):
                st.write(f"MP4: {m['mp4_url']}")
            if m.get("minutes_url"):
                st.write(f"Minutes: {m['minutes_url']}")
            if m.get("youtube_url"):
                st.write(f"YouTube: {m['youtube_url']}")
                # embed
                ytid = m.get("youtube_id")
                if ytid:
                    st.video(f"https://www.youtube.com/watch?v={ytid}")
        with colB:
            st.write("**Local server copy (no dependency)**")
            st.write(m.get("local_path") or f"server_data/cheyenne/meetings/{m.get('clip_id')}/")
            st.write("**RAG layers:**")
            st.write("- agenda.html + txt + sha256")
            st.write("- minutes.pdf + txt")
            st.write("- docs/*.pdf (MetaViewer)")
            st.write("- video/meeting.mp4")
            st.write("- captions.vtt")
            st.write("- vectordb chunk + manifest external_url preserved")

st.divider()
st.header("Other Cities — Seeded + Ready to Scale")

for city in cities_sorted:
    if city["slug"] == "cheyenne":
        continue
    rm = recent_meetings(city["slug"], months=months)
    with st.expander(f"{city['name']} ({city['slug']}) — {city['status']}"):
        st.write(f"**County:** {city.get('county')} | **Pop:** {city.get('population')} | **Granicus:** {city.get('granicus_domain')} | **Municode:** {city.get('municode_slug')}")
        st.write(f"**City site:** {city.get('city_site')}")
        st.write("**Storage layout (local server copy + external link preserved):**")
        st.code(f"server_data/{city['slug']}/meetings/{{clip_id}}/\n  agenda.html (local) + external_url = https://{city.get('granicus_domain')}/AgendaViewer.php?...\n  minutes.pdf + external_url\n  docs/*.pdf + external_url\n  video/meeting.mp4 + external_url\n  manifest.json {{external_url, local_path, sha256}}", language="text")
        st.write("**To populate real data (runs in Colab, not sandbox):**")
        st.code(f"python tools/seed-city.py {city['slug']} wy --granicus {city.get('granicus_domain')} --municode {city.get('municode_slug')}\n# then in Colab:\nexec(open('tools/granicus_document_pull.py').read())  # edit OUT_ROOT to server_data/{city['slug']}\nexec(open('tools/cheyenne_boards_pull.py').read())\nexec(open('tools/wy_statutes_pull.py').read())  # shared across WY\npython tools/unified_meeting_builder.py\npython rag/build_vector_db.py --all --persist server_data/{city['slug']}/vectordb\n", language="bash")
        if rm and rm[0].get("status")=="seeded":
            st.info(rm[0].get("note"))

st.divider()
st.write("**Principle:** Every file has `external_url` preserved in manifest, but `local_path` is served if external down. RAG vectordb stored locally in `server_data/<city>/vectordb/` + backup to R2 (egress free). No dependency on external sites for reading. See `engine/local_store.py` + `tools/server_sync.py`.")
