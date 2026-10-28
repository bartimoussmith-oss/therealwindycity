/**
 * Audio plumbing: opens the requested input (microphone, a browser tab's audio,
 * an audio file or the built-in demo), routes it through the capture worklet and
 * hands the samples to the analysis worker.
 */
import type { ToWorker } from '../engine/protocol';
import { renderSong, type SongSpec } from './synth';

export type InputKind = 'mic' | 'tab' | 'file' | 'demo';

export interface CaptureHandle {
  kind: InputKind;
  sampleRate: number;
  /** The captured track (mic/tab) — used for optional speech recognition. */
  track: MediaStreamTrack | null;
  /** For file/demo: play (another) buffer into the running session. */
  play(buffer: AudioBuffer): void;
  stop(): void;
  ended: Promise<void>;
}

let ctx: AudioContext | null = null;
let workletReady: Promise<void> | null = null;

export function audioContext(): AudioContext {
  if (!ctx) {
    const AC = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    ctx = new AC({ latencyHint: 'interactive' });
  }
  return ctx;
}

async function ensureWorklet(c: AudioContext): Promise<void> {
  if (!workletReady) workletReady = c.audioWorklet.addModule(new URL('capture-worklet.js', document.baseURI).href);
  return workletReady;
}

export class CaptureError extends Error {}

async function openMic(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) throw new CaptureError('This browser cannot use the microphone (it needs HTTPS and a modern browser).');
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
      video: false,
    });
  } catch (err) {
    const name = (err as DOMException)?.name;
    if (name === 'NotAllowedError') throw new CaptureError('Microphone permission was denied. Allow the microphone for this site and try again.');
    if (name === 'NotFoundError') throw new CaptureError('No microphone was found.');
    throw new CaptureError(`Could not open the microphone (${name ?? err}).`);
  }
}

async function openTab(): Promise<MediaStream> {
  const md = navigator.mediaDevices as MediaDevices & { getDisplayMedia?: MediaDevices['getDisplayMedia'] };
  if (!md?.getDisplayMedia) throw new CaptureError('Capturing another tab’s audio needs desktop Chrome or Edge. Use the microphone instead.');
  let stream: MediaStream;
  try {
    stream = await md.getDisplayMedia({
      video: true,
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, suppressLocalAudioPlayback: false } as MediaTrackConstraints,
      // @ts-expect-error — Chrome-specific hints
      systemAudio: 'include',
      selfBrowserSurface: 'exclude',
    });
  } catch (err) {
    throw new CaptureError(`Screen/tab sharing was cancelled (${(err as DOMException)?.name ?? err}).`);
  }
  stream.getVideoTracks().forEach((t) => t.stop());
  if (stream.getAudioTracks().length === 0) {
    throw new CaptureError('No audio was shared. Pick a browser tab and switch on “Share tab audio”.');
  }
  return stream;
}

export async function decodeFile(file: File): Promise<AudioBuffer> {
  const c = audioContext();
  const data = await file.arrayBuffer();
  try {
    return await c.decodeAudioData(data);
  } catch {
    throw new CaptureError('That file could not be decoded as audio.');
  }
}

export function demoBuffer(spec: SongSpec): AudioBuffer {
  const c = audioContext();
  const pcm = renderSong(spec, c.sampleRate);
  const buf = c.createBuffer(1, pcm.length, c.sampleRate);
  buf.copyToChannel(pcm as Float32Array<ArrayBuffer>, 0);
  return buf;
}

/**
 * Starts capturing. `post` sends control messages to the worker; the audio itself
 * flows worklet → worker over a MessageChannel.
 */
export async function startCapture(
  kind: InputKind,
  worker: Worker,
  opts: { buffer?: AudioBuffer; monitor?: boolean } = {},
): Promise<CaptureHandle> {
  const c = audioContext();
  if (c.state === 'suspended') await c.resume();
  await ensureWorklet(c);

  let stream: MediaStream | null = null;
  if (kind === 'mic') stream = await openMic();
  if (kind === 'tab') stream = await openTab();

  const node = new AudioWorkletNode(c, 'tunealong-capture', {
    numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1], processorOptions: { chunkSize: 2048 },
  });
  const sink = c.createGain();
  sink.gain.value = 0;
  node.connect(sink).connect(c.destination);
  const channel = new MessageChannel();
  node.port.postMessage({ type: 'port', port: channel.port1 }, [channel.port1]);
  const startMsg: ToWorker = { type: 'session:start', sampleRate: c.sampleRate };
  worker.postMessage(startMsg);
  const portMsg: ToWorker = { type: 'audio-port', port: channel.port2 };
  worker.postMessage(portMsg, [channel.port2]);

  const sources: AudioNode[] = [];
  let resolveEnded: () => void = () => undefined;
  const ended = new Promise<void>((r) => (resolveEnded = r));
  let current: AudioBufferSourceNode | null = null;

  if (stream) {
    const src = c.createMediaStreamSource(stream);
    src.connect(node);
    sources.push(src);
    stream.getAudioTracks()[0].addEventListener('ended', () => resolveEnded());
  }

  const play = (buffer: AudioBuffer) => {
    try { current?.stop(); } catch { /* already stopped */ }
    const src = c.createBufferSource();
    src.buffer = buffer;
    src.connect(node);
    if (opts.monitor !== false) src.connect(c.destination);
    src.onended = () => { if (current === src) resolveEnded(); };
    src.start();
    current = src;
    sources.push(src);
  };
  if (opts.buffer) play(opts.buffer);

  return {
    kind,
    sampleRate: c.sampleRate,
    track: stream?.getAudioTracks()[0] ?? null,
    play,
    ended,
    stop() {
      try { current?.stop(); } catch { /* ignore */ }
      sources.forEach((s) => { try { s.disconnect(); } catch { /* ignore */ } });
      node.port.postMessage({ type: 'stop' });
      try { node.disconnect(); sink.disconnect(); } catch { /* ignore */ }
      stream?.getTracks().forEach((t) => t.stop());
      resolveEnded();
    },
  };
}
