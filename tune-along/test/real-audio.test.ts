/**
 * Opt-in evaluation on real recordings (not shipped with the repo — bring your own):
 *   REAL_AUDIO_DIR=/path/to/wavs npx vitest run test/real-audio.test.ts
 * Every 16-bit mono/stereo PCM .wav in the folder is learned once, then 12-second
 * excerpts are replayed through a simulated phone-in-a-room channel (gain change,
 * echo, low-pass, hiss at 8 dB SNR) and must be recognised as the right song at
 * the right position. Prints key / tempo / reference pitch / tuning guesses too.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { AnalysisEngine, type LiveMatch, type SegmentResult } from '../src/engine/engine';
import { FingerprintIndex } from '../src/dsp/fingerprint';
import { chordLabel } from '../src/dsp/chords';
import { mulberry32 } from '../src/audio/synth';
import { createSongFromSegment, type SongRecord } from '../src/lib/songModel';

const DIR = process.env.REAL_AUDIO_DIR;

function readWav(path: string): { pcm: Float32Array; sr: number } {
  const b = readFileSync(path);
  const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  let p = 12, sr = 44100, ch = 1, bits = 16;
  let data: { off: number; len: number } | null = null;
  while (p + 8 <= b.length) {
    const id = b.toString('ascii', p, p + 4);
    const len = v.getUint32(p + 4, true);
    if (id === 'fmt ') { ch = v.getUint16(p + 10, true); sr = v.getUint32(p + 12, true); bits = v.getUint16(p + 22, true); }
    if (id === 'data') { data = { off: p + 8, len }; break; }
    p += 8 + len + (len & 1);
  }
  if (!data || bits !== 16) throw new Error(`${path}: need 16-bit PCM wav`);
  const frames = Math.floor(data.len / 2 / ch);
  const pcm = new Float32Array(frames);
  for (let i = 0; i < frames; i++) {
    let s = 0;
    for (let c = 0; c < ch; c++) s += v.getInt16(data.off + (i * ch + c) * 2, true);
    pcm[i] = s / ch / 32768;
  }
  return { pcm, sr };
}

function degrade(x: Float32Array, sr: number, snrDb: number, seed: number): Float32Array {
  const out = new Float32Array(x.length);
  const d = Math.floor(0.029 * sr);
  const a = 1 - Math.exp((-2 * Math.PI * 3000) / sr); // ~3 kHz low-pass, like a cheap mic
  let lp = 0, e = 0;
  for (let i = 0; i < x.length; i++) {
    lp += a * (0.4 * x[i] + (i >= d ? 0.2 * x[i - d] : 0) - lp);
    out[i] = lp;
    e += lp * lp;
  }
  const noise = Math.sqrt(e / x.length) / Math.pow(10, snrDb / 20);
  const rng = mulberry32(seed);
  for (let i = 0; i < out.length; i++) out[i] += noise * Math.sqrt(3) * (rng() * 2 - 1);
  return out;
}

function feed(e: AnalysisEngine, x: Float32Array): void {
  for (let i = 0; i < x.length; i += 2048) e.pushAudio(x.subarray(i, i + 2048));
}

describe.skipIf(!DIR)('real recordings', () => {
  it('learns each recording and recognises degraded excerpts', () => {
    const files = readdirSync(DIR!).filter((f) => f.toLowerCase().endsWith('.wav')).sort();
    expect(files.length).toBeGreaterThan(0);
    const songs: { name: string; song: SongRecord; seg: SegmentResult; pcm: Float32Array; sr: number }[] = [];
    for (const f of files) {
      const { pcm, sr } = readWav(join(DIR!, f));
      const segs: SegmentResult[] = [];
      const e = new AnalysisEngine(sr, { onSegment: (s) => segs.push(s) }, { minSongSec: 8 });
      feed(e, pcm);
      const last = e.stop();
      const all = last && !segs.includes(last) ? [...segs, last] : segs;
      const seg = all.sort((a, b) => b.duration - a.duration)[0];
      const song = createSongFromSegment(seg, { source: 'file', title: f });
      songs.push({ name: f, song, seg, pcm, sr });
      const top = seg.tuning.candidates[0];
      console.log(
        `${f}: ${seg.duration.toFixed(0)} s learned (${all.length} segment${all.length === 1 ? '' : 's'}), key ${seg.key?.label}, ` +
          `${seg.bpm} BPM, A=${seg.tuning.refHz.toFixed(1)} Hz (${seg.tuning.cents.toFixed(1)}¢, conf ${seg.tuning.centsConfidence.toFixed(2)}), ` +
          `tuning ${top.id} ${(top.probability * 100).toFixed(0)}%, ${seg.fp.hashes.length} hashes\n   chords: ` +
          seg.chords.filter((c) => c.end - c.start > 0.5).slice(0, 16).map((c) => chordLabel(c, 'common')).join(' '),
      );
    }
    const index = new FingerprintIndex();
    index.build(songs.map((s) => ({ id: s.song.id, fp: s.song.fp })));
    let tried = 0, right = 0, exact = 0, wrongSong = 0;
    const latencies: number[] = [];
    for (const [si, s] of songs.entries()) {
      const dur = s.pcm.length / s.sr;
      for (const start of [8, 25, 45, 70, 100]) {
        if (start + 12 > dur - 1) continue;
        tried++;
        const clip = degrade(s.pcm.subarray(Math.floor(start * s.sr), Math.floor((start + 12) * s.sr)), s.sr, 8, si * 100 + start);
        const hit: { v: { m: LiveMatch; now: number } | null } = { v: null };
        const e = new AnalysisEngine(s.sr, { onMatch: (m, now) => { if (m && !hit.v) hit.v = { m, now }; } });
        e.setIndex(index);
        feed(e, clip);
        const final = e.currentMatch;
        const first = hit.v;
        if (!first) { console.log(`  ${s.name} @${start}s: not recognised`); continue; }
        if (first.m.songId !== s.song.id) { wrongSong++; console.log(`  ${s.name} @${start}s: WRONG SONG`); continue; }
        right++;
        latencies.push(first.now);
        const truth = start - s.seg.sessionStart;
        const err = Math.abs((final ?? first.m).offsetSec - truth);
        if (err < 0.15) exact++;
        console.log(`  ${s.name} @${start}s: recognised after ${first.now.toFixed(1)} s, position error ${err.toFixed(2)} s`);
      }
    }
    latencies.sort((a, b) => a - b);
    console.log(`\nrecognised ${right}/${tried} (exact position ${exact}/${tried}), wrong-song ${wrongSong}, median latency ${latencies[Math.floor(latencies.length / 2)]?.toFixed(1)} s`);
    // songs that are NOT in the library must not be "recognised" as something else
    let falsePositives = 0;
    for (const s of songs) {
      const others = new FingerprintIndex();
      others.build(songs.filter((o) => o !== s).map((o) => ({ id: o.song.id, fp: o.song.fp })));
      const clip = degrade(s.pcm.subarray(Math.floor(5 * s.sr), Math.floor(35 * s.sr)), s.sr, 15, 7);
      let fp = false;
      const e = new AnalysisEngine(s.sr, { onMatch: (m) => { if (m) fp = true; } });
      e.setIndex(others);
      feed(e, clip);
      if (fp) falsePositives++;
    }
    console.log(`unknown-song false positives: ${falsePositives}/${songs.length}`);
    expect(falsePositives).toBe(0);
    expect(wrongSong).toBe(0);
    expect(right / tried).toBeGreaterThan(0.8);
  });
});
