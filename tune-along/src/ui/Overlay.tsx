/**
 * The "overlay": a small always-on-top window with the current/next chord and the
 * current line of words, so TuneAlong can sit over a music app.
 *  - Desktop Chrome/Edge (116+) and Firefox (151+): Document Picture-in-Picture.
 *  - Elsewhere (incl. Android Chrome, iOS Safari): a canvas rendered into a video
 *    shown picture-in-picture, where the browser supports it.
 */
import { createRoot } from 'react-dom/client';
import { chordAt, stateToChord, type Chord } from '../dsp/chords';
import { getTuning } from '../dsp/tuning';
import { makeLabeler, songPrefs, defaultPrefs, type Labeler } from '../app/labels';
import { live, songTimeNow, type LiveState } from '../app/session';
import { library } from '../lib/library';
import type { SongRecord } from '../lib/songModel';
import { useStore } from '../lib/store';
import { buildSheet } from '../music/sheet';
import { prettyChord, useAnimationClock } from './widgets';

interface OverlayModel {
  title: string;
  now: string;
  nowSub: string;
  next: string;
  countdown: number | null;
  line: string;
  chordLine: string;
  tuning: string;
}

const sheetCache = new WeakMap<SongRecord, { key: string; sheet: ReturnType<typeof buildSheet> }>();

function model(s: LiveState, songs: SongRecord[]): OverlayModel {
  const song = s.match ? songs.find((x) => x.id === s.match!.songId) ?? null : null;
  const prefs = song ? songPrefs(song) : defaultPrefs(s.tuning);
  const labeler: Labeler = makeLabeler(song?.key ?? s.key, prefs);
  const report = song?.tuning ?? s.tuning;
  const tuning = report && report.basedOnSec >= 4 ? `${getTuning(report.candidates[0].id).short} · A=${report.refHz.toFixed(1)}` : 'Tuning: listening…';
  const out: OverlayModel = { title: song ? song.title : s.music ? 'Learning a new song…' : 'Waiting for music…', now: '—', nowSub: '', next: '', countdown: null, line: '', chordLine: '', tuning };
  const t = songTimeNow(s);
  let cur: Chord | null = null;
  if (song && t !== null) {
    const i = chordAt(song.chords, t);
    cur = i >= 0 ? song.chords[i] : null;
    const nxt = song.chords.slice(Math.max(0, i + 1)).find((c) => c.type !== 'N' && c.start > t);
    if (nxt) { out.next = prettyChord(labeler.label(nxt)); out.countdown = nxt.start - t; }
    if (song.lyrics) {
      const key = `${prefs.mode}|${prefs.capo}|${prefs.tuningId}|${song.lyricsOffset}|${song.updatedAt}`;
      let cached = sheetCache.get(song);
      if (!cached || cached.key !== key) {
        cached = { key, sheet: buildSheet(song.chords, song.lyrics.lines, { label: (c) => labeler.label(c), lyricsOffset: song.lyricsOffset }) };
        sheetCache.set(song, cached);
      }
      const lines = cached.sheet.filter((l) => l.kind === 'lyric');
      const line = [...lines].reverse().find((l) => l.t <= t + 0.15);
      if (line) {
        out.line = line.text;
        let row = '';
        for (const c of line.chords) { if (row.length < c.col) row = row.padEnd(c.col); row += c.label + ' '; }
        out.chordLine = prettyChord(row.trimEnd());
      }
    }
  } else if (s.frame && s.music) {
    cur = stateToChord(s.frame.state);
  }
  if (cur) { out.now = prettyChord(labeler.label(cur)); out.nowSub = prettyChord(labeler.sub(cur)); }
  return out;
}

function OverlayContent() {
  const s = useStore(live, (x) => x);
  const songs = useStore(library, (x) => x.songs);
  useAnimationClock(true, 15);
  const m = model(s, songs);
  return (
    <div className="overlay">
      <div className="ov-top"><span className="ov-title">{m.title}</span><span className="ov-tuning">{m.tuning}</span></div>
      <div className="ov-chords">
        <div className="ov-now"><span className="ov-label">{m.now}</span>{m.nowSub && <small>{m.nowSub}</small>}</div>
        {m.next && <div className="ov-next"><small>next</small><span>{m.next}</span>{m.countdown !== null && <small>{m.countdown.toFixed(1)} s</small>}</div>}
      </div>
      {m.line && <div className="ov-line"><pre className="chords">{m.chordLine}</pre><pre className="words">{m.line}</pre></div>}
    </div>
  );
}

type DocPip = { requestWindow(o: { width: number; height: number }): Promise<Window> };

export function overlaySupport(): 'document' | 'video' | 'none' {
  if (typeof window === 'undefined') return 'none';
  if ('documentPictureInPicture' in window) return 'document';
  const canvasOk = typeof HTMLCanvasElement !== 'undefined' && 'captureStream' in HTMLCanvasElement.prototype;
  if (canvasOk && (document as Document & { pictureInPictureEnabled?: boolean }).pictureInPictureEnabled) return 'video';
  return 'none';
}

let pipWindow: Window | null = null;
let videoPip: { video: HTMLVideoElement; timer: number } | null = null;

export async function openOverlay(): Promise<void> {
  const mode = overlaySupport();
  if (mode === 'document') {
    if (pipWindow && !pipWindow.closed) { pipWindow.focus(); return; }
    const dpip = (window as unknown as { documentPictureInPicture: DocPip }).documentPictureInPicture;
    const win = await dpip.requestWindow({ width: 420, height: 230 });
    pipWindow = win;
    for (const sheet of Array.from(document.styleSheets)) {
      try {
        const style = win.document.createElement('style');
        style.textContent = Array.from(sheet.cssRules).map((r) => r.cssText).join('\n');
        win.document.head.appendChild(style);
      } catch {
        if (sheet.href) {
          const link = win.document.createElement('link');
          link.rel = 'stylesheet';
          link.href = sheet.href;
          win.document.head.appendChild(link);
        }
      }
    }
    win.document.title = 'TuneAlong';
    win.document.body.className = 'pip-body';
    const host = win.document.createElement('div');
    win.document.body.appendChild(host);
    const root = createRoot(host);
    root.render(<OverlayContent />);
    win.addEventListener('pagehide', () => { root.unmount(); pipWindow = null; });
    return;
  }
  if (mode === 'video') {
    if (videoPip) { await videoPip.video.requestPictureInPicture().catch(() => undefined); return; }
    const canvas = document.createElement('canvas');
    canvas.width = 640; canvas.height = 360;
    const g = canvas.getContext('2d')!;
    const draw = () => {
      const m = model(live.get(), library.get().songs);
      g.fillStyle = '#0b0d12'; g.fillRect(0, 0, 640, 360);
      g.fillStyle = '#9aa3b5'; g.font = '600 24px system-ui, sans-serif'; g.fillText(m.title.slice(0, 40), 24, 40);
      g.textAlign = 'right'; g.fillText(m.tuning, 616, 40); g.textAlign = 'left';
      g.fillStyle = '#ffb648'; g.font = '800 120px system-ui, sans-serif'; g.fillText(m.now, 24, 170);
      if (m.nowSub) { g.fillStyle = '#9aa3b5'; g.font = '500 24px system-ui'; g.fillText(m.nowSub, 28, 205); }
      if (m.next) {
        g.fillStyle = '#8ab4ff'; g.font = '700 64px system-ui'; g.textAlign = 'right'; g.fillText(m.next, 616, 160);
        if (m.countdown !== null) { g.font = '500 24px system-ui'; g.fillText(`next in ${m.countdown.toFixed(1)} s`, 616, 200); }
        g.textAlign = 'left';
      }
      g.fillStyle = '#ffb648'; g.font = '700 26px ui-monospace, monospace'; g.fillText(m.chordLine.slice(0, 44), 24, 280);
      g.fillStyle = '#eef1f7'; g.font = '500 26px ui-monospace, monospace'; g.fillText(m.line.slice(0, 44), 24, 316);
    };
    draw();
    const video = document.createElement('video');
    video.muted = true;
    video.playsInline = true;
    video.srcObject = (canvas as HTMLCanvasElement & { captureStream(fps: number): MediaStream }).captureStream(10);
    await video.play();
    const timer = window.setInterval(draw, 120);
    videoPip = { video, timer };
    video.addEventListener('leavepictureinpicture', () => { if (videoPip) { clearInterval(videoPip.timer); videoPip = null; } });
    await video.requestPictureInPicture();
  }
}
