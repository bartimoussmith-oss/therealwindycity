/** LRC (timestamped lyrics) parsing and formatting. */
import type { LyricLine } from '../lib/songModel';

const TAG = /\[(\d{1,3}):(\d{1,2}(?:[.:]\d{1,3})?)\]/g;

export function parseLrc(text: string): LyricLine[] {
  const out: LyricLine[] = [];
  let offsetMs = 0;
  for (const raw of text.split(/\r?\n/)) {
    const off = /^\[offset:\s*([+-]?\d+)\]/i.exec(raw.trim());
    if (off) { offsetMs = Number(off[1]); continue; }
    const times: number[] = [];
    let m: RegExpExecArray | null;
    TAG.lastIndex = 0;
    let last = 0;
    while ((m = TAG.exec(raw))) {
      if (m.index !== last) break; // tags must lead the line
      times.push(Number(m[1]) * 60 + Number(m[2].replace(':', '.')));
      last = TAG.lastIndex;
    }
    if (!times.length) continue;
    const words = raw.slice(last).replace(/<\d{1,3}:\d{1,2}(?:\.\d{1,3})?>/g, '').trim();
    for (const t of times) out.push({ t: Math.max(0, t - offsetMs / 1000), text: words });
  }
  return out.sort((a, b) => a.t - b.t);
}

export function isLrc(text: string): boolean {
  return /^\s*\[\d{1,3}:\d{1,2}([.:]\d{1,3})?\]/m.test(text);
}

export function formatTime(t: number): string {
  const s = Math.max(0, t);
  const mm = Math.floor(s / 60);
  const ss = s - mm * 60;
  return `${String(mm).padStart(2, '0')}:${ss.toFixed(2).padStart(5, '0')}`;
}

export function formatLrc(lines: LyricLine[], meta: { title?: string; artist?: string } = {}): string {
  const head: string[] = [];
  if (meta.title) head.push(`[ti:${meta.title}]`);
  if (meta.artist) head.push(`[ar:${meta.artist}]`);
  return [...head, ...lines.map((l) => `[${formatTime(l.t)}]${l.text}`)].join('\n');
}

/** Plain lyrics (no timestamps) → evenly spread placeholder timing across a span. */
export function plainToLines(text: string, start: number, end: number): LyricLine[] {
  const rows = text.split(/\r?\n/).map((s) => s.trim());
  const sung = rows.filter((r) => r.length > 0);
  if (!sung.length) return [];
  const step = (end - start) / sung.length;
  return sung.map((text, i) => ({ t: start + i * step, text }));
}
