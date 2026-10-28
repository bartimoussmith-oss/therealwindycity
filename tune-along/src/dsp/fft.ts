/**
 * Small, allocation-free radix-2 FFT plus window helpers.
 * Everything in TuneAlong's analysis runs on top of this file, so it is
 * deliberately boring and covered by a DFT comparison test.
 */
export class FFT {
  readonly n: number;
  private readonly rev: Uint32Array;
  private readonly cosT: Float64Array;
  private readonly sinT: Float64Array;
  private readonly re: Float64Array;
  private readonly im: Float64Array;

  constructor(n: number) {
    if (n < 2 || (n & (n - 1)) !== 0) throw new Error(`FFT size must be a power of two, got ${n}`);
    this.n = n;
    this.rev = new Uint32Array(n);
    const bits = Math.log2(n);
    for (let i = 0; i < n; i++) {
      let r = 0;
      for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b);
      this.rev[i] = r;
    }
    this.cosT = new Float64Array(n / 2);
    this.sinT = new Float64Array(n / 2);
    for (let i = 0; i < n / 2; i++) {
      this.cosT[i] = Math.cos((2 * Math.PI * i) / n);
      this.sinT[i] = Math.sin((2 * Math.PI * i) / n);
    }
    this.re = new Float64Array(n);
    this.im = new Float64Array(n);
  }

  /** In-place complex forward transform. */
  transform(re: Float64Array, im: Float64Array): void {
    const n = this.n;
    const rev = this.rev;
    for (let i = 0; i < n; i++) {
      const j = rev[i];
      if (j > i) {
        let t = re[i]; re[i] = re[j]; re[j] = t;
        t = im[i]; im[i] = im[j]; im[j] = t;
      }
    }
    for (let size = 2; size <= n; size <<= 1) {
      const half = size >> 1;
      const step = n / size;
      for (let start = 0; start < n; start += size) {
        for (let k = 0; k < half; k++) {
          const wr = this.cosT[k * step];
          const wi = -this.sinT[k * step];
          const a = start + k;
          const b = a + half;
          const xr = re[b] * wr - im[b] * wi;
          const xi = re[b] * wi + im[b] * wr;
          re[b] = re[a] - xr;
          im[b] = im[a] - xi;
          re[a] += xr;
          im[a] += xi;
        }
      }
    }
  }

  /**
   * Windowed real-input magnitude spectrum. `out` receives n/2+1 linear magnitudes,
   * scaled so a full-scale sine of amplitude A reads roughly A (for a Hann window).
   */
  magnitudes(input: ArrayLike<number>, window: Float32Array | null, out: Float32Array, offset = 0): Float32Array {
    const n = this.n;
    const re = this.re;
    const im = this.im;
    for (let i = 0; i < n; i++) {
      const v = input[offset + i] ?? 0;
      re[i] = window ? v * window[i] : v;
      im[i] = 0;
    }
    this.transform(re, im);
    const scale = window ? 4 / n : 2 / n; // Hann coherent gain is 0.5
    const half = n >> 1;
    for (let k = 0; k <= half; k++) out[k] = Math.hypot(re[k], im[k]) * scale;
    return out;
  }
}

const hannCache = new Map<number, Float32Array>();

/** Periodic Hann window (the right choice for spectral analysis). Cached per size. */
export function hann(n: number): Float32Array {
  let w = hannCache.get(n);
  if (!w) {
    w = new Float32Array(n);
    for (let i = 0; i < n; i++) w[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / n);
    hannCache.set(n, w);
  }
  return w;
}

export function rms(buf: ArrayLike<number>, start = 0, end = buf.length): number {
  let s = 0;
  for (let i = start; i < end; i++) s += buf[i] * buf[i];
  return Math.sqrt(s / Math.max(1, end - start));
}
