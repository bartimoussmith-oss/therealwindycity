/** How chords are named on screen: sounding names vs. guitar shapes (tuning + capo). */
import { chordLabel, type Chord, type ChordSegment } from '../dsp/chords';
import type { KeyResult } from '../dsp/key';
import { spellingForKey } from '../dsp/notes';
import { getTuning, type TuningReport } from '../dsp/tuning';
import { shapeName } from '../music/chordShapes';
import type { SongRecord } from '../lib/songModel';

export interface DisplayPrefs {
  mode: 'sound' | 'shape';
  capo: number;
  tuningId: string;
}

export interface Labeler {
  /** Main label in the chosen mode. */
  label(c: Chord): string;
  /** Secondary label (the other mode), or '' when identical. */
  sub(c: Chord): string;
  /** Root/type in shape space + drop flag, for diagrams; null if diagrams don't apply. */
  shape(c: Chord): { root: number; type: string; drop: boolean } | null;
  shift: number;
  prefs: DisplayPrefs;
  diagramsApply: boolean;
}

export function defaultPrefs(tuning: TuningReport | null | undefined, saved?: Partial<DisplayPrefs>): DisplayPrefs {
  return {
    mode: saved?.mode ?? 'sound',
    capo: saved?.capo ?? 0,
    tuningId: saved?.tuningId ?? tuning?.candidates[0]?.id ?? 'standard',
  };
}

export function songPrefs(song: SongRecord): DisplayPrefs {
  return defaultPrefs(song.tuning, { mode: song.prefs.display, capo: song.prefs.capo, tuningId: song.prefs.tuningId });
}

export function makeLabeler(key: KeyResult | null | undefined, prefs: DisplayPrefs): Labeler {
  const t = getTuning(prefs.tuningId);
  const family = t.down !== undefined;
  const shift = family ? (t.down ?? 0) - prefs.capo : -prefs.capo;
  const spelling = spellingForKey(key?.tonic, key?.mode);
  const sound = (c: Chord) => chordLabel(c, spelling);
  const shapeLabel = (c: Chord) => (c.type === 'N' || c.root < 0 ? 'N.C.' : shapeName(c.root + shift, c.type));
  const transposes = shift !== 0;
  return {
    label: (c) => (prefs.mode === 'shape' && transposes ? shapeLabel(c) : sound(c)),
    sub: (c) => {
      if (!transposes || c.type === 'N') return '';
      return prefs.mode === 'shape' ? `sounds ${sound(c)}` : `play ${shapeLabel(c)} shape`;
    },
    shape: (c) => (family && c.type !== 'N' && c.root >= 0 ? { root: c.root + shift, type: c.type, drop: !!t.drop } : null),
    shift,
    prefs,
    diagramsApply: family,
  };
}

export function uniqueChords(chords: ChordSegment[]): Chord[] {
  const seen = new Map<string, { c: Chord; d: number }>();
  for (const c of chords) {
    if (c.type === 'N' || c.root < 0) continue;
    const k = `${c.root}:${c.type}`;
    const cur = seen.get(k);
    if (cur) cur.d += c.end - c.start; else seen.set(k, { c: { root: c.root, type: c.type }, d: c.end - c.start });
  }
  return [...seen.values()].filter((x) => x.d >= 0.8).map((x) => x.c);
}

export function fmtTime(t: number): string {
  const s = Math.max(0, Math.floor(t));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}
