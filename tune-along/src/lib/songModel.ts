/**
 * The stored song: what TuneAlong remembers after hearing a track, plus pure
 * functions to create one from a listening segment, merge later listens into it,
 * and export/import it as a portable JSON file.
 */
import { CHROMA_HOP_SEC } from '../dsp/chroma';
import type { ChordSegment } from '../dsp/chords';
import { FP_HOP_SEC, type FingerprintData } from '../dsp/fingerprint';
import type { KeyResult } from '../dsp/key';
import type { TuningReport } from '../dsp/tuning';
import { analyzeFeatures, type TuningAccumulator } from '../engine/analysis';
import type { SegmentResult } from '../engine/engine';

export type SourceKind = 'mic' | 'tab' | 'file' | 'demo';

export interface LyricLine {
  t: number;
  text: string;
}

export interface SongLyrics {
  lines: LyricLine[];
  synced: boolean;
  source: 'lrclib' | 'manual' | 'transcript' | 'demo';
  lrclibId?: number;
}

export interface SongPrefs {
  capo?: number;
  tuningId?: string;
  display?: 'sound' | 'shape';
}

export interface SongRecord {
  id: string;
  title: string;
  artist: string;
  createdAt: number;
  updatedAt: number;
  listens: number;
  lastHeardAt: number;
  source: SourceKind;
  demoId?: string;
  // stored features (song timeline, frame i ≈ i·CHROMA_HOP_SEC)
  chroma: Float32Array;
  bass: Float32Array;
  energy: Float32Array;
  coverage: Uint8Array;
  stacks: Float32Array;
  musicFrames: number;
  tuningAcc: TuningAccumulator;
  bpm: number | null;
  fp: FingerprintData;
  // derived
  duration: number;
  chords: ChordSegment[];
  key: KeyResult | null;
  tuning: TuningReport;
  // words
  lyrics: SongLyrics | null;
  /** lyricTime = songTime + lyricsOffset */
  lyricsOffset: number;
  /** Speech-recognised words, song time. */
  transcript: LyricLine[];
  prefs: SongPrefs;
}

export function newId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c && 'randomUUID' in c) return c.randomUUID();
  return 'song-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function defaultTitle(at = new Date()): string {
  return `Untitled song · ${at.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${at.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`;
}

export function createSongFromSegment(
  seg: SegmentResult,
  meta: { title?: string; artist?: string; source: SourceKind; demoId?: string; transcript?: LyricLine[]; now?: number },
): SongRecord {
  const now = meta.now ?? Date.now();
  const frames = seg.energy.length;
  const coverage = new Uint8Array(frames).fill(1);
  return {
    id: newId(),
    title: meta.title ?? defaultTitle(new Date(now)),
    artist: meta.artist ?? '',
    createdAt: now,
    updatedAt: now,
    listens: 1,
    lastHeardAt: now,
    source: meta.source,
    demoId: meta.demoId,
    chroma: seg.chroma,
    bass: seg.bass,
    energy: seg.energy,
    coverage,
    stacks: seg.stacks,
    musicFrames: seg.musicFrames,
    tuningAcc: { ...seg.tuningAcc },
    bpm: seg.bpm,
    fp: seg.fp,
    duration: seg.duration,
    chords: seg.chords,
    key: seg.key,
    tuning: seg.tuning,
    lyrics: null,
    lyricsOffset: 0,
    transcript: meta.transcript ?? [],
    prefs: {},
  };
}

function growF32(a: Float32Array, len: number, prepend: number): Float32Array {
  const out = new Float32Array(len);
  out.set(a, prepend);
  return out;
}

/**
 * Folds a recognised listen into the stored song: fills in parts of the song that
 * were not heard before (e.g. the first listen started mid-song), averages the
 * overlap, adds fingerprints for new regions, and re-runs the analysis.
 */
export function mergeSegmentIntoSong(song: SongRecord, seg: SegmentResult, transcript: LyricLine[] = [], now = Date.now()): SongRecord {
  if (!seg.match) throw new Error('segment is not matched to a song');
  const shift = Math.round(seg.match.offsetSec / CHROMA_HOP_SEC); // segment frame k → song frame k+shift
  const oldFrames = song.energy.length;
  const segFrames = seg.energy.length;
  const prepend = Math.max(0, -shift);
  const newLen = Math.max(oldFrames + prepend, shift + prepend + segFrames);
  const chroma = growF32(song.chroma, newLen * 12, prepend * 12);
  const bass = growF32(song.bass, newLen * 12, prepend * 12);
  const energy = growF32(song.energy, newLen, prepend);
  const coverage = new Uint8Array(newLen);
  coverage.set(song.coverage, prepend);
  for (let k = 0; k < segFrames; k++) {
    const s = k + shift + prepend;
    if (s < 0 || s >= newLen) continue;
    if (seg.energy[k] <= 0.0025) continue;
    const c = coverage[s];
    for (let j = 0; j < 12; j++) {
      chroma[s * 12 + j] = (chroma[s * 12 + j] * c + seg.chroma[k * 12 + j]) / (c + 1);
      bass[s * 12 + j] = (bass[s * 12 + j] * c + seg.bass[k * 12 + j]) / (c + 1);
    }
    // re-normalise the averaged chroma row
    let n = 0;
    for (let j = 0; j < 12; j++) n += chroma[s * 12 + j] ** 2;
    n = Math.sqrt(n);
    if (n > 0) for (let j = 0; j < 12; j++) chroma[s * 12 + j] /= n;
    energy[s] = Math.max(energy[s], seg.energy[k]);
    coverage[s] = Math.min(255, c + 1);
  }
  // fingerprints: shift old ones if we prepended, add new ones outside the old range
  const fpShift = Math.round(seg.match.offsetSec / FP_HOP_SEC);
  const fpPrepend = prepend * 4;
  let minT = Infinity, maxT = -Infinity;
  for (let i = 0; i < song.fp.times.length; i++) {
    const t = song.fp.times[i];
    if (t < minT) minT = t;
    if (t > maxT) maxT = t;
  }
  const hashes: number[] = Array.from(song.fp.hashes);
  const times: number[] = Array.from(song.fp.times, (t) => t + fpPrepend);
  for (let i = 0; i < seg.fp.times.length; i++) {
    const t = seg.fp.times[i] + fpShift; // old song timeline
    if (t >= minT && t <= maxT) continue;
    const nt = t + fpPrepend;
    if (nt < 0) continue;
    hashes.push(seg.fp.hashes[i]);
    times.push(nt);
  }
  const order = times.map((_, i) => i).sort((a, b) => times[a] - times[b]);
  const fp: FingerprintData = { hashes: Uint32Array.from(order, (i) => hashes[i]), times: Uint32Array.from(order, (i) => times[i]) };

  const stacks = new Float32Array(128);
  for (let i = 0; i < 128; i++) stacks[i] = song.stacks[i] + seg.stacks[i];
  const tuningAcc = { re: song.tuningAcc.re + seg.tuningAcc.re, im: song.tuningAcc.im + seg.tuningAcc.im, w: song.tuningAcc.w + seg.tuningAcc.w };
  const musicFrames = song.musicFrames + seg.musicFrames;
  const analysis = analyzeFeatures({ chroma, bass, energy, stacks, musicFrames, tuningAcc }, 0);
  const prependSec = prepend * CHROMA_HOP_SEC;
  const segToSong = (t: number) => t + seg.match!.offsetSec + prependSec;
  const mergedTranscript = [
    ...song.transcript.map((l) => ({ ...l, t: l.t + prependSec })),
    ...transcript.map((l) => ({ ...l, t: segToSong(l.t) })),
  ].sort((a, b) => a.t - b.t);
  return {
    ...song,
    updatedAt: now,
    lastHeardAt: now,
    listens: song.listens + 1,
    chroma, bass, energy, coverage, stacks, musicFrames, tuningAcc,
    bpm: song.bpm ?? seg.bpm,
    fp,
    duration: newLen * CHROMA_HOP_SEC,
    chords: analysis.chords,
    key: analysis.key,
    tuning: analysis.tuning,
    lyricsOffset: song.lyricsOffset - prependSec,
    transcript: mergedTranscript,
  };
}

// ---------------------------------------------------------------------------
// Portable export / import (typed arrays as base64)
// ---------------------------------------------------------------------------

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

export function bytesToBase64(bytes: Uint8Array): string {
  let out = '';
  let i = 0;
  for (; i + 2 < bytes.length; i += 3) {
    const n = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
    out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + B64[(n >> 6) & 63] + B64[n & 63];
  }
  const rest = bytes.length - i;
  if (rest === 1) {
    const n = bytes[i] << 16;
    out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + '==';
  } else if (rest === 2) {
    const n = (bytes[i] << 16) | (bytes[i + 1] << 8);
    out += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + B64[(n >> 6) & 63] + '=';
  }
  return out;
}

export function base64ToBytes(s: string): Uint8Array {
  const clean = s.replace(/[^A-Za-z0-9+/]/g, '');
  const len = Math.floor((clean.length * 3) / 4);
  const out = new Uint8Array(len);
  const lut = new Int16Array(128).fill(-1);
  for (let i = 0; i < 64; i++) lut[B64.charCodeAt(i)] = i;
  let o = 0;
  for (let i = 0; i < clean.length; i += 4) {
    const a = lut[clean.charCodeAt(i)], b = lut[clean.charCodeAt(i + 1)];
    const c = i + 2 < clean.length ? lut[clean.charCodeAt(i + 2)] : 0;
    const d = i + 3 < clean.length ? lut[clean.charCodeAt(i + 3)] : 0;
    const n = (a << 18) | (b << 12) | (c << 6) | d;
    if (o < len) out[o++] = (n >> 16) & 255;
    if (o < len && i + 2 < clean.length) out[o++] = (n >> 8) & 255;
    if (o < len && i + 3 < clean.length) out[o++] = n & 255;
  }
  return out.subarray(0, o);
}

type Tagged = { $t: 'f32' | 'u8' | 'u32'; b64: string };

function encodeValue(v: unknown): unknown {
  if (v instanceof Float32Array) return { $t: 'f32', b64: bytesToBase64(new Uint8Array(v.buffer, v.byteOffset, v.byteLength)) } satisfies Tagged;
  if (v instanceof Uint32Array) return { $t: 'u32', b64: bytesToBase64(new Uint8Array(v.buffer, v.byteOffset, v.byteLength)) } satisfies Tagged;
  if (v instanceof Uint8Array) return { $t: 'u8', b64: bytesToBase64(v) } satisfies Tagged;
  if (Array.isArray(v)) return v.map(encodeValue);
  if (v && typeof v === 'object') {
    const o: Record<string, unknown> = {};
    for (const [k, x] of Object.entries(v)) o[k] = encodeValue(x);
    return o;
  }
  return v;
}

function decodeValue(v: unknown): unknown {
  if (v && typeof v === 'object' && !Array.isArray(v) && '$t' in (v as Record<string, unknown>)) {
    const t = v as Tagged;
    const bytes = base64ToBytes(t.b64);
    const copy = new Uint8Array(bytes.length);
    copy.set(bytes);
    if (t.$t === 'f32') return new Float32Array(copy.buffer, 0, copy.length / 4);
    if (t.$t === 'u32') return new Uint32Array(copy.buffer, 0, copy.length / 4);
    return copy;
  }
  if (Array.isArray(v)) return v.map(decodeValue);
  if (v && typeof v === 'object') {
    const o: Record<string, unknown> = {};
    for (const [k, x] of Object.entries(v)) o[k] = decodeValue(x);
    return o;
  }
  return v;
}

export interface ExportFile {
  format: 'tunealong-library';
  version: 1;
  exportedAt: string;
  songs: unknown[];
}

export function exportSongs(songs: SongRecord[]): string {
  const file: ExportFile = { format: 'tunealong-library', version: 1, exportedAt: new Date().toISOString(), songs: songs.map(encodeValue) };
  return JSON.stringify(file);
}

export function importSongs(json: string): SongRecord[] {
  const data = JSON.parse(json) as Partial<ExportFile>;
  if (data.format !== 'tunealong-library' || !Array.isArray(data.songs)) throw new Error('Not a TuneAlong library file');
  return data.songs.map((s) => {
    const song = decodeValue(s) as SongRecord;
    if (!song.id || !(song.fp?.hashes instanceof Uint32Array)) throw new Error('Song entry is damaged');
    return song;
  });
}

/** Lyrics (lyric time) → song time helpers. */
export function lyricToSongTime(song: Pick<SongRecord, 'lyricsOffset'>, t: number): number {
  return t - song.lyricsOffset;
}
