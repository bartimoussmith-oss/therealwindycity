/**
 * Web Worker host for the AnalysisEngine. Audio arrives either as 'audio' messages
 * or directly from the AudioWorklet through a transferred MessagePort, so the UI
 * thread never touches raw samples.
 */
import { FingerprintIndex, type SongFingerprint } from '../dsp/fingerprint';
import { AnalysisEngine, type SegmentResult } from './engine';
import type { FromWorker, ToWorker } from './protocol';

const ctx = self as unknown as {
  postMessage(msg: FromWorker, transfer?: Transferable[]): void;
  onmessage: ((e: MessageEvent<ToWorker>) => void) | null;
};

const songs = new Map<string, SongFingerprint>();
let index = new FingerprintIndex();
let engine: AnalysisEngine | null = null;
let port: MessagePort | null = null;
let stopping = false;

function post(msg: FromWorker, transfer: Transferable[] = []): void {
  ctx.postMessage(msg, transfer);
}

function rebuild(): void {
  index = new FingerprintIndex();
  index.build([...songs.values()]);
  engine?.setIndex(index);
  post({ type: 'ready', indexSongs: index.songCount, indexHashes: index.size });
}

function segmentTransfer(s: SegmentResult): Transferable[] {
  return [s.chroma.buffer, s.bass.buffer, s.energy.buffer, s.stacks.buffer, s.fp.hashes.buffer, s.fp.times.buffer] as Transferable[];
}

function push(samples: Float32Array): void {
  if (!engine) return;
  try {
    engine.pushAudio(samples);
  } catch (err) {
    post({ type: 'error', message: err instanceof Error ? err.message : String(err) });
  }
}

ctx.onmessage = (e: MessageEvent<ToWorker>) => {
  const msg = e.data;
  switch (msg.type) {
    case 'index:set':
      songs.clear();
      for (const s of msg.songs) songs.set(s.id, s);
      rebuild();
      break;
    case 'index:upsert':
      songs.set(msg.song.id, msg.song);
      rebuild();
      break;
    case 'index:remove':
      songs.delete(msg.id);
      rebuild();
      break;
    case 'session:start': {
      engine = new AnalysisEngine(msg.sampleRate, {
        onFrame: (frame) => post({ type: 'frame', frame }),
        onTuning: (report) => post({ type: 'tuning', report }),
        onKey: (key) => post({ type: 'key', key }),
        onTempo: (bpm) => post({ type: 'tempo', bpm }),
        onMatch: (match, now) => post({ type: 'match', match, now }),
        onMusic: (music, now) => post({ type: 'music', music, now }),
        onSegment: (segment) => {
          if (stopping) return; // delivered by the stop handler instead
          post({ type: 'segment', segment, final: false }, segmentTransfer(segment));
        },
      });
      engine.setIndex(index);
      break;
    }
    case 'session:stop': {
      if (!engine) { post({ type: 'stopped', hadSegment: false }); break; }
      stopping = true;
      const seg = engine.stop();
      stopping = false;
      engine = null;
      if (seg) post({ type: 'segment', segment: seg, final: true }, segmentTransfer(seg));
      post({ type: 'stopped', hadSegment: !!seg });
      break;
    }
    case 'audio':
      push(msg.samples);
      break;
    case 'audio-port':
      port?.close();
      port = msg.port;
      port.onmessage = (ev: MessageEvent<Float32Array>) => push(ev.data);
      break;
  }
};
