/** Minimal promise wrapper around IndexedDB for the song library. */
import type { SongRecord } from './songModel';

const DB_NAME = 'tunealong';
const STORE = 'songs';
const VERSION = 1;

let dbPromise: Promise<IDBDatabase> | null = null;

function open(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') { reject(new Error('IndexedDB is not available in this browser')); return; }
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE, { keyPath: 'id' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('Could not open the song library'));
  });
  return dbPromise;
}

function tx<T>(mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return open().then(
    (db) =>
      new Promise<T>((resolve, reject) => {
        const t = db.transaction(STORE, mode);
        const req = run(t.objectStore(STORE));
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      }),
  );
}

export const songDb = {
  all: () => tx<SongRecord[]>('readonly', (s) => s.getAll() as IDBRequest<SongRecord[]>),
  put: (song: SongRecord) => tx<IDBValidKey>('readwrite', (s) => s.put(song)),
  remove: (id: string) => tx<undefined>('readwrite', (s) => s.delete(id) as IDBRequest<undefined>),
  clear: () => tx<undefined>('readwrite', (s) => s.clear() as IDBRequest<undefined>),
};
