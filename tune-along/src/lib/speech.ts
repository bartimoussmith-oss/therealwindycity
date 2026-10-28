/**
 * Optional "write down the words" using the browser's speech recogniser.
 * Experimental by nature: speech engines are trained on talking, not singing over a
 * band, so results are rough. Where the browser supports it, recognition is told to
 * stay on the device (processLocally) and to listen to the captured track rather
 * than the default microphone.
 */
type AnyRec = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  processLocally?: boolean;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(track?: MediaStreamTrack): void;
  stop(): void;
  abort(): void;
};
type RecCtor = (new () => AnyRec) & { available?: (o: { langs: string[]; processLocally: boolean }) => Promise<string> };

function ctor(): RecCtor | null {
  const w = globalThis as unknown as { SpeechRecognition?: RecCtor; webkitSpeechRecognition?: RecCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function speechSupported(): boolean {
  return ctor() !== null;
}

export interface Transcriber {
  stop(): void;
  local: boolean;
}

export async function startTranscription(
  track: MediaStreamTrack | null,
  onText: (text: string, final: boolean) => void,
  onError: (msg: string) => void,
): Promise<Transcriber | null> {
  const C = ctor();
  if (!C) return null;
  const lang = (globalThis.navigator?.language || 'en-US');
  let local = false;
  try {
    if (typeof C.available === 'function') local = (await C.available({ langs: [lang], processLocally: true })) === 'available';
  } catch { local = false; }
  let stopped = false;
  let rec: AnyRec | null = null;
  const begin = () => {
    rec = new C();
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = true;
    if (local && 'processLocally' in rec) rec.processLocally = true;
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        onText(r[0].transcript.trim(), r.isFinal);
      }
    };
    rec.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return;
      onError(e.error === 'not-allowed' ? 'Speech recognition was blocked by the browser.' : `Speech recognition: ${e.error}`);
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') stopped = true;
    };
    rec.onend = () => { if (!stopped) setTimeout(begin, 250); }; // engines stop after pauses; keep going
    try {
      if (track) rec.start(track); else rec.start();
    } catch {
      try { rec.start(); } catch (err) { onError(String(err)); stopped = true; }
    }
  };
  begin();
  return {
    local,
    stop() {
      stopped = true;
      try { rec?.abort(); } catch { /* ignore */ }
    },
  };
}
