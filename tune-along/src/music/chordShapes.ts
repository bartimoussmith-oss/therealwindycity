/**
 * Guitar chord shapes. Shapes are defined in "shape space" (what you would call the
 * chord in standard tuning). For E♭/D/C♯ standard the sounding chord is shifted into
 * shape space first, so a sounding E♭ in E♭-standard shows the familiar E shape.
 */
import { mod12 } from '../dsp/notes';

export interface Shape {
  /** Fret per string, lowest string first. −1 = muted, 0 = open. */
  frets: number[];
  /** Lowest fret drawn at the top of the diagram (1 = nut). */
  baseFret: number;
  barre: { fret: number; from: number; to: number } | null;
  /** True for open-position shapes. */
  open: boolean;
}

const SHAPE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const SUFFIX: Record<string, string> = { maj: '', min: 'm', '7': '7', m7: 'm7', maj7: 'maj7', sus4: 'sus4', sus2: 'sus2', dim: 'dim', aug: 'aug', '5': '5' };

const X = -1;
const OPEN: Record<string, number[]> = {
  C: [X, 3, 2, 0, 1, 0], C7: [X, 3, 2, 3, 1, 0], Cmaj7: [X, 3, 2, 0, 0, 0], Csus2: [X, 3, 0, 0, 1, 3], Csus4: [X, 3, 3, 0, 1, 1], C5: [X, 3, 5, 5, X, X], Caug: [X, 3, 2, 1, 1, 0],
  D: [X, X, 0, 2, 3, 2], D7: [X, X, 0, 2, 1, 2], Dmaj7: [X, X, 0, 2, 2, 2], Dm: [X, X, 0, 2, 3, 1], Dm7: [X, X, 0, 2, 1, 1], Dsus2: [X, X, 0, 2, 3, 0], Dsus4: [X, X, 0, 2, 3, 3], D5: [X, X, 0, 2, 3, X], Ddim: [X, X, 0, 1, 3, 1], Daug: [X, X, 0, 3, 3, 2],
  E: [0, 2, 2, 1, 0, 0], E7: [0, 2, 0, 1, 0, 0], Emaj7: [0, 2, 1, 1, 0, 0], Em: [0, 2, 2, 0, 0, 0], Em7: [0, 2, 0, 0, 0, 0], Esus4: [0, 2, 2, 2, 0, 0], Esus2: [0, 2, 4, 4, 0, 0], E5: [0, 2, 2, X, X, X], Eaug: [0, 3, 2, 1, 1, 0],
  Fmaj7: [X, X, 3, 2, 1, 0],
  G: [3, 2, 0, 0, 0, 3], G7: [3, 2, 0, 0, 0, 1], Gmaj7: [3, 2, 0, 0, 0, 2], G5: [3, 5, 5, X, X, X], Gsus4: [3, 3, 0, 0, 1, 3],
  A: [X, 0, 2, 2, 2, 0], A7: [X, 0, 2, 0, 2, 0], Amaj7: [X, 0, 2, 1, 2, 0], Am: [X, 0, 2, 2, 1, 0], Am7: [X, 0, 2, 0, 1, 0], Asus2: [X, 0, 2, 2, 0, 0], Asus4: [X, 0, 2, 2, 3, 0], A5: [X, 0, 2, 2, X, X],
  B7: [X, 2, 1, 2, 0, 2],
};

// Movable shapes as offsets from the root fret (M = muted; offsets may be negative).
const M = -99;
const E_FORM: Record<string, number[]> = {
  maj: [0, 2, 2, 1, 0, 0], min: [0, 2, 2, 0, 0, 0], '7': [0, 2, 0, 1, 0, 0], m7: [0, 2, 0, 0, 0, 0],
  maj7: [0, M, 1, 1, 0, M], sus4: [0, 2, 2, 2, 0, 0], sus2: [0, 2, 4, 4, 0, 0], '5': [0, 2, 2, M, M, M],
  dim: [0, 1, 2, 0, M, M], aug: [0, 3, 2, 1, M, M],
};
const A_FORM: Record<string, number[]> = {
  maj: [M, 0, 2, 2, 2, 0], min: [M, 0, 2, 2, 1, 0], '7': [M, 0, 2, 0, 2, 0], m7: [M, 0, 2, 0, 1, 0],
  maj7: [M, 0, 2, 1, 2, 0], sus4: [M, 0, 2, 2, 3, 0], sus2: [M, 0, 2, 2, 0, 0], '5': [M, 0, 2, 2, M, M],
  dim: [M, 0, 1, 2, 1, M], aug: [M, 0, -1, -2, -2, M],
};

export function shapeName(root: number, type: string): string {
  return SHAPE_NAMES[mod12(root)] + (SUFFIX[type] ?? '');
}

function finish(frets: number[], open: boolean): Shape {
  const fretted = frets.filter((f) => f > 0);
  const min = fretted.length ? Math.min(...fretted) : 0;
  const max = fretted.length ? Math.max(...fretted) : 0;
  const baseFret = max <= 4 ? 1 : min;
  let barre: Shape['barre'] = null;
  if (min > 0 && !open) {
    const at = frets.map((f, i) => (f === min ? i : -1)).filter((i) => i >= 0);
    if (at.length >= 2) {
      const from = at[0], to = at[at.length - 1];
      // only a real barre if nothing between is open/muted/lower
      if (frets.slice(from, to + 1).every((f) => f >= min)) barre = { fret: min, from, to };
    }
  }
  return { frets, baseFret, barre, open };
}

function movable(form: number[], r: number): number[] | null {
  if (form.some((o) => o !== M && r + o < 0)) return null;
  return form.map((o) => (o === M ? X : r + o));
}

/**
 * Shape for a chord given in shape space. `drop` = the low string is tuned a whole
 * step below the others (drop D family).
 */
export function shapeFor(root: number, type: string, drop = false): Shape | null {
  if (type === 'N' || root < 0) return null;
  const r = mod12(root);
  if (drop && type === '5') {
    const f = mod12(r - 2); // low string is "D" in shape space
    return finish([f, f, f, X, X, X], f === 0);
  }
  const name = shapeName(r, type);
  let frets: number[] | null = OPEN[name] ? [...OPEN[name]] : null;
  let open = frets !== null;
  if (!frets) {
    const e = E_FORM[type], a = A_FORM[type];
    if (!e || !a) return null;
    const rE = mod12(r - 4), rA = mod12(r - 9);
    const fe = movable(e, rE) ?? movable(e, rE + 12);
    const fa = movable(a, rA) ?? movable(a, rA + 12);
    const lowE = fe ? Math.max(...fe) : 99, lowA = fa ? Math.max(...fa) : 99;
    frets = type === 'sus2' || type === 'maj7' ? (fa && lowA <= lowE + 2 ? fa : fe) : lowE <= lowA ? fe : fa;
    open = false;
  }
  if (!frets) return null;
  if (drop && frets[0] !== X) {
    const moved = frets[0] + 2;
    const others = frets.slice(1).filter((f) => f > 0);
    const hi = others.length ? Math.max(...others) : moved;
    const lo = others.length ? Math.min(...others) : moved;
    frets[0] = moved <= 15 && Math.max(hi, moved) - Math.min(lo, moved) <= 4 ? moved : X;
  }
  return finish(frets, open);
}

/** MIDI notes a shape produces on a given set of open strings (for tests and audition). */
export function shapeNotes(shape: Shape, strings: number[]): number[] {
  return shape.frets.flatMap((f, i) => (f === X || i >= strings.length ? [] : [strings[i] + f]));
}
