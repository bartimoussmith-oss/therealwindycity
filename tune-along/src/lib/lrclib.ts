/**
 * LRCLIB (https://lrclib.net) — free, community-maintained lyrics with timestamps.
 * No API key; CORS is open and the `Lrclib-Client` header is on its allow-list.
 * NOTE: community-contributed lyrics are fine for personal use; a commercial
 * release needs licensed lyrics (see docs/STRATEGY-MEMO.md).
 */
const BASE = 'https://lrclib.net/api';
const CLIENT = 'TuneAlong v0.1 (https://github.com/bartimoussmith-oss/therealwindycity/tree/main/tune-along)';

export interface LrclibTrack {
  id: number;
  trackName: string;
  artistName: string;
  albumName: string | null;
  duration: number | null;
  instrumental: boolean;
  plainLyrics: string | null;
  syncedLyrics: string | null;
}

async function call<T>(path: string, params: Record<string, string>): Promise<T | null> {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v.trim() !== '')).toString();
  const res = await fetch(`${BASE}${path}?${qs}`, { headers: { 'Lrclib-Client': CLIENT } });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Lyrics service answered ${res.status}`);
  return (await res.json()) as T;
}

export async function searchLyrics(title: string, artist: string): Promise<LrclibTrack[]> {
  const params: Record<string, string> = artist.trim() ? { track_name: title, artist_name: artist } : { q: title };
  const results = (await call<LrclibTrack[]>('/search', params)) ?? [];
  // synced first, then plain
  return results.sort((a, b) => Number(!!b.syncedLyrics) - Number(!!a.syncedLyrics)).slice(0, 12);
}

export async function getLyrics(title: string, artist: string, durationSec?: number): Promise<LrclibTrack | null> {
  const params: Record<string, string> = { track_name: title, artist_name: artist };
  if (durationSec && durationSec > 0) params.duration = String(Math.round(durationSec));
  return call<LrclibTrack>('/get', params);
}
