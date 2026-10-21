import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import requests

ROOT = 'https://www.broadcastify.com'
OUT = Path('scanner-results/history')
OUT.mkdir(parents=True, exist_ok=True)
STATE = OUT / 'state.json'
now = dt.datetime.now(ZoneInfo('America/Denver')).date()
state = json.loads(STATE.read_text()) if STATE.exists() else {
    'feed_id': '47003', 'first_date': str(now - dt.timedelta(days=364)),
    'last_date': str(now), 'next_date': str(now - dt.timedelta(days=364)),
    'inventory_complete': False, 'archives': {}, 'completed': [],
    'errors': {}, 'sample_complete': False, 'blocked': False,
    'notice': 'Public unverified automated transcripts. Retention-window snapshot, not a guarantee of complete historical coverage.'
}
started = time.monotonic()
model = None

def save():
    state['updated_at_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    state['completed_count'] = len(state['completed'])
    state['discovered_count'] = len(state['archives'])
    state['status'] = ('blocked' if state['blocked'] else 'complete' if state['inventory_complete'] and len(state['completed']) == len(state['archives']) else 'in_progress')
    STATE.write_text(json.dumps(state, indent=2) + '\n')

def block(message):
    state['blocked'] = True
    state['block_reason'] = message
    save()
    raise RuntimeError('Provider access blocked; automatic processing paused.')

session = requests.Session()
session.headers['User-Agent'] = 'LaramieAuthorizedArchiveBackfill/1.0'

def api(path, params):
    time.sleep(2)
    response = session.get(ROOT + path, params=params, timeout=45, allow_redirects=False)
    if response.status_code in (401, 403, 429):
        block('Provider returned HTTP ' + str(response.status_code))
    if response.status_code != 200:
        raise RuntimeError('Provider API request failed: HTTP ' + str(response.status_code))
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError('Unexpected provider API structure.')
    return payload

def transcribe(archive_id, sample=False):
    global model
    if not re.fullmatch(r'47003-[0-9]+', archive_id):
        raise RuntimeError('Unexpected archive identifier.')
    metadata = api('/archives/api/play.php', {'id': archive_id})
    url = urljoin(ROOT, metadata.get('url', ''))
    if not metadata.get('url') or urlparse(url).scheme != 'https':
        raise RuntimeError('Playback URL missing or unsafe.')
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    if model is None:
        model = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=2)
    with tempfile.TemporaryDirectory() as temp:
        audio = Path(temp) / 'audio.mp3'
        with session.get(url, stream=True, timeout=(30, 60)) as response:
            if response.status_code in (401, 403, 429):
                block('Audio provider returned HTTP ' + str(response.status_code))
            if response.status_code != 200 or any(t in response.headers.get('Content-Type', '').lower() for t in ('text/', 'json')):
                raise RuntimeError('Audio unavailable or non-audio response.')
            with audio.open('wb') as output:
                for chunk in response.iter_content(65536):
                    output.write(chunk)
                    if output.tell() > 100_000_000:
                        raise RuntimeError('Recording exceeds 100 MB safety limit.')
        waveform = decode_audio(str(audio), sampling_rate=16000)
        segments = []
        for offset in range(0, len(waveform), 30 * 16000):
            window = waveform[offset:offset + 30 * 16000]
            decoded, _ = model.transcribe(window, language='en', beam_size=5, temperature=0.0,
                condition_on_previous_text=False, word_timestamps=True, vad_filter=True,
                vad_parameters={'min_silence_duration_ms': 500}, hallucination_silence_threshold=1.0)
            for segment in decoded:
                words = [{'start_seconds': w.start + offset / 16000, 'end_seconds': w.end + offset / 16000,
                          'text': w.word, 'probability': w.probability} for w in (segment.words or [])]
                flags = ['unverified']
                if segment.avg_logprob < -1 or segment.no_speech_prob > 0.6 or segment.compression_ratio > 2.4:
                    flags.append('low_confidence_or_repetition')
                if any(w['probability'] < 0.5 for w in words):
                    flags.append('low_confidence_words')
                if segment.end - segment.start > 30:
                    flags.append('implausible_segment_duration')
                segments.append({'start_seconds': segment.start + offset / 16000,
                    'end_seconds': segment.end + offset / 16000, 'text': segment.text.strip(),
                    'words': words, 'review_flags': flags})
    destination = OUT / ('quality-sample' if sample else 'recordings') / archive_id
    destination.mkdir(parents=True, exist_ok=True)
    result = {'archive_id': archive_id, 'feed_id': '47003', 'model': 'small.en',
        'source': ROOT + '/archives/feed/47003/' + archive_id,
        'credit': metadata.get('feedDescr', 'Laramie County Law Enforcement'),
        'license': 'https://creativecommons.org/licenses/by/3.0/us/',
        'metadata': {key: metadata.get(key) for key in ['dateDisplay', 'startDisplay', 'endDisplay', 'tzDisplay']},
        'notice': 'Unverified automated transcription. Not a verified incident report. Offsets are not wall-clock times. Independent 30-second windows can split words at boundaries.',
        'review_required': True, 'duration_seconds': len(waveform) / 16000, 'segments': segments}
    (destination / 'transcript.json').write_text(json.dumps(result, indent=2) + '\n')
    header = '\n'.join([result['notice'], result['credit'], result['source'], result['license']])
    lines = [f"[{s['start_seconds']:.1f}-{s['end_seconds']:.1f}] {s['text']}" for s in segments]
    (destination / 'transcript.txt').write_text(header + '\n' + '\n'.join(lines) + '\n')

def main():
    if state['blocked'] or state.get('status') == 'complete':
        return
    if not os.environ.get('BC_USER') or not os.environ.get('BC_PASS'):
        block('Missing existing Broadcastify secrets.')
    response = session.post(ROOT + '/login/', data={'username': os.environ['BC_USER'], 'password': os.environ['BC_PASS'], 'action': 'auth', 'redirect': ROOT}, allow_redirects=False, timeout=30)
    if not any(c.name == 'bcfyuser1' and c.value for c in session.cookies):
        block('Broadcastify login failed; credentials and response withheld.')
    if not state['sample_complete']:
        transcribe('47003-1792597004', sample=True)
        state['sample_complete'] = True
        state['sample_notice'] = 'Rerun generated, not human-validated. Historical processing remains unverified.'
        save()
    while not state['inventory_complete'] and time.monotonic() - started < 900:
        day = dt.date.fromisoformat(state['next_date'])
        listing = api('/archives/api/archives.php', {'feedId': '47003', 'date': day.strftime('%m/%d/%Y')})
        rows = listing.get('archives')
        if not isinstance(rows, list):
            raise RuntimeError('Archive listing missing expected list; date not skipped.')
        for row in rows:
            archive_id = str(row.get('id', ''))
            if not re.fullmatch(r'47003-[0-9]+', archive_id):
                raise RuntimeError('Unexpected listing identifier; date not skipped.')
            state['archives'][archive_id] = str(day)
        day += dt.timedelta(days=1)
        state['next_date'] = str(day)
        state['inventory_complete'] = day > dt.date.fromisoformat(state['last_date'])
        save()
    pending = sorted((k for k in state['archives'] if k not in state['completed'] and state['errors'].get(k, {}).get('attempts', 0) < 3), key=lambda k: (state['archives'][k], k))
    for archive_id in pending:
        if time.monotonic() - started > 2400:
            break
        try:
            transcribe(archive_id)
            state['completed'].append(archive_id)
            state['errors'].pop(archive_id, None)
        except Exception as exc:
            if state['blocked']:
                raise
            previous = state['errors'].get(archive_id, {}).get('attempts', 0)
            state['errors'][archive_id] = {'attempts': previous + 1, 'error_type': type(exc).__name__, 'notice': 'Raw exception withheld to avoid leaking URLs or credentials.'}
        save()
    save()

try:
    main()
except Exception as exc:
    state['last_error_type'] = type(exc).__name__
    save()
    raise SystemExit('Batch stopped safely. See public checkpoint for sanitized status.')
