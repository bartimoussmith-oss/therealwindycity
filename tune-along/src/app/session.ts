/**
 * Orchestrates a listening session on the UI thread: owns the analysis worker,
 * starts/stops capture, keeps the live state for the screen, and turns finished
 * segments into new or updated songs in the library.
 */
import type { KeyResult } from '../dsp/key';
import type { TuningReport } from '../dsp/tuning';
import type { LiveFrame, LiveMatch, SegmentResult } from '../engine/engine';
import type { FromWorker, ToWorker } from '../engine/protocol';
import { CaptureError, audioContext, demoBuffer, decodeFile, startCapture, type CaptureHandle, type InputKind } from '../audio/capture';
import { DEMO_SONGS } from '../audio/demoSongs';
import { songLrc } from '../audio/synth';
import { parseLrc } from '../music/lrc';
import { deleteSong, getSong, library, loadLibrary, saveSong } from '../lib/library';
import { createSongFromSegment, mergeSegmentIntoSong, type LyricLine, type SongRecord } from '../lib/songModel';
import { speechSupported, startTranscription, type Transcriber } from '../lib/speech';
import { Store } from '../lib/store';

export interface Notice {
  kind: 'learned' | 'updated' | 'info' | 'error';
  text: string;
  songId?: string;
  at: number;
}

export interface LiveState {
  status: 'idle' | 'starting' | 'listening' | 'stopping';
  input: InputKind | null;
  inputLabel: string;
  error: string | null;
  music: boolean;
  now: number;
  wallAt: number;
  frame: LiveFrame | null;
  history: { t: number; state: number }[];
  tuning: TuningReport | null;
  key: KeyResult | null;
  bpm: number | null;
  match: LiveMatch | null;
  segmentStart: number | null;
  transcript: { t: number; text: string }[];
  interim: string;
  transcribe: boolean;
  transcriberLocal: boolean | null;
  demo: { id: string; plays: number; startedAt: number; learnedSongId?: string } | null;
  notices: Notice[];
  index: { songs: number; hashes: number };
}

export const live = new Store<LiveState>({
  status: 'idle', input: null, inputLabel: '', error: null, music: false, now: 0, wallAt: 0, frame: null, history: [],
  tuning: null, key: null, bpm: null, match: null, segmentStart: null, transcript: [], interim: '',
  transcribe: false, transcriberLocal: null, demo: null, notices: [], index: { songs: 0, hashes: 0 },
});

let worker: Worker | null = null;
let capture: CaptureHandle | null = null;
let transcriber: Transcriber | null = null;
let stopResolve: (() => void) | null = null;
const pendingSaves: Promise<void>[] = [];
let wakeLock: { release(): Promise<void> } | null = null;

/** Keep the screen on while playing along (where the browser supports it). */
async function holdScreen(on: boolean): Promise<void> {
  try {
    if (on && !wakeLock) {
      const wl = (navigator as Navigator & { wakeLock?: { request(t: 'screen'): Promise<{ release(): Promise<void> }> } }).wakeLock;
      if (wl) wakeLock = await wl.request('screen');
    } else if (!on && wakeLock) {
      await wakeLock.release();
      wakeLock = null;
    }
  } catch {
    wakeLock = null; // not allowed right now (e.g. tab hidden) — harmless
  }
}

/** iOS/Safari only allow audio to start inside the tap that asked for it. */
function unlockAudio(): void {
  try { void audioContext().resume(); } catch { /* ignore */ }
}

function post(msg: ToWorker): void {
  worker?.postMessage(msg);
}

export function notify(kind: Notice['kind'], text: string, songId?: string): void {
  const n: Notice = { kind, text, songId, at: Date.now() };
  live.set((s) => ({ notices: [...s.notices.slice(-3), n] }));
}

export function dismissNotice(at: number): void {
  live.set((s) => ({ notices: s.notices.filter((n) => n.at !== at) }));
}

function indexEntry(s: SongRecord) {
  return { id: s.id, fp: { hashes: s.fp.hashes.slice(), times: s.fp.times.slice() } };
}

export async function initSession(): Promise<void> {
  if (worker) return;
  worker = new Worker(new URL('../engine/engine.worker.ts', import.meta.url), { type: 'module' });
  worker.onmessage = (e: MessageEvent<FromWorker>) => onWorker(e.data);
  worker.onerror = (e) => notify('error', `Analysis engine failed: ${e.message}`);
  document.addEventListener('visibilitychange', () => {
    // browsers drop the wake lock when the page is hidden; take it back on return
    if (document.visibilityState === 'visible' && live.get().status === 'listening') { wakeLock = null; void holdScreen(true); }
  });
  const songs = await loadLibrary();
  post({ type: 'index:set', songs: songs.map(indexEntry) });
}

/** Current position in the recognised song (seconds), or null. */
export function songTimeNow(s: LiveState = live.get()): number | null {
  if (!s.match) return null;
  const elapsed = s.status === 'listening' ? Math.min(1.5, (performance.now() - s.wallAt) / 1000) : 0;
  return s.now + elapsed + s.match.offsetSec;
}

export function sessionTimeNow(s: LiveState = live.get()): number {
  const elapsed = s.status === 'listening' ? Math.min(1.5, (performance.now() - s.wallAt) / 1000) : 0;
  return s.now + elapsed;
}

function onWorker(msg: FromWorker): void {
  switch (msg.type) {
    case 'ready':
      live.set({ index: { songs: msg.indexSongs, hashes: msg.indexHashes } });
      break;
    case 'frame': {
      const f = msg.frame;
      live.set((s) => {
        let history = s.history;
        if (f.music) {
          const last = history[history.length - 1];
          if (!last || last.state !== f.state) {
            history = [...history, { t: f.t, state: f.state }];
            if (history.length > 400) history = history.slice(-300);
          }
        }
        return { frame: f, now: f.now, wallAt: performance.now(), history };
      });
      break;
    }
    case 'tuning':
      live.set({ tuning: msg.report });
      break;
    case 'key':
      live.set({ key: msg.key });
      break;
    case 'tempo':
      live.set({ bpm: msg.bpm });
      break;
    case 'match': {
      const prev = live.get().match;
      live.set({ match: msg.match });
      if (msg.match && (!prev || prev.songId !== msg.match.songId)) {
        const song = getSong(msg.match.songId);
        if (song) notify('info', `Recognised “${song.title}”`, song.id);
      }
      break;
    }
    case 'music':
      live.set((s) => ({
        music: msg.music,
        segmentStart: msg.music ? msg.now : s.segmentStart,
        ...(msg.music ? { history: [], tuning: null, key: null, bpm: null } : {}),
      }));
      break;
    case 'segment': {
      const p = handleSegment(msg.segment);
      pendingSaves.push(p);
      p.finally(() => pendingSaves.splice(pendingSaves.indexOf(p), 1));
      break;
    }
    case 'stopped':
      stopResolve?.();
      stopResolve = null;
      break;
    case 'error':
      notify('error', msg.message);
      break;
  }
}

function transcriptFor(seg: SegmentResult): LyricLine[] {
  return live
    .get()
    .transcript.map((l) => ({ t: l.t - seg.sessionStart, text: l.text }))
    .filter((l) => l.t >= -1 && l.t <= seg.duration + 1 && l.text);
}

async function handleSegment(seg: SegmentResult): Promise<void> {
  const s = live.get();
  const transcript = transcriptFor(seg);
  const known = seg.match ? getSong(seg.match.songId) : undefined;
  if (seg.match && known) {
    const updated = mergeSegmentIntoSong(known, seg, transcript);
    await saveSong(updated);
    post({ type: 'index:upsert', song: indexEntry(updated) });
    notify('updated', `Played along with “${updated.title}” (heard ${updated.listens}×). Anything new was added.`, updated.id);
    return;
  }
  const spec = s.input === 'demo' && s.demo ? DEMO_SONGS.find((d) => d.id === s.demo!.id) : undefined;
  const song = createSongFromSegment(seg, {
    source: s.input ?? 'mic',
    title: spec?.title,
    artist: spec?.artist,
    demoId: spec?.id,
    transcript,
  });
  if (spec && s.demo) {
    song.lyrics = { lines: parseLrc(songLrc(spec)), synced: true, source: 'demo' };
    song.lyricsOffset = seg.sessionStart - s.demo.startedAt; // LRC is relative to the start of the file
    live.set((st) => ({ demo: st.demo ? { ...st.demo, learnedSongId: song.id } : null }));
  } else if (transcript.length >= 3) {
    song.lyrics = { lines: transcript, synced: true, source: 'transcript' };
  }
  await saveSong(song);
  post({ type: 'index:upsert', song: indexEntry(song) });
  notify('learned', spec ? `Learned “${song.title}”. Play it again and TuneAlong will show what’s coming.` : 'Learned a new song. Give it a name so you can find it later.', song.id);
}

const LABELS: Record<InputKind, string> = { mic: 'Microphone', tab: 'Tab audio', file: 'Audio file', demo: 'Demo song' };

export async function startListening(kind: InputKind, opts: { file?: File; demoId?: string } = {}): Promise<void> {
  unlockAudio();
  if (live.get().status !== 'idle') await stopListening();
  await initSession();
  live.set({ status: 'starting', input: kind, inputLabel: LABELS[kind], error: null, match: null, history: [], frame: null, tuning: null, key: null, bpm: null, transcript: [], interim: '', music: false, segmentStart: null });
  try {
    let buffer: AudioBuffer | undefined;
    if (kind === 'file' && opts.file) {
      buffer = await decodeFile(opts.file);
      live.set({ inputLabel: opts.file.name });
    }
    if (kind === 'demo') {
      const spec = DEMO_SONGS.find((d) => d.id === opts.demoId) ?? DEMO_SONGS[0];
      buffer = demoBuffer(spec);
      const prev = live.get().demo;
      live.set({ demo: { id: spec.id, plays: (prev?.id === spec.id ? prev.plays : 0) + 1, startedAt: 0, learnedSongId: prev?.id === spec.id ? prev.learnedSongId : undefined }, inputLabel: `Demo: ${spec.title}` });
    }
    capture = await startCapture(kind, worker!, { buffer });
    live.set({ status: 'listening', now: 0, wallAt: performance.now() });
    void holdScreen(true);
    capture.ended.then(() => {
      // tab/mic track ended by the user (e.g. "Stop sharing") → stop the session
      if ((kind === 'mic' || kind === 'tab') && live.get().status === 'listening') void stopListening();
    });
    if (live.get().transcribe && capture.track && speechSupported()) {
      transcriber = await startTranscription(
        capture.track,
        (text, final) => {
          if (final) live.set((s) => ({ transcript: [...s.transcript, { t: Math.max(0, sessionTimeNow(s) - 1.2), text }], interim: '' }));
          else live.set({ interim: text });
        },
        (m) => notify('error', m),
      );
      live.set({ transcriberLocal: transcriber?.local ?? null });
    }
  } catch (err) {
    capture?.stop();
    capture = null;
    post({ type: 'session:stop' });
    live.set({ status: 'idle', error: err instanceof CaptureError ? err.message : `Could not start: ${err instanceof Error ? err.message : String(err)}` });
  }
}

/** Play the demo (again) inside the running demo session, or start one. */
export async function playDemo(demoId: string): Promise<void> {
  unlockAudio();
  const s = live.get();
  if (s.status === 'listening' && s.input === 'demo' && capture) {
    const spec = DEMO_SONGS.find((d) => d.id === demoId) ?? DEMO_SONGS[0];
    const same = s.demo?.id === spec.id;
    live.set({ demo: { id: spec.id, plays: (same ? s.demo!.plays : 0) + 1, startedAt: sessionTimeNow(s), learnedSongId: same ? s.demo?.learnedSongId : undefined }, inputLabel: `Demo: ${spec.title}` });
    capture.play(demoBuffer(spec));
    return;
  }
  await startListening('demo', { demoId });
}

export async function stopListening(): Promise<void> {
  const s = live.get();
  if (s.status === 'idle' || s.status === 'stopping') return;
  live.set({ status: 'stopping' });
  transcriber?.stop();
  transcriber = null;
  const done = new Promise<void>((r) => (stopResolve = r));
  post({ type: 'session:stop' });
  await Promise.race([done, new Promise((r) => setTimeout(r, 4000))]);
  capture?.stop();
  capture = null;
  void holdScreen(false);
  await Promise.all(pendingSaves);
  live.set({ status: 'idle', match: null, music: false });
}

export function setTranscribe(on: boolean): void {
  live.set({ transcribe: on });
}

export async function removeSong(id: string): Promise<void> {
  await deleteSong(id);
  post({ type: 'index:remove', id });
}

export function reindexAll(): void {
  post({ type: 'index:set', songs: library.get().songs.map(indexEntry) });
}
