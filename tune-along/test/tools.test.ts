/**
 * Developer utility, skipped unless asked for:
 *   WRITE_DEMO_WAV=/tmp/demo.wav npx vitest run test/tools.test.ts
 * renders the demo song(s) to 16-bit WAV files — handy for testing the microphone
 * path with a real speaker and phone, or with Chrome's fake-microphone flag.
 * Set DEMO_WAV_DEGRADE=1 to add room echo, low-pass and hiss.
 */
import { writeFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { DEMO_SONGS } from '../src/audio/demoSongs';
import { mulberry32, renderSong } from '../src/audio/synth';

function wav(pcm: Float32Array, sr: number): Uint8Array {
  const out = new Uint8Array(44 + pcm.length * 2);
  const v = new DataView(out.buffer);
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + pcm.length * 2, true); str(8, 'WAVE');
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, 'data'); v.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, pcm[i])) * 32767, true);
  return out;
}

const target = process.env.WRITE_DEMO_WAV;

describe('tools', () => {
  it.skipIf(!target)('renders the demo songs to WAV', () => {
    const sr = 48000;
    DEMO_SONGS.forEach((spec, i) => {
      let pcm = renderSong(spec, sr);
      if (process.env.DEMO_WAV_DEGRADE) {
        const rng = mulberry32(42 + i);
        const d = Math.floor(0.027 * sr);
        const out = new Float32Array(pcm.length);
        let lp = 0;
        for (let k = 0; k < pcm.length; k++) {
          const x = 0.5 * pcm[k] + (k >= d ? 0.22 * pcm[k - d] : 0);
          lp += 0.3 * (x - lp);
          out[k] = lp + 0.01 * (rng() * 2 - 1);
        }
        pcm = out;
      }
      // a little silence after, so a looping fake mic leaves a gap between plays
      const padded = new Float32Array(pcm.length + sr * 4);
      padded.set(pcm);
      const path = i === 0 ? target! : target!.replace(/\.wav$/, `-${spec.id}.wav`);
      writeFileSync(path, wav(padded, sr));
      expect(padded.length).toBeGreaterThan(sr * 30);
    });
  });
});
