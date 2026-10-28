/**
 * Song memory: landmark audio fingerprinting (spectral-peak pairs), the same family
 * of technique popularised by Wang (2003). The first time TuneAlong hears a song it
 * stores ~20–30 compact hashes per second; the next time, a few seconds of audio —
 * even through a phone microphone in a noisy room — line up with the stored hashes
 * at one consistent time offset, which says both WHICH song and WHERE in it we are.
 *
 * Everything runs at the fixed ANALYSIS_RATE so a song learned on a laptop is
 * recognised on a phone.
 */
import { FFT, hann } from './fft';
import { ANALYSIS_RATE } from './resample';

export const FP_FFT = 1024;
export const FP_HOP = 256;
export const FP_HOP_SEC = FP_HOP / ANALYSIS_RATE;
export const FP_VERSION = 1;

const K_MIN = 20; // ≈215 Hz — below this phone mics and rooms are unreliable
const K_MAX = 420; // ≈4.5 kHz — the resampler's anti-alias corner
const NB = K_MAX - K_MIN + 1;
const NT = 6; // ±6 frames (±140 ms) time neighbourhood
const NF = 9; // ±9 bins (±97 Hz) frequency neighbourhood
const DT_MIN = 1;
const DT_MAX = 63; // pair with peaks up to ~1.46 s later
const DF_MAX = 120;
const FANOUT = 5;
const MAX_PEAKS_PER_FRAME = 5;
const FLOOR_DB = -110;

class GrowU32 {
  data = new Uint32Array(1024);
  length = 0;
  push(v: number): void {
    if (this.length === this.data.length) {
      const d = new Uint32Array(this.data.length * 2);
      d.set(this.data);
      this.data = d;
    }
    this.data[this.length++] = v >>> 0;
  }
  slice(from = 0, to = this.length): Uint32Array {
    return this.data.slice(from, to);
  }
}

export interface FingerprintData {
  hashes: Uint32Array;
  times: Uint32Array;
}

export function packHash(k1: number, k2: number, dt: number): number {
  return (((k1 - K_MIN) << 15) | ((k2 - K_MIN) << 6) | dt) >>> 0;
}

/**
 * Streaming fingerprinter. Push ANALYSIS_RATE samples in any chunk size; read new
 * hashes with takeNew(). Also exposes a spectral-flux onset envelope for tempo.
 */
export class Fingerprinter {
  private readonly fft = new FFT(FP_FFT);
  private readonly win = hann(FP_FFT);
  private readonly mag = new Float32Array(FP_FFT / 2 + 1);
  private pending = new Float32Array(FP_FFT * 4);
  private pendingLen = 0;
  /** Index of the next frame to be computed. Frame i starts at sample i·FP_HOP. */
  frame = 0;
  private readonly specRing: Float32Array[] = [];
  private readonly fmaxRing: Float32Array[] = [];
  private readonly ringFrames: number[] = [];
  private readonly meanRing: number[] = [];
  private prevSpec: Float32Array | null = null;
  private runningMaxDb = -200;
  private peaks: { t: number; k: number }[] = [];
  private readonly hashes = new GrowU32();
  private readonly times = new GrowU32();
  private taken = 0;
  readonly onset: number[] = [];
  peakCount = 0;

  push(samples: Float32Array): void {
    let offset = 0;
    while (offset < samples.length) {
      const room = this.pending.length - this.pendingLen;
      const n = Math.min(room, samples.length - offset);
      this.pending.set(samples.subarray(offset, offset + n), this.pendingLen);
      this.pendingLen += n;
      offset += n;
      let start = 0;
      while (this.pendingLen - start >= FP_FFT) {
        this.processFrame(this.pending, start);
        start += FP_HOP;
      }
      if (start > 0) {
        this.pending.copyWithin(0, start, this.pendingLen);
        this.pendingLen -= start;
      }
    }
  }

  private processFrame(buf: Float32Array, start: number): void {
    let energy = 0;
    for (let i = 0; i < FP_FFT; i++) energy += buf[start + i] * buf[start + i];
    const silent = Math.sqrt(energy / FP_FFT) < 2e-4;
    this.fft.magnitudes(buf, this.win, this.mag, start);
    const spec = new Float32Array(NB);
    let mean = 0;
    for (let k = 0; k < NB; k++) {
      const v = silent ? FLOOR_DB : Math.max(FLOOR_DB, 20 * Math.log10(this.mag[k + K_MIN] + 1e-9));
      spec[k] = v;
      mean += v;
    }
    mean /= NB;
    // onset strength (spectral flux)
    let flux = 0;
    if (this.prevSpec) for (let k = 0; k < NB; k++) {
      const d = spec[k] - this.prevSpec[k];
      if (d > 0) flux += Math.min(d, 30);
    }
    this.onset.push(silent ? 0 : flux / NB);
    this.prevSpec = spec;

    let frameMax = FLOOR_DB;
    for (let k = 0; k < NB; k++) if (spec[k] > frameMax) frameMax = spec[k];
    this.runningMaxDb = Math.max(this.runningMaxDb - 0.05, frameMax);

    const fmax = new Float32Array(NB);
    for (let k = 0; k < NB; k++) {
      let m = FLOOR_DB;
      const a = Math.max(0, k - NF), b = Math.min(NB - 1, k + NF);
      for (let j = a; j <= b; j++) if (spec[j] > m) m = spec[j];
      fmax[k] = m;
    }
    this.specRing.push(spec);
    this.fmaxRing.push(fmax);
    this.ringFrames.push(this.frame);
    this.meanRing.push(mean);
    this.frame++;
    if (this.specRing.length > 2 * NT + 1) {
      this.specRing.shift();
      this.fmaxRing.shift();
      this.ringFrames.shift();
      this.meanRing.shift();
    }
    if (this.specRing.length === 2 * NT + 1) this.detectPeaksAtCenter();
    this.pairReady(this.frame - 1 - NT - DT_MAX);
  }

  private detectPeaksAtCenter(): void {
    const c = NT;
    const spec = this.specRing[c];
    const fmax = this.fmaxRing[c];
    const mean = this.meanRing[c];
    const thresh = Math.max(mean + 9, this.runningMaxDb - 55);
    const found: { k: number; v: number }[] = [];
    for (let k = 0; k < NB; k++) {
      const v = spec[k];
      if (v < thresh || v < fmax[k]) continue;
      let isMax = true;
      for (let j = 0; j < this.fmaxRing.length; j++) {
        if (j === c) continue;
        if (this.fmaxRing[j][k] > v) { isMax = false; break; }
      }
      if (isMax) found.push({ k, v });
    }
    if (found.length > MAX_PEAKS_PER_FRAME) {
      found.sort((a, b) => b.v - a.v);
      found.length = MAX_PEAKS_PER_FRAME;
    }
    found.sort((a, b) => a.k - b.k);
    const t = this.ringFrames[c];
    for (const f of found) this.peaks.push({ t, k: f.k + K_MIN });
    this.peakCount += found.length;
  }

  /** Emit hashes for every anchor at or before frame `upTo`. */
  private pairReady(upTo: number): void {
    let consumed = 0;
    const peaks = this.peaks;
    while (consumed < peaks.length && peaks[consumed].t <= upTo) {
      const a = peaks[consumed];
      let made = 0;
      for (let j = consumed + 1; j < peaks.length && made < FANOUT; j++) {
        const p = peaks[j];
        const dt = p.t - a.t;
        if (dt < DT_MIN) continue;
        if (dt > DT_MAX) break;
        if (Math.abs(p.k - a.k) > DF_MAX) continue;
        this.hashes.push(packHash(a.k, p.k, dt));
        this.times.push(a.t);
        made++;
      }
      consumed++;
    }
    if (consumed > 0) peaks.splice(0, consumed);
  }

  /** Call at end of stream so the last ~1.5 s of anchors are paired too. */
  flush(): void {
    this.pairReady(Number.MAX_SAFE_INTEGER);
  }

  /** Hashes produced since the previous call. */
  takeNew(): FingerprintData {
    const from = this.taken;
    this.taken = this.hashes.length;
    return { hashes: this.hashes.slice(from), times: this.times.slice(from) };
  }

  all(): FingerprintData {
    return { hashes: this.hashes.slice(), times: this.times.slice() };
  }

  get hashCount(): number {
    return this.hashes.length;
  }
}

export function fingerprintSignal(samples: Float32Array): FingerprintData {
  const fp = new Fingerprinter();
  fp.push(samples);
  fp.flush();
  return fp.all();
}

// ---------------------------------------------------------------------------
// Index + matching
// ---------------------------------------------------------------------------

const TIME_BITS = 20;
const TIME_MASK = (1 << TIME_BITS) - 1;
const OFFSET_BIAS = 1 << TIME_BITS;
const KEY_SPAN = 2 ** 21;
const MAX_POSTINGS = 400; // ignore "stop-word" hashes that occur everywhere

/** LSD radix sort of 24-bit keys carrying a satellite value. */
function radixSort24(keys: Uint32Array, vals: Uint32Array): void {
  const n = keys.length;
  let k1: Uint32Array = keys, v1: Uint32Array = vals;
  let k2: Uint32Array = new Uint32Array(n), v2: Uint32Array = new Uint32Array(n);
  const count = new Uint32Array(256);
  for (let shift = 0; shift < 24; shift += 8) {
    count.fill(0);
    for (let i = 0; i < n; i++) count[(k1[i] >>> shift) & 255]++;
    let sum = 0;
    for (let b = 0; b < 256; b++) { const c = count[b]; count[b] = sum; sum += c; }
    for (let i = 0; i < n; i++) {
      const b = (k1[i] >>> shift) & 255;
      const pos = count[b]++;
      k2[pos] = k1[i];
      v2[pos] = v1[i];
    }
    const tk = k1; k1 = k2; k2 = tk;
    const tv = v1; v1 = v2; v2 = tv;
  }
  // three passes → result sits in the temporaries; copy back
  if (k1 !== keys) { keys.set(k1); vals.set(v1); }
}

export interface SongFingerprint {
  id: string;
  fp: FingerprintData;
}

export interface MatchResult {
  songId: string;
  /** stored time − query time, in fingerprint frames. */
  offset: number;
  score: number;
  /** Best score of any other song (for ambiguity checks). */
  runnerUp: number;
  queryHashes: number;
  /**
   * Other strong offsets within the same song (≥ 60 % of the best score, > 1 s
   * apart), best first. Songs repeat themselves — a chorus can match chorus 1 and
   * chorus 2 equally well — so the caller decides using continuity.
   */
  alternatives: { offset: number; score: number }[];
}

export class FingerprintIndex {
  private keys = new Uint32Array(0);
  private vals = new Uint32Array(0);
  private songIds: string[] = [];

  build(songs: SongFingerprint[]): void {
    const usable = songs.slice(0, 4095);
    let total = 0;
    for (const s of usable) total += s.fp.hashes.length;
    const keys = new Uint32Array(total);
    const vals = new Uint32Array(total);
    let p = 0;
    usable.forEach((s, idx) => {
      const { hashes, times } = s.fp;
      for (let i = 0; i < hashes.length; i++) {
        keys[p] = hashes[i];
        vals[p] = ((idx << TIME_BITS) | (times[i] & TIME_MASK)) >>> 0;
        p++;
      }
    });
    radixSort24(keys, vals);
    this.keys = keys;
    this.vals = vals;
    this.songIds = usable.map((s) => s.id);
  }

  get size(): number {
    return this.keys.length;
  }

  get songCount(): number {
    return this.songIds.length;
  }

  private lowerBound(h: number): number {
    let lo = 0, hi = this.keys.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.keys[mid] < h) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  /**
   * Finds the song/offset that the most query hashes agree on. If `onlySong` is
   * given, other songs are ignored (used to re-verify a song we are following).
   */
  query(q: FingerprintData, onlySong?: string): MatchResult | null {
    if (this.keys.length === 0 || q.hashes.length === 0) return null;
    const only = onlySong !== undefined ? this.songIds.indexOf(onlySong) : -1;
    if (onlySong !== undefined && only < 0) return null;
    const counts = new Map<number, number>();
    for (let i = 0; i < q.hashes.length; i++) {
      const h = q.hashes[i];
      const tq = q.times[i];
      let j = this.lowerBound(h);
      const start = j;
      while (j < this.keys.length && this.keys[j] === h) j++;
      if (j - start > MAX_POSTINGS) continue;
      for (let x = start; x < j; x++) {
        const v = this.vals[x];
        const s = v >>> TIME_BITS;
        if (only >= 0 && s !== only) continue;
        const off = (v & TIME_MASK) - tq + OFFSET_BIAS;
        if (off < 0) continue;
        const key = s * KEY_SPAN + off;
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
    }
    if (counts.size === 0) return null;
    const bestBySong = new Map<number, { score: number; off: number }>();
    for (const [key, c] of counts) {
      const total = c + 0.5 * ((counts.get(key - 1) ?? 0) + (counts.get(key + 1) ?? 0));
      const s = Math.floor(key / KEY_SPAN);
      const cur = bestBySong.get(s);
      if (!cur || total > cur.score) bestBySong.set(s, { score: total, off: key - s * KEY_SPAN - OFFSET_BIAS });
    }
    let bestSong = -1, best = { score: 0, off: 0 }, runner = 0;
    for (const [s, v] of bestBySong) {
      if (v.score > best.score) {
        if (bestSong >= 0) runner = Math.max(runner, best.score);
        bestSong = s; best = v;
      } else runner = Math.max(runner, v.score);
    }
    if (bestSong < 0) return null;
    // collect strong alternative offsets inside the winning song
    const cands: { offset: number; score: number }[] = [];
    for (const [key, c] of counts) {
      const s = Math.floor(key / KEY_SPAN);
      if (s !== bestSong) continue;
      const total = c + 0.5 * ((counts.get(key - 1) ?? 0) + (counts.get(key + 1) ?? 0));
      if (total >= 0.6 * best.score) cands.push({ offset: key - s * KEY_SPAN - OFFSET_BIAS, score: total });
    }
    cands.sort((a, b) => b.score - a.score);
    const alternatives: { offset: number; score: number }[] = [];
    const minGap = Math.round(1 / FP_HOP_SEC);
    for (const c of cands) {
      if (alternatives.every((a) => Math.abs(a.offset - c.offset) > minGap)) alternatives.push(c);
      if (alternatives.length >= 6) break;
    }
    return { songId: this.songIds[bestSong], offset: best.off, score: best.score, runnerUp: runner, queryHashes: q.hashes.length, alternatives };
  }
}

/** Decision rule used by the live engine. */
export function isConfidentMatch(m: MatchResult | null): m is MatchResult {
  if (!m) return false;
  return m.score >= 10 && m.score >= 2.2 * Math.max(3, m.runnerUp);
}
