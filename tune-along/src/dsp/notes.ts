/** Note names, MIDI/frequency conversion and enharmonic spelling. */

export const SHARP_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'] as const;
export const FLAT_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'] as const;
/** What most chord charts print when the key is unknown. */
export const COMMON_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'] as const;

export type Spelling = 'sharp' | 'flat' | 'common';

export function mod12(n: number): number {
  return ((Math.round(n) % 12) + 12) % 12;
}

export function freqToMidi(freq: number, refA4 = 440): number {
  return 69 + 12 * Math.log2(freq / refA4);
}

export function midiToFreq(midi: number, refA4 = 440): number {
  return refA4 * Math.pow(2, (midi - 69) / 12);
}

export function centsOff(freq: number, targetFreq: number): number {
  return 1200 * Math.log2(freq / targetFreq);
}

export function pcName(pc: number, spelling: Spelling = 'common'): string {
  const names = spelling === 'sharp' ? SHARP_NAMES : spelling === 'flat' ? FLAT_NAMES : COMMON_NAMES;
  return names[mod12(pc)];
}

export function midiName(midi: number, spelling: Spelling = 'common'): string {
  const m = Math.round(midi);
  return `${pcName(m, spelling)}${Math.floor(m / 12) - 1}`;
}

/** Parses "C", "F#", "Bb", "Eb3" → pitch class (and octave if present). */
export function parseNote(name: string): { pc: number; octave?: number } | null {
  const m = /^([A-Ga-g])([#b♯♭]?)(-?\d+)?$/.exec(name.trim());
  if (!m) return null;
  const base: Record<string, number> = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  let pc = base[m[1].toUpperCase()];
  if (m[2] === '#' || m[2] === '♯') pc += 1;
  if (m[2] === 'b' || m[2] === '♭') pc -= 1;
  return { pc: mod12(pc), octave: m[3] !== undefined ? Number(m[3]) : undefined };
}

// Keys whose signatures use flats (major tonic pcs / minor tonic pcs).
const FLAT_MAJOR = new Set([5, 10, 3, 8, 1, 6]); // F Bb Eb Ab Db Gb
const FLAT_MINOR = new Set([2, 7, 0, 5, 10, 3]); // Dm Gm Cm Fm Bbm Ebm

export function spellingForKey(tonic: number | null | undefined, mode: 'major' | 'minor' | null | undefined): Spelling {
  if (tonic == null || mode == null) return 'common';
  const pc = mod12(tonic);
  if (mode === 'major') return FLAT_MAJOR.has(pc) ? 'flat' : pc === 0 ? 'common' : 'sharp';
  return FLAT_MINOR.has(pc) ? 'flat' : pc === 9 ? 'common' : 'sharp';
}
