/** Key detection (Krumhansl–Kessler profiles correlated with the song's chroma). */
import { pcName, spellingForKey } from './notes';

const MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88];
const MINOR = [6.33, 2.68, 3.52, 5.38, 2.6, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17];

export interface KeyResult {
  tonic: number;
  mode: 'major' | 'minor';
  label: string;
  /** Pearson correlation of the winning profile (−1..1). */
  correlation: number;
  /** Margin over the runner-up (0..~0.3). */
  confidence: number;
}

function pearson(a: ArrayLike<number>, b: ArrayLike<number>, rot: number): number {
  let ma = 0, mb = 0;
  for (let i = 0; i < 12; i++) { ma += a[i]; mb += b[i]; }
  ma /= 12; mb /= 12;
  let num = 0, da = 0, db = 0;
  for (let i = 0; i < 12; i++) {
    const x = a[(i + rot) % 12] - ma;
    const y = b[i] - mb;
    num += x * y; da += x * x; db += y * y;
  }
  return da > 0 && db > 0 ? num / Math.sqrt(da * db) : 0;
}

export function keyLabel(tonic: number, mode: 'major' | 'minor'): string {
  const sp = spellingForKey(tonic, mode);
  return `${pcName(tonic, sp === 'common' ? 'common' : sp)} ${mode}`;
}

export function detectKey(chromaSum: ArrayLike<number>): KeyResult | null {
  let total = 0;
  for (let i = 0; i < 12; i++) total += chromaSum[i];
  if (!(total > 0)) return null;
  const results: { tonic: number; mode: 'major' | 'minor'; r: number }[] = [];
  for (let tonic = 0; tonic < 12; tonic++) {
    results.push({ tonic, mode: 'major', r: pearson(chromaSum, MAJOR, tonic) });
    results.push({ tonic, mode: 'minor', r: pearson(chromaSum, MINOR, tonic) });
  }
  results.sort((x, y) => y.r - x.r);
  const best = results[0];
  return {
    tonic: best.tonic,
    mode: best.mode,
    label: keyLabel(best.tonic, best.mode),
    correlation: best.r,
    confidence: best.r - results[1].r,
  };
}
