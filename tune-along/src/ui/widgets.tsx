import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import type { Chord, ChordSegment } from '../dsp/chords';
import type { KeyResult } from '../dsp/key';
import { midiName, pcName, spellingForKey } from '../dsp/notes';
import { TUNINGS, getTuning, stringNames, type TuningReport } from '../dsp/tuning';
import type { Labeler, DisplayPrefs } from '../app/labels';
import { buildSheet, type SheetLine } from '../music/sheet';
import type { LyricLine } from '../lib/songModel';
import { ChordDiagram } from './ChordDiagram';

/** Re-renders every animation frame while `active`; returns performance.now(). */
export function useAnimationClock(active: boolean, fps = 30): number {
  const [t, setT] = useState(() => performance.now());
  useEffect(() => {
    if (!active) return;
    let raf = 0;
    let last = 0;
    const tick = (now: number) => {
      if (now - last >= 1000 / fps) { last = now; setT(now); }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active, fps]);
  return t;
}

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const p: Record<string, ReactNode> = {
    mic: <><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>,
    tab: <><rect x="3" y="4" width="18" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></>,
    file: <><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z" /><path d="M14 3v5h5M10 17a2 2 0 1 1-2-2V10l5-1v6" /></>,
    play: <path d="M7 4l13 8-13 8z" />,
    stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
    songs: <><path d="M9 18V5l11-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="17" cy="16" r="3" /></>,
    tuner: <><path d="M4 16a8 8 0 0 1 16 0" /><path d="M12 16l4-6" /><circle cx="12" cy="16" r="1.5" /></>,
    help: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7M12 17h.01" /></>,
    listen: <><path d="M3 12h2l2-6 3 12 3-9 2 6 2-3h4" /></>,
    pip: <><rect x="3" y="5" width="18" height="14" rx="2" /><rect x="12" y="11" width="7" height="6" rx="1" /></>,
    print: <><path d="M6 9V3h12v6" /><rect x="3" y="9" width="18" height="8" rx="2" /><path d="M6 14h12v7H6z" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></>,
    back: <path d="M15 5l-7 7 7 7" />,
    trash: <><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></>,
    download: <><path d="M12 3v12M7 10l5 5 5-5M4 21h16" /></>,
    upload: <><path d="M12 21V9M7 14l5-5 5 5M4 3h16" /></>,
    check: <path d="M5 12l5 5 9-10" />,
    sound: <><path d="M4 9h4l5-4v14l-5-4H4z" /><path d="M17 8a5 5 0 0 1 0 8" /></>,
    x: <path d="M6 6l12 12M18 6L6 18" />,
  };
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {p[name] ?? null}
    </svg>
  );
}

/** Never print 100 % for something that is inferred. */
function pct(p: number): string {
  return `${Math.min(99, Math.round(p * 100))}%`;
}

function sureness(p: number): string {
  return p >= 0.9 ? 'very likely' : p >= 0.6 ? 'likely' : 'best guess';
}

export function TuningCard({ report, keyResult, bpm, onTune, compact = false, learning = false }: {
  report: TuningReport | null;
  keyResult: KeyResult | null;
  bpm: number | null;
  onTune?: () => void;
  compact?: boolean;
  learning?: boolean;
}) {
  const [why, setWhy] = useState(false);
  if (!report || report.basedOnSec < 4) {
    return (
      <section className={`card tuning-card ${compact ? 'compact' : ''}`} aria-live="polite">
        <div className="tuning-head"><span className="eyebrow">Tuning</span></div>
        <p className="muted">Listening for the tuning… it needs about 5–10 seconds of music.</p>
      </section>
    );
  }
  const top = report.candidates[0];
  const tuning = getTuning(top.id);
  const flatSharp = Math.abs(report.cents) < 6 ? 'standard pitch' : `${report.cents > 0 ? '+' : '−'}${Math.abs(report.cents).toFixed(0)}¢`;
  const early = report.basedOnSec < 12;
  const spelling = spellingForKey(keyResult?.tonic, keyResult?.mode);
  return (
    <section className={`card tuning-card ${compact ? 'compact' : ''}`} aria-live="polite">
      <div className="tuning-head">
        <span className="eyebrow">Tune to {learning || early ? <em className="tag">{early ? 'early guess' : 'estimate'}</em> : null}</span>
        {onTune && <button className="btn small" onClick={onTune}><Icon name="tuner" size={16} /> Tuner</button>}
      </div>
      <div className="tuning-main">
        <div>
          <div className="tuning-name">{tuning.short}</div>
          <div className="tuning-strings">{stringNames(tuning)}</div>
        </div>
        <div className="tuning-prob" title="How sure TuneAlong is about the guitar tuning">{pct(top.probability)}<small>{sureness(top.probability)}</small></div>
      </div>
      <div className="tuning-facts">
        <span title="Reference pitch of the recording"><b>A = {report.refHz.toFixed(1)} Hz</b> <small>({flatSharp})</small></span>
        {keyResult && <span>Key <b>{keyResult.label}</b></span>}
        {bpm && <span><b>{Math.round(bpm)}</b> BPM</span>}
        {report.capo && report.capo.capo > 0 && <span>Capo <b>{report.capo.capo}</b> = easier shapes</span>}
        {report.standardCapo && <span>or <b>Standard + capo {report.standardCapo.capo}</b></span>}
        {report.lowestStack !== null && !compact && <span>Lowest power chord <b>{midiName(report.lowestStack, spelling === 'common' ? 'flat' : spelling)}</b></span>}
      </div>
      {!compact && (
        <>
          <button className="linklike" onClick={() => setWhy(!why)} aria-expanded={why}>{why ? 'Hide' : 'Why?'} </button>
          {why && (
            <div className="why">
              <ul>{report.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              <p className="muted small">Other possibilities: {report.candidates.slice(1, 4).map((c) => `${getTuning(c.id).short} ${pct(c.probability)}`).join(' · ')}</p>
              <p className="muted small">Based on {Math.round(report.basedOnSec)} s of music. The reference pitch is measured; the guitar tuning is an informed guess from power chords below low E and which shapes fit the song.</p>
            </div>
          )}
        </>
      )}
    </section>
  );
}

export function ChordName({ chord, labeler, size = 'xl' }: { chord: Chord | null; labeler: Labeler; size?: 'xl' | 'lg' | 'md' }) {
  if (!chord) return <div className={`chord-name ${size} dim`}>—</div>;
  const label = labeler.label(chord);
  const sub = labeler.sub(chord);
  return (
    <div className={`chord-name ${size} ${chord.type === 'N' ? 'dim' : ''}`}>
      <span className="label">{prettyChord(label)}</span>
      {sub && <span className="sub">{prettyChord(sub)}</span>}
    </div>
  );
}

/**
 * Chord labels stay in plain ASCII (Eb, F#) like most chord charts: the ♭/♯ glyphs
 * are missing from some phone and printer fonts. Kept as one hook for styling.
 */
export function prettyChord(label: string): string {
  return label;
}

export function Diagram({ chord, labeler, size = 96 }: { chord: Chord | null; labeler: Labeler; size?: number }) {
  if (!chord || chord.type === 'N') return <div className="diagram-placeholder" style={{ width: size, height: size * 1.2 }} />;
  const s = labeler.shape(chord);
  if (!s) return null;
  return <ChordDiagram root={s.root} type={s.type} drop={s.drop} size={size} label={labeler.label(chord)} />;
}

export function ChordLane({ chords, now, labeler, before = 4, after = 10, height = 64 }: {
  chords: ChordSegment[];
  now: number;
  labeler: Labeler;
  before?: number;
  after?: number;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);
  const span = before + after;
  const pps = width / span;
  const x0 = before * pps;
  const visible = chords.filter((c) => c.end > now - before && c.start < now + after);
  return (
    <div className="chord-lane" ref={ref} style={{ height }} aria-hidden="true">
      {visible.map((c, i) => {
        const left = x0 + (c.start - now) * pps;
        const w = Math.max(2, (c.end - c.start) * pps - 3);
        const cur = c.start <= now && c.end > now;
        return (
          <div key={`${c.start}-${i}`} className={`lane-block ${cur ? 'current' : ''} ${c.type === 'N' ? 'nc' : ''} ${c.start > now ? 'future' : ''}`} style={{ left, width: w, paddingLeft: left < 0 ? Math.min(w - 24, -left + 8) : undefined }}>
            {w + Math.min(0, left) > 26 && c.type !== 'N' ? prettyChord(labeler.label(c)) : ''}
          </div>
        );
      })}
      <div className="lane-playhead" style={{ left: x0 }} />
    </div>
  );
}

export function ChromaBars({ chroma, keyResult, lowest, showLowest = false }: { chroma: number[] | null; keyResult: KeyResult | null; lowest: number | null; showLowest?: boolean }) {
  const sp = spellingForKey(keyResult?.tonic, keyResult?.mode);
  const max = chroma ? Math.max(1e-6, ...chroma) : 1;
  return (
    <div className="chroma">
      <div className="chroma-bars">
        {Array.from({ length: 12 }, (_, i) => (
          <div key={i} className="chroma-col">
            <div className="chroma-bar" style={{ height: `${chroma ? (100 * chroma[i]) / max : 0}%` }} />
            <span>{prettyChord(pcName(i, sp))}</span>
          </div>
        ))}
      </div>
      <div className="muted small">Notes heard right now{lowest !== null && showLowest ? ` · lowest ${midiName(lowest, sp === 'common' ? 'flat' : sp)}` : ''}</div>
    </div>
  );
}

export function DisplayControls({ prefs, onChange, report }: { prefs: DisplayPrefs; onChange: (p: DisplayPrefs) => void; report: TuningReport | null }) {
  const suggested = report?.capo?.capo ?? 0;
  const guitarTunings = TUNINGS.filter((t) => t.instrument === 'guitar' && t.down !== undefined && t.id !== 'seven-std');
  return (
    <div className="display-controls">
      <div className="seg" role="group" aria-label="Chord names">
        <button className={prefs.mode === 'sound' ? 'on' : ''} onClick={() => onChange({ ...prefs, mode: 'sound' })}>Sounding names</button>
        <button className={prefs.mode === 'shape' ? 'on' : ''} onClick={() => onChange({ ...prefs, mode: 'shape' })}>Shapes I play</button>
      </div>
      <label className="inline">
        My tuning
        <select value={prefs.tuningId} onChange={(e) => onChange({ ...prefs, tuningId: e.target.value })}>
          {guitarTunings.map((t) => <option key={t.id} value={t.id}>{t.short}</option>)}
        </select>
      </label>
      <div className="stepper" aria-label="Capo">
        <span>Capo</span>
        <button onClick={() => onChange({ ...prefs, capo: Math.max(0, prefs.capo - 1) })} aria-label="Capo down">−</button>
        <b>{prefs.capo}</b>
        <button onClick={() => onChange({ ...prefs, capo: Math.min(9, prefs.capo + 1) })} aria-label="Capo up">+</button>
        {suggested > 0 && prefs.capo !== suggested && <button className="btn small ghost" onClick={() => onChange({ ...prefs, capo: suggested, mode: 'shape' })}>Try capo {suggested}</button>}
      </div>
    </div>
  );
}

export function SheetLineView({ line, active = false }: { line: SheetLine; active?: boolean }) {
  if (line.kind === 'instrumental') {
    return <div className={`sheet-line instrumental ${active ? 'active' : ''}`}><pre className="chords">{prettyChord(line.text)}</pre></div>;
  }
  // build the chord row with absolute columns (monospace)
  let row = '';
  for (const c of line.chords) {
    if (row.length < c.col) row = row.padEnd(c.col);
    row += c.label + ' ';
  }
  return (
    <div className={`sheet-line ${active ? 'active' : ''}`}>
      <pre className="chords">{prettyChord(row.trimEnd()) || ' '}</pre>
      <pre className="words">{line.text}</pre>
    </div>
  );
}

export function useSheet(chords: ChordSegment[], lyrics: LyricLine[], labeler: Labeler, lyricsOffset: number): SheetLine[] {
  return useMemo(
    () => buildSheet(chords, lyrics, { label: (c) => labeler.label(c), lyricsOffset }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [chords, lyrics, lyricsOffset, labeler.prefs.mode, labeler.prefs.capo, labeler.prefs.tuningId, labeler.shift],
  );
}

export function LyricsLive({ sheet, now }: { sheet: SheetLine[]; now: number }) {
  let idx = -1;
  for (let i = 0; i < sheet.length; i++) if (sheet[i].t <= now + 0.15) idx = i;
  const start = Math.max(0, idx - 1);
  const rows = sheet.slice(start, start + 4);
  return (
    <div className="lyrics-live" aria-live="off">
      {rows.map((l, k) => (
        <SheetLineView key={`${l.t}-${k}`} line={l} active={start + k === idx} />
      ))}
      {idx >= sheet.length - 1 && sheet.length > 0 && now > sheet[sheet.length - 1].end + 2 && <p className="muted small">End of the words.</p>}
    </div>
  );
}
