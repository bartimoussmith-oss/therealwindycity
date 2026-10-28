import { describe, expect, it } from 'vitest';
import { CHORD_TYPES, chordLabel, chordTones } from '../src/dsp/chords';
import { mod12 } from '../src/dsp/notes';
import { shapeFor, shapeNotes, shapeName } from '../src/music/chordShapes';
import { parseLrc, formatLrc, isLrc } from '../src/music/lrc';
import { buildSheet, sheetToText } from '../src/music/sheet';
import { getTuning, inferTuning, suggestCapo, easeScore } from '../src/dsp/tuning';
import type { ChordSegment } from '../src/dsp/chords';

const STD = getTuning('standard').strings;
const DROP_D = getTuning('drop-d').strings;

describe('chord shapes', () => {
  it('every shape for every chord plays only chord tones, includes the root and the defining notes', () => {
    const problems: string[] = [];
    for (const t of CHORD_TYPES) {
      for (let root = 0; root < 12; root++) {
        const shape = shapeFor(root, t.id);
        const name = shapeName(root, t.id);
        if (!shape) { problems.push(`${name}: no shape`); continue; }
        const notes = shapeNotes(shape, STD);
        const pcs = new Set(notes.map(mod12));
        const tones = chordTones({ root, type: t.id });
        const extra = [...pcs].filter((p) => !tones.includes(p));
        if (extra.length) problems.push(`${name}: wrong notes ${extra}`);
        if (!pcs.has(mod12(root))) problems.push(`${name}: no root`);
        // third and seventh (when present) must sound; the fifth may be omitted in 7th shapes
        const required = t.intervals.filter((iv) => !(iv === 7 && t.intervals.length === 4)).map((iv) => mod12(root + iv));
        for (const r of required) if (!pcs.has(r)) problems.push(`${name}: missing ${r}`);
        const fretted = shape.frets.filter((f) => f > 0);
        if (fretted.length && Math.max(...fretted) - Math.min(...fretted) > 4) problems.push(`${name}: stretch`);
        if (shape.frets.filter((f) => f >= 0).length < 3) problems.push(`${name}: too few strings`);
      }
    }
    expect(problems).toEqual([]);
  });

  it('gives drop-D power chords as one-finger shapes on the low three strings', () => {
    const d5 = shapeFor(2, '5', true)!;
    expect(d5.frets).toEqual([0, 0, 0, -1, -1, -1]);
    const f5 = shapeFor(5, '5', true)!;
    expect(f5.frets).toEqual([3, 3, 3, -1, -1, -1]);
    expect(shapeNotes(f5, DROP_D).map(mod12)).toEqual([5, 0, 5]);
  });

  it('keeps drop-D shapes correct for full chords', () => {
    for (const [root, type] of [[7, 'maj'], [0, 'maj'], [9, 'min'], [5, 'maj']] as [number, string][]) {
      const s = shapeFor(root, type, true)!;
      const pcs = new Set(shapeNotes(s, DROP_D).map(mod12));
      const tones = chordTones({ root, type });
      expect([...pcs].every((p) => tones.includes(p))).toBe(true);
    }
  });

  it('marks barres', () => {
    expect(shapeFor(5, 'maj')!.barre).toEqual({ fret: 1, from: 0, to: 5 }); // F
    expect(shapeFor(11, 'min')!.barre?.fret).toBe(2); // Bm
    expect(shapeFor(4, 'maj')!.barre).toBeNull(); // open E
  });
});

describe('LRC', () => {
  const text = `[ti:Song]\n[ar:Band]\n[offset:+500]\n[00:12.50]First line\n[00:15.00][01:15.00]Chorus line\nnot a lyric\n[00:20.10]<00:20.10>Word <00:21.00>sync`;
  it('parses timestamps, repeats, offsets and word tags', () => {
    const lines = parseLrc(text);
    expect(isLrc(text)).toBe(true);
    expect(lines.map((l) => l.text)).toEqual(['First line', 'Chorus line', 'Word sync', 'Chorus line']);
    expect(lines[0].t).toBeCloseTo(12.0, 5);
    expect(lines[3].t).toBeCloseTo(74.5, 5);
  });
  it('round-trips', () => {
    const lines = parseLrc('[00:01.00]a\n[01:02.25]b');
    expect(parseLrc(formatLrc(lines))).toEqual(lines);
  });
});

describe('chord sheet layout', () => {
  const seg = (start: number, end: number, root: number, type = 'maj'): ChordSegment => ({ start, end, root, type, confidence: 1 });
  const chords = [seg(0, 4, 3, '5'), seg(4, 8, 8), seg(8, 10, 3), seg(10, 12, 10), seg(12, 16, 0, 'min'), seg(16, 20, 8)];
  const lyrics = [
    { t: 8, text: 'Wind comes off the lake at dawn' },
    { t: 12, text: 'Rattles every window on the avenue' },
  ];
  const label = (c: ChordSegment) => chordLabel(c, 'flat');

  it('puts the intro on an instrumental line and chords over the right words', () => {
    const sheet = buildSheet(chords, lyrics, { label });
    expect(sheet[0].kind).toBe('instrumental');
    expect(sheet[0].text).toContain('Eb5');
    expect(sheet[0].text).toContain('Ab');
    const l1 = sheet.find((l) => l.text.startsWith('Wind'))!;
    expect(l1.chords.map((c) => c.label)).toEqual(['Eb', 'Bb']);
    // Bb starts halfway through the 4-second line → around "lake"
    const bb = l1.chords[1];
    expect(l1.text.slice(bb.col).startsWith('lake') || l1.text.slice(bb.col).startsWith('the')).toBe(true);
    const txt = sheetToText(sheet);
    expect(txt).toContain('Rattles every window');
  });

  it('honours the lyrics offset', () => {
    const sheet = buildSheet(chords, lyrics.map((l) => ({ ...l, t: l.t + 2 })), { label, lyricsOffset: 2 });
    const l1 = sheet.find((l) => l.text.startsWith('Wind'))!;
    expect(l1.chords[0].label).toBe('Eb');
  });

  it('works with no lyrics at all (chord chart only)', () => {
    const sheet = buildSheet(chords, [], { label, chordsPerInstrumentalLine: 4 });
    expect(sheet.length).toBe(2);
    expect(sheet.every((l) => l.kind === 'instrumental')).toBe(true);
  });
});

describe('tuning inference and capo advice', () => {
  const seg = (root: number, type: string, d = 2): ChordSegment => ({ start: 0, end: d, root, type, confidence: 1 });
  it('suggests capo 3 for a G-C-D-Em style song in B♭', () => {
    const song = [seg(10, 'maj'), seg(3, 'maj'), seg(5, 'maj'), seg(7, 'min')]; // Bb Eb F Gm
    const advice = suggestCapo(song, 0);
    expect(advice.capo).toBe(3);
    expect(easeScore(song, -3)).toBe(1);
  });

  it('defaults to standard tuning without low evidence, and picks drop D from D power-chord stacks', () => {
    const stacks = new Float32Array(128);
    const chords = [seg(2, '5'), seg(0, '5'), seg(7, '5'), seg(9, '5')];
    const plain = inferTuning({ cents: 0, centsConfidence: 0.9, stacks, musicFrames: 1000 }, chords, 0.093);
    expect(plain.candidates[0].id).toBe('standard');
    stacks[38] = 300; // D2 stacks
    const drop = inferTuning({ cents: 0, centsConfidence: 0.9, stacks, musicFrames: 1000 }, chords, 0.093);
    expect(['drop-d', 'whole-down']).toContain(drop.candidates[0].id);
    expect(drop.candidates[0].id).toBe('drop-d');
    expect(drop.lowestStack).toBe(38);
  });
});
