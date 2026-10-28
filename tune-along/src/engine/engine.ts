/**
 * The listening engine. Feed it audio (any sample rate, any chunk size); it
 *  - tracks loudness and decides when music starts/stops (one song = one segment),
 *  - computes live chroma, chord, key, tempo and tuning estimates,
 *  - fingerprints everything and, every second, asks the song index "do I know this?",
 *  - when a segment ends, returns everything needed to store or update the song.
 * Pure TypeScript with no DOM access: it runs in a Web Worker and under Vitest.
 */
import { FFT, hann } from '../dsp/fft';
import { ANALYSIS_RATE, StreamResampler } from '../dsp/resample';
import {
  CHROMA_BIN_HZ, CHROMA_FFT, CHROMA_HOP, CHROMA_HOP_SEC, TuningEstimator, accumulateChroma,
  detectLowStack, findPeaks, l2normalize, lowestNote, type Peak,
} from '../dsp/chroma';
import { NUM_STATES, OnlineChordDecoder, scoreFrame, stateToChord, type ChordSegment } from '../dsp/chords';
import { FP_HOP, FP_HOP_SEC, Fingerprinter, FingerprintIndex, isConfidentMatch, type FingerprintData, type MatchResult } from '../dsp/fingerprint';
import { detectKey, type KeyResult } from '../dsp/key';
import { estimateTempo } from '../dsp/tempo';
import { inferTuning, type TuningReport } from '../dsp/tuning';
import { analyzeFeatures, type AnalysisResult, type FrameFeatures, type TuningAccumulator } from './analysis';

export interface LiveFrame {
  /** Session seconds of audio processed so far. */
  now: number;
  /** Session time the frame describes (window centre). */
  t: number;
  chroma: number[];
  state: number;
  confidence: number;
  rms: number;
  music: boolean;
  lowest: number | null;
}

export interface LiveMatch {
  songId: string;
  /** songTime = sessionTime + offsetSec */
  offsetSec: number;
  score: number;
  since: number;
}

export interface SegmentResult extends FrameFeatures, AnalysisResult {
  /** Session seconds at which chroma frame 0 starts. */
  sessionStart: number;
  duration: number;
  bpm: number | null;
  /** Fingerprints with times in fp frames from the segment start. */
  fp: FingerprintData;
  /** If the segment was recognised: segmentTime + offsetSec = songTime. */
  match: { songId: string; offsetSec: number; score: number } | null;
  /** Fraction of the segment's duration that was locked to `match`. */
  matchedFraction: number;
}

export interface EngineEvents {
  onFrame?(f: LiveFrame): void;
  onTuning?(r: TuningReport): void;
  onKey?(k: KeyResult | null): void;
  onTempo?(bpm: number | null): void;
  onMatch?(m: LiveMatch | null, now: number): void;
  onSegment?(s: SegmentResult): void;
  onMusic?(music: boolean, now: number): void;
}

export interface EngineConfig {
  /** Minimum length for an unrecognised segment to be kept as a new song. */
  minSongSec: number;
  /** Silence needed to close a segment. */
  silenceSec: number;
  matchEverySec: number;
  matchWindowSec: number;
}

export const DEFAULT_CONFIG: EngineConfig = { minSongSec: 12, silenceSec: 2.5, matchEverySec: 1, matchWindowSec: 9 };

const FP_PER_CHROMA = CHROMA_HOP / FP_HOP; // 4

class GrowF32 {
  data: Float32Array;
  length = 0;
  constructor(cap = 4096) { this.data = new Float32Array(cap); }
  pushArray(v: ArrayLike<number>): void {
    if (this.length + v.length > this.data.length) {
      const d = new Float32Array(Math.max(this.data.length * 2, this.length + v.length));
      d.set(this.data.subarray(0, this.length));
      this.data = d;
    }
    for (let i = 0; i < v.length; i++) this.data[this.length + i] = v[i];
    this.length += v.length;
  }
  push(x: number): void { this.pushArray([x]); }
  slice(a = 0, b = this.length): Float32Array { return this.data.slice(a, b); }
}

class GrowU32 {
  data = new Uint32Array(4096);
  length = 0;
  pushAll(v: Uint32Array): void {
    if (this.length + v.length > this.data.length) {
      const d = new Uint32Array(Math.max(this.data.length * 2, this.length + v.length));
      d.set(this.data.subarray(0, this.length));
      this.data = d;
    }
    this.data.set(v, this.length);
    this.length += v.length;
  }
}

interface Segment {
  startFrame: number; // session chroma frame
  lastMusicFrame: number;
  peaks: Float32Array[]; // per frame [f0, m0, f1, m1…]
  energy: GrowF32;
  tuning: TuningEstimator;
  liveStates: number[];
  match: LiveMatch | null;
  lastConfirm: number;
  matchedFrames: number;
  matchVotes: Map<string, { offsetSec: number; score: number; frames: number }>;
}

export class AnalysisEngine {
  readonly config: EngineConfig;
  private resampler: StreamResampler;
  private readonly fft = new FFT(CHROMA_FFT);
  private readonly win = hann(CHROMA_FFT);
  private readonly mag = new Float32Array(CHROMA_FFT / 2 + 1);
  private pending = new Float32Array(CHROMA_FFT * 4);
  private pendingLen = 0;
  private frame = 0; // chroma frames processed
  private samples = 0; // analysis-rate samples received
  private readonly fp = new Fingerprinter();
  private readonly fpHashes = new GrowU32();
  private readonly fpTimes = new GrowU32();
  private index: FingerprintIndex = new FingerprintIndex();
  private decoder = new OnlineChordDecoder();
  private readonly chroma = new Float32Array(12);
  private readonly bass = new Float32Array(12);
  private readonly scores = new Float32Array(NUM_STATES);
  private readonly liveTuning = new TuningEstimator();
  private liveChromaSum = new Float64Array(12);
  private liveStacks = new Float32Array(128);
  private liveMusicFrames = 0;
  // activity detection
  private music = false;
  private loudRun = 0;
  private quietRun = 0;
  private noiseFloor = 0.002;
  private seg: Segment | null = null;
  private lastMatchAt = -Infinity;
  private lastReportAt = 0;
  private lastTempoAt = 0;

  constructor(inputRate: number, private readonly events: EngineEvents = {}, config: Partial<EngineConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.resampler = new StreamResampler(inputRate);
  }

  setIndex(index: FingerprintIndex): void {
    this.index = index;
  }

  /** Session seconds of audio processed. */
  get now(): number {
    return this.samples / ANALYSIS_RATE;
  }

  get currentMatch(): LiveMatch | null {
    return this.seg?.match ?? null;
  }

  pushAudio(input: Float32Array): void {
    const x = this.resampler.process(input);
    if (x.length === 0) return;
    this.samples += x.length;
    this.fp.push(x);
    const fresh = this.fp.takeNew();
    if (fresh.hashes.length) {
      this.fpHashes.pushAll(fresh.hashes);
      this.fpTimes.pushAll(fresh.times);
    }
    let offset = 0;
    while (offset < x.length) {
      const room = this.pending.length - this.pendingLen;
      const n = Math.min(room, x.length - offset);
      this.pending.set(x.subarray(offset, offset + n), this.pendingLen);
      this.pendingLen += n;
      offset += n;
      let start = 0;
      while (this.pendingLen - start >= CHROMA_FFT) {
        this.processFrame(start);
        start += CHROMA_HOP;
      }
      if (start > 0) {
        this.pending.copyWithin(0, start, this.pendingLen);
        this.pendingLen -= start;
      }
    }
  }

  private processFrame(start: number): void {
    const buf = this.pending;
    let e = 0;
    for (let i = 0; i < CHROMA_FFT; i++) e += buf[start + i] * buf[start + i];
    const rms = Math.sqrt(e / CHROMA_FFT);
    const i = this.frame++;
    const t = i * CHROMA_HOP_SEC + (CHROMA_FFT / 2) / ANALYSIS_RATE;

    // --- music / silence detection with hysteresis and an adaptive noise floor
    // The floor drops quickly to quieter input and only creeps up while no music is
    // playing, so a long loud song cannot raise it and cut itself off.
    if (rms < this.noiseFloor) this.noiseFloor = rms * 0.5 + this.noiseFloor * 0.5;
    else if (!this.music) this.noiseFloor = Math.min(rms, this.noiseFloor * 1.003);
    this.noiseFloor = Math.max(0.0003, Math.min(this.noiseFloor, 0.03));
    const enter = Math.max(0.006, this.noiseFloor * 4);
    const exit = Math.max(0.003, this.noiseFloor * 2);
    if (rms > enter) { this.loudRun++; this.quietRun = 0; } else if (rms < exit) { this.quietRun++; this.loudRun = 0; } else { this.loudRun = 0; }
    const silenceFrames = Math.round(this.config.silenceSec / CHROMA_HOP_SEC);
    if (!this.music && this.loudRun >= 3) {
      this.music = true;
      this.startSegment(i);
      this.events.onMusic?.(true, this.now);
    } else if (this.music && this.quietRun >= silenceFrames) {
      this.music = false;
      this.endSegment();
      this.events.onMusic?.(false, this.now);
    }

    // --- spectrum → peaks → live features
    this.fft.magnitudes(buf, this.win, this.mag, start);
    const peaks = rms > 1e-4 ? findPeaks(this.mag, CHROMA_BIN_HZ, 40, 4000) : [];
    if (this.music) {
      this.liveTuning.addPeaks(peaks);
      // let the live estimate adapt if a new song starts (≈30 s memory)
      this.liveTuning.decay(0.997);
    }
    const cents = this.liveTuning.w > 0.5 ? this.liveTuning.cents : 0;
    accumulateChroma(peaks, cents, this.chroma, this.bass);
    const norm = l2normalize(this.chroma);
    const ok = this.music && norm > 0 && rms > 0.0025;
    scoreFrame(this.chroma, this.bass, ok, this.scores);
    const dec = this.decoder.push(this.scores);
    const stack = ok ? detectLowStack(peaks, cents) : null;
    if (ok) {
      this.liveMusicFrames++;
      for (let k = 0; k < 12; k++) this.liveChromaSum[k] += this.chroma[k];
      if (stack !== null) this.liveStacks[stack]++;
    }

    if (this.seg) {
      const packed = new Float32Array(peaks.length * 2);
      peaks.forEach((p, k) => { packed[2 * k] = p.freq; packed[2 * k + 1] = p.mag; });
      this.seg.peaks.push(packed);
      this.seg.energy.push(rms);
      if (this.music) this.seg.tuning.addPeaks(peaks);
      this.seg.liveStates.push(dec.state);
      if (rms > exit) this.seg.lastMusicFrame = i;
      if (this.seg.match) this.seg.matchedFrames++;
    }

    this.events.onFrame?.({
      now: this.now, t, chroma: Array.from(this.chroma), state: dec.state, confidence: dec.confidence,
      rms, music: this.music, lowest: ok ? lowestNote(peaks, cents) : null,
    });

    // --- periodic jobs
    const now = this.now;
    if (this.seg && now - this.lastMatchAt >= this.config.matchEverySec) {
      this.lastMatchAt = now;
      this.runMatch(now);
    }
    if (this.seg && now - this.lastReportAt >= 2) {
      this.lastReportAt = now;
      this.events.onTuning?.(this.liveReport());
      this.events.onKey?.(detectKey(this.liveChromaSum));
    }
    if (this.seg && now - this.lastTempoAt >= 4) {
      this.lastTempoAt = now;
      const n = this.fp.onset.length;
      const from = Math.max(0, n - Math.round(20 / FP_HOP_SEC), this.seg.startFrame * FP_PER_CHROMA);
      const tempo = estimateTempo(this.fp.onset.slice(from), 1 / FP_HOP_SEC);
      this.events.onTempo?.(tempo ? tempo.bpm : null);
    }
  }

  private liveReport(): TuningReport {
    const states = this.seg?.liveStates ?? [];
    const chords: ChordSegment[] = [];
    let runStart = 0;
    for (let k = 1; k <= states.length; k++) {
      if (k === states.length || states[k] !== states[runStart]) {
        const c = stateToChord(states[runStart]);
        chords.push({ start: runStart * CHROMA_HOP_SEC, end: k * CHROMA_HOP_SEC, root: c.root, type: c.type, confidence: 1 });
        runStart = k;
      }
    }
    return inferTuning(
      { cents: this.liveTuning.cents, centsConfidence: this.liveTuning.confidence, stacks: this.liveStacks, musicFrames: this.liveMusicFrames },
      chords,
      CHROMA_HOP_SEC,
    );
  }

  private startSegment(startFrame: number): void {
    this.seg = {
      startFrame,
      lastMusicFrame: startFrame,
      peaks: [],
      energy: new GrowF32(),
      tuning: new TuningEstimator(),
      liveStates: [],
      match: null,
      lastConfirm: this.now,
      matchedFrames: 0,
      matchVotes: new Map(),
    };
    this.liveChromaSum = new Float64Array(12);
    this.liveStacks = new Float32Array(128);
    this.liveMusicFrames = 0;
    this.decoder.reset();
    this.lastReportAt = this.now;
    this.lastTempoAt = this.now;
  }

  /** Hashes whose anchor lies in the last `seconds` of the session. */
  private recentHashes(seconds: number, sinceFrame: number): FingerprintData {
    const minT = Math.max(sinceFrame, this.fp.frame - Math.round(seconds / FP_HOP_SEC));
    let lo = this.fpTimes.length;
    while (lo > 0 && this.fpTimes.data[lo - 1] >= minT) lo--;
    return {
      hashes: this.fpHashes.data.slice(lo, this.fpHashes.length),
      times: this.fpTimes.data.slice(lo, this.fpTimes.length),
    };
  }

  private runMatch(now: number): void {
    const seg = this.seg!;
    if (this.index.size === 0) return;
    const segFpStart = seg.startFrame * FP_PER_CHROMA;
    const q = this.recentHashes(this.config.matchWindowSec, Math.max(0, segFpStart - 40));
    if (q.hashes.length < 20) return;
    const m: MatchResult | null = this.index.query(q);
    if (!isConfidentMatch(m)) {
      if (seg.match && now - seg.lastConfirm > 12) {
        seg.match = null;
        this.events.onMatch?.(null, now);
      }
      return;
    }
    // Songs repeat (chorus 1 ≈ chorus 2). Among near-equal offsets, keep following the
    // one we are already on; on a fresh match prefer the earliest occurrence.
    const strong = [{ offset: m.offset, score: m.score }, ...m.alternatives]
      .filter((a, i, arr) => arr.findIndex((b) => b.offset === a.offset) === i && a.score >= 0.8 * m.score);
    let chosen = strong[0];
    if (seg.match && seg.match.songId === m.songId) {
      const cur = Math.round(seg.match.offsetSec / FP_HOP_SEC);
      const same = [{ offset: m.offset, score: m.score }, ...m.alternatives].find((a) => Math.abs(a.offset - cur) <= 6 && a.score >= 0.6 * m.score);
      if (same) chosen = same;
    } else {
      chosen = strong.reduce((a, b) => (b.offset < a.offset ? b : a), strong[0]);
    }
    const offsetSec = chosen.offset * FP_HOP_SEC;
    if (seg.match && seg.match.songId === m.songId) {
      if (Math.abs(offsetSec - seg.match.offsetSec) > 0.25) {
        seg.match = { ...seg.match, offsetSec, score: chosen.score };
        this.events.onMatch?.(seg.match, now);
      } else {
        seg.match.score = chosen.score;
      }
      seg.lastConfirm = now;
      this.vote(seg, seg.match);
    } else if (!seg.match || m.score > 1.5 * seg.match.score || now - seg.lastConfirm > 6) {
      seg.match = { songId: m.songId, offsetSec, score: chosen.score, since: now };
      seg.lastConfirm = now;
      this.vote(seg, seg.match);
      this.events.onMatch?.(seg.match, now);
    }
  }

  private vote(seg: Segment, m: LiveMatch): void {
    const v = seg.matchVotes.get(m.songId);
    // keep the most recent offset: later evidence has resolved repeats better
    seg.matchVotes.set(m.songId, { offsetSec: m.offsetSec, score: Math.max(m.score, v?.score ?? 0), frames: (v?.frames ?? 0) + 1 });
  }

  /** Stop listening: closes the current segment (if any) and returns it. */
  stop(): SegmentResult | null {
    this.fp.flush();
    const fresh = this.fp.takeNew();
    if (fresh.hashes.length) {
      this.fpHashes.pushAll(fresh.hashes);
      this.fpTimes.pushAll(fresh.times);
    }
    const r = this.endSegment(true);
    this.music = false;
    return r;
  }

  private endSegment(stopping = false): SegmentResult | null {
    const seg = this.seg;
    this.seg = null;
    if (!seg) return null;
    const result = this.finalize(seg, stopping);
    if (result) this.events.onSegment?.(result);
    if (seg.match) this.events.onMatch?.(null, this.now);
    return result;
  }

  private finalize(seg: Segment, stopping: boolean): SegmentResult | null {
    // trim trailing silence (keep a little tail)
    const keep = Math.min(seg.peaks.length, seg.lastMusicFrame - seg.startFrame + 6);
    const n = Math.max(0, keep);
    const duration = n * CHROMA_HOP_SEC;
    const totalFrames = Math.max(1, seg.peaks.length);
    const matchedFraction = seg.matchedFrames / totalFrames;
    let best: { songId: string; offsetSec: number; score: number } | null = null;
    for (const [songId, v] of seg.matchVotes) if (!best || v.score > best.score) best = { songId, offsetSec: v.offsetSec, score: v.score };
    const recognised = best !== null && (matchedFraction >= 0.3 || seg.matchVotes.size > 0 && duration < 25);
    const minSec = stopping ? Math.min(8, this.config.minSongSec) : this.config.minSongSec;
    if (!recognised && duration < minSec) return null;

    const cents = seg.tuning.cents;
    const chroma = new Float32Array(n * 12);
    const bass = new Float32Array(n * 12);
    const energy = seg.energy.slice(0, n);
    const stacks = new Float32Array(128);
    let musicFrames = 0;
    const row = new Float32Array(12), brow = new Float32Array(12);
    for (let f = 0; f < n; f++) {
      const packed = seg.peaks[f];
      const peaks: Peak[] = [];
      for (let k = 0; k < packed.length; k += 2) peaks.push({ freq: packed[k], mag: packed[k + 1] });
      accumulateChroma(peaks, cents, row, brow);
      const norm = l2normalize(row);
      chroma.set(row, f * 12);
      bass.set(brow, f * 12);
      if (norm > 0 && energy[f] > 0.0025) {
        musicFrames++;
        const st = detectLowStack(peaks, cents);
        if (st !== null) stacks[st]++;
      }
    }
    const tuningAcc: TuningAccumulator = seg.tuning.snapshot();
    const features: FrameFeatures = { chroma, bass, energy, stacks, musicFrames, tuningAcc };
    const analysis = analyzeFeatures(features, 0);

    const fpStart = seg.startFrame * FP_PER_CHROMA;
    const fpEnd = fpStart + n * FP_PER_CHROMA;
    const hashes: number[] = [], times: number[] = [];
    for (let k = 0; k < this.fpTimes.length; k++) {
      const tt = this.fpTimes.data[k];
      if (tt >= fpStart && tt < fpEnd) { hashes.push(this.fpHashes.data[k]); times.push(tt - fpStart); }
    }
    const onset = this.fp.onset.slice(fpStart, Math.min(this.fp.onset.length, fpEnd));
    const tempo = estimateTempo(onset, 1 / FP_HOP_SEC);
    const sessionStart = seg.startFrame * CHROMA_HOP_SEC;
    return {
      ...features,
      ...analysis,
      sessionStart,
      duration,
      bpm: tempo ? Math.round(tempo.bpm * 10) / 10 : null,
      fp: { hashes: Uint32Array.from(hashes), times: Uint32Array.from(times) },
      match: recognised && best ? { songId: best.songId, offsetSec: best.offsetSec + sessionStart, score: best.score } : null,
      matchedFraction,
    };
  }
}
