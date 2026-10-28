/**
 * End-to-end: the built-in demo song goes through the real engine exactly as the
 * app feeds it (chunked audio at a device sample rate). Checks the musician-facing
 * output against the song's ground truth, then checks that a degraded, partial
 * replay is recognised at the right position, and that a different song is not.
 */
import { beforeAll, describe, expect, it } from 'vitest';
import { AnalysisEngine, type LiveMatch, type SegmentResult } from '../src/engine/engine';
import { FingerprintIndex } from '../src/dsp/fingerprint';
import { chordAt, chordLabel } from '../src/dsp/chords';
import { parseNote } from '../src/dsp/notes';
import { renderSong, truthChords, mulberry32 } from '../src/audio/synth';
import { PRAIRIE_WALTZ, WINDY_CITY_SHUFFLE } from '../src/audio/demoSongs';
import { createSongFromSegment, mergeSegmentIntoSong, exportSongs, importSongs, type SongRecord } from '../src/lib/songModel';

const SR = 44100;

function feed(engine: AnalysisEngine, audio: Float32Array, chunk = 2048): void {
  for (let i = 0; i < audio.length; i += chunk) engine.pushAudio(audio.subarray(i, Math.min(audio.length, i + chunk)));
}

function withSilence(audio: Float32Array, sr: number, before: number, after: number): Float32Array {
  const out = new Float32Array(audio.length + Math.floor((before + after) * sr));
  out.set(audio, Math.floor(before * sr));
  return out;
}

/** Phone-in-a-room simulation: gain change, low-pass, early reflection, hiss. */
function degrade(audio: Float32Array, sr: number, snrDb: number, seed: number): Float32Array {
  const out = new Float32Array(audio.length);
  const d = Math.floor(0.031 * sr);
  let lp = 0, sig = 0;
  for (let i = 0; i < audio.length; i++) {
    const x = 0.45 * audio[i] + (i >= d ? 0.25 * audio[i - d] : 0);
    lp += 0.35 * (x - lp);
    out[i] = lp;
    sig += lp * lp;
  }
  const rmsSig = Math.sqrt(sig / audio.length);
  const noise = rmsSig / Math.pow(10, snrDb / 20);
  const rng = mulberry32(seed);
  for (let i = 0; i < out.length; i++) out[i] += noise * Math.sqrt(3) * (rng() * 2 - 1);
  return out;
}

function chordName(label: string): { root: number; minor: boolean; power: boolean } {
  const m = /^([A-G][b#]?)(.*)$/.exec(label)!;
  return { root: parseNote(m[1])!.pc, minor: m[2].startsWith('m') && !m[2].startsWith('maj'), power: m[2] === '5' };
}

function scoreChords(result: SegmentResult, spec: typeof WINDY_CITY_SHUFFLE, sessionStart: number) {
  const truth = truthChords(spec);
  let strict = 0, majmin = 0, total = 0;
  const misses: string[] = [];
  for (const bar of truth) {
    // sample 4 points inside each bar (song time = file time − sessionStart)
    for (const f of [0.2, 0.4, 0.6, 0.8]) {
      const t = bar.start + f * (bar.end - bar.start) - sessionStart;
      const idx = chordAt(result.chords, t);
      total++;
      if (idx < 0) { misses.push(`${bar.chord}@${t.toFixed(1)}→none`); continue; }
      const got = result.chords[idx];
      const gotLabel = chordLabel(got, 'flat');
      const want = chordName(bar.chord);
      const g = chordName(gotLabel);
      const sameRoot = g.root === want.root;
      const qualityOk = want.power ? !g.minor : g.minor === want.minor && !g.power;
      if (sameRoot && (want.power || qualityOk)) majmin++;
      else misses.push(`${bar.chord}@${t.toFixed(1)}→${gotLabel}`);
      if (gotLabel === bar.chord || (want.power && sameRoot && (gotLabel === bar.chord.replace('5', '') || gotLabel === bar.chord))) strict++;
    }
  }
  return { strict: strict / total, majmin: majmin / total, misses };
}

describe('learn → recognise, end to end', () => {
  let shuffle: Float32Array;
  let learned: SegmentResult;
  let song: SongRecord;
  let index: FingerprintIndex;
  let renderMs = 0, analyseMs = 0;

  beforeAll(() => {
    let t = performance.now();
    shuffle = renderSong(WINDY_CITY_SHUFFLE, SR);
    renderMs = performance.now() - t;
    const segments: SegmentResult[] = [];
    const engine = new AnalysisEngine(SR, { onSegment: (s) => segments.push(s) });
    t = performance.now();
    feed(engine, withSilence(shuffle, SR, 0, 4));
    analyseMs = performance.now() - t;
    expect(segments.length).toBe(1);
    learned = segments[0];
    song = createSongFromSegment(learned, { source: 'demo', title: 'Windy City Shuffle' });
    index = new FingerprintIndex();
    index.build([{ id: song.id, fp: song.fp }]);
  });

  it('runs faster than real time', () => {
    const seconds = shuffle.length / SR;
    console.log(`render ${renderMs.toFixed(0)} ms, analyse ${analyseMs.toFixed(0)} ms for ${seconds.toFixed(1)} s of audio`);
    expect(analyseMs / 1000).toBeLessThan(seconds / 5);
  });

  it('segments the song from silence to silence', () => {
    expect(learned.sessionStart).toBeGreaterThan(0.3);
    expect(learned.sessionStart).toBeLessThan(1.2);
    const expected = WINDY_CITY_SHUFFLE.bars.length * (60 / WINDY_CITY_SHUFFLE.bpm) * 4;
    expect(learned.duration).toBeGreaterThan(expected - 1);
    expect(learned.duration).toBeLessThan(expected + 5);
  });

  it('writes down the chords', () => {
    const s = scoreChords(learned, WINDY_CITY_SHUFFLE, learned.sessionStart);
    console.log(`chord accuracy: major/minor ${(s.majmin * 100).toFixed(1)}%, strict ${(s.strict * 100).toFixed(1)}%`, s.misses.slice(0, 12));
    console.log(learned.chords.slice(0, 14).map((c) => `${chordLabel(c, 'flat')}@${c.start.toFixed(1)}`).join(' '));
    expect(s.majmin).toBeGreaterThan(0.85);
  });

  it('finds the key, tempo, reference pitch and guitar tuning', () => {
    console.log('key', learned.key, 'bpm', learned.bpm, 'tuning', learned.tuning.cents.toFixed(1), learned.tuning.candidates.slice(0, 3), learned.tuning.reasons);
    expect(learned.key?.label).toBe('Eb major');
    expect(Math.abs(learned.tuning.cents - WINDY_CITY_SHUFFLE.refCents)).toBeLessThan(4);
    expect(learned.tuning.refHz).toBeGreaterThan(434);
    expect(learned.tuning.refHz).toBeLessThan(438.5);
    expect(learned.tuning.candidates[0].id).toBe('half-down');
    expect(learned.tuning.candidates[0].probability).toBeGreaterThan(0.6);
    expect(learned.bpm).not.toBeNull();
    expect(Math.abs(learned.bpm! - 104) / 104).toBeLessThan(0.03);
  });

  /** Is the matched position musically right? (same chord as the truth at each moment) */
  function positionAgrees(offsetSec: number, fileStart: number, fromSession: number, toSession: number): number {
    const truth = truthChords(WINDY_CITY_SHUFFLE);
    let ok = 0, n = 0;
    for (let ts = fromSession; ts < toSession; ts += 0.5) {
      const fileT = fileStart + ts;
      const bar = truth.find((b) => fileT >= b.start + 0.25 && fileT < b.end - 0.25);
      if (!bar) continue;
      const idx = chordAt(song.chords, ts + offsetSec);
      n++;
      if (idx >= 0) {
        const got = chordName(chordLabel(song.chords[idx], 'flat'));
        const want = chordName(bar.chord);
        if (got.root === want.root && (want.power || got.minor === want.minor)) ok++;
      }
    }
    return n ? ok / n : 0;
  }

  it('recognises a noisy phone-mic replay that starts 30 s in, at a musically correct position', () => {
    const start = 30, len = 15;
    const clip = degrade(shuffle.subarray(start * SR, (start + len) * SR), SR, 8, 99);
    const matches: { m: LiveMatch | null; now: number }[] = [];
    const engine = new AnalysisEngine(SR, { onMatch: (m, now) => matches.push({ m, now }) });
    engine.setIndex(index);
    feed(engine, clip);
    const first = matches.find((x) => x.m);
    expect(first).toBeTruthy();
    console.log(`recognised after ${first!.now.toFixed(1)} s of audio, score ${first!.m!.score}, offset ${first!.m!.offsetSec.toFixed(2)} (true ${(start - learned.sessionStart).toFixed(2)})`);
    expect(first!.now).toBeLessThan(7);
    expect(first!.m!.songId).toBe(song.id);
    const final = engine.currentMatch!;
    expect(final.songId).toBe(song.id);
    const agree = positionAgrees(final.offsetSec, start, first!.now, len);
    expect(agree).toBeGreaterThan(0.9);
  });

  it('settles on the exact position once the music stops repeating', () => {
    // 40 s → 58 s: end of chorus 1 into verse 2. Chorus 2 sounds the same but is
    // followed by the outro, so the true position wins once the verse starts.
    const start = 40, len = 18;
    const clip = degrade(shuffle.subarray(start * SR, (start + len) * SR), SR, 10, 21);
    const engine = new AnalysisEngine(SR, {});
    engine.setIndex(index);
    feed(engine, clip);
    const m = engine.currentMatch!;
    expect(m).toBeTruthy();
    expect(Math.abs(m.offsetSec - (start - learned.sessionStart))).toBeLessThan(0.1);
  });

  it('recognises audio captured at a different device sample rate (48 kHz)', () => {
    const at48 = renderSong(WINDY_CITY_SHUFFLE, 48000);
    const start = 50, len = 12;
    const clip = degrade(at48.subarray(start * 48000, (start + len) * 48000), 48000, 12, 5);
    let hit: { m: LiveMatch; now: number } | null = null;
    const engine = new AnalysisEngine(48000, { onMatch: (m, now) => { if (m && !hit) hit = { m, now }; } });
    engine.setIndex(index);
    feed(engine, clip, 4096);
    expect(hit).toBeTruthy();
    const final = engine.currentMatch!;
    expect(final.songId).toBe(song.id);
    expect(positionAgrees(final.offsetSec, start, hit!.now, len)).toBeGreaterThan(0.9);
  });

  it('does not claim a different song', () => {
    const waltz = renderSong(PRAIRIE_WALTZ, SR);
    const clip = degrade(waltz.subarray(10 * SR, 40 * SR), SR, 15, 7);
    const hits: LiveMatch[] = [];
    const segments: SegmentResult[] = [];
    const engine = new AnalysisEngine(SR, { onMatch: (m) => { if (m) hits.push(m); }, onSegment: (s) => segments.push(s) });
    engine.setIndex(index);
    feed(engine, clip);
    const seg = engine.stop();
    expect(hits).toEqual([]);
    expect(seg?.match ?? null).toBeNull();
    expect(seg?.key?.label).toBe('G major');
    expect(seg?.tuning.candidates[0].id).toBe('standard');
  });

  it('merges a later listen and fills in the part it missed the first time', () => {
    // learn only from 25 s onward…
    const segs: SegmentResult[] = [];
    const e1 = new AnalysisEngine(SR, { onSegment: (s) => segs.push(s) });
    feed(e1, withSilence(shuffle.subarray(25 * SR), SR, 0.5, 4));
    expect(segs.length).toBe(1);
    let partial = createSongFromSegment(segs[0], { source: 'mic' });
    const idx = new FingerprintIndex();
    idx.build([{ id: partial.id, fp: partial.fp }]);
    // …then hear the whole song: recognised once playback reaches the known part
    const segs2: SegmentResult[] = [];
    const e2 = new AnalysisEngine(SR, { onSegment: (s) => segs2.push(s) });
    e2.setIndex(idx);
    feed(e2, withSilence(shuffle, SR, 0.5, 4));
    expect(segs2.length).toBe(1);
    expect(segs2[0].match?.songId).toBe(partial.id);
    const before = partial.duration;
    partial = mergeSegmentIntoSong(partial, segs2[0], [], Date.now());
    console.log(`duration before merge ${before.toFixed(1)} s → after ${partial.duration.toFixed(1)} s, listens ${partial.listens}`);
    expect(partial.duration).toBeGreaterThan(before + 20);
    expect(partial.listens).toBe(2);
    expect(partial.key?.label).toBe('Eb major');
    // chords now exist for the intro/verse that were missed the first time
    const early = partial.chords.filter((c) => c.end < 22 && c.type !== 'N');
    expect(early.length).toBeGreaterThan(4);
    // and the merged song is still recognisable from its (new) beginning
    const idx2 = new FingerprintIndex();
    idx2.build([{ id: partial.id, fp: partial.fp }]);
    let hit: LiveMatch | null = null;
    const e3 = new AnalysisEngine(SR, { onMatch: (m) => { if (m && !hit) hit = m; } });
    e3.setIndex(idx2);
    feed(e3, degrade(shuffle.subarray(5 * SR, 17 * SR), SR, 10, 3));
    expect(hit).toBeTruthy();
  });

  it('exports and re-imports a song losslessly', () => {
    const json = exportSongs([song]);
    const [back] = importSongs(json);
    expect(back.id).toBe(song.id);
    expect(back.fp.hashes).toEqual(song.fp.hashes);
    expect(back.chroma.length).toBe(song.chroma.length);
    expect(back.chroma[123]).toBeCloseTo(song.chroma[123], 6);
    expect(back.chords).toEqual(song.chords);
    console.log(`export size ${(json.length / 1024).toFixed(0)} KB for ${song.duration.toFixed(0)} s`);
  });
});
