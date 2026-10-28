/**
 * Instrument tunings, the "what is this song tuned to?" estimator, and capo advice.
 *
 * Two different things get called "tuning" by players and both matter:
 *  1. Reference pitch — is the record at A = 440 Hz, or (old tape, deliberate
 *     choice) at 432/436/445 Hz? Measured directly from the audio.
 *  2. Guitar tuning — standard, ½-step down, drop D… This cannot be measured
 *     with certainty from a mixed recording, so it is inferred from evidence
 *     (power-chord stacks below low E, which chords are easy in which tuning)
 *     and reported as ranked probabilities, never as fact.
 */
import { chordTones, type ChordSegment } from './chords';
import { midiName, midiToFreq, mod12 } from './notes';

export interface TuningPreset {
  id: string;
  name: string;
  short: string;
  /** Open-string MIDI notes, lowest string first. */
  strings: number[];
  instrument: 'guitar' | 'bass' | 'ukulele';
  /** For standard-family/drop tunings: semitones below E standard (shapes = sounding + down). */
  down?: number;
  drop?: boolean;
}

export const TUNINGS: TuningPreset[] = [
  { id: 'standard', name: 'Standard (E A D G B E)', short: 'Standard', strings: [40, 45, 50, 55, 59, 64], instrument: 'guitar', down: 0 },
  { id: 'half-down', name: 'Eb Standard (½ step down)', short: 'Eb Standard', strings: [39, 44, 49, 54, 58, 63], instrument: 'guitar', down: 1 },
  { id: 'whole-down', name: 'D Standard (whole step down)', short: 'D Standard', strings: [38, 43, 48, 53, 57, 62], instrument: 'guitar', down: 2 },
  { id: 'c-sharp-std', name: 'C# Standard (1½ steps down)', short: 'C# Standard', strings: [37, 42, 47, 52, 56, 61], instrument: 'guitar', down: 3 },
  { id: 'c-std', name: 'C Standard (2 steps down)', short: 'C Standard', strings: [36, 41, 46, 51, 55, 60], instrument: 'guitar', down: 4 },
  { id: 'b-std', name: 'B Standard (2½ steps down)', short: 'B Standard', strings: [35, 40, 45, 50, 54, 59], instrument: 'guitar', down: 5 },
  { id: 'drop-d', name: 'Drop D (D A D G B E)', short: 'Drop D', strings: [38, 45, 50, 55, 59, 64], instrument: 'guitar', down: 0, drop: true },
  { id: 'drop-c-sharp', name: 'Drop C# (C# G# C# F# A# D#)', short: 'Drop C#', strings: [37, 44, 49, 54, 58, 63], instrument: 'guitar', down: 1, drop: true },
  { id: 'drop-c', name: 'Drop C (C G C F A D)', short: 'Drop C', strings: [36, 43, 48, 53, 57, 62], instrument: 'guitar', down: 2, drop: true },
  { id: 'drop-b', name: 'Drop B (B F# B E G# C#)', short: 'Drop B', strings: [35, 42, 47, 52, 56, 61], instrument: 'guitar', down: 3, drop: true },
  { id: 'dadgad', name: 'DADGAD', short: 'DADGAD', strings: [38, 45, 50, 55, 57, 62], instrument: 'guitar' },
  { id: 'open-g', name: 'Open G (D G D G B D)', short: 'Open G', strings: [38, 43, 50, 55, 59, 62], instrument: 'guitar' },
  { id: 'open-d', name: 'Open D (D A D F# A D)', short: 'Open D', strings: [38, 45, 50, 54, 57, 62], instrument: 'guitar' },
  { id: 'open-e', name: 'Open E (E B E G# B E)', short: 'Open E', strings: [40, 47, 52, 56, 59, 64], instrument: 'guitar' },
  { id: 'seven-std', name: '7-string Standard (B E A D G B E)', short: '7-string', strings: [35, 40, 45, 50, 55, 59, 64], instrument: 'guitar', down: 0 },
  { id: 'bass-4', name: 'Bass — Standard (E A D G)', short: 'Bass', strings: [28, 33, 38, 43], instrument: 'bass' },
  { id: 'bass-4-half', name: 'Bass — Eb Standard', short: 'Bass Eb', strings: [27, 32, 37, 42], instrument: 'bass' },
  { id: 'bass-5', name: 'Bass — 5-string (B E A D G)', short: 'Bass 5', strings: [23, 28, 33, 38, 43], instrument: 'bass' },
  { id: 'ukulele', name: 'Ukulele (G C E A)', short: 'Ukulele', strings: [67, 60, 64, 69], instrument: 'ukulele' },
];

export function getTuning(id: string): TuningPreset {
  return TUNINGS.find((t) => t.id === id) ?? TUNINGS[0];
}

export function stringNames(t: TuningPreset): string {
  return t.strings.map((m) => midiName(m, t.down && t.down > 0 && !t.drop ? 'flat' : 'common').replace(/-?\d+$/, '')).join(' ');
}

export function refHzFromCents(cents: number): number {
  return 440 * Math.pow(2, cents / 1200);
}

export function stringFrequencies(t: TuningPreset, refA4 = 440): number[] {
  return t.strings.map((m) => midiToFreq(m, refA4));
}

// ---------------------------------------------------------------------------
// Playability: which chord shapes are friendly to play
// ---------------------------------------------------------------------------

const EASY = new Set([
  'E', 'Em', 'E7', 'Em7', 'Emaj7', 'Esus4', 'E5',
  'A', 'Am', 'A7', 'Am7', 'Amaj7', 'Asus2', 'Asus4', 'A5',
  'D', 'Dm', 'D7', 'Dm7', 'Dmaj7', 'Dsus2', 'Dsus4', 'D5',
  'G', 'G7', 'Gmaj7', 'G5',
  'C', 'C7', 'Cmaj7', 'Csus2', 'Csus4', 'C5',
  'B7', 'Fmaj7',
]);
const SHAPE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const SUFFIX: Record<string, string> = { maj: '', min: 'm', '7': '7', m7: 'm7', maj7: 'maj7', sus4: 'sus4', sus2: 'sus2', dim: 'dim', aug: 'aug', '5': '5' };

function shapeEase(root: number, type: string): number {
  if (type === '5') return 0.95; // power chords are movable one/two-finger shapes
  const name = SHAPE_NAMES[mod12(root)] + (SUFFIX[type] ?? '');
  if (EASY.has(name)) return 1;
  return 0.35; // barre chord
}

/** Duration-weighted share of chords that are easy shapes after shifting by `shift` semitones. */
export function easeScore(chords: ChordSegment[], shift: number): number {
  let total = 0, ease = 0;
  for (const c of chords) {
    if (c.type === 'N' || c.root < 0) continue;
    const d = c.end - c.start;
    total += d;
    ease += d * shapeEase(c.root + shift, c.type);
  }
  return total > 0 ? ease / total : 0;
}

export interface CapoAdvice {
  capo: number;
  ease: number;
  easeNoCapo: number;
}

/** Best capo position (0–7) for a guitar already tuned `down` semitones below standard. */
export function suggestCapo(chords: ChordSegment[], down = 0): CapoAdvice {
  const base = easeScore(chords, down);
  let best = { capo: 0, ease: base, easeNoCapo: base };
  for (let capo = 1; capo <= 7; capo++) {
    const e = easeScore(chords, down - capo);
    if (e > best.ease + 0.12 + capo * 0.01) best = { capo, ease: e, easeNoCapo: base };
  }
  return best;
}

// ---------------------------------------------------------------------------
// Guitar tuning inference
// ---------------------------------------------------------------------------

export interface TuningEvidence {
  /** Reference offset from A440 in cents and how consistent the partials were. */
  cents: number;
  centsConfidence: number;
  /** Counts of low power-chord stacks by root MIDI note (index = MIDI). */
  stacks: ArrayLike<number>;
  /** Frames that contained music. */
  musicFrames: number;
}

export interface TuningCandidate {
  id: string;
  name: string;
  probability: number;
}

export interface TuningReport {
  /** Offset of the recording from A = 440 Hz. */
  cents: number;
  refHz: number;
  centsConfidence: number;
  /** Ranked guitar tunings with probabilities (sum ≈ 1). */
  candidates: TuningCandidate[];
  /** Lowest power-chord root heard (MIDI), if any. */
  lowestStack: number | null;
  /** Seconds of music the report is based on. */
  basedOnSec: number;
  capo: CapoAdvice | null;
  /** When the guess is a down-tuning: a standard-tuning + capo alternative, if one is easy. */
  standardCapo?: CapoAdvice | null;
  /** Plain-English explanation of why. */
  reasons: string[];
}

const AUTO_CANDIDATES: { id: string; low: number; prior: number; down: number }[] = [
  { id: 'standard', low: 40, prior: 0.62, down: 0 },
  { id: 'half-down', low: 39, prior: 0.16, down: 1 },
  { id: 'drop-d', low: 38, prior: 0.09, down: 0 },
  { id: 'whole-down', low: 38, prior: 0.06, down: 2 },
  { id: 'drop-c-sharp', low: 37, prior: 0.02, down: 1 },
  { id: 'c-sharp-std', low: 37, prior: 0.015, down: 3 },
  { id: 'drop-c', low: 36, prior: 0.02, down: 2 },
  { id: 'c-std', low: 36, prior: 0.01, down: 4 },
  { id: 'b-std', low: 35, prior: 0.005, down: 5 },
];

export function inferTuning(ev: TuningEvidence, chords: ChordSegment[], hopSec: number): TuningReport {
  const music = Math.max(1, ev.musicFrames);
  const rate = (midi: number) => (ev.stacks[midi] ?? 0) / music;
  // Evidence below E2 (the lowest note of a standard-tuned guitar).
  let lowestStack: number | null = null;
  let maxRate = 0;
  for (let m = 30; m <= 52; m++) maxRate = Math.max(maxRate, rate(m));
  for (let m = 30; m <= 52; m++) {
    const r = rate(m);
    if (r >= 0.025 && r >= maxRate * 0.15) { lowestStack = m; break; }
  }

  const reasons: string[] = [];
  // Calibrated on synthetic and real recordings: a bass playing under a guitar can
  // also produce low root-fifth-octave stacks, so stack evidence saturates (≈20 % of
  // music frames) instead of being treated as proof, and the final probabilities are
  // softened (temperature 1.5). The card always shows the runner-up alternatives.
  const scores = AUTO_CANDIDATES.map((c) => {
    let s = Math.log(c.prior);
    // Stacks rooted below this tuning's lowest string are physically impossible on it.
    let impossible = 0;
    for (let m = 30; m < c.low; m++) impossible += rate(m);
    s -= 20 * impossible;
    // Stacks right on the lowest open string are the signature of the tuning.
    const own = rate(c.low);
    s += 4 * Math.min(1, own / 0.2);
    if (c.id === 'standard' && lowestStack !== null && lowestStack >= 40) s += 1.5;
    // Chord shapes: tunings that turn the progression into open chords are likelier.
    const ease = easeScore(chords, c.down);
    s += 2.2 * ease;
    // Drop vs whole-step-down: drop tunings shine on power chords rooted on the low string.
    if (c.id.startsWith('drop') && own > 0) {
      const lowPc = mod12(c.low);
      let pcDur = 0, total = 0;
      for (const ch of chords) {
        if (ch.type === 'N') continue;
        const d = ch.end - ch.start;
        total += d;
        if (ch.root === lowPc && (ch.type === '5' || ch.type === 'maj' || ch.type === 'min')) pcDur += d;
      }
      if (total > 0) s += 1.5 * (pcDur / total);
    }
    return s / 1.5;
  });
  const mx = Math.max(...scores);
  const exps = scores.map((s) => Math.exp(s - mx));
  const sum = exps.reduce((a, b) => a + b, 0);
  const candidates = AUTO_CANDIDATES.map((c, i) => ({ id: c.id, name: getTuning(c.id).name, probability: exps[i] / sum }))
    .sort((a, b) => b.probability - a.probability);

  const top = getTuning(candidates[0].id);
  if (lowestStack !== null && lowestStack < 40) {
    reasons.push(`Heard root–fifth–octave “power chord” stacks on ${midiName(lowestStack, 'flat')}, below a standard guitar’s low E. That is typical of a guitar tuned down — though a bass playing under a guitar can do it too.`);
  } else if (lowestStack !== null) {
    reasons.push(`Lowest power-chord root heard was ${midiName(lowestStack)}, which fits standard tuning.`);
  } else {
    reasons.push('No low power-chord stacks heard, so the guess leans on which chord shapes are easiest.');
  }
  const capo = chords.length ? suggestCapo(chords, top.down ?? 0) : null;
  if (capo && capo.capo > 0) reasons.push(`Capo ${capo.capo} turns most of the chords into open shapes.`);
  let standardCapo: CapoAdvice | null = null;
  if ((top.down ?? 0) > 0 && chords.length) {
    const sc = suggestCapo(chords, 0);
    if (sc.capo > 0 && sc.ease >= 0.75) {
      standardCapo = sc;
      reasons.push(`Not sure? In standard tuning, capo ${sc.capo} also makes the chords easy.`);
    }
  }
  if (Math.abs(ev.cents) >= 8 && ev.centsConfidence > 0.35) {
    reasons.push(`The recording sits ${Math.abs(ev.cents).toFixed(0)} cents ${ev.cents < 0 ? 'flat' : 'sharp'} of A440 — tune to A = ${refHzFromCents(ev.cents).toFixed(1)} Hz to match it.`);
  }
  return {
    cents: ev.cents,
    refHz: refHzFromCents(ev.cents),
    centsConfidence: ev.centsConfidence,
    candidates,
    lowestStack,
    basedOnSec: ev.musicFrames * hopSec,
    capo,
    standardCapo,
    reasons,
  };
}

/** Pitch classes that a chord would contain once a guitar is tuned to `t` (helper for UIs/tests). */
export function soundingTones(root: number, type: string): number[] {
  return chordTones({ root, type });
}
