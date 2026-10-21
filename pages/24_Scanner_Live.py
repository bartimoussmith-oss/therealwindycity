from pathlib import PurePosixPath
import datetime as dt
import requests
import streamlit as st

st.set_page_config(page_title='Scanner Live and Archives', page_icon='📻', layout='wide')
REPO = 'bartimoussmith-oss/therealwindycity'
RAW = 'https://raw.githubusercontent.com/' + REPO + '/main/'
WEB = 'https://github.com/' + REPO + '/blob/main/'

@st.cache_data(ttl=60, show_spinner=False)
def read_json(path):
    if not path.startswith('scanner-results/') or '..' in PurePosixPath(path).parts:
        return None
    try:
        response = requests.get(RAW + path, timeout=20)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        return None

@st.cache_data(ttl=300, show_spinner=False)
def list_directory(path):
    try:
        response = requests.get('https://api.github.com/repos/' + REPO + '/contents/' + path, params={'ref': 'main'}, timeout=20)
        response.raise_for_status()
        result = response.json()
        return result if isinstance(result, list) else []
    except (requests.RequestException, ValueError):
        return []

def transcript(path):
    data = read_json(path)
    if not isinstance(data, dict):
        st.info('Transcript is not available at this checkpoint.')
        return
    st.caption('Source file: ' + path)
    st.link_button('Open committed source', WEB + path)
    if data.get('source'):
        st.write('Recording source:', data['source'])
    if data.get('credit'):
        st.write('Credit:', data['credit'])
    if data.get('license'):
        st.write('License:', data['license'])
    for key in ('capture_started_at_utc', 'capture_ended_at_utc', 'metadata'):
        if data.get(key):
            st.write(key, data[key])
    st.caption(data.get('notice', 'Unverified automated radio transcription. Not a verified incident report.'))
    rows = data.get('segments', [])
    if not rows:
        st.info('No transcribed speech segments in this file.')
    for row in rows[:500]:
        st.caption(str(row.get('start_seconds', '?')) + '–' + str(row.get('end_seconds', '?')) + ' seconds from audio start; review required')
        st.text(row.get('text', ''))
        if row.get('review_flags'):
            st.caption('Flags: ' + ', '.join(row['review_flags']))
    if len(rows) > 500:
        st.caption('Display capped at 500 segments; open the source for the full recording.')

def archive_panel(section, title):
    st.subheader(title)
    state = read_json('scanner-results/' + section + '/state.json')
    if not isinstance(state, dict):
        st.info('No readable checkpoint yet; this does not establish that the workflow is stopped.')
        return
    cols = st.columns(3)
    cols[0].metric('Discovered', state.get('discovered_count', len(state.get('archives', {}))))
    cols[1].metric('Completed', state.get('completed_count', len(state.get('completed', []))))
    cols[2].metric('Recordings with errors', len(state.get('errors', {})))
    st.write('Checkpoint status:', state.get('status', 'unknown'))
    st.caption('Last checkpoint: ' + state.get('updated_at_utc', 'unknown'))
    if state.get('blocked'):
        st.error(state.get('block_reason', 'Provider access blocked.'))
    completed = state.get('completed', [])
    if completed:
        chosen = st.selectbox('Recording', list(reversed(completed[-100:])), key=section)
        transcript('scanner-results/' + section + '/recordings/' + chosen + '/transcript.json')

def dashboard():
    st.title('Scanner Live and Archives')
    st.warning('Automated, unverified radio transcriptions—not verified incident reports. No automatic identification of suspects, victims, or officers. Best-effort capture can have gaps.')
    st.caption('Reads committed GitHub results; an open page refreshes about once per minute. Repository publication, transcription, and cache delays mean this is not instantaneous.')
    live_tab, recent_tab, history_tab, correlation_tab = st.tabs(['Live capture', 'Recent archive recovery', 'Historical backfill', 'Socrata correlation'])
    with live_tab:
        entries = list_directory('scanner-results/live-runs')
        runs = sorted([r['name'] for r in entries if r.get('type') == 'dir'], reverse=True)
        if not runs:
            st.info('No readable live-run directory yet. The GitHub listing may also be unavailable or rate-limited; capture is not verified here.')
        else:
            run = st.selectbox('Capture run', runs[:30], key='live_run')
            base = 'scanner-results/live-runs/' + run + '/'
            status = read_json(base + 'status.json')
            if isinstance(status, dict):
                st.write('Reported status:', status.get('status', 'unknown'))
                st.write('Last audio received (UTC):', status.get('last_audio_at_utc'))
                st.write('Last published heartbeat (UTC):', status.get('heartbeat_at_utc'))
                st.write('Bytes received:', status.get('bytes_received', 0))
                st.write('Transcribed segments saved:', status.get('segments_saved', 0))
                last = status.get('last_audio_at_utc')
                if last:
                    try:
                        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(last)).total_seconds()
                        if age > 600:
                            st.warning('Last audio timestamp is over ten minutes old. Do not interpret this checkpoint as proof of current capture.')
                    except (ValueError, TypeError):
                        st.warning('Audio timestamp cannot be interpreted.')
                if status.get('run_ended_at_utc'):
                    st.info('This capture run has ended. Another scheduled run may exist; check the run selector.')
                with st.expander('Connections and sanitized errors'):
                    st.json({'connections': status.get('connections', []), 'errors': status.get('errors', [])})
            chunks = [r['name'] for r in list_directory(base.rstrip('/')) if r.get('name', '').startswith('chunk-') and r['name'].endswith('.json')]
            chunks.sort(key=lambda name: int(name[6:-5]), reverse=True)
            if chunks:
                chunk = st.selectbox('Transcribed audio chunk', chunks, key='live_chunk')
                transcript(base + chunk)
            else:
                st.info('No committed transcript chunk yet for this run.')
    with recent_tab:
        archive_panel('recent', 'Recent archive recovery')
    with history_tab:
        archive_panel('history', 'Historical backfill')
    with correlation_tab:
        st.info('Correlation is not running: a verified local Socrata incident dataset and its field mapping are still required.')
        st.write('Planned evidence: dataset and row ID, event timestamp and time zone, recording ID and offsets, compatible location or incident number, matching reasons, conflicting evidence, and human-review status.')
        st.warning('A similar phrase, name, date, or location is not proof of the same incident. Unmatched recordings and unmatched records must remain visible. Existing arrest-page access controls are not bypassed.')

if st.button('Refresh scanner data'):
    read_json.clear()
    list_directory.clear()
if hasattr(st, 'fragment'):
    st.fragment(run_every=60)(dashboard)()
else:
    dashboard()
    st.caption('This Streamlit version requires the Refresh scanner data button for updates.')
