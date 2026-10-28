/** What the tuner should tune to (set from a song's tuning card). */
import { Store } from '../lib/store';

export interface TunerTarget {
  tuningId: string;
  refHz: number;
  fromSong: boolean;
}

export const tunerTarget = new Store<TunerTarget>({ tuningId: 'standard', refHz: 440, fromSong: false });

export function tuneTo(tuningId: string, refHz: number): void {
  tunerTarget.set({ tuningId, refHz: Math.round(refHz * 10) / 10, fromSong: true });
}
