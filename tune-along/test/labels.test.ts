import { describe, expect, it } from 'vitest';
import { makeLabeler } from '../src/app/labels';
import type { KeyResult } from '../src/dsp/key';

const ebMajor: KeyResult = { tonic: 3, mode: 'major', label: 'Eb major', correlation: 0.9, confidence: 0.1 };

describe('chord labels: sounding names vs shapes', () => {
  it('names sounding chords with the key’s spelling and shows the shape to play in Eb standard', () => {
    const l = makeLabeler(ebMajor, { mode: 'sound', capo: 0, tuningId: 'half-down' });
    expect(l.label({ root: 3, type: 'maj' })).toBe('Eb');
    expect(l.label({ root: 10, type: '7' })).toBe('Bb7');
    expect(l.sub({ root: 3, type: 'maj' })).toBe('play E shape');
    expect(l.shape({ root: 3, type: 'maj' })).toEqual({ root: 4, type: 'maj', drop: false });
  });

  it('switches to shape names and reverses the hint', () => {
    const l = makeLabeler(ebMajor, { mode: 'shape', capo: 0, tuningId: 'half-down' });
    expect(l.label({ root: 8, type: 'maj' })).toBe('A');
    expect(l.label({ root: 0, type: 'min' })).toBe('C#m');
    expect(l.sub({ root: 8, type: 'maj' })).toBe('sounds Ab');
  });

  it('applies a capo in standard tuning (Bb song, capo 3 → G shapes)', () => {
    const l = makeLabeler(null, { mode: 'shape', capo: 3, tuningId: 'standard' });
    expect(l.label({ root: 10, type: 'maj' })).toBe('G');
    expect(l.label({ root: 7, type: 'min' })).toBe('Em');
  });

  it('has no hint when nothing is transposed, and keeps N.C. as is', () => {
    const l = makeLabeler(null, { mode: 'shape', capo: 0, tuningId: 'standard' });
    expect(l.sub({ root: 4, type: 'maj' })).toBe('');
    expect(l.label({ root: -1, type: 'N' })).toBe('N.C.');
  });

  it('marks drop-D shapes and does not offer diagrams for open tunings', () => {
    expect(makeLabeler(null, { mode: 'sound', capo: 0, tuningId: 'drop-d' }).shape({ root: 2, type: '5' })?.drop).toBe(true);
    expect(makeLabeler(null, { mode: 'sound', capo: 0, tuningId: 'open-g' }).diagramsApply).toBe(false);
  });
});
