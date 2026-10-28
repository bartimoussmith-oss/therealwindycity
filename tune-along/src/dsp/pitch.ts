/**
 * Monophonic pitch detection (YIN, de Cheveigné & Kawahara 2002) used by the tuner.
 * Returns the fundamental frequency of a single plucked string / sung note.
 */
export interface PitchResult {
  freq: number;
  /** 0..1 — how periodic the signal is (1 = perfectly periodic). */
  clarity: number;
  rms: number;
}

export interface YinOptions {
  minFreq?: number;
  maxFreq?: number;
  threshold?: number;
  /** Below this RMS the frame is treated as silence. */
  minRms?: number;
}

export function detectPitch(buf: Float32Array, sampleRate: number, opts: YinOptions = {}): PitchResult | null {
  const minFreq = opts.minFreq ?? 38;
  const maxFreq = opts.maxFreq ?? 1400;
  const threshold = opts.threshold ?? 0.12;
  const minRms = opts.minRms ?? 0.004;

  let energy = 0;
  for (let i = 0; i < buf.length; i++) energy += buf[i] * buf[i];
  const level = Math.sqrt(energy / buf.length);
  if (level < minRms) return null;

  const maxTau = Math.min(Math.floor(sampleRate / minFreq), Math.floor(buf.length / 2));
  const minTau = Math.max(2, Math.floor(sampleRate / maxFreq));
  if (maxTau <= minTau + 2) return null;
  const w = buf.length - maxTau;

  // Difference function d(tau) and its cumulative mean normalised form.
  const d = new Float32Array(maxTau + 1);
  for (let tau = 1; tau <= maxTau; tau++) {
    let s = 0;
    for (let j = 0; j < w; j++) {
      const diff = buf[j] - buf[j + tau];
      s += diff * diff;
    }
    d[tau] = s;
  }
  const cmnd = new Float32Array(maxTau + 1);
  cmnd[0] = 1;
  let running = 0;
  for (let tau = 1; tau <= maxTau; tau++) {
    running += d[tau];
    cmnd[tau] = running > 0 ? (d[tau] * tau) / running : 1;
  }

  let tauEst = -1;
  for (let tau = minTau; tau < maxTau; tau++) {
    if (cmnd[tau] < threshold) {
      while (tau + 1 < maxTau && cmnd[tau + 1] < cmnd[tau]) tau++;
      tauEst = tau;
      break;
    }
  }
  if (tauEst < 0) {
    // No dip under the threshold: fall back to the global minimum, but only if it is convincing.
    let best = minTau;
    for (let tau = minTau; tau < maxTau; tau++) if (cmnd[tau] < cmnd[best]) best = tau;
    if (cmnd[best] > 0.35) return null;
    tauEst = best;
  }
  // Octave guard: a string with a weak fundamental can look periodic at half its
  // period. If the doubled period is clearly *more* periodic, take it instead.
  for (let guard = 0; guard < 2; guard++) {
    const t2 = tauEst * 2;
    if (t2 + 2 >= maxTau || cmnd[tauEst] < 0.04) break;
    let b2 = t2;
    for (let tau = Math.max(minTau, t2 - 2); tau <= t2 + 2; tau++) if (cmnd[tau] < cmnd[b2]) b2 = tau;
    if (cmnd[b2] < 0.4 * cmnd[tauEst]) tauEst = b2; else break;
  }

  // Parabolic interpolation for sub-sample accuracy.
  let betterTau = tauEst;
  if (tauEst > 1 && tauEst < maxTau) {
    const s0 = cmnd[tauEst - 1], s1 = cmnd[tauEst], s2 = cmnd[tauEst + 1];
    const denom = s0 + s2 - 2 * s1;
    if (Math.abs(denom) > 1e-12) betterTau = tauEst + (s0 - s2) / (2 * denom);
  }
  const freq = sampleRate / betterTau;
  if (!Number.isFinite(freq) || freq < minFreq * 0.9 || freq > maxFreq * 1.1) return null;
  return { freq, clarity: Math.max(0, Math.min(1, 1 - cmnd[tauEst])), rms: level };
}

/** Cheap 2:1 / 4:1 decimation with a short low-pass, for running the tuner at 48 kHz devices. */
export function decimate(buf: Float32Array, factor: number): Float32Array {
  if (factor <= 1) return buf;
  const out = new Float32Array(Math.floor(buf.length / factor));
  for (let i = 0; i < out.length; i++) {
    let s = 0;
    const base = i * factor;
    for (let k = 0; k < factor; k++) s += buf[base + k];
    out[i] = s / factor;
  }
  return out;
}
