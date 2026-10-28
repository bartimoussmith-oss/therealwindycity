/** In-memory song library backed by IndexedDB. */
import { songDb } from './db';
import { Store } from './store';
import { exportSongs, importSongs, type SongRecord } from './songModel';

export interface LibraryState {
  loaded: boolean;
  songs: SongRecord[];
  error: string | null;
}

export const library = new Store<LibraryState>({ loaded: false, songs: [], error: null });

function sorted(songs: SongRecord[]): SongRecord[] {
  return [...songs].sort((a, b) => b.lastHeardAt - a.lastHeardAt);
}

export async function loadLibrary(): Promise<SongRecord[]> {
  try {
    const songs = await songDb.all();
    library.set({ loaded: true, songs: sorted(songs), error: null });
    return songs;
  } catch (err) {
    library.set({ loaded: true, songs: [], error: err instanceof Error ? err.message : String(err) });
    return [];
  }
}

export async function saveSong(song: SongRecord): Promise<void> {
  const songs = library.get().songs.filter((s) => s.id !== song.id);
  library.set({ songs: sorted([song, ...songs]) });
  try {
    await songDb.put(song);
  } catch (err) {
    library.set({ error: `Could not save "${song.title}": ${err instanceof Error ? err.message : String(err)}` });
  }
}

export async function updateSong(id: string, patch: Partial<SongRecord>): Promise<SongRecord | null> {
  const cur = getSong(id);
  if (!cur) return null;
  const next = { ...cur, ...patch, updatedAt: Date.now() };
  await saveSong(next);
  return next;
}

export async function deleteSong(id: string): Promise<void> {
  library.set({ songs: library.get().songs.filter((s) => s.id !== id) });
  await songDb.remove(id).catch(() => undefined);
}

export function getSong(id: string): SongRecord | undefined {
  return library.get().songs.find((s) => s.id === id);
}

export function exportLibrary(ids?: string[]): string {
  const songs = library.get().songs.filter((s) => !ids || ids.includes(s.id));
  return exportSongs(songs);
}

export async function importLibrary(json: string): Promise<SongRecord[]> {
  const songs = importSongs(json);
  for (const s of songs) await saveSong(s);
  return songs;
}
