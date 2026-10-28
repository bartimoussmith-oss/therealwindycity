/**
 * Two original demo songs (written for TuneAlong — no third-party rights involved).
 *  - "Windy City Shuffle": E♭ major, guitars tuned ½ step down, record pitched
 *    15 cents flat (A ≈ 436 Hz) — exercises the tuning detector.
 *  - "Prairie Waltz": G major, 3/4, standard tuning at A440 — a second, different
 *    song so you can see TuneAlong keep songs apart.
 */
import { mod12, parseNote } from '../dsp/notes';
import type { BarSpec, SongSpec } from './synth';

// Guitar voicings, sounding MIDI notes, lowest string first.
const EB_TUNING = {
  Eb: [39, 46, 51, 55, 58, 63], // "E" shape in E♭ standard
  Eb5: [39, 46, 51], // "E5" power chord
  Ab: [44, 51, 56, 60, 63], // "A" shape
  Bb: [46, 53, 58, 62, 65], // "B" barre shape
  Cm: [48, 55, 60, 63, 67], // "C#m" barre shape
} as Record<string, number[]>;
const EB_BASS: Record<string, number> = { Eb: 27, Eb5: 27, Ab: 32, Bb: 34, Cm: 36 };

const STD_TUNING = {
  G: [43, 47, 50, 55, 59, 67],
  C: [48, 52, 55, 60, 64],
  D: [50, 57, 62, 66],
  D7: [50, 57, 60, 66],
  Em: [40, 47, 52, 55, 59, 64],
  Am: [45, 52, 57, 60, 64],
} as Record<string, number[]>;
const STD_BASS: Record<string, number> = { G: 31, C: 36, D: 38, D7: 38, Em: 40, Am: 33 };

function chordPcs(chord: string): number[] {
  const m = /^([A-G][b#]?)(m|5|7)?$/.exec(chord);
  if (!m) return [0];
  const root = parseNote(m[1])!.pc;
  const ivs = m[2] === 'm' ? [0, 3, 7] : m[2] === '5' ? [0, 7] : m[2] === '7' ? [0, 4, 7, 10] : [0, 4, 7];
  return ivs.map((i) => mod12(root + i));
}

/** Deterministic, singable-ish melody built from chord tones. */
function melodyFor(chord: string, rhythm: [number, number][], lo: number, hi: number, startFrom: number): { notes: [number, number, number][]; last: number } {
  const pcs = chordPcs(chord);
  const pool: number[] = [];
  for (let m = lo; m <= hi; m++) if (pcs.includes(mod12(m))) pool.push(m);
  let cur = startFrom;
  const notes: [number, number, number][] = [];
  rhythm.forEach(([beat, len], i) => {
    // alternate stepping up and down through the chord tones nearest the previous note
    const sorted = [...pool].sort((a, b) => Math.abs(a - cur) - Math.abs(b - cur));
    const pick = sorted[Math.min(sorted.length - 1, i % 2 === 0 ? 0 : 1)];
    notes.push([beat, len, pick]);
    cur = pick;
  });
  return { notes, last: cur };
}

function shuffleBars(): BarSpec[] {
  const intro = ['Eb5', 'Eb5', 'Ab', 'Bb'];
  const verse = ['Eb', 'Eb', 'Ab', 'Eb', 'Cm', 'Ab', 'Bb', 'Bb'];
  const chorus = ['Ab', 'Bb', 'Eb', 'Cm', 'Ab', 'Bb', 'Eb', 'Eb'];
  const outro = ['Eb', 'Eb'];
  const bars: BarSpec[] = [];
  let last = 67;
  const add = (chord: string, style: BarSpec['style'], sing: 'verse' | 'chorus' | null) => {
    let melody: [number, number, number][] | undefined;
    if (sing) {
      const rhythm: [number, number][] = sing === 'verse' ? [[0, 1.5], [1.5, 0.5], [2, 1], [3, 1]] : [[0, 2], [2, 1], [3, 1]];
      const m = melodyFor(chord, rhythm, 63, 75, last);
      melody = m.notes;
      last = m.last;
    }
    bars.push({ chord, voicing: EB_TUNING[chord], bass: EB_BASS[chord], style, melody });
  };
  intro.forEach((c) => add(c, c === 'Eb5' ? 'chug' : 'strum', null));
  verse.forEach((c) => add(c, 'strum', 'verse'));
  chorus.forEach((c) => add(c, 'strum', 'chorus'));
  verse.forEach((c) => add(c, 'strum', 'verse'));
  chorus.forEach((c) => add(c, 'strum', 'chorus'));
  outro.forEach((c, i) => add(c, i === outro.length - 1 ? 'ring' : 'strum', null));
  return bars;
}

const CHORUS_LINES = [
  'Tune along, play along',
  'Hear it once and you know where it goes',
  'Tune along, play along',
  'Every chord the city ever wrote',
];

export const WINDY_CITY_SHUFFLE: SongSpec = {
  id: 'demo-windy-city-shuffle',
  title: 'Windy City Shuffle',
  artist: 'TuneAlong House Band (demo)',
  bpm: 104,
  beatsPerBar: 4,
  refCents: -15,
  leadIn: 0.6,
  bars: shuffleBars(),
  seed: 1871,
  truth: { key: 'Eb major', tuningId: 'half-down' },
  lyrics: [
    { bar: 4, beat: 0, text: 'Wind comes off the lake at dawn' },
    { bar: 6, beat: 0, text: 'Rattles every window on the avenue' },
    { bar: 8, beat: 0, text: "Coffee's cold, the train is gone" },
    { bar: 10, beat: 0, text: 'Still I got this song to see me through' },
    ...CHORUS_LINES.map((text, i) => ({ bar: 12 + i * 2, beat: 0, text })),
    { bar: 20, beat: 0, text: 'Neon hums on Halsted Street' },
    { bar: 22, beat: 0, text: "Somebody's busking with a busted string" },
    { bar: 24, beat: 0, text: 'Half a step down, keep the beat' },
    { bar: 26, beat: 0, text: 'Tune it low and let the bottom ring' },
    ...CHORUS_LINES.map((text, i) => ({ bar: 28 + i * 2, beat: 0, text })),
  ],
};

function waltzBars(): BarSpec[] {
  const two = (cs: string[]) => cs.flatMap((c) => [c, c]);
  const intro = two(['G', 'D']);
  const a = two(['G', 'C', 'G', 'D', 'G', 'C', 'D', 'G']);
  const b = two(['Em', 'C', 'G', 'D', 'Em', 'C', 'D7', 'G']);
  const bars: BarSpec[] = [];
  let last = 71;
  const add = (chord: string, sing: boolean, i: number) => {
    let melody: [number, number, number][] | undefined;
    if (sing) {
      const rhythm: [number, number][] = i % 2 === 0 ? [[0, 2], [2, 1]] : [[0, 3]];
      const m = melodyFor(chord, rhythm, 62, 76, last);
      melody = m.notes;
      last = m.last;
    }
    bars.push({ chord, voicing: STD_TUNING[chord], bass: STD_BASS[chord], style: 'waltz', melody });
  };
  intro.forEach((c, i) => add(c, false, i));
  a.forEach((c, i) => add(c, true, i));
  b.forEach((c, i) => add(c, true, i));
  a.forEach((c, i) => add(c, true, i));
  return bars;
}

export const PRAIRIE_WALTZ: SongSpec = {
  id: 'demo-prairie-waltz',
  title: 'Prairie Waltz',
  artist: 'TuneAlong House Band (demo)',
  bpm: 132,
  beatsPerBar: 3,
  refCents: 0,
  leadIn: 0.5,
  bars: waltzBars(),
  seed: 1890,
  truth: { key: 'G major', tuningId: 'standard' },
  lyrics: [
    { bar: 4, beat: 0, text: 'Out where the wheat meets the sky' },
    { bar: 8, beat: 0, text: 'Cheyenne lights in the rearview' },
    { bar: 12, beat: 0, text: 'Three-quarter time on the county line' },
    { bar: 16, beat: 0, text: 'Turning the radio up for you' },
    { bar: 20, beat: 0, text: 'Hear how the fiddle would go' },
    { bar: 24, beat: 0, text: 'If we had a fiddle tonight' },
    { bar: 28, beat: 0, text: 'Hum it once, the app will know' },
    { bar: 32, beat: 0, text: 'Every chord from left to right' },
    { bar: 36, beat: 0, text: 'Out where the wheat meets the sky' },
    { bar: 40, beat: 0, text: 'Cheyenne lights in the rearview' },
    { bar: 44, beat: 0, text: 'Three-quarter time on the county line' },
    { bar: 48, beat: 0, text: 'Turning the radio up for you' },
  ],
};

export const DEMO_SONGS: SongSpec[] = [WINDY_CITY_SHUFFLE, PRAIRIE_WALTZ];
