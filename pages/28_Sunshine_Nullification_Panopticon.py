"""Public, snapshot-only Sunshine coverage browser; no private API or vault access."""
import hashlib
import inspect
import json
from datetime import date
from pathlib import Path
import streamlit as st

ROOT=Path(__file__).resolve().parents[1]
SNAPSHOT=ROOT/'data/sunshine_public_export.json'
st.set_page_config(page_title='Sunshine Evidence Coverage | The Real Windy City',page_icon='☀️',layout='wide')
st.title('Sunshine Evidence Coverage')
st.caption('Wyoming roster · nationwide domain-discovery pilot · explicitly approved findings')
st.warning('Discovery coverage is not a legal audit or a compliance clearance. No keyword match, archive change, missing text, or access feature alone establishes misconduct.')

@st.cache_data(ttl=120)
def load_snapshot(path):
    p=Path(path)
    if not p.is_file():return None,None,'No approved snapshot has been generated.'
    try:
        raw=p.read_bytes()
        payload=json.loads(raw)
        if payload.get('schema_version')!='sunshine-public-1.0' or payload.get('publication_tier')!='PUB_TIER_1_PUBLIC':
            return None,None,'Snapshot schema or publication classification is invalid.'
        if not isinstance(payload.get('summary_metrics'),dict):return None,None,'Snapshot has invalid summary metrics.'
        for key in ('wyoming_roster','approved_findings','nationwide_discovery'):
            if not isinstance(payload.get(key),list) or not all(isinstance(row,dict) for row in payload[key]):return None,None,'Snapshot has an invalid record collection.'
        return payload,hashlib.sha256(raw).hexdigest(),None
    except (OSError,UnicodeError,ValueError):return None,None,'Snapshot could not be read. No fallback findings are supplied.'

def show_table(items):
    kwargs={'width':'stretch'} if 'width' in inspect.signature(st.dataframe).parameters else {'use_container_width':True}
    st.dataframe(items,hide_index=True,**kwargs)

snapshot,digest,error=load_snapshot(str(SNAPSHOT))
if error:
    st.info(error)
    st.stop()
metrics=snapshot['summary_metrics']
cols=st.columns(4)
cols[0].metric('Wyoming roster rows',metrics.get('wyoming_roster_rows',0))
cols[1].metric('Nationwide pilot candidates',metrics.get('nationwide_pilot_candidates',0))
cols[2].metric('Approved findings',metrics.get('approved_findings',0))
cols[3].metric('Registry domain rows',metrics.get('national_registry_domain_rows') or 0)
st.caption('Snapshot generated: '+snapshot.get('generated_utc','unknown'))
st.code('Snapshot SHA-256: '+digest,language=None)
for limitation in snapshot.get('limitations',[]):st.caption('• '+limitation)
wy,us,verified,request=st.tabs(['Wyoming coverage','Nationwide discovery','Approved findings','Records-request worksheet'])
with wy:
    st.subheader('Wyoming roster — not a 99-town audit clearance')
    items=snapshot['wyoming_roster']
    county=st.selectbox('County',['All']+sorted({r.get('county','') for r in items if r.get('county')}))
    selected=[r for r in items if county=='All' or r.get('county')==county]
    show_table(selected)
    st.caption('Unknown findings and unreviewed access arrangements are not represented as zero violations or confirmed participation rights.')
with us:
    st.subheader('Nationwide domain-discovery pilot')
    items=snapshot['nationwide_discovery']
    state=st.selectbox('State',['All']+sorted({r.get('state','') for r in items if r.get('state')}))
    selected=[r for r in items if state=='All' or r.get('state')==state]
    if selected:show_table(selected)
    else:st.info('No discovery rows in this snapshot. This does not imply complete coverage.')
    st.caption('A CISA domain row is not a unique government. This view does not establish population, prior news coverage, litigation history, hostility, or wrongdoing.')
with verified:
    st.subheader('Explicitly approved findings only')
    findings=snapshot['approved_findings']
    if not findings:st.info('No findings have passed the publication approval gate. No Pine Bluffs or other allegations are supplied as fallback content.')
    for item in findings:
        with st.expander(item['municipality']+' — '+item.get('meeting_date','date unverified')):
            st.write(item['summary']);st.code(item['quote'],language=None)
            st.link_button('Inspect primary source',item['source_url'])
            st.code('Artifact SHA-256: '+item['sha256'],language=None)
            st.caption(item['review_status']+' · '+item['evidence_tier'])
with request:
    st.subheader('Neutral records-request worksheet — unsent draft')
    st.caption('Educational drafting aid, not legal advice. Confirm the applicable law, custodian, exemptions, fees, standing, and deadlines separately. This page sends nothing and does not assert a violation.')
    body=st.text_input('Governing body',value='')
    meeting=st.text_input('Meeting date or date range',value='')
    records=st.text_area('Describe existing records sought',value='Posted notice, agenda, approved open-session minutes, and any existing open-session audio or video recording.')
    text=(f'Subject: Request for existing public meeting records\nDate: {date.today().isoformat()}\n'
          f'To: Records custodian, {body or "[governing body]"}\n\n'
          f'Please provide electronic copies of the following existing records for {meeting or "[date range]"}:\n{records}\n\n'
          'Please identify any applicable exemption for material withheld and advise of any anticipated fees before processing. '
          'This request seeks existing records, not the creation of a new analysis.\n\n[Name and preferred contact method]\n')
    st.text_area('Review draft before use',text,height=240)
    st.download_button('Download unsent draft',text,file_name='meeting-records-request-draft.txt',mime='text/plain')
st.download_button('Download public snapshot',json.dumps(snapshot,ensure_ascii=False,indent=2),file_name='sunshine-public-snapshot.json',mime='application/json')
