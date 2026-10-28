/**
 * Streaming resampler to TuneAlong's fixed analysis rate.
 *
 * Every device records at a different rate (44.1 kHz, 48 kHz, 16 kHz…). The song
 * fingerprints must be identical no matter which device learned the song, so all
 * analysis happens at exactly ANALYSIS_RATE. An 8th-order Butterworth low-pass
 * (four biquads) removes content that would alias, then linear interpolation
 * produces the output stream. State carries across chunks, so feeding 128 samples
 * at a time gives the same output as feeding the whole file at once.
 */
export const ANALYSIS_RATE = 11025;

class Biquad {
  private b0 = 1; private b1 = 0; private b2 = 0; private a1 = 0; private a2 = 0;
  private z1 = 0; private z2 = 0;
  constructor(fs: number, fc: number, q: number) {
    const w0 = (2 * Math.PI * fc) / fs;
    const cos = Math.cos(w0);
    const alpha = Math.sin(w0) / (2 * q);
    const a0 = 1 + alpha;
    this.b0 = (1 - cos) / 2 / a0;
    this.b1 = (1 - cos) / a0;
    this.b2 = (1 - cos) / 2 / a0;
    this.a1 = (-2 * cos) / a0;
    this.a2 = (1 - alpha) / a0;
  }
  /** Transposed direct form II, in place. */
  run(x: Float32Array): void {
    let z1 = this.z1, z2 = this.z2;
    const { b0, b1, b2, a1, a2 } = this;
    for (let i = 0; i < x.length; i++) {
      const v = x[i];
      const y = b0 * v + z1;
      z1 = b1 * v - a1 * y + z2;
      z2 = b2 * v - a2 * y;
      x[i] = y;
    }
    this.z1 = z1; this.z2 = z2;
  }
}

// Q values for an 8th-order Butterworth split into four biquads.
const BUTTER8_Q = [0.5098, 0.6013, 0.9, 2.5629];

export class StreamResampler {
  readonly inRate: number;
  readonly outRate: number;
  private readonly step: number;
  private readonly filters: Biquad[] = [];
  private t = 1; // position of the next output sample; index 0 = last sample of previous chunk
  private last = 0;

  constructor(inRate: number, outRate = ANALYSIS_RATE) {
    if (!(inRate > 0)) throw new Error('bad input rate');
    this.inRate = inRate;
    this.outRate = outRate;
    this.step = inRate / outRate;
    if (inRate > outRate * 1.02) {
      const fc = Math.min(outRate * 0.41, inRate * 0.45); // ≈4.5 kHz for 11025 output
      for (const q of BUTTER8_Q) this.filters.push(new Biquad(inRate, fc, q));
    }
  }

  get passthrough(): boolean {
    return Math.abs(this.step - 1) < 1e-9;
  }

  process(input: Float32Array): Float32Array {
    if (this.passthrough) return input.slice();
    const n = input.length;
    if (n === 0) return new Float32Array(0);
    const x = input.slice();
    for (const f of this.filters) f.run(x);
    const maxOut = Math.ceil((n - this.t) / this.step) + 2;
    const out = new Float32Array(Math.max(0, maxOut));
    let count = 0;
    let t = this.t;
    const last = this.last;
    while (t < n) {
      const i = Math.floor(t);
      const frac = t - i;
      const a = i === 0 ? last : x[i - 1];
      const b = x[i];
      out[count++] = a + (b - a) * frac;
      t += this.step;
    }
    this.t = t - n;
    this.last = x[n - 1];
    return out.subarray(0, count);
  }
}

/** Convenience for whole buffers (tests, file analysis). */
export function resampleBuffer(input: Float32Array, inRate: number, outRate = ANALYSIS_RATE): Float32Array {
  const r = new StreamResampler(inRate, outRate);
  return r.process(input).slice();
}
