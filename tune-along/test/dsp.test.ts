import { describe, expect, it } from 'vitest';
import { FFT, hann } from '../src/dsp/fft';
import { ANALYSIS_RATE, StreamResampler, resampleBuffer } from '../src/dsp/resample';
import { detectPitch, decimate } from '../src/dsp/pitch';
import { CHROMA_BIN_HZ, CHROMA_FFT, TuningEstimator, accumulateChroma, findPeaks, l2normalize, detectLowStack } from '../src/dsp/chroma';
import { NUM_STATES, scoreFrame, stateToChord, chordLabel, viterbi, pathToSegments } from '../src/dsp/chords';
import { detectKey } from '../src/dsp/key';
import { estimateTempo } from '../src/dsp/tempo';
import { midiToFreq, freqToMidi, parseNote, spellingForKey, midiName } from '../src/dsp/notes';
import { mulberry32, pluck } from '../src/audio/synth';

function sine(freq: number, sr: number, seconds: number, amp = 0.5): Float32Array {
  const out = new Float32Array(Math.floor(sr * seconds));
  for (let i = 0; i < out.length; i++) out[i] = amp * Math.sin((2 * Math.PI * freq * i) / sr);
  return out;
}

function harmonicTone(freq: number, sr: number, seconds: number, partials = 8, amp = 0.3): Float32Array {
  const out = new Float32Array(Math.floor(sr * seconds));
  for (let h = 1; h <= partials; h++) {
    const a = amp / h;
    for (let i = 0; i < out.length; i++) out[i] += a * Math.sin((2 * Math.PI * freq * h * i) / sr);
  }
  return out;
}

describe('notes', () => {
  it('converts between midi and frequency', () => {
    expect(midiToFreq(69)).toBeCloseTo(440, 6);
    expect(freqToMidi(82.4069)).toBeCloseTo(40, 3);
    expect(midiName(39, 'flat')).toBe('Eb2');
    expect(parseNote('Bb')!.pc).toBe(10);
    expect(parseNote('F#3')).toEqual({ pc: 6, octave: 3 });
    expect(spellingForKey(3, 'major')).toBe('flat');
    expect(spellingForKey(7, 'major')).toBe('sharp');
  });
});

describe('FFT', () => {
  it('matches a direct DFT', () => {
    const n = 64;
    const rng = mulberry32(7);
    const x = Float64Array.from({ length: n }, () => rng() * 2 - 1);
    const re = Float64Array.from(x), im = new Float64Array(n);
    new FFT(n).transform(re, im);
    for (let k = 0; k < n; k++) {
      let sr = 0, si = 0;
      for (let t = 0; t < n; t++) {
        sr += x[t] * Math.cos((2 * Math.PI * k * t) / n);
        si -= x[t] * Math.sin((2 * Math.PI * k * t) / n);
      }
      expect(re[k]).toBeCloseTo(sr, 9);
      expect(im[k]).toBeCloseTo(si, 9);
    }
  });

  it('reads the amplitude of a windowed sine', () => {
    const n = 4096;
    const fft = new FFT(n);
    const sr = ANALYSIS_RATE;
    const k = 200;
    const x = sine((k * sr) / n, sr, 1, 0.5);
    const mag = new Float32Array(n / 2 + 1);
    fft.magnitudes(x, hann(n), mag);
    expect(mag[k]).toBeCloseTo(0.5, 2);
  });
});

describe('resampler', () => {
  for (const inRate of [48000, 44100, 22050, 16000]) {
    it(`keeps pitch when converting ${inRate} → ${ANALYSIS_RATE}`, () => {
      const x = sine(440, inRate, 1.5);
      // feed in odd-sized chunks to exercise the streaming state
      const r = new StreamResampler(inRate);
      const parts: Float32Array[] = [];
      for (let i = 0; i < x.length; i += 333) parts.push(r.process(x.subarray(i, i + 333)));
      const y = new Float32Array(parts.reduce((a, p) => a + p.length, 0));
      let o = 0;
      for (const p of parts) { y.set(p, o); o += p.length; }
      expect(Math.abs(y.length - 1.5 * ANALYSIS_RATE)).toBeLessThan(3);
      const whole = resampleBuffer(x, inRate);
      expect(Math.abs(whole.length - y.length)).toBeLessThanOrEqual(1);
      const p = detectPitch(y.subarray(4000, 6048), ANALYSIS_RATE)!;
      expect(Math.abs(1200 * Math.log2(p.freq / 440))).toBeLessThan(1.5);
    });
  }

  it('suppresses content above the analysis Nyquist', () => {
    const x = sine(7000, 48000, 1);
    const y = resampleBuffer(x, 48000);
    let e = 0;
    for (let i = 2000; i < y.length; i++) e += y[i] * y[i];
    const rmsOut = Math.sqrt(e / (y.length - 2000));
    expect(rmsOut).toBeLessThan(0.5 / Math.SQRT2 * 0.05); // > 26 dB down
  });
});

describe('pitch detection (tuner)', () => {
  const strings = [40, 45, 50, 55, 59, 64];
  it('finds the open strings of a guitar within 2 cents (Karplus–Strong)', () => {
    const sr = ANALYSIS_RATE;
    for (const m of strings) {
      const f = midiToFreq(m);
      const buf = new Float32Array(sr);
      pluck(buf, 0, f, sr, 0.5, mulberry32(m), { t60: 3 });
      const p = detectPitch(buf.subarray(1500, 1500 + 2048), sr)!;
      expect(p).not.toBeNull();
      expect(Math.abs(1200 * Math.log2(p.freq / f))).toBeLessThan(2);
    }
  });

  it('handles a bright harmonic tone and noise', () => {
    const sr = 48000;
    const f = midiToFreq(45 - 1, 436); // A♭2 at A=436
    const x = harmonicTone(f, sr, 0.5);
    const rng = mulberry32(3);
    for (let i = 0; i < x.length; i++) x[i] += 0.02 * (rng() * 2 - 1);
    const y = decimate(x.subarray(0, 8192), 4);
    const p = detectPitch(y, sr / 4)!;
    expect(Math.abs(1200 * Math.log2(p.freq / f))).toBeLessThan(3);
  });

  it('returns null for silence', () => {
    expect(detectPitch(new Float32Array(2048), ANALYSIS_RATE)).toBeNull();
  });
});

function chromaOf(signal: Float32Array, tuningCents = 0) {
  const fft = new FFT(CHROMA_FFT);
  const mag = new Float32Array(CHROMA_FFT / 2 + 1);
  const chroma = new Float32Array(12), bass = new Float32Array(12);
  const sum = new Float32Array(12), bassSum = new Float32Array(12);
  const est = new TuningEstimator();
  let stacks: (number | null)[] = [];
  for (let s = 0; s + CHROMA_FFT <= signal.length; s += 1024) {
    fft.magnitudes(signal, hann(CHROMA_FFT), mag, s);
    const peaks = findPeaks(mag, CHROMA_BIN_HZ, 40, 4000);
    est.addPeaks(peaks);
    stacks.push(detectLowStack(peaks, tuningCents));
    accumulateChroma(peaks, tuningCents, chroma, bass);
    l2normalize(chroma);
    for (let i = 0; i < 12; i++) { sum[i] += chroma[i]; bassSum[i] += bass[i]; }
  }
  l2normalize(sum);
  return { chroma: sum, bass: bassSum, est, stacks };
}

function strum(midis: number[], refA4: number, seconds = 2.5, seed = 1): Float32Array {
  const sr = ANALYSIS_RATE;
  const buf = new Float32Array(Math.floor(sr * seconds));
  const rng = mulberry32(seed);
  midis.forEach((m, i) => pluck(buf, Math.floor(i * 0.012 * sr), midiToFreq(m, refA4), sr, 0.2, rng, { t60: 3 }));
  return buf;
}

describe('reference pitch estimation', () => {
  for (const cents of [-30, -15, 0, 12, 25]) {
    it(`measures a ${cents}¢ detuned guitar strum within 3¢`, () => {
      const ref = 440 * Math.pow(2, cents / 1200);
      const x = strum([40, 47, 52, 56, 59, 64], ref); // E major open shape
      const { est } = chromaOf(x);
      expect(Math.abs(est.cents - cents)).toBeLessThan(3);
      expect(est.confidence).toBeGreaterThan(0.6);
    });
  }

  it('is not dragged flat by strong 5th/7th harmonics', () => {
    const sr = ANALYSIS_RATE;
    const x = new Float32Array(sr * 2);
    for (const m of [45, 52, 57]) {
      const f = midiToFreq(m);
      for (let h = 1; h <= 8; h++) for (let i = 0; i < x.length; i++) x[i] += (0.25 / Math.sqrt(h)) * Math.sin((2 * Math.PI * f * h * i) / sr);
    }
    const { est } = chromaOf(x);
    expect(Math.abs(est.cents)).toBeLessThan(4);
  });
});

describe('chord recognition on synthetic strums', () => {
  // [label, sounding MIDI notes of a real guitar voicing]
  const cases: [string, number[]][] = [
    ['E', [40, 47, 52, 56, 59, 64]],
    ['Em', [40, 47, 52, 55, 59, 64]],
    ['A', [45, 52, 57, 61, 64]],
    ['Am', [45, 52, 57, 60, 64]],
    ['D', [50, 57, 62, 66]],
    ['Dm', [50, 57, 62, 65]],
    ['G', [43, 47, 50, 55, 59, 67]],
    ['C', [48, 52, 55, 60, 64]],
    ['F', [41, 48, 53, 57, 60, 65]],
    ['Bm', [47, 54, 59, 62, 66]],
    ['E7', [40, 47, 50, 56, 59, 64]],
    ['A7', [45, 52, 55, 61, 64]],
    ['Eb', [39, 46, 51, 55, 58, 63]],
    ['Cm', [48, 55, 60, 63, 67]],
  ];
  for (const detune of [0, -30]) {
    it(`labels ${cases.length} common chords correctly (detune ${detune}¢, tuning-compensated)`, () => {
      const ref = 440 * Math.pow(2, detune / 1200);
      let correct = 0;
      const wrong: string[] = [];
      cases.forEach(([label, notes], i) => {
        const x = strum(notes, ref, 2.5, i + 11);
        const { est } = chromaOf(x);
        const { chroma, bass } = chromaOf(x, est.cents);
        const scores = new Float32Array(NUM_STATES);
        scoreFrame(chroma, bass, true, scores);
        let best = 0;
        for (let s = 1; s < NUM_STATES; s++) if (scores[s] > scores[best]) best = s;
        const got = chordLabel(stateToChord(best), 'flat').replace('Db', 'C#');
        const want = label;
        const norm = (s: string) => s.replace('A#', 'Bb').replace('D#', 'Eb');
        if (norm(got) === norm(want)) correct++; else wrong.push(`${want}→${got}`);
      });
      expect(wrong).toEqual([]);
      expect(correct).toBe(cases.length);
    });
  }

  it('Viterbi turns a noisy frame sequence into clean segments', () => {
    const T = 60;
    const scores: Float32Array[] = [];
    const rng = mulberry32(5);
    for (let t = 0; t < T; t++) {
      const s = new Float32Array(NUM_STATES);
      for (let k = 0; k < NUM_STATES; k++) s[k] = 0.5 + 0.05 * rng();
      const truth = t < 30 ? 0 : 7; // C major then G major
      s[truth] = 0.9;
      if (t === 12) s[5] = 0.95; // one-frame blip
      scores.push(s);
    }
    const segs = pathToSegments(viterbi(scores), scores, 0);
    expect(segs.length).toBe(2);
    expect(chordLabel(segs[0])).toBe('C');
    expect(chordLabel(segs[1])).toBe('G');
  });
});

describe('low power-chord stacks', () => {
  it('finds an E♭2 stack in an E♭-standard "E5" and nothing below E2 for a standard E5', () => {
    const eb = chromaOf(strum([39, 46, 51], 440), 0);
    const e = chromaOf(strum([40, 47, 52], 440), 0);
    const mode = (xs: (number | null)[]) => {
      const c = new Map<number, number>();
      for (const v of xs) if (v !== null) c.set(v, (c.get(v) ?? 0) + 1);
      return [...c.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    };
    expect(mode(eb.stacks)).toBe(39);
    expect(mode(e.stacks)).toBe(40);
  });
});

describe('key detection', () => {
  it('finds E♭ major and G major from chord-tone weighted chroma', () => {
    const add = (acc: number[], pcs: number[], w = 1) => pcs.forEach((p) => (acc[p] += w));
    const eb = new Array(12).fill(0);
    add(eb, [3, 7, 10], 4); add(eb, [8, 0, 3], 2); add(eb, [10, 2, 5], 2); add(eb, [0, 3, 7], 1);
    expect(detectKey(eb)!.label).toBe('Eb major');
    const g = new Array(12).fill(0);
    add(g, [7, 11, 2], 4); add(g, [0, 4, 7], 2); add(g, [2, 6, 9], 2); add(g, [4, 7, 11], 1);
    expect(detectKey(g)!.label).toBe('G major');
  });
});

describe('tempo', () => {
  it('finds 104 BPM from a click-like onset envelope', () => {
    const fps = ANALYSIS_RATE / 256;
    const n = Math.floor(fps * 20);
    const env = new Float32Array(n);
    const period = (60 / 104) * fps;
    for (let b = 0; b * period < n; b++) {
      const i = Math.round(b * period);
      env[i] += 1;
      const half = Math.round(b * period + period / 2);
      if (half < n) env[half] += 0.4;
    }
    const t = estimateTempo(env, fps)!;
    expect(Math.abs(t.bpm - 104)).toBeLessThan(1.5);
  });
});
