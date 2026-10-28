/**
 * Chord recognition: harmonic-aware chord templates scored against chroma, then
 * an HMM (Viterbi) that prefers staying on a chord, which removes flicker.
 */
import { CHROMA_CENTER_SEC, CHROMA_HOP_SEC } from './chroma';
import { mod12, pcName, type Spelling } from './notes';

export interface ChordType {
  id: string;
  suffix: string;
  intervals: number[];
  /** Small score handicap so rich chords only win when the evidence is clearly there. */
  penalty: number;
  name: string;
}

export const CHORD_TYPES: ChordType[] = [
  { id: 'maj', suffix: '', intervals: [0, 4, 7], penalty: 0, name: 'major' },
  { id: 'min', suffix: 'm', intervals: [0, 3, 7], penalty: 0, name: 'minor' },
  { id: '7', suffix: '7', intervals: [0, 4, 7, 10], penalty: 0.03, name: 'dominant 7th' },
  { id: 'm7', suffix: 'm7', intervals: [0, 3, 7, 10], penalty: 0.035, name: 'minor 7th' },
  { id: 'maj7', suffix: 'maj7', intervals: [0, 4, 7, 11], penalty: 0.045, name: 'major 7th' },
  { id: 'sus4', suffix: 'sus4', intervals: [0, 5, 7], penalty: 0.045, name: 'suspended 4th' },
  { id: 'sus2', suffix: 'sus2', intervals: [0, 2, 7], penalty: 0.05, name: 'suspended 2nd' },
  { id: 'dim', suffix: 'dim', intervals: [0, 3, 6], penalty: 0.05, name: 'diminished' },
  { id: 'aug', suffix: 'aug', intervals: [0, 4, 8], penalty: 0.06, name: 'augmented' },
  { id: '5', suffix: '5', intervals: [0, 7], penalty: 0.02, name: 'power chord' },
];

export const NUM_CHORD_STATES = CHORD_TYPES.length * 12;
export const NO_CHORD = NUM_CHORD_STATES; // "N" state
export const NUM_STATES = NUM_CHORD_STATES + 1;

export interface Chord {
  root: number; // pitch class, −1 for no chord
  type: string; // ChordType.id or 'N'
}

export function stateToChord(s: number): Chord {
  if (s >= NUM_CHORD_STATES || s < 0) return { root: -1, type: 'N' };
  return { root: s % 12, type: CHORD_TYPES[Math.floor(s / 12)].id };
}

export function chordToState(c: Chord): number {
  if (c.type === 'N' || c.root < 0) return NO_CHORD;
  const t = CHORD_TYPES.findIndex((x) => x.id === c.type);
  return t < 0 ? NO_CHORD : t * 12 + mod12(c.root);
}

export function chordLabel(c: Chord, spelling: Spelling = 'common', transpose = 0): string {
  if (c.type === 'N' || c.root < 0) return 'N.C.';
  const t = CHORD_TYPES.find((x) => x.id === c.type);
  return pcName(c.root + transpose, spelling) + (t ? t.suffix : '');
}

export function chordTones(c: Chord): number[] {
  const t = CHORD_TYPES.find((x) => x.id === c.type);
  if (!t || c.root < 0) return [];
  return t.intervals.map((i) => mod12(c.root + i));
}

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

const HARMONIC_SEMITONES = [0, 12, 19, 24, 28, 31]; // partials 1..6
const HARMONIC_DECAY = 0.55;

function buildTemplates(): Float32Array[] {
  const templates: Float32Array[] = [];
  for (const type of CHORD_TYPES) {
    for (let root = 0; root < 12; root++) {
      const t = new Float32Array(12);
      type.intervals.forEach((iv, idx) => {
        const noteWeight = idx === 0 ? 1.15 : 1;
        HARMONIC_SEMITONES.forEach((h, hi) => {
          t[mod12(root + iv + h)] += noteWeight * Math.pow(HARMONIC_DECAY, hi);
        });
      });
      let n = 0;
      for (let i = 0; i < 12; i++) n += t[i] * t[i];
      n = Math.sqrt(n);
      for (let i = 0; i < 12; i++) t[i] /= n;
      templates.push(t);
    }
  }
  return templates;
}

const TEMPLATES = buildTemplates();
const PENALTIES = (() => {
  const p = new Float32Array(NUM_STATES);
  CHORD_TYPES.forEach((t, ti) => {
    for (let r = 0; r < 12; r++) p[ti * 12 + r] = t.penalty;
  });
  return p;
})();

/** Score assigned to "no chord"; chords must beat this to be reported. */
export const NO_CHORD_SCORE = 0.62;
const BASS_WEIGHT = 0.09;

/**
 * Scores every chord state for one frame. `chroma` must be L2-normalised;
 * `bass` may be any non-negative vector (it is max-normalised here).
 * `energyOk=false` forces the "no chord" state (silence / noise).
 */
export function scoreFrame(chroma: Float32Array, bass: Float32Array | null, energyOk: boolean, out: Float32Array): Float32Array {
  let bassMax = 0;
  if (bass) for (let i = 0; i < 12; i++) if (bass[i] > bassMax) bassMax = bass[i];
  for (let s = 0; s < NUM_CHORD_STATES; s++) {
    const t = TEMPLATES[s];
    let dot = 0;
    for (let i = 0; i < 12; i++) dot += chroma[i] * t[i];
    let score = dot - PENALTIES[s];
    if (bassMax > 0 && bass) score += BASS_WEIGHT * (bass[s % 12] / bassMax);
    out[s] = energyOk ? score : 0;
  }
  out[NO_CHORD] = energyOk ? NO_CHORD_SCORE : 1;
  return out;
}

// ---------------------------------------------------------------------------
// Decoding
// ---------------------------------------------------------------------------

export interface DecoderParams {
  /** Sharpness of emission probabilities. */
  kappa: number;
  /** Per-frame probability of staying on the same chord. */
  stay: number;
}

export const DEFAULT_DECODER: DecoderParams = { kappa: 28, stay: 0.92 };

/**
 * Online (forward max-product) decoder for live display. Each push returns the
 * currently most likely chord given everything heard so far.
 */
export class OnlineChordDecoder {
  private delta = new Float64Array(NUM_STATES);
  private readonly logStay: number;
  private readonly logSwitch: number;
  private started = false;

  constructor(private readonly params: DecoderParams = DEFAULT_DECODER) {
    this.logStay = Math.log(params.stay);
    this.logSwitch = Math.log((1 - params.stay) / (NUM_STATES - 1));
  }

  push(scores: Float32Array): { state: number; confidence: number } {
    const k = this.params.kappa;
    let best = 0;
    if (!this.started) {
      for (let s = 0; s < NUM_STATES; s++) this.delta[s] = k * scores[s];
      this.started = true;
    } else {
      let prevBest = -Infinity;
      for (let s = 0; s < NUM_STATES; s++) if (this.delta[s] > prevBest) prevBest = this.delta[s];
      for (let s = 0; s < NUM_STATES; s++) {
        const stay = this.delta[s] + this.logStay;
        const sw = prevBest + this.logSwitch;
        this.delta[s] = (stay > sw ? stay : sw) + k * scores[s];
      }
      // keep numbers small
      let m = -Infinity;
      for (let s = 0; s < NUM_STATES; s++) if (this.delta[s] > m) m = this.delta[s];
      for (let s = 0; s < NUM_STATES; s++) this.delta[s] -= m;
    }
    for (let s = 1; s < NUM_STATES; s++) if (this.delta[s] > this.delta[best]) best = s;
    return { state: best, confidence: scores[best] };
  }

  reset(): void {
    this.started = false;
  }
}

/**
 * Full Viterbi over a sequence of score frames (uniform switching makes it O(T·S)).
 */
export function viterbi(scores: Float32Array[], params: DecoderParams = DEFAULT_DECODER): Int16Array {
  const T = scores.length;
  const path = new Int16Array(T);
  if (T === 0) return path;
  const k = params.kappa;
  const logStay = Math.log(params.stay);
  const logSwitch = Math.log((1 - params.stay) / (NUM_STATES - 1));
  let delta = new Float64Array(NUM_STATES);
  let next = new Float64Array(NUM_STATES);
  const fromSwitch: Uint8Array[] = [];
  const bestPrev = new Int16Array(T);
  for (let s = 0; s < NUM_STATES; s++) delta[s] = k * scores[0][s];
  fromSwitch.push(new Uint8Array(NUM_STATES));
  for (let t = 1; t < T; t++) {
    let pb = 0;
    for (let s = 1; s < NUM_STATES; s++) if (delta[s] > delta[pb]) pb = s;
    bestPrev[t] = pb;
    const sw = delta[pb] + logSwitch;
    const flags = new Uint8Array(NUM_STATES);
    const sc = scores[t];
    for (let s = 0; s < NUM_STATES; s++) {
      const stay = delta[s] + logStay;
      if (stay >= sw) next[s] = stay + k * sc[s];
      else { next[s] = sw + k * sc[s]; flags[s] = 1; }
    }
    fromSwitch.push(flags);
    let mx = -Infinity;
    for (let s = 0; s < NUM_STATES; s++) if (next[s] > mx) mx = next[s];
    for (let s = 0; s < NUM_STATES; s++) next[s] -= mx;
    const tmp = delta; delta = next; next = tmp;
  }
  let s = 0;
  for (let i = 1; i < NUM_STATES; i++) if (delta[i] > delta[s]) s = i;
  for (let t = T - 1; t >= 0; t--) {
    path[t] = s;
    if (t > 0 && fromSwitch[t][s]) s = bestPrev[t];
  }
  return path;
}

export interface ChordSegment {
  /** Seconds on the owning timeline (song time). */
  start: number;
  end: number;
  root: number;
  type: string;
  /** Mean template score of the chosen chord over the segment (≈0.6–1). */
  confidence: number;
}

/**
 * Run-length encodes a state path into chord segments. Frame i is centred at
 * t0 + i·hop + CHROMA_CENTER_SEC. Very short blips are merged into neighbours.
 */
export function pathToSegments(path: Int16Array, scores: Float32Array[], t0 = 0, minDur = 0.35): ChordSegment[] {
  const segs: ChordSegment[] = [];
  const hop = CHROMA_HOP_SEC;
  let i = 0;
  while (i < path.length) {
    let j = i;
    let conf = 0;
    while (j < path.length && path[j] === path[i]) { conf += scores[j][path[i]]; j++; }
    const c = stateToChord(path[i]);
    segs.push({
      start: t0 + i * hop + CHROMA_CENTER_SEC - hop / 2,
      end: t0 + j * hop + CHROMA_CENTER_SEC - hop / 2,
      root: c.root,
      type: c.type,
      confidence: conf / (j - i),
    });
    i = j;
  }
  // merge blips
  let changed = true;
  while (changed && segs.length > 1) {
    changed = false;
    for (let k = 0; k < segs.length; k++) {
      const s = segs[k];
      if (s.end - s.start >= minDur) continue;
      const prev = segs[k - 1];
      const nxt = segs[k + 1];
      const target = !prev ? nxt : !nxt ? prev : prev.end - prev.start >= nxt.end - nxt.start ? prev : nxt;
      if (target === prev) prev.end = s.end; else { nxt.start = s.start; }
      segs.splice(k, 1);
      changed = true;
      break;
    }
  }
  // merge equal neighbours created by blip removal
  const out: ChordSegment[] = [];
  for (const s of segs) {
    const last = out[out.length - 1];
    if (last && last.root === s.root && last.type === s.type) {
      const d1 = last.end - last.start, d2 = s.end - s.start;
      last.confidence = (last.confidence * d1 + s.confidence * d2) / Math.max(1e-9, d1 + d2);
      last.end = s.end;
    } else out.push({ ...s });
  }
  return out;
}

export function chordAt(segs: ChordSegment[], t: number): number {
  let lo = 0, hi = segs.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (segs[mid].end <= t) lo = mid + 1;
    else if (segs[mid].start > t) hi = mid - 1;
    else return mid;
  }
  return -1;
}
