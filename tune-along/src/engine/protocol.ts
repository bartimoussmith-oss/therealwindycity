/** Messages between the UI thread and the analysis worker. */
import type { FingerprintData } from '../dsp/fingerprint';
import type { KeyResult } from '../dsp/key';
import type { TuningReport } from '../dsp/tuning';
import type { LiveFrame, LiveMatch, SegmentResult } from './engine';

export type ToWorker =
  | { type: 'index:set'; songs: { id: string; fp: FingerprintData }[] }
  | { type: 'index:upsert'; song: { id: string; fp: FingerprintData } }
  | { type: 'index:remove'; id: string }
  | { type: 'session:start'; sampleRate: number }
  | { type: 'session:stop' }
  | { type: 'audio'; samples: Float32Array }
  | { type: 'audio-port'; port: MessagePort };

export type FromWorker =
  | { type: 'ready'; indexSongs: number; indexHashes: number }
  | { type: 'frame'; frame: LiveFrame }
  | { type: 'tuning'; report: TuningReport }
  | { type: 'key'; key: KeyResult | null }
  | { type: 'tempo'; bpm: number | null }
  | { type: 'match'; match: LiveMatch | null; now: number }
  | { type: 'music'; music: boolean; now: number }
  | { type: 'segment'; segment: SegmentResult; final: boolean }
  | { type: 'stopped'; hadSegment: boolean }
  | { type: 'error'; message: string };
