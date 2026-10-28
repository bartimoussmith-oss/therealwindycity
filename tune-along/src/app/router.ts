/** Hash router: #/listen, #/songs, #/song/<id>, #/tuner, #/help */
import { useSyncExternalStore } from 'react';

function current(): string {
  const h = typeof location !== 'undefined' ? location.hash.replace(/^#/, '') : '';
  return h || '/listen';
}

export function navigate(path: string): void {
  if (current() !== path) location.hash = path;
}

function subscribe(cb: () => void): () => void {
  window.addEventListener('hashchange', cb);
  return () => window.removeEventListener('hashchange', cb);
}

export function useRoute(): string[] {
  const path = useSyncExternalStore(subscribe, current, () => '/listen');
  return path.split('/').filter(Boolean);
}
