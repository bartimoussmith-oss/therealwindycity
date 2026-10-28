/**
 * Turns stored per-frame features (chroma, bass, energy) plus accumulated evidence
 * into the musician-facing result: chord timeline, key, tuning report, capo advice.
 * Used both when a song is first learned and every time another listen is merged in.
 */
import { CHROMA_HOP_SEC } from '../dsp/chroma';
import { NUM_STATES, pathToSegments, scoreFrame, viterbi, type ChordSegment } from '../dsp/chords';
import { detectKey, type KeyResult } from '../dsp/key';
import { inferTuning, type TuningReport } from '../dsp/tuning';

export interface TuningAccumulator {
  re: number;
  im: number;
  w: number;
}

export interface FrameFeatures {
  /** n×12, each row L2-normalised (zero rows = silence). */
  chroma: Float32Array;
  /** n×12 bass chroma (unnormalised). */
  bass: Float32Array;
  /** n frame RMS values. */
  energy: Float32Array;
  stacks: Float32Array; // length 128, power-chord stack counts by root MIDI
  musicFrames: number;
  tuningAcc: TuningAccumulator;
}

export interface AnalysisResult {
  chords: ChordSegment[];
  key: KeyResult | null;
  tuning: TuningReport;
}

export const ENERGY_FLOOR = 0.0025;

export function frameCount(f: FrameFeatures): number {
  return f.energy.length;
}

export function analyzeFeatures(f: FrameFeatures, t0 = 0): AnalysisResult {
  const n = f.energy.length;
  const scores: Float32Array[] = new Array(n);
  const chromaSum = new Float64Array(12);
  const row = new Float32Array(12);
  const bassRow = new Float32Array(12);
  for (let i = 0; i < n; i++) {
    let sumSq = 0;
    for (let k = 0; k < 12; k++) {
      row[k] = f.chroma[i * 12 + k];
      bassRow[k] = f.bass[i * 12 + k];
      sumSq += row[k] * row[k];
    }
    const ok = f.energy[i] > ENERGY_FLOOR && sumSq > 0.5;
    if (ok) for (let k = 0; k < 12; k++) chromaSum[k] += row[k] * Math.min(1, f.energy[i] * 20);
    const s = new Float32Array(NUM_STATES);
    scoreFrame(row, bassRow, ok, s);
    scores[i] = s;
  }
  const chords = pathToSegments(viterbi(scores), scores, t0);
  const key = detectKey(chromaSum);
  const acc = f.tuningAcc;
  const cents = acc.w > 0 ? (100 * Math.atan2(acc.im, acc.re)) / (2 * Math.PI) : 0;
  const conf = acc.w > 0 ? Math.hypot(acc.re, acc.im) / acc.w : 0;
  const tuning = inferTuning({ cents, centsConfidence: conf, stacks: f.stacks, musicFrames: f.musicFrames }, chords, CHROMA_HOP_SEC);
  return { chords, key, tuning };
}
