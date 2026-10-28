/**
 * Tiny deterministic band-in-a-box used for the built-in demo song and for the
 * automated tests: Karplus–Strong guitar and bass (with fractional-delay tuning so
 * pitch is exact to the cent), a sine-ish lead "voice", and noise drums.
 * Pure functions on Float32Arrays — runs the same in the browser and in Node.
 */
import { midiToFreq } from '../dsp/notes';

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export interface PluckOptions {
  /** Seconds for the note to fall by 60 dB. */
  t60?: number;
  /** 0..1 excitation brightness. */
  brightness?: number;
  /** Seconds before the note is damped (re-strum / palm mute). */
  duration?: number;
}

/** Karplus–Strong plucked string, mixed into `out` starting at `start`. */
export function pluck(out: Float32Array, start: number, freq: number, sr: number, amp: number, rng: () => number, opts: PluckOptions = {}): void {
  const P = sr / freq;
  const N = Math.max(2, Math.floor(P - 0.5 - 0.1));
  const d = P - 0.5 - N;
  const C = (1 - d) / (1 + d);
  const t60 = opts.t60 ?? 2.5;
  const g = Math.pow(10, -3 / (t60 * freq));
  const brightness = opts.brightness ?? 0.6;
  const buf = new Float32Array(N);
  // excitation: the string's displaced shape when plucked ~1/5 along its length
  // (a triangle, which gives a strong fundamental) plus a little noise, lowpassed.
  let lp = 0;
  const a = 0.15 + 0.85 * brightness;
  const pickPos = 0.18 + 0.06 * rng();
  let mean = 0;
  for (let i = 0; i < N; i++) {
    const x = i / N;
    const tri = x < pickPos ? x / pickPos : (1 - x) / (1 - pickPos);
    const v = 0.8 * (tri * 2 - 1) + 0.35 * (rng() * 2 - 1);
    lp += a * (v - lp);
    buf[i] = lp;
    mean += lp;
  }
  mean /= N;
  let peak = 0;
  for (let i = 0; i < N; i++) { buf[i] -= mean; peak = Math.max(peak, Math.abs(buf[i])); }
  if (peak > 0) for (let i = 0; i < N; i++) buf[i] *= amp / peak;
  const total = Math.min(out.length - start, Math.floor((opts.duration ?? t60) * sr));
  const release = Math.floor(0.02 * sr);
  let idx = 0, last = 0, apX = 0, apY = 0;
  for (let i = 0; i < total; i++) {
    const cur = buf[idx];
    const avg = g * 0.5 * (cur + last);
    last = cur;
    const ap = C * avg + apX - C * apY;
    apX = avg; apY = ap;
    buf[idx] = ap;
    idx++; if (idx === N) idx = 0;
    let env = 1;
    if (i < 32) env = i / 32; // soften the pick click
    if (i > total - release) env *= (total - i) / release;
    out[start + i] += cur * env;
  }
}

/** Bass-drum: pitch-swept sine. */
export function kick(out: Float32Array, start: number, sr: number, amp: number): void {
  const len = Math.min(out.length - start, Math.floor(0.28 * sr));
  let phase = 0;
  for (let i = 0; i < len; i++) {
    const t = i / sr;
    const f = 45 + 75 * Math.exp(-t / 0.035);
    phase += (2 * Math.PI * f) / sr;
    out[start + i] += amp * Math.sin(phase) * Math.exp(-t / 0.11);
  }
}

export function snare(out: Float32Array, start: number, sr: number, amp: number, rng: () => number): void {
  const len = Math.min(out.length - start, Math.floor(0.22 * sr));
  let prev = 0;
  for (let i = 0; i < len; i++) {
    const t = i / sr;
    const n = rng() * 2 - 1;
    const hp = n - prev; prev = n;
    out[start + i] += amp * (0.55 * hp * Math.exp(-t / 0.07) + 0.45 * Math.sin(2 * Math.PI * 185 * t) * Math.exp(-t / 0.045));
  }
}

export function hat(out: Float32Array, start: number, sr: number, amp: number, rng: () => number): void {
  const len = Math.min(out.length - start, Math.floor(0.06 * sr));
  let prev = 0;
  for (let i = 0; i < len; i++) {
    const n = rng() * 2 - 1;
    const hp = n - prev; prev = n;
    out[start + i] += amp * hp * Math.exp(-i / sr / 0.018);
  }
}

/** Lead "voice": a few harmonics with vibrato and a soft envelope. */
export function lead(out: Float32Array, start: number, freq: number, sr: number, dur: number, amp: number): void {
  const len = Math.min(out.length - start, Math.floor(dur * sr));
  const att = Math.floor(0.04 * sr), rel = Math.floor(0.08 * sr);
  let ph = 0;
  for (let i = 0; i < len; i++) {
    const t = i / sr;
    const vib = 1 + 0.006 * Math.sin(2 * Math.PI * 5.4 * t) * Math.min(1, t / 0.25);
    ph += (2 * Math.PI * freq * vib) / sr;
    let env = 1;
    if (i < att) env = i / att;
    if (i > len - rel) env *= Math.max(0, (len - i) / rel);
    const s = Math.sin(ph) + 0.35 * Math.sin(2 * ph) + 0.18 * Math.sin(3 * ph) + 0.08 * Math.sin(4 * ph);
    out[start + i] += amp * env * s;
  }
}

export interface BarSpec {
  /** Chord as written in the chart (sounding pitch), e.g. "Eb", "Cm", "Bb7", "Eb5". */
  chord: string;
  /** Guitar voicing, sounding MIDI notes from the lowest string up. */
  voicing: number[];
  /** Bass note (MIDI). */
  bass: number;
  style: 'strum' | 'chug' | 'ring' | 'waltz';
  /** [beat, lengthInBeats, midi] lead notes. */
  melody?: [number, number, number][];
}

export interface SongSpec {
  id: string;
  title: string;
  artist: string;
  bpm: number;
  beatsPerBar: number;
  /** Offset of the whole performance from A440, in cents. */
  refCents: number;
  /** Silence before the music starts (seconds). */
  leadIn: number;
  bars: BarSpec[];
  lyrics: { bar: number; beat: number; text: string }[];
  seed: number;
  /** Ground truth the tests check against. */
  truth: { key: string; tuningId: string };
}

export function songDuration(spec: SongSpec): number {
  const bar = (60 / spec.bpm) * spec.beatsPerBar;
  return spec.leadIn + spec.bars.length * bar + 2.5;
}

export function barStart(spec: SongSpec, bar: number): number {
  return spec.leadIn + bar * (60 / spec.bpm) * spec.beatsPerBar;
}

export function renderSong(spec: SongSpec, sr: number): Float32Array {
  const rng = mulberry32(spec.seed);
  const out = new Float32Array(Math.ceil(songDuration(spec) * sr));
  const ref = 440 * Math.pow(2, spec.refCents / 1200);
  const beat = 60 / spec.bpm;
  const S = (t: number) => Math.floor(t * sr);
  spec.bars.forEach((b, bi) => {
    const t0 = barStart(spec, bi);
    const nextBar = bi + 1 < spec.bars.length ? spec.bars[bi + 1] : null;
    void nextBar;
    // guitar
    if (b.style === 'chug') {
      for (let e = 0; e < spec.beatsPerBar * 2; e++) {
        const t = t0 + e * beat * 0.5;
        b.voicing.forEach((m, si) => {
          pluck(out, S(t + si * 0.004), midiToFreq(m, ref), sr, 0.16, rng, { t60: 1.2, brightness: 0.75, duration: beat * 0.42 });
        });
      }
    } else if (b.style === 'ring') {
      b.voicing.forEach((m, si) => {
        pluck(out, S(t0 + si * 0.03), midiToFreq(m, ref), sr, 0.17, rng, { t60: 4, brightness: 0.6, duration: beat * spec.beatsPerBar * 1.6 });
      });
    } else {
      // strum pattern: D . D U . U D U  (eighths) for 4/4, D D U D for waltz
      const pattern = b.style === 'waltz' ? [0, 1, 1.5, 2] : [0, 1, 1.5, 2.5, 3, 3.5];
      const ups = b.style === 'waltz' ? new Set([1.5]) : new Set([1.5, 2.5, 3.5]);
      for (let pi = 0; pi < pattern.length; pi++) {
        const pb = pattern[pi];
        const nextPb = pi + 1 < pattern.length ? pattern[pi + 1] : spec.beatsPerBar;
        const t = t0 + pb * beat;
        const up = ups.has(pb);
        const order = up ? [...b.voicing].reverse() : b.voicing;
        const amp = up ? 0.11 : 0.15;
        order.forEach((m, si) => {
          pluck(out, S(t + si * 0.011), midiToFreq(m, ref), sr, amp, rng, { t60: 2.2, brightness: up ? 0.45 : 0.6, duration: (nextPb - pb) * beat + 0.03 });
        });
      }
    }
    // bass: root on beats, eighth pickup
    const bassBeats = spec.beatsPerBar === 3 ? [0, 2] : [0, 1.5, 2, 3];
    bassBeats.forEach((bb, i) => {
      const len = (i + 1 < bassBeats.length ? bassBeats[i + 1] : spec.beatsPerBar) - bb;
      const note = i === 2 && spec.beatsPerBar === 4 ? b.bass + 7 : b.bass;
      pluck(out, S(t0 + bb * beat), midiToFreq(note, ref), sr, 0.22, rng, { t60: 1.8, brightness: 0.18, duration: len * beat * 0.95 });
    });
    // drums
    for (let k = 0; k < spec.beatsPerBar; k++) {
      const t = t0 + k * beat;
      if (spec.beatsPerBar === 3) {
        if (k === 0) kick(out, S(t), sr, 0.42); else hat(out, S(t), sr, 0.05, rng);
      } else {
        if (k === 0 || k === 2) kick(out, S(t), sr, 0.42);
        if (k === 1 || k === 3) snare(out, S(t), sr, 0.2, rng);
        hat(out, S(t), sr, 0.045, rng);
        hat(out, S(t + beat / 2), sr, 0.03, rng);
      }
    }
    // lead voice
    for (const [mb, len, m] of b.melody ?? []) {
      lead(out, S(t0 + mb * beat), midiToFreq(m, ref), sr, len * beat, 0.05);
    }
  });
  // gentle master: soft clip + normalise to −3 dBFS
  let peak = 0;
  for (let i = 0; i < out.length; i++) { out[i] = Math.tanh(out[i] * 1.2); peak = Math.max(peak, Math.abs(out[i])); }
  if (peak > 0) { const g = 0.7 / peak; for (let i = 0; i < out.length; i++) out[i] *= g; }
  return out;
}

export function songLrc(spec: SongSpec): string {
  const beat = 60 / spec.bpm;
  const lines = [`[ti:${spec.title}]`, `[ar:${spec.artist}]`];
  for (const l of spec.lyrics) {
    const t = barStart(spec, l.bar) + l.beat * beat;
    const mm = Math.floor(t / 60);
    const ss = t - mm * 60;
    lines.push(`[${String(mm).padStart(2, '0')}:${ss.toFixed(2).padStart(5, '0')}]${l.text}`);
  }
  return lines.join('\n');
}

/** Bar-level chord chart (sounding pitch) for test scoring. */
export function truthChords(spec: SongSpec): { start: number; end: number; chord: string }[] {
  return spec.bars.map((b, i) => ({ start: barStart(spec, i), end: barStart(spec, i + 1), chord: b.chord }));
}
