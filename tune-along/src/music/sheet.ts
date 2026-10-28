/**
 * Chord-over-lyrics layout ("chord sheet") from a chord timeline and timed lyrics,
 * for the screen and for printing. Chords are placed above the syllable being sung
 * when they change, using each line's timing; instrumental passages become bar-style
 * chord lines.
 */
import type { ChordSegment } from '../dsp/chords';
import type { LyricLine } from '../lib/songModel';

export interface PlacedChord {
  col: number;
  label: string;
  t: number;
}

export interface SheetLine {
  kind: 'lyric' | 'instrumental';
  t: number;
  end: number;
  text: string;
  chords: PlacedChord[];
}

export interface SheetOptions {
  /** Converts a chord to the label to print (handles spelling, capo, shapes). */
  label: (c: ChordSegment) => string;
  /** lyricTime = songTime + lyricsOffset */
  lyricsOffset?: number;
  /** Gap (s) without lyrics that becomes an instrumental line. */
  instrumentalGap?: number;
  /** Max seconds a single lyric line may claim. */
  maxLine?: number;
  chordsPerInstrumentalLine?: number;
}

function realChords(chords: ChordSegment[]): ChordSegment[] {
  return chords.filter((c) => c.type !== 'N' && c.root >= 0 && c.end - c.start >= 0.3);
}

function instrumentalLines(chords: ChordSegment[], from: number, to: number, opts: SheetOptions): SheetLine[] {
  const inRange = realChords(chords).filter((c) => c.end > from + 0.4 && c.start < to - 0.4);
  if (!inRange.length) return [];
  const per = opts.chordsPerInstrumentalLine ?? 8;
  const out: SheetLine[] = [];
  for (let i = 0; i < inRange.length; i += per) {
    const group = inRange.slice(i, i + per);
    let text = '';
    const placed: PlacedChord[] = [];
    for (const c of group) {
      const label = opts.label(c);
      placed.push({ col: text.length + 2, label, t: Math.max(c.start, from) });
      text += '| ' + label.padEnd(Math.max(4, label.length + 1));
    }
    text += '|';
    out.push({ kind: 'instrumental', t: Math.max(group[0].start, from), end: Math.min(group[group.length - 1].end, to), text, chords: placed });
  }
  return out;
}

export function buildSheet(chords: ChordSegment[], lyrics: LyricLine[], opts: SheetOptions): SheetLine[] {
  const offset = opts.lyricsOffset ?? 0;
  const gap = opts.instrumentalGap ?? 6;
  const maxLine = opts.maxLine ?? 8;
  const cs = realChords(chords);
  const songEnd = chords.length ? chords[chords.length - 1].end : 0;
  const lines = lyrics
    .map((l) => ({ t: l.t - offset, text: l.text }))
    .filter((l) => l.text.trim().length > 0)
    .sort((a, b) => a.t - b.t);
  const out: SheetLine[] = [];
  if (!lines.length) return instrumentalLines(chords, 0, songEnd, opts);

  let cursor = cs.length ? Math.min(cs[0].start, lines[0].t) : lines[0].t;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const next = i + 1 < lines.length ? lines[i + 1].t : Math.max(songEnd, line.t + 4);
    if (line.t - cursor >= gap * 0.5 && (i === 0 || line.t - cursor >= gap)) out.push(...instrumentalLines(chords, cursor, line.t, opts));
    else if (i === 0 && line.t - cursor > 1.5) out.push(...instrumentalLines(chords, cursor, line.t, opts));
    const end = Math.min(next, line.t + maxLine);
    const span = Math.max(0.5, end - line.t);
    const text = line.text;
    const placed: PlacedChord[] = [];
    // chord sounding when the line starts
    const active = cs.find((c) => c.start <= line.t + 0.05 && c.end > line.t + 0.05);
    const changes = cs.filter((c) => c.start > line.t + 0.05 && c.start < end - 0.15);
    if (active && !(changes.length && changes[0].start - line.t < span * 0.1)) placed.push({ col: 0, label: opts.label(active), t: line.t });
    for (const c of changes) {
      let col = Math.round(((c.start - line.t) / span) * text.length);
      // snap to the start of the word being sung
      while (col > 0 && col < text.length && text[col - 1] !== ' ') col--;
      placed.push({ col, label: opts.label(c), t: c.start });
    }
    // no overlaps: each label needs its width + 1 space
    for (let k = 1; k < placed.length; k++) {
      const prev = placed[k - 1];
      const min = prev.col + prev.label.length + 1;
      if (placed[k].col < min) placed[k].col = min;
    }
    out.push({ kind: 'lyric', t: line.t, end, text, chords: placed });
    cursor = end;
  }
  if (songEnd - cursor >= 2) out.push(...instrumentalLines(chords, cursor, songEnd, opts));
  return out;
}

/** The chord line as a string (monospace) for plain-text export. */
export function chordLineText(line: SheetLine): string {
  let s = '';
  for (const c of line.chords) {
    if (s.length < c.col) s = s.padEnd(c.col);
    s += c.label + ' ';
  }
  return s.trimEnd();
}

export function sheetToText(lines: SheetLine[]): string {
  return lines
    .map((l) => (l.kind === 'instrumental' ? l.text : `${chordLineText(l)}\n${l.text}`))
    .join('\n\n');
}
