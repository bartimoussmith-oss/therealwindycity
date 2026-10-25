"""Integrated Civic Atlas + opt-in Dais Lens; no secondary service required."""
from pathlib import Path
import json
import sys
import streamlit as st
import streamlit.components.v1 as components

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
st.set_page_config(page_title='Civic Atlas + Dais Lens',page_icon='▣',layout='wide')
from civic_atlas.server import Corpus
from civic_atlas.streamlit_integration import evidence_map_html, render_lens_option

@st.cache_resource(ttl=600,show_spinner='Indexing local public-record material…')
def corpus():
    return Corpus(ROOT)

st.title('Civic Atlas + Dais Lens')
st.caption('Follow the record. Enlarge the visible dais. Read-only research tools, now inside The Real Windy City.')
map_tab,lens_tab=st.tabs(['⌘ Agenda evidence map','▣ Dais Lens'])
with map_tab:
    try:
        c=corpus()
    except (OSError,ValueError) as error:
        st.error(f'Local source index unavailable: {error}')
        c=None
    if c:
        counts={kind:sum(r['kind']==kind for r in c.records) for kind in ['Meeting transcript','Repository document','Archived agenda']}
        st.caption(f"Indexed: {counts['Meeting transcript']} meeting entries · {counts['Repository document']} repository documents · {counts['Archived agenda']} source agenda(s). Not complete historical coverage: PDFs and other repositories are not indexed.")
        left,right=st.columns([1,2])
        with left:
            mode=st.radio('Start from',['Topic','Archived agenda item','Paste agenda'],key='atlas_mode')
            if mode=='Archived agenda item':
                if c.agendas:
                    ai=st.selectbox('Source agenda',range(len(c.agendas)),format_func=lambda i:c.agendas[i]['title'])
                    items=c.agendas[ai]['items']
                    if items:
                        ix=st.selectbox('Agenda item',range(len(items)),format_func=lambda i:items[i]['title'])
                        query=items[ix]['title']
                        if items[ix]['url'].startswith('https://'):st.link_button('Open official item / video',items[ix]['url'])
                    else:query=''
                else:st.info('No archived HTML agendas in this checkout.');query=''
            elif mode=='Paste agenda':
                pasted=st.text_area('Paste agenda text',help='Text is processed by this app, not sent to an AI service.')
                lines=[line.strip() for line in pasted.splitlines() if len(line.strip())>8][:100]
                query=st.selectbox('Line to investigate',lines) if lines else ''
            else:query=st.text_input('Topic, ordinance, or phrase','Data center')
            st.warning('Edges mean shared text—not a proven personal, financial, legal, or causal relationship. Repository research is not an official record.')
            hits=c.search(query) if query else []
            st.caption(f'{len(hits)} ranked leads; first 12 shown as graph nodes.')
            st.download_button('Export leads (JSON)',json.dumps({'topic':query,'relation':'Lexical overlap; human source review required','records':hits},ensure_ascii=False,indent=2),'civic-atlas-leads.json','application/json')
        with right:
            if hits:components.html(evidence_map_html(query,hits),height=850,scrolling=True)
            else:st.info('Choose an agenda item or enter a searchable topic.')
        if hits:
            st.subheader('Inspect the source record')
            rid=st.selectbox('Matched source', [h['id'] for h in hits],format_func=lambda i:c.byid[i]['title'])
            record=c.byid[rid]
            st.caption(f"{record['kind']} · {record.get('date') or 'Undated'} · {record['path']}")
            st.code(record['text'],language=None)
            st.caption('Caption-derived meeting text and speaker attribution may contain errors. Check the original audio and official documents before asserting a finding.')
with lens_tab:
    st.subheader('One video. Every visible seat.')
    st.write('Use the Lens option alongside existing video players, or open the universal workspace here. For YouTube and other embedded players, share the player’s tab/window with explicit browser permission.')
    render_lens_option('universal_page','Any meeting video')
