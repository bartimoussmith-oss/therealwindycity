import ast, datetime as dt, json, os, queue, subprocess, sys, tempfile, threading, time
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

mode = sys.argv[1]
root = Path('scanner-results') / ('live-runs' if mode == 'live' else 'recent')
if mode == 'live':
    root = root / (os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT'])
root.mkdir(parents=True, exist_ok=True)
started = time.monotonic()

def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def write(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)

def publish():
    def git(*args, check=True):
        return subprocess.run(['git', *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=check)
    git('config', 'user.name', 'github-actions[bot]')
    git('config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    files = [str(p) for p in root.rglob('*.json')]
    if not files:
        return
    git('add', '--', *files)
    if git('diff', '--cached', '--quiet', check=False).returncode == 0:
        return
    git('commit', '-m', 'Checkpoint scanner ' + mode + ' run ' + os.environ['GITHUB_RUN_ID'])
    for attempt in range(4):
        if git('pull', '--rebase', 'origin', 'main', check=False).returncode != 0:
            raise RuntimeError('Checkpoint rebase failed.')
        if git('push', 'origin', 'HEAD:main', check=False).returncode == 0:
            return
        time.sleep(3 * (attempt + 1))
    raise RuntimeError('Checkpoint push failed.')

def recent():
    source = ast.parse(Path('scripts/scanner_history.py').read_text())
    if not isinstance(source.body[-1], ast.Try):
        raise RuntimeError('Historical helper layout changed; refusing unexpected execution.')
    source.body.pop()
    library = {}
    exec(compile(source, 'scanner_history_helpers', 'exec'), library)
    state_path = root / 'state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'archives': {}, 'completed': [], 'errors': {}, 'blocked': False, 'inventory_complete': False}
    library.update({'OUT': root, 'STATE': state_path, 'state': state})
    if state['blocked']:
        return
    session = library['session']
    session.post(library['ROOT'] + '/login/', data={'username': os.environ.get('BC_USER', ''), 'password': os.environ.get('BC_PASS', ''), 'action': 'auth', 'redirect': library['ROOT']}, allow_redirects=False, timeout=30)
    if not any(c.name == 'bcfyuser1' and c.value for c in session.cookies):
        library['block']('Recent-archive login failed.')
    today = dt.datetime.now(ZoneInfo('America/Denver')).date()
    for days in (2, 1, 0):
        day = today - dt.timedelta(days=days)
        listing = library['api']('/archives/api/archives.php', {'feedId': '47003', 'date': day.strftime('%m/%d/%Y')})
        rows = listing.get('archives')
        if not isinstance(rows, list):
            raise RuntimeError('Recent archive listing malformed.')
        for row in rows:
            key = str(row.get('id', ''))
            if not library['re'].fullmatch(r'47003-[0-9]+', key):
                raise RuntimeError('Unexpected recent archive ID.')
            state['archives'][key] = str(day)
    library['save']()
    publish()
    for key in sorted(state['archives'], key=lambda k: (state['archives'][k], k), reverse=True):
        if key in state['completed'] or state['errors'].get(key, {}).get('attempts', 0) >= 3:
            continue
        if time.monotonic() - started > 2400:
            break
        try:
            library['transcribe'](key)
            state['completed'].append(key)
            state['errors'].pop(key, None)
        except Exception as exc:
            if state['blocked']:
                raise
            previous = state['errors'].get(key, {}).get('attempts', 0)
            state['errors'][key] = {'attempts': previous + 1, 'error_type': type(exc).__name__}
        library['save']()
        publish()

def live():
    state = {'feed_id': '47003', 'status': 'starting', 'started_at_utc': utc(), 'last_audio_at_utc': None, 'bytes_received': 0, 'segments_saved': 0, 'connections': [], 'errors': [], 'continuous_capture_guaranteed': False, 'planned_capture_seconds': 3900, 'notice': 'Best-effort public unverified capture. Separate runs may overlap or have gaps. Raw audio is temporary; recent archives are processed separately, not yet reconciled against live gaps.'}
    pending = queue.Queue()
    stop = threading.Event()
    lock = threading.Lock()
    def checkpoint():
        with lock:
            state['heartbeat_at_utc'] = utc()
            write(root / 'status.json', state)
        publish()
    checkpoint()
    def record(directory):
        deadline = time.monotonic() + 3900
        count = 0
        try:
            while time.monotonic() < deadline and not stop.is_set():
                path = None
                output = None
                try:
                    with requests.get('https://audio.broadcastify.com/47003.mp3', auth=(os.environ.get('BC_USER', ''), os.environ.get('BC_PASS', '')), stream=True, timeout=(20, 30), allow_redirects=False) as response:
                        with lock:
                            event = {'connected_at_utc': utc(), 'http_status': response.status_code}
                            state['connections'].append(event)
                        if response.status_code in (401, 403, 429):
                            with lock:
                                state['status'] = 'blocked'
                            break
                        if response.status_code != 200 or any(t in response.headers.get('Content-Type', '').lower() for t in ('text/', 'json')):
                            raise RuntimeError('Stream did not return audio.')
                        with lock:
                            state['status'] = 'capturing'
                        for data in response.iter_content(4096):
                            if stop.is_set() or time.monotonic() >= deadline:
                                break
                            if not data:
                                continue
                            if output is None:
                                count += 1
                                path = Path(directory) / (str(count) + '.mp3')
                                output = path.open('wb')
                                chunk_start = time.monotonic()
                                wall_start = utc()
                            output.write(data)
                            with lock:
                                state['last_audio_at_utc'] = utc()
                                state['bytes_received'] += len(data)
                            if time.monotonic() - chunk_start >= 300:
                                output.close()
                                pending.put((path, wall_start, utc()))
                                output = None
                        with lock:
                            event['disconnected_at_utc'] = utc()
                except Exception as exc:
                    with lock:
                        state['errors'].append({'at_utc': utc(), 'error_type': type(exc).__name__, 'stage': 'stream'})
                finally:
                    if output is not None:
                        output.close()
                        pending.put((path, wall_start, utc()))
                if time.monotonic() < deadline and not stop.is_set():
                    stop.wait(5)
        finally:
            with lock:
                state['capture_ended_at_utc'] = utc()
                if state['status'] != 'blocked':
                    state['status'] = 'capture_ended_processing_pending'
            pending.put(None)
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    model = None
    with tempfile.TemporaryDirectory() as directory:
        thread = threading.Thread(target=record, args=(directory,), daemon=True)
        thread.start()
        last_save = time.monotonic()
        count = 0
        try:
            while time.monotonic() - started < 5400:
                try:
                    item = pending.get(timeout=30)
                except queue.Empty:
                    item = 'waiting'
                if item is None:
                    break
                if item != 'waiting':
                    path, begin, end = item
                    count += 1
                    try:
                        if model is None:
                            model = WhisperModel('small.en', device='cpu', compute_type='int8', cpu_threads=2)
                        audio = decode_audio(str(path), sampling_rate=16000)
                        segments = []
                        for offset in range(0, len(audio), 480000):
                            decoded, _ = model.transcribe(audio[offset:offset + 480000], language='en', beam_size=5, temperature=0.0, word_timestamps=True, vad_filter=True, condition_on_previous_text=False, hallucination_silence_threshold=1.0)
                            for s in decoded:
                                segments.append({'start_seconds': s.start + offset / 16000, 'end_seconds': s.end + offset / 16000, 'text': s.text.strip(), 'avg_logprob': s.avg_logprob, 'review_required': True})
                        write(root / ('chunk-' + str(count) + '.json'), {'capture_started_at_utc': begin, 'capture_ended_at_utc': end, 'model': 'small.en', 'review_required': True, 'notice': 'Unverified radio transcription. MP3 and transcription window boundaries may lose or split words. Offsets are not exact wall-clock times.', 'segments': segments})
                        with lock:
                            state['segments_saved'] += len(segments)
                    except Exception as exc:
                        with lock:
                            state['errors'].append({'at_utc': utc(), 'error_type': type(exc).__name__, 'stage': 'transcription', 'capture_started_at_utc': begin, 'capture_ended_at_utc': end})
                    finally:
                        path.unlink(missing_ok=True)
                if time.monotonic() - last_save >= 300:
                    checkpoint()
                    last_save = time.monotonic()
        finally:
            stop.set()
            thread.join(timeout=60)
            with lock:
                state['pending_queue_items'] = pending.qsize()
                state['run_ended_at_utc'] = utc()
                if state['status'] != 'blocked':
                    state['status'] = 'ended_with_errors_or_pending_audio' if state['errors'] or pending.qsize() else 'ended'
            checkpoint()

try:
    if mode == 'live':
        live()
    elif mode == 'recent':
        recent()
    else:
        raise RuntimeError('Unsupported mode.')
except Exception as exc:
    write(root / 'run-error.json', {'at_utc': utc(), 'error_type': type(exc).__name__, 'notice': 'Raw diagnostics withheld.'})
    try:
        publish()
    except Exception:
        pass
    raise SystemExit('Scanner job stopped; inspect sanitized repository status.')
