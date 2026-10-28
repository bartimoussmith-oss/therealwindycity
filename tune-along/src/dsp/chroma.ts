/**
 * Spectral peaks → chroma ("which of the 12 notes are sounding"), reference-pitch
 * (tuning) estimation and low-register evidence used to guess the guitar tuning.
 */
import { ANALYSIS_RATE } from './resample';
import { freqToMidi, mod12 } from './notes';

export const CHROMA_FFT = 4096;
export const CHROMA_HOP = 1024;
export const CHROMA_BIN_HZ = ANALYSIS_RATE / CHROMA_FFT;
export const CHROMA_HOP_SEC = CHROMA_HOP / ANALYSIS_RATE;
/** A chroma frame describes audio centred this far after its first sample. */
export const CHROMA_CENTER_SEC = CHROMA_FFT / 2 / ANALYSIS_RATE;

export interface Peak {
  freq: number;
  /** Linear magnitude (parabolically interpolated). */
  mag: number;
}

/**
 * Local-maximum peak picking with an adaptive (local mean) threshold and parabolic
 * interpolation on the dB spectrum for sub-bin frequency accuracy.
 */
export function findPeaks(mag: Float32Array, binHz: number, fMin: number, fMax: number, maxPeaks = 64): Peak[] {
  const kLo = Math.max(2, Math.floor(fMin / binHz));
  const kHi = Math.min(mag.length - 3, Math.ceil(fMax / binHz));
  if (kHi <= kLo) return [];
  let frameMax = 0;
  for (let k = kLo; k <= kHi; k++) if (mag[k] > frameMax) frameMax = mag[k];
  if (frameMax < 1e-6) return [];

  // Prefix sums for a ±W-bin local mean.
  const W = 12;
  const lo = Math.max(0, kLo - W);
  const hi = Math.min(mag.length - 1, kHi + W);
  const prefix = new Float64Array(hi - lo + 2);
  for (let k = lo; k <= hi; k++) prefix[k - lo + 1] = prefix[k - lo] + mag[k];

  const floor = frameMax * 0.003; // −50 dB relative to the loudest bin
  const peaks: Peak[] = [];
  for (let k = kLo; k <= kHi; k++) {
    const v = mag[k];
    if (v <= floor || v <= mag[k - 1] || v < mag[k + 1]) continue;
    const a = Math.max(lo, k - W);
    const b = Math.min(hi, k + W);
    const localMean = (prefix[b - lo + 1] - prefix[a - lo]) / (b - a + 1);
    if (v < localMean * 1.8) continue;
    const l0 = 20 * Math.log10(mag[k - 1] + 1e-12);
    const l1 = 20 * Math.log10(v + 1e-12);
    const l2 = 20 * Math.log10(mag[k + 1] + 1e-12);
    const denom = l0 - 2 * l1 + l2;
    const p = Math.abs(denom) > 1e-9 ? (0.5 * (l0 - l2)) / denom : 0;
    const peakDb = l1 - 0.25 * (l0 - l2) * p;
    peaks.push({ freq: (k + p) * binHz, mag: Math.pow(10, peakDb / 20) });
  }
  if (peaks.length > maxPeaks) {
    peaks.sort((x, y) => y.mag - x.mag);
    peaks.length = maxPeaks;
    peaks.sort((x, y) => x.freq - y.freq);
  }
  return peaks;
}

function peakMax(peaks: Peak[]): number {
  let m = 0;
  for (const p of peaks) if (p.mag > m) m = p.mag;
  return m;
}

/**
 * Accumulates a 12-bin chroma vector and a bass chroma vector from peaks.
 * `tuningCents` shifts the semitone grid (e.g. −20 for a record pitched at A=435 Hz).
 */
export function accumulateChroma(peaks: Peak[], tuningCents: number, chroma: Float32Array, bass: Float32Array): void {
  chroma.fill(0);
  bass.fill(0);
  const max = peakMax(peaks);
  if (max <= 0) return;
  const shift = tuningCents / 100;
  for (const p of peaks) {
    const m = freqToMidi(p.freq) - shift;
    const r = Math.round(m);
    const d = m - r;
    const tune = Math.cos(Math.PI * d) ** 2;
    const amp = Math.log1p((100 * p.mag) / max);
    const pc = mod12(r);
    if (p.freq >= 65 && p.freq <= 2100) {
      const oct = Math.exp(-0.5 * ((m - 62) / 13) ** 2);
      chroma[pc] += tune * oct * amp;
    }
    if (p.freq >= 38 && p.freq <= 260) {
      const low = Math.exp(-0.5 * ((m - 40) / 7) ** 2);
      bass[pc] += tune * low * amp;
    }
  }
}

export function l2normalize(v: Float32Array): number {
  let s = 0;
  for (let i = 0; i < v.length; i++) s += v[i] * v[i];
  const n = Math.sqrt(s);
  if (n > 0) for (let i = 0; i < v.length; i++) v[i] /= n;
  return n;
}

const HARMONIC_RATIOS = [5, 7, 10, 14, 2.5, 3.5];

/**
 * Estimates how far the recording sits from A = 440 Hz, using a circular mean of
 * every strong partial's deviation from the equal-tempered grid. Partials that are
 * 5th/7th harmonics (which are naturally ~14 and ~31 cents flat of the grid) are
 * skipped so bright, distorted guitars do not drag the estimate.
 */
export class TuningEstimator {
  re = 0;
  im = 0;
  w = 0;

  addPeaks(peaks: Peak[]): void {
    const band = peaks.filter((p) => p.freq >= 90 && p.freq <= 2000);
    if (band.length === 0) return;
    const max = peakMax(band);
    const strong = band
      .filter((p) => p.mag >= 0.15 * max)
      .sort((a, b) => b.mag - a.mag)
      .slice(0, 12);
    for (const p of strong) {
      let harmonic = false;
      for (const q of band) {
        if (q.freq >= p.freq || q.mag < 0.25 * p.mag) continue;
        const ratio = p.freq / q.freq;
        for (const h of HARMONIC_RATIOS) {
          if (Math.abs(ratio / h - 1) < 0.009) { harmonic = true; break; }
        }
        if (harmonic) break;
      }
      if (harmonic) continue;
      const m = freqToMidi(p.freq);
      const d = m - Math.round(m);
      const ang = 2 * Math.PI * d;
      const ww = (p.mag / max) ** 2;
      this.re += ww * Math.cos(ang);
      this.im += ww * Math.sin(ang);
      this.w += ww;
    }
  }

  decay(f: number): void {
    this.re *= f; this.im *= f; this.w *= f;
  }

  merge(o: { re: number; im: number; w: number }): void {
    this.re += o.re; this.im += o.im; this.w += o.w;
  }

  /** Offset from A440 in cents, in (−50, 50]. */
  get cents(): number {
    if (this.w <= 0) return 0;
    return (100 * Math.atan2(this.im, this.re)) / (2 * Math.PI);
  }

  /** 0..1 — 1 means every partial agreed on the same offset. */
  get confidence(): number {
    return this.w > 0 ? Math.hypot(this.re, this.im) / this.w : 0;
  }

  snapshot(): { re: number; im: number; w: number } {
    return { re: this.re, im: this.im, w: this.w };
  }
}

/**
 * Looks for a "power-chord stack" (root + fifth + octave) in the low register and
 * returns the MIDI note of its root. Bass guitars rarely play fifths, so a stack
 * rooted below E2 is strong evidence that a guitar is tuned down.
 */
export function detectLowStack(peaks: Peak[], tuningCents: number): number | null {
  const max = peakMax(peaks);
  if (max <= 0) return null;
  const tol = 0.016;
  for (const c of peaks) {
    if (c.freq < 48) continue;
    if (c.freq > 100) break;
    if (c.mag < 0.08 * max) continue;
    let fifth = false, octave = false;
    for (const p of peaks) {
      if (p.freq <= c.freq) continue;
      if (p.freq > c.freq * 2.1) break;
      if (p.mag < 0.12 * c.mag) continue;
      const r = p.freq / c.freq;
      if (Math.abs(r / 1.4983 - 1) < tol) fifth = true;
      else if (Math.abs(r / 2 - 1) < tol) octave = true;
    }
    if (fifth && octave) return Math.round(freqToMidi(c.freq) - tuningCents / 100);
  }
  return null;
}

/** Lowest clearly-sounding pitch (MIDI), for the "lowest note heard" readout. */
export function lowestNote(peaks: Peak[], tuningCents: number): number | null {
  const low = peaks.filter((p) => p.freq >= 38 && p.freq <= 400);
  if (low.length === 0) return null;
  const max = peakMax(low);
  for (const p of low) {
    if (p.mag >= 0.3 * max) return Math.round(freqToMidi(p.freq) - tuningCents / 100);
  }
  return null;
}
